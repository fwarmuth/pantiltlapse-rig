# Development Roadmap & Verification Checklist

## Phase 1: Monorepo Foundation & Motor Testing UI (Completed)
- [x] Create project layout and LLM documentation (`docs/`)
- [x] Define ESP/NodeMCU motor serial protocol details
- [x] Create PlatformIO NodeMCU firmware v1.0.4 with 16x microstepping
- [x] Build Python FastAPI backend with Async Serial Manager & Interactive CLI
- [x] Build modern lightweight Web UI for manual motor jogging & status monitoring
- [x] **Verification Point 1**: Test manual Pan/Tilt motor controls from web interface & CLI (Verified on live hardware)

## Phase 2: Camera Integration & Exposure Sync (Completed)
- [x] Implement native camera trigger module (`python-gphoto2` persistent session for Canon EOS 700D)
- [x] Add shutter release delay (0.5s settle time) & USB RAM photo download preview
- [x] **Verification Point 2**: Execute single step "Move -> Pause -> Shoot -> Confirm" test via Web UI (Verified on live hardware)

## Phase 3: Time-lapse Engine & Sequence Planning (Completed)
- [x] Implement event-driven time-lapse state machine in Backend (`TimelapseEngine`)
- [x] Define session data model (Start Pos A, End Pos B, Shot Count, Interval, Settle Time)
- [x] Web UI Time-lapse sequence setup wizard & live progress dashboard
- [x] **Verification Point 3**: Complete full automated time-lapse run (Verified on live hardware)

## Phase 4: Motion Easing & Mobile API Polish (Completed)
- [x] Smooth motion easing curves (Ease-In-Out, Linear, S-curve)
- [x] Real-time Server-Sent Events (SSE) streaming API (`GET /api/events`)
- [x] Mobile-friendly responsive UI & touch optimization
