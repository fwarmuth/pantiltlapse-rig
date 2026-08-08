# CameraCommander Backend

FastAPI service for the two-axis head, Canon DSLR, and time-lapses. It serves `../frontend` at `/` and the API at `/api`.

## Run it

```bash
uv sync
uv run python main.py
```

Open `http://localhost:8000` (UI) or `/docs` (interactive API).

## Hardware and mock mode

`MOCK_MODE=true` is the default. `MOCK_MODE=false` attempts hardware, then falls back to mock mode if serial or camera initialization fails.

```bash
SERIAL_PORT=/dev/ttyUSB0 SERIAL_BAUD=9600 MOCK_MODE=false uv run python main.py
```

Serial defaults: `/dev/ttyUSB0`, 9600 baud. The camera uses persistent `python-gphoto2`; captures go to `../output/captures/`.

See [`../docs/PROTOCOL.md`](../docs/PROTOCOL.md) for the complete request and response reference.
