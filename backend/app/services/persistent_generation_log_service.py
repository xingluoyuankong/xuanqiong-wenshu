"""将旧的生成日志接口桥接到持久化 TaskRuntime 事件流。

日志与正文 content_delta 严格分流：本服务只写 LOG/终态事件，正文流由
writer 自己的 content_delta 事件负责，因此刷新、重启和多 worker 场景不依赖进程内缓冲区。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.task_runtime import TaskRuntime
from ..schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus
from .task_runtime import TERMINAL_STATUSES, TaskRuntimeNotFound, TaskRuntimeService


class PersistentGenerationLogService:
    """GenerationLogService 的持久化兼容适配器。"""

    async def ensure_task(
        self,
        session: AsyncSession,
        task_id: str,
        *,
        owner_user_id: int,
        create_if_missing: bool = True,
    ) -> TaskRuntime:
        service = TaskRuntimeService(session)
        try:
            return await service.get_task(task_id, owner_user_id)
        except TaskRuntimeNotFound:
            if not create_if_missing:
                raise
            return await service.create_task(
                task_id=task_id,
                task_type="generation_log",
                idempotency_key=f"generation-log:{owner_user_id}:{task_id}",
                owner_user_id=owner_user_id,
                payload={"channel": "log"},
            )

    async def append(
        self,
        session: AsyncSession,
        task_id: str,
        *,
        owner_user_id: int,
        message: str,
        level: str = "info",
        metadata: Optional[dict[str, Any]] = None,
    ) -> TaskRuntime:
        service = TaskRuntimeService(session)
        task = await service.get_task(task_id, owner_user_id)
        if task.status in TERMINAL_STATUSES:
            raise RuntimeError(f"task {task_id} is already terminal")
        return await service.append_event(
            task_id,
            event_type=TaskRuntimeEventType.LOG.value,
            status=TaskRuntimeStatus.RUNNING.value,
            stage=task.stage or "logging",
            message=message,
            payload={"channel": "log", "level": level, "metadata": metadata or {}},
            owner_user_id=owner_user_id,
        )

    async def complete(
        self, session: AsyncSession, task_id: str, *, owner_user_id: int
    ) -> TaskRuntime:
        service = TaskRuntimeService(session)
        task = await service.get_task(task_id, owner_user_id)
        if task.status in TERMINAL_STATUSES:
            return task
        if task.status == TaskRuntimeStatus.CANCELLING.value:
            return task
        return await service.append_event(
            task_id,
            event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
            status=TaskRuntimeStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            message="任务完成",
            payload={"channel": "log"},
            owner_user_id=owner_user_id,
        )

    async def list_active(
        self, session: AsyncSession, *, owner_user_id: int
    ) -> list[TaskRuntime]:
        result = await session.execute(
            select(TaskRuntime)
            .where(
                TaskRuntime.owner_user_id == owner_user_id,
                TaskRuntime.status.not_in(list(TERMINAL_STATUSES)),
            )
            .order_by(TaskRuntime.updated_at.desc())
        )
        return list(result.scalars().all())


def get_persistent_generation_log_service() -> PersistentGenerationLogService:
    return PersistentGenerationLogService()
