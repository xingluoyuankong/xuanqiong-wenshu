from fastapi import BackgroundTasks
import pytest

from app.api.routers import style
from app.schemas.user import UserInDB


class _FakeNovelService:
    def __init__(self, session):
        self.session = session

    async def ensure_project_owner(self, project_id, user_id):
        return object()


@pytest.fixture(autouse=True)
def clear_style_profile_jobs():
    style._STYLE_PROFILE_JOBS.clear()
    style._STYLE_PROFILE_PROJECT_RUNS.clear()
    yield
    style._STYLE_PROFILE_JOBS.clear()
    style._STYLE_PROFILE_PROJECT_RUNS.clear()


@pytest.mark.asyncio
async def test_style_profile_job_has_start_status_and_cancel(monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    request = style.CreateStyleProfileRequest(source_ids=["src-1"], name="冷峻叙事")
    background_tasks = BackgroundTasks()

    started = await style.start_style_profile_generation(
        project_id="project-1",
        request=request,
        background_tasks=background_tasks,
        current_user=current_user,
        session=object(),
    )

    assert started.status == "queued"
    assert started.progress_stage == "queued"
    assert len(background_tasks.tasks) == 1

    running = await style.get_style_profile_generation_status(
        project_id="project-1",
        current_user=current_user,
        session=object(),
    )
    assert running.run_id == started.run_id
    assert running.status == "queued"

    cancelled = await style.cancel_style_profile_generation(
        project_id="project-1",
        current_user=current_user,
        session=object(),
    )
    assert cancelled.status == "cancelled"
    assert cancelled.error is not None
    assert cancelled.error.code == "style_profile_generation_cancelled"

    overwritten = await style._set_style_profile_job_state(
        started.run_id,
        status="extracting",
        progress_stage="extracting",
        progress_message="后台任务稍后启动",
    )
    assert overwritten["status"] == "cancelled"
