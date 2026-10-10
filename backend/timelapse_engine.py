import asyncio
from datetime import datetime, timezone
import logging
import math
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from media_helper import generate_resized_preview_async, generate_resized_preview_sync

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
    raw: bool | None = Field(default=None, description="Enable or disable RAW+JPEG capture")
    image_format: str | None = Field(default=None, description="Direct image format override")
    easing: str = Field(default="ease_in_out", description="Motion profile: 'linear', 'ease_in_out', or 's_curve'")
    plan_id: str | None = Field(default=None, description="Optional associated plan UUID")
    plan_name: str | None = Field(default=None, description="Optional associated human-readable plan name")
    poses: list[dict[str, float]] | None = Field(default=None, description="Explicit sampled trajectory poses")
    camera_settings: list[dict[str, str]] | None = Field(
        default=None, description="Explicit per-shot camera exposure settings"
    )
    target_dir: str | None = Field(default=None, description="Explicit target directory for sequence captures")

    @model_validator(mode="after")
    def validate_explicit_pose_count(self) -> "TimelapseConfig":
        """Reject an explicit trajectory that cannot cover every configured shot."""
        if self.poses is not None and len(self.poses) != self.total_shots:
            raise ValueError("poses length must match total_shots when poses are provided")
        if self.camera_settings is not None and len(self.camera_settings) != self.total_shots:
            raise ValueError("camera_settings length must match total_shots when provided")
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
        self.captured_shots: list[dict[str, Any]] = []
        self._latest_capture: dict[str, Any] | None = None
        self._preview_semaphore: asyncio.Semaphore = asyncio.Semaphore(1)

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
            self.run_id, self.capture_dir = self._create_capture_storage(config)
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
        self.captured_shots = []
        self._latest_capture = None
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

    def _create_capture_storage(self, config: TimelapseConfig | None = None) -> tuple[str, str | None]:
        """Allocate a unique, human-readable run identity and an isolated capture directory."""
        if config and config.target_dir:
            target_path = Path(config.target_dir).resolve()
            if target_path.exists():
                existing = [f for f in target_path.iterdir() if f.is_file() and not f.name.startswith(".")]
                if existing:
                    target_path = target_path / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            target_path.mkdir(parents=True, exist_ok=True)
            return target_path.name, str(target_path)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_title = config.plan_name if config else None

        if plan_title:
            clean_name = re.sub(r"[^\w\-_]+", "_", plan_title.strip())
            clean_name = re.sub(r"_+", "_", clean_name).strip("_")
            dir_name = f"timelapse_{clean_name}_{timestamp}"
        else:
            dir_name = f"timelapse_{timestamp}"

        camera_capture_dir = getattr(self.camera_mgr, "capture_dir", None)
        if not camera_capture_dir:
            # Test doubles and older camera adapters may not expose storage plumbing;
            # run-qualified filenames still prevent collisions for those adapters.
            return dir_name, None

        base_dir = Path(camera_capture_dir).resolve()
        run_dir = base_dir / dir_name
        if run_dir.exists():
            dir_name = f"{dir_name}_{uuid4().hex[:6]}"
            run_dir = base_dir / dir_name

        run_dir.mkdir(parents=True, exist_ok=False)
        return dir_name, str(run_dir)

    def _capture_filename(self, shot_index: int) -> str:
        """Return a sequential, ffmpeg-friendly filename (e.g. 0001.jpg)."""
        if self.run_id is None:
            raise RuntimeError("Cannot capture without an active run identity")
        if self.capture_dir is None:
            # Fallback for adapters without isolated directories to avoid collisions
            return f"tl_{self.run_id}_{shot_index + 1:04d}.jpg"
        return f"{shot_index + 1:04d}.jpg"

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

    async def adjust_active_run(
        self,
        poses: list[dict[str, float]] | None = None,
        camera_settings: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Hot-update future trajectory poses and/or camera settings during an active run."""
        if self.state not in ("RUNNING", "PAUSED") or not self.config:
            return {"status": "ERROR", "message": "No active time-lapse sequence to adjust"}

        if poses is not None:
            if len(poses) != self.total_shots:
                return {
                    "status": "ERROR",
                    "message": f"poses length {len(poses)} must match total_shots {self.total_shots}",
                }
            # Enforce immutability of executed poses (0 .. current_shot-1)
            updated_poses = list(poses)
            if self.config.poses and self.current_shot > 0:
                for idx in range(min(self.current_shot, len(self.config.poses))):
                    updated_poses[idx] = self.config.poses[idx]

            # Validate remaining targets against rig limits
            for p in updated_poses[self.current_shot:]:
                self.rig_mgr.validate_move(pan=p.get("pan", 0.0), tilt=p.get("tilt", 0.0))
            self.config.poses = updated_poses

        if camera_settings is not None:
            if len(camera_settings) != self.total_shots:
                return {
                    "status": "ERROR",
                    "message": f"camera_settings length {len(camera_settings)} must match total_shots {self.total_shots}",
                }
            # Enforce immutability of executed camera settings
            updated_settings = list(camera_settings)
            if self.config.camera_settings and self.current_shot > 0:
                for idx in range(min(self.current_shot, len(self.config.camera_settings))):
                    updated_settings[idx] = self.config.camera_settings[idx]
            self.config.camera_settings = updated_settings

        logger.info(
            f"Active time-lapse adjusted at shot {self.current_shot + 1}/{self.total_shots} "
            f"(poses={'updated' if poses else 'unchanged'}, camera={'updated' if camera_settings else 'unchanged'})"
        )
        return {"status": "OK", "current_shot": self.current_shot}



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
            # Apply initial time-lapse image format / RAW mode if requested
            if config.image_format and hasattr(self.camera_mgr, "set_config"):
                try:
                    await self.camera_mgr.set_config("image_format", config.image_format)
                except Exception as e:
                    logger.warning(f"Failed to set initial time-lapse image_format: {e}")
            elif config.raw is not None and hasattr(self.camera_mgr, "set_config"):
                try:
                    await self.camera_mgr.set_config("raw", "true" if config.raw else "false")
                except Exception as e:
                    logger.warning(f"Failed to set initial time-lapse raw={config.raw}: {e}")

            total = config.total_shots
            for k in range(total):
                if self._cancel_flag:
                    break

                await self._pause_event.wait()
                if self._cancel_flag:
                    break

                step_start_time = time.time()
                cur_config = self.config or config

                # Calculate target pose from explicit trajectory poses or fallback to easing profile
                if cur_config.poses and len(cur_config.poses) == total:
                    target_pan = float(cur_config.poses[k].get("pan", 0.0))
                    target_tilt = float(cur_config.poses[k].get("tilt", 0.0))
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

                # Step 1: Move Motors (with automatic retries for transient communication glitches)
                move_res = None
                for move_attempt in range(1, 4):
                    move_res = await self.serial_mgr.move_absolute(target_pan, target_tilt)
                    if move_res.get("status") == "OK":
                        break

                    if move_attempt < 3:
                        logger.warning(
                            f"Shot {k + 1} motor move attempt {move_attempt}/3 failed ({move_res.get('message')}). "
                            f"Retrying move in {self.motor_retry_delay_s}s..."
                        )
                        if self.motor_retry_delay_s > 0:
                            await asyncio.sleep(self.motor_retry_delay_s)
                    if self._cancel_flag:
                        break

                # If all direct move retries failed, attempt serial reconnect recovery
                if move_res.get("status") != "OK" and hasattr(self.serial_mgr, "reconnect"):
                    logger.warning(
                        f"Shot {k + 1} motor move failed after 3 attempts ({move_res.get('message')}). "
                        "Invalidating the coordinate reference before serial reconnection."
                    )
                    self.rig_mgr.invalidate_reference("Motor controller reconnect attempted during time-lapse")
                    reconnected = False
                    for attempt in range(1, 6):
                        if self.motor_retry_delay_s > 0:
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

                # Step 2: Settle Delay Pause & Camera Parameter Application
                if cur_config.camera_settings and k < len(cur_config.camera_settings):
                    shot_cam = cur_config.camera_settings[k]
                    for param_key in ("iso", "shutter_speed", "aperture", "white_balance", "image_format", "raw"):
                        val = shot_cam.get(param_key)
                        if val and hasattr(self.camera_mgr, "set_config"):
                            try:
                                await self.camera_mgr.set_config(param_key, str(val))
                            except Exception as cam_err:
                                logger.warning(f"Shot {k + 1}: Failed to apply camera {param_key}={val}: {cam_err}")

                if config.settle_time_s > 0:
                    await asyncio.sleep(config.settle_time_s)

                if self._cancel_flag:
                    break

                # Step 3: Trigger Shutter Release & USB Photo Download
                if config.capture_photo:
                    logger.info(f"Shot {k + 1}/{total}: Triggering camera shutter...")
                    filename = self._capture_filename(k)
                    capture_res = await self._trigger_capture(filename)

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
                                capture_res = await self._trigger_capture(filename)
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

                    shot_data = {
                        "shot_index": k + 1,
                        "filename": filename,
                        "pan": target_pan,
                        "tilt": target_tilt,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    if capture_res.get("has_raw"):
                        shot_data["has_raw"] = True
                        shot_data["raw_filename"] = capture_res.get("raw_filename")
                    self.captured_shots.append(shot_data)

                    # Update latest capture telemetry for live viewport monitoring
                    latest_cap: dict[str, Any] = {
                        "shot_index": k + 1,
                        "filename": filename,
                        "url": f"/api/timelapse/captures/{filename}?quality=low",
                        "timestamp": shot_data["timestamp"],
                    }
                    if capture_res.get("has_raw"):
                        latest_cap["has_raw"] = True
                        latest_cap["raw_filename"] = capture_res.get("raw_filename")
                    self._latest_capture = latest_cap

                    # Asynchronously pre-generate low-res (1024px) preview in background
                    asyncio.create_task(self._eager_generate_preview(filename, capture_res))

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
            "start_time": self.start_time if self.start_time > 0 else None,
            "last_error": self.last_error,
            "run_id": self.run_id,
            "capture_dir": self.capture_dir,
            "latest_capture": self._latest_capture,
            "config": self.config.model_dump(mode="json") if self.config else None,
        }

    def get_captures(self, target_dir: str | Path | None = None) -> list[dict[str, Any]]:
        """Return ordered list of captured photos for the specified or current/latest time-lapse run."""
        results = []
        active_dir = target_dir or self.capture_dir
        capture_path = Path(active_dir).resolve() if active_dir else None

        if not target_dir or target_dir == self.capture_dir:
            for shot in self.captured_shots:
                fn = shot["filename"]
                exists = (capture_path / fn).exists() if capture_path else False
                shot_dict = {
                    **shot,
                    "url": f"/api/timelapse/captures/{fn}",
                    "download_url": f"/api/timelapse/captures/{fn}/download",
                    "exists": exists,
                }
                raw_fn = shot.get("raw_filename")
                if raw_fn:
                    raw_exists = (capture_path / raw_fn).exists() if capture_path else False
                    shot_dict["raw_url"] = f"/api/timelapse/captures/{raw_fn}"
                    shot_dict["raw_download_url"] = f"/api/timelapse/captures/{raw_fn}/download"
                    shot_dict["raw_exists"] = raw_exists
                results.append(shot_dict)

        if not results and capture_path and capture_path.exists():
            files = sorted([f for f in capture_path.iterdir() if f.is_file() and not f.name.startswith(".")])
            raw_exts = (".cr2", ".cr3", ".nef", ".arw", ".dng")
            raw_map = {f.stem.lower(): f for f in files if f.suffix.lower() in raw_exts}
            jpg_map = {f.stem.lower(): f for f in files if f.suffix.lower() in (".jpg", ".jpeg", ".svg")}

            for stem_key, f in sorted(jpg_map.items()):
                shot_idx = 0
                try:
                    parts = f.stem.split("_")
                    shot_idx = int(parts[-1])
                except (ValueError, IndexError):
                    pass
                raw_f = raw_map.get(stem_key)
                item = {
                    "shot_index": shot_idx,
                    "filename": f.name,
                    "url": f"/api/timelapse/captures/{f.name}",
                    "download_url": f"/api/timelapse/captures/{f.name}/download",
                    "size_bytes": f.stat().st_size,
                    "exists": True,
                }
                if raw_f:
                    item["raw_filename"] = raw_f.name
                    item["raw_url"] = f"/api/timelapse/captures/{raw_f.name}"
                    item["raw_download_url"] = f"/api/timelapse/captures/{raw_f.name}/download"
                    item["raw_exists"] = True
                results.append(item)
        return results

    async def _eager_generate_preview(self, filename: str, capture_res: dict[str, Any] | None = None) -> None:
        """Asynchronously pre-generate low-res (1024px) preview into .previews/ using Pillow."""
        if not self.capture_dir:
            return

        async with self._preview_semaphore:
            try:
                capture_path = Path(self.capture_dir)
                orig_file = capture_path / filename

                # Determine displayable source image (companion preview if RAW, otherwise original file)
                source_img = orig_file
                raw_exts = (".cr2", ".cr3", ".nef", ".arw", ".dng")
                if orig_file.suffix.lower() in raw_exts:
                    for ext in (".jpg", ".jpeg", ".JPG", ".JPEG"):
                        companion = orig_file.with_suffix(ext)
                        if companion.exists():
                            source_img = companion
                            break
                        companion_prev = orig_file.parent / f"{orig_file.stem}_preview{ext}"
                        if companion_prev.exists():
                            source_img = companion_prev
                            break

                if not source_img.exists():
                    return

                cache_dir = capture_path / ".previews"
                target_preview = cache_dir / f"{source_img.stem}_low.jpg"

                # Offload Pillow draft downscale with single-concurrency serialization
                await generate_resized_preview_async(source_img, target_preview, 1024, 70)
                logger.debug(f"Eagerly generated preview: {target_preview.name}")
            except Exception as exc:
                logger.debug(f"Could not eagerly generate preview for '{filename}': {exc}")

