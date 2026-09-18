#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANAGER="$ROOT/scripts/manage_public_backend.sh"
LOG_DIR="$ROOT/logs/public-backend-8013"
LOG_FILE="$LOG_DIR/keepalive.log"
mkdir -p "$LOG_DIR"
log(){ printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"; }
if ! "$MANAGER" status >"$LOG_DIR/status.out" 2>"$LOG_DIR/status.err"; then log "status failed; starting public backend"; "$MANAGER" start >>"$LOG_FILE" 2>&1; exit 0; fi
if grep -q '"status": "running"' "$LOG_DIR/status.out" && ! grep -q '"code_drift": true' "$LOG_DIR/status.out" && ! grep -q '"working_tree_dirty": true' "$LOG_DIR/status.out"; then log "public backend healthy and commit-aligned"; exit 0; fi
if grep -q '"code_drift": true' "$LOG_DIR/status.out" || grep -q '"working_tree_dirty": true' "$LOG_DIR/status.out"; then log "public backend code drift detected; restarting"; "$MANAGER" restart >>"$LOG_FILE" 2>&1; exit 0; fi
log "public backend not running; starting"; "$MANAGER" start >>"$LOG_FILE" 2>&1
