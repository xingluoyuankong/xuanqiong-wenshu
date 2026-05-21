from fastapi import BackgroundTasks
import pytest

from app.api.routers import writer
from app.schemas.novel import GenerateOutlineRequest, RewriteChapterOutlineRequest
from app.schemas.user import UserInDB


class _FakeNovelService:
    def __init__(self, session):
        self.session = session

    async def ensure_project_owner(self, project_id, user_id):
        return object()


@pytest.fixture(autouse=True)
def clear_outline_jobs():
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()
    yield
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()


@pytest.mark.asyncio
async def test_outline_generation_job_has_start_status_and_cancel(monkeypatch):
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    request = GenerateOutlineRequest(start_chapter=2, num_chapters=4, target_total_chapters=80)
    background_tasks = BackgroundTasks()

    started = await writer.start_chapters_outline_generation(
        project_id="project-1",
        request=request,
        background_tasks=background_tasks,
        session=object(),
        current_user=current_user,
    )

    assert started.status == "queued"
    assert started.progress_stage == "queued"
    assert len(background_tasks.tasks) == 1

    running = await writer.get_chapters_outline_generation_status(
        project_id="project-1",
        session=object(),
        current_user=current_user,
    )
    assert running.run_id == started.run_id
    assert running.status == "queued"

    cancelled = await writer.cancel_chapters_outline_generation(
        project_id="project-1",
        session=object(),
        current_user=current_user,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.error is not None
    assert cancelled.error.code == "outline_generation_cancelled"


@pytest.mark.asyncio
async def test_outline_rewrite_job_has_start_status_and_cancel(monkeypatch):
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    request = RewriteChapterOutlineRequest(chapter_number=3, title="旧标题", summary="旧摘要", direction="加强冲突")
    background_tasks = BackgroundTasks()

    started = await writer.start_chapter_outline_rewrite(
        project_id="project-1",
        request=request,
        background_tasks=background_tasks,
        session=object(),
        current_user=current_user,
    )

    assert started.status == "queued"
    assert started.progress_stage == "queued"
    assert len(background_tasks.tasks) == 1

    running = await writer.get_chapter_outline_rewrite_status(
        project_id="project-1",
        session=object(),
        current_user=current_user,
    )
    assert running.run_id == started.run_id
    assert running.status == "queued"

    cancelled = await writer.cancel_chapter_outline_rewrite(
        project_id="project-1",
        session=object(),
        current_user=current_user,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.error is not None
    assert cancelled.error.code == "outline_generation_cancelled"

    overwritten = await writer._set_outline_job_state(
        started.run_id,
        status="outline_rewrite",
        progress_stage="outline_rewrite",
        progress_message="后台任务稍后启动",
    )
    assert overwritten["status"] == "cancelled"
