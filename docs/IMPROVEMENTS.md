# System Improvements & Hardware Optimization Plan

> **Target Platform**: Raspberry Pi Zero 2 W + Canon EOS 700D + 2-Axis Stepper Rig  
> **Date**: August 2026

---

## 1. Issue Analysis & Root Causes

### 1.1 Sequence Shot Count Mismatch (Set 60, Stopped at 24)
- **Root Cause**: 
  - `activePlan` is initialized in `app.js` with a default schedule of `{ total_shots: 24, ... }`.
  - In Step 4 (Acquisition), when changing the `<input id="planTotalShots">` field, only `updateTrajectoryPreview()` is triggered; the value is **never synced back** to `activePlan.schedule.total_shots` unless `saveCurrentPlan()` is explicitly pressed.
  - When transitioning to Step 5 (Review & Execution) and clicking "Start Sequence Execution", `startSequenceExecution()` reads `activePlan?.schedule?.total_shots || 20`, which was still holding `24`.
- **Fix Plan**:
  1. Add an `oninput` / `onchange` listener on `planTotalShots`, `planInterval`, and `planSettle` that immediately writes the new values into `activePlan.schedule` and recalculates the trajectory preview in real time.
  2. Ensure `startSequenceExecution()` prioritizes the input field value: `parseInt(document.getElementById("planTotalShots")?.value) || activePlan?.schedule?.total_shots || 20`.
  3. Ensure Step 5 summary cards and timeline calculations update dynamically whenever timing inputs change.

---

### 1.2 Cannot Pan/Tilt When in Enlarged Live View Modal
- **Root Cause**:
  - The HTML for the enlarged modal D-pad (`index.html`) calls `onclick="jogPanRelative(...)"` and `onclick="jogTiltRelative(...)"`.
  - These two functions **do not exist** anywhere in `app.js` (the main sidebar uses `moveRelative(dx, dy)`). Clicking any button in the enlarged D-pad threw a silent `ReferenceError: jogPanRelative is not defined`.
  - Keyboard shortcuts (Arrow keys) were not bound to the viewport or modal.
- **Fix Plan**:
  1. Replace the invalid function calls in the enlarged D-pad with standard `moveRelative(dx, dy)`.
  2. Implement global and modal-scoped keyboard shortcuts:
     - `ArrowLeft` / `ArrowRight` -> Pan relative (`-step`, `+step`)
     - `ArrowUp` / `ArrowDown` -> Tilt relative (`+step`, `-step`)
     - `Home` or `0` -> Return to Origin `(0°, 0°)`
     - `Space` -> Emergency Stop / Cancel move
     - `[` / `]` or `1` / `2` / `3` -> Cycle step increments (`0.5°`, `1.0°`, `5.0°`, `15.0°`)
  3. Add visual button-press feedback on the on-screen D-pad when keyboard shortcuts are used.

---

### 1.3 Live Stream Bandwidth & Browser Performance Over Wi-Fi
- **Root Cause**:
  - In `app.js`, `runFrameFetchLoop()` runs in a tight `while (isLiveViewActive)` loop that immediately requests the next frame as soon as the previous one arrives, with **zero delay or pacing**.
  - On each frame, `createImageBitmap`, multiple canvas `drawImage` operations, and unoptimized CPU image processing filters (CLAHE, gain/gamma) run on every tick, driving browser CPU to 100% and choking the Pi's Wi-Fi link.
  - Full-resolution preview frames from `gphoto2` (often 1024×680 or uncompressed JPEG) consume excess network throughput when streamed continuously over Wi-Fi.
- **Fix Plan**:
  1. **Client-Side Frame Pacing**: Introduce a configurable framerate limiter (default **5–8 FPS** for low-latency Wi-Fi operation) using `setTimeout` / `requestAnimationFrame` timing pacing.
  2. **Framerate Selector UI**: Add an FPS selector dropdown in the live view toolbar (`3 FPS`, `5 FPS`, `8 FPS`, `12 FPS`, `Max`).
  3. **Server-Side Compression / Resize Option**: Optional JPEG quality compression and lightweight downscaling in `backend/camera_manager.py` / `preview_controller.py` to keep each frame under 25–40 KB.
  4. **Offscreen Canvas & Worker Rendering**: Avoid redundant canvas allocations and skip heavy filters when filter mode is `"none"`.

---

## 2. Additional Codebase Hardening & UX Improvements

| Area | Improvement Description | Priority |
| :--- | :--- | :--- |
| **Exposure & Test Shot Preview** | Automatically display the last taken test shot thumbnail with a 1-click zoom modal in Step 4. | High |
| **Wi-Fi Disconnect Recovery** | Implement automatic reconnection with exponential backoff on SSE / live polling if the Wi-Fi drops momentarily in the field. | High |
| **Coordinate Safety Checks** | Prevent starting execution or dry-run if physical tilt limits (`tilt_min_deg`, `tilt_max_deg`) are exceeded by any sampled trajectory pose. | High |
| **Single-Click Camera Sleep Prevention** | Send periodic low-overhead gPhoto2 keepalive pings during idle preview so the DSLR auto-power-off timer does not trip. | Medium |
| **Systemd Service Unit** | Provide a `cameracommander.service` systemd unit file on the Pi for auto-starting the backend on boot. | Medium |

---

## 3. Implementation Steps

1. **Step 1**: Fix input synchronization in `frontend/app.js` and `frontend/index.html` (resolves shot count issue).
2. **Step 2**: Fix D-pad handlers in `frontend/index.html` and add keyboard arrow controls in `frontend/app.js`.
3. **Step 3**: Implement framerate limiting and stream pacing in `frontend/app.js` and backend preview pacing.
4. **Step 4**: Commit & push changes locally, then pull and verify on the Raspberry Pi Zero 2 W hardware.
