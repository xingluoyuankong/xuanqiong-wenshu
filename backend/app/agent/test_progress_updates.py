from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.agent.runner import _run_visible_response
from app.agent.runner import release_cancel_event
from app.models import User
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_publish_progress_is_persisted_visible_and_monotonic(task_session):
    user = User(
        id=4101,
        username="progress-owner",
        email="progress-owner@example.com",
        hashed_password="x",
        is_active=True,
    )
    task_session.add(user)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)

    first = await runtime.publish_progress(
        run_id=run.id,
        user_id=user.id,
        status="planning",
        phase="planning",
        action_id="plan:build",
        result_ref="response:progress-run",
        progress=20,
        progress_message="正在构建计划。",
    )
    second = await runtime.publish_progress(
        run_id=run.id,
        user_id=user.id,
        status="running",
        phase="tool_execution",
        action_id="tool:chapter.inspect",
        step=1,
        tool_name="chapter.inspect",
        progress=10,
        progress_message="正在执行章节检查。",
    )

    assert first.progress == 20
    assert second.progress == 20
    assert second.status == "running"
    events = await runtime.list_events(run_id=run.id, user_id=user.id, after_sequence=0)
    progress_events = [event for event in events if event.event_type == "progress_update"]
    assert [event.data_json["progress"] for event in progress_events] == [20.0, 20.0]
    assert progress_events[0].data_json["result_ref"] == "response:progress-run"
    assert progress_events[-1].data_json == {
        "progress": 20.0,
        "phase": "tool_execution",
        "action_id": "tool:chapter.inspect",
        "progress_message": "正在执行章节检查。",
        "step": 1,
        "tool_name": "chapter.inspect",
    }


@pytest.mark.asyncio
async def test_append_event_retries_one_agent_event_sequence_conflict(task_session, monkeypatch):
    user = User(
        id=4102,
        username="event-retry-owner",
        email="event-retry-owner@example.com",
        hashed_password="x",
        is_active=True,
    )
    task_session.add(user)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)

    run_id = run.id
    user_id = user.id
    original_commit = task_session.commit
    attempts = 0

    async def conflict_once():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IntegrityError(
                "INSERT INTO agent_events",
                {},
                Exception("UNIQUE constraint failed: agent_events.run_id, agent_events.sequence"),
            )
        await original_commit()

    monkeypatch.setattr(task_session, "commit", conflict_once)

    event = await runtime.append_event(
        run_id=run_id,
        user_id=user_id,
        event_type="planner_started",
        summary="并发序列重试",
        data={"phase": "planning"},
    )

    assert attempts == 2
    assert event.sequence == 1
    events = await runtime.list_events(run_id=run_id, user_id=user_id, after_sequence=0)
    assert [(item.sequence, item.event_type) for item in events] == [(1, "planner_started")]


