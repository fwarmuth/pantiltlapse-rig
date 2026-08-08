import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from domain.trajectory import sample_trajectory

logger = logging.getLogger("CameraCommander.DryRun")


class DryRunStatus(BaseModel):
    state: str = Field(default="IDLE", description="State: IDLE, RUNNING, COMPLETED, CANCELLED, ERROR")
    plan_id: str | None = Field(default=None, description="Active plan ID")
    current_shot: int = Field(default=0, ge=0)
    total_shots: int = Field(default=0, ge=0)
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    elapsed_time_s: float = Field(default=0.0, ge=0.0)
    last_error: str | None = Field(default=None)


class DryRunEngine:
    """
    Engine for executing motion-only plan rehearsals (dry runs).
    Moves through all planned poses without camera triggers or settle delays.
    Generates persistent, stale-checked DryRunReports.
    """

    def __init__(self, serial_mgr: Any, rig_mgr: Any, plan_store: Any, coordinator: Any):
        self.serial_mgr = serial_mgr
        self.rig_mgr = rig_mgr
        self.plan_store = plan_store
        self.coordinator = coordinator

        self.state = "IDLE"  # IDLE, RUNNING, COMPLETED, CANCELLED, ERROR
        self.active_plan_id: str | None = None
        self.current_shot = 0
        self.total_shots = 0
        self.start_time = 0.0
        self.elapsed_time_s = 0.0
        self.last_error: str | None = None

        self._task: asyncio.Task | None = None
        self._cancel_flag = False

    async def start(self, plan_id: UUID) -> dict[str, Any]:
        """Start dry-run motion rehearsal for specified plan."""
        if self.state == "RUNNING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "ERROR", "message": "Dry run already active"},
            )

        if not self.rig_mgr.reference.confirmed:
            reason = self.rig_mgr.reference.invalidation_reason
            msg = f"Coordinate reference unconfirmed ({reason}). Confirm zero first."
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "ERROR", "message": msg},
            )

        # Acquire exclusive coordinator lock
        acquired = await self.coordinator.acquire("DRY_RUN", str(plan_id))
        if not acquired:
            active = self.coordinator.active_mode
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "ERROR", "message": f"Operation lock busy: '{active}' active"},
            )

        plan = self.plan_store.get_plan(plan_id)
        if not plan:
            await self.coordinator.release("DRY_RUN")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "ERROR", "message": f"Plan '{plan_id}' not found"},
            )

        traj_result = sample_trajectory(plan.trajectory, plan.schedule, rig_limits=self.rig_mgr.snapshot)
        if not traj_result.valid:
            await self.coordinator.release("DRY_RUN")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "ERROR",
                    "message": "Trajectory contains invalid poses",
                    "errors": traj_result.errors,
                },
            )

        self.state = "RUNNING"
        self.active_plan_id = str(plan_id)
        self.current_shot = 0
        self.total_shots = len(traj_result.samples)
        self.start_time = time.time()
        self.elapsed_time_s = 0.0
        self.last_error = None
        self._cancel_flag = False

        self._task = asyncio.create_task(self._run_loop(plan, traj_result.samples))
        return {"status": "OK", "state": self.state}

    async def cancel(self) -> dict[str, Any]:
        """Cancel active dry-run motion rehearsal."""
        if self.state != "RUNNING":
            return {"status": "OK", "state": self.state}

        self.state = "CANCELLED"
        self._cancel_flag = True
        if self._task and not self._task.done():
            self._task.cancel()

        logger.info("Dry run sequence CANCELLED.")
        return {"status": "OK", "state": self.state}

    async def _run_loop(self, plan: Any, samples: list[Any]):
        """Asynchronous motion loop traversing dry-run poses."""
        try:
            total = len(samples)
            ref_id_at_start = str(self.rig_mgr.reference.reference_id)
            plan_rev_at_start = plan.revision

            for idx, sample in enumerate(samples):
                if self._cancel_flag:
                    break

                target_pan = sample.pose.pan_deg
                target_tilt = sample.pose.tilt_deg

                logger.info(f"Dry run [{idx+1}/{total}]: Moving to ({target_pan:.2f}°, {target_tilt:.2f}°)...")
                await self.serial_mgr.move_absolute(target_pan, target_tilt)

                if self._cancel_flag:
                    break

                self.current_shot = idx + 1
                self.elapsed_time_s = time.time() - self.start_time

            if not self._cancel_flag:
                self.state = "COMPLETED"
                logger.info(f"Dry run COMPLETED! Traversed {total} poses in {self.elapsed_time_s:.1f}s.")
                # Save DryRunReport
                self._save_report(plan, ref_id_at_start, plan_rev_at_start, total, samples)

        except asyncio.CancelledError:
            self.state = "CANCELLED"
        except Exception as e:
            self.state = "ERROR"
            self.last_error = str(e)
            logger.error(f"Dry run exception: {e}")
        finally:
            await self.coordinator.release("DRY_RUN")

    def _save_report(self, plan: Any, ref_id: str, plan_rev: int, completed: int, samples: list[Any]):
        """Save DryRunReport to output/plans/<plan_id>/dry_run_report.json."""
        plan_dir = self.plan_store.base_dir / str(plan.id)
        plan_dir.mkdir(parents=True, exist_ok=True)
        report_file = plan_dir / "dry_run_report.json"

        sample_dicts = [s.model_dump(mode="json") for s in samples]

        report = {
            "plan_id": str(plan.id),
            "plan_revision": plan_rev,
            "coordinate_reference_id": ref_id,
            "rig_limits": self.rig_mgr.snapshot.model_dump(mode="json"),
            "total_shots": len(samples),
            "completed_shots": completed,
            "valid": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "samples": sample_dicts,
        }

        temp_file = plan_dir / "dry_run_report.json.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, report_file)

    def get_report(self, plan_id: UUID) -> dict[str, Any] | None:
        """Fetch DryRunReport for plan and evaluate stale status."""
        report_file = self.plan_store.base_dir / str(plan_id) / "dry_run_report.json"
        if not report_file.exists():
            return None

        try:
            with open(report_file, encoding="utf-8") as f:
                report = json.load(f)

            plan = self.plan_store.get_plan(plan_id)
            current_ref_id = str(self.rig_mgr.reference.reference_id)
            is_ref_unconfirmed = not self.rig_mgr.reference.confirmed

            # Report is stale if plan revision changed or reference ID changed or reference unconfirmed
            stale = (
                plan is None
                or report.get("plan_revision") != plan.revision
                or report.get("coordinate_reference_id") != current_ref_id
                or is_ref_unconfirmed
            )

            report["stale"] = stale
            return report
        except Exception as e:
            logger.error(f"Failed to read dry-run report for '{plan_id}': {e}")
            return None

    def get_status(self) -> dict[str, Any]:
        pct = (self.current_shot / self.total_shots * 100.0) if self.total_shots > 0 else 0.0
        return {
            "state": self.state,
            "plan_id": self.active_plan_id,
            "current_shot": self.current_shot,
            "total_shots": self.total_shots,
            "progress_pct": round(pct, 1),
            "elapsed_time_s": round(self.elapsed_time_s, 1),
            "last_error": self.last_error,
        }
