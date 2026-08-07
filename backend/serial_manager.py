import asyncio
import logging
from typing import Any

logger = logging.getLogger("CameraCommander.Serial")


class SerialManager:
    """
    Manages serial communication between Raspberry Pi Zero 2 W and the NodeMCU/ESP motor controller.
    Supports physical serial (`9600` baud ASCII protocol) and automatic Mock Mode for desktop testing.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600, mock: bool = True):
        self.port = port
        self.baudrate = baudrate
        self.mock = mock
        self.is_connected = False

        # Telemetry state
        self.current_pan = 0.0
        self.current_tilt = 0.0
        self.drivers_enabled = True
        self.state = "IDLE"  # IDLE, MOVING, ERROR

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> bool:
        if self.mock:
            logger.info("Initializing SerialManager in MOCK mode")
            self.is_connected = True
            return True

        try:
            import serial_asyncio

            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.port, baudrate=self.baudrate
            )
            self.is_connected = True
            logger.info(f"Connected to motor controller on {self.port} at {self.baudrate} baud.")
            # Query version and initial status
            await self.send_command("V")
            await self.send_command("S")
            return True
        except Exception as e:
            logger.warning(f"Failed to open serial port {self.port}: {e}. Falling back to MOCK mode.")
            self.mock = True
            self.is_connected = True
            return True

    async def send_command(self, cmd_str: str) -> dict[str, Any]:
        """Send ASCII command string to motor controller (e.g. 'M 10.0 5.0' or 'S')."""
        cmd_clean = cmd_str.strip()
        logger.info(f"Serial Command: '{cmd_clean}'")

        if self.mock:
            return await self._mock_process_command(cmd_clean)

        if not self._writer:
            return {"status": "ERROR", "message": "Not connected"}

        try:
            msg = f"{cmd_clean}\n"
            self._writer.write(msg.encode("ascii"))
            await self._writer.drain()

            # Read response line from hardware
            response_bytes = await self._reader.readline()
            response = response_bytes.decode("ascii").strip()
            self._parse_response(response)
            return {"status": "OK", "response": response}
        except Exception as e:
            logger.error(f"Serial communication error: {e}")
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
        self.state = "MOVING"
        res = await self.send_command(f"M {pan:.2f} {tilt:.2f}")
        self.current_pan = pan
        self.current_tilt = tilt
        self.state = "IDLE"
        if not self.mock:
            await self.send_command("S")
        return res

    async def move_relative(self, delta_pan: float, delta_tilt: float) -> dict[str, Any]:
        """Move motors relative to current position."""
        target_pan = self.current_pan + delta_pan
        target_tilt = self.current_tilt + delta_tilt
        return await self.move_absolute(target_pan, target_tilt)

    async def stop(self) -> dict[str, Any]:
        """Emergency stop both motor axes."""
        self.state = "IDLE"
        return await self.send_command("X")

    async def set_drivers(self, enable: bool) -> dict[str, Any]:
        """Enable ('e') or Disable ('d') motor drivers."""
        cmd = "e" if enable else "d"
        res = await self.send_command(cmd)
        self.drivers_enabled = enable
        return res

    async def _mock_process_command(self, cmd: str) -> dict[str, Any]:
        """Simulate motor behavior in mock mode."""
        if cmd.startswith("M "):
            parts = cmd[2:].split()
            if len(parts) == 2:
                target_pan, target_tilt = float(parts[0]), float(parts[1])
                self.state = "MOVING"
                await asyncio.sleep(0.3)  # Simulate travel time
                self.current_pan = target_pan
                self.current_tilt = target_tilt
                self.state = "IDLE"
                return {"status": "OK", "response": "DONE"}
        elif cmd == "S":
            status_flag = "1" if self.drivers_enabled else "0"
            resp = f"STATUS {self.current_pan:.3f} {self.current_tilt:.3f} {status_flag}"
            return {"status": "OK", "response": resp}
        elif cmd == "X":
            self.state = "IDLE"
            return {"status": "OK", "response": "OK STOP"}
        elif cmd in ("d", "D"):
            self.drivers_enabled = False
            return {"status": "OK", "response": "OK DRIVERS OFF"}
        elif cmd in ("e", "E"):
            self.drivers_enabled = True
            return {"status": "OK", "response": "OK DRIVERS ON"}
        elif cmd == "V":
            return {"status": "OK", "response": "VERSION 1.0.1 (MOCK)"}

        return {"status": "OK", "response": "OK"}

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "mock_mode": self.mock,
            "port": self.port,
            "baudrate": self.baudrate,
            "state": self.state,
            "drivers_enabled": self.drivers_enabled,
            "pan": round(self.current_pan, 2),
            "tilt": round(self.current_tilt, 2),
        }
