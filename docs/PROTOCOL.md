# Protocol Specification (Extracted from Firmware v1.0.1)

## 1. Physical Serial Communication (Pi Zero 2 W <-> ESP/NodeMCU)

- **Baud Rate**: `9600`
- **Line Ending**: `\n` (ASCII command per line)

### ASCII Serial Command Reference

| Command | Arguments | Example | Response | Description |
|---|---|---|---|---|
| `V` | None | `V\n` | `VERSION 1.0.1` | Query firmware version |
| `M` | `<pan_deg> <tilt_deg>` | `M 15.5 -10.0\n` | `DONE` | Move both axes to absolute degrees (blocks until move completes) |
| `S` | None | `S\n` | `STATUS 15.500 -10.000 1` | Report current pan/tilt angles and driver enable state (`1` or `0`) |
| `1`,`2`,`4`,`8`,`6` | None | `6\n` | `OK MICROSTEP 16` | Set microstep resolution (`6` = 16 microsteps) |
| `X` | None | `X\n` | `OK STOP` | Emergency stop both axes |
| `d` / `D` | None | `d\n` | `OK DRIVERS OFF` | Disable stepper motor drivers |
| `e` / `E` | None | `e\n` | `OK DRIVERS ON` | Enable stepper motor drivers |
| `+` / `-` | None | `+\n` | `OK SPEED` | Increase (`+`) or decrease (`-`) common output speed by 10% |

---

## 2. Backend REST API Endpoints (Raspberry Pi <-> Web / Mobile UI)

### Motor Controls
- `GET /api/motors/status` -> Returns `{ "connected": true, "pan": 15.5, "tilt": -10.0, "drivers_enabled": true, "state": "IDLE" }`
- `POST /api/motors/move` -> Request motor move (body: `{ "pan": 15.5, "tilt": -10.0, "relative": false }`)
- `POST /api/motors/stop` -> Emergency stop (`X` command)
- `POST /api/motors/drivers` -> Enable/disable drivers (body: `{ "enable": true }`)
