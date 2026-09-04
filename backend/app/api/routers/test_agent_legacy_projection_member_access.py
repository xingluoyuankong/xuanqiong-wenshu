from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.api.routers import agent
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.user import UserInDB
from app.services.agent_context_service import AgentContextService
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_plan_service import AgentPlanService
from app.services.agent_runtime import AgentRuntimeService, AgentNotFound


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    private_owner: User
    private_reader: User
    project: NovelProject
    session_id: str
    run_id: str
    private_session_id: str
    private_run_id: str
    step_id: str
    approval_id: str
    artifact_id: str
    snapshot_id: str
    revision_id: str
    summary_id: str


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id),
        username=user.username,
        email=user.email,
        hashed_password=user.hashed_password,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
    )


async def _seed(task_session) -> Fixture:
    owner = User(id=97401, username="agent-projection-owner", email="agent-projection-owner@example.com", hashed_password="x", is_active=True)
    editor = User(id=97402, username="agent-projection-editor", email="agent-projection-editor@example.com", hashed_password="x", is_active=True)
    viewer = User(id=97403, username="agent-projection-viewer", email="agent-projection-viewer@example.com", hashed_password="x", is_active=True)
    admin = User(id=97404, username="agent-projection-admin", email="agent-projection-admin@example.com", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=97405, username="agent-projection-outsider", email="agent-projection-outsider@example.com", hashed_password="x", is_active=True)
    private_owner = User(id=97406, username="agent-projection-private-owner", email="agent-projection-private-owner@example.com", hashed_password="x", is_active=True)
    private_reader = User(id=97407, username="agent-projection-private-reader", email="agent-projection-private-reader@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="agent-projection-member-project", user_id=owner.id, title="Agent 成员投影项目")
    task_session.add_all(
        [
            owner,
            editor,
            viewer,
            admin,
            outsider,
            private_owner,
            private_reader,
            project,
            ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    project_session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(session_id=project_session.id, user_id=owner.id, project_id=project.id)
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=owner.id,
        step_order=1,
        tool_name="chapter.version.accept",
        idempotency_key="agent-projection-step",
        input_payload={"chapter_number": 1},
    )
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=owner.id,
        tool_name="chapter.version.accept",
        project_id=project.id,
        step_id=step.id,
        arguments={"artifact_id": "agent-projection-artifact"},
    )
    task_session.add(SimpleNamespace()) if False else None
    artifact = await runtime.add_artifact(
        run_id=run.id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_candidate",
        uri="memory://agent-projection-artifact",
        metadata={"status": "candidate"},
    )
    await runtime.append_event(
        run_id=run.id,
        user_id=owner.id,
        event_type="task_completed",
        summary="成员投影测试完成",
        data={"artifact_id": artifact.id},
    )

    context_service = AgentContextService(task_session)
    snapshot = await context_service.create_snapshot(
        run=run,
        session=project_session,
        context_json={"chapter_number": 1, "fixture": "member-readable"},
        refs=[{
            "ref_order": 0,
            "ref_type": "chapter",
            "ref_key": "1",
            "ref_version": "v1",
            "role": "target",
            "payload_json": {"title": "第一章"},
        }],
    )
    run.context_json = {
        **dict(run.context_json or {}),
        "relational_context_snapshot_key": snapshot.snapshot_id,
    }
    await task_session.flush()

    revision = await AgentPlanService(task_session).create_revision(
        run=run,
        session=project_session,
        context_snapshot=snapshot,
        plan_json={
            "goal": "读取成员可见计划",
            "mode": "explore",
            "provider_called": False,
            "steps": [{
                "order": 1,
                "tool_name": "chapter.version.accept",
                "intent": "验证候选版本",
                "expected_result": "返回接受结果",
                "depends_on": [],
                "planner_arguments": {"artifact_id": artifact.id},
            }],
        },
        planner_id="member-projection-fixture",
    )

    await runtime.append_message(
        session_id=project_session.id,
        user_id=owner.id,
        role="user",
        content="请读取成员投影",
    )
    await runtime.append_message(
        session_id=project_session.id,
        user_id=owner.id,
        role="assistant",
        content="已生成成员投影",
    )
    summary = await AgentConversationService(task_session).create_summary(
        session=project_session,
        run=run,
        start_message_sequence=1,
        end_message_sequence=2,
        summary_text="成员可读的对话摘要",
        summary_json={"fixture": "member-readable"},
        summary_kind="rolling",
        summarizer_id="test-fixture",
    )
    await task_session.commit()

    private_session = await runtime.create_session(user_id=private_owner.id)
    private_run = await runtime.create_run(session_id=private_session.id, user_id=private_owner.id, project_id=None)
    await runtime.append_event(
        run_id=private_run.id,
        user_id=private_owner.id,
        event_type="task_completed",
        summary="私有投影测试完成",
    )
    await task_session.commit()
    return Fixture(
        owner=owner,
        editor=editor,
        viewer=viewer,
        admin=admin,
        outsider=outsider,
        private_owner=private_owner,
        private_reader=private_reader,
        project=project,
        session_id=project_session.id,
        run_id=run.id,
        private_session_id=private_session.id,
        private_run_id=private_run.id,
        step_id=step.id,
        approval_id=approval.id,
        artifact_id=artifact.id,
        snapshot_id=snapshot.snapshot_id,
        revision_id=revision.revision_id,
        summary_id=summary.summary_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "viewer", "admin"])
