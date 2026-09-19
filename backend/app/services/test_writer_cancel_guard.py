import json
import types

import pytest
from fastapi import BackgroundTasks

from app.api.routers import writer
from app.schemas.novel import CancelChapterRequest


class _Session:
    def __init__(self):
        self.commit_count = 0
        self.refresh_count = 0

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _chapter):
        self.refresh_count += 1


instances = []


class _Service:
    def __init__(self, session):
        self.session = session
        self.chapter = types.SimpleNamespace(
            project_id="project-1",
            chapter_number=1,
            status="generating",
            real_summary=json.dumps({"generation_runtime": {"run_id": "run-1", "progress_stage": "generate_mission"}}),
        )
        instances.append(self)

    async def ensure_project_owner(self, project_id, user_id):
        return types.SimpleNamespace(id=project_id, user_id=user_id)

    async def get_or_create_chapter(self, project_id, chapter_number):
        return self.chapter



@pytest.mark.anyio
async def test_cancel_marks_request_but_keeps_chapter_busy(monkeypatch):
    session = _Session()
    monkeypatch.setattr(writer, "NovelService", _Service)
    async def fake_drain(_run_id):
        return False
    monkeypatch.setattr(writer, "_cancel_registered_generation_task", fake_drain)
    async def fake_load(*_args, **_kwargs):
        return {"ok": True}
    monkeypatch.setattr(writer, "_load_project_schema", fake_load)

    chapter = await writer.cancel_chapter_generation(
        project_id="project-1",
        request=CancelChapterRequest(chapter_number=1, reason="stop now"),
        session=session,
        current_user=types.SimpleNamespace(id=7),
    )

    assert chapter == {"ok": True}
    assert session.commit_count == 1
    assert session.refresh_count == 1
    runtime = json.loads(instances[0].chapter.real_summary)["generation_runtime"]
    assert instances[0].chapter.status == "generating"
    assert runtime["cancel_requested"] is True
    assert runtime["progress_stage"] == "cancel_requested"
    assert runtime["allowed_actions"] == ["refresh_status"]


@pytest.mark.anyio
async def test_cancel_marks_failed_only_after_task_is_drained(monkeypatch):
    session = _Session()
    calls = {}
    monkeypatch.setattr(writer, "NovelService", _Service)

    async def fake_load(*_args, **_kwargs):
        return {"ok": True}

    async def fake_drain(run_id):
        calls["drain"] = run_id
        return True

    async def fake_mark(session_arg, *, chapter, reason, run_id):
        calls["mark"] = (session_arg, chapter.status, reason, run_id)

    async def fake_terminal(**kwargs):
        calls["terminal"] = kwargs

    monkeypatch.setattr(writer, "_load_project_schema", fake_load)
    monkeypatch.setattr(writer, "_cancel_registered_generation_task", fake_drain)
    monkeypatch.setattr(writer, "_mark_busy_chapter_failed", fake_mark)
    monkeypatch.setattr(writer, "_emit_generation_failure_terminal", fake_terminal)

    result = await writer.cancel_chapter_generation(
        project_id="project-1",
        request=CancelChapterRequest(chapter_number=1, reason="drained stop"),
        session=session,
        current_user=types.SimpleNamespace(id=7),
    )

    assert result == {"ok": True}
    assert calls["drain"] == "run-1"
    assert calls["mark"][1:] == ("generating", "drained stop", "run-1")
    assert calls["terminal"] == {
        "run_id": "run-1",
        "reason": "drained stop",
        "code": "GENERATION_CANCELLED",
        "stage": "cancelled",
    }
