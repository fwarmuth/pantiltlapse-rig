import asyncio
import logging
from typing import Literal

logger = logging.getLogger("CameraCommander.Coordinator")

OperationMode = Literal["IDLE", "PREVIEW", "DRY_RUN", "RECORDING"]


class OperationCoordinator:
    """
    Coordinator lock managing operation states (PREVIEW, DRY_RUN, RECORDING).
    - PREVIEW (Live View streaming) and DRY_RUN (motion rehearsal) can run concurrently.
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

    @active_mode.setter
    def active_mode(self, mode: str):
        """Backwards-compatibility setter for direct mode assignment in tests/fixtures."""
        if mode == "IDLE":
            self.is_previewing = False
            self.is_dry_running = False
            self.is_recording = False
        elif mode == "PREVIEW":
            self.is_previewing = True
            self.is_dry_running = False
            self.is_recording = False
        elif mode == "DRY_RUN":
            self.is_dry_running = True
            self.is_previewing = False
            self.is_recording = False
        elif mode == "RECORDING":
            self.is_recording = True

    async def acquire(self, mode: OperationMode, plan_id: str | None = None) -> bool:
        """Acquire operation lock for mode. Allows concurrent PREVIEW and DRY_RUN."""
        async with self._lock:
            if mode == "RECORDING":
                if self.is_recording or self.is_dry_running:
                    logger.warning(f"Failed to acquire 'RECORDING' lock: active mode is '{self.active_mode}'")
                    return False
                self.is_recording = True
                self.active_plan_id = plan_id
                logger.info(f"Operation lock acquired for 'RECORDING' (plan={plan_id})")
                return True

            if mode == "DRY_RUN":
                if self.is_recording or self.is_dry_running:
                    logger.warning(f"Failed to acquire 'DRY_RUN' lock: active mode is '{self.active_mode}'")
                    return False
                self.is_dry_running = True
                self.active_plan_id = plan_id
                logger.info(f"Operation lock acquired for 'DRY_RUN' (plan={plan_id})")
                return True

            if mode == "PREVIEW":
                if self.is_recording:
                    logger.warning(f"Failed to acquire 'PREVIEW' lock: active mode is '{self.active_mode}'")
                    return False
                self.is_previewing = True
                if not self.active_plan_id:
                    self.active_plan_id = plan_id
                logger.info(f"Operation lock acquired for 'PREVIEW' (plan={plan_id})")
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

    def get_status(self) -> dict[str, str | None]:
        return {
            "active_mode": self.active_mode,
            "active_plan_id": self.active_plan_id,
        }
