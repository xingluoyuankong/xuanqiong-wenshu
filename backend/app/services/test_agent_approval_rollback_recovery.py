from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.agent.schemas import AgentApprovalRead
from app.models import User
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_decide_approval_rehydrates_after_event_sequence_rollback(task_session, monkeypatch):
    user_id = 1801
    task_session.add(
        User(
            id=user_id,
            username="approval-rollback-owner",
            email="approval-rollback-owner@example.com",
            hashed_password="x",
            is_active=True,
        )
    )
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user_id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user_id)
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=user_id,
        step_order=1,
        tool_name="chapter.generate",
        idempotency_key="approval-rollback-step",
        input_payload={"chapter_number": 3},
    )
    step.status = "awaiting_approval"
    await task_session.commit()
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=user_id,
        tool_name="chapter.generate",
        project_id=None,
        arguments={"chapter_number": 3},
        step_id=step.id,
    )
    expected_approval_id = approval.id
    expected_run_id = run.id
    expected_correlation_id = run.correlation_id
    expected_step_id = step.id

    original_commit = task_session.commit
    commit_count = 0

    async def commit_with_one_event_sequence_conflict():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise IntegrityError(
                "INSERT",
                {},
                Exception("UNIQUE constraint failed: agent_events.run_id, agent_events.sequence"),
            )
        return await original_commit()

    monkeypatch.setattr(task_session, "commit", commit_with_one_event_sequence_conflict)

    decided = await runtime.decide_approval(
        approval_id=approval.id,
        user_id=user_id,
        approved=True,
        reason="event retry regression",
    )
    response = AgentApprovalRead.model_validate(decided)

    assert commit_count >= 4
    assert response.id == expected_approval_id
    assert response.run_id == expected_run_id
    assert response.correlation_id == expected_correlation_id
    assert response.step_id == expected_step_id
    assert response.user_id == user_id
    assert response.tool_name == "chapter.generate"
    assert response.status == "approved"
    assert response.reason == "event retry regression"
    assert response.request_json == {"chapter_number": 3}

    events = await runtime.list_events(run_id=expected_run_id, user_id=user_id)
    assert [event.event_type for event in events] == [
        "approval_granted",
        "public_work_summary",
    ]
