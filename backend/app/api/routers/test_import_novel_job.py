import asyncio
from io import BytesIO
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile
import pytest

from app.api.routers import novels
from app.schemas.user import UserInDB
from app.schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus
from app.services.task_runtime import TaskRuntimeService


@pytest.fixture(autouse=True)
def clear_import_jobs():
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()
    novels._IMPORT_SCHEDULED_RUNS.clear()
    yield
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()
    novels._IMPORT_SCHEDULED_RUNS.clear()


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


@pytest.mark.asyncio
async def test_import_cancel_does_not_abort_ledger_rebuild():
    current_user = UserInDB(id=9, username="importer", email=None, hashed_password="x")
    run_id = "import-ledger"
    novels._IMPORT_JOBS[run_id] = {
        "run_id": run_id,
        "user_id": current_user.id,
        "status": "import_ledger_rebuild",
        "progress_stage": "import_ledger_rebuild",
        "progress_message": "正在重建账本",
    }

    cancelled = await novels.cancel_import_novel(
        run_id=run_id,
        current_user=current_user,
    )

    assert cancelled.status == "import_ledger_rebuild"
    assert cancelled.progress_stage == "import_ledger_rebuild"


@pytest.mark.asyncio
async def test_import_start_persists_legacy_job_snapshot(task_session):
    current_user = UserInDB(id=9, username="importer", email=None, hashed_password="x")
    upload = UploadFile(
        filename="restartable.txt",
        file=BytesIO("第一章 旧稿\n主角推门而入。".encode("utf-8")),
    )
    background_tasks = BackgroundTasks()

    started = await novels.start_import_novel(
        background_tasks=background_tasks,
        file=upload,
        session=task_session,
        current_user=current_user,
    )

    task = await TaskRuntimeService(task_session).get_task(started.run_id, owner_user_id=9)
    snapshot = (task.payload or {}).get("legacy_job")
    assert task.task_type == "novel_import"
    assert snapshot["run_id"] == started.run_id
    assert snapshot["status"] == "queued"
    assert snapshot["filename"] == "restartable.txt"
    assert snapshot["task_domain"] == "novel_import"
    storage_path = Path(snapshot["storage_path"])
    assert storage_path == novels._import_storage_path(9, started.run_id)
    assert storage_path.read_bytes() == "第一章 旧稿\n主角推门而入。".encode("utf-8")


