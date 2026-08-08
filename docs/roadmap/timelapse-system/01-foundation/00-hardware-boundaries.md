# Task 00 — Hardware and Simulation Boundaries

## Goal

Simplify the backend before adding planning features: motor control always uses the real serial protocol, while camera simulation is an explicitly selected alternative camera class.

## Prerequisites

- Read `../00-contract.md` and the repository `AGENTS.md`.
- No other roadmap task is required.
- This task records the user's explicit project decision that replaces the earlier general inline-mock requirement.

## Checklist

- [ ] Remove the `mock` constructor flag and command-processing branches from production `SerialManager`.
- [ ] Remove automatic serial fallback. A failed serial connection leaves the backend available with motors visibly disconnected/error; motor commands return an intentional `503`.
- [ ] Keep one serial command/parser path for physical hardware and any future external serial emulator.
- [ ] Remove simulation behavior from the gphoto-backed `CameraManager`.
- [ ] Add a separate `FakeCameraManager` class with the small operation surface currently consumed by routes/engines.
- [ ] Add one explicit `FAKE_CAMERA=true|false` setting, defaulting to `false`; select the class with a simple conditional during application setup, not a factory hierarchy.
- [ ] Make the fake camera retain/set ISO, shutter, and aperture; apply realistic async delays; create correctly typed placeholder images; and expose obvious `fake` status.
- [ ] Never switch to the fake camera after a real-camera connection/runtime error.
- [ ] Replace the global `MOCK_MODE` documentation/configuration with separate motor connection status and the camera flag.
- [ ] Update existing tests for disconnected serial, explicit fake camera, real-camera failure, and correct status/error reporting.

## Local camera check

Start with `FAKE_CAMERA=true` and no camera connected. Confirm camera status is explicitly fake, settings can be changed, trigger produces a browser-viewable placeholder after a delay, and restart preserves no unsupported camera state assumptions. Confirm motors remain visibly disconnected rather than simulated when no serial peer exists.

## Hardware bench check

- [ ] Start with `FAKE_CAMERA=false`, real motor controller, and real camera; verify both connect through their production paths.
- [ ] Disconnect serial and confirm the backend remains reachable but motor commands fail visibly without changing reported actuator position.
- [ ] Disconnect the real camera and confirm it reports an error without switching to fake.
- [ ] Re-run existing manual motor move, camera settings, and trigger behavior.

## Optional future serial-emulator contract

Do not implement the emulator in this task. When needed, create it as a separate subproject that:

- Opens or exposes a serial/PTY endpoint accepted by `SERIAL_PORT`.
- Implements the documented ESP newline protocol and response timing.
- Tracks and visualizes pan, tilt, driver, and movement state.
- Does not require any conditional behavior in CameraCommander backend code.

## Acceptance criteria

- Searching production backend code finds no motor simulation command processor or motor mock-mode branch.
- There is exactly one serial protocol path.
- Fake camera selection is explicit and cannot occur due to hardware failure.
- Backend startup without serial hardware remains diagnosable and does not pretend motors are connected.
- Existing non-simulation HTTP behavior remains available.

## Not in this task

- The external serial emulator itself.
- Plan/run domain models or persistence.
- Enhanced live view, RAW previews, retry policy, or new frontend planning controls.
- Firmware changes.

## Implementation notes

- Record the final environment setting, status fields, and manual hardware results here.

