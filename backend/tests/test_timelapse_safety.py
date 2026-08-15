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
