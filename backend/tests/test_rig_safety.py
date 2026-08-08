import pytest
from fastapi.testclient import TestClient

from main import app, rig_mgr, serial_mgr


def test_rig_safety_workflow(monkeypatch):
    async def mock_send_command(cmd: str):
        return {"status": "OK", "response": "OK"}
    monkeypatch.setattr(serial_mgr, "send_command", mock_send_command)

    with TestClient(app) as client:
        # Force serial_mgr connected state inside active lifespan
        serial_mgr.is_connected = True

        # 1. Startup check: Reference should be unconfirmed
        resp = client.get("/api/rig/status")
        assert resp.status_code == 200
        rig_data = resp.json()
        assert rig_data["reference"]["confirmed"] is False
        assert rig_data["snapshot"]["tilt_min_deg"] == 0.0
        assert rig_data["snapshot"]["tilt_max_deg"] == 80.0

        # 2. Planned absolute move before confirmation -> HTTP 409 Conflict
        resp = client.post("/api/motors/move", json={"pan": 10.0, "tilt": 20.0, "relative": False})
        assert resp.status_code == 409
        assert "unconfirmed" in resp.json()["detail"]["message"].lower()

        # 3. Confirm zero reference -> HTTP 200 OK
        resp = client.post("/api/rig/confirm-zero")
        assert resp.status_code == 200
        assert resp.json()["reference"]["confirmed"] is True

        # 4. Out-of-bounds move (tilt=90° > 80°) -> HTTP 422 Unprocessable Entity
        resp = client.post("/api/motors/move", json={"pan": 10.0, "tilt": 90.0, "relative": False})
        assert resp.status_code == 422
        assert "violates rig bounds" in resp.json()["detail"]["message"].lower()

        # 5. Out-of-bounds move below min (tilt=-5° < 0°) -> HTTP 422
        resp = client.post("/api/motors/move", json={"pan": 10.0, "tilt": -5.0, "relative": False})
        assert resp.status_code == 422

        # 6. Toggle motor drivers -> Invalidates zero confirmation
        resp = client.post("/api/motors/drivers", json={"enable": False})
        assert resp.status_code == 200
        assert rig_mgr.reference.confirmed is False

        # 7. Verify absolute move is blocked again after driver toggle
        resp = client.post("/api/motors/move", json={"pan": 10.0, "tilt": 20.0, "relative": False})
        assert resp.status_code == 409


def test_emergency_stop_always_available():
    with TestClient(app) as client:
        serial_mgr.is_connected = True
        rig_mgr.reference.confirmed = False

        # Stop command should succeed even if reference is unconfirmed
        resp = client.post("/api/motors/stop")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sse_events_stream_json_serialization():
    from main import stream_events
    response = await stream_events()
    gen = response.body_iterator
    chunk = await anext(gen)
    assert chunk.startswith("data: ")
    import json
    data = json.loads(chunk[6:].strip())
    assert "rig" in data
    assert "reference" in data
    assert "coordinate_reference_id" in data["rig"]
