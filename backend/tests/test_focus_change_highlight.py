import pytest
from pathlib import Path
from uuid import uuid4

from fake_camera_manager import FakeCameraManager
from media_helper import create_test_shot_artifact


@pytest.mark.asyncio
async def test_focus_change_tracking_and_consumption():
    cam = FakeCameraManager()
    await cam.initialize()

    # Initial state: no actions
    fc0 = cam.consume_pending_focus_change()
    assert fc0["has_change"] is False
    assert fc0["summary"] == "Unchanged"
    assert fc0["actions"] == []

    # Step near 1 twice
    await cam.step_focus("near", 1)
    await cam.step_focus("near", 1)

    fc1 = cam.consume_pending_focus_change()
    assert fc1["has_change"] is True
    assert fc1["summary"] == "Near 1 (x2)"
    assert fc1["actions"] == ["Near 1", "Near 1"]

    # Now pending should be cleared
    fc2 = cam.consume_pending_focus_change()
    assert fc2["has_change"] is False
    assert fc2["summary"] == "Unchanged"


@pytest.mark.asyncio
async def test_test_shot_attaches_focus_change(tmp_path: Path):
    cam = FakeCameraManager(capture_dir=str(tmp_path / "captures"))
    await cam.initialize()
    plan_id = uuid4()
    plans_dir = tmp_path / "plans"

    # Shot 1: No focus change prior to shot
    res1 = await create_test_shot_artifact(
        plan_id=plan_id,
        camera_mgr=cam,
        plans_base_dir=plans_dir,
        requested_settings={"iso": "400", "shutter_speed": "1/125", "aperture": "4.5"},
    )
    assert res1["status"] == "OK"
    meta1 = res1["metadata"]
    assert "focus_change" in meta1
    assert meta1["focus_change"]["has_change"] is False
    assert meta1["focus_change"]["summary"] == "Unchanged"

    # Make focus adjustments before Shot 2
    await cam.step_focus("far", 2)
    res2 = await create_test_shot_artifact(
        plan_id=plan_id,
        camera_mgr=cam,
        plans_base_dir=plans_dir,
        requested_settings={"iso": "400", "shutter_speed": "1/125", "aperture": "4.5"},
    )
    assert res2["status"] == "OK"
    meta2 = res2["metadata"]
    assert meta2["focus_change"]["has_change"] is True
    assert meta2["focus_change"]["summary"] == "Far 2"
    assert meta2["focus_change"]["actions"] == ["Far 2"]

    # Shot 3 without adjustments: should be Unchanged
    res3 = await create_test_shot_artifact(
        plan_id=plan_id,
        camera_mgr=cam,
        plans_base_dir=plans_dir,
        requested_settings={"iso": "400", "shutter_speed": "1/125", "aperture": "4.5"},
    )
    assert res3["status"] == "OK"
    meta3 = res3["metadata"]
    assert meta3["focus_change"]["has_change"] is False
    assert meta3["focus_change"]["summary"] == "Unchanged"
