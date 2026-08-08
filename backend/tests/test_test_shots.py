import pytest
from fastapi.testclient import TestClient

from domain.models import Keyframe, Pose, Schedule, SequencePlan, Trajectory, TransitionMode
from fake_camera_manager import FakeCameraManager
from main import app, plan_store


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    original_base_dir = plan_store.base_dir
    plan_store.base_dir = tmp_path / "plans"
    plan_store.base_dir.mkdir(parents=True, exist_ok=True)

    # Use FakeCameraManager for predictable test environment
    fake_cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    fake_cam.is_connected = True

    # Patch global camera_mgr in main
    import main
    original_cam = main.camera_mgr
    main.camera_mgr = fake_cam

    yield

    plan_store.base_dir = original_base_dir
    main.camera_mgr = original_cam


def create_sample_plan() -> SequencePlan:
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=90.0, tilt_deg=45.0), outgoing_mode=TransitionMode.SMOOTH)
    traj = Trajectory(keyframes=[kf1, kf2])
    sched = Schedule(total_shots=10, interval_s=5.0)
    plan = SequencePlan(name="Test Shot Plan", trajectory=traj, schedule=sched)
    return plan_store.save_plan(plan)


def test_create_and_fetch_test_shot_api():
    plan = create_sample_plan()

    with TestClient(app) as client:
        # 1. Trigger Test Shot
        resp = client.post(f"/api/plans/{plan.id}/test-shots")
        assert resp.status_code == 201
        meta = resp.json()
        shot_id = meta["shot_id"]
        assert meta["plan_id"] == str(plan.id)
        assert len(meta["checksum_sha256"]) == 64
        assert len(meta["artifacts"]) == 2

        # 2. List Test Shots
        resp = client.get(f"/api/plans/{plan.id}/test-shots")
        assert resp.status_code == 200
        shots_list = resp.json()
        assert len(shots_list) == 1
        assert shots_list[0]["shot_id"] == shot_id

        # 3. Get Test Shot Detail
        resp = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["shot_id"] == shot_id

        # 4. Fetch Preview Artifact File
        resp = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}/artifacts/preview")
        assert resp.status_code == 200
        assert len(resp.content) > 0


def test_test_shot_cleanup_on_camera_failure(tmp_path):
    plan = create_sample_plan()

    import main

    with TestClient(app) as client:
        # Disconnect camera inside active lifespan
        main.camera_mgr.is_connected = False
        resp = client.post(f"/api/plans/{plan.id}/test-shots")
        assert resp.status_code == 500

    # Ensure no orphan .tmp_ directories are left
    test_shots_dir = plan_store.base_dir / str(plan.id) / "test-shots"
    if test_shots_dir.exists():
        tmp_dirs = [d for d in test_shots_dir.iterdir() if d.name.startswith(".tmp_")]
        assert len(tmp_dirs) == 0
