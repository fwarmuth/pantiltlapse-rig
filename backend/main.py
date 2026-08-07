import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from serial_manager import SerialManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CameraCommander.Backend")

# Global serial manager instance matching extracted 9600 baud protocol
serial_mgr = SerialManager(
    port=os.getenv("SERIAL_PORT", "/dev/ttyUSB0"),
    baudrate=int(os.getenv("SERIAL_BAUD", "9600")),
    mock=os.getenv("MOCK_MODE", "true").lower() == "true",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CameraCommander Backend starting up...")
    await serial_mgr.connect()
    yield
    logger.info("CameraCommander Backend shutting down...")


app = FastAPI(title="CameraCommander REST API", version="0.1.0", lifespan=lifespan)

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


# API Endpoints
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
    return await serial_mgr.stop()


@app.post("/api/motors/drivers")
async def set_motor_drivers(req: DriverRequest):
    return await serial_mgr.set_drivers(req.enable)


# Serve Frontend static files if directory exists
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
