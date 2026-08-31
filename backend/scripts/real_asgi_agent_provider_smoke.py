"""Isolated real-Provider Agent smoke. Never prints secrets, prompts, response text, or reasoning."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / '.env', override=False)


def _safe_report(**values: object) -> None:
    print('AGENT_PROVIDER_SMOKE ' + json.dumps(values, ensure_ascii=False, sort_keys=True))


def _contains_hidden_reasoning(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if 'reasoning' in normalized or 'thought' in normalized or normalized in {'cot', 'chain_of_thought'}:
                return True
            if _contains_hidden_reasoning(item):
                return True
    if isinstance(value, list):
        return any(_contains_hidden_reasoning(item) for item in value)
    return False


async def main() -> int:
    if '--execute' not in sys.argv:
        _safe_report(status='blocked', reason='missing_execute_flag', provider_called=False)
        return 2

    temp_dir = Path(tempfile.mkdtemp(prefix='xq-agent-provider-smoke-'))
    db_path = temp_dir / 'agent-provider-smoke.db'
    os.environ['DB_PROVIDER'] = 'sqlite'
    os.environ['DATABASE_URL'] = ''
    os.environ['SQLITE_DB_PATH'] = str(db_path)
    # One logical visible-response request only. The Agent request specifies a
    # read tool, so planner Provider selection is deliberately skipped.
    os.environ['AGENT_VISIBLE_RESPONSE_MAX_TOKENS'] = '96'
    os.environ['XUANQIONG_TEST_LIGHT_IMPORTS'] = '1'
    os.environ['PYTHONUTF8'] = '1'
    sys.path.insert(0, str(ROOT))

    from app.db.session import engine
    from app.main import app

    started = time.monotonic()
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url='http://agent-provider-smoke', timeout=20.0) as client:
                username = os.getenv('ADMIN_DEFAULT_USERNAME', 'admin')
                password = os.getenv('ADMIN_DEFAULT_PASSWORD', '')
                if not password:
                    _safe_report(status='blocked', reason='missing_admin_password', provider_called=False)
                    return 2
                login = await client.post('/api/auth/login', data={'username': username, 'password': password})
                if login.status_code != 200:
                    _safe_report(status='failed', phase='login', http_status=login.status_code, provider_called=False)
                    return 1
                token = str(login.json().get('access_token') or '')
                if not token:
                    _safe_report(status='failed', phase='login_token', provider_called=False)
                    return 1
                headers = {'Authorization': 'Bearer ' + token}
                project = await client.post(
                    '/api/novels',
                    headers=headers,
                    json={
                        'title': '隔离 Provider Agent 冒烟',
                        'initial_prompt': '仅用于验证受控 Agent 的只读可见回复，不含用户小说正文。',
                    },
                )
                if project.status_code != 201:
                    _safe_report(status='failed', phase='project_create', http_status=project.status_code, provider_called=False)
                    return 1
                project_id = str(project.json().get('id') or '')
                session = await client.post('/api/agent/sessions', headers=headers, json={'project_id': project_id, 'title': 'Provider smoke'})
                if session.status_code != 201:
                    _safe_report(status='failed', phase='session_create', http_status=session.status_code, provider_called=False)
                    return 1
                session_id = str(session.json().get('id') or '')
                message = await client.post(
                    '/api/agent/sessions/' + session_id + '/messages',
                    headers=headers,
                    json={
                        'content': '请仅用一句不超过四十字的中文确认项目上下文已经读取；不要引用或扩写小说内容。',
                        'tools': ['project.context'],
                        'arguments': {},
                    },
                )
                if message.status_code != 201:
                    _safe_report(status='failed', phase='message_submit', http_status=message.status_code, provider_called=False)
                    return 1
                payload = message.json()
                if payload.get('provider_called') is not False:
                    _safe_report(status='failed', phase='planner_guard', provider_called=False)
                    return 1
                run_id = str((payload.get('run') or {}).get('id') or '')
                deadline = time.monotonic() + 75.0
                events: list[dict[str, object]] = []
                run_status = ''
                while time.monotonic() < deadline:
                    run_response = await client.get('/api/agent/sessions/' + session_id, headers=headers)
                    if run_response.status_code != 200:
                        _safe_report(status='failed', phase='session_poll', http_status=run_response.status_code, provider_called=False)
                        return 1
                    runs = run_response.json().get('runs') or []
                    matching = next((item for item in runs if str(item.get('id')) == run_id), None)
                    run_status = str((matching or {}).get('status') or '')
                    event_response = await client.get('/api/agent/sessions/' + session_id + '/runs/' + run_id + '/events', headers=headers)
                    if event_response.status_code == 200:
                        events = list(event_response.json() or [])
                    if run_status in {'completed', 'failed', 'cancelled'}:
                        break
                    await asyncio.sleep(0.25)
                else:
                    await client.post('/api/agent/runs/' + run_id + '/cancel', headers=headers)
                    _safe_report(status='failed', phase='timeout_cancelled', provider_called=False, elapsed_seconds=round(time.monotonic() - started, 2))
                    return 1

                event_types = [str(item.get('event_type') or '') for item in events]
                delta_events = [item for item in events if item.get('event_type') == 'assistant_delta']
                delta_chars = sum(len(str((item.get('data_json') or {}).get('content') or '')) for item in delta_events)
                reasoning_seen = any(_contains_hidden_reasoning((item.get('data_json') or {})) for item in delta_events)
                verified = run_status == 'completed' and bool(delta_events) and delta_chars > 0 and not reasoning_seen
                _safe_report(
                    status='passed' if verified else 'failed',
                    phase='completed' if verified else 'run_terminal',
                    provider_called=verified,
                    logical_provider_requests=1,
                    planner_provider_called=False,
                    run_status=run_status,
                    event_types=event_types,
                    visible_delta_events=len(delta_events),
                    visible_delta_characters=delta_chars,
                    reasoning_fields_seen=reasoning_seen,
                    max_output_tokens=96,
                    elapsed_seconds=round(time.monotonic() - started, 2),
                )
                return 0 if verified else 1
    finally:
        await engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
