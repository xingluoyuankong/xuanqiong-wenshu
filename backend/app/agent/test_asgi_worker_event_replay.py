from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

import httpx
import pytest
from alembic import command
from alembic.config import Config

from app.core.config import settings


BACKEND_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 60
TEST_ADMIN_USERNAME = "card010-asgi-admin"
TEST_ADMIN_PASSWORD = "Card010-Unique-Password-For-Worker-Replay"
TEST_SECRET_KEY = "card010-shared-jwt-secret-key-for-two-independent-asgi-workers"


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def _prepare_current_schema(database_url: str) -> None:
    """Run the actual Alembic head upgrade for the disposable shared database."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    previous_database_url = settings.database_url
    settings.database_url = database_url
    try:
        await asyncio.to_thread(command.upgrade, config, "head")
    finally:
        settings.database_url = previous_database_url


def _worker_environment(database_url: str, log_dir: Path) -> dict[str, str]:
    """Return one explicit production environment shared by both Uvicorn processes."""
    return {
        **os.environ,
        "DATABASE_URL": database_url,
        "DB_PROVIDER": "sqlite",
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "SECRET_KEY": TEST_SECRET_KEY,
        "ADMIN_DEFAULT_USERNAME": TEST_ADMIN_USERNAME,
        "ADMIN_DEFAULT_PASSWORD": TEST_ADMIN_PASSWORD,
        "ADMIN_DEFAULT_EMAIL": "card010-asgi-admin@example.invalid",
        "FILE_LOGGING_ENABLED": "false",
        "XUANQIONG_WENSHU_LOG_DIR": str(log_dir),
        "LOGGING_LEVEL": "WARNING",
        "CONSOLE_LOGGING_LEVEL": "WARNING",
        "AGENT_TOOL_PROVIDERS_ENABLED": "false",
        "AGENT_TOOL_PROVIDER_STARTUP_POLICY": "fail_closed",
        "AGENT_INLINE_EXECUTION": "false",
        "AGENT_INLINE_VISIBLE_RESPONSE": "false",
        "PYTHONUTF8": "1",
    }


def _start_worker(*, port: int, environment: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
            "--no-access-log",
        ],
        cwd=str(BACKEND_ROOT),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _worker_output(worker: subprocess.Popen[str]) -> str:
    if worker.poll() is None:
        return "worker is still running"
    stdout, stderr = worker.communicate(timeout=5)
    return f"stdout:\n{stdout[-4000:]}\nstderr:\n{stderr[-4000:]}"


def _wait_for_health(*, port: int, worker: subprocess.Popen[str]) -> None:
    endpoint = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_error = ""
    while time.monotonic() < deadline:
        if worker.poll() is not None:
            raise AssertionError(f"ASGI worker on port {port} exited during startup:\n{_worker_output(worker)}")
        try:
            with urlopen(endpoint, timeout=1.5) as response:  # nosec B310: loopback test worker only
                if response.status == 200:
                    return
        except (URLError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.1)
    raise AssertionError(
        f"ASGI worker on port {port} did not become healthy within {STARTUP_TIMEOUT_SECONDS}s: {last_error}\n"
        f"{_worker_output(worker)}"
    )


def _stop_workers(workers: Iterable[subprocess.Popen[str]]) -> None:
    for worker in workers:
        if worker.poll() is None:
            worker.terminate()
    for worker in workers:
        if worker.poll() is None:
            try:
                worker.wait(timeout=12)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=12)


async def _read_sse_replay(
    client: httpx.AsyncClient,
    *,
    url: str,
    headers: dict[str, str],
    expected_count: int,
) -> list[tuple[int, str, dict[str, object]]]:
    emitted: list[tuple[int, str, dict[str, object]]] = []
    pending_id: int | None = None
    pending_event = ""
    pending_data = ""
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                pending_id = int(line.removeprefix("id: "))
            elif line.startswith("event: "):
                pending_event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                pending_data = line.removeprefix("data: ")
            elif line == "" and pending_id is not None:
                payload = json.loads(pending_data)
                emitted.append((pending_id, pending_event, payload))
                if len(emitted) == expected_count:
                    return emitted
                pending_id = None
                pending_event = ""
                pending_data = ""
    raise AssertionError(f"SSE closed before {expected_count} durable events were replayed: {emitted}")


@pytest.mark.asyncio
async def test_worker_b_replays_events_written_via_worker_a_http_to_shared_sqlite(tmp_path: Path):
    """Worker A writes via production JWT HTTP; Worker B replays via real SSE."""
    database_path = (tmp_path / "two-asgi-workers.sqlite").resolve()
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    writer_port = _free_local_port()
    reader_port = _free_local_port()
    while reader_port == writer_port:
        reader_port = _free_local_port()

    await _prepare_current_schema(database_url)
    log_dir = tmp_path / "asgi-worker-logs"
    log_dir.mkdir()
    environment = _worker_environment(database_url, log_dir)
    workers: list[subprocess.Popen[str]] = []
    writer_base_url = f"http://127.0.0.1:{writer_port}"
    reader_base_url = f"http://127.0.0.1:{reader_port}"
    try:
        # Writer performs the one-time first-boot seed, then Reader starts as
        # an independent Uvicorn process against the already initialized same
        # database.  This isolates the replay proof from the separate admin
        # seed race while keeping both real lifespans and shared DB semantics.
        writer = _start_worker(port=writer_port, environment=environment)
        workers.append(writer)
        _wait_for_health(port=writer_port, worker=writer)
        reader = _start_worker(port=reader_port, environment=environment)
        workers.append(reader)
        assert writer.pid != reader.pid
        _wait_for_health(port=reader_port, worker=reader)

        async with httpx.AsyncClient(timeout=20) as client:
            login_response = await client.post(
                f"{writer_base_url}/api/auth/login",
                data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
            )
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            create_session_response = await client.post(
                f"{writer_base_url}/api/agent/sessions",
                headers=headers,
                json={"title": "CARD-010 cross-process durable replay"},
            )
            assert create_session_response.status_code == 201
            session_id = create_session_response.json()["id"]

            # This is the only write path in the test.  It uses Worker A's
            # public API to persist the message, Run, run_started and progress
            # ledger records; the pytest process never writes AgentEventRecord.
            create_run_response = await client.post(
                f"{writer_base_url}/api/agent/sessions/{session_id}/messages",
                headers=headers,
                json={
                    "content": "验证两个独立 ASGI Worker 之间的 durable Agent event replay。",
                    "tools": [],
                    "arguments": {},
                    "context_refs": [],
                    "tool_arguments": {},
                },
            )
            assert create_run_response.status_code == 201
            run_id = create_run_response.json()["run"]["id"]

            list_response = await client.get(
                f"{writer_base_url}/api/agent/sessions/{session_id}/runs/{run_id}/events?after_sequence=0",
                headers=headers,
            )
            assert list_response.status_code == 200
            durable_events = list_response.json()
            sequences = [item["sequence"] for item in durable_events]
            assert len(durable_events) >= 2
            assert sequences == sorted(sequences)
            assert len(sequences) == len(set(sequences))
            assert all(sequence > 0 for sequence in sequences)
            assert durable_events[0]["event_type"] == "run_started"

            first_sequence = sequences[0]
            expected_replay = durable_events[1:]
            replay = await _read_sse_replay(
                client,
                url=f"{reader_base_url}/api/agent/sessions/{session_id}/runs/{run_id}/stream?after_sequence=0",
                headers={**headers, "Last-Event-ID": str(first_sequence)},
                expected_count=len(expected_replay),
            )

        emitted_sequences = [sequence for sequence, _, _ in replay]
        emitted_event_types = [event_type for _, event_type, _ in replay]
        assert emitted_sequences == [item["sequence"] for item in expected_replay]
        assert emitted_event_types == [item["event_type"] for item in expected_replay]
        assert first_sequence not in emitted_sequences
        for sequence, event_type, payload in replay:
            assert payload["sequence"] == sequence
            assert payload["run_id"] == run_id
            assert payload["event_type"] == event_type
    finally:
        _stop_workers(workers)


@pytest.mark.asyncio
async def test_independent_worker_once_claims_agent_job_created_via_http(tmp_path: Path):
    """A queued HTTP Agent job is claimed by the separate worker CLI exactly once.

    The explicit read-only project.list tool avoids any Provider call: this test
    exercises the durable HTTP -> Job -> worker process -> HTTP ledger path.
    """
    database_path = (tmp_path / "worker-once-http.sqlite").resolve()
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    writer_port = _free_local_port()
    await _prepare_current_schema(database_url)
    log_dir = tmp_path / "worker-once-logs"
    log_dir.mkdir()
    environment = _worker_environment(database_url, log_dir)
    workers: list[subprocess.Popen[str]] = []
    writer_base_url = f"http://127.0.0.1:{writer_port}"
    try:
        writer = _start_worker(port=writer_port, environment=environment)
        workers.append(writer)
        _wait_for_health(port=writer_port, worker=writer)

        async with httpx.AsyncClient(timeout=25) as client:
            login_response = await client.post(
                f"{writer_base_url}/api/auth/login",
                data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
            )
            assert login_response.status_code == 200
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
            session_response = await client.post(
                f"{writer_base_url}/api/agent/sessions",
                headers=headers,
                json={"title": "CARD-014 worker once"},
            )
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]
            message_response = await client.post(
                f"{writer_base_url}/api/agent/sessions/{session_id}/messages",
                headers=headers,
                json={
                    "content": "使用 project.list 验证独立 Worker 领取 durable Job。",
                    "tools": ["project.list"],
                    "arguments": {},
                    "context_refs": [],
                    "tool_arguments": {},
                },
            )
            assert message_response.status_code == 201
            response_payload = message_response.json()
            run_id = response_payload["run"]["id"]
            execution_job_id = response_payload["execution_job"]["id"]
            assert response_payload["execution_job"]["kind"] == "agent_execution"
            assert response_payload["execution_job"]["status"] == "queued"

        worker_result = subprocess.run(
            [sys.executable, "scripts/agent_worker.py", "--once", "--worker-id", "card014-worker-once"],
            cwd=str(BACKEND_ROOT),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=75,
        )
        assert worker_result.returncode == 0, worker_result.stdout
        assert worker_result.returncode == 0

        async with httpx.AsyncClient(timeout=25) as client:
            jobs_response = await client.get(f"{writer_base_url}/api/agent/jobs", headers=headers)
            events_response = await client.get(
                f"{writer_base_url}/api/agent/sessions/{session_id}/runs/{run_id}/events?after_sequence=0",
                headers=headers,
            )
            state_response = await client.get(f"{writer_base_url}/api/agent/runs/{run_id}/state", headers=headers)

        assert jobs_response.status_code == 200
        jobs = {item["id"]: item for item in jobs_response.json()}
        assert jobs[execution_job_id]["status"] == "succeeded"
        visible_jobs = [item for item in jobs.values() if item["run_id"] == run_id and item["kind"] == "visible_response"]
        assert len(visible_jobs) == 1
        assert visible_jobs[0]["status"] == "queued"

        assert events_response.status_code == 200
        event_types = [item["event_type"] for item in events_response.json()]
        assert "run_started" in event_types
        assert "plan_created" in event_types
        assert "assistant_queued" in event_types

        assert state_response.status_code == 200
        state_jobs = {item["id"]: item for item in state_response.json()["jobs"]}
        assert state_jobs[execution_job_id]["status"] == "succeeded"
        assert state_jobs[visible_jobs[0]["id"]]["status"] == "queued"
    finally:
        _stop_workers(workers)
