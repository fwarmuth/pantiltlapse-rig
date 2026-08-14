# Task 09B — Camera Profiles and Media Contract

## Goal

Give test shots and future run shots one trustworthy camera/file contract before unattended recording is implemented.

## Prerequisites

- Tasks 06, 08, and 09.
- Task 09A for operation guards.
- Read `../implementation-audit.md`.

## Checklist

- [x] Define a small typed capture result containing camera filename/path, saved original path, extension, MIME type, capture timestamp, and optional camera-preview path; use it for both camera managers.
- [x] Change capture naming to accept a destination plus optional stem, then preserve the camera-reported extension. Never force RAW bytes into `.jpg`.
- [x] Make `FakeCameraManager` write an actual JPEG for JPEG captures and generate predictable RAW-like originals plus a real JPEG preview when RAW is selected.
- [x] Remove synthetic fallback frames from the real `CameraManager`; gphoto preview failure must increment/report a real preview error.
- [x] Make preview start plan-scoped and pass the persisted selected plan's `PreviewProfile` and `AcquisitionProfile` to `PreviewController`; require the UI to save edits before starting/restarting preview.
- [x] Check every camera setting result and read back settings. A failed preview/acquisition setting must be visible and must not proceed as though applied.
- [x] Stop preview before a test shot, apply the persisted plan acquisition profile plus any explicit test-only request override, capture, and leave the camera in those effective acquisition settings; require the operator to restart preview explicitly.
- [x] Move blocking gphoto calls and large checksum/copy/preview operations off the asyncio event loop while retaining the camera lock.
- [x] Refactor the plan test-shot helper into reusable artifact publication functions suitable for Task 10B; keep plan- and run-specific manifest assembly outside camera managers.
- [x] Extend test-shot metadata with plan revision/effective settings and each artifact's byte size/SHA-256; extract available JPEG EXIF without requiring RAW development.
- [x] Serve artifacts by manifest entry/ID rather than guessing `original.jpg`, `original.svg`, or `preview.jpg` filenames.
- [x] Return camera unavailability as `503`, invalid state as `409`, and malformed/unsupported settings as `422` using the shared error shape.
- [x] Update camera/backend/protocol documentation and remove remaining operational references to `MOCK_MODE`.

## Fake-camera check

Capture JPEG and simulated RAW test shots. Verify MIME signatures match extensions, originals and previews have independent hashes/metadata, preview settings never overwrite plan acquisition settings, and the event loop remains responsive during configured capture delay.

## Hardware check

- [ ] Capture the camera's configured JPEG format and verify extension, MIME, preview, EXIF, and setting readback.
- [ ] Capture RAW or RAW+JPEG and document the exact files gphoto exposes; preserve every downloaded original and one browser preview.
- [ ] Cause live-view failure/disconnect and verify it is shown as an error rather than a synthetic real-camera frame.
- [ ] Stop plan preview via test shot and verify the saved acquisition profile is active for the exposure.

## Acceptance criteria

- Camera and media code never infer file type solely from a caller-provided name.
- Only the explicit fake camera creates placeholder imagery.
- Test-shot artifact publication is directly reusable by run storage without copying plan-route logic.
- Camera operations do not block unrelated SSE/status processing for the duration of an exposure or large file hash.

## Not in this task

- Capture retries or ambiguous-download recovery policy.
- Run directories, shot records, or monitoring UI.
- RAW processing/color development.

## Implementation notes

- Defined `CaptureResult` schema in `domain/models.py`.
- Updated `FakeCameraManager` to generate Pillow JPEGs and mock RAW binaries with companion previews.
- Removed synthetic fallback image generation from real `CameraManager.capture_preview_frame()`.
- Offloaded blocking python-gphoto2 calls, file hashing (`compute_sha256_async`), and image file operations to thread pools via `asyncio.to_thread`.
- Exported `publish_media_artifact(...)` and `extract_jpeg_exif(...)` in `media_helper.py` for reusable manifest and artifact publication.
