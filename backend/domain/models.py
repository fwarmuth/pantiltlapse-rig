from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TransitionMode(str, Enum):
    LINEAR = "linear"
    SMOOTH = "smooth"


class RunState(str, Enum):
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_GAPS = "COMPLETED_WITH_GAPS"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    INTERRUPTED = "INTERRUPTED"


class Pose(BaseModel):
    """
    Absolute pan and tilt angles in degrees.
    Pan is unwrapped and unbounded (e.g. 370° is distinct from 10°).
    Tilt is bounded by physical rig limits (0.0° to 80.0° by default).
    """
    pan_deg: float = Field(..., description="Unbounded pan angle in degrees")
    tilt_deg: float = Field(..., description="Tilt angle in degrees")


class Keyframe(BaseModel):
    """
    A single waypoint along a trajectory with progress in [0.0, 1.0].
    """
    id: UUID = Field(default_factory=uuid4, description="Unique keyframe ID")
    label: str | None = Field(default=None, description="Optional user-facing label")
    progress: float = Field(..., ge=0.0, le=1.0, description="Normalized progress from 0.0 to 1.0")
    pose: Pose = Field(..., description="Target pose at this keyframe")
    outgoing_mode: TransitionMode = Field(
        default=TransitionMode.SMOOTH,
        description="Interpolation curve leaving this keyframe: 'linear' or 'smooth'"
    )
    tangent_scale: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Smooth tangent multiplier (0.0 eases to a stop, 1.0 flows naturally)"
    )


class Trajectory(BaseModel):
    """
    Sequence of keyframes defining the path.
    Enforces progress starting at 0.0, ending at 1.0, and strictly increasing.
    """
    keyframes: list[Keyframe] = Field(..., min_length=2, description="Keyframes defining the path")

    @model_validator(mode="after")
    def validate_keyframes(self) -> "Trajectory":
        if not self.keyframes:
            raise ValueError("Trajectory must have at least 2 keyframes")

        # Check endpoints
        if abs(self.keyframes[0].progress - 0.0) > 1e-6:
            raise ValueError(f"First keyframe progress must be 0.0, got {self.keyframes[0].progress}")
        if abs(self.keyframes[-1].progress - 1.0) > 1e-6:
            raise ValueError(f"Last keyframe progress must be 1.0, got {self.keyframes[-1].progress}")

        # Check strictly increasing progress
        for i in range(len(self.keyframes) - 1):
            if self.keyframes[i + 1].progress <= self.keyframes[i].progress:
                raise ValueError(
                    f"Keyframe progress must be strictly increasing: keyframe {i} ({self.keyframes[i].progress}) "
                    f">= keyframe {i+1} ({self.keyframes[i+1].progress})"
                )

        return self


class Schedule(BaseModel):
    """
    Time-lapse schedule parameters.
    """
    total_shots: int = Field(..., ge=2, description="Total number of captured frames (minimum 2)")
    interval_s: float = Field(..., gt=0.0, description="Minimum start-to-start interval between shots in seconds")
    settle_time_s: float = Field(default=0.5, ge=0.0, description="Pause duration after motion before shutter release")


class AcquisitionProfile(BaseModel):
    """
    Camera acquisition settings fixed for a run.
    Allows extra camera-specific parameters without breaking validation.
    """
    model_config = ConfigDict(extra="allow")

    iso: str = Field(default="400", description="ISO setting string")
    shutter_speed: str = Field(default="1/125", description="Shutter speed string")
    aperture: str = Field(default="4.5", description="Aperture string")
    camera_format: str = Field(default="JPEG", description="Camera format")
    extra_settings: dict[str, Any] = Field(default_factory=dict, description="Custom camera options")


class PreviewProfile(BaseModel):
    """
    Camera preview settings used prior to acquisition.
    """
    model_config = ConfigDict(extra="allow")

    iso: str = Field(default="400", description="ISO setting string")
    shutter_speed: str = Field(default="1/125", description="Shutter speed string")
    aperture: str = Field(default="5.6", description="Aperture string")
    extra_settings: dict[str, Any] = Field(default_factory=dict, description="Custom preview options")


class RetryPolicy(BaseModel):
    """
    Hardware retry configuration for shot acquisition and transfer.
    """
    max_attempts: int = Field(default=3, ge=1, description="Total capture/download attempts")
    attempt_delay_s: float = Field(default=2.0, ge=0.0, description="Delay between retry attempts in seconds")


class SequencePlan(BaseModel):
    """
    Canonical, editable sequence plan container.
    """
    schema_version: int = Field(default=1, description="Plan schema version")
    id: UUID = Field(default_factory=uuid4, description="Unique plan UUID")
    revision: int = Field(default=1, ge=1, description="Material edit revision counter")
    name: str = Field(..., min_length=1, description="Human-readable plan name")
    description: str = Field(default="", description="Detailed description")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last update timestamp"
    )
    trajectory: Trajectory = Field(..., description="Planned motion trajectory")
    schedule: Schedule = Field(..., description="Planned timing schedule")
    acquisition: AcquisitionProfile = Field(
        default_factory=AcquisitionProfile,
        description="Camera settings for capture"
    )
    preview: PreviewProfile = Field(
        default_factory=PreviewProfile,
        description="Camera settings for preview"
    )
    retry_policy: RetryPolicy = Field(
        default_factory=RetryPolicy,
        description="Shot retry settings"
    )


