# Task 10B — Immutable Run Snapshots and Storage

## Goal

Create a durable run directory and immutable execution snapshot before introducing hardware execution.

## Prerequisites

- Tasks 03, 04, and 10A.

## Checklist

- [ ] Add a focused `RunStore` rooted at configurable `output/runs`; keep `PlanStore` behavior separate.
- [ ] Implement run creation, read, atomic mutable-summary update, lightweight list, event append/read, shot publication/read, and artifact lookup.
- [ ] Accept an already-built `RunSnapshot`; storage must not query plans, hardware, or cameras.
- [ ] Use the canonical date/slug/UUID directory layout without trusting the display name as a path.
- [ ] Write the initial `PREPARING` manifest atomically before returning success.
- [ ] Persist and verify the Task 10A canonical snapshot hash on every run read; report mismatch as corruption without rewriting evidence.
- [ ] Add shot-directory staging and atomic publication of `shot.json` plus available artifacts.
- [ ] Append typed `RunEvent` JSONL records with strictly increasing sequence numbers and fsync each append.
- [ ] Calculate summary counters from persisted shot records or update them consistently after shot publication.
- [ ] Resolve artifacts from their persisted manifest records using IDs/relative paths only; validate containment inside that run directory.
- [ ] On store initialization, identify orphan `.tmp_*` shot directories as incomplete diagnostics but do not publish or delete them automatically.
- [ ] Add tests for duplicate names, unusual characters, interrupted shot staging, event ordering, snapshot immutability, restart/reload, and date-tree scanning.

## Functional check

Without motors or cameras, provide a prepared snapshot, publish one synthetic success and one synthetic gap, recreate `RunStore`, and inspect `run.json`, `events.jsonl`, and both shot directories.

## Acceptance criteria

- Editing/deleting the source plan cannot change or remove the run snapshot.
- A run is discoverable immediately after its initial manifest is written.
- Incomplete staged shots are distinguishable from completed shots after restart.
- Storage code does not create snapshots or decide movement, retry, timing, or restart policy.

## Not in this task

- Starting motors or triggering cameras.
- A public start-run endpoint.
- Restart state conversion or retry behavior.
- History UI.

## Implementation notes

- Record snapshot hashing and atomic shot-publication details here.
