# Task 11 — Durable Recording Engine

## Goal

Execute the immutable plan snapshot through move, settle, capture, and immediate persistence with truthful timing.

## Prerequisites

- Tasks 02, 09A, 09B, 10A, and 10B.

## Checklist

- [ ] Add a focused `RunEngine`; keep hardware managers limited to individual operations and reuse the coordinator/trajectory/media contracts.
- [ ] Add `POST /api/plans/{plan_id}/runs` with `{plan_revision, allow_stale_dry_run:false}` and `GET /api/runs/active` plus per-run status/pause/resume/cancel routes.
- [ ] Validate exact plan revision, confirmed reference, current limits, generated trajectory, free storage, camera readiness, no active dry run, and coordinator ownership.
- [ ] If dry-run validation is missing/stale, reject unless `allow_stale_dry_run=true`; persist the acknowledgement and reason in `RunSnapshot`.
- [ ] If preview is active for the same plan, stop it and restore settings before acquiring exclusive recording ownership. Reject an unrelated active preview rather than silently taking it over.
- [ ] Create the immutable run snapshot before applying settings or moving.
- [ ] Apply/read back the snapshotted acquisition profile and fail before motion if required settings cannot be applied.
- [ ] In `PREPARING`, move to pose 0 and settle; enter `RUNNING` and establish the monotonic/UTC timing anchors immediately before shutter 0.
- [ ] After shot `i` is durably published, pause-check, move to pose `i+1`, settle, then wait for its eligible shutter time and capture. Never move while capture/download is active.
- [ ] Use monotonic time for waits and UTC for records. For shot `i`, nominal shutter time is `shot0_started + i*interval`; earliest shutter is also no earlier than the previous actual shutter start plus interval.
- [ ] Never catch up in bursts. Persist each shot's delay from nominal time and the run's maximum/current accumulated delay.
- [ ] Add pause/resume/cancel checkpoints before movement, after movement, after settle, before shutter, and after publication. Pause requested during a blocking hardware call takes effect at the next checkpoint.
- [ ] End as `COMPLETED` or `COMPLETED_WITH_GAPS`; reserve `ERROR` for a terminal engine/storage condition.
- [ ] Emit coordinator and active-run progress through SSE without embedding image bytes; REST remains the refresh/reconnect source of truth.
- [ ] Make global stop cancel the run before sending motor `X`; do not delete completed artifacts.
- [ ] Delete `TimelapseEngine`, `TimelapseConfig`, `/api/timelapse/*`, their tests, and their documentation in this task. Do not add aliases, deprecation responses, or compatibility adapters.

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
- A long exposure or slow move increases shutter schedule delay but never causes rapid catch-up captures or motor motion during exposure.
- Manual controls, test shots, preview, and dry runs cannot take hardware ownership while a run is active.

## Not in this task

- Automatic retries beyond a single clean attempt; task 12 adds detailed policy.
- Restart continuation.
- Final monitoring/history screens.

## Implementation notes

- Record measured hardware timing and any camera readback limitations here.
