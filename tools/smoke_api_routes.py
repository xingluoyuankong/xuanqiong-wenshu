from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlsplit
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_BACKEND_PORT = os.getenv("XUANQIONG_WENSHU_BACKEND_PORT", "8013")
BASE_URL = (
    os.getenv("XUANQIONG_WENSHU_BACKEND_BASE_URL")
    or f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}"
).rstrip("/")
OPENAPI_URL = f"{BASE_URL}/openapi.json"
ARTIFACT_STORAGE_ROOT = (Path(__file__).resolve().parents[1] / "backend" / "output" / "agent-artifacts").resolve()
ARTIFACT_FIXTURE_ENV = "XUANQIONG_WENSHU_SMOKE_ARTIFACT_FIXTURE"
ARTIFACT_FIXTURE_KEY = "xq-smoke-artifact-fixture-key"
ARTIFACT_FIXTURE_MODEL = "xq-smoke-artifact-fixture-model"
ARTIFACT_FIXTURE_CONTENT = (
    "夜雨落在青石巷，沈砚收起纸伞，沿着河堤追上那盏忽明忽暗的纸灯。\n\n"
    "纸灯停在旧戏台前，台下没有观众，台上却传来三声木鱼。沈砚推开半掩的幕布，"
    "看见一枚刻着玄穹印记的铜牌，随后把铜牌收入袖中。\n\n"
    "远处城门缓缓开启，守夜人举灯示意他立即离开。沈砚回望戏台，确认铜牌上的裂纹正在发光，"
    "便沿着石阶走向城门，并把今晚的发现记入随身札记。"
)
HTTP_METHODS = ("get", "post", "put", "patch", "delete")
ALLOWED_STATUSES = {200, 201, 202, 204, 400, 401, 403, 404, 405, 409, 410, 415, 422, 429, 503}
AUTH_HEADERS: dict[str, str] = {}
AUTH_MODE = "anonymous"
PATH_PARAM_PATTERN = re.compile(r"\{([^}]+)\}")
SKIPPED_MUTATING_ROUTES = {
    ("POST", "/api/llm-config/auto-switch"),
    ("PUT", "/api/llm-config"),
    ("DELETE", "/api/llm-config"),
    ("POST", "/api/projects/{project_id}/chapters/{chapter_number}/patch/apply"),
    ("POST", "/api/projects/{project_id}/chapters/{chapter_number}/patch/revert"),
    ("POST", "/api/optimizer/apply-optimization"),
    ("POST", "/api/updates/stream/create"),
    ("POST", "/api/agent/sessions"),
    ("POST", "/api/agent/sessions/{session_id}/messages"),
}
SKIPPED_STREAMING_ROUTES = {
    ("GET", "/api/writer/novels/{project_id}/chapters/{chapter_number}/stream"),
    ("GET", "/api/updates/stream/{task_id}"),
    ("GET", "/api/task-runtime/tasks/{task_id}/stream"),
    ("GET", "/api/agent/sessions/{session_id}/runs/{run_id}/stream"),
}
SKIPPED_EXPENSIVE_ROUTES = {
    ("GET", "/api/llm-config/health-check"),
    ("POST", "/api/optimizer/optimize"),
}


@dataclass
class CheckResult:
    method: str
    path: str
    status: int
    ok: bool
    detail: str


SKIP_REASON_LABELS = {
    "skipped-mutating-route": "跳过：该接口会产生真实写入/变更，冒烟检查默认不执行。",
    "skipped-expensive-route": "跳过：该接口调用开销较高，冒烟检查默认不执行。",
    "skipped-streaming-route": "跳过：该接口是长连接流式接口，使用独立 SSE 验收，不用普通短请求读取。",
    "skipped-resource-identity-route": "跳过：该接口依赖真实资源 ID，当前冒烟检查未提供可用资源，因此不再伪造占位 ID 请求。",
    "skipped-live-resource-prerequisite": "跳过：最小真实资源前置条件未满足，暂不继续后续写作台动作。",
    "live-resource-smoke": "使用最小真实资源执行写作台关键路由冒烟。",
}


