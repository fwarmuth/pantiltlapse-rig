# Task 10 — Immutable Run Snapshots and Storage

## Goal

Create a durable run directory and immutable execution snapshot before introducing hardware execution.

## Prerequisites

- Tasks 01, 03, and 04.

## Checklist

- [ ] Extend storage with run creation, read, update-summary, list, event append, and per-shot publication operations.
- [ ] On creation, deep-copy the complete plan and current rig/camera/backend state into the run manifest.
- [ ] Use the canonical date/slug/UUID directory layout without trusting the display name as a path.
- [ ] Write the initial `PREPARING` manifest atomically before returning success.
- [ ] Add an immutable snapshot hash so accidental mutation can be detected in tests and diagnostics.
- [ ] Add shot-directory staging and atomic publication of `shot.json` plus available artifacts.
- [ ] Append structured state events with sequence numbers and UTC timestamps.
- [ ] Calculate summary counters from persisted shot records or update them consistently after shot publication.
- [ ] Add internal APIs/services for artifact lookup using IDs/relative paths only.
- [ ] Add tests for duplicate names, unusual characters, interrupted shot staging, event ordering, snapshot immutability, restart/reload, and date-tree scanning.

## Functional check

Without motors or cameras, create a run snapshot from a plan, publish one synthetic success and one synthetic gap, reload the store, and inspect `run.json`, `events.jsonl`, and both shot directories.

## Acceptance criteria

- Editing/deleting the source plan cannot change or remove the run snapshot.
- A run is discoverable immediately after its initial manifest is written.
- Incomplete staged shots are distinguishable from completed shots after restart.
- Storage code does not decide movement, retry, or timing policy.

## Not in this task

- Starting motors or triggering cameras.
- A public start-run endpoint.
- Restart state conversion or retry behavior.
- History UI.

## Implementation notes

- Record snapshot hashing and atomic shot-publication details here.

