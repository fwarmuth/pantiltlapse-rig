from domain.models import Keyframe, Pose, RigSnapshot, Schedule, Trajectory, TransitionMode
from domain.trajectory import sample_trajectory


def test_two_point_linear_trajectory():
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=10.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=100.0, tilt_deg=50.0), outgoing_mode=TransitionMode.LINEAR)
    traj = Trajectory(keyframes=[kf1, kf2])
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
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0), outgoing_mode=TransitionMode.SMOOTH)
    kf2 = Keyframe(progress=0.5, pose=Pose(pan_deg=180.0, tilt_deg=40.0), outgoing_mode=TransitionMode.SMOOTH)
    kf3 = Keyframe(progress=1.0, pose=Pose(pan_deg=360.0, tilt_deg=80.0), outgoing_mode=TransitionMode.SMOOTH)
    traj = Trajectory(keyframes=[kf1, kf2, kf3])
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


def test_mixed_mode_trajectory():
    # kf1 -> kf2 is LINEAR, kf2 -> kf3 is SMOOTH
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=10.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=0.5, pose=Pose(pan_deg=50.0, tilt_deg=20.0), outgoing_mode=TransitionMode.SMOOTH)
    kf3 = Keyframe(progress=1.0, pose=Pose(pan_deg=150.0, tilt_deg=60.0), outgoing_mode=TransitionMode.SMOOTH)
    traj = Trajectory(keyframes=[kf1, kf2, kf3])
    sched = Schedule(total_shots=11, interval_s=1.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert len(result.samples) == 11
    # Shot 0..5 are in segment 0 (LINEAR)
    assert result.samples[2].active_segment == 0
    # Shot 6..10 are in segment 1 (SMOOTH)
    assert result.samples[7].active_segment == 1


def test_stopped_tangent_scale():
    # tangent_scale = 0.0 should ease to a stop
    kf1 = Keyframe(
        progress=0.0,
        pose=Pose(pan_deg=0.0, tilt_deg=0.0),
        outgoing_mode=TransitionMode.SMOOTH,
        tangent_scale=0.0,
    )
    kf2 = Keyframe(
        progress=1.0,
        pose=Pose(pan_deg=100.0, tilt_deg=50.0),
        outgoing_mode=TransitionMode.SMOOTH,
        tangent_scale=0.0,
    )
    traj = Trajectory(keyframes=[kf1, kf2])
    sched = Schedule(total_shots=11, interval_s=1.0)

    result = sample_trajectory(traj, sched)

    assert result.valid is True
    assert result.samples[0].pose.pan_deg == 0.0
    assert result.samples[10].pose.pan_deg == 100.0


def test_unwrapped_pan_and_negative_angles():
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=-180.0, tilt_deg=10.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=540.0, tilt_deg=70.0), outgoing_mode=TransitionMode.LINEAR)
    traj = Trajectory(keyframes=[kf1, kf2])
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
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=50.0, tilt_deg=95.0), outgoing_mode=TransitionMode.LINEAR)
    traj = Trajectory(keyframes=[kf1, kf2])
    sched = Schedule(total_shots=11, interval_s=1.0)

    result = sample_trajectory(traj, sched, rig_limits=rig)

    assert result.valid is False
    assert len(result.errors) > 0
    assert "violates rig limits" in result.errors[0]
