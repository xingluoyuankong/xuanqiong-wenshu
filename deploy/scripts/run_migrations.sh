#!/usr/bin/env bash
# Safe deployment migration runner. Legacy SQL remains compatible; Alembic is authoritative for Agent 005-014.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env}"
DRY_RUN=false
APPLY_LEGACY_SQL="${APPLY_LEGACY_SQL:-true}"

usage() { echo "Usage: bash deploy/scripts/run_migrations.sh [--dry-run]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true ;;
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
DB_NAME="${MYSQL_DATABASE-xuanqiong_wenshu}"
MYSQL_BIN="${MYSQL_BIN:-mysql}"
MYSQLDUMP_BIN="${MYSQLDUMP_BIN:-mysqldump}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$DB_PASSWORD" ]]; then
  echo "ERROR: MYSQL_PASSWORD is required; no migration was executed." >&2
  exit 1
fi

# Match the Docker rollback database identity and keep names out of filesystem paths.
# An unset name keeps the historical default; an explicitly empty name is invalid.
if [[ ! "$DB_NAME" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]] || (( ${#DB_NAME} > 64 )); then
  echo "ERROR: invalid MYSQL_DATABASE; expected 1-64 ASCII letters/digits/underscores, starting with a letter." >&2
  exit 1
fi
case "${DB_NAME,,}" in
  mysql|sys|information_schema|performance_schema)
    echo "ERROR: system MYSQL_DATABASE is not an application backup target." >&2
    exit 1 ;;
esac

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    PYTHON_BIN="$(command -v python)"
  fi
fi

mysql_exec() { MYSQL_PWD="$DB_PASSWORD" "$MYSQL_BIN" --protocol=tcp -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$@"; }
require_command() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: required command not found: $1" >&2; exit 1; }; }

require_command "$MYSQL_BIN"
require_command "$MYSQLDUMP_BIN"
[[ -f "$BACKEND_DIR/alembic.ini" ]] || { echo "ERROR: missing $BACKEND_DIR/alembic.ini" >&2; exit 1; }

echo "== Xuanqiong Wenshu database migration =="
echo "Host: $DB_HOST:$DB_PORT  Database: $DB_NAME  User: $DB_USER"
echo "Alembic backend: $BACKEND_DIR"
mysql_exec -e "SELECT 1" >/dev/null
mysql_exec "$DB_NAME" -e "SELECT 1" >/dev/null
echo "MySQL health check: OK"

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run: no backup, legacy SQL, or Alembic upgrade will run."
  ( cd "$BACKEND_DIR"; "$PYTHON_BIN" -m alembic -c alembic.ini current; "$PYTHON_BIN" -m alembic -c alembic.ini heads )
  exit 0
fi

# Native writer quiescence is the caller's responsibility. This section aligns
# the backup format with deploy_docker.sh / rollback.sh; it does not stop services.
require_command sha256sum
require_command mktemp
umask 077
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
mkdir -p -- "$BACKUP_DIR"
BACKUP_FILE="$(mktemp "$BACKUP_DIR/${DB_NAME}_before_alembic_XXXXXXXX.sql")"
echo "Creating backup: $BACKUP_FILE"
MYSQL_PWD="$DB_PASSWORD" "$MYSQLDUMP_BIN" --single-transaction --routines --events --triggers --hex-blob \
  -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" --add-drop-database --databases "$DB_NAME" > "$BACKUP_FILE"
[[ -s "$BACKUP_FILE" ]] || { echo "ERROR: backup is empty; refusing migration." >&2; exit 1; }
# pipefail preserves a failed hash command even when it printed a partial digest.
# The provider sidecar is published last. A failed/partial package is retained
# for inspection, never advertised as complete, and never followed by migration.
BACKUP_HASH="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
[[ "$BACKUP_HASH" =~ ^[a-f0-9]{64}$ ]] || { echo "ERROR: invalid backup checksum; no migration was executed." >&2; exit 1; }
printf '%s\n' "$BACKUP_HASH" > "$BACKUP_FILE.sha256"
printf '%s\n' "$DB_NAME" > "$BACKUP_FILE.database"
printf '%s\n' 'mysql' > "$BACKUP_FILE.provider"
echo "Backup complete."

if [[ "$APPLY_LEGACY_SQL" == true ]]; then
  LEGACY_DIR="$BACKEND_DIR/db/migrations"
  for legacy in add_novel_kit_features.sql add_deep_optimization_features.sql; do
    if [[ -f "$LEGACY_DIR/$legacy" ]]; then
      echo "Applying compatible legacy SQL: $legacy"
      mysql_exec "$DB_NAME" < "$LEGACY_DIR/$legacy"
    fi
  done
else
  echo "Legacy SQL skipped (APPLY_LEGACY_SQL=false)."
fi

echo "Running Alembic upgrade head (authoritative application schema)."
( cd "$BACKEND_DIR"; "$PYTHON_BIN" -m alembic -c alembic.ini upgrade head; "$PYTHON_BIN" -m alembic -c alembic.ini current )
echo "Migration complete. Backup retained at: $BACKUP_FILE"
echo "Next: run bash deploy/scripts/verify_migration.sh and application health checks."
