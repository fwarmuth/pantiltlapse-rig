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
        """Initialize persistent gphoto2 camera session asynchronously off main event loop."""
        async with self._lock:
            if not HAS_GPHOTO2:
                self.is_connected = False
                return False

            def _init_gphoto():
                try:
                    logger.info("Initializing persistent python-gphoto2 session...")
                    cam = gp.Camera()
                    cam.init()
                    model_name = "Canon EOS DSLR"
                    summary = cam.get_summary()
                    summary_str = str(summary)
                    for line in summary_str.splitlines():
                        if "Manufacturer:" in line or "Model:" in line:
                            model_name = line.strip()
                            break
                    return cam, model_name
                except Exception as e:
                    logger.error(f"Failed to open native gphoto2 camera session: {e}")
                    return None, "Disconnected"

            cam, model_name = await asyncio.to_thread(_init_gphoto)
            if not cam:
                self.is_connected = False
                self.model = "Disconnected"
                self._camera = None
                return False

            self._camera = cam
            self.is_connected = True
            self.model = model_name
            logger.info(f"Connected to persistent camera session: '{self.model}'")
            await asyncio.to_thread(self._read_configs_nolock)
            return True

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

    async def get_config_choices(self) -> dict[str, list[str]]:
        """
        Query native gPhoto2 camera widget choices for iso, shutterspeed, and aperture.
        If camera is disconnected, raises Exception (explicit failure, no silent fallbacks).
        """
        if not self.is_connected or not self._camera:
            raise Exception("Camera is disconnected. Connect real camera or enable FAKE_CAMERA=true in .env")

        async with self._lock:
            try:
                config = self._camera.get_config()
                key_map = {
                    "iso": "iso",
                    "shutter_speed": "shutterspeed",
                    "aperture": "aperture",
                }
                choices: dict[str, list[str]] = {}
                for param, child_name in key_map.items():
                    try:
                        child = config.get_child_by_name(child_name)
                        count = child.count_choices()
                        param_choices = [str(child.get_choice(i)) for i in range(count)]
                        choices[param] = param_choices
                    except Exception as e:
                        logger.warning(f"Could not read choices for widget '{child_name}': {e}")
                        choices[param] = []

                return choices
            except Exception as e:
                logger.error(f"Error reading camera config choices: {e}")
                raise Exception(f"Failed to query camera config choices: {e}") from e

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

        val_str = str(value)
        if param == "aperture":
            val_str = val_str.replace("f/", "").replace("F/", "").strip()

        async with self._lock:
            try:
                config = self._camera.get_config()
                child = config.get_child_by_name(child_name)
                child.set_value(val_str)
                self._camera.set_config(config)
                setattr(self, param, val_str)
                logger.info(f"Updated camera config '{param}' -> '{val_str}'")
                return {"status": "OK", "param": param, "value": val_str}
            except Exception as e:
                logger.error(f"Failed to set camera config '{param}' to '{val_str}': {e}")
                return {"status": "ERROR", "message": str(e)}

    async def trigger_capture(self, filename: str | None = None, target_dir: str | None = None) -> dict[str, Any]:
        """Trigger shutter release and save photo preserving real camera extension."""
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        dest_dir = os.path.abspath(target_dir) if target_dir else self.capture_dir
        os.makedirs(dest_dir, exist_ok=True)

        async with self._lock:
            try:
                logger.info("Triggering native gphoto2 shutter release...")

                def _do_gphoto_capture():
                    file_path = self._camera.capture(gp.GP_CAPTURE_IMAGE)
                    cam_ext = os.path.splitext(file_path.name)[1].lower() or ".jpg"

                    if filename:
                        stem = os.path.splitext(filename)[0]
                        save_name = f"{stem}{cam_ext}"
                    else:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        save_name = f"capture_{timestamp}{cam_ext}"

                    target_file = os.path.join(dest_dir, save_name)
                    camera_file = self._camera.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
                    camera_file.save(target_file)

                    try:
                        self._camera.file_delete(file_path.folder, file_path.name)
                    except Exception:
                        pass

                    return save_name, target_file, cam_ext

                save_name, target_file, cam_ext = await asyncio.to_thread(_do_gphoto_capture)

                self.latest_photo_path = target_file
                self.last_capture_time = time.time()
                logger.info(f"Photo captured and saved to '{target_file}'")

                mime_map = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".cr2": "image/x-canon-cr2",
                    ".cr3": "image/x-canon-cr3",
                    ".nef": "image/x-nikon-nef",
                    ".arw": "image/x-sony-arw",
                }
                mime_type = mime_map.get(cam_ext, "application/octet-stream")

                result = {
                    "camera_filename": save_name,
                    "saved_original_path": target_file,
                    "extension": cam_ext,
                    "mime_type": mime_type,
                    "capture_timestamp": self.last_capture_time,
                    "camera_preview_path": None,
                }

                return {
                    "status": "OK",
                    "filename": save_name,
                    "path": target_file,
                    "timestamp": self.last_capture_time,
                    "result": result,
                }
            except Exception as e:
                logger.error(f"Native gphoto2 capture error: {e}")
                self.is_connected = False
                return {"status": "ERROR", "message": str(e)}

    async def capture_preview_frame(self, gain: float = 1.0) -> bytes:
        """Capture live preview frame bytes from native gPhoto2 camera. Raises on error."""
        if not self.is_connected or not self._camera:
            raise Exception("Camera is disconnected")

        async with self._lock:
            try:
                def _do_preview():
                    camera_file = self._camera.capture_preview()
                    file_data = camera_file.get_data_and_size()
                    return bytes(file_data)

                return await asyncio.to_thread(_do_preview)
            except Exception as e:
                logger.warning(f"Native gphoto2 capture_preview error: {e}")
                raise Exception(f"gphoto2 preview failure: {e}") from e

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
