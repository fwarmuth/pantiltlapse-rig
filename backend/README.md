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

See [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md) and [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for full specifications.
