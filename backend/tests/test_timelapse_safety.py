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

    async def trigger_capture(self, filename: str, target_dir: str | None = None):
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

    async def trigger_capture(self, filename: str, target_dir: str | None = None):
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


class ConfigTrackingCameraManager:
    def __init__(self):
        self.is_connected = True
        self.configs_set: list[tuple[str, str]] = []
        self.captures = 0

    async def set_config(self, param: str, value: str):
        self.configs_set.append((param, value))
        return {"status": "OK"}

    async def trigger_capture(self, filename: str, target_dir: str | None = None):
        self.captures += 1
        return {"status": "OK", "filename": filename}


def test_timelapse_applies_per_shot_camera_settings(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path)
        rig_mgr.confirm_reference()
        serial_mgr = WorkingSerialManager()
        camera_mgr = ConfigTrackingCameraManager()
        coordinator = OperationCoordinator()
        engine = TimelapseEngine(serial_mgr, camera_mgr, rig_mgr, coordinator)

        # Test validation rejects mismatched count
        with pytest.raises(ValueError, match="camera_settings length must match total_shots"):
            TimelapseConfig(total_shots=2, camera_settings=[{"iso": "100"}])

        cam_settings = [
            {"iso": "100", "shutter_speed": "1/250", "aperture": "4.0", "white_balance": "Auto"},
            {"iso": "400", "shutter_speed": "1/60", "aperture": "4.0", "white_balance": "Daylight"},
        ]
        config = TimelapseConfig(
            total_shots=2,
            interval_s=1.0,
            settle_time_s=0.0,
            camera_settings=cam_settings,
        )
        await engine.start(config)
        await engine._task

        assert engine.state == "COMPLETED"
        assert camera_mgr.captures == 2
        iso_calls = [val for param, val in camera_mgr.configs_set if param == "iso"]
        assert "100" in iso_calls
        assert "400" in iso_calls
        shutter_calls = [val for param, val in camera_mgr.configs_set if param == "shutter_speed"]
        assert "1/250" in shutter_calls
        assert "1/60" in shutter_calls

    asyncio.run(run())


def test_timelapse_adjust_active_run(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path)
        rig_mgr.confirm_reference()
        serial_mgr = WorkingSerialManager()
        camera_mgr = ConfigTrackingCameraManager()
        coordinator = OperationCoordinator()
        engine = TimelapseEngine(serial_mgr, camera_mgr, rig_mgr, coordinator)

        poses_a = [{"pan": 0.0, "tilt": 0.0}, {"pan": 10.0, "tilt": 5.0}, {"pan": 20.0, "tilt": 10.0}]
        config = TimelapseConfig(
            total_shots=3,
            interval_s=1.0,
            settle_time_s=0.0,
            poses=poses_a,
        )
        await engine.start(config)

        # Hot-update remaining poses while running
        poses_b = [{"pan": 0.0, "tilt": 0.0}, {"pan": 15.0, "tilt": 5.0}, {"pan": 35.0, "tilt": 15.0}]
        adjust_res = await engine.adjust_active_run(poses=poses_b)
        assert adjust_res["status"] == "OK"

        await engine._task
        assert engine.state == "COMPLETED"

    asyncio.run(run())

