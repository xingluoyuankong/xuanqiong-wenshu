"""Project-member access contracts for Agent Run user controls."""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routers import agent
from app.agent.schemas import AgentRunCommandRequest
from app.models import NovelProject, ProjectMember, User
from app.models.agent import AgentEventRecord
from app.models.project_member import ProjectMemberRole
from app.schemas.user import UserInDB
from app.services.agent_runtime import AgentRuntimeService

PROJECT_ID = "agent-member-control-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    run_id: str


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id),
        username=user.username,
        email=user.email,
        hashed_password=user.hashed_password,
        is_active=True,
        is_admin=bool(user.is_admin),
    )


async def _seed(task_session) -> Fixture:
    owner = User(id=97201, username="agent-control-owner", hashed_password="x", is_active=True)
    editor = User(id=97202, username="agent-control-editor", hashed_password="x", is_active=True)
    viewer = User(id=97203, username="agent-control-viewer", hashed_password="x", is_active=True)
    admin = User(id=97204, username="agent-control-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=97205, username="agent-control-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="Agent 控制成员项目")
    task_session.add_all([
        owner,
        editor,
        viewer,
        admin,
        outsider,
        project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=PROJECT_ID)
    run = await runtime.create_run(session_id=session.id, user_id=owner.id, project_id=PROJECT_ID)
    run.status = "running"
    run.current_phase = "planning"
    await task_session.commit()
    await task_session.refresh(run)
    return Fixture(owner, editor, viewer, admin, outsider, run.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["editor", "admin"])
async def test_project_writer_can_pause_and_resume_owner_run(task_session, member_kind: str):
    fixture = await _seed(task_session)
    principal = _principal(getattr(fixture, member_kind))

    paused = await agent.pause_agent_run(fixture.run_id, session=task_session, current_user=principal)
    assert paused.status == "paused"
    assert paused.user_id == fixture.owner.id

    resumed = await agent.resume_agent_run(fixture.run_id, session=task_session, current_user=principal)
    assert resumed.status == "running"
    assert resumed.user_id == fixture.owner.id


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["viewer", "outsider"])
async def test_read_only_or_nonmember_cannot_control_owner_run(task_session, member_kind: str):
    fixture = await _seed(task_session)

    with pytest.raises(HTTPException) as denied:
        await agent.cancel_agent_run(
            fixture.run_id,
            session=task_session,
            current_user=_principal(getattr(fixture, member_kind)),
        )

    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_member_command_uses_execution_owner_but_records_actor_context(task_session):
    fixture = await _seed(task_session)
    request = AgentRunCommandRequest(
        command_type="pause",
        execution_mode="queued",
        payload_json={"request_source": "member-control-test"},
    )

    command = await agent.submit_agent_run_command(
        fixture.run_id,
        request,
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    assert command.run_id == fixture.run_id
    assert command.user_id == fixture.owner.id
    assert command.status == "requested"
    assert command.payload_json["actor_user_id"] == fixture.editor.id
    assert command.payload_json["request_source"] == "member-control-test"

    stored = await AgentRuntimeService(task_session).get_run_command(
        command_id=command.id,
        user_id=fixture.owner.id,
    )
    assert stored.payload_json["actor_user_id"] == fixture.editor.id
    event = (await task_session.execute(select(AgentEventRecord).where(AgentEventRecord.run_id == fixture.run_id, AgentEventRecord.event_type == "run_command_requested"))).scalar_one()
    assert event.data_json["actor_user_id"] == fixture.editor.id
    assert event.data_json["execution_owner_id"] == fixture.owner.id
