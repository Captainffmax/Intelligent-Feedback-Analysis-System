#!/usr/bin/env bash
#
# start.sh — bring up the full IFAS stack (MongoDB + backend + admin-dashboard).
#
#   Usage:  ./start.sh            # start everything, wait until healthy
#           ./start.sh stop       # stop backend + dashboard (leaves mongod running)
#
# All Python tooling lives in backend/.venv — there is NO global streamlit/uvicorn.
# Backend model warm-up can take 1-4 min on this machine (low RAM / swap).

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/backend/.venv"
LOGDIR="$ROOT/.run-logs"
mkdir -p "$LOGDIR"

# ---- stop mode -------------------------------------------------------------
if [ "${1:-}" = "stop" ]; then
  for port in 8000 8501; do
    pids=$(lsof -ti:"$port" 2>/dev/null)
    [ -n "$pids" ] && kill $pids 2>/dev/null && echo "stopped service on :$port"
  done
  echo "(mongod left running — stop it with: mongod --dbpath ~/mongo-data --shutdown)"
  exit 0
fi

# ---- 1. MongoDB ------------------------------------------------------------
if pgrep -x mongod >/dev/null; then
  echo "[1/3] MongoDB already running."
else
  echo "[1/3] Starting MongoDB..."
  mkdir -p ~/mongo-data ~/mongo-logs
  mongod --dbpath ~/mongo-data --port 27017 --bind_ip 127.0.0.1 \
         --logpath ~/mongo-logs/mongod.log --fork >/dev/null
fi

# ---- 2. Backend ------------------------------------------------------------
if lsof -ti:8000 >/dev/null 2>&1; then
  echo "[2/3] Backend already running on :8000."
else
  echo "[2/3] Starting backend (models warm up — this can take a few minutes)..."
  ( cd "$ROOT/backend" && \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 \
    >"$LOGDIR/backend.log" 2>&1 & )
  printf "      waiting for /health"
  for _ in $(seq 1 100); do
    if curl -s --max-time 3 http://127.0.0.1:8000/health 2>/dev/null | grep -q '"ai_engine_ready":true'; then
      echo " — ready."; break
    fi
    printf "."; sleep 3
  done
fi

# ---- 3. Admin dashboard ----------------------------------------------------
if lsof -ti:8501 >/dev/null 2>&1; then
  echo "[3/3] Dashboard already running on :8501."
else
  echo "[3/3] Starting Streamlit dashboard..."
  ( cd "$ROOT/admin-dashboard" && \
    "$VENV/bin/streamlit" run app.py --server.port 8501 --server.headless true \
    >"$LOGDIR/streamlit.log" 2>&1 & )
  sleep 4
fi

echo
echo "All up:"
echo "  Dashboard : http://localhost:8501   (login: admin / ChangeMe!2026)"
echo "  Backend   : http://127.0.0.1:8000/docs"
echo "  Logs      : $LOGDIR/{backend,streamlit}.log"
echo
echo "Stop backend + dashboard with:  ./start.sh stop"
