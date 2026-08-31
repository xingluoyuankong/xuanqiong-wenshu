"""Isolated real Provider Worker smoke; emits only a redacted status report."""
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
load_dotenv(ROOT / '.env', override=False)


def report(**values: object) -> None:
    print('AGENT_PROVIDER_WORKER_SMOKE ' + json.dumps(values, ensure_ascii=False, sort_keys=True))


def startup_timeout_seconds() -> float:
    raw = os.getenv("AGENT_SMOKE_STARTUP_TIMEOUT_SECONDS", "90")
    try:
        return min(180.0, max(30.0, float(raw)))
    except (TypeError, ValueError):
        return 90.0


def hidden(value: object) -> bool:
    if isinstance(value, dict):
        return any(('reasoning' in str(k).lower() or 'thought' in str(k).lower() or str(k).lower() in {'system_prompt', 'provider_secret', 'api_key', 'authorization'}) or hidden(v) for k, v in value.items())
    if isinstance(value, list):
        return any(hidden(v) for v in value)
    return False


async def wait_login(client: httpx.AsyncClient, username: str, password: str, deadline: float):
    while time.monotonic() < deadline:
        try:
            response = await client.post('/api/auth/login', data={'username': username, 'password': password})
            if response.status_code == 200:
                return response
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None


async def main() -> int:
    if '--execute' not in sys.argv:
        report(status='blocked', reason='missing_execute_flag', provider_called=False)
        return 2
    password = os.getenv('ADMIN_DEFAULT_PASSWORD', '')
    username = os.getenv('ADMIN_DEFAULT_USERNAME', 'admin')
    if not password:
        report(status='blocked', reason='missing_admin_password', provider_called=False)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix='xq-agent-provider-worker-'))
    db_path = temp_dir / 'worker-smoke.db'
    port = '18127'
    env = {
        **os.environ,
        'DB_PROVIDER': 'sqlite',
        'DATABASE_URL': '',
        'SQLITE_DB_PATH': str(db_path),
        'ENVIRONMENT': 'development',
        'DEBUG': 'false',
        'XUANQIONG_TEST_LIGHT_IMPORTS': '1',
        'PYTHONUNBUFFERED': '1',
        'PYTHONUTF8': '1',
        'AGENT_INLINE_VISIBLE_RESPONSE': 'false',
        'AGENT_WORKER_POLL_INTERVAL': '0.1',
        'AGENT_WORKER_LEASE_SECONDS': '60',
    }
    api = subprocess.Popen([
        sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', port, '--log-level', 'warning', '--no-access-log'
    ], cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    worker = None
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=20.0) as client:
            login = await wait_login(client, username, password, time.monotonic() + startup_timeout_seconds())
            if login is None:
                report(status='failed', phase='api_startup_or_login', provider_called=False, api_exit=api.poll())
                return 1
            token = str(login.json().get('access_token') or '')
            headers = {'Authorization': 'Bearer ' + token}
            worker = subprocess.Popen([sys.executable, 'scripts/agent_worker.py', '--worker-id', 'provider-smoke-worker', '--poll-interval', '0.1'], cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            project = await client.post('/api/novels', headers=headers, json={'title': '隔离 Worker Provider 冒烟', 'initial_prompt': '仅用于验证 Agent Worker 与 Provider 通道，不含用户小说正文。'})
            if project.status_code not in {200, 201}:
                report(status='failed', phase='project_create', http_status=project.status_code, provider_called=False)
                return 1
            project_id = str(project.json().get('id') or '')
            session = await client.post('/api/agent/sessions', headers=headers, json={'project_id': project_id, 'title': 'Worker Provider smoke'})
            session_id = str(session.json().get('id') or '')
            message = await client.post('/api/agent/sessions/' + session_id + '/messages', headers=headers, json={'content': '请仅用一句不超过四十字的中文确认项目上下文已读取，不引用或扩写小说内容。', 'tools': ['project.context'], 'arguments': {}})
            if message.status_code != 201:
                report(status='failed', phase='message_submit', http_status=message.status_code, provider_called=False)
                return 1
            payload = message.json()
            run_id = str((payload.get('run') or {}).get('id') or '')
            deadline = time.monotonic() + 120
            run_status = ''
            events: list[dict] = []
            jobs: list[dict] = []
            while time.monotonic() < deadline:
                detail = await client.get('/api/agent/sessions/' + session_id, headers=headers)
                runs = detail.json().get('runs') or [] if detail.status_code == 200 else []
                run = next((item for item in runs if str(item.get('id')) == run_id), {})
                run_status = str(run.get('status') or '')
                events_response = await client.get('/api/agent/sessions/' + session_id + '/runs/' + run_id + '/events', headers=headers)
                if events_response.status_code == 200:
                    events = list(events_response.json() or [])
                jobs_response = await client.get('/api/agent/jobs?project_id=' + project_id, headers=headers)
                if jobs_response.status_code == 200:
                    jobs = list(jobs_response.json() or [])
                if run_status in {'completed', 'failed', 'cancelled'} and jobs and jobs[0].get('status') in {'succeeded', 'failed', 'cancelled', 'dead_letter'}:
                    break
                await asyncio.sleep(0.5)
            event_types = [str(item.get('event_type') or '') for item in events]
            deltas = [item for item in events if item.get('event_type') == 'assistant_delta']
            delta_chars = sum(len(str((item.get('data_json') or {}).get('content') or '')) for item in deltas)
            hidden_seen = any(hidden(item.get('data_json') or {}) for item in events)
            job_status = str((jobs[0] if jobs else {}).get('status') or '')
            run_error_types = [{'type': str((item.get('data_json') or {}).get('error_type') or ''), 'reason': str((item.get('data_json') or {}).get('reason') or '')[:200]} for item in events if item.get('event_type') == 'run_failed']
            job_error_type = str((jobs[0] if jobs else {}).get('error_type') or '')
            verified = run_status == 'completed' and job_status == 'succeeded' and bool(deltas) and delta_chars > 0 and not hidden_seen
            report(status='passed' if verified else 'failed', phase='completed' if verified else 'terminal', provider_called=verified, worker_process_exit=worker.poll() if worker else None, api_process_exit=api.poll(), planner_provider_called=False, run_status=run_status, job_status=job_status, job_error_type=job_error_type, run_error_types=run_error_types, logical_provider_requests=1, visible_delta_events=len(deltas), visible_delta_characters=delta_chars, reasoning_fields_seen=hidden_seen, event_types=event_types, elapsed_seconds=round(time.monotonic() - started, 2))
            return 0 if verified else 1
    finally:
        for proc in (worker, api):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
