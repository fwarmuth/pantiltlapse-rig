# Task 12 — Failure Policy and Restart Handling

## Goal

Make long unattended runs leave useful, truthful records when camera, storage, transport, or backend failures occur.

## Prerequisites

- Task 11 recording engine.

## Checklist

- [ ] Persist movement, shutter, download, preview generation, and publication as distinct attempt phases using the Task 10A schema.
- [ ] Apply three total attempts with a two-second delay to camera/download/storage phases.
- [ ] When shutter succeeded and a camera path is known but transfer failed, use an explicit `download_existing` camera operation before considering another shutter. Record when the hardware cannot support this distinction.
- [ ] After exhausted camera/download failures, publish a `GAP` shot and continue with minimum interval spacing.
- [ ] Treat failed preview generation as a warning when a valid original is safely persisted; do not recapture solely for a thumbnail.
- [ ] Use a separate motor retry count fixed at two total command attempts. After exhaustion, invalidate coordinate confirmation and pause with an uncertain-coordinate error instead of continuing.
- [ ] Require coordinate reconfirmation before resuming from uncertain motor state; keep already persisted shot indices immutable.
- [ ] Check estimated free space before run start and current free space before every shutter; treat insufficient space as a terminal paused/error condition, never a capturable gap.
- [ ] On startup, scan runs and change unfinished states to `INTERRUPTED`, append a recovery event, and release no automatic hardware command.
- [ ] Add deterministic failure controls to `FakeCameraManager` for setting, shutter, download, and preview phases; use test-only serial/storage/media stubs for other fault cases.
- [ ] Add tests for failure on each attempt, eventual success, exhausted gap continuation, ambiguous shutter result, preview-only failure, serial pause, persistence failure, and restart interruption.

## Automated fault check

Run the fault matrix with the fake camera and test-only fault stubs. Inspect that shot numbering remains stable, attempts are visible, gaps do not stop later captures, serial errors pause, and a simulated restart yields `INTERRUPTED` without motor/camera calls. Do not add production motor simulation branches to enable these tests.

## Hardware bench check

- [ ] Briefly disconnect/reconnect the camera between shots and inspect retry/gap behavior.
- [ ] Test a safely controlled loss of backend camera access without deleting camera files.
- [ ] Disconnect serial between moves and verify the run pauses instead of commanding later poses.
- [ ] Terminate/restart the backend during an interval and verify the run becomes `INTERRUPTED` without resuming.
- [ ] Do not simulate destructive disk-full conditions on valuable storage; use a controlled small test filesystem if available.

## Acceptance criteria

- Failures are never represented as successful shots.
- An ambiguous shutter result is never blindly retried as though no exposure occurred; it becomes a recorded uncertain/gap attempt unless the camera can identify the produced file.
- A storage failure cannot cause the engine to advance while falsely claiming durability.
- Restart recovery is observational only and sends no hardware commands.

## Not in this task

- Automatic continuation of interrupted runs.
- Mechanical collision/stall detection.
- Remote notifications outside the current UI/API.

## Implementation notes

- Record actual gphoto transfer-retry behavior and any unavoidable ambiguity here.
