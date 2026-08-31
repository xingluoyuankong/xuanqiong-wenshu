from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.jobs import AgentJobService
from app.db.base import Base
from app.models import User
from app.services.agent_runtime import AgentRuntimeService

CHILD_LINES = [
    'import asyncio, json, os',
    'from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine',
    'from sqlalchemy.pool import NullPool',
    'from app.agent.jobs import AgentJobService',
    'async def main():',
    "    engine = create_async_engine(os.environ['CLAIM_DB'], connect_args={'timeout': 30}, poolclass=NullPool)",
    "    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)",
    "    async with factory() as session:",
    "        job = await AgentJobService(session).claim_next_job(lease_owner=os.environ['CLAIM_WORKER'], lease_seconds=60)",
    "        print(json.dumps({'job_id': job.id if job else None, 'worker': os.environ['CLAIM_WORKER']}), flush=True)",
    "    await engine.dispose()",
    'asyncio.run(main())',
]

@pytest.mark.asyncio
async def test_two_real_processes_only_one_claims_same_sqlite_job(tmp_path: Path):
    db_path = tmp_path / 'claim.sqlite'
    engine = create_async_engine(f'sqlite+aiosqlite:///{db_path.as_posix()}', connect_args={'timeout': 30}, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        user = User(id=1601, username='multi-claim', email='multi-claim@example.com', hashed_password='x', is_active=True)
        session.add(user)
        await session.flush()
        runtime = AgentRuntimeService(session)
        agent_session = await runtime.create_session(user_id=user.id)
        run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
        await AgentJobService(session).create_job(run_id=run.id, user_id=user.id, project_id=None, kind='demo', idempotency_key='multi-process')
    await engine.dispose()
    child = '\n'.join(CHILD_LINES)
    env_base = os.environ.copy()
    env_base['CLAIM_DB'] = f'sqlite+aiosqlite:///{db_path.as_posix()}'
    processes = []
    for worker in ('process-a', 'process-b'):
        env = {**env_base, 'CLAIM_WORKER': worker}
        processes.append(subprocess.Popen([sys.executable, '-u', '-c', child], cwd=str(Path(__file__).resolve().parents[2]), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    outputs = [proc.communicate(timeout=30) for proc in processes]
    assert all(proc.returncode == 0 for proc in processes), outputs
    claims = [json.loads(stdout.strip())['job_id'] for stdout, _ in outputs]
    assert claims.count(None) == 1
    assert len([item for item in claims if item]) == 1


@pytest.mark.asyncio
async def test_real_process_lease_expiry_allows_takeover_after_termination(tmp_path: Path):
    db_path = tmp_path / 'takeover.sqlite'
    engine = create_async_engine(f'sqlite+aiosqlite:///{db_path.as_posix()}', connect_args={'timeout': 30}, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        user = User(id=1602, username='lease-takeover', email='lease-takeover@example.com', hashed_password='x', is_active=True)
        session.add(user)
        await session.flush()
        runtime = AgentRuntimeService(session)
        agent_session = await runtime.create_session(user_id=user.id)
        run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
        job = await AgentJobService(session).create_job(run_id=run.id, user_id=user.id, project_id=None, kind='demo', idempotency_key='takeover')
    await engine.dispose()

    child_lines = [
        'import asyncio, json, os',
        'from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine',
        'from sqlalchemy.pool import NullPool',
        'from app.agent.jobs import AgentJobService',
        'async def main():',
        "    engine = create_async_engine(os.environ['CLAIM_DB'], connect_args={'timeout': 30}, poolclass=NullPool)",
        "    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)",
        "    async with factory() as session:",
        "        job = await AgentJobService(session).claim_next_job(lease_owner=os.environ['CLAIM_WORKER'], lease_seconds=1)",
        "        print(json.dumps({'job_id': job.id if job else None}), flush=True)",
        "        await asyncio.sleep(30)",
        '    await engine.dispose()',
        'asyncio.run(main())',
    ]
    child = '\n'.join(child_lines)
    env = {**os.environ.copy(), 'CLAIM_DB': f'sqlite+aiosqlite:///{db_path.as_posix()}', 'CLAIM_WORKER': 'crashed-process'}
    crashed = subprocess.Popen([sys.executable, '-c', child], cwd=str(Path(__file__).resolve().parents[2]), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = crashed.stdout.readline() if crashed.stdout else ''
        assert json.loads(line)['job_id'] == job.id
        crashed.terminate()
        crashed.wait(timeout=10)
        await asyncio.sleep(2.2)
        takeover = subprocess.run(
            [sys.executable, '-u', '-c', '\n'.join(CHILD_LINES)],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**os.environ.copy(), 'CLAIM_DB': f'sqlite+aiosqlite:///{db_path.as_posix()}', 'CLAIM_WORKER': 'takeover-process'},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert takeover.returncode == 0, takeover.stderr
        assert json.loads(takeover.stdout.strip())['job_id'] == job.id
    finally:
        if crashed.poll() is None:
            crashed.kill()
            crashed.wait(timeout=10)
