# AIMETA P=生成日志路由_持久化实时流式API|R=日志查询_实时流|NR=不含正文内容|E=route:GET_/api/updates/*|X=http|A=日志路由|D=fastapi,sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.task_runtime import TaskRuntimeEvent
from ...schemas.admin import UpdateLogRead
from ...schemas.task_runtime import TaskRuntimeEventType
from ...schemas.user import UserInDB
from ...services.persistent_generation_log_service import get_persistent_generation_log_service
from ...services.task_runtime import (
    TERMINAL_STATUSES,
    TaskRuntimeError,
    TaskRuntimeNotFound,
    TaskRuntimeService,
)
from ...services.update_log_service import UpdateLogService

router = APIRouter(prefix="/api/updates", tags=["Updates"])
logger = logging.getLogger(__name__)


_LOG_STREAM_EXCLUDED_EVENT_TYPES = {TaskRuntimeEventType.CONTENT_DELTA.value}


def _is_log_stream_event(event_type: str) -> bool:
    """正文 content_delta 不得进入运行日志流；其余事件均可回放。"""
    return event_type not in _LOG_STREAM_EXCLUDED_EVENT_TYPES


def _sse_frame(event: str, data: dict, *, event_id: int | None = None) -> str:
    """统一 SSE frame：显式事件名、稳定游标、JSON 信封。"""
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False, default=str)}")
    return "\n".join(lines) + "\n\n"


def _stream_sse_envelope(event: TaskRuntimeEvent) -> dict:
    """把持久化事件投影为统一 envelope，兼容旧事件并保持频道/序号稳定。"""
    payload = event.payload or {}
    return {
        "task_id": event.task_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "status": event.status,
        "stage": event.stage,
        "progress": event.progress,
        "message": event.message or "",
        "timestamp": event.created_at.isoformat() if event.created_at else None,
        "channel": payload.get("channel") or TaskRuntimeService.event_channel(event.event_type),
        "event_sequence": payload.get("event_sequence", event.event_id),
        "payload": payload,
        "level": "info",
        "metadata": {},
    }

def _resolve_stream_cursor(after_event_id: int = 0, last_event_id: int | None = None) -> int:
    """Merge explicit query and Last-Event-ID values for lossless reconnects."""
    return max(0, int(after_event_id or 0), int(last_event_id or 0))


def get_update_log_service(session: AsyncSession = Depends(get_session)) -> UpdateLogService:
    return UpdateLogService(session)


@router.get("/latest", response_model=List[UpdateLogRead])
async def read_latest_updates(
    service: UpdateLogService = Depends(get_update_log_service),
) -> List[UpdateLogRead]:
    logs = await service.list_logs(limit=5)
    return [UpdateLogRead.model_validate(log) for log in logs]


@router.get("/stream/tasks")
async def list_active_tasks(current_user: UserInDB = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        tasks = await get_persistent_generation_log_service().list_active(
            session, owner_user_id=int(current_user.id)
        )
    payload = [
        {
            "task_id": task.task_id,
            "status": task.status,
            "stage": task.stage,
            "progress": task.progress,
            "message": task.message,
            "event_cursor": task.event_cursor,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
        for task in tasks
    ]
    return {"tasks": payload, "total": len(payload)}




@router.get("/stream/{task_id}")
async def stream_generation_logs(
    task_id: str,
    after_event_id: int = Query(default=0, ge=0),
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID", ge=0),
    current_user: UserInDB = Depends(get_current_user),
):
    """从 TaskRuntime 持久化事件流读取日志，支持 Last-Event-ID 断线续接。"""
    owner_id = int(current_user.id)
    async with AsyncSessionLocal() as session:
        try:
            await get_persistent_generation_log_service().ensure_task(
                session, task_id, owner_user_id=owner_id, create_if_missing=False
            )
        except TaskRuntimeError as exc:
            raise HTTPException(status_code=404, detail="日志任务不存在") from exc

    async def event_generator():
        # The explicit query is useful for fetch-based clients; the header is the browser SSE standard.
        cursor = _resolve_stream_cursor(after_event_id, last_event_id)
        last_heartbeat = time.monotonic()
        while True:
            async with AsyncSessionLocal() as session:
                service = get_persistent_generation_log_service()
                try:
                    task = await service.ensure_task(
                        session, task_id, owner_user_id=owner_id, create_if_missing=False
                    )
                    result = await session.execute(
                        select(TaskRuntimeEvent)
                        .where(
                            TaskRuntimeEvent.task_id == task_id,
                            TaskRuntimeEvent.event_id > cursor,
                            TaskRuntimeEvent.event_type.not_in(list(_LOG_STREAM_EXCLUDED_EVENT_TYPES)),
                        )
                        .order_by(TaskRuntimeEvent.event_id)
                        .limit(500)
                    )
                    events = list(result.scalars().all())
                except TaskRuntimeError:
                    break
            for event in events:
                cursor = max(cursor, event.event_id)
                data = _stream_sse_envelope(event)
                payload = event.payload or {}
                data["level"] = payload.get("level", "info")
                data["metadata"] = {
                    **(payload.get("metadata") or {}),
                    "event_type": event.event_type,
                    "status": event.status,
                }
                yield _sse_frame(event.event_type, data, event_id=event.event_id)
            if task.status in TERMINAL_STATUSES and not events:
                break
            if time.monotonic() - last_heartbeat >= 15:
                yield ": keepalive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/stream/{task_id}/log")
async def append_generation_log(
    task_id: str,
    message: str = Query(..., description="日志消息"),
    level: str = Query(default="info", description="日志级别"),
    current_user: UserInDB = Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        try:
            task = await get_persistent_generation_log_service().append(
                session, task_id, owner_user_id=int(current_user.id), message=message, level=level
            )
        except TaskRuntimeNotFound as exc:
            raise HTTPException(status_code=404, detail="日志任务不存在") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "task_id": task.task_id, "status": task.status, "event_cursor": task.event_cursor}


@router.post("/stream/{task_id}/complete")
async def complete_generation_task(
    task_id: str,
    current_user: UserInDB = Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        try:
            task = await get_persistent_generation_log_service().complete(
                session, task_id, owner_user_id=int(current_user.id)
            )
        except TaskRuntimeError as exc:
            raise HTTPException(status_code=404, detail="日志任务不存在") from exc
    return {"success": True, "task_id": task_id, "status": task.status}


@router.post("/stream/create")
async def create_generation_task(
    task_id: str = Query(default=None, description="可选自定义 task_id"),
    current_user: UserInDB = Depends(get_current_user),
):
    tid = task_id or f"generation-log-{int(time.time() * 1000)}"
    async with AsyncSessionLocal() as session:
        try:
            task = await get_persistent_generation_log_service().ensure_task(
                session, tid, owner_user_id=int(current_user.id)
            )
        except TaskRuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task_id": task.task_id, "status": task.status}
