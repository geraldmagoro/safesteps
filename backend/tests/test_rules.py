"""Rule engine: every alert type, plus the guards that stop false alarms and AI-cost storms."""
import json
import re
import time

from backend import main


def test_normal_reading_raises_no_alert(post, child, on_route):
    res = post(child, *on_route)
    assert res["anomaly"] is False


def test_skin_off_alert(post, child, on_route):
    res = post(child, *on_route, skin_distance_cm=3.5)
    assert res["anomaly"] and res["type"] == "skin_off"


def test_skin_gap_at_threshold_is_not_an_alert(post, child, on_route):
    assert post(child, *on_route, skin_distance_cm=2.5)["anomaly"] is False


def test_heart_rate_spike_when_still(post, child, on_route):
    post(child, *on_route)
    res = post(child, *on_route, hr=145)
    assert res["anomaly"] and res["type"] == "hr_spike_no_movement"


def test_heart_rate_spike_needs_stillness(post, child, on_route):
    post(child, *on_route)
    res = post(child, on_route[0] + 0.0005, on_route[1], hr=145)  # ~55 m away: moving
    assert res.get("type") != "hr_spike_no_movement"


def test_possible_faint(post, child, on_route):
    post(child, *on_route)
    res = post(child, *on_route, hr=40)
    assert res["anomaly"] and res["type"] == "possible_faint"


def test_possible_drowning(post, child, on_route):
    post(child, *on_route)
    res = post(child, *on_route, hr=140, water_depth_cm=120, water_time_sec=40)
    assert res["anomaly"] and res["type"] == "possible_drowning"


def test_off_route_needs_five_minutes(post, child):
    far = (main.ROUTE[0][0], main.ROUTE[0][1] + 0.002)  # ~200 m east of home
    assert post(child, *far)["anomaly"] is False  # the timer has only just started
    main._state(child).off_route_since = time.time() - 301
    res = post(child, *far)
    assert res["anomaly"] and res["type"] == "off_route"


def test_small_gps_wobble_is_not_off_route(post, child, on_route):
    wobble = (on_route[0] + 0.00005, on_route[1])  # about 5 m
    assert post(child, *wobble)["anomaly"] is False


def test_repeat_alerts_are_folded(post, child, on_route):
    first = post(child, *on_route, skin_distance_cm=3.5)
    second = post(child, *on_route, skin_distance_cm=3.5)
    assert first["anomaly"] and not first.get("deduped")
    assert second["anomaly"] and second["deduped"] and second["id"] == first["id"]


def test_batch_counts_real_alerts_only(client, child, on_route):
    batch = [
        {"child_id": child, "gps_lat": on_route[0], "gps_lon": on_route[1], "hr": 90,
         "skin_distance_cm": 3.5, "battery": 90, "link": "buffered"}
        for _ in range(5)
    ]
    res = client.post("/ingest/batch", json=batch).json()
    assert res["received"] == 5 and res["alerts"] == 1


def test_saved_alert_file_rounds_location(client, post, child, on_route, tmp_path):
    post(child, on_route[0] + 0.0000123, on_route[1] + 0.0000456, skin_distance_cm=3.5)
    saved = json.loads((tmp_path / "alert.json").read_text())
    assert len(str(saved["location"]["gps_lat"]).split(".")[-1]) <= 3
    assert not re.search(r"-?\d+\.\d{5}", saved["ai_summary"])


def test_live_alert_keeps_exact_location(post, child, on_route):
    res = post(child, on_route[0] + 0.0000123, on_route[1], skin_distance_cm=3.5)
    assert abs(res["location"]["gps_lat"] - (on_route[0] + 0.0000123)) < 1e-9


def test_route_rebase_moves_the_route(client, post, child):
    new_home, new_school = (-25.7479, 28.2293), (-25.7470, 28.2293)  # about 100 m apart
    assert client.post("/route/rebase", json={"home": new_home, "school": new_school}).status_code == 200
    assert post(child, *new_home)["anomaly"] is False  # not "off route" in the new place
    assert client.get("/route").json()["home"] == list(new_home)


def test_route_rebase_rejects_bad_distances(client):
    near = client.post("/route/rebase", json={"home": [-25.0, 28.0], "school": [-25.0, 28.00001]})
    far = client.post("/route/rebase", json={"home": [-25.0, 28.0], "school": [-20.0, 28.0]})
    assert near.status_code == 400 and far.status_code == 400
