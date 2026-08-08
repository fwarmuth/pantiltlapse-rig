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

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.is_connected = False

        # Telemetry state
        self.current_pan = 0.0
        self.current_tilt = 0.0
        self.drivers_enabled = True
        self.state = "DISCONNECTED"  # DISCONNECTED, IDLE, MOVING, ERROR

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Attempt connection to physical or emulated serial endpoint. No silent fallback to mock mode."""
        try:
            import serial_asyncio

            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.port, baudrate=self.baudrate
            )
            self.is_connected = True
            self.state = "IDLE"
            logger.info(f"Connected to motor controller on {self.port} at {self.baudrate} baud.")

            # Flush any boot banner text lines from serial buffer
            await self._flush_input_buffer()

            # Query version and initial status
            await self.send_command("V")
            await self.send_command("S")
            return True
        except Exception as e:
            logger.warning(f"Failed to open serial port {self.port}: {e}. Motors remain disconnected.")
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
        if not self._reader:
            return
        for _ in range(20):
            try:
                line = await asyncio.wait_for(self._reader.readline(), timeout=0.15)
                if not line:
                    break
                logger.debug(f"Flushed boot line: {line.decode('ascii', errors='replace').strip()}")
            except asyncio.TimeoutError:
                break

    async def send_command(self, cmd_str: str) -> dict[str, Any]:
        """Send ASCII command string to motor controller (e.g. 'M 10.0 5.0' or 'S'). Strictly serialized via Lock."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}

        cmd_clean = cmd_str.strip()
        logger.info(f"Serial Command: '{cmd_clean}'")

        async with self._lock:
            if not self._writer or not self._reader:
                self.is_connected = False
                self.state = "DISCONNECTED"
                return {"status": "ERROR", "message": "Not connected"}

            try:
                msg = f"{cmd_clean}\n"
                self._writer.write(msg.encode("ascii"))
                await self._writer.drain()

                # Read response line from hardware
                response_bytes = await self._reader.readline()
                response = response_bytes.decode("ascii", errors="replace").strip()
                self._parse_response(response)
                return {"status": "OK", "response": response}
            except Exception as e:
                logger.error(f"Serial communication error: {e}")
                self.is_connected = False
                self.state = "ERROR"
                return {"status": "ERROR", "message": str(e)}

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

        self.state = "MOVING"
        res = await self.send_command(f"M {pan:.2f} {tilt:.2f}")
        if res.get("status") == "OK":
            self.current_pan = pan
            self.current_tilt = tilt
            self.state = "IDLE"
            await self.send_command("S")
        else:
            self.state = "ERROR"
        return res

    async def move_relative(self, delta_pan: float, delta_tilt: float) -> dict[str, Any]:
        """Move motors relative to current position."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}

        target_pan = self.current_pan + delta_pan
        target_tilt = self.current_tilt + delta_tilt
        return await self.move_absolute(target_pan, target_tilt)

    async def stop(self) -> dict[str, Any]:
        """Emergency stop both motor axes."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Serial motor controller disconnected"}

        res = await self.send_command("X")
        self.state = "IDLE"
        return res

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
