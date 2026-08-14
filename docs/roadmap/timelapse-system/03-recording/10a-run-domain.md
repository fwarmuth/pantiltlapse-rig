# Task 10A — Finalize the Run Domain

## Goal

Replace the provisional run/shot models with a decision-complete schema before any durable run manifests are written.

## Prerequisites

- Tasks 01, 09A, and 09B.

## Checklist

- [ ] Add string enums for `ShotStatus` (`PENDING`, `SUCCESS`, `GAP`) and attempt phase/status; remove free-form shot status strings.
- [ ] Define `RunSnapshot` as the immutable execution input: complete `SequencePlan`, `RigSnapshot`, confirmed coordinate-reference ID, camera type/model, observed acquisition settings, backend version, firmware/serial status, trajectory samples, and stale-dry-run acknowledgement.
- [ ] Keep mutable `SequenceRun` state separate from `RunSnapshot`; include schema version, IDs, state/timestamps, counters, current/next shot, accumulated delay, and last error.
- [ ] Define snapshot SHA-256 as canonical sorted-key JSON of `RunSnapshot` only. Mutable run fields never affect it.
- [ ] Expand `ShotRecord` with shutter `scheduled_at`, `started_at`, `completed_at`, `schedule_delay_s`, intended/reported pose, requested/observed settings, attempts, artifacts, warnings, and final status.
- [ ] Expand `Attempt` with phase, attempt number, started/completed timestamps, outcome, error type/message, and phase-specific metadata.
- [ ] Expand `Artifact` with role, relative path, MIME type, original camera filename, byte size, SHA-256, and optional extracted metadata.
- [ ] Define `RunEvent` with monotonically increasing sequence number, UTC timestamp, type, severity, message, shot index, and JSON details.
- [ ] Remove or rename the unused provisional `DryRunReport` model so trajectory validation and executed dry-run reports cannot be confused.
- [ ] Validate counters against total shots, timezone-aware timestamps, artifact paths as relative, and immutable snapshot consistency.
- [ ] Add complete JSON fixtures for preparing/running/completed-with-gaps/interrupted runs, successful/gap shots, staged capture attempts, JPEG, and RAW+preview.
- [ ] Add schema round-trip and canonical-hash tests before changing storage.

## Functional check

Build one immutable snapshot and three mutable run-state variants from it. Serialize/reload each, verify one stable snapshot hash, and prove changing mutable counters does not alter the hash while changing any snapshotted plan input does.

## Acceptance criteria

- Task 10B can persist runs without inventing any new domain field.
- Historical UI requirements can be answered from the run, shot, event, and artifact models.
- Models remain independent of FastAPI, filesystem storage, and hardware managers.

## Not in this task

- Run directory creation or APIs.
- Scheduling, movement, capture, or retry execution.
- Loaders or migrations for provisional/development run schemas.

## Implementation notes

- Record canonical hash serialization and final enum values here.
