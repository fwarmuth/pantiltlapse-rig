import asyncio
import logging
import math
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

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
    plan_id: str | None = Field(default=None, description="Optional associated plan UUID")
    poses: list[dict[str, float]] | None = Field(default=None, description="Explicit sampled trajectory poses")

    @model_validator(mode="after")
    def validate_explicit_pose_count(self) -> "TimelapseConfig":
        """Reject an explicit trajectory that cannot cover every configured shot."""
        if self.poses is not None and len(self.poses) != self.total_shots:
            raise ValueError("poses length must match total_shots when poses are provided")
        return self


class TimelapseEngine:
    """
    Event-driven background state machine for 2-axis automated motion time-lapses.
    Calculates step interpolation with configurable motion easing or explicit multi-keyframe trajectory poses,
    controls motors, handles settle pauses, triggers Canon DSLR, and streams live progress.
    """

    def __init__(self, serial_mgr: Any, camera_mgr: Any, rig_mgr: Any, coordinator: Any):
        self.serial_mgr = serial_mgr
        self.camera_mgr = camera_mgr
        self.rig_mgr = rig_mgr
        self.coordinator = coordinator

        self.state: str = "IDLE"  # IDLE, RUNNING, PAUSED, COMPLETED, CANCELLED, ERROR
        self.config: TimelapseConfig | None = None
        self.current_shot: int = 0
        self.total_shots: int = 0
        self.start_time: float = 0.0
        self.elapsed_time_s: float = 0.0
        self.estimated_eta_s: float = 0.0
        self.last_error: str | None = None
        self.camera_retry_delay_s: float = 2.5
        self.motor_retry_delay_s: float = 1.2
        self.run_id: str | None = None
        self.capture_dir: str | None = None

        self._task: asyncio.Task | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._cancel_flag = False
        self._cancel_complete = asyncio.Event()
        self._cancel_complete.set()
        self._run_started = asyncio.Event()

    async def start(self, config: TimelapseConfig) -> dict[str, Any]:
        """Start a new automated time-lapse sequence."""
        if self.state in ("RUNNING", "PAUSED"):
            return {"status": "ERROR", "message": "Time-lapse already active"}

        # Validate movement boundaries
        if config.poses:
            for p in config.poses:
                self.rig_mgr.validate_move(pan=p.get("pan", 0.0), tilt=p.get("tilt", 0.0))
        else:
            self.rig_mgr.validate_move(pan=config.start_pan, tilt=config.start_tilt)
            self.rig_mgr.validate_move(pan=config.end_pan, tilt=config.end_tilt)

        acquired = await self.coordinator.acquire("RECORDING", config.plan_id)
        if not acquired:
            active = self.coordinator.active_mode
            return {"status": "ERROR", "message": f"Operation lock busy: '{active}' active"}

        try:
            self.run_id, self.capture_dir = self._create_capture_storage()
        except Exception as exc:
            await self.coordinator.release("RECORDING")
            logger.error("Unable to create isolated capture directory: %s", exc)
            return {"status": "ERROR", "message": f"Unable to prepare capture storage: {exc}"}

        self.config = config
        self.state = "RUNNING"
        self.current_shot = 0
        self.total_shots = config.total_shots
        self.start_time = time.time()
        self.elapsed_time_s = 0.0
        self.estimated_eta_s = config.total_shots * config.interval_s
        self.last_error = None
        self._cancel_flag = False
        self._cancel_complete = asyncio.Event()
        self._cancel_complete.set()
        self._run_started = asyncio.Event()
        self._pause_event.set()

        logger.info(
            f"Starting time-lapse ({config.easing}): {config.total_shots} shots, interval={config.interval_s}s, "
            f"A=({config.start_pan}°, {config.start_tilt}°), B=({config.end_pan}°, {config.end_tilt}°)"
        )

        self._task = asyncio.create_task(self._run_loop(config, self._cancel_complete, self._run_started))
        return {"status": "OK", "state": self.state, "run_id": self.run_id}

    def _create_capture_storage(self) -> tuple[str, str | None]:
        """Allocate a unique run identity and, when supported, an isolated capture directory."""
        run_id = uuid4().hex
        camera_capture_dir = getattr(self.camera_mgr, "capture_dir", None)
        if not camera_capture_dir:
            # Test doubles and older camera adapters may not expose storage plumbing;
            # run-qualified filenames still prevent collisions for those adapters.
            return run_id, None

        base_dir = Path(camera_capture_dir).resolve()
        run_dir = base_dir / f"timelapse_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_id, str(run_dir)

    def _capture_filename(self, shot_index: int) -> str:
        """Return a stable, run-qualified filename reused by capture retries."""
        if self.run_id is None:
            raise RuntimeError("Cannot capture without an active run identity")
        return f"tl_{self.run_id}_{shot_index + 1:04d}.jpg"

    async def _trigger_capture(self, filename: str) -> dict[str, Any]:
        """Capture into this run's isolated directory and drain cancellation safely."""
        if self.capture_dir is None:
            capture_task = asyncio.create_task(self.camera_mgr.trigger_capture(filename=filename))
        else:
            capture_task = asyncio.create_task(
                self.camera_mgr.trigger_capture(filename=filename, target_dir=self.capture_dir)
            )
        try:
            return await asyncio.shield(capture_task)
        except asyncio.CancelledError:
            # A native camera download may still hold the camera manager lock after
            # the engine is cancelled. Let it finish before releasing RECORDING.
            while not capture_task.done():
                try:
                    await asyncio.shield(capture_task)
                except asyncio.CancelledError:
                    # A repeated cancel request must not release the coordinator
                    # while the native capture/download is still in flight.
                    continue
                except Exception as exc:
                    logger.warning("Camera capture failed while cancellation was draining: %s", exc)
                    break
            raise

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

        task = self._task
        cancel_complete = self._cancel_complete
        run_started = self._run_started
        self.state = "CANCELLED"
        self._cancel_flag = True
        cancel_complete.clear()
        self._pause_event.set()

        stop_error: Exception | None = None
        try:
            # Stop physical motion before waiting for task cleanup. This is also
            # required when cancellation arrives while camera work is still active.
            if hasattr(self.serial_mgr, "stop"):
                await self.serial_mgr.stop()
        except Exception as exc:
            stop_error = exc
            self.last_error = f"Motor stop failed during cancellation: {exc}"
            logger.error(self.last_error)
        finally:
            cancel_complete.set()
            if task and not task.done():
                task.cancel()

        if task and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        if not run_started.is_set():
            await self.coordinator.release("RECORDING")

        logger.info("Time-lapse sequence CANCELLED.")
        if stop_error:
            return {"status": "ERROR", "state": self.state, "message": self.last_error}
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

    async def _run_loop(
        self,
        config: TimelapseConfig,
        cancel_complete: asyncio.Event,
        run_started: asyncio.Event,
    ):
        """Asynchronous execution loop for motion time-lapse."""
        run_started.set()
        try:
            total = config.total_shots
            for k in range(total):
                if self._cancel_flag:
                    break

                await self._pause_event.wait()
                if self._cancel_flag:
                    break

                step_start_time = time.time()

                # Calculate target pose from explicit trajectory poses or fallback to easing profile
                if config.poses and len(config.poses) == total:
                    target_pan = float(config.poses[k].get("pan", 0.0))
                    target_tilt = float(config.poses[k].get("tilt", 0.0))
                    profile_label = "trajectory"
                else:
                    raw_ratio = k / (total - 1) if total > 1 else 0.0
                    eased_ratio = self._calculate_easing(raw_ratio, config.easing)
                    target_pan = config.start_pan + eased_ratio * (config.end_pan - config.start_pan)
                    target_tilt = config.start_tilt + eased_ratio * (config.end_tilt - config.start_tilt)
                    profile_label = config.easing

                logger.info(
                    f"Shot {k + 1}/{total} [{profile_label}]: Moving to ({target_pan:.2f}°, {target_tilt:.2f}°)..."
                )

                # Step 1: Move Motors (with automatic recovery for transient USB disconnects)
                move_res = await self.serial_mgr.move_absolute(target_pan, target_tilt)
                if move_res.get("status") != "OK" and hasattr(self.serial_mgr, "reconnect"):
                    logger.warning(
                        f"Shot {k + 1} motor move failed ({move_res.get('message')}). "
                        "Invalidating the coordinate reference before serial reconnection."
                    )
                    self.rig_mgr.invalidate_reference("Motor controller reconnect attempted during time-lapse")
                    reconnected = False
                    for attempt in range(1, 6):
                        await asyncio.sleep(self.motor_retry_delay_s)
                        logger.info(f"Serial reconnection attempt {attempt}/5...")
                        if await self.serial_mgr.reconnect():
                            reconnected = True
                            break

                    if reconnected:
                        move_res = {
                            "status": "ERROR",
                            "message": (
                                "Motor controller reconnected, but its coordinate origin may have reset. "
                                "Confirm physical zero before starting a new sequence."
                            ),
                        }

                if move_res.get("status") != "OK":
                    message = move_res.get("message", f"Motor returned non-OK status: {move_res}")
                    raise RuntimeError(f"Shot {k + 1} move failed: {message}")

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
                    capture_res = await self._trigger_capture(self._capture_filename(k))

                    if capture_res.get("status") != "OK":
                        err_msg = capture_res.get("message", "Camera disconnected or capture failed")
                        logger.warning(
                            f"Shot {k + 1}/{total} capture failed ({err_msg}). "
                            f"Holding motor position and waiting for camera to reconnect..."
                        )
                        self.last_error = f"Shot {k + 1}: Waiting for camera reconnection ({err_msg})"

                        while not self._cancel_flag:
                            await self._pause_event.wait()
                            if self._cancel_flag:
                                break

                            # Attempt camera recovery
                            if not self.camera_mgr.is_connected:
                                logger.info(f"Shot {k + 1}: Attempting camera reconnect...")
                                if hasattr(self.camera_mgr, "reconnect"):
                                    await self.camera_mgr.reconnect()
                                elif hasattr(self.camera_mgr, "restart"):
                                    await self.camera_mgr.restart()
                                elif hasattr(self.camera_mgr, "initialize"):
                                    await self.camera_mgr.initialize()

                            if self.camera_mgr.is_connected:
                                logger.info(f"Shot {k + 1}: Camera reconnected! Retrying photo capture...")
                                capture_res = await self._trigger_capture(self._capture_filename(k))
                                if capture_res.get("status") == "OK":
                                    logger.info(
                                        f"Shot {k + 1}/{total} captured successfully after camera reconnection! "
                                        "Resuming sequence."
                                    )
                                    self.last_error = None
                                    break
                                else:
                                    logger.warning(
                                        f"Shot {k + 1} capture retry failed ({capture_res.get('message')}). "
                                        "Retrying in 3s..."
                                    )

                            await asyncio.sleep(self.camera_retry_delay_s)

                        if self._cancel_flag:
                            break

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
        finally:
            if self._cancel_flag:
                while not cancel_complete.is_set():
                    try:
                        await asyncio.shield(cancel_complete.wait())
                    except asyncio.CancelledError:
                        continue
            release_task = asyncio.create_task(self.coordinator.release("RECORDING"))
            while not release_task.done():
                try:
                    await asyncio.shield(release_task)
                except asyncio.CancelledError:
                    continue
            release_task.result()

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
            "run_id": self.run_id,
            "capture_dir": self.capture_dir,
            "config": self.config.model_dump(mode="json") if self.config else None,
        }
