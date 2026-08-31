#!/usr/bin/env bash
# Read-only deployment schema verifier.  It checks Alembic plus critical Agent correlation columns.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env}"
STRICT=false

usage() { echo "Usage: bash deploy/scripts/verify_migration.sh [--strict]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) STRICT=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

DB_HOST="${MYSQL_HOST:-localhost}"
DB_PORT="${MYSQL_PORT:-3306}"
DB_USER="${MYSQL_USER:-xuanqiong_wenshu}"
DB_PASSWORD="${MYSQL_PASSWORD:-}"
DB_NAME="${MYSQL_DATABASE:-xuanqiong_wenshu}"
MYSQL_BIN="${MYSQL_BIN:-mysql}"
PYTHON_BIN="${PYTHON_BIN:-}"

[[ -n "$DB_PASSWORD" ]] || { echo "ERROR: MYSQL_PASSWORD is required." >&2; exit 1; }
command -v "$MYSQL_BIN" >/dev/null 2>&1 || { echo "ERROR: mysql command unavailable: $MYSQL_BIN" >&2; exit 1; }
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then PYTHON_BIN="$BACKEND_DIR/.venv/bin/python";
  elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python3)";
  else PYTHON_BIN="$(command -v python)"; fi
fi

mysql_exec() { MYSQL_PWD="$DB_PASSWORD" "$MYSQL_BIN" --protocol=tcp -N -s -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$@"; }
failures=0
check() { local label="$1"; shift; if "$@"; then echo "OK: $label"; else echo "FAIL: $label" >&2; failures=$((failures + 1)); fi; }

check "MySQL connectivity" mysql_exec -e "SELECT 1"
check "database exists" mysql_exec "$DB_NAME" -e "SELECT 1"

echo "Alembic current (read-only):"
if ! ( cd "$BACKEND_DIR" && "$PYTHON_BIN" -m alembic -c alembic.ini current ); then
  echo "FAIL: Alembic current" >&2
  failures=$((failures + 1))
fi

echo "Critical Agent correlation columns:"
for table in agent_runs agent_run_steps agent_events agent_approvals agent_artifact_refs agent_jobs task_runtime_tasks task_runtime_events; do
  if [[ "$(mysql_exec "$DB_NAME" -e "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='${DB_NAME//\'/\'\'}' AND table_name='$table' AND column_name='correlation_id';" 2>/dev/null || true)" == "1" ]]; then
    echo "OK: $table.correlation_id"
  else
    echo "FAIL: $table.correlation_id" >&2
    failures=$((failures + 1))
  fi
done

if [[ "$STRICT" == true && "$failures" -gt 0 ]]; then
  echo "Verification failed with $failures issue(s)." >&2
  exit 1
fi

echo "Verification finished: failures=$failures strict=$STRICT"
[[ "$failures" -eq 0 ]] || echo "WARNING: non-strict mode returned success; do not treat this as deploy verified." >&2