class RigSnapshot(BaseModel):
    """
    Rig hardware snapshot and boundary limits.
    Default tilt min = 0.0° (zero reference at mechanical bottom), tilt max = 80.0°.
    """
    coordinate_reference_id: UUID = Field(default_factory=uuid4, description="Coordinate system session ID")
    tilt_min_deg: float = Field(default=0.0, description="Minimum allowable tilt angle in degrees")
    tilt_max_deg: float = Field(default=80.0, description="Maximum allowable tilt angle in degrees")

    @model_validator(mode="after")
    def check_tilt_bounds(self) -> "RigSnapshot":
        if self.tilt_max_deg < self.tilt_min_deg:
            msg = f"tilt_max_deg ({self.tilt_max_deg}) cannot be less than tilt_min_deg ({self.tilt_min_deg})"
            raise ValueError(msg)
        return self


class Artifact(BaseModel):
    """
    Saved file artifact metadata (relative path, type, creation time).
    """
    id: UUID = Field(default_factory=uuid4, description="Unique artifact ID")
    type: str = Field(..., description="Artifact type: 'original', 'preview', 'metadata'")
    relative_path: str = Field(..., description="Relative filepath within output storage")
    mime_type: str = Field(..., description="MIME content type")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )


class Attempt(BaseModel):
    """
    Single shot acquisition attempt record.
    """
    attempt_number: int = Field(..., ge=1, description="1-based attempt index")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of attempt"
    )
    success: bool = Field(..., description="Whether attempt succeeded")
    error_detail: str | None = Field(default=None, description="Error details if attempt failed")


class ShotRecord(BaseModel):
    """
    Durable record of a single time-lapse shot.
    """
    shot_index: int = Field(..., ge=0, description="0-based shot sequence index")
    progress: float = Field(..., ge=0.0, le=1.0, description="Normalized progress")
    intended_pose: Pose = Field(..., description="Target calculated pose")
    actual_pose: Pose | None = Field(default=None, description="Reported hardware pose")
    scheduled_time: datetime = Field(..., description="UTC scheduled start time")
    actual_time: datetime | None = Field(default=None, description="UTC actual start time")
    attempts: list[Attempt] = Field(default_factory=list, description="Execution attempts")
    artifacts: list[Artifact] = Field(default_factory=list, description="Captured media files")
    status: str = Field(default="PENDING", description="Shot status: PENDING, SUCCESS, GAP, SKIPPED")


class DryRunReport(BaseModel):
    """
    Validation and trajectory summary report.
    """
    valid: bool = Field(..., description="True if path passes all safety checks")
    planned_duration_s: float = Field(..., ge=0.0, description="Calculated total sequence duration")
    max_pan_delta_deg: float = Field(..., ge=0.0, description="Maximum pan step between consecutive shots")
    max_tilt_delta_deg: float = Field(..., ge=0.0, description="Maximum tilt step between consecutive shots")
    errors: list[str] = Field(default_factory=list, description="Validation failure messages")
    warnings: list[str] = Field(default_factory=list, description="Planning warnings")


class SequenceRun(BaseModel):
    """
    Immutable execution run record.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique run UUID")
    plan_id: UUID = Field(..., description="Referenced plan UUID")
    plan_revision: int = Field(..., ge=1, description="Plan revision executed")
    state: RunState = Field(default=RunState.PREPARING, description="Current run lifecycle state")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )
    started_at: datetime | None = Field(default=None, description="UTC execution start time")
    completed_at: datetime | None = Field(default=None, description="UTC execution completion time")
    total_shots: int = Field(..., ge=2, description="Target total shots")
    completed_shots: int = Field(default=0, ge=0, description="Successfully captured shots")
    gap_shots: int = Field(default=0, ge=0, description="Exhausted gap shots")


class CaptureResult(BaseModel):
    """
    Standardized typed result of a camera shutter release capture.
    """
    camera_filename: str = Field(..., description="Filename reported by camera or target name")
    saved_original_path: str = Field(..., description="Absolute path to saved original image/RAW file")
    extension: str = Field(..., description="File extension including leading dot, e.g. .jpg, .CR2, .svg")
    mime_type: str = Field(..., description="MIME content type, e.g. image/jpeg, image/x-canon-cr2, image/svg+xml")
    capture_timestamp: float = Field(..., description="POSIX timestamp of capture completion")
    camera_preview_path: str | None = Field(
        default=None, description="Optional path to extracted or companion JPEG preview"
    )
