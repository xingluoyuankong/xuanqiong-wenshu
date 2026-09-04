"""Legacy outline fallback state contract tests.

The latest legacy record is the source of truth: active states may be restored,
while terminal and idle states must not be projected as an active job.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.api.routers import writer


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class _FakeSession:
    pass


class _FakeNovelService:
    records = []

    def __init__(self, _session):
        pass

    async def list_conversations(self, _project_id):
        return self.records


async def _load(monkeypatch, records):
    session = _FakeSession()
    _FakeNovelService.records = records
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    return await writer._load_active_outline_job_from_db("legacy-outline-project")


def _record(status: str, run_id: str, *, progress_stage: str | None = None):
    payload = {
        "run_id": run_id,
        "project_id": "legacy-outline-project",
        "status": status,
        "progress_stage": progress_stage or status,
    }
    return SimpleNamespace(
        metadata={"type": "outline_generation_job", "status": status},
        content=json.dumps(payload),
    )


@pytest.mark.asyncio
async def test_latest_active_legacy_record_is_restored(monkeypatch):
    result = await _load(
        monkeypatch,
        [_record("successful", "old-terminal"), _record("generating", "active-run")],
    )

    assert result is not None
    assert result["run_id"] == "active-run"


@pytest.mark.asyncio
async def test_latest_terminal_legacy_record_does_not_resurrect_older_active_job(monkeypatch):
    result = await _load(
        monkeypatch,
        [_record("generating", "old-active"), _record("successful", "latest-terminal")],
    )

    assert result is None


@pytest.mark.asyncio
async def test_latest_idle_legacy_record_does_not_project_an_active_job(monkeypatch):
    result = await _load(
        monkeypatch,
        [_record("generating", "old-active"), _record("idle", "latest-idle")],
    )

    assert result is None


@pytest.mark.asyncio
async def test_latest_cancelled_legacy_record_is_terminal(monkeypatch):
    result = await _load(monkeypatch, [_record("cancelled", "cancelled-run")])

    assert result is None
