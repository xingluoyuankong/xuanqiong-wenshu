from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routers import agent as agent_router
from app.models import User
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_reasoning_route_returns_page_with_cursor(task_session):
    user = await _user(task_session, 1811, "reasoning-route")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=0, content="分片一")
    await service.append_assistant_reasoning_chunk(run_id=run.id, user_id=user.id, chunk_index=1, content="分片二")

    page = await agent_router.list_agent_run_reasoning(
        run_id=run.id, after_sequence=0, limit=1, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    assert page.run_id == run.id
    assert len(page.items) == 1
    assert page.has_more is True
    assert page.next_cursor is not None

    next_page = await agent_router.list_agent_run_reasoning(
        run_id=run.id, after_sequence=page.next_cursor, limit=10, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    assert [item.chunk_index for item in next_page.items] == [1]
