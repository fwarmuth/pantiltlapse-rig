import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from domain.models import RigSnapshot

logger = logging.getLogger("CameraCommander.Rig")


class CoordinateReferenceState(BaseModel):
    """
    Runtime in-memory coordinate reference system state.
    Invalidated on backend startup or whenever motor drivers are toggled.
    Requires explicit operator confirmation before planned absolute motion can execute.
    """
    reference_id: UUID = Field(default_factory=uuid4, description="Unique coordinate system reference ID")
    confirmed: bool = Field(default=False, description="True if operator has confirmed physical zero reference")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this reference was established"
    )
    confirmed_at: datetime | None = Field(default=None, description="UTC timestamp when reference was confirmed")
    invalidation_reason: str | None = Field(default="Backend startup", description="Reason for reference generation")


class RigManager:
    """
    Manages physical rig safety bounds and runtime coordinate reference confirmation.
    Enforces minimum and maximum tilt boundaries and rejects absolute movement when unconfirmed.
    Persists tilt_min_deg and tilt_max_deg atomically in output/rig.json.
    """

    def __init__(
        self,
        tilt_min_deg: float = 0.0,
        tilt_max_deg: float = 80.0,
        storage_dir: str | Path = "output",
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.rig_file = self.storage_dir / "rig.json"

        loaded_min, loaded_max = self._load_limits(tilt_min_deg, tilt_max_deg)

        self.snapshot = RigSnapshot(
            coordinate_reference_id=uuid4(),
            tilt_min_deg=loaded_min,
            tilt_max_deg=loaded_max,
        )
        self.reference = CoordinateReferenceState(
            reference_id=self.snapshot.coordinate_reference_id,
            invalidation_reason="Initial startup",
        )

    def _load_limits(self, default_min: float, default_max: float) -> tuple[float, float]:
        if self.rig_file.exists():
            try:
                with open(self.rig_file, encoding="utf-8") as f:
                    data = json.load(f)
                return float(data.get("tilt_min_deg", default_min)), float(data.get("tilt_max_deg", default_max))
            except Exception as e:
                logger.warning(f"Failed to load rig limits from '{self.rig_file}': {e}")
        return default_min, default_max

    def _save_limits(self):
        temp_file = self.storage_dir / "rig.json.tmp"
        data = {
            "tilt_min_deg": self.snapshot.tilt_min_deg,
            "tilt_max_deg": self.snapshot.tilt_max_deg,
        }
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, self.rig_file)

    def invalidate_reference(self, reason: str = "Driver cycle"):
        """Invalidate physical zero reference confirmation and create a new reference UUID."""
        new_id = uuid4()
        self.snapshot.coordinate_reference_id = new_id
        self.reference = CoordinateReferenceState(
            reference_id=new_id,
            confirmed=False,
            created_at=datetime.now(timezone.utc),
            confirmed_at=None,
            invalidation_reason=reason,
        )
        logger.info(f"Coordinate reference invalidated ({reason}). New ID: {new_id}")

    def confirm_reference(self) -> CoordinateReferenceState:
        """Operator confirms physical zero reference."""
        self.reference.confirmed = True
        self.reference.confirmed_at = datetime.now(timezone.utc)
        logger.info(f"Coordinate reference {self.reference.reference_id} confirmed by operator.")
        return self.reference

    def set_limits(self, tilt_min_deg: float, tilt_max_deg: float) -> RigSnapshot:
        """Update rig tilt limits and persist atomically."""
        self.snapshot = RigSnapshot(
            coordinate_reference_id=self.reference.reference_id,
            tilt_min_deg=tilt_min_deg,
            tilt_max_deg=tilt_max_deg,
        )
        self._save_limits()
        logger.info(f"Updated rig limits: tilt [{tilt_min_deg}°, {tilt_max_deg}°] and saved to '{self.rig_file}'")
        return self.snapshot

    def validate_move(
        self,
        pan: float,
        tilt: float,
        relative: bool = False,
        current_pan: float = 0.0,
        current_tilt: float = 0.0,
    ):
        """
        Validate absolute or relative motor target.
        - Absolute moves require an operator-confirmed coordinate reference.
        - Target tilt is validated against rig min/max bounds.
        Raises HTTP 409 Conflict if unconfirmed, or HTTP 422 Unprocessable Entity if out of bounds.
        """
        if not relative and not self.reference.confirmed:
            reason = self.reference.invalidation_reason
            msg = f"Coordinate reference unconfirmed ({reason}). Confirm physical zero first."
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "ERROR", "message": msg},
            )

        target_tilt = (current_tilt + tilt) if relative else tilt

        if target_tilt < self.snapshot.tilt_min_deg or target_tilt > self.snapshot.tilt_max_deg:
            msg = (
                f"Target tilt {target_tilt:.2f}° violates rig bounds "
                f"[{self.snapshot.tilt_min_deg:.1f}°, {self.snapshot.tilt_max_deg:.1f}°]"
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"status": "ERROR", "message": msg},
            )
