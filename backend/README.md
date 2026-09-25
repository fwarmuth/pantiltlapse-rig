# pantiltlapse-rig Backend

FastAPI service for the two-axis head, Canon DSLR, and time-lapse sequences. It serves `../frontend` at `/` and the REST/SSE API at `/api`.

## Running the Backend

```bash
cd backend
uv sync
uv run python main.py
```

Open `http://localhost:8000` (UI) or `/docs` (interactive API).

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `SERIAL_PORT` | `/dev/ttyUSB0` | Serial port connected to ESP32/NodeMCU motor controller |
| `SERIAL_BAUD` | `9600` | Baud rate for serial communication |
| `FAKE_CAMERA` | `false` | When `true`, uses `FakeCameraManager` to simulate camera captures without physical DSLR |
| `UVICORN_RELOAD`| `false` | Enable automatic reloading during backend development |

Captures and plan files are stored in `../output/`.

Each recording gets a unique `run_id` and writes to `../output/captures/timelapse_<run_id>/`, so starting another sequence preserves previous captures. The start response includes `run_id`; status also includes `capture_dir`.

Motor reconnection can reset the controller's coordinates. After a connection change or failed recording move, confirm the physical zero again before starting planned motion. A recording does not automatically resume absolute movement after reconnecting the controller.

Camera reconnect/disconnect stops live preview first. Hardware lifecycle changes and zero resets are rejected while a recording or rehearsal owns the rig.

Cancelling a recording stops motor motion before waiting for an in-flight camera capture to finish. The camera remains reserved during that cleanup; a long exposure can therefore delay the cancellation response.

See [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md) and [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for full specifications.
