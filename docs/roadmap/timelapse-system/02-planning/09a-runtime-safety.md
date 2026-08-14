# Task 09A — Runtime Ownership and Motion Safety

## Goal

Make the completed planning workflow truthful and safe enough to become the foundation of unattended recording.

## Prerequisites

- Tasks 05, 07, and 09.
- Read `../implementation-audit.md`.

## Checklist

- [x] Persist `tilt_min_deg` and `tilt_max_deg` in an atomic `output/rig.json`; load them at startup and keep the coordinate-reference UUID/confirmation runtime-only.
- [x] Changing limits invalidates existing dry-run validity even when the coordinate-reference UUID is unchanged.
- [x] Encode the shared operation-concurrency matrix in `OperationCoordinator` with small query/guard methods; do not scatter direct boolean checks through routes.
- [x] Remove the `active_mode` compatibility setter; update tests/fixtures to acquire and release coordinator state through its current API.
- [x] Apply guards to manual moves, sequence step, driver changes, rig-limit changes, test shots, preview, dry run, and later recording.
- [x] Preserve the intentional ability to jog while previewing and to stream preview during dry run, but allow preview+dry-run only when both identify the same plan.
- [x] Make `DryRunEngine` inspect every motor response. On non-`OK`, stop immediately, persist an invalid/error report, and never increment that pose as completed.
- [x] Record commanded pose, response/error, start/end timestamps, and completed count in the dry-run report.
- [x] Make report staleness compare plan revision, coordinate-reference ID/confirmation, and both current tilt limits.
- [x] Add dry-run and coordinator status to SSE so the UI need not create a second progress polling truth.
- [x] Make global stop cancel the active dry run before sending `X`; Task 11 extends the same path to `RunEngine`. Retain the documented firmware delay limitation.
- [x] Invalidate coordinate reference after a driver command only when the command actually succeeded.
- [x] Update protocol/hardware documentation for the operation matrix, persisted limits, dry-run result meaning, and stop behavior.

## Automated check

Use test-only serial responses to cover `OK`, returned `ERROR`, exception, cancellation, and delayed completion. Assert that invalid reports cannot be mistaken for successful validation, conflicting routes return `409`, preview+dry-run remains allowed, and changed limits make a report stale after restart/reload.

## Hardware check

- [ ] Run a short preview-assisted dry run and verify every commanded pose is recorded.
- [ ] Disconnect serial between poses and verify the report becomes invalid/error rather than completed.
- [ ] Try manual move, driver, and limit changes during dry run and verify no serial command is sent.
- [ ] Restart the backend and verify configured tilt limits persist while zero confirmation resets.

## Acceptance criteria

- No motion result is treated as success merely because an async call returned a dictionary.
- Every mutating hardware route follows the same operation matrix.
- A successful dry-run report corresponds to all planned poses returning `OK` under the same plan revision, reference, and limits.

## Not in this task

- Run snapshots or recording execution.
- Camera file-format refactoring.
- Firmware stop behavior changes.

## Implementation notes

- Implemented `RigManager` atomic `output/rig.json` persistence for `tilt_min_deg` and `tilt_max_deg` while keeping zero reference confirmation in-memory.
- Added query/guard methods (`can_move`, `can_change_drivers`, `can_change_limits`, `can_test_shot`, `can_dry_run`, `can_preview`, `can_record`) on `OperationCoordinator`.
- Updated `DryRunEngine` to check motor response status, record execution logs and pose errors, save invalid reports on failure, and evaluate staleness against rig tilt bounds.
- Included `dry_run` and `coordinator` state dictionary in `/api/events` SSE payload.
