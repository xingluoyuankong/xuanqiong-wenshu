from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import AgentCapabilityDefinition, AgentCapabilityExecution, AgentRunCapabilitySnapshot, NovelProject, User
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_execution_facts_project_safe_metadata_and_stable_refs(task_session):
    user = User(id=6401, username='execution-facts-owner', email='execution-facts-owner@example.com', hashed_password='x', is_active=True)
    task_session.add(user)
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(
        session_id=agent_session.id,
        user_id=user.id,
        context={'requested_tools': ['project.list']},
    )
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=user.id,
        step_order=1,
        tool_name='project.list',
        idempotency_key='execution-facts-step',
    )
    snapshot = (await task_session.execute(
        select(AgentRunCapabilitySnapshot).where(AgentRunCapabilitySnapshot.run_id == run.id),
    )).scalar_one()
    capability = (await task_session.execute(
        select(AgentCapabilityDefinition).where(
            AgentCapabilityDefinition.catalog_release_id == snapshot.catalog_release_id,
            AgentCapabilityDefinition.capability_id == 'project.list',
        ),
    )).scalar_one()
    task_session.add(AgentCapabilityExecution(
        execution_id='execution-facts-1',
        run_id=run.id,
        transaction_id=run.transaction_id,
        step_id=step.id,
        snapshot_id=snapshot.id,
        capability_definition_id=capability.id,
        provider_release_id=capability.provider_release_id,
        correlation_id=run.correlation_id,
        capability_id='project.list',
        resolved_version=capability.version,
        status='completed',
        attempt=2,
        idempotency_key='execution-facts-idempotency',
        input_json={'project_id': 'p1'},
        output_json={'count': 1, 'content': 'SECRET_PROSE'},
        input_digest='a' * 64,
        output_digest='b' * 64,
        error_type=None,
    ))
    await task_session.commit()

    from app.agent.execution_facts import AgentExecutionFactService
    facts = await AgentExecutionFactService(task_session).list_for_run(run_id=run.id, user_id=user.id)

    assert len(facts) == 1
    fact = facts[0]
    assert fact['execution_id'] == 'execution-facts-1'
    assert fact['result_ref'] == 'execution:execution-facts-1'
    assert fact['action_id'] == f'step:{step.id}'
    assert fact['tool_name'] == 'project.list'
    assert fact['status'] == 'completed'
    assert fact['attempt'] == 2
    assert 'output_json' not in fact
    assert 'SECRET_PROSE' not in str(fact)


@pytest.mark.asyncio
async def test_provider_usage_summary_aggregates_attempt_outcomes_without_raw_output(task_session):
    user = User(id=6404, username='provider-summary-owner', email='provider-summary-owner@example.com', hashed_password='x', is_active=True)
    task_session.add(user)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    run.context_json = {
        'response_provider_attempts': {
            'provider_attempts': [
                {'attempt': 1, 'status': 'failed', 'error_category': 'TIMEOUT', 'first_token_at': '2026-09-02T10:00:00Z', 'output_digest': 'a' * 64},
                {'attempt': 2, 'status': 'failed', 'error_category': 'RATE_LIMIT', 'fallback_from_attempt': 1},
                {'attempt': 3, 'status': 'succeeded', 'first_token_at': '2026-09-02T10:01:00Z', 'output_digest': 'b' * 64},
            ],
            'selected_provider_attempt': 3,
            'fallback_used': True,
        },
        'planner_provider_attempts': {
            'provider_attempts': [{'attempt': 1, 'status': 'succeeded'}],
            'selected_provider_attempt': 1,
            'fallback_used': False,
        },
    }
    await task_session.commit()

    from app.agent.execution_facts import AgentExecutionFactService
    summary = await AgentExecutionFactService(task_session).provider_usage_summary(run_id=run.id, user_id=user.id)

    assert summary['total_attempts'] == 4
    assert summary['succeeded_attempts'] == 2
    assert summary['failed_attempts'] == 2
    assert summary['fallback_attempts'] == 1
    assert summary['first_token_attempts'] == 2
    assert summary['digest_attempts'] == 2
    assert summary['last_error_category'] == 'RATE_LIMIT'
    assert summary['selected_attempts'] == 2
    assert 'output' not in str(summary).lower()


@pytest.mark.asyncio
async def test_execution_facts_are_scoped_to_the_run_owner(task_session):
    owner = User(id=6402, username='execution-facts-owner-2', email='execution-facts-owner-2@example.com', hashed_password='x', is_active=True)
    other = User(id=6403, username='execution-facts-other', email='execution-facts-other@example.com', hashed_password='x', is_active=True)
    task_session.add_all([owner, other])
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id)

    from app.agent.execution_facts import AgentExecutionFactNotFound, AgentExecutionFactService
    with pytest.raises(AgentExecutionFactNotFound):
        await AgentExecutionFactService(task_session).list_for_run(run_id=run.id, user_id=other.id)


