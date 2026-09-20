#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${XQ_CHROME_PROFILE:-${TMPDIR:-/tmp}/xq-browser-audit-$$}"
PORT="${XQ_CHROME_PORT:-9222}"
rm -rf -- "$PROFILE"
chromium --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" about:blank >/tmp/xq-browser-audit-chrome.out 2>/tmp/xq-browser-audit-chrome.err &
CHROME_PID=$!
cleanup() {
  kill "$CHROME_PID" 2>/dev/null || true
  wait "$CHROME_PID" 2>/dev/null || true
  rm -rf -- "$PROFILE"
}
trap cleanup EXIT
for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:${PORT}/json/list" >/dev/null; then break; fi
  sleep 0.2
done
XQ_CHROME_PORT="$PORT" node "$ROOT/scripts/audit_frontend_browser.mjs"