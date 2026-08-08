# Task 01 — Domain Models

## Goal

Create the validated, serializable vocabulary used by all later planning and recording work without changing existing runtime behavior.

## Prerequisites

- Read `../00-contract.md` and the repository `AGENTS.md`.
- No other roadmap task is required.

## Checklist

- [x] Add `pytest` as a backend development dependency through `uv` if the repository does not already provide it.
- [x] Add a small backend domain-model module; avoid inheritance hierarchies and service abstractions.
- [x] Define enums and Pydantic models for pose, keyframe, trajectory, schedule, acquisition profile, preview profile, retry policy, sequence plan, rig snapshot, artifact, attempt, shot record, dry-run report, and sequence run.
- [x] Use UUIDs, timezone-aware UTC datetimes, `schema_version=1`, and JSON-safe camera-specific metadata.
- [x] Validate strictly increasing keyframe progress and exact `0.0`/`1.0` endpoints.
- [x] Validate positive shot counts/intervals, non-negative settle time, supported transition modes, and tangent scale range.
- [x] Keep pan unbounded. Put tilt limits in the rig model, not the plan.
- [x] Ensure unknown camera metadata can be preserved without weakening validation of canonical fields.
- [x] Add representative plan, run, successful-shot, gap-shot, JPEG artifact, and RAW artifact fixtures.
- [x] Add round-trip tests proving models serialize to JSON and deserialize without semantic changes.
- [x] Document every field whose units or timing meaning could be ambiguous.

## Functional check

Provide a narrow test or development command that constructs the representative plan, prints its JSON, reloads it, and confirms equality. This may be a test rather than a permanent CLI.

## Acceptance criteria

- Invalid endpoint progress, duplicate progress, invalid tangent scale, and invalid schedule values are rejected with useful messages.
- A plan containing extra camera-specific settings and metadata survives a JSON round trip.
- Domain models do not import application managers, FastAPI, or storage modules.
- The existing web UI and time-lapse API behave unchanged.

## Not in this task

- Interpolation calculations.
- Reading or writing plan files.
- New HTTP endpoints or frontend controls.
- Camera or motor changes.

## Implementation notes

- Created `backend/domain/models.py` with Pydantic v2 models.
- Added `pytest`, `pytest-asyncio`, and `httpx` to `[project.optional-dependencies] dev` in `pyproject.toml`.
- Added unit tests in `backend/tests/test_domain_models.py` covering serialization round-tripping, keyframe progress bounds ($0.0$ to $1.0$), strictly increasing progress, schedule constraints, and rig tilt limits ($0.0^\circ$ to $80.0^\circ$).
