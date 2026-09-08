from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_release_migration_script_uses_alembic_after_backed_up_mysql_preflight() -> None:
    script = (ROOT / "deploy" / "scripts" / "run_migrations.sh").read_text(encoding="utf-8")
    assert "set -Eeuo pipefail" in script
    assert '"$PYTHON_BIN" -m alembic -c alembic.ini upgrade head' in script
    assert '"$PYTHON_BIN" -m alembic -c alembic.ini current' in script
    assert "mysqldump" in script and "--single-transaction" in script
    assert 'MYSQL_PWD="$DB_PASSWORD"' in script
    assert 'mysql_exec -e "SELECT 1"' in script
    assert "--dry-run" in script


def test_compose_declares_one_independent_agent_worker_and_maintenance_migrator() -> None:
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "  agent-worker:\n" in compose
    assert 'command: ["python", "scripts/agent_worker.py"]' in compose
    assert "AGENT_WORKER_LEASE_SECONDS" in compose
    assert "AGENT_WORKER_POLL_INTERVAL" in compose
    assert "  migrate:\n" in compose
    assert 'command: ["python", "-m", "alembic", "upgrade", "head"]' in compose
    assert "agent-worker" not in (ROOT / "deploy" / "supervisord.conf").read_text(encoding="utf-8")


def test_compose_agent_command_worker_contract() -> None:
    compose_path = ROOT / "deploy" / "docker-compose.yml"
    lines = compose_path.read_text(encoding="utf-8").splitlines()
    start = lines.index("  agent-command-worker:")
    end = next(index for index in range(start + 1, len(lines)) if lines[index].startswith("  ") and not lines[index].startswith("    "))
    worker = "\n".join(lines[start:end]) + "\n"

    assert worker.count("  agent-command-worker:") == 1
    assert 'command: ["python", "scripts/agent_command_worker.py"]' in worker
    assert "restart: unless-stopped" in worker
    assert "- ${SQLITE_STORAGE_SOURCE:-sqlite-data}:/app/storage" in worker
    assert "      - app-network" in worker
    assert "      db:" in worker
    assert "        condition: service_healthy" in worker
    assert "        required: false" in worker
    healthcheck_line = next(line for line in worker.splitlines() if line.strip().startswith("test:"))
    assert "CMD-SHELL" in healthcheck_line
    assert "tr" in healthcheck_line and "/proc/1/cmdline" in healthcheck_line
    assert "grep -F" in healthcheck_line and "scripts/agent_command_worker.py" in healthcheck_line
    assert "interval: 30s" in worker
    assert "timeout: 10s" in worker
    assert "retries: 3" in worker
    assert "start_period: 30s" in worker

    assert "AGENT_WORKER_ID: ${AGENT_COMMAND_WORKER_ID:-agent-command-worker-1}" in worker
    assert "AGENT_WORKER_LEASE_SECONDS: ${AGENT_COMMAND_WORKER_LEASE_SECONDS:-120}" in worker
    assert "AGENT_WORKER_POLL_INTERVAL: ${AGENT_COMMAND_WORKER_POLL_INTERVAL:-0.25}" in worker
    assert "DB_PROVIDER: ${DB_PROVIDER:-sqlite}" in worker
    assert "SQLITE_DB_PATH: ${SQLITE_DB_PATH:-/app/storage/xuanqiong_wenshu.db}" in worker
    assert "MYSQL_HOST: ${MYSQL_HOST:-db}" in worker
    assert "OPENAI_API_KEY" not in worker

    # The command worker must remain a separate consumer, not a second command
    # on the existing Agent Job worker service.
    agent_worker_start = lines.index("  agent-worker:")
    agent_worker_end = next(index for index in range(agent_worker_start + 1, len(lines)) if lines[index].startswith("  ") and not lines[index].startswith("    "))
    agent_worker = "\n".join(lines[agent_worker_start:agent_worker_end]) + "\n"
    assert 'command: ["python", "scripts/agent_worker.py"]' in agent_worker
    assert 'command: ["python", "scripts/agent_worker.py"]' not in worker


