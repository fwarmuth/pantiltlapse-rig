# CameraCommander Architecture & Monorepo Overview

## System Overview
CameraCommander is an automated, motion-controlled time-lapse system for Canon DSLR cameras mounted on a 2-axis (Pan/Tilt) 3D-printed motorized head.

```
+-------------------------------------------------------+
|                Browser / Mobile Client                |
|           (Lightweight HTML5 / JS Web UI)            |
+---------------------------+---------------------------+
                            | REST / SSE / WebSockets
                            v
+-------------------------------------------------------+
|             Raspberry Pi Zero 2 W (Brain)             |
|                                                       |
|  +--------------------+    +-----------------------+  |
|  |   FastAPI / Async  |    | Camera Controller     |  |
|  |   (Managed by uv)  |<-->| (gphoto2 / USB / GPIO)|  |
|  |   REST API Server  |    |                       |  |
|  +---------+----------+    +-----------------------+  |
|            |                                          |
|            v Async Serial Manager                     |
+------------+------------------------------------------+
             | UART / USB Serial (`/dev/ttyUSB0` or `ttyS0`)
             v
+-------------------------------------------------------+
|                 ESP32 Motor Controller                |
|  - Pan Stepper Motor Driver (X Axis)                  |
|  - Tilt Stepper Motor Driver (Y Axis)                 |
|  - Endstops / Homing logic (optional)                 |
+-------------------------------------------------------+
```

## Directory Structure
```
CameraCommander3/
├── docs/                      # LLM-focused architecture, hardware & protocol docs
│   ├── ARCHITECTURE.md        # System design, component roles, thread/async model
│   ├── HARDWARE.md            # Hardware wiring, steppers, ESP32 pins, camera trigger
│   ├── PROTOCOL.md            # Serial protocol (Pi <-> ESP32) & REST API specs
│   └── ROADMAP.md             # Step-by-step progress tracking & testing steps
├── firmware/                  # ESP32 firmware source code (PlatformIO / Arduino)
├── backend/                   # Python FastAPI event-driven backend service
└── frontend/                  # Modern lightweight web UI
```

## Principles for Agentic AI Development
1. **Source of Truth in Docs**: All hardware pinouts, serial command formats, and API schemas are documented in `docs/` so any AI agent can understand the context instantly.
2. **Modular Decoupling**: Backend (REST API + Serial Worker) is decoupled from Frontend, allowing direct API testing and future mobile app integration.
3. **Hardware Isolation**: Serial commands and camera shutter triggers use abstraction interfaces, allowing mock/dry-run testing without physical hardware connected.
4. **Step-by-Step Verification**: Every feature milestone must be testable via web UI or CLI before proceeding to the next phase.
