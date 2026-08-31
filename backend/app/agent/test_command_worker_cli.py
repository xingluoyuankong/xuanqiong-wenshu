from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.base import Base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from scripts.agent_command_worker import _parse_args


def test_command_worker_cli_parses_overrides(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_command_worker.py",
            "--worker-id",
            "command-cli-test",
            "--lease-seconds",
            "45",
            "--poll-interval",
            "0.4",
            "--once",
        ],
    )
    args = _parse_args()
    assert args.worker_id == "command-cli-test"
    assert args.lease_seconds == 45
    assert args.poll_interval == 0.4
    assert args.once is True


def test_command_worker_cli_is_independent_entrypoint():
    script = Path(__file__).resolve().parents[2] / "scripts" / "agent_command_worker.py"
    text = script.read_text(encoding="utf-8")
    assert "CommandWorker" in text
    assert "await worker.run_forever(stop_event)" in text
    assert 'if __name__ == "__main__"' in text
    assert "init_db" not in text


@pytest.mark.asyncio
async def test_command_worker_cli_once_exits_cleanly_on_empty_database(tmp_path):
    db_path = tmp_path / "command-worker-cli.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        poolclass=NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}",
        "DB_PROVIDER": "sqlite",
        "SECRET_KEY": "command-worker-cli-secret-key-abcdefghijklmnopqrstuvwxyz",
        "FILE_LOGGING_ENABLED": "false",
    }
    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_command_worker.py",
            "--once",
            "--worker-id",
            "command-cli-once",
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "command worker stopped" in (result.stdout + result.stderr).lower()
