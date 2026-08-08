import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger("CameraCommander.FakeCamera")


class FakeCameraManager:
    """
    Explicit simulation camera manager for desktop development and hardware isolation.
    Mimics gphoto2 exposure settings, realistic async delays, and placeholder image creation.
    Exposes an obvious 'fake' status.
    """

    def __init__(self, capture_dir: str = "output/captures"):
        self.capture_dir = os.path.abspath(capture_dir)
        os.makedirs(self.capture_dir, exist_ok=True)

        self.model = "Fake Camera (Simulation)"
        self.is_connected = False
        self.iso = "400"
        self.shutter_speed = "1/125"
        self.aperture = "5.6"
        self.latest_photo_path: str | None = None
        self.last_capture_time: float = 0.0

    async def initialize(self) -> bool:
        logger.info("Initializing FakeCameraManager...")
        self.is_connected = True
        return True

    async def refresh_config(self) -> dict[str, str]:
        return {"iso": self.iso, "shutter_speed": self.shutter_speed, "aperture": self.aperture}

    async def set_config(self, param: str, value: str) -> dict[str, Any]:
        supported_params = {"iso", "shutter_speed", "aperture"}
        if param not in supported_params:
            return {"status": "ERROR", "message": f"Unsupported parameter '{param}'"}

        setattr(self, param, str(value))
        logger.info(f"Fake camera config set: {param} -> {value}")
        return {"status": "OK", "param": param, "value": str(value), "fake": True}

    async def trigger_capture(self, filename: str | None = None) -> dict[str, Any]:
        """Simulate camera shutter release delay and create placeholder file."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Fake camera not initialized"}

        await asyncio.sleep(0.3)  # Realistic capture delay

        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"fake_capture_{timestamp}.jpg"

        target_file = os.path.join(self.capture_dir, filename)
        self._create_placeholder_image(target_file)

        self.latest_photo_path = target_file
        self.last_capture_time = time.time()
        logger.info(f"Fake camera captured photo: {target_file}")

        return {
            "status": "OK",
            "fake": True,
            "filename": filename,
            "path": target_file,
            "timestamp": self.last_capture_time,
        }

    def close(self):
        logger.info("Closing FakeCameraManager session.")

    def _create_placeholder_image(self, file_path: str):
        """Create lightweight placeholder preview file."""
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        if file_path.endswith(".svg"):
            content = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">\n'
                '  <rect width="640" height="480" fill="#0f172a"/>\n'
                '  <circle cx="320" cy="240" r="120" fill="none" stroke="#38bdf8" stroke-width="4"/>\n'
                '  <text x="320" y="230" fill="#f8fafc" font-family="sans-serif" font-size="18" '
                'text-anchor="middle">CameraCommander Fake Capture</text>\n'
                f'  <text x="320" y="260" fill="#94a3b8" font-family="sans-serif" font-size="14" '
                f'text-anchor="middle">{timestamp_str}</text>\n'
                "</svg>"
            )
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            # Simple SVG or raw bytes format stored for preview
            svg_content = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">\n'
                '  <rect width="640" height="480" fill="#0f172a"/>\n'
                '  <circle cx="320" cy="240" r="120" fill="none" stroke="#38bdf8" stroke-width="4"/>\n'
                '  <text x="320" y="230" fill="#f8fafc" font-family="sans-serif" font-size="18" '
                'text-anchor="middle">CameraCommander Fake Capture</text>\n'
                f'  <text x="320" y="260" fill="#94a3b8" font-family="sans-serif" font-size="14" '
                f'text-anchor="middle">{timestamp_str}</text>\n'
                "</svg>"
            )
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(svg_content)

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "mock_mode": True,
            "camera_type": "fake",
            "model": self.model,
            "iso": self.iso,
            "shutter_speed": self.shutter_speed,
            "aperture": self.aperture,
            "has_latest_photo": self.latest_photo_path is not None and os.path.exists(self.latest_photo_path),
            "latest_photo_filename": os.path.basename(self.latest_photo_path) if self.latest_photo_path else None,
            "last_capture_time": self.last_capture_time,
        }