def test_compose_command_worker_documents_independent_env_names() -> None:
    env_example = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")
    assert "AGENT_COMMAND_WORKER_ID=agent-command-worker-1" in env_example
    assert "AGENT_COMMAND_WORKER_LEASE_SECONDS=120" in env_example
    assert "AGENT_COMMAND_WORKER_POLL_INTERVAL=0.25" in env_example


def test_deployment_image_installs_mysql_backup_client_and_env_documents_worker() -> None:
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    env_example = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")
    assert "default-mysql-client" in dockerfile
    assert "AGENT_WORKER_ID=agent-worker-1" in env_example


def test_ci_runs_full_backend_and_frontend_release_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "xuanqiong-wenshu-quick-smoke.yml").read_text(encoding="utf-8")
    assert "Run full backend regression gate" in workflow
    assert "backend/.venv/Scripts/python.exe -m pytest -q" in workflow
    assert "npm --prefix frontend run type-check" in workflow
    assert "npm --prefix frontend run test:run" in workflow
    assert "npm --prefix frontend run build-only" in workflow



# Execute the actual Bash scripts with an isolated docker executable, never a daemon.
from contextlib import closing
import hashlib
import sqlite3
import sys
import os
import shutil
import subprocess

import pytest


def _bash() -> str:
    git = shutil.which("git")
    if git:
        # Windows: .../Git/cmd/git.exe -> .../Git/bin/bash.exe (not WSL).
        candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    if os.name != "nt" and shutil.which("bash"):
        return shutil.which("bash")
    pytest.fail("Git Bash is required for deployment execution contracts")


DOCKER_STUB = r"""#!/usr/bin/env bash
set -eu
args=" $* "
phase=unknown
case "$args" in
  *' compose version '*) phase=version ;;
  *' info '*) phase=info ;;
  *' config --quiet '*) phase=config ;;
  *' build '*) phase=build ;;
  *' pull '*) phase=pull ;;
  *' image inspect '*) phase=image ;;
  *' stop '*) phase=stop ;;
  *SQLITE_BACKUP*) phase=backup ;;
  *SQLITE_RESTORE*) phase=restore ;;
  *mysqldump*) phase=backup ;;
  *'--execute='*) phase=db_probe ;;
  *' exec mysql '*) phase=restore ;;
  *' run '*' migrate '*) phase=migrate ;;
  *' up '*' db '*) phase=db ;;
  *' up '*) phase=start ;;
esac
printf '%s\n' "$phase" >> phases.log
printf '%s\n' "$*" >> docker.log
[[ "$phase" != unknown ]] || exit 98
if [[ "${SIGNAL_STAGE:-}" == "$phase" ]]; then
    kill -TERM "$PPID"
    exit 0
fi
if [[ "$phase" == backup && "${TAMPER_SOURCE:-0}" == 1 ]]; then
    printf 'changed after preflight\n' > source.sql
fi
if [[ "${FAIL_STAGE:-}" == "$phase" ]]; then
    [[ "$phase" != backup ]] || printf 'partial dump\n'
    exit 71
fi
if [[ "${REAL_SQLITE:-0}" == 1 && "$args" == *SQLITE_* && "${EMPTY_BACKUP:-0}" != 1 ]]; then
    export STORAGE_DIR="$TEST_STORAGE" SQLITE_DB_PATH="$TEST_STORAGE/state.sqlite"
    while (( $# )); do
        if [[ "$1" == -c ]]; then shift; exec "$TEST_PYTHON" -c "$1"; fi
        shift
    done
    exit 97
fi
if [[ "$phase" == backup && "${EMPTY_BACKUP:-0}" != 1 ]]; then
    printf '%s\n' '-- SQL dump' 'DROP DATABASE IF EXISTS `novel_test`;' 'CREATE DATABASE `novel_test`;' '-- Dump completed'
fi
if [[ "$phase" == restore ]]; then cat > restored.sql; fi
"""


