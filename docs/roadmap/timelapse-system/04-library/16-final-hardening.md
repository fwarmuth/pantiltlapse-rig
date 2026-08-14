# Task 16 — Final Hardening and Documentation

## Goal

Finish quality and documentation work after the plan/run workflow has proven itself with the fake camera and real motor hardware.

## Prerequisites

- Tasks 01 through 15 completed and hardware-refined.

## Checklist

- [ ] Confirm Task 11 deleted `TimelapseConfig`, the old engine/routes, tests, documentation, and all references; no adapter or deprecation route remains.
- [ ] Leave pre-roadmap flat captures untouched but outside the supported library; do not add migration code and never delete them automatically.
- [ ] Remove obsolete flat manual-capture helpers when no current frontend or diagnostic workflow references them.
- [ ] Consolidate duplicate state enums, interpolation logic, filename generation, and artifact serving created during incremental work.
- [ ] Update architecture, protocol, backend README, hardware limitations, output-tree documentation, and operator workflow.
- [ ] Add a fresh-install walkthrough and a safe real-hardware setup checklist.
- [ ] Add a recovery guide for camera disconnect, serial uncertainty, interrupted backend, corrupt manifest, and low storage.
- [ ] Run the full automated suite, fake-camera integration checks, JavaScript checks, Ruff, Python compilation, dependency sync, and PlatformIO build.
- [ ] Resolve the recorded Starlette TestClient/httpx and HTTP 422 constant deprecation warnings without weakening assertions.
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

- The documented end-to-end workflow works with real motor hardware and both explicitly selected camera implementations.
- No active code writes new time-lapse captures to the old flat naming scheme.
- Current limitations remain explicit: open-loop motors, uninterruptible synchronous moves, operator-established zero, and no automatic restart continuation.
- The repository contains only the current API/schema implementation; no backward-compatibility branches remain.

## Not in this task

- New product features.
- Old schema/API loaders or data migrations.
- Database introduction or video rendering.

## Implementation notes

- Record removed obsolete paths, preserved media locations, final hardware versions, and the acceptance-run location here.

