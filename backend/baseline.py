"""Personal baseline: learn what is normal for THIS child, propose (never impose) a threshold.

Why: heart rate alone is a weak signal. A child who runs when late can trip the
"heart-rate spike while still" rule every time she waits at a crossing.

How it stays safe:
  * Facts (averages, ranges, counts) are computed deterministically here.
  * The Meta Model reads the history and PROPOSES a threshold with reasons.
  * The server clamps the proposal: never below the evidence from the child's
    own history, never above HR_SPIKE_MAX.
  * A parent must approve. Nothing changes until they do.
  * Only the heart-rate-while-still rule can be personalised. Band-off, drowning,
    faint and off-route rules never change.

The demo history is SYNTHETIC and labelled as such everywhere. The method works
on real trip logs; collecting those is on the roadmap.
"""

from __future__ import annotations

import asyncio
import json
import random
import statistics
from typing import Callable, Dict, List, Optional

try:
    from . import ai
except ImportError:  # run as a plain script
    import ai  # type: ignore

DEFAULT_HR_SPIKE = 130
HR_SPIKE_MAX = 150  # a personal threshold can never exceed this
SAFETY_NOTE = "Band-off, drowning, faint and off-route rules are never personalised."

# child_id -> {"trips", "synthetic", "stats", "status", "proposal", "error"}
BASELINES: Dict[str, dict] = {}


# ---------------------------------------------------------------- history
def _hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def synthetic_history(child_id: str, days: int = 14, seed: Optional[int] = None) -> List[dict]:
    """Three weeks of school-day trips. ~4 'late-run' days: she leaves late and runs."""
    rng = random.Random(seed if seed is not None else sum(map(ord, child_id)))
    late_days = set(rng.sample(range(days), 4))
    trips = []
    for i in range(days):
        late = i in late_days
        depart = 6 * 60 + 50 + (rng.randint(8, 18) if late else rng.randint(-8, 6))
        walk_avg = rng.randint(112, 122) if late else rng.randint(92, 102)
        trips.append({
            "day": i + 1,
            "depart": _hhmm(depart),
            "duration_min": rng.randint(14, 17) if late else rng.randint(19, 23),
            "hr_walk_avg": walk_avg,
            "hr_peak_moving": walk_avg + rng.randint(10, 18),
            "hr_peak_while_still": rng.randint(132, 142) if late else rng.randint(96, 108),
            "max_off_route_m": rng.randint(2, 9),
            "late_run": late,
        })
    return trips


def compute_stats(trips: List[dict]) -> Optional[dict]:
    """Deterministic facts. The model is never asked to calculate these."""
    if not trips:
        return None
    normal = [t for t in trips if not t["late_run"]]
    late = [t for t in trips if t["late_run"]]
    dep = [_mins(t["depart"]) for t in trips]
    still_late = [t["hr_peak_while_still"] for t in late]
    return {
        "trips": len(trips),
        "late_run_days": len(late),
        "hr_walk_avg_normal_days": round(statistics.mean(t["hr_walk_avg"] for t in normal)) if normal else None,
        "hr_walk_range_normal_days": [min(t["hr_walk_avg"] for t in normal), max(t["hr_walk_avg"] for t in normal)] if normal else None,
        "hr_peak_while_still_normal_days_max": max(t["hr_peak_while_still"] for t in normal) if normal else None,
        "hr_peak_while_still_late_run_days": [min(still_late), max(still_late)] if still_late else None,
        "depart_median": _hhmm(statistics.median(dep)),
        "depart_range": [_hhmm(min(dep)), _hhmm(max(dep))],
        "max_off_route_m": max(t["max_off_route_m"] for t in trips),
        "days_that_would_fire_default_hr_rule": sum(1 for t in trips if t["hr_peak_while_still"] > DEFAULT_HR_SPIKE),
        "default_hr_spike": DEFAULT_HR_SPIKE,
        "hard_cap_hr_spike": HR_SPIKE_MAX,
    }


# ------------------------------------------------------------- guardrails
def evidence_floor(stats: dict) -> int:
    """Lowest personal threshold the child's own history supports."""
    late = stats.get("hr_peak_while_still_late_run_days")
    if not late:
        return DEFAULT_HR_SPIKE
    return max(DEFAULT_HR_SPIKE, min(HR_SPIKE_MAX, late[1] + 3))


def apply_guardrail(proposed: int, stats: dict) -> dict:
    """Clamp the model's number. Returns the value and whether it was changed."""
    floor = evidence_floor(stats)
    value = max(floor, min(HR_SPIKE_MAX, int(proposed)))
    reason = ""
    if value != int(proposed):
        reason = (f"Model proposed {int(proposed)} bpm; adjusted to {value} bpm "
                  f"(history supports at least {floor}, hard cap {HR_SPIKE_MAX}).")
    return {"value": value, "adjusted": value != int(proposed), "reason": reason, "floor": floor}


