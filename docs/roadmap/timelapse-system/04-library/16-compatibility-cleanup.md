# Task 16 — Compatibility Cleanup and Documentation

## Goal

Finish the migration only after the plan/run workflow has proven itself with the fake camera and real motor hardware.

## Prerequisites

- Tasks 01 through 15 completed and hardware-refined.

## Checklist

- [ ] Inventory old `TimelapseConfig`, engine, routes, UI controls, and flat capture behaviors against their new replacements.
- [ ] Add one-release deprecation responses/log messages for legacy `/api/timelapse/*` use if external clients may exist.
- [ ] Migrate any still-useful flat captures deliberately or leave them untouched with documented access; never silently delete them.
- [ ] Remove legacy implementation only when no frontend or test references remain.
- [ ] Consolidate duplicate state enums, interpolation logic, filename generation, and artifact serving created during incremental work.
- [ ] Update architecture, protocol, backend README, hardware limitations, output-tree documentation, and operator workflow.
- [ ] Add a fresh-install walkthrough and a safe real-hardware setup/checklist.
- [ ] Add a recovery guide for camera disconnect, serial uncertainty, interrupted backend, corrupt manifest, and low storage.
- [ ] Run the full automated suite, fake-camera integration checks, JavaScript checks, Ruff, Python compilation, dependency sync, and PlatformIO build.
- [ ] Confirm no later task reintroduced inline motor simulation or automatic hardware fallback; keep motor simulation outside the backend.
- [ ] Confirm real-camera connection failures remain visible and never silently select `FakeCameraManager`.
- [ ] Perform one end-to-end hardware acceptance sequence and browse it after a clean backend restart.

## End-to-end acceptance scenario

1. Boot the rig and backend.
2. Configure tilt bounds and confirm physical zero.
3. Create a plan using enhanced live view and four keyframes with mixed transitions.
4. Apply fixed acquisition settings and save test shots.
5. Complete a full-path dry run.
6. Record a sequence containing at least one injected/recoverable camera failure.
7. Monitor it from a phone through a browser reconnect.
8. Restart the backend after completion.
9. Browse the run, shots, gaps/attempts, metadata, previews, and original files.

## Acceptance criteria

- The documented end-to-end workflow works with real motor hardware and with both explicitly selected camera implementations.
- No active code writes new time-lapse captures to the old flat naming scheme.
- No user media is deleted as part of migration.
- Current limitations remain explicit: open-loop motors, uninterruptible synchronous move, operator-established zero, and no automatic restart continuation.

## Not in this task

- New product features.
- Schema v2 or speculative migrations.
- Database introduction or video rendering.

## Implementation notes

- Record legacy removal decisions, preserved files, final hardware versions, and acceptance-run location here.