@pytest.mark.asyncio
async def test_visible_response_emits_progress_for_start_delta_and_save(monkeypatch):
    events: list[dict] = []
    messages: list[str] = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRuntime:
        async def claim_run(self, **kwargs):
            return SimpleNamespace(id=kwargs["run_id"], status="running", progress=80, lease_generation=0)

        async def get_run(self, *args, **kwargs):
            run_id = args[0] if args else kwargs["run_id"]
            return SimpleNamespace(id=run_id, status="running", context_json={})

        async def append_event(self, **kwargs):
            events.append(kwargs)

        async def append_public_work_summary(self, **kwargs):
            events.append({"event_type": "public_work_summary", "data": kwargs["summary"]})

        async def publish_progress(self, **kwargs):
            events.append({"event_type": "progress_update", "data": {key: value for key, value in kwargs.items() if key not in {"run_id", "user_id", "status"}}})
            return SimpleNamespace(progress=kwargs["progress"], status=kwargs["status"])

        async def append_message(self, **kwargs):
            messages.append(kwargs["content"])
            return SimpleNamespace(sequence=1)


        async def finalize_visible_response(self, **kwargs):
            messages.append(kwargs["content"])
            return SimpleNamespace(sequence=1)
        async def update_run(self, **kwargs):
            return SimpleNamespace(progress=kwargs.get("progress"), status=kwargs["status"])

        async def update_run_provider_provenance(self, **kwargs):
            events.append({"event_type": "provider_provenance", "data": kwargs["updates"]})
            return SimpleNamespace(context_json=dict(kwargs["updates"]))

    class FakeLLM:
        async def stream_visible_response(self, **kwargs):
            yield "甲" * 300
            yield "。"

    async def always_runnable(*args, **kwargs):
        return True

    async def heartbeat(*args, **kwargs):
        await asyncio.Event().wait()

    fake_runtime = FakeRuntime()
    monkeypatch.setattr("app.agent.runner.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr("app.agent.runner.AgentRuntimeService", lambda session: fake_runtime)
    monkeypatch.setattr("app.agent.runner.LLMService", lambda session: FakeLLM())
    monkeypatch.setattr("app.agent.runner._wait_until_runnable", always_runnable)
    monkeypatch.setattr("app.agent.runner._lease_heartbeat", heartbeat)

    run_id = "progress-visible-run"
    await _run_visible_response(
        run_id=run_id,
        session_id="session-progress",
        user_id=1,
        goal="输出可见回复",
        tool_results=[],
        manage_job=False,
    )

    progress = [entry["data"] for entry in events if entry["event_type"] == "progress_update"]
    assert progress[0]["progress"] == 85
    assert progress[0]["progress_message"] == "正在整理工具结果并生成可见回复。"
    assert progress[0]["action_id"] == "response:started"
    assert all(item["result_ref"] == f"response:{run_id}" for item in progress)
    assert any(item["progress"] > 85 and item["progress"] <= 95 for item in progress)
    assert progress[-1]["progress"] == 99
    assert messages == ["甲" * 300 + "。"]
    release_cancel_event(run_id)


@pytest.mark.asyncio
async def test_worker_visible_response_timeout_records_retry_provenance_and_reraises(monkeypatch):
    events: list[dict] = []
    provenance: list[dict] = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRuntime:
        async def claim_run(self, **kwargs):
            return SimpleNamespace(id=kwargs["run_id"], status="running", progress=80, lease_generation=0)

        async def get_run(self, *args, **kwargs):
            run_id = args[0] if args else kwargs["run_id"]
            return SimpleNamespace(id=run_id, status="running", context_json={})

        async def update_run_provider_provenance(self, **kwargs):
            provenance.append(dict(kwargs["updates"]))
            return SimpleNamespace(context_json=dict(kwargs["updates"]))

        async def append_event(self, **kwargs):
            events.append(kwargs)

        async def append_public_work_summary(self, **kwargs):
            events.append({"event_type": "public_work_summary", "data": kwargs["summary"]})

        async def publish_progress(self, **kwargs):
            return SimpleNamespace(progress=kwargs["progress"], status=kwargs["status"])

        async def update_run(self, **kwargs):
            return SimpleNamespace(progress=kwargs.get("progress"), status=kwargs["status"])

    class TimeoutLLM:
        async def stream_visible_response(self, **kwargs):
            raise TimeoutError("response timeout fixture")
            yield "unreachable"

    async def always_runnable(*args, **kwargs):
        return True

    async def heartbeat(*args, **kwargs):
        await asyncio.Event().wait()

    fake_runtime = FakeRuntime()
    monkeypatch.setattr("app.agent.runner.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr("app.agent.runner.AgentRuntimeService", lambda session: fake_runtime)
    monkeypatch.setattr("app.agent.runner.LLMService", lambda session: TimeoutLLM())
    monkeypatch.setattr("app.agent.runner._wait_until_runnable", always_runnable)
    monkeypatch.setattr("app.agent.runner._lease_heartbeat", heartbeat)

    with pytest.raises(TimeoutError, match="response timeout fixture"):
        await _run_visible_response(
            run_id="response-timeout-run",
            session_id="response-timeout-session",
            user_id=1,
            goal="触发可见回复超时",
            tool_results=[],
            manage_job=False,
        )

    assert provenance[0] == {
        "response_provider_called": False,
        "response_provider_fallback_reason": None,
    }
    assert provenance[-1] == {
        "response_provider_called": False,
        "response_provider_fallback_reason": "TimeoutError",
    }
    retry_pending = next(item for item in events if item.get("event_type") == "visible_response_retry_pending")
    assert retry_pending["data"]["response_provider_called"] is False
    assert retry_pending["data"]["response_provider_fallback_reason"] == "TimeoutError"
    assert retry_pending["data"]["phase"] == "assistant_response_retry"
    assert not any(item.get("event_type") == "run_failed" for item in events)
    release_cancel_event("response-timeout-run")
