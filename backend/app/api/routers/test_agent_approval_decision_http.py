from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.api.routers.agent import get_current_user
from app.core.dependencies import get_current_user as dependency_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, User
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_approval_decision_http_serializes_agent_approval_response(task_session):
    user = User(id=1101, username='approval-http-owner', email='approval-http@example.com', hashed_password='x', is_active=True)
    task_session.add(user)
    task_session.add(NovelProject(id='approval-http-project', user_id=user.id, title='Approval HTTP Project'))
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id='approval-http-project')
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id='approval-http-project')
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=user.id,
        step_order=1,
        tool_name='chapter.generate',
        idempotency_key='approval-http-step',
        input_payload={'chapter_number': 3},
    )
    step.status = 'awaiting_approval'
    await task_session.commit()
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=user.id,
        tool_name='chapter.generate',
        project_id='approval-http-project',
        arguments={'chapter_number': 3},
        step_id=step.id,
    )

    async def override_session():
        yield task_session

    async def override_current_user():
        return SimpleNamespace(id=user.id)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[dependency_current_user] = override_current_user
    # The route imports get_current_user directly; keep this explicit alias in
    # the override map so a future import refactor cannot silently bypass auth.
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url='http://agent-test') as client:
            response = await client.post(
                '/api/agent/approvals/' + approval.id + '/decision',
                json={'approved': True, 'reason': 'http response regression'},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload['id'] == approval.id
        assert payload['step_id'] == step.id
        assert payload['status'] == 'approved'
        assert payload['reason'] == 'http response regression'
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(dependency_current_user, None)
        app.dependency_overrides.pop(get_current_user, None)