# ------------------------------------------------------------- Meta Model
SYSTEM = (
    "You analyse a child's recent walk-to-school history for SafeSteps, a safety band. "
    "All numbers in STATS are already computed: do not recalculate or invent numbers. "
    "Propose a threshold ONLY for the 'heart rate above X while the child is still' rule. "
    "A parent will approve it; band-off, drowning, faint and off-route rules are never changed. "
    "Prefer the smallest change that removes repeated false alarms and say honestly what could be missed. "
    "Return ONLY a JSON object with keys: "
    '"summary" (max 40 words), "normal_pattern" (list of up to 3 short strings), '
    '"false_alarm_patterns" (list of up to 3 short strings), '
    '"suggested_hr_spike" (integer bpm between 130 and 150), '
    '"trade_off" (one sentence), "confidence" (number 0 to 1).'
)


def analyze_sync(child_id: str) -> None:
    """Run the Meta Model analysis (blocking; call from a worker thread)."""
    b = BASELINES.get(child_id)
    if not b:
        return
    b["status"], b["error"] = "running", None
    try:
        user = json.dumps({"TRIPS": b["trips"], "STATS": b["stats"]})
        msg = ai.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], timeout=120)
        out = ai._extract_json(msg.get("content") or "")
        guard = apply_guardrail(int(out.get("suggested_hr_spike", DEFAULT_HR_SPIKE)), b["stats"])
        out["suggested_hr_spike_final"] = guard["value"]
        out["guardrail"] = guard
        out["model"] = ai.MODEL_NAME
        out["safety_note"] = SAFETY_NOTE
        b["proposal"], b["status"] = out, "ok"
    except Exception as exc:  # never crash the server
        b["status"], b["error"] = "error", str(exc)[:300]


def summary_for(child_id: str) -> dict:
    """What the triage agent sees via the get_baseline tool."""
    b = BASELINES.get(child_id)
    if not b:
        return {"available": False, "note": "No history for this child yet."}
    return {
        "available": True,
        "history_is_synthetic_demo_data": b["synthetic"],
        "stats": b["stats"],
        "approved_hr_spike": b.get("approved_hr_spike"),
        "proposal_summary": (b.get("proposal") or {}).get("summary"),
        "false_alarm_patterns": (b.get("proposal") or {}).get("false_alarm_patterns"),
    }


# ------------------------------------------------------------- endpoints
def install(app, get_state: Callable) -> None:
    from fastapi import HTTPException

    def view(child_id: str) -> dict:
        b = BASELINES.get(child_id)
        st = get_state(child_id)
        active = st.hr_spike_override or DEFAULT_HR_SPIKE
        base = {"child_id": child_id, "has_history": bool(b), "active_hr_spike": active,
                "default_hr_spike": DEFAULT_HR_SPIKE, "approved": bool(st.hr_spike_override),
                "safety_note": SAFETY_NOTE}
        if not b:
            return base
        return {**base, "synthetic": b["synthetic"], "trips": b["trips"], "stats": b["stats"],
                "status": b["status"], "error": b.get("error"), "proposal": b.get("proposal")}

    @app.get("/baseline/{child_id}")
    def baseline_get(child_id: str) -> dict:
        return view(child_id)

    @app.post("/baseline/{child_id}/seed")
    def baseline_seed(child_id: str) -> dict:
        trips = synthetic_history(child_id)
        BASELINES[child_id] = {"trips": trips, "synthetic": True, "stats": compute_stats(trips),
                               "status": "idle", "proposal": None, "error": None, "approved_hr_spike": None}
        get_state(child_id).hr_spike_override = None
        return view(child_id)

    @app.post("/baseline/{child_id}/analyze")
    async def baseline_analyze(child_id: str) -> dict:
        b = BASELINES.get(child_id)
        if not b:
            raise HTTPException(status_code=400, detail="Load history first.")
        if not ai.configured():
            raise HTTPException(status_code=400, detail="META_API_KEY is not set on the backend.")
        if b["status"] == "running":
            return view(child_id)
        b["status"] = "running"
        asyncio.create_task(asyncio.to_thread(analyze_sync, child_id))
        return view(child_id)

    @app.post("/baseline/{child_id}/approve")
    def baseline_approve(child_id: str) -> dict:
        b = BASELINES.get(child_id)
        if not b or not b.get("proposal"):
            raise HTTPException(status_code=400, detail="Nothing to approve yet.")
        value = b["proposal"]["suggested_hr_spike_final"]
        get_state(child_id).hr_spike_override = value
        b["approved_hr_spike"] = value
        return view(child_id)

    @app.post("/baseline/{child_id}/reset")
    def baseline_reset(child_id: str) -> dict:
        get_state(child_id).hr_spike_override = None
        if child_id in BASELINES:
            BASELINES[child_id]["approved_hr_spike"] = None
        return view(child_id)
