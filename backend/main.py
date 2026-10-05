import asyncio
import json
import logging
import os
from pathlib import Path
import shutil
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import dotenv
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camera_manager import CameraManager
from coordinator import OperationCoordinator
from domain.models import SequencePlan
from domain.rig import RigManager
from domain.studio_state import AppStateManager
from domain.trajectory import sample_trajectory
from dry_run_engine import DryRunEngine
from fake_camera_manager import FakeCameraManager
from fake_serial_manager import FakeSerialManager
from media_helper import generate_resized_preview_sync
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
is_simulation = os.getenv("SIMULATION", "false").lower() == "true"
use_fake_serial = os.getenv("FAKE_SERIAL", "false").lower() == "true" or is_simulation
use_fake_camera = os.getenv("FAKE_CAMERA", "false").lower() == "true" or is_simulation

if use_fake_serial:
    logger.info("Initializing application with FakeSerialManager (SIMULATION=true)")
    serial_mgr = FakeSerialManager()
else:
    serial_mgr = SerialManager(
        port=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
        baudrate=int(os.getenv("SERIAL_BAUD", "9600")),
    )

capture_dir = os.path.join(os.path.dirname(__file__), "..", "output", "captures")
if use_fake_camera:
    logger.info("Initializing application with FakeCameraManager (SIMULATION=true)")
    camera_mgr = FakeCameraManager(capture_dir=capture_dir)
else:
    logger.info("Initializing application with real CameraManager (gphoto2)")
    camera_mgr = CameraManager(capture_dir=capture_dir)

plan_store = PlanStore()
app_state_mgr = AppStateManager()
rig_mgr = RigManager(tilt_min_deg=-80.0, tilt_max_deg=80.0)

coordinator = OperationCoordinator()
timelapse_engine = TimelapseEngine(
    serial_mgr=serial_mgr,
    camera_mgr=camera_mgr,
    rig_mgr=rig_mgr,
    coordinator=coordinator,
)
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
    await dry_run_engine.cancel()
    await timelapse_engine.cancel()
    await preview_controller.stop()
    await serial_mgr.disconnect()
    camera_mgr.close()


app = FastAPI(title="pantiltlapse-rig REST API", version="0.4.0", lifespan=lifespan)

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
    tilt_min_deg: float = Field(default=-80.0, description="Minimum allowable tilt angle in degrees")
    tilt_max_deg: float = Field(default=80.0, description="Maximum allowable tilt angle in degrees")


class CameraConfigRequest(BaseModel):
    param: str | None = Field(default=None, description="Parameter key: 'iso', 'shutter_speed', 'aperture', or 'white_balance'")
    value: str | None = Field(default=None, description="Parameter target value, e.g. '400', '1/125'")
    iso: str | None = Field(default=None, description="Batch ISO setting")
    shutter_speed: str | None = Field(default=None, description="Batch shutter speed setting")
    aperture: str | None = Field(default=None, description="Batch aperture setting")
    white_balance: str | None = Field(default=None, description="Batch white balance setting")


def _require_serial_connected():
    if not serial_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Motor controller is disconnected"},
        )


def _require_hardware_idle(action: str):
    """Reject lifecycle/reference changes while an operation owns the rig."""
    if coordinator.is_recording or coordinator.is_dry_running or serial_mgr.state in ("MOVING", "STOPPING"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "ERROR",
                "message": f"Cannot {action} while operation '{coordinator.active_mode}' is active",
            },
        )


def _require_camera_lifecycle_idle(action: str):
    if coordinator.is_recording or coordinator.is_dry_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "ERROR",
                "message": f"Cannot {action} while operation '{coordinator.active_mode}' is active",
            },
        )


def _require_camera_control_idle(action: str):
    if coordinator.is_recording or coordinator.is_dry_running or coordinator.is_maintenance:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "ERROR",
                "message": f"Cannot {action} while operation '{coordinator.active_mode}' owns the camera",
            },
        )


