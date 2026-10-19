#!/usr/bin/env bash
#
# tunnel.sh — publish the running system to the internet over HTTPS.
#
# Uses Cloudflare "quick tunnels": no account, no domain, free. Each run gets a
# NEW random *.trycloudflare.com address, so re-share the link after restarting.
#
#   Usage:  ./tunnel.sh          # open public HTTPS links
#           ./tunnel.sh stop     # close them
#           ./tunnel.sh url      # reprint the current links
#
# Requires the stack to be running already (./deploy.sh).

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$ROOT/.run-logs"
mkdir -p "$LOGDIR"

APP_LOG="$LOGDIR/tunnel-app.log"
DASH_LOG="$LOGDIR/tunnel-dash.log"

case "${1:-start}" in
  stop)
    pkill -f "cloudflared tunnel --url http://localhost:8000" 2>/dev/null && echo "closed the student-app tunnel"
    pkill -f "cloudflared tunnel --url http://localhost:8501" 2>/dev/null && echo "closed the dashboard tunnel"
    rm -f "$LOGDIR"/tunnel-*.url
    echo "Public links are now dead. The system still runs on the local network."
    exit 0
    ;;
  url)
    for f in "$LOGDIR"/tunnel-*.url; do
      [ -f "$f" ] && echo "  $(basename "$f" .url): $(cat "$f")"
    done
    exit 0
    ;;
esac

command -v cloudflared >/dev/null || {
  echo "[ERROR] cloudflared is not installed."
  echo "        Install it from https://github.com/cloudflare/cloudflared/releases"
  exit 1
}

curl -s --max-time 5 -o /dev/null http://localhost:8000/ || {
  echo "[ERROR] The system is not running locally. Start it first:  ./deploy.sh"
  exit 1
}

# Open one quick tunnel and wait for Cloudflare to hand back the public address.
open_tunnel() {
  local port="$1" log="$2" label="$3"
  if pgrep -f "cloudflared tunnel --url http://localhost:$port" >/dev/null; then
    echo "  $label already published."
    return
  fi
  : > "$log"
  setsid cloudflared tunnel --url "http://localhost:$port" >"$log" 2>&1 </dev/null &
  disown 2>/dev/null || true
  printf "  publishing %s" "$label"
  for _ in $(seq 1 45); do
    if grep -qE "https://[a-z0-9-]+\.trycloudflare\.com" "$log" 2>/dev/null; then
      grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$log" | head -1 \
        > "$LOGDIR/$(basename "$log" .log).url"
      echo " — done."
      return
    fi
    printf "."; sleep 2
  done
  echo
  echo "  [WARNING] $label did not come up. Check $log"
}

echo "======================================================"
echo "  IFAS — Publishing to the internet"
echo "======================================================"
echo
open_tunnel 8000 "$APP_LOG"  "student app"
open_tunnel 8501 "$DASH_LOG" "admin dashboard"

APP_URL=$(cat "$LOGDIR/tunnel-app.url" 2>/dev/null || echo "not available")
DASH_URL=$(cat "$LOGDIR/tunnel-dash.url" 2>/dev/null || echo "not available")

cat <<EOF

------------------------------------------------------
 Students (share this) : $APP_URL
 Admin dashboard       : $DASH_URL
------------------------------------------------------
 These are live on the public internet over HTTPS.

 NOTE: the addresses change every time you run this,
 so share them fresh. They stop working when you run
 './tunnel.sh stop', close the laptop, or lose Wi-Fi.

 Reprint them any time with:  ./tunnel.sh url
EOF
