# Task 09 — Browser Planning Workspace

## Goal

Connect the independently tested planning capabilities into one phone-friendly workflow without introducing a frontend build system.

## Prerequisites

- Tasks 04 through 08.

## Checklist

- [ ] Add plan list/create/open/rename controls while preserving quick access to existing manual motor controls.
- [ ] Add a plan editor for shot count, interval, settle time, fixed acquisition settings, and preview settings.
- [ ] Allow saving current motor pose as a start, end, or intermediate keyframe.
- [ ] Allow keyframe reorder/delete/label, normalized progress editing, outgoing linear/smooth selection, and tangent-scale adjustment.
- [ ] Render pan and tilt against shot/progress with lightweight browser-native SVG or canvas; do not add a chart framework.
- [ ] Show calculated duration, maximum angular step, validation failures, current plan revision, coordinate-reference state, and dry-run validity.
- [ ] Let the user visit a selected keyframe through the validated motor API.
- [ ] Integrate enhanced live view, its measured status, and the slower test-shot fallback.
- [ ] Show persistent test-shot thumbnails and metadata.
- [ ] Add full dry-run start/progress/cancel and a visible warning/confirmation when recording would use a missing or stale report.
- [ ] Prevent stale-revision overwrites and offer reload rather than discarding another browser's edit.
- [ ] Keep controls usable on phone, tablet, and desktop and preserve global stop access.

## Local integration check

With the fake camera selected and either the real motor controller or a future external serial emulator connected: create a plan, add four keyframes from motor positions, mix transitions, change schedule/acquisition, inspect samples, run/cancel/re-run a dry run, take test shots, reload the page, and reopen all persisted data. Without a serial peer, verify only the non-motor planning and camera portions and leave the motor workflow unverified.

## Hardware field check

- [ ] Complete the setup from a phone on the same network without touching camera/head after initial physical setup.
- [ ] Confirm zero and limits, compose through live view, visit/save keyframes, and take acquisition test shots.
- [ ] Complete a full dry run and inspect the validity indicator.
- [ ] Refresh/reconnect the browser and verify the plan and dry-run state recover.

## Acceptance criteria

- The user can complete planning without using `/docs` or editing JSON.
- Every destructive plan action is explicit; routine edits do not lose persisted media.
- Hardware-busy, offline, stale-reference, validation, and capture errors are visible near the affected control.
- Existing dark style and zero-build frontend approach remain intact.

## Not in this task

- Starting the new durable recording engine.
- Historical run browsing.
- Sophisticated 2D scene visualization or Bézier handles.

## Implementation notes

- Record manual device/browser coverage and any UI compromises here.
