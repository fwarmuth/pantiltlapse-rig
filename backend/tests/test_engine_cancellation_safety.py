import asyncio

import pytest

from coordinator import OperationCoordinator
from domain.rig import RigManager
from dry_run_engine import DryRunEngine
from serial_manager import SerialManager
from timelapse_engine import TimelapseConfig, TimelapseEngine


class NoopCamera:
    async def trigger_capture(self, filename: str):
        return {"status": "OK", "filename": filename}


class DelayedStopSerial:
    def __init__(self):
        self.move_started = asyncio.Event()
        self.stop_started = asyncio.Event()
        self.allow_stop = asyncio.Event()

    async def move_absolute(self, pan: float, tilt: float):
        self.move_started.set()
        await asyncio.Event().wait()

    async def stop(self):
        self.stop_started.set()
        await self.allow_stop.wait()
        return {"status": "OK", "response": "OK STOP"}


class ReconnectingSerial:
    def __init__(self):
        self.moves = 0
        self.reconnects = 0

    async def move_absolute(self, pan: float, tilt: float):
        self.moves += 1
        return {"status": "ERROR", "message": "USB disconnected"}

    async def reconnect(self):
        self.reconnects += 1
        return True


class DelayedStopAckWriter:
    def __init__(self, reader: asyncio.StreamReader):
        self.reader = reader
        self.move_written = asyncio.Event()
        self.stop_written = asyncio.Event()

    def write(self, data: bytes):
        command = data.decode("ascii").strip()
        if command.startswith("M "):
            self.move_written.set()
        elif command == "X":
            self.stop_written.set()
        elif command == "S":
            self.reader.feed_data(b"STATUS 1.000 2.000 1\n")

    async def drain(self):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_timelapse_cancel_holds_ownership_until_physical_stop_finishes(tmp_path):
    rig = RigManager(storage_dir=tmp_path)
    rig.confirm_reference()
    serial = DelayedStopSerial()
    coordinator = OperationCoordinator()
    engine = TimelapseEngine(serial, NoopCamera(), rig, coordinator)

    await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, capture_photo=False))
    await asyncio.wait_for(serial.move_started.wait(), timeout=0.2)
    cancel_task = asyncio.create_task(engine.cancel())
    await asyncio.wait_for(serial.stop_started.wait(), timeout=0.2)

    assert coordinator.active_mode == "RECORDING"
    assert engine._task is not None and not engine._task.done()
    second_start = await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, capture_photo=False))
    assert second_start["status"] == "ERROR"
    assert coordinator.active_mode == "RECORDING"

    serial.allow_stop.set()
    await asyncio.wait_for(cancel_task, timeout=0.5)
    assert coordinator.active_mode == "IDLE"
    assert engine.state == "CANCELLED"


@pytest.mark.asyncio
async def test_real_serial_stop_gate_holds_recording_ownership_until_acknowledged(tmp_path):
    rig = RigManager(storage_dir=tmp_path)
    rig.confirm_reference()
    reader = asyncio.StreamReader()
    writer = DelayedStopAckWriter(reader)
    serial = SerialManager(fallback_ports=[])
    serial._reader = reader
    serial._writer = writer
    serial.is_connected = True
    serial.state = "IDLE"
    coordinator = OperationCoordinator()
    engine = TimelapseEngine(serial, NoopCamera(), rig, coordinator)

    await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, capture_photo=False))
    await asyncio.wait_for(writer.move_written.wait(), timeout=0.2)
    cancel_task = asyncio.create_task(engine.cancel())
    await asyncio.wait_for(writer.stop_written.wait(), timeout=0.2)

    assert coordinator.active_mode == "RECORDING"
    assert engine._task is not None and not engine._task.done()
    blocked_start = await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, capture_photo=False))
    assert blocked_start["status"] == "ERROR"
    assert coordinator.active_mode == "RECORDING"

    reader.feed_data(b"OK STOP\n")
    result = await asyncio.wait_for(cancel_task, timeout=0.5)

    assert result["status"] == "OK"
    assert coordinator.active_mode == "IDLE"
    assert engine.state == "CANCELLED"
    assert serial.state == "IDLE"


@pytest.mark.asyncio
async def test_timelapse_immediate_cancel_releases_coordinator(tmp_path):
    rig = RigManager(storage_dir=tmp_path)
    rig.confirm_reference()
    serial = DelayedStopSerial()
    serial.allow_stop.set()
    coordinator = OperationCoordinator()
    engine = TimelapseEngine(serial, NoopCamera(), rig, coordinator)

    await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, capture_photo=False))
    await engine.cancel()

    assert coordinator.active_mode == "IDLE"
    assert engine.state == "CANCELLED"


@pytest.mark.asyncio
async def test_motor_reconnect_invalidates_reference_without_retrying_absolute_move(tmp_path):
    rig = RigManager(storage_dir=tmp_path)
    original_reference_id = rig.confirm_reference().reference_id
    serial = ReconnectingSerial()
    coordinator = OperationCoordinator()
    engine = TimelapseEngine(serial, NoopCamera(), rig, coordinator)
    engine.motor_retry_delay_s = 0.0

    await engine.start(TimelapseConfig(total_shots=2, interval_s=1.0, capture_photo=False))
    await asyncio.wait_for(engine._task, timeout=0.5)

    assert engine.state == "ERROR"
    assert serial.moves == 1
    assert serial.reconnects == 1
    assert rig.reference.confirmed is False
    assert rig.reference.reference_id != original_reference_id
    assert "Confirm physical zero" in engine.last_error
    assert coordinator.active_mode == "IDLE"


@pytest.mark.asyncio
async def test_dry_run_immediate_cancel_releases_coordinator(tmp_path):
    coordinator = OperationCoordinator()
    await coordinator.acquire("DRY_RUN", "plan-id")
    serial = DelayedStopSerial()
    serial.allow_stop.set()
    engine = DryRunEngine(serial, RigManager(storage_dir=tmp_path), object(), coordinator)
    engine.state = "RUNNING"
    engine._task = asyncio.create_task(asyncio.sleep(60))

    await engine.cancel()

    assert coordinator.active_mode == "IDLE"
    assert engine.state == "CANCELLED"
