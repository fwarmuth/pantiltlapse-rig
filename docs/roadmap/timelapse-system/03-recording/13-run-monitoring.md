# Task 13 — Live Run Monitoring UI

## Goal

Let the operator detect failures during a long run and safely control it from the existing browser UI.

## Prerequisites

- Tasks 11 and 12.
- The planning UI from task 09.

## Checklist

- [ ] Replace the planning editor with a focused run view while a run owns the hardware; restore the editor after terminal state.
- [ ] Show run identity/state, current shot, success/gap counts, percentage, elapsed time, ETA, next earliest shot, and accumulated schedule delay.
- [ ] Show the latest successful preview and a bounded strip/grid of recent success/gap entries.
- [ ] Make each recent entry reveal intended/reported pose, settings, timestamps, attempts, and errors.
- [ ] Show pause/resume/cancel and persistent global stop; disable unrelated manual, preview, test-shot, plan-edit, and dry-run controls.
- [ ] Display retry activity and distinguish camera gap continuation from serial-error pause.
- [ ] Reconstruct the current view from REST state after page refresh; SSE is an optimization, not the only source of truth.
- [ ] Keep image requests cache-safe and avoid polling originals when thumbnails are available.
- [ ] Show `INTERRUPTED` runs clearly and never offer a misleading automatic resume button.
- [ ] Add accessible live-region announcements for state transitions/errors without announcing every normal frame.

## Local integration check

Use the fake camera plus real hardware or the future external serial emulator to observe a 50-shot run. Refresh/reconnect during it, inject a recovered camera failure and an exhausted gap, then use a test-only serial fault for the paused-state UI scenario. Exercise pause/resume/cancel and inspect the final persisted view.

## Hardware field check

- [ ] Monitor a sequence from a phone for long enough to cover screen sleep/reconnection.
- [ ] Verify thumbnails appear shortly after each downloaded capture.
- [ ] Confirm an intentionally disconnected camera produces visible retry/gap information during the run.
- [ ] Verify unrelated hardware controls remain locked while stop/cancel remain accessible.

## Acceptance criteria

- An operator can identify within one refresh interval whether frames are succeeding, failing, or delayed.
- Reloading the page loses no durable run information.
- The UI never labels a gap or uncertain operation as a captured frame.
- Phone layout keeps state, latest image, and emergency actions readily visible.

## Not in this task

- Browsing arbitrary old runs.
- Push/email notifications.
- Editing an active plan snapshot.

## Implementation notes

- Record manual browser/device checks and refresh latency here.
