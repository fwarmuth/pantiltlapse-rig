# pantiltlapse-rig Protocol Reference

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

All routes return JSON except preview MJPEG stream and SSE. Full schemas: `/docs`.

| Route | Body / result |
|---|---|
| `GET /api/motors/status` | `{connected,port,baudrate,state,drivers_enabled,pan,tilt,rig,reference}`; hardware refreshes `S`. |
| `POST /api/motors/move` | `{pan,tilt,relative:true}`; guarded by coordinator (`can_move()`). Returns 409 if active dry run/recording. |
| `POST /api/motors/stop` | Cancels dry run and time-lapse, sends `X`. |
| `POST /api/motors/drivers` | `{enable:boolean}`. Toggling invalidates coordinate reference if command succeeds. |
| `POST /api/rig/limits` | `{tilt_min_deg,tilt_max_deg}`. Persisted to `output/rig.json`. Invalidates dry-run report staleness. |
| `POST /api/rig/confirm-zero` | Operator confirms zero reference position. |
| `GET /api/camera/status` | Connection status, camera type (`gphoto2` or `fake`), model, and current exposure configuration. |
| `POST /api/camera/config` | `{param,value}`; `param`: `iso`, `shutter_speed`, or `aperture`. Validated against camera choices. |
| `POST /api/camera/trigger` | Shutter release capture preserving camera extension. |
| `POST /api/camera/preview/start` | `{gain:1.0..4.0, plan_id:UUID|null}`. Starts MJPEG live view stream with plan acquisition/preview profiles. |
| `GET /api/camera/preview/stream` | MJPEG HTTP stream response (`multipart/x-mixed-replace`). |
| `POST /api/plans/{id}/dry-run/start` | Motion-only rehearsal. Inspects all motor responses and generates `DryRunReport`. |
| `GET /api/plans/{id}/test-shots` | List plan test-shot metadata with SHA256, byte sizes, EXIF, and artifact files. |
| `GET /api/events` | SSE every second: `{motors,camera,rig,reference,timelapse,dry_run,coordinator}`. |

## Operation Concurrency Matrix

- **PREVIEW** and **DRY_RUN** can run concurrently **only if** both operate on the same plan ID.
- **RECORDING** requires exclusive execution.
- Manual move, driver toggle, limit updates, and test shots are rejected with `409 Conflict` during active dry-run or recording sequences.
