# Task 06 — Test Shots and Media Artifacts

## Goal

Capture a plan-scoped test image while preserving the camera original, a browser-viewable preview, and useful metadata.

## Prerequisites

- Tasks 00, 01, and 03.
- Task 04 is required for the HTTP endpoint but core artifact work can be tested before it.

## Checklist

- [ ] Refactor camera capture output so callers choose a destination directory and the camera-provided name/extension is preserved.
- [ ] Introduce a small media helper that writes artifact metadata and produces `preview.jpg` when the original cannot be displayed directly.
- [ ] Record file role, relative path, media type, byte size, checksum, capture time, requested settings, observed settings, and extractable EXIF/camera metadata.
- [ ] If the original JPEG is suitable for the browser, allow preview metadata to reference it instead of duplicating bytes.
- [ ] Extend the explicit `FakeCameraManager` from task 00 to create the same artifact and metadata shapes as real capture, including intentional failure hooks for tests.
- [ ] Add `POST /api/plans/{id}/test-shots`, list/detail endpoints, and a safe artifact-serving endpoint.
- [ ] Apply the plan acquisition profile immediately before capture and verify/read back supported settings.
- [ ] Use a temporary test-shot directory and atomically publish it only after required artifacts and metadata are complete.
- [ ] Clean up incomplete temporary artifacts on expected failure; never delete completed user captures.
- [ ] Add tests for JPEG, simulated RAW plus preview, metadata extraction fallback, checksum, safe paths, and failed capture/download.

## Fake-camera check

Start the backend with the explicit fake-camera setting. Create a plan, trigger two test shots, open both previews in the browser, inspect their metadata responses, restart the backend, and confirm they remain listed under the plan.

## Hardware bench check

- [ ] Test with camera JPEG mode and verify the downloaded extension and browser preview.
- [ ] Test with a RAW-capable camera setting and verify the original is retained plus a viewable preview exists.
- [ ] Confirm ISO, shutter, and aperture in metadata/readback match the requested acquisition profile where the camera exposes them.
- [ ] Disconnect the camera and verify the incomplete test shot is reported without damaging previous artifacts.

## Acceptance criteria

- The original camera file is never renamed to a misleading extension.
- API responses never disclose absolute filesystem paths.
- Every completed test shot has readable metadata and a browser-viewable artifact.
- The old manual trigger endpoint remains functional during migration.

## Not in this task

- Live-view streaming.
- Recording-run shot records or retries.
- RAW development/color processing; use camera-provided preview data or a minimal supported thumbnail strategy.

## Implementation notes

- Record camera formats actually verified and any metadata unavailable from the Canon/gphoto combination.
