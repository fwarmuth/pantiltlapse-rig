import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger("CameraCommander.Media")


def compute_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


async def create_test_shot_artifact(
    plan_id: UUID,
    camera_mgr: Any,
    plans_base_dir: Path,
    requested_settings: dict[str, str],
) -> dict[str, Any]:
    """
    Capture plan-scoped test shot, calculate checksum, generate preview, write metadata.json,
    and atomically publish to output/plans/<plan_id>/test-shots/<test_shot_id>/.
    Cleans up temporary files on capture failure.
    """
    if not camera_mgr.is_connected:
        return {"status": "ERROR", "message": "Camera is disconnected"}

    shot_id = uuid4()
    plan_dir = plans_base_dir / str(plan_id)
    test_shots_dir = plan_dir / "test-shots"
    temp_dir = test_shots_dir / f".tmp_{shot_id.hex}"
    final_dir = test_shots_dir / str(shot_id)

    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Apply requested camera settings
        for param, val in requested_settings.items():
            if val and param in ("iso", "shutter_speed", "aperture"):
                await camera_mgr.set_config(param, str(val))

        observed_settings = await camera_mgr.refresh_config()

        # Trigger capture into temp directory
        filename = "original.jpg"
        cap_res = await camera_mgr.trigger_capture(filename=filename, target_dir=temp_dir)
        if cap_res.get("status") != "OK":
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"status": "ERROR", "message": cap_res.get("message", "Capture failed")}

        orig_file = Path(cap_res["path"])
        if not orig_file.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"status": "ERROR", "message": "Captured file not found"}

        # Determine mime type & file extension
        is_svg = orig_file.name.endswith(".svg")
        orig_mime = "image/svg+xml" if is_svg else "image/jpeg"
        orig_filename = "original.svg" if is_svg else "original.jpg"
        if orig_file.name != orig_filename:
            target_orig = temp_dir / orig_filename
            orig_file.rename(target_orig)
            orig_file = target_orig

        checksum = compute_sha256(orig_file)
        byte_size = orig_file.stat().st_size

        # Create preview artifact (JPEG or SVG copy)
        preview_filename = "preview.svg" if is_svg else "preview.jpg"
        preview_file = temp_dir / preview_filename
        shutil.copy2(orig_file, preview_file)
        preview_mime = orig_mime

        now_utc = datetime.now(timezone.utc).isoformat()
        rel_prefix = f"test-shots/{shot_id}"

        artifacts = [
            {
                "id": str(uuid4()),
                "type": "original",
                "relative_path": f"{rel_prefix}/{orig_filename}",
                "mime_type": orig_mime,
                "created_at": now_utc,
            },
            {
                "id": str(uuid4()),
                "type": "preview",
                "relative_path": f"{rel_prefix}/{preview_filename}",
                "mime_type": preview_mime,
                "created_at": now_utc,
            },
        ]

        metadata = {
            "shot_id": str(shot_id),
            "plan_id": str(plan_id),
            "created_at": now_utc,
            "checksum_sha256": checksum,
            "byte_size": byte_size,
            "requested_settings": requested_settings,
            "observed_settings": observed_settings,
            "artifacts": artifacts,
        }

        meta_file = temp_dir / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Atomically rename temporary directory to final shot ID directory
        os.replace(temp_dir, final_dir)
        logger.info(f"Published test shot artifact '{shot_id}' for plan '{plan_id}'")

        return {"status": "OK", "metadata": metadata}
    except Exception as e:
        logger.error(f"Error creating test shot artifact: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"status": "ERROR", "message": str(e)}
