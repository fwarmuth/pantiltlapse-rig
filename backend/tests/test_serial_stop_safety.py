import asyncio

import pytest

from serial_manager import SerialManager


class ScriptedSerialWriter:
    def __init__(self, reader: asyncio.StreamReader, *, acknowledge_stop: bool = True):
        self.reader = reader
        self.acknowledge_stop = acknowledge_stop
        self.commands: list[str] = []
        self.move_written = asyncio.Event()

    def write(self, data: bytes):
        command = data.decode("ascii").strip()
        self.commands.append(command)
        if command.startswith("M "):
            self.move_written.set()
        elif command == "X" and self.acknowledge_stop:
            # Mirror the firmware race where a completed move reply was already
            # buffered immediately before X is parsed.
            self.reader.feed_data(b"DONE\nOK STOP\n")
        elif command == "S":
            self.reader.feed_data(b"STATUS 3.250 4.500 1\n")

    async def drain(self):
        await asyncio.sleep(0)


def make_connected_manager(*, acknowledge_stop: bool = True) -> tuple[SerialManager, ScriptedSerialWriter]:
    manager = SerialManager(fallback_ports=[])
    reader = asyncio.StreamReader()
    writer = ScriptedSerialWriter(reader, acknowledge_stop=acknowledge_stop)
    manager._reader = reader
    manager._writer = writer
    manager.is_connected = True
    manager.state = "IDLE"
    return manager, writer


@pytest.mark.asyncio
async def test_stop_interrupts_active_and_queued_moves_and_realigns_responses():
    manager, writer = make_connected_manager()

    first_move = asyncio.create_task(manager.move_absolute(20.0, 10.0))
    second_move = asyncio.create_task(manager.move_absolute(30.0, 15.0))
    await asyncio.wait_for(writer.move_written.wait(), timeout=0.2)

    stop_result = await asyncio.wait_for(manager.stop(timeout=0.2), timeout=0.5)
    move_results = await asyncio.gather(first_move, second_move, return_exceptions=True)

    assert stop_result == {"status": "OK", "response": "OK STOP"}
    assert all(isinstance(result, asyncio.CancelledError) for result in move_results)
    assert writer.commands == ["M 20.00 10.00", "X", "S"]
    assert manager.current_pan == 3.25
    assert manager.current_tilt == 4.5
    assert manager.state == "IDLE"

    # No stale DONE/OK STOP remains to be mistaken for the next command reply.
    status_result = await manager.send_command("S")
    assert status_result["response"] == "STATUS 3.250 4.500 1"


@pytest.mark.asyncio
async def test_stop_timeout_requires_reconnect_and_blocks_new_moves():
    manager, writer = make_connected_manager(acknowledge_stop=False)
    move = asyncio.create_task(manager.move_absolute(20.0, 10.0))
    await asyncio.wait_for(writer.move_written.wait(), timeout=0.2)

    stop_result = await manager.stop(timeout=0.01)
    move_result = (await asyncio.gather(move, return_exceptions=True))[0]

    assert stop_result["status"] == "TIMEOUT"
    assert isinstance(move_result, asyncio.CancelledError)
    assert manager.is_connected is False
    assert manager.state == "ERROR"
    assert await manager.move_absolute(1.0, 1.0) == {
        "status": "ERROR",
        "message": "Serial motor controller disconnected",
    }
    assert writer.commands == ["M 20.00 10.00", "X"]


@pytest.mark.asyncio
async def test_move_is_rejected_while_stop_transaction_is_active():
    manager, writer = make_connected_manager(acknowledge_stop=False)
    manager._stopping = True

    result = await manager.move_absolute(1.0, 1.0)

    assert result == {"status": "ERROR", "message": "Emergency stop in progress"}
    assert writer.commands == []


@pytest.mark.asyncio
async def test_move_absolute_tolerates_and_absorbs_stray_status_line():
    manager = SerialManager(fallback_ports=[])
    reader = asyncio.StreamReader()

    class StatusThenDoneWriter:
        def __init__(self, r: asyncio.StreamReader):
            self.reader = r
            self.commands: list[str] = []

        def write(self, data: bytes):
            cmd = data.decode("ascii").strip()
            self.commands.append(cmd)
            if cmd.startswith("M "):
                # Simulate the firmware sending a late STATUS line before DONE
                self.reader.feed_data(b"STATUS 19.463 12.041 1\nDONE\n")

        async def drain(self):
            await asyncio.sleep(0)

    writer = StatusThenDoneWriter(reader)
    manager._reader = reader
    manager._writer = writer
    manager.is_connected = True
    manager.state = "IDLE"

    res = await manager.move_absolute(20.15, 12.25)
    assert res == {"status": "OK", "response": "DONE"}
    assert manager.current_pan == 20.15
    assert manager.current_tilt == 12.25
    assert manager.state == "IDLE"


@pytest.mark.asyncio
async def test_move_absolute_drains_prior_unread_bytes():
    manager = SerialManager(fallback_ports=[])
    reader = asyncio.StreamReader()

    # Pre-populate reader with a stale response from a prior timed-out command
    reader.feed_data(b"STATUS 15.000 5.000 1\n")

    class SimpleDoneWriter:
        def __init__(self, r: asyncio.StreamReader):
            self.reader = r
            self.commands: list[str] = []

        def write(self, data: bytes):
            cmd = data.decode("ascii").strip()
            self.commands.append(cmd)
            if cmd.startswith("M "):
                self.reader.feed_data(b"DONE\n")

        async def drain(self):
            await asyncio.sleep(0)

    writer = SimpleDoneWriter(reader)
    manager._reader = reader
    manager._writer = writer
    manager.is_connected = True
    manager.state = "IDLE"

    res = await manager.move_absolute(10.0, 5.0)
    assert res == {"status": "OK", "response": "DONE"}
    assert manager.current_pan == 10.0
    assert manager.current_tilt == 5.0
