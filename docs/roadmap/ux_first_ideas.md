# UX Feedback and Safety Milestone

## Summary

Rework the current single-column page into a phone-first responsive dashboard with integrated Motion, Camera, and Time-lapse cards. Prioritize trustworthy status, safe control locking, visible errors, and diagnostics without changing firmware.

## Key Changes

- Use a two-column layout on tablets/desktop and one column on phones; integrate telemetry into its related control card.
- Add a sticky health bar for backend transport, motor, camera, hardware/mock/fallback mode, and current operation.
- Add a persistent mobile action strip containing global Stop, operation state, and a console button with an unseen-error badge.
- Replace the time-lapse setup card with progress controls while running; restore setup with the final state after completion/cancellation.
- During a time-lapse, disable all manual motor and camera controls; retain pause/resume, cancel, global Stop, and diagnostics.
- Rename Home to “Go to 0°”; require confirmation before disabling drivers and warn that doing so resets the coordinate reference.
- Show per-action busy states, inline contextual errors, and toasts for failures and meaningful actions. Routine jog moves only update state/activity to avoid notification noise.
- Centralize frontend requests so every action consistently handles HTTP failures, logs its result, and restores controls.
- Add a collapsible console with `Unified`, `Activity`, and `System` views, level filtering, timestamps, sources, expandable traces, and auto-scroll.
- Keep browser activity in memory for the page lifetime. Keep up to 500 backend log records in a thread-safe memory buffer; no disk persistence.
- Expose `GET /api/logs?after_id=<id>&limit=<1..500>` returning:
  `{"entries":[{"id","timestamp","level","source","message","trace"}],"latest_id":n}`.
  The frontend loads recent history and polls incrementally once per second.
- Preserve existing status fields and add `mode: "hardware" | "mock" | "fallback"` plus `fallback_reason`; add camera operation state so other clients can see captures in progress.
- Convert action failures to appropriate HTTP responses with `{"status":"ERROR","detail":"..."}`: validation/unsupported input `4xx`, state conflicts `409`, and hardware/I/O failures `503`. Abort a sequence step if movement fails.
- Update the compact protocol documentation for the additive status fields, log endpoint, and error contract.

## Test Plan

- Backend tests: explicit mock versus hardware fallback, fallback reasons, action error status/envelope, invalid time-lapse transitions, sequence-step abort, camera busy state, bounded log history, incremental log retrieval, and trace serialization.
- UI scenarios: phone/tablet/desktop layouts; hardware/mock/fallback/offline states; request errors; SSE-to-polling fallback; action locking; driver confirmation; delayed Stop messaging; run/setup card transitions; console views, filters, badge, and reconnection.
- Accessibility checks: keyboard focus, 44 px minimum touch targets, visible focus states, dialog labeling, and `aria-live` feedback.
- Verification: Ruff, Python compilation, backend tests, JavaScript syntax check, `uv sync`, and `pio run`.

## Assumptions

- No firmware or serial-protocol changes.
- Stop remains best-effort and may wait for a synchronous firmware move; the UI must state this while pending.
- Existing dark visual style stays; this milestone changes layout and state communication, not branding.
- Aperture, settle-time controls, presets, path previews, homing, limits, PWA support, and persistent logs remain future milestones.
