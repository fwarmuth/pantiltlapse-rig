# Shared Timelapse Contract

All roadmap tasks must follow this contract. Change it only through an explicit design decision recorded here and in every affected task.

## Architectural boundaries

- Pydantic models own validation and JSON serialization; they do not access hardware or the filesystem.
- The trajectory module is a pure calculation module; it does not import FastAPI, storage, motors, or cameras.
- Storage receives and returns domain models; it does not execute a run.
- Hardware managers perform individual motor or camera operations; they do not decide sequence policy.
- The operation coordinator enforces the explicit concurrency matrix below; routes must not bypass it.
- FastAPI route handlers validate, delegate, and translate known errors to HTTP responses.

## Simulation boundaries

- Production motor control has one path: `SerialManager` talks to a serial endpoint using the real firmware protocol. Do not add motor mock flags or simulation branches throughout the backend.
- If actuator simulation is needed, build it as a separate optional subproject that opens/emulates a serial endpoint, implements the ESP protocol, and visualizes actuator state. The backend must treat it exactly like the physical controller.
- Camera selection is the one intentional backend simulation seam. An explicit setting selects either the gphoto-backed `CameraManager` or a `FakeCameraManager` with realistic delays and placeholder image artifacts.
- Never fall back silently from the real camera to the fake camera. Connection failure in real-camera mode remains a visible hardware error.
- Unit tests may use narrow stubs, spies, monkeypatching, and temporary files to isolate policy. These are test-only aids, not runtime modes or new abstraction layers.

## Canonical concepts

### Sequence plan

An editable, reusable `SequencePlan` contains:

- `schema_version`, UUID `id`, integer `revision`, name and description.
- UTC `created_at` and `updated_at` timestamps.
- A `Trajectory`, `Schedule`, `AcquisitionProfile`, and `PreviewProfile`.
- A capture retry policy of three total attempts with a two-second delay by default.

Saving a material plan change increments `revision`. Cosmetic display state is not part of the plan.

### Trajectory

- A `Pose` is absolute `pan_deg` and `tilt_deg` in the current operator-established coordinate frame.
- Pan values are unwrapped and unbounded; `370°` is distinct from `10°`.
- Tilt is bounded by the current rig configuration.
- Keyframe progress uses `0.0..1.0`, is strictly increasing, and includes exact endpoints `0.0` and `1.0`.
- A keyframe has a label, pose, `outgoing_mode: linear | smooth`, and `tangent_scale: 0.0..1.0`.
- The trajectory generator returns exactly `total_shots` poses, including the first and last poses.
- Smooth segments use cubic Hermite interpolation with neighboring automatic tangents. `tangent_scale=0` eases to a stop at that keyframe; `1` flows through it.
- Preview, dry run, and recording must call the same generator.

### Schedule and acquisition

- Canonical schedule inputs are `total_shots`, shutter-start-to-shutter-start `interval_s`, and `settle_time_s`.
- Before shot 0, move to the first pose and settle while the run is `PREPARING`; start the run clock when shot 0 begins capture.
- After each capture completes, move and settle at the next pose, then wait until the next eligible shutter time. Motors never move during an exposure.
- The interval is minimum shutter spacing. An overrun shifts later starts; the engine never creates catch-up bursts.
- Acquisition settings are fixed for a run. ISO, shutter, aperture, camera format, and camera-specific settings remain strings/JSON values supported by the camera.
- Preview settings are separate and must be restored to acquisition settings before a test shot or recording.

### Coordinate reference and limits

- Startup and every driver disable/enable cycle create a new in-memory coordinate-reference UUID.
- Planned motion requires the operator to confirm the current physical zero/reference.
- Changing the reference or plan revision makes a previous dry-run report stale.
- Pan has no configured travel limit. Tilt minimum and maximum are required setup values.
- All manual, dry-run, and recording targets pass through the same backend bounds check.
- There are no encoders, endstops, or stall detection. Firmware `DONE` means commanded steps were emitted, not that physical motion succeeded.

### Operation concurrency

- `PREVIEW` may coexist with manual jogs and a `DRY_RUN` of the same plan, allowing the operator to watch a rehearsal.
- `DRY_RUN` blocks manual moves, driver changes, rig-limit changes, test shots, and recording.
- `RECORDING` is exclusive and blocks preview, dry run, manual camera/motor actions, driver changes, and rig-limit changes.
- Starting a recording stops preview first, restores/applies the snapshotted acquisition profile, then acquires recording ownership.
- Test shots use the persisted plan acquisition profile plus any explicit test-only override, record the plan revision/effective settings, and require preview/dry run/recording to be inactive.
- Global motor stop remains callable in every state and also cancels the active dry run or recording task before sending `X`.

### Runs and shots

- Starting a run writes an immutable plan and rig snapshot before moving hardware.
- Run states are `PREPARING`, `RUNNING`, `PAUSED`, `COMPLETED`, `COMPLETED_WITH_GAPS`, `CANCELLED`, `ERROR`, and `INTERRUPTED`.
- A shot records intended/reported pose, scheduled/actual timing, schedule delay, requested/observed settings, attempt history, errors, and artifacts.
- Camera/download/storage operations receive three total attempts. Exhaustion records a gap and continues.
- Exhausted serial transport failures pause the run because software position is uncertain.
- A process restart changes an unfinished run to `INTERRUPTED`; v1 never resumes automatically.

## Durable directory layout

```text
output/
  plans/<plan-id>/
    plan.json
    test-shots/<test-shot-id>/
      original.<camera-extension>
      preview.jpg
      metadata.json

  runs/YYYY/MM/DD/<timestamp>-<slug>-<run-id>/
    run.json
    events.jsonl
    shots/000001/
      original.<camera-extension>
      preview.jpg
      shot.json
```

- JSON manifests are written atomically using a temporary sibling and `os.replace`.
- Event records are newline-delimited JSON and appended after each meaningful state transition.
- API responses expose artifact IDs or relative paths, never absolute host paths.
- The filesystem is the source of truth. Do not introduce SQLite in these tasks.
- Original camera extensions and bytes are preserved. Browser previews are distinct artifacts and must never be RAW/SVG bytes mislabeled as JPEG.

## Error and change rules

- Validation failures return `422` or an intentional `400`. Use the established FastAPI shape `{"detail":{"status":"ERROR","message":"..."}}` consistently.
- Missing resources return `404`, state/ownership conflicts `409`, and hardware/I/O unavailability `503`.
- Task 00 intentionally replaces the existing `MOCK_MODE` and silent hardware fallback.
- The current frontend no longer consumes `/api/timelapse/*`. Task 11 removes the legacy engine/routes when the durable run API becomes available; do not keep two schedulers alive.
- Backward compatibility is not required. When an API, schema, or file layout is replaced, remove the old implementation and update the current frontend, tests, and documentation in the same task.
- Do not build migration loaders for old development manifests. Incompatible local development data may be moved aside manually, but code must never delete user media automatically.
- Do not change firmware unless a task explicitly says so.

## Global exclusions for v1

- Exposure ramping or automatic exposure policy.
- Video rendering, cloud synchronization, or remote accounts.
- Encoder/stall detection or automatic homing.
- Bézier handles and manual tangent vectors.
- Automatic continuation after a backend restart.
