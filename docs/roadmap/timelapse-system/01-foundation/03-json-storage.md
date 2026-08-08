# Task 03 — Atomic JSON Storage

## Goal

Persist plans and generic manifests in a readable directory tree that survives process restarts and partial/corrupt entries.

## Prerequisites

- Task 01 domain models.
- Task 02 is not required.

## Checklist

- [x] Add a storage module rooted at a configurable output directory; default to the existing project `output/` location.
- [x] Implement create, read, update, list, and delete operations for plans.
- [x] Increment plan revision and update `updated_at` on material updates.
- [x] Write JSON through a temporary sibling, flush it, and replace the destination atomically.
- [x] Reject path traversal and never derive paths directly from user-provided names.
- [x] Return domain models rather than raw dictionaries.
- [x] Isolate malformed plan directories during listing: report a warning/error entry without preventing valid plans from loading.
- [x] Add a reusable append-only JSONL event writer for later dry-run and run tasks.
- [x] Use the same storage implementation for real and fake camera artifacts; tests select a temporary output root.
- [x] Add tests for restart/reload, atomic replacement failure, missing IDs, corrupt JSON, duplicate IDs, revision increments, Unicode names, and path traversal attempts.

## Functional check

In a temporary directory, create two plans, update one, restart/recreate the store object, list both, and reload the updated revision. Inspect the generated tree manually.

## Acceptance criteria

- No API or model contains an absolute artifact path.
- A corrupt plan does not hide valid plans.
- Failed replacement leaves either the previous valid manifest or the new valid manifest, never a partially written file.
- Existing `output/captures/` files are untouched.

## Not in this task

- HTTP routes.
- Test-shot or run media copying.
- Database/index creation.
- Automatic schema migration.

## Implementation notes

- Created `backend/storage.py` containing `PlanStore` and `JsonlWriter`.
- Directory layout: `output/plans/<plan_id>/plan.json`.
- Atomic writes: write to `plan.json.tmp.<uuid>`, `f.flush()`, `os.fsync()`, `os.replace()`.
- Path traversal prevention: enforces UUID validation on `plan_id`.
- Unit tests added in `backend/tests/test_json_storage.py`.
