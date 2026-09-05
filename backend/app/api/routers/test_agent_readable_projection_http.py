from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from app.api.routers import agent
from app.core.security import hash_password
from app.core.dependencies import get_current_user, get_session
from app.db import session as db_session
from app.db.base import Base
from app.main import app
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.services.agent_context_service import AgentContextService
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_plan_service import AgentPlanService
from app.services.agent_runtime import AgentRuntimeService

PASSWORD = "AgentProjectionHttp123!"
PROJECT_ID = "agent-projection-http-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    private_owner: User
    private_reader: User
    session_id: str
    run_id: str
    private_session_id: str
    private_run_id: str


async def _seed(session) -> Fixture:
    owner = User(id=97501, username="projection-http-owner", email="projection-http-owner@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    editor = User(id=97502, username="projection-http-editor", email="projection-http-editor@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    viewer = User(id=97503, username="projection-http-viewer", email="projection-http-viewer@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    admin = User(id=97504, username="projection-http-admin", email="projection-http-admin@example.com", hashed_password=hash_password(PASSWORD), is_active=True, is_admin=True)
    outsider = User(id=97505, username="projection-http-outsider", email="projection-http-outsider@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    private_owner = User(id=97506, username="projection-http-private-owner", email="projection-http-private-owner@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    private_reader = User(id=97507, username="projection-http-private-reader", email="projection-http-private-reader@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="Agent projection HTTP project")
    session.add_all([
        owner,
        editor,
        viewer,
        admin,
        outsider,
        private_owner,
        private_reader,
        project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await session.commit()

    runtime = AgentRuntimeService(session)
    agent_session = await runtime.create_session(user_id=owner.id, project_id=PROJECT_ID)
    run = await runtime.create_run(
        session_id=agent_session.id,
        user_id=owner.id,
        project_id=PROJECT_ID,
        context={
            "goal": "验证共享历史投影",
            "plan_mode": "explore",
            "planner_provider_called": True,
            "planner_provider_attempts": {"provider_attempts": [{"status": "succeeded", "provider": "fixture"}]},
            "response_provider_called": False,
            "plan_steps": [{"order": 1, "tool_name": "project.context", "intent": "读取项目上下文"}],
        },
    )
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=owner.id,
        step_order=1,
        tool_name="chapter.version.accept",
        idempotency_key="projection-http-step",
        input_payload={"artifact_id": "projection-http-artifact"},
    )
    await runtime.request_approval(
        run_id=run.id,
        user_id=owner.id,
        tool_name="chapter.version.accept",
        project_id=PROJECT_ID,
        step_id=step.id,
        arguments={"artifact_id": "projection-http-artifact"},
    )
    await runtime.add_artifact(
        run_id=run.id,
        user_id=owner.id,
        project_id=PROJECT_ID,
        kind="chapter_candidate",
        uri="agent-artifact://projection-http-artifact",
        metadata={"status": "candidate"},
    )
    await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=owner.id,
        summary={"action_id": "projection-http", "phase": "planning", "current_action": "共享投影验收"},
    )
    await runtime.append_event(
        run_id=run.id,
        user_id=owner.id,
        event_type="task_completed",
        summary="共享投影验收完成",
        data={"fixture": True},
    )

    snapshot = await AgentContextService(session).create_snapshot(
        run=run,
        session=agent_session,
        context_json={"fixture": "shared-context"},
        refs=[{"ref_type": "project", "ref_key": PROJECT_ID, "role": "current_scope"}],
    )
    await AgentPlanService(session).create_revision(
        run=run,
        session=agent_session,
        context_snapshot=snapshot,
        plan_json={"goal": "共享历史投影", "mode": "explore", "provider_called": True, "steps": [{"order": 1, "tool_name": "project.context", "intent": "读取项目上下文"}]},
        status="ready",
    )
    first = await runtime.append_message(session_id=agent_session.id, user_id=owner.id, role="user", content="请读取共享项目")
    second = await runtime.append_message(session_id=agent_session.id, user_id=owner.id, role="assistant", content="已读取共享项目")
    summary = await AgentConversationService(session).create_summary(
        session=agent_session,
        run=run,
        start_message_sequence=first.sequence,
        end_message_sequence=second.sequence,
        summary_text="共享历史摘要",
        summary_json={"fixture": True},
    )
    await session.commit()

    private_session = await runtime.create_session(user_id=private_owner.id)
    private_run = await runtime.create_run(session_id=private_session.id, user_id=private_owner.id, project_id=None)
    await runtime.append_event(run_id=private_run.id, user_id=private_owner.id, event_type="task_completed", summary="私有任务完成")
    await session.commit()
    return Fixture(owner, editor, viewer, admin, outsider, private_owner, private_reader, agent_session.id, run.id, private_session.id, private_run.id)


@pytest.fixture
async def http_jwt(task_session):
    connection = await task_session.connection()
    await connection.run_sync(Base.metadata.create_all)
    fixture = await _seed(task_session)

    async def override_session():
        yield task_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[db_session.get_session] = override_session
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://agent-projection-http") as client:
        tokens = {}
        for user in (fixture.owner, fixture.editor, fixture.viewer, fixture.admin, fixture.outsider, fixture.private_owner, fixture.private_reader):
            response = await client.post("/api/auth/login", data={"username": user.username, "password": PASSWORD})
            assert response.status_code == 200, response.text
            tokens[user.username] = response.json()["access_token"]

        def headers(user: User) -> dict[str, str]:
            return {"Authorization": f"Bearer {tokens[user.username]}"}

        yield client, fixture, headers

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(db_session.get_session, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("member_field", ["owner", "editor", "viewer", "admin"])
async def test_real_jwt_project_members_read_all_agent_history_projections(http_jwt, member_field: str):
    client, fixture, headers = http_jwt
    member = getattr(fixture, member_field)
    routes = [
        f"/api/agent/runs/{fixture.run_id}/plan",
        f"/api/agent/runs/{fixture.run_id}/provider-provenance",
        f"/api/agent/runs/{fixture.run_id}/context-snapshot",
        f"/api/agent/runs/{fixture.run_id}/plan-revision",
        f"/api/agent/runs/{fixture.run_id}/conversation-summaries",
        f"/api/agent/runs/{fixture.run_id}/commands",
        f"/api/agent/runs/{fixture.run_id}/approvals",
        f"/api/agent/runs/{fixture.run_id}/steps",
        f"/api/agent/runs/{fixture.run_id}/artifacts",
    ]
    for route in routes:
        response = await client.get(route, headers=headers(member))
        assert response.status_code == 200, (route, response.text)

    plan = (await client.get(routes[0], headers=headers(member))).json()
    snapshot = (await client.get(routes[2], headers=headers(member))).json()
    revision = (await client.get(routes[3], headers=headers(member))).json()
    summaries = (await client.get(routes[4], headers=headers(member))).json()
    assert plan["created_by_user_id"] == fixture.owner.id
    assert snapshot["user_id"] == fixture.owner.id
    assert revision["user_id"] == fixture.owner.id
    assert summaries[0]["summary_text"] == "共享历史摘要"


@pytest.mark.asyncio
@pytest.mark.parametrize("route_suffix", ["plan", "provider-provenance", "context-snapshot", "plan-revision", "conversation-summaries", "commands", "approvals", "steps", "artifacts"])
async def test_real_jwt_nonmember_is_rejected_from_agent_history_projections(http_jwt, route_suffix: str):
    client, fixture, headers = http_jwt
    response = await client.get(f"/api/agent/runs/{fixture.run_id}/{route_suffix}", headers=headers(fixture.outsider))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_real_jwt_projectless_history_remains_creator_private(http_jwt):
    client, fixture, headers = http_jwt
    owner_response = await client.get(
        f"/api/agent/runs/{fixture.private_run_id}/activity",
        headers=headers(fixture.private_owner),
    )
    reader_response = await client.get(
        f"/api/agent/runs/{fixture.private_run_id}/activity",
        headers=headers(fixture.private_reader),
    )
    assert owner_response.status_code == 200
    assert reader_response.status_code == 404

@pytest.mark.asyncio
async def test_real_jwt_paginated_history_keeps_member_scope_and_legacy_shape(http_jwt):
    client, fixture, headers = http_jwt

    for route_suffix in ("commands", "steps", "artifacts"):
        member_response = await client.get(
            f"/api/agent/runs/{fixture.run_id}/{route_suffix}?limit=1&offset=0",
            headers=headers(fixture.editor),
        )
        assert member_response.status_code == 200, (route_suffix, member_response.text)
        payload = member_response.json()
        assert set(("run_id", "items", "total", "limit", "offset", "has_more", "next_offset")) <= set(payload)
        assert payload["run_id"] == fixture.run_id
        assert payload["limit"] == 1
        assert payload["offset"] == 0
        assert isinstance(payload["items"], list)

        outsider_response = await client.get(
            f"/api/agent/runs/{fixture.run_id}/{route_suffix}?limit=1&offset=0",
            headers=headers(fixture.outsider),
        )
        assert outsider_response.status_code == 403, (route_suffix, outsider_response.text)

    legacy_response = await client.get(
        f"/api/agent/runs/{fixture.run_id}/steps",
        headers=headers(fixture.editor),
    )
    assert legacy_response.status_code == 200
    assert isinstance(legacy_response.json(), list)
