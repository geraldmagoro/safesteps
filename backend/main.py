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
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from . import ai
except ImportError:  # run as a plain script
    import ai  # type: ignore

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

OFF_ROUTE_DIST_M = float(os.getenv("SAFESTEPS_OFF_ROUTE_M", "15"))  # metres from route polyline (consumer GPS error is several metres)
OFF_ROUTE_SECS = 5 * 60      # ... for more than 5 minutes
SKIN_OFF_CM = 2.5            # skin_distance_cm above this = band off skin
HR_SPIKE = 130               # hr above this + no movement = possible distress
STILL_M = 2.0                # consecutive pings closer than this = no movement
EARLIEST_HOUR = int(os.getenv("SAFESTEPS_EARLIEST_HOUR", "6"))  # departures before this local hour = early departure

ALERT_COOLDOWN_SECS = int(os.getenv("SAFESTEPS_ALERT_COOLDOWN_SECS", "60"))  # same alert type repeats are folded (saves AI credits)
ACTIONS = ["notify 5 contacts", "SMS fallback", "community alert 500m"]
MODEL_NAME = ai.MODEL_NAME
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
    ts: Optional[float] = None        # band clock (epoch s) - set when buffered offline
    link: str = "direct"              # direct | relay | buffered (how this reading reached us)
    edge_alarm: bool = False          # band already sounded its local buzzer/LED


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
    history: List[dict] = Field(default_factory=list)
    last_alert_ts: Dict[str, float] = Field(default_factory=dict)  # alert type -> epoch
    last_alert_id: Dict[str, str] = Field(default_factory=dict)


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
def rule_summary(alert_type: str, reading: Reading, detail: str) -> str:
    """Instant, offline, rule-based text. Always available; AI enriches later."""
    return (
        f"{alert_type.replace('_', ' ')}: child {reading.child_id} at "
        f"({reading.gps_lat:.5f}, {reading.gps_lon:.5f}), HR {reading.hr}, "
        f"skin gap {reading.skin_distance_cm}cm. {detail}"
    )


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
    loc = dict(record.get("location") or {})
    for k in ("gps_lat", "gps_lon"):
        if k in loc:
            loc[k] = round(loc[k], 3)  # ~100 m: logs never hold the exact position
    record["location"] = loc
    record["ai_summary"] = re.sub(
        r"-?\d+\.\d{5}", lambda m: f"{float(m.group(0)):.3f}", str(record.get("ai_summary", ""))
    )
    record["privacy"] = "coordinates rounded to ~100 m in saved logs; live alert to parent is exact"
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
    school: str = ""
    language: str = ""   # parent's language for the AI message, e.g. isiZulu


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
    return {"ok": True, "model": MODEL_NAME, "children": len(store), "ai": ai.configured()}


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
    return await _ingest_one(r)


@app.post("/ingest/batch")
async def ingest_batch(readings: List[Reading]) -> dict:
    """Store-and-forward: a band that was offline flushes its buffer here."""
    results = [await _ingest_one(r) for r in readings]
    alerts_raised = [x for x in results if x.get("anomaly") and not x.get("deduped")]
    return {"received": len(results), "alerts": len(alerts_raised), "last": results[-1] if results else None}


async def _ingest_one(r: Reading) -> dict:
    st = _state(r.child_id)
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    delay_s = round(max(0.0, now_ts - r.ts), 1) if r.ts else 0.0

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
    st.history.append({**r.model_dump(), "seen": now.isoformat()})
    del st.history[:-30]

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

    prev_ts = st.last_alert_ts.get(alert_type)
    if prev_ts is not None and now_ts - prev_ts < ALERT_COOLDOWN_SECS:
        return {
            "anomaly": True, "deduped": True, "type": alert_type,
            "id": st.last_alert_id.get(alert_type), "detail": detail,
        }
    alert_id = uuid.uuid4().hex[:12]
    st.last_alert_ts[alert_type] = now_ts
    st.last_alert_id[alert_type] = alert_id
    summary = rule_summary(alert_type, r, detail)
    payload = {
        "anomaly": True,
        "id": alert_id,
        "type": alert_type,
        "location": {"gps_lat": r.gps_lat, "gps_lon": r.gps_lon},
        "detail": detail,
        "ai_summary": summary,
        "ai": {"status": "pending" if ai.configured() else "offline"},
        "actions": ACTIONS,
        "child_id": r.child_id,
        "timestamp": now.isoformat(),
        "event": "alert",
        "link": r.link,
        "delivery_delay_s": delay_s,
        "edge_alarm": r.edge_alarm,
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
    if ai.configured():
        asyncio.create_task(_run_ai(alert_id))
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
        "trail": [[h["gps_lat"], h["gps_lon"]] for h in st.history[-25:]],
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


async def _run_ai(alert_id: str) -> None:
    """Background triage: never blocks or delays the alert itself."""
    rec = alerts.get(alert_id)
    if rec is None:
        return
    child_id = rec.get("child_id", "")
    st = _state(child_id)
    profile = _load_children().get(child_id, {})

    def get_recent_readings(n: int = 10) -> list:
        return [
            {k: h.get(k) for k in ("gps_lat", "gps_lon", "hr", "skin_distance_cm", "link", "seen")}
            for h in st.history[-int(n):]
        ]

    def get_child_profile() -> dict:
        return {
            "name": profile.get("full_name") or "unknown",
            "age": profile.get("age") or "unknown",
            "school": profile.get("school") or "unknown",
            "emergency_contacts": len(profile.get("contacts", [])),
        }

    def get_nearby_help() -> dict:
        return _primary_ems()

    try:
        result = await asyncio.to_thread(
            ai.triage,
            rec,
            {
                "get_recent_readings": get_recent_readings,
                "get_child_profile": get_child_profile,
                "get_nearby_help": get_nearby_help,
            },
            profile.get("language", ""),
        )
        result["status"] = "ok"
    except Exception as exc:  # offline demo must never crash on an AI call
        result = {"status": "error", "error": str(exc)[:300]}
    rec["ai"] = result
    if result.get("status") == "ok" and result.get("parent_message"):
        rec["ai_summary"] = result["parent_message"]
    if st.last_alert and st.last_alert.get("id") == alert_id:
        st.last_alert = {k: rec[k] for k in st.last_alert if k in rec}
    await hub.broadcast(
        {"event": "alert_update", "id": alert_id, "ai": rec["ai"], "ai_summary": rec["ai_summary"]}
    )


@app.get("/ai/status")
def ai_status() -> dict:
    return ai.status()


@app.post("/ai/selftest")
async def ai_selftest() -> dict:
    """Proves the Meta Model API key + endpoint work (and shows token usage)."""
    if not ai.configured():
        raise HTTPException(status_code=400, detail="META_API_KEY is not set")
    try:
        return await asyncio.to_thread(ai.selftest)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:300])


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


try:
    from . import demo as _demo
except ImportError:
    import demo as _demo  # type: ignore
_demo.install(app, _ingest_one, _state, hub, Reading)


# --------------------------------------------- serve the built parent web app
# One origin for API + app: a single tunnel URL works on any phone, any network.
WEB_DIST = Path(__file__).parent.parent / "parent-app" / "dist"


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi.responses import FileResponse

    f = Path(__file__).parent.parent / "parent-app" / "assets" / "favicon.png"
    if not f.exists():
        raise HTTPException(status_code=404)
    return FileResponse(str(f), media_type="image/png")

if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
