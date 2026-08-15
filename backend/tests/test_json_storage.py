import json
from uuid import uuid4

import pytest

from domain.models import AxisKeyframe, Schedule, SequencePlan, Trajectory, TransitionMode
from storage import JsonlWriter, PlanStore


def create_sample_plan(name: str = "Test Plan") -> SequencePlan:
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
    return SequencePlan(name=name, trajectory=traj, schedule=sched)


def test_plan_crud_and_revision_increment(tmp_path):
    store = PlanStore(base_dir=tmp_path / "plans")

    plan = create_sample_plan("Sunset Pan")
    assert plan.revision == 1

    # 1. Create (Save)
    saved = store.save_plan(plan)
    assert saved.revision == 1
    plan_file = tmp_path / "plans" / str(saved.id) / "plan.json"
    assert plan_file.exists()

    # 2. Get (Read)
    loaded = store.get_plan(saved.id)
    assert loaded is not None
    assert loaded.name == "Sunset Pan"
    assert loaded.revision == 1

    # 3. Update
    loaded.description = "Updated description"
    updated = store.save_plan(loaded)
    assert updated.revision == 2

    reloaded = store.get_plan(saved.id)
    assert reloaded.revision == 2
    assert reloaded.description == "Updated description"

    # 4. List
    plan2 = create_sample_plan("Macro Motion")
    store.save_plan(plan2)

    plan_list = store.list_plans()
    assert len(plan_list) == 2
    assert plan_list[0].id in (saved.id, plan2.id)

    # 5. Delete
    deleted = store.delete_plan(saved.id)
    assert deleted is True
    assert store.get_plan(saved.id) is None
    assert len(store.list_plans()) == 1


def test_path_traversal_rejection(tmp_path):
    store = PlanStore(base_dir=tmp_path / "plans")

    with pytest.raises(ValueError) as exc:
        store._get_plan_dir("../../../etc/passwd")
    assert "Invalid plan ID format" in str(exc.value)

    assert store.get_plan("../../../etc/passwd") is None
    assert store.delete_plan("invalid-uuid-string") is False


def test_corrupt_manifest_isolation(tmp_path):
    store = PlanStore(base_dir=tmp_path / "plans")

    # Create one valid plan
    valid_plan = create_sample_plan("Valid Plan")
    store.save_plan(valid_plan)

    # Create a corrupt plan directory with garbage JSON
    corrupt_dir = tmp_path / "plans" / str(uuid4())
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    with open(corrupt_dir / "plan.json", "w", encoding="utf-8") as f:
        f.write("{this is invalid json content")

    # list_plans should skip corrupt manifest without crashing
    plans = store.list_plans()
    assert len(plans) == 1
    assert plans[0].id == valid_plan.id


def test_jsonl_writer(tmp_path):
    event_file = tmp_path / "events.jsonl"

    JsonlWriter.append_event(event_file, {"event": "START", "code": 200})
    JsonlWriter.append_event(event_file, {"event": "SHOT", "shot": 1})

    assert event_file.exists()
    lines = event_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "START"
    assert json.loads(lines[1])["shot"] == 1
