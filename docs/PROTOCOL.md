# CameraCommander Protocol Reference

Firmware v1.0.4 uses newline-terminated ASCII at 9600 baud. `M` targets are absolute degrees; pan `+` is right. All positions use the current zero reference.

| Command | Response | Action |
|---|---|---|
| `V` / `v` | `VERSION 1.0.4` | Version |
| `M <pan> <tilt>` | `DONE` | Absolute dual-axis move |
| `S` / `s` | `STATUS <pan> <tilt> <0|1>` | Position and driver state |
| `1`/`2`/`4`/`8`/`6` | `OK MICROSTEP <n>` | Set both axes to 1/2/4/8/16 (`6` = 16) microsteps |
| `n` / `c` / `r` / `x` | `OK ROT STEP/REV/DIR/STOP` | Pan step / output revolution / direction toggle / stop |
| `w` / `p` / `t` / `z` | `OK TILT STEP/REV/DIR/STOP` | Tilt step / output revolution / direction toggle / stop |
| `X` | `OK STOP` | Stop both axes |
| `+` / `-` | `OK SPEED` | Multiply speed and acceleration by 1.15 / 0.85 |
| `d`/`D` / `e`/`E` | `OK DRIVERS OFF/ON` | Disable / enable both drivers; resets coordinates to zero |
| other | `ERR Unknown` | Reject command |

`M` blocks the firmware command loop, so `X` is processed only after an active move returns; it is not a hardware-interrupt emergency stop.

## HTTP API

All routes return JSON except preview and SSE. Full schemas: `/docs`.

| Route | Body / result |
|---|---|
| `GET /api/motors/status` | `{connected,mock_mode,port,baudrate,state,drivers_enabled,pan,tilt}`; hardware refreshes `S`. |
| `POST /api/motors/move` | `{pan,tilt,relative:true}`; relative defaults to true, false is absolute. |
| `POST /api/motors/stop` | Cancels time-lapse, sends `X`. |
| `POST /api/motors/drivers` | `{enable:boolean}`. |
| `GET /api/camera/status` | Connection/mock/model/exposure/latest-capture metadata. |
| `POST /api/camera/config` | `{param,value}`; `param`: `iso`, `shutter_speed`, or `aperture`. |
| `POST /api/camera/trigger` | Capture/download to `output/captures/`; response has `status`, `filename`, `path`, `timestamp` (`mock:true` in mock mode). |
| `GET /api/camera/preview/latest` | Latest file; 404 before a capture. |
| `POST /api/sequence/step` | `{pan,tilt,relative:true,pause_s:0.5,capture:true}`; returns move, capture, motor and camera states. |
| `GET /api/timelapse/status` | State, progress, elapsed/ETA, error, and configuration. |
| `POST /api/timelapse/start` | Configuration below; rejects when running/paused. |
| `POST /api/timelapse/pause` / `resume` / `cancel` | Control a background sequence. |
| `GET /api/events` | SSE every second: `{motors,camera,timelapse}`. |

Time-lapse configuration:

```json
{"start_pan":0,"start_tilt":0,"end_pan":15,"end_tilt":0,"total_shots":10,"interval_s":5,"settle_time_s":0.5,"capture_photo":true,"easing":"ease_in_out"}
```

`total_shots >= 2`; `interval_s >= 1`; easing is `linear`, `ease_in_out`, or `s_curve` (other values use linear). Each shot moves, settles, optionally captures, then waits out its interval. States: `IDLE`, `RUNNING`, `PAUSED`, `COMPLETED`, `CANCELLED`, `ERROR`. The UI polls status every second if SSE is unavailable.
