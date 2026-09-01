from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import User
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_two_independent_workers_replay_committed_events_by_cursor(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'worker-replay.db').as_posix()}"
    engine = create_async_engine(database_url, connect_args={"check_same_thread": False})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as worker_a, factory() as worker_b:
        user = User(
            id=1401,
            username="durable-worker-owner",
            email="durable-worker-owner@example.com",
            hashed_password="x",
            is_active=True,
        )
        worker_a.add(user)
        await worker_a.commit()

        service_a = AgentRuntimeService(worker_a)
        service_b = AgentRuntimeService(worker_b)
        agent_session = await service_a.create_session(user_id=user.id)
        run = await service_a.create_run(session_id=agent_session.id, user_id=user.id)
        first = await service_a.append_event(
            run_id=run.id,
            user_id=user.id,
            event_type="run_started",
            summary="worker A started",
            data={"phase": "observe"},
        )

        first_replay = await service_b.list_events(run_id=run.id, user_id=user.id, after_sequence=0)
        assert [item.sequence for item in first_replay] == [first.sequence]

        second = await service_a.append_work_trace_delta(
            run_id=run.id,
            user_id=user.id,
            trace_id="worker-trace-2",
            phase="act",
            kind="tool",
            message="Worker A 已提交，Worker B 读取新增事件",
            progress=50,
        )
        second_replay = await service_b.list_events(
            run_id=run.id,
            user_id=user.id,
            after_sequence=first.sequence,
        )
        assert [item.sequence for item in second_replay] == [second.sequence]
        assert second_replay[0].data_json["trace_id"] == "worker-trace-2"

        await service_a.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)
        terminal = await service_a.append_event(
            run_id=run.id,
            user_id=user.id,
            event_type="run_completed",
            summary="worker A completed",
            data={"phase": "finish"},
        )
        terminal_replay = await service_b.list_events(
            run_id=run.id,
            user_id=user.id,
            after_sequence=second.sequence,
        )
        assert [item.sequence for item in terminal_replay] == [terminal.sequence]
        assert terminal_replay[0].event_type == "run_completed"

    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_replay_is_user_scoped_even_when_event_sequence_matches(tmp_path):
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'worker-scope.db').as_posix()}"
    engine = create_async_engine(database_url, connect_args={"check_same_thread": False})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as worker_a, factory() as worker_b:
        owner = User(
            id=1402,
            username="worker-scope-owner",
            email="worker-scope-owner@example.com",
            hashed_password="x",
            is_active=True,
        )
        stranger = User(
            id=1403,
            username="worker-scope-stranger",
            email="worker-scope-stranger@example.com",
            hashed_password="x",
            is_active=True,
        )
        worker_a.add_all([owner, stranger])
        await worker_a.commit()

        service_a = AgentRuntimeService(worker_a)
        service_b = AgentRuntimeService(worker_b)
        agent_session = await service_a.create_session(user_id=owner.id)
        run = await service_a.create_run(session_id=agent_session.id, user_id=owner.id)
        await service_a.append_event(
            run_id=run.id,
            user_id=owner.id,
            event_type="run_started",
            summary="scoped event",
            data={"phase": "observe"},
        )

        with pytest.raises(Exception):
            await service_b.list_events(run_id=run.id, user_id=stranger.id, after_sequence=0)

    await engine.dispose()