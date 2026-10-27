"""SafeSteps ankle-band simulator — stdlib only, no pip install needed.

Emits {"child_id","gps_lat","gps_lon","hr","skin_distance_cm","battery",
"water_depth_cm","water_time_sec"} every 2 s (stdout + POST to the backend).
Band is 12h waterproof: water readings keep streaming while submerged.

Normal route: Home -> Spaza (left) -> School (matches backend/main.py).

Usage:
  python band-simulator/simulate.py --mode normal
  python band-simulator/simulate.py --mode offroute --fast 60   # 6 min in 6 s
  python band-simulator/simulate.py --mode demo --fast 20   # full reel in ~25 s
  python band-simulator/simulate.py --mode pool_play        # shallow water play
  python band-simulator/simulate.py --mode drowning --fast 10
Modes: normal | offroute | skinoff | spike | faint | demo | pool_play | drowning
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import urllib.request

HOME = (-26.2485, 27.8540)
SPAZA = (-26.2470, 27.8525)   # left turn off the main path
SCHOOL = (-26.2455, 27.8535)
OFF_ROUTE = (-26.2470, 27.8560)  # wrong (right) turn: 200 m+ off route

STEP_M = 2.4          # walking ~1.2 m/s at a 2 s tick
OFF_ROUTE_TICKS = 180  # 6 minutes at 2 s/tick


def _move_toward(lat, lon, tlat, tlon, step_m=STEP_M):
    """Move step_m toward target; returns (lat, lon, arrived_bool)."""
    kx = 111320.0 * math.cos(math.radians(lat))
    ky = 110540.0
    dx, dy = (tlon - lon) * kx, (tlat - lat) * ky
    dist = math.hypot(dx, dy)
    if dist <= step_m:
        return tlat, tlon, True
    f = step_m / dist
    return lat + (tlat - lat) * f, lon + (tlon - lon) * f, False


def _jitter(v, amt=0.00001):
    return v + random.uniform(-amt, amt)


class Band:
    """Position + vitals state for one simulated child."""

    def __init__(self, child_id: str):
        self.child_id = child_id
        self.lat, self.lon = HOME
        self.tick = 0
        self.hr = 90
        self.skin = 0.4
        self.water_depth = 0.0   # cm, 0 = dry
        self.water_time = 0.0    # continuous submersion seconds (sim time)
        self.tick_secs = 2.0     # sim seconds per tick (set from --interval)

    def reading(self) -> dict:
        battery = max(5, 100 - self.tick // 150)
        return {
            "child_id": self.child_id,
            "gps_lat": round(self.lat, 6),
            "gps_lon": round(self.lon, 6),
            "hr": int(self.hr),
            "skin_distance_cm": round(self.skin, 2),
            "battery": battery,
            "water_depth_cm": round(self.water_depth, 1),
            "water_time_sec": round(self.water_time, 1),
        }

    def _dry(self):
        self.water_depth = 0.0
        self.water_time = 0.0

    # -- scenarios ---------------------------------------------------------
    def normal_walk(self):
        """Home -> Spaza (left) -> School, then idle at school."""
        self._dry()
        for target in (SPAZA, SCHOOL):
            while True:
                self.lat, self.lon, done = _move_toward(self.lat, self.lon, *target)
                self.hr = 88 + random.randint(0, 8)
                self.skin = round(random.uniform(0.3, 0.6), 2)
                self.tick += 1
                yield self.reading()
                if done:
                    break
        while True:  # at school, calm
            self.lat, self.lon = _jitter(SCHOOL[0]), _jitter(SCHOOL[1])
            self.hr = 82 + random.randint(0, 6)
            self.tick += 1
            yield self.reading()

    def off_route(self, ticks: int = OFF_ROUTE_TICKS):
        """Turn RIGHT at the junction (away from Spaza) for 6 min."""
        self._dry()
        self.lat, self.lon = HOME
        # walk to junction area first (a few ticks toward Spaza then veer off)
        for _ in range(10):
            self.lat, self.lon, _ = _move_toward(self.lat, self.lon, *SPAZA)
            self.hr = 90 + random.randint(0, 6)
            self.tick += 1
            yield self.reading()
        # veer right and keep walking away from the route
        for _ in range(ticks):
            self.lat, self.lon, done = _move_toward(self.lat, self.lon, *OFF_ROUTE)
            if done:  # wander past it so we stay off-route
                self.lat += random.uniform(0, 0.00003)
                self.lon += random.uniform(0, 0.00003)
            self.hr = 95 + random.randint(0, 10)
            self.tick += 1
            yield self.reading()

    def skin_off(self, ticks: int = 30):
        """Band slipped off skin: gap reads 3 cm while walking normally."""
        gen = self.normal_walk()
        for _ in range(ticks):
            r = next(gen)
            r["skin_distance_cm"] = 3.0
            yield r

    def hr_spike(self, ticks: int = 40):
        """HR ramps 90 -> 145 with no movement (stand still, panic-like)."""
        self._dry()
        for i in range(ticks):
            self.lat, self.lon = _jitter(self.lat, 0.000002), _jitter(self.lon, 0.000002)
            self.hr = min(145, 90 + i * 4)  # 90 -> 145 in ~14 ticks, hold
            self.tick += 1
            yield self.reading()

    def faint(self, ticks: int = 30):
        """Faint: fully still + HR drops to ~45."""
        self._dry()
        for _ in range(ticks):
            self.hr = max(45, self.hr - 8)
            self.tick += 1
            yield self.reading()

    def pool_play(self, ticks: int = 60):
        """Pool play: 40 cm depth, splashing around (movement), HR ~105-120."""
        self.water_depth = 40.0
        self.water_time = 0.0
        cx, cy = self.lat, self.lon
        angle = 0.0
        for _ in range(ticks):
            angle += 0.6
            self.lat = cx + 0.00001 * math.cos(angle) + random.uniform(-0.000004, 0.000004)
            self.lon = cy + 0.00001 * math.sin(angle) + random.uniform(-0.000004, 0.000004)
            self.hr = 105 + random.randint(0, 15)
            self.skin = round(random.uniform(0.3, 0.6), 2)
            self.water_time += self.tick_secs
            self.tick += 1
            yield self.reading()

    def drowning(self, ticks: int = 30):
        """Drowning: 120 cm depth, 60 s no movement, HR 145 (waterproof band)."""
        self.water_depth = 120.0
        self.water_time = 0.0
        for _ in range(ticks):
            self.lat, self.lon = _jitter(self.lat, 0.000002), _jitter(self.lon, 0.000002)
            self.hr = 145
            self.water_time += self.tick_secs
            self.tick += 1
            yield self.reading()

    def demo(self):
        """Full demo reel: normal -> off-route -> skin-off -> spike -> faint."""
        yield from self._take(self.normal_walk(), 20)
        yield from self.off_route(ticks=160)  # >=150 pings trips the 5-min rule
        yield from self.skin_off(ticks=10)
        yield from self.hr_spike(ticks=20)
        yield from self.faint(ticks=15)

    @staticmethod
    def _take(gen, n):
        for _, r in zip(range(n), gen):
            yield r


def post(backend_url: str, payload: dict) -> str:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        backend_url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            out = json.loads(resp.read().decode() or "{}")
        if out.get("anomaly"):
            return f"  <-- ALERT {out.get('type')}"
        return ""
    except Exception as exc:
        return f"  <-- backend unreachable ({exc})"


def main() -> None:
    ap = argparse.ArgumentParser(description="SafeSteps band simulator")
    ap.add_argument("--mode", default="normal",
                    choices=["normal", "offroute", "skinoff", "spike", "faint", "demo",
                             "pool_play", "drowning"])
    ap.add_argument("--child-id", default="child-001")
    ap.add_argument("--backend", default="http://localhost:8000/ingest")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds per tick")
    ap.add_argument("--fast", type=float, default=1.0, help="time-lapse divisor")
    ap.add_argument("--ticks", type=int, default=0, help="max ticks (0 = run mode default)")
    args = ap.parse_args()

    band = Band(args.child_id)
    band.tick_secs = args.interval
    gen = {
        "normal": band.normal_walk,
        "offroute": band.off_route,
        "skinoff": band.skin_off,
        "spike": band.hr_spike,
        "faint": band.faint,
        "demo": band.demo,
        "pool_play": band.pool_play,
        "drowning": band.drowning,
    }[args.mode]()

    print(f"[band {args.child_id}] mode={args.mode} -> {args.backend} (every {args.interval}s)")
    n = 0
    for reading in gen:
        line = json.dumps(reading)
        print(line, flush=True)
        print(post(args.backend, reading))
        n += 1
        if args.ticks and n >= args.ticks:
            break
        time.sleep(args.interval / args.fast)


if __name__ == "__main__":
    main()
