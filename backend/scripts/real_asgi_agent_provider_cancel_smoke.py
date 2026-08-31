"""Real Provider cancellation-convergence smoke with redacted output only."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env", override=False)


def report(**values: object) -> None:
    print("AGENT_PROVIDER_CANCEL_SMOKE " + json.dumps(values, ensure_ascii=False, sort_keys=True))


def hidden(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            ("reasoning" in str(key).lower()
             or "thought" in str(key).lower()
             or str(key).lower() in {"system_prompt", "provider_secret", "api_key", "authorization"})
            or hidden(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(hidden(item) for item in value)
    return False


async def wait_login(client: httpx.AsyncClient, username: str, password: str, deadline: float):
    while time.monotonic() < deadline:
        try:
            response = await client.post("/api/auth/login", data={"username": username, "password": password})
            if response.status_code == 200:
                return response
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None


async def main() -> int:
    if "--execute" not in sys.argv:
        report(status="blocked", reason="missing_execute_flag", cancellation_verified=False)
        return 2
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        report(status="blocked", reason="missing_admin_password", cancellation_verified=False)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="xq-agent-provider-cancel-"))
    db_path = temp_dir / "cancel.sqlite"
    port = "18132"
    env = {
        **os.environ,
        "DB_PROVIDER": "sqlite",
        "DATABASE_URL": "",
        "SQLITE_DB_PATH": str(db_path),
        "ENVIRONMENT": "development",
        "DEBUG": "false",
        "XUANQIONG_TEST_LIGHT_IMPORTS": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        "AGENT_INLINE_VISIBLE_RESPONSE": "false",
        "AGENT_VISIBLE_RESPONSE_MAX_TOKENS": "1200",
        "AGENT_WORKER_POLL_INTERVAL": "0.05",
        "AGENT_WORKER_LEASE_SECONDS": "30",
        "AGENT_RUN_LEASE_SECONDS": "30",
    }
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port, "--log-level", "warning", "--no-access-log"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
    )
    worker = None
    started = time.monotonic()
    cancel_response_status: int | None = None
    cancel_requested = False
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20.0) as client:
            login = await wait_login(client, username, password, time.monotonic() + 120)
            if login is None:
                report(status="failed", phase="api_startup_or_login", cancellation_verified=False, api_exit=api.poll())
                return 1
            token = str(login.json().get("access_token") or "")
            headers = {"Authorization": "Bearer " + token}
            worker = subprocess.Popen(
                [sys.executable, "scripts/agent_worker.py", "--worker-id", "provider-cancel-worker", "--poll-interval", "0.05", "--lease-seconds", "30"],
                cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
            )
            project = await client.post("/api/novels", headers=headers, json={"title": "Provider cancel smoke", "initial_prompt": "仅用于取消收敛验证，不含用户小说正文。"})
            if project.status_code not in {200, 201}:
                report(status="failed", phase="project_create", http_status=project.status_code, cancellation_verified=False)
                return 1
            project_id = str(project.json().get("id") or "")
            session_response = await client.post("/api/agent/sessions", headers=headers, json={"project_id": project_id, "title": "Provider cancel smoke"})
            if session_response.status_code != 201:
                report(status="failed", phase="session_create", http_status=session_response.status_code, cancellation_verified=False)
                return 1
            session_id = str(session_response.json().get("id") or "")
            message = await client.post(
                f"/api/agent/sessions/{session_id}/messages",
                headers=headers,
                json={"content": "请连续输出大量简短的中文状态标签，至少输出一千字；只使用通用状态词，不引用、扩写或复述任何小说内容。", "tools": ["project.context"], "arguments": {}},
            )
            if message.status_code != 201:
                report(status="failed", phase="message_submit", http_status=message.status_code, cancellation_verified=False)
                return 1
            run_id = str((message.json().get("run") or {}).get("id") or "")
            events: list[dict] = []
            jobs: list[dict] = []
            run: dict = {}
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                detail = await client.get(f"/api/agent/sessions/{session_id}", headers=headers)
                if detail.status_code == 200:
                    run = next((item for item in (detail.json().get("runs") or []) if str(item.get("id")) == run_id), {})
                events_response = await client.get(f"/api/agent/sessions/{session_id}/runs/{run_id}/events", headers=headers)
                if events_response.status_code == 200:
                    events = list(events_response.json() or [])
                jobs_response = await client.get(f"/api/agent/jobs?project_id={project_id}", headers=headers)
                if jobs_response.status_code == 200:
                    jobs = list(jobs_response.json() or [])
                event_types = [str(item.get("event_type") or "") for item in events]
                visible_job = next((item for item in jobs if str(item.get("kind") or "") == "visible_response"), {})
                if not cancel_requested and "assistant_started" in event_types and str(run.get("status") or "") not in {"completed", "failed", "cancelled"}:
                    response = await client.post(f"/api/agent/runs/{run_id}/cancel", headers=headers)
                    cancel_response_status = response.status_code
                    cancel_requested = response.status_code == 200
                if cancel_requested and run.get("status") in {"cancelled", "failed"} and str(visible_job.get("status") or "") in {"cancelled", "failed", "dead_letter"}:
                    break
                await asyncio.sleep(0.1)

            event_types = [str(item.get("event_type") or "") for item in events]
            sequences = [int(item.get("sequence") or 0) for item in events]
            visible_job = next((item for item in jobs if str(item.get("kind") or "") == "visible_response"), {})
            deltas = [item for item in events if item.get("event_type") == "assistant_delta"]
            hidden_seen = any(hidden(item.get("data_json") or {}) for item in events)
            cancellation_verified = (
                cancel_requested
                and cancel_response_status == 200
                and "run_cancelling" in event_types
                and "run_cancelled" in event_types
                and run.get("status") == "cancelled"
                and visible_job.get("status") == "cancelled"
                and sequences == sorted(set(sequences))
                and not hidden_seen
            )
            report(
                status="passed" if cancellation_verified else "failed",
                phase="completed" if cancellation_verified else "terminal",
                cancellation_verified=cancellation_verified,
                cancel_response_status=cancel_response_status,
                run_status=run.get("status"),
                job_status=visible_job.get("status"),
                visible_delta_events=len(deltas),
                event_sequence_count=len(sequences),
                event_sequence_monotonic=sequences == sorted(set(sequences)),
                reasoning_fields_seen=hidden_seen,
                event_types=event_types,
                api_exit=api.poll(),
                worker_exit=worker.poll() if worker else None,
                elapsed_seconds=round(time.monotonic() - started, 2),
            )
            return 0 if cancellation_verified else 1
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=10)
        if api.poll() is None:
            api.terminate()
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait(timeout=10)
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
