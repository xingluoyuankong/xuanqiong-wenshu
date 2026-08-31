from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.api.routers.agent import get_current_user
from app.core.dependencies import get_current_user as dependency_current_user
from app.db.session import get_session
from app.main import app
from sqlalchemy import delete

from app.models import User
from app.models.agent_context import ContextSnapshot
from app.services.agent_context_service import AgentContextService
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_plan_service import AgentPlanService
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, username: str) -> User:
    item = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return item


@pytest.mark.asyncio
async def test_p1_fact_query_http_returns_scoped_facts_and_empty_legacy_projection(task_session):
    owner = await _user(task_session, 1601, "p1-query-owner")
    other = await _user(task_session, 1602, "p1-query-other")
    runtime = AgentRuntimeService(task_session)
    conversation = await runtime.create_session(user_id=owner.id, title="P1 事实查询")
    run = await runtime.create_run(session_id=conversation.id, user_id=owner.id)
    legacy_run = await runtime.create_run(session_id=conversation.id, user_id=owner.id)
    # create_run now writes the P1-A snapshot as part of its normal path.
    # Remove only this fixture row so the API regression also proves the
    # not-yet-wired/legacy empty projection contract.
    await task_session.execute(
        delete(ContextSnapshot).where(ContextSnapshot.run_id == legacy_run.id)
    )
    await task_session.flush()

    context_service = AgentContextService(task_session)
    snapshot = await context_service.create_snapshot(
        run=run,
        session=conversation,
        context_json={"goal": "整理第三章", "visible_only": True},
        refs=[
            {
                "kind": "project",
                "project_id": "fixture-project",
                "role": "selected",
            }
        ],
    )
    revision = await AgentPlanService(task_session).create_revision(
        run=run,
        session=conversation,
        context_snapshot=snapshot,
        plan_json={"steps": [{"tool_name": "chapter.inspect", "order": 1}]},
        planner_id="fixture-planner",
        rationale="先读取章节结构。",
    )
    # Mirror a real replan/current-fact transition: API should expose the Run's
    # explicit immutable locator rather than relying on same-second row ordering.
    current_context = dict(run.context_json or {})
    current_context.update({
        "relational_context_snapshot_id": snapshot.id,
        "relational_context_snapshot_key": snapshot.snapshot_id,
        "relational_plan_revision_id": revision.id,
        "relational_plan_revision_key": revision.revision_id,
    })
    await runtime.set_run_context(
        run_id=run.id,
        user_id=owner.id,
        context=current_context,
        commit=False,
    )
    await runtime.append_message(
        session_id=conversation.id,
        user_id=owner.id,
        role="user",
        content="整理第三章",
        commit=False,
    )
    await runtime.append_message(
        session_id=conversation.id,
        user_id=owner.id,
        role="assistant",
        content="已建立章节整理计划。",
        commit=False,
    )
    await task_session.flush()
    summary = await AgentConversationService(task_session).create_summary(
        session=conversation,
        run=run,
        start_message_sequence=1,
        end_message_sequence=2,
        summary_text="用户要求整理第三章，助手已建立计划。",
        summary_json={"phase": "planning"},
    )
    await task_session.commit()

    # Service methods keep their own Run/Session/User filters; a caller cannot
    # obtain owner facts by passing another user id even if it knows the run id.
    assert await context_service.get_latest_snapshot_for_run(
        run_id=run.id, session_id=conversation.id, user_id=other.id
    ) is None
    assert await AgentPlanService(task_session).get_latest_revision_for_run(
        run_id=run.id, session_id=conversation.id, user_id=other.id
    ) is None
    assert await AgentConversationService(task_session).list_summaries_for_run(
        run_id=run.id, session_id=conversation.id, user_id=other.id
    ) == []

    active_user = SimpleNamespace(id=owner.id)

    async def override_session():
        yield task_session

    async def override_current_user():
        return active_user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[dependency_current_user] = override_current_user
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-test") as client:
            context_response = await client.get(f"/api/agent/runs/{run.id}/context-snapshot")
            revision_response = await client.get(f"/api/agent/runs/{run.id}/plan-revision")
            summaries_response = await client.get(f"/api/agent/runs/{run.id}/conversation-summaries")
            legacy_context_response = await client.get(f"/api/agent/runs/{legacy_run.id}/context-snapshot")
            legacy_revision_response = await client.get(f"/api/agent/runs/{legacy_run.id}/plan-revision")
            legacy_summaries_response = await client.get(f"/api/agent/runs/{legacy_run.id}/conversation-summaries")

            active_user.id = other.id
            denied_response = await client.get(f"/api/agent/runs/{run.id}/context-snapshot")

        assert context_response.status_code == 200
        context_payload = context_response.json()
        assert context_payload["snapshot_id"] == snapshot.snapshot_id
        assert context_payload["run_id"] == run.id
        assert context_payload["session_id"] == conversation.id
        assert context_payload["refs"][0]["ref_key"] == "fixture-project"
        assert context_payload["context_json"] == {"goal": "整理第三章", "visible_only": True}

        assert revision_response.status_code == 200
        revision_payload = revision_response.json()
        assert revision_payload["revision_id"] == revision.revision_id
        assert revision_payload["context_snapshot_id"] == snapshot.id
        assert revision_payload["revision_number"] == 1
        assert revision_payload["plan_json"]["steps"][0]["tool_name"] == "chapter.inspect"

        assert summaries_response.status_code == 200
        summaries_payload = summaries_response.json()
        assert [item["summary_id"] for item in summaries_payload] == [summary.summary_id]
        assert summaries_payload[0]["run_id"] == run.id
        assert summaries_payload[0]["summary_text"] == "用户要求整理第三章，助手已建立计划。"

        assert legacy_context_response.status_code == 200
        assert legacy_context_response.json() is None
        assert legacy_revision_response.status_code == 200
        assert legacy_revision_response.json() is None
        assert legacy_summaries_response.status_code == 200
        assert legacy_summaries_response.json() == []

        assert denied_response.status_code == 404
        assert denied_response.json()["detail"]["code"] == "AGENT_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(dependency_current_user, None)
        app.dependency_overrides.pop(get_current_user, None)


