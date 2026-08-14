import asyncio
import logging
import time
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from domain.models import AcquisitionProfile, PreviewProfile

logger = logging.getLogger("CameraCommander.Preview")


class PreviewStatus(BaseModel):
    state: str = Field(default="IDLE", description="State: IDLE, STARTING, STREAMING, ERROR")
    active_profile: dict[str, Any] = Field(default_factory=dict)
    digital_gain: float = Field(default=1.0, ge=1.0, le=4.0)
    measured_fps: float = Field(default=0.0, ge=0.0)
    dropped_frames: int = Field(default=0, ge=0)
    resolution: str = Field(default="640x480")
    last_error: str | None = Field(default=None)


class PreviewController:
    """
    Manages dark-scene night-oriented live view streaming.
    Acquires exclusive coordinator lock, applies PreviewProfile settings,
    streams MJPEG frames with telemetry, and restores AcquisitionProfile upon exit.
    """

    def __init__(self, camera_mgr: Any, coordinator: Any):
        self.camera_mgr = camera_mgr
        self.coordinator = coordinator

        self.state: str = "IDLE"  # IDLE, STARTING, STREAMING, ERROR
        self.digital_gain: float = 1.0
        self.preview_profile: PreviewProfile = PreviewProfile()
        self.restoration_profile: AcquisitionProfile = AcquisitionProfile()

        self.measured_fps: float = 0.0
        self.dropped_frames: int = 0
        self.last_error: str | None = None

        self._streaming_event = asyncio.Event()
        self._frame_count = 0
        self._start_time = 0.0

    async def start(
        self,
        preview_profile: PreviewProfile | None = None,
        acquisition_profile: AcquisitionProfile | None = None,
        gain: float = 1.0,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        """Start preview stream, acquiring coordinator lock for plan and applying preview profile."""
        if self.state in ("STARTING", "STREAMING"):
            return {"status": "OK", "state": self.state}

        if not self.camera_mgr.is_connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "ERROR", "message": "Camera is disconnected"},
            )

        acquired = await self.coordinator.acquire("PREVIEW", plan_id=plan_id)
        if not acquired:
            active = self.coordinator.active_mode
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "ERROR", "message": f"Operation lock busy: '{active}' active"},
            )

        self.state = "STARTING"
        self.digital_gain = max(1.0, min(4.0, gain))
        if preview_profile:
            self.preview_profile = preview_profile
        if acquisition_profile:
            self.restoration_profile = acquisition_profile

        try:
            # Apply and verify preview profile settings
            for param, val in [
                ("iso", self.preview_profile.iso),
                ("shutter_speed", self.preview_profile.shutter_speed),
                ("aperture", self.preview_profile.aperture),
            ]:
                res = await self.camera_mgr.set_config(param, val)
                if isinstance(res, dict) and res.get("status") != "OK":
                    raise Exception(f"Failed to apply camera setting '{param}={val}': {res.get('message')}")

            await self.camera_mgr.refresh_config()

            self.state = "STREAMING"
            self._streaming_event.set()
            self._frame_count = 0
            self._start_time = time.time()
            self.dropped_frames = 0
            self.last_error = None
            logger.info(f"Live view streaming started with profile {self.preview_profile.model_dump()}")
            return {"status": "OK", "state": self.state}
        except Exception as e:
            self.state = "ERROR"
            self.last_error = str(e)
            await self.coordinator.release("PREVIEW")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"status": "ERROR", "message": str(e)},
            ) from e

    async def stop(self) -> dict[str, Any]:
        """Stop preview stream, restore acquisition profile settings, and release coordinator lock."""
        if self.state == "IDLE":
            return {"status": "OK", "state": self.state}

        self.state = "IDLE"
        self._streaming_event.clear()

        try:
            # Restore acquisition camera settings
            if self.camera_mgr.is_connected:
                await self.camera_mgr.set_config("iso", self.restoration_profile.iso)
                await self.camera_mgr.set_config("shutter_speed", self.restoration_profile.shutter_speed)
                await self.camera_mgr.set_config("aperture", self.restoration_profile.aperture)
                logger.info(f"Restored camera acquisition settings: {self.restoration_profile.model_dump()}")
        except Exception as e:
            logger.warning(f"Error restoring camera settings on preview stop: {e}")
        finally:
            await self.coordinator.release("PREVIEW")

        return {"status": "OK", "state": self.state}

    async def generate_mjpeg_stream(self):
        """Async generator yielding MJPEG multipart frame bytes with telemetry."""
        while self.state == "STREAMING" and self.camera_mgr.is_connected:
            try:
                frame_bytes = await self._fetch_frame_bytes()
                now = time.time()
                self._frame_count += 1
                elapsed = now - self._start_time
                if elapsed > 0:
                    self.measured_fps = round(self._frame_count / elapsed, 1)

                gain_header = f"X-Digital-Gain: {self.digital_gain}\r\n\r\n".encode("ascii")
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n" + gain_header + frame_bytes + b"\r\n"
                )
                await asyncio.sleep(0.1)  # ~10 FPS stream pacing
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.dropped_frames += 1
                logger.warning(f"Live view frame error: {e}")
                await asyncio.sleep(0.2)

        await self.stop()

    async def _fetch_frame_bytes(self) -> bytes:
        """Fetch real JPEG preview bytes from camera manager or synthetic dark-scene framing JPEG."""
        if hasattr(self.camera_mgr, "capture_preview_frame"):
            return await self.camera_mgr.capture_preview_frame(gain=self.digital_gain)

        from io import BytesIO

        from PIL import Image, ImageDraw, ImageEnhance

        img = Image.new("RGB", (640, 480), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        draw.ellipse([220, 140, 420, 340], outline=(56, 189, 248), width=2)
        draw.line([320, 100, 320, 380], fill=(56, 189, 248), width=1)
        draw.line([160, 240, 480, 240], fill=(56, 189, 248), width=1)

        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        draw.text((20, 20), f"Live View Preview (Gain {self.digital_gain:.1f}x)", fill=(248, 250, 252))
        draw.text((20, 450), timestamp_str, fill=(148, 163, 184))

        if self.digital_gain > 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(min(4.0, self.digital_gain))

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def get_status(self) -> dict[str, Any]:
        return PreviewStatus(
            state=self.state,
            active_profile=self.preview_profile.model_dump(mode="json"),
            digital_gain=self.digital_gain,
            measured_fps=self.measured_fps,
            dropped_frames=self.dropped_frames,
            resolution="640x480",
            last_error=self.last_error,
        ).model_dump(mode="json")
