# Task 12 — Failure Policy and Restart Handling

## Goal

Make long unattended runs leave useful, truthful records when camera, storage, transport, or backend failures occur.

## Prerequisites

- Task 11 recording engine.

## Checklist

- [ ] Separate movement, shutter, download, preview generation, and persistence phases in attempt records.
- [ ] Apply three total attempts with a two-second delay to camera/download/storage phases.
- [ ] When the camera returned a file path but transfer failed, retry transfer of that file before triggering another exposure where supported.
- [ ] After exhausted camera/download failures, publish a `GAP` shot and continue with minimum interval spacing.
- [ ] Treat failed preview generation as a warning when a valid original is safely persisted; do not recapture solely for a thumbnail.
- [ ] Retry serial transport failures, then pause with an uncertain-coordinate error instead of continuing commands.
- [ ] Require coordinate reconfirmation before resuming from uncertain motor state; keep already persisted shot indices immutable.
- [ ] Detect low/failed storage before capture where practical and record exact stage/error details.
- [ ] On startup, scan runs and change unfinished states to `INTERRUPTED`, append a recovery event, and release no automatic hardware command.
- [ ] Add deterministic failure controls to `FakeCameraManager`; use test-only serial/storage/media stubs or monkeypatching for the remaining automated fault cases.
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
- Retrying an ambiguous shutter operation does not silently overwrite an artifact; possible duplicate camera captures are recorded.
- A storage failure cannot cause the engine to advance while falsely claiming durability.
- Restart recovery is observational only and sends no hardware commands.

## Not in this task

- Automatic continuation of interrupted runs.
- Mechanical collision/stall detection.
- Remote notifications outside the current UI/API.

## Implementation notes

- Record actual gphoto transfer-retry behavior and any unavoidable ambiguity here.
