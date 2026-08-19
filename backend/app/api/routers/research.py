from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...schemas.research import ResearchArtifactRead, ResearchConfigRead, ResearchConfigUpdate, ResearchJobRead, ResearchRunRequest
from ...schemas.user import UserInDB
from ...services.novel_service import NovelService
from ...services.research_service import ProjectResearchService, ResearchConsentRequired
from ...services.task_runtime import TaskRuntimeConflict, TaskRuntimeError, TaskRuntimeNotFound, TaskRuntimeService
from ...schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus

router = APIRouter(prefix="/api/projects/{project_id}/research", tags=["Project Research"])
logger = logging.getLogger(__name__)
_RESEARCH_TASKS: Dict[str, asyncio.Task[Any]] = {}
_RESEARCH_JOBS: Dict[str, Dict[str, Any]] = {}
_RESEARCH_TASK_LOCK = asyncio.Lock()
# 已请求取消或已取消：worker 不得再推进，也不得把状态改回 running。
_RESEARCH_CANCEL_STATUSES = {TaskRuntimeStatus.CANCELLING.value, TaskRuntimeStatus.CANCELLED.value}
_RESEARCH_SCHEDULED_RUNS: set[str] = set()
_RESEARCH_HEARTBEAT_SECONDS = 30
_RESEARCH_LEASE_OWNER = f"research-worker:{uuid.uuid4().hex}"


class _ResearchRuntimeDetached(RuntimeError):
    """持久化任务已丢失或归属不匹配，worker 必须立即停止。"""


def _runtime_matches_research(task: Any, project_id: str) -> bool:
    return (
        str(getattr(task, "project_id", "") or "") == str(project_id)
        and str(getattr(task, "task_type", "") or "") == "research"
    )


async def _runtime_event(session: AsyncSession, run_id: str, *, event_type: str, status: str | None = None, stage: str | None = None, progress: float | None = None, message: str | None = None) -> bool:
    """把研究任务状态写入统一任务事件流；测试替身没有数据库接口时保持兼容。"""
    if not hasattr(session, "execute"):
        return False
    try:
        await TaskRuntimeService(session).append_event(
            run_id,
            event_type=event_type,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
        )
        return True
    except TaskRuntimeError:
        logger.warning("研究任务 %s 的运行时事件写入失败", run_id, exc_info=True)
        return False


async def _claim_research_runtime(
    run_id: str, project_id: str, user_id: int,
) -> bool | None:
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            return None
        runtime = TaskRuntimeService(session)
        try:
            persisted = await runtime.get_task(run_id, int(user_id))
            if not _runtime_matches_research(persisted, project_id):
                return False
            await runtime.claim(
                run_id, lease_owner=_RESEARCH_LEASE_OWNER,
                owner_user_id=int(user_id), stale_after_seconds=120,
            )
            return True
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            return False


async def _research_is_cancelled(
    run_id: str, project_id: str, user_id: int,
) -> bool:
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            async with _RESEARCH_TASK_LOCK:
                job = _RESEARCH_JOBS.get(run_id)
                return bool(
                    job
                    and job.get("project_id") == project_id
                    and job.get("status") in _RESEARCH_CANCEL_STATUSES
                )
        try:
            task = await TaskRuntimeService(session).get_task(run_id, int(user_id))
        except TaskRuntimeNotFound as exc:
            raise _ResearchRuntimeDetached(f"research runtime {run_id} is missing") from exc
        if not _runtime_matches_research(task, project_id):
            raise _ResearchRuntimeDetached(
                f"research runtime {run_id} does not belong to project {project_id}"
            )
        return task.status in _RESEARCH_CANCEL_STATUSES


async def _research_heartbeat(
    run_id: str, project_id: str, user_id: int, message: str,
) -> None:
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            return
        runtime = TaskRuntimeService(session)
        try:
            persisted = await runtime.get_task(run_id, int(user_id))
            if not _runtime_matches_research(persisted, project_id):
                raise _ResearchRuntimeDetached(
                    f"research runtime {run_id} changed project ownership"
                )
            await runtime.heartbeat(
                run_id, lease_owner=_RESEARCH_LEASE_OWNER,
                owner_user_id=int(user_id), message=message,
            )
        except TaskRuntimeNotFound as exc:
            raise _ResearchRuntimeDetached(f"research runtime {run_id} is missing") from exc
        except TaskRuntimeConflict as exc:
            raise _ResearchRuntimeDetached(f"research runtime {run_id} lease was lost") from exc