async def _acquire_maintenance(action: str):
    if not await coordinator.begin_maintenance(allow_preview=True):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "ERROR",
                "message": f"Cannot {action} while operation '{coordinator.active_mode}' is active",
            },
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
async def confirm_physical_zero():
    """Operator resets current position as origin (0, 0) and confirms zero reference."""
    _require_serial_connected()
    _require_hardware_idle("confirm zero")
    await _acquire_maintenance("confirm zero")
    try:
        rig_mgr.invalidate_reference("Zero confirmation reset requested")
        enable_res = await serial_mgr.send_command("e")
        if not isinstance(enable_res, dict) or enable_res.get("status") != "OK":
            raise HTTPException(
                status_code=503,
                detail={"status": "ERROR", "message": "Motor controller rejected zero confirmation reset"},
            )
        status_res = await serial_mgr.send_command("S")
        response = status_res.get("response") if isinstance(status_res, dict) else None
        try:
            status_parts = str(response).split()
            is_zero = (
                status_parts[0] == "STATUS"
                and abs(float(status_parts[1])) < 1e-6
                and abs(float(status_parts[2])) < 1e-6
            )
            drivers_on = status_parts[3] == "1"
        except (IndexError, TypeError, ValueError):
            is_zero = False
            drivers_on = False
        if not isinstance(status_res, dict) or status_res.get("status") != "OK" or not is_zero or not drivers_on:
            raise HTTPException(
                status_code=503,
                detail={"status": "ERROR", "message": "Motor controller status unavailable after zero reset"},
            )
        serial_mgr.current_pan = 0.0
        serial_mgr.current_tilt = 0.0
        serial_mgr.drivers_enabled = True
        ref = rig_mgr.confirm_reference()
        return {"status": "OK", "reference": ref, "motors": serial_mgr.get_status()}
    finally:
        await coordinator.end_maintenance()


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
    _require_hardware_idle("reconnect motors")
    await _acquire_maintenance("reconnect motors")
    try:
        rig_mgr.invalidate_reference("Motor controller reconnect requested")
        connected = await serial_mgr.reconnect()
        if not connected:
            raise HTTPException(
                status_code=503,
                detail={"status": "ERROR", "message": f"Failed to connect to serial port '{serial_mgr.port}'"},
            )
        return {"status": "OK", "motors": serial_mgr.get_status(), "reference": rig_mgr.reference}
    finally:
        await coordinator.end_maintenance()


@app.post("/api/motors/disconnect")
async def disconnect_motors():
    """Disconnect and close serial port handle to release hardware."""
    _require_hardware_idle("disconnect motors")
    await _acquire_maintenance("disconnect motors")
    try:
        rig_mgr.invalidate_reference("Motor controller disconnect requested")
        await serial_mgr.disconnect()
        return {"status": "OK", "motors": serial_mgr.get_status(), "reference": rig_mgr.reference}
    finally:
        await coordinator.end_maintenance()


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
        return {
            "status": "OK",
            "choices": choices,
            "exposure_mode": getattr(camera_mgr, "exposure_mode", "Unknown"),
            "is_manual_mode": getattr(camera_mgr, "is_manual_mode", True),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": str(e)},
        ) from e


@app.post("/api/camera/config")
async def set_camera_config(req: CameraConfigRequest):
    _require_camera_control_idle("change camera configuration")
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )

    # Collect parameters to apply
    params_to_set: dict[str, str] = {}
    if req.param and req.value is not None:
        params_to_set[req.param] = str(req.value)
    if req.iso is not None:
        params_to_set["iso"] = str(req.iso)
    if req.shutter_speed is not None:
        params_to_set["shutter_speed"] = str(req.shutter_speed)
    if req.aperture is not None:
        params_to_set["aperture"] = str(req.aperture)
    if req.white_balance is not None:
        params_to_set["white_balance"] = str(req.white_balance)

    if not params_to_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "ERROR", "message": "No configuration parameters provided to update"},
        )

    # Validate against supported camera choices
    try:
        choices = await camera_mgr.get_config_choices()
        for p_key, p_val in params_to_set.items():
            valid_options = choices.get(p_key, [])
            if valid_options and p_val not in valid_options:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "status": "ERROR",
                        "message": f"Invalid {p_key} value '{p_val}'. Supported options: {valid_options}",
                    },
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Could not validate choice against camera choices: {e}")

    last_res = {"status": "OK"}
    for p_key, p_val in params_to_set.items():
        last_res = await camera_mgr.set_config(p_key, p_val)

    return last_res


