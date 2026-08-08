import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camera_manager import CameraManager
from domain.models import SequencePlan
from domain.trajectory import sample_trajectory
from fake_camera_manager import FakeCameraManager
from serial_manager import SerialManager
from storage import PlanStore
from timelapse_engine import TimelapseConfig, TimelapseEngine

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CameraCommander Backend starting up...")
    await serial_mgr.connect()
    await camera_mgr.initialize()
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


# Pydantic Schemas
class MoveRequest(BaseModel):
    pan: float = Field(default=0.0, description="Target Pan angle in degrees (or relative delta)")
    tilt: float = Field(default=0.0, description="Target Tilt angle in degrees (or relative delta)")
    relative: bool = Field(default=True, description="If True, move relative to current position. Otherwise absolute.")


class DriverRequest(BaseModel):
    enable: bool = Field(default=True, description="Enable (True) or Disable (False) stepper motor drivers")


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


# --- Motor API Endpoints ---
@app.get("/api/motors/status")
async def get_motor_status():
    if serial_mgr.is_connected:
        await serial_mgr.send_command("S")
    return serial_mgr.get_status()


@app.post("/api/motors/move")
async def move_motors(req: MoveRequest):
    _require_serial_connected()
    if req.relative:
        return await serial_mgr.move_relative(req.pan, req.tilt)
    return await serial_mgr.move_absolute(req.pan, req.tilt)


@app.post("/api/motors/stop")
async def stop_motors():
    _require_serial_connected()
    await timelapse_engine.cancel()
    return await serial_mgr.stop()


@app.post("/api/motors/drivers")
async def set_motor_drivers(req: DriverRequest):
    _require_serial_connected()
    return await serial_mgr.set_drivers(req.enable)


# --- Camera API Endpoints ---
@app.get("/api/camera/status")
async def get_camera_status():
    if camera_mgr.is_connected:
        await camera_mgr.refresh_config()
    return camera_mgr.get_status()


@app.post("/api/camera/config")
async def set_camera_config(req: CameraConfigRequest):
    if not camera_mgr.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "ERROR", "message": "Camera is disconnected"},
        )
    return await camera_mgr.set_config(req.param, req.value)


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


# --- Integrated Sequence Step Endpoint ---
@app.post("/api/sequence/step")
async def execute_sequence_step(req: SequenceStepRequest):
    _require_serial_connected()
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

    result = sample_trajectory(plan.trajectory, plan.schedule)
    return result


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
    """Stream real-time motor, camera, and time-lapse state events to frontend clients."""

    async def event_generator():
        while True:
            payload = {
                "motors": serial_mgr.get_status(),
                "camera": camera_mgr.get_status(),
                "timelapse": timelapse_engine.get_status(),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Serve Frontend static files if directory exists
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
