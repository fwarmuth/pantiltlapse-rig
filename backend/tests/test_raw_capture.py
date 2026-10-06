import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from fake_camera_manager import FakeCameraManager
from main import app
import main


@pytest.fixture(autouse=True)
def setup_test_camera(tmp_path):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    fake_cam = FakeCameraManager(capture_dir=str(capture_dir))
    fake_cam.is_connected = True

    original_cam = main.camera_mgr
    main.camera_mgr = fake_cam

    yield fake_cam, capture_dir

    main.camera_mgr = original_cam


def test_raw_config_and_capture(tmp_path):
    with TestClient(app) as client:
        # 1. Check initial status
        res = client.get("/api/camera/status")
        assert res.status_code == 200
        assert "image_format" in res.json()

        # Check config choices contains RAW + L
        choices_res = client.get("/api/camera/config/choices")
        assert choices_res.status_code == 200
        assert "RAW + L" in choices_res.json()["choices"].get("image_format", [])

        # 2. Set image_format to RAW + L
        res = client.post("/api/camera/config", json={"image_format": "RAW + L"})
        assert res.status_code == 200
        assert res.json()["status"] == "OK"

        res = client.get("/api/camera/status")
        assert res.json()["image_format"] == "RAW + L"

        # 3. Trigger capture
        res = client.post("/api/camera/trigger")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "OK"
        assert data.get("has_raw") is True
        assert data.get("raw_filename") is not None
        assert data["raw_filename"].endswith(".cr2")

        # 4. List test shots
        res = client.get("/api/camera/test-shots")
        assert res.status_code == 200
        shots = res.json().get("test_shots", [])
        assert len(shots) == 1
        shot = shots[0]
        assert shot["has_raw"] is True
        assert shot["raw_filename"].endswith(".cr2")
        assert shot["raw_download_url"] == f"/api/camera/test-shots/{shot['raw_filename']}/download"
        assert shot["download_url"] == f"/api/camera/test-shots/{shot['filename']}/download"

        # 5. Download JPEG test shot
        res = client.get(shot["download_url"])
        assert res.status_code == 200
        assert f'filename="{shot["filename"]}"' in res.headers.get("content-disposition", "")

        # 6. Download RAW test shot
        res = client.get(shot["raw_download_url"])
        assert res.status_code == 200
        assert res.headers.get("content-type") == "image/x-canon-cr2"
        assert f'filename="{shot["raw_filename"]}"' in res.headers.get("content-disposition", "")

        # 7. Quality preview for RAW file (should serve companion jpeg preview)
        res = client.get(f"/api/camera/test-shots/{shot['raw_filename']}?quality=low")
        assert res.status_code == 200
        assert res.headers.get("content-type") == "image/jpeg"

        # 8. Delete test shot, should delete both JPEG and RAW companion
        res = client.delete(f"/api/camera/test-shots/{shot['filename']}")
        assert res.status_code == 200

        res = client.get("/api/camera/test-shots")
        assert res.status_code == 200
        assert len(res.json().get("test_shots", [])) == 0


def test_timelapse_capture_download(tmp_path):
    with TestClient(app) as client:
        # Create a mock capture directory and files for timelapse
        run_dir = tmp_path / "timelapse_captures"
        run_dir.mkdir(parents=True, exist_ok=True)
        img_file = run_dir / "0001.jpg"
        raw_file = run_dir / "0001.cr2"
        img_file.write_bytes(b"JPEG_BYTES")
        raw_file.write_bytes(b"CR2_RAW_BYTES")

        # Set timelapse_engine capture_dir
        orig_capture_dir = main.timelapse_engine.capture_dir
        main.timelapse_engine.capture_dir = str(run_dir)

        try:
            # Download JPEG capture
            res = client.get("/api/timelapse/captures/0001.jpg/download")
            assert res.status_code == 200
            assert res.content == b"JPEG_BYTES"
            assert 'filename="0001.jpg"' in res.headers.get("content-disposition", "")

            # Download RAW capture
            res = client.get("/api/timelapse/captures/0001.cr2/download")
            assert res.status_code == 200
            assert res.content == b"CR2_RAW_BYTES"
            assert res.headers.get("content-type") == "image/x-canon-cr2"
            assert 'filename="0001.cr2"' in res.headers.get("content-disposition", "")
        finally:
            main.timelapse_engine.capture_dir = orig_capture_dir