@app.post("/api/camera/restart")
@app.post("/api/camera/reconnect")
async def reconnect_camera():
    """Attempt a robust camera restart: releases preview, resets hardware USB port, and reconnects."""
    _require_camera_lifecycle_idle("reconnect camera")
    await _acquire_maintenance("reconnect camera")
    try:
        if coordinator.is_previewing:
            await preview_controller.stop()
        if hasattr(camera_mgr, "restart"):
            connected = await camera_mgr.restart()
        else:
            camera_mgr.close()
            await asyncio.sleep(0.5)
            connected = await camera_mgr.initialize()
            if connected:
                await camera_mgr.apply_startup_defaults()
    finally:
        await coordinator.end_maintenance()

    if connected:
        try:
            choices = await camera_mgr.get_config_choices()
        except Exception:
            choices = {}

        mode_str = getattr(camera_mgr, "exposure_mode", "Unknown")
        is_m = getattr(camera_mgr, "is_manual_mode", True)
        msg = f"Connected to camera '{camera_mgr.model}' [Mode: {mode_str}]"
        if not is_m:
            msg += (
                " - Warning: Camera dial is NOT in 'M' (Manual). "
                "Exposure settings will be locked by camera hardware."
            )

        return {
            "status": "OK",
            "message": msg,
            "model": camera_mgr.model,
            "exposure_mode": mode_str,
            "is_manual_mode": is_m,
            "iso": camera_mgr.iso,
            "shutter_speed": camera_mgr.shutter_speed,
            "aperture": camera_mgr.aperture,
            "choices": choices,
        }

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "ERROR",
            "message": (
                "Failed to connect to camera. Ensure camera is powered on, awake, "
                "and dial is set to 'M' (Manual)."
            ),
        },
    )


@app.post("/api/camera/disconnect")
async def disconnect_camera():
    """Disconnect and close persistent camera session to release USB handle."""
    _require_camera_lifecycle_idle("disconnect camera")
    await _acquire_maintenance("disconnect camera")
    try:
        if coordinator.is_previewing:
            await preview_controller.stop()
        camera_mgr.close()
    finally:
        await coordinator.end_maintenance()
    return {"status": "OK", "camera": camera_mgr.get_status()}


@app.post("/api/camera/trigger")
async def trigger_camera_shot():
    _require_camera_control_idle("trigger camera")
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    return await camera_mgr.trigger_capture()


@app.get("/api/camera/preview/latest")
async def get_latest_preview(
    quality: str = Query("low", description="Preview quality tier: 'low', 'balanced', or 'full'"),
    tier: str | None = Query(None, description="Alias for quality tier: 'low', 'balanced', or 'full'"),
):
    """
    Serve latest snapshot image in one of 3 tiers:
    - 'low' (default): 1024px compressed JPEG (~50-80KB) for fast loading over Wi-Fi.
    - 'balanced': 1920px Full HD JPEG (~250-400KB) for crisp composition inspection.
    - 'full': Original uncompressed native resolution (RAW/full-res JPEG) for star pinpoints and Focus Loupe.
    """
    selected_tier = (tier or quality or "low").strip().lower()
    if selected_tier in ("fast", "draft"):
        selected_tier = "low"
    elif selected_tier in ("medium", "standard"):
        selected_tier = "balanced"
    elif selected_tier in ("native", "original", "high"):
        selected_tier = "full"

    if not camera_mgr.latest_photo_path or not os.path.exists(camera_mgr.latest_photo_path):
        raise HTTPException(status_code=404, detail="No photo captured yet")

    orig_path = Path(camera_mgr.latest_photo_path)
    if orig_path.suffix.lower() == ".svg" or selected_tier == "full":
        media_type = "image/svg+xml" if orig_path.suffix.lower() == ".svg" else "image/jpeg"
        return FileResponse(orig_path, media_type=media_type)

    cache_dir = orig_path.parent / ".previews"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if selected_tier == "low":
        target_preview = cache_dir / f"{orig_path.stem}_low.jpg"
        if not target_preview.exists() or target_preview.stat().st_mtime < orig_path.stat().st_mtime:
            ok = await asyncio.to_thread(generate_resized_preview_sync, orig_path, target_preview, 1024, 70)
            if not ok or not target_preview.exists():
                return FileResponse(orig_path, media_type="image/jpeg")
        return FileResponse(target_preview, media_type="image/jpeg")

    elif selected_tier == "balanced":
        target_preview = cache_dir / f"{orig_path.stem}_balanced.jpg"
        if not target_preview.exists() or target_preview.stat().st_mtime < orig_path.stat().st_mtime:
            ok = await asyncio.to_thread(generate_resized_preview_sync, orig_path, target_preview, 1920, 80)
            if not ok or not target_preview.exists():
                return FileResponse(orig_path, media_type="image/jpeg")
        return FileResponse(target_preview, media_type="image/jpeg")

    return FileResponse(orig_path, media_type="image/jpeg")


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