@pytest.mark.asyncio
async def test_project_provider_usage_summary_aggregates_bounded_owner_runs_without_payload(task_session):
    owner = User(id=6405, username='project-provider-owner', email='project-provider-owner@example.com', hashed_password='x', is_active=True)
    other = User(id=6406, username='project-provider-other', email='project-provider-other@example.com', hashed_password='x', is_active=True)
    project = NovelProject(id='provider-project-owned', user_id=owner.id, title='Owned provider project')
    other_project = NovelProject(id='provider-project-other', user_id=owner.id, title='Other provider project')
    foreign_project = NovelProject(id='provider-project-foreign', user_id=other.id, title='Foreign provider project')
    task_session.add_all([owner, other, project, other_project, foreign_project])
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    project_session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    other_project_session = await runtime.create_session(user_id=owner.id, project_id=other_project.id)
    foreign_session = await runtime.create_session(user_id=other.id, project_id=foreign_project.id)

    old_run = await runtime.create_run(
        session_id=project_session.id,
        user_id=owner.id,
        project_id=project.id,
        context={
            'response_provider_attempts': {
                'provider_attempts': [
                    {'status': 'failed', 'error_category': 'OLD_ERROR', 'input': 'SECRET_OLD_INPUT', 'output': 'SECRET_OLD_OUTPUT'},
                ],
            },
        },
    )
    first_recent_run = await runtime.create_run(
        session_id=project_session.id,
        user_id=owner.id,
        project_id=project.id,
        context={
            'planner_provider_attempts': {
                'provider_attempts': [
                    {'status': 'failed', 'error_category': 'FIRST_ERROR', 'first_token_at': '2026-09-02T10:00:00Z'},
                    {'status': 'succeeded', 'output_digest': 'a' * 64},
                ],
                'selected_provider_attempt': 2,
            },
        },
    )
    latest_run = await runtime.create_run(
        session_id=project_session.id,
        user_id=owner.id,
        project_id=project.id,
        context={
            'response_provider_attempts': {
                'provider_attempts': [
                    {'status': 'failed', 'error_category': 'LATEST_ERROR', 'fallback_from_attempt': 1, 'input': 'SECRET_INPUT', 'output': 'SECRET_OUTPUT'},
                    {'status': 'succeeded', 'first_token_at': '2026-09-03T10:30:00Z', 'output_digest': 'b' * 64},
                ],
                'selected_provider_attempt': 2,
            },
        },
    )
    excluded_project_run = await runtime.create_run(
        session_id=other_project_session.id,
        user_id=owner.id,
        project_id=other_project.id,
        context={'response_provider_attempts': {'provider_attempts': [{'status': 'failed', 'error_category': 'OTHER_PROJECT_SECRET'}]}},
    )
    foreign_run = await runtime.create_run(
        session_id=foreign_session.id,
        user_id=other.id,
        project_id=foreign_project.id,
        context={'response_provider_attempts': {'provider_attempts': [{'status': 'failed', 'error_category': 'FOREIGN_SECRET'}]}},
    )
    old_run.created_at = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    first_recent_run.created_at = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
    latest_run.created_at = datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc)
    excluded_project_run.created_at = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    foreign_run.created_at = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    await task_session.commit()

    from app.agent.execution_facts import AgentExecutionFactNotFound, AgentExecutionFactService

    service = AgentExecutionFactService(task_session)
    summary = await service.project_provider_usage_summary(
        project_id=project.id,
        user_id=owner.id,
        since=datetime(2026, 9, 2, tzinfo=timezone.utc),
        limit=2,
    )

    assert summary['project_id'] == project.id
    assert summary['run_count'] == 2
    assert summary['attempt_count'] == 4
    assert summary['succeeded_attempts'] == 2
    assert summary['failed_attempts'] == 2
    assert summary['fallback_attempts'] == 1
    assert summary['first_token_attempts'] == 2
    assert summary['digest_attempts'] == 2
    assert summary['selected_attempts'] == 2
    assert summary['last_error_category'] == 'LATEST_ERROR'
    assert summary['latest_attempt_at'] == '2026-09-03T10:30:00Z'
    assert [item['run_id'] for item in summary['runs']] == [latest_run.id, first_recent_run.id]
    assert summary['runs'][0]['attempt_count'] == 2
    assert summary['runs'][0]['last_error_category'] == 'LATEST_ERROR'
    assert summary['runs'][1]['attempt_count'] == 2
    assert summary['runs'][1]['last_error_category'] == 'FIRST_ERROR'
    assert old_run.id not in {item['run_id'] for item in summary['runs']}
    assert excluded_project_run.id not in {item['run_id'] for item in summary['runs']}
    assert foreign_run.id not in {item['run_id'] for item in summary['runs']}
    assert 'SECRET_INPUT' not in str(summary)
    assert 'SECRET_OUTPUT' not in str(summary)
    assert 'SECRET_OLD_INPUT' not in str(summary)

    limited = await service.project_provider_usage_summary(project_id=project.id, user_id=owner.id, limit=1)
    assert limited['run_count'] == 1
    assert limited['runs'][0]['run_id'] == latest_run.id

    with pytest.raises(AgentExecutionFactNotFound):
        await service.project_provider_usage_summary(project_id=project.id, user_id=other.id)
