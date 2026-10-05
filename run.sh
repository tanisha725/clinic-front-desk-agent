#!/bin/sh
# One command: installs what is missing, builds the UI once, starts everything on :8000.
set -e
cd "$(dirname "$0")"

[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -r backend/requirements.txt
[ -d frontend/dist ] || (cd frontend && npm install && npm run build)

# Load LLM_API_KEY and friends from .env if the file exists (it is never committed).
if [ -f .env ]; then set -a; . ./.env; set +a; fi

cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
