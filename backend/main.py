import asyncio
import json
import logging
import os
import shutil
from contextlib import asynccontextmanager
from uuid import UUID

import dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camera_manager import CameraManager
from coordinator import OperationCoordinator
from domain.models import SequencePlan
from domain.rig import RigManager
from domain.trajectory import sample_trajectory
from dry_run_engine import DryRunEngine
from fake_camera_manager import FakeCameraManager
from preview_controller import PreviewController
from serial_manager import SerialManager
from storage import PlanStore
from timelapse_engine import TimelapseConfig, TimelapseEngine

# Load deployment environment variables from backend/.env file if present
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
dotenv.load_dotenv(dotenv_path=ENV_FILE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CameraCommander.Backend")

# Hardware & Engine Managers Initialization
serial_mgr = SerialManager(
    port=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
    baudrate=int(os.getenv("SERIAL_BAUD", "9600")),
)

use_fake_camera = os.getenv("FAKE_CAMERA", "false").lower() == "true"
capture_dir = os.path.join(os.path.dirname(__file__), "..", "output", "captures")
if use_fake_camera:
    logger.info("Initializing application with FakeCameraManager (FAKE_CAMERA=true)")
    camera_mgr = FakeCameraManager(capture_dir=capture_dir)
else:
    logger.info("Initializing application with real CameraManager (gphoto2)")
    camera_mgr = CameraManager(capture_dir=capture_dir)

timelapse_engine = TimelapseEngine(serial_mgr=serial_mgr, camera_mgr=camera_mgr)
plan_store = PlanStore()
rig_mgr = RigManager(tilt_min_deg=0.0, tilt_max_deg=80.0)

coordinator = OperationCoordinator()
dry_run_engine = DryRunEngine(
    serial_mgr=serial_mgr,
    rig_mgr=rig_mgr,
    plan_store=plan_store,
    coordinator=coordinator,
)
preview_controller = PreviewController(
    camera_mgr=camera_mgr,
    coordinator=coordinator,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CameraCommander Backend starting up...")
    rig_mgr.invalidate_reference("Backend startup")
    await serial_mgr.connect()
    await camera_mgr.initialize()
    if camera_mgr.is_connected:
        await camera_mgr.apply_startup_defaults()
    yield
    logger.info("CameraCommander Backend shutting down...")
    await timelapse_engine.cancel()
    camera_mgr.close()


app = FastAPI(title="CameraCommander REST API", version="0.4.0", lifespan=lifespan)

# Allow CORS for mobile apps & web UI clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".css", ".js", ".html")) or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Pydantic Schemas
class MoveRequest(BaseModel):
    pan: float = Field(default=0.0, description="Target Pan angle in degrees (or relative delta)")
    tilt: float = Field(default=0.0, description="Target Tilt angle in degrees (or relative delta)")
    relative: bool = Field(default=True, description="If True, move relative to current position. Otherwise absolute.")


class DriverRequest(BaseModel):
    enable: bool = Field(default=True, description="Enable (True) or Disable (False) stepper motor drivers")


class RigLimitsRequest(BaseModel):
    tilt_min_deg: float = Field(default=0.0, description="Minimum allowable tilt angle in degrees")
    tilt_max_deg: float = Field(default=80.0, description="Maximum allowable tilt angle in degrees")


class CameraConfigRequest(BaseModel):
    param: str = Field(description="Parameter key: 'iso', 'shutter_speed', or 'aperture'")
    value: str = Field(description="Parameter target value, e.g. '400', '1/125'")


class SequenceStepRequest(BaseModel):
    pan: float = Field(default=5.0, description="Pan angle (relative or absolute)")
    tilt: float = Field(default=0.0, description="Tilt angle (relative or absolute)")
    relative: bool = Field(default=True, description="If True, relative move")
    pause_s: float = Field(default=0.5, description="Settle time pause after move before shooting (seconds)")
    capture: bool = Field(default=True, description="Trigger photo capture")


def _require_serial_connected():
    if not serial_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Motor controller is disconnected"},
        )


# --- Rig & Coordinate Reference Endpoints ---
@app.get("/api/rig/status")
async def get_rig_status():
    """Return physical rig limits and coordinate reference state."""
    return {
        "snapshot": rig_mgr.snapshot,
        "reference": rig_mgr.reference,
    }


@app.post("/api/rig/limits")
async def update_rig_limits(req: RigLimitsRequest):
    """Update allowable rig tilt bounds."""
    if not coordinator.can_change_limits():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "ERROR", "message": f"Operation lock busy: '{coordinator.active_mode}' active"},
        )
    if req.tilt_max_deg < req.tilt_min_deg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "ERROR", "message": "tilt_max_deg cannot be less than tilt_min_deg"},
        )
    snapshot = rig_mgr.set_limits(req.tilt_min_deg, req.tilt_max_deg)
    return {"status": "OK", "snapshot": snapshot}


