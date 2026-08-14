# Task 08 — Enhanced Night-Oriented Live View

## Goal

Provide dark-scene framing stream using separate `PreviewProfile` camera settings and client-side digital gain boost.

## Checklist

- [x] Create `PreviewController` acquiring exclusive `OperationCoordinator` lock (`PREVIEW` mode).
- [x] Apply plan `PreviewProfile` settings (ISO, shutter, aperture) during live view stream.
- [x] Stream MJPEG (`multipart/x-mixed-replace`) video frames with boundary headers.
- [x] Support client-side contrast/gain boost ($1.0 \dots 4.0\times$) for night framing without altering raw acquisition settings.
- [x] Include measured FPS, resolution, dropped frames, and gain telemetry in status API.
- [x] Restore camera `AcquisitionProfile` settings upon stopping live view stream.
- [x] Add REST endpoints for preview start, status, stop, and stream.
- [x] Add unit tests for live view start/stop, lock conflicts, and camera setting restoration.

## Implementation notes

- Created `backend/preview_controller.py`.
- Added endpoints `/api/camera/preview/start`, `status`, `stop`, and `stream`.
- All tests pass in `backend/tests/test_live_view.py`.
- Post-Task-09 audit: the generic start route does not pass the selected plan profiles, and the real manager hides gphoto preview failure with a synthetic frame. Task 09B makes preview plan-scoped and truthful.
