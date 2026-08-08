import pytest
from pydantic import ValidationError

from domain.models import (
    AcquisitionProfile,
    Keyframe,
    Pose,
    RigSnapshot,
    Schedule,
    SequencePlan,
    Trajectory,
    TransitionMode,
)


def make_valid_plan() -> SequencePlan:
    kf1 = Keyframe(
        progress=0.0,
        pose=Pose(pan_deg=0.0, tilt_deg=0.0),
        outgoing_mode=TransitionMode.SMOOTH,
        tangent_scale=1.0,
    )
    kf2 = Keyframe(
        progress=0.5,
        pose=Pose(pan_deg=180.0, tilt_deg=40.0),
        outgoing_mode=TransitionMode.LINEAR,
        tangent_scale=0.5,
    )
    kf3 = Keyframe(
        progress=1.0,
        pose=Pose(pan_deg=370.0, tilt_deg=80.0),
        outgoing_mode=TransitionMode.SMOOTH,
        tangent_scale=1.0,
    )
    trajectory = Trajectory(keyframes=[kf1, kf2, kf3])
    schedule = Schedule(total_shots=50, interval_s=10.0, settle_time_s=1.0)
    acq = AcquisitionProfile(iso="800", shutter_speed="1/250", aperture="4.0", extra_custom_param="lens_profile_1")

    return SequencePlan(
        name="Test Pan & Tilt Run",
        description="A 50-shot smooth pan/tilt sequence",
        trajectory=trajectory,
        schedule=schedule,
        acquisition=acq,
    )


def test_valid_plan_json_roundtrip():
    plan = make_valid_plan()
    json_str = plan.model_dump_json()

    # Deserialize back to SequencePlan
    reloaded = SequencePlan.model_validate_json(json_str)

    assert reloaded.id == plan.id
    assert reloaded.revision == plan.revision
    assert reloaded.name == plan.name
    assert len(reloaded.trajectory.keyframes) == 3
    assert reloaded.trajectory.keyframes[2].pose.pan_deg == 370.0
    # Extra settings preservation check
    assert getattr(reloaded.acquisition, "extra_custom_param", None) == "lens_profile_1"


def test_invalid_keyframe_endpoints():
    # Non-zero starting progress
    kf1 = Keyframe(progress=0.1, pose=Pose(pan_deg=0.0, tilt_deg=0.0))
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=10.0, tilt_deg=5.0))
    with pytest.raises(ValidationError) as exc:
        Trajectory(keyframes=[kf1, kf2])
    assert "First keyframe progress must be 0.0" in str(exc.value)

    # Non-1.0 ending progress
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0))
    kf2 = Keyframe(progress=0.9, pose=Pose(pan_deg=10.0, tilt_deg=5.0))
    with pytest.raises(ValidationError) as exc:
        Trajectory(keyframes=[kf1, kf2])
    assert "Last keyframe progress must be 1.0" in str(exc.value)


def test_non_increasing_keyframe_progress():
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0))
    kf2 = Keyframe(progress=0.5, pose=Pose(pan_deg=10.0, tilt_deg=5.0))
    kf3 = Keyframe(progress=0.4, pose=Pose(pan_deg=20.0, tilt_deg=10.0))
    kf4 = Keyframe(progress=1.0, pose=Pose(pan_deg=30.0, tilt_deg=15.0))
    with pytest.raises(ValidationError) as exc:
        Trajectory(keyframes=[kf1, kf2, kf3, kf4])
    assert "strictly increasing" in str(exc.value)


def test_invalid_schedule():
    with pytest.raises(ValidationError):
        Schedule(total_shots=1, interval_s=5.0)  # total_shots < 2

    with pytest.raises(ValidationError):
        Schedule(total_shots=10, interval_s=0.0)  # interval_s <= 0


def test_rig_snapshot_defaults_and_validation():
    rig = RigSnapshot()
    assert rig.tilt_min_deg == 0.0
    assert rig.tilt_max_deg == 80.0

    with pytest.raises(ValidationError):
        RigSnapshot(tilt_min_deg=50.0, tilt_max_deg=10.0)
