from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.agent_worker import _parse_args


def test_worker_cli_defaults_and_overrides(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['agent_worker.py', '--worker-id', 'worker-test', '--lease-seconds', '60', '--poll-interval', '0.5'])
    args = _parse_args()
    assert args.worker_id == 'worker-test'
    assert args.lease_seconds == 60
    assert args.poll_interval == 0.5


def test_worker_cli_is_explicit_process_entrypoint():
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'agent_worker.py'
    text = script.read_text(encoding='utf-8')
    assert 'if __name__ == "__main__"' in text
    assert 'await worker.run_forever(stop_event)' in text
    assert 'await engine.dispose()' in text
    assert 'init_db' not in text


@pytest.mark.asyncio
async def test_worker_cli_once_mode_exits_cleanly(tmp_path):
    import os
    import subprocess
    import sys
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.db.base import Base

    db_path = tmp_path / 'worker-cli.sqlite'
    engine = create_async_engine(f'sqlite+aiosqlite:///{db_path.as_posix()}', poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    env = {
        **os.environ,
        'DATABASE_URL': f'sqlite+aiosqlite:///{db_path.as_posix()}',
        'DB_PROVIDER': 'sqlite',
        'SECRET_KEY': 'worker-cli-test-secret-key-abcdefghijklmnopqrstuvwxyz',
        'FILE_LOGGING_ENABLED': 'false',
    }
    result = subprocess.run(
        [sys.executable, 'scripts/agent_worker.py', '--once', '--worker-id', 'cli-once'],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'worker stopped' in (result.stdout + result.stderr).lower()