@app.post("/api/rig/confirm-zero")
@app.post("/api/rig/reset-origin")
async def confirm_physical_zero():
    """Operator resets current position as origin (0, 0) and confirms zero reference."""
    if serial_mgr.is_connected:
        await serial_mgr.send_command("e")
        serial_mgr.current_pan = 0.0
        serial_mgr.current_tilt = 0.0
        await serial_mgr.send_command("S")
    ref = rig_mgr.confirm_reference()
    return {"status": "OK", "reference": ref, "motors": serial_mgr.get_status()}


# --- Motor API Endpoints ---
@app.get("/api/motors/status")
async def get_motor_status():
    if serial_mgr.is_connected:
        await serial_mgr.send_command("S")
    motor_st = serial_mgr.get_status()
    motor_st["rig"] = rig_mgr.snapshot.model_dump(mode="json")
    motor_st["reference"] = rig_mgr.reference.model_dump(mode="json")
    return motor_st


@app.post("/api/motors/reconnect")
async def reconnect_motors():
    """Attempt reconnection to physical serial port."""
    connected = await serial_mgr.reconnect()
    if not connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": f"Failed to connect to serial port '{serial_mgr.port}'"},
        )
    return {"status": "OK", "motors": serial_mgr.get_status()}


@app.post("/api/motors/move")
async def move_motors(req: MoveRequest):
    _require_serial_connected()
    if not coordinator.can_move():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "ERROR", "message": f"Operation lock busy: '{coordinator.active_mode}' active"},
        )
    rig_mgr.validate_move(
        pan=req.pan,
        tilt=req.tilt,
        relative=req.relative,
        current_pan=serial_mgr.current_pan,
        current_tilt=serial_mgr.current_tilt,
    )
    if req.relative:
        return await serial_mgr.move_relative(req.pan, req.tilt)
    return await serial_mgr.move_absolute(req.pan, req.tilt)


@app.post("/api/motors/stop")
async def stop_motors():
    # Emergency stop is always accessible regardless of reference status
    _require_serial_connected()
    await dry_run_engine.cancel()
    await timelapse_engine.cancel()
    return await serial_mgr.stop()


@app.post("/api/motors/drivers")
async def set_motor_drivers(req: DriverRequest):
    _require_serial_connected()
    if not coordinator.can_change_drivers():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "ERROR", "message": f"Operation lock busy: '{coordinator.active_mode}' active"},
        )
    res = await serial_mgr.set_drivers(req.enable)
    # Toggling motor drivers invalidates physical zero reference if command succeeded
    if isinstance(res, dict) and res.get("status") == "OK":
        rig_mgr.invalidate_reference(f"Motor drivers {'enabled' if req.enable else 'disabled'}")
    res["reference"] = rig_mgr.reference.model_dump(mode="json")
    return res


# --- Camera API Endpoints ---
@app.get("/api/camera/status")
async def get_camera_status():
    if camera_mgr.is_connected:
        await camera_mgr.refresh_config()
    return camera_mgr.get_status()


@app.get("/api/camera/config/choices")
async def get_camera_config_choices():
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "ERROR",
                "message": "Camera is disconnected. Connect real camera or set FAKE_CAMERA=true in .env",
            },
        )
    try:
        choices = await camera_mgr.get_config_choices()
        return {"status": "OK", "choices": choices}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": str(e)},
        ) from e


@app.post("/api/camera/config")
async def set_camera_config(req: CameraConfigRequest):
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )

    # Validate against supported camera choices
    try:
        choices = await camera_mgr.get_config_choices()
        valid_options = choices.get(req.param, [])
        if valid_options and req.value not in valid_options:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "status": "ERROR",
                    "message": f"Invalid {req.param} value '{req.value}'. Supported options: {valid_options}",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Could not validate choice against camera choices: {e}")

    return await camera_mgr.set_config(req.param, req.value)


@app.post("/api/camera/reconnect")
async def reconnect_camera():
    """Attempt to re-establish a persistent gphoto2 session with the camera."""
    camera_mgr.close()
    await asyncio.sleep(0.5)
    connected = await camera_mgr.initialize()
    if connected:
        await camera_mgr.apply_startup_defaults()
        return {
            "status": "OK",
            "message": f"Connected to camera '{camera_mgr.model}'",
            "model": camera_mgr.model,
            "iso": camera_mgr.iso,
            "shutter_speed": camera_mgr.shutter_speed,
            "aperture": camera_mgr.aperture,
        }
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "ERROR",
            "message": "Failed to connect to camera. Ensure camera is powered on and awake, then retry.",
        },
    )


