import tempfile
from pathlib import Path
from session_manager import SessionManager, slugify_name


def test_slugify_name():
    assert slugify_name("Milkyway 2026-10-08!") == "Milkyway_2026-10-08"
    assert slugify_name("Sunset / Lake... #1") == "Sunset_Lake_1"
    assert slugify_name("   ") == "session"


def test_session_manager_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(base_dir=tmpdir)
        active = sm.get_active_session()
        assert active is not None
        assert active.slug.startswith("Session_")

        # Directories exist
        test_shots_dir = sm.get_active_test_shots_dir()
        timelapse_dir = sm.get_active_timelapse_dir()
        assert test_shots_dir.exists()
        assert timelapse_dir.exists()

        # Create new session
        s2 = sm.create_session(name="Milky Way Shoot", plan={"name": "Milky Way Track", "totalShots": 100})
        assert s2.name == "Milky Way Shoot"
        assert s2.slug == "Milky_Way_Shoot"
        assert sm.get_active_session().slug == "Milky_Way_Shoot"
        assert sm.get_active_test_shots_dir().parent.name == "Milky_Way_Shoot"

        # Add dummy test shot to s2
        dummy_file = sm.get_active_test_shots_dir() / "capture_001.jpg"
        dummy_file.write_bytes(b"dummy_test_shot")

        # List sessions
        sessions = sm.list_sessions()
        assert len(sessions) == 2
        s2_summary = next(s for s in sessions if s["slug"] == "Milky_Way_Shoot")
        assert s2_summary["is_active"] is True
        assert s2_summary["test_shots_count"] == 1
        assert s2_summary["thumbnail_url"] == "/api/sessions/Milky_Way_Shoot/test-shots/capture_001.jpg?quality=low"

        # Switch back to first session
        sm.switch_session(active.slug)
        assert sm.get_active_session().slug == active.slug
        assert sm.get_active_test_shots_dir().parent.name == active.slug

        # Update plan
        sm.save_active_plan({"name": "Updated Plan", "totalShots": 240})
        reloaded = sm.get_active_session()
        assert reloaded.plan["totalShots"] == 240

        # Rename session
        sm.rename_session(active.slug, "First Shoot")
        assert sm.get_active_session().name == "First Shoot"

        # Delete session s2
        assert sm.delete_session(s2.slug) is True
        assert len(sm.list_sessions()) == 1


def test_session_api_endpoints():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)

    # GET /api/sessions/active
    res = client.get("/api/sessions/active")
    assert res.status_code == 200
    active = res.json()
    assert "slug" in active
    assert "name" in active

    # POST /api/sessions
    create_res = client.post("/api/sessions", json={"name": "Sunset Harbor Shoot"})
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["name"] == "Sunset Harbor Shoot"
    assert created["slug"].startswith("Sunset_Harbor_Shoot")

    # Verify active session changed
    res_active = client.get("/api/sessions/active")
    assert res_active.json()["slug"] == created["slug"]

    # GET /api/sessions
    res_list = client.get("/api/sessions")
    assert res_list.status_code == 200
    sessions = res_list.json()
    assert any(s["slug"] == created["slug"] for s in sessions)

    # POST /api/sessions/active/plan
    res_plan = client.post("/api/sessions/active/plan", json={"name": "Harbor Move", "totalShots": 120})
    assert res_plan.status_code == 200
    assert res_plan.json()["plan"]["totalShots"] == 120

    # PATCH /api/sessions/{slug}
    res_rename = client.patch(f"/api/sessions/{created['slug']}", json={"name": "Sunset Harbor Renamed"})
    assert res_rename.status_code == 200
    assert res_rename.json()["name"] == "Sunset Harbor Renamed"

    # DELETE /api/sessions/{slug}
    res_del = client.delete(f"/api/sessions/{created['slug']}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "OK"


def test_session_takes_and_non_overwriting():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(base_dir=tmpdir)
        session = sm.create_session("MultiTakeTest")

        # Initial take is take_01
        take1 = sm.get_next_timelapse_take_dir(session.slug)
        assert take1.name == "take_01"

        # If take_01 has 0 files, calling get_next_timelapse_take_dir reuses take_01
        take1_again = sm.get_next_timelapse_take_dir(session.slug)
        assert take1_again.name == "take_01"

        # Now simulate images saved in take_01
        (take1 / "0001.jpg").write_bytes(b"frame1")
        (take1 / "0002.jpg").write_bytes(b"frame2")

        # Calling get_next_timelapse_take_dir now allocates take_02
        take2 = sm.get_next_timelapse_take_dir(session.slug)
        assert take2.name == "take_02"
        assert take2.exists()

        # Both takes are listed
        takes = sm.list_takes(session.slug)
        assert takes == ["take_01", "take_02"]

        # Latest take dir is take_02
        latest = sm.get_latest_timelapse_take_dir(session.slug)
        assert latest.name == "take_02"

        # list_sessions reflects total count across takes
        sessions = sm.list_sessions()
        s_data = next(s for s in sessions if s["slug"] == session.slug)
        assert s_data["timelapse_shots_count"] == 2
        assert s_data["takes_count"] == 2


