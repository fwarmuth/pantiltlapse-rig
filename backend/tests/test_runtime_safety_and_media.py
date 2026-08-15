import asyncio

import pytest
from fastapi.testclient import TestClient

from domain.models import AxisKeyframe, Schedule, SequencePlan, Trajectory, TransitionMode
from domain.rig import RigManager
from fake_camera_manager import FakeCameraManager
from main import app, coordinator, plan_store, preview_controller, rig_mgr, serial_mgr


@pytest.fixture(autouse=True)
def setup_stabilization_env(tmp_path):
    original_base_dir = plan_store.base_dir
    plan_store.base_dir = tmp_path / "plans"
    plan_store.base_dir.mkdir(parents=True, exist_ok=True)

    rig_mgr.storage_dir = tmp_path / "output"
    rig_mgr.storage_dir.mkdir(parents=True, exist_ok=True)
    rig_mgr.rig_file = rig_mgr.storage_dir / "rig.json"
    rig_mgr.set_limits(0.0, 80.0)

    fake_cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    fake_cam.is_connected = True

    import main
    main.camera_mgr = fake_cam
    preview_controller.camera_mgr = fake_cam

    if coordinator.is_previewing:
        asyncio.run(coordinator.release("PREVIEW"))
    if coordinator.is_dry_running:
        asyncio.run(coordinator.release("DRY_RUN"))
    if coordinator.is_recording:
        asyncio.run(coordinator.release("RECORDING"))

    yield

    plan_store.base_dir = original_base_dir
    rig_mgr.set_limits(0.0, 80.0)
    if coordinator.is_previewing:
        asyncio.run(coordinator.release("PREVIEW"))
    if coordinator.is_dry_running:
        asyncio.run(coordinator.release("DRY_RUN"))
    if coordinator.is_recording:
        asyncio.run(coordinator.release("RECORDING"))


def create_sample_plan(name: str = "Safety Test Plan") -> SequencePlan:
    pan_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=30.0, outgoing_mode=TransitionMode.SMOOTH),
    ]
    tilt_kfs = [
        AxisKeyframe(progress=0.0, value=0.0, outgoing_mode=TransitionMode.LINEAR),
        AxisKeyframe(progress=1.0, value=15.0, outgoing_mode=TransitionMode.SMOOTH),
    ]
    traj = Trajectory(pan_keyframes=pan_kfs, tilt_keyframes=tilt_kfs)
    sched = Schedule(total_shots=3, interval_s=2.0)
    plan = SequencePlan(name=name, trajectory=traj, schedule=sched)
    return plan_store.save_plan(plan)


def test_persisted_rig_limits(tmp_path):
    storage_dir = tmp_path / "output"
    rig1 = RigManager(tilt_min_deg=0.0, tilt_max_deg=80.0, storage_dir=storage_dir)
    assert rig1.snapshot.tilt_min_deg == 0.0
    assert rig1.snapshot.tilt_max_deg == 80.0

    rig1.set_limits(tilt_min_deg=10.0, tilt_max_deg=60.0)
    assert (storage_dir / "rig.json").exists()

    # Re-initialize RigManager from same directory -> should reload 10.0 and 60.0
    rig2 = RigManager(storage_dir=storage_dir)
    assert rig2.snapshot.tilt_min_deg == 10.0
    assert rig2.snapshot.tilt_max_deg == 60.0
    assert rig2.reference.confirmed is False  # In-memory zero confirmation starts False


