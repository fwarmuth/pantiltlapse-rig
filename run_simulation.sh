#!/usr/bin/env bash
# Runs the PanTiltLapse backend and frontend locally in full SIMULATION mode.
# No physical Arduino or Raspberry Pi camera required.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export SIMULATION=true

echo "=========================================================="
echo " Starting PanTiltLapse in Simulation Mode"
echo " Simulated Serial: FakeSerialManager (Pan & Tilt mock motors)"
echo " Simulated Camera: FakeCameraManager (Live stream & photos)"
echo " Local URL:        http://localhost:8000"
echo "=========================================================="

exec backend/.venv/bin/uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000
