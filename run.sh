#!/bin/sh
# One command: installs what is missing, builds the UI once, starts everything on :8000.
set -e
cd "$(dirname "$0")"

[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -r backend/requirements.txt
[ -d frontend/dist ] || (cd frontend && npm install && npm run build)

cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
