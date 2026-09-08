"""Regression coverage for the standalone OpenAPI smoke authentication setup."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_smoke_routes_module() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "tools" / "smoke_api_routes.py"
    spec = importlib.util.spec_from_file_location("xq_smoke_api_routes_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_openapi_smoke_anonymous_auth_has_defined_mode_and_clears_stale_headers(monkeypatch):
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_TOKEN", raising=False)
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_USERNAME", raising=False)
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_PASSWORD", raising=False)
    smoke = _load_smoke_routes_module()
    smoke.AUTH_HEADERS = {"Authorization": "Bearer stale-token"}
    smoke.AUTH_MODE = "bearer-token"

    ok, mode = smoke.configure_auth()

    assert ok is True
    assert mode == "anonymous"
    assert smoke.AUTH_MODE == "anonymous"
    assert smoke.AUTH_HEADERS == {}


def test_resource_identity_families_are_stable_and_actionable():
    smoke = _load_smoke_routes_module()
    assert smoke.resource_identity_families("/api/projects/{project_id}/tasks/{task_id}") == ("project_id", "task_id")
    assert smoke.resource_identity_families("/api/chapters/{chapter_id}/versions/{v1}/vs/{v2}") == ("chapter_id", "v1", "v2")
    assert smoke.resource_identity_families("/api/health") == ()
    assert smoke.has_unresolved_resource_identity("/api/projects/{project_id}/overview") is False
    assert smoke.has_unresolved_resource_identity("/api/projects/{project_id}/runs/{run_id}") is True
    assert smoke.has_unresolved_resource_identity("/api/projects/{project_id}/clues/{clue_id}") is True
    clue_context = smoke.SmokeResourceContext(project_id="fixture-project", chapter_number=7, clue_id=9)
    assert smoke.has_unresolved_resource_identity("/api/projects/{project_id}/clues/{clue_id}", clue_context) is False
    context = smoke.SmokeResourceContext(project_id="fixture-project", chapter_number=7)
    assert smoke.substitute_path_params("/api/projects/{project_id}/chapters/{chapter_number}", context) == "/api/projects/fixture-project/chapters/7"
    assert ("GET", "/api/writer/novels/{project_id}/chapters/{chapter_number}/stream") in smoke.SKIPPED_STREAMING_ROUTES
    assert ("POST", "/api/updates/stream/create") in smoke.SKIPPED_MUTATING_ROUTES
    assert ("POST", "/api/agent/sessions") in smoke.SKIPPED_MUTATING_ROUTES
    session_context = smoke.SmokeResourceContext(project_id="fixture-project", chapter_number=1, session_id="session-1", run_id="run-1")
    assert smoke.has_unresolved_resource_identity("/api/agent/sessions/{session_id}", session_context) is False
    assert smoke.has_unresolved_resource_identity("/api/agent/sessions/{session_id}/runs/{run_id}/events", session_context) is False
    assert smoke.substitute_path_params("/api/agent/sessions/{session_id}/runs/{run_id}/events", session_context) == "/api/agent/sessions/session-1/runs/run-1/events"

def test_capture_generation_task_id_binds_nested_runtime_id():
    smoke = _load_smoke_routes_module()
    context = smoke.SmokeResourceContext(project_id="fixture-project", chapter_number=1)
    smoke.capture_generation_task_id(context, '{"generation_runtime":{"run_id":"task-123"}}')
    assert context.task_id == "task-123"
    assert smoke.substitute_path_params("/api/task-runtime/tasks/{task_id}", context) == "/api/task-runtime/tasks/task-123"


def test_artifact_context_binds_only_returned_identity():
    smoke = _load_smoke_routes_module()
    context = smoke.SmokeResourceContext(project_id="fixture-project", chapter_number=1, artifact_id="candidate-1")
    path = "/api/agent/artifacts/{artifact_id}/content"
    assert smoke.has_unresolved_resource_identity(path, context) is False
    assert smoke.substitute_path_params(path, context) == "/api/agent/artifacts/candidate-1/content"


def test_existing_llm_config_is_never_overwritten(monkeypatch):
    smoke = _load_smoke_routes_module()
    monkeypatch.setenv(smoke.ARTIFACT_FIXTURE_ENV, "1")
    monkeypatch.setattr(smoke, "BASE_URL", "http://127.0.0.1:8013")
    monkeypatch.setattr(smoke, "AUTH_HEADERS", {"Authorization": "Bearer fixture"})
    calls = []
    def request(method, url, **kwargs):
        calls.append(method)
        return 200, {"llm_provider_api_key_configured": True}, "masked"
    monkeypatch.setattr(smoke, "request_json", request)
    server, restore, reason = smoke.enable_artifact_fixture_provider()
    assert server is None and restore is None
    assert "no-saved-llm-config" in reason
    assert calls == ["GET"]


def test_fixture_config_is_removed_only_if_still_owned(monkeypatch):
    smoke = _load_smoke_routes_module()
    monkeypatch.setenv(smoke.ARTIFACT_FIXTURE_ENV, "1")
    monkeypatch.setattr(smoke, "BASE_URL", "http://127.0.0.1:8013")
    monkeypatch.setattr(smoke, "AUTH_HEADERS", {"Authorization": "Bearer fixture"})
    state, calls = {}, []
    def request_json(method, url, *, json_body=None):
        calls.append(method)
        if method == "GET":
            return (200, dict(state), "") if state else (404, None, "")
        state.update(json_body)
        return 200, {}, ""
    def request(method, url, **kwargs):
        calls.append(method)
        assert method == "DELETE"
        state.clear()
        return 204, ""
    monkeypatch.setattr(smoke, "request_json", request_json)
    monkeypatch.setattr(smoke, "request", request)
    server, restore, detail = smoke.enable_artifact_fixture_provider()
    try:
        assert detail == "enabled" and server is not None and restore is not None
        saved = dict(state)
        state["llm_provider_model"] = "concurrent-user-change"
        assert restore() == (False, "llm-config-changed-during-fixture-preserved")
        assert "DELETE" not in calls
        state.update(saved)
        assert restore() == (True, "")
        assert calls[-2:] == ["DELETE", "GET"]
    finally:
        smoke._shutdown_artifact_fixture_provider(server)


def test_artifact_accept_http_500_is_not_classified_as_a_skip(monkeypatch):
    smoke = _load_smoke_routes_module()
    context = smoke.SmokeResourceContext(project_id="fixture-project", chapter_number=1, artifact_id="candidate-1")

    def fake_request(method, url, *, json_body=None, max_chars=300):
        assert method == "POST"
        assert url.endswith("/api/agent/artifacts/candidate-1/accept")
        return 500, '{"detail":"accept failed"}'

    monkeypatch.setattr(smoke, "request", fake_request)
    status, detail = smoke.smoke_artifact_accept_route(context)
    assert status == 500
    assert detail == '{"detail":"accept failed"}'
    assert status not in smoke.ALLOWED_STATUSES or status >= 500


def test_fixture_failure_makes_main_nonzero_and_runs_all_finalizers(monkeypatch):
    import io
    import json
    smoke = _load_smoke_routes_module()
    monkeypatch.setenv(smoke.ARTIFACT_FIXTURE_ENV, "1")
    monkeypatch.setattr(smoke, "configure_auth", lambda: (True, "fixture"))
    spec = {"paths": {"/api/agent/artifacts/{artifact_id}/accept": {"post": {}}}}
    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(spec).encode()))
    actions = []
    server = object()
    def restore():
        actions.append("config")
        return True, ""
    monkeypatch.setattr(smoke, "enable_artifact_fixture_provider", lambda: (server, restore, "enabled"))
    context = smoke.SmokeResourceContext(project_id="temporary-project", chapter_number=1, artifact_id="candidate")
    monkeypatch.setattr(smoke, "create_smoke_project", lambda **kw: (context, "accept-status=500"))
    def cleanup(*args):
        actions.append("project")
        raise OSError("cleanup failed")
    monkeypatch.setattr(smoke, "cleanup_smoke_project", cleanup)
    monkeypatch.setattr(smoke, "_shutdown_artifact_fixture_provider", lambda s: actions.append("server"))
    assert smoke.main() == 1
    assert actions == ["project", "config", "server"]


def test_fixture_setup_exception_closes_provider(monkeypatch):
    import io
    import json
    smoke = _load_smoke_routes_module()
    monkeypatch.setenv(smoke.ARTIFACT_FIXTURE_ENV, "1")
    monkeypatch.setattr(smoke, "configure_auth", lambda: (True, "fixture"))
    spec = {"paths": {"/api/agent/artifacts/{artifact_id}/accept": {"post": {}}}}
    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(spec).encode()))
    actions = []
    def restore():
        actions.append("config")
        return True, ""
    monkeypatch.setattr(smoke, "enable_artifact_fixture_provider", lambda: (object(), restore, "enabled"))
    def setup(**kw):
        raise RuntimeError("setup interrupted")
    monkeypatch.setattr(smoke, "create_smoke_project", setup)
    monkeypatch.setattr(smoke, "_shutdown_artifact_fixture_provider", lambda s: actions.append("server"))
    assert smoke.main() == 1
    assert actions == ["config", "server"]


@pytest.mark.parametrize("response_status", [400, 401, 403, 404, 409, 422, 500, 503])
def test_main_rejects_every_unsuccessful_artifact_accept(response_status, monkeypatch, capsys):
    import io
    import json
    smoke = _load_smoke_routes_module()
    monkeypatch.setenv(smoke.ARTIFACT_FIXTURE_ENV, "1")
    monkeypatch.setattr(smoke, "configure_auth", lambda: (True, "fixture"))
    spec = {"paths": {"/api/agent/artifacts/{artifact_id}/accept": {"post": {}}}}
    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(spec).encode()))
    monkeypatch.setattr(smoke, "enable_artifact_fixture_provider", lambda: (object(), lambda: (True, ""), "enabled"))
    context = smoke.SmokeResourceContext(project_id="temporary", chapter_number=1, artifact_id="real-candidate")
    monkeypatch.setattr(smoke, "create_smoke_project", lambda **kw: (context, ""))
    monkeypatch.setattr(smoke, "request", lambda *a, **kw: (response_status, "accept failure"))
    monkeypatch.setattr(smoke, "cleanup_smoke_project", lambda *a: (True, ""))
    monkeypatch.setattr(smoke, "_shutdown_artifact_fixture_provider", lambda s: None)
    assert smoke.main() == 1
    assert "accept failure" in capsys.readouterr().out
