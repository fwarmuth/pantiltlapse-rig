import asyncio
import logging
from typing import Any

logger = logging.getLogger("CameraCommander.Serial")


class SerialManager:
    """
    Manages serial communication between Raspberry Pi Zero 2 W and the NodeMCU/ESP motor controller.
    Uses the single production serial protocol (9600 baud ASCII).
    Thread/Task safe with an internal asyncio.Lock.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        fallback_ports: list[str] | None = None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.fallback_ports = (
            ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"]
            if fallback_ports is None
            else list(fallback_ports)
        )
        self.is_connected = False

        # Telemetry state
        self.current_pan = 0.0
        self.current_tilt = 0.0
        self.drivers_enabled = True
        self.state = "DISCONNECTED"  # DISCONNECTED, IDLE, MOVING, ERROR

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._move_tasks: set[asyncio.Task[dict[str, Any]]] = set()
        self._stopping = False

    async def _open_port(self, port_path: str) -> bool:
        """Internal helper to open a specific serial port and establish initial handshakes."""
        import serial_asyncio

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=port_path, baudrate=self.baudrate
        )
        self.is_connected = True
        self.state = "IDLE"
        self.port = port_path
        logger.info(f"Connected to motor controller on {port_path} at {self.baudrate} baud.")

        # Allow ESP/NodeMCU hardware to complete reset after DTR toggle
        await asyncio.sleep(1.5)

        # Flush any boot banner text lines from serial buffer
        await self._flush_input_buffer()

        # Query version and initial status (unlocked to avoid reentrant deadlock when called from reconnect())
        await self._send_command_unlocked("V", timeout=2.0)
        await self._send_command_unlocked("S", timeout=2.0)
        return True

    async def connect(self) -> bool:
        """Attempt connection to configured serial endpoint or fallback priority ports."""
        candidate_ports = [self.port]
        for fallback in self.fallback_ports:
            if fallback not in candidate_ports:
                candidate_ports.append(fallback)

        for idx, port_path in enumerate(candidate_ports):
            try:
                if await self._open_port(port_path):
                    return True
            except Exception as e:
                if idx == 0:
                    logger.warning(
                        f"Failed to open primary serial port '{port_path}': {e}. "
                        f"Attempting fallback ports {candidate_ports[1:]}..."
                    )
                else:
                    logger.debug(f"Fallback port '{port_path}' failed: {e}")

        logger.warning(
            f"Failed to open serial port across all candidate paths {candidate_ports}. Motors remain disconnected."
        )
        self.is_connected = False
        self.state = "DISCONNECTED"
        self._reader = None
        self._writer = None
        return False

    async def disconnect(self):
        """Close serial connection if open."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing serial writer: {e}")
        self._reader = None
        self._writer = None
        self.is_connected = False
        self.state = "DISCONNECTED"

    async def reconnect(self) -> bool:
        """Disconnect and attempt to reconnect serial port."""
        async with self._lock:
            await self.disconnect()
            return await self.connect()

    async def _flush_input_buffer(self):
        """Drain any stale boot banner lines from serial reader."""
        await self._drain_unread_lines(timeout=0.15, max_lines=20)

    async def _drain_unread_lines(self, timeout: float = 0.02, max_lines: int = 20):
        """Drain any lingering unread lines from the serial reader buffer to prevent desync."""
        if not self._reader:
            return
        for _ in range(max_lines):
            try:
                line_bytes = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
                if not line_bytes:
                    break
                decoded = line_bytes.decode("ascii", errors="replace").strip()
                if decoded:
                    logger.debug(f"Drained unread serial line: '{decoded}'")
                    self._parse_response(decoded)
            except asyncio.TimeoutError:
                break
            except Exception as e:
                logger.debug(f"Exception while draining serial buffer: {e}")
                break

    async def _send_command_unlocked(self, cmd_clean: str, timeout: float | None = 3.0) -> dict[str, Any]:
        """Low-level sender without acquiring self._lock (caller must hold self._lock or be initializing)."""
        if not self._writer or not self._reader:
            self.is_connected = False
            self.state = "DISCONNECTED"
            return {"status": "ERROR", "message": "Not connected"}

        try:
            # Drain any stale unread lines before writing the new command
            await self._drain_unread_lines()

            msg = f"{cmd_clean}\n"
            self._writer.write(msg.encode("ascii"))
            await self._writer.drain()

            deadline = (asyncio.get_running_loop().time() + timeout) if timeout is not None else None

            while True:
                if deadline is not None:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        logger.warning(f"Serial command '{cmd_clean}' timed out waiting for response ({timeout}s)")
                        return {"status": "TIMEOUT", "message": f"Serial command '{cmd_clean}' timed out"}
                    response_bytes = await asyncio.wait_for(self._reader.readline(), timeout=remaining)
                else:
                    response_bytes = await self._reader.readline()

                response = response_bytes.decode("ascii", errors="replace").strip()
                if not response:
                    continue

                self._parse_response(response)

                # For move commands ('M ...'), absorb intermediate/queued STATUS lines and keep waiting for DONE
                if cmd_clean.startswith("M ") and response.startswith("STATUS"):
                    logger.debug(f"Absorbed queued/intermediate status during move: '{response}'")
                    continue

                if response.startswith("ERR"):
                    return {"status": "ERROR", "message": response}

                return {"status": "OK", "response": response}
        except asyncio.TimeoutError:
            logger.warning(f"Serial command '{cmd_clean}' timed out waiting for response ({timeout}s)")
            return {"status": "TIMEOUT", "message": f"Serial command '{cmd_clean}' timed out"}
        except Exception as e:
            logger.error(f"Serial communication error: {e}")
            self.is_connected = False
            self.state = "ERROR"
            return {"status": "ERROR", "message": str(e)}

    async def send_command(self, cmd_str: str, timeout: float | None = 3.0) -> dict[str, Any]:
        """Send ASCII command string to motor controller (e.g. 'M 10.0 5.0' or 'S'). Strictly serialized via Lock."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}

        cmd_clean = cmd_str.strip()
        logger.info(f"Serial Command: '{cmd_clean}'")

        async with self._lock:
            return await self._send_command_unlocked(cmd_clean, timeout=timeout)

    def _parse_response(self, resp: str):
        """Parse status response from NodeMCU/ESP controller."""
        if resp.startswith("STATUS"):
            parts = resp.split()
            if len(parts) >= 4:
                try:
                    self.current_pan = float(parts[1])
                    self.current_tilt = float(parts[2])
                    self.drivers_enabled = parts[3] == "1"
                except ValueError:
                    pass

    async def move_absolute(self, pan: float, tilt: float) -> dict[str, Any]:
        """Move motors to absolute target angles in degrees."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}
        if self._stopping:
            return {"status": "ERROR", "message": "Emergency stop in progress"}

        self.state = "MOVING"
        task = asyncio.create_task(self._move_absolute_transaction(pan, tilt))
        self._move_tasks.add(task)
        task.add_done_callback(self._move_tasks.discard)
        return await asyncio.shield(task)

    async def _move_absolute_transaction(self, pan: float, tilt: float) -> dict[str, Any]:
        """Run a complete move transaction while retaining a cancellable command task."""
        async with self._lock:
            self.state = "MOVING"
            cmd_clean = f"M {pan:.2f} {tilt:.2f}"
            res = await self._send_command_unlocked(cmd_clean, timeout=60.0)
            if res.get("status") == "OK" and res.get("response") == "DONE":
                self.current_pan = pan
                self.current_tilt = tilt
                self.state = "IDLE"
            else:
                if res.get("status") == "OK":
                    res = {
                        "status": "ERROR",
                        "message": f"Unexpected motor move response: {res.get('response', '')}",
                    }
                self.state = "ERROR"
            return res

    async def move_relative(self, delta_pan: float, delta_tilt: float) -> dict[str, Any]:
        """Move motors relative to current position."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}

        target_pan = self.current_pan + delta_pan
        target_tilt = self.current_tilt + delta_tilt
        return await self.move_absolute(target_pan, target_tilt)

    async def stop(self, timeout: float = 2.0) -> dict[str, Any]:
        """Interrupt pending moves, stop both axes, and synchronize the reported pose."""
        async with self._stop_lock:
            self._stopping = True
            try:
                pending_moves = [task for task in self._move_tasks if not task.done()]
                for task in pending_moves:
                    task.cancel()
                if pending_moves:
                    await asyncio.gather(*pending_moves, return_exceptions=True)

                if not self.is_connected:
                    return {"status": "ERROR", "message": "Serial motor controller disconnected"}

                self.state = "STOPPING"
                async with self._lock:
                    res = await self._send_stop_unlocked(timeout)
                    if res.get("status") != "OK":
                        self.is_connected = False
                        self.state = "ERROR"
                        return res

                    status_res = await self._send_command_unlocked("S", timeout=timeout)
                    if status_res.get("status") != "OK" or not status_res.get("response", "").startswith("STATUS"):
                        self.is_connected = False
                        self.state = "ERROR"
                        return {
                            "status": "ERROR",
                            "message": "Motors stopped, but position synchronization failed; reconnect required",
                            "stop_response": res.get("response"),
                            "status_response": status_res,
                        }

                self.state = "IDLE"
                return res
            finally:
                self._stopping = False

    async def _send_stop_unlocked(self, timeout: float) -> dict[str, Any]:
        """Send X and discard replies from the interrupted transaction until OK STOP."""
        if not self._writer or not self._reader:
            self.is_connected = False
            self.state = "DISCONNECTED"
            return {"status": "ERROR", "message": "Not connected"}

        try:
            self._writer.write(b"X\n")
            await self._writer.drain()
            deadline = asyncio.get_running_loop().time() + timeout

            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                response_bytes = await asyncio.wait_for(self._reader.readline(), timeout=remaining)
                response = response_bytes.decode("ascii", errors="replace").strip()
                self._parse_response(response)

                if response == "OK STOP":
                    return {"status": "OK", "response": response}
                if not response or response.startswith("ERR"):
                    return {"status": "ERROR", "message": response or "Empty response from motor controller"}

                logger.warning(f"Discarding pre-stop serial response while awaiting OK STOP: '{response}'")
        except asyncio.TimeoutError:
            logger.warning(f"Emergency stop timed out waiting for acknowledgement ({timeout}s)")
            return {"status": "TIMEOUT", "message": "Emergency stop timed out"}
        except Exception as e:
            logger.error(f"Emergency stop serial communication error: {e}")
            self.is_connected = False
            self.state = "ERROR"
            return {"status": "ERROR", "message": str(e)}

    async def set_drivers(self, enable: bool) -> dict[str, Any]:
        """Enable ('e') or Disable ('d') motor drivers."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}

        cmd = "e" if enable else "d"
        res = await self.send_command(cmd)
        if res.get("status") == "OK":
            self.drivers_enabled = enable
        return res

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "state": self.state,
            "drivers_enabled": self.drivers_enabled,
            "pan": round(self.current_pan, 2),
            "tilt": round(self.current_tilt, 2),
        }
