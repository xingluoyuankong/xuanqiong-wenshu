from io import BytesIO

from fastapi import BackgroundTasks, UploadFile
import pytest

from app.api.routers import novels
from app.schemas.user import UserInDB


@pytest.fixture(autouse=True)
def clear_import_jobs():
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()
    yield
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()


@pytest.mark.asyncio
async def test_import_job_has_start_status_and_cancel():
    current_user = UserInDB(id=9, username="importer", email=None, hashed_password="x")
    upload = UploadFile(filename="old.txt", file=BytesIO("第一章 旧稿\n主角推门而入。".encode("utf-8")))
    background_tasks = BackgroundTasks()

    started = await novels.start_import_novel(
        background_tasks=background_tasks,
        file=upload,
        current_user=current_user,
    )

    assert started.status == "queued"
    assert started.progress_stage == "queued"
    assert started.filename == "old.txt"
    assert started.metrics["bytes"] > 0
    assert len(background_tasks.tasks) == 1

    running = await novels.get_import_novel_status(
        run_id=started.run_id,
        current_user=current_user,
    )
    assert running.run_id == started.run_id
    assert running.status == "queued"

    cancelled = await novels.cancel_import_novel(
        run_id=started.run_id,
        current_user=current_user,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.error is not None
    assert cancelled.error.code == "import_cancelled"

    overwritten = await novels._set_import_job_state(
        started.run_id,
        status="import_reading",
        progress_stage="import_reading",
        progress_message="后台任务稍后启动",
    )
    assert overwritten["status"] == "cancelled"
