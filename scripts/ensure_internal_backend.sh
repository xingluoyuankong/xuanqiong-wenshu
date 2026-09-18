#!/usr/bin/env bash
# Keep the loopback-only 8099 backend alive through the qwenpaw supervisor loop.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANAGER="$ROOT/scripts/manage_internal_backend.sh"
LOG_DIR="${XQ_INTERNAL_BACKEND_STATE_DIR:-$ROOT/logs/internal-backend-8099}"
LOG_FILE="$LOG_DIR/keepalive.log"
mkdir -p "$LOG_DIR"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"; }

if ! "$MANAGER" status >"$LOG_DIR/status.out" 2>"$LOG_DIR/status.err"; then
  log "status command failed; attempting start"
  "$MANAGER" start >>"$LOG_FILE" 2>&1
  exit 0
fi

if grep -q '"status": "running"' "$LOG_DIR/status.out" && ! grep -q '"code_drift": true' "$LOG_DIR/status.out"; then
  log "internal backend healthy and commit-aligned; manifest refreshed"
  exit 0
fi

if grep -q '"code_drift": true' "$LOG_DIR/status.out"; then
  log "internal backend code drift detected; restarting to current checkout"
  "$MANAGER" restart >>"$LOG_FILE" 2>&1
  log "internal backend drift restart completed"
  exit 0
fi

log "internal backend not running; attempting start"
"$MANAGER" start >>"$LOG_FILE" 2>&1
log "internal backend start completed"
