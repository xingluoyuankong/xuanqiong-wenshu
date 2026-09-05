"""Project-member contracts for Agent candidate Artifact acceptance."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
import pytest
from fastapi import HTTPException

from app.api.routers import agent
from app.agent.schemas import AgentArtifactAcceptRequest
from app.models import AgentArtifactRef, NovelProject, ProjectMember, User
from app.models.agent import AgentApproval, AgentEventRecord
from app.models.project_member import ProjectMemberRole
from app.schemas.user import UserInDB
from app.services.agent_runtime import AgentRuntimeService

PROJECT_ID = "agent-artifact-member-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    artifact: AgentArtifactRef


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
    owner = User(id=97301, username="artifact-owner", hashed_password="x", is_active=True)
    editor = User(id=97302, username="artifact-editor", hashed_password="x", is_active=True)
    viewer = User(id=97303, username="artifact-viewer", hashed_password="x", is_active=True)
    admin = User(id=97304, username="artifact-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=97305, username="artifact-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="Artifact 成员项目")
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
    agent_session = await runtime.create_session(user_id=owner.id, project_id=PROJECT_ID)
    run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id=PROJECT_ID)
    artifact = await runtime.add_artifact(
        run_id=run.id,
        user_id=owner.id,
        project_id=PROJECT_ID,
        kind="chapter_candidate",
        uri="agent-artifact://member-accept.md",
        sha256="a" * 64,
        metadata={"status": "candidate", "chapter_number": 1, "storage_key": "member-accept.md"},
    )
    return Fixture(owner, editor, viewer, admin, outsider, artifact)


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["editor", "admin"])
async def test_project_writers_can_accept_owner_candidate_with_owner_execution_identity(task_session, monkeypatch, member_kind: str):
    fixture = await _seed(task_session)
    captured: dict[str, int] = {}

    async def fake_execute_registered_approval(*, approval_id: str, session, user_id: int):
        captured["user_id"] = user_id
        return fixture.artifact

    monkeypatch.setattr(agent, "_execute_registered_approval", fake_execute_registered_approval)
    result = await agent.accept_agent_artifact(
        fixture.artifact.id,
        AgentArtifactAcceptRequest(note="成员接受"),
        session=task_session,
        current_user=_principal(getattr(fixture, member_kind)),
    )

    assert result.id == fixture.artifact.id
    assert captured["user_id"] == fixture.owner.id
    approval = (await task_session.execute(select(AgentApproval).where(AgentApproval.run_id == fixture.artifact.run_id))).scalar_one()
    assert approval.request_json["actor_user_id"] == getattr(fixture, member_kind).id
    event = (await task_session.execute(select(AgentEventRecord).where(AgentEventRecord.run_id == fixture.artifact.run_id, AgentEventRecord.event_type == "approval_required"))).scalar_one()
    assert event.data_json["actor_user_id"] == getattr(fixture, member_kind).id
    decision_event = (await task_session.execute(select(AgentEventRecord).where(AgentEventRecord.run_id == fixture.artifact.run_id, AgentEventRecord.event_type == "approval_granted"))).scalar_one()
    assert decision_event.data_json["actor_user_id"] == getattr(fixture, member_kind).id
    assert decision_event.data_json["execution_owner_id"] == fixture.owner.id


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["viewer", "outsider"])
async def test_read_only_or_nonmember_cannot_accept_owner_candidate(task_session, member_kind: str):
    fixture = await _seed(task_session)

    with pytest.raises(HTTPException) as denied:
        await agent.accept_agent_artifact(
            fixture.artifact.id,
            AgentArtifactAcceptRequest(note="越权接受"),
            session=task_session,
            current_user=_principal(getattr(fixture, member_kind)),
        )

    assert denied.value.status_code == 403
