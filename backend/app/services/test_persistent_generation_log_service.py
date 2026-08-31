import pytest

from app.schemas.task_runtime import TaskRuntimeEventType
from app.services.persistent_generation_log_service import PersistentGenerationLogService
from app.services.task_runtime import TaskRuntimeNotFound, TaskRuntimeService


@pytest.mark.asyncio
async def test_generation_logs_persist_and_complete(task_session):
    service = PersistentGenerationLogService()
    task = await service.ensure_task(task_session, "log-task-1", owner_user_id=7)
    assert task.status == "queued"

    running = await service.append(
        task_session,
        task.task_id,
        owner_user_id=7,
        message="生成阶段开始",
        level="info",
        metadata={"stage": "draft"},
    )
    assert running.status == "running"

    done = await service.complete(task_session, task.task_id, owner_user_id=7)
    assert done.status == "succeeded"
    events = await TaskRuntimeService(task_session).list_events(task.task_id, after_event_id=0, owner_user_id=7)
    assert [event.event_type for event in events] == [
        TaskRuntimeEventType.TASK_CREATED.value,
        TaskRuntimeEventType.LOG.value,
        TaskRuntimeEventType.TASK_COMPLETED.value,
    ]
    assert events[1].payload["channel"] == "log"
    assert events[1].payload["metadata"]["stage"] == "draft"


@pytest.mark.asyncio
async def test_generation_logs_enforce_owner_and_terminal_state(task_session):
    service = PersistentGenerationLogService()
    await service.ensure_task(task_session, "log-task-2", owner_user_id=7)
    with pytest.raises(TaskRuntimeNotFound):
        await service.append(task_session, "log-task-2", owner_user_id=8, message="nope")
    await service.complete(task_session, "log-task-2", owner_user_id=7)
    with pytest.raises(RuntimeError):
        await service.append(task_session, "log-task-2", owner_user_id=7, message="late")


# 保持测试通过现有 TaskRuntimeService 的持久化事件查询，不引入第二套存储。


@pytest.mark.asyncio
async def test_read_does_not_create_missing_log_task(task_session):
    service = PersistentGenerationLogService()
    with pytest.raises(TaskRuntimeNotFound):
        await service.ensure_task(task_session, "missing-log", owner_user_id=7, create_if_missing=False)
