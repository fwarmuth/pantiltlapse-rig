import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import main
from coordinator import OperationCoordinator
from domain.rig import RigManager
from fake_camera_manager import FakeCameraManager
from preview_controller import PreviewController
from serial_manager import SerialManager


@pytest.fixture(autouse=True)
def reset_operation_state(monkeypatch, tmp_path):
    coordinator = OperationCoordinator()
    serial = SerialManager(fallback_ports=[])
    serial.is_connected = True
    serial.state = "IDLE"
    camera = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    camera.is_connected = True
    monkeypatch.setattr(main, "coordinator", coordinator)
    monkeypatch.setattr(main, "serial_mgr", serial)
    monkeypatch.setattr(main, "rig_mgr", RigManager(storage_dir=tmp_path / "rig"))
    monkeypatch.setattr(main, "camera_mgr", camera)
    monkeypatch.setattr(main, "preview_controller", PreviewController(camera, coordinator))

    @asynccontextmanager
    async def no_hardware_lifespan(app):
        yield

    monkeypatch.setattr(main.app.router, "lifespan_context", no_hardware_lifespan)


def test_confirm_zero_requires_connected_controller():
    main.serial_mgr.is_connected = False
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.confirm_physical_zero())
    assert exc.value.status_code == 503
    assert main.rig_mgr.reference.confirmed is False


def test_confirm_zero_requires_successful_reset(monkeypatch):
    called = False

    async def rejected(command: str, timeout=None):
        nonlocal called
        called = True
        main.serial_mgr.is_connected = True
        return {"status": "ERROR", "message": "reset rejected"}

    monkeypatch.setattr(main.serial_mgr, "send_command", rejected)
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.confirm_physical_zero())
    assert exc.value.status_code == 503
    assert called is True
    assert main.rig_mgr.reference.confirmed is False


def test_motor_disconnect_invalidates_reference(monkeypatch):
    async def disconnect():
        main.serial_mgr.is_connected = False
        main.serial_mgr.state = "DISCONNECTED"

    monkeypatch.setattr(main.serial_mgr, "disconnect", disconnect)
    main.rig_mgr.confirm_reference()
    with TestClient(main.app) as client:
        response = client.post("/api/motors/disconnect")
    assert response.status_code == 200
    assert response.json()["motors"]["connected"] is False
    assert response.json()["reference"]["confirmed"] is False


def test_motor_reconnect_invalidates_reference(monkeypatch):
    async def reconnect():
        main.serial_mgr.is_connected = True
        main.serial_mgr.state = "IDLE"
        return True

    monkeypatch.setattr(main.serial_mgr, "reconnect", reconnect)
    main.rig_mgr.confirm_reference()
    with TestClient(main.app) as client:
        response = client.post("/api/motors/reconnect")
    assert response.status_code == 200
    assert response.json()["reference"]["confirmed"] is False


def test_camera_disconnect_stops_preview_with_controller(monkeypatch):
    stopped = False

    async def stop_preview():
        nonlocal stopped
        stopped = True
        await main.coordinator.release("PREVIEW")
        return {"status": "OK", "state": "IDLE"}

    monkeypatch.setattr(main.preview_controller, "stop", stop_preview)
    monkeypatch.setattr(main.camera_mgr, "close", lambda: setattr(main.camera_mgr, "is_connected", False))
    main.coordinator.is_previewing = True
    with TestClient(main.app) as client:
        response = client.post("/api/camera/disconnect")
    assert response.status_code == 200
    assert stopped is True


def test_motor_lifecycle_rejected_during_recording():
    asyncio.run(main.coordinator.acquire("RECORDING"))
    with TestClient(main.app) as client:
        response = client.post("/api/motors/disconnect")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_recording_cannot_acquire_during_zero_confirmation(monkeypatch):
    entered = asyncio.Event()
    unblock = asyncio.Event()

    async def blocked_command(command: str, timeout=None):
        entered.set()
        await unblock.wait()
        return {"status": "OK", "response": "STATUS 0 0 1"}

    monkeypatch.setattr(main.serial_mgr, "send_command", blocked_command)
    task = asyncio.create_task(main.confirm_physical_zero())
    await entered.wait()
    assert await main.coordinator.acquire("RECORDING") is False
    unblock.set()
    await task


@pytest.mark.asyncio
async def test_dry_run_cannot_acquire_during_motor_reconnect(monkeypatch):
    entered = asyncio.Event()
    unblock = asyncio.Event()

    async def blocked_reconnect():
        entered.set()
        await unblock.wait()
        return True

    monkeypatch.setattr(main.serial_mgr, "reconnect", blocked_reconnect)
    task = asyncio.create_task(main.reconnect_motors())
    await entered.wait()
    assert await main.coordinator.acquire("DRY_RUN", "test-plan") is False
    unblock.set()
    await task


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reconnect_camera", "disconnect_camera"])
async def test_cancelled_preview_cleanup_releases_maintenance(monkeypatch, action):
    entered = asyncio.Event()

    async def blocked_stop():
        entered.set()
        await asyncio.Event().wait()

    main.coordinator.is_previewing = True
    monkeypatch.setattr(main.preview_controller, "stop", blocked_stop)
    task = asyncio.create_task(getattr(main, action)())
    await asyncio.wait_for(entered.wait(), timeout=1)
    assert main.coordinator.is_maintenance
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not main.coordinator.is_maintenance