async def _schedule_research_recovery_now(
    run_id: str, project_id: str, user_id: int, payload: ResearchRunRequest,
) -> None:
    async with _RESEARCH_TASK_LOCK:
        if run_id in _RESEARCH_SCHEDULED_RUNS or run_id in _RESEARCH_TASKS:
            return
        _RESEARCH_SCHEDULED_RUNS.add(run_id)
    asyncio.create_task(_run_research_job(run_id, project_id, user_id, payload))


async def _run_research_job(run_id: str, project_id: str, user_id: int, payload: ResearchRunRequest) -> None:
    task = asyncio.current_task()
    if task is None:
        return
    async with _RESEARCH_TASK_LOCK:
        job = _RESEARCH_JOBS.get(run_id)
    runtime_backed = await _claim_research_runtime(run_id, project_id, user_id)
    if runtime_backed is False:
        return
    async with _RESEARCH_TASK_LOCK:
        job = _RESEARCH_JOBS.get(run_id)
        # 持久化任务已被成功领取后，进程内字典可能因重启为空；此时不得退出。
        # 仅旧兼容任务（没有 TaskRuntime）仍需要依赖本地快照继续执行。
        if runtime_backed is None and (
            not job or job.get("status") in _RESEARCH_CANCEL_STATUSES
        ):
            return
        _RESEARCH_TASKS[run_id] = task
        if runtime_backed is None:
            job["status"] = "running"
    runtime_detached = False

    async def heartbeat() -> None:
        nonlocal runtime_detached
        while True:
            await asyncio.sleep(_RESEARCH_HEARTBEAT_SECONDS)
            try:
                if await _research_is_cancelled(run_id, project_id, user_id):
                    task.cancel()
                    return
                await _research_heartbeat(
                    run_id, project_id, user_id, "研究任务进行中"
                )
            except _ResearchRuntimeDetached:
                runtime_detached = True
                task.cancel()
                return
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        if await _research_is_cancelled(run_id, project_id, user_id):
            raise asyncio.CancelledError()
        async with AsyncSessionLocal() as session:
            service = ProjectResearchService(session)
            started = await _runtime_event(session, run_id, event_type=TaskRuntimeEventType.TASK_STARTED.value, status=TaskRuntimeStatus.RUNNING.value, stage="research", progress=0.0, message="研究任务开始")
            if runtime_backed is True and not started:
                if await _research_is_cancelled(run_id, project_id, user_id):
                    raise asyncio.CancelledError()
                runtime_detached = True
                raise _ResearchRuntimeDetached(
                    f"research runtime {run_id} rejected the start event"
                )
            await service.touch_artifact_heartbeat(project_id, run_id, status="running")
            artifact = await service.run_research(
                project_id=project_id,
                user_id=user_id,
                scope=payload.scope,
                chapter_number=payload.chapter_number,
                consent=payload.consent,
                force=payload.force,
                trigger=payload.trigger,
                context=payload.context,
                run_id=run_id,
            )
        if await _research_is_cancelled(run_id, project_id, user_id):
            raise asyncio.CancelledError()
        async with AsyncSessionLocal() as runtime_session:
            completed = await _runtime_event(
                runtime_session,
                run_id,
                event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
                status=TaskRuntimeStatus.SUCCEEDED.value,
                stage="research",
                progress=100.0,
                message="研究任务完成",
            )
        if not completed:
            if await _research_is_cancelled(run_id, project_id, user_id):
                raise asyncio.CancelledError()
            runtime_detached = True
            raise _ResearchRuntimeDetached(
                f"research runtime {run_id} rejected the completion event"
            )
        async with _RESEARCH_TASK_LOCK:
            job = _RESEARCH_JOBS.get(run_id)
            if runtime_backed is None and job and job.get("status") not in _RESEARCH_CANCEL_STATUSES:
                job["status"] = artifact.status
                job["artifact"] = artifact
    except ResearchConsentRequired as exc:
        async with AsyncSessionLocal() as session:
            await _runtime_event(session, run_id, event_type=TaskRuntimeEventType.TASK_FAILED.value, status=TaskRuntimeStatus.FAILED.value, stage="research", message=str(exc))
        async with _RESEARCH_TASK_LOCK:
            if runtime_backed is None and run_id in _RESEARCH_JOBS:
                _RESEARCH_JOBS[run_id].update(status="failed", error=str(exc))
    except asyncio.CancelledError:
        if not runtime_detached:
            async with AsyncSessionLocal() as session:
                await _runtime_event(session, run_id, event_type=TaskRuntimeEventType.TASK_CANCELLED.value, status=TaskRuntimeStatus.CANCELLED.value, stage="research", message="研究任务已取消")
        try:
            async with AsyncSessionLocal() as artifact_session:
                artifact_service = ProjectResearchService(artifact_session)
                if runtime_detached:
                    await artifact_service.mark_artifact_interrupted(
                        project_id, run_id, force=True
                    )
                else:
                    await artifact_service.mark_artifact_cancelled(project_id, run_id)
        except Exception:
            logger.warning("研究任务 %s 停止后回写工件状态失败", run_id, exc_info=True)
        async with _RESEARCH_TASK_LOCK:
            if runtime_backed is None and run_id in _RESEARCH_JOBS:
                _RESEARCH_JOBS[run_id]["status"] = (
                    "failed" if runtime_detached else "cancelled"
                )
        raise
    except _ResearchRuntimeDetached:
        try:
            async with AsyncSessionLocal() as artifact_session:
                await ProjectResearchService(artifact_session).mark_artifact_interrupted(
                    project_id, run_id, force=True
                )
        except Exception:
            logger.warning("研究任务 %s 运行时丢失后回写失败", run_id, exc_info=True)
    except Exception as exc:
        async with AsyncSessionLocal() as session:
            await _runtime_event(session, run_id, event_type=TaskRuntimeEventType.TASK_FAILED.value, status=TaskRuntimeStatus.FAILED.value, stage="research", message=str(exc)[:500])
        async with _RESEARCH_TASK_LOCK:
            if runtime_backed is None and run_id in _RESEARCH_JOBS:
                _RESEARCH_JOBS[run_id].update(status="failed", error=str(exc)[:500])
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        async with _RESEARCH_TASK_LOCK:
            if _RESEARCH_TASKS.get(run_id) is task:
                _RESEARCH_TASKS.pop(run_id, None)
            _RESEARCH_SCHEDULED_RUNS.discard(run_id)