@dataclass
class SmokeResourceContext:
    project_id: str
    chapter_number: int
    clue_id: int | None = None
    task_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    artifact_id: str | None = None
    accepted_artifact_id: str | None = None
    accepted_version_id: int | None = None
    artifact_storage_keys: list[str] | None = None
    generated: bool = False


def has_resource_identity_param(path: str) -> bool:
    params = [match.group(1).lower() for match in PATH_PARAM_PATTERN.finditer(path)]
    if not params:
        return False
    for name in params:
        if "chapter" in name and "number" in name:
            continue
        if name.endswith("_id") or name == "id":
            return True
    return False


def resource_identity_families(path: str) -> tuple[str, ...]:
    """Return stable placeholder families for actionable skip aggregation."""
    params = [match.group(1).lower() for match in PATH_PARAM_PATTERN.finditer(path)]
    families = [name for name in params if name.endswith("_id") or name in {"id", "v1", "v2"}]
    return tuple(dict.fromkeys(families))


def has_unresolved_resource_identity(path: str, context: SmokeResourceContext | None = None) -> bool:
    """Return whether a route needs an ID absent from the current smoke fixture."""
    available = {"project_id"}
    if context is not None and context.clue_id is not None:
        available.add("clue_id")
    if context is not None and context.task_id:
        available.add("task_id")
    if context is not None and context.session_id:
        available.add("session_id")
    if context is not None and context.run_id:
        available.add("run_id")
    if context is not None and context.artifact_id:
        available.add("artifact_id")
    if context is not None and context.accepted_artifact_id:
        available.add("accepted_artifact_id")
    for name in (match.group(1).lower() for match in PATH_PARAM_PATTERN.finditer(path)):
        if "chapter" in name and "number" in name:
            continue
        if name.endswith("_id") or name == "id":
            if name not in available:
                return True
    return False


def substitute_path_params(path: str, context: SmokeResourceContext | None = None) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if name == "project_id" and context is not None:
            return context.project_id
        if name == "clue_id" and context is not None and context.clue_id is not None:
            return str(context.clue_id)
        if name == "task_id" and context is not None and context.task_id:
            return context.task_id
        if name == "session_id" and context is not None and context.session_id:
            return context.session_id
        if name == "run_id" and context is not None and context.run_id:
            return context.run_id
        if name == "artifact_id" and context is not None and context.artifact_id:
            return context.artifact_id
        if name == "accepted_artifact_id" and context is not None and context.accepted_artifact_id:
            return context.accepted_artifact_id
        if "chapter" in name and "number" in name:
            return str(context.chapter_number if context is not None else 1)
        return "test"

    return PATH_PARAM_PATTERN.sub(repl, path)


def request(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    max_chars: int = 300,
) -> tuple[int, str]:
    headers = {
        "Accept": "application/json",
        "X-Smoke-Test": "openapi-route-smoke",
        **AUTH_HEADERS,
    }
    data = None
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        payload = json.dumps(json_body if json_body is not None else {}, ensure_ascii=False).encode("utf-8")
        data = payload
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.status, body[:max_chars] if max_chars > 0 else body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        return exc.code, body[:max_chars] if max_chars > 0 else body
    except Exception as exc:
        return 599, repr(exc)


def request_json(method: str, url: str, *, json_body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | None, str]:
    status, detail = request(method, url, json_body=json_body, max_chars=0)
    if not detail:
        return status, None, ""
    try:
        return status, json.loads(detail), detail
    except Exception:
        return status, None, detail


