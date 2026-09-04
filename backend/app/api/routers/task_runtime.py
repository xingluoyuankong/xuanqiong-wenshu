"""通用任务运行时 API。"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import NovelProject
from ...models.project_member import ProjectMember
from ...models.task_runtime import TaskRuntime
from ...schemas.task_runtime import (
    TaskRuntimeClaim,
    TaskRuntimeCreate,
    TaskRuntimeEventCreate,
    TaskRuntimeEventRead,
    TaskRuntimeHeartbeat,
    TaskRuntimeProgressUpdate,
    TaskRuntimeRead,
    TaskRuntimeRetryRequest,
    TaskRuntimeMetrics,
)
from ...schemas.user import UserInDB
from ...services.project_access_service import ProjectAccessService
from ...services.task_runtime import TERMINAL_STATUSES, TaskRuntimeError, TaskRuntimeNotFound, TaskRuntimeService

router = APIRouter(prefix="/api/task-runtime", tags=["task-runtime"])


def _owner(user: UserInDB) -> int | None:
    return getattr(user, "id", None)


def _raise_runtime_error(exc: TaskRuntimeError) -> None:
    code = 404 if isinstance(exc, TaskRuntimeNotFound) else 409
    raise HTTPException(status_code=code, detail=str(exc)) from exc


async def _readable_task(
    session: AsyncSession,
    task_id: str,
    current_user: UserInDB,
):
    """Load a task and enforce project-member visibility without leaking projectless jobs."""
    task = await TaskRuntimeService(session).get_task(task_id)
    if task.project_id:
        await ProjectAccessService(session).require_project_read(task.project_id, current_user)
        return task, None
    if task.owner_user_id != int(current_user.id):
        raise TaskRuntimeNotFound(f"task {task_id} not found")
    return task, int(current_user.id)


async def _controllable_task(
    session: AsyncSession,
    task_id: str,
    current_user: UserInDB,
):
    """Load a task for user-facing controls while retaining execution ownership."""
    task = await TaskRuntimeService(session).get_task(task_id)
    if task.project_id:
        await ProjectAccessService(session).require_project_write(task.project_id, current_user)
        return task
    if task.owner_user_id != int(current_user.id):
        raise TaskRuntimeNotFound(f"task {task_id} not found")
    return task


async def _list_visible_tasks(
    session: AsyncSession,
    current_user: UserInDB,
    *,
    project_id: str | None,
    chapter_id: str | None,
    statuses: list[str] | None,
    limit: int,
) -> list[TaskRuntime]:
    """Return shared project tasks plus only the caller's projectless tasks."""
    uid = int(current_user.id)
    if project_id is not None:
        await ProjectAccessService(session).require_project_read(project_id, current_user)
        visibility = TaskRuntime.project_id == project_id
    elif ProjectAccessService.is_admin(current_user):
        visibility = or_(
            TaskRuntime.project_id.is_not(None),
            and_(TaskRuntime.project_id.is_(None), TaskRuntime.owner_user_id == uid),
        )
    else:
        visible_projects = (
            select(NovelProject.id)
            .outerjoin(ProjectMember, ProjectMember.project_id == NovelProject.id)
            .where(
                or_(
                    NovelProject.user_id == uid,
                    and_(ProjectMember.user_id == uid, ProjectMember.deleted_at.is_(None)),
                )
            )
        )
        visibility = or_(
            and_(TaskRuntime.project_id.is_(None), TaskRuntime.owner_user_id == uid),
            TaskRuntime.project_id.in_(visible_projects),
        )

    conditions = [visibility]
    if chapter_id is not None:
        conditions.append(TaskRuntime.chapter_id == chapter_id)
    if statuses:
        conditions.append(TaskRuntime.status.in_(list(statuses)))
    result = await session.execute(
        select(TaskRuntime)
        .where(*conditions)
        .order_by(TaskRuntime.updated_at.desc())
        .limit(min(max(int(limit), 1), 500))
    )
    return list(result.scalars().all())


