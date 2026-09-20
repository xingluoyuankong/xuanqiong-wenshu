#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
PORT=18174
cleanup() {
  XQ_FRONTEND_PORT="$PORT" XQ_FRONTEND_STATE_DIR="$TMP/state" XQ_FRONTEND_DIST="$TMP/dist" \
    "$ROOT/scripts/manage_frontend.sh" stop >/dev/null 2>&1 || true
  rm -rf -- "$TMP"
}
trap cleanup EXIT
mkdir -p "$TMP/dist/assets"
printf '<!doctype html><title>fixture</title><div id="app"></div>' > "$TMP/dist/index.html"
printf 'console.log("fixture")' > "$TMP/dist/assets/app.js"
ENV=(XQ_FRONTEND_PORT="$PORT" XQ_FRONTEND_HOST=127.0.0.1 XQ_FRONTEND_STATE_DIR="$TMP/state" XQ_FRONTEND_DIST="$TMP/dist")
env "${ENV[@]}" "$ROOT/scripts/manage_frontend.sh" start >/tmp/xq-frontend-manager-start.out
curl -fsS "http://127.0.0.1:$PORT/workspace" | grep -Fq 'id="app"'
test "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/assets/app.js")" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/missing.js")" = 404
test "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/health")" = 404
env "${ENV[@]}" "$ROOT/scripts/manage_frontend.sh" status >/tmp/xq-frontend-manager-status.json
grep -Fq '"status": "running"' "$TMP/state/manifest.json"
env "${ENV[@]}" "$ROOT/scripts/manage_frontend.sh" stop >/tmp/xq-frontend-manager-stop.out
test "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)" != 200
printf 'frontend manager lifecycle: PASS\n'