import asyncio

import pytest
from fastapi.testclient import TestClient

from fake_camera_manager import FakeCameraManager
from main import app, coordinator, preview_controller


@pytest.fixture(autouse=True)
def setup_live_view_env(tmp_path):
    fake_cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    fake_cam.is_connected = True

    import main
    main.camera_mgr = fake_cam
    preview_controller.camera_mgr = fake_cam
    if coordinator.is_previewing:
        asyncio.run(coordinator.release("PREVIEW"))
    if coordinator.is_dry_running:
        asyncio.run(coordinator.release("DRY_RUN"))
    if coordinator.is_recording:
        asyncio.run(coordinator.release("RECORDING"))

    yield

    # Ensure preview is stopped after test
    asyncio.run(preview_controller.stop())
    if coordinator.is_previewing:
        asyncio.run(coordinator.release("PREVIEW"))
    if coordinator.is_dry_running:
        asyncio.run(coordinator.release("DRY_RUN"))
    if coordinator.is_recording:
        asyncio.run(coordinator.release("RECORDING"))


def test_live_view_start_stop_workflow():
    with TestClient(app) as client:
        # 1. Start Preview
        resp = client.post("/api/camera/preview/start", json={"gain": 2.5})
        assert resp.status_code == 200
        assert resp.json()["state"] == "STREAMING"
        assert coordinator.active_mode == "PREVIEW"

        # 2. Get Preview Status
        resp = client.get("/api/camera/preview/status")
        assert resp.status_code == 200
        status_data = resp.json()
        assert status_data["state"] == "STREAMING"
        assert status_data["digital_gain"] == 2.5

        # 3. Stop Preview
        resp = client.post("/api/camera/preview/stop")
        assert resp.status_code == 200
        assert resp.json()["state"] == "IDLE"
        assert coordinator.active_mode == "IDLE"


def test_live_view_allowed_during_dry_run():
    with TestClient(app) as client:
        # Acquire DRY_RUN lock
        asyncio.run(coordinator.acquire("DRY_RUN"))

        # Preview start should succeed during DRY_RUN
        resp = client.post("/api/camera/preview/start", json={"gain": 1.5})
        assert resp.status_code == 200
        assert resp.json()["state"] == "STREAMING"
        assert coordinator.is_previewing is True
        assert coordinator.is_dry_running is True

        # Stop preview restores state back to DRY_RUN
        client.post("/api/camera/preview/stop")
        assert coordinator.is_previewing is False
        assert coordinator.is_dry_running is True
        asyncio.run(coordinator.release("DRY_RUN"))


def test_live_view_lock_conflict():
    with TestClient(app) as client:
        # Acquire RECORDING lock
        asyncio.run(coordinator.acquire("RECORDING"))

        resp = client.post("/api/camera/preview/start")
        assert resp.status_code == 409
        assert "busy" in resp.json()["detail"]["message"].lower()

        asyncio.run(coordinator.release("RECORDING"))
