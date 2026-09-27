import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger("CameraCommander.StudioState")


class StudioFilterSettings(BaseModel):
    mode: str = Field(default="none", description="Live video enhancement filter mode")
    gain: float = Field(default=1.5, ge=1.0, le=5.0, description="Digital gain multiplier")
    contrast: float = Field(default=1.3, ge=0.5, le=3.0, description="Contrast multiplier")


class StudioState(BaseModel):
    """Runtime and persistent studio UI state for browser reload rehydration."""
    active_plan_id: UUID | None = Field(default=None, description="Currently selected plan ID")
    active_step: int = Field(default=1, ge=1, le=5, description="Active wizard step (1..5)")
    jog_step_deg: float = Field(default=1.0, description="Selected manual jog step size in degrees")
    filter_settings: StudioFilterSettings = Field(default_factory=StudioFilterSettings)
    active_track_tab: str = Field(default="pan", description="Active keyframe track tab ('pan' or 'tilt')")
    curve_filter: str = Field(default="all", description="Active curve plot filter ('all', 'pan', 'tilt')")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last state modification"
    )


class AppStateManager:
    """Manages persistent studio session state across browser reloads."""

    def __init__(self, storage_dir: str | Path = "output"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.storage_dir / "studio_state.json"
        self.state = self._load()

    def _load(self) -> StudioState:
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    return StudioState.model_validate_json(f.read())
            except Exception as e:
                logger.warning(f"Failed to load studio state from '{self.state_file}': {e}")
        return StudioState()

    def update(self, **kwargs) -> StudioState:
        """Update fields and persist to disk atomically."""
        current = self.state.model_dump()
        for k, v in kwargs.items():
            if v is not None and k in current:
                if k == "filter_settings" and isinstance(v, dict):
                    current[k] = StudioFilterSettings.model_validate(v).model_dump()
                elif k == "active_plan_id" and v:
                    current[k] = UUID(str(v))
                else:
                    current[k] = v
        current["updated_at"] = datetime.now(timezone.utc)
        self.state = StudioState.model_validate(current)
        self._save()
        return self.state

    def _save(self):
        temp_file = self.storage_dir / "studio_state.json.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(self.state.model_dump_json(indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, self.state_file)
