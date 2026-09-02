from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.registry import DEFAULT_TOOL_REGISTRY, RunBoundToolRegistry
from app.agent.runner import _AGENT_CANCEL_EVENTS, _agent_run_lease_seconds, _claim_visible_response_run, _lease_heartbeat_interval, _visible_response_max_tokens, cancel_visible_response, get_cancel_event, release_cancel_event
from app.agent.runner import _recover_pending_read_steps


def test_cancel_token_is_shared_and_released():
    run_id = "cancel-token-test"
    _AGENT_CANCEL_EVENTS.pop(run_id, None)
    first = get_cancel_event(run_id)
    second = get_cancel_event(run_id)
    assert first is second
    assert not first.is_set()
    assert cancel_visible_response(run_id) is True
    assert first.is_set()
    release_cancel_event(run_id)
    assert run_id not in _AGENT_CANCEL_EVENTS


def test_cancel_token_is_not_created_until_requested():
    run_id = "cancel-token-lifecycle"
    _AGENT_CANCEL_EVENTS.pop(run_id, None)
    assert run_id not in _AGENT_CANCEL_EVENTS
    assert cancel_visible_response(run_id) is False
    assert run_id not in _AGENT_CANCEL_EVENTS


@pytest.mark.asyncio
async def test_recovery_reuses_completed_step_and_executes_only_pending_read(monkeypatch):
    completed = SimpleNamespace(id="step-1", status="completed", output_json={"cached": True})
    pending = SimpleNamespace(id="step-2", status="pending", output_json={})
    calls: list[str] = []

    class FakeRuntime:
        session = object()

        async def ensure_step(self, **kwargs):
            return completed if kwargs["step_order"] == 1 else pending

        async def claim_step(self, **kwargs):
            pending.status = "running"
            return pending

        async def complete_step(self, **kwargs):
            pending.status = "completed"
            pending.output_json = kwargs["output"]
            return pending

        async def append_event(self, **kwargs):
            return None

    async def fake_execute(**kwargs):
        calls.append(kwargs["tool_name"])
        return {"fresh": True}

    monkeypatch.setattr("app.agent.runner.execute_read_tool", fake_execute)
    run = SimpleNamespace(id="run-recover", user_id=1, project_id="project-1")
    result = await _recover_pending_read_steps(
        runtime=FakeRuntime(),
        run=run,
        context={"arguments": {}},
        plan_steps=[
            {"order": 1, "tool_name": "project.context", "risk_level": "read"},
            {"order": 2, "tool_name": "chapter.inspect", "risk_level": "read"},
        ],
    )
    assert result == [{"tool_name": "project.context", "result": {"cached": True}}, {"tool_name": "chapter.inspect", "result": {"fresh": True}}]
    assert calls == ["chapter.inspect"]
    release_cancel_event(run.id)


@pytest.mark.asyncio
async def test_recovery_uses_run_bound_registry_for_pending_read(monkeypatch):
    pending = SimpleNamespace(id="step-bound", status="pending", output_json={})
    captured = {}

    class FakeRuntime:
        session = object()

        async def ensure_step(self, **kwargs):
            return pending

        async def claim_step(self, **kwargs):
            pending.status = "running"
            return pending

        async def complete_step(self, **kwargs):
            pending.status = "completed"
            return pending

        async def append_event(self, **kwargs):
            return None

    async def fake_execute(**kwargs):
        captured.update(kwargs)
        return {"bound": True}

    monkeypatch.setattr("app.agent.runner.execute_read_tool", fake_execute)
    tool_name = "project.context"
    context = {
        "arguments": {},
        "capability_resolution": {"tools": [{"name": tool_name}]},
        "catalog_release": {
            "tools": [{"name": tool_name, "handler_identity": DEFAULT_TOOL_REGISTRY.get_handler_identity(tool_name)}],
        },
    }
    run = SimpleNamespace(id="run-bound-recover", user_id=1, project_id="project-1")
    result = await _recover_pending_read_steps(
        runtime=FakeRuntime(),
        run=run,
        context=context,
        plan_steps=[{"order": 1, "tool_name": tool_name, "risk_level": "read"}],
    )

    assert result == [{"tool_name": tool_name, "result": {"bound": True}}]
    assert isinstance(captured["registry"], RunBoundToolRegistry)
    release_cancel_event(run.id)


