# Task 11 — Durable Recording Engine

## Goal

Execute the immutable plan snapshot through move, settle, capture, and immediate persistence with truthful timing.

## Prerequisites

- Tasks 02, 05, 06, 07, and 10.

## Checklist

- [ ] Replace policy inside the existing ephemeral loop with a focused `RunEngine`; keep hardware managers limited to individual operations.
- [ ] Add a start endpoint that validates plan revision, setup confirmation, generated trajectory, storage availability, camera readiness, and exclusive hardware ownership.
- [ ] If dry-run validation is missing/stale, require an explicit request confirmation flag and persist that acknowledgement.
- [ ] Create the immutable run snapshot before applying settings or moving.
- [ ] Stop live view, apply/read back the acquisition profile, and record actual supported settings.
- [ ] For each shot: wait for minimum start spacing, move absolute, settle, capture/download, publish artifacts/shot record, then update run summary.
- [ ] Use a monotonic clock for interval waiting and UTC wall-clock timestamps for persisted records.
- [ ] Never burst to catch up after an overrun; set the next earliest start from the previous actual start plus `interval_s` and report accumulated delay.
- [ ] Add pause, resume, and cancel controls. Pause prevents the next phase/shot; cancel preserves all completed records.
- [ ] End as `COMPLETED` or `COMPLETED_WITH_GAPS`; reserve `ERROR` for a terminal engine/storage condition.
- [ ] Emit progress through the existing SSE channel without embedding image bytes.
- [ ] Map legacy time-lapse status/control calls to the new engine where feasible, without removing them yet.

## Local integration check

With the fake camera and either the real motor controller or a future external serial emulator, run short sequences with two, five, and 50 shots. Pause during interval, resume, cancel another run, edit the source plan during a run, and confirm the immutable snapshot and persisted frames remain correct. Use test-only transport stubs for automated engine-policy tests, not as a backend runtime mode.

## Hardware bench check

- [ ] Record a short JPEG sequence with start, end, and an intermediate smooth keyframe.
- [ ] Confirm movement occurs between exposures and acquisition settings remain fixed.
- [ ] Compare persisted scheduled/actual timestamps with observed camera activity.
- [ ] Pause/resume and cancel safely between shots.
- [ ] Verify originals and previews can be opened after backend shutdown.

## Acceptance criteria

- Every completed attempt is durable before the engine advances to the next shot.
- Plan edits during execution cannot change targets, timing, or settings.
- A long exposure or slow move increases schedule delay but never causes rapid catch-up captures.
- Manual controls, test shots, preview, and dry runs cannot take hardware ownership while a run is active.

## Not in this task

- Automatic retries/failure injection beyond clean terminal handling; task 12 adds detailed policy.
- Restart continuation.
- Final monitoring/history screens.

## Implementation notes

- Record measured hardware timing and any camera readback limitations here.
