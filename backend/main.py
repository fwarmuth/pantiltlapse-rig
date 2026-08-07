import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camera_manager import CameraManager
from serial_manager import SerialManager
from timelapse_engine import TimelapseConfig, TimelapseEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CameraCommander.Backend")

# Hardware & Engine Managers
serial_mgr = SerialManager(
    port=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
    baudrate=int(os.getenv("SERIAL_BAUD", "9600")),
    mock=os.getenv("MOCK_MODE", "true").lower() == "true",
)

camera_mgr = CameraManager(
    mock=os.getenv("MOCK_MODE", "true").lower() == "true",
    capture_dir=os.path.join(os.path.dirname(__file__), "..", "output", "captures"),
)

timelapse_engine = TimelapseEngine(serial_mgr=serial_mgr, camera_mgr=camera_mgr)


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


# --- Motor API Endpoints ---
@app.get("/api/motors/status")
async def get_motor_status():
    if not serial_mgr.mock and serial_mgr.is_connected:
        await serial_mgr.send_command("S")
    return serial_mgr.get_status()


@app.post("/api/motors/move")
async def move_motors(req: MoveRequest):
    if req.relative:
        return await serial_mgr.move_relative(req.pan, req.tilt)
    return await serial_mgr.move_absolute(req.pan, req.tilt)


@app.post("/api/motors/stop")
async def stop_motors():
    await timelapse_engine.cancel()
    return await serial_mgr.stop()


@app.post("/api/motors/drivers")
async def set_motor_drivers(req: DriverRequest):
    return await serial_mgr.set_drivers(req.enable)


# --- Camera API Endpoints ---
@app.get("/api/camera/status")
async def get_camera_status():
    if not camera_mgr.mock and camera_mgr.is_connected:
        await camera_mgr.refresh_config()
    return camera_mgr.get_status()


@app.post("/api/camera/config")
async def set_camera_config(req: CameraConfigRequest):
    return await camera_mgr.set_config(req.param, req.value)


@app.post("/api/camera/trigger")
async def trigger_camera_shot():
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
    logger.info(f"Executing sequence step: move (pan={req.pan}, tilt={req.tilt}), pause={req.pause_s}s")

    if req.relative:
        move_res = await serial_mgr.move_relative(req.pan, req.tilt)
    else:
        move_res = await serial_mgr.move_absolute(req.pan, req.tilt)

    if req.pause_s > 0:
        await asyncio.sleep(req.pause_s)

    capture_res = None
    if req.capture:
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


# --- Automated Time-lapse Engine API Endpoints ---
@app.get("/api/timelapse/status")
async def get_timelapse_status():
    return timelapse_engine.get_status()


@app.post("/api/timelapse/start")
async def start_timelapse(config: TimelapseConfig):
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
