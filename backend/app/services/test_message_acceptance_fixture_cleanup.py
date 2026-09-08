"""Fixture ownership regressions; HTTP and database operations are all stubbed."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from scripts import agent_tcp_message_pagination_acceptance as acceptance


@pytest.fixture
def fixture_env(monkeypatch):
    title = "TCP pagination acceptance fixture"
    old_id, new_id = "existing-same-title", "this-run-session"
    state = SimpleNamespace(
        sessions={old_id: title}, old_id=old_id, new_id=new_id,
        fail=None, create_payload={"id": new_id}, requests=[],
    )

    def forbid_database(*args, **kwargs):
        raise AssertionError("Real database access is forbidden in this regression")

    monkeypatch.setattr(acceptance, "AsyncSessionLocal", forbid_database)

    async def seed(session_id, user_id, count):
        assert (session_id, user_id, count) == (new_id, 7, 5)

    async def cleanup(session_id):
        assert session_id == new_id
        del state.sessions[session_id]

    state.seed = AsyncMock(side_effect=seed)
    state.cleanup = AsyncMock(side_effect=cleanup)
    monkeypatch.setattr(acceptance, "_seed_messages", state.seed)
    monkeypatch.setattr(acceptance, "_delete_fixture", state.cleanup)

    def handle(request):
        path = request.url.path
        state.requests.append(request)
        phase = (
            "login" if path == "/api/auth/login" else
            "profile" if path == "/api/novels/current-user" else
            "create" if request.method == "POST" else
            "page2" if request.url.params.get("before_sequence") == "4" else
            "page" if path.endswith("/messages") else "detail"
        )
        if state.fail == phase:
            return httpx.Response(503, json={"detail": "injected HTTP failure"})
        if phase == "login":
            return httpx.Response(200, json={"access_token": "stub-token"})
        assert request.headers["Authorization"] == "Bearer stub-token"
        if phase == "profile":
            return httpx.Response(200, json={"id": 7})
        if phase == "create":
            assert json.loads(request.content)["title"] == title
            if state.create_payload.get("id") == new_id:
                state.sessions[new_id] = title
            return httpx.Response(201, json=state.create_payload)
        assert new_id in path
        if phase == "detail":
            assert dict(request.url.params) == {"include_messages": "false", "include_runs": "false"}
            return httpx.Response(200, json={"messages": [], "runs": []})
        assert request.url.params["limit"] == "2"
        cursor = request.url.params.get("before_sequence")
        sequences, next_cursor = {None: ([4, 5], 4), "4": ([2, 3], 2), "2": ([1], None)}[cursor]
        if state.fail == "sequence":
            sequences = [99]
        return httpx.Response(200, json={
            "items": [{"sequence": value} for value in sequences],
            "has_more": next_cursor is not None, "next_cursor": next_cursor,
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        acceptance.httpx, "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(acceptance.sys, "argv", [
        "acceptance", "--username", "stub-user", "--password", "stub-password",
        "--count", "5", "--limit", "2",
    ])
    return state


async def invoke():
    return await acceptance.run("http://stub.invalid", "stub-user", "stub-password", 5, 2)


def assert_owned_cleanup(state):
    state.cleanup.assert_awaited_once_with(state.new_id)
    assert state.sessions == {state.old_id: "TCP pagination acceptance fixture"}


async def test_run_success_keeps_count_and_pagination_contract(fixture_env):
    result = await invoke()
    assert result == {
        "status": "TCP_MESSAGE_PAGINATION_PASSED", "base_url": "http://stub.invalid",
        "session_id": fixture_env.new_id, "user_id": 7, "message_count": 5,
        "page_limit": 2, "pages": 3, "first_sequence": 1, "last_sequence": 5,
        "duplicate_count": 0,
    }
    fixture_env.seed.assert_awaited_once_with(fixture_env.new_id, 7, 5)
    assert_owned_cleanup(fixture_env)


@pytest.mark.parametrize("phase", ["detail", "page", "page2", "sequence"])
async def test_mid_run_failure_cleans_only_own_id_and_propagates(fixture_env, phase):
    fixture_env.fail = phase
    with pytest.raises(acceptance.AcceptanceFailure):
        await invoke()
    assert_owned_cleanup(fixture_env)


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_seed_failure_and_cancellation_preserve_original_exception(fixture_env, error_type):
    error = error_type("seed interrupted")
    fixture_env.seed.side_effect = error
    with pytest.raises(error_type) as caught:
        await invoke()
    assert caught.value is error
    assert_owned_cleanup(fixture_env)


@pytest.mark.parametrize("phase", ["login", "profile", "create"])
async def test_failure_before_created_id_never_deletes_existing_session(fixture_env, phase):
    fixture_env.fail = phase
    with pytest.raises(acceptance.AcceptanceFailure):
        await invoke()
    fixture_env.cleanup.assert_not_awaited()
    fixture_env.seed.assert_not_awaited()
    assert set(fixture_env.sessions) == {fixture_env.old_id}


@pytest.mark.parametrize("payload", [{}, {"id": None}, {"id": ""}, {"id": " "}, {"id": 7}])
async def test_invalid_create_id_never_selects_a_cleanup_target(fixture_env, payload):
    fixture_env.create_payload = payload
    with pytest.raises(acceptance.AcceptanceFailure, match="missing valid session id"):
        await invoke()
    fixture_env.cleanup.assert_not_awaited()
    fixture_env.seed.assert_not_awaited()
    assert set(fixture_env.sessions) == {fixture_env.old_id}


async def test_cleanup_failure_after_success_is_propagated(fixture_env):
    error = RuntimeError("cleanup unavailable")
    fixture_env.cleanup.side_effect = error
    with pytest.raises(RuntimeError) as caught:
        await invoke()
    assert caught.value is error
    fixture_env.cleanup.assert_awaited_once_with(fixture_env.new_id)
    assert fixture_env.old_id in fixture_env.sessions


async def test_cleanup_failure_preserves_primary_error_with_diagnostic(fixture_env):
    error = RuntimeError("seed failed")
    fixture_env.seed.side_effect = error
    fixture_env.cleanup.side_effect = RuntimeError("cleanup unavailable")
    with pytest.raises(RuntimeError) as caught:
        await invoke()
    assert caught.value is error
    assert any("cleanup unavailable" in note and fixture_env.new_id in note for note in error.__notes__)
    fixture_env.cleanup.assert_awaited_once_with(fixture_env.new_id)
    assert fixture_env.old_id in fixture_env.sessions


async def test_main_success_does_not_repeat_cleanup(fixture_env, capsys):
    assert await acceptance.main() == 0
    assert json.loads(capsys.readouterr().out)["message_count"] == 5
    assert_owned_cleanup(fixture_env)


@pytest.mark.parametrize("phase", ["login", "create", "page2"])
async def test_main_failure_never_uses_title_fallback(fixture_env, capsys, phase):
    fixture_env.fail = phase
    assert await acceptance.main() == 1
    output = capsys.readouterr()
    assert not output.out
    assert json.loads(output.err)["status"] == "TCP_MESSAGE_PAGINATION_FAILED"
    if phase == "page2":
        assert_owned_cleanup(fixture_env)
    else:
        fixture_env.cleanup.assert_not_awaited()
        assert set(fixture_env.sessions) == {fixture_env.old_id}


@pytest.mark.parametrize("primary_failure", [False, True])
async def test_main_reports_cleanup_failure_without_retry(fixture_env, capsys, primary_failure):
    if primary_failure:
        fixture_env.seed.side_effect = RuntimeError("seed failed")
    fixture_env.cleanup.side_effect = RuntimeError("cleanup unavailable")
    assert await acceptance.main() == 1
    output = capsys.readouterr()
    assert not output.out
    payload = json.loads(output.err)
    assert payload["status"] == "TCP_MESSAGE_PAGINATION_FAILED"
    if primary_failure:
        assert payload["error"] == "seed failed"
        assert "cleanup unavailable" in payload["notes"][0]
    else:
        assert payload["error"] == "cleanup unavailable"
    fixture_env.cleanup.assert_awaited_once_with(fixture_env.new_id)
    assert fixture_env.old_id in fixture_env.sessions
