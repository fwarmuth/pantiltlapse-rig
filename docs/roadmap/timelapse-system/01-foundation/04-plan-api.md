# Task 04 — Plan CRUD and Trajectory API

## Goal

Expose persistent plans and calculated path samples through FastAPI while preserving all existing endpoints.

## Prerequisites

- Tasks 01, 02, and 03.

## Checklist

- [x] Construct one plan store during application startup and inject/pass it directly to short route handlers.
- [x] Add `POST /api/plans`, `GET /api/plans`, `GET /api/plans/{id}`, `PUT /api/plans/{id}`, and `DELETE /api/plans/{id}`.
- [x] Require the caller's current revision on update and return `409` for stale edits.
- [x] Add `GET /api/plans/{id}/trajectory` returning generated shot poses, expected duration, maximum angular deltas, validation errors, and warnings.
- [x] Keep list responses compact; load full trajectory/keyframe data only in plan detail.
- [x] Use the shared JSON error envelope and documented status codes.
- [x] Add FastAPI tests using a temporary output root.
- [x] Update the API protocol document with the additive endpoints.

## Functional check

Using `/docs` or `curl`, create a plan, retrieve it, update a waypoint, inspect generated trajectory samples, restart the backend, and retrieve the same updated plan.

## Acceptance criteria

- Concurrent/stale updates cannot silently overwrite a newer plan revision.
- API trajectory samples exactly match direct trajectory-module results.
- Invalid plans and missing resources return intentional errors.
- The current UI, motor routes, camera routes, and old time-lapse routes remain operational.

## Not in this task

- Plan editing UI.
- Dry-run, live-view, test-shot, or recording endpoints.
- Deleting historical runs when a plan is deleted.

## Implementation notes

- Created endpoints in `backend/main.py`:
  - `POST /api/plans`: Returns `201 Created` with created `SequencePlan`.
  - `GET /api/plans`: Returns compact plan summaries list.
  - `GET /api/plans/{plan_id}`: Returns full `SequencePlan`.
  - `PUT /api/plans/{plan_id}`: Validates request revision against stored revision, returning HTTP `409 Conflict` on mismatch.
  - `DELETE /api/plans/{plan_id}`: Deletes plan directory.
  - `GET /api/plans/{plan_id}/trajectory`: Samples trajectory poses and returns `TrajectorySamplingResult`.
- Unit & integration tests added in `backend/tests/test_plan_api.py`.

