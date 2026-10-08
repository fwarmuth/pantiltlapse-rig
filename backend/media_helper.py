import asyncio
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


async def compute_sha256_async(file_path: Path) -> str:
    """Offload SHA256 computation off the asyncio event loop."""
    return await asyncio.to_thread(compute_sha256, file_path)


def extract_jpeg_exif(file_path: Path) -> dict[str, Any]:
    """Extract lightweight EXIF tags from a JPEG file without raw development."""
    if not file_path.name.lower().endswith((".jpg", ".jpeg")):
        return {}
    try:
        from PIL import ExifTags, Image
        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return {}
            tags = {}
            for tag_id, value in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if isinstance(value, (int, float, str)):
                    tags[tag_name] = value
                elif isinstance(value, bytes):
                    tags[tag_name] = value.hex()
            return tags
    except Exception as e:
        logger.debug(f"Could not extract EXIF from '{file_path}': {e}")
        return {}


_preview_semaphore = asyncio.Semaphore(1)


def generate_resized_preview_sync(
    orig_path: Path,
    dest_path: Path,
    max_dimension: int = 1024,
    quality: int = 75,
) -> bool:
    """Downscale an image file using Pillow, handling orientation and fast DCT draft."""
    if not orig_path.exists():
        return False
    if orig_path.suffix.lower() == ".svg":
        try:
            shutil.copy2(orig_path, dest_path)
            return True
        except Exception:
            return False

    tmp: Path | None = None
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image, ImageOps

        with Image.open(orig_path) as im:
            # 1. libjpeg DCT scaling MUST be set via draft() BEFORE reading pixels or transposing
            if hasattr(im, "draft") and max_dimension <= 1920:
                im.draft("RGB", (max_dimension, max_dimension))
            # 2. Exif orientation transposition on the DCT-reduced bitmap
            im = ImageOps.exif_transpose(im)
            # 3. Fast bilinear resample to exact target bounding box
            im.thumbnail((max_dimension, max_dimension), Image.Resampling.BILINEAR)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            tmp = dest_path.parent / f".tmp_{dest_path.stem}_{os.getpid()}_{uuid4().hex[:8]}.jpg"
            # 4. optimize=False avoids extra memory-heavy Huffman optimization pass
            im.save(tmp, "JPEG", quality=quality, optimize=False)
            tmp.replace(dest_path)
            return True
    except Exception as e:
        if tmp and tmp.exists():
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        logger.warning(f"Failed to generate resized preview '{dest_path}' from '{orig_path}': {e}")
        return False
    finally:
        # Reclaim memory immediately on memory-constrained devices (e.g. Pi Zero 2 W)
        try:
            import gc
            gc.collect()
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass


async def generate_resized_preview_async(
    orig_path: Path,
    dest_path: Path,
    max_dimension: int = 1024,
    quality: int = 75,
) -> bool:
    """Safely offload preview downscaling with serialized single-concurrency to prevent OOM/swap."""
    async with _preview_semaphore:
        if dest_path.exists() and orig_path.exists() and dest_path.stat().st_mtime >= orig_path.stat().st_mtime:
            return True
        return await asyncio.to_thread(
            generate_resized_preview_sync, orig_path, dest_path, max_dimension, quality
        )



