from __future__ import annotations

import asyncio
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

router = APIRouter(prefix="/api/projects/{project_id}/research", tags=["Project Research"])
_RESEARCH_TASKS: Dict[str, asyncio.Task[Any]] = {}
_RESEARCH_JOBS: Dict[str, Dict[str, Any]] = {}
_RESEARCH_TASK_LOCK = asyncio.Lock()


async def _run_research_job(run_id: str, project_id: str, user_id: int, payload: ResearchRunRequest) -> None:
    task = asyncio.current_task()
    if task is None:
        return
    async with _RESEARCH_TASK_LOCK:
        job = _RESEARCH_JOBS.get(run_id)
        if not job or job.get("status") == "cancelled":
            return
        _RESEARCH_TASKS[run_id] = task
        job["status"] = "running"
    try:
        async with AsyncSessionLocal() as session:
            service = ProjectResearchService(session)
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
        async with _RESEARCH_TASK_LOCK:
            job = _RESEARCH_JOBS.get(run_id)
            if job and job.get("status") != "cancelled":
                job["status"] = artifact.status
                job["artifact"] = artifact
    except ResearchConsentRequired as exc:
        async with _RESEARCH_TASK_LOCK:
            _RESEARCH_JOBS[run_id].update(status="failed", error=str(exc))
    except asyncio.CancelledError:
        async with _RESEARCH_TASK_LOCK:
            if run_id in _RESEARCH_JOBS:
                _RESEARCH_JOBS[run_id]["status"] = "cancelled"
        raise
    except Exception as exc:
        async with _RESEARCH_TASK_LOCK:
            _RESEARCH_JOBS[run_id].update(status="failed", error=str(exc)[:500])
    finally:
        async with _RESEARCH_TASK_LOCK:
            if _RESEARCH_TASKS.get(run_id) is task:
                _RESEARCH_TASKS.pop(run_id, None)


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
    async with _RESEARCH_TASK_LOCK:
        _RESEARCH_JOBS[run_id] = job
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
        if job and job.get("project_id") == project_id:
            return _job_read(dict(job))
    service = ProjectResearchService(session)
    artifact = await service.get_artifact(project_id, run_id)
    if artifact and artifact.status in {"queued", "running"}:
        artifact = await service.mark_artifact_interrupted(project_id, run_id)
    if artifact:
        return ResearchJobRead(
            run_id=run_id, project_id=project_id, scope=artifact.scope,
            chapter_number=artifact.chapter_number, status=artifact.status, artifact=artifact,
        )
    raise HTTPException(status_code=404, detail="研究任务不存在")


@router.post("/run/{run_id}/cancel", response_model=ResearchJobRead)
async def cancel_research_job(
    project_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ResearchJobRead:
    await _ensure_owner(project_id, session, current_user)
    async with _RESEARCH_TASK_LOCK:
        job = _RESEARCH_JOBS.get(run_id)
        if job and job.get("project_id") == project_id:
            task = _RESEARCH_TASKS.get(run_id)
            cancelled = bool(task and not task.done())
            job["status"] = "cancelled"
            job["cancel_signal_sent"] = cancelled
            job["in_process_task_cancelled"] = cancelled
            snapshot = dict(job)
        else:
            task = None
            cancelled = False
            snapshot = None
    if cancelled and task:
        task.cancel()
    service = ProjectResearchService(session)
    artifact = await service.get_artifact(project_id, run_id)
    if snapshot is None:
        if not artifact:
            raise HTTPException(status_code=404, detail="研究任务不存在")
        if artifact.status not in {"queued", "running"}:
            return ResearchJobRead(
                run_id=run_id, project_id=project_id, scope=artifact.scope,
                chapter_number=artifact.chapter_number, status=artifact.status, artifact=artifact,
            )
        snapshot = {
            "run_id": run_id, "project_id": project_id, "scope": artifact.scope,
            "chapter_number": artifact.chapter_number, "status": "cancelled",
            "artifact": artifact, "cancel_signal_sent": False,
            "in_process_task_cancelled": False,
        }
    cancelled_artifact = await service.mark_artifact_cancelled(project_id, run_id)
    if cancelled_artifact:
        snapshot["artifact"] = cancelled_artifact
    return _job_read(snapshot)