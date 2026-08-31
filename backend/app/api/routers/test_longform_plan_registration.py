from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.routers import writer as writer_router


@pytest.mark.asyncio
async def test_longform_plan_registration_rejects_persistence_failure(monkeypatch):
    """计划落库失败不得静默降级为不可恢复的正文任务。"""
    session = SimpleNamespace(execute=AsyncMock())

    class FailingNovelService:
        def __init__(self, _session):
            pass

        async def get_project_schema(self, _project_id, _user_id):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(writer_router, "NovelService", FailingNovelService)

    class FailingRuntimeService:
        def __init__(self, _session):
            pass

        async def merge_payload(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(writer_router, "TaskRuntimeService", FailingRuntimeService)

    with pytest.raises(HTTPException) as caught:
        await writer_router._register_longform_generation_plan(
            session,
            run_id="run-plan-failure",
            project_id="project-plan-failure",
            chapter_number=1,
            user_id=7,
            flow_config={
                "target_word_count": 20000,
                "min_word_count": 18000,
                "segment_word_limit": 4500,
            },
        )

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "LONGFORM_PLAN_PERSISTENCE_FAILED"
    assert caught.value.detail["retryable"] is True


@pytest.mark.asyncio
async def test_longform_plan_registration_failure_closes_claimed_task(monkeypatch):
    """计划登记失败时，正式入口必须释放章节占用并写任务失败事件。"""
    session = SimpleNamespace(execute=AsyncMock(), rollback=AsyncMock())
    chapter = SimpleNamespace(
        id=11,
        project_id="project-plan-failure",
        chapter_number=1,
        status=writer_router.ChapterGenerationStatus.GENERATING.value,
        real_summary=None,
        selected_version_id=None,
    )

    mark_failed = AsyncMock()
    append_event = AsyncMock()
    monkeypatch.setattr(writer_router, "_mark_busy_chapter_failed", mark_failed)

    class FailingRuntimeService:
        def __init__(self, _session):
            pass

        async def merge_payload(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

        async def append_event(self, *_args, **_kwargs):
            await append_event(*_args, **_kwargs)

    monkeypatch.setattr(writer_router, "TaskRuntimeService", FailingRuntimeService)
    monkeypatch.setattr(
        writer_router,
        "_register_longform_generation_plan",
        AsyncMock(
            side_effect=HTTPException(
                status_code=503,
                detail={
                    "code": "LONGFORM_PLAN_PERSISTENCE_FAILED",
                    "message": "长篇分段计划保存失败，任务未启动。",
                    "retryable": True,
                },
            )
        ),
    )

    await writer_router._close_claimed_chapter_after_startup_failure(
        session,
        chapter=chapter,
        run_id="run-plan-failure",
        project_id="project-plan-failure",
        chapter_number=1,
        user_id=7,
        error=HTTPException(
            status_code=503,
            detail={
                "code": "LONGFORM_PLAN_PERSISTENCE_FAILED",
                "message": "长篇分段计划保存失败，任务未启动。",
                "retryable": True,
            },
        ),
    )
    mark_failed.assert_awaited_once()
    append_event.assert_awaited_once()
    assert mark_failed.await_args.kwargs["reason"] == "长篇分段计划保存失败，任务未启动。"
    assert append_event.await_args.kwargs["payload"]["error_code"] == "LONGFORM_PLAN_PERSISTENCE_FAILED"
    assert append_event.await_args.kwargs["payload"]["retryable"] is True
