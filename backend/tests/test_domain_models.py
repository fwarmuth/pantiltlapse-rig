import pytest
from pydantic import ValidationError

from domain.models import (
    AcquisitionProfile,
    AxisKeyframe,
    RigSnapshot,
    Schedule,
    SequencePlan,
    Trajectory,
    TransitionMode,
)


def make_valid_plan() -> SequencePlan:
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=1.0),
        AxisKeyframe(progress=0.5, value=180.0, outgoing_mode=TransitionMode.LINEAR, tangent_scale=0.5),
        AxisKeyframe(progress=1.0, value=370.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=1.0),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=1.0),
        AxisKeyframe(progress=0.7, value=40.0, outgoing_mode=TransitionMode.LINEAR, tangent_scale=0.5),
        AxisKeyframe(progress=1.0, value=80.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=1.0),
    ]
    trajectory = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
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
    assert len(reloaded.trajectory.pan_keyframes) == 3
    assert len(reloaded.trajectory.tilt_keyframes) == 3
    assert reloaded.trajectory.pan_keyframes[2].value == 370.0
    assert reloaded.trajectory.tilt_keyframes[1].progress == 0.7
    # Extra settings preservation check
    assert getattr(reloaded.acquisition, "extra_custom_param", None) == "lens_profile_1"


def test_invalid_keyframe_endpoints():
    # Non-zero starting progress
    pk1 = AxisKeyframe(progress=0.1, value=0.0)
    pk2 = AxisKeyframe(progress=1.0, value=10.0)
    tk1 = AxisKeyframe(progress=0.0, value=0.0)
    tk2 = AxisKeyframe(progress=1.0, value=5.0)
    with pytest.raises(ValidationError) as exc:
        Trajectory(pan_keyframes=[pk1, pk2], tilt_keyframes=[tk1, tk2])
    assert "First pan keyframe progress must be 0.0" in str(exc.value)

    # Non-1.0 ending progress
    pk1 = AxisKeyframe(progress=0.0, value=0.0)
    pk2 = AxisKeyframe(progress=0.9, value=10.0)
    with pytest.raises(ValidationError) as exc:
        Trajectory(pan_keyframes=[pk1, pk2], tilt_keyframes=[tk1, tk2])
    assert "Last pan keyframe progress must be 1.0" in str(exc.value)


def test_non_increasing_keyframe_progress():
    pk1 = AxisKeyframe(progress=0.0, value=0.0)
    pk2 = AxisKeyframe(progress=0.5, value=10.0)
    pk3 = AxisKeyframe(progress=0.4, value=20.0)
    pk4 = AxisKeyframe(progress=1.0, value=30.0)
    tk1 = AxisKeyframe(progress=0.0, value=0.0)
    tk2 = AxisKeyframe(progress=1.0, value=5.0)
    with pytest.raises(ValidationError) as exc:
        Trajectory(pan_keyframes=[pk1, pk2, pk3, pk4], tilt_keyframes=[tk1, tk2])
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
