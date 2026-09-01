from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.agent.runner import _record_visible_response_summary, _run_visible_response
from app.models import User
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_runtime import AgentRuntimeService


async def _create_runtime_run(task_session, *, user_id: int):
    user = User(
        id=user_id,
        username=f"conversation-runtime-{user_id}",
        email=f"conversation-runtime-{user_id}@example.com",
        hashed_password="x",
        is_active=True,
    )
    task_session.add(user)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id, title="Conversation runtime")
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    return runtime, session, run


@pytest.mark.asyncio
async def test_visible_response_summary_is_idempotent_incremental_and_recoverable(task_session):
    runtime, session, run = await _create_runtime_run(task_session, user_id=2860)
    await runtime.append_message(
        session_id=session.id,
        user_id=run.user_id,
        role="user",
        content="先整理第一章的冲突。",
    )
    final_message = await runtime.append_message(
        session_id=session.id,
        user_id=run.user_id,
        role="assistant",
        content="第一章应先让主角在选择中付出代价。",
    )
    service = AgentConversationService(task_session)
    first = await service.ensure_visible_response_summary(
        run_id=run.id,
        user_id=run.user_id,
        final_message_sequence=final_message.sequence,
    )
    duplicate = await service.ensure_visible_response_summary(
        run_id=run.id,
        user_id=run.user_id,
        final_message_sequence=final_message.sequence,
    )
    assert duplicate.summary_id == first.summary_id
    assert (first.summary_kind, first.start_message_sequence, first.end_message_sequence) == (
        "visible_response",
        1,
        final_message.sequence,
    )
    assert first.summary_json["final_message_sequence"] == final_message.sequence
    await service.verify_summary(first, verify_source=True)
    await task_session.commit()

    recovered = await service.get_visible_response_summary(
        run_id=run.id,
        user_id=run.user_id,
        final_message_sequence=final_message.sequence,
        verify_source=True,
    )
    assert recovered is not None
    assert recovered.summary_id == first.summary_id

    second_run = await runtime.create_run(session_id=session.id, user_id=run.user_id)
    await runtime.append_message(
        session_id=session.id,
        user_id=run.user_id,
        role="user",
        content="继续保留第二章的悬念。",
    )
    second_final = await runtime.append_message(
        session_id=session.id,
        user_id=run.user_id,
        role="assistant",
        content="第二章末尾只揭示线索，不揭示背后的人。",
    )
    second = await service.ensure_visible_response_summary(
        run_id=second_run.id,
        user_id=run.user_id,
        final_message_sequence=second_final.sequence,
    )
    assert (second.start_message_sequence, second.end_message_sequence) == (
        final_message.sequence + 1,
        second_final.sequence,
    )
    await service.verify_summary(second, verify_source=True)


