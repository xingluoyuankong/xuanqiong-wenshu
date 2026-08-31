"""Isolated real Provider Planner smoke for the durable Agent HTTP lifecycle.

Never prints secrets, prompts, model output, or hidden reasoning.  Use --execute to
make one planner request and one visible-response request against the configured
Provider in an isolated SQLite database.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env", override=False)


def _safe_report(**values: object) -> None:
    print("AGENT_PLANNER_PROVIDER_SMOKE " + json.dumps(values, ensure_ascii=False, sort_keys=True))


def _contains_hidden_reasoning(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if "reasoning" in normalized or "thought" in normalized or normalized in {"cot", "chain_of_thought"}:
                return True
            if _contains_hidden_reasoning(item):
                return True
    if isinstance(value, list):
        return any(_contains_hidden_reasoning(item) for item in value)
    return False


def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("data_json")
    return value if isinstance(value, dict) else {}


async def main() -> int:
    if "--execute" not in sys.argv:
        _safe_report(status="blocked", reason="missing_execute_flag", planner_provider_called=False)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="xq-agent-planner-provider-smoke-"))
    db_path = temp_dir / "agent-planner-provider-smoke.db"
    os.environ["DB_PROVIDER"] = "sqlite"
    os.environ["DATABASE_URL"] = ""
    os.environ["SQLITE_DB_PATH"] = str(db_path)
    os.environ["AGENT_INLINE_EXECUTION"] = "true"
    os.environ["AGENT_INLINE_VISIBLE_RESPONSE"] = "true"
    os.environ["AGENT_VISIBLE_RESPONSE_MAX_TOKENS"] = "96"
    os.environ["XUANQIONG_TEST_LIGHT_IMPORTS"] = "1"
    os.environ["PYTHONUTF8"] = "1"
    sys.path.insert(0, str(ROOT))

    from app.db.session import engine
    from app.main import app

    started = time.monotonic()
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://agent-planner-provider-smoke", timeout=30.0) as client:
                username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
                password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
                if not password:
                    _safe_report(status="blocked", reason="missing_admin_password", planner_provider_called=False)
                    return 2
                login = await client.post("/api/auth/login", data={"username": username, "password": password})
                if login.status_code != 200:
                    _safe_report(status="failed", phase="login", http_status=login.status_code, planner_provider_called=False)
                    return 1
                token = str(login.json().get("access_token") or "")
                if not token:
                    _safe_report(status="failed", phase="login_token", planner_provider_called=False)
                    return 1
                headers = {"Authorization": "Bearer " + token}
                project = await client.post(
                    "/api/novels",
                    headers=headers,
                    json={
                        "title": "隔离 Planner Provider 冒烟",
                        "initial_prompt": "仅用于验证受控 Agent 的动态只读规划和公开可见回复，不含用户小说正文。",
                    },
                )
                if project.status_code != 201:
                    _safe_report(status="failed", phase="project_create", http_status=project.status_code, planner_provider_called=False)
                    return 1
                project_id = str(project.json().get("id") or "")
                session = await client.post(
                    "/api/agent/sessions",
                    headers=headers,
                    json={"project_id": project_id, "title": "Planner Provider smoke"},
                )
                if session.status_code != 201:
                    _safe_report(status="failed", phase="session_create", http_status=session.status_code, planner_provider_called=False)
                    return 1
                session_id = str(session.json().get("id") or "")
                # Intentionally omit tools, arguments, and tool_arguments.  This is the
                # only path that invokes AgentOrchestrator's Provider-backed planner.
                message = await client.post(
                    "/api/agent/sessions/" + session_id + "/messages",
                    headers=headers,
                    json={
                        "content": "请动态选择项目内只读能力，确认当前项目上下文可用并给出一句简短可见摘要；不得生成、改写或接受任何小说正文。",
                    },
                )
                if message.status_code != 201:
                    _safe_report(status="failed", phase="message_submit", http_status=message.status_code, planner_provider_called=False)
                    return 1
                initial = message.json()
                run_id = str((initial.get("run") or {}).get("id") or "")
                if not run_id:
                    _safe_report(status="failed", phase="message_run_id", planner_provider_called=False)
                    return 1

                events: list[dict[str, Any]] = []
                run_status = ""
                deadline = time.monotonic() + 105.0
                while time.monotonic() < deadline:
                    session_response = await client.get("/api/agent/sessions/" + session_id, headers=headers)
                    event_response = await client.get(
                        "/api/agent/sessions/" + session_id + "/runs/" + run_id + "/events",
                        headers=headers,
                    )
                    if session_response.status_code != 200 or event_response.status_code != 200:
                        _safe_report(
                            status="failed",
                            phase="poll",
                            session_http_status=session_response.status_code,
                            events_http_status=event_response.status_code,
                            planner_provider_called=False,
                        )
                        return 1
                    runs = session_response.json().get("runs") or []
                    matching = next((item for item in runs if str(item.get("id") or "") == run_id), None)
                    run_status = str((matching or {}).get("status") or "")
                    events = list(event_response.json() or [])
                    if run_status in {"completed", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(0.25)
                else:
                    await client.post("/api/agent/runs/" + run_id + "/cancel", headers=headers)
                    _safe_report(status="failed", phase="timeout_cancelled", planner_provider_called=False, elapsed_seconds=round(time.monotonic() - started, 2))
                    return 1

                plan_response = await client.get("/api/agent/runs/" + run_id + "/plan", headers=headers)
                revision_response = await client.get("/api/agent/runs/" + run_id + "/plan-revision", headers=headers)
                provenance_response = await client.get("/api/agent/runs/" + run_id + "/provider-provenance", headers=headers)
                summaries_response = await client.get("/api/agent/runs/" + run_id + "/conversation-summaries", headers=headers)
                final_session_response = await client.get("/api/agent/sessions/" + session_id, headers=headers)
                if any(response.status_code != 200 for response in (plan_response, revision_response, provenance_response, summaries_response, final_session_response)):
                    _safe_report(
                        status="failed",
                        phase="fact_queries",
                        plan_http_status=plan_response.status_code,
                        revision_http_status=revision_response.status_code,
                        provenance_http_status=provenance_response.status_code,
                        summaries_http_status=summaries_response.status_code,
                        session_http_status=final_session_response.status_code,
                        planner_provider_called=False,
                    )
                    return 1

                plan = plan_response.json()
                revision = revision_response.json()
                provenance = provenance_response.json()
                summaries = list(summaries_response.json() or [])
                final_messages = list(final_session_response.json().get("messages") or [])
                plan_steps = list(plan.get("steps") or []) if isinstance(plan, dict) else []
                planned_tools = [str(step.get("tool_name") or "") for step in plan_steps if isinstance(step, dict)]
                event_types = [str(item.get("event_type") or "") for item in events]
                delta_events = [item for item in events if item.get("event_type") == "assistant_delta"]
                summary_events = [item for item in events if item.get("event_type") == "public_work_summary"]
                delta_characters = sum(len(str(_event_data(item).get("content") or "")) for item in delta_events)
                hidden_reasoning_seen = any(_contains_hidden_reasoning(_event_data(item)) for item in events)
                first_sequence = int(events[0].get("sequence") or 0) if events else 0
                replay_events: list[dict[str, Any]] = []
                replay_ok = False
                if first_sequence > 0:
                    replay = await client.get(
                        "/api/agent/sessions/" + session_id + "/runs/" + run_id + "/events",
                        headers=headers,
                        params={"after_sequence": first_sequence},
                    )
                    if replay.status_code == 200:
                        replay_events = list(replay.json() or [])
                        replay_ok = bool(replay_events) and all(int(item.get("sequence") or 0) > first_sequence for item in replay_events)

                revision_plan = revision.get("plan_json") if isinstance(revision, dict) else None
                revision_provider_called = bool((revision_plan or {}).get("provider_called")) if isinstance(revision_plan, dict) else False
                planner_provider_called = bool(plan.get("provider_called")) if isinstance(plan, dict) else False
                planner_fallback_reason = plan.get("planner_fallback_reason") if isinstance(plan, dict) else None
                response_provider_called = bool(provenance.get("response_provider_called")) if isinstance(provenance, dict) else False
                candidate_writer_provider_called = provenance.get("candidate_writer_provider_called") if isinstance(provenance, dict) else None
                has_final_assistant = any(str(item.get("role") or "") == "assistant" and str(item.get("content") or "").strip() for item in final_messages)
                verified = (
                    run_status == "completed"
                    and planner_provider_called
                    and revision_provider_called
                    and response_provider_called
                    and candidate_writer_provider_called is None
                    and not planner_fallback_reason
                    and bool(planned_tools)
                    and "plan_created" in event_types
                    and bool(summary_events)
                    and bool(delta_events)
                    and delta_characters > 0
                    and bool(summaries)
                    and has_final_assistant
                    and replay_ok
                    and not hidden_reasoning_seen
                )
                _safe_report(
                    status="passed" if verified else "failed",
                    phase="completed" if verified else "planner_or_lifecycle_unconfirmed",
                    planner_provider_called=planner_provider_called,
                    planner_fallback_reason=(str(planner_fallback_reason)[:160] if planner_fallback_reason else None),
                    plan_revision_provider_called=revision_provider_called,
                    response_provider_called=response_provider_called,
                    candidate_writer_provider_called=candidate_writer_provider_called,
                    run_status=run_status,
                    planned_tools=planned_tools,
                    event_types=event_types,
                    public_work_summary_events=len(summary_events),
                    assistant_delta_events=len(delta_events),
                    assistant_delta_characters=delta_characters,
                    conversation_summary_count=len(summaries),
                    final_assistant_present=has_final_assistant,
                    after_sequence_replay_count=len(replay_events),
                    after_sequence_replay_ok=replay_ok,
                    hidden_reasoning_fields_seen=hidden_reasoning_seen,
                    initial_response_provider_called=bool(initial.get("provider_called")),
                    elapsed_seconds=round(time.monotonic() - started, 2),
                )
                return 0 if verified else 1
    finally:
        await engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
