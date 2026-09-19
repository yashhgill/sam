#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SAM — Start Script (run from terminal or SAM.app)
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/.sam_logs"
mkdir -p "$LOG_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[SAM]${NC} $1"; }
warn() { echo -e "${YELLOW}[SAM]${NC} $1"; }
err() { echo -e "${RED}[SAM]${NC} $1"; }

log "Starting SAM..."

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ -f "$JARVIS_DIR/.env" ]; then
    set -a
    source "$JARVIS_DIR/.env"
    set +a
    log "Loaded .env"
else
    warn ".env not found — using defaults"
fi

# ── [0/3] OmniRoute (optional) ────────────────────────────────────────────────
if command -v omniroute &>/dev/null; then
    if ! lsof -i :20128 &>/dev/null; then
        log "Starting OmniRoute on :20128..."
        omniroute serve --port 20128 --no-open --daemon > "$LOG_DIR/omniroute.log" 2>&1 &
        sleep 2
        if curl -sf http://localhost:20128/health &>/dev/null; then
            log "OmniRoute ✓"
        else
            warn "OmniRoute didn't start — using Groq directly"
        fi
    else
        log "OmniRoute already running ✓"
    fi
else
    log "OmniRoute not installed — using Groq directly (that's fine)"
fi

# ── [1/3] Backend ─────────────────────────────────────────────────────────────
if lsof -i :8000 &>/dev/null; then
    warn "Backend already running on :8000"
else
    log "Starting backend..."
    cd "$JARVIS_DIR/backend"

    # Find Python
    PYTHON=""
    for p in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$p" &>/dev/null; then
            PYTHON="$p"
            break
        fi
    done

    if [ -z "$PYTHON" ]; then
        err "Python 3 not found! Install from https://python.org"
        exit 1
    fi

    # Install deps if needed
    if ! "$PYTHON" -c "import fastapi, groq, ddgs" 2>/dev/null; then
        log "Installing Python dependencies..."
        "$PYTHON" -m pip install -r requirements.txt -q
    fi

    "$PYTHON" -m uvicorn main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --log-level warning \
        > "$LOG_DIR/backend.log" 2>&1 &

    echo $! > "$LOG_DIR/backend.pid"

    # Wait for backend to be ready
    log "Waiting for backend..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:8000/health &>/dev/null; then
            log "Backend ready ✓ → http://localhost:8000"
            break
        fi
        sleep 0.5
    done
fi

# ── [2/3] Frontend ────────────────────────────────────────────────────────────
if lsof -i :5173 &>/dev/null || lsof -i :5174 &>/dev/null; then
    warn "Frontend already running"
else
    log "Starting frontend..."
    cd "$JARVIS_DIR/frontend"

    if ! command -v node &>/dev/null; then
        err "Node.js not found! Install from https://nodejs.org"
        warn "SAM will work without the frontend — use http://localhost:8000 as API"
    else
        if [ ! -d "node_modules" ]; then
            log "Installing npm dependencies (first time)..."
            npm install -q
        fi

        npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
        echo $! > "$LOG_DIR/frontend.pid"

        # Wait for frontend
        for i in $(seq 1 20); do
            if curl -sf http://localhost:5173 &>/dev/null || curl -sf http://localhost:5174 &>/dev/null; then
                log "Frontend ready ✓ → http://localhost:5173"
                break
            fi
            sleep 0.5
        done
    fi
fi

echo ""
log "════════════════════════════════════"
log "  SAM is online! 🤖"
log ""
log "  Chat:    http://localhost:5173"
log "  API:     http://localhost:8000"
log "  Logs:    $LOG_DIR"
log ""
log "  Stop:    bash scripts/stop-sam.sh"
log "════════════════════════════════════"

# Open browser
sleep 1
if curl -sf http://localhost:5173 &>/dev/null; then
    open http://localhost:5173 2>/dev/null || true
elif curl -sf http://localhost:5174 &>/dev/null; then
    open http://localhost:5174 2>/dev/null || true
fi
