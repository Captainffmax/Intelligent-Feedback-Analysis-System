#!/usr/bin/env bash
#
# build-frontend.sh — compile the student app for production.
#
# The app talks to the API using the RELATIVE path /api, which the browser
# resolves against whatever address the page was loaded from. The backend serves
# the compiled files from its own origin, so no machine address is baked in and
# one build works on every network. Nothing to configure here.
#
#   Usage:  ./build-frontend.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================"
echo "  IFAS — Build the Student App for Production"
echo "======================================================"
echo

cd "$ROOT/frontend-pwa"

command -v npm >/dev/null || { echo "[ERROR] npm not found. Install Node.js first."; exit 1; }

if [ ! -d node_modules ]; then
  echo "  Installing dependencies (a few minutes the first time)..."
  npm install --no-audit --no-fund
fi

# VITE_API_BASE_URL is deliberately unset: the client then falls back to the
# relative "/api". Clear any inherited value so a stray export cannot bake an
# absolute address back into the bundle.
env -u VITE_API_BASE_URL npm run build

echo
echo "------------------------------------------------------"
echo "  Build complete — files are in frontend-pwa/dist"
echo
echo "  The backend serves these files, so there is no"
echo "  address to configure. Go live with:  ./deploy.sh"
echo "------------------------------------------------------"
