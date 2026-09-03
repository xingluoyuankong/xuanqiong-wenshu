from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import AgentRunReasoningChunk, NovelProject, User
from app.services.agent_runtime import AgentConflict, AgentRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_reasoning_chunk_is_persisted_separately_and_paginated(task_session):
    user = await _user(task_session, 1801, "reasoning-owner")
    task_session.add(NovelProject(id="project-reasoning", user_id=user.id, title="Reasoning Project"))
    await task_session.flush()
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id, project_id="project-reasoning")
    run = await service.create_run(session_id=agent_session.id, user_id=user.id, project_id="project-reasoning")

    first = await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=0, content="先读取项目上下文。")
    second = await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=1, content="再选择章节工具。")

    assert first.event_type == "assistant_reasoning_chunk"
    assert second.sequence > first.sequence
    rows = await service.list_reasoning_chunks(run_id=run.id, user_id=user.id, limit=1)
    assert len(rows) == 1
    assert rows[0].chunk_index == 0
    assert rows[0].content == "先读取项目上下文。"
    assert rows[0].content_hash
    newer = await service.list_reasoning_chunks(run_id=run.id, user_id=user.id, after_sequence=rows[0].sequence)
    assert [item.chunk_index for item in newer] == [1]


@pytest.mark.asyncio
async def test_reasoning_chunk_duplicate_index_is_rejected(task_session):
    user = await _user(task_session, 1802, "reasoning-unique")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=0, content="same")

    with pytest.raises(AgentConflict):
        await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=0, content="different")

    rows = (await task_session.execute(select(AgentRunReasoningChunk).where(AgentRunReasoningChunk.run_id == run.id))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reasoning_chunk_is_rejected_after_terminal_run(task_session):
    user = await _user(task_session, 1803, "reasoning-terminal")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    await service.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)

    with pytest.raises(AgentConflict):
        await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=0, content="late")
