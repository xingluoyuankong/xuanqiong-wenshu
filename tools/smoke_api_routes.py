from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BACKEND_PORT = os.getenv("XUANQIONG_WENSHU_BACKEND_PORT", "8013")
BASE_URL = (
    os.getenv("XUANQIONG_WENSHU_BACKEND_BASE_URL")
    or f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}"
).rstrip("/")
OPENAPI_URL = f"{BASE_URL}/openapi.json"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")
ALLOWED_STATUSES = {200, 201, 202, 204, 400, 401, 403, 404, 405, 409, 410, 415, 422, 429, 503}
PATH_PARAM_PATTERN = re.compile(r"\{([^}]+)\}")
SKIPPED_MUTATING_ROUTES = {
    ("POST", "/api/llm-config/auto-switch"),
    ("PUT", "/api/llm-config"),
    ("DELETE", "/api/llm-config"),
    ("POST", "/api/projects/{project_id}/chapters/{chapter_number}/patch/apply"),
    ("POST", "/api/projects/{project_id}/chapters/{chapter_number}/patch/revert"),
    ("POST", "/api/optimizer/apply-optimization"),
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
    "skipped-resource-identity-route": "跳过：该接口依赖真实资源 ID，当前冒烟检查未提供可用资源，因此不再伪造占位 ID 请求。",
    "skipped-live-resource-prerequisite": "跳过：最小真实资源前置条件未满足，暂不继续后续写作台动作。",
    "live-resource-smoke": "使用最小真实资源执行写作台关键路由冒烟。",
}


@dataclass
class SmokeResourceContext:
    project_id: str
    chapter_number: int
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


def substitute_path_params(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if "chapter" in name and "number" in name:
            return "1"
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
    }
    data = None
    if method in {"POST", "PUT", "PATCH"}:
        payload = json.dumps(json_body or {}, ensure_ascii=False).encode("utf-8")
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


def create_smoke_project() -> tuple[SmokeResourceContext | None, str]:
    status, payload, detail = request_json(
        "POST",
        f"{BASE_URL}/api/novels",
        json_body={
            "title": f"OpenAPI Smoke {int(os.times().elapsed * 1000)}",
            "initial_prompt": "用于最小真实资源写作台路由冒烟校验。",
        },
    )
    if status != 201 or not payload or not payload.get("id"):
        preview = detail[:300] if detail else ""
        return None, f"create-project-failed: status={status} detail={preview}"

    project_id = str(payload["id"])
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
        cleanup_smoke_project(project_id)
        preview = blueprint_detail[:300] if blueprint_detail else ""
        return None, f"patch-blueprint-failed: status={blueprint_status} detail={preview}"

    return SmokeResourceContext(project_id=project_id, chapter_number=1), ""


def cleanup_smoke_project(project_id: str) -> None:
    request("DELETE", f"{BASE_URL}/api/novels", json_body=[project_id])


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
        )
        if status < 500:
            context.generated = True
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
    try:
        with urllib.request.urlopen(OPENAPI_URL, timeout=10) as resp:
            spec = json.loads(resp.read().decode("utf-8"))
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

    if any(path in paths for path in writer_live_smoke_paths):
        smoke_context, smoke_context_error = create_smoke_project()

    try:
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            real_path = substitute_path_params(path)
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
                status, detail = request(method_upper, url)
                ok = status in ALLOWED_STATUSES and status < 500
                results.append(
                    CheckResult(
                        method=method_upper,
                        path=path,
                        status=status,
                        ok=ok,
                        detail=detail,
                    )
                )
    finally:
        if smoke_context is not None:
            cleanup_smoke_project(smoke_context.project_id)

    failed = [item for item in results if not item.ok]
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
