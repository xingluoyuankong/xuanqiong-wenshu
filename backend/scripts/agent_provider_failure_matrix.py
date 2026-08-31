"""Deterministic ASGI Provider failure matrix for Agent provenance.

Runs against isolated SQLite and patches only the LLM adapter boundary.  It exercises
real FastAPI routes, durable Run/Job/Event facts, approvals, and after_sequence
replay without sending prompts, credentials, or novel text to an external Provider.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env", override=False)


def report(**values: object) -> None:
    print("AGENT_PROVIDER_FAILURE_MATRIX " + json.dumps(values, ensure_ascii=False, sort_keys=True))


def event_data(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("data_json")
    return value if isinstance(value, dict) else {}


def contains_hidden(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            "reasoning" in str(key).lower()
            or "thought" in str(key).lower()
            or str(key).lower() in {"cot", "chain_of_thought"}
            or contains_hidden(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_hidden(item) for item in value)
    return False


def status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", f"https://provider-fixture.invalid/{status_code}")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError(f"fixture provider status {status_code}", request=request, response=response)


async def create_project_session(
    client: httpx.AsyncClient, headers: dict[str, str], *, title: str
) -> tuple[str, str]:
    project_response = await client.post(
        "/api/novels",
        headers=headers,
        json={"title": title, "initial_prompt": "隔离 Agent Provider 故障矩阵项目。"},
    )
    project_response.raise_for_status()
    project_id = str(project_response.json().get("id") or "")
    session_response = await client.post(
        "/api/agent/sessions", headers=headers, json={"project_id": project_id, "title": title}
    )
    session_response.raise_for_status()
    return project_id, str(session_response.json().get("id") or "")


async def run_snapshot(
    client: httpx.AsyncClient, headers: dict[str, str], *, session_id: str, run_id: str
) -> dict[str, Any]:
    detail, events, provenance = await asyncio.gather(
        client.get(f"/api/agent/sessions/{session_id}", headers=headers),
        client.get(f"/api/agent/sessions/{session_id}/runs/{run_id}/events", headers=headers),
        client.get(f"/api/agent/runs/{run_id}/provider-provenance", headers=headers),
    )
    detail.raise_for_status()
    events.raise_for_status()
    provenance.raise_for_status()
    run = next((item for item in detail.json().get("runs") or [] if str(item.get("id")) == run_id), {})
    rows = list(events.json() or [])
    first_sequence = int(rows[0].get("sequence") or 0) if rows else 0
    replay_rows: list[dict[str, Any]] = []
    if first_sequence:
        replay = await client.get(
            f"/api/agent/sessions/{session_id}/runs/{run_id}/events",
            headers=headers,
            params={"after_sequence": first_sequence},
        )
        replay.raise_for_status()
        replay_rows = list(replay.json() or [])
    return {
        "run": run,
        "events": rows,
        "provenance": provenance.json(),
        "after_sequence_count": len(replay_rows),
        "after_sequence_ok": bool(replay_rows) and all(int(item.get("sequence") or 0) > first_sequence for item in replay_rows),
    }


async def wait_terminal(
    client: httpx.AsyncClient, headers: dict[str, str], *, session_id: str, run_id: str
) -> dict[str, Any]:
    for _ in range(100):
        snapshot = await run_snapshot(client, headers, session_id=session_id, run_id=run_id)
        if str(snapshot["run"].get("status") or "") in {"completed", "failed", "cancelled"}:
            return snapshot
        await asyncio.sleep(0.05)
    raise TimeoutError("fixture run did not become terminal")


async def submit_message(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    session_id: str,
    content: str,
    tools: list[str] | None = None,
    arguments: dict[str, Any] | None = None,
    context_refs: list[dict[str, Any]] | None = None,
) -> str:
    payload: dict[str, Any] = {"content": content}
    if tools is not None:
        payload["tools"] = tools
    if arguments is not None:
        payload["arguments"] = arguments
    if context_refs is not None:
        payload["context_refs"] = context_refs
    response = await client.post(f"/api/agent/sessions/{session_id}/messages", headers=headers, json=payload)
    response.raise_for_status()
    return str((response.json().get("run") or {}).get("id") or "")


async def wait_approval(
    client: httpx.AsyncClient, headers: dict[str, str], *, run_id: str
) -> str:
    for _ in range(100):
        approvals = await client.get(f"/api/agent/runs/{run_id}/approvals", headers=headers)
        approvals.raise_for_status()
        rows = list(approvals.json() or [])
        if rows:
            return str(rows[0].get("id") or "")
        await asyncio.sleep(0.05)
    raise TimeoutError("fixture write approval was not created")


async def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="xq-agent-provider-failure-matrix-"))
    os.environ.update(
        {
            "DB_PROVIDER": "sqlite",
            "DATABASE_URL": "",
            "SQLITE_DB_PATH": str(temp_dir / "provider-failure-matrix.db"),
            "AGENT_INLINE_EXECUTION": "true",
            "AGENT_INLINE_VISIBLE_RESPONSE": "true",
            "AGENT_VISIBLE_RESPONSE_MAX_TOKENS": "96",
            "XUANQIONG_TEST_LIGHT_IMPORTS": "1",
            "PYTHONUTF8": "1",
        }
    )
    sys.path.insert(0, str(ROOT))
    from app.db.session import AsyncSessionLocal, engine
    from app.main import app
    from app.models import Chapter
    from app.services.llm_service import LLMService

    results: list[dict[str, Any]] = []
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://provider-failure-matrix", timeout=30.0) as client:
                password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
                username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
                if not password:
                    report(status="blocked", reason="missing_admin_password", cases=[])
                    return 2
                login = await client.post("/api/auth/login", data={"username": username, "password": password})
                login.raise_for_status()
                headers = {"Authorization": "Bearer " + str(login.json().get("access_token") or "")}

                async def visible_success(self: Any, **kwargs: Any):
                    yield "Provider fixture visible response."

                # Case 1: Planner HTTP 429 falls back to read-only plan, then Response still succeeds.
                async def planner_429(self: Any, *args: Any, **kwargs: Any) -> str:
                    raise status_error(429)

                project_id, session_id = await create_project_session(client, headers, title="P2-4 planner 429")
                with ExitStack() as stack:
                    stack.enter_context(patch.object(LLMService, "get_llm_response", planner_429))
                    stack.enter_context(patch.object(LLMService, "stream_visible_response", visible_success))
                    run_id = await submit_message(client, headers, session_id=session_id, content="动态读取项目状态。")
                    snapshot = await wait_terminal(client, headers, session_id=session_id, run_id=run_id)
                events = snapshot["events"]
                provenance = snapshot["provenance"]
                passed = (
                    snapshot["run"].get("status") == "completed"
                    and provenance.get("planner_provider_called") is False
                    and provenance.get("planner_provider_fallback_reason") == "HTTPStatusError"
                    and provenance.get("response_provider_called") is True
                    and provenance.get("candidate_writer_provider_called") is None
                    and "plan_created" in [item.get("event_type") for item in events]
                    and snapshot["after_sequence_ok"]
                    and not contains_hidden([event_data(item) for item in events])
                )
                results.append({"case": "planner_http_429", "passed": passed, "run_status": snapshot["run"].get("status"), "provenance": provenance, "event_types": [item.get("event_type") for item in events], "after_sequence_ok": snapshot["after_sequence_ok"]})

                # Case 2: Planner succeeds but the visible Response stream returns HTTP 5xx.
                async def planner_success(self: Any, *args: Any, **kwargs: Any) -> str:
                    return '{"summary":"fixture plan","tools":["project.context"]}'

                async def response_5xx(self: Any, **kwargs: Any):
                    raise status_error(503)
                    yield "unreachable"

                project_id, session_id = await create_project_session(client, headers, title="P2-4 response 503")
                with ExitStack() as stack:
                    stack.enter_context(patch.object(LLMService, "get_llm_response", planner_success))
                    stack.enter_context(patch.object(LLMService, "stream_visible_response", response_5xx))
                    run_id = await submit_message(client, headers, session_id=session_id, content="动态读取项目状态。")
                    snapshot = await wait_terminal(client, headers, session_id=session_id, run_id=run_id)
                events = snapshot["events"]
                provenance = snapshot["provenance"]
                passed = (
                    snapshot["run"].get("status") == "failed"
                    and provenance.get("planner_provider_called") is True
                    and provenance.get("response_provider_called") is False
                    and provenance.get("response_provider_fallback_reason") == "HTTPStatusError"
                    and provenance.get("candidate_writer_provider_called") is None
                    and "run_failed" in [item.get("event_type") for item in events]
                    and snapshot["after_sequence_ok"]
                    and not contains_hidden([event_data(item) for item in events])
                )
                results.append({"case": "response_http_503", "passed": passed, "run_status": snapshot["run"].get("status"), "provenance": provenance, "event_types": [item.get("event_type") for item in events], "after_sequence_ok": snapshot["after_sequence_ok"]})

                # Case 3: approved Candidate Writer receives HTTP 429; no Artifact may be created.
                async def writer_429(self: Any, **kwargs: Any):
                    raise status_error(429)
                    yield "unreachable"

                project_id, session_id = await create_project_session(client, headers, title="P2-4 writer 429")
                async with AsyncSessionLocal() as fixture_session:
                    fixture_session.add(Chapter(project_id=project_id, chapter_number=1, status="not_generated"))
                    await fixture_session.commit()
                with patch.object(LLMService, "stream_visible_response", writer_429):
                    run_id = await submit_message(
                        client,
                        headers,
                        session_id=session_id,
                        content="生成一个受审批的章节候选。",
                        tools=["chapter.generate"],
                        arguments={"chapter_number": 1, "goal": "Provider 429 fixture"},
                        context_refs=[{"kind": "chapter", "project_id": project_id, "chapter_number": 1, "role": "selected"}],
                    )
                    approval_id = await wait_approval(client, headers, run_id=run_id)
                    if not approval_id:
                        raise RuntimeError("fixture write approval identifier is empty")
                    decision = await client.post(f"/api/agent/approvals/{approval_id}/decision", headers=headers, json={"approved": True})
                    decision.raise_for_status()
                    execute = await client.post(f"/api/agent/approvals/{approval_id}/execute", headers=headers)
                    execute_status = execute.status_code
                    try:
                        execute_detail = execute.json()
                    except ValueError:
                        execute_detail = {"body": execute.text[:300]}
                snapshot = await wait_terminal(client, headers, session_id=session_id, run_id=run_id)
                events = snapshot["events"]
                provenance = snapshot["provenance"]
                artifacts = await client.get(f"/api/agent/runs/{run_id}/artifacts", headers=headers)
                artifacts.raise_for_status()
                passed = (
                    execute_status == 409
                    and snapshot["run"].get("status") == "failed"
                    and provenance.get("planner_provider_called") is False
                    and provenance.get("response_provider_called") is None
                    and provenance.get("candidate_writer_provider_called") is False
                    and provenance.get("candidate_writer_provider_fallback_reason") == "HTTPStatusError"
                    and not artifacts.json()
                    and "write_execution_failed" in [item.get("event_type") for item in events]
                    and snapshot["after_sequence_ok"]
                    and not contains_hidden([event_data(item) for item in events])
                )
                results.append({"case": "writer_http_429", "passed": passed, "run_status": snapshot["run"].get("status"), "execute_http_status": execute_status, "provenance": provenance, "event_types": [item.get("event_type") for item in events], "after_sequence_ok": snapshot["after_sequence_ok"], "artifact_count": len(artifacts.json() or [])})

        report(status="passed" if all(item["passed"] for item in results) else "failed", cases=results)
        return 0 if all(item["passed"] for item in results) else 1
    finally:
        await engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
