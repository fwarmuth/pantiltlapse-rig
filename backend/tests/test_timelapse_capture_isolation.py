import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from coordinator import OperationCoordinator
from domain.rig import RigManager
from timelapse_engine import TimelapseConfig, TimelapseEngine


class RecordingSerial:
    async def move_absolute(self, pan: float, tilt: float):
        return {"status": "OK"}


class RecordingCamera:
    def __init__(self, capture_dir: Path):
        self.capture_dir = str(capture_dir)
        self.is_connected = True
        self.calls: list[tuple[str, str | None]] = []

    async def trigger_capture(self, filename: str, target_dir: str | None = None):
        self.calls.append((filename, target_dir))
        destination = Path(target_dir or self.capture_dir)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / filename
        path.write_bytes(b"test image")
        return {"status": "OK", "filename": filename, "path": str(path)}


class BlockingCamera(RecordingCamera):
    def __init__(self, capture_dir: Path):
        super().__init__(capture_dir)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.completed = asyncio.Event()

    async def trigger_capture(self, filename: str, target_dir: str | None = None):
        self.started.set()
        await self.release.wait()
        result = await super().trigger_capture(filename, target_dir)
        self.completed.set()
        return result


def test_timelapse_captures_are_isolated_per_run(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path / "rig")
        rig_mgr.confirm_reference()
        camera = RecordingCamera(tmp_path / "captures")
        engine = TimelapseEngine(RecordingSerial(), camera, rig_mgr, OperationCoordinator())
        config = TimelapseConfig(total_shots=2, interval_s=1.0, settle_time_s=0.0)

        first = await engine.start(config)
        await engine._task
        second = await engine.start(config)
        await engine._task

        assert first["status"] == second["status"] == "OK"
        assert first["run_id"] != second["run_id"]
        assert len(camera.calls) == 4

        first_calls = camera.calls[:2]
        second_calls = camera.calls[2:]
        assert all(target_dir for _, target_dir in first_calls + second_calls)
        assert first_calls[0][1] != second_calls[0][1]
        assert first_calls[0][0].startswith(f"tl_{first['run_id']}_")
        assert second_calls[0][0].startswith(f"tl_{second['run_id']}_")
        assert sorted(Path(first_calls[0][1]).iterdir())
        assert sorted(Path(second_calls[0][1]).iterdir())

    asyncio.run(run())


def test_explicit_poses_must_cover_all_shots():
    with pytest.raises(ValidationError, match="poses length must match total_shots"):
        TimelapseConfig(total_shots=2, poses=[])

    with pytest.raises(ValidationError, match="poses length must match total_shots"):
        TimelapseConfig(total_shots=2, poses=[{"pan": 0.0, "tilt": 0.0}])


def test_cancel_waits_for_inflight_capture_before_releasing_recording(tmp_path):
    async def run():
        rig_mgr = RigManager(storage_dir=tmp_path / "rig")
        rig_mgr.confirm_reference()
        coordinator = OperationCoordinator()
        camera = BlockingCamera(tmp_path / "captures")
        engine = TimelapseEngine(RecordingSerial(), camera, rig_mgr, coordinator)

        await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, settle_time_s=0.0))
        await camera.started.wait()
        cancel_task = asyncio.create_task(engine.cancel())
        await asyncio.sleep(0)

        assert coordinator.active_mode == "RECORDING"
        assert not camera.completed.is_set()

        camera.release.set()
        await cancel_task
        await engine._task
        assert camera.completed.is_set()
        assert coordinator.active_mode == "IDLE"

    asyncio.run(run())