@pytest.fixture
def deployment_workspace(tmp_path):
    (tmp_path / "deploy/scripts").mkdir(parents=True)
    (tmp_path / "bin").mkdir()
    for name in ("deploy_docker.sh", "rollback.sh"):
        (tmp_path / "deploy/scripts" / name).write_text(
            (ROOT / "deploy/scripts" / name).read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
        )
    (tmp_path / "deploy/docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "deploy/.env").write_text(
        "DB_PROVIDER=mysql\nMYSQL_HOST=db\nMYSQL_PORT=3306\nMYSQL_DATABASE=novel_test\n"
        "MYSQL_PASSWORD=fixture-password\nMYSQL_ROOT_PASSWORD=fixture-root\n"
        "SECRET_KEY=fixture-secret\nADMIN_DEFAULT_PASSWORD=fixture-admin\n",
        encoding="utf-8",
    )
    stub = tmp_path / "bin/docker"
    stub.write_text(DOCKER_STUB, encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    dump = tmp_path / "source.sql"
    dump.write_bytes(b"-- rollback fixture\nDROP DATABASE IF EXISTS `novel_test`;\nCREATE DATABASE `novel_test`;\n")
    (tmp_path / "source.sql.sha256").write_text(hashlib.sha256(dump.read_bytes()).hexdigest() + "\n")
    (tmp_path / "source.sql.database").write_text("novel_test\n")
    (tmp_path / "source.sql.provider").write_text("mysql\n")
    return tmp_path


def _run_deployment(workspace, script="deploy_docker.sh", **overrides):
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "COMSPEC", "PATHEXT", "SYSTEMDRIVE"
    }}
    for key in ("COMPOSE_FILE", "COMPOSE_PROFILES", "DATABASE_URL", "RUN_MIGRATIONS", "BACKUP_DIR", "HEALTH_TIMEOUT", "FAIL_STAGE", "EMPTY_BACKUP"):
        env.pop(key, None)
    env.update(
        CONFIRM_ROLLBACK="RESTORE_DATABASE", ROLLBACK_BACKUP="source.sql",
        ROLLBACK_IMAGE="example/novel@sha256:" + "a" * 64,
        BACKUP_DIR="backups", HEALTH_TIMEOUT="1",
        TEST_PYTHON=sys.executable, TEST_STORAGE=str(workspace / "storage"),
    )
    env.update(overrides)
    result = subprocess.run(
        [_bash(), "--noprofile", "--norc", "-c",
         'export PATH="$PWD/bin:$PATH"; hash -r; '
         '[[ "$(command -v docker)" == "$PWD/bin/docker" ]] || exit 99; '
         f'bash deploy/scripts/{script}'],
        cwd=workspace, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    phases = (workspace / "phases.log").read_text().splitlines() if (workspace / "phases.log").exists() else []
    return result, phases


def _assert_deploy_order(result, phases):
    assert result.returncode == 0, result.stdout + result.stderr
    assert phases == ["version", "info", "config", "build", "db", "stop", "backup", "migrate", "start"]


def test_docker_deploy_orders_database_health_migrations_before_app_workers(deployment_workspace):
    result, phases = _run_deployment(deployment_workspace)
    _assert_deploy_order(result, phases)
    log = (deployment_workspace / "docker.log").read_text()
    assert " down" not in log
    for line in log.splitlines():
        if " stop " in line:
            assert line.endswith("stop app agent-worker agent-command-worker")
        if " run " in line or " up " in line:
            assert "--no-deps" in line
    assert "--no-build --pull never --wait" in log
    assert "fixture-password" not in log and "fixture-root" not in log
    dumps = list((deployment_workspace / "backups").glob("pre-migrate-*.sql"))
    assert len(dumps) == 1
    assert Path(str(dumps[0]) + ".sha256").read_text().strip() == hashlib.sha256(dumps[0].read_bytes()).hexdigest()
    assert Path(str(dumps[0]) + ".database").read_text().strip() == "novel_test"
    assert not (deployment_workspace / "deploy/.deployment-lock").exists()


@pytest.mark.parametrize("phase", ["version", "info", "config", "build", "db", "stop", "backup", "migrate", "start"])
def test_deploy_failure_injection_is_fail_closed(deployment_workspace, phase):
    result, phases = _run_deployment(deployment_workspace, FAIL_STAGE=phase)
    assert result.returncode != 0
    assert "DEPLOY_OK" not in result.stdout
    if phase in {"version", "info", "config", "build", "db"}:
        assert "stop" not in phases and "backup" not in phases
    if phase in {"stop", "backup"}:
        assert "migrate" not in phases
    if phase != "start":
        assert "start" not in phases
    if phase in {"stop", "backup", "migrate", "start"}:
        assert phases[-1] == "stop"
    assert "restore" not in phases


@pytest.mark.parametrize("setting", ["MYSQL_PORT=3309", "DATABASE_URL=mysql://external/db", "RUN_MIGRATIONS=false", "COMPOSE_PROFILES=mysql", "DB_PROVIDER=postgres", "MYSQL_DATABASE=mysql"])
@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
def test_unsupported_modes_have_no_docker_side_effects(deployment_workspace, setting, script):
    with (deployment_workspace / "deploy/.env").open("a") as handle:
        handle.write(setting + "\n")
    result, phases = _run_deployment(deployment_workspace, script)
    assert result.returncode != 0
    assert phases == []


def test_empty_backup_prevents_migration(deployment_workspace):
    result, phases = _run_deployment(deployment_workspace, EMPTY_BACKUP="1")
    assert result.returncode != 0
    assert "backup" in phases and "migrate" not in phases and "start" not in phases
    assert phases[-1] == "stop"


def test_rollback_uses_deploy_env_and_compose_v2(deployment_workspace):
    result, phases = _run_deployment(deployment_workspace, "rollback.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    assert phases == ["version", "info", "config", "pull", "image", "config", "build", "db", "stop", "backup", "restore", "start"]
    assert (deployment_workspace / "restored.sql").read_bytes() == (deployment_workspace / "source.sql").read_bytes()
    assert len(list((deployment_workspace / "backups").glob("pre-restore-*.sql"))) == 1
    override_files = list((deployment_workspace / "backups").glob("rollback-compose-*.yml"))
    assert len(override_files) == 1
    assert override_files[0].read_text().count("example/novel@sha256:" + "a" * 64) == 3
    assert "ROLLBACK_COMPOSE_OVERRIDE:" in result.stdout
    assert not list((deployment_workspace / "backups").glob("restore-input-*.sql"))
    log = (deployment_workspace / "docker.log").read_text()
    assert " down" not in log
    assert "--host=\"$MYSQL_HOST\"" in log  # client executed in the Compose network
    assert "migrate sh -eu -c" in log
    assert "--no-deps --no-build --pull never --wait" in log


@pytest.mark.parametrize("phase", ["pull", "image", "build", "db", "stop", "backup", "restore", "start"])
def test_rollback_failure_injection_never_restores_online(deployment_workspace, phase):
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", FAIL_STAGE=phase)
    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    if phase in {"pull", "image", "build", "db"}:
        assert "stop" not in phases
    if phase in {"stop", "backup"}:
        assert "restore" not in phases
    if phase == "restore":
        assert "start" not in phases
    if phase in {"stop", "backup", "restore", "start"}:
        assert phases[-1] == "stop"
    assert phases.count("restore") <= 1  # never restore safety backup over live writers
    assert "migrate" not in phases


@pytest.mark.parametrize("kind", ["checksum", "database", "missing_manifest", "confirmation", "image"])
def test_rollback_preflight_rejects_bad_inputs_before_stop(deployment_workspace, kind):
    overrides = {}
    if kind == "checksum":
        (deployment_workspace / "source.sql").write_text("tampered")
    elif kind == "database":
        (deployment_workspace / "source.sql.database").write_text("another_db")
    elif kind == "missing_manifest":
        (deployment_workspace / "source.sql.sha256").unlink()
    elif kind == "confirmation":
        overrides["CONFIRM_ROLLBACK"] = "no"
    else:
        overrides["ROLLBACK_IMAGE"] = "example/novel:latest"
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", **overrides)
    assert result.returncode != 0
    assert not set(phases) & {"pull", "db", "stop", "backup", "restore", "start"}


@pytest.mark.parametrize("mutation", ["stop_before_build", "migrate_before_backup"])
def test_reverse_validation_detects_broken_deploy_order(deployment_workspace, mutation):
    script = deployment_workspace / "deploy/scripts/deploy_docker.sh"
    text = script.read_text()
    if mutation == "stop_before_build":
        text = text.replace("    compose build app agent-worker agent-command-worker migrate", "    quiesce_apps\n    compose build app agent-worker agent-command-worker migrate")
    else:
        text = text.replace("    backup_database pre-migrate\n    compose run --rm --no-deps -T migrate", "    compose run --rm --no-deps -T migrate\n    backup_database pre-migrate")
    script.write_text(text, newline="\n")
    result, phases = _run_deployment(deployment_workspace)
    # Reuse the same behavioral oracle; mutation is not applied to working sources.
    with pytest.raises(AssertionError):
        _assert_deploy_order(result, phases)


def test_reverse_validation_detects_online_restore_after_health_failure(deployment_workspace):
    script = deployment_workspace / "deploy/scripts/rollback.sh"
    script.write_text(script.read_text().replace(
        "    start_apps\n", "    start_apps || compose run --rm --no-deps -T migrate sh -eu -c 'exec mysql' < \"$ROLLBACK_BACKUP\"\n"
    ), newline="\n")
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", FAIL_STAGE="start")
    with pytest.raises(AssertionError):
        assert result.returncode != 0 and phases.count("restore") <= 1 and phases[-1] == "stop"



def test_deployment_lock_prevents_concurrent_mutation(deployment_workspace):
    (deployment_workspace / "deploy/.deployment-lock").mkdir(parents=True)
    result, phases = _run_deployment(deployment_workspace)
    assert result.returncode != 0
    assert phases == ["version", "info", "config"]
    assert (deployment_workspace / "deploy/.deployment-lock").is_dir()


def test_rollback_empty_safety_backup_prevents_restore(deployment_workspace):
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", EMPTY_BACKUP="1")
    assert result.returncode != 0
    assert "backup" in phases and "restore" not in phases and "start" not in phases
    assert phases[-1] == "stop"


def test_reverse_validation_detects_swallowed_migration_error(deployment_workspace):
    script = deployment_workspace / "deploy/scripts/deploy_docker.sh"
    script.write_text(script.read_text().replace(
        "    compose run --rm --no-deps -T migrate\n",
        "    compose run --rm --no-deps -T migrate || true\n",
    ), newline="\n")
    result, phases = _run_deployment(deployment_workspace, FAIL_STAGE="migrate")
    with pytest.raises(AssertionError):
        assert result.returncode != 0 and "start" not in phases



@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
def test_backup_destination_change_does_not_bypass_deployment_lock(deployment_workspace, script):
    (deployment_workspace / "deploy/.deployment-lock").mkdir()
    result, phases = _run_deployment(deployment_workspace, script, BACKUP_DIR="another-backup-directory")
    assert result.returncode != 0
    assert phases == ["version", "info", "config"]
    assert (deployment_workspace / "deploy/.deployment-lock").is_dir()


def _assert_restore_uses_verified_bytes(result, workspace, original):
    assert result.returncode == 0, result.stdout + result.stderr
    assert (workspace / "restored.sql").read_bytes() == original


def test_rollback_source_change_after_preflight_does_not_change_restore(deployment_workspace):
    original = (deployment_workspace / "source.sql").read_bytes()
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", TAMPER_SOURCE="1")
    assert (deployment_workspace / "source.sql").read_bytes() != original
    _assert_restore_uses_verified_bytes(result, deployment_workspace, original)
    assert phases.count("restore") == 1
    assert not list((deployment_workspace / "backups").glob("restore-input-*.sql"))


def test_reverse_validation_catches_mutable_restore_input(deployment_workspace):
    original = (deployment_workspace / "source.sql").read_bytes()
    script = deployment_workspace / "deploy/scripts/rollback.sh"
    text = script.read_text()
    assert "' < \"$RESTORE_SNAPSHOT\"" in text
    script.write_text(text.replace("' < \"$RESTORE_SNAPSHOT\"", "' < \"$ROLLBACK_BACKUP\""), newline="\n")
    result, _ = _run_deployment(deployment_workspace, "rollback.sh", TAMPER_SOURCE="1")
    with pytest.raises(AssertionError):
        _assert_restore_uses_verified_bytes(result, deployment_workspace, original)


@pytest.mark.parametrize("phase", ["build", "backup", "start"])
@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
def test_term_signal_exits_nonzero_and_quiesces_partial_start(deployment_workspace, script, phase):
    result, phases = _run_deployment(deployment_workspace, script, SIGNAL_STAGE=phase)
    assert result.returncode == 143, result.stdout + result.stderr
    assert "DEPLOY_OK:" not in result.stdout and "ROLLBACK_OK:" not in result.stdout
    if phase == "build":
        assert "stop" not in phases
    else:
        assert phases[-1] == "stop"
    if phase == "backup":
        assert "migrate" not in phases and "restore" not in phases and "start" not in phases
    assert phases.count("restore") <= 1
    assert not (deployment_workspace / "deploy/.deployment-lock").exists()


@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
def test_failed_emergency_stop_retains_lock(deployment_workspace, script):
    result, phases = _run_deployment(deployment_workspace, script, FAIL_STAGE="stop")
    assert result.returncode != 0 and phases[-2:] == ["stop", "stop"]
    assert (deployment_workspace / "deploy/.deployment-lock").is_dir()
    assert "manual isolation" in result.stderr


def test_rollback_health_failure_retains_pinned_image_override(deployment_workspace):
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", FAIL_STAGE="start")
    assert result.returncode != 0 and phases[-1] == "stop"
    assert len(list((deployment_workspace / "backups").glob("rollback-compose-*.yml"))) == 1
    assert "ROLLBACK_COMPOSE_OVERRIDE:" in result.stdout



def _sqlite_mode(workspace, *, existing=True, default_provider=False):
    (workspace / "deploy/.env").write_text(
        ("" if default_provider else "DB_PROVIDER=sqlite\n") +
        "SECRET_KEY=fixture-secret\nADMIN_DEFAULT_PASSWORD=fixture-admin\n"
        "SQLITE_DB_PATH=/app/storage/state.sqlite\n"
    )
    (workspace / "storage").mkdir()
    if existing:
        with closing(sqlite3.connect(workspace / "storage/state.sqlite")) as db, db:
            db.execute("CREATE TABLE sentinel(value TEXT)")
            db.execute("INSERT INTO sentinel VALUES ('before-deploy')")
    # Real SQLite rollback input; no application database or host docker involved.
    source = workspace / "source.sql"
    source.unlink()
    with closing(sqlite3.connect(source)) as db, db:
        db.execute("CREATE TABLE sentinel(value TEXT)")
        db.execute("INSERT INTO sentinel VALUES ('rollback-original')")
    (workspace / "source.sql.sha256").write_text(hashlib.sha256(source.read_bytes()).hexdigest())
    (workspace / "source.sql.database").write_text("/app/storage/state.sqlite\n")
    (workspace / "source.sql.provider").write_text("sqlite\n")


def _external_mode(workspace):
    text = (workspace / "deploy/.env").read_text()
    text = text.replace("MYSQL_HOST=db", "MYSQL_HOST=mysql.external.example").replace("MYSQL_PORT=3306", "MYSQL_PORT=3309")
    text = text.replace("MYSQL_ROOT_PASSWORD=fixture-root\n", "")
    (workspace / "deploy/.env").write_text(text)


def _assert_no_internal_db(workspace, phases):
    assert "db" not in phases
    log = (workspace / "docker.log").read_text()
    assert "--profile mysql" not in log
    for line in log.splitlines():
        if " run " in line or " up " in line:
            assert "--no-deps" in line


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("default_provider", [True, False])
def test_sqlite_deploy_real_backup_before_migration(deployment_workspace, existing, default_provider):
    _sqlite_mode(deployment_workspace, existing=existing, default_provider=default_provider)
    result, phases = _run_deployment(deployment_workspace, REAL_SQLITE="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert phases == ["version", "info", "config", "build", "stop", "backup", "migrate", "start"]
    _assert_no_internal_db(deployment_workspace, phases)
    backups = list((deployment_workspace / "backups").glob("pre-migrate-*.sqlite"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as db, db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        if existing:
            assert db.execute("SELECT value FROM sentinel").fetchall() == [("before-deploy",)]
        else:
            assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    assert Path(str(backups[0]) + ".provider").read_text().strip() == "sqlite"
    assert Path(str(backups[0]) + ".sha256").read_text().strip() == hashlib.sha256(backups[0].read_bytes()).hexdigest()
    if not existing:
        # The backup step must not create the live database on a first install.
        assert not (deployment_workspace / "storage/state.sqlite").exists()


def test_sqlite_backup_includes_wal_commits(deployment_workspace):
    _sqlite_mode(deployment_workspace)
    live = deployment_workspace / "storage/state.sqlite"
    with closing(sqlite3.connect(live)) as writer, writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO sentinel VALUES ('committed-in-wal')")
        writer.commit()
        assert Path(str(live) + "-wal").stat().st_size > 0
        result, phases = _run_deployment(deployment_workspace, REAL_SQLITE="1")
        assert result.returncode == 0, result.stderr
        backup = next((deployment_workspace / "backups").glob("pre-migrate-*.sqlite"))
        with closing(sqlite3.connect(backup)) as db, db:
            assert db.execute("SELECT value FROM sentinel").fetchall() == [("before-deploy",), ("committed-in-wal",)]


def test_sqlite_rollback_real_restore_and_safety_backup(deployment_workspace):
    _sqlite_mode(deployment_workspace)
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", REAL_SQLITE="1")
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_no_internal_db(deployment_workspace, phases)
    assert phases.index("stop") < phases.index("backup") < phases.index("restore") < phases.index("start")
    assert "migrate" not in phases
    with closing(sqlite3.connect(deployment_workspace / "storage/state.sqlite")) as db, db:
        assert db.execute("SELECT value FROM sentinel").fetchall() == [("rollback-original",)]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    safety = next((deployment_workspace / "backups").glob("pre-restore-*.sqlite"))
    with closing(sqlite3.connect(safety)) as db, db:
        assert db.execute("SELECT value FROM sentinel").fetchall() == [("before-deploy",)]
    assert not list((deployment_workspace / "storage").glob(".restore-*"))


@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
@pytest.mark.parametrize("phase", ["build", "stop", "backup", "start"])
def test_sqlite_failure_matrix(deployment_workspace, script, phase):
    _sqlite_mode(deployment_workspace)
    result, phases = _run_deployment(deployment_workspace, script, FAIL_STAGE=phase, REAL_SQLITE="1")
    assert result.returncode != 0
    _assert_no_internal_db(deployment_workspace, phases)
    if phase == "build":
        assert "stop" not in phases
    else:
        assert phases[-1] == "stop"
    if phase in {"build", "stop", "backup"}:
        assert not set(phases) & {"migrate", "restore", "start"}
    assert phases.count("restore") <= 1


@pytest.mark.parametrize("script,phase", [("deploy_docker.sh", "migrate"), ("rollback.sh", "restore")])
def test_sqlite_database_operation_failure_never_starts_apps(deployment_workspace, script, phase):
    _sqlite_mode(deployment_workspace)
    result, phases = _run_deployment(deployment_workspace, script, FAIL_STAGE=phase, REAL_SQLITE="1")
    assert result.returncode != 0 and "start" not in phases and phases[-1] == "stop"


def test_sqlite_invalid_restore_file_preserves_current_database(deployment_workspace):
    _sqlite_mode(deployment_workspace)
    source = deployment_workspace / "source.sql"
    source.write_bytes(b"not a sqlite database")
    (deployment_workspace / "source.sql.sha256").write_text(hashlib.sha256(source.read_bytes()).hexdigest())
    result, phases = _run_deployment(deployment_workspace, "rollback.sh", REAL_SQLITE="1")
    assert result.returncode != 0 and "start" not in phases and phases[-1] == "stop"
    with closing(sqlite3.connect(deployment_workspace / "storage/state.sqlite")) as db, db:
        assert db.execute("SELECT value FROM sentinel").fetchall() == [("before-deploy",)]


@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
def test_external_mysql_full_order_without_internal_db(deployment_workspace, script):
    _external_mode(deployment_workspace)
    result, phases = _run_deployment(deployment_workspace, script)
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_no_internal_db(deployment_workspace, phases)
    assert phases.index("build") < phases.index("db_probe") < phases.index("stop") < phases.index("backup")
    operation = "restore" if script == "rollback.sh" else "migrate"
    assert phases.index("backup") < phases.index(operation) < phases.index("start")


@pytest.mark.parametrize("script", ["deploy_docker.sh", "rollback.sh"])
@pytest.mark.parametrize("phase", ["build", "db_probe", "stop", "backup", "start"])
def test_external_mysql_failure_matrix(deployment_workspace, script, phase):
    _external_mode(deployment_workspace)
    result, phases = _run_deployment(deployment_workspace, script, FAIL_STAGE=phase)
    assert result.returncode != 0
    _assert_no_internal_db(deployment_workspace, phases)
    if phase in {"build", "db_probe"}:
        assert "stop" not in phases
    else:
        assert phases[-1] == "stop"
    if phase != "start":
        assert not set(phases) & {"migrate", "restore", "start"}
    assert phases.count("restore") <= 1


@pytest.mark.parametrize("script,phase", [("deploy_docker.sh", "migrate"), ("rollback.sh", "restore")])
def test_external_mysql_operation_failure_stops_writers(deployment_workspace, script, phase):
    _external_mode(deployment_workspace)
    result, phases = _run_deployment(deployment_workspace, script, FAIL_STAGE=phase)
    assert result.returncode != 0 and "start" not in phases and phases[-1] == "stop"
    _assert_no_internal_db(deployment_workspace, phases)


def test_reverse_validation_catches_external_mysql_starting_internal_db(deployment_workspace):
    _external_mode(deployment_workspace)
    script = deployment_workspace / "deploy/scripts/deploy_docker.sh"
    text = script.read_text()
    assert 'if [[ "$INTERNAL_MYSQL" == true ]]; then' in text
    script.write_text(text.replace('if [[ "$INTERNAL_MYSQL" == true ]]; then', 'if [[ "$DB_PROVIDER" == mysql ]]; then'), newline="\n")
    result, phases = _run_deployment(deployment_workspace)
    assert result.returncode == 0, result.stderr
    with pytest.raises(AssertionError):
        _assert_no_internal_db(deployment_workspace, phases)


def test_reverse_validation_catches_sqlite_backup_without_data(deployment_workspace):
    _sqlite_mode(deployment_workspace)
    script = deployment_workspace / "deploy/scripts/deploy_docker.sh"
    text = script.read_text()
    assert "source.backup(target)" in text
    script.write_text(text.replace("source.backup(target)", "pass # broken backup"), newline="\n")
    result, phases = _run_deployment(deployment_workspace, REAL_SQLITE="1")
    assert result.returncode == 0, result.stderr
    backup = next((deployment_workspace / "backups").glob("pre-migrate-*.sqlite"))
    with closing(sqlite3.connect(backup)) as db, db:
        with pytest.raises(AssertionError):
            assert db.execute("SELECT name FROM sqlite_master WHERE name='sentinel'").fetchall() == [("sentinel",)]
