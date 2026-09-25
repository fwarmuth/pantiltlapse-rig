#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export PATH="/home/felix/.cargo/bin:/usr/local/bin:$PATH"
if [ -f .venv/bin/uvicorn ]; then
    exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
else
    exec uv run --offline uvicorn main:app --host 0.0.0.0 --port 8000
fi