def _job_read(job: Dict[str, Any]) -> ResearchJobRead:
    return ResearchJobRead(
        run_id=job["run_id"], project_id=job["project_id"], scope=job["scope"],
        chapter_number=job.get("chapter_number"), status=job["status"],
        cancel_signal_sent=bool(job.get("cancel_signal_sent")),
        in_process_task_cancelled=bool(job.get("in_process_task_cancelled")),
        artifact=job.get("artifact"),
    )


async def _ensure_owner(project_id: str, session: AsyncSession, current_user: UserInDB) -> None:
    await NovelService(session).ensure_project_owner(project_id, current_user.id)


@router.get("/config", response_model=ResearchConfigRead)
async def get_research_config(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchConfigRead:
    await _ensure_owner(project_id, session, current_user)
    return await ProjectResearchService(session).read_config(project_id)


@router.put("/config", response_model=ResearchConfigRead)
async def update_research_config(
    project_id: str,
    payload: ResearchConfigUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchConfigRead:
    await _ensure_owner(project_id, session, current_user)
    return await ProjectResearchService(session).update_config(project_id, payload)


@router.get("/artifacts", response_model=List[ResearchArtifactRead])
async def list_research_artifacts(
    project_id: str,
    scope: Optional[str] = Query(default=None),
    chapter_number: Optional[int] = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[ResearchArtifactRead]:
    await _ensure_owner(project_id, session, current_user)
    return await ProjectResearchService(session).list_artifacts(
        project_id,
        scope=scope,
        chapter_number=chapter_number,
    )


@router.post("/run", response_model=ResearchArtifactRead)
async def run_research(
    project_id: str,
    payload: ResearchRunRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchArtifactRead:
    await _ensure_owner(project_id, session, current_user)
    try:
        return await ProjectResearchService(session).run_research(
            project_id=project_id,
            user_id=int(current_user.id),
            scope=payload.scope,
            chapter_number=payload.chapter_number,
            consent=payload.consent,
            force=payload.force,
            trigger=payload.trigger,
            context=payload.context,
        )
    except ResearchConsentRequired as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RESEARCH_CONSENT_REQUIRED",
                "message": str(exc),
                "retryable": True,
            },
        ) from exc

@router.post("/run/start", response_model=ResearchJobRead)
async def start_research_job(
    project_id: str,
    payload: ResearchRunRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchJobRead:
    await _ensure_owner(project_id, session, current_user)
    if payload.scope == "chapter" and not payload.chapter_number:
        raise HTTPException(status_code=400, detail="chapter scope requires chapter_number")
    config = await ProjectResearchService(session).get_or_create_config(project_id)
    should_run, reason = ProjectResearchService.should_run(config, payload.scope, consent=payload.consent, force=payload.force)
    if not should_run:
        if reason == "consent_required":
            raise HTTPException(status_code=409, detail={"code": "RESEARCH_CONSENT_REQUIRED", "message": "当前项目研究模式为每次询问，需要用户同意后才能联网检索"})
        raise HTTPException(status_code=409, detail={"code": "RESEARCH_DISABLED", "message": reason})
    service = ProjectResearchService(session)
    active = await service.get_active_artifact(project_id, payload.scope, payload.chapter_number)
    if active and active.status in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RESEARCH_ALREADY_RUNNING",
                "message": "相同项目和研究范围已有任务正在运行，请等待完成或先取消现有任务",
                "run_id": active.run_id,
                "status": active.status,
            },
        )
    run_id = str(uuid.uuid4())
    job = {
        "run_id": run_id, "project_id": project_id, "scope": payload.scope,
        "chapter_number": payload.chapter_number, "status": "queued", "artifact": None,
    }
    artifact = await service.create_pending_artifact(
        run_id=run_id, project_id=project_id, user_id=int(current_user.id),
        scope=payload.scope, chapter_number=payload.chapter_number, trigger=payload.trigger,
    )
    job["artifact"] = artifact
    if hasattr(session, "execute"):
        await TaskRuntimeService(session).create_task(
            task_id=run_id,
            task_type="research",
            idempotency_key=f"research:{project_id}:{payload.scope}:{payload.chapter_number or 0}:{run_id}",
            owner_user_id=int(current_user.id),
            project_id=project_id,
            chapter_id=str(payload.chapter_number) if payload.chapter_number else None,
            payload=payload.model_dump(mode="json"),
        )
    async with _RESEARCH_TASK_LOCK:
        _RESEARCH_JOBS[run_id] = job
    async with _RESEARCH_TASK_LOCK:
        _RESEARCH_SCHEDULED_RUNS.add(run_id)
    background_tasks.add_task(_run_research_job, run_id, project_id, int(current_user.id), payload)
    return _job_read(job)


@router.get("/run/{run_id}/status", response_model=ResearchJobRead)
async def get_research_job_status(
    project_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchJobRead:
    await _ensure_owner(project_id, session, current_user)
    async with _RESEARCH_TASK_LOCK:
        job = _RESEARCH_JOBS.get(run_id)
        in_memory = job if job and job.get("project_id") == project_id else None
    service = ProjectResearchService(session)
    artifact = await service.get_artifact(project_id, run_id)
    runtime_task = None
    db_backed = hasattr(session, "execute")
    if db_backed:
        try:
            runtime_task = await TaskRuntimeService(session).get_task(
                run_id, int(current_user.id)
            )
        except TaskRuntimeNotFound:
            runtime_task = None
        if runtime_task is not None and not _runtime_matches_research(
            runtime_task, project_id
        ):
            raise HTTPException(status_code=404, detail="研究任务不存在")
    if artifact and artifact.status in {"queued", "running"} and runtime_task is None:
        # 兼容未迁移的旧研究记录；新任务以 TaskRuntime 为恢复真相源。
        artifact = await service.mark_artifact_interrupted(
            project_id, run_id, force=db_backed
        )
    if runtime_task is not None and runtime_task.status in {
        TaskRuntimeStatus.QUEUED.value, TaskRuntimeStatus.STALE.value,
    }:
        try:
            recovery_payload = ResearchRunRequest.model_validate(runtime_task.payload or {})
        except Exception:
            recovery_payload = None
        if recovery_payload is not None:
            await _schedule_research_recovery_now(
                run_id, project_id, int(current_user.id), recovery_payload
            )
    if artifact:
        # TaskRuntime 是状态真相源；内存字典仅用于持有 asyncio.Task 句柄。
        # 进程重启后内存为空，这条路径也能正确返回持久化状态。
        # 新任务的状态只能来自持久化 TaskRuntime；兼容旧记录时才使用工件状态。
        # 内存快照可能停留在 queued/running，绝不能覆盖数据库中的真实工件状态。
        effective_status = runtime_task.status if runtime_task is not None else artifact.status
        return ResearchJobRead(
            run_id=run_id, project_id=project_id, scope=artifact.scope,
            chapter_number=artifact.chapter_number,
            status=effective_status,
            artifact=artifact,
        )

    if runtime_task is not None:
        runtime_payload = runtime_task.payload or {}
        return ResearchJobRead(
            run_id=run_id,
            project_id=project_id,
            scope=str(runtime_payload.get("scope") or "global"),
            chapter_number=runtime_payload.get("chapter_number"),
            status=runtime_task.status,
            artifact=None,
        )

    if in_memory is not None and not db_backed:
        return _job_read(dict(in_memory))

    raise HTTPException(status_code=404, detail="研究任务不存在")


@router.post("/run/{run_id}/cancel", response_model=ResearchJobRead)
async def cancel_research_job(
    project_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchJobRead:
    await _ensure_owner(project_id, session, current_user)
    service = ProjectResearchService(session)
    artifact = await service.get_artifact(project_id, run_id)
    runtime_task = None
    db_backed = hasattr(session, "execute")
    if db_backed:
        runtime = TaskRuntimeService(session)
        try:
            persisted = await runtime.get_task(run_id, int(current_user.id))
        except TaskRuntimeNotFound:
            persisted = None
        if persisted is not None:
            if not _runtime_matches_research(persisted, project_id):
                raise HTTPException(status_code=404, detail="研究任务不存在")
            runtime_task = await runtime.request_cancel(
                run_id,
                owner_user_id=int(current_user.id),
                finalize_unclaimed=True,
            )
        elif artifact is None:
            raise HTTPException(status_code=404, detail="研究任务不存在")
    async with _RESEARCH_TASK_LOCK:
        job = _RESEARCH_JOBS.get(run_id)
        if job and job.get("project_id") == project_id:
            task = _RESEARCH_TASKS.get(run_id)
            cancelled = bool(task and not task.done())
            # TaskRuntime 是对外真相源；本地字典只同步其快照并保存协作取消句柄。
            # 旧任务没有 runtime 时才保留历史兼容行为。
            job["status"] = (
                runtime_task.status
                if runtime_task is not None
                else (TaskRuntimeStatus.CANCELLING.value if cancelled else "cancelled")
            )
            job["cancel_signal_sent"] = cancelled
            job["in_process_task_cancelled"] = cancelled
            snapshot = dict(job)
        else:
            task = None
            cancelled = False
            snapshot = None
    if cancelled and task:
        task.cancel()
    if snapshot is None:
        if not artifact and runtime_task is None:
            raise HTTPException(status_code=404, detail="研究任务不存在")
        if runtime_task is not None:
            runtime_payload = runtime_task.payload or {}
            snapshot = {
                "run_id": run_id,
                "project_id": project_id,
                "scope": (artifact.scope if artifact else runtime_payload.get("scope", "global")),
                "chapter_number": (
                    artifact.chapter_number if artifact else runtime_payload.get("chapter_number")
                ),
                "status": runtime_task.status,
                "artifact": artifact,
                "cancel_signal_sent": False,
                "in_process_task_cancelled": False,
            }
        elif artifact.status not in {"queued", "running"}:
            return ResearchJobRead(
                run_id=run_id, project_id=project_id, scope=artifact.scope,
                chapter_number=artifact.chapter_number, status=artifact.status, artifact=artifact,
            )
        else:
            snapshot = {
                "run_id": run_id, "project_id": project_id, "scope": artifact.scope,
                "chapter_number": artifact.chapter_number, "status": "cancelled",
                "artifact": artifact, "cancel_signal_sent": False,
                "in_process_task_cancelled": False,
            }
    if snapshot["status"] == TaskRuntimeStatus.CANCELLING.value:
        # 进程内 worker 尚未收敛，不提前把工件写成终态，避免与实际执行分叉。
        if artifact is not None:
            snapshot["artifact"] = artifact
    elif snapshot["status"] == TaskRuntimeStatus.CANCELLED.value:
        cancelled_artifact = await service.mark_artifact_cancelled(project_id, run_id)
        if cancelled_artifact:
            snapshot["artifact"] = cancelled_artifact
    return _job_read(snapshot)
