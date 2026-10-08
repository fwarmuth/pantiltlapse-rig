import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


def test_timelapse_captures_endpoints():
    client = TestClient(main.app)

    # When no run has occurred or capture_dir is None
    main.timelapse_engine.capture_dir = None
    res = client.get("/api/timelapse/captures")
    assert res.status_code == 200
    assert res.json() == []

    # Create dummy capture dir with sample captures
    with tempfile.TemporaryDirectory() as tmpdir:
        main.timelapse_engine.capture_dir = tmpdir
        main.timelapse_engine.captured_shots = [
            {
                "shot_index": 1,
                "filename": "tl_test_0001.jpg",
                "pan": 5.0,
                "tilt": 2.0,
                "timestamp": "2026-09-26T22:00:00Z",
            }
        ]
        # Create the file on disk
        img_file = Path(tmpdir) / "tl_test_0001.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0testjpeg")

        # GET /api/timelapse/captures
        res = client.get("/api/timelapse/captures")
        assert res.status_code == 200
        captures = res.json()
        assert len(captures) == 1
        assert captures[0]["shot_index"] == 1
        assert captures[0]["filename"] == "tl_test_0001.jpg"
        assert captures[0]["url"] == "/api/timelapse/captures/tl_test_0001.jpg"
        assert captures[0]["exists"] is True

        # GET /api/timelapse/captures/tl_test_0001.jpg
        img_res = client.get("/api/timelapse/captures/tl_test_0001.jpg")
        assert img_res.status_code == 200
        assert img_res.content == b"\xff\xd8\xff\xe0testjpeg"

        # Missing file returns 404
        missing_res = client.get("/api/timelapse/captures/missing.jpg")
        assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_timelapse_eager_preview_generation():
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmpdir:
        main.timelapse_engine.capture_dir = tmpdir
        main.timelapse_engine._latest_capture = {
            "shot_index": 1,
            "filename": "tl_0001.jpg",
            "url": "/api/timelapse/captures/tl_0001.jpg?quality=low",
            "timestamp": "2026-10-08T12:00:00Z",
        }
        status = main.timelapse_engine.get_status()
        assert status["latest_capture"] is not None
        assert status["latest_capture"]["shot_index"] == 1

        # Create a valid JPEG
        img = Image.new("RGB", (200, 200), color=(255, 0, 0))
        img_path = Path(tmpdir) / "tl_0001.jpg"
        img.save(img_path, "JPEG")

        # Call eager preview generation
        await main.timelapse_engine._eager_generate_preview("tl_0001.jpg")

        preview_path = Path(tmpdir) / ".previews" / "tl_0001_low.jpg"
        assert preview_path.exists()
        assert preview_path.stat().st_size > 0

