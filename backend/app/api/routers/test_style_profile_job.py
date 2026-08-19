import asyncio
import io
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile
import pytest

from app.api.routers import style
from app.schemas.user import UserInDB
from app.schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus
from app.services.task_runtime import TaskRuntimeConflict, TaskRuntimeNotFound, TaskRuntimeService


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
    style._STYLE_SCHEDULED_RUNS.clear()
    for task in list(style._STYLE_TASKS.values()):
        if not task.done():
            task.cancel()
    style._STYLE_TASKS.clear()
    yield
    for task in list(style._STYLE_TASKS.values()):
        if not task.done():
            task.cancel()
    style._STYLE_TASKS.clear()
    style._STYLE_SCHEDULED_RUNS.clear()
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

@pytest.mark.asyncio
async def test_style_profile_status_rebuilds_from_task_runtime_after_restart(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-profile-restart"
    snapshot = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "profiling",
        "progress_stage": "profiling",
        "progress_message": "正在提炼叙事画像",
        "profile": {"id": "profile-1", "name": "冷峻叙事"},
        "error": None,
        "task_domain": "style_profile",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="style_profile_generation",
        owner_user_id=7,
        project_id="project-1",
        payload={"style_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="profiling",
        message="正在提炼叙事画像",
        payload={"task_domain": "style_profile", "style_job": snapshot},
        owner_user_id=7,
    )

    style._STYLE_PROFILE_JOBS.clear()
    style._STYLE_PROFILE_PROJECT_RUNS.clear()
    restored = await style.get_style_profile_generation_status(
        project_id="project-1",
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert restored.run_id == run_id
    assert restored.status == "profiling"
    assert restored.progress_message == "正在提炼叙事画像"
    assert restored.profile == {"id": "profile-1", "name": "冷峻叙事"}
    assert style._STYLE_PROFILE_PROJECT_RUNS["project-1"] == run_id


@pytest.mark.asyncio
async def test_style_source_upload_status_rebuilds_from_task_runtime_after_restart(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-upload-restart"
    snapshot = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "successful",
        "progress_stage": "successful",
        "progress_message": "文风素材导入完成",
        "filename": "reference.txt",
        "source": {"id": "source-1", "title": "参考文本"},
        "metrics": {"extracted_chars": 1200},
        "error": None,
        "task_domain": "style_source_upload",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="style_source_upload",
        owner_user_id=7,
        project_id="project-1",
        payload={"style_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
        status=TaskRuntimeStatus.SUCCEEDED.value,
        stage="successful",
        message="文风素材导入完成",
        payload={"task_domain": "style_source_upload", "style_job": snapshot},
        owner_user_id=7,
    )

    style._STYLE_SOURCE_UPLOAD_JOBS.clear()
    style._STYLE_SOURCE_UPLOAD_PROJECT_RUNS.clear()
    restored = await style.get_style_source_upload_status(
        project_id="project-1",
        run_id=run_id,
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert restored.run_id == run_id
    assert restored.status == "successful"
    assert restored.filename == "reference.txt"
    assert restored.source == {"id": "source-1", "title": "参考文本"}
    assert restored.metrics["extracted_chars"] == 1200
    assert style._STYLE_SOURCE_UPLOAD_PROJECT_RUNS["project-1"] == run_id


@pytest.mark.asyncio
async def test_style_source_upload_status_recovers_persisted_file_once_after_restart(
    task_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    storage_root = tmp_path / "style_uploads"
    monkeypatch.setattr(style, "_STYLE_UPLOAD_STORAGE_ROOT", storage_root)
    run_id = f"style-upload-queued-recovery-{uuid.uuid4().hex}"
    storage_path = storage_root / "project-1" / f"{run_id}.bin"
    storage_path.parent.mkdir(parents=True)
    storage_path.write_bytes("恢复用的文风素材内容。".encode("utf-8"))
    snapshot = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "queued",
        "progress_stage": "queued",
        "progress_message": "文风素材导入任务已入队",
        "filename": "reference.txt",
        "metrics": {"uploaded_bytes": storage_path.stat().st_size},
        "task_domain": "style_source_upload",
    }
    await TaskRuntimeService(task_session).create_task(
        task_id=run_id,
        task_type="style_source_upload",
        owner_user_id=7,
        project_id="project-1",
        payload={
            "storage_path": str(storage_path),
            "filename": "reference.txt",
            "title": "恢复素材",
            "source_type": "external_text",
            "parsed_extra": {"import_mode": "restart"},
            "style_job": snapshot,
        },
    )

    scheduled = []

    class _CapturedTask:
        def done(self):
            return False

        def cancel(self):
            return True

    def capture_task(coro):
        scheduled.append(coro)
        return _CapturedTask()

    monkeypatch.setattr(style.asyncio, "create_task", capture_task)
    user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    style._STYLE_SOURCE_UPLOAD_JOBS.clear()
    style._STYLE_SOURCE_UPLOAD_PROJECT_RUNS.clear()
    style._STYLE_SCHEDULED_RUNS.clear()

    first = await style.get_style_source_upload_status(
        project_id="project-1", run_id=run_id, current_user=user, session=task_session
    )
    second = await style.get_style_source_upload_status(
        project_id="project-1", run_id=run_id, current_user=user, session=task_session
    )

    assert first.status == "queued"
    assert second.status == "queued"
    assert len(scheduled) == 1
    assert style._STYLE_SCHEDULED_RUNS == {run_id}
    scheduled[0].close()


@pytest.mark.asyncio
async def test_style_source_upload_recovery_rejects_external_or_cross_project_path(
    task_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    storage_root = tmp_path / "style_uploads"
    monkeypatch.setattr(style, "_STYLE_UPLOAD_STORAGE_ROOT", storage_root)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"must not be read")
    run_id = f"style-upload-path-guard-{uuid.uuid4().hex}"
    user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    scheduled = []

    class _CapturedTask:
        def done(self):
            return False

        def cancel(self):
            return True

    def capture_task(coro):
        scheduled.append(coro)
        return _CapturedTask()

    monkeypatch.setattr(style.asyncio, "create_task", capture_task)
    bad_paths = (str(outside), str(storage_root / "other-project" / f"{run_id}.bin"),
                 str(storage_root / "project-1" / ".." / "outside.bin"))
    for index, bad_path in enumerate(bad_paths):
        bad_run_id = f"{run_id}-{index}"
        await TaskRuntimeService(task_session).create_task(
            task_id=bad_run_id,
            task_type="style_source_upload",
            owner_user_id=7,
            project_id="project-1",
            payload={
                "storage_path": bad_path,
                "filename": "reference.txt",
                "style_job": {
                    "run_id": bad_run_id, "project_id": "project-1",
                    "user_id": 7, "status": "queued", "progress_stage": "queued",
                    "task_domain": "style_source_upload",
                },
            },
        )

    for index in range(3):
        await style.get_style_source_upload_status(
            project_id="project-1", run_id=f"{run_id}-{index}", current_user=user,
            session=task_session,
        )
    assert scheduled == []


@pytest.mark.asyncio
async def test_style_profile_cancel_recovers_persisted_runtime_after_restart(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = f"style-profile-cancel-restart-{uuid.uuid4().hex}"
    snapshot = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "profiling",
        "progress_stage": "profiling",
        "progress_message": "正在提炼叙事画像",
        "task_domain": "style_profile",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="style_profile_generation",
        owner_user_id=7,
        project_id="project-1",
        payload={"request": {"source_ids": ["src-1"], "name": "恢复画像"}, "style_job": snapshot},
    )
    await runtime.claim(run_id, lease_owner="test-style-profile-live", owner_user_id=7)
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="profiling",
        message="正在提炼叙事画像",
        payload={"task_domain": "style_profile", "style_job": snapshot},
        owner_user_id=7,
    )

    style._STYLE_PROFILE_JOBS.clear()
    style._STYLE_PROFILE_PROJECT_RUNS.clear()
    result = await style.cancel_style_profile_generation(
        project_id="project-1",
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert result.run_id == run_id
    assert result.status == "cancelling"
    refreshed = await runtime.get_task(run_id, 7)
    assert refreshed.status == TaskRuntimeStatus.CANCELLING.value


@pytest.mark.asyncio
async def test_style_source_upload_cancel_recovers_persisted_runtime_after_restart(task_session, monkeypatch, tmp_path):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    storage_root = tmp_path / "style_uploads"
    monkeypatch.setattr(style, "_STYLE_UPLOAD_STORAGE_ROOT", storage_root)
    run_id = f"style-upload-cancel-restart-{uuid.uuid4().hex}"
    storage_path = storage_root / "project-1" / f"{run_id}.bin"
    storage_path.parent.mkdir(parents=True)
    storage_path.write_bytes("恢复取消测试素材内容。".encode("utf-8"))
    snapshot = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "upload_extracting",
        "progress_stage": "upload_extracting",
        "progress_message": "正在解析素材",
        "filename": "reference.txt",
        "task_domain": "style_source_upload",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="style_source_upload",
        owner_user_id=7,
        project_id="project-1",
        payload={
            "storage_path": str(storage_path),
            "filename": "reference.txt",
            "title": "恢复素材",
            "source_type": "external_text",
            "style_job": snapshot,
        },
    )
    await runtime.claim(run_id, lease_owner="test-style-upload-live", owner_user_id=7)
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="upload_extracting",
        message="正在解析素材",
        payload={"task_domain": "style_source_upload", "style_job": snapshot},
        owner_user_id=7,
    )

    style._STYLE_SOURCE_UPLOAD_JOBS.clear()
    style._STYLE_SOURCE_UPLOAD_PROJECT_RUNS.clear()
    result = await style.cancel_style_source_upload(
        project_id="project-1",
        run_id=run_id,
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert result.run_id == run_id
    assert result.status == "cancelling"
    refreshed = await runtime.get_task(run_id, 7)
    assert refreshed.status == TaskRuntimeStatus.CANCELLING.value


@pytest.mark.asyncio
async def test_style_profile_start_uses_runtime_not_stale_memory(task_session, monkeypatch):
    """持久化终态必须释放槽位，旧内存 profiling 快照不得阻止新任务。"""
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    old_run_id = "style-profile-memory-stale"
    await TaskRuntimeService(task_session).create_task(
        task_id=old_run_id,
        task_type="style_profile_generation",
        owner_user_id=7,
        project_id="project-1",
        payload={"style_job": {
            "run_id": old_run_id, "project_id": "project-1", "user_id": 7,
            "status": "profiling", "progress_stage": "profiling", "task_domain": "style_profile",
        }},
    )
    await TaskRuntimeService(task_session).append_event(
        old_run_id,
        event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
        status=TaskRuntimeStatus.SUCCEEDED.value,
        owner_user_id=7,
    )
    style._STYLE_PROFILE_JOBS[old_run_id] = {
        "run_id": old_run_id, "project_id": "project-1", "user_id": 7,
        "status": "profiling", "progress_stage": "profiling",
    }
    style._STYLE_PROFILE_PROJECT_RUNS["project-1"] = old_run_id
    background = BackgroundTasks()

    started = await style.start_style_profile_generation(
        project_id="project-1",
        request=style.CreateStyleProfileRequest(source_ids=["src-new"]),
        background_tasks=background,
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert started.run_id != old_run_id
    assert started.status == "queued"
    assert len(background.tasks) == 1


@pytest.mark.asyncio
async def test_style_profile_start_reuses_persisted_active_runtime_after_restart(task_session, monkeypatch):
    """重启后无内存缓存时，第二次启动不得重复创建同项目文风任务。"""
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-profile-active-restart"
    await TaskRuntimeService(task_session).create_task(
        task_id=run_id,
        task_type="style_profile_generation",
        owner_user_id=7,
        project_id="project-1",
        payload={
            "request": {"source_ids": ["src-1"]},
            "style_job": {
                "run_id": run_id, "project_id": "project-1", "user_id": 7,
                "status": "profiling", "progress_stage": "profiling", "task_domain": "style_profile",
            },
        },
    )
    await TaskRuntimeService(task_session).append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="profiling",
        owner_user_id=7,
    )
    background = BackgroundTasks()

    started = await style.start_style_profile_generation(
        project_id="project-1",
        request=style.CreateStyleProfileRequest(source_ids=["src-2"]),
        background_tasks=background,
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert started.run_id == run_id
    assert started.status == "profiling"
    assert background.tasks == []


@pytest.mark.asyncio
async def test_style_profile_queued_cancel_finalizes_unclaimed_runtime(task_session, monkeypatch):
    """未领取的文风任务取消后必须终态化，避免 SSE 永久停在 cancelling。"""
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-profile-queued-cancel"
    await TaskRuntimeService(task_session).create_task(
        task_id=run_id,
        task_type="style_profile_generation",
        owner_user_id=7,
        project_id="project-1",
        payload={"style_job": {
            "run_id": run_id, "project_id": "project-1", "user_id": 7,
            "status": "queued", "progress_stage": "queued", "task_domain": "style_profile",
        }},
    )

    result = await style.cancel_style_profile_generation(
        project_id="project-1",
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert result.status == "cancelled"
    assert (await TaskRuntimeService(task_session).get_task(run_id, 7)).status == TaskRuntimeStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_style_source_cancel_rejects_cross_project_runtime(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-source-cross-project"
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="style_source_upload",
        owner_user_id=7,
        project_id="project-2",
        payload={"style_job": {"run_id": run_id, "project_id": "project-2", "status": "queued"}},
    )

    with pytest.raises(Exception) as exc_info:
        await style.cancel_style_source_upload(
            project_id="project-1",
            run_id=run_id,
            current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
            session=task_session,
        )

    assert getattr(exc_info.value, "status_code", None) == 404
    assert (await runtime.get_task(run_id, 7)).status == TaskRuntimeStatus.QUEUED.value


@pytest.mark.asyncio
async def test_style_profile_cancel_ignores_same_project_other_task_type(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-source-not-profile"
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="style_source_upload",
        owner_user_id=7,
        project_id="project-1",
        payload={"style_job": {"run_id": run_id, "project_id": "project-1", "status": "queued"}},
    )

    result = await style.cancel_style_profile_generation(
        project_id="project-1",
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert result.status == "idle"
    assert (await runtime.get_task(run_id, 7)).status == TaskRuntimeStatus.QUEUED.value


@pytest.mark.asyncio
async def test_style_status_does_not_fallback_to_memory_after_runtime_missing(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-profile-runtime-missing"
    style._STYLE_PROFILE_JOBS[run_id] = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "profiling",
        "progress_stage": "profiling",
        "progress_message": "旧进程快照",
    }
    style._STYLE_PROFILE_PROJECT_RUNS["project-1"] = run_id

    result = await style.get_style_profile_generation_status(
        project_id="project-1",
        current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
        session=task_session,
    )

    assert result.status == "idle"
    assert result.run_id == ""


@pytest.mark.asyncio
async def test_style_runtime_cancelled_raises_when_runtime_disappears(monkeypatch):
    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            return None

    class _DbContext:
        async def __aenter__(self):
            return _DbSession()

        async def __aexit__(self, *_args):
            return False

    calls = 0

    class _Runtime:
        def __init__(self, _session):
            pass

        async def get_task(self, _run_id, _user_id):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise TaskRuntimeNotFound("deleted after claim")
            return type("T", (), {
                "project_id": "project-1",
                "task_type": "style_profile_generation",
                "status": TaskRuntimeStatus.RUNNING.value,
            })()

    monkeypatch.setattr(style, "AsyncSessionLocal", _DbContext)
    monkeypatch.setattr(style, "TaskRuntimeService", _Runtime)

    assert await style._style_runtime_cancelled(
        "style-runtime-delete", "project-1", 7, "style_profile"
    ) is False
    with pytest.raises(style._StyleRuntimeDetached):
        await style._style_runtime_cancelled(
            "style-runtime-delete", "project-1", 7, "style_profile"
        )


@pytest.mark.asyncio
async def test_style_profile_worker_stops_before_provider_when_runtime_detached(monkeypatch):
    monkeypatch.setattr(style, "_claim_style_runtime", lambda *args: _async_value(True))
    monkeypatch.setattr(
        style,
        "_style_worker_checkpoint",
        lambda *args: _async_raise(style._StyleRuntimeDetached("runtime deleted")),
    )
    monkeypatch.setattr(style, "_compensate_style_profile", _async_noop)
    detached = []
    monkeypatch.setattr(style, "_mark_style_worker_detached", lambda *args: _async_record(detached, args))
    provider_calls = []

    class _NeverProvider:
        def __init__(self, *_args):
            provider_calls.append("init")

    monkeypatch.setattr(style, "StyleRAGService", _NeverProvider)
    style._STYLE_PROFILE_JOBS["style-detached-before-provider"] = {
        "run_id": "style-detached-before-provider",
        "project_id": "project-1",
        "user_id": 7,
        "status": "queued",
        "progress_stage": "queued",
    }

    await style._run_style_profile_job(
        "style-detached-before-provider", "project-1", 7, {"source_ids": ["src-1"]}
    )

    assert provider_calls == []
    assert detached


@pytest.mark.asyncio
async def test_style_profile_heartbeat_cancels_parent_worker(monkeypatch):
    run_id = "style-heartbeat-parent-cancel"
    started = asyncio.Event()
    heartbeat_seen = asyncio.Event()
    monkeypatch.setattr(style, "_claim_style_runtime", lambda *args: _async_value(True))
    monkeypatch.setattr(style, "_style_worker_checkpoint", _async_noop)
    monkeypatch.setattr(style, "_STYLE_PROFILE_HEARTBEAT_SECONDS", 0)

    async def detached_heartbeat(*_args):
        heartbeat_seen.set()
        raise style._StyleRuntimeDetached("lease lost")

    monkeypatch.setattr(style, "_style_runtime_heartbeat", detached_heartbeat)
    monkeypatch.setattr(style, "_compensate_style_profile", _async_noop)
    monkeypatch.setattr(style, "_mark_style_worker_detached", _async_noop)

    class _DbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return False

    class _SlowStyleService:
        def __init__(self, *_args):
            pass

        async def list_style_profiles(self, _user_id):
            return []

        async def create_profile_from_sources(self, *_args, **_kwargs):
            started.set()
            await asyncio.sleep(60)

    monkeypatch.setattr(style, "AsyncSessionLocal", _DbContext)
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    monkeypatch.setattr(style, "StyleRAGService", _SlowStyleService)
    style._STYLE_PROFILE_JOBS[run_id] = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "queued",
        "progress_stage": "queued",
        "runtime_task_registered": False,
    }

    task = asyncio.create_task(
        style._run_style_profile_job(run_id, "project-1", 7, {"source_ids": ["src-1"]})
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    await asyncio.wait_for(heartbeat_seen.wait(), timeout=2)
    await asyncio.wait_for(task, timeout=2)
    assert task.done()
    assert not task.cancelled()


@pytest.mark.asyncio
async def test_style_profile_cancel_persistence_conflict_does_not_fake_cancel(task_session, monkeypatch):
    monkeypatch.setattr(style, "NovelService", _FakeNovelService)
    run_id = "style-cancel-persist-conflict"
    runtime = TaskRuntimeService(task_session)
    snapshot = {
        "run_id": run_id,
        "project_id": "project-1",
        "user_id": 7,
        "status": "profiling",
        "progress_stage": "profiling",
        "progress_message": "正在生成",
        "task_domain": "style_profile",
    }
    await runtime.create_task(
        task_id=run_id,
        task_type="style_profile_generation",
        owner_user_id=7,
        project_id="project-1",
        payload={"style_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="profiling",
        owner_user_id=7,
        payload={"task_domain": "style_profile", "style_job": snapshot},
    )
    monkeypatch.setattr(
        style,
        "_request_style_runtime_cancel",
        lambda *args, **kwargs: _async_raise(TaskRuntimeConflict("lease changed")),
    )

    with pytest.raises(Exception) as exc_info:
        await style.cancel_style_profile_generation(
            project_id="project-1",
            current_user=UserInDB(id=7, username="tester", email=None, hashed_password="x"),
            session=task_session,
        )

    assert getattr(exc_info.value, "status_code", None) == 409
    assert style._STYLE_PROFILE_JOBS[run_id]["status"] == "profiling"


async def _async_value(value):
    return value


async def _async_raise(exc):
    raise exc


async def _async_noop(*_args, **_kwargs):
    return None


async def _async_record(target, value):
    target.append(value)
