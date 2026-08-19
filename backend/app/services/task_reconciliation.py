"""进程重启与僵尸任务巡检的唯一恢复入口。

启动时不再无条件把所有 ``generating`` 章节重置为 ``draft``：那会杀掉仍在其他
实例上运行的任务，并丢掉恢复所需的 run_id / 阶段 / 事件游标。这里改为以
TaskRuntime 的持久化租约与心跳为唯一判据：

* 心跳超时的 running/cancelling 任务 -> ``stale``（可被 ``recover`` 重新领取）。
* 只有当章节的 TaskRuntime 已进入终态（或根本没有任务记录）时，才把 busy 章节
  落到可操作状态，并保留 run_id、阶段与原因，便于前端展示"可重试/可恢复"。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.novel import Chapter
from ..models.task_runtime import TaskRuntime
from ..schemas.novel import ChapterGenerationStatus
from .task_runtime import TERMINAL_STATUSES, TaskRuntimeService

logger = logging.getLogger(__name__)

CHAPTER_GENERATION_TASK_TYPES = ("chapter_generation",)

BUSY_CHAPTER_STATUSES = (
    ChapterGenerationStatus.GENERATING.value,
    ChapterGenerationStatus.EVALUATING.value,
    ChapterGenerationStatus.SELECTING.value,
)


@dataclass
class ReconciliationReport:
    """一次巡检的结果，便于启动日志与测试断言。"""

    stale_task_ids: list[str] = field(default_factory=list)
    released_chapter_ids: list[int] = field(default_factory=list)
    preserved_chapter_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stale_tasks": len(self.stale_task_ids),
            "released_chapters": len(self.released_chapter_ids),
            "preserved_chapters": len(self.preserved_chapter_ids),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_runtime_state(chapter: Chapter) -> dict[str, Any]:
    raw = (chapter.real_summary or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _chapter_run_id(chapter: Chapter) -> Optional[str]:
    runtime = _load_runtime_state(chapter).get("generation_runtime")
    if not isinstance(runtime, dict):
        return None
    run_id = runtime.get("run_id")
    return str(run_id) if run_id else None


def _build_released_runtime_state(
    chapter: Chapter,
    *,
    run_id: Optional[str],
    reason: str,
    task_status: Optional[str],
) -> str:
    """保留 run_id/事件历史，把章节标成"可重试"而不是抹掉全部运行信息。"""
    payload = _load_runtime_state(chapter)
    runtime = payload.get("generation_runtime")
    runtime = dict(runtime) if isinstance(runtime, dict) else {}
    events = runtime.get("events") if isinstance(runtime.get("events"), list) else []
    now_iso = _now_iso()
    runtime.update(
        {
            "run_id": run_id or runtime.get("run_id"),
            "cancel_requested": False,
            "progress_stage": "interrupted",
            "progress_message": reason,
            "reason": reason,
            "recovered_from_restart": True,
            "task_status": task_status,
            "allowed_actions": ["refresh_status", "retry_generation"],
            "updated_at": now_iso,
            "heartbeat_at": now_iso,
            "estimated_remaining_seconds": 0,
            "chapter_number": chapter.chapter_number,
            "events": [
                *events[-199:],
                {
                    "at": now_iso,
                    "stage": "interrupted",
                    "level": "warning",
                    "message": reason,
                },
            ],
        }
    )
    payload["generation_runtime"] = runtime
    return json.dumps(payload, ensure_ascii=False)


class TaskReconciliationService:
    """把重启恢复、僵尸任务清理收敛到一处，供 lifespan 与巡检共用。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.runtime = TaskRuntimeService(session)

    async def reconcile(self, *, stale_after_seconds: int = 180) -> ReconciliationReport:
        report = ReconciliationReport()
        stale_tasks = await self.runtime.mark_stale(stale_after_seconds=stale_after_seconds)
        report.stale_task_ids = [task.task_id for task in stale_tasks]
        await self._release_orphaned_busy_chapters(report)
        return report

    async def _load_chapter_task(self, chapter: Chapter) -> Optional[TaskRuntime]:
        run_id = _chapter_run_id(chapter)
        if run_id:
            found = (
                await self.session.execute(select(TaskRuntime).where(TaskRuntime.task_id == run_id))
            ).scalar_one_or_none()
            if found is not None:
                return found
        result = await self.session.execute(
            select(TaskRuntime)
            .where(
                TaskRuntime.task_type.in_(list(CHAPTER_GENERATION_TASK_TYPES)),
                TaskRuntime.chapter_id == str(chapter.id),
            )
            .order_by(TaskRuntime.updated_at.desc(), TaskRuntime.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _release_orphaned_busy_chapters(self, report: ReconciliationReport) -> None:
        result = await self.session.execute(
            select(Chapter).where(Chapter.status.in_(list(BUSY_CHAPTER_STATUSES)))
        )
        chapters = list(result.scalars().all())
        if not chapters:
            return

        changed = False
        for chapter in chapters:
            task = await self._load_chapter_task(chapter)
            if task is not None and task.status not in TERMINAL_STATUSES:
                # 任务仍持有活跃租约或排队中：交给心跳/租约判定，不在此处误杀。
                report.preserved_chapter_ids.append(chapter.id)
                continue

            task_status = task.status if task is not None else None
            reason = (
                f"服务重启后检测到任务已处于终态（{task_status}），章节已释放为可重试状态"
                if task_status
                else "服务重启后未找到该章节的持久化任务记录，章节已释放为可重试状态"
            )
            chapter.status = ChapterGenerationStatus.FAILED.value
            chapter.real_summary = _build_released_runtime_state(
                chapter,
                run_id=task.task_id if task is not None else _chapter_run_id(chapter),
                reason=reason,
                task_status=task_status,
            )
            self.session.add(chapter)
            report.released_chapter_ids.append(chapter.id)
            changed = True

        if changed:
            await self.session.commit()
