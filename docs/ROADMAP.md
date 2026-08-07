# Development Roadmap & Verification Checklist

## Phase 1: Monorepo Foundation & Motor Testing UI (Current Phase)
- [x] Create project layout and LLM documentation (`docs/`)
- [ ] Define ESP32 motor serial protocol details
- [ ] Create minimal ESP32 firmware (or mock serial backend for testing UI)
- [ ] Build Python FastAPI backend with Async Serial Manager
- [ ] Build modern lightweight Web UI for manual motor jogging & status monitoring
- [ ] **Verification Point 1**: Test manual Pan/Tilt motor controls from web interface

## Phase 2: Camera Integration & Exposure Sync
- [ ] Implement camera trigger module (gphoto2 or GPIO shutter interface)
- [ ] Add shutter release delay & exposure completion confirmation
- [ ] **Verification Point 2**: Execute single step "Move -> Pause -> Shoot -> Confirm" test

## Phase 3: Time-lapse Engine & Sequence Planning
- [ ] Implement event-driven time-lapse state machine in Backend
- [ ] Define session data model (Start Pos, End Pos, Shot Count, Interval, Exposure Wait Time)
- [ ] Web UI Time-lapse sequence setup wizard & live progress dashboard
- [ ] **Verification Point 3**: Complete full automated time-lapse run

## Phase 4: User-Defined Functions, Presets & Mobile API Polish
- [ ] Save & load movement presets / keyframes
- [ ] Smooth easing curves (Linear, Ease-In-Out, S-curve)
- [ ] Mobile-friendly app readiness (REST + WebSockets / SSE for real-time status)
