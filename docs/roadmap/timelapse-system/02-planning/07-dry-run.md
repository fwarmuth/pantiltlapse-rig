# Task 07 — Full-Path Dry-Run Engine

## Goal

Traverse every planned shot pose without camera capture or interval waits so the operator can inspect clearance and cable behavior.

## Prerequisites

- Tasks 02, 03, 04, and 05.

## Checklist

- [ ] Add a single-operation coordinator/lock shared by manual automated work, dry runs, and later recording.
- [ ] Snapshot plan revision, trajectory samples, rig limits, and coordinate-reference ID when the dry run starts.
- [ ] Reject start when the reference is unconfirmed, another exclusive operation is active, or any generated target is invalid.
- [ ] Move through every generated shot pose in order using the normal absolute motor method.
- [ ] Do not settle, wait the recording interval, apply camera settings, or capture.
- [ ] Expose start, status, and cancel endpoints and include progress in SSE.
- [ ] Persist a `DryRunReport` under the plan containing each commanded pose and result.
- [ ] Mark reports stale when plan revision, limits, or coordinate-reference ID changes.
- [ ] Keep emergency stop available; cancellation must prevent the next move even though current synchronous firmware motion may finish first.
- [ ] Add tests for full pose order, no camera calls, cancellation, operation conflicts, stale reports, limit rejection, and serial error reporting.

## Automated check

Use a test-only serial transport stub with a five-shot and a 100-shot plan. Confirm the dry run emits exactly five and 100 real-protocol move requests, creates no images, reports progress, can be cancelled, and becomes stale after editing a waypoint. This verifies coordinator policy, not hardware behavior.

## Hardware bench check

- [ ] Begin with a small, unobstructed path and external motor power accessible.
- [ ] Observe that the head visits every expected framing position without triggering the camera.
- [ ] Exercise cancel between moves and document the synchronous-stop delay.
- [ ] Run a path with at least one intermediate smooth waypoint and inspect cable/clearance behavior.
- [ ] Change/reconfirm zero and verify the previous report is shown as stale.

## Acceptance criteria

- Dry run and future recording consume the identical sample list for the same plan revision.
- A successful report proves only that commands completed and the operator observed clearance; UI/API wording does not imply encoder verification.
- Recording is allowed without a current successful dry run only after a prominent explicit confirmation warning.

## Not in this task

- Camera operation.
- Interval-accurate rehearsal.
- Automatically starting a recording after a dry run.
- Collision or motor-stall detection.

## Implementation notes

- Record approximate real-hardware duration for representative shot counts.