@pytest.mark.asyncio
async def test_import_status_rebuilds_from_task_runtime_after_restart(task_session):
    run_id = "import-restart"
    snapshot = {
        "run_id": run_id,
        "user_id": 9,
        "status": "import_splitting",
        "progress_stage": "import_splitting",
        "progress_message": "正在拆分章节",
        "started_at": "2026-08-11T00:00:00+00:00",
        "updated_at": "2026-08-11T00:00:05+00:00",
        "filename": "restartable.txt",
        "project_id": None,
        "metrics": {"bytes": 42, "chapters": 3},
        "error": None,
        "task_domain": "novel_import",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="novel_import",
        idempotency_key=f"novel-import:{run_id}",
        owner_user_id=9,
        payload={"legacy_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="import_splitting",
        message="正在拆分章节",
        payload={"task_domain": "novel_import", "legacy_job": snapshot},
        owner_user_id=9,
    )

    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()
    restored = await novels.get_import_novel_status(
        current_user=UserInDB(id=9, username="importer", email=None, hashed_password="x"),
        session=task_session,
    )

    assert restored.run_id == run_id
    assert restored.status == "import_splitting"
    assert restored.progress_stage == "import_splitting"
    assert restored.progress_message == "正在拆分章节"
    assert restored.filename == "restartable.txt"
    assert restored.metrics == {"bytes": 42, "chapters": 3}
    assert novels._IMPORT_USER_RUNS[9] == run_id


@pytest.mark.asyncio
async def test_import_cancel_uses_persisted_state_after_restart(task_session):
    run_id = "import-persisted-cancel"
    snapshot = {
        "run_id": run_id,
        "user_id": 9,
        "status": "import_reading",
        "progress_stage": "import_reading",
        "progress_message": "正在读取旧稿文件",
        "filename": "cancel-me.txt",
        "metrics": {"bytes": 12},
        "error": None,
        "task_domain": "novel_import",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="novel_import",
        idempotency_key=f"novel-import:{run_id}",
        owner_user_id=9,
        payload={"legacy_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="import_reading",
        message="正在读取旧稿文件",
        payload={"task_domain": "novel_import", "legacy_job": snapshot},
        owner_user_id=9,
    )
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()

    cancelled = await novels.cancel_import_novel(
        run_id=run_id,
        current_user=UserInDB(id=9, username="importer", email=None, hashed_password="x"),
        session=task_session,
    )

    assert cancelled.run_id == run_id
    assert cancelled.status == "cancelled"
    assert cancelled.error is not None
    persisted = await runtime.get_task(run_id, owner_user_id=9)
    assert persisted.status == TaskRuntimeStatus.CANCELLED.value
    assert (persisted.payload or {}).get("legacy_job", {}).get("status") == "cancelled"


@pytest.mark.asyncio
async def test_import_status_does_not_restore_other_task_type(task_session):
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id="not-an-import",
        task_type="research",
        owner_user_id=9,
        payload={"legacy_job": {"run_id": "not-an-import", "status": "running"}},
    )

    restored = await novels.get_import_novel_status(
        current_user=UserInDB(id=9, username="importer", email=None, hashed_password="x"),
        session=task_session,
    )

    assert restored.status == "idle"
    assert restored.run_id == ""


@pytest.mark.asyncio
async def test_import_start_reuses_persisted_active_task_after_process_restart(task_session):
    run_id = "import-restart-no-duplicate"
    snapshot = {
        "run_id": run_id,
        "user_id": 9,
        "status": "import_splitting",
        "progress_stage": "import_splitting",
        "progress_message": "正在拆分章节",
        "filename": "restartable.txt",
        "metrics": {"bytes": 42},
        "error": None,
        "task_domain": "novel_import",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="novel_import",
        idempotency_key=f"novel-import:{run_id}",
        owner_user_id=9,
        payload={"legacy_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="import_splitting",
        message="正在拆分章节",
        payload={"task_domain": "novel_import", "legacy_job": snapshot},
        owner_user_id=9,
    )
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()

    background_tasks = BackgroundTasks()
    started = await novels.start_import_novel(
        background_tasks=background_tasks,
        file=UploadFile(filename="new.txt", file=BytesIO(b"new content")),
        session=task_session,
        current_user=UserInDB(id=9, username="importer", email=None, hashed_password="x"),
    )

    assert started.run_id == run_id
    assert started.status == "import_splitting"
    assert started.filename == "restartable.txt"
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_import_status_and_cancel_do_not_cross_user_boundary(task_session):
    run_id = "import-owner-boundary"
    snapshot = {
        "run_id": run_id,
        "user_id": 9,
        "status": "import_reading",
        "progress_stage": "import_reading",
        "progress_message": "正在读取旧稿文件",
        "filename": "private.txt",
        "task_domain": "novel_import",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id=run_id,
        task_type="novel_import",
        idempotency_key=f"novel-import:{run_id}",
        owner_user_id=9,
        payload={"legacy_job": snapshot},
    )

    other_user = UserInDB(id=10, username="other", email=None, hashed_password="x")
    status_result = await novels.get_import_novel_status(
        run_id=run_id,
        current_user=other_user,
        session=task_session,
    )
    cancel_result = await novels.cancel_import_novel(
        run_id=run_id,
        current_user=other_user,
        session=task_session,
    )

    assert status_result.status == "idle"
    assert status_result.run_id == run_id
    assert cancel_result.status == "idle"
    assert (await runtime.get_task(run_id, owner_user_id=9)).status == TaskRuntimeStatus.QUEUED.value
    assert await novels._is_import_job_cancelled(run_id, user_id=10) is False


@pytest.mark.asyncio
async def test_import_stale_runtime_is_visible_and_not_duplicated(task_session):
    run_id = "import-stale-after-restart"
    snapshot = {
        "run_id": run_id,
        "user_id": 9,
        "status": "import_reading",
        "progress_stage": "import_reading",
        "progress_message": "进程重启前正在读取",
        "filename": "stale.txt",
        "task_domain": "novel_import",
    }
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_id=run_id,
        task_type="novel_import",
        idempotency_key=f"novel-import:{run_id}",
        owner_user_id=9,
        payload={"legacy_job": snapshot},
    )
    await runtime.append_event(
        run_id,
        event_type=TaskRuntimeEventType.TASK_STALE.value,
        status=TaskRuntimeStatus.STALE.value,
        stage="import_reading",
        message="heartbeat timeout",
        payload={"task_domain": "novel_import", "legacy_job": snapshot},
        owner_user_id=9,
    )
    assert task.task_id == run_id
    novels._IMPORT_JOBS.clear()
    novels._IMPORT_USER_RUNS.clear()

    background_tasks = BackgroundTasks()
    restored = await novels.start_import_novel(
        background_tasks=background_tasks,
        file=UploadFile(filename="replacement.txt", file=BytesIO(b"replacement")),
        session=task_session,
        current_user=UserInDB(id=9, username="importer", email=None, hashed_password="x"),
    )

    assert restored.run_id == run_id
    assert restored.status == "import_reading"
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_import_status_recovers_persisted_bytes_and_schedules_once(task_session, monkeypatch):
    run_id = "import-bytes-recovery"
    storage = novels._import_storage_path(9, run_id)
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_bytes(b"persisted novel")
    snapshot = {
        "run_id": run_id, "user_id": 9, "status": "queued",
        "progress_stage": "queued", "filename": "persisted.txt",
        "storage_path": str(storage), "task_domain": "novel_import",
    }
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(task_id=run_id, task_type="novel_import",
        owner_user_id=9, payload={"legacy_job": snapshot, "storage_path": str(storage), "filename": "persisted.txt"})
    scheduled = []
    async def fake_worker(*args, **kwargs):
        scheduled.append((args, kwargs))
    monkeypatch.setattr(novels, "_run_import_novel_job", fake_worker)
    novels._IMPORT_JOBS.clear(); novels._IMPORT_USER_RUNS.clear()
    user = UserInDB(id=9, username="importer", email=None, hashed_password="x")
    result = await novels.get_import_novel_status(run_id=run_id, current_user=user, session=task_session)
    await asyncio.sleep(0)
    assert result.status == "queued"
    assert len(scheduled) == 1
    assert scheduled[0][0][:3] == (run_id, 9, "persisted.txt")
    assert scheduled[0][1]["storage_path"] == str(storage.resolve())
    await novels.get_import_novel_status(run_id=run_id, current_user=user, session=task_session)
    await asyncio.sleep(0)
    assert len(scheduled) == 1


def test_import_storage_path_rejects_cross_user_and_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(novels, "_IMPORT_STORAGE_ROOT", tmp_path)
    expected = novels._import_storage_path(9, "safe-run")
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"ok")
    assert novels._validated_import_storage_path(9, "safe-run", str(expected)) == expected.resolve()
    assert novels._validated_import_storage_path(10, "safe-run", str(expected)) is None
    assert novels._validated_import_storage_path(9, "safe-run", str(tmp_path / "9" / ".." / "10" / "safe-run.bin")) is None


@pytest.mark.asyncio
async def test_import_worker_clears_scheduled_marker(monkeypatch):
    run_id = "import-cleanup"
    novels._IMPORT_SCHEDULED_RUNS.add(run_id)
    async def fake_claim(*args, **kwargs): return False
    monkeypatch.setattr(novels, "_claim_import_runtime", fake_claim)
    await novels._run_import_novel_job(run_id, 9, "x.txt", b"x")
    assert run_id not in novels._IMPORT_SCHEDULED_RUNS