@pytest.mark.asyncio
async def test_summary_failure_after_final_message_does_not_prevent_run_completion(task_session, monkeypatch):
    runtime, session, run = await _create_runtime_run(task_session, user_id=2861)
    final_message = await runtime.append_message(
        session_id=session.id,
        user_id=run.user_id,
        role="assistant",
        content="最终可见回复已经保存。",
    )

    async def fail_summary(**_kwargs):
        raise RuntimeError("summary storage unavailable")

    monkeypatch.setattr("app.agent.runner._persist_visible_response_summary", fail_summary)
    summary = await _record_visible_response_summary(
        runtime=runtime,
        run_id=run.id,
        user_id=run.user_id,
        final_message_sequence=final_message.sequence,
    )
    assert summary is None
    await runtime.update_run(run_id=run.id, user_id=run.user_id, status="running", phase="assistant_response")
    completed = await runtime.update_run(run_id=run.id, user_id=run.user_id, status="completed", phase="summary")
    messages = await runtime.list_messages(session_id=session.id, user_id=run.user_id)
    events = await runtime.list_events(run_id=run.id, user_id=run.user_id)
    assert completed.status == "completed"
    assert [(message.role, message.content) for message in messages] == [
        ("assistant", "最终可见回复已经保存。"),
    ]
    failure = [event for event in events if event.event_type == "conversation_summary_failed"]
    assert len(failure) == 1
    assert failure[0].data_json["final_message_sequence"] == final_message.sequence
    assert failure[0].data_json["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_runner_archives_summary_after_persisting_final_visible_message(task_session, monkeypatch):
    runtime, session, run = await _create_runtime_run(task_session, user_id=2862)
    await runtime.append_message(
        session_id=session.id,
        user_id=run.user_id,
        role="user",
        content="给我一个开篇冲突。",
    )

    @asynccontextmanager
    async def same_test_session():
        yield task_session

    class FakeVisibleLLM:
        def __init__(self, _session):
            pass

        async def stream_visible_response(self, **_kwargs):
            yield "开篇先让主角失去唯一的退路。"

    monkeypatch.setattr("app.agent.runner.AsyncSessionLocal", lambda: same_test_session())
    monkeypatch.setattr("app.agent.runner.LLMService", FakeVisibleLLM)
    await _run_visible_response(
        run_id=run.id,
        session_id=session.id,
        user_id=run.user_id,
        goal="设计开篇冲突",
        tool_results=[],
        manage_job=False,
        worker_id="conversation-runtime-test",
    )

    completed = await runtime.get_run(run.id, run.user_id)
    messages = await runtime.list_messages(session_id=session.id, user_id=run.user_id)
    summary = await AgentConversationService(task_session).get_visible_response_summary(
        run_id=run.id,
        user_id=run.user_id,
        final_message_sequence=messages[-1].sequence,
        verify_source=True,
    )
    events = await runtime.list_events(run_id=run.id, user_id=run.user_id)
    assert completed.status == "completed"
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "开篇先让主角失去唯一的退路。"
    assert summary is not None
    assert (summary.start_message_sequence, summary.end_message_sequence) == (1, messages[-1].sequence)
    assert len([event for event in events if event.event_type == "conversation_summary_created"]) == 1


@pytest.mark.asyncio
async def test_worker_mode_visible_response_provider_failure_keeps_run_retryable(task_session, monkeypatch):
    """A durable worker must rethrow provider failures without terminalizing its Run."""
    runtime, session, run = await _create_runtime_run(task_session, user_id=2863)
    await runtime.update_run(
        run_id=run.id,
        user_id=run.user_id,
        status="running",
        phase="assistant_response",
        progress=85,
    )

    @asynccontextmanager
    async def same_test_session():
        yield task_session

    class ProviderTimeout(Exception):
        pass

    class FailingVisibleLLM:
        def __init__(self, _session):
            pass

        async def stream_visible_response(self, **_kwargs):
            if False:
                yield ""
            raise ProviderTimeout("fixture-visible-provider-timeout")

    monkeypatch.setattr("app.agent.runner.AsyncSessionLocal", lambda: same_test_session())
    monkeypatch.setattr("app.agent.runner.LLMService", FailingVisibleLLM)

    with pytest.raises(ProviderTimeout, match="fixture-visible-provider-timeout"):
        await _run_visible_response(
            run_id=run.id,
            session_id=session.id,
            user_id=run.user_id,
            goal="验证失败重试",
            tool_results=[],
            manage_job=False,
            worker_id="worker-retry-contract-test",
        )

    stored_run = await runtime.get_run(run.id, run.user_id)
    messages = await runtime.list_messages(session_id=session.id, user_id=run.user_id)
    events = await runtime.list_events(run_id=run.id, user_id=run.user_id)
    event_types = [event.event_type for event in events]

    assert (stored_run.status, stored_run.current_phase) == ("running", "assistant_response_retry")
    assert messages == []
    assert "visible_response_retry_pending" in event_types
    assert "run_failed" not in event_types
    assert event_types.count("assistant_completed") == 0
    assert event_types.count("run_completed") == 0


@pytest.mark.asyncio
async def test_finalize_visible_response_is_atomic_and_idempotent(task_session):
    runtime, session, run = await _create_runtime_run(task_session, user_id=2864)
    await runtime.update_run(
        run_id=run.id,
        user_id=run.user_id,
        status="running",
        phase="assistant_response",
        progress=99,
    )
    completion_data = {
        "phase": "summary",
        "length": 12,
        "provider_called": True,
        "response_provider_called": True,
        "response_provider_fallback_reason": None,
    }

    first = await runtime.finalize_visible_response(
        run_id=run.id,
        user_id=run.user_id,
        session_id=session.id,
        content="只应保存一次的最终回复。",
        completion_data=completion_data,
    )
    duplicate = await runtime.finalize_visible_response(
        run_id=run.id,
        user_id=run.user_id,
        session_id=session.id,
        content="不应再次写入的文本。",
        completion_data=completion_data,
    )

    stored_run = await runtime.get_run(run.id, run.user_id)
    messages = await runtime.list_messages(session_id=session.id, user_id=run.user_id)
    events = await runtime.list_events(run_id=run.id, user_id=run.user_id)
    event_types = [event.event_type for event in events]

    assert duplicate.id == first.id
    assert stored_run.status == "completed"
    assert stored_run.context_json["visible_response_final_message_id"] == first.id
    assert stored_run.context_json["visible_response_final_message_sequence"] == first.sequence
    assert [(message.role, message.content) for message in messages] == [
        ("assistant", "只应保存一次的最终回复。"),
    ]
    assert event_types.count("assistant_completed") == 1
    assert event_types.count("run_completed") == 1
