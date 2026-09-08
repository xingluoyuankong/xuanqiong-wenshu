"""Run the real HTTP Artifact smoke against a disposable production application."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app.agent.test_asgi_worker_event_replay import (
    BACKEND_ROOT, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD,
    _free_local_port, _prepare_current_schema, _worker_environment,
    _wait_for_health, _stop_workers,
)


@pytest.mark.asyncio
async def test_tcp_artifact_smoke_generates_accepts_reads_and_cleans(tmp_path, monkeypatch, capsys):
    database = tmp_path / "artifact-http.sqlite"
    await _prepare_current_schema(f"sqlite+aiosqlite:///{database.as_posix()}")
    port = _free_local_port()
    artifact_root = tmp_path / "artifact-files"
    artifact_root.mkdir()
    # A pre-existing unrelated file must survive even though it is in the same root.
    sentinel = artifact_root / "unrelated.md"
    sentinel.write_text("keep existing artifact", encoding="utf-8")
    env = _worker_environment(f"sqlite+aiosqlite:///{database.as_posix()}", tmp_path / "logs")
    env.update({"AGENT_INLINE_EXECUTION": "true", "AGENT_INLINE_VISIBLE_RESPONSE": "false",
                "VECTOR_DB_URL": "", "PYTHONPATH": str(BACKEND_ROOT)})
    bootstrap = (
        "from pathlib import Path; import app.agent.write_executor as writer; "
        f"writer._ARTIFACT_ROOT = Path({str(artifact_root)!r}); "
        "import uvicorn; "
        f"uvicorn.run('app.main:app', host='127.0.0.1', port={port}, access_log=False, log_level='warning')"
    )
    path = BACKEND_ROOT.parent / "tools" / "smoke_api_routes.py"
    spec = importlib.util.spec_from_file_location("tcp_artifact_smoke", path)
    smoke = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = smoke
    spec.loader.exec_module(smoke)
    monkeypatch.setattr(smoke, "BASE_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(smoke, "OPENAPI_URL", f"http://127.0.0.1:{port}/openapi.json")
    monkeypatch.setattr(smoke, "ARTIFACT_STORAGE_ROOT", artifact_root)
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_TOKEN", raising=False)
    monkeypatch.setenv("XUANQIONG_WENSHU_SMOKE_USERNAME", TEST_ADMIN_USERNAME)
    monkeypatch.setenv("XUANQIONG_WENSHU_SMOKE_PASSWORD", TEST_ADMIN_PASSWORD)
    monkeypatch.setenv(smoke.ARTIFACT_FIXTURE_ENV, "1")
    observed = []
    original_cleanup = smoke.cleanup_smoke_project

    def checked_cleanup(project_id, context=None):
        try:
            if context and context.artifact_id and context.accepted_artifact_id:
                assert context.artifact_id != context.accepted_artifact_id
                status, run, detail = smoke.request_json("GET", f"{smoke.BASE_URL}/api/agent/runs/{context.run_id}/state")
                assert status == 200, detail
                assert run["status"] == "completed"
                assert run["phase"] == "accepted"
                observed.append(context)
        finally:
            cleanup_result = original_cleanup(project_id, context)
        return cleanup_result

    monkeypatch.setattr(smoke, "cleanup_smoke_project", checked_cleanup)
    with (tmp_path / "http-server.log").open("w", encoding="utf-8") as log:
        worker = subprocess.Popen([sys.executable, "-c", bootstrap], cwd=str(BACKEND_ROOT),
                                  env=env, stdout=log, stderr=log)
        try:
            _wait_for_health(port=port, worker=worker)
            # Snapshot live, disposable state only after boot seeding completes.
            with sqlite3.connect(database) as con:
                tracked = [row[0] for row in con.execute("select name from sqlite_master where type='table'")
                           if row[0].startswith('agent_') and row[0] not in {
                               'agent_catalog_releases', 'agent_provider_releases', 'agent_capability_definitions'}]
                tracked += ["novel_projects", "chapters", "chapter_versions", "llm_configs"]
                before = {name: con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tracked}
            result = smoke.main()
            output = capsys.readouterr().out
            assert result == 0, output
            assert len(observed) == 1
            for suffix in ('content', 'quality', 'lineage', 'quality-blockers', 'rewrite-instructions', 'diff', 'chapter-version-diff'):
                lines = [line for line in output.splitlines() if f'/api/agent/artifacts/{{artifact_id}}/{suffix} ' in line]
                assert len(lines) == 1 and '[通过]' in lines[0] and '200' in lines[0], (suffix, output)
            with sqlite3.connect(database) as con:
                after = {name: con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tracked}
                assert after == before, {name: (before[name], after[name]) for name in tracked if before[name] != after[name]}
                assert con.execute('PRAGMA foreign_key_check').fetchall() == []
            assert sorted(p.name for p in artifact_root.iterdir()) == [sentinel.name]
            assert sentinel.read_text(encoding='utf-8') == 'keep existing artifact'
            print('TCP_ARTIFACT_SMOKE_PASSED', json.dumps({'tables_checked': len(tracked), 'state_counts_restored': True}))
        finally:
            _stop_workers([worker])
