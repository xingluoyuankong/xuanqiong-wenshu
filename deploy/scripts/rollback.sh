#!/usr/bin/env bash
# Explicit offline restore, with a caller-selected immutable application image.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/deploy_docker.sh"

main() {
    [[ "${CONFIRM_ROLLBACK:-}" == RESTORE_DATABASE ]] || fail 'Set CONFIRM_ROLLBACK=RESTORE_DATABASE to confirm destructive restore'
    [[ -n "${ROLLBACK_BACKUP:-}" && -s "$ROLLBACK_BACKUP" ]] || fail 'ROLLBACK_BACKUP must name a nonempty backup'
    [[ "${ROLLBACK_IMAGE:-}" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*@sha256:[a-f0-9]{64}$ ]] || fail 'ROLLBACK_IMAGE must be an immutable image@sha256:digest'
    readonly CONFIRM_ROLLBACK ROLLBACK_BACKUP ROLLBACK_IMAGE
    load_deployment
    [[ -f "$ROLLBACK_BACKUP.sha256" && -f "$ROLLBACK_BACKUP.database" ]] || fail 'Backup manifest is missing'
    [[ "$(cat "$ROLLBACK_BACKUP.database")" == "$DATABASE_ID" ]] || fail 'Backup database identity mismatch'
    [[ -f "$ROLLBACK_BACKUP.provider" && "$(cat "$ROLLBACK_BACKUP.provider")" == "$DB_PROVIDER" ]] || fail 'Backup provider identity mismatch'
    local expected actual
    expected="$(cat "$ROLLBACK_BACKUP.sha256")"
    # Verify the exact bytes later fed to mysql, not a mutable caller path.
    RESTORE_SNAPSHOT="$(mktemp "$BACKUP_DIR/restore-input-XXXXXXXX.sql")"
    cp -- "$ROLLBACK_BACKUP" "$RESTORE_SNAPSHOT"
    actual="$(sha256sum "$RESTORE_SNAPSHOT" | awk '{print $1}')"
    [[ "$expected" =~ ^[a-f0-9]{64}$ && "$actual" == "$expected" ]] || fail 'Backup checksum mismatch'
    # Fetch and validate rollback image before stopping anything.
    docker pull "$ROLLBACK_IMAGE"
    docker image inspect "$ROLLBACK_IMAGE" >/dev/null
    OVERRIDE_FILE="$(mktemp "$BACKUP_DIR/rollback-compose-XXXXXXXX.yml")"
    printf 'services:\n' > "$OVERRIDE_FILE"
    for service in "${APP_SERVICES[@]}"; do
        printf '  %s:\n    image: "%s"\n' "$service" "$ROLLBACK_IMAGE" >> "$OVERRIDE_FILE"
    done
    COMPOSE_ARGS+=(-f "$OVERRIDE_FILE")
    compose config --quiet
    # Backup/restore client comes from the current maintenance image, not host mysql.
    compose build migrate
    ensure_database
    quiesce_apps
    backup_database pre-restore
    if [[ "$DB_PROVIDER" == sqlite ]]; then
        sqlite_restore < "$RESTORE_SNAPSHOT"
    else
    compose run --rm --no-deps -T migrate sh -eu -c '
        export MYSQL_PWD="$MYSQL_PASSWORD"
        exec mysql --host="$MYSQL_HOST" --port="$MYSQL_PORT" --user="$MYSQL_USER"
    ' < "$RESTORE_SNAPSHOT"
    fi
    # No automatic migration: this is the schema belonging to the selected image.
    # If health fails the EXIT trap stops all apps, leaving the safety backup intact.
    # Preserve the immutable image override even if startup only partly succeeds.
    KEEP_OVERRIDE=true
    start_apps
    printf 'ROLLBACK_OK: restored=%s safety_backup=%s\n' "$ROLLBACK_BACKUP" "$LAST_BACKUP"
}

main "$@"
