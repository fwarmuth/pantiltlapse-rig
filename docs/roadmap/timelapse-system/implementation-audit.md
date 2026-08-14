# Implementation Audit after Task 09

Audit date: 2026-08-08.

## Verified baseline

- All 38 backend tests pass.
- Ruff and Python compilation pass.
- Frontend JavaScript syntax passes.
- NodeMCU firmware builds successfully with PlatformIO.
- Tasks 00–09 provide useful, runnable vertical slices and should not be discarded.
- The test run emits three non-blocking deprecation warnings: the Starlette TestClient/httpx compatibility shim and two uses of deprecated `HTTP_422_UNPROCESSABLE_ENTITY` naming.

Passing tests do not yet mean the recording foundation is safe. Several assertions are missing around negative hardware results, persistence, media typing, and cross-operation ownership.

## Findings that affect later tasks

| Area | Current implementation | Impact | Resolution |
|---|---|---|---|
| Run models | `SequenceRun`, `ShotRecord`, `Attempt`, and `Artifact` are minimal placeholders. There is no immutable plan/rig snapshot or phase-level attempt data. | Task 10 storage cannot be implemented safely against the current schema. | Task 10A finalizes the models before Task 10B writes files. |
| Rig limits | Limits are hardcoded during startup and API updates exist only in memory. | Restart can silently restore different safety bounds; dry-run and run snapshots become ambiguous. | Task 09A persists limits atomically and invalidates dry-run validity when changed. |
| Operation ownership | Preview/dry-run coordination exists, but manual routes, driver/limit changes, test shots, and old time-lapse routes bypass it. | Concurrent operations can move the rig or change camera state during rehearsal/recording. | Task 09A applies one documented concurrency matrix at every mutating route. |
| Dry-run truth | The loop ignores a returned motor `ERROR`, records no movement responses, omits rig-limit comparison from stale detection, and is absent from SSE. | A disconnected/failed move can still produce a valid completed report. | Task 09A hardens dry run before its report may authorize recording. |
| Media typing | Test capture forces `original.jpg`; the fake camera writes SVG text into that filename; the real camera does not preserve the camera extension. | RAW/JPEG originals and previews cannot be trusted by run storage or browsers. | Task 09B establishes a shared captured-file/artifact contract. |
| Preview profiles | The controller supports profiles, but the HTTP start route passes only gain, so default profiles are applied/restored rather than the selected plan profiles. | Recording could inherit incorrect settings after live view. | Task 09B makes preview plan-scoped and verifies setting responses/readback. |
| Real preview errors | The real camera manager generates a synthetic frame after gphoto preview failure. | Hardware failure can look like a valid live view. | Task 09B exposes the error; only `FakeCameraManager` generates placeholders. |
| Blocking work | gphoto calls and large media hashing/copying execute directly in async functions. | Long exposures or RAW files can stall SSE and API responsiveness. | Task 09B moves blocking camera/media work off the event loop while preserving serialization. |
| Error envelope | Routes consistently use FastAPI's nested `detail` object, while the old roadmap specified a different envelope. | New APIs could introduce a third shape. | The shared contract now adopts the existing FastAPI shape. |
| Old scheduler | `TimelapseEngine` remains live but the current frontend has no `/api/timelapse/*` references and it does not use the coordinator. | Keeping it beside `RunEngine` permits conflicting untracked runs. | Task 11 deletes the old engine/routes when durable runs land. No compatibility layer is required. |
| Documentation | Architecture, protocol, hardware, and backend README still describe `MOCK_MODE` and omit much of the plan API. | Smaller models and operators receive stale guidance. | Tasks 09A/09B update the sections they change; Task 16 performs the final consistency pass. |
| Dependency warnings | Current tests use a deprecated Starlette/httpx compatibility path and old HTTP 422 constant name. | Not a recording blocker, but future upgrades may break tests. | Task 16 updates the test client dependency/API and replaces deprecated constants after feature work stabilizes. |

## Decisions locked by this refinement

- Preview and dry run may run together; recording is exclusive.
- The interval is measured between shutter starts, not between move-cycle starts.
- The rig prepositions and settles before the first exposure; that preparation is outside recorded duration.
- Originals preserve their real extension and bytes; preview artifacts are separately typed.
- The immutable hash covers only a canonical `RunSnapshot`, not mutable run state.
- Old `/api/timelapse/*` routes and `TimelapseEngine` are deleted unconditionally in Task 11.
- No old API, schema, or development-manifest compatibility is required.
