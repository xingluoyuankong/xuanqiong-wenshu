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
