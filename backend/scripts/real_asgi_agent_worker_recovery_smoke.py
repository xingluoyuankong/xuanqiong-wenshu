"""Real API + Worker crash/recovery smoke; prints only redacted facts."""
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
    print("AGENT_WORKER_RECOVERY_SMOKE " + json.dumps(values, ensure_ascii=False, sort_keys=True))


def hidden(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            ("reasoning" in str(k).lower() or "thought" in str(k).lower() or str(k).lower() in {"system_prompt", "provider_secret", "api_key", "authorization"})
            or hidden(v)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return any(hidden(v) for v in value)
    return False


def startup_timeout_seconds() -> float:
    raw = os.getenv("AGENT_SMOKE_STARTUP_TIMEOUT_SECONDS", "90")
    try:
        return min(180.0, max(30.0, float(raw)))
    except (TypeError, ValueError):
        return 90.0


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
        report(status="blocked", reason="missing_execute_flag", recovery_verified=False)
        return 2
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        report(status="blocked", reason="missing_admin_password", recovery_verified=False)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix="xq-agent-worker-recovery-"))
    db_path = temp_dir / "recovery.sqlite"
    port = "18128"
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
        "AGENT_VISIBLE_RESPONSE_MAX_TOKENS": "512",
        "AGENT_RUN_LEASE_SECONDS": "3",
        "AGENT_WORKER_POLL_INTERVAL": "0.1",
        "AGENT_WORKER_LEASE_SECONDS": "3",
        "TASK_RECONCILE_INTERVAL_SECONDS": "15",
    }
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port, "--log-level", "warning", "--no-access-log"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
    )
    worker1 = None
    worker2 = None
    started = time.monotonic()
    killed_after_event = False
    recovery_ready_seen = False
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20.0) as client:
            login = await wait_login(client, username, password, time.monotonic() + startup_timeout_seconds())
            if login is None:
                report(status="failed", phase="api_startup_or_login", recovery_verified=False, api_exit=api.poll())
                return 1
            token = str(login.json().get("access_token") or "")
            headers = {"Authorization": "Bearer " + token}
            worker1 = subprocess.Popen(
                [sys.executable, "scripts/agent_worker.py", "--worker-id", "recovery-worker-1", "--lease-seconds", "3", "--poll-interval", "0.1"],
                cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
            )
            project = await client.post("/api/novels", headers=headers, json={"title": "Worker 恢复冒烟", "initial_prompt": "仅用于验证 Worker 崩溃接管，不含用户小说正文。"})
            if project.status_code not in {200, 201}:
                report(status="failed", phase="project_create", http_status=project.status_code, recovery_verified=False)
                return 1
            project_id = str(project.json().get("id") or "")
            session_response = await client.post("/api/agent/sessions", headers=headers, json={"project_id": project_id, "title": "Worker recovery smoke"})
            session_id = str(session_response.json().get("id") or "")
            message = await client.post(
                f"/api/agent/sessions/{session_id}/messages",
                headers=headers,
                json={"content": "请连续输出至少二百个简短的中文项目状态标签；只使用通用状态词，不引用、扩写或复述任何小说内容。", "tools": ["project.context"], "arguments": {}},
            )
            if message.status_code != 201:
                report(status="failed", phase="message_submit", http_status=message.status_code, recovery_verified=False)
                return 1
            run_id = str((message.json().get("run") or {}).get("id") or "")

            crash_deadline = time.monotonic() + 30
            pre_crash_events: list[dict] = []
            pre_crash_job: dict = {}
            pre_crash_run: dict = {}
            while time.monotonic() < crash_deadline:
                detail = await client.get(f"/api/agent/sessions/{session_id}", headers=headers)
                if detail.status_code == 200:
                    runs = detail.json().get("runs") or []
                    pre_crash_run = next((item for item in runs if str(item.get("id")) == run_id), {})
                events_response = await client.get(f"/api/agent/sessions/{session_id}/runs/{run_id}/events", headers=headers)
                if events_response.status_code == 200:
                    pre_crash_events = list(events_response.json() or [])
                jobs_response = await client.get(f"/api/agent/jobs?project_id={project_id}", headers=headers)
                if jobs_response.status_code == 200:
                    rows = list(jobs_response.json() or [])
                    pre_crash_job = next((item for item in rows if str(item.get("kind") or "") == "visible_response"), {})
                event_types = [str(item.get("event_type") or "") for item in pre_crash_events]
                run_is_active = str(pre_crash_run.get("status") or "") not in {"completed", "failed", "cancelled"}
                # Kill only after the visible-response worker has durably emitted its
                # start event.  Earlier queued/running observations can belong to the
                # planning job and do not prove a provider-response lease was interrupted.
                if run_is_active and "assistant_started" in event_types:
                    worker1.terminate()
                    try:
                        worker1.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        worker1.kill()
                        worker1.wait(timeout=10)
                    killed_after_event = True
                    break
                await asyncio.sleep(0.05)
            if not killed_after_event:
                report(status="failed", phase="worker1_did_not_claim_before_timeout", recovery_verified=False, pre_crash_run_status=pre_crash_run.get("status"), pre_crash_job_status=pre_crash_job.get("status"))
                return 1

            # The second worker is started immediately; it must wait for the
            # first worker lease to expire and then atomically reclaim the durable job.

            worker2 = subprocess.Popen(
                [sys.executable, "scripts/agent_worker.py", "--worker-id", "recovery-worker-2", "--lease-seconds", "3", "--poll-interval", "0.1"],
                cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
            )
            terminal_deadline = time.monotonic() + 90
            while time.monotonic() < terminal_deadline:
                detail = await client.get(f"/api/agent/sessions/{session_id}", headers=headers)
                if detail.status_code == 200:
                    runs = detail.json().get("runs") or []
                    final_run = next((item for item in runs if str(item.get("id")) == run_id), {})
                events_response = await client.get(f"/api/agent/sessions/{session_id}/runs/{run_id}/events", headers=headers)
                if events_response.status_code == 200:
                    final_events = list(events_response.json() or [])
                jobs_response = await client.get(f"/api/agent/jobs?project_id={project_id}", headers=headers)
                if jobs_response.status_code == 200:
                    final_jobs = list(jobs_response.json() or [])
                final_job = next((item for item in final_jobs if str(item.get("kind") or "") == "visible_response"), {})
                if final_run.get("status") in {"completed", "failed", "cancelled"} and final_job.get("status") in {"succeeded", "failed", "cancelled", "dead_letter"}:
                    break
                await asyncio.sleep(0.5)

            event_types = [str(item.get("event_type") or "") for item in final_events]
            sequences = [int(item.get("sequence") or 0) for item in final_events]
            deltas = [item for item in final_events if item.get("event_type") == "assistant_delta"]
            hidden_seen = any(hidden(item.get("data_json") or {}) for item in final_events)
            final_job = next((item for item in final_jobs if str(item.get("kind") or "") == "visible_response"), {})
            job_attempt_count = int(final_job.get("attempt_count") or 0)
            job_lease_generation = int(final_job.get("lease_generation") or 0)
            job_reclaimed = job_attempt_count >= 2 and job_lease_generation >= 2
            run_failure_types = [
                str((item.get("data_json") or {}).get("error_type") or "")
                for item in final_events
                if item.get("event_type") == "run_failed"
            ]
            run_failure_reasons = [
                str((item.get("data_json") or {}).get("reason") or "")[:200]
                for item in final_events
                if item.get("event_type") == "run_failed"
            ]
            recovery_verified = (
                killed_after_event
                and job_reclaimed
                and final_run.get("status") == "completed"
                and final_job.get("status") == "succeeded"
                and bool(deltas)
                and sequences == sorted(set(sequences))
                and not hidden_seen
            )
            report(
                status="passed" if recovery_verified else "failed",
                phase="completed" if recovery_verified else "terminal",
                recovery_verified=recovery_verified,
                killed_after_event=killed_after_event,
                recovery_ready_seen=recovery_ready_seen,
                job_reclaimed=job_reclaimed,
                job_attempt_count=job_attempt_count,
                job_lease_generation=job_lease_generation,
                job_error_type=str(final_job.get("error_type") or ""),
                job_error_detail_present=bool(final_job.get("error_detail")),
                run_failure_types=run_failure_types,
                run_failure_reasons=run_failure_reasons,
                run_status=final_run.get("status"),
                job_status=final_job.get("status"),
                visible_delta_events=len(deltas),
                visible_delta_characters=sum(len(str((item.get("data_json") or {}).get("content") or "")) for item in deltas),
                event_types=event_types,
                event_sequence_count=len(sequences),
                event_sequence_monotonic=sequences == sorted(set(sequences)),
                reasoning_fields_seen=hidden_seen,
                worker1_exit=worker1.poll() if worker1 else None,
                worker2_exit=worker2.poll() if worker2 else None,
                api_exit=api.poll(),
                elapsed_seconds=round(time.monotonic() - started, 2),
            )
            return 0 if recovery_verified else 1
    finally:
        for proc in (worker2, worker1, api):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
