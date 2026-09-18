#!/bin/bash
# SAM — Personal AI OS
# Starts OmniRoute (AI proxy), backend (FastAPI), and frontend (Vite)
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OMNIROUTE_PORT=20128

echo "SAM v2.0 — starting up"
echo "=============================="

if [ -f "$ROOT/.env" ]; then
  cp "$ROOT/.env" "$ROOT/backend/.env"
fi

# OmniRoute
echo "[0/3] OmniRoute AI proxy..."
if command -v omniroute &>/dev/null; then
  if lsof -i :$OMNIROUTE_PORT -sTCP:LISTEN -t &>/dev/null; then
    echo "  OmniRoute already running on :$OMNIROUTE_PORT ✓"
  else
    echo "  Starting OmniRoute on :$OMNIROUTE_PORT"
    omniroute serve --port $OMNIROUTE_PORT --no-open --daemon 2>/dev/null || \
    omniroute serve --port $OMNIROUTE_PORT --no-open &
    sleep 2
  fi
else
  echo "  OmniRoute not installed — using Groq directly"
fi

# Backend
echo "[1/3] Starting backend..."
cd "$ROOT/backend"
[ ! -d ".venv" ] && python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q --upgrade
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
echo "[2/3] Starting frontend..."
cd "$ROOT/frontend"
[ ! -d "node_modules" ] && npm install
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=============================="
echo "SAM is running:"
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  OmniRoute: http://localhost:$OMNIROUTE_PORT"
echo "=============================="

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
