from pydantic import BaseModel, Field

from domain.models import AxisKeyframe, Pose, RigSnapshot, Schedule, Trajectory, TransitionMode


class TrajectorySample(BaseModel):
    """
    A single sampled point along a motion trajectory.
    """
    shot_index: int = Field(..., ge=0, description="0-based shot index")
    progress: float = Field(..., ge=0.0, le=1.0, description="Normalized progress t in [0.0, 1.0]")
    pose: Pose = Field(..., description="Sampled pan/tilt pose")


class TrajectorySamplingResult(BaseModel):
    """
    Complete trajectory sampling results and diagnostic metrics.
    """
    samples: list[TrajectorySample] = Field(..., description="Generated trajectory poses")
    total_shots: int = Field(..., ge=2, description="Total shot count")
    planned_duration_s: float = Field(..., ge=0.0, description="Total duration in seconds")
    max_pan_delta_deg: float = Field(..., ge=0.0, description="Maximum pan step between consecutive shots")
    max_tilt_delta_deg: float = Field(..., ge=0.0, description="Maximum tilt step between consecutive shots")
    valid: bool = Field(..., description="True if all targets pass rig limits and safety checks")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Planning warnings")


def _calculate_track_tangents(keyframes: list[AxisKeyframe]) -> list[float]:
    """
    Calculate Hermite tangents for an axis keyframe track.
    Uses central differences for interior keyframes and forward/backward differences for endpoints,
    scaled by keyframe.tangent_scale.
    """
    num_kfs = len(keyframes)
    tangents: list[float] = []

    for idx, kf in enumerate(keyframes):
        scale = kf.tangent_scale
        if scale == 0.0:
            tangents.append(0.0)
            continue

        if idx == 0:
            dt = keyframes[1].progress - keyframes[0].progress
            slope = (keyframes[1].value - keyframes[0].value) / dt if dt > 0 else 0.0
        elif idx == num_kfs - 1:
            dt = keyframes[-1].progress - keyframes[-2].progress
            slope = (keyframes[-1].value - keyframes[-2].value) / dt if dt > 0 else 0.0
        else:
            dt = keyframes[idx + 1].progress - keyframes[idx - 1].progress
            slope = (keyframes[idx + 1].value - keyframes[idx - 1].value) / dt if dt > 0 else 0.0

        tangents.append(slope * scale)

    return tangents


def _interpolate_track_value(keyframes: list[AxisKeyframe], tangents: list[float], t: float) -> float:
    """
    Interpolate the value of a single axis track at progress t.
    """
    num_kfs = len(keyframes)
    seg_idx = 0
    for i in range(num_kfs - 1):
        if keyframes[i].progress <= t:
            seg_idx = i
        if keyframes[i + 1].progress >= t:
            break
    if seg_idx >= num_kfs - 1:
        seg_idx = num_kfs - 2

    kf_a = keyframes[seg_idx]
    kf_b = keyframes[seg_idx + 1]

    h = kf_b.progress - kf_a.progress
    u = max(0.0, min(1.0, (t - kf_a.progress) / h)) if h > 0 else 0.0

    if kf_a.outgoing_mode == TransitionMode.LINEAR:
        return kf_a.value + u * (kf_b.value - kf_a.value)

    # Cubic Hermite Spline
    h00 = 2 * (u ** 3) - 3 * (u ** 2) + 1
    h10 = (u ** 3) - 2 * (u ** 2) + u
    h01 = -2 * (u ** 3) + 3 * (u ** 2)
    h11 = (u ** 3) - (u ** 2)

    d_a = tangents[seg_idx]
    d_b = tangents[seg_idx + 1]

    return (
        h00 * kf_a.value
        + h10 * h * d_a
        + h01 * kf_b.value
        + h11 * h * d_b
    )


def sample_trajectory(
    trajectory: Trajectory,
    schedule: Schedule,
    rig_limits: RigSnapshot | None = None,
) -> TrajectorySamplingResult:
    """
    Generate deterministic pose samples for independent Pan and Tilt tracks across total_shots.
    Supports linear and cubic Hermite interpolation per track segment.
    Validates targets against rig_limits (defaulting to 0.0° min, 80.0° max tilt).
    """
    if rig_limits is None:
        rig_limits = RigSnapshot(tilt_min_deg=0.0, tilt_max_deg=80.0)

    total_shots = schedule.total_shots
    samples: list[TrajectorySample] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Pre-calculate Hermite tangents for each track independently
    pan_tangents = _calculate_track_tangents(trajectory.pan_keyframes)
    tilt_tangents = _calculate_track_tangents(trajectory.tilt_keyframes)

    for shot_idx in range(total_shots):
        t = shot_idx / (total_shots - 1) if total_shots > 1 else 0.0
        t = max(0.0, min(1.0, t))

        sampled_pan = _interpolate_track_value(trajectory.pan_keyframes, pan_tangents, t)
        sampled_tilt = _interpolate_track_value(trajectory.tilt_keyframes, tilt_tangents, t)

        pose = Pose(pan_deg=round(sampled_pan, 4), tilt_deg=round(sampled_tilt, 4))

        # Check rig tilt limits
        if sampled_tilt < rig_limits.tilt_min_deg or sampled_tilt > rig_limits.tilt_max_deg:
            msg = (
                f"Shot {shot_idx} (progress={t:.3f}) tilt {sampled_tilt:.2f}° "
                f"violates rig limits [{rig_limits.tilt_min_deg:.1f}°, {rig_limits.tilt_max_deg:.1f}°]"
            )
            if msg not in errors:
                errors.append(msg)

        samples.append(
            TrajectorySample(
                shot_index=shot_idx,
                progress=round(t, 6),
                pose=pose,
            )
        )

    # Compute step diagnostics
    max_pan_delta = 0.0
    max_tilt_delta = 0.0
    for i in range(len(samples) - 1):
        pan_d = abs(samples[i + 1].pose.pan_deg - samples[i].pose.pan_deg)
        tilt_d = abs(samples[i + 1].pose.tilt_deg - samples[i].pose.tilt_deg)
        if pan_d > max_pan_delta:
            max_pan_delta = pan_d
        if tilt_d > max_tilt_delta:
            max_tilt_delta = tilt_d

    planned_duration = (total_shots - 1) * schedule.interval_s
    valid = len(errors) == 0

    return TrajectorySamplingResult(
        samples=samples,
        total_shots=total_shots,
        planned_duration_s=round(planned_duration, 2),
        max_pan_delta_deg=round(max_pan_delta, 4),
        max_tilt_delta_deg=round(max_tilt_delta, 4),
        valid=valid,
        errors=errors,
        warnings=warnings,
    )
