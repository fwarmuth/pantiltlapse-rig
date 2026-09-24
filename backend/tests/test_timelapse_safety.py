import asyncio

import pytest
from fastapi import HTTPException

from coordinator import OperationCoordinator
from domain.rig import RigManager
from timelapse_engine import TimelapseConfig, TimelapseEngine


class FailingSerialManager:
    def __init__(self):
        self.moves: list[tuple[float, float]] = []

    async def move_absolute(self, pan: float, tilt: float):
        self.moves.append((pan, tilt))
        return {"status": "ERROR", "message": "Simulated motor stall"}


class FakeCameraManager:
    def __init__(self):
        self.captures = 0

    async def trigger_capture(self, filename: str):
        self.captures += 1
        return {"status": "OK"}


def test_timelapse_requires_confirmed_reference_and_valid_bounds(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path)
        engine = TimelapseEngine(FailingSerialManager(), FakeCameraManager(), rig_mgr, OperationCoordinator())

        with pytest.raises(HTTPException, match="unconfirmed") as exc_info:
            await engine.start(TimelapseConfig())
        assert exc_info.value.status_code == 409

        rig_mgr.confirm_reference()
        with pytest.raises(HTTPException, match="violates rig bounds") as exc_info:
            await engine.start(TimelapseConfig(end_tilt=81.0))
        assert exc_info.value.status_code == 422

    asyncio.run(run())


def test_timelapse_stops_before_capture_when_motor_move_fails(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path)
        rig_mgr.confirm_reference()
        serial_mgr = FailingSerialManager()
        camera_mgr = FakeCameraManager()
        coordinator = OperationCoordinator()
        engine = TimelapseEngine(serial_mgr, camera_mgr, rig_mgr, coordinator)

        await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0))
        await engine._task

        assert engine.state == "ERROR"
        assert "move failed" in engine.last_error
        assert camera_mgr.captures == 0
        assert coordinator.active_mode == "IDLE"

    asyncio.run(run())


class FlakyCameraManager:
    def __init__(self):
        self.is_connected = True
        self.captures = 0
        self.reconnect_calls = 0

    async def trigger_capture(self, filename: str):
        if self.captures == 0 and self.reconnect_calls == 0:
            self.is_connected = False
            return {"status": "ERROR", "message": "Camera disconnected unexpectedly"}
        self.captures += 1
        return {"status": "OK", "filename": filename}

    async def reconnect(self):
        self.reconnect_calls += 1
        self.is_connected = True
        return True


class WorkingSerialManager:
    def __init__(self):
        self.moves: list[tuple[float, float]] = []

    async def move_absolute(self, pan: float, tilt: float):
        self.moves.append((pan, tilt))
        return {"status": "OK", "response": "DONE"}


def test_timelapse_waits_for_camera_reconnect_on_capture_failure(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path)
        rig_mgr.confirm_reference()
        serial_mgr = WorkingSerialManager()
        camera_mgr = FlakyCameraManager()
        coordinator = OperationCoordinator()
        engine = TimelapseEngine(serial_mgr, camera_mgr, rig_mgr, coordinator)
        engine.camera_retry_delay_s = 0.05

        await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, settle_time_s=0.0))
        await engine._task

        assert engine.state == "COMPLETED"
        assert camera_mgr.reconnect_calls >= 1
        assert camera_mgr.captures == 2
        assert len(serial_mgr.moves) == 2
        assert coordinator.active_mode == "IDLE"

    asyncio.run(run())

