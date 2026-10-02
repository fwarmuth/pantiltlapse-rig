import asyncio
import logging
from typing import Any

logger = logging.getLogger("CameraCommander.FakeSerial")


class FakeSerialManager:
    """
    Simulation serial motor manager for desktop development and hardware isolation.
    Simulates motor movements, limits, and driver state with realistic delays.
    """

    def __init__(self, port: str = "SIMULATION", baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.is_connected = False
        self.current_pan = 0.0
        self.current_tilt = 0.0
        self.drivers_enabled = True
        self.state = "IDLE"  # IDLE, MOVING, DISCONNECTED

    async def connect(self) -> bool:
        logger.info("Connected to simulated motor controller (FakeSerialManager).")
        self.is_connected = True
        self.state = "IDLE"
        return True

    async def disconnect(self):
        logger.info("Disconnected from simulated motor controller.")
        self.is_connected = False
        self.state = "DISCONNECTED"

    async def reconnect(self) -> bool:
        self.is_connected = True
        self.state = "IDLE"
        return True

    async def move_absolute(self, pan: float, tilt: float) -> dict[str, Any]:
        """Simulate moving motors to target pan/tilt coordinates."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Motor controller is disconnected"}

        self.state = "MOVING"
        # Small realistic motion delay (0.05s) for smooth simulation
        await asyncio.sleep(0.05)
        self.current_pan = round(float(pan), 2)
        self.current_tilt = round(float(tilt), 2)
        self.state = "IDLE"
        logger.debug(f"Simulated move complete: Pan={self.current_pan}°, Tilt={self.current_tilt}°")
        return {"status": "OK", "pan": self.current_pan, "tilt": self.current_tilt}

    async def move_relative(self, delta_pan: float, delta_tilt: float) -> dict[str, Any]:
        """Simulate relative motor step adjustment."""
        target_pan = self.current_pan + delta_pan
        target_tilt = self.current_tilt + delta_tilt
        return await self.move_absolute(target_pan, target_tilt)

    async def stop(self, timeout: float = 2.0) -> dict[str, Any]:
        """Simulate emergency stop."""
        self.state = "IDLE"
        logger.info("Simulated motors stopped.")
        return {"status": "OK"}

    async def send_command(self, cmd_str: str, timeout: float | None = 2.0) -> dict[str, Any]:
        """Simulate sending low-level ASCII commands to motor controller."""
        cmd = cmd_str.strip().upper()
        if cmd == "S":
            drv = 1 if self.drivers_enabled else 0
            resp_str = f"STATUS {self.current_pan:.6f} {self.current_tilt:.6f} {drv}"
            return {
                "status": "OK",
                "response": resp_str,
                "pan": self.current_pan,
                "tilt": self.current_tilt,
                "state": self.state,
                "drivers_enabled": self.drivers_enabled,
            }
        elif cmd == "V":
            return {"status": "OK", "response": "VERSION FakeSerial-v1.0-Sim", "version": "FakeSerial-v1.0-Sim"}
        elif cmd == "H":
            self.current_pan = 0.0
            self.current_tilt = 0.0
            return {"status": "OK", "response": "OK"}
        elif cmd.startswith("E"):
            self.drivers_enabled = True
            self.current_pan = 0.0
            self.current_tilt = 0.0
            return {"status": "OK", "response": "OK"}
        elif cmd.startswith("D"):
            self.drivers_enabled = False
            return {"status": "OK", "response": "OK"}
        return {"status": "OK", "response": "OK"}

    async def set_drivers(self, enable: bool) -> dict[str, Any]:
        """Enable or disable simulated motor drivers."""
        self.drivers_enabled = enable
        logger.info(f"Simulated motor drivers {'enabled' if enable else 'disabled'}.")
        return {"status": "OK"}

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
