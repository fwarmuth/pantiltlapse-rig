# Task 05 — Rig Limits and Coordinate Reference

## Goal

Add the minimum truthful safety state required before reusable plans can command open-loop hardware.

## Prerequisites

- Tasks 00 and 04.

## Checklist

- [ ] Add persistent rig configuration containing required `tilt_min_deg` and `tilt_max_deg`; pan bounds remain `null`/unbounded.
- [ ] Add runtime coordinate-reference state with UUID, creation reason/time, and operator-confirmed flag/time.
- [ ] Create a new unconfirmed coordinate reference on backend startup and every driver disable or enable operation.
- [ ] Add endpoints to read rig/setup status, update tilt limits while no automated operation is active, and confirm the physical zero.
- [ ] Put one bounds-check function in the motor-command path so manual, sequence-step, dry-run, and future run moves cannot bypass it.
- [ ] Reject planned absolute moves until the coordinate reference is confirmed; keep emergency stop and driver operations available.
- [ ] Include rig limits and coordinate-reference status in SSE/status data.
- [ ] Return clear `409` errors for unconfirmed reference and `422` for out-of-bounds tilt targets.
- [ ] Add unit tests for startup invalidation, confirmation, driver-cycle invalidation, bounded tilt, and unbounded multi-rotation pan; spy on serial writes rather than adding a runtime motor mock.
- [ ] Update hardware/protocol documentation to state that limits are backend-enforced and not firmware endstops.

## Automated check

With a test-only serial spy, confirm zero and request pan `720°` within valid tilt. Assert the correct real protocol command would be sent. Attempt moves below and above configured tilt bounds and assert no serial command is emitted. Toggle drivers and verify planned motion is blocked until reconfirmed.

## Hardware bench check

- [ ] Establish a safe physical zero with motor power immediately accessible.
- [ ] Configure conservative tilt bounds inside the real mechanical limits.
- [ ] Verify valid moves at both configured tilt edges.
- [ ] Verify an out-of-bounds API request causes no serial `M` command.
- [ ] Verify a driver toggle invalidates coordinate confirmation.

## Acceptance criteria

- Every backend route that commands an absolute motor target uses the common check.
- Manual relative movement calculates and validates its absolute target before changing internal telemetry.
- No test assumes that firmware can detect collision, stall, or lost steps.
- Existing emergency stop remains callable regardless of setup state.

## Not in this task

- Homing, encoders, endstops, or firmware travel limits.
- Dry-run execution.
- A polished setup UI; API/docs controls are sufficient.

## Implementation notes

- Record the real rig tilt values used during bench verification here; do not bake them into tests.
