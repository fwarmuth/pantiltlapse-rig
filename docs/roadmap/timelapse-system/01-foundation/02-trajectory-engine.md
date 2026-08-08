# Task 02 — Pure Trajectory Engine

## Goal

Convert a validated trajectory and shot count into deterministic motor poses that can be inspected without running hardware.

## Prerequisites

- Task 01 domain models.

## Checklist

- [x] Add a pure trajectory module with one public sampling function.
- [x] Generate exactly `total_shots` normalized progress values including `0.0` and `1.0`.
- [x] Locate the correct keyframe segment for every progress value.
- [x] Implement linear interpolation per axis.
- [x] Implement cubic Hermite interpolation with automatic neighboring tangents and per-keyframe tangent scaling as defined by the shared contract.
- [x] Support mixed linear and smooth outgoing segments in one trajectory.
- [x] Return pose plus useful derived data such as shot index, normalized progress, active segment, and nearby keyframe IDs.
- [x] Validate generated tilt targets against supplied rig limits; pan remains unbounded.
- [x] Derive expected duration and maximum per-shot pan/tilt delta for planning diagnostics.
- [x] Add tests for two-point, multi-waypoint, mixed-mode, stopped-tangent, reversing, negative-angle, and pan-beyond-360 trajectories.

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

- Created `backend/domain/trajectory.py` with `sample_trajectory()`.
- Tangent calculation formula:
  - Interior keyframes: $D_j = \frac{P_{j+1} - P_{j-1}}{p_{j+1} - p_{j-1}} \cdot \text{tangent\_scale}_j$
  - Endpoints: forward/backward differences scaled by `tangent_scale`.
- Hermite Basis: $h_{00} = 2u^3 - 3u^2 + 1$, $h_{10} = u^3 - 2u^2 + u$, $h_{01} = -2u^3 + 3u^2$, $h_{11} = u^3 - u^2$.
- Tests added in `backend/tests/test_trajectory_engine.py`.