# --- Manual Focus & Autofocus Endpoints ---
class FocusStepRequest(BaseModel):
    direction: str = Field(..., description="Focus direction: 'near' or 'far'")
    step_size: int = Field(1, ge=1, le=3, description="Focus step size: 1 (fine), 2 (medium), 3 (coarse)")


@app.post("/api/camera/focus/step")
async def step_camera_focus(req: FocusStepRequest):
    """Drive camera manual focus near or far in discrete steps."""
    _require_camera_control_idle("change camera focus")
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    res = await camera_mgr.step_focus(direction=req.direction, step_size=req.step_size)
    if res.get("status") != "OK":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "ERROR", "message": res.get("message", "Focus step failed")},
        )
    return res


@app.post("/api/camera/focus/autofocus")
async def trigger_camera_autofocus():
    """Trigger camera autofocus lock."""
    _require_camera_control_idle("trigger camera autofocus")
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    res = await camera_mgr.trigger_autofocus()
    if res.get("status") != "OK":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "ERROR", "message": res.get("message", "Autofocus failed")},
        )
    return res


# --- Debug Camera Interface & Widget Diagnostics ---
@app.get("/debug/camera")
async def get_debug_camera_page():
    """Serve standalone camera debug and gphoto2 diagnostic control interface."""
    debug_html = os.path.join(os.path.dirname(__file__), "..", "frontend", "debug_camera.html")
    if os.path.exists(debug_html):
        return FileResponse(debug_html, media_type="text/html")
    raise HTTPException(status_code=404, detail="Debug camera page not found")


@app.get("/api/debug/camera/widgets")
async def get_camera_widgets():
    """Retrieve full configuration widget tree and choice options from connected camera."""
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    widgets = await camera_mgr.get_all_widgets()
    return {"status": "OK", "count": len(widgets), "widgets": widgets}


class RawWidgetSetRequest(BaseModel):
    widget_name: str = Field(..., description="Exact gphoto2 widget name, e.g. manualfocusdrive, iso, shutterspeed")
    value: Any = Field(..., description="Raw value to set")


@app.post("/api/debug/camera/set-raw-widget")
async def set_camera_raw_widget(req: RawWidgetSetRequest):
    """Set a raw camera configuration widget directly and return detailed gphoto2 response."""
    _require_camera_control_idle("change camera configuration")
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    res = await camera_mgr.set_raw_widget(req.widget_name, req.value)
    if res.get("status") != "OK":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "ERROR", "message": res.get("message", "Widget set failed"), "widget": req.widget_name},
        )
    return res


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
    white_balance: str | None = None


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
        "white_balance": (req.white_balance if req and req.white_balance else getattr(plan.acquisition, "white_balance", "Auto")),
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


