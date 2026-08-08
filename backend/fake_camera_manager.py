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

    async def get_config_choices(self) -> dict[str, list[str]]:
        """Return explicit simulation camera choice lists."""
        if not self.is_connected:
            raise Exception("Fake camera is disconnected")

        return {
            "iso": ["100", "200", "400", "800", "1600", "3200", "6400", "12800"],
            "shutter_speed": [
                "1/4000", "1/2000", "1/1000", "1/500", "1/250", "1/125", "1/60",
                "1/30", "1/15", "1/8", "1/4", "1/2", "1", "2", "4", "8", "15", "30"
            ],
            "aperture": ["f/1.4", "f/1.8", "f/2", "f/2.8", "f/3.5", "f/4", "f/5.6", "f/8", "f/11", "f/16", "f/22"]
        }

    async def set_config(self, param: str, value: str) -> dict[str, Any]:
        supported_params = {"iso", "shutter_speed", "aperture"}
        if param not in supported_params:
            return {"status": "ERROR", "message": f"Unsupported parameter '{param}'"}

        setattr(self, param, str(value))
        logger.info(f"Fake camera config set: {param} -> {value}")
        return {"status": "OK", "param": param, "value": str(value), "fake": True}

    async def trigger_capture(self, filename: str | None = None, target_dir: str | None = None) -> dict[str, Any]:
        """Simulate camera shutter release delay and create placeholder file."""
        if not self.is_connected:
            return {"status": "ERROR", "message": "Fake camera not initialized"}

        await asyncio.sleep(0.3)  # Realistic capture delay

        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"fake_capture_{timestamp}.jpg"

        dest_dir = os.path.abspath(target_dir) if target_dir else self.capture_dir
        os.makedirs(dest_dir, exist_ok=True)
        target_file = os.path.join(dest_dir, filename)
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

    async def capture_preview_frame(self, gain: float = 1.0) -> bytes:
        """Generate synthetic JPEG preview frame for dark-scene framing live stream."""
        from io import BytesIO

        from PIL import Image, ImageDraw, ImageEnhance

        img = Image.new("RGB", (640, 480), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Draw framing crosshairs & center target
        draw.ellipse([220, 140, 420, 340], outline=(56, 189, 248), width=2)
        draw.line([320, 100, 320, 380], fill=(56, 189, 248), width=1)
        draw.line([160, 240, 480, 240], fill=(56, 189, 248), width=1)

        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        draw.text((20, 20), f"Fake Camera Live View (Gain {gain:.1f}x)", fill=(248, 250, 252))
        cam_text = f"ISO: {self.iso} | Shutter: {self.shutter_speed} | Aperture: {self.aperture}"
        draw.text((20, 40), cam_text, fill=(148, 163, 184))
        draw.text((20, 450), timestamp_str, fill=(148, 163, 184))

        if gain > 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(min(4.0, gain))

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
