import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app, rig_mgr, serial_mgr, time_mgr
from time_manager import SystemTimeManager


@pytest.fixture
def client():
    return TestClient(app)


def test_system_time_manager_initial_state():
    mgr = SystemTimeManager()
    assert mgr.synced is False
    assert mgr.time_offset == 0.0
    status = mgr.get_status()
    assert status["synced"] is False
    assert status["time_offset"] == 0.0


def test_system_time_manager_sync_seconds():
    mgr = SystemTimeManager()
    fake_client_time = 1800000000.0  # Epoch seconds in 2027
    with patch("time.clock_settime", side_effect=PermissionError("Permission denied")), \
         patch("subprocess.run", side_effect=Exception("No sudo")):
        res = mgr.sync(fake_client_time, timezone_name="Europe/Berlin")

    assert mgr.synced is True
    assert mgr.client_timezone == "Europe/Berlin"
    assert mgr.os_clock_updated is False
    assert mgr.os_error is not None
    # Rig time should be very close to fake_client_time
    assert abs(mgr.get_current_time() - fake_client_time) < 1.0
    assert abs(res["rig_time"] - fake_client_time) < 1.0


def test_system_time_manager_sync_milliseconds():
    mgr = SystemTimeManager()
    fake_client_time_ms = 1800000000000.0  # Epoch ms
    with patch("time.clock_settime", side_effect=PermissionError("Operation not permitted")), \
         patch("subprocess.run", side_effect=Exception("No sudo")):
        res = mgr.sync(fake_client_time_ms, timezone_name="UTC")

    assert mgr.synced is True
    assert abs(mgr.get_current_time() - 1800000000.0) < 1.0


def test_system_time_manager_os_success():
    mgr = SystemTimeManager()
    target_time = 1750000000.0
    with patch("time.clock_settime") as mock_settime:
        res = mgr.sync(target_time)
        mock_settime.assert_called_once_with(time.CLOCK_REALTIME, target_time)

    assert mgr.synced is True
    assert mgr.os_clock_updated is True
    assert mgr.os_error is None
    assert mgr.time_offset == 0.0


def test_get_system_time_endpoint(client):
    res = client.get("/api/system/time")
    assert res.status_code == 200
    data = res.json()
    assert "synced" in data
    assert "rig_time" in data
    assert "time_offset" in data


def test_post_system_time_sync_endpoint(client):
    target = 1850000000.0
    res = client.post("/api/system/time-sync", json={
        "client_time": target,
        "client_iso": "2028-08-19T06:13:20Z",
        "timezone": "Europe/Berlin"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OK"
    assert "time_sync" in data
    assert abs(data["time_sync"]["rig_time"] - target) < 2.0


def test_confirm_zero_backward_compatibility_no_body(client, monkeypatch):
    async def mock_send_command(cmd: str):
        return {"status": "OK", "response": "STATUS 0.00 0.00 1"}
    monkeypatch.setattr(serial_mgr, "send_command", mock_send_command)
    serial_mgr.is_connected = True

    # Calling confirm-zero with no body must succeed and not fail with 422
    res = client.post("/api/rig/confirm-zero")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OK"
    assert data["reference"]["confirmed"] is True
    assert "time_sync" in data


def test_confirm_zero_with_client_time_payload(client, monkeypatch):
    async def mock_send_command(cmd: str):
        return {"status": "OK", "response": "STATUS 0.00 0.00 1"}
    monkeypatch.setattr(serial_mgr, "send_command", mock_send_command)
    serial_mgr.is_connected = True

    target = 1860000000.0
    res = client.post("/api/rig/confirm-zero", json={
        "client_time": target,
        "client_iso": "2028-12-12T12:00:00Z",
        "timezone": "America/New_York"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OK"
    assert data["reference"]["confirmed"] is True
    assert "time_sync" in data
    assert data["time_sync"]["synced"] is True
    assert abs(data["time_sync"]["rig_time"] - target) < 2.0
    assert data["time_sync"]["timezone"] == "America/New_York"
