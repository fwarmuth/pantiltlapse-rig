from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from domain.models import Keyframe, Pose, Schedule, SequencePlan, Trajectory, TransitionMode
from main import app, plan_store


@pytest.fixture(autouse=True)
def use_temp_plan_store(tmp_path):
    # Redirect plan_store base_dir to a temporary test directory
    original_base_dir = plan_store.base_dir
    plan_store.base_dir = tmp_path / "plans"
    plan_store.base_dir.mkdir(parents=True, exist_ok=True)
    yield
    plan_store.base_dir = original_base_dir


def create_sample_plan_payload(name: str = "API Test Plan") -> dict:
    kf1 = Keyframe(progress=0.0, pose=Pose(pan_deg=0.0, tilt_deg=0.0), outgoing_mode=TransitionMode.LINEAR)
    kf2 = Keyframe(progress=1.0, pose=Pose(pan_deg=180.0, tilt_deg=60.0), outgoing_mode=TransitionMode.SMOOTH)
    traj = Trajectory(keyframes=[kf1, kf2])
    sched = Schedule(total_shots=10, interval_s=5.0)
    plan = SequencePlan(name=name, trajectory=traj, schedule=sched)
    return plan.model_dump(mode="json")


def test_plan_api_full_workflow():
    with TestClient(app) as client:
        # 1. Create Plan (POST /api/plans)
        payload = create_sample_plan_payload("Sunrise Pan")
        resp = client.post("/api/plans", json=payload)
        assert resp.status_code == 201
        created_data = resp.json()
        plan_id = created_data["id"]
        assert created_data["name"] == "Sunrise Pan"
        assert created_data["revision"] == 1

        # 2. List Plans (GET /api/plans)
        resp = client.get("/api/plans")
        assert resp.status_code == 200
        summaries = resp.json()
        assert len(summaries) == 1
        assert summaries[0]["id"] == plan_id
        assert summaries[0]["total_shots"] == 10

        # 3. Get Plan Detail (GET /api/plans/{id})
        resp = client.get(f"/api/plans/{plan_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == plan_id
        assert len(detail["trajectory"]["keyframes"]) == 2

        # 4. Get Trajectory Samples (GET /api/plans/{id}/trajectory)
        resp = client.get(f"/api/plans/{plan_id}/trajectory")
        assert resp.status_code == 200
        traj_res = resp.json()
        assert traj_res["valid"] is True
        assert len(traj_res["samples"]) == 10
        assert traj_res["samples"][0]["pose"]["pan_deg"] == 0.0
        assert traj_res["samples"][9]["pose"]["pan_deg"] == 180.0

        # 5. Update Plan (PUT /api/plans/{id})
        detail["description"] = "Updated API Description"
        resp = client.put(f"/api/plans/{plan_id}", json=detail)
        assert resp.status_code == 200
        updated_data = resp.json()
        assert updated_data["revision"] == 2
        assert updated_data["description"] == "Updated API Description"

        # 6. Test Stale Revision Conflict (PUT /api/plans/{id} with revision=1)
        stale_payload = updated_data.copy()
        stale_payload["revision"] = 1  # Stale revision!
        resp = client.put(f"/api/plans/{plan_id}", json=stale_payload)
        assert resp.status_code == 409
        err_detail = resp.json()
        assert "Stale revision conflict" in err_detail["detail"]["message"]

        # 7. Delete Plan (DELETE /api/plans/{id})
        resp = client.delete(f"/api/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "OK"

        # 8. Verify 404 after deletion
        resp = client.get(f"/api/plans/{plan_id}")
        assert resp.status_code == 404


def test_plan_api_not_found_handling():
    with TestClient(app) as client:
        fake_id = str(uuid4())
        resp = client.get(f"/api/plans/{fake_id}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]["message"].lower()
