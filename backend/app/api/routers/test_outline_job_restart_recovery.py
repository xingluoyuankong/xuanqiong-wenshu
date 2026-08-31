"""进程重启后章节大纲任务必须从持久化任务恢复，而不是重复入队。"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import BackgroundTasks

from app.api.routers import writer
from app.models.novel import NovelProject
from app.models.user import User
from app.schemas.novel import GenerateOutlineRequest
from app.schemas.task_runtime import TaskRuntimeStatus
from app.schemas.user import UserInDB
from app.services.task_runtime import TaskRuntimeService

PROJECT_ID = "proj-outline-restart"
USER_ID = 77


class _FakeNovelService:
    def __init__(self, session):
        self.session = session

    async def ensure_project_owner(self, project_id, user_id):
        return object()


@pytest.fixture(autouse=True)
def _clear_outline_memory():
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()
    yield
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()


async def _seed_project(session) -> None:
    session.add(
        User(id=USER_ID, username="outline-restart", email="or@example.com", hashed_password="x")
    )
    session.add(NovelProject(id=PROJECT_ID, user_id=USER_ID, title="重启恢复项目"))
    await session.commit()


@pytest.mark.asyncio
async def test_start_does_not_duplicate_when_persisted_task_is_active(task_session, monkeypatch):
    """内存索引被清空（模拟重启）时，start 必须复用持久化任务而不是新建。"""
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    runtime = TaskRuntimeService(task_session)
    persisted = await runtime.create_task(
        task_id="outline-run-1",
        task_type="chapter_outline_generation",
        owner_user_id=USER_ID,
        project_id=PROJECT_ID,
        payload={"run_id": "outline-run-1", "request": {"start_chapter": 1, "num_chapters": 3}},
    )
    await runtime.update_progress(
        persisted.task_id, progress=30.0, stage="outline_chapter_skeleton", message="生成中"
    )

    background_tasks = BackgroundTasks()
    response = await writer.start_chapters_outline_generation(
        project_id=PROJECT_ID,
        request=GenerateOutlineRequest(start_chapter=1, num_chapters=3),
        background_tasks=background_tasks,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    assert response.run_id == "outline-run-1"
    assert response.status in writer._OUTLINE_ACTIVE_STATUSES
    # 关键断言：没有派发新的后台任务，也没有创建第二个 TaskRuntime。
    assert background_tasks.tasks == []
    tasks = await runtime.list_tasks(owner_user_id=USER_ID, limit=50)
    outline_tasks = [t for t in tasks if t.project_id == PROJECT_ID]
    assert len(outline_tasks) == 1


@pytest.mark.asyncio
async def test_status_reports_persisted_task_after_restart(task_session, monkeypatch):
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_id="outline-run-2",
        task_type="chapter_outline_generation",
        owner_user_id=USER_ID,
        project_id=PROJECT_ID,
    )
    await runtime.update_progress(task.task_id, progress=55.0, stage="outline_context", message="审计上下文")

    response = await writer.get_chapters_outline_generation_status(
        project_id=PROJECT_ID,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    assert response.run_id == "outline-run-2"
    assert response.status != "idle"
    assert response.progress_stage == "outline_context"


@pytest.mark.asyncio
async def test_status_prefers_terminal_runtime_over_stale_memory_cache(task_session, monkeypatch):
    """进程内旧快照不能把已取消的持久化任务误报为生成中。"""
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_id="outline-run-terminal-memory",
        task_type="chapter_outline_generation",
        owner_user_id=USER_ID,
        project_id=PROJECT_ID,
        payload={"request": {"start_chapter": 1, "num_chapters": 3}},
    )
    await runtime.append_event(
        task.task_id,
        event_type="task_cancelled",
        status=TaskRuntimeStatus.CANCELLED.value,
        stage="cancelled",
        message="任务已取消",
    )
    writer._OUTLINE_PROJECT_RUNS[PROJECT_ID] = task.task_id
    writer._OUTLINE_JOBS[task.task_id] = {
        "run_id": task.task_id,
        "project_id": PROJECT_ID,
        "user_id": USER_ID,
        "status": "generating",
        "progress_stage": "outline_context",
        "progress_message": "旧进程缓存仍显示生成中",
    }

    response = await writer.get_chapters_outline_generation_status(
        project_id=PROJECT_ID,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    assert response.run_id == task.task_id
    assert response.status == "cancelled"
    assert response.progress_stage == "cancelled"


@pytest.mark.asyncio
async def test_terminal_persisted_task_allows_new_run(task_session, monkeypatch):
    """已完成的任务不得阻塞新任务：否则用户永远无法再生成大纲。"""
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    runtime = TaskRuntimeService(task_session)
    done = await runtime.create_task(
        task_id="outline-run-3",
        task_type="chapter_outline_generation",
        owner_user_id=USER_ID,
        project_id=PROJECT_ID,
    )
    await runtime.append_event(
        done.task_id, event_type="task_completed", status=TaskRuntimeStatus.SUCCEEDED.value
    )

    background_tasks = BackgroundTasks()
    response = await writer.start_chapters_outline_generation(
        project_id=PROJECT_ID,
        request=GenerateOutlineRequest(start_chapter=1, num_chapters=3),
        background_tasks=background_tasks,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    assert response.run_id != "outline-run-3"
    assert len(background_tasks.tasks) == 1


@pytest.mark.asyncio
async def test_cancel_recovers_queued_runtime_when_memory_cache_is_empty(task_session, monkeypatch):
    """重启后清空大纲缓存，取消入口仍必须收敛持久化 queued 任务。"""
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_id="outline-run-cancel-after-restart",
        task_type="chapter_outline_generation",
        owner_user_id=USER_ID,
        project_id=PROJECT_ID,
        payload={"request": {"start_chapter": 1, "num_chapters": 3}},
    )

    assert writer._OUTLINE_JOBS == {}
    response = await writer.cancel_chapters_outline_generation(
        project_id=PROJECT_ID,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    persisted = await runtime.get_task(task.task_id, USER_ID)
    assert response.run_id == task.task_id
    assert response.status == "cancelled"
    assert persisted.status == TaskRuntimeStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancel_finalizes_queued_runtime_even_when_worker_is_scheduled(task_session, monkeypatch):
    """已登记但尚未领取的后台协程不能把取消任务永远留在 cancelling。"""
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_id="outline-run-queued-scheduled-cancel",
        task_type="chapter_outline_generation",
        owner_user_id=USER_ID,
        project_id=PROJECT_ID,
        payload={"request": {"start_chapter": 1, "num_chapters": 3}},
    )
    writer._OUTLINE_PROJECT_RUNS[PROJECT_ID] = task.task_id
    writer._OUTLINE_JOBS[task.task_id] = {
        "run_id": task.task_id,
        "project_id": PROJECT_ID,
        "user_id": USER_ID,
        "status": "queued",
        "progress_stage": "queued",
        "progress_message": "已入队",
        "_runtime_status": TaskRuntimeStatus.QUEUED.value,
    }
    writer._OUTLINE_SCHEDULED_RUNS.add(task.task_id)

    response = await writer.cancel_chapters_outline_generation(
        project_id=PROJECT_ID,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    assert response.status == "cancelled"
    assert (await runtime.get_task(task.task_id, USER_ID)).status == TaskRuntimeStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_other_users_active_task_does_not_block(task_session, monkeypatch):
    """归属隔离：别人的任务不能占用当前用户的项目大纲入口。"""
    monkeypatch.setattr(writer, "NovelService", _FakeNovelService)
    await _seed_project(task_session)
    task_session.add(
        User(id=99, username="other-user", email="other@example.com", hashed_password="x")
    )
    await task_session.commit()
    runtime = TaskRuntimeService(task_session)
    await runtime.create_task(
        task_id="outline-run-other",
        task_type="chapter_outline_generation",
        owner_user_id=99,
        project_id=PROJECT_ID,
    )

    background_tasks = BackgroundTasks()
    response = await writer.start_chapters_outline_generation(
        project_id=PROJECT_ID,
        request=GenerateOutlineRequest(start_chapter=1, num_chapters=3),
        background_tasks=background_tasks,
        session=task_session,
        current_user=UserInDB(id=USER_ID, username="t", email=None, hashed_password="x"),
    )

    assert response.run_id != "outline-run-other"
    assert len(background_tasks.tasks) == 1

@pytest.mark.asyncio
async def test_rewrite_job_consults_runtime_stop_check_before_rewrite(monkeypatch):
    """重写 worker 必须把持久化 Runtime 停止判断放在业务调用之前。

    反向验证：若有人把判断改回旧的内存缓存检查，本测试将因业务方法被调用而失败。
    """
    called = False

    async def _claim_true(run_id, user_id):
        return True

    async def _should_stop(run_id, user_id):
        return True

    async def _set_state(run_id, **updates):
        return {"run_id": run_id, **updates}

    async def _noop_finish(*args, **kwargs):
        return None

    async def _fail_rewrite(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("任务已终态，重写 worker 不得继续调用业务方法")

    monkeypatch.setattr(writer, "_claim_outline_runtime", _claim_true)
    monkeypatch.setattr(writer, "_outline_runtime_should_stop", _should_stop)
    monkeypatch.setattr(writer, "_set_outline_job_state", _set_state)
    monkeypatch.setattr(writer, "_finish_outline_runtime", _noop_finish)
    monkeypatch.setattr(writer, "rewrite_chapter_outline", _fail_rewrite)

    with pytest.raises(asyncio.CancelledError):
        await writer._run_outline_rewrite_job(
            "outline-rewrite-terminal-run",
            "proj-outline-restart",
            77,
            {"chapter_number": 1},
        )

    assert not called


@pytest.mark.asyncio
async def test_outline_runtime_should_stop_uses_persisted_terminal_status(monkeypatch):
    """Runtime 停止判断：记录消失或终态必须停止，运行中不停止。"""

    class _Task:
        def __init__(self, status):
            self.status = status

    async def _fake_task(run_id, user_id):
        # fake 直接把 run_id 当作持久化状态，便于单测枚举终态/非终态。
        return _Task(run_id)

    monkeypatch.setattr(writer, "_outline_runtime_task", _fake_task)

    assert await writer._outline_runtime_should_stop("succeeded", 77) is True
    assert await writer._outline_runtime_should_stop("failed", 77) is True
    assert await writer._outline_runtime_should_stop("cancelled", 77) is True
    assert await writer._outline_runtime_should_stop("stale", 77) is True
    assert await writer._outline_runtime_should_stop("running", 77) is False
    assert await writer._outline_runtime_should_stop("queued", 77) is False

    async def _missing_task(run_id, user_id):
        return None

    monkeypatch.setattr(writer, "_outline_runtime_task", _missing_task)
    assert await writer._outline_runtime_should_stop("missing-run", 77) is True


