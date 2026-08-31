from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routers.agent import list_agent_audit, list_agent_timeline
from app.models import NovelProject, User
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, username: str) -> User:
    user = User(id=user_id, username=username, email=username + '@example.com', hashed_password='x', is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_timeline_is_cross_session_filtered_and_user_scoped(task_session):
    owner = await _user(task_session, 1201, 'timeline-owner')
    other = await _user(task_session, 1202, 'timeline-other')
    task_session.add(NovelProject(id='timeline-project-a', user_id=owner.id, title='Timeline A'))
    task_session.add(NovelProject(id='timeline-project-b', user_id=owner.id, title='Timeline B'))
    task_session.add(NovelProject(id='timeline-project-other', user_id=other.id, title='Timeline Other'))
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    session_a = await runtime.create_session(user_id=owner.id, project_id='timeline-project-a', title='A')
    session_b = await runtime.create_session(user_id=owner.id, project_id='timeline-project-b', title='B')
    session_other = await runtime.create_session(user_id=other.id, project_id='timeline-project-other', title='Other')
    run_a = await runtime.create_run(session_id=session_a.id, user_id=owner.id, project_id='timeline-project-a')
    run_b = await runtime.create_run(session_id=session_b.id, user_id=owner.id, project_id='timeline-project-b')
    run_other = await runtime.create_run(session_id=session_other.id, user_id=other.id, project_id='timeline-project-other')
    await runtime.update_run(run_id=run_a.id, user_id=owner.id, status='completed', phase='summary', progress=100)
    await runtime.update_run(run_id=run_b.id, user_id=owner.id, status='failed', phase='error', progress=50)
    await runtime.append_event(run_id=run_a.id, user_id=owner.id, event_type='tool_call_completed', summary='A completed', data={'tool_name': 'project.context', 'step': 1})
    await runtime.append_event(run_id=run_b.id, user_id=owner.id, event_type='tool_call_failed', summary='B failed', data={'tool_name': 'chapter.inspect', 'error_type': 'TestError'})
    await runtime.append_event(run_id=run_other.id, user_id=other.id, event_type='tool_call_completed', summary='Other completed', data={'tool_name': 'project.context'})

    all_rows = await runtime.list_timeline(user_id=owner.id, limit=20)
    assert {row[0].run_id for row in all_rows} == {run_a.id, run_b.id}
    project_rows = await runtime.list_timeline(user_id=owner.id, project_id='timeline-project-a', limit=20)
    assert {row[0].run_id for row in project_rows} == {run_a.id}
    status_rows = await runtime.list_timeline(user_id=owner.id, run_status='failed', limit=20)
    assert {row[0].run_id for row in status_rows} == {run_b.id}
    tool_rows = await runtime.list_timeline(user_id=owner.id, tool_name='chapter.inspect', limit=20)
    assert {row[0].run_id for row in tool_rows} == {run_b.id}

    api_rows = await list_agent_timeline(
        project_id='timeline-project-a',
        session_id=None,
        run_id=None,
        run_status=None,
        tool_name=None,
        offset=0,
        limit=100,
        event_type='tool_call_completed',
        current_user=SimpleNamespace(id=owner.id),
        session=task_session,
    )
    assert len(api_rows) == 1
    assert api_rows[0].session_id == session_a.id
    assert api_rows[0].project_id == 'timeline-project-a'
    assert api_rows[0].tool_name == 'project.context'
    assert api_rows[0].run_status == 'completed'


@pytest.mark.asyncio
async def test_audit_projection_links_tool_approval_artifact_and_versions(task_session):
    owner = await _user(task_session, 1203, 'audit-owner')
    other = await _user(task_session, 1204, 'audit-other')
    task_session.add(NovelProject(id='audit-project', user_id=owner.id, title='Audit'))
    task_session.add(NovelProject(id='audit-project-other', user_id=other.id, title='Other'))
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id, project_id='audit-project', title='Audit')
    run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id='audit-project')
    approval = await runtime.request_approval(
        run_id=run.id, user_id=owner.id, tool_name='chapter.rewrite',
        project_id='audit-project', arguments={'chapter_number': 3, 'source_version_id': 11},
    )
    artifact = await runtime.add_artifact(
        run_id=run.id, user_id=owner.id, project_id='audit-project',
        kind='chapter_candidate', uri='artifact://audit-candidate',
        metadata={'source_version_id': 11, 'accepted_version_id': 12},
    )
    await runtime.append_event(
        run_id=run.id, user_id=owner.id, event_type='tool_call_completed',
        summary='rewrite tool completed', data={'tool_name': 'chapter.rewrite', 'step': 1, 'phase': 'rewrite'},
    )
    await runtime.append_event(
        run_id=run.id, user_id=owner.id, event_type='approval_granted',
        summary='rewrite approved', data={'approval_id': approval.id, 'tool_name': 'chapter.rewrite', 'status': 'approved'},
    )
    await runtime.append_event(
        run_id=run.id, user_id=owner.id, event_type='artifact_accepted',
        summary='artifact accepted', data={'artifact_id': artifact.id, 'chapter_number': 3, 'version_id': 12},
    )

    rows = await list_agent_audit(
        project_id='audit-project', session_id=None, run_id=None,
        event_type=None, run_status=None, tool_name=None,
        approval_id=None, artifact_id=artifact.id, source_version_id=11,
        offset=0, limit=100, current_user=SimpleNamespace(id=owner.id), session=task_session,
    )
    assert len(rows) == 1
    assert rows[0].event_type == 'artifact_accepted'
    assert rows[0].artifact_id == artifact.id
    assert rows[0].source_version_id == 11
    assert rows[0].accepted_version_id == 12
    assert rows[0].session_id == agent_session.id
    assert rows[0].project_id == 'audit-project'

    approval_rows = await list_agent_audit(
        project_id='audit-project', session_id=None, run_id=None,
        event_type='approval_granted', run_status=None, tool_name=None,
        approval_id=approval.id, artifact_id=None, source_version_id=None,
        offset=0, limit=100, current_user=SimpleNamespace(id=owner.id), session=task_session,
    )
    assert len(approval_rows) == 1
    assert approval_rows[0].approval_id == approval.id
    assert approval_rows[0].tool_name == 'chapter.rewrite'

    other_rows = await list_agent_audit(
        project_id=None, session_id=None, run_id=run.id,
        event_type=None, run_status=None, tool_name=None,
        approval_id=None, artifact_id=None, source_version_id=None,
        offset=0, limit=100, current_user=SimpleNamespace(id=other.id), session=task_session,
    )
    assert other_rows == []
