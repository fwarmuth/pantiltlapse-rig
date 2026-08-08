from uuid import UUID

from pydantic import BaseModel, Field

from domain.models import Pose, RigSnapshot, Schedule, Trajectory, TransitionMode


class TrajectorySample(BaseModel):
    """
    A single sampled point along a motion trajectory.
    """
    shot_index: int = Field(..., ge=0, description="0-based shot index")
    progress: float = Field(..., ge=0.0, le=1.0, description="Normalized progress t in [0.0, 1.0]")
    pose: Pose = Field(..., description="Sampled pan/tilt pose")
    active_segment: int = Field(..., ge=0, description="Index j of keyframe segment [K_j, K_{j+1}]")
    keyframe_a_id: UUID = Field(..., description="Starting keyframe ID")
    keyframe_b_id: UUID = Field(..., description="Ending keyframe ID")


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


def _calculate_tangent(keyframes: list, idx: int, axis: str) -> float:
    """
    Calculate Hermite tangent for keyframe idx along given axis ('pan_deg' or 'tilt_deg').
    Uses central differences for interior keyframes and forward/backward differences for endpoints,
    scaled by keyframe.tangent_scale.
    """
    kf = keyframes[idx]
    scale = kf.tangent_scale
    if scale == 0.0:
        return 0.0

    num_kfs = len(keyframes)

    if idx == 0:
        p_curr = getattr(keyframes[0].pose, axis)
        p_next = getattr(keyframes[1].pose, axis)
        dt = keyframes[1].progress - keyframes[0].progress
        slope = (p_next - p_curr) / dt if dt > 0 else 0.0
    elif idx == num_kfs - 1:
        p_prev = getattr(keyframes[-2].pose, axis)
        p_curr = getattr(keyframes[-1].pose, axis)
        dt = keyframes[-1].progress - keyframes[-2].progress
        slope = (p_curr - p_prev) / dt if dt > 0 else 0.0
    else:
        p_prev = getattr(keyframes[idx - 1].pose, axis)
        p_next = getattr(keyframes[idx + 1].pose, axis)
        dt = keyframes[idx + 1].progress - keyframes[idx - 1].progress
        slope = (p_next - p_prev) / dt if dt > 0 else 0.0

    return slope * scale


def sample_trajectory(
    trajectory: Trajectory,
    schedule: Schedule,
    rig_limits: RigSnapshot | None = None,
) -> TrajectorySamplingResult:
    """
    Generate deterministic pose samples for a trajectory across total_shots.
    Supports linear and cubic Hermite interpolation per keyframe segment.
    Validates targets against rig_limits (defaulting to 0.0° min, 80.0° max tilt).
    """
    if rig_limits is None:
        rig_limits = RigSnapshot(tilt_min_deg=0.0, tilt_max_deg=80.0)

    keyframes = trajectory.keyframes
    num_keyframes = len(keyframes)
    total_shots = schedule.total_shots

    samples: list[TrajectorySample] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Pre-calculate Hermite tangents for all keyframes
    pan_tangents = [_calculate_tangent(keyframes, i, "pan_deg") for i in range(num_keyframes)]
    tilt_tangents = [_calculate_tangent(keyframes, i, "tilt_deg") for i in range(num_keyframes)]

    for shot_idx in range(total_shots):
        t = shot_idx / (total_shots - 1) if total_shots > 1 else 0.0
        # Clamp progress to [0.0, 1.0] for precision safety
        t = max(0.0, min(1.0, t))

        # Find keyframe segment [seg_idx, seg_idx + 1]
        seg_idx = 0
        for i in range(num_keyframes - 1):
            if keyframes[i].progress <= t:
                seg_idx = i
            if keyframes[i + 1].progress >= t:
                break
        # Guard against trailing segment overflow
        if seg_idx >= num_keyframes - 1:
            seg_idx = num_keyframes - 2

        kf_a = keyframes[seg_idx]
        kf_b = keyframes[seg_idx + 1]

        p_a = kf_a.progress
        p_b = kf_b.progress
        h = p_b - p_a

        if h <= 0:
            u = 0.0
        else:
            u = (t - p_a) / h
        u = max(0.0, min(1.0, u))

        mode = kf_a.outgoing_mode

        if mode == TransitionMode.LINEAR:
            sampled_pan = kf_a.pose.pan_deg + u * (kf_b.pose.pan_deg - kf_a.pose.pan_deg)
            sampled_tilt = kf_a.pose.tilt_deg + u * (kf_b.pose.tilt_deg - kf_a.pose.tilt_deg)
        else:
            # Cubic Hermite Spline
            h00 = 2 * (u ** 3) - 3 * (u ** 2) + 1
            h10 = (u ** 3) - 2 * (u ** 2) + u
            h01 = -2 * (u ** 3) + 3 * (u ** 2)
            h11 = (u ** 3) - (u ** 2)

            d_pan_a = pan_tangents[seg_idx]
            d_pan_b = pan_tangents[seg_idx + 1]
            d_tilt_a = tilt_tangents[seg_idx]
            d_tilt_b = tilt_tangents[seg_idx + 1]

            sampled_pan = (
                h00 * kf_a.pose.pan_deg
                + h10 * h * d_pan_a
                + h01 * kf_b.pose.pan_deg
                + h11 * h * d_pan_b
            )
            sampled_tilt = (
                h00 * kf_a.pose.tilt_deg
                + h10 * h * d_tilt_a
                + h01 * kf_b.pose.tilt_deg
                + h11 * h * d_tilt_b
            )

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
                active_segment=seg_idx,
                keyframe_a_id=kf_a.id,
                keyframe_b_id=kf_b.id,
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
