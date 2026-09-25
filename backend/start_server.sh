#!/usr/bin/env bash
set -e
cd /home/felix/data/pantiltlapse-rig/backend
export PATH="/home/felix/.cargo/bin:/usr/local/bin:$PATH"
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000
