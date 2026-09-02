from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import AgentCapabilityDefinition, AgentCapabilityExecution, AgentRunCapabilitySnapshot, User
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
