from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import types

import pytest

from app.api.routers import writer
from app.services.task_runtime import TaskRuntimeService


def test_stream_cursor_prefers_the_farthest_resume_position():
    assert writer._stream_cursor(3, 8) == 8
    assert writer._stream_cursor(9, 4) == 9
    assert writer._stream_cursor(-4, None) == 0


def test_task_runtime_event_payload_promotes_content_delta_and_log():
    event = SimpleNamespace(
        event_id=12,
        task_id="task-1",
        event_type="content_delta",
        status="running",
        stage="draft",
        progress=42.0,
        message=None,
        payload={"delta": "a content chunk"},
        created_at=datetime.now(timezone.utc),
    )
    payload = writer._task_runtime_event_payload(event)
    assert payload["content_delta"] == "a content chunk"
    assert payload["payload"]["content_delta"] == "a content chunk"
    assert payload["stage"] == "draft"
    assert payload["progress"] == 42.0


def test_completed_task_replay_does_not_mark_old_events_terminal():
    task = SimpleNamespace(status="succeeded")
    created = SimpleNamespace(event_type="task_created", status="queued")
    completed = SimpleNamespace(event_type="task_completed", status="succeeded")
    assert writer._runtime_event_is_terminal(created, task) is False
    assert writer._runtime_event_is_terminal(completed, task) is True


def test_terminal_task_with_historical_non_terminal_events_must_stop_replay():
    """终态任务即使只有旧版历史事件，也不能让 SSE 无限等待。"""
    task = SimpleNamespace(status="succeeded")
    historical_events = [
        SimpleNamespace(event_type="task_created", status="queued"),
        SimpleNamespace(event_type="content_delta", status="running"),
    ]
    terminal_event_seen = any(
        writer._runtime_event_is_terminal(event, task)
        for event in historical_events
    )
    assert terminal_event_seen is False
    assert writer._runtime_stream_should_stop(task, terminal_event_seen) is True
    assert writer._runtime_stream_should_stop(SimpleNamespace(status="running"), False) is False


@pytest.mark.asyncio
async def test_find_chapter_runtime_task_matches_run_id_and_scope(task_session):
    task = await TaskRuntimeService(task_session).create_task(
        task_id="chapter-run-1",
        task_type="chapter_generation",
        owner_user_id=7,
        project_id="project-1",
        chapter_id="11",
        payload={"run_id": "chapter-run-1"},
    )
    found = await writer._find_chapter_runtime_task(
        task_session,
        project_id="project-1",
        chapter_number=3,
        chapter_id=11,
        owner_user_id=7,
        run_id=task.task_id,
    )
    assert found is not None
    assert found.task_id == "chapter-run-1"


def test_log_event_does_not_promote_content_delta():
    event = SimpleNamespace(
        event_id=13,
        task_id="task-1",
        event_type="log",
        status="running",
        stage="draft",
        progress=42.0,
        message="backend log",
        payload={"content_delta": "should stay out", "log": "backend log"},
        created_at=datetime.now(timezone.utc),
    )
    payload = writer._task_runtime_event_payload(event)
    assert "content_delta" not in payload
    assert "content_delta" not in payload["payload"]
    assert payload["log"] == "backend log"


@pytest.mark.asyncio
async def test_longform_plan_registration_persists_blueprint_context(task_session, monkeypatch):
    task = await TaskRuntimeService(task_session).create_task(
        task_id="chapter-longform-context-1",
        task_type="chapter_generation",
        owner_user_id=7,
        project_id="project-context",
        chapter_id="12",
        payload={"run_id": "chapter-longform-context-1"},
    )

    class SnapshotService:
        def __init__(self, _session):
            pass

        async def get_project_schema(self, _project_id, _user_id):
            return types.SimpleNamespace(
                blueprint=types.SimpleNamespace(
                    model_dump=lambda: {
                        "title": "星海长夜",
                        "world_setting": {"laws": ["潮汐灵脉"]},
                        "long_term_threads": ["主线谜团"],
                    }
                )
            )

    monkeypatch.setattr(writer, "NovelService", SnapshotService)
    runtime = await writer._register_longform_generation_plan(
        task_session,
        run_id=task.task_id,
        project_id="project-context",
        chapter_number=12,
        user_id=7,
        flow_config={"target_word_count": 20000, "min_word_count": 18000, "segment_word_limit": 4500},
        outline=types.SimpleNamespace(title="潮汐之门", summary="主角追查潮汐灵脉的异常"),
    )
    assert runtime is not None
    assert runtime["plan"]["book_context"]["title"] == "星海长夜"
    assert runtime["plan"]["book_context"]["long_term_threads"] == ["主线谜团"]
    assert runtime["plan"]["chapter_context"]["title"] == "潮汐之门"


@pytest.mark.asyncio
async def test_formal_chapter_entry_persists_longform_plan(task_session):
    task = await TaskRuntimeService(task_session).create_task(
        task_id="chapter-longform-1",
        task_type="chapter_generation",
        owner_user_id=7,
        project_id="project-long",
        chapter_id="12",
        payload={"run_id": "chapter-longform-1"},
    )
    runtime = await writer._register_longform_generation_plan(
        task_session,
        run_id=task.task_id,
        project_id="project-long",
        chapter_number=12,
        user_id=7,
        flow_config={"target_word_count": 20000, "min_word_count": 18000, "segment_word_limit": 4500},
    )
    assert runtime is not None
    assert runtime["segment_count"] == 5
    stored = await TaskRuntimeService(task_session).get_task(task.task_id, 7)
    assert stored.payload["segmentation_required"] is True
    assert stored.payload["longform_generation"]["checkpoint"]["next_segment_index"] == 0


@pytest.mark.asyncio
async def test_cancelled_background_generation_releases_busy_chapter(monkeypatch):
    """Provider 等待被取消时，章节必须从 generating 释放为可重试状态。"""
    events: list[dict] = []
    marked: list[dict] = []

    class FakeSession:
        async def execute(self, *_args, **_kwargs):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(first=lambda: None),
            )

        async def rollback(self):
            return None

    class FakeSessionContext:
        def __init__(self):
            self.session = FakeSession()

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *_args):
            return False

    class FakeOrchestrator:
        def __init__(self, _session):
            pass

        async def generate_chapter(self, **_kwargs):
            raise asyncio.CancelledError

    class FakeNovelService:
        def __init__(self, _session):
            pass

        async def get_or_create_chapter(self, project_id, chapter_number):
            return SimpleNamespace(
                id=11,
                project_id=project_id,
                chapter_number=chapter_number,
                status="generating",
                real_summary="",
                selected_version_id=None,
            )

    async def fake_append(_run_id, **kwargs):
        events.append(kwargs)

    async def fake_mark(_session, **kwargs):
        marked.append(kwargs)

    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(writer, "PipelineOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(writer, "NovelService", FakeNovelService)
    monkeypatch.setattr(writer, "_append_chapter_task_event", fake_append)
    monkeypatch.setattr(writer, "_mark_busy_chapter_failed", fake_mark)

    with pytest.raises(asyncio.CancelledError):
        await writer._generate_chapter_async(
            project_id="project-cancel",
            chapter_number=3,
            user_id=7,
            writing_notes=None,
            flow_config={},
            run_id="run-cancel",
        )

    assert marked and marked[0]["run_id"] == "run-cancel"
    assert "可重试" in marked[0]["reason"]
    assert events[-1]["status"] == writer.TaskRuntimeStatus.CANCELLED.value
    assert events[-1]["event_type"] == writer.TaskRuntimeEventType.TASK_CANCELLED.value
