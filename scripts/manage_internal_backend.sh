#!/usr/bin/env bash
# Manage the loopback-only 8099 backend without touching public 8013.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${XQ_BACKEND_PORT:-${XQ_INTERNAL_BACKEND_PORT:-8099}}"
HOST="${XQ_BACKEND_HOST:-127.0.0.1}"
ROLE="${XQ_BACKEND_ROLE:-internal_loopback_backend}"
STATE_DIR="${XQ_BACKEND_STATE_DIR:-${XQ_INTERNAL_BACKEND_STATE_DIR:-$ROOT/logs/internal-backend-8099}}"
MANIFEST="$STATE_DIR/manifest.json"
LOG="$STATE_DIR/backend.log"
ERR="$STATE_DIR/backend-error.log"
APP="backend.app.main:app"

source "$ROOT/scripts/server_runtime.sh"

listener_pid() {
  lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

write_manifest() {
  local pid="${1:-}" status="${2:-unknown}"
  mkdir -p "$STATE_DIR"
  XQ_STATE_DIR="$STATE_DIR" XQ_HOST="$HOST" XQ_ROLE="$ROLE" XQ_PID="$pid" XQ_STATUS="$status" XQ_PORT="$PORT" XQ_ROOT="$ROOT" XQ_LOG="$LOG" XQ_ERR="$ERR" XQ_APP="$APP" XQ_PYTHON="$XQ_PYTHON" XQ_CURRENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)" XQ_PROCESS_COMMIT="${XQ_PROCESS_COMMIT:-}" XQ_STARTED="${XQ_STARTED:-}" XQ_PYTHONPATH="$PYTHONPATH" \
  "$XQ_PYTHON" - <<'PY'
import json, os, platform, subprocess
from datetime import datetime, timezone
from pathlib import Path
path=Path(os.environ["XQ_STATE_DIR"]) / "manifest.json"
path.parent.mkdir(parents=True, exist_ok=True)
current_commit=os.environ.get("XQ_CURRENT_COMMIT", "")
process_commit=os.environ.get("XQ_PROCESS_COMMIT", "")
existing={}
if path.exists():
    try: existing=json.loads(path.read_text(encoding="utf-8"))
    except Exception: existing={}
if not process_commit and existing.get("pid") == int(os.environ["XQ_PID"] or 0):
    process_commit=existing.get("process_commit") or existing.get("commit") or current_commit
if not process_commit:
    process_commit=current_commit
started_at=os.environ.get("XQ_STARTED") or (existing.get("started_at") if existing.get("pid") == int(os.environ["XQ_PID"] or 0) else None)
data={
  "role":os.environ["XQ_ROLE"],
  "host":os.environ["XQ_HOST"], "port":int(os.environ["XQ_PORT"]),
  "app":os.environ["XQ_APP"], "pid":int(os.environ["XQ_PID"] or 0),
  "status":os.environ["XQ_STATUS"], "repo":os.environ["XQ_ROOT"],
  "commit":process_commit, "process_commit":process_commit, "current_commit":current_commit,
  "code_drift": bool(process_commit and current_commit and process_commit != current_commit),
  "python":os.environ["XQ_PYTHON"],
  "python_version":platform.python_version(),
  "pythonpath":os.environ.get("XQ_PYTHONPATH", ""),
  "stdout":os.environ["XQ_LOG"], "stderr":os.environ["XQ_ERR"],
  "updated_at":datetime.now(timezone.utc).isoformat(),
  "started_at":started_at,
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(path)
PY
}

status() {
  xq_prepare_runtime
  local current_commit; current_commit="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  local pid; pid="$(listener_pid)"
  if [[ -n "$pid" ]]; then
    XQ_STATE_DIR="$STATE_DIR" XQ_HOST="$HOST" XQ_ROLE="$ROLE" XQ_PID="$pid" XQ_STATUS="running" XQ_PORT="$PORT" XQ_ROOT="$ROOT" XQ_LOG="$LOG" XQ_ERR="$ERR" XQ_APP="$APP" XQ_PYTHON="$XQ_PYTHON" XQ_CURRENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)" XQ_PYTHONPATH="$PYTHONPATH" write_manifest "$pid" running >/dev/null
  else
    XQ_STATE_DIR="$STATE_DIR" XQ_HOST="$HOST" XQ_ROLE="$ROLE" XQ_PID=0 XQ_STATUS="stopped" XQ_PORT="$PORT" XQ_ROOT="$ROOT" XQ_LOG="$LOG" XQ_ERR="$ERR" XQ_APP="$APP" XQ_PYTHON="$XQ_PYTHON" XQ_CURRENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)" XQ_PYTHONPATH="$PYTHONPATH" write_manifest 0 stopped >/dev/null
  fi
  cat "$MANIFEST"
  if [[ -n "$pid" ]]; then curl -fsS --max-time 5 "http://${HOST}:${PORT}/api/health"; echo; fi
}

start() {
  xq_prepare_runtime
  local current_commit; current_commit="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  local pid; pid="$(listener_pid)"
  if [[ -n "$pid" ]]; then echo "already listening pid=$pid"; status; return 0; fi
  mkdir -p "$STATE_DIR"
  export XQ_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export XQ_PROCESS_COMMIT="$current_commit"
  nohup env PYTHONPATH="$PYTHONPATH" "$XQ_PYTHON" -m uvicorn "$APP" --host "$HOST" --port "$PORT" --app-dir "$ROOT" >"$LOG" 2>"$ERR" < /dev/null &
  pid=$!
  for _ in $(seq 1 60); do
    if curl -fsS --max-time 2 "http://${HOST}:${PORT}/api/health" >/dev/null 2>&1; then
      XQ_STATE_DIR="$STATE_DIR" XQ_HOST="$HOST" XQ_ROLE="$ROLE" XQ_PID="$(listener_pid)" XQ_STATUS=running XQ_PORT="$PORT" XQ_ROOT="$ROOT" XQ_LOG="$LOG" XQ_ERR="$ERR" XQ_APP="$APP" XQ_PYTHON="$XQ_PYTHON" XQ_CURRENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)" XQ_PYTHONPATH="$PYTHONPATH" write_manifest "$(listener_pid)" running >/dev/null
      echo "started pid=$(listener_pid)"; status; return 0
    fi
    sleep 1
  done
  echo "internal backend failed to become healthy" >&2
  tail -80 "$ERR" >&2 || true
  return 1
}

stop() {
  local pid; pid="$(listener_pid)"
  if [[ -z "$pid" ]]; then echo "already stopped"; status; return 0; fi
  kill -TERM "$pid"
  for _ in $(seq 1 30); do [[ -z "$(listener_pid)" ]] && break; sleep 1; done
  if [[ -n "$(listener_pid)" ]]; then kill -KILL "$(listener_pid)"; fi
  xq_prepare_runtime
  XQ_STATE_DIR="$STATE_DIR" XQ_HOST="$HOST" XQ_ROLE="$ROLE" XQ_PID=0 XQ_STATUS=stopped XQ_PORT="$PORT" XQ_ROOT="$ROOT" XQ_LOG="$LOG" XQ_ERR="$ERR" XQ_APP="$APP" XQ_PYTHON="$XQ_PYTHON" XQ_CURRENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)" XQ_PYTHONPATH="$PYTHONPATH" write_manifest 0 stopped >/dev/null
  echo "stopped pid=$pid"
}

case "${1:-status}" in
  status|manifest) status ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  *) echo "usage: $0 {status|manifest|start|stop|restart}" >&2; exit 2 ;;
esac
