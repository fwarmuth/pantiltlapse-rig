import asyncio
import logging
import math
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("CameraCommander.Timelapse")


class TimelapseConfig(BaseModel):
    start_pan: float = Field(default=0.0, description="Start Pan angle in degrees")
    start_tilt: float = Field(default=0.0, description="Start Tilt angle in degrees")
    end_pan: float = Field(default=15.0, description="End Pan angle in degrees")
    end_tilt: float = Field(default=0.0, description="End Tilt angle in degrees")
    total_shots: int = Field(default=10, ge=2, description="Total number of shots in sequence")
    interval_s: float = Field(default=5.0, ge=1.0, description="Interval time between shots (seconds)")
    settle_time_s: float = Field(default=0.5, ge=0.0, description="Settle delay pause after move (seconds)")
    capture_photo: bool = Field(default=True, description="Trigger photo capture on each step")
    easing: str = Field(default="ease_in_out", description="Motion profile: 'linear', 'ease_in_out', or 's_curve'")


class TimelapseEngine:
    """
    Event-driven background state machine for 2-axis automated motion time-lapses.
    Calculates step interpolation with configurable motion easing (Linear, Ease-In-Out, S-Curve),
    controls motors, handles settle pauses, triggers Canon DSLR, and streams live progress.
    """

    def __init__(self, serial_mgr: Any, camera_mgr: Any):
        self.serial_mgr = serial_mgr
        self.camera_mgr = camera_mgr

        self.state: str = "IDLE"  # IDLE, RUNNING, PAUSED, COMPLETED, CANCELLED, ERROR
        self.config: TimelapseConfig | None = None
        self.current_shot: int = 0
        self.total_shots: int = 0
        self.start_time: float = 0.0
        self.elapsed_time_s: float = 0.0
        self.estimated_eta_s: float = 0.0
        self.last_error: str | None = None

        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cancel_flag = False

    async def start(self, config: TimelapseConfig) -> dict[str, Any]:
        """Start a new automated time-lapse sequence."""
        if self.state in ("RUNNING", "PAUSED"):
            return {"status": "ERROR", "message": "Time-lapse already active"}

        self.config = config
        self.state = "RUNNING"
        self.current_shot = 0
        self.total_shots = config.total_shots
        self.start_time = time.time()
        self.elapsed_time_s = 0.0
        self.estimated_eta_s = config.total_shots * config.interval_s
        self.last_error = None
        self._cancel_flag = False
        self._pause_event.set()

        logger.info(
            f"Starting time-lapse ({config.easing}): {config.total_shots} shots, interval={config.interval_s}s, "
            f"A=({config.start_pan}°, {config.start_tilt}°), B=({config.end_pan}°, {config.end_tilt}°)"
        )

        self._task = asyncio.create_task(self._run_loop(config))
        return {"status": "OK", "state": self.state}

    async def pause(self) -> dict[str, Any]:
        """Pause active time-lapse sequence."""
        if self.state != "RUNNING":
            return {"status": "ERROR", "message": "Time-lapse is not running"}

        self.state = "PAUSED"
        self._pause_event.clear()
        logger.info("Time-lapse sequence PAUSED.")
        return {"status": "OK", "state": self.state}

    async def resume(self) -> dict[str, Any]:
        """Resume paused time-lapse sequence."""
        if self.state != "PAUSED":
            return {"status": "ERROR", "message": "Time-lapse is not paused"}

        self.state = "RUNNING"
        self._pause_event.set()
        logger.info("Time-lapse sequence RESUMED.")
        return {"status": "OK", "state": self.state}

    async def cancel(self) -> dict[str, Any]:
        """Cancel active time-lapse sequence."""
        if self.state in ("IDLE", "COMPLETED", "CANCELLED"):
            return {"status": "OK", "state": self.state}

        self.state = "CANCELLED"
        self._cancel_flag = True
        self._pause_event.set()

        if self._task and not self._task.done():
            self._task.cancel()

        logger.info("Time-lapse sequence CANCELLED.")
        return {"status": "OK", "state": self.state}

    @staticmethod
    def _calculate_easing(ratio: float, profile: str) -> float:
        """Calculate motion easing curve ratio (0.0 to 1.0)."""
        r = max(0.0, min(1.0, ratio))
        if profile == "ease_in_out":
            return (1.0 - math.cos(math.pi * r)) / 2.0
        elif profile == "s_curve":
            return r * r * (3.0 - 2.0 * r)
        return r  # Default: linear

    async def _run_loop(self, config: TimelapseConfig):
        """Asynchronous execution loop for motion time-lapse."""
        try:
            total = config.total_shots
            for k in range(total):
                if self._cancel_flag:
                    break

                await self._pause_event.wait()
                if self._cancel_flag:
                    break

                step_start_time = time.time()

                # Calculate step ratio with easing profile
                raw_ratio = k / (total - 1) if total > 1 else 0.0
                eased_ratio = self._calculate_easing(raw_ratio, config.easing)

                target_pan = config.start_pan + eased_ratio * (config.end_pan - config.start_pan)
                target_tilt = config.start_tilt + eased_ratio * (config.end_tilt - config.start_tilt)

                logger.info(
                    f"Shot {k + 1}/{total} [{config.easing}]: Moving to ({target_pan:.2f}°, {target_tilt:.2f}°)..."
                )

                # Step 1: Move Motors
                await self.serial_mgr.move_absolute(target_pan, target_tilt)

                if self._cancel_flag:
                    break

                # Step 2: Settle Delay Pause
                if config.settle_time_s > 0:
                    await asyncio.sleep(config.settle_time_s)

                if self._cancel_flag:
                    break

                # Step 3: Trigger Shutter Release & USB Photo Download
                if config.capture_photo:
                    logger.info(f"Shot {k + 1}/{total}: Triggering camera shutter...")
                    capture_res = await self.camera_mgr.trigger_capture(filename=f"tl_{k + 1:04d}.jpg")
                    if capture_res.get("status") != "OK":
                        logger.warning(f"Shot {k + 1} capture warning: {capture_res.get('message')}")

                # Update Progress Telemetry
                self.current_shot = k + 1
                self.elapsed_time_s = time.time() - self.start_time
                avg_time_per_shot = self.elapsed_time_s / (k + 1)
                remaining_shots = total - (k + 1)
                self.estimated_eta_s = remaining_shots * max(config.interval_s, avg_time_per_shot)

                if self._cancel_flag:
                    break

                # Step 4: Interval Delay Sleep
                step_elapsed = time.time() - step_start_time
                remaining_sleep = config.interval_s - step_elapsed
                if remaining_sleep > 0 and k < total - 1:
                    sleep_end = time.time() + remaining_sleep
                    while time.time() < sleep_end:
                        if self._cancel_flag:
                            break
                        await self._pause_event.wait()
                        await asyncio.sleep(0.2)

            if not self._cancel_flag:
                self.state = "COMPLETED"
                logger.info(f"Time-lapse COMPLETED! Total {total} shots in {self.elapsed_time_s:.1f}s.")
        except asyncio.CancelledError:
            self.state = "CANCELLED"
            logger.info("Time-lapse loop task cancelled.")
        except Exception as e:
            self.state = "ERROR"
            self.last_error = str(e)
            logger.error(f"Time-lapse engine exception: {e}")

    def get_status(self) -> dict[str, Any]:
        """Return current status dictionary for REST API."""
        progress_pct = (self.current_shot / self.total_shots * 100.0) if self.total_shots > 0 else 0.0
        return {
            "state": self.state,
            "current_shot": self.current_shot,
            "total_shots": self.total_shots,
            "progress_pct": round(progress_pct, 1),
            "elapsed_time_s": round(self.elapsed_time_s, 1),
            "estimated_eta_s": round(self.estimated_eta_s, 1),
            "last_error": self.last_error,
            "config": self.config.model_dump() if self.config else None,
        }
