"""与具体业务解耦的持久化任务状态和事件服务。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.task_runtime import TaskRuntime, TaskRuntimeEvent
from ..schemas.task_runtime import (
    TaskRuntimeEventChannel,
    TaskRuntimeEventType,
    TaskRuntimeStatus,
)


TERMINAL_STATUSES = {
    TaskRuntimeStatus.CANCELLED.value,
    TaskRuntimeStatus.SUCCEEDED.value,
    TaskRuntimeStatus.FAILED.value,
    TaskRuntimeStatus.STALE.value,
}
VALID_STATUSES = {item.value for item in TaskRuntimeStatus}

# Chapter generation has an explicit provider/background budget. The generic
# sweeper must not declare such a task dead before that budget has elapsed,
# while ordinary jobs retain the normal short zombie-task threshold.
_CHAPTER_GENERATION_TASK_TYPE = "chapter_generation"
_TASK_RUNTIME_BUDGET_GRACE_SECONDS = 180
_MAX_RUNTIME_BUDGET_SECONDS = 24 * 60 * 60


def _coerce_positive_seconds(value: Any) -> Optional[int]:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def _extract_normalized_generation_timeout(payload: Any) -> Optional[int]:
    """Read the persisted, normalized budget without importing writer code."""
    if not isinstance(payload, dict):
        return None

    spec = payload.get("generation_spec")
    spec = spec if isinstance(spec, dict) else {}
    flow_config = spec.get("flow_config")
    flow_config = flow_config if isinstance(flow_config, dict) else {}
    limits = payload.get("chapter_generation_limits")
    limits = limits if isinstance(limits, dict) else {}

    for value in (
        payload.get("normalized_generation_timeout_seconds"),
        payload.get("runtime_timeout_seconds"),
        limits.get("timeout_seconds"),
        spec.get("normalized_generation_timeout_seconds"),
        spec.get("runtime_timeout_seconds"),
        flow_config.get("generation_timeout_seconds"),
    ):
        seconds = _coerce_positive_seconds(value)
        if seconds is not None:
            return min(_MAX_RUNTIME_BUDGET_SECONDS, seconds)
    return None


def _effective_stale_after_seconds(task: TaskRuntime, default_seconds: int) -> int:
    """Return a per-task stale threshold while preserving default job behavior."""
    base = max(1, int(default_seconds))
    if task.task_type != _CHAPTER_GENERATION_TASK_TYPE:
        return base
    budget = _extract_normalized_generation_timeout(task.payload)
    if budget is None:
        return base
    return min(
        _MAX_RUNTIME_BUDGET_SECONDS,
        max(base, budget + _TASK_RUNTIME_BUDGET_GRACE_SECONDS),
    )


class TaskRuntimeError(Exception):
    """任务运行时基础异常。"""


class TaskRuntimeNotFound(TaskRuntimeError):
    pass


class TaskRuntimeConflict(TaskRuntimeError):
    pass


class TaskRuntimeService:
    """提供创建、状态更新、心跳、取消、重试和事件回放能力。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
        """Normalize SQLite/MySQL naive timestamps to UTC-aware datetimes."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def event_channel(event_type: str) -> str:
        """把旧事件类型投影到统一 UI 频道，保持旧调用方兼容。"""
        if event_type == TaskRuntimeEventType.CONTENT_DELTA.value:
            return TaskRuntimeEventChannel.CONTENT.value
        if event_type == TaskRuntimeEventType.LOG.value:
            return TaskRuntimeEventChannel.LOG.value
        if event_type in {
            TaskRuntimeEventType.PROGRESS.value,
            TaskRuntimeEventType.STAGE_CHANGED.value,
            TaskRuntimeEventType.HEARTBEAT.value,
        }:
            return TaskRuntimeEventChannel.PROGRESS.value
        if event_type in {
            TaskRuntimeEventType.DIAGNOSTIC.value,
            TaskRuntimeEventType.QUALITY_UPDATE.value,
        }:
            return TaskRuntimeEventChannel.DIAGNOSTIC.value
        if event_type in {
            TaskRuntimeEventType.TASK_COMPLETED.value,
            TaskRuntimeEventType.TASK_FAILED.value,
            TaskRuntimeEventType.TASK_CANCELLED.value,
            TaskRuntimeEventType.TASK_STALE.value,
        }:
            return TaskRuntimeEventChannel.TERMINAL.value
        return TaskRuntimeEventChannel.TASK_RUNTIME.value

    async def _get(self, task_id: str, owner_user_id: Optional[int] = None) -> TaskRuntime:
        stmt = select(TaskRuntime).where(TaskRuntime.task_id == task_id)
        if owner_user_id is not None:
            stmt = stmt.where(TaskRuntime.owner_user_id == owner_user_id)
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise TaskRuntimeNotFound(f"task {task_id} not found")
        return task

    async def get_task(self, task_id: str, owner_user_id: Optional[int] = None) -> TaskRuntime:
        return await self._get(task_id, owner_user_id)

    async def list_tasks(
        self,
        *,
        owner_user_id: Optional[int] = None,
        project_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[TaskRuntime]:
        """按归属和业务作用域列出任务，供刷新/重启后的恢复入口使用。"""
        stmt = select(TaskRuntime).order_by(TaskRuntime.updated_at.desc()).limit(
            min(max(int(limit), 1), 500)
        )
        if owner_user_id is not None:
            stmt = stmt.where(TaskRuntime.owner_user_id == owner_user_id)
        if project_id is not None:
            stmt = stmt.where(TaskRuntime.project_id == project_id)
        if chapter_id is not None:
            stmt = stmt.where(TaskRuntime.chapter_id == chapter_id)
        if statuses:
            stmt = stmt.where(TaskRuntime.status.in_(list(statuses)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def merge_payload(
        self,
        task_id: str,
        payload_patch: dict[str, Any],
        *,
        owner_user_id: Optional[int] = None,
    ) -> TaskRuntime:
        """持久化任务恢复所需的计划/断点元数据，并写入可回放审计事件。"""
        task = await self._get(task_id, owner_user_id)
        patch = dict(payload_patch or {})
        merged = dict(task.payload or {})
        if patch and all(merged.get(key) == value for key, value in patch.items()):
            return task
        merged.update(patch)
        task.payload = merged

        await self._append_event(
            task,
            event_type=TaskRuntimeEventType.DIAGNOSTIC.value,
            status=task.status,
            stage=task.stage,
            progress=task.progress,
            message="task payload updated",
            payload={"channel": "task_runtime", "keys": sorted(patch.keys())},
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def create_task(
        self,
        *,
        task_id: Optional[str] = None,
        task_type: str,
        idempotency_key: Optional[str] = None,
        owner_user_id: Optional[int] = None,
        project_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        max_retries: int = 3,
        input_hash: Optional[str] = None,
        config_snapshot_id: Optional[str] = None,
        artifact_ref: Optional[str] = None,
        artifact_revision: Optional[str] = None,
    ) -> TaskRuntime:
        if idempotency_key:
            existing = (
                await self.session.execute(
                    select(TaskRuntime).where(TaskRuntime.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                if existing.task_type != task_type or existing.owner_user_id != owner_user_id:
                    raise TaskRuntimeConflict("idempotency_key is already used by another task")
                return existing

        resolved_task_id = task_id or uuid4().hex
        if len(resolved_task_id) > 64:
            raise TaskRuntimeConflict("task_id exceeds 64 characters")
        task = TaskRuntime(
            task_id=resolved_task_id,
            task_type=task_type,
            idempotency_key=idempotency_key,
            owner_user_id=owner_user_id,
            input_hash=input_hash,
            config_snapshot_id=config_snapshot_id,
            artifact_ref=artifact_ref,
            artifact_revision=artifact_revision,
            project_id=project_id,
            correlation_id=(str(correlation_id).strip()[:36] or None) if correlation_id else None,
            chapter_id=chapter_id,
            payload=payload or {},
            max_retries=max_retries,
            status=TaskRuntimeStatus.QUEUED.value,
            progress=0.0,
        )
        self.session.add(task)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            if idempotency_key:
                existing = (
                    await self.session.execute(
                        select(TaskRuntime).where(TaskRuntime.idempotency_key == idempotency_key)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.task_type != task_type or existing.owner_user_id != owner_user_id:
                        raise TaskRuntimeConflict("idempotency_key is already used by another task")
                    return existing
            raise

        await self._append_event(
            task,
            event_type=TaskRuntimeEventType.TASK_CREATED.value,
            status=task.status,
            message="task queued",
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def _append_event(
        self,
        task: TaskRuntime,
        *,
        event_type: str,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        attempt: Optional[int] = None,
        lease_generation: Optional[int] = None,
    ) -> TaskRuntimeEvent:
        event_payload = dict(payload or {})
        channel = event_payload.setdefault("channel", self.event_channel(event_type))
        event_payload.setdefault("event_sequence", None)
        event = TaskRuntimeEvent(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            event_type=event_type,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            idempotency_key=idempotency_key,
            attempt=attempt if attempt is not None else task.attempt,
            lease_generation=(
                lease_generation if lease_generation is not None else task.lease_generation
            ),
            channel=channel,
            payload=event_payload,
        )
        self.session.add(event)
        await self.session.flush()
        event.sequence = event.event_id
        event_payload["event_sequence"] = event.event_id
        event.payload = dict(event_payload)
        await self.session.execute(
            update(TaskRuntimeEvent)
            .where(TaskRuntimeEvent.event_id == event.event_id)
            .values(
                payload=dict(event_payload),
                channel=channel,
                sequence=event.event_id,
            )
        )
        task.event_cursor = event.event_id
        task.updated_at = self._now()
        return event

    async def _assert_writer_fence(
        self,
        task: TaskRuntime,
        *,
        attempt: Optional[int],
        lease_owner: Optional[str],
        lease_generation: Optional[int],
    ) -> None:
        """Reject a worker callback once its attempt or lease is no longer current.

        Legacy callers may omit the fence while compatibility adapters are being
        migrated; any caller that supplies one fence field must supply a complete
        matching tuple so a stale worker cannot partially update the projection.
        """
        supplied = (attempt, lease_owner, lease_generation)
        if not any(value is not None for value in supplied):
            return
        if attempt is None or lease_owner is None or lease_generation is None:
            raise TaskRuntimeConflict("writer fence requires attempt, lease_owner and lease_generation")
        result = await self.session.execute(
            update(TaskRuntime)
            .where(
                TaskRuntime.task_id == task.task_id,
                TaskRuntime.attempt == attempt,
                TaskRuntime.lease_owner == lease_owner,
                TaskRuntime.lease_generation == lease_generation,
                TaskRuntime.status.in_([
                    TaskRuntimeStatus.RUNNING.value,
                    TaskRuntimeStatus.CANCELLING.value,
                ]),
            )
            .values(updated_at=self._now())
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) != 1:
            raise TaskRuntimeConflict("stale task writer")
        await self.session.refresh(task)

    async def append_event(
        self,
        task_id: str,
        *,
        event_type: str,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        owner_user_id: Optional[int] = None,
        elapsed_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        attempt: Optional[int] = None,
        lease_owner: Optional[str] = None,
        lease_generation: Optional[int] = None,
    ) -> TaskRuntime:
        if status is not None and status not in VALID_STATUSES:
            raise TaskRuntimeConflict(f"invalid task status {status}")
        task = await self._get(task_id, owner_user_id)
        fence_owner = lease_owner if attempt is not None or lease_generation is not None else None
        await self._assert_writer_fence(
            task,
            attempt=attempt,
            lease_owner=fence_owner,
            lease_generation=lease_generation,
        )
        if (
            task.status in TERMINAL_STATUSES
            and status is not None
            and status != task.status
        ):
            raise TaskRuntimeConflict(
                f"cannot transition terminal task {task.status} to {status}"
            )
        # 取消请求是不可逆的中间态：Provider 的迟到回调只能继续记录
        # cancelling/cancelled，绝不能把任务复活为 running 或成功/失败。
        if (
            task.status == TaskRuntimeStatus.CANCELLING.value
            and status is not None
            and status not in {
                TaskRuntimeStatus.CANCELLING.value,
                TaskRuntimeStatus.CANCELLED.value,
            }
        ):
            raise TaskRuntimeConflict(
                f"cannot transition cancelling task to {status}"
            )
        if idempotency_key:
            duplicate = (
                await self.session.execute(
                    select(TaskRuntimeEvent).where(
                        TaskRuntimeEvent.task_id == task_id,
                        TaskRuntimeEvent.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                return task

        if status is not None:
            task.status = status
        if stage is not None:
            task.stage = stage
        if progress is not None:
            task.progress = progress
        if message is not None:
            task.message = message
        if status == TaskRuntimeStatus.RUNNING.value and task.started_at is None:
            task.started_at = self._now()
        if status in TERMINAL_STATUSES:
            task.finished_at = self._now()
            started_at = self._normalize_datetime(task.started_at)
            finished_at = self._normalize_datetime(task.finished_at)
            if started_at is not None and finished_at is not None and elapsed_ms is None:
                elapsed_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        if elapsed_ms is not None:
            task.elapsed_ms = max(0, int(elapsed_ms))
        if input_tokens is not None:
            task.input_tokens = max(0, int(input_tokens))
        if output_tokens is not None:
            task.output_tokens = max(0, int(output_tokens))
        if total_tokens is not None:
            task.total_tokens = max(0, int(total_tokens))
        elif input_tokens is not None or output_tokens is not None:
            task.total_tokens = (task.input_tokens or 0) + (task.output_tokens or 0)

        # Durable activity events also refresh liveness during long provider waits.
        # Queued and terminal tasks must not be made active by observability writes.
        if task.status in {
            TaskRuntimeStatus.RUNNING.value,
            TaskRuntimeStatus.CANCELLING.value,
        }:
            task.heartbeat_at = self._now()

        await self._append_event(
            task,
            event_type=event_type,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            idempotency_key=idempotency_key,
            payload=payload,
            attempt=attempt,
            lease_generation=lease_generation,
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def claim(
        self,
        task_id: str,
        *,
        lease_owner: str,
        stale_after_seconds: int = 120,
        owner_user_id: Optional[int] = None,
    ) -> TaskRuntime:
        """以持久化租约领取任务，避免多 worker 重复执行。"""
        if not lease_owner.strip():
            raise TaskRuntimeConflict("lease_owner is required")
        task = await self._get(task_id, owner_user_id)
        now = self._now()
        if task.status in TERMINAL_STATUSES and task.status != TaskRuntimeStatus.STALE.value:
            raise TaskRuntimeConflict(f"cannot claim terminal task {task.status}")
        effective_stale_after = _effective_stale_after_seconds(task, stale_after_seconds)
        heartbeat = self._normalize_datetime(task.heartbeat_at)
        if (
            task.status == TaskRuntimeStatus.RUNNING.value
            and task.lease_owner == lease_owner
            and heartbeat is not None
            and now - heartbeat < timedelta(seconds=effective_stale_after)
        ):
            return task

        cutoff = now - timedelta(seconds=effective_stale_after)
        reclaimable = or_(
            TaskRuntime.status.in_([TaskRuntimeStatus.QUEUED.value, TaskRuntimeStatus.STALE.value]),
            and_(
                TaskRuntime.status == TaskRuntimeStatus.RUNNING.value,
                or_(
                    TaskRuntime.lease_owner == lease_owner,
                    TaskRuntime.heartbeat_at.is_(None),
                    TaskRuntime.heartbeat_at < cutoff,
                ),
            ),
        )
        result = await self.session.execute(
            update(TaskRuntime)
            .where(TaskRuntime.task_id == task_id, reclaimable)
            .values(
                status=TaskRuntimeStatus.RUNNING.value,
                stage=task.stage or "running",
                lease_owner=lease_owner,
                lease_generation=TaskRuntime.lease_generation + 1,
                heartbeat_at=now,
                started_at=func.coalesce(TaskRuntime.started_at, now),
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) != 1:
            raise TaskRuntimeConflict("task lease is held by another live worker")

        await self.session.refresh(task)
        await self._append_event(
            task,
            event_type=TaskRuntimeEventType.TASK_STARTED.value,
            status=task.status,
            stage=task.stage,
            progress=task.progress,
            message=f"claimed by {lease_owner}",
            idempotency_key=f"claim:{lease_owner}:{task.attempt}:{task.lease_generation}",
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def recover(
        self,
        task_id: str,
        *,
        lease_owner: str,
        stale_after_seconds: int = 120,
        owner_user_id: Optional[int] = None,
    ) -> TaskRuntime:
        """正式恢复入口：仅通过持久化租约重新领取 stale/超时任务。"""
        task = await self._get(task_id, owner_user_id)
        if task.status not in {TaskRuntimeStatus.STALE.value, TaskRuntimeStatus.RUNNING.value}:
            raise TaskRuntimeConflict(f"task status {task.status} is not recoverable")
        return await self.claim(
            task_id,
            lease_owner=lease_owner,
            stale_after_seconds=stale_after_seconds,
            owner_user_id=owner_user_id,
        )

    async def mark_stale(
        self,
        *,
        stale_after_seconds: int = 120,
        project_id: Optional[str] = None,
        owner_user_id: Optional[int] = None,
    ) -> list[TaskRuntime]:
        """将心跳超时的运行中任务标记为 stale，供重启/巡检恢复。"""
        cutoff = self._now() - timedelta(seconds=max(1, int(stale_after_seconds)))
        stmt = select(TaskRuntime).where(
            TaskRuntime.status.in_([TaskRuntimeStatus.RUNNING.value, TaskRuntimeStatus.CANCELLING.value]),
            (TaskRuntime.heartbeat_at.is_(None) | (TaskRuntime.heartbeat_at < cutoff)),
        )
        if project_id is not None:
            stmt = stmt.where(TaskRuntime.project_id == project_id)
        if owner_user_id is not None:
            stmt = stmt.where(TaskRuntime.owner_user_id == owner_user_id)
        candidates = list((await self.session.execute(stmt)).scalars().all())
        tasks: list[TaskRuntime] = []
        for candidate in candidates:
            # Re-check the liveness predicate in the UPDATE. Two sweepers may
            # read the same stale row; only the first one may transition it and
            # append the durable task_stale event.
            now = self._now()
            effective_stale_after = _effective_stale_after_seconds(candidate, stale_after_seconds)
            effective_cutoff = now - timedelta(seconds=effective_stale_after)
            heartbeat = self._normalize_datetime(candidate.heartbeat_at)
            if heartbeat is not None and heartbeat >= effective_cutoff:
                continue
            result = await self.session.execute(
                update(TaskRuntime)
                .where(
                    TaskRuntime.task_id == candidate.task_id,
                    TaskRuntime.status.in_([
                        TaskRuntimeStatus.RUNNING.value,
                        TaskRuntimeStatus.CANCELLING.value,
                    ]),
                    (TaskRuntime.heartbeat_at.is_(None) | (TaskRuntime.heartbeat_at < effective_cutoff)),
                )
                .values(
                    status=TaskRuntimeStatus.STALE.value,
                    finished_at=now,
                    error_code="STALE_TASK",
                    error_detail="heartbeat timeout",
                    message="task marked stale after heartbeat timeout",
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if int(result.rowcount or 0) != 1:
                continue
            await self.session.refresh(candidate)
            await self._append_event(
                candidate,
                event_type=TaskRuntimeEventType.TASK_STALE.value,
                status=candidate.status,
                stage=candidate.stage,
                progress=candidate.progress,
                message=candidate.message,
            )
            tasks.append(candidate)
        await self.session.commit()
        for task in tasks:
            await self.session.refresh(task)
        return tasks

    async def update_metrics(
        self,
        task_id: str,
        *,
        elapsed_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        owner_user_id: Optional[int] = None,
    ) -> TaskRuntime:
        return await self.append_event(
            task_id,
            event_type=TaskRuntimeEventType.DIAGNOSTIC.value,
            message="task metrics updated",
            owner_user_id=owner_user_id,
            elapsed_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            payload={"metrics": True},
        )

    async def update_progress(
        self,
        task_id: str,
        *,
        progress: float,
        stage: Optional[str] = None,
        message: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        owner_user_id: Optional[int] = None,
        attempt: Optional[int] = None,
        lease_owner: Optional[str] = None,
        lease_generation: Optional[int] = None,
    ) -> TaskRuntime:
        task = await self._get(task_id, owner_user_id)
        if task.status in TERMINAL_STATUSES:
            raise TaskRuntimeConflict(f"cannot update terminal task {task.status}")
        # 取消请求与 Provider 迟到进度并发时，不能把 cancelling 覆盖回 running。
        effective_status = (
            TaskRuntimeStatus.CANCELLING.value
            if task.status == TaskRuntimeStatus.CANCELLING.value
            else TaskRuntimeStatus.RUNNING.value
        )
        return await self.append_event(
            task_id,
            event_type=TaskRuntimeEventType.PROGRESS.value,
            status=effective_status,
            stage=stage,
            progress=progress,
            message=message,
            payload=payload,
            owner_user_id=owner_user_id,
            attempt=attempt,
            lease_owner=lease_owner,
            lease_generation=lease_generation,
        )

    async def heartbeat(
        self,
        task_id: str,
        *,
        lease_owner: Optional[str] = None,
        lease_generation: Optional[int] = None,
        attempt: Optional[int] = None,
        message: Optional[str] = None,
        owner_user_id: Optional[int] = None,
    ) -> TaskRuntime:
        task = await self._get(task_id, owner_user_id)
        if task.status in TERMINAL_STATUSES:
            return task
        fence_owner = lease_owner if attempt is not None or lease_generation is not None else None
        await self._assert_writer_fence(
            task,
            attempt=attempt,
            lease_owner=fence_owner,
            lease_generation=lease_generation,
        )
        if lease_owner and task.lease_owner and task.lease_owner != lease_owner:
            heartbeat = self._normalize_datetime(task.heartbeat_at)
            if heartbeat is not None:
                if self._now() - heartbeat < timedelta(seconds=120):
                    raise TaskRuntimeConflict("task heartbeat is owned by another live worker")
        if lease_owner is not None and task.lease_owner is None:
            task.lease_owner = lease_owner
        return await self.append_event(
            task_id,
            event_type=TaskRuntimeEventType.HEARTBEAT.value,
            status=task.status,
            message=message,
            owner_user_id=owner_user_id,
            attempt=attempt,
            lease_owner=lease_owner,
            lease_generation=lease_generation,
        )

    async def request_cancel(
        self,
        task_id: str,
        *,
        owner_user_id: Optional[int] = None,
        finalize_unclaimed: bool = False,
    ) -> TaskRuntime:
        task = await self._get(task_id, owner_user_id)
        if task.status in TERMINAL_STATUSES:
            return task
        requested = await self.append_event(
            task_id,
            event_type=TaskRuntimeEventType.CANCEL_REQUESTED.value,
            status=TaskRuntimeStatus.CANCELLING.value,
            message="cancellation requested",
            owner_user_id=owner_user_id,
        )
        # 队列任务尚未被 worker 领取时没有消费者推进取消终态；API 入口可
        # 安全地立即收口，避免 SSE 永久等待，同时不影响运行中任务的取消竞态。
        if finalize_unclaimed and requested.status == TaskRuntimeStatus.CANCELLING.value and not requested.lease_owner:
            return await self.append_event(
                task_id,
                event_type=TaskRuntimeEventType.TASK_CANCELLED.value,
                status=TaskRuntimeStatus.CANCELLED.value,
                message="task cancelled before worker claim",
                owner_user_id=owner_user_id,
            )
        return requested

    async def retry(
        self,
        task_id: str,
        *,
        idempotency_key: Optional[str] = None,
        message: Optional[str] = None,
        owner_user_id: Optional[int] = None,
    ) -> TaskRuntime:
        task = await self._get(task_id, owner_user_id)
        if idempotency_key:
            duplicate = (
                await self.session.execute(
                    select(TaskRuntimeEvent).where(
                        TaskRuntimeEvent.task_id == task_id,
                        TaskRuntimeEvent.event_type == TaskRuntimeEventType.RETRY_REQUESTED.value,
                        TaskRuntimeEvent.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                return task
        if task.status not in {
            TaskRuntimeStatus.FAILED.value,
            TaskRuntimeStatus.CANCELLED.value,
            TaskRuntimeStatus.STALE.value,
        }:
            raise TaskRuntimeConflict(f"task status {task.status} is not retryable")
        if task.retry_count >= task.max_retries:
            raise TaskRuntimeConflict("maximum retry count reached")

        task.retry_count += 1
        task.attempt += 1
        task.status = TaskRuntimeStatus.QUEUED.value
        task.progress = 0.0
        task.stage = "queued"
        task.started_at = None
        task.finished_at = None
        task.elapsed_ms = None
        task.error_code = None
        task.error_detail = None
        task.message = message or "task queued for retry"
        # 重试是新一次 attempt 的排队，不得继承旧 worker 的租约；否则
        # 旧进程即使已经失败/断线，也会阻塞新 worker 或继续写入旧 attempt。
        task.lease_owner = None
        task.heartbeat_at = None
        await self._append_event(
            task,
            event_type=TaskRuntimeEventType.RETRY_REQUESTED.value,
            status=task.status,
            stage=task.stage,
            progress=task.progress,
            message=task.message,
            idempotency_key=idempotency_key,
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def list_events(
        self,
        task_id: str,
        *,
        after_event_id: int = 0,
        limit: int = 100,
        owner_user_id: Optional[int] = None,
    ) -> list[TaskRuntimeEvent]:
        await self._get(task_id, owner_user_id)
        result = await self.session.execute(
            select(TaskRuntimeEvent)
            .where(TaskRuntimeEvent.task_id == task_id, TaskRuntimeEvent.event_id > after_event_id)
            .order_by(TaskRuntimeEvent.event_id)
            .limit(min(max(limit, 1), 500))
        )
        return list(result.scalars().all())
