#!/usr/bin/env bash
#
# deploy.sh — run the full IFAS stack in production mode on this machine.
#
# Unlike start.sh (development, reachable only from this computer), this serves
# the COMPILED student app and binds every service to all network interfaces so
# phones and laptops on the same network can reach them.
#
#   Usage:  ./deploy.sh          # start everything
#           ./deploy.sh stop     # stop the three services (mongod keeps running)
#
# All Python tooling lives in backend/.venv — there is no global uvicorn.

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/backend/.venv"
LOGDIR="$ROOT/.run-logs"
mkdir -p "$LOGDIR"

BACKEND_PORT=8000
DASH_PORT=8501
# 4173 is no longer served separately — the backend serves the compiled app from
# its own origin. Still listed so `stop` cleans up any older run.
LEGACY_APP_PORT=4173

# ---- stop mode -------------------------------------------------------------
if [ "${1:-}" = "stop" ]; then
  for port in "$BACKEND_PORT" "$DASH_PORT" "$LEGACY_APP_PORT"; do
    pids=$(lsof -ti:"$port" 2>/dev/null)
    if [ -n "$pids" ]; then
      kill $pids 2>/dev/null && echo "stopped service on :$port"
    fi
  done
  echo "(mongod left running — stop it with: mongod --dbpath ~/mongo-data --shutdown)"
  exit 0
fi

# Pick this machine's real LAN address. VPN and container interfaces (WARP,
# Tailscale, docker0, ...) also carry private addresses and would otherwise be
# chosen ahead of the Wi-Fi card, so they are excluded by name.
detect_ip() {
  local virt='^(docker|veth|br-|virbr|tun|tap|wg|tailscale|zt|CloudflareWARP|lo)'
  # Prefer the interface carrying the default route, unless it is virtual.
  local dev src
  read -r dev src < <(ip route show default 2>/dev/null | awk '{
      d=""; s="";
      for (i=1; i<=NF; i++) { if ($i=="dev") d=$(i+1); if ($i=="src") s=$(i+1) }
      if (d != "" && s != "") { print d, s; exit }
    }')
  if [ -n "${dev:-}" ] && [ -n "${src:-}" ] && ! [[ $dev =~ $virt ]]; then
    echo "$src"; return
  fi
  # Otherwise take the first global IPv4 on a non-virtual interface.
  ip -o -4 addr show scope global 2>/dev/null | awk -v virt="$virt" '
    $2 !~ virt { split($4, a, "/"); print a[1]; exit }'
}
HOSTIP="$(detect_ip || true)"
[ -z "$HOSTIP" ] && HOSTIP="127.0.0.1"

echo "======================================================"
echo "  IFAS — Production Launcher"
echo "======================================================"
echo

# ---- Pre-flight 1: Python environment --------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  cat <<EOF
[ERROR] Python virtual environment not found at:
        $VENV

  Create it with:
      cd "$ROOT/backend"
      python3 -m venv .venv
      .venv/bin/python -m pip install -r requirements.txt
      .venv/bin/python -m pip install -r ../admin-dashboard/requirements.txt
      .venv/bin/python -m spacy download en_core_web_sm
EOF
  exit 1
fi

for mod in uvicorn streamlit; do
  if ! "$VENV/bin/python" -c "import $mod" 2>/dev/null; then
    echo "[ERROR] $mod is not installed in the virtual environment."
    echo "        Run: $VENV/bin/python -m pip install -r backend/requirements.txt"
    echo "        and: $VENV/bin/python -m pip install -r admin-dashboard/requirements.txt"
    exit 1
  fi
done

# ---- Pre-flight 2: the student app has been built ---------------------------
if [ ! -f "$ROOT/frontend-pwa/dist/index.html" ]; then
  echo "[ERROR] The student app has not been built yet."
  echo "        Run ./build-frontend.sh first, then try again."
  exit 1
fi

# ---- Pre-flight 3: MongoDB --------------------------------------------------
if pgrep -x mongod >/dev/null; then
  echo "[1/3] MongoDB already running."
else
  echo "[1/3] Starting MongoDB..."
  mkdir -p ~/mongo-data ~/mongo-logs
  if ! mongod --dbpath ~/mongo-data --port 27017 --bind_ip 127.0.0.1 \
              --logpath ~/mongo-logs/mongod.log --fork >/dev/null 2>&1; then
    echo "[ERROR] Could not start MongoDB. Check ~/mongo-logs/mongod.log"
    exit 1
  fi
fi

# Launch a service fully detached from this script.
#
#   start_bg <logfile> <workdir> <command...>
#
# `setsid` puts the service in its own session so closing the terminal does not
# kill it, and `exec` replaces the subshell rather than leaving a parent behind.
# The redirections are applied to the SUBSHELL, not just the command: a lingering
# child that still holds this script's stdout keeps the pipe open, so `./deploy.sh
# | tail` would never return to the prompt even once every service was up.
start_bg() {
  local log="$1" dir="$2"
  shift 2
  ( cd "$dir" && exec setsid "$@" ) >"$log" 2>&1 </dev/null &
  disown 2>/dev/null || true
}

# ---- Backend ----------------------------------------------------------------
if lsof -ti:"$BACKEND_PORT" >/dev/null 2>&1; then
  echo "[2/3] Backend already running on :$BACKEND_PORT."
else
  echo "[2/3] Starting backend (AI models warm up — this can take 1-4 minutes)..."
  start_bg "$LOGDIR/backend.log" "$ROOT/backend" \
    "$VENV/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
  printf "      waiting for /health"
  ready=0
  for _ in $(seq 1 100); do
    if curl -s --max-time 3 "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null \
         | grep -q '"ai_engine_ready":true'; then
      echo " — ready."; ready=1; break
    fi
    printf "."; sleep 3
  done
  if [ "$ready" -eq 0 ]; then
    echo
    echo "[WARNING] The backend did not report ready in time."
    echo "          Check the log: $LOGDIR/backend.log"
  fi
fi

# ---- Admin dashboard --------------------------------------------------------
if lsof -ti:"$DASH_PORT" >/dev/null 2>&1; then
  echo "[3/3] Dashboard already running on :$DASH_PORT."
else
  echo "[3/3] Starting the admin dashboard..."
  start_bg "$LOGDIR/streamlit.log" "$ROOT/admin-dashboard" \
    "$VENV/bin/python" -m streamlit run app.py \
      --server.port "$DASH_PORT" --server.address 0.0.0.0 --server.headless true
  sleep 4
fi

cat <<EOF

------------------------------------------------------
 Students open : http://$HOSTIP:$BACKEND_PORT
 Dashboard     : http://$HOSTIP:$DASH_PORT
 API docs      : http://$HOSTIP:$BACKEND_PORT/docs
------------------------------------------------------
 The student app is served by the backend itself, so it
 works on ANY network without rebuilding — students can
 also reach it by this machine's hostname:

   http://$(hostname):$BACKEND_PORT

 Logs : $LOGDIR/{backend,streamlit}.log
 Stop : ./deploy.sh stop

 If phones cannot reach these addresses, open the
 firewall ports — see the deployment guide.
EOF
