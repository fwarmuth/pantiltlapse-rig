import asyncio
import logging
from typing import Any, Literal

logger = logging.getLogger("CameraCommander.Coordinator")

OperationMode = Literal["IDLE", "PREVIEW", "DRY_RUN", "RECORDING"]


class OperationCoordinator:
    """
    Coordinator lock managing operation states (PREVIEW, DRY_RUN, RECORDING).
    - PREVIEW (Live View streaming) and DRY_RUN (motion rehearsal) can run
      concurrently ONLY if both target the same plan ID.
    - RECORDING (full time-lapse execution) requires exclusive execution.
    """

    def __init__(self):
        self.is_previewing = False
        self.is_dry_running = False
        self.is_recording = False
        self.active_plan_id: str | None = None
        self._lock = asyncio.Lock()

    @property
    def active_mode(self) -> str:
        if self.is_recording:
            return "RECORDING"
        if self.is_dry_running and self.is_previewing:
            return "DRY_RUN_PREVIEW"
        if self.is_dry_running:
            return "DRY_RUN"
        if self.is_previewing:
            return "PREVIEW"
        return "IDLE"

    def can_move(self) -> bool:
        """Manual jog moves are allowed unless dry-run or recording is active."""
        return not self.is_dry_running and not self.is_recording

    def can_change_drivers(self) -> bool:
        """Driver changes are allowed only when idle or previewing without active motion rehearsal/run."""
        return not self.is_dry_running and not self.is_recording

    def can_change_limits(self) -> bool:
        """Rig limits updates are allowed only when idle or previewing."""
        return not self.is_dry_running and not self.is_recording

    def can_test_shot(self) -> bool:
        """Test shots are allowed only when idle or previewing."""
        return not self.is_dry_running and not self.is_recording

    def can_dry_run(self, plan_id: str | None = None) -> bool:
        """Dry run is allowed if no recording or dry-run is active, and plan matches active preview plan if set."""
        if self.is_recording or self.is_dry_running:
            return False
        if self.is_previewing and self.active_plan_id and plan_id and self.active_plan_id != str(plan_id):
            return False
        return True

    def can_preview(self, plan_id: str | None = None) -> bool:
        """Preview is allowed if no recording is active, and plan matches active dry run plan if set."""
        if self.is_recording:
            return False
        if self.is_dry_running and self.active_plan_id and plan_id and self.active_plan_id != str(plan_id):
            return False
        return True

    def can_record(self, plan_id: str | None = None) -> bool:
        """Recording requires exclusive execution."""
        return not self.is_recording and not self.is_dry_running and not self.is_previewing

    async def acquire(self, mode: OperationMode, plan_id: str | None = None) -> bool:
        """Acquire operation lock for mode. Enforces plan matching for concurrent PREVIEW and DRY_RUN."""
        async with self._lock:
            plan_str = str(plan_id) if plan_id else None

            if mode == "RECORDING":
                if not self.can_record(plan_str):
                    logger.warning(f"Failed to acquire 'RECORDING' lock: active mode is '{self.active_mode}'")
                    return False
                self.is_recording = True
                self.active_plan_id = plan_str
                logger.info(f"Operation lock acquired for 'RECORDING' (plan={plan_str})")
                return True

            if mode == "DRY_RUN":
                if not self.can_dry_run(plan_str):
                    logger.warning(f"Failed to acquire 'DRY_RUN' lock: active mode is '{self.active_mode}'")
                    return False
                self.is_dry_running = True
                if not self.active_plan_id:
                    self.active_plan_id = plan_str
                logger.info(f"Operation lock acquired for 'DRY_RUN' (plan={plan_str})")
                return True

            if mode == "PREVIEW":
                if not self.can_preview(plan_str):
                    logger.warning(f"Failed to acquire 'PREVIEW' lock: active mode is '{self.active_mode}'")
                    return False
                self.is_previewing = True
                if not self.active_plan_id and plan_str:
                    self.active_plan_id = plan_str
                logger.info(f"Operation lock acquired for 'PREVIEW' (plan={plan_str})")
                return True

            return False

    async def release(self, mode: OperationMode):
        """Release operation lock."""
        async with self._lock:
            if mode == "RECORDING":
                self.is_recording = False
            elif mode == "DRY_RUN":
                self.is_dry_running = False
            elif mode == "PREVIEW":
                self.is_previewing = False

            if not self.is_recording and not self.is_dry_running and not self.is_previewing:
                self.active_plan_id = None
            logger.info(f"Operation lock released for '{mode}'")

    def get_status(self) -> dict[str, Any]:
        return {
            "active_mode": self.active_mode,
            "active_plan_id": self.active_plan_id,
            "is_previewing": self.is_previewing,
            "is_dry_running": self.is_dry_running,
            "is_recording": self.is_recording,
        }
