import os
import time
import uuid

import pytest

# Tests must never call the real Meta API or need a key.
os.environ.pop("META_API_KEY", None)
os.environ.pop("SAFESTEPS_PIN", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend import main  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "EARLIEST_HOUR", 0)  # tests may run at any hour
    monkeypatch.setattr(main, "ALERT_FILE", tmp_path / "alert.json")
    monkeypatch.setattr(main, "EMS_FILE", tmp_path / "ems_call.json")
    yield TestClient(main.app)
    main.ROUTE[:] = main.ROUTE_DEFAULT  # undo any route re-basing


@pytest.fixture
def child():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def on_route():
    """A point exactly on the expected route (the school end)."""
    lat, lon = main.ROUTE[2]
    return lat, lon


def reading(child_id, lat, lon, **kw):
    base = {"child_id": child_id, "gps_lat": lat, "gps_lon": lon, "hr": 90,
            "skin_distance_cm": 0.4, "battery": 90}
    base.update(kw)
    return base


@pytest.fixture
def post(client):
    def _post(child_id, lat, lon, **kw):
        res = client.post("/ingest", json=reading(child_id, lat, lon, **kw))
        assert res.status_code == 200, res.text
        return res.json()
    return _post


@pytest.fixture
def now():
    return time.time
