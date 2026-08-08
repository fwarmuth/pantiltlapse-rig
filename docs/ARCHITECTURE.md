# CameraCommander Architecture

```
Browser ── REST + SSE ──> FastAPI backend ── 9600-baud serial ──> NodeMCU v3 ──> pan/tilt drivers
                                  └── USB PTP / python-gphoto2 ──> Canon DSLR
```

The backend serves `frontend/` at `/`; the frontend uses `GET /api/events` and falls back to one-second polling of the three status routes.

| Module | Role |
|---|---|
| `main.py` | FastAPI lifecycle/routes, SSE, frontend mount |
| `serial_manager.py` | Locked async serial I/O, telemetry, mock motor |
| `camera_manager.py` | Persistent gphoto2 session, capture/configuration, mock camera |
| `timelapse_engine.py` | Background move → settle → optional capture sequence |
| `cli.py` | Direct serial console |
| `firmware/src/main.cpp` | NodeMCU/AccelStepper motor controller; `M` replies after move + 50 ms settle |

`MOCK_MODE=true` is the default; failed real serial/camera initialization also falls back to mock mode. `SERIAL_PORT` defaults to `/dev/ttyUSB0`, `SERIAL_BAUD` to `9600`; captures go to `output/captures/`.

Firmware coordinates are an operator-established zero: there is no homing, persistence, or travel limits, and driver enable/disable resets both axes to zero.

```bash
cd backend && uv sync && uv run python main.py
```

Open `http://localhost:8000` (UI) or `/docs` (API). Source directories: `backend/`, `firmware/`, `frontend/`, and `docs/`.