def configure_auth() -> tuple[bool, str]:
    """Load a smoke Bearer token, or mint one from environment credentials.

    Anonymous mode remains the default so the base smoke still exercises public
    and authentication-contract responses. Credentials are read only from the
    environment and never printed.
    """
    global AUTH_HEADERS, AUTH_MODE
    AUTH_HEADERS = {}
    AUTH_MODE = "anonymous"
    token = os.getenv("XUANQIONG_WENSHU_SMOKE_TOKEN", "").strip()
    username = os.getenv("XUANQIONG_WENSHU_SMOKE_USERNAME", "").strip()
    password = os.getenv("XUANQIONG_WENSHU_SMOKE_PASSWORD", "")
    if token:
        AUTH_HEADERS = {"Authorization": f"Bearer {token}"}
        AUTH_MODE = "bearer-token"
        return True, AUTH_MODE
    if not username and not password:
        return True, AUTH_MODE
    if not username or not password:
        return False, "credentials-incomplete"
    body = urlencode({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data=body,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        return False, f"login-failed: {exc}"
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        return False, "login-failed: missing access_token"
    AUTH_HEADERS = {"Authorization": f"Bearer {access_token}"}
    AUTH_MODE = "credentials"
    return True, AUTH_MODE


class _ArtifactFixtureProviderHandler(BaseHTTPRequestHandler):
    """Tiny local OpenAI-compatible provider used only by the opt-in HTTP fixture."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path.rstrip("/") != "/v1/models":
            self.send_error(404)
            return
        body = json.dumps(
            {"object": "list", "data": [{"id": ARTIFACT_FIXTURE_MODEL, "object": "model"}]},
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self.send_error(404)
            return
        content_length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(content_length)
        if not self.headers.get("Authorization", "").endswith(ARTIFACT_FIXTURE_KEY):
            self.send_error(401)
            return
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.send_error(415)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        content = ARTIFACT_FIXTURE_CONTENT
        chunks = (content[: len(content) // 3], content[len(content) // 3 : 2 * len(content) // 3], content[2 * len(content) // 3 :])
        for index, part in enumerate(chunks):
            event = json.dumps(
                {
                    "id": f"xq-smoke-artifact-{index}",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}],
                },
                ensure_ascii=False,
            )
            self.wfile.write(f"data: {event}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _start_artifact_fixture_provider() -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ArtifactFixtureProviderHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="xq-artifact-fixture-provider", daemon=True)
    thread.start()
    return server, thread


def _snapshot_llm_config() -> tuple[int, dict[str, Any] | None, str]:
    return request_json("GET", f"{BASE_URL}/api/llm-config")


def enable_artifact_fixture_provider() -> tuple[ThreadingHTTPServer | None, Callable[[], tuple[bool, str]] | None, str]:
    """Use a disposable account only; masked GET responses cannot restore secrets."""
    if os.getenv(ARTIFACT_FIXTURE_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None, None, "disabled"
    if not AUTH_HEADERS.get("Authorization"):
        return None, None, "artifact-fixture-requires-explicit-test-account-authentication"
    if urlsplit(BASE_URL).hostname not in {"localhost", "127.0.0.1", "::1"}:
        return None, None, "artifact-fixture-requires-loopback-backend"
    status, snapshot, _ = _snapshot_llm_config()
    if status != 404:
        return None, None, "artifact-fixture-requires-account-with-no-saved-llm-config"
    server, _thread = _start_artifact_fixture_provider()
    fixture_url = f"http://127.0.0.1:{int(server.server_address[1])}/v1"

    def restore() -> tuple[bool, str]:
        current_status, current, _ = _snapshot_llm_config()
        if current_status == 404:
            return True, ""
        if current_status != 200 or not isinstance(current, dict):
            return False, "llm-config-cleanup-read-failed"
        if (current.get("llm_provider_url") != fixture_url
                or current.get("llm_provider_model") != ARTIFACT_FIXTURE_MODEL):
            return False, "llm-config-changed-during-fixture-preserved"
        delete_status, _ = request("DELETE", f"{BASE_URL}/api/llm-config")
        if delete_status not in {204, 404}:
            return False, f"llm-config-cleanup-status={delete_status}"
        final_status, _, _ = _snapshot_llm_config()
        return (True, "") if final_status == 404 else (False, "llm-config-cleanup-not-confirmed")

    try:
        put_status, _, _ = request_json(
            "PUT", f"{BASE_URL}/api/llm-config",
            json_body={"llm_provider_url": fixture_url,
                       "llm_provider_api_key": ARTIFACT_FIXTURE_KEY,
                       "llm_provider_model": ARTIFACT_FIXTURE_MODEL},
        )
        if put_status not in {200, 201}:
            cleaned, cleanup_detail = restore()
            _shutdown_artifact_fixture_provider(server)
            return None, None, f"llm-config-fixture-status={put_status}; cleanup={cleaned}: {cleanup_detail}"
    except Exception:
        try:
            restore()
        finally:
            _shutdown_artifact_fixture_provider(server)
        raise
    return server, restore, "enabled"


def _shutdown_artifact_fixture_provider(server: ThreadingHTTPServer | None) -> None:
    if server is None:
        return
    server.shutdown()
    server.server_close()


def create_smoke_project(*, artifact_fixture: bool = False) -> tuple[SmokeResourceContext | None, str]:
    marker = uuid.uuid4().hex[:12]
    status, payload, detail = request_json(
        "POST",
        f"{BASE_URL}/api/novels",
        json_body={
            "title": f"OpenAPI Smoke {marker}",
            "initial_prompt": f"用于最小真实资源写作台路由冒烟校验。xq-smoke-fixture:{marker}",
        },
    )
    if status != 201 or not payload or not payload.get("id"):
        preview = detail[:300] if detail else ""
        return None, f"create-project-failed: status={status} detail={preview}"

    project_id = str(payload["id"])
    context = SmokeResourceContext(project_id=project_id, chapter_number=1, artifact_storage_keys=[])
    blueprint_status, _, blueprint_detail = request_json(
        "PATCH",
        f"{BASE_URL}/api/novels/{project_id}/blueprint",
        json_body={
            "full_synopsis": "冒烟校验用项目，仅用于验证写作台关键路由不会返回 500。",
            "chapter_outline": [
                {
                    "chapter_number": 1,
                    "title": "冒烟章节",
                    "summary": "用于写作台最小真实资源路由校验。",
                }
            ],
        },
    )
    if blueprint_status not in {200, 201, 204}:
        preview = blueprint_detail[:300] if blueprint_detail else ""
        return context, f"patch-blueprint-failed: status={blueprint_status} detail={preview}"

    clue_status, clue_payload, _ = request_json(
        "POST",
        f"{BASE_URL}/api/projects/{project_id}/clues",
        json_body={
            "name": "OpenAPI smoke clue",
            "clue_type": "plot_hook",
            "description": "Temporary clue used by resource-identity smoke coverage.",
            "importance": 3,
            "planted_chapter": 1,
            "clue_content": "smoke fixture",
            "hint_level": 1,
            "design_intent": "smoke coverage",
        },
    )
    clue_id = None
    if clue_status in {200, 201} and clue_payload and clue_payload.get("id") is not None:
        try:
            clue_id = int(clue_payload["id"])
        except (TypeError, ValueError):
            clue_id = None

    session_status, session_payload, _ = request_json(
        "POST",
        f"{BASE_URL}/api/agent/sessions",
        json_body={"project_id": project_id, "title": "OpenAPI smoke session"},
    )
    session_id = None
    run_id = None
    if session_status in {200, 201} and session_payload and session_payload.get("id"):
        session_id = str(session_payload["id"])
        message_body: dict[str, Any] = {"content": "只返回“收到”。", "tools": [], "arguments": {}}
        if artifact_fixture:
            message_body = {
                "content": "生成一个可回收的章节候选 Artifact。",
                "tools": ["chapter.generate"],
                "arguments": {
                    "chapter_number": 1,
                    "instruction": "生成一段有场景、动作和结果的章节候选。",
                    "target_word_count": 100,
                    "min_word_count": 1,
                },
            }
        message_status, message_payload, _ = request_json(
            "POST",
            f"{BASE_URL}/api/agent/sessions/{session_id}/messages",
            json_body=message_body,
        )
        if message_status in {200, 201} and message_payload:
            run = message_payload.get("run")
            if isinstance(run, dict) and run.get("id"):
                run_id = str(run["id"])

    context.clue_id, context.session_id, context.run_id = clue_id, session_id, run_id
    if artifact_fixture and not run_id:
        return context, "artifact-fixture-run-creation-failed"
    if artifact_fixture and run_id:
        approval_id = None
        for _ in range(30):
            approval_status, approval_payload, _ = request_json(
                "GET", f"{BASE_URL}/api/agent/runs/{run_id}/approvals"
            )
            if approval_status == 200 and isinstance(approval_payload, list):
                pending = next((item for item in approval_payload if isinstance(item, dict) and item.get("status") == "pending"), None)
                if pending and pending.get("id"):
                    approval_id = str(pending["id"])
                    break
            time.sleep(1)
        if not approval_id:
            return context, "artifact-fixture-approval-timeout"
        decision_status, _, decision_detail = request_json(
            "POST", f"{BASE_URL}/api/agent/approvals/{approval_id}/decision",
            json_body={"approved": True, "reason": "OpenAPI Artifact fixture"},
        )
        if decision_status not in {200, 201}:
            return context, f"artifact-fixture-approval-decision-failed: status={decision_status} detail={decision_detail[:300]}"
        execute_status, execute_payload, execute_detail = request_json(
            "POST", f"{BASE_URL}/api/agent/approvals/{approval_id}/execute"
        )
        if execute_status not in {200, 201} or not isinstance(execute_payload, dict) or not execute_payload.get("id"):
            return context, f"artifact-fixture-execute-failed: status={execute_status} detail={execute_detail[:500]}"
        context.artifact_id = str(execute_payload["id"])
        candidate_metadata = execute_payload.get("metadata_json") if isinstance(execute_payload.get("metadata_json"), dict) else {}
        if candidate_metadata.get("storage_key"):
            context.artifact_storage_keys.append(str(candidate_metadata["storage_key"]))
        accept_status, accept_payload, accept_detail = request_json(
            "POST", f"{BASE_URL}/api/agent/artifacts/{context.artifact_id}/accept",
            json_body={"note": "OpenAPI Artifact fixture acceptance"},
        )
        if accept_status not in {200, 201} or not isinstance(accept_payload, dict):
            return context, f"artifact-fixture-accept-failed: status={accept_status} detail={accept_detail[-1500:]}"
        accepted_meta = accept_payload.get("metadata_json") if isinstance(accept_payload.get("metadata_json"), dict) else {}
        if accepted_meta.get("storage_key"):
            context.artifact_storage_keys.append(str(accepted_meta["storage_key"]))
        if accepted_meta.get("accepted_artifact_ref_id"):
            context.accepted_artifact_id = str(accepted_meta["accepted_artifact_ref_id"])
        context.accepted_version_id = accepted_meta.get("accepted_version_id")
        if not context.accepted_artifact_id or not context.accepted_version_id or accepted_meta.get("status") != "accepted":
            return context, "artifact-fixture-acceptance-not-persisted"
    return context, ""


def capture_generation_task_id(context: SmokeResourceContext, detail: str) -> None:
    """Bind the chapter-generation TaskRuntime ID returned by the real API."""
    try:
        payload = json.loads(detail)
    except (TypeError, ValueError):
        return
    runtime = payload.get("generation_runtime") if isinstance(payload, dict) else None
    run_id = runtime.get("run_id") if isinstance(runtime, dict) else None
    if not run_id and isinstance(payload, dict):
        chapters = payload.get("chapters")
        if isinstance(chapters, list) and chapters and isinstance(chapters[0], dict):
            nested = chapters[0].get("generation_runtime")
            if isinstance(nested, dict):
                run_id = nested.get("run_id")
    if run_id:
        context.task_id = str(run_id)


def cleanup_smoke_project(project_id: str, context: SmokeResourceContext | None = None) -> tuple[bool, str]:
    status, detail = request("DELETE", f"{BASE_URL}/api/novels", json_body=[project_id])
    if status not in {200, 204, 404}:
        return False, f"cleanup project={project_id} status={status} detail={detail[:300]}"
    # Project deletion removes relational rows; remove only storage keys created
    # by this fixture, never scan or delete the shared artifact directory.
    if context and context.artifact_storage_keys:
        root = ARTIFACT_STORAGE_ROOT.resolve()
        for raw_key in context.artifact_storage_keys:
            key = str(raw_key or "").strip()
            if not key or Path(key).name != key:
                return False, "artifact-cleanup-invalid-storage-key"
            target = (root / key).resolve()
            if root in target.parents and target.is_file():
                target.unlink()
    return True, ""


def smoke_artifact_accept_route(context: SmokeResourceContext) -> tuple[int, str]:
    """Run the idempotent accept probe; server 5xx must remain a failure."""
    if not context.artifact_id:
        return 599, "artifact-fixture-did-not-yield-artifact"
    url = f"{BASE_URL}/api/agent/artifacts/{context.artifact_id}/accept"
    return request("POST", url, json_body={"note": "OpenAPI Artifact fixture idempotence check"})


def smoke_writer_route(
    method: str,
    path: str,
    context: SmokeResourceContext,
) -> tuple[int, str]:
    real_path = path.replace("{project_id}", context.project_id).replace("{chapter_number}", str(context.chapter_number))
    url = f"{BASE_URL}{real_path}"

    if method == "POST" and path == "/api/writer/novels/{project_id}/chapters/generate":
        status, detail = request(
            method,
            url,
            json_body={
                "chapter_number": context.chapter_number,
                "writing_notes": "最小真实资源冒烟检查",
                "quality_requirements": "仅验证接口可返回非 500。",
                "target_word_count": 800,
                "min_word_count": 500,
            },
            max_chars=0,
        )
        capture_generation_task_id(context, detail)
        # The generate route queues background work; a 2xx response does not
        # mean a selectable completed version exists yet. Keep evaluate/select
        # gated until a dedicated wait-for-terminal acceptance flow is used.
        return status, detail

    if method == "POST" and path == "/api/writer/novels/{project_id}/chapters/cancel":
        return request(method, url, json_body={"chapter_number": context.chapter_number, "reason": "OpenAPI smoke"})

    if method == "POST" and path == "/api/writer/novels/{project_id}/chapters/evaluate":
        if not context.generated:
            return 0, "skipped-live-resource-prerequisite"
        return request(method, url, json_body={"chapter_number": context.chapter_number, "version_index": 0})

    if method == "POST" and path == "/api/writer/novels/{project_id}/chapters/select":
        if not context.generated:
            return 0, "skipped-live-resource-prerequisite"
        return request(method, url, json_body={"chapter_number": context.chapter_number, "version_index": 0})

    return request(method, url)


def main() -> int:
    auth_ok, auth_detail = configure_auth()
    if not auth_ok:
        print(f"[失败] smoke 认证配置无效：{auth_detail}")
        return 1
    print(f"[正常] smoke 认证模式：{auth_detail}")
    cleanup_errors: list[str] = []
    artifact_fixture_server: ThreadingHTTPServer | None = None
    artifact_fixture_restore: Callable[[], tuple[bool, str]] | None = None
    artifact_fixture_enabled = False
    try:
        with urllib.request.urlopen(OPENAPI_URL, timeout=10) as resp:
            spec = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        print(f"[失败] 无法获取 OpenAPI 文档：{exc}")
        return 1

    paths = spec.get("paths", {})
    results: list[CheckResult] = []
    smoke_context: SmokeResourceContext | None = None
    smoke_context_error = ""

    writer_live_smoke_paths = {
        "/api/writer/novels/{project_id}/chapters/generate",
        "/api/writer/novels/{project_id}/chapters/cancel",
        "/api/writer/novels/{project_id}/chapters/evaluate",
        "/api/writer/novels/{project_id}/chapters/select",
    }

    artifact_live_smoke_path = "/api/agent/artifacts/{artifact_id}/accept"

    try:
        artifact_routes_present = any("/api/agent/artifacts/{artifact_id}" in path for path in paths)
        if artifact_routes_present and os.getenv(ARTIFACT_FIXTURE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
            artifact_fixture_server, artifact_fixture_restore, fixture_detail = enable_artifact_fixture_provider()
            if artifact_fixture_server is None or artifact_fixture_restore is None:
                smoke_context_error = fixture_detail
                print(f"[失败] Artifact fixture 初始化失败：{fixture_detail}")
                raise RuntimeError(fixture_detail)
            artifact_fixture_enabled = True
            print("[正常] Artifact HTTP fixture：enabled（本地 Provider，配置可逆）")

        if any(path in paths for path in writer_live_smoke_paths) or artifact_fixture_enabled:
            smoke_context, smoke_context_error = create_smoke_project(artifact_fixture=artifact_fixture_enabled)
            if artifact_fixture_enabled and (smoke_context_error or smoke_context is None or not smoke_context.artifact_id):
                raise RuntimeError(smoke_context_error or "artifact-fixture-did-not-yield-artifact")

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            real_path = substitute_path_params(path, smoke_context)
            path_requires_resource_identity = has_resource_identity_param(path)
            for method in HTTP_METHODS:
                if method not in methods:
                    continue
                method_upper = method.upper()
                if (method_upper, path) in SKIPPED_MUTATING_ROUTES:
                    results.append(
                        CheckResult(
                            method=method_upper,
                            path=path,
                            status=0,
                            ok=True,
                            detail="skipped-mutating-route",
                        )
                    )
                    continue
                if (method_upper, path) in SKIPPED_STREAMING_ROUTES:
                    results.append(
                        CheckResult(
                            method=method_upper,
                            path=path,
                            status=0,
                            ok=True,
                            detail="skipped-streaming-route",
                        )
                    )
                    continue
                if (method_upper, path) in SKIPPED_EXPENSIVE_ROUTES:
                    results.append(
                        CheckResult(
                            method=method_upper,
                            path=path,
                            status=0,
                            ok=True,
                            detail="skipped-expensive-route",
                        )
                    )
                    continue
                if path == artifact_live_smoke_path and artifact_fixture_enabled:
                    if smoke_context is None or not smoke_context.artifact_id:
                        results.append(
                            CheckResult(
                                method=method_upper,
                                path=path,
                                status=599,
                                ok=False,
                                detail=smoke_context_error or "artifact-fixture-did-not-yield-artifact",
                            )
                        )
                        continue
                    status, detail = smoke_artifact_accept_route(smoke_context)
                    results.append(
                        CheckResult(
                            method=method_upper,
                            path=path,
                            status=status,
                            ok=status == 200,
                            detail=detail,
                        )
                    )
                    continue
                if path in writer_live_smoke_paths and artifact_fixture_enabled:
                    results.append(CheckResult(method_upper, path, 0, True, "skipped-mutating-route"))
                    continue
                if path in writer_live_smoke_paths:
                    if smoke_context is None:
                        results.append(
                            CheckResult(
                                method=method_upper,
                                path=path,
                                status=0,
                                ok=True,
                                detail=smoke_context_error or "skipped-resource-identity-route",
                            )
                        )
                        continue
                    status, detail = smoke_writer_route(method_upper, path, smoke_context)
                    ok = status == 0 or (status in ALLOWED_STATUSES and status < 500)
                    results.append(
                        CheckResult(
                            method=method_upper,
                            path=path,
                            status=status,
                            ok=ok,
                            detail=("live-resource-smoke" if status != 0 else detail),
                        )
                    )
                    if detail == "live-resource-smoke":
                        results[-1].detail = "live-resource-smoke"
                    elif detail == "skipped-live-resource-prerequisite":
                        results[-1].detail = detail
                    continue
                if path_requires_resource_identity:
                    resolvable_get = (
                        method_upper == "GET"
                        and smoke_context is not None
                        and not has_unresolved_resource_identity(path, smoke_context)
                    )
                    if not resolvable_get:
                        results.append(
                            CheckResult(
                                method=method_upper,
                                path=path,
                                status=0,
                                ok=True,
                                detail="skipped-resource-identity-route",
                            )
                        )
                        continue
                url = f"{BASE_URL}{real_path}"
                if artifact_fixture_enabled and smoke_context:
                    if path == "/api/agent/artifacts/{artifact_id}/diff":
                        url += "?" + urlencode({"against_artifact_id": smoke_context.accepted_artifact_id})
                    elif path == "/api/agent/artifacts/{artifact_id}/chapter-version-diff":
                        url += "?" + urlencode({"project_id": smoke_context.project_id,
                                                "chapter_number": smoke_context.chapter_number,
                                                "version_id": smoke_context.accepted_version_id})
                status, detail = request(method_upper, url)
                ok = (status == 200 if artifact_fixture_enabled and path.startswith("/api/agent/artifacts/") else status in ALLOWED_STATUSES and status < 500)
                results.append(
                    CheckResult(
                        method=method_upper,
                        path=path,
                        status=status,
                        ok=ok,
                        detail=detail,
                    )
                )
    except Exception as exc:
        results.append(CheckResult("FIXTURE", "smoke-fixture", 599, False, str(exc)))
    finally:
        try:
            if smoke_context is not None:
                cleanup_ok, cleanup_detail = cleanup_smoke_project(smoke_context.project_id, smoke_context)
                if not cleanup_ok:
                    cleanup_errors.append(cleanup_detail)
        except Exception as exc:
            cleanup_errors.append(f"project-cleanup: {type(exc).__name__}")
        try:
            if artifact_fixture_restore is not None:
                restore_ok, restore_detail = artifact_fixture_restore()
                if not restore_ok:
                    cleanup_errors.append(restore_detail)
        except Exception as exc:
            cleanup_errors.append(f"provider-config-cleanup: {type(exc).__name__}")
        finally:
            _shutdown_artifact_fixture_provider(artifact_fixture_server)

    failed = [item for item in results if not item.ok]
    if cleanup_errors:
        failed.extend(
            CheckResult(method="CLEANUP", path="smoke-fixture", status=599, ok=False, detail=detail)
            for detail in cleanup_errors
        )
    skipped = [item for item in results if item.status == 0]
    passed = [item for item in results if item.ok and item.status != 0]

    for item in results:
        if item.status == 0:
            reason = SKIP_REASON_LABELS.get(item.detail, item.detail or "跳过：未提供原因。")
            print(f"[跳过] {item.method:6} {item.path:70} -> {reason}")
            continue

        if item.ok:
            print(f"[通过] {item.method:6} {item.path:70} -> 状态码 {item.status}")
            continue

        print(f"[失败] {item.method:6} {item.path:70} -> 状态码 {item.status}")
        if item.detail:
            print(f"        原因：{item.detail}")

    print()
    print(f"检查总数：{len(results)}")
    print(f"通过：{len(passed)}")
    print(f"跳过：{len(skipped)}")
    print(f"失败：{len(failed)}")
    skip_counts = Counter(item.detail or "unknown" for item in results if item.status == 0)
    identity_family_counts = Counter(
        family
        for item in results
        if item.status == 0 and item.detail == "skipped-resource-identity-route"
        for family in resource_identity_families(item.path)
    )
    if skip_counts:
        print("跳过分类：")
        for reason, count in sorted(skip_counts.items()):
            print(f"  {reason}: {count}")
    if identity_family_counts:
        print("资源身份跳过分组：")
        for family, count in sorted(identity_family_counts.items()):
            print(f"  {family}: {count}")

    if failed:
        print("\n失败明细：")
        for item in failed:
            print(f"- {item.method} {item.path} -> 状态码 {item.status}")
            if item.detail:
                print(f"  原因：{item.detail}")
        return 1

    print("[通过] OpenAPI 路由冒烟检查通过：未发现 500 级错误。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
