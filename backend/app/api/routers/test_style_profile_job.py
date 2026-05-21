import io

from fastapi import BackgroundTasks, UploadFile
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
    style._STYLE_SOURCE_UPLOAD_JOBS.clear()
    style._STYLE_SOURCE_UPLOAD_PROJECT_RUNS.clear()
    yield
    style._STYLE_PROFILE_JOBS.clear()
    style._STYLE_PROFILE_PROJECT_RUNS.clear()
    style._STYLE_SOURCE_UPLOAD_JOBS.clear()
    style._STYLE_SOURCE_UPLOAD_PROJECT_RUNS.clear()


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


@pytest.mark.asyncio
async def test_style_source_upload_job_has_start_status_and_cancel(monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    background_tasks = BackgroundTasks()
    upload = UploadFile(
        filename="style-sample.txt",
        file=io.BytesIO("这一段文风素材足够长，用于测试后台上传任务。".encode("utf-8")),
    )

    started = await style.start_style_source_upload(
        project_id="project-1",
        background_tasks=background_tasks,
        file=upload,
        title="冷峻参考",
        source_type="external_text",
        extra='{"import_mode":"file_stub"}',
        current_user=current_user,
        session=object(),
    )

    assert started.status == "queued"
    assert started.progress_stage == "queued"
    assert started.filename == "style-sample.txt"
    assert started.metrics["uploaded_bytes"] > 0
    assert len(background_tasks.tasks) == 1

    running = await style.get_style_source_upload_status(
        project_id="project-1",
        run_id=started.run_id,
        current_user=current_user,
        session=object(),
    )
    assert running.run_id == started.run_id
    assert running.status == "queued"

    cancelled = await style.cancel_style_source_upload(
        project_id="project-1",
        run_id=started.run_id,
        current_user=current_user,
        session=object(),
    )
    assert cancelled.status == "cancelled"
    assert cancelled.error is not None
    assert cancelled.error.code == "style_source_upload_cancelled"

    overwritten = await style._set_style_source_upload_job_state(
        started.run_id,
        status="upload_extracting",
        progress_stage="upload_extracting",
        progress_message="后台任务稍后启动",
    )
    assert overwritten["status"] == "cancelled"


@pytest.mark.asyncio
async def test_style_source_upload_cancel_does_not_abort_saving(monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    run_id = "style-upload-saving"
    style._STYLE_SOURCE_UPLOAD_JOBS[run_id] = {
        "run_id": run_id,
        "project_id": "project-1",
        "status": "upload_saving",
        "progress_stage": "upload_saving",
        "progress_message": "正在保存",
    }

    cancelled = await style.cancel_style_source_upload(
        project_id="project-1",
        run_id=run_id,
        current_user=current_user,
        session=object(),
    )

    assert cancelled.status == "upload_saving"
    assert "无法安全取消" in cancelled.progress_message
