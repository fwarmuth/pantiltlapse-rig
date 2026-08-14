# Task 06 — Test Shots and Media Artifacts

## Goal

Capture and organize plan-scoped test shots with previews and complete metadata before starting sequence execution.

## Checklist

- [x] Create test shot artifact helper saving images under `output/plans/<plan_id>/test-shots/<test_shot_id>/`.
- [x] Refactor camera managers to accept target directory parameter in `trigger_capture`.
- [x] Generate browser-viewable JPEG/SVG preview artifacts.
- [x] Calculate SHA256 checksum and byte size for original images.
- [x] Write `metadata.json` capturing requested settings, observed camera settings, and file manifest.
- [x] Atomically rename temp directory `.tmp_<id>` to final shot ID directory upon completion.
- [x] Add REST endpoints for test shot capture, list, detail, and file artifact serving.
- [x] Add unit tests verifying artifact directory structure, checksums, metadata, and failure cleanup.

## Implementation notes

- Post-Task-09 audit: the current helper hardcodes `original.jpg`, guesses artifact filenames, and is not operation-coordinated. Task 09B replaces this with the shared typed capture/media contract required by run storage.

- Created `backend/media_helper.py`.
- Added endpoints `/api/plans/{id}/test-shots`, detail, and artifact file server.
- All tests pass in `backend/tests/test_test_shots.py`.