def test_operation_coordinator_concurrency_matrix():
    plan_a = create_sample_plan("Plan A")
    plan_b = create_sample_plan("Plan B")

    with TestClient(app) as client:
        serial_mgr.is_connected = True
        client.post("/api/rig/confirm-zero")

        # Acquire DRY_RUN for Plan A
        asyncio.run(coordinator.acquire("DRY_RUN", str(plan_a.id)))

        # Manual move attempt should return 409 Conflict
        resp = client.post("/api/motors/move", json={"pan": 5, "tilt": 0, "relative": True})
        assert resp.status_code == 409
        assert "busy" in resp.json()["detail"]["message"].lower()

        # Driver toggle attempt should return 409 Conflict
        resp = client.post("/api/motors/drivers", json={"enable": False})
        assert resp.status_code == 409

        # Limit update attempt should return 409 Conflict
        resp = client.post("/api/rig/limits", json={"tilt_min_deg": 5, "tilt_max_deg": 70})
        assert resp.status_code == 409

        # Test shot attempt should return 409 Conflict
        resp = client.post(f"/api/plans/{plan_a.id}/test-shots")
        assert resp.status_code == 409

        # Preview for DIFFERENT plan B should return 409 Conflict
        resp = client.post("/api/camera/preview/start", json={"gain": 1.0, "plan_id": str(plan_b.id)})
        assert resp.status_code == 409

        # Preview for SAME plan A should succeed
        resp = client.post("/api/camera/preview/start", json={"gain": 1.0, "plan_id": str(plan_a.id)})
        assert resp.status_code == 200

        asyncio.run(coordinator.release("DRY_RUN"))
        asyncio.run(coordinator.release("PREVIEW"))


def test_dry_run_motor_failure_inspection(monkeypatch):
    plan = create_sample_plan("Fail Plan")

    # Mock serial move_absolute to return ERROR on pose 2
    call_count = 0

    async def mock_failing_move(pan: float, tilt: float):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            return {"status": "ERROR", "message": "Simulated Motor Stall"}
        return {"status": "OK"}

    monkeypatch.setattr(serial_mgr, "move_absolute", mock_failing_move)

    with TestClient(app) as client:
        serial_mgr.is_connected = True
        client.post("/api/rig/confirm-zero")

        resp = client.post(f"/api/plans/{plan.id}/dry-run/start")
        assert resp.status_code == 200

        import time
        for _ in range(20):
            resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
            if resp.json()["status"]["state"] == "ERROR":
                break
            time.sleep(0.1)

        resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
        data = resp.json()
        assert data["status"]["state"] == "ERROR"
        report = data["report"]
        assert report["valid"] is False
        assert "Stall" in report["error_message"]
        # Completed shots count must NOT increment for failed pose
        assert report["completed_shots"] == 1


def test_rig_limit_change_invalidates_dry_run_report(monkeypatch):
    plan = create_sample_plan("Limit Stale Plan")

    async def mock_ok_move(pan: float, tilt: float):
        return {"status": "OK"}
    monkeypatch.setattr(serial_mgr, "move_absolute", mock_ok_move)

    with TestClient(app) as client:
        serial_mgr.is_connected = True
        client.post("/api/rig/confirm-zero")

        # Run dry run to completion
        client.post(f"/api/plans/{plan.id}/dry-run/start")
        import time
        time.sleep(0.3)

        resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
        report = resp.json()["report"]
        assert report is not None
        assert report["stale"] is False

        # Changing rig limits makes report stale even if coordinate reference ID is untouched
        rig_mgr.set_limits(tilt_min_deg=5.0, tilt_max_deg=75.0)

        resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
        assert resp.json()["report"]["stale"] is True


def test_typed_fake_camera_capture_and_artifacts():
    plan = create_sample_plan("Typed Camera Plan")

    with TestClient(app) as client:
        # Trigger Test Shot
        resp = client.post(f"/api/plans/{plan.id}/test-shots", json={"iso": "800", "shutter_speed": "1/250"})
        assert resp.status_code == 201
        meta = resp.json()

        shot_id = meta["shot_id"]
        assert "checksum_sha256" in meta
        assert "byte_size" in meta
        assert len(meta["artifacts"]) >= 1

        # Fetch artifact by type "original"
        resp = client.get(f"/api/plans/{plan.id}/test-shots/{shot_id}/artifacts/original")
        assert resp.status_code == 200
        assert len(resp.content) > 0
