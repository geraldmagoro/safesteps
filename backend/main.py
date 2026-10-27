"""SafeSteps backend (FastAPI) — hackathon MVP.

Endpoints:
  POST /ingest                  band readings -> anomaly detection -> alert
  GET  /children/{child_id}/status   latest reading + status
  WS   /ws/alerts               live alert broadcast
  POST /routes  GET /routes     favorite routes (+ pre-populated EMS cache)
  POST /schedule  GET /schedule/{date}   daily route schedule
  POST /children/{id}/profile   child/parent/contact profile for EMS calls
  POST /alerts/{id}/ack  GET /alerts/{id}   ack tracking + EMS escalation

Run:
  python -m venv .venv
  .venv\\Scripts\\activate            (Windows)
  pip install -r backend/requirements.txt
  uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="SafeSteps backend (MVP)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALERT_FILE = Path(__file__).parent / "alert.json"
ROUTES_FILE = Path(__file__).parent / "routes.json"
CHILDREN_FILE = Path(__file__).parent / "children.json"
EMS_FILE = Path(__file__).parent / "ems_call.json"

# ---------------------------------------------------------------- route model
# Home -> Spaza (left turn) -> School. Must match band-simulator/simulate.py.
HOME = (-26.2485, 27.8540)
SPAZA = (-26.2470, 27.8525)
SCHOOL = (-26.2455, 27.8535)
ROUTE = [HOME, SPAZA, SCHOOL]

OFF_ROUTE_DIST_M = 2.0       # more than 2 m from the route polyline
OFF_ROUTE_SECS = 5 * 60      # ... for more than 5 minutes
SKIN_OFF_CM = 2.5            # skin_distance_cm above this = band off skin
HR_SPIKE = 130               # hr above this + no movement = possible distress
STILL_M = 2.0                # consecutive pings closer than this = no movement
EARLIEST_HOUR = int(os.getenv("SAFESTEPS_EARLIEST_HOUR", "6"))  # departures before this local hour = early departure

ACTIONS = ["notify 5 contacts", "SMS fallback", "community alert 500m"]
MODEL_NAME = os.getenv("META_MODEL", "muse-wonder-1.0")
ACK_TIMEOUT_SECS = int(os.getenv("SAFESTEPS_ACK_TIMEOUT_SECS", "300"))  # 5 min no-ack -> EMS


class Reading(BaseModel):
    child_id: str
    gps_lat: float
    gps_lon: float
    hr: int = Field(ge=0, le=250)
    skin_distance_cm: float = Field(ge=0)
    battery: int = Field(ge=0, le=100)
    water_depth_cm: float = Field(default=0.0, ge=0)   # 0 = dry
    water_time_sec: float = Field(default=0.0, ge=0)   # continuous submersion


class ChildState(BaseModel):
    child_id: str
    last: Optional[Reading] = None
    last_seen: Optional[str] = None
    off_route_since: Optional[float] = None
    off_route_hits: int = 0
    off_route_m: float = 0.0
    early_flag_dates: List[str] = Field(default_factory=list)
    last_alert: Optional[dict] = None
    water_watch: bool = False


store: Dict[str, ChildState] = {}


def _state(child_id: str) -> ChildState:
    st = store.get(child_id)
    if st is None:
        st = ChildState(child_id=child_id)
        store[child_id] = st
    return st


# --------------------------------------------------------------- geo helpers
def _haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _dist_to_route_m(lat: float, lon: float) -> float:
    """Min distance (m) from a point to the ROUTE polyline (equirect approx)."""
    lat0 = math.radians(lat)
    kx = 111320.0 * math.cos(lat0)
    ky = 110540.0
    px, py = lon * kx, lat * ky
    best = float("inf")
    for (a_lat, a_lon), (b_lat, b_lon) in zip(ROUTE, ROUTE[1:]):
        ax, ay = a_lon * kx, a_lat * ky
        bx, by = b_lon * kx, b_lat * ky
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = ((px - ax) * dx + (py - ay) * dy) / seg2 if seg2 else 0.0
        t = max(0.0, min(1.0, t))
        cx, cy = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(px - cx, py - cy))
    return best


# ------------------------------------------------------------------ AI summary
def ai_summarize(alert_type: str, reading: Reading, detail: str) -> str:
    """Summarize risk via the Meta Model API when configured, else heuristic."""
    fallback = (
        f"[{MODEL_NAME} offline] {alert_type}: child {reading.child_id} at "
        f"({reading.gps_lat:.5f}, {reading.gps_lon:.5f}), HR {reading.hr}, "
        f"skin gap {reading.skin_distance_cm}cm. {detail} "
        f"Set META_API_KEY + META_API_URL for a live AI summary."
    )
    api_key = os.getenv("META_API_KEY")
    api_url = os.getenv("META_API_URL")  # no default: never guess the endpoint
    if not api_key or not api_url:
        return fallback
    prompt = (
        f"You are a child-safety assistant. Alert type: {alert_type}. Detail: {detail}. "
        f"Reading: child={reading.child_id} lat={reading.gps_lat} lon={reading.gps_lon} "
        f"hr={reading.hr} skin_distance_cm={reading.skin_distance_cm} "
        f"battery={reading.battery}. Summarize the risk in 2 sentences and "
        f"suggest the single most urgent action."
    )
    body = json.dumps({"model": MODEL_NAME, "prompt": prompt}).encode()
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode() or "{}")
        for key in ("summary", "text", "output", "result"):
            if isinstance(data.get(key), str) and data[key].strip():
                return data[key].strip()
        return fallback + f" (model reply had no text field: {str(data)[:200]})"
    except Exception as exc:  # offline demo must never crash on AI call
        return fallback + f" (live call failed: {exc})"


# ------------------------------------------------------------- websocket fans
class _AlertsHub:
    def __init__(self) -> None:
        self.clients: List[WebSocket] = []

    async def broadcast(self, payload: dict) -> None:
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.clients:
                self.clients.remove(ws)


hub = _AlertsHub()


def _write_alert_file(payload: dict) -> None:
    record = dict(payload)
    record["bursts"] = {
        # 20 s burst placeholders: real band uploads clips here.
        "audio_20s": "placeholder: 20s audio burst not captured in MVP",
        "video_20s": "placeholder: 20s video burst not captured in MVP",
    }
    ALERT_FILE.write_text(json.dumps(record, indent=2))


# --------------------------------------------- favorite routes + EMS + ack store
class RouteIn(BaseModel):
    name: str
    waypoints: List[List[float]] = Field(default_factory=list)
    destination: str = ""
    arrival: str = ""
    departure: str = ""
    supervisor_contacts: List[str] = Field(default_factory=list)


class Route(RouteIn):
    id: str


class DaySchedule(BaseModel):
    date: str  # YYYY-MM-DD
    route_id: str


class EMSCache(BaseModel):
    route_id: str
    nearest_saps: str
    clinic: str
    hospital: str
    phone: str
    sms: str


class ChildProfile(BaseModel):
    full_name: str = ""
    age: int = 0
    parent_name: str = ""
    contacts: List[str] = Field(default_factory=list)
    profile_link: str = ""


# alert_id -> alert payload + ack tracking (in-memory; ems_call.json on disk)
alerts: Dict[str, dict] = {}


def _load_routes_file() -> dict:
    try:
        data = json.loads(ROUTES_FILE.read_text())
        if isinstance(data, dict):
            data.setdefault("routes", [])
            data.setdefault("schedules", {})
            data.setdefault("ems_cache", {})
            return data
        if isinstance(data, list):  # legacy: bare route list
            return {"routes": data, "schedules": {}, "ems_cache": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"routes": [], "schedules": {}, "ems_cache": {}}


def _save_routes_file(data: dict) -> None:
    ROUTES_FILE.write_text(json.dumps(data, indent=2))


def _load_children() -> dict:
    try:
        data = json.loads(CHILDREN_FILE.read_text())
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def _save_children(data: dict) -> None:
    CHILDREN_FILE.write_text(json.dumps(data, indent=2))


def _mock_ems(route_id: str = "", destination: str = "") -> dict:
    near = f" near {destination}" if destination else ""
    return EMSCache(
        route_id=route_id,
        nearest_saps="SAPS 10111 (Orlando SAPS, +27118761010)",
        clinic=f"Chiawelo Clinic{near} (+27111301001)",
        hospital="Chris Hani Baragwanath Hospital (+27119399111)",
        phone="10111",
        sms="+27118761010",
    ).model_dump()


def _primary_ems() -> dict:
    cache = _load_routes_file().get("ems_cache", {})
    if cache:
        return next(iter(cache.values()))
    return _mock_ems()


def _build_ems_payload(alert_id: str, rec: dict) -> dict:
    profile = _load_children().get(rec.get("child_id", ""), {})
    return {
        "alert_id": alert_id,
        "type": "ems_escalation",
        "child_full_name": profile.get("full_name") or "unknown",
        "child_id": rec.get("child_id"),
        "age": profile.get("age", 0),
        "parent": profile.get("parent_name") or "unknown",
        "contacts": profile.get("contacts", []),
        "location": rec.get("location", {}),
        "nature": f"{rec.get('type')}: {rec.get('detail', '')}",
        "profile_link": profile.get("profile_link")
        or f"/children/{rec.get('child_id')}/status",
        "ems": _primary_ems(),
        "original_alert_at": rec.get("timestamp"),
        "escalated_at": datetime.now(timezone.utc).isoformat(),
    }


def _check_ems_escalations(now_ts: float) -> List[dict]:
    """Sync sweep: unacked alerts older than ACK_TIMEOUT_SECS trigger EMS."""
    escalated: List[dict] = []
    for alert_id, rec in alerts.items():
        if rec.get("acked") or rec.get("ems_triggered"):
            continue
        if now_ts - rec.get("created_ts", now_ts) < ACK_TIMEOUT_SECS:
            continue
        rec["ems_triggered"] = True
        payload = _build_ems_payload(alert_id, rec)
        EMS_FILE.write_text(json.dumps(payload, indent=2))
        escalated.append(payload)
    return escalated


# ------------------------------------------------------------------ endpoints
@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": MODEL_NAME, "children": len(store)}


@app.get("/route")
def route() -> dict:
    return {
        "home": HOME,
        "spaza": SPAZA,
        "school": SCHOOL,
        "off_route_dist_m": OFF_ROUTE_DIST_M,
        "off_route_secs": OFF_ROUTE_SECS,
    }


@app.post("/ingest")
async def ingest(r: Reading) -> dict:
    st = _state(r.child_id)
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    moved_m = 0.0
    if st.last is not None:
        moved_m = _haversine_m(st.last.gps_lat, st.last.gps_lon, r.gps_lat, r.gps_lon)
    off_m = _dist_to_route_m(r.gps_lat, r.gps_lon)

    # Track continuous off-route time (wall clock) and consecutive
    # off-route pings (band ticks every ~2 s). Either crossing 5 min trips
    # the alert, so time-lapse demos (--fast) trigger the same as realtime.
    if off_m > OFF_ROUTE_DIST_M:
        if st.off_route_since is None:
            st.off_route_since = now_ts
        st.off_route_hits += 1
        off_secs = max(now_ts - st.off_route_since, st.off_route_hits * 2)
    else:
        st.off_route_since = None
        st.off_route_hits = 0
        off_secs = 0.0
    st.off_route_m = off_m

    alert_type: Optional[str] = None
    detail = ""
    water_watch = False
    if (
        r.water_depth_cm > 100
        and r.water_time_sec > 30
        and moved_m < 1.0
        and r.hr > 130
        and st.last is not None
    ):
        alert_type, detail = (
            "possible_drowning",
            f"Submerged {r.water_depth_cm:.0f}cm for {r.water_time_sec:.0f}s, "
            f"HR {r.hr}, no movement ({moved_m:.1f}m).",
        )
    elif r.skin_distance_cm > SKIN_OFF_CM:
        alert_type, detail = "skin_off", f"Band off skin (gap {r.skin_distance_cm}cm)."
    elif off_secs > OFF_ROUTE_SECS:
        alert_type, detail = (
            "off_route",
            f"{off_m:.0f}m off route for {off_secs / 60:.1f}min.",
        )
    elif r.hr > HR_SPIKE and moved_m < STILL_M and st.last is not None:
        alert_type, detail = (
            "hr_spike_no_movement",
            f"HR {r.hr} with no movement ({moved_m:.1f}m since last ping).",
        )
    elif r.hr < 50 and r.hr > 0 and moved_m < STILL_M and st.last is not None:
        alert_type, detail = (
            "possible_faint",
            f"HR dropped to {r.hr} with no movement ({moved_m:.1f}m).",
        )
    else:
        if 20 <= r.water_depth_cm <= 80 and moved_m > 0:
            # Shallow water + movement = pool play: watch-only, never an alert.
            water_watch = True
            st.water_watch = True
            detail = (
                f"Water play: {r.water_depth_cm:.0f}cm depth with movement "
                f"({moved_m:.1f}m). Watch-only until safe."
            )
        else:
            if r.water_depth_cm < 20:
                st.water_watch = False  # dry again -> watch clears
            today = now.astimezone().date().isoformat()
            early = now.astimezone().hour < EARLIEST_HOUR
            if early and today not in st.early_flag_dates:
                st.early_flag_dates.append(today)
                alert_type, detail = (
                    "early_departure",
                    f"Movement at {now.astimezone().strftime('%H:%M')} "
                    f"before {EARLIEST_HOUR:02d}:00 window.",
                )

    st.last = r
    st.last_seen = now.isoformat()

    # Opportunistic EMS sweep on every ping (watchdog covers idle periods).
    for esc in _check_ems_escalations(now_ts):
        await hub.broadcast(esc)

    if alert_type is None:
        resp = {
            "anomaly": False,
            "status": "water_watch" if water_watch else "ok",
            "off_route_m": round(off_m, 1),
            "moved_m": round(moved_m, 1),
        }
        if water_watch:
            resp["detail"] = detail
            resp["water_watch"] = True
        return resp

    alert_id = uuid.uuid4().hex[:12]
    summary = ai_summarize(alert_type, r, detail)
    payload = {
        "anomaly": True,
        "id": alert_id,
        "type": alert_type,
        "location": {"gps_lat": r.gps_lat, "gps_lon": r.gps_lon},
        "detail": detail,
        "ai_summary": summary,
        "actions": ACTIONS,
        "child_id": r.child_id,
        "timestamp": now.isoformat(),
    }
    alerts[alert_id] = {
        **payload,
        "acked": False,
        "ack_at": None,
        "created_ts": now_ts,
        "ems_triggered": False,
    }
    st.last_alert = payload
    _write_alert_file(payload)
    await hub.broadcast(payload)
    return payload


@app.get("/children/{child_id}/status")
def child_status(child_id: str) -> dict:
    _check_ems_escalations(datetime.now(timezone.utc).timestamp())
    st = store.get(child_id)
    if st is None or st.last is None:
        return {"child_id": child_id, "status": "unknown", "last": None}
    last = st.last
    return {
        "child_id": child_id,
        "status": "alert" if st.last_alert else "ok",
        "last": last.model_dump(),
        "last_seen": st.last_seen,
        "off_route_m": round(st.off_route_m, 1),
        "water_watch": st.water_watch,
        "last_alert": st.last_alert,
    }


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket) -> None:
    await ws.accept()
    hub.clients.append(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive; server only broadcasts
    except WebSocketDisconnect:
        pass
    finally:
        if ws in hub.clients:
            hub.clients.remove(ws)


# ------------------------------------------------- routes / schedule / ack
@app.post("/routes")
def create_route(r: RouteIn) -> dict:
    data = _load_routes_file()
    route = Route(**r.model_dump(), id=uuid.uuid4().hex[:12])
    data["routes"].append(route.model_dump())
    # Pre-populate EMS cache so escalation has numbers ready on day one.
    data["ems_cache"][route.id] = _mock_ems(route.id, route.destination)
    _save_routes_file(data)
    return {**route.model_dump(), "ems": data["ems_cache"][route.id]}


@app.get("/routes")
def list_routes() -> dict:
    return {"routes": _load_routes_file()["routes"]}


@app.post("/schedule")
def save_schedule(s: DaySchedule) -> dict:
    data = _load_routes_file()
    data["schedules"][s.date] = s.model_dump()
    _save_routes_file(data)
    return s.model_dump()


@app.get("/schedule/{date}")
def get_schedule(date: str) -> dict:
    data = _load_routes_file()
    sched = data["schedules"].get(date)
    if sched is None:
        raise HTTPException(status_code=404, detail=f"no schedule for {date}")
    out = dict(sched)
    for r in data["routes"]:
        if r.get("id") == sched.get("route_id"):
            out["route"] = r
            out["ems"] = data["ems_cache"].get(r["id"])
            break
    return out


@app.post("/children/{child_id}/profile")
def save_child_profile(child_id: str, p: ChildProfile) -> dict:
    data = _load_children()
    data[child_id] = p.model_dump()
    _save_children(data)
    return {"child_id": child_id, **p.model_dump()}


@app.get("/children/{child_id}/profile")
def get_child_profile(child_id: str) -> dict:
    data = _load_children()
    if child_id not in data:
        raise HTTPException(status_code=404, detail=f"no profile for {child_id}")
    return {"child_id": child_id, **data[child_id]}


@app.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str) -> dict:
    rec = alerts.get(alert_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"unknown alert {alert_id}")
    rec["acked"] = True
    rec["ack_at"] = datetime.now(timezone.utc).isoformat()
    return {"alert_id": alert_id, "acked": True, "ack_at": rec["ack_at"]}


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict:
    rec = alerts.get(alert_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"unknown alert {alert_id}")
    return rec


@app.on_event("startup")
async def _ems_watchdog() -> None:
    async def loop() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                now_ts = datetime.now(timezone.utc).timestamp()
                for esc in _check_ems_escalations(now_ts):
                    await hub.broadcast(esc)
            except Exception:
                pass  # watchdog must never crash the app

    asyncio.create_task(loop())
