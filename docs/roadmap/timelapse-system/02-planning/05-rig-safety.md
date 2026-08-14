# Task 05 — Rig Limits and Coordinate Reference

## Goal

Add the minimum truthful safety state required before reusable plans can command open-loop hardware.

## Prerequisites

- Tasks 00 and 04.

## Checklist

- [x] Add persistent rig configuration containing required `tilt_min_deg` and `tilt_max_deg`; pan bounds remain `null`/unbounded.
- [x] Add runtime coordinate-reference state with UUID, creation reason/time, and operator-confirmed flag/time.
- [x] Create a new unconfirmed coordinate reference on backend startup and every driver disable or enable operation.
- [x] Add endpoints to read rig/setup status, update tilt limits while no automated operation is active, and confirm the physical zero.
- [x] Put one bounds-check function in the motor-command path so manual, sequence-step, dry-run, and future run moves cannot bypass it.
- [x] Reject planned absolute moves until the coordinate reference is confirmed; keep emergency stop and driver operations available.
- [x] Include rig limits and coordinate-reference status in SSE/status data.
- [x] Return clear `409` errors for unconfirmed reference and `422` for out-of-bounds tilt targets.
- [x] Add unit tests for startup invalidation, confirmation, driver-cycle invalidation, bounded tilt, and unbounded multi-rotation pan; spy on serial writes rather than adding a runtime motor mock.
- [x] Update hardware/protocol documentation to state that limits are backend-enforced and not firmware endstops.

## Implementation notes

- Created `backend/domain/rig.py` with `RigManager` and `CoordinateReferenceState`.
- Connected to `/api/rig/status`, `/api/rig/limits`, `/api/rig/confirm-zero`, `/api/motors/move`, `/api/motors/drivers`.
- All tests pass in `backend/tests/test_rig_safety.py`.
- Post-Task-09 audit: limits are currently in memory and mutation routes do not yet enforce coordinator state; Task 09A completes persistence and operation guards before recording.
