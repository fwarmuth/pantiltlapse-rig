# Task 02 — Pure Trajectory Engine

## Goal

Convert a validated trajectory and shot count into deterministic motor poses that can be inspected without running hardware.

## Prerequisites

- Task 01 domain models.

## Checklist

- [ ] Add a pure trajectory module with one public sampling function.
- [ ] Generate exactly `total_shots` normalized progress values including `0.0` and `1.0`.
- [ ] Locate the correct keyframe segment for every progress value.
- [ ] Implement linear interpolation per axis.
- [ ] Implement cubic Hermite interpolation with automatic neighboring tangents and per-keyframe tangent scaling as defined by the shared contract.
- [ ] Support mixed linear and smooth outgoing segments in one trajectory.
- [ ] Return pose plus useful derived data such as shot index, normalized progress, active segment, and nearby keyframe IDs.
- [ ] Validate generated tilt targets against supplied rig limits; pan remains unbounded.
- [ ] Derive expected duration and maximum per-shot pan/tilt delta for planning diagnostics.
- [ ] Add tests for two-point, multi-waypoint, mixed-mode, stopped-tangent, reversing, negative-angle, and pan-beyond-360 trajectories.

## Functional check

Add a test fixture that prints or snapshots a small 11-shot path. A developer must be able to inspect every generated pan/tilt value without starting FastAPI.

## Acceptance criteria

- The first and last samples exactly match endpoint poses.
- Linear segments produce expected values within floating-point tolerance.
- Smooth trajectories pass through keyframes that coincide with sample progress and remain deterministic.
- Any generated target outside tilt limits is rejected before hardware use.
- The module has no hardware, storage, FastAPI, or asyncio dependency.

## Not in this task

- A path editor or chart.
- Motor movement or dry runs.
- Persisting samples; they should be regenerated from the plan.
- Collision detection, which is impossible with current hardware.

## Implementation notes

- Record the exact tangent formula in code and here so later models do not reinterpret it.

