from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import AgentSession, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.services.agent_runtime import AgentRuntimeService, AgentScopeViolation


@pytest.mark.asyncio
async def test_project_member_can_read_run_reasoning_and_activity(task_session):
    owner = User(id=4101, username="agent-owner-4101", hashed_password="x", is_active=True)
    viewer = User(id=4102, username="agent-viewer-4102", hashed_password="x", is_active=True)
    outsider = User(id=4103, username="agent-outsider-4103", hashed_password="x", is_active=True)
    project = NovelProject(id="agent-member-project", user_id=owner.id, title="成员访问")
    task_session.add_all([
        owner,
        viewer,
        outsider,
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(session_id=session.id, user_id=owner.id, project_id=project.id)
    await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=owner.id,
        summary={"action_id": "read", "phase": "planning", "current_action": "读取项目上下文"},
    )
    await runtime.append_assistant_reasoning_chunk(
        run_id=run.id,
        user_id=owner.id,
        chunk_index=0,
        content="原始 Provider reasoning",
    )

    readable = await runtime.get_readable_run(run.id, viewer.id)
    assert readable.id == run.id
    reasoning = await runtime.list_reasoning_chunks_readable(run_id=run.id, user_id=viewer.id)
    activity = await runtime.list_events_readable(run_id=run.id, user_id=viewer.id)
    assert [item.content for item in reasoning] == ["原始 Provider reasoning"]
    assert [item.event_type for item in activity] == ["public_work_summary", "assistant_reasoning_chunk"]

    with pytest.raises(HTTPException) as denied:
        await runtime.get_readable_run(run.id, outsider.id)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_project_session_or_run(task_session):
    owner = User(id=4111, username="writer-owner-4111", hashed_password="x", is_active=True)
    viewer = User(id=4112, username="writer-viewer-4112", hashed_password="x", is_active=True)
    project = NovelProject(id="agent-write-project", user_id=owner.id, title="只读项目")
    task_session.add_all([
        owner,
        viewer,
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    with pytest.raises(AgentScopeViolation):
        await runtime.create_session(user_id=viewer.id, project_id=project.id)


@pytest.mark.asyncio
async def test_editor_can_create_project_session_and_run(task_session):
    owner = User(id=4121, username="writer-owner-4121", hashed_password="x", is_active=True)
    editor = User(id=4122, username="writer-editor-4122", hashed_password="x", is_active=True)
    project = NovelProject(id="agent-editor-project", user_id=owner.id, title="编辑项目")
    task_session.add_all([
        owner,
        editor,
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
    ])
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=editor.id, project_id=project.id)
    run = await runtime.create_run(session_id=session.id, user_id=editor.id, project_id=project.id)
    assert session.user_id == editor.id
    assert run.user_id == editor.id
