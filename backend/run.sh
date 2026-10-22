#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
ENV_PATH="${ENV_FILE:-.env}"
if [[ -f "$ENV_PATH" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_PATH"
  set +a
fi
PYTHON="$PWD/.venv/bin/python"
UVICORN="$PWD/.venv/bin/uvicorn"
"$PYTHON" -m app.db migrate
"$PYTHON" -m app.seed --if-empty
exec "$UVICORN" app.main:app --host 0.0.0.0 --port 8000