@app.post("/api/camera/trigger")
async def trigger_camera_shot():
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    return await camera_mgr.trigger_capture()


@app.get("/api/camera/preview/latest")
async def get_latest_preview():
    if camera_mgr.latest_photo_path and os.path.exists(camera_mgr.latest_photo_path):
        media_type = "image/svg+xml" if camera_mgr.latest_photo_path.endswith(".svg") else "image/jpeg"
        return FileResponse(camera_mgr.latest_photo_path, media_type=media_type)
    raise HTTPException(status_code=404, detail="No photo captured yet")


# --- Enhanced Live View API Endpoints ---
class PreviewStartRequest(BaseModel):
    gain: float = Field(default=1.0, ge=1.0, le=4.0, description="Digital contrast/gain boost multiplier")
    plan_id: UUID | None = Field(default=None, description="Optional sequence plan ID for plan-scoped profiles")


@app.post("/api/camera/preview/start")
async def start_camera_preview(req: PreviewStartRequest | None = None):
    """Start enhanced live view streaming with exclusive camera ownership."""
    gain = req.gain if req else 1.0
    plan_id = str(req.plan_id) if req and req.plan_id else None

    preview_profile = None
    acquisition_profile = None
    if plan_id:
        plan = plan_store.get_plan(req.plan_id)
        if plan:
            preview_profile = plan.preview
            acquisition_profile = plan.acquisition

    return await preview_controller.start(
        preview_profile=preview_profile,
        acquisition_profile=acquisition_profile,
        gain=gain,
        plan_id=plan_id,
    )


@app.get("/api/camera/preview/status")
async def get_camera_preview_status():
    """Get active preview status, resolution, and FPS telemetry."""
    return preview_controller.get_status()


@app.post("/api/camera/preview/stop")
async def stop_camera_preview():
    """Stop live view stream and restore camera acquisition profile."""
    return await preview_controller.stop()


@app.get("/api/camera/preview/stream")
async def get_camera_preview_stream():
    """MJPEG HTTP stream response (multipart/x-mixed-replace) for dark-scene framing."""
    if preview_controller.state != "STREAMING":
        await preview_controller.start()

    return StreamingResponse(
        preview_controller.generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/camera/preview/frame")
async def get_camera_preview_frame():
    """Fetch single live view preview JPEG frame with low-latency headers."""
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    try:
        frame_bytes = await preview_controller._fetch_frame_bytes()
        return Response(
            content=frame_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "ERROR", "message": str(e)},
        ) from e


# --- Integrated Sequence Step Endpoint ---
@app.post("/api/sequence/step")
async def execute_sequence_step(req: SequenceStepRequest):
    _require_serial_connected()
    if not coordinator.can_move():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "ERROR", "message": f"Operation lock busy: '{coordinator.active_mode}' active"},
        )
    rig_mgr.validate_move(
        pan=req.pan,
        tilt=req.tilt,
        relative=req.relative,
        current_pan=serial_mgr.current_pan,
        current_tilt=serial_mgr.current_tilt,
    )
    logger.info(f"Executing sequence step: move (pan={req.pan}, tilt={req.tilt}), pause={req.pause_s}s")

    if req.relative:
        move_res = await serial_mgr.move_relative(req.pan, req.tilt)
    else:
        move_res = await serial_mgr.move_absolute(req.pan, req.tilt)

    if req.pause_s > 0:
        await asyncio.sleep(req.pause_s)

    capture_res = None
    if req.capture:
        if not camera_mgr.is_connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "ERROR", "message": "Camera is disconnected"},
            )
        capture_res = await camera_mgr.trigger_capture()

    motor_status = serial_mgr.get_status()
    camera_status = camera_mgr.get_status()

    return {
        "status": "OK",
        "move": move_res,
        "capture": capture_res,
        "motors": motor_status,
        "camera": camera_status,
    }


