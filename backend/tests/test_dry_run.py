import pytest
from fastapi.testclient import TestClient

from domain.models import Keyframe, Pose, Schedule, SequencePlan, Trajectory, TransitionMode
from fake_camera_manager import FakeCameraManager
from main import app, coordinator, plan_store, rig_mgr, serial_mgr


@pytest.fixture(autouse=True)
def setup_dry_run_env(tmp_path):
    original_base_dir = plan_store.base_dir
    plan_store.base_dir = tmp_path / "plans"
    plan_store.base_dir.mkdir(parents=True, exist_ok=True)

    fake_cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    fake_cam.is_connected = True

    import main
    main.camera_mgr = fake_cam
    serial_mgr.is_connected = True

    yield

    plan_store.base_dir = original_base_dir


def create_test_plan() -> SequencePlan:
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=100.0, tilt_deg=50.0), outgoing_mode=TransitionMode.SMOOTH)
    traj = Trajectory(keyframes=[kf1, kf2])
    sched = Schedule(total_shots=5, interval_s=2.0)
    plan = SequencePlan(name="Dry Run Test Plan", trajectory=traj, schedule=sched)
    return plan_store.save_plan(plan)


def test_dry_run_unconfirmed_reference_rejected():
    plan = create_test_plan()
    rig_mgr.reference.confirmed = False

    with TestClient(app) as client:
        serial_mgr.is_connected = True
        resp = client.post(f"/api/plans/{plan.id}/dry-run/start")
        assert resp.status_code == 409
        assert "unconfirmed" in resp.json()["detail"]["message"].lower()


def test_dry_run_full_execution_and_stale_detection(monkeypatch):
    plan = create_test_plan()

    # Stub move_absolute to simulate instant successful motor movement
    async def mock_move_absolute(pan: float, tilt: float):
        return {"status": "OK", "response": "DONE"}
    monkeypatch.setattr(serial_mgr, "move_absolute", mock_move_absolute)

    with TestClient(app) as client:
        serial_mgr.is_connected = True
        # Confirm zero reference
        client.post("/api/rig/confirm-zero")

        # Start Dry Run
        resp = client.post(f"/api/plans/{plan.id}/dry-run/start")
        assert resp.status_code == 200

        # Poll status until dry run task loop completes
        import time
        for _ in range(30):
            resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
            if resp.status_code == 200 and resp.json()["status"]["state"] == "COMPLETED":
                break
            time.sleep(0.1)

        # Fetch status & report
        resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["state"] == "COMPLETED"

        # Report check
        report = data["report"]
        assert report is not None
        assert report["plan_id"] == str(plan.id)
        assert report["stale"] is False

        # Material edit on plan increments revision -> Report should become stale
        plan.description = "Edited after dry run"
        plan_store.save_plan(plan)

        resp = client.get(f"/api/plans/{plan.id}/dry-run/status")
        report_stale = resp.json()["report"]
        assert report_stale["stale"] is True


def test_dry_run_lock_conflict():
    plan = create_test_plan()

    with TestClient(app) as client:
        serial_mgr.is_connected = True
        client.post("/api/rig/confirm-zero")

        # Manually lock coordinator mode to RECORDING
        coordinator.active_mode = "RECORDING"

        resp = client.post(f"/api/plans/{plan.id}/dry-run/start")
        assert resp.status_code == 409
        assert "busy" in resp.json()["detail"]["message"].lower()

        coordinator.active_mode = "IDLE"
