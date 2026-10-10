"""
Real-time clock synchronization manager for Raspberry Pi and backend.
Handles synchronizing rig time from browser/client timestamps upon physical zeroing,
attempting OS clock updates (via clock_settime or sudo date), and maintaining
a continuous internal time offset fallback.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("CameraCommander.TimeManager")


class SystemTimeManager:
    def __init__(self) -> None:
        self.synced: bool = False
        self.time_offset: float = 0.0  # client_time - system_time
        self.last_sync_timestamp: float | None = None
        self.last_sync_iso: str | None = None
        self.client_timezone: str | None = None
        self.os_clock_updated: bool = False
        self.os_error: str | None = None

    def sync(self, client_time: float | int | None, timezone_name: str | None = None) -> dict[str, Any]:
        """
        Synchronize rig time with client timestamp.
        client_time can be in seconds (e.g. 1728418000.123) or milliseconds (e.g. 1728418000123).
        """
        if client_time is None:
            return self.get_status()

        # Handle millisecond timestamps if client sends Date.now() directly
        ts = float(client_time)
        if ts > 1e11:  # Year 1973 in ms is ~1e11; year 2026 in sec is ~1.78e9
            ts /= 1000.0

        current_sys = time.time()
        self.time_offset = ts - current_sys
        self.last_sync_timestamp = ts
        self.client_timezone = timezone_name
        self.synced = True

        # Attempt to set OS clock if supported
        self.os_clock_updated = False
        self.os_error = None

        # 1. Try Python clock_settime (Linux)
        if hasattr(time, "clock_settime") and hasattr(time, "CLOCK_REALTIME"):
            try:
                time.clock_settime(time.CLOCK_REALTIME, ts)
                self.os_clock_updated = True
                self.time_offset = 0.0
                logger.info("Successfully synchronized OS real-time clock via clock_settime to %s", ts)
            except PermissionError as pe:
                self.os_error = f"clock_settime PermissionError: {pe}"
                logger.warning("Permission denied setting OS clock via clock_settime: %s", pe)
            except Exception as e:
                self.os_error = f"clock_settime failed: {e}"
                logger.warning("Failed setting OS clock via clock_settime: %s", e)

        # 2. If not updated, try non-interactive sudo date as fallback
        if not self.os_clock_updated and shutil.which("sudo") and shutil.which("date"):
            try:
                res = subprocess.run(
                    ["sudo", "-n", "date", "-s", f"@{ts}"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0:
                    self.os_clock_updated = True
                    self.time_offset = 0.0
                    self.os_error = None
                    logger.info("Successfully synchronized OS real-time clock via sudo date")
                else:
                    err_msg = res.stderr.strip() or f"exit code {res.returncode}"
                    self.os_error = f"sudo date failed: {err_msg}"
            except Exception as e:
                self.os_error = f"sudo date execution error: {e}"

        now_dt = self.get_current_datetime()
        self.last_sync_iso = now_dt.isoformat()

        logger.info(
            "Rig time synced: epoch=%.3f, offset=%.3fs, os_updated=%s, tz=%s",
            self.get_current_time(),
            self.time_offset,
            self.os_clock_updated,
            self.client_timezone,
        )
        return self.get_status()

    def get_current_time(self) -> float:
        """Return current epoch timestamp in seconds, adjusted by sync offset if OS clock was not modified."""
        return time.time() + self.time_offset

    def get_current_datetime(self, tz: timezone | None = None) -> datetime:
        """Return current datetime based on rig time."""
        target_tz = tz or timezone.utc
        return datetime.fromtimestamp(self.get_current_time(), tz=target_tz)

    def get_status(self) -> dict[str, Any]:
        curr_time = self.get_current_time()
        curr_dt = datetime.fromtimestamp(curr_time, tz=timezone.utc)
        return {
            "synced": self.synced,
            "system_time": time.time(),
            "rig_time": curr_time,
            "rig_iso": curr_dt.isoformat(),
            "time_offset": self.time_offset,
            "os_clock_updated": self.os_clock_updated,
            "os_error": self.os_error,
            "last_sync": self.last_sync_iso,
            "timezone": self.client_timezone,
        }
