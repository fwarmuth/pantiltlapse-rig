# Task 07 — Full-Path Dry Run Engine

## Goal

Provide motion-only sequence rehearsal traversing all sampled keyframe poses without camera shutter triggers or interval delays.

## Checklist

- [x] Create `OperationCoordinator` for exclusive operation locking (`IDLE`, `PREVIEW`, `DRY_RUN`, `RECORDING`).
- [x] Create `DryRunEngine` executing full-path motion rehearsal across sampled trajectory poses.
- [x] Validate zero reference confirmation and tilt bounds before dry run start.
- [x] Emit real-time progress events over SSE stream.
- [x] Persist `DryRunReport` under `output/plans/<plan_id>/dry_run_report.json`.
- [x] Implement stale detection comparing plan revision, reference ID, and rig limits.
- [x] Add REST endpoints for dry run start, status/report, and cancellation.
- [x] Add unit tests for dry run traversal, lock conflicts, cancellation, and stale detection.

## Implementation notes

- Created `backend/coordinator.py` and `backend/dry_run_engine.py`.
- Added endpoints `/api/plans/{id}/dry-run/start`, `status`, and `cancel`.
- All tests pass in `backend/tests/test_dry_run.py`.
