import os

import pytest
from fastapi.testclient import TestClient

from camera_manager import CameraManager
from fake_camera_manager import FakeCameraManager
from main import app, serial_mgr
from serial_manager import SerialManager


@pytest.mark.asyncio
async def test_disconnected_serial_manager():
    sm = SerialManager(port="/dev/nonexistent_tty_device_12345")
    connected = await sm.connect()
    assert connected is False
    assert sm.is_connected is False
    assert sm.get_status()["connected"] is False

    res = await sm.move_absolute(10.0, 5.0)
    assert res["status"] == "ERROR"
    assert "disconnected" in res["message"].lower()


@pytest.mark.asyncio
async def test_fake_camera_manager(tmp_path):
    capture_dir = str(tmp_path / "captures")
    fake_cam = FakeCameraManager(capture_dir=capture_dir)
    await fake_cam.initialize()

    status_data = fake_cam.get_status()
    assert status_data["connected"] is True
    assert status_data["camera_type"] == "fake"
    assert status_data["mock_mode"] is True

    # Test config
    cfg_res = await fake_cam.set_config("iso", "800")
    assert cfg_res["status"] == "OK"
    assert fake_cam.iso == "800"

    # Test capture
    cap_res = await fake_cam.trigger_capture("test.jpg")
    assert cap_res["status"] == "OK"
    assert os.path.exists(cap_res["path"])


@pytest.mark.asyncio
async def test_real_camera_manager_disconnected_no_fake_fallback(tmp_path):
    capture_dir = str(tmp_path / "captures")
    cam = CameraManager(capture_dir=capture_dir)
    # Attempting to connect without a real camera should result in disconnected state
    # without silently switching to fake camera.
    connected = await cam.connect_camera()
    assert cam.get_status()["mock_mode"] is False
    assert cam.get_status()["camera_type"] == "gphoto2"
    if not connected:
        assert cam.is_connected is False
        cap_res = await cam.trigger_capture("should_fail.jpg")
        assert cap_res["status"] == "ERROR"


def test_fastapi_motor_disconnected_returns_503():
    # Ensure serial_mgr is marked disconnected
    serial_mgr.is_connected = False
    with TestClient(app) as client:
        response = client.post("/api/motors/move", json={"pan": 10.0, "tilt": 5.0, "relative": False})
        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
