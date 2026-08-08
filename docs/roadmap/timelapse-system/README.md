# Timelapse System Implementation Roadmap

This directory turns the timelapse architecture into small, independently verifiable implementation tasks. Each task is intended to fit into one focused coding session and to leave the application runnable when it is complete.

## How to use this roadmap

1. Give a smaller model this file, [`00-contract.md`](00-contract.md), the selected task file, and the repository root `AGENTS.md`.
2. Ask it to implement only that task. Items listed under **Not in this task** are hard scope boundaries.
3. Run the task-specific automated and manual checks before marking it complete.
4. Commit or otherwise checkpoint the working state before beginning the next task.
5. Record discoveries or changed hardware assumptions in the task's **Implementation notes** section rather than silently changing the shared contract.

Suggested handoff prompt for a smaller model:

```text
Implement only Task NN from docs/roadmap/timelapse-system.
Read AGENTS.md, README.md, 00-contract.md, and the selected task completely first.
Inspect the current code before editing and preserve unrelated/user changes.
Treat "Not in this task" as a hard boundary. Complete the narrow automated and
local checks, then report any hardware checks I still need to perform. Mark task
checkboxes only for work actually verified; never infer hardware success from unit tests.
```

When a task is complete, update its checkboxes and implementation notes. Update the milestone checkbox in this README only after the task's acceptance criteria and applicable hardware check have passed.

Status convention:

- `[ ]` not started
- `[~]` in progress
- `[x]` complete and verified
- `[!]` blocked, with the reason written beside it

## Dependency map

```text
Foundation
  00 hardware/simulation boundaries
  01 domain models
    ├── 02 trajectory engine
    └── 03 JSON storage
           └── 04 plan API

Planning tools
  00 + 04 plan API ── 05 rig safety
  00 + 03 JSON storage ── 06 test-shot artifacts
  05 rig safety + 02 trajectory ── 07 dry-run engine
  06 test-shot artifacts ── 08 enhanced live view
  04 + 05 + 06 + 07 + 08 ── 09 planning UI

Recording
  03 + 04 ── 10 run snapshots and storage
  02 + 05 + 06 + 10 ── 11 recording engine
  11 ── 12 failure policy and restart handling
  11 + 12 ── 13 run monitoring UI

Library and migration
  10 + 12 ── 14 history API
  13 + 14 ── 15 history UI
  all completed tasks ── 16 compatibility cleanup and documentation
```

Tasks on different branches of the graph may be implemented in either order. For example, trajectory calculation and JSON persistence only share the domain models and can be developed separately.

## Milestone checkpoints

### A. Persistent planning foundation

- [x] [00 — Hardware and simulation boundaries](01-foundation/00-hardware-boundaries.md)
- [x] [01 — Domain models](01-foundation/01-domain-models.md)
- [x] [02 — Trajectory engine](01-foundation/02-trajectory-engine.md)
- [x] [03 — JSON storage](01-foundation/03-json-storage.md)
- [x] [04 — Plan API](01-foundation/04-plan-api.md)

Checkpoint: create, validate, save, reload, and sample a plan through FastAPI while the existing application still works.

### B. Hardware-testable planning workflow

- [x] [05 — Rig safety and coordinate reference](02-planning/05-rig-safety.md)
- [x] [06 — Test shots and media artifacts](02-planning/06-test-shots.md)
- [x] [07 — Full-path dry run](02-planning/07-dry-run.md)
- [x] [08 — Enhanced live view](02-planning/08-live-view.md)
- [x] [09 — Planning UI](02-planning/09-planning-ui.md)

Checkpoint: build a plan entirely from the browser, inspect night-oriented live view, save test shots, and traverse every planned pose without capturing.

### C. Durable recording

- [ ] [10 — Run snapshots and storage](03-recording/10-run-snapshots.md)
- [ ] [11 — Recording engine](03-recording/11-recording-engine.md)
- [ ] [12 — Failure policy and restart handling](03-recording/12-failure-and-recovery.md)
- [ ] [13 — Run monitoring UI](03-recording/13-run-monitoring.md)

Checkpoint: execute a persistent time-lapse on hardware, observe its frames while it runs, and retain useful evidence after failures or restarts. The fake camera may be used to isolate motor/timing checks.

### D. Browseable library and migration

- [ ] [14 — History API](04-library/14-history-api.md)
- [ ] [15 — History UI](04-library/15-history-ui.md)
- [ ] [16 — Compatibility cleanup](04-library/16-compatibility-cleanup.md)

Checkpoint: browse previous runs and their metadata, then retire the old ephemeral implementation without breaking the documented workflow.

## Verification required after every task

Run the narrow task tests first, followed by the project checks relevant to files changed:

```bash
cd backend
uv run pytest
uv run ruff check .
uv run python -m py_compile main.py serial_manager.py
uv sync

cd ../firmware
pio run
```

For frontend changes also run a JavaScript syntax check and the manual browser scenarios listed by the task. Motor-facing tasks remain hardware-unverified until run against the real controller or a separate serial-protocol emulator. The backend does not provide an actuator mock mode.
