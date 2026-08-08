# Task 08 — Enhanced Night-Oriented Live View

## Goal

Provide a measurable, independently stoppable planning feed that improves dark-scene framing without changing the plan's acquisition profile.

## Prerequisites

- Task 06 media/camera refactor.
- This is deliberately a hardware capability task; keep a working fallback when the camera cannot provide useful live view.

## Checklist

- [ ] Perform and document a short Canon 700D/python-gphoto2 spike: preview API used, supported temporary settings, stable frame rate, frame dimensions, and disconnect behavior.
- [ ] Add a `PreviewController` with explicit `IDLE`, `STARTING`, `STREAMING`, and `ERROR` states and exclusive camera ownership.
- [ ] Implement start/status/stop endpoints and one browser-friendly stream mechanism; prefer an MJPEG `StreamingResponse` if the measured gphoto behavior supports it reliably.
- [ ] Apply `PreviewProfile` settings independently of acquisition settings.
- [ ] Add bounded digital gain/gamma enhancement; avoid expensive speculative image processing that misses the requested FPS.
- [ ] Report measured FPS, frame age, dropped/error count, resolution, and active enhancement values.
- [ ] Stop on client cancellation or explicit stop, release camera ownership, and restore the acquisition profile.
- [ ] Provide a clear one-click fallback to a slower plan test shot when live-view signal is insufficient.
- [ ] Implement fake-camera preview frames with controllable darkness so UI/error paths are testable without a camera.
- [ ] Add tests for setting isolation/restoration, exclusive ownership, stream disconnect, repeated start/stop, fake-camera darkness enhancement, and real-camera loss.

## Fake-camera check

Run the feed for several minutes, adjust enhancement, verify changing frames and reported FPS, stop/restart repeatedly, then take a test shot and prove acquisition settings were restored.

## Hardware bench check

- [ ] Measure normal-light baseline FPS and latency for at least two minutes.
- [ ] Measure a dark scene with the fastest useful temporary preview settings.
- [ ] Compare enhancement off/on without claiming detail that is not present in the sensor signal.
- [ ] Disconnect/reconnect USB during preview and verify recoverable error behavior.
- [ ] Stop preview and take a test shot; verify acquisition settings were restored.

## Acceptance criteria

- Preview cannot run concurrently with a test capture or recording capture.
- Acquisition settings in the saved plan are never silently modified by preview controls.
- UI/API exposes actual measured performance rather than promising a fixed FPS.
- If the hardware cannot deliver a useful enhanced feed, the task still delivers honest status and the slower test-shot fallback.

## Not in this task

- Temporal frame stacking, AI denoising, or RAW development.
- Trajectory controls.
- Recording while live view owns the camera.

## Implementation notes

- Record measured Canon 700D results and the chosen stream transport here before marking complete.
