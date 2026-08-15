# CameraCommander Architecture

```
Browser (5-Step Wizard UI) ── REST + SSE ──> FastAPI backend ── Async Serial (9600 baud) ──> ESP32/NodeMCU ──> Pan/Tilt Stepper Drivers
                                                    └── USB PTP / python-gphoto2 ──> Canon DSLR (or FakeCameraManager)
```

The backend serves `frontend/` at `/` and provides a unified REST + Server-Sent Events (SSE) API at `/api`.

## System Components

| Module | Role |
|---|---|
| `main.py` | FastAPI lifecycle, REST API routes, SSE streaming, static frontend mount |
| `serial_manager.py` | Asynchronous serial I/O communicating with firmware over ASCII protocol |
| `camera_manager.py` | Persistent gphoto2 session, camera configuration, shutter release, live view frames |
| `fake_camera_manager.py` | Explicit simulation camera (`FAKE_CAMERA=true`) for testing without camera hardware |
| `coordinator.py` | Operation locking and concurrency matrix (PREVIEW, DRY_RUN, RECORDING) |
| `domain/rig.py` | Rig safety bounds (tilt min/max) and operator coordinate reference management |
| `domain/trajectory.py` | Smooth cubic Hermite / linear interpolation trajectory generation |
| `domain/models.py` | Pydantic v2 schemas for SequencePlan, Trajectory, Keyframes, Profiles, and Run data |
| `dry_run_engine.py` | Motion rehearsal engine without shutter release |
| `timelapse_engine.py` | Time-lapse sequence executor (move → settle → capture → repeat) |
| `preview_controller.py`| Live view streaming controller with profile management and MJPEG stream |
| `storage.py` | Persistent JSON storage for SequencePlan records in `output/plans/` |
| `firmware/src/main.cpp`| ESP32/NodeMCU AccelStepper motor controller; ASCII command interface |

## Hardware & Simulation Boundaries

- **Motors / Serial**: Production motor control uses only the real serial path (`SERIAL_PORT`, `SERIAL_BAUD`). There are no inline motor mocks or silent fallbacks.
- **Camera**: Controlled via real gphoto2 (`CameraManager`) or explicitly simulated via `FakeCameraManager` when `FAKE_CAMERA=true` in `.env`. Failed real camera initialization does NOT silently fall back to fake camera.

## Frontend 5-Step Workflow

The web interface is structured as a clear, step-by-step wizard to guide the user from rig setup through capture execution:

1. **Step 1: Setup & Framing (Raw Movement & Framing)**
   - Manual jog movement (D-pad / increments), zero/origin reference confirmation, motor driver enable/disable.
   - Live framing preview with auto framing settings and client-side image processing (CLAHE / contrast / brightness boost) for framing in dark scenery.
2. **Step 2: Sequence Definition**
   - Create or select a sequence plan with name and optional description.
3. **Step 3: Key Poses & Trajectory**
   - Define waypoints (Start, End, and intermediate key poses) using current rig position or numerical entry.
   - Test and simulate movement (play/stop dry run, trajectory curve visualizer).
4. **Step 4: Acquisition Settings**
   - Camera capture parameters (ISO, shutter speed, aperture, format).
   - Schedule parameters (total shots, interval, settle pause) and test shot capture with metadata verification.
5. **Step 5: Final Review & Live Progress**
   - Summary checklist of sequence plan and rig status.
   - Sequence execution with real-time telemetry (progress %, shot index, elapsed/ETA).
   - Live review of captured images, pause/resume, cancel, and emergency stop.

## Running Locally

```bash
# Backend
cd backend
uv sync
uv run python main.py

# Firmware (PlatformIO)
cd firmware
pio run
```
