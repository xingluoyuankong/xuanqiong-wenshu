#!/usr/bin/env bash
# Manage the production SPA frontend without treating a root-page 200 as route health.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${XQ_FRONTEND_PORT:-5174}"
HOST="${XQ_FRONTEND_HOST:-0.0.0.0}"
ROLE="${XQ_FRONTEND_ROLE:-spa_frontend}"
STATE_DIR="${XQ_FRONTEND_STATE_DIR:-$ROOT/logs/frontend-$PORT}"
MANIFEST="$STATE_DIR/manifest.json"
LOG="$STATE_DIR/frontend.log"
ERR="$STATE_DIR/frontend-error.log"
SERVER="$ROOT/scripts/frontend_spa_server.py"
DIST="${XQ_FRONTEND_DIST:-$ROOT/frontend/dist}"

listener_pid() {
  lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

is_managed_pid() {
  local pid="${1:-}"
  [[ -n "$pid" && -r "/proc/$pid/cmdline" ]] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -Fq "$SERVER"
}

worktree_dirty_marker() {
  git -C "$ROOT" status --porcelain --untracked-files=all 2>/dev/null \
    | grep -vE '^.. storage/.*\.(db-wal|db-shm)$|^.. logs/|^.. backups/|^\?\? .*(__pycache__|\.pyc)$|^\?\? frontend/dist/' \
    | head -1 || true
}

write_manifest() {
  local pid="${1:-0}" status="${2:-unknown}" process_commit="${3:-}"
  mkdir -p "$STATE_DIR"
  XQ_STATE_DIR="$STATE_DIR" XQ_HOST="$HOST" XQ_ROLE="$ROLE" XQ_PID="$pid" XQ_STATUS="$status" \
  XQ_PORT="$PORT" XQ_ROOT="$ROOT" XQ_LOG="$LOG" XQ_ERR="$ERR" XQ_SERVER="$SERVER" XQ_DIST="$DIST" \
  XQ_CURRENT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)" \
  XQ_WORKTREE_DIRTY="$(worktree_dirty_marker)" XQ_PROCESS_COMMIT="$process_commit" \
  python3 - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path
path = Path(os.environ['XQ_STATE_DIR']) / 'manifest.json'
existing = {}
if path.exists():
    try: existing = json.loads(path.read_text(encoding='utf-8'))
    except Exception: existing = {}
pid = int(os.environ.get('XQ_PID') or 0)
current = os.environ.get('XQ_CURRENT_COMMIT', '')
process = os.environ.get('XQ_PROCESS_COMMIT') or (
    existing.get('process_commit') if existing.get('pid') == pid else None
) or current
data = {
    'role': os.environ['XQ_ROLE'], 'host': os.environ['XQ_HOST'], 'port': int(os.environ['XQ_PORT']),
    'pid': pid, 'status': os.environ['XQ_STATUS'], 'repo': os.environ['XQ_ROOT'],
    'server': os.environ['XQ_SERVER'], 'dist': os.environ['XQ_DIST'],
    'commit': process, 'process_commit': process, 'current_commit': current,
    'code_drift': bool(process and current and process != current),
    'working_tree_dirty': bool(os.environ.get('XQ_WORKTREE_DIRTY', '')),
    'stdout': os.environ['XQ_LOG'], 'stderr': os.environ['XQ_ERR'],
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'started_at': existing.get('started_at') if existing.get('pid') == pid else None,
}
if data['status'] == 'running' and not data['started_at']:
    data['started_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY
}

health() {
  curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/" >/dev/null
}

status() {
  local pid; pid="$(listener_pid)"
  if [[ -z "$pid" ]]; then
    write_manifest 0 stopped
  elif is_managed_pid "$pid"; then
    write_manifest "$pid" running
  else
    write_manifest "$pid" foreign_listener
  fi
  cat "$MANIFEST"
  if [[ -n "$pid" ]]; then health && echo '{"status":"healthy"}'; fi
}

start() {
  [[ -f "$SERVER" && -d "$DIST" ]] || { echo "frontend server/dist missing" >&2; exit 2; }
  local pid; pid="$(listener_pid)"
  if [[ -n "$pid" ]]; then
    if is_managed_pid "$pid"; then echo "already listening pid=$pid"; status; return 0; fi
    echo "port $PORT is owned by unmanaged pid=$pid; refusing to replace it" >&2
    status
    return 1
  fi
  mkdir -p "$STATE_DIR"
  local commit; commit="$(git -C "$ROOT" rev-parse HEAD)"
  nohup python3 "$SERVER" --root "$DIST" --host "$HOST" --port "$PORT" >"$LOG" 2>"$ERR" < /dev/null &
  local spawned=$!
  for _ in $(seq 1 30); do
    pid="$(listener_pid)"
    if [[ -n "$pid" ]] && is_managed_pid "$pid" && health; then
      write_manifest "$pid" running "$commit"
      echo "started pid=$pid"
      status
      return 0
    fi
    sleep 1
  done
  echo "frontend failed to become healthy (spawned=$spawned)" >&2
  tail -80 "$ERR" >&2 || true
  return 1
}

stop() {
  local pid; pid="$(listener_pid)"
  if [[ -z "$pid" ]]; then echo 'already stopped'; write_manifest 0 stopped; return 0; fi
  if ! is_managed_pid "$pid"; then
    echo "port $PORT is owned by unmanaged pid=$pid; refusing to stop it" >&2
    status
    return 1
  fi
  kill -TERM "$pid"
  for _ in $(seq 1 20); do [[ -z "$(listener_pid)" ]] && break; sleep 1; done
  if [[ -n "$(listener_pid)" ]]; then kill -KILL "$pid"; fi
  write_manifest 0 stopped
  echo "stopped pid=$pid"
}

case "${1:-status}" in
  status|manifest) status ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  *) echo "usage: $0 {status|start|stop|restart}" >&2; exit 2 ;;
esac