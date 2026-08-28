#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$ROOT/backend/.venv" ]]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi

export PYTHONPATH="$ROOT/backend"
"$ROOT/backend/.venv/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir "$ROOT/backend" &
API_PID=$!
trap 'kill $API_PID' EXIT

cd "$ROOT/frontend"
npm run dev -- --hostname 0.0.0.0 --port 3000
