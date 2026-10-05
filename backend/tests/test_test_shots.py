from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from domain.models import AxisKeyframe, Schedule, SequencePlan, Trajectory, TransitionMode
from fake_camera_manager import FakeCameraManager
from main import app, plan_store


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    original_base_dir = plan_store.base_dir
    plan_store.base_dir = tmp_path / "plans"
    plan_store.base_dir.mkdir(parents=True, exist_ok=True)

    fake_cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    fake_cam.is_connected = True
    import main
    original_cam = main.camera_mgr
    main.camera_mgr = fake_cam

    yield

    plan_store.base_dir = original_base_dir
    main.camera_mgr = original_cam


def create_sample_plan() -> SequencePlan:
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=90.0, outgoing_mode=TransitionMode.SMOOTH),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=45.0, outgoing_mode=TransitionMode.SMOOTH),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
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

        # 4. Fetch Preview Artifact File (Default, Fast, and Full)
        resp = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}/artifacts/preview")
        assert resp.status_code == 200
        assert len(resp.content) > 0

        resp_fast = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}/artifacts/preview?quality=fast")
        assert resp_fast.status_code == 200
        assert len(resp_fast.content) > 0

        resp_full = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}/artifacts/preview?quality=full")
        assert resp_full.status_code == 200
        assert len(resp_full.content) > 0

        # 5. Delete Test Shot
        resp = client.delete(f"/api/plans/{plan.id}/test-shots/{shot_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "OK"

        # 6. Verify Deletion
        resp = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}")
        assert resp.status_code == 404
        resp = client.get(f"/api/plans/{plan.id}/test-shots")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


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


def test_camera_test_shots_history_and_tiered_files(tmp_path):
    import main
    capture_dir = Path(main.camera_mgr.capture_dir)
    capture_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy capture files
    sample_file_1 = capture_dir / "capture_20261001_120000.jpg"
    sample_file_1.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x11\x08\x00\x10\x00\x10\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\n\x0b\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xbf\x00\xff\xd9")

    sample_file_2 = capture_dir / "capture_20261001_120100.jpg"
    sample_file_2.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9")

    with TestClient(app) as client:
        # 1. List test shots
        resp = client.get("/api/camera/test-shots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "OK"
        assert data["count"] >= 2
        filenames = [s["filename"] for s in data["test_shots"]]
        assert "capture_20261001_120100.jpg" in filenames
        assert "capture_20261001_120000.jpg" in filenames

        # 2. Get specific test shot file
        resp_file = client.get("/api/camera/test-shots/capture_20261001_120100.jpg?quality=full")
        assert resp_file.status_code == 200
        assert len(resp_file.content) > 0

        # 3. Delete single test shot file
        resp_del = client.delete("/api/camera/test-shots/capture_20261001_120000.jpg")
        assert resp_del.status_code == 200
        assert resp_del.json()["deleted"] == "capture_20261001_120000.jpg"
        assert not sample_file_1.exists()

        # 4. Delete all remaining test shots
        resp_del_all = client.delete("/api/camera/test-shots")
        assert resp_del_all.status_code == 200
        del_data = resp_del_all.json()
        assert del_data["status"] == "OK"
        assert del_data["count"] >= 1
        assert "capture_20261001_120100.jpg" in del_data["deleted"]
        assert not sample_file_2.exists()

        # 5. Verify list is now empty
        resp_empty = client.get("/api/camera/test-shots")
        assert resp_empty.status_code == 200
        assert resp_empty.json()["count"] == 0
