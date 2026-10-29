"""One-click demo scenarios, run INSIDE the backend (no terminal needed).

POST /demo/play {"scenario": "offline_hr_spike"}   start a scripted band story
GET  /demo/status                                  running flag + step log
GET  /demo/scenarios                               list for the UI

The scripted band feeds the same ingest path as the real simulator, so the
rule engine, alerts, WebSocket and Meta Model triage all run for real.
Two things are time-compressed and labelled as such in the log: the 5-minute
off-route timer and the water submersion timer.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List

HOME = (-26.2485, 27.8540)
SPAZA = (-26.2470, 27.8525)
SCHOOL = (-26.2455, 27.8535)
WRONG_TURN = (-26.2470, 27.8560)
TICK_S = 0.35
CHILD_ID = "child-001"

SCENARIOS = [
    {
        "id": "offline_hr_spike",
        "title": "Dead zone, then nearest relay",
        "blurb": "Band loses signal, sounds its own buzzer, buffers readings, then flushes through a nearby relay.",
    },
    {
        "id": "skin_off",
        "title": "Band removed",
        "blurb": "Band comes off the ankle on a normal link. Instant alert, then Meta Model triage.",
    },
    {
        "id": "off_route",
        "title": "Wrong turn (time-compressed)",
        "blurb": "Child leaves the route. The 5-minute timer is fast-forwarded and labelled in the log.",
    },
    {
        "id": "drowning",
        "title": "Possible drowning (time-compressed)",
        "blurb": "Deep water, no movement, racing heart rate. Submersion timer is fast-forwarded.",
    },
]


def _move_toward(lat, lon, tlat, tlon, step_m):
    kx = 111320.0 * math.cos(math.radians(lat))
    ky = 110540.0
    dx, dy = (tlon - lon) * kx, (tlat - lat) * ky
    dist = math.hypot(dx, dy)
    if dist <= step_m:
        return tlat, tlon
    f = step_m / dist
    return lat + (tlat - lat) * f, lon + (tlon - lon) * f


def _moved_m(a, b) -> float:
    kx = 111320.0 * math.cos(math.radians(a["gps_lat"]))
    return math.hypot((b["gps_lon"] - a["gps_lon"]) * kx, (b["gps_lat"] - a["gps_lat"]) * 110540.0)


def _edge_check(r: dict, prev: dict | None):
    """Rules the band itself runs with no internet (mirror of the simulator)."""
    moved = _moved_m(prev, r) if prev else 99.0
    if r["water_depth_cm"] > 100 and r["water_time_sec"] > 30 and moved < 1 and r["hr"] > 130:
        return "possible drowning"
    if r["skin_distance_cm"] > 2.5:
        return "band off skin"
    if r["hr"] > 130 and moved < 2:
        return "heart rate spike, no movement"
    return None


class DemoRunner:
    def __init__(self, ingest_one: Callable, get_state: Callable, hub, reading_cls):
        self.ingest_one = ingest_one
        self.get_state = get_state
        self.hub = hub
        self.Reading = reading_cls
        self.running = False
        self.scenario: str | None = None
        self.log: List[dict] = []
        self._prev: dict | None = None
        self._pos = HOME

    # ---------------------------------------------------------------- helpers
    async def emit(self, kind: str, msg: str) -> None:
        rec = {"event": "demo", "kind": kind, "msg": msg,
               "t": datetime.now(timezone.utc).isoformat()}
        self.log.append(rec)
        del self.log[:-80]
        await self.hub.broadcast(rec)

    def _reset_child(self) -> None:
        st = self.get_state(CHILD_ID)
        st.last = None
        st.last_alert = None
        st.history.clear()
        st.last_alert_ts.clear()
        st.last_alert_id.clear()
        st.off_route_since = None
        st.off_route_hits = 0
        st.water_watch = False
        # keep night-time demos clean: no "early departure" alert on a normal walk
        st.early_flag_dates.append(datetime.now().astimezone().date().isoformat())
        self._prev = None
        self._pos = HOME

    def _reading(self, lat, lon, hr, **kw) -> dict:
        base = {
            "child_id": CHILD_ID, "gps_lat": lat, "gps_lon": lon, "hr": int(hr),
            "skin_distance_cm": 0.4, "battery": 90, "water_depth_cm": 0.0,
            "water_time_sec": 0.0, "ts": round(time.time(), 1), "edge_alarm": False,
        }
        base.update(kw)
        return base

    async def _push(self, rd: dict, link: str) -> dict:
        res = await self.ingest_one(self.Reading(**rd, link=link))
        if res.get("anomaly") and not res.get("deduped"):
            await self.emit("alert", f"ALERT raised: {res.get('type')} - {res.get('detail')}")
        return res

    def _walk(self, target, hr):
        lat, lon = self._pos
        lat, lon = _move_toward(lat, lon, target[0], target[1], 2.4)
        self._pos = (lat + random.uniform(-4e-6, 4e-6), lon + random.uniform(-4e-6, 4e-6))
        return self._reading(self._pos[0], self._pos[1], hr)

    # ------------------------------------------------------------- scenarios
    async def _normal_walk(self, n: int, link: str = "direct", hr0: int = 90):
        for i in range(n):
            rd = self._walk(SPAZA, hr0 + i)
            await self._push(rd, link)
            self._prev = rd
            await asyncio.sleep(TICK_S)

    async def run_offline_hr_spike(self):
        await self.emit("scenario", "Child walks Home -> Spaza, band on a normal link.")
        await self._normal_walk(4)
        await self.emit("link", "Signal lost: band is OFFLINE. It keeps its own safety rules running.")
        buffered: List[dict] = []
        hr = 102
        alarmed = False
        for _ in range(16):
            lat, lon = self._pos
            rd = self._reading(lat + random.uniform(-3e-6, 3e-6), lon + random.uniform(-3e-6, 3e-6), min(hr, 145))
            hr += 4
            why = _edge_check(rd, self._prev)
            rd["edge_alarm"] = bool(why)
            if why and not alarmed:
                alarmed = True
                await self.emit("band", f"LOCAL ALARM ({why}): buzzer + LED on. No internet needed.")
            buffered.append(rd)
            self._prev = rd
            await asyncio.sleep(TICK_S)
        await self.emit("band", f"{len(buffered)} readings buffered in band memory.")
        await self.emit("link", "Nearest relay found (closest connection). Flushing buffer in order.")
        for rd in buffered:
            await self._push(rd, "buffered")
            await asyncio.sleep(0.05)
        last = self._reading(self._pos[0], self._pos[1], 145, edge_alarm=True)
        await self._push(last, "relay")
        await self.emit("link", "Buffer delivered. Meta Model triage is running in the background.")

    async def run_skin_off(self):
        await self.emit("scenario", "Child walks to school, link is normal.")
        await self._normal_walk(6)
        await self.emit("band", "Band gap to skin jumps to 3.5 cm: band removed.")
        rd = self._reading(self._pos[0], self._pos[1], 92, skin_distance_cm=3.5)
        await self._push(rd, "direct")

    async def run_off_route(self):
        await self.emit("scenario", "Child walks the planned route.")
        await self._normal_walk(4)
        await self.emit("scenario", "Child takes a wrong turn (positions fast-forwarded).")
        for _ in range(5):
            lat, lon = _move_toward(self._pos[0], self._pos[1], WRONG_TURN[0], WRONG_TURN[1], 45)
            self._pos = (lat, lon)
            await self._push(self._reading(lat, lon, 104), "direct")
            await asyncio.sleep(TICK_S)
        await self.emit("note", "DEMO TIME-COMPRESSION: pretending 5 minutes passed off-route.")
        st = self.get_state(CHILD_ID)
        st.off_route_since = time.time() - 301
        await self._push(self._reading(self._pos[0], self._pos[1], 106), "direct")

    async def run_drowning(self):
        await self.emit("scenario", "Child reaches water near the route.")
        await self._normal_walk(3)
        await self.emit("note", "DEMO TIME-COMPRESSION: submersion timer fast-forwarded.")
        for secs in (8, 18, 28, 38, 48):
            lat, lon = self._pos
            hr = 142 if secs > 30 else 118  # stays under the heart-rate rule until submersion is long enough
            rd = self._reading(lat + random.uniform(-2e-6, 2e-6), lon + random.uniform(-2e-6, 2e-6), hr,
                               water_depth_cm=120, water_time_sec=secs)
            await self._push(rd, "direct")
            self._prev = rd
            await asyncio.sleep(TICK_S)

    # ------------------------------------------------------------------ main
    async def play(self, scenario: str) -> None:
        self.running = True
        self.scenario = scenario
        try:
            self.log.clear()
            self._reset_child()
            await self.emit("start", f"Scenario started: {scenario}")
            await getattr(self, f"run_{scenario}")()
            await self.emit("done", "Scenario finished. Watch the alert screen and AI triage.")
        except Exception as exc:  # never crash the server from a demo
            await self.emit("error", f"Demo stopped: {exc}")
        finally:
            self.running = False


def install(app, ingest_one, get_state, hub, reading_cls) -> DemoRunner:
    from fastapi import HTTPException

    runner = DemoRunner(ingest_one, get_state, hub, reading_cls)
    valid = {s["id"] for s in SCENARIOS}

    @app.get("/demo/scenarios")
    def demo_scenarios() -> dict:
        return {"scenarios": SCENARIOS}

    @app.get("/demo/status")
    def demo_status() -> dict:
        return {"running": runner.running, "scenario": runner.scenario, "log": runner.log[-40:]}

    @app.post("/demo/play")
    async def demo_play(body: Dict[str, str]) -> dict:
        scenario = body.get("scenario", "")
        if scenario not in valid:
            raise HTTPException(status_code=400, detail=f"unknown scenario '{scenario}'")
        if runner.running:
            raise HTTPException(status_code=409, detail="a demo is already running")
        asyncio.create_task(runner.play(scenario))
        return {"started": scenario}

    return runner
