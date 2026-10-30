"""Access PIN: protects every data endpoint, leaves the shell and health public."""


def test_open_when_no_pin_is_set(client, child):
    assert client.get(f"/children/{child}/status").status_code == 200
    assert client.get("/auth/check").json() == {"pin_required": False, "ok": True}


def test_pin_blocks_data_without_it(client, child, monkeypatch):
    monkeypatch.setenv("SAFESTEPS_PIN", "4321")
    assert client.get(f"/children/{child}/status").status_code == 401
    assert client.post("/ingest", json={"child_id": child, "gps_lat": 0, "gps_lon": 0, "hr": 80,
                                         "skin_distance_cm": 0.4, "battery": 50}).status_code == 401
    assert client.get("/ai/status").status_code == 401
    assert client.post("/demo/play", json={"scenario": "skin_off"}).status_code == 401


def test_pin_accepts_header_and_query(client, child, monkeypatch):
    monkeypatch.setenv("SAFESTEPS_PIN", "4321")
    assert client.get(f"/children/{child}/status", headers={"x-pin": "4321"}).status_code == 200
    assert client.get(f"/children/{child}/status?pin=4321").status_code == 200


def test_wrong_pin_is_rejected(client, child, monkeypatch):
    monkeypatch.setenv("SAFESTEPS_PIN", "4321")
    assert client.get(f"/children/{child}/status", headers={"x-pin": "0000"}).status_code == 401
    check = client.get("/auth/check", headers={"x-pin": "0000"}).json()
    assert check == {"pin_required": True, "ok": False}


def test_health_and_shell_stay_public(client, monkeypatch):
    monkeypatch.setenv("SAFESTEPS_PIN", "4321")
    assert client.get("/health").status_code == 200
    assert client.get("/band").status_code == 200
    assert client.get("/auth/check").status_code == 200
