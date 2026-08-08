# Task 04 — Plan CRUD and Trajectory API

## Goal

Expose persistent plans and calculated path samples through FastAPI while preserving all existing endpoints.

## Prerequisites

- Tasks 01, 02, and 03.

## Checklist

- [ ] Construct one plan store during application startup and inject/pass it directly to short route handlers.
- [ ] Add `POST /api/plans`, `GET /api/plans`, `GET /api/plans/{id}`, `PUT /api/plans/{id}`, and `DELETE /api/plans/{id}`.
- [ ] Require the caller's current revision on update and return `409` for stale edits.
- [ ] Add `GET /api/plans/{id}/trajectory` returning generated shot poses, expected duration, maximum angular deltas, validation errors, and warnings.
- [ ] Keep list responses compact; load full trajectory/keyframe data only in plan detail.
- [ ] Use the shared JSON error envelope and documented status codes.
- [ ] Add FastAPI tests using a temporary output root.
- [ ] Update the API protocol document with the additive endpoints.

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

- Record final request/response examples here after implementation.