# --- Sequence Plan CRUD & Trajectory API Endpoints ---
@app.post("/api/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(plan: SequencePlan):
    """Save a new SequencePlan to persistent storage."""
    saved_plan = plan_store.save_plan(plan)
    return saved_plan


@app.get("/api/plans")
async def list_plans():
    """List summary records of all stored sequence plans."""
    plans = plan_store.list_plans()
    summaries = []
    for p in plans:
        duration = (p.schedule.total_shots - 1) * p.schedule.interval_s
        summaries.append({
            "id": p.id,
            "revision": p.revision,
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "total_shots": p.schedule.total_shots,
            "duration_s": duration,
        })
    return summaries


@app.get("/api/plans/{plan_id}")
async def get_plan(plan_id: UUID):
    """Retrieve complete SequencePlan detail by UUID."""
    plan = plan_store.get_plan(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Plan '{plan_id}' not found"},
        )
    return plan


@app.put("/api/plans/{plan_id}")
async def update_plan(plan_id: UUID, plan: SequencePlan):
    """
    Update an existing SequencePlan.
    Requires request plan.id to match URL plan_id and revision to match current stored revision.
    Returns HTTP 409 Conflict if edit revision is stale.
    """
    if plan.id != plan_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "ERROR", "message": "URL plan_id does not match body plan.id"},
        )

    existing = plan_store.get_plan(plan_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Plan '{plan_id}' not found"},
        )

    if existing.revision != plan.revision:
        msg = f"Stale revision conflict: stored revision is {existing.revision}, request is {plan.revision}"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "ERROR", "message": msg},
        )

    updated = plan_store.save_plan(plan)
    return updated


@app.delete("/api/plans/{plan_id}")
async def delete_plan(plan_id: UUID):
    """Delete SequencePlan by UUID."""
    success = plan_store.delete_plan(plan_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Plan '{plan_id}' not found"},
        )
    return {"status": "OK", "id": str(plan_id)}


@app.get("/api/plans/{plan_id}/trajectory")
async def get_plan_trajectory(plan_id: UUID):
    """Generate sampled trajectory poses, expected duration, and diagnostic metrics for a plan."""
    plan = plan_store.get_plan(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Plan '{plan_id}' not found"},
        )

    result = sample_trajectory(plan.trajectory, plan.schedule, rig_limits=rig_mgr.snapshot)
    return result


# --- Test Shots & Media Artifacts API Endpoints ---
class TestShotRequest(BaseModel):
    iso: str | None = None
    shutter_speed: str | None = None
    aperture: str | None = None


@app.post("/api/plans/{plan_id}/test-shots", status_code=status.HTTP_201_CREATED)
async def trigger_plan_test_shot(plan_id: UUID, req: TestShotRequest | None = None):
    """Trigger a single test shot using plan acquisition camera settings (or explicit overrides)."""
    if not coordinator.can_test_shot():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "ERROR", "message": f"Operation lock busy: '{coordinator.active_mode}' active"},
        )

    plan = plan_store.get_plan(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Plan '{plan_id}' not found"},
        )

    # Stop live view preview before taking test shot exposure
    if preview_controller.state != "IDLE":
        await preview_controller.stop()

    requested_settings = {
        "iso": (req.iso if req and req.iso else plan.acquisition.iso),
        "shutter_speed": (req.shutter_speed if req and req.shutter_speed else plan.acquisition.shutter_speed),
        "aperture": (req.aperture if req and req.aperture else plan.acquisition.aperture),
    }

    from media_helper import create_test_shot_artifact

    res = await create_test_shot_artifact(
        plan_id=plan_id,
        camera_mgr=camera_mgr,
        plans_base_dir=plan_store.base_dir,
        requested_settings=requested_settings,
    )

    if res.get("status") != "OK":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "ERROR", "message": res.get("message", "Test shot failed")},
        )

    return res["metadata"]


@app.get("/api/plans/{plan_id}/test-shots")
async def list_plan_test_shots(plan_id: UUID):
    """List all captured test shot metadata for a plan."""
    plan_dir = plan_store.base_dir / str(plan_id)
    test_shots_dir = plan_dir / "test-shots"
    if not test_shots_dir.exists():
        return []

    shots = []
    for entry in test_shots_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith(".tmp_"):
            meta_file = entry / "metadata.json"
            if meta_file.exists():
                try:
                    with open(meta_file, encoding="utf-8") as f:
                        meta = json.load(f)
                    shots.append(meta)
                except Exception as e:
                    logger.warning(f"Failed to parse test shot metadata at '{meta_file}': {e}")

    shots.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return shots


@app.get("/api/plans/{plan_id}/test-shots/{shot_id}")
async def get_test_shot_detail(plan_id: UUID, shot_id: UUID):
    """Retrieve metadata detail for a specific test shot."""
    meta_file = plan_store.base_dir / str(plan_id) / "test-shots" / str(shot_id) / "metadata.json"
    if not meta_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Test shot '{shot_id}' not found"},
        )
    try:
        with open(meta_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "ERROR", "message": str(e)},
        ) from e


