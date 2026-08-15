from domain.models import AxisKeyframe, RigSnapshot, Schedule, Trajectory, TransitionMode
from domain.trajectory import sample_trajectory


def test_two_point_linear_trajectory():
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=100.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=10.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=50.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=11, interval_s=2.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert len(result.samples) == 11
    assert result.samples[0].pose.pan_deg == 0.0
    assert result.samples[0].pose.tilt_deg == 10.0
    assert result.samples[5].pose.pan_deg == 50.0
    assert result.samples[5].pose.tilt_deg == 30.0
    assert result.samples[10].pose.pan_deg == 100.0
    assert result.samples[10].pose.tilt_deg == 50.0
    assert result.planned_duration_s == 20.0
    assert result.max_pan_delta_deg == 10.0
    assert result.max_tilt_delta_deg == 4.0


def test_multi_keyframe_smooth_hermite_trajectory():
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.SMOOTH),
        AxisKeyframe(progress=0.5, value=180.0, outgoing_mode=TransitionMode.SMOOTH),
        AxisKeyframe(progress=1.0, value=360.0, outgoing_mode=TransitionMode.SMOOTH),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.SMOOTH),
        AxisKeyframe(progress=0.5, value=40.0, outgoing_mode=TransitionMode.SMOOTH),
        AxisKeyframe(progress=1.0, value=80.0, outgoing_mode=TransitionMode.SMOOTH),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=21, interval_s=5.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert len(result.samples) == 21
    # Check exact endpoints and midpoint
    assert result.samples[0].pose.pan_deg == 0.0
    assert result.samples[10].pose.pan_deg == 180.0
    assert result.samples[10].pose.tilt_deg == 40.0
    assert result.samples[20].pose.pan_deg == 360.0
    assert result.samples[20].pose.tilt_deg == 80.0


def test_independent_asymmetric_tracks():
    # Pan has a waypoint at t=0.2, Tilt has a waypoint at t=0.8
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=0.2, value=90.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=180.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=10.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=0.8, value=50.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=20.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=11, interval_s=1.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert len(result.samples) == 11
    # At t=0.2 (shot 2), Pan is exactly 90.0
    assert result.samples[2].pose.pan_deg == 90.0
    # At t=0.8 (shot 8), Tilt is exactly 50.0
    assert result.samples[8].pose.tilt_deg == 50.0


def test_stopped_tangent_scale():
    # tangent_scale = 0.0 should ease to a stop
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=0.0),
        AxisKeyframe(progress=1.0, value=100.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=0.0),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=0.0),
        AxisKeyframe(progress=1.0, value=50.0, outgoing_mode=TransitionMode.SMOOTH, tangent_scale=0.0),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=11, interval_s=1.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert result.samples[0].pose.pan_deg == 0.0
    assert result.samples[10].pose.pan_deg == 100.0


def test_unwrapped_pan_and_negative_angles():
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=-180.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=540.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=10.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=70.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=5, interval_s=1.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert result.samples[0].pose.pan_deg == -180.0
    assert result.samples[2].pose.pan_deg == 180.0
    assert result.samples[4].pose.pan_deg == 540.0


def test_tilt_limit_violation_detection():
    # Rig tilt limits: 0.0° to 80.0°
    rig = RigSnapshot(tilt_min_deg=0.0, tilt_max_deg=80.0)
    # Pose exceeds tilt max (95.0°)
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=50.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=95.0, outgoing_mode=TransitionMode.LINEAR),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=11, interval_s=1.0)

    result = sample_trajectory(traj, sched, rig_limits=rig)

    assert result.valid is False
    assert len(result.errors) > 0
    assert "violates rig limits" in result.errors[0]
