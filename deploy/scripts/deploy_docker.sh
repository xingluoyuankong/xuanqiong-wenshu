#!/usr/bin/env bash
# SQLite and internal/external MySQL deployment. Source this file to reuse guarded operations.
set -Eeuo pipefail

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
compose() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }

load_deployment() {
    [[ -f deploy/docker-compose.yml && -f deploy/.env ]] || fail 'Run from repository root with deploy/.env present'
    set -a
    source deploy/.env
    set +a
    export DB_PROVIDER="${DB_PROVIDER:-sqlite}"
    [[ "$DB_PROVIDER" == sqlite || "$DB_PROVIDER" == mysql ]] || fail 'DB_PROVIDER must be sqlite or mysql'
    [[ -z "${DATABASE_URL:-}" && -z "${COMPOSE_FILE:-}" && -z "${COMPOSE_PROFILES:-}" ]] || fail 'DATABASE_URL/COMPOSE_FILE/COMPOSE_PROFILES overrides are not supported'
    [[ "${RUN_MIGRATIONS:-true}" == true ]] || fail 'RUN_MIGRATIONS must be true'
    [[ -n "${SECRET_KEY:-}" && -n "${ADMIN_DEFAULT_PASSWORD:-}" ]] || fail 'Required application credentials are missing'
    INTERNAL_MYSQL=false
    if [[ "$DB_PROVIDER" == mysql ]]; then
        export MYSQL_HOST="${MYSQL_HOST:-db}" MYSQL_PORT="${MYSQL_PORT:-3306}"
        export MYSQL_USER="${MYSQL_USER:-xuanqiong_wenshu}" MYSQL_DATABASE="${MYSQL_DATABASE:-xuanqiong_wenshu}"
        [[ -n "${MYSQL_PASSWORD:-}" ]] || fail 'MYSQL_PASSWORD is missing'
        [[ "$MYSQL_PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( MYSQL_PORT <= 65535 )) || fail 'Invalid MYSQL_PORT'
        [[ "$MYSQL_DATABASE" =~ ^[A-Za-z][A-Za-z0-9_]*$ && "$MYSQL_DATABASE" != mysql && "$MYSQL_DATABASE" != sys && "$MYSQL_DATABASE" != information_schema && "$MYSQL_DATABASE" != performance_schema ]] || fail 'Invalid application database name'
        if [[ "$MYSQL_HOST" == db ]]; then
            [[ "$MYSQL_PORT" == 3306 && -n "${MYSQL_ROOT_PASSWORD:-}" ]] || fail 'Internal MySQL requires port 3306 and MYSQL_ROOT_PASSWORD'
            INTERNAL_MYSQL=true
        fi
        DATABASE_ID="$MYSQL_DATABASE"
        BACKUP_EXTENSION=sql
    else
        export SQLITE_DB_PATH="${SQLITE_DB_PATH:-/app/storage/xuanqiong_wenshu.db}"
        [[ "$SQLITE_DB_PATH" == /app/storage/* && "$SQLITE_DB_PATH" != */../* && "$SQLITE_DB_PATH" != */./* && "$SQLITE_DB_PATH" != */.. && "$SQLITE_DB_PATH" != */ ]] || fail 'SQLITE_DB_PATH must be a file below the shared /app/storage mount'
        DATABASE_ID="$SQLITE_DB_PATH"
        BACKUP_EXTENSION=sqlite
    fi
    HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"
    [[ "$HEALTH_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || fail 'HEALTH_TIMEOUT must be a positive integer'
    COMPOSE_ARGS=(--env-file deploy/.env -f deploy/docker-compose.yml --profile maintenance)
    if [[ "$INTERNAL_MYSQL" == true ]]; then COMPOSE_ARGS+=(--profile mysql); fi
    APP_SERVICES=(app agent-worker agent-command-worker)
    command -v docker >/dev/null || fail 'Docker is missing'
    command -v sha256sum >/dev/null || fail 'sha256sum is missing'
    docker compose version >/dev/null
    docker info >/dev/null
    compose config --quiet
    umask 077
    BACKUP_DIR="${BACKUP_DIR:-./backups}"
    mkdir -p -- "$BACKUP_DIR"
    BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd -P)"
    # Lock the deployment, not a caller-selected backup destination.
    LOCK_DIR="$(cd deploy && pwd -P)/.deployment-lock"
    mkdir -- "$LOCK_DIR" || fail 'Deployment lock exists; check its owner before retrying'
    APPS_QUIESCED=false
    OVERRIDE_FILE=''
    RESTORE_SNAPSHOT=''
    KEEP_OVERRIDE=false
    trap deployment_exit EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
}

deployment_exit() {
    local rc=$? keep_lock=false
    trap - EXIT
    trap '' INT TERM
    # Cleanup failures must not mask the original operation failure.
    set +e
    if (( rc != 0 )) && [[ "$APPS_QUIESCED" == true ]]; then
        if ! compose stop "${APP_SERVICES[@]}"; then
            keep_lock=true
            printf 'ERROR: application stop failed; manual isolation is required; lock retained\n' >&2
        fi
        printf 'ERROR: operation failed; no automatic database restore or application restart\n' >&2
    fi
    if [[ -n "$OVERRIDE_FILE" ]]; then
        if [[ "$KEEP_OVERRIDE" == true ]]; then
            printf 'ROLLBACK_COMPOSE_OVERRIDE: %s (retain this override for subsequent Compose operations)\n' "$OVERRIDE_FILE"
        elif ! rm -f -- "$OVERRIDE_FILE"; then
            (( rc != 0 )) || rc=1
            printf 'ERROR: temporary override cleanup failed\n' >&2
        fi
    fi
    if [[ -n "$RESTORE_SNAPSHOT" ]] && ! rm -f -- "$RESTORE_SNAPSHOT"; then
        (( rc != 0 )) || rc=1
        printf 'ERROR: restore snapshot cleanup failed\n' >&2
    fi
    if [[ "$keep_lock" == false ]] && ! rmdir -- "$LOCK_DIR"; then
        (( rc != 0 )) || rc=1
        printf 'ERROR: deployment lock cleanup failed\n' >&2
    fi
    exit "$rc"
}

ensure_database() {
    if [[ "$INTERNAL_MYSQL" == true ]]; then
        compose up -d --no-deps --no-recreate --wait --wait-timeout "$HEALTH_TIMEOUT" db
    elif [[ "$DB_PROVIDER" == mysql ]]; then
        # External hostnames are resolved in the same network as migration/backup.
        compose run --rm --no-deps -T --entrypoint sh migrate -eu -c '
            export MYSQL_PWD="$MYSQL_PASSWORD"
            exec mysql --connect-timeout=10 --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" --database="$MYSQL_DATABASE" --execute="SELECT 1"
        ' >/dev/null
    fi
}

sqlite_backup() {
    compose run --rm --no-deps -T --entrypoint python migrate -c '
# SQLITE_BACKUP: SQLite backup API includes committed WAL frames.
import os, sqlite3, sys, tempfile
from pathlib import Path
path = Path(os.environ["SQLITE_DB_PATH"])
root = Path(os.environ.get("STORAGE_DIR", "/app/storage")).resolve()
if root not in path.resolve().parents or path.is_symlink():
    raise RuntimeError("SQLite source escapes the storage mount")
if not path.exists() and any(Path(str(path) + ext).exists() for ext in ("-wal", "-shm")):
    raise RuntimeError("Missing database with orphan WAL/SHM; operator inspection required")
with tempfile.TemporaryDirectory() as folder:
    backup = Path(folder) / "backup.sqlite"
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) if path.exists() else sqlite3.connect(":memory:")
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode=DELETE")
        target.execute("VACUUM")
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite backup integrity check failed")
    finally:
        target.close()
        source.close()
    with backup.open("rb") as stream:
        import shutil
        shutil.copyfileobj(stream, sys.stdout.buffer)
'
}

sqlite_restore() {
    compose run --rm --no-deps -T --entrypoint python migrate -c '
# SQLITE_RESTORE: validate first, checkpoint old WAL, then atomically replace.
import os, shutil, sqlite3, sys, tempfile
from pathlib import Path
path = Path(os.environ["SQLITE_DB_PATH"])
root = Path(os.environ.get("STORAGE_DIR", "/app/storage")).resolve()
if root not in path.resolve().parents or path.is_symlink():
    raise RuntimeError("SQLite destination escapes the storage mount")
path.parent.mkdir(parents=True, exist_ok=True)
fd, name = tempfile.mkstemp(prefix=".restore-", suffix=".sqlite", dir=path.parent)
snapshot = Path(name)
try:
    with os.fdopen(fd, "wb") as output:
        shutil.copyfileobj(sys.stdin.buffer, output)
        output.flush()
        os.fsync(output.fileno())
    check = sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
    try:
        if check.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite restore input integrity check failed")
    finally:
        check.close()
    if path.exists():
        old = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            if old.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] != 0:
                raise RuntimeError("SQLite checkpoint is busy; writers must stay stopped")
        finally:
            old.close()
    for ext in ("-wal", "-shm"):
        Path(str(path) + ext).unlink(missing_ok=True)
    os.replace(snapshot, path)
finally:
    snapshot.unlink(missing_ok=True)
'
}

quiesce_apps() {
    APPS_QUIESCED=true
    compose stop "${APP_SERVICES[@]}"
}

backup_database() {
    local label=$1
    LAST_BACKUP="$(mktemp "$BACKUP_DIR/${label}-XXXXXXXX.$BACKUP_EXTENSION")"
    # SQL includes DROP/CREATE DATABASE, so restoration removes post-backup tables.
    # Consumers must be stopped. No credentials are placed in host command args.
    if [[ "$DB_PROVIDER" == sqlite ]]; then
        if ! sqlite_backup > "$LAST_BACKUP"; then fail "SQLite backup failed; partial file retained: $LAST_BACKUP"; fi
    elif ! compose run --rm --no-deps -T migrate sh -eu -c '

        export MYSQL_PWD="$MYSQL_PASSWORD"
        exec mysqldump --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER" \
          --single-transaction --routines --events --triggers --hex-blob \
          --add-drop-database --databases "$MYSQL_DATABASE"
    ' > "$LAST_BACKUP"; then
        fail "Backup failed; partial file retained: $LAST_BACKUP"
    fi
    [[ -s "$LAST_BACKUP" ]] || fail "Backup is empty: $LAST_BACKUP"
    sha256sum "$LAST_BACKUP" | awk '{print $1}' > "$LAST_BACKUP.sha256"
    printf '%s\n' "$DATABASE_ID" > "$LAST_BACKUP.database"
    printf '%s\n' "$DB_PROVIDER" > "$LAST_BACKUP.provider"
    printf 'BACKUP_OK: %s\n' "$LAST_BACKUP"
}

start_apps() {
    compose up -d --no-deps --no-build --pull never --wait --wait-timeout "$HEALTH_TIMEOUT" "${APP_SERVICES[@]}"
    APPS_QUIESCED=false
}

main() {
    load_deployment
    # Build failure must leave existing app and db containers untouched.
    compose build app agent-worker agent-command-worker migrate
    ensure_database
    quiesce_apps
    backup_database pre-migrate
    compose run --rm --no-deps -T migrate
    start_apps
    printf 'DEPLOY_OK: backup=%s\n' "$LAST_BACKUP"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
