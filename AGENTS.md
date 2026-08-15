# AGENTS.md - Project Guidelines for AI Agents

> **Scope**: Root workspace guidelines for `pantiltlapse-rig`
> **Tools Supported**: Antigravity CLI (`agy`), Codex CLI

---

## 1. Project Philosophy: Simple, Flat, Human-Maintainable

1. **KISS (Keep It Simple, Stupid)**:
   - Prefer simple, readable procedural or functional code over multi-layered OOP enterprise abstractions.
   - Do **NOT** create factory classes, dependency injection containers, repository patterns, or multi-tier interface wrappers unless explicitly required.
   - Avoid deep indentation & nesting. Use guard clauses and early returns.

2. **YAGNI (You Aren't Gonna Need It)**:
   - Implement only the features requested for the current milestone.
   - Do not write speculative configuration options or "future-proof" abstract interfaces for hypothetical hardware.

3. **Flat Directory & Modular Boundaries**:
   - `backend/` — Python FastAPI backend + Async I/O (Serial & Camera management).
   - `frontend/` — Single-page HTML5/JS Web UI (zero complex build toolchain or heavy node modules).
   - `firmware/` — ESP32 C++ stepper driver firmware.
   - `docs/` — Specifications and hardware documentation.

4. **No Backward Compatibility by Default**:
   - When replacing an API, schema, file layout, or implementation, remove the old path and update the current frontend, tests, and documentation in the same change.
   - Do **NOT** add compatibility adapters, deprecated aliases, or migration loaders unless explicitly requested.
   - Never automatically delete user capture media; incompatible development data may be moved aside manually.

---

## 2. Python Backend Standards (`backend/`)

- **Dependency Management**: Always use `uv`.
  - Add dependencies via `uv add <package>` (or edit `pyproject.toml` and run `uv sync`).
  - Run scripts via `uv run python main.py`.
- **Python Version**: Python 3.10+ with standard type annotations (`int | None`, `dict[str, Any]`).
- **AsyncIO & FastAPI**:
  - Keep route handlers short (validate request -> delegate to state manager -> return response).
  - Use `asyncio` for non-blocking I/O (serial reading/writing, camera triggers).
  - Never run blocking `time.sleep()` on the main event loop; use `await asyncio.sleep()`.
- **Error Handling**:
  - Prefer explicit exception handling over generic `except Exception: pass`.
  - Return clear JSON error messages (`{"status": "ERROR", "detail": "..."}`) with appropriate HTTP status codes.

---

## 3. Hardware & Serial Communication Rules

- **Hardware Simulation Boundaries**:
  - `SerialManager` uses only the real serial protocol path. Do **NOT** add inline motor mock branches or silently simulate a missing controller.
  - If motor simulation is needed, use a separate serial-emulator subproject that behaves like the ESP controller from the backend's perspective.
  - Camera simulation is selected explicitly with a flag and a separate fake camera-manager class that mimics gphoto2 delays, settings, and image capture.
  - Never silently fall back from the real camera manager to the fake implementation after a hardware error.
- **Fail-Safe Motor Controls**:
  - Include hard bounds and emergency stop methods (`/api/motors/stop`).

---

## 4. How to Verify Changes

Before declaring any feature complete, run verification commands:

```bash
# 1. Verify Python Backend syntax & linting (Ruff)
cd backend
uv run ruff check .
uv run python -m py_compile main.py serial_manager.py

# 2. Sync backend dependencies
uv sync --extra dev

# 3. Verify ESP32 Firmware build via PlatformIO
cd ../firmware
pio run

```
