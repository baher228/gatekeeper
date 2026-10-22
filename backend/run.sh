#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="$PWD/.venv/bin/python"
UVICORN="$PWD/.venv/bin/uvicorn"
"$PYTHON" -m app.db migrate
"$PYTHON" -m app.seed --if-empty
exec "$UVICORN" app.main:app --host 0.0.0.0 --port 8000