async def test_project_members_can_read_agent_legacy_projections(task_session, actor_kind: str):
    fixture = await _seed(task_session)
    principal = _principal(getattr(fixture, actor_kind))

    events = await agent.list_agent_events(
        fixture.session_id,
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    activity = await agent.list_agent_run_activity(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    provenance = await agent.get_agent_run_provider_provenance(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    plan = await agent.get_agent_run_plan(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    snapshot = await agent.get_agent_run_context_snapshot(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    revision = await agent.get_agent_run_latest_plan_revision(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    summaries = await agent.list_agent_run_conversation_summaries(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    approvals = await agent.list_agent_approvals(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    steps = await agent.list_agent_run_steps(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )
    artifacts = await agent.list_agent_artifacts(
        fixture.run_id,
        session=task_session,
        current_user=principal,
    )

    assert events[-1].event_type == "task_completed"
    assert any(item.event_type == "public_work_summary" for item in events)
    assert [(item.sequence, item.event_type) for item in activity] == [(item.sequence, item.event_type) for item in events]
    assert provenance is not None
    assert plan.project_id == fixture.project.id
    assert plan.plan_id is not None
    assert plan.steps[0].tool_name == "chapter.version.accept"
    assert snapshot is not None
    assert snapshot.snapshot_id == fixture.snapshot_id
    assert snapshot.user_id == fixture.owner.id
    assert revision is not None
    assert revision.revision_id == fixture.revision_id
    assert summaries[0].summary_id == fixture.summary_id
    assert [item.id for item in approvals] == [fixture.approval_id]
    assert [item.id for item in steps] == [fixture.step_id]
    assert [item.id for item in artifacts] == [fixture.artifact_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["events", "activity", "provenance", "plan", "snapshot", "revision", "summaries", "approvals", "steps", "artifacts"])
async def test_nonmember_is_rejected_from_agent_legacy_projections(task_session, route: str):
    fixture = await _seed(task_session)
    principal = _principal(fixture.outsider)

    with pytest.raises(HTTPException) as denied:
        if route == "events":
            await agent.list_agent_events(fixture.session_id, fixture.run_id, session=task_session, current_user=principal)
        elif route == "activity":
            await agent.list_agent_run_activity(fixture.run_id, session=task_session, current_user=principal)
        elif route == "provenance":
            await agent.get_agent_run_provider_provenance(fixture.run_id, session=task_session, current_user=principal)
        elif route == "plan":
            await agent.get_agent_run_plan(fixture.run_id, session=task_session, current_user=principal)
        elif route == "snapshot":
            await agent.get_agent_run_context_snapshot(fixture.run_id, session=task_session, current_user=principal)
        elif route == "revision":
            await agent.get_agent_run_latest_plan_revision(fixture.run_id, session=task_session, current_user=principal)
        elif route == "summaries":
            await agent.list_agent_run_conversation_summaries(fixture.run_id, session=task_session, current_user=principal)
        elif route == "approvals":
            await agent.list_agent_approvals(fixture.run_id, session=task_session, current_user=principal)
        elif route == "steps":
            await agent.list_agent_run_steps(fixture.run_id, session=task_session, current_user=principal)
        else:
            await agent.list_agent_artifacts(fixture.run_id, session=task_session, current_user=principal)

    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_projectless_agent_projections_remain_creator_scoped(task_session):
    fixture = await _seed(task_session)
    owner_principal = _principal(fixture.private_owner)
    reader_principal = _principal(fixture.private_reader)

    events = await agent.list_agent_events(
        fixture.private_session_id,
        fixture.private_run_id,
        session=task_session,
        current_user=owner_principal,
    )
    assert events[-1].event_type == "task_completed"
    assert (await agent.list_agent_run_activity(fixture.private_run_id, session=task_session, current_user=owner_principal))[-1].event_type == "task_completed"
    assert (await agent.get_agent_run_provider_provenance(fixture.private_run_id, session=task_session, current_user=owner_principal)) is not None
    assert (await agent.get_agent_run_plan(fixture.private_run_id, session=task_session, current_user=owner_principal)).project_id is None
    private_snapshot = await agent.get_agent_run_context_snapshot(
        fixture.private_run_id, session=task_session, current_user=owner_principal
    )
    assert private_snapshot is not None
    assert private_snapshot.run_id == fixture.private_run_id
    assert await agent.get_agent_run_latest_plan_revision(fixture.private_run_id, session=task_session, current_user=owner_principal) is None
    assert await agent.list_agent_run_conversation_summaries(fixture.private_run_id, session=task_session, current_user=owner_principal) == []
    assert await agent.list_agent_approvals(fixture.private_run_id, session=task_session, current_user=owner_principal) == []
    assert await agent.list_agent_run_steps(fixture.private_run_id, session=task_session, current_user=owner_principal) == []
    assert await agent.list_agent_artifacts(fixture.private_run_id, session=task_session, current_user=owner_principal) == []

    projectless_readers = [
        lambda: agent.list_agent_events(fixture.private_session_id, fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.list_agent_run_activity(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.get_agent_run_provider_provenance(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.get_agent_run_plan(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.get_agent_run_context_snapshot(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.get_agent_run_latest_plan_revision(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.list_agent_run_conversation_summaries(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.list_agent_approvals(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.list_agent_run_steps(fixture.private_run_id, session=task_session, current_user=reader_principal),
        lambda: agent.list_agent_artifacts(fixture.private_run_id, session=task_session, current_user=reader_principal),
    ]
    for read_projection in projectless_readers:
        with pytest.raises(HTTPException) as denied:
            await read_projection()
        assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_project_members_can_read_agent_plan_facts_without_rebinding_owner(task_session):
    fixture = await _seed(task_session)
    principal = _principal(fixture.editor)

    plan = await agent.get_agent_run_plan(
        fixture.run_id, session=task_session, current_user=principal
    )
    provenance = await agent.get_agent_run_provider_provenance(
        fixture.run_id, session=task_session, current_user=principal
    )
    snapshot = await agent.get_agent_run_context_snapshot(
        fixture.run_id, session=task_session, current_user=principal
    )
    revision = await agent.get_agent_run_latest_plan_revision(
        fixture.run_id, session=task_session, current_user=principal
    )
    summaries = await agent.list_agent_run_conversation_summaries(
        fixture.run_id, limit=10, session=task_session, current_user=principal
    )
    commands = await agent.list_agent_run_commands(
        fixture.run_id, limit=10, session=task_session, current_user=principal
    )

    assert plan.project_id == fixture.project.id
    assert plan.created_by_user_id == fixture.owner.id
    assert provenance is not None
    assert snapshot is not None
    assert snapshot.run_id == fixture.run_id
    assert snapshot.session_id == fixture.session_id
    assert revision is not None
    assert revision.run_id == fixture.run_id
    assert revision.session_id == fixture.session_id
    assert revision.user_id == fixture.owner.id
    assert summaries[0].summary_id == fixture.summary_id
    assert commands == []


@pytest.mark.asyncio
async def test_nonmember_cannot_read_agent_plan_facts(task_session):
    fixture = await _seed(task_session)
    principal = _principal(fixture.outsider)

    with pytest.raises(HTTPException) as denied:
        await agent.get_agent_run_plan(
            fixture.run_id, session=task_session, current_user=principal
        )

    assert denied.value.status_code == 403
