import pytest
from fastapi.testclient import TestClient

import main
from fake_camera_manager import FakeCameraManager
from main import app


@pytest.fixture(autouse=True)
def setup_fake_camera(tmp_path):
    fake_cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    fake_cam.is_connected = True
    main.camera_mgr = fake_cam
    yield


def test_get_camera_choices_success():
    with TestClient(app) as client:
        resp = client.get("/api/camera/config/choices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "OK"
        choices = data["choices"]
        assert "iso" in choices
        assert "shutter_speed" in choices
        assert "aperture" in choices
        assert "400" in choices["iso"]
        assert "1/125" in choices["shutter_speed"]


def test_get_camera_choices_disconnected():
    with TestClient(app) as client:
        # Save connection state
        original_state = main.camera_mgr.is_connected
        main.camera_mgr.is_connected = False

        try:
            resp = client.get("/api/camera/config/choices")
            assert resp.status_code == 503
            assert "disconnected" in resp.json()["detail"]["message"].lower()
        finally:
            main.camera_mgr.is_connected = original_state


def test_post_camera_config_validation():
    with TestClient(app) as client:
        # Test valid configuration setting
        resp_valid = client.post("/api/camera/config", json={"param": "iso", "value": "800"})
        assert resp_valid.status_code == 200

        # Test invalid configuration value (should return HTTP 422)
        resp_invalid = client.post("/api/camera/config", json={"param": "iso", "value": "INVALID_ISO_VALUE_999"})
        assert resp_invalid.status_code == 422
        assert "invalid" in resp_invalid.json()["detail"]["message"].lower()