async def publish_media_artifact(
    target_dir: Path,
    artifact_id: UUID,
    orig_path: Path,
    preview_path: Path | None,
    mime_type: str,
    extension: str,
    requested_settings: dict[str, str],
    observed_settings: dict[str, str],
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Modular, reusable artifact publication helper for test shots and run shot records.
    Atomically publishes original file, companion preview file, SHA256, byte sizes, EXIF, and metadata.json.
    """
    temp_dir = target_dir / f".tmp_{artifact_id.hex}"
    final_dir = target_dir / str(artifact_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        orig_filename = f"original{extension}"
        dest_orig = temp_dir / orig_filename
        await asyncio.to_thread(shutil.copy2, orig_path, dest_orig)

        orig_checksum = await compute_sha256_async(dest_orig)
        orig_byte_size = dest_orig.stat().st_size
        exif_tags = await asyncio.to_thread(extract_jpeg_exif, dest_orig)

        now_utc = datetime.now(timezone.utc).isoformat()
        rel_prefix = str(artifact_id)

        artifacts = [
            {
                "id": str(uuid4()),
                "type": "original",
                "filename": orig_filename,
                "relative_path": f"{rel_prefix}/{orig_filename}",
                "mime_type": mime_type,
                "byte_size": orig_byte_size,
                "checksum_sha256": orig_checksum,
                "created_at": now_utc,
            }
        ]

        if preview_path and preview_path.exists():
            preview_ext = preview_path.suffix or ".jpg"
            preview_filename = f"preview{preview_ext}"
            dest_preview = temp_dir / preview_filename
            await asyncio.to_thread(shutil.copy2, preview_path, dest_preview)

            prev_checksum = await compute_sha256_async(dest_preview)
            prev_byte_size = dest_preview.stat().st_size
            prev_mime = "image/svg+xml" if preview_ext == ".svg" else "image/jpeg"

            artifacts.append({
                "id": str(uuid4()),
                "type": "preview",
                "filename": preview_filename,
                "relative_path": f"{rel_prefix}/{preview_filename}",
                "mime_type": prev_mime,
                "byte_size": prev_byte_size,
                "checksum_sha256": prev_checksum,
                "created_at": now_utc,
            })

        metadata = {
            "id": str(artifact_id),
            "artifact_id": str(artifact_id),
            "shot_id": str(artifact_id),
            "created_at": now_utc,
            "checksum_sha256": orig_checksum,
            "byte_size": orig_byte_size,
            "requested_settings": requested_settings,
            "observed_settings": observed_settings,
            "exif": exif_tags,
            "artifacts": artifacts,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        meta_file = temp_dir / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_dir, final_dir)
        logger.info(f"Published media artifact '{artifact_id}' into '{final_dir}'")
        return {"status": "OK", "metadata": metadata}
    except Exception as e:
        logger.error(f"Error publishing media artifact: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"status": "ERROR", "message": str(e)}


async def create_test_shot_artifact(
    plan_id: UUID,
    camera_mgr: Any,
    plans_base_dir: Path,
    requested_settings: dict[str, str],
) -> dict[str, Any]:
    """
    Capture plan-scoped test shot, calculate checksum, write metadata.json,
    and publish atomically to output/plans/<plan_id>/test-shots/<test_shot_id>/.
    """
    if not camera_mgr.is_connected:
        return {"status": "ERROR", "message": "Camera is disconnected"}

    shot_id = uuid4()
    plan_dir = plans_base_dir / str(plan_id)
    test_shots_dir = plan_dir / "test-shots"
    test_shots_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Apply requested camera settings
        for param, val in requested_settings.items():
            if val and param in ("iso", "shutter_speed", "aperture", "white_balance"):
                res = await camera_mgr.set_config(param, str(val))
                if isinstance(res, dict) and res.get("status") != "OK":
                    logger.warning(f"Setting config '{param}={val}' warning: {res}")

        observed_settings = await camera_mgr.refresh_config()

        # Trigger capture
        stem = f"test_shot_{shot_id.hex[:8]}"
        cap_res = await camera_mgr.trigger_capture(filename=stem, target_dir=test_shots_dir)
        if cap_res.get("status") != "OK":
            return {"status": "ERROR", "message": cap_res.get("message", "Capture failed")}

        res_data = cap_res.get("result", {})
        orig_path = Path(cap_res.get("path") or res_data.get("saved_original_path"))
        if not orig_path or not orig_path.exists():
            return {"status": "ERROR", "message": "Captured file not found"}

        ext = res_data.get("extension") or orig_path.suffix or ".jpg"
        mime_type = res_data.get("mime_type") or ("image/svg+xml" if ext == ".svg" else "image/jpeg")
        preview_str = res_data.get("camera_preview_path")
        preview_path = Path(preview_str) if preview_str else (orig_path if ext in (".jpg", ".jpeg", ".svg") else None)

        focus_change = None
        if hasattr(camera_mgr, "consume_pending_focus_change"):
            focus_change = camera_mgr.consume_pending_focus_change()

        extra_meta = {
            "shot_id": str(shot_id),
            "plan_id": str(plan_id),
            "focus_change": focus_change,
        }

        pub_res = await publish_media_artifact(
            target_dir=test_shots_dir,
            artifact_id=shot_id,
            orig_path=orig_path,
            preview_path=preview_path,
            mime_type=mime_type,
            extension=ext,
            requested_settings=requested_settings,
            observed_settings=observed_settings,
            extra_metadata=extra_meta,
        )

        # Cleanup raw capture file from root test-shots dir
        try:
            if orig_path.exists():
                orig_path.unlink()
            if preview_path and preview_path.exists() and preview_path != orig_path:
                preview_path.unlink()
        except Exception:
            pass

        return pub_res
    except Exception as e:
        logger.error(f"Error creating test shot artifact: {e}")
        return {"status": "ERROR", "message": str(e)}
