# CameraCommander 5-Step Workflow Specification

The web frontend implements a streamlined, step-by-step workflow designed to prevent screen clutter, guide the operator logically, and ensure hardware safety.

```
[1. Setup & Framing] ──> [2. Sequence Plan] ──> [3. Key Poses & Trajectory] ──> [4. Acquisition Settings] ──> [5. Execution & Monitoring]
```

---

## Step 1: Raw Movement & Rig Setup

**Purpose**: Position the camera rig, calibrate origin, and frame the target scene.

### Features & Controls
- **Manual Movement**: Directional D-pad for Pan (azimuth) and Tilt (elevation) with selectable step sizes (0.5°, 1°, 5°, 15°).
- **Origin & Reference**: Operator confirmation of physical zero reference (`/api/rig/confirm-zero`).
- **Driver Management**: Enable / Disable stepper drivers (with confirmation prompt).
- **Live Framing Preview**:
  - Auto-configured framing view (high-gain / wide-open preview profile) to see target in low light.
  - Client-side image enhancement: CLAHE (Contrast Limited Adaptive Histogram Equalization), brightness, contrast, and gain multipliers to reveal details in pitch-black environments.
  - Live RGB histogram.
- **Safety**: Emergency Stop button (`/api/motors/stop`) always visible and accessible.

---

## Step 2: Sequence Definition

**Purpose**: Initialize or load a time-lapse sequence plan.

### Features & Controls
- **Plan Selector**: Dropdown to switch between existing stored sequence plans or create a new one.
- **Metadata**:
  - Sequence Name (required).
  - Description / notes (optional).
- **Persistence**: Save Plan (`POST/PUT /api/plans`), Delete Plan (`DELETE /api/plans/{id}`).

---

## Step 3: Key Poses & Trajectory

**Purpose**: Set up the camera movement path, configure keyframes, and test motion clearance.

### Features & Controls
- **Keyframe Configuration**:
  - Minimum requirement: Start Pose ($t=0.0$) and End Pose ($t=1.0$).
  - Optional intermediate key poses ($0.0 < t < 1.0$) for multi-segment pans, tilts, or compound motions.
  - One-click "Capture Current Pose as Keyframe" button.
  - Interpolation curve selection: Linear vs. Smooth (cubic Hermite) with configurable tangent scaling.
- **Trajectory Visualizer**:
  - Interactive SVG curve plot showing Pan (cyan) and Tilt (emerald) curves across sequence progress $t$.
- **Motion Clearance & Testing (Dry Run)**:
  - Play / Start Motion Dry Run (`POST /api/plans/{id}/dry-run/start`): moves motors along the full path without firing shutter.
  - Stop / Cancel Dry Run (`POST /api/plans/{id}/dry-run/cancel`).
  - Clearance validation status badge.

---

## Step 4: Acquisition Settings

**Purpose**: Configure actual exposure parameters for the sequence and verify image quality with test shots.

### Features & Controls
- **Exposure Configuration**:
  - ISO (populated dynamically from camera supported choices).
  - Shutter Speed / Exposure Time (e.g. 1/125, 1s, 5s, bulb).
  - Aperture (f-stop).
- **Schedule Parameters**:
  - Total Shots (minimum 2).
  - Interval (seconds between shutter releases).
  - Settle Pause (seconds to wait after motor stops before releasing shutter).
  - Computed total sequence run duration.
- **Test Shot Verification**:
  - "Take Test Shot" trigger using acquisition settings.
  - Test shot gallery with thumbnail display, EXIF data, SHA256 integrity, and file size inspector.

---

## Step 5: Final Review & Live Progress Monitoring

**Purpose**: Review pre-flight settings, execute the time-lapse, and monitor captured photos in real time.

### Features & Controls
- **Pre-Flight Summary Checklist**:
  - Sequence name, shot count, interval, estimated total time.
  - Hardware status check (zero confirmed, drivers enabled, camera connected).
- **Execution Controls**:
  - "Start Sequence" trigger.
  - Pause / Resume / Cancel execution.
  - Emergency Stop.
- **Real-Time Telemetry**:
  - Progress bar and percentage.
  - Current shot index vs. total shots ($N / M$).
  - Elapsed time, estimated time remaining (ETA), time until next shot.
- **Live Captured Photo Review**:
  - Live gallery updating as each frame is captured and downloaded.
  - Image viewer to inspect recent frames.
