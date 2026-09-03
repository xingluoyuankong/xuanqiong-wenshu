from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import User
from app.services.agent_runtime import AgentRuntimeService

_CHILD_SCRIPT = r'''
import asyncio
import json
import sys
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.services.agent_runtime import AgentRuntimeService

async def main():
    database_url, run_id, user_id, cursor = sys.argv[1:]
    engine = create_async_engine(database_url, connect_args={"check_same_thread": False})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        events = await AgentRuntimeService(session).list_events(
            run_id=run_id, user_id=int(user_id), after_sequence=int(cursor), limit=500
        )
        print(json.dumps([
            {"sequence": item.sequence, "event_type": item.event_type, "data": item.data_json}
            for item in events
        ], ensure_ascii=False))
    await engine.dispose()

asyncio.run(main())
'''


def _run_child(database_url: str, run_id: str, user_id: int, cursor: int) -> list[dict]:
    env = dict(os.environ)
    env.update({"DB_PROVIDER": "sqlite", "XUANQIONG_TEST_LIGHT_IMPORTS": "1"})
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT, database_url, run_id, str(user_id), str(cursor)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_independent_python_worker_replays_committed_agent_events(tmp_path):
    database_path = (tmp_path / "subprocess-replay.db").resolve()
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    engine = create_async_engine(database_url, connect_args={"check_same_thread": False})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as worker_a:
        user = User(
            id=1410,
            username="subprocess-worker-owner",
            email="subprocess-worker-owner@example.com",
            hashed_password="x",
            is_active=True,
        )
        worker_a.add(user)
        await worker_a.commit()
        service_a = AgentRuntimeService(worker_a)
        agent_session = await service_a.create_session(user_id=user.id)
        run = await service_a.create_run(session_id=agent_session.id, user_id=user.id)
        first = await service_a.append_event(
            run_id=run.id, user_id=user.id, event_type="run_started", summary="subprocess start", data={"phase": "observe"}
        )

    first_read = _run_child(database_url, run.id, user.id, 0)
    assert [item["sequence"] for item in first_read] == [first.sequence]
    assert first_read[0]["event_type"] == "run_started"

    async with factory() as worker_a:
        service_a = AgentRuntimeService(worker_a)
        second = await service_a.append_work_trace_delta(
            run_id=run.id,
            user_id=user.id,
            trace_id="subprocess-trace",
            phase="act",
            kind="tool",
            message="独立 Python Worker 读取公开轨迹",
            progress=44,
        )
        await service_a.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)
        terminal = await service_a.append_event(
            run_id=run.id, user_id=user.id, event_type="run_completed", summary="subprocess complete", data={"phase": "finish"}
        )

    increment = _run_child(database_url, run.id, user.id, first.sequence)
    assert [item["sequence"] for item in increment] == [second.sequence, terminal.sequence]
    assert increment[0]["event_type"] == "work_trace_delta"
    assert increment[0]["data"]["trace_id"] == "subprocess-trace"
    assert increment[-1]["event_type"] == "run_completed"

    await engine.dispose()