from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routers.agent import accept_agent_artifact, execute_agent_approval
from app.agent.schemas import AgentArtifactAcceptRequest
from app.models import NovelProject, User
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_approval_route_dispatches_registered_write_handler(task_session, monkeypatch):
    user = User(id=1401, username='write-handler-owner', email='write-handler@example.com', hashed_password='x', is_active=True)
    task_session.add(user)
    task_session.add(NovelProject(id='write-handler-project', user_id=user.id, title='Write Handler'))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id='write-handler-project')
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id='write-handler-project')
    step = await runtime.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name='chapter.generate', idempotency_key='write-handler-step', input_payload={'chapter_number': 3})
    step.status = 'awaiting_approval'
    await task_session.commit()
    approval = await runtime.request_approval(run_id=run.id, user_id=user.id, step_id=step.id, tool_name='chapter.generate', project_id='write-handler-project', arguments={'chapter_number': 3})
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)
    artifact = await runtime.add_artifact(run_id=run.id, user_id=user.id, project_id='write-handler-project', kind='chapter_candidate', uri='agent-artifact://handler.md', metadata={'status': 'candidate'})
    calls = []

    async def fake_execute(name, **kwargs):
        calls.append((name, kwargs))
        return {'artifact': artifact, 'tool_name': name}

    monkeypatch.setattr('app.api.routers.agent.DEFAULT_TOOL_REGISTRY.execute', fake_execute)
    result = await execute_agent_approval(approval.id, session=task_session, current_user=SimpleNamespace(id=user.id))
    assert result.id == artifact.id
    assert calls[0][0] == 'chapter.generate'
    assert calls[0][1]['arguments']['_approval_id'] == approval.id


@pytest.mark.asyncio
async def test_artifact_accept_route_dispatches_registered_version_accept_handler(task_session, monkeypatch):
    user = User(id=1402, username="version-accept-owner", email="version-accept@example.com", hashed_password="x", is_active=True)
    task_session.add_all([user, NovelProject(id="version-accept-project", user_id=user.id, title="Version Accept")])
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="version-accept-project")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="version-accept-project")
    artifact = await runtime.add_artifact(run_id=run.id, user_id=user.id, project_id="version-accept-project", kind="chapter_candidate", uri="agent-artifact://accept-handler.md", metadata={"status": "candidate"})
    calls = []

    async def fake_execute(name, **kwargs):
        calls.append((name, kwargs))
        artifact.metadata_json = {"status": "accepted", "accepted_version_id": 999}
        await task_session.commit()
        return {"artifact": artifact, "tool_name": name}

    monkeypatch.setattr("app.api.routers.agent.DEFAULT_TOOL_REGISTRY.execute", fake_execute)
    result = await accept_agent_artifact(artifact.id, AgentArtifactAcceptRequest(note="explicit click"), session=task_session, current_user=SimpleNamespace(id=user.id))
    assert result.id == artifact.id
    assert calls[0][0] == "chapter.version.accept"
    assert calls[0][1]["arguments"]["artifact_id"] == artifact.id
    assert calls[0][1]["arguments"]["_approval_id"]
