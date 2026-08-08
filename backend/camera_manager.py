import asyncio
import logging
import os
import time
from typing import Any

try:
    import gphoto2 as gp

    HAS_GPHOTO2 = True
except ImportError:
    HAS_GPHOTO2 = False

logger = logging.getLogger("CameraCommander.Camera")


class CameraManager:
    """
    Manages Canon DSLR camera control via native python-gphoto2 C-bindings.
    Maintains a persistent camera session for fast, zero-latency shutter releases.
    Does NOT include silent fake fallback. If gphoto2 fails, connection fails explicitly.
    """

    def __init__(self, capture_dir: str = "output/captures"):
        self.capture_dir = os.path.abspath(capture_dir)
        os.makedirs(self.capture_dir, exist_ok=True)

        self.model = "Unknown"
        self.is_connected = False
        self.iso = "400"
        self.shutter_speed = "1/125"
        self.aperture = "5.6"
        self.latest_photo_path: str | None = None
        self.last_capture_time: float = 0.0

        self._camera: Any = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        if not HAS_GPHOTO2:
            logger.error("python-gphoto2 package is not installed. CameraManager unavailable.")
            self.is_connected = False
            return False

        return await self.connect_camera()

    async def connect_camera(self) -> bool:
        """Initialize persistent gphoto2 camera session."""
        async with self._lock:
            if not HAS_GPHOTO2:
                self.is_connected = False
                return False

            try:
                logger.info("Initializing persistent python-gphoto2 session...")
                self._camera = gp.Camera()
                self._camera.init()
                self.is_connected = True

                # Extract model from summary
                summary = self._camera.get_summary()
                summary_str = str(summary)
                for line in summary_str.splitlines():
                    if "Manufacturer:" in line or "Model:" in line:
                        self.model = line.strip()
                        break
                if not self.model or self.model == "Unknown":
                    self.model = "Canon EOS DSLR"

                logger.info(f"Connected to persistent camera session: '{self.model}'")
                self._read_configs_nolock()
                return True
            except Exception as e:
                logger.error(f"Failed to open native gphoto2 camera session: {e}")
                self.is_connected = False
                self.model = "Disconnected"
                self._camera = None
                return False

    def _read_configs_nolock(self):
        """Read ISO, shutter speed, and aperture directly from native C config tree."""
        if not self._camera:
            return
        try:
            config = self._camera.get_config()
            try:
                self.iso = str(config.get_child_by_name("iso").get_value())
            except Exception:
                pass
            try:
                self.shutter_speed = str(config.get_child_by_name("shutterspeed").get_value())
            except Exception:
                pass
            try:
                self.aperture = str(config.get_child_by_name("aperture").get_value())
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error reading camera configs: {e}")

    async def refresh_config(self) -> dict[str, str]:
        """Refresh exposure settings from active camera session."""
        if not self.is_connected or not self._camera:
            return {"iso": self.iso, "shutter_speed": self.shutter_speed, "aperture": self.aperture}

        async with self._lock:
            self._read_configs_nolock()

        return {"iso": self.iso, "shutter_speed": self.shutter_speed, "aperture": self.aperture}

    async def set_config(self, param: str, value: str) -> dict[str, Any]:
        """Set ISO, shutter speed, or aperture."""
        key_map = {
            "iso": "iso",
            "shutter_speed": "shutterspeed",
            "aperture": "aperture",
        }
        if param not in key_map:
            return {"status": "ERROR", "message": f"Unsupported parameter '{param}'"}

        child_name = key_map[param]
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        async with self._lock:
            try:
                config = self._camera.get_config()
                child = config.get_child_by_name(child_name)
                child.set_value(value)
                self._camera.set_config(config)
                setattr(self, param, value)
                logger.info(f"Updated camera config '{param}' -> '{value}'")
                return {"status": "OK", "param": param, "value": value}
            except Exception as e:
                logger.error(f"Failed to set camera config '{param}' to '{value}': {e}")
                return {"status": "ERROR", "message": str(e)}

    async def trigger_capture(self, filename: str | None = None) -> dict[str, Any]:
        """Trigger shutter release and save photo to output/captures/."""
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp}.jpg"

        target_file = os.path.join(self.capture_dir, filename)

        async with self._lock:
            try:
                logger.info("Triggering native gphoto2 shutter release...")
                file_path = self._camera.capture(gp.GP_CAPTURE_IMAGE)
                camera_file = self._camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
                camera_file.save(target_file)

                try:
                    self._camera.file_delete(file_path.folder, file_path.name)
                except Exception:
                    pass

                self.latest_photo_path = target_file
                self.last_capture_time = time.time()
                logger.info(f"Photo captured and saved to '{target_file}'")
                return {
                    "status": "OK",
                    "filename": filename,
                    "path": target_file,
                    "timestamp": self.last_capture_time,
                }
            except Exception as e:
                logger.error(f"Native gphoto2 capture error: {e}")
                self.is_connected = False
                return {"status": "ERROR", "message": str(e)}

    def close(self):
        """Close persistent camera session cleanly."""
        if self._camera:
            try:
                logger.info("Closing persistent python-gphoto2 session...")
                self._camera.exit()
                self._camera = None
            except Exception as e:
                logger.error(f"Error closing camera session: {e}")

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "mock_mode": False,
            "camera_type": "gphoto2",
            "model": self.model,
            "iso": self.iso,
            "shutter_speed": self.shutter_speed,
            "aperture": self.aperture,
            "has_latest_photo": self.latest_photo_path is not None and os.path.exists(self.latest_photo_path),
            "latest_photo_filename": os.path.basename(self.latest_photo_path) if self.latest_photo_path else None,
            "last_capture_time": self.last_capture_time,
        }
