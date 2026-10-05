import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

import main
from main import app


def test_preview_latest_no_photo():
    with TestClient(app) as client:
        orig = main.camera_mgr.latest_photo_path
        main.camera_mgr.latest_photo_path = None
        try:
            resp = client.get("/api/camera/preview/latest")
            assert resp.status_code == 404
        finally:
            main.camera_mgr.latest_photo_path = orig


def test_preview_latest_quality_tiers(tmp_path: Path):
    with TestClient(app) as client:
        # Create a large test image (2400x1600)
        img_path = tmp_path / "test_shot_001.jpg"
        img = Image.new("RGB", (2400, 1600), color=(120, 50, 200))
        img.save(img_path, "JPEG")

        orig = main.camera_mgr.latest_photo_path
        main.camera_mgr.latest_photo_path = str(img_path)

        try:
            # 1. Low quality (default)
            resp_default = client.get("/api/camera/preview/latest")
            assert resp_default.status_code == 200
            assert resp_default.headers["content-type"] == "image/jpeg"
            cached_low = tmp_path / ".previews" / "test_shot_001_low.jpg"
            assert cached_low.exists()
            with Image.open(cached_low) as im_low:
                assert max(im_low.size) <= 1024

            # 2. Balanced quality
            resp_balanced = client.get("/api/camera/preview/latest?quality=balanced")
            assert resp_balanced.status_code == 200
            assert resp_balanced.headers["content-type"] == "image/jpeg"
            cached_balanced = tmp_path / ".previews" / "test_shot_001_balanced.jpg"
            assert cached_balanced.exists()
            with Image.open(cached_balanced) as im_med:
                assert max(im_med.size) <= 1920
                assert max(im_med.size) > 1024

            # 3. Full quality
            resp_full = client.get("/api/camera/preview/latest?quality=full")
            assert resp_full.status_code == 200
            assert len(resp_full.content) == img_path.stat().st_size
            with Image.open(img_path) as im_orig:
                assert im_orig.size == (2400, 1600)

            # 4. Verify alias ?tier=low
            resp_alias = client.get("/api/camera/preview/latest?tier=low")
            assert resp_alias.status_code == 200
            assert len(resp_alias.content) == cached_low.stat().st_size

        finally:
            main.camera_mgr.latest_photo_path = orig
