import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from domain.studio_state import AppStateManager, StudioState
import main


def test_studio_state_defaults_and_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = AppStateManager(storage_dir=tmpdir)
        assert mgr.state.active_step == 1
        assert mgr.state.jog_step_deg == 1.0
        assert mgr.state.filter_settings.mode == "none"

        plan_id = uuid4()
        mgr.update(
            active_step=3,
            active_plan_id=plan_id,
            jog_step_deg=5.0,
            filter_settings={"mode": "clahe", "gain": 2.5, "contrast": 1.8},
            active_track_tab="tilt",
            curve_filter="pan",
        )

        assert mgr.state.active_step == 3
        assert mgr.state.active_plan_id == plan_id
        assert mgr.state.jog_step_deg == 5.0
        assert mgr.state.filter_settings.mode == "clahe"
        assert mgr.state.filter_settings.gain == 2.5
        assert mgr.state.active_track_tab == "tilt"
        assert mgr.state.curve_filter == "pan"

        # Verify atomic persistence by re-loading in a new manager
        mgr2 = AppStateManager(storage_dir=tmpdir)
        assert mgr2.state.active_step == 3
        assert mgr2.state.active_plan_id == plan_id
        assert mgr2.state.jog_step_deg == 5.0
        assert mgr2.state.filter_settings.mode == "clahe"
        assert mgr2.state.active_track_tab == "tilt"
        assert mgr2.state.curve_filter == "pan"


def test_api_app_state_get_and_post():
    client = TestClient(main.app)
    # GET state
    res = client.get("/api/app/state")
    assert res.status_code == 200
    data = res.json()
    assert "active_step" in data
    assert "jog_step_deg" in data
    assert "filter_settings" in data

    # POST update
    new_plan_id = str(uuid4())
    post_res = client.post(
        "/api/app/state",
        json={
            "active_step": 4,
            "active_plan_id": new_plan_id,
            "jog_step_deg": 15.0,
            "filter_settings": {"mode": "night_vision", "gain": 3.0, "contrast": 1.5},
            "active_track_tab": "tilt",
        },
    )
    assert post_res.status_code == 200
    updated = post_res.json()
    assert updated["active_step"] == 4
    assert updated["active_plan_id"] == new_plan_id
    assert updated["jog_step_deg"] == 15.0
    assert updated["active_track_tab"] == "tilt"


def test_frontend_markup_integration():
    client = TestClient(main.app)
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert 'id="toastContainer"' in html
    assert 'id="recalibrateModal"' in html
    assert 'onclick="goHome()"' in html
    assert 'id="execZeroWarningBanner"' in html