@app.api_route(
    "/api/plans/{plan_id}/test-shots/{shot_id}/artifacts/{artifact_type}",
    methods=["GET", "HEAD"],
)
async def get_test_shot_artifact_file(
    plan_id: UUID,
    shot_id: UUID,
    artifact_type: str,
    quality: str | None = None,
):
    """Serve an image artifact file by ID, type, or filename for a test shot, supporting on-demand quality downscaling."""
    shot_dir = (plan_store.base_dir / str(plan_id) / "test-shots" / str(shot_id)).resolve()
    if not shot_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "ERROR", "message": f"Test shot '{shot_id}' not found"},
        )

    meta_file = shot_dir / "metadata.json"
    target_file = None
    media_type = "application/octet-stream"

    # Locate original file in shot_dir as reference source
    orig_path = shot_dir / "original.jpg"
    if not orig_path.exists():
        for p in shot_dir.glob("original.*"):
            orig_path = p
            break

    # Handle quality-specific preview requests
    if artifact_type in ("preview", "preview.jpg", "preview.jpeg", "thumbnail"):
        if quality in ("fast", "low"):
            cached_fast = shot_dir / "preview_fast.jpg"
            if cached_fast.exists():
                target_file = cached_fast
                media_type = "image/jpeg"
            elif orig_path.exists() and orig_path.suffix.lower() in (".jpg", ".jpeg"):
                ok = await asyncio.to_thread(generate_resized_preview_sync, orig_path, cached_fast, 1024, 75)
                if ok and cached_fast.exists():
                    target_file = cached_fast
                    media_type = "image/jpeg"
            elif orig_path.exists() and orig_path.suffix.lower() == ".svg":
                target_file = orig_path
                media_type = "image/svg+xml"

        elif quality in ("medium", "balanced"):
            cached_med = shot_dir / "preview_medium.jpg"
            if cached_med.exists():
                target_file = cached_med
                media_type = "image/jpeg"
            elif orig_path.exists() and orig_path.suffix.lower() in (".jpg", ".jpeg"):
                ok = await asyncio.to_thread(generate_resized_preview_sync, orig_path, cached_med, 1920, 82)
                if ok and cached_med.exists():
                    target_file = cached_med
                    media_type = "image/jpeg"
            elif orig_path.exists() and orig_path.suffix.lower() == ".svg":
                target_file = orig_path
                media_type = "image/svg+xml"

        elif quality in ("full", "native", "original"):
            if orig_path.exists():
                target_file = orig_path
                media_type = "image/jpeg" if orig_path.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream"

    if not target_file and meta_file.exists():
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


class TimelapseAdjustRequest(BaseModel):
    poses: list[dict[str, float]] | None = Field(default=None, description="Updated full trajectory poses")
    camera_settings: list[dict[str, str]] | None = Field(default=None, description="Updated full camera settings")


@app.patch("/api/timelapse/adjust")
async def adjust_timelapse(req: TimelapseAdjustRequest):
    """Hot-update future trajectory poses and/or camera settings during an active run."""
    res = await timelapse_engine.adjust_active_run(
        poses=req.poses,
        camera_settings=req.camera_settings,
    )
    if res.get("status") != "OK":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res,
        )
    return res


@app.get("/api/timelapse/captures")
async def get_timelapse_captures():
    """Return ordered list of captured photos for the active or latest time-lapse run."""
    return timelapse_engine.get_captures()


@app.get("/api/timelapse/captures/{filename}")
async def get_timelapse_capture_file(filename: str):
    """Serve a captured time-lapse image file."""
    if not timelapse_engine.capture_dir:
        raise HTTPException(status_code=404, detail="No active or recent time-lapse capture directory")
    capture_dir_path = Path(timelapse_engine.capture_dir).resolve()
    file_path = (capture_dir_path / filename).resolve()
    if not str(file_path).startswith(str(capture_dir_path)):
        raise HTTPException(status_code=403, detail="Forbidden file path")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Capture file '{filename}' not found")
    media_type = "image/svg+xml" if filename.endswith(".svg") else "image/jpeg"
    return FileResponse(str(file_path), media_type=media_type)


# --- Studio UI State & Reload Rehydration Endpoints ---
class StudioStateUpdateRequest(BaseModel):
    active_plan_id: UUID | None = None
    active_step: int | None = Field(default=None, ge=1, le=5)
    jog_step_deg: float | None = None
    filter_settings: dict[str, Any] | None = None
    active_track_tab: str | None = None
    curve_filter: str | None = None


@app.get("/api/app/state")
async def get_app_state():
    """Return current studio UI session state for rehydration."""
    return app_state_mgr.state.model_dump(mode="json")


@app.post("/api/app/state")
async def update_app_state(req: StudioStateUpdateRequest):
    """Update studio UI session state across reloads."""
    updates = req.model_dump(exclude_unset=True)
    updated = app_state_mgr.update(**updates)
    return updated.model_dump(mode="json")


# --- Real-Time Server-Sent Events (SSE) Streaming ---
@app.get("/api/events")
async def stream_events():
    """Stream real-time motor, camera, rig, time-lapse, dry run, coordinator, and studio app state events."""

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
                "app_state": app_state_mgr.state.model_dump(mode="json"),
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
