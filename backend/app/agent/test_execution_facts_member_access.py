from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import AgentCapabilityExecution, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.services.agent_runtime import AgentRuntimeService


async def _project_run_with_execution(task_session):
    owner = User(id=78101, username='facts-owner', email='facts-owner@example.com', hashed_password='x', is_active=True)
    viewer = User(id=78102, username='facts-viewer', email='facts-viewer@example.com', hashed_password='x', is_active=True)
    editor = User(id=78103, username='facts-editor', email='facts-editor@example.com', hashed_password='x', is_active=True)
    outsider = User(id=78104, username='facts-outsider', email='facts-outsider@example.com', hashed_password='x', is_active=True)
    project = NovelProject(id='facts-member-project', user_id=owner.id, title='执行事实成员访问')
    task_session.add_all([
        owner,
        viewer,
        editor,
        outsider,
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
    ])
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(
        session_id=agent_session.id,
        user_id=owner.id,
        project_id=project.id,
        context={
            'response_provider_attempts': {
                'provider_attempts': [
                    {'attempt': 1, 'status': 'failed', 'error_category': 'TIMEOUT'},
                    {'attempt': 2, 'status': 'succeeded', 'output_digest': 'a' * 64},
                ],
                'selected_provider_attempt': 2,
                'fallback_used': True,
            },
        },
    )
    task_session.add(AgentCapabilityExecution(
        execution_id='facts-member-execution',
        run_id=run.id,
        transaction_id=run.transaction_id,
        correlation_id=run.correlation_id,
        capability_id='project.context',
        status='completed',
        attempt=1,
        idempotency_key='facts-member-execution-key',
        input_json={'project_id': project.id},
        output_json={'content': 'PRIVATE_PROSE'},
        input_digest='b' * 64,
        output_digest='c' * 64,
    ))
    await task_session.commit()
    return SimpleNamespace(owner=owner, viewer=viewer, editor=editor, outsider=outsider, project=project, run=run)


@pytest.mark.asyncio
@pytest.mark.parametrize('member_kind', ['viewer', 'editor'])
async def test_project_members_can_read_single_run_execution_facts_and_provider_summary(task_session, member_kind):
    fixture = await _project_run_with_execution(task_session)
    member = getattr(fixture, member_kind)

    from app.agent.execution_facts import AgentExecutionFactService

    service = AgentExecutionFactService(task_session)
    facts = await service.list_for_run(run_id=fixture.run.id, user_id=member.id)
    summary = await service.provider_usage_summary(run_id=fixture.run.id, user_id=member.id)

    assert [fact['execution_id'] for fact in facts] == ['facts-member-execution']
    assert 'PRIVATE_PROSE' not in str(facts)
    assert summary['run_id'] == fixture.run.id
    assert summary['total_attempts'] == 2
    assert summary['failed_attempts'] == 1
    assert summary['succeeded_attempts'] == 1
    assert 'provider_attempts' not in str(summary)


@pytest.mark.asyncio
async def test_non_member_is_explicitly_forbidden_from_project_run_execution_facts_and_provider_summary(task_session):
    fixture = await _project_run_with_execution(task_session)

    from app.agent.execution_facts import AgentExecutionFactService

    service = AgentExecutionFactService(task_session)
    for reader in (service.list_for_run, service.provider_usage_summary):
        with pytest.raises(HTTPException) as denied:
            await reader(run_id=fixture.run.id, user_id=fixture.outsider.id)
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_projectless_run_execution_facts_remain_creator_scoped(task_session):
    owner = User(id=78111, username='facts-private-owner', email='facts-private-owner@example.com', hashed_password='x', is_active=True)
    other = User(id=78112, username='facts-private-other', email='facts-private-other@example.com', hashed_password='x', is_active=True)
    task_session.add_all([owner, other])
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id)
    task_session.add(AgentCapabilityExecution(
        execution_id='facts-private-execution',
        run_id=run.id,
        transaction_id=run.transaction_id,
        correlation_id=run.correlation_id,
        capability_id='project.list',
        status='completed',
        attempt=1,
        idempotency_key='facts-private-execution-key',
        input_json={},
        output_json={'content': 'PRIVATE_PROJECTLESS_PROSE'},
    ))
    await task_session.commit()

    from app.agent.execution_facts import AgentExecutionFactNotFound, AgentExecutionFactService

    service = AgentExecutionFactService(task_session)
    assert len(await service.list_for_run(run_id=run.id, user_id=owner.id)) == 1
    assert (await service.provider_usage_summary(run_id=run.id, user_id=owner.id))['run_id'] == run.id
    for reader in (service.list_for_run, service.provider_usage_summary):
        with pytest.raises(AgentExecutionFactNotFound):
            await reader(run_id=run.id, user_id=other.id)
