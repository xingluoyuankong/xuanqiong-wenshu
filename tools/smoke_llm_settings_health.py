from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Tuple


DEFAULT_BACKEND_PORT = os.getenv("XUANQIONG_WENSHU_BACKEND_PORT", "8013")
DEFAULT_FRONTEND_PORT = os.getenv("XUANQIONG_WENSHU_FRONTEND_PORT", "5174")
BACKEND_BASE = (
    os.getenv("XUANQIONG_WENSHU_BACKEND_BASE_URL")
    or f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}"
).rstrip("/")
FRONTEND_BASE = (
    os.getenv("XUANQIONG_WENSHU_FRONTEND_BASE_URL")
    or f"http://127.0.0.1:{DEFAULT_FRONTEND_PORT}"
).rstrip("/")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def http_get(url: str, timeout: int = 30) -> Tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "ignore")
        return resp.status, body


def expect_status(url: str, expected_status: int) -> None:
    try:
        status, _ = http_get(url)
    except urllib.error.HTTPError as exc:
        status = exc.code
    if status != expected_status:
        raise RuntimeError(f"接口 {url} 期望状态码 {expected_status}，实际为 {status}")
    print(f"[正常] 接口可访问：{url} -> {status}")


def expect_one_of(url: str, expected_statuses: tuple[int, ...]) -> None:
    try:
        status, _ = http_get(url)
    except urllib.error.HTTPError as exc:
        status = exc.code
    if status not in expected_statuses:
        raise RuntimeError(f"接口 {url} 期望状态码属于 {expected_statuses}，实际为 {status}")
    print(f"[正常] 接口可访问：{url} -> {status}")


def main() -> int:
    try:
        # Base service reachability.
        expect_status(f"{BACKEND_BASE}/docs", 200)
        expect_status(f"{FRONTEND_BASE}", 200)
        expect_status(f"{BACKEND_BASE}/api/updates/latest", 200)
        expect_one_of(f"{BACKEND_BASE}/api/llm-config", (200, 404))

        # LLM settings feature APIs should be present in OpenAPI.
        status, body = http_get(f"{BACKEND_BASE}/openapi.json")
        if status != 200:
            raise RuntimeError(f"/openapi.json 期望状态码 200，实际为 {status}")
        spec = json.loads(body)
        paths = spec.get("paths", {})
        required_paths = [
            "/api/llm-config/health-check",
            "/api/llm-config/auto-switch",
            "/api/llm-config/models",
        ]
        for path in required_paths:
            if path not in paths:
                raise RuntimeError(f"OpenAPI 中缺少接口路径：{path}")
            print(f"[正常] OpenAPI 已包含接口：{path}")

        # health-check 在开启鉴权时可能返回 401；脚本只验证接口存在与鉴权语义正确。
        try:
            health_status, health_body = http_get(f"{BACKEND_BASE}/api/llm-config/health-check", timeout=30)
        except urllib.error.HTTPError as exc:
            health_status = exc.code
            health_body = exc.read().decode("utf-8", "ignore")

        if health_status == 200:
            health = json.loads(health_body)
            if "has_usable_profile" not in health:
                raise RuntimeError("health-check 响应缺少 has_usable_profile 字段")
            print(f"[正常] health-check 响应包含 has_usable_profile={health['has_usable_profile']}")
        elif health_status == 401:
            print("[正常] health-check 需要鉴权，匿名请求返回 401，接口鉴权语义正常")
        else:
            raise RuntimeError(f"/api/llm-config/health-check 期望状态码为 200 或 401，实际为 {health_status}")

        print("[通过] LLM 设置相关接口检查通过（已验证 OpenAPI 暴露与 health-check 可达/鉴权语义）。")
        return 0
    except Exception as exc:
        print(f"[失败] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