@pytest.mark.asyncio
async def test_recovery_does_not_bypass_unfinished_write_step():
    class FakeRuntime:
        session = object()

        async def ensure_step(self, **kwargs):
            return SimpleNamespace(id="step-write", status="awaiting_approval", output_json={})

        async def append_event(self, **kwargs):
            return None

    run = SimpleNamespace(id="run-write-recover", user_id=1, project_id="project-1")
    result = await _recover_pending_read_steps(
        runtime=FakeRuntime(),
        run=run,
        context={"arguments": {}},
        plan_steps=[{"order": 1, "tool_name": "chapter.generate", "risk_level": "write"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_visible_response_claim_retries_transient_recovery_lease_conflict():
    from app.services.agent_runtime import AgentConflict

    class Runtime:
        def __init__(self):
            self.calls = 0

        async def claim_run(self, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise AgentConflict("run lease is held by another worker or run is terminal")
            return SimpleNamespace(id=kwargs["run_id"], lease_generation=2)

    runtime = Runtime()
    claimed = await _claim_visible_response_run(
        runtime,
        run_id="reclaim-run",
        user_id=1,
        lease_owner="replacement-worker",
        lease_seconds=3,
        recovery_wait_seconds=1.0,
    )
    assert claimed.id == "reclaim-run"
    assert runtime.calls == 3




@pytest.mark.asyncio
async def test_wait_until_runnable_allows_recovery_ready_pause():
    from app.agent.runner import _wait_until_runnable

    class RecoveryReadyRuntime:
        async def get_run(self, run_id, user_id):
            return SimpleNamespace(status="paused", current_phase="recovery_ready", cancel_requested_at=None)

    assert await _wait_until_runnable(RecoveryReadyRuntime(), "recovery-ready-run", 1) is True




def test_agent_run_lease_seconds_is_bounded(monkeypatch):
    monkeypatch.delenv('AGENT_RUN_LEASE_SECONDS', raising=False)
    assert _agent_run_lease_seconds() == 120
    monkeypatch.setenv('AGENT_RUN_LEASE_SECONDS', '3')
    assert _agent_run_lease_seconds() == 3
    monkeypatch.setenv('AGENT_RUN_LEASE_SECONDS', '0')
    assert _agent_run_lease_seconds() == 1
    monkeypatch.setenv('AGENT_RUN_LEASE_SECONDS', '999999')
    assert _agent_run_lease_seconds() == 3600
    monkeypatch.setenv('AGENT_RUN_LEASE_SECONDS', 'invalid')
    assert _agent_run_lease_seconds() == 120


def test_agent_lease_heartbeat_interval_tracks_short_and_long_leases():
    assert _lease_heartbeat_interval(1) == pytest.approx(1 / 3)
    assert _lease_heartbeat_interval(3) == pytest.approx(1.0)
    assert _lease_heartbeat_interval(120) == pytest.approx(30.0)
    assert _lease_heartbeat_interval(3600) == pytest.approx(30.0)




def test_visible_response_token_budget_is_bounded(monkeypatch):
    monkeypatch.delenv('AGENT_VISIBLE_RESPONSE_MAX_TOKENS', raising=False)
    assert _visible_response_max_tokens() == 1200
    monkeypatch.setenv('AGENT_VISIBLE_RESPONSE_MAX_TOKENS', '96')
    assert _visible_response_max_tokens() == 96
    monkeypatch.setenv('AGENT_VISIBLE_RESPONSE_MAX_TOKENS', '3')
    assert _visible_response_max_tokens() == 64
    monkeypatch.setenv('AGENT_VISIBLE_RESPONSE_MAX_TOKENS', '999999')
    assert _visible_response_max_tokens() == 1200
    monkeypatch.setenv('AGENT_VISIBLE_RESPONSE_MAX_TOKENS', 'invalid')
    assert _visible_response_max_tokens() == 1200


@pytest.mark.asyncio
async def test_wait_until_runnable_stops_for_durable_cancel():
    from app.agent.runner import _wait_until_runnable

    run_id = "durable-cancel-fresh-worker"
    _AGENT_CANCEL_EVENTS.pop(run_id, None)

    class FreshWorkerRuntime:
        async def get_run(self, run_id, user_id):
            return SimpleNamespace(status="running", cancel_requested_at="2026-08-24T10:00:00+08:00")

    assert run_id not in _AGENT_CANCEL_EVENTS
    assert await _wait_until_runnable(FreshWorkerRuntime(), run_id, 1) is False
    assert run_id not in _AGENT_CANCEL_EVENTS