@app.delete("/api/plans/{plan_id}/test-shots/{shot_id}")
async def delete_test_shot(plan_id: UUID, shot_id: UUID):
    """Delete a test shot and its artifacts."""
    shot_dir = (plan_store.base_dir / str(plan_id) / "test-shots" / str(shot_id)).resolve()
    if not shot_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Test shot '{shot_id}' not found"},
        )
    try:
        shutil.rmtree(shot_dir)
        return {"status": "OK", "message": f"Test shot '{shot_id}' deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "ERROR", "message": str(e)},
        ) from e


@app.get("/api/plans/{plan_id}/test-shots/{shot_id}/artifacts/{artifact_type}")
async def get_test_shot_artifact_file(plan_id: UUID, shot_id: UUID, artifact_type: str):
    """Serve an image artifact file by ID, type, or filename for a test shot."""
    shot_dir = (plan_store.base_dir / str(plan_id) / "test-shots" / str(shot_id)).resolve()
    if not shot_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Test shot '{shot_id}' not found"},
        )

    meta_file = shot_dir / "metadata.json"
    target_file = None
    media_type = "application/octet-stream"

    if meta_file.exists():
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
            for art in meta.get("artifacts", []):
                if (
                    art.get("id") == artifact_type
                    or art.get("type") == artifact_type
                    or art.get("filename") == artifact_type
                ):
                    fn = art.get("filename") or os.path.basename(art.get("relative_path", ""))
                    target_file = shot_dir / fn
                    media_type = art.get("mime_type", media_type)
                    break
        except Exception:
            pass

    if not target_file:
        if artifact_type in ("preview", "preview.jpg", "thumbnail"):
            # Fall back to original artifact if no separate preview was stored
            if meta_file.exists():
                try:
                    with open(meta_file, encoding="utf-8") as f:
                        meta = json.load(f)
                    for art in meta.get("artifacts", []):
                        if art.get("type") == "original":
                            fn = art.get("filename") or os.path.basename(art.get("relative_path", ""))
                            target_file = shot_dir / fn
                            media_type = art.get("mime_type", media_type)
                            break
                except Exception:
                    pass
        elif artifact_type == "metadata.json":
            target_file = meta_file
            media_type = "application/json"
        else:
            target_file = shot_dir / artifact_type

    if not target_file or not target_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Artifact '{artifact_type}' not found"},
        )

    return FileResponse(target_file, media_type=media_type)


# --- Dry Run Engine API Endpoints ---
@app.post("/api/plans/{plan_id}/dry-run/start")
async def start_dry_run(plan_id: UUID):
    """Start full-path motion dry run for sequence plan."""
    _require_serial_connected()
    return await dry_run_engine.start(plan_id)


@app.get("/api/plans/{plan_id}/dry-run/status")
async def get_dry_run_status(plan_id: UUID):
    """Get active dry-run progress and persisted DryRunReport with stale status."""
    return {
        "status": dry_run_engine.get_status(),
        "report": dry_run_engine.get_report(plan_id),
    }


@app.post("/api/plans/{plan_id}/dry-run/cancel")
async def cancel_dry_run(plan_id: UUID):
    """Cancel active dry-run motion sequence."""
    return await dry_run_engine.cancel()


# --- Automated Time-lapse Engine API Endpoints ---
@app.get("/api/timelapse/status")
async def get_timelapse_status():
    return timelapse_engine.get_status()


@app.post("/api/timelapse/start")
async def start_timelapse(config: TimelapseConfig):
    _require_serial_connected()
    return await timelapse_engine.start(config)


@app.post("/api/timelapse/pause")
async def pause_timelapse():
    return await timelapse_engine.pause()


@app.post("/api/timelapse/resume")
async def resume_timelapse():
    return await timelapse_engine.resume()


@app.post("/api/timelapse/cancel")
async def cancel_timelapse():
    return await timelapse_engine.cancel()


# --- Real-Time Server-Sent Events (SSE) Streaming ---
@app.get("/api/events")
async def stream_events():
    """Stream real-time motor, camera, rig, time-lapse, dry run, and coordinator state events."""

    async def event_generator():
        while True:
            payload = {
                "motors": serial_mgr.get_status(),
                "camera": camera_mgr.get_status(),
                "rig": rig_mgr.snapshot.model_dump(mode="json"),
                "reference": rig_mgr.reference.model_dump(mode="json"),
                "timelapse": timelapse_engine.get_status(),
                "dry_run": dry_run_engine.get_status(),
                "coordinator": coordinator.get_status(),
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Serve Frontend static files if directory exists
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    reload_enabled = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    if reload_enabled:
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000)
