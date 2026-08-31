from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.models import User
from app.services.agent_runtime import AgentRuntimeService


CHILD = r'''
import asyncio
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.services.agent_runtime import AgentRuntimeService

async def wait_for_start(path: str) -> None:
    for _ in range(1500):
        if os.path.exists(path):
            return
        await asyncio.sleep(0.01)
    raise RuntimeError('start barrier timed out')

async def main() -> None:
    await wait_for_start(os.environ['PUBLIC_SUMMARY_START'])
    engine = create_async_engine(
        os.environ['PUBLIC_SUMMARY_DB'],
        connect_args={'timeout': 30},
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            action = os.environ['PUBLIC_SUMMARY_ACTION']
            if action == 'event':
                event = await runtime.append_event(
                    run_id=os.environ['PUBLIC_SUMMARY_RUN_ID'],
                    user_id=int(os.environ['PUBLIC_SUMMARY_USER_ID']),
                    event_type='planner_started',
                    summary='parallel planner event',
                    data={'phase': 'planning'},
                )
            else:
                event = await runtime.append_public_work_summary(
                    run_id=os.environ['PUBLIC_SUMMARY_RUN_ID'],
                    user_id=int(os.environ['PUBLIC_SUMMARY_USER_ID']),
                    summary={
                        'action_id': action,
                        'phase': 'tool_execution',
                        'current_action': f'parallel {action}',
                        'input_scope': [{'kind': 'project'}],
                        'selected_capability': 'project.context',
                        'revision': 0,
                    },
                )
            print(json.dumps({'action': action, 'sequence': event.sequence}, ensure_ascii=True), flush=True)
    finally:
        await engine.dispose()

asyncio.run(main())
'''


@pytest.mark.asyncio
async def test_real_processes_keep_same_run_event_sequence_and_summary_checkpoint_consistent(
    tmp_path: Path,
):
    db_path = tmp_path / 'public-summary-race.sqlite'
    engine = create_async_engine(
        f'sqlite+aiosqlite:///{db_path.as_posix()}',
        connect_args={'timeout': 30},
        poolclass=NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        user = User(
            id=1651,
            username='public-summary-race',
            email='public-summary-race@example.com',
            hashed_password='x',
            is_active=True,
        )
        session.add(user)
        await session.flush()
        runtime = AgentRuntimeService(session)
        agent_session = await runtime.create_session(user_id=user.id)
        run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
        run_id = run.id
        correlation_id = run.correlation_id
    await engine.dispose()

    start = tmp_path / 'start'
    environment = {
        **os.environ,
        'PUBLIC_SUMMARY_DB': f'sqlite+aiosqlite:///{db_path.as_posix()}',
        'PUBLIC_SUMMARY_START': str(start),
        'PUBLIC_SUMMARY_RUN_ID': run_id,
        'PUBLIC_SUMMARY_USER_ID': '1651',
        'PYTHONUTF8': '1',
    }
    processes = [
        subprocess.Popen(
            [sys.executable, '-u', '-c', CHILD],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**environment, 'PUBLIC_SUMMARY_ACTION': action},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
        )
        for action in ('event', 'summary-a', 'summary-b')
    ]
    # All child processes wait on the same barrier before opening their write
    # transactions, so success proves actual multi-process interleaving rather
    # than three serial service calls.
    time.sleep(0.15)
    start.touch()
    outputs = [process.communicate(timeout=45) for process in processes]
    assert all(process.returncode == 0 for process in processes), outputs
    child_events = [json.loads(stdout.strip()) for stdout, _ in outputs]
    assert sorted(item['sequence'] for item in child_events) == [1, 2, 3]

    verify_engine = create_async_engine(
        f'sqlite+aiosqlite:///{db_path.as_posix()}',
        connect_args={'timeout': 30},
        poolclass=NullPool,
    )
    verify_factory = async_sessionmaker(verify_engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with verify_factory() as session:
            runtime = AgentRuntimeService(session)
            run = await runtime.get_run(run_id, 1651)
            events = await runtime.list_events(run_id=run_id, user_id=1651, after_sequence=0, limit=20)
    finally:
        await verify_engine.dispose()

    assert run.correlation_id == correlation_id
    assert run.event_sequence == 3
    assert [(event.sequence, event.event_type) for event in events] in (
        [(1, 'planner_started'), (2, 'public_work_summary'), (3, 'public_work_summary')],
        [(1, 'public_work_summary'), (2, 'planner_started'), (3, 'public_work_summary')],
        [(1, 'public_work_summary'), (2, 'public_work_summary'), (3, 'planner_started')],
    )
    summary_event = next(event for event in events if event.sequence == run.latest_public_summary_sequence)
    assert summary_event.event_type == 'public_work_summary'
    assert summary_event.data_json['action_id'] == run.latest_public_summary_json['action_id']
    assert run.latest_public_summary_json['action_id'] in {'summary-a', 'summary-b'}