@router.post("/tasks", response_model=TaskRuntimeRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: TaskRuntimeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    if request.project_id:
        try:
            access = await ProjectAccessService(session).require_project_read(
                request.project_id, current_user
            )
        except HTTPException as exc:
            # Preserve the historical resource-hiding contract for a principal
            # with no relationship to the project; a visible read-only member
            # still receives the explicit 403 write denial below.
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在或无权访问"},
                ) from exc
            raise
        if not access.can_write:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前项目为只读成员")
    try:
        return await TaskRuntimeService(session).create_task(
            task_type=request.task_type,
            idempotency_key=request.idempotency_key,
            actor_user_id=_owner(current_user),
            execution_owner_id=_owner(current_user),
            input_hash=request.input_hash,
            config_snapshot_id=request.config_snapshot_id,
            artifact_ref=request.artifact_ref,
            artifact_revision=request.artifact_revision,
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            payload=request.payload,
            max_retries=request.max_retries,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.get("/tasks", response_model=list[TaskRuntimeRead])
async def list_tasks(
    project_id: Annotated[str | None, Query(max_length=64)] = None,
    chapter_id: Annotated[str | None, Query(max_length=64)] = None,
    task_status: Annotated[str | None, Query(alias="status", max_length=24)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[TaskRuntimeRead]:
    statuses = [task_status] if task_status else None
    return await _list_visible_tasks(
        session,
        current_user,
        project_id=project_id,
        chapter_id=chapter_id,
        statuses=statuses,
        limit=limit,
    )


@router.get("/tasks/{task_id}/stream")
async def stream_task_events(
    task_id: str,
    request: Request,
    after_event_id: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StreamingResponse:
    """持久化任务事件 SSE：支持断线游标回放、心跳和终态自动收口。"""
    try:
        _task, owner_user_id = await _readable_task(session, task_id, current_user)
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)

    async def event_generator():
        cursor = max(after_event_id, int(last_event_id or 0))
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            async with AsyncSessionLocal() as session:
                service = TaskRuntimeService(session)
                try:
                    task = await service.get_task(task_id, owner_user_id)
                    if task.project_id:
                        await ProjectAccessService(session).require_project_read(task.project_id, current_user)
                        event_owner = None
                    else:
                        event_owner = owner_user_id
                    events = await service.list_events(
                        task_id,
                        after_event_id=cursor,
                        limit=500,
                        owner_user_id=event_owner,
                    )
                except (TaskRuntimeError, HTTPException):
                    break
            for event in events:
                cursor = max(cursor, event.event_id)
                payload = {
                    "event_id": event.event_id,
                    "task_id": event.task_id,
                    "event_type": event.event_type,
                    "status": event.status,
                    "stage": event.stage,
                    "progress": event.progress,
                    "message": event.message,
                    "payload": event.payload or {},
                    "channel": (event.payload or {}).get("channel"),
                    "event_sequence": (event.payload or {}).get("event_sequence", event.event_id),
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                }
                yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
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


@router.get("/tasks/{task_id}", response_model=TaskRuntimeRead)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task, _owner_filter = await _readable_task(session, task_id, current_user)
        return task
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.get("/tasks/{task_id}/events", response_model=list[TaskRuntimeEventRead])
async def list_task_events(
    task_id: str,
    after_event_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[TaskRuntimeEventRead]:
    try:
        _task, owner_filter = await _readable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).list_events(
            task_id, after_event_id=after_event_id, limit=limit, owner_user_id=owner_filter
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/claim", response_model=TaskRuntimeRead)
async def claim_task(
    task_id: str,
    request: TaskRuntimeClaim,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).claim(
            task_id,
            lease_owner=request.lease_owner,
            stale_after_seconds=request.stale_after_seconds,
            owner_user_id=task.owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/recover", response_model=TaskRuntimeRead)
async def recover_task(
    task_id: str,
    request: TaskRuntimeClaim,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    """在进程重启/心跳超时后，通过持久化租约恢复任务。"""
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).recover(
            task_id,
            lease_owner=request.lease_owner,
            stale_after_seconds=request.stale_after_seconds,
            owner_user_id=task.owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/metrics", response_model=TaskRuntimeRead)
async def update_task_metrics(
    task_id: str,
    request: TaskRuntimeMetrics,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).update_metrics(
            task_id,
            elapsed_ms=request.elapsed_ms,
            input_tokens=request.input_tokens,
            output_tokens=request.output_tokens,
            total_tokens=request.total_tokens,
            owner_user_id=task.owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/stale/reconcile", response_model=list[TaskRuntimeRead])
async def reconcile_stale_tasks(
    stale_after_seconds: Annotated[int, Query(ge=1, le=86400)] = 120,
    project_id: str | None = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[TaskRuntimeRead]:
    try:
        if project_id is not None:
            await ProjectAccessService(session).require_project_write(project_id, current_user)
            owner_user_id = None
        else:
            owner_user_id = _owner(current_user)
        return await TaskRuntimeService(session).mark_stale(
            stale_after_seconds=stale_after_seconds,
            project_id=project_id,
            owner_user_id=owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/progress", response_model=TaskRuntimeRead)
async def update_task_progress(
    task_id: str,
    request: TaskRuntimeProgressUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).update_progress(
            task_id,
            progress=request.progress,
            stage=request.stage,
            message=request.message,
            payload=request.payload,
            attempt=request.attempt,
            lease_owner=request.lease_owner,
            lease_generation=request.lease_generation,
            owner_user_id=task.owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/heartbeat", response_model=TaskRuntimeRead)
async def heartbeat_task(
    task_id: str,
    request: TaskRuntimeHeartbeat,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).heartbeat(
            task_id,
            lease_owner=request.lease_owner,
            lease_generation=request.lease_generation,
            attempt=request.attempt,
            message=request.message,
            owner_user_id=_owner(current_user),
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/cancel", response_model=TaskRuntimeRead)
async def cancel_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).request_cancel(
            task_id, owner_user_id=task.owner_user_id, finalize_unclaimed=True
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/retry", response_model=TaskRuntimeRead)
async def retry_task(
    task_id: str,
    request: TaskRuntimeRetryRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).retry(
            task_id,
            idempotency_key=request.idempotency_key,
            message=request.message,
            owner_user_id=task.owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)


@router.post("/tasks/{task_id}/events", response_model=TaskRuntimeRead)
async def append_task_event(
    task_id: str,
    request: TaskRuntimeEventCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> TaskRuntimeRead:
    try:
        task = await _controllable_task(session, task_id, current_user)
        return await TaskRuntimeService(session).append_event(
            task_id,
            event_type=request.event_type.value,
            status=request.status.value if request.status else None,
            stage=request.stage,
            progress=request.progress,
            message=request.message,
            idempotency_key=request.idempotency_key,
            attempt=request.attempt,
            lease_owner=request.lease_owner,
            lease_generation=request.lease_generation,
            payload=request.payload,
            owner_user_id=task.owner_user_id,
        )
    except TaskRuntimeError as exc:
        _raise_runtime_error(exc)
