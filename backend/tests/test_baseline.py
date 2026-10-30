"""Personal baseline: facts are computed in code, the model only proposes, the server clamps,
the parent approves, and only the heart-rate-while-still rule can change."""
import json

import pytest

from backend import ai, baseline, main


@pytest.fixture
def seeded(client, child):
    client.post(f"/baseline/{child}/seed")
    return child


def _fake_model(value):
    payload = {"summary": "Runs when late.", "normal_pattern": ["calm walk"], "false_alarm_patterns": ["waits at crossings after running"],
               "suggested_hr_spike": value, "trade_off": "A real spike between 130 and the new limit would not alert.", "confidence": 0.7}
    return lambda messages, tools=None, timeout=90.0: {"role": "assistant", "content": "```json\n" + json.dumps(payload) + "\n```"}


def test_history_is_deterministic_and_labelled_synthetic(client, child):
    a = baseline.synthetic_history(child)
    assert a == baseline.synthetic_history(child)
    assert client.post(f"/baseline/{child}/seed").json()["synthetic"] is True


def test_stats_are_computed_not_guessed(seeded):
    stats = baseline.BASELINES[seeded]["stats"]
    assert stats["trips"] == 14 and stats["late_run_days"] == 4
    assert stats["days_that_would_fire_default_hr_rule"] == 4  # exactly the late-run days
    assert stats["hr_peak_while_still_normal_days_max"] < 110


def test_guardrail_raises_a_too_low_proposal(seeded):
    stats = baseline.BASELINES[seeded]["stats"]
    g = baseline.apply_guardrail(131, stats)
    assert g["value"] == baseline.evidence_floor(stats) and g["adjusted"]


def test_guardrail_caps_a_reckless_proposal(seeded):
    g = baseline.apply_guardrail(200, baseline.BASELINES[seeded]["stats"])
    assert g["value"] == baseline.HR_SPIKE_MAX and g["adjusted"]


def test_guardrail_leaves_a_sensible_proposal_alone(seeded):
    stats = baseline.BASELINES[seeded]["stats"]
    ok = baseline.evidence_floor(stats) + 1
    g = baseline.apply_guardrail(ok, stats)
    assert g["value"] == ok and not g["adjusted"]


def test_analysis_stores_a_clamped_proposal(client, seeded, monkeypatch):
    monkeypatch.setattr(ai, "chat", _fake_model(120))  # below the evidence: must be raised
    baseline.analyze_sync(seeded)
    view = client.get(f"/baseline/{seeded}").json()
    assert view["status"] == "ok" and view["proposal"]["guardrail"]["adjusted"]
    assert view["proposal"]["suggested_hr_spike_final"] >= baseline.evidence_floor(view["stats"])


def test_model_failure_is_reported_not_raised(client, seeded, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(ai, "chat", boom)
    baseline.analyze_sync(seeded)
    view = client.get(f"/baseline/{seeded}").json()
    assert view["status"] == "error" and "network down" in view["error"]


def test_cannot_approve_before_analysis(client, seeded):
    assert client.post(f"/baseline/{seeded}/approve").status_code == 400


def test_approved_threshold_changes_only_the_hr_rule(client, post, seeded, on_route, monkeypatch):
    # default rule: a still child at 138 bpm raises an alert
    post(seeded, *on_route)
    assert post(seeded, *on_route, hr=138)["type"] == "hr_spike_no_movement"

    # propose, approve
    other = seeded + "-b"
    client.post(f"/baseline/{other}/seed")
    monkeypatch.setattr(ai, "chat", _fake_model(145))
    baseline.analyze_sync(other)
    floor = baseline.evidence_floor(baseline.BASELINES[other]["stats"])
    assert client.post(f"/baseline/{other}/approve").json()["approved"] is True

    # same reading is now normal for this child ...
    post(other, *on_route)
    assert post(other, *on_route, hr=floor - 1)["anomaly"] is False
    # ... but a higher one still alerts, and the safety rules are untouched
    assert post(other, *on_route, hr=151)["type"] == "hr_spike_no_movement"
    assert post(other, *on_route, skin_distance_cm=3.5)["type"] == "skin_off"
    assert post(other, *on_route, hr=140, water_depth_cm=120, water_time_sec=40)["type"] == "possible_drowning"
    assert post(other, *on_route, hr=40)["type"] == "possible_faint"


def test_reset_restores_the_default(client, seeded, monkeypatch):
    monkeypatch.setattr(ai, "chat", _fake_model(145))
    baseline.analyze_sync(seeded)
    client.post(f"/baseline/{seeded}/approve")
    assert client.post(f"/baseline/{seeded}/reset").json()["active_hr_spike"] == baseline.DEFAULT_HR_SPIKE


def test_triage_can_read_the_baseline(seeded):
    assert "get_baseline" in [t["function"]["name"] for t in ai.TOOLS]
    info = baseline.summary_for(seeded)
    assert info["available"] and info["history_is_synthetic_demo_data"] is True
    assert baseline.summary_for("nobody")["available"] is False


def test_baseline_endpoints_need_the_pin(client, child, monkeypatch):
    monkeypatch.setenv("SAFESTEPS_PIN", "4321")
    assert client.get(f"/baseline/{child}").status_code == 401
    assert client.get(f"/baseline/{child}", headers={"x-pin": "4321"}).status_code == 200
