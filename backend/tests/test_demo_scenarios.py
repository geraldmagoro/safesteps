"""Every one-click demo scenario must raise the alert it promises, including after a parent
has approved a personal heart-rate baseline (the hero demo must never go silent on camera)."""
import asyncio

import pytest

from backend import demo, main

EXPECT = {
    "skin_off": "skin_off",
    "off_route": "off_route",
    "drowning": "possible_drowning",
    "offline_hr_spike": "hr_spike_no_movement",
}


@pytest.fixture
def runner(client, monkeypatch):
    monkeypatch.setattr(demo, "TICK_S", 0)
    st = main._state(demo.CHILD_ID)
    yield demo.DemoRunner(main._ingest_one, main._state, main.hub, main.Reading, lambda: main.ROUTE)
    st.hr_spike_override = None


def _play(runner, scenario):
    asyncio.run(runner.play(scenario))
    assert not [e for e in runner.log if e["kind"] == "error"], runner.log
    return set(main._state(demo.CHILD_ID).last_alert_ts)


@pytest.mark.parametrize("scenario,alert", EXPECT.items())
def test_scenario_raises_its_alert(runner, scenario, alert):
    assert alert in _play(runner, scenario)


@pytest.mark.parametrize("scenario,alert", EXPECT.items())
def test_scenario_still_alerts_with_a_personal_threshold_approved(runner, scenario, alert):
    main._state(demo.CHILD_ID).hr_spike_override = 150  # the highest a parent can approve
    assert alert in _play(runner, scenario)


def test_runner_crossing_alerts_by_default(runner):
    assert "hr_spike_no_movement" in _play(runner, "runner_crossing")


def test_runner_crossing_is_quiet_after_approval(runner):
    main._state(demo.CHILD_ID).hr_spike_override = 145
    assert "hr_spike_no_movement" not in _play(runner, "runner_crossing")
