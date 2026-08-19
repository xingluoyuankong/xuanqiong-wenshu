# AIMETA P=风格学习路由_文风提取和注入API|R=风格提取_风格查询_风格删除|NR=不含业务逻辑|E=style|X=internal|A=路由端点|D=none|S=none|RD=./README.ai
"""
风格学习路由 (Style RAG Router)

提供写作风格学习相关的 API：
- POST /api/projects/{id}/style/extract - 从章节提取写作风格
- GET /api/projects/{id}/style - 获取项目当前风格配置
- DELETE /api/projects/{id}/style - 清除风格配置
- POST /api/projects/{id}/style/generate - 带风格上下文的生成
"""
import asyncio
import json
import logging
from pathlib import Path
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.style_rag_service import StyleRAGService, StyleFeature, StyleProfile
from ...services.novel_service import NovelService
from ...schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus
from ...services.task_runtime import TERMINAL_STATUSES, TaskRuntimeConflict, TaskRuntimeNotFound, TaskRuntimeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/style", tags=["style-rag"])

_STYLE_PROFILE_JOBS: Dict[str, Dict[str, Any]] = {}
_STYLE_PROFILE_PROJECT_RUNS: Dict[str, str] = {}
_STYLE_PROFILE_JOB_LOCK = asyncio.Lock()
_STYLE_PROFILE_ACTIVE_STATUSES = {"queued", "extracting", "profiling", "saving"}
_STYLE_PROFILE_HEARTBEAT_SECONDS = 30
_STYLE_SOURCE_UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
_STYLE_SOURCE_UPLOAD_PROJECT_RUNS: Dict[str, str] = {}
_STYLE_SOURCE_UPLOAD_JOB_LOCK = asyncio.Lock()
_STYLE_SOURCE_UPLOAD_ACTIVE_STATUSES = {"queued", "upload_reading", "upload_extracting", "upload_saving"}
_STYLE_SOURCE_UPLOAD_CANCELLABLE_STATUSES = {"queued", "upload_reading", "upload_extracting"}
_STYLE_SOURCE_UPLOAD_HEARTBEAT_SECONDS = 20
_STYLE_CANCEL_STATUSES = {"cancelling", "cancelled"}
_STYLE_RUNTIME_ACTIVE_STATUSES = {
    TaskRuntimeStatus.QUEUED.value,
    TaskRuntimeStatus.RUNNING.value,
    TaskRuntimeStatus.CANCELLING.value,
    TaskRuntimeStatus.STALE.value,
}
_STYLE_UPLOAD_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "style_uploads"


def _style_upload_path(project_id: str, run_id: str) -> Path:
    return _STYLE_UPLOAD_STORAGE_ROOT / project_id / f"{run_id}.bin"


def _validated_style_upload_path(
    project_id: str,
    run_id: str,
    storage_value: Any,
) -> Optional[Path]:
    """Validate a persisted upload path before it is read during recovery.

    TaskRuntime payloads are durable input and may outlive the process that
    created them.  Never trust a path copied from that payload: recovery must
    only read the canonical file for this project and run.
    """
    if not isinstance(storage_value, str) or not storage_value.strip():
        return None
    expected = _style_upload_path(str(project_id), str(run_id)).resolve()
    try:
        candidate = Path(storage_value).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if candidate != expected or not candidate.is_file():
        return None
    return candidate


_STYLE_LEASE_OWNER = f"style-worker:{uuid.uuid4().hex}"
_STYLE_SCHEDULED_RUNS: set[str] = set()
_STYLE_TASKS: Dict[str, asyncio.Task[Any]] = {}
_STYLE_RUNTIME_TASK_TYPES = {
    "style_profile": "style_profile_generation",
    "style_source_upload": "style_source_upload",
}


class _StyleRuntimeDetached(RuntimeError):
    """数据库任务缺失、归属变化或租约丢失时终止本地 worker。"""


class _StyleRuntimeCancellation(RuntimeError):
    """持久化任务进入取消态时触发协作取消。"""


def _style_runtime_matches(task: Any, project_id: str, domain: str) -> bool:
    return bool(
        getattr(task, "project_id", None) == project_id
        and getattr(task, "task_type", None) == _STYLE_RUNTIME_TASK_TYPES.get(domain)
    )


async def _claim_style_runtime(
    run_id: str, project_id: str, user_id: int, domain: str,
) -> bool | None:
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            return None
        runtime = TaskRuntimeService(session)
        try:
            persisted = await runtime.get_task(run_id, int(user_id))
            if not _style_runtime_matches(persisted, project_id, domain):
                return False
            await runtime.claim(
                run_id,
                lease_owner=_STYLE_LEASE_OWNER,
                owner_user_id=int(user_id),
                stale_after_seconds=120,
            )
            return True
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            return False


async def _style_runtime_cancelled(
    run_id: str, project_id: str, user_id: int, domain: str,
) -> bool:
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            lock = _STYLE_PROFILE_JOB_LOCK if domain == "style_profile" else _STYLE_SOURCE_UPLOAD_JOB_LOCK
            jobs = _STYLE_PROFILE_JOBS if domain == "style_profile" else _STYLE_SOURCE_UPLOAD_JOBS
            async with lock:
                job = jobs.get(run_id) or {}
                return bool(
                    job.get("project_id") == project_id
                    and str(job.get("status")) in _STYLE_CANCEL_STATUSES
                )
        try:
            task = await TaskRuntimeService(session).get_task(run_id, int(user_id))
        except TaskRuntimeNotFound as exc:
            raise _StyleRuntimeDetached(f"style runtime {run_id} is missing") from exc
        if not _style_runtime_matches(task, project_id, domain):
            raise _StyleRuntimeDetached(
                f"style runtime {run_id} does not belong to {project_id}/{domain}"
            )
        if task.status in {
            TaskRuntimeStatus.CANCELLING.value,
            TaskRuntimeStatus.CANCELLED.value,
        }:
            return True
        if task.status not in {
            TaskRuntimeStatus.QUEUED.value,
            TaskRuntimeStatus.RUNNING.value,
        }:
            raise _StyleRuntimeDetached(
                f"style runtime {run_id} is already terminal: {task.status}"
            )
        return False


async def _request_style_runtime_cancel(
    run_id: str,
    project_id: str,
    user_id: int,
    domain: str,
    *,
    session: Any = None,
) -> Optional[Any]:
    async def persist(runtime_session: Any) -> Optional[Any]:
        if not hasattr(runtime_session, "execute"):
            return None
        runtime = TaskRuntimeService(runtime_session)
        persisted = await runtime.get_task(run_id, int(user_id))
        if not _style_runtime_matches(persisted, project_id, domain):
            raise TaskRuntimeNotFound(f"style task {run_id} not found")
        return await runtime.request_cancel(
            run_id,
            owner_user_id=int(user_id),
            finalize_unclaimed=True,
        )

    if session is not None:
        if not hasattr(session, "execute"):
            return None
        return await persist(session)
    async with AsyncSessionLocal() as runtime_session:
        return await persist(runtime_session)


async def _style_runtime_heartbeat(
    run_id: str,
    project_id: str,
    user_id: int,
    domain: str,
    message: str,
) -> None:
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            return
        runtime = TaskRuntimeService(session)
        try:
            persisted = await runtime.get_task(run_id, int(user_id))
            if not _style_runtime_matches(persisted, project_id, domain):
                raise _StyleRuntimeDetached(
                    f"style runtime {run_id} changed project or task type"
                )
            await runtime.heartbeat(
                run_id,
                lease_owner=_STYLE_LEASE_OWNER,
                owner_user_id=int(user_id),
                message=message,
            )
        except TaskRuntimeNotFound as exc:
            raise _StyleRuntimeDetached(f"style runtime {run_id} is missing") from exc
        except TaskRuntimeConflict as exc:
            raise _StyleRuntimeDetached(f"style runtime {run_id} lease was lost") from exc


class ExtractStyleRequest(BaseModel):
    """风格提取请求"""
    chapter_numbers: List[int] = Field(..., description="要分析的章节号列表")


class ExtractStyleResponse(BaseModel):
    """风格提取响应"""
    success: bool
    message: str
    style_summary: Optional[dict] = None


class CreateStyleSourceRequest(BaseModel):
    """创建外部文风来源请求"""
    title: str = Field(..., min_length=1, max_length=100)
    content_text: str = Field(..., min_length=20)
    source_type: str = Field(default="external_text", pattern="^(external_text|external_novel)$")
    extra: Dict[str, Any] = Field(default_factory=dict)


class CreateStyleProfileRequest(BaseModel):
    """从来源创建或补全文风画像请求"""
    source_ids: List[str] = Field(..., min_length=1)
    name: Optional[str] = Field(default=None, max_length=100)
    append_to_profile_id: Optional[str] = Field(default=None, min_length=1)


class StyleProfileJobError(BaseModel):
    code: str
    message: str
    detail: Optional[str] = None
    retryable: bool = True


class StyleProfileJobResponse(BaseModel):
    run_id: str
    project_id: str
    status: str
    progress_stage: str = "queued"
    progress_message: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    error: Optional[StyleProfileJobError] = None


class StyleSourceUploadJobResponse(BaseModel):
    run_id: str
    project_id: str
    status: str
    progress_stage: str = "queued"
    progress_message: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    filename: Optional[str] = None
    source: Optional[Dict[str, Any]] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[StyleProfileJobError] = None


class ActivateStyleProfileRequest(BaseModel):
    """激活文风画像请求"""
    profile_id: str = Field(..., min_length=1)


class ApplyStyleProfileRequest(BaseModel):
    """应用文风画像请求"""
    profile_id: str = Field(..., min_length=1)
    scope: Literal["global", "project"] = Field(...)


class ClearStyleApplicationRequest(BaseModel):
    """清理文风应用请求"""
    scope: Literal["global", "project"] = Field(...)


class StyleGenerateRequest(BaseModel):
    """风格化生成请求"""
    existing_content: str = Field(..., description="已有内容")
    direction: str = Field(..., description="续写方向")
    max_tokens: int = Field(default=2000, ge=500, le=4000)


class StyleGenerateResponse(BaseModel):
    """风格化生成响应"""
    content: str
    style_applied: bool


class UpdateStyleProfileRequest(BaseModel):
    """更新文风画像请求"""
    name: Optional[str] = Field(default=None, max_length=100)
    summary: Optional[Dict[str, str]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class StyleSummaryResponse(BaseModel):
    """风格摘要响应"""
    has_style: bool
    summary: Optional[dict] = None
    source: Optional[dict] = None


def _style_job_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _style_job_error(code: str, message: str, *, detail: Any = None, retryable: bool = True) -> Dict[str, Any]:
    if detail is None:
        detail_text = None
    elif isinstance(detail, str):
        detail_text = detail[:800]
    else:
        try:
            detail_text = json.dumps(detail, ensure_ascii=False, default=str)[:800]
        except TypeError:
            detail_text = str(detail)[:800]
    return {"code": code, "message": message, "detail": detail_text, "retryable": retryable}


def _serialize_style_profile_job(job: Dict[str, Any]) -> StyleProfileJobResponse:
    return StyleProfileJobResponse(
        run_id=str(job.get("run_id") or ""),
        project_id=str(job.get("project_id") or ""),
        status=str(job.get("status") or "idle"),
        progress_stage=str(job.get("progress_stage") or job.get("status") or "idle"),
        progress_message=str(job.get("progress_message") or ""),
        started_at=job.get("started_at"),
        updated_at=job.get("updated_at"),
        profile=job.get("profile"),
        error=job.get("error"),
    )


def _serialize_style_source_upload_job(job: Dict[str, Any]) -> StyleSourceUploadJobResponse:
    return StyleSourceUploadJobResponse(
        run_id=str(job.get("run_id") or ""),
        project_id=str(job.get("project_id") or ""),
        status=str(job.get("status") or "idle"),
        progress_stage=str(job.get("progress_stage") or job.get("status") or "idle"),
        progress_message=str(job.get("progress_message") or ""),
        started_at=job.get("started_at"),
        updated_at=job.get("updated_at"),
        filename=job.get("filename"),
        source=job.get("source"),
        metrics=dict(job.get("metrics") or {}),
        error=job.get("error"),
    )


def _style_runtime_job_snapshot(job: Dict[str, Any], *, domain: str) -> Dict[str, Any]:
    """返回可写入 TaskRuntime 的小型响应快照，不保存上传正文或其他大对象。"""
    fields = (
        "run_id", "project_id", "user_id", "status", "progress_stage",
        "progress_message", "started_at", "updated_at", "filename", "source",
        "metrics", "profile", "error", "request",
    )
    snapshot = {key: job.get(key) for key in fields if key in job}
    snapshot["task_domain"] = domain
    return snapshot


def _style_runtime_datetime(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) else None


def _rebuild_style_job_from_runtime(task: Any, events: List[Any], *, domain: str) -> Dict[str, Any]:
    """用持久化任务和事件重建路由响应，供进程重启后恢复查询。"""
    task_payload = dict(getattr(task, "payload", None) or {})
    snapshot: Dict[str, Any] = {}
    for key in ("style_job", "job"):
        candidate = task_payload.get(key)
        if isinstance(candidate, dict):
            snapshot.update(candidate)

    for event in events:
        payload = dict(getattr(event, "payload", None) or {})
        candidate = payload.get("style_job") or payload.get("job")
        if isinstance(candidate, dict) and candidate.get("task_domain", domain) == domain:
            snapshot.update(candidate)
        elif payload.get("task_domain") == domain and payload.get("legacy_status"):
            snapshot["status"] = payload["legacy_status"]

    runtime_status = str(getattr(task, "status", "queued") or "queued")
    stage = str(snapshot.get("progress_stage") or getattr(task, "stage", None) or runtime_status)
    message = str(snapshot.get("progress_message") or getattr(task, "message", None) or "")
    active_statuses = _STYLE_PROFILE_ACTIVE_STATUSES | _STYLE_SOURCE_UPLOAD_ACTIVE_STATUSES
    if runtime_status == TaskRuntimeStatus.QUEUED.value:
        legacy_status = "queued"
    elif runtime_status == TaskRuntimeStatus.RUNNING.value:
        legacy_status = str(snapshot.get("status") or stage or "running")
        if legacy_status not in active_statuses:
            legacy_status = stage or "running"
    elif runtime_status == TaskRuntimeStatus.SUCCEEDED.value:
        legacy_status = "successful"
    elif runtime_status == TaskRuntimeStatus.CANCELLED.value:
        legacy_status = "cancelled"
    elif runtime_status == TaskRuntimeStatus.FAILED.value:
        legacy_status = "failed"
    else:
        legacy_status = "stale"

    snapshot.update({
        "run_id": str(snapshot.get("run_id") or getattr(task, "task_id", "")),
        "project_id": str(snapshot.get("project_id") or getattr(task, "project_id", "") or ""),
        "status": legacy_status,
        "progress_stage": stage,
        "progress_message": message,
        "started_at": snapshot.get("started_at") or _style_runtime_datetime(getattr(task, "started_at", None)),
        "updated_at": snapshot.get("updated_at") or _style_runtime_datetime(getattr(task, "updated_at", None)),
        "runtime_task_registered": True,
        "_runtime_status": runtime_status,
        "_runtime_payload": task_payload,
    })
    if legacy_status == "failed" and not snapshot.get("error"):
        snapshot["error"] = _style_job_error(
            f"{domain}_failed", "文风后台任务失败",
            detail=getattr(task, "error_detail", None), retryable=True,
        )
    if legacy_status == "cancelled" and not snapshot.get("error"):
        snapshot["error"] = _style_job_error(
            f"{domain}_cancelled", "文风后台任务已取消", retryable=True,
        )
    return snapshot


async def _load_persisted_style_job(
    session: Any, *, project_id: str, user_id: int, task_type: str,
    domain: str, run_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """从 TaskRuntime 查找并重建文风任务；不影响旧的内存任务路径。"""
    if not hasattr(session, "execute"):
        return None
    runtime = TaskRuntimeService(session)
    if run_id:
        try:
            task = await runtime.get_task(run_id, int(user_id))
        except TaskRuntimeNotFound:
            return None
        if task.project_id != project_id or task.task_type != task_type:
            return None
    else:
        tasks = await runtime.list_tasks(owner_user_id=int(user_id), project_id=project_id, limit=100)
        matching = [item for item in tasks if item.task_type == task_type]
        if not matching:
            return None
        task = matching[0]
    events = await runtime.list_events(task.task_id, owner_user_id=int(user_id), limit=500)
    return _rebuild_style_job_from_runtime(task, events, domain=domain)


async def _load_active_persisted_style_job(
    session: Any, *, project_id: str, user_id: int, task_type: str, domain: str,
) -> Optional[Dict[str, Any]]:
    """只返回仍占用该项目槽位的持久化文风任务。"""
    job = await _load_persisted_style_job(
        session,
        project_id=project_id,
        user_id=user_id,
        task_type=task_type,
        domain=domain,
    )
    if job and str(job.get("_runtime_status") or "") in _STYLE_RUNTIME_ACTIVE_STATUSES:
        return job
    return None


async def _append_style_task_runtime_event(
    job: Dict[str, Any],
    *,
    domain: str,
    session: Any = None,
    strict: bool = False,
) -> None:
    if not job.get("runtime_task_registered"):
        return
    run_id = str(job.get("run_id") or "")
    project_id = str(job.get("project_id") or "")
    user_id = job.get("user_id")
    if not run_id or not project_id or user_id is None:
        return
    status_raw = str(job.get("status") or "queued")
    terminal_map = {
        "successful": (TaskRuntimeStatus.SUCCEEDED.value, TaskRuntimeEventType.TASK_COMPLETED.value),
        "failed": (TaskRuntimeStatus.FAILED.value, TaskRuntimeEventType.TASK_FAILED.value),
        "cancelled": (TaskRuntimeStatus.CANCELLED.value, TaskRuntimeEventType.TASK_CANCELLED.value),
    }
    runtime_status, event_type = terminal_map.get(
        status_raw,
        (
            TaskRuntimeStatus.QUEUED.value
            if status_raw == "queued"
            else TaskRuntimeStatus.CANCELLING.value
            if status_raw == "cancelling"
            else TaskRuntimeStatus.RUNNING.value,
            TaskRuntimeEventType.PROGRESS.value,
        ),
    )

    async def persist(runtime_session: Any) -> None:
        service = TaskRuntimeService(runtime_session)
        persisted = await service.get_task(run_id, int(user_id))
        if not _style_runtime_matches(persisted, project_id, domain):
            raise _StyleRuntimeDetached(
                f"style runtime {run_id} changed project or task type"
            )
        if persisted.status in {
            TaskRuntimeStatus.CANCELLING.value,
            TaskRuntimeStatus.CANCELLED.value,
        } and runtime_status not in {
            TaskRuntimeStatus.CANCELLING.value,
            TaskRuntimeStatus.CANCELLED.value,
        }:
            raise _StyleRuntimeCancellation(
                f"style runtime {run_id} is cancelling"
            )
        await service.append_event(
            run_id,
            event_type=event_type,
            status=runtime_status,
            stage=str(job.get("progress_stage") or status_raw),
            progress=100.0 if runtime_status in TERMINAL_STATUSES else 0.0,
            message=str(job.get("progress_message") or ""),
            idempotency_key=f"style-state:{domain}:{job.get('updated_at') or _style_job_now_iso()}",
            payload={
                "task_domain": domain,
                "legacy_status": status_raw,
                "metrics": job.get("metrics") or {},
                "style_job": _style_runtime_job_snapshot(job, domain=domain),
            },
            owner_user_id=int(user_id),
        )

    try:
        if hasattr(session, "execute"):
            await persist(session)
        else:
            async with AsyncSessionLocal() as runtime_session:
                if hasattr(runtime_session, "execute"):
                    await persist(runtime_session)
    except _StyleRuntimeCancellation:
        raise
    except (TaskRuntimeNotFound, TaskRuntimeConflict, _StyleRuntimeDetached) as exc:
        if strict:
            raise _StyleRuntimeDetached(
                f"style runtime {run_id} rejected state {status_raw}"
            ) from exc
        logger.warning(
            "写入文风 TaskRuntime 事件失败：project=%s run_id=%s",
            project_id,
            run_id,
            exc_info=True,
        )
    except Exception:
        if strict:
            raise
        logger.warning(
            "写入文风 TaskRuntime 事件失败：project=%s run_id=%s",
            project_id,
            run_id,
            exc_info=True,
        )


async def _set_style_profile_job_state(
    run_id: str, *, strict_runtime: bool = False, **updates: Any,
) -> Dict[str, Any]:
    async with _STYLE_PROFILE_JOB_LOCK:
        job = _STYLE_PROFILE_JOBS.get(run_id)
        if not job:
            job = {"run_id": run_id, "status": "idle", "progress_stage": "idle"}
            _STYLE_PROFILE_JOBS[run_id] = job
        if job.get("status") in _STYLE_CANCEL_STATUSES and updates.get("status") not in _STYLE_CANCEL_STATUSES:
            return dict(job)
        previous = dict(job)
        job.update(updates)
        job["updated_at"] = _style_job_now_iso()
        snapshot = dict(job)
    try:
        await _append_style_task_runtime_event(
            snapshot, domain="style_profile", strict=strict_runtime
        )
    except BaseException:
        if strict_runtime:
            async with _STYLE_PROFILE_JOB_LOCK:
                current = _STYLE_PROFILE_JOBS.get(run_id)
                if current and current.get("updated_at") == snapshot.get("updated_at"):
                    _STYLE_PROFILE_JOBS[run_id] = previous
        raise
    return snapshot


async def _set_style_source_upload_job_state(
    run_id: str, *, strict_runtime: bool = False, **updates: Any,
) -> Dict[str, Any]:
    async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
        job = _STYLE_SOURCE_UPLOAD_JOBS.get(run_id)
        if not job:
            job = {"run_id": run_id, "status": "idle", "progress_stage": "idle"}
            _STYLE_SOURCE_UPLOAD_JOBS[run_id] = job
        if job.get("status") in _STYLE_CANCEL_STATUSES and updates.get("status") not in _STYLE_CANCEL_STATUSES:
            return dict(job)
        previous = dict(job)
        job.update(updates)
        job["updated_at"] = _style_job_now_iso()
        snapshot = dict(job)
    try:
        await _append_style_task_runtime_event(
            snapshot, domain="style_source_upload", strict=strict_runtime
        )
    except BaseException:
        if strict_runtime:
            async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
                current = _STYLE_SOURCE_UPLOAD_JOBS.get(run_id)
                if current and current.get("updated_at") == snapshot.get("updated_at"):
                    _STYLE_SOURCE_UPLOAD_JOBS[run_id] = previous
        raise
    return snapshot


async def _launch_style_source_upload_task(
    run_id: str,
    project_id: str,
    user_id: int,
    *,
    filename: str,
    raw_bytes: bytes,
    title: Optional[str],
    source_type: str,
    parsed_extra: Dict[str, Any],
) -> None:
    async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
        existing = _STYLE_TASKS.get(run_id)
        if existing is not None and not existing.done():
            return
        _STYLE_SCHEDULED_RUNS.add(run_id)
        task = asyncio.create_task(
            _run_style_source_upload_job(
                run_id,
                project_id,
                user_id,
                filename=filename,
                raw_bytes=raw_bytes,
                title=title,
                source_type=source_type,
                parsed_extra=parsed_extra,
            )
        )
        _STYLE_TASKS[run_id] = task


async def _launch_style_profile_task(
    run_id: str,
    project_id: str,
    user_id: int,
    request_payload: Dict[str, Any],
) -> None:
    async with _STYLE_PROFILE_JOB_LOCK:
        existing = _STYLE_TASKS.get(run_id)
        if existing is not None and not existing.done():
            return
        _STYLE_SCHEDULED_RUNS.add(run_id)
        task = asyncio.create_task(
            _run_style_profile_job(run_id, project_id, user_id, request_payload)
        )
        _STYLE_TASKS[run_id] = task


async def _style_worker_checkpoint(
    run_id: str, project_id: str, user_id: int, domain: str,
) -> None:
    if await _style_runtime_cancelled(run_id, project_id, user_id, domain):
        raise _StyleRuntimeCancellation(f"style runtime {run_id} is cancelling")


async def _mark_style_worker_detached(
    run_id: str, domain: str, detail: str,
) -> None:
    lock = _STYLE_PROFILE_JOB_LOCK if domain == "style_profile" else _STYLE_SOURCE_UPLOAD_JOB_LOCK
    jobs = _STYLE_PROFILE_JOBS if domain == "style_profile" else _STYLE_SOURCE_UPLOAD_JOBS
    async with lock:
        job = jobs.get(run_id)
        if not job or job.get("status") in {"successful", "cancelled"}:
            return
        job.update({
            "status": "failed",
            "progress_stage": "runtime_detached",
            "progress_message": "持久化任务已脱离，后台执行已安全停止",
            "updated_at": _style_job_now_iso(),
            "error": _style_job_error(
                f"{domain}_runtime_detached",
                "持久化任务已脱离，后台执行已安全停止",
                detail=detail,
                retryable=True,
            ),
        })


async def _compensate_style_source(user_id: int, source_id: Optional[str]) -> None:
    if not source_id:
        return
    try:
        async with AsyncSessionLocal() as session:
            await StyleRAGService(session, LLMService(session)).delete_style_source(
                user_id, source_id
            )
    except Exception:
        logger.exception("文风素材任务中断后的补偿删除失败: source_id=%s", source_id)


async def _compensate_style_profile(
    user_id: int,
    before_profiles: List[Dict[str, Any]],
    created_profile_id: Optional[str],
    append_to_profile_id: Optional[str],
) -> None:
    if not created_profile_id:
        return
    before_by_id = {
        str(item.get("id")): item
        for item in before_profiles
        if isinstance(item, dict) and item.get("id")
    }
    try:
        async with AsyncSessionLocal() as session:
            service = StyleRAGService(session, LLMService(session))
            current = await service.list_style_profiles(user_id)
            restored: List[StyleProfile] = []
            for profile in current:
                if append_to_profile_id and profile.id == append_to_profile_id:
                    previous = before_by_id.get(profile.id)
                    if previous:
                        restored.append(StyleProfile(previous))
                    continue
                if not append_to_profile_id and profile.id == created_profile_id:
                    continue
                previous = before_by_id.get(profile.id)
                if previous and "active" in previous:
                    profile.active = bool(previous["active"])
                restored.append(profile)
            await service._save_user_profiles(user_id, restored)
    except Exception:
        logger.exception(
            "文风画像任务中断后的补偿恢复失败: profile_id=%s", created_profile_id
        )


async def _run_style_source_upload_job(
    run_id: str,
    project_id: str,
    user_id: int,
    *,
    filename: str,
    raw_bytes: bytes,
    title: Optional[str],
    source_type: str,
    parsed_extra: Dict[str, Any],
) -> None:
    parent_task = asyncio.current_task()
    if parent_task is None:
        return
    runtime_backed = await _claim_style_runtime(
        run_id, project_id, user_id, "style_source_upload"
    )
    if runtime_backed is False:
        if _STYLE_TASKS.get(run_id) is parent_task:
            _STYLE_TASKS.pop(run_id, None)
        _STYLE_SCHEDULED_RUNS.discard(run_id)
        return
    _STYLE_TASKS[run_id] = parent_task
    runtime_detached = False
    source_id: Optional[str] = None

    async def heartbeat() -> None:
        nonlocal runtime_detached
        while True:
            await asyncio.sleep(_STYLE_SOURCE_UPLOAD_HEARTBEAT_SECONDS)
            async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
                job = _STYLE_SOURCE_UPLOAD_JOBS.get(run_id)
                if job and job.get("status") not in _STYLE_SOURCE_UPLOAD_ACTIVE_STATUSES:
                    return
                message = str(
                    (job or {}).get("progress_message")
                    or "正在处理文风素材上传"
                )
            try:
                await _style_worker_checkpoint(
                    run_id, project_id, user_id, "style_source_upload"
                )
                await _style_runtime_heartbeat(
                    run_id,
                    project_id,
                    user_id,
                    "style_source_upload",
                    message,
                )
            except _StyleRuntimeCancellation:
                parent_task.cancel()
                return
            except _StyleRuntimeDetached:
                runtime_detached = True
                parent_task.cancel()
                return

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        await _style_worker_checkpoint(
            run_id, project_id, user_id, "style_source_upload"
        )
        state = await _set_style_source_upload_job_state(
            run_id,
            strict_runtime=runtime_backed is True,
            status="upload_reading",
            progress_stage="upload_reading",
            progress_message="正在读取上传文件并准备抽取正文",
            metrics={"uploaded_bytes": len(raw_bytes or b"")},
        )
        if state.get("status") in _STYLE_CANCEL_STATUSES:
            raise _StyleRuntimeCancellation(f"style runtime {run_id} is cancelling")

        async with AsyncSessionLocal() as job_session:
            await NovelService(job_session).ensure_project_owner(project_id, user_id)
            style_service = StyleRAGService(job_session, LLMService(job_session))
            await _style_worker_checkpoint(
                run_id, project_id, user_id, "style_source_upload"
            )
            await _set_style_source_upload_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="upload_extracting",
                progress_stage="upload_extracting",
                progress_message="正在从 txt/docx/epub 等素材中抽取可学习正文",
            )
            extracted = style_service.extract_text_from_uploaded_file(
                filename or "", raw_bytes
            )
            await _style_worker_checkpoint(
                run_id, project_id, user_id, "style_source_upload"
            )
            await _set_style_source_upload_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="upload_saving",
                progress_stage="upload_saving",
                progress_message=f"已抽取 {extracted.get('char_count', 0)} 字，正在写入文风素材库",
                metrics={
                    "uploaded_bytes": len(raw_bytes or b""),
                    "format": extracted.get("format"),
                    "extracted_chars": extracted.get("char_count", 0),
                },
            )
            await _style_worker_checkpoint(
                run_id, project_id, user_id, "style_source_upload"
            )
            source = await style_service.create_external_style_source(
                user_id,
                title=(title or filename or "未命名参考文件"),
                content_text=extracted["text"],
                source_type=source_type,
                extra={
                    **parsed_extra,
                    "format": extracted["format"],
                    "file_name": filename,
                    "file_chars": extracted["char_count"],
                    "import_mode": parsed_extra.get("import_mode") or "file_upload",
                    "is_batch_note": parsed_extra.get("is_batch_note", False),
                },
            )
            source_payload = source.to_dict()
            source_id = str(source_payload.get("id") or "") or None

        await _style_worker_checkpoint(
            run_id, project_id, user_id, "style_source_upload"
        )
        await _set_style_source_upload_job_state(
            run_id,
            strict_runtime=runtime_backed is True,
            status="successful",
            progress_stage="successful",
            progress_message="文风素材导入完成，可以加入画像学习批次",
            source=source_payload,
            metrics={
                "uploaded_bytes": len(raw_bytes or b""),
                "format": source_payload.get("extra", {}).get("format"),
                "extracted_chars": source_payload.get("char_count", 0),
                "source_id": source_payload.get("id"),
            },
            error=None,
        )
    except (asyncio.CancelledError, _StyleRuntimeCancellation):
        await _compensate_style_source(user_id, source_id)
        if runtime_detached:
            await _mark_style_worker_detached(
                run_id, "style_source_upload", "runtime heartbeat or lease was lost"
            )
        else:
            try:
                await _set_style_source_upload_job_state(
                    run_id,
                    strict_runtime=runtime_backed is True,
                    status="cancelled",
                    progress_stage="cancelled",
                    progress_message="文风素材导入任务已取消",
                    error=_style_job_error(
                        "style_source_upload_cancelled",
                        "文风素材导入任务已取消",
                        retryable=True,
                    ),
                )
            except _StyleRuntimeDetached as exc:
                await _mark_style_worker_detached(
                    run_id, "style_source_upload", str(exc)
                )
        # 清理已经完成；不把后台 worker 的取消传播到 ASGI 请求任务。
        return
    except _StyleRuntimeDetached as exc:
        await _compensate_style_source(user_id, source_id)
        await _mark_style_worker_detached(run_id, "style_source_upload", str(exc))
    except ValueError as exc:
        try:
            await _set_style_source_upload_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="failed",
                progress_stage="failed",
                progress_message="文风素材导入失败",
                error=_style_job_error(
                    "style_source_upload_failed",
                    "文风素材导入失败",
                    detail=str(exc),
                    retryable=False,
                ),
            )
        except (_StyleRuntimeDetached, _StyleRuntimeCancellation) as runtime_exc:
            await _mark_style_worker_detached(
                run_id, "style_source_upload", str(runtime_exc)
            )
    except Exception as exc:
        logger.exception("文风素材上传后台任务失败: project=%s run_id=%s", project_id, run_id)
        try:
            await _set_style_source_upload_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="failed",
                progress_stage="failed",
                progress_message="文风素材导入失败",
                error=_style_job_error(
                    "style_source_upload_failed",
                    "文风素材导入失败",
                    detail=exc,
                    retryable=True,
                ),
            )
        except (_StyleRuntimeDetached, _StyleRuntimeCancellation) as runtime_exc:
            await _mark_style_worker_detached(
                run_id, "style_source_upload", str(runtime_exc)
            )
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        if _STYLE_TASKS.get(run_id) is parent_task:
            _STYLE_TASKS.pop(run_id, None)
        _STYLE_SCHEDULED_RUNS.discard(run_id)


async def _run_style_profile_job(
    run_id: str,
    project_id: str,
    user_id: int,
    request_payload: Dict[str, Any],
) -> None:
    parent_task = asyncio.current_task()
    if parent_task is None:
        return
    runtime_backed = await _claim_style_runtime(
        run_id, project_id, user_id, "style_profile"
    )
    if runtime_backed is False:
        if _STYLE_TASKS.get(run_id) is parent_task:
            _STYLE_TASKS.pop(run_id, None)
        _STYLE_SCHEDULED_RUNS.discard(run_id)
        return
    _STYLE_TASKS[run_id] = parent_task
    runtime_detached = False
    before_profiles: List[Dict[str, Any]] = []
    created_profile_id: Optional[str] = None
    append_to_profile_id: Optional[str] = None

    async def heartbeat() -> None:
        nonlocal runtime_detached
        while True:
            await asyncio.sleep(_STYLE_PROFILE_HEARTBEAT_SECONDS)
            async with _STYLE_PROFILE_JOB_LOCK:
                job = _STYLE_PROFILE_JOBS.get(run_id)
                if job and job.get("status") not in _STYLE_PROFILE_ACTIVE_STATUSES:
                    return
                message = str(
                    (job or {}).get("progress_message")
                    or "正在生成文风画像"
                )
            try:
                await _style_worker_checkpoint(
                    run_id, project_id, user_id, "style_profile"
                )
                await _style_runtime_heartbeat(
                    run_id,
                    project_id,
                    user_id,
                    "style_profile",
                    message,
                )
            except _StyleRuntimeCancellation:
                parent_task.cancel()
                return
            except _StyleRuntimeDetached:
                runtime_detached = True
                parent_task.cancel()
                return

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        request = CreateStyleProfileRequest(**request_payload)
        append_to_profile_id = request.append_to_profile_id
        await _style_worker_checkpoint(run_id, project_id, user_id, "style_profile")
        state = await _set_style_profile_job_state(
            run_id,
            strict_runtime=runtime_backed is True,
            status="extracting",
            progress_stage="extracting",
            progress_message="正在读取参考素材并整理风格样本",
        )
        if state.get("status") in _STYLE_CANCEL_STATUSES:
            raise _StyleRuntimeCancellation(f"style runtime {run_id} is cancelling")

        async with AsyncSessionLocal() as job_session:
            await NovelService(job_session).ensure_project_owner(project_id, user_id)
            style_service = StyleRAGService(job_session, LLMService(job_session))
            before_profiles = [
                profile.to_dict()
                for profile in await style_service.list_style_profiles(user_id)
            ]
            await _style_worker_checkpoint(run_id, project_id, user_id, "style_profile")
            await _set_style_profile_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="profiling",
                progress_stage="profiling",
                progress_message="正在提炼叙事、句式、对话和节奏画像",
            )
            profile = await style_service.create_profile_from_sources(
                user_id,
                source_ids=request.source_ids,
                name=request.name,
                append_to_profile_id=request.append_to_profile_id,
            )
            profile_payload = profile.to_dict()
            created_profile_id = str(profile_payload.get("id") or "") or None

        await _style_worker_checkpoint(run_id, project_id, user_id, "style_profile")
        await _set_style_profile_job_state(
            run_id,
            strict_runtime=runtime_backed is True,
            status="successful",
            progress_stage="successful",
            progress_message="文风画像生成完成",
            profile=profile_payload,
            error=None,
        )
    except (asyncio.CancelledError, _StyleRuntimeCancellation):
        await _compensate_style_profile(
            user_id, before_profiles, created_profile_id, append_to_profile_id
        )
        if runtime_detached:
            await _mark_style_worker_detached(
                run_id, "style_profile", "runtime heartbeat or lease was lost"
            )
        else:
            try:
                await _set_style_profile_job_state(
                    run_id,
                    strict_runtime=runtime_backed is True,
                    status="cancelled",
                    progress_stage="cancelled",
                    progress_message="文风画像生成任务已取消",
                    error=_style_job_error(
                        "style_profile_generation_cancelled",
                        "文风画像生成任务已取消",
                        retryable=True,
                    ),
                )
            except _StyleRuntimeDetached as exc:
                await _mark_style_worker_detached(run_id, "style_profile", str(exc))
        # 清理已经完成；不把后台 worker 的取消传播到 ASGI 请求任务。
        return
    except _StyleRuntimeDetached as exc:
        await _compensate_style_profile(
            user_id, before_profiles, created_profile_id, append_to_profile_id
        )
        await _mark_style_worker_detached(run_id, "style_profile", str(exc))
    except ValueError as exc:
        try:
            await _set_style_profile_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="failed",
                progress_stage="failed",
                progress_message="文风画像生成失败",
                error=_style_job_error(
                    "style_profile_generation_failed",
                    "文风画像生成失败",
                    detail=str(exc),
                    retryable=False,
                ),
            )
        except (_StyleRuntimeDetached, _StyleRuntimeCancellation) as runtime_exc:
            await _mark_style_worker_detached(run_id, "style_profile", str(runtime_exc))
    except Exception as exc:
        logger.exception("文风画像后台任务失败: project=%s run_id=%s", project_id, run_id)
        try:
            await _set_style_profile_job_state(
                run_id,
                strict_runtime=runtime_backed is True,
                status="failed",
                progress_stage="failed",
                progress_message="文风画像生成失败",
                error=_style_job_error(
                    "style_profile_generation_failed",
                    "文风画像生成失败",
                    detail=exc,
                    retryable=True,
                ),
            )
        except (_StyleRuntimeDetached, _StyleRuntimeCancellation) as runtime_exc:
            await _mark_style_worker_detached(run_id, "style_profile", str(runtime_exc))
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        if _STYLE_TASKS.get(run_id) is parent_task:
            _STYLE_TASKS.pop(run_id, None)
        _STYLE_SCHEDULED_RUNS.discard(run_id)


@router.get("/sources", response_model=dict)
async def list_style_sources(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    sources = await style_service.list_style_sources(current_user.id)
    return {"sources": [source.to_dict() for source in sources]}


@router.get("/library", response_model=dict)
async def get_style_library(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    sources = await style_service.list_style_sources(current_user.id)
    profiles = await style_service.list_style_profiles(current_user.id)
    project_profile = await style_service.get_project_applied_style_profile(project_id, current_user.id)
    global_profile = await style_service.get_global_active_style_profile(current_user.id)
    return {
        "sources": [source.to_dict() for source in sources],
        "profiles": [profile.to_dict() for profile in profiles],
        "project_active_profile": project_profile.to_dict() if project_profile else None,
        "global_active_profile": global_profile.to_dict() if global_profile else None,
    }


@router.post("/sources", response_model=dict)
async def create_style_source(
    project_id: str,
    request: CreateStyleSourceRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    try:
        source = await style_service.create_external_style_source(
            current_user.id,
            title=request.title,
            content_text=request.content_text,
            source_type=request.source_type,
            extra=request.extra,
        )
        return {"success": True, "source": source.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/sources/{source_id}", response_model=dict)
async def delete_style_source(
    project_id: str,
    source_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    deleted = await style_service.delete_style_source(current_user.id, source_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到指定参考文本")
    return {"success": True}


@router.post("/sources/upload/start", response_model=StyleSourceUploadJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_style_source_upload(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    source_type: str = Form(default="external_novel"),
    extra: Optional[str] = Form(default=None),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StyleSourceUploadJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    try:
        parsed_extra = json.loads(extra) if extra else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="extra 不是合法 JSON")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")

    persisted_active = await _load_active_persisted_style_job(
        session,
        project_id=project_id,
        user_id=int(current_user.id),
        task_type="style_source_upload",
        domain="style_source_upload",
    ) if hasattr(session, "execute") else None
    if persisted_active:
        async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
            _STYLE_SOURCE_UPLOAD_JOBS[persisted_active["run_id"]] = dict(persisted_active)
            _STYLE_SOURCE_UPLOAD_PROJECT_RUNS[project_id] = persisted_active["run_id"]
        return _serialize_style_source_upload_job(persisted_active)

    async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
        existing_run_id = _STYLE_SOURCE_UPLOAD_PROJECT_RUNS.get(project_id)
        existing = _STYLE_SOURCE_UPLOAD_JOBS.get(existing_run_id or "")
        if (
            existing
            and not hasattr(session, "execute")
            and existing.get("status") in _STYLE_SOURCE_UPLOAD_ACTIVE_STATUSES
        ):
            return _serialize_style_source_upload_job(existing)

        run_id = str(uuid.uuid4())
        storage_path = _style_upload_path(project_id, run_id)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(raw_bytes)
        now = _style_job_now_iso()
        job = {
            "run_id": run_id,
            "project_id": project_id,
            "user_id": int(current_user.id),
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "文风素材导入任务已入队",
            "started_at": now,
            "updated_at": now,
            "filename": file.filename,
            "source": None,
            "metrics": {"uploaded_bytes": len(raw_bytes)},
            "error": None,
        }
        if hasattr(session, "execute"):
            await TaskRuntimeService(session).create_task(
                task_id=run_id,
                task_type="style_source_upload",
            idempotency_key=f"style-source-upload:{run_id}",
            owner_user_id=int(current_user.id),
            project_id=project_id,
                payload={
                    "run_id": run_id,
                    "filename": file.filename,
                    "bytes": len(raw_bytes),
                    "storage_path": str(storage_path),
                    "title": title,
                    "source_type": source_type,
                    "parsed_extra": parsed_extra,
                    "style_job": _style_runtime_job_snapshot(job, domain="style_source_upload"),
                },
            )
            job["runtime_task_registered"] = True
        _STYLE_SOURCE_UPLOAD_JOBS[run_id] = job
        _STYLE_SOURCE_UPLOAD_PROJECT_RUNS[project_id] = run_id

    background_tasks.add_task(
        _launch_style_source_upload_task,
        run_id,
        project_id,
        int(current_user.id),
        filename=file.filename or "",
        raw_bytes=raw_bytes,
        title=title,
        source_type=source_type,
        parsed_extra=parsed_extra,
    )
    return _serialize_style_source_upload_job(job)


@router.get("/sources/upload/status", response_model=StyleSourceUploadJobResponse)
async def get_style_source_upload_status(
    project_id: str,
    run_id: Optional[str] = Query(default=None),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StyleSourceUploadJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
        resolved_run_id = run_id or _STYLE_SOURCE_UPLOAD_PROJECT_RUNS.get(project_id)
        memory_job = dict(_STYLE_SOURCE_UPLOAD_JOBS.get(resolved_run_id or "") or {})
        job = memory_job if (
            memory_job
            and memory_job.get("project_id") == project_id
            and memory_job.get("user_id") == int(current_user.id)
        ) else {}

    # 数据库可用时，TaskRuntime 是状态真相源；内存只作为无数据库兼容回退。
    persisted_job = await _load_persisted_style_job(
        session, project_id=project_id, user_id=int(current_user.id),
        task_type="style_source_upload", domain="style_source_upload", run_id=run_id,
    ) if hasattr(session, "execute") else None
    if hasattr(session, "execute"):
        job = persisted_job or {}
    if persisted_job:
        async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
            _STYLE_SOURCE_UPLOAD_JOBS[job["run_id"]] = dict(job)
            _STYLE_SOURCE_UPLOAD_PROJECT_RUNS[project_id] = job["run_id"]

    if job:
        runtime_payload = job.get("_runtime_payload") if isinstance(job.get("_runtime_payload"), dict) else {}
        if job.get("_runtime_status") in {TaskRuntimeStatus.QUEUED.value, TaskRuntimeStatus.STALE.value}:
            storage = _validated_style_upload_path(
                project_id, job["run_id"], runtime_payload.get("storage_path")
            )
            if storage:
                await _launch_style_source_upload_task(
                    job["run_id"], project_id, int(current_user.id),
                    filename=str(runtime_payload.get("filename") or job.get("filename") or ""),
                    raw_bytes=storage.read_bytes(),
                    title=runtime_payload.get("title"),
                    source_type=str(runtime_payload.get("source_type") or "external_novel"),
                    parsed_extra=dict(runtime_payload.get("parsed_extra") or {}),
                )
        return _serialize_style_source_upload_job(job)

    return StyleSourceUploadJobResponse(
        run_id=run_id or "",
        project_id=project_id,
        status="idle",
        progress_stage="idle",
        progress_message="暂无文风素材导入任务",
    )


@router.post("/sources/upload/{run_id}/cancel", response_model=StyleSourceUploadJobResponse)
async def cancel_style_source_upload(
    project_id: str,
    run_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StyleSourceUploadJobResponse:
    await NovelService(session).ensure_project_owner(project_id, current_user.id)
    db_backed = hasattr(session, "execute")

    if db_backed:
        job = await _load_persisted_style_job(
            session,
            project_id=project_id,
            user_id=int(current_user.id),
            task_type="style_source_upload",
            domain="style_source_upload",
            run_id=run_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="文风素材导入任务不存在")
        async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
            _STYLE_SOURCE_UPLOAD_JOBS[run_id] = dict(job)
            _STYLE_SOURCE_UPLOAD_PROJECT_RUNS[project_id] = run_id
    else:
        async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
            memory_job = dict(_STYLE_SOURCE_UPLOAD_JOBS.get(run_id) or {})
        job = memory_job if (
            memory_job.get("project_id") == project_id
            and (
                memory_job.get("user_id") is None
                or memory_job.get("user_id") == int(current_user.id)
            )
        ) else {}
        if not job:
            return StyleSourceUploadJobResponse(
                run_id=run_id,
                project_id=project_id,
                status="idle",
                progress_stage="idle",
                progress_message="暂无可取消的文风素材导入任务",
            )

    if job.get("status") == "upload_saving":
        job = dict(job)
        job["progress_message"] = "素材已进入原子保存阶段，无法安全取消，请等待保存结果"
        return _serialize_style_source_upload_job(job)

    try:
        runtime_task = await _request_style_runtime_cancel(
            run_id,
            project_id,
            int(current_user.id),
            "style_source_upload",
            session=session,
        )
    except TaskRuntimeNotFound as exc:
        raise HTTPException(status_code=404, detail="文风素材导入任务不存在") from exc
    except TaskRuntimeConflict as exc:
        raise HTTPException(status_code=409, detail=f"文风素材导入任务无法取消: {exc}") from exc

    runtime_status = str(getattr(runtime_task, "status", "") or "")
    async with _STYLE_SOURCE_UPLOAD_JOB_LOCK:
        live_job = _STYLE_SOURCE_UPLOAD_JOBS.get(run_id)
        if live_job is None:
            live_job = dict(job)
            _STYLE_SOURCE_UPLOAD_JOBS[run_id] = live_job
        if live_job.get("status") in _STYLE_SOURCE_UPLOAD_CANCELLABLE_STATUSES:
            terminal = runtime_status in {"", TaskRuntimeStatus.CANCELLED.value}
            live_job.update({
                "status": "cancelled" if terminal else "cancelling",
                "progress_stage": "cancelled" if terminal else "cancelling",
                "progress_message": (
                    "文风素材导入任务已取消"
                    if terminal
                    else "已请求取消文风素材导入任务，等待后台收敛"
                ),
                "updated_at": _style_job_now_iso(),
                "error": _style_job_error(
                    "style_source_upload_cancelled" if terminal else "style_source_upload_cancelling",
                    "文风素材导入任务已取消"
                    if terminal
                    else "已请求取消文风素材导入任务，等待后台收敛",
                    retryable=True,
                ),
            })
        snapshot = dict(live_job)

    local_task = _STYLE_TASKS.get(run_id)
    if (
        runtime_status == TaskRuntimeStatus.CANCELLING.value
        and local_task is not None
        and not local_task.done()
    ):
        local_task.cancel()
    return _serialize_style_source_upload_job(snapshot)


@router.post("/sources/upload", response_model=dict, deprecated=True)
async def upload_style_source(
    project_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    source_type: str = Form(default="external_novel"),
    extra: Optional[str] = Form(default=None),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    try:
        raw_bytes = await file.read()
        parsed_extra = json.loads(extra) if extra else {}
        extracted = style_service.extract_text_from_uploaded_file(file.filename or "", raw_bytes)
        source = await style_service.create_external_style_source(
            current_user.id,
            title=(title or file.filename or "未命名参考文件"),
            content_text=extracted["text"],
            source_type=source_type,
            extra={
                **parsed_extra,
                "format": extracted["format"],
                "file_name": file.filename,
                "file_chars": extracted["char_count"],
                "import_mode": parsed_extra.get("import_mode") or "file_upload",
                "is_batch_note": parsed_extra.get("is_batch_note", False),
            },
        )
        return {"success": True, "source": source.to_dict()}
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="extra 不是合法 JSON")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/profiles", response_model=dict)
async def list_style_profiles(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    profiles = await style_service.list_style_profiles(current_user.id)
    return {"profiles": [profile.to_dict() for profile in profiles]}


@router.post("/profiles/start", response_model=StyleProfileJobResponse)
async def start_style_profile_generation(
    project_id: str,
    request: CreateStyleProfileRequest,
    background_tasks: BackgroundTasks,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StyleProfileJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    persisted_active = await _load_active_persisted_style_job(
        session,
        project_id=project_id,
        user_id=int(current_user.id),
        task_type="style_profile_generation",
        domain="style_profile",
    ) if hasattr(session, "execute") else None
    if persisted_active:
        async with _STYLE_PROFILE_JOB_LOCK:
            _STYLE_PROFILE_JOBS[persisted_active["run_id"]] = dict(persisted_active)
            _STYLE_PROFILE_PROJECT_RUNS[project_id] = persisted_active["run_id"]
        return _serialize_style_profile_job(persisted_active)

    async with _STYLE_PROFILE_JOB_LOCK:
        existing_run_id = _STYLE_PROFILE_PROJECT_RUNS.get(project_id)
        existing = _STYLE_PROFILE_JOBS.get(existing_run_id or "")
        if (
            existing
            and not hasattr(session, "execute")
            and existing.get("status") in _STYLE_PROFILE_ACTIVE_STATUSES
        ):
            return _serialize_style_profile_job(existing)

        run_id = str(uuid.uuid4())
        now = _style_job_now_iso()
        job = {
            "run_id": run_id,
            "project_id": project_id,
            "user_id": int(current_user.id),
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "文风画像生成任务已入队",
            "started_at": now,
            "updated_at": now,
            "profile": None,
            "error": None,
            "request": request.model_dump(),
        }
        if hasattr(session, "execute"):
            await TaskRuntimeService(session).create_task(
                task_id=run_id,
                task_type="style_profile_generation",
            idempotency_key=f"style-profile-generation:{run_id}",
            owner_user_id=int(current_user.id),
            project_id=project_id,
                payload={
                    "run_id": run_id,
                    "request": request.model_dump(),
                    "style_job": _style_runtime_job_snapshot(job, domain="style_profile"),
                },
            )
            job["runtime_task_registered"] = True
        _STYLE_PROFILE_JOBS[run_id] = job
        _STYLE_PROFILE_PROJECT_RUNS[project_id] = run_id

    background_tasks.add_task(
        _launch_style_profile_task,
        run_id,
        project_id,
        int(current_user.id),
        request.model_dump(),
    )
    return _serialize_style_profile_job(job)


@router.get("/profiles/status", response_model=StyleProfileJobResponse)
async def get_style_profile_generation_status(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StyleProfileJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _STYLE_PROFILE_JOB_LOCK:
        run_id = _STYLE_PROFILE_PROJECT_RUNS.get(project_id)
        memory_job = dict(_STYLE_PROFILE_JOBS.get(run_id or "") or {})
        job = memory_job if (
            memory_job
            and memory_job.get("project_id") == project_id
            and memory_job.get("user_id") == int(current_user.id)
        ) else {}

    # 数据库可用时，TaskRuntime 是状态真相源；内存只作为无数据库兼容回退。
    persisted_job = await _load_persisted_style_job(
        session, project_id=project_id, user_id=int(current_user.id),
        task_type="style_profile_generation", domain="style_profile",
    ) if hasattr(session, "execute") else None
    if hasattr(session, "execute"):
        job = persisted_job or {}
    if persisted_job:
        async with _STYLE_PROFILE_JOB_LOCK:
            _STYLE_PROFILE_JOBS[job["run_id"]] = dict(job)
            _STYLE_PROFILE_PROJECT_RUNS[project_id] = job["run_id"]

    if job:
        if job.get("_runtime_status") in {TaskRuntimeStatus.QUEUED.value, TaskRuntimeStatus.STALE.value}:
            request_payload = job.get("request")
            if isinstance(request_payload, dict):
                await _launch_style_profile_task(
                    job["run_id"], project_id, int(current_user.id), request_payload
                )
        return _serialize_style_profile_job(job)

    return StyleProfileJobResponse(
        run_id="",
        project_id=project_id,
        status="idle",
        progress_stage="idle",
        progress_message="暂无文风画像生成任务",
    )


@router.post("/profiles/cancel", response_model=StyleProfileJobResponse)
async def cancel_style_profile_generation(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StyleProfileJobResponse:
    await NovelService(session).ensure_project_owner(project_id, current_user.id)
    db_backed = hasattr(session, "execute")

    if db_backed:
        job = await _load_persisted_style_job(
            session,
            project_id=project_id,
            user_id=int(current_user.id),
            task_type="style_profile_generation",
            domain="style_profile",
        )
        if not job:
            return StyleProfileJobResponse(
                run_id="",
                project_id=project_id,
                status="idle",
                progress_stage="idle",
                progress_message="暂无可取消的文风画像生成任务",
            )
        run_id = str(job.get("run_id") or "")
        async with _STYLE_PROFILE_JOB_LOCK:
            _STYLE_PROFILE_JOBS[run_id] = dict(job)
            _STYLE_PROFILE_PROJECT_RUNS[project_id] = run_id
    else:
        async with _STYLE_PROFILE_JOB_LOCK:
            run_id = _STYLE_PROFILE_PROJECT_RUNS.get(project_id)
            memory_job = dict(_STYLE_PROFILE_JOBS.get(run_id or "") or {})
        job = memory_job if (
            memory_job.get("project_id") == project_id
            and memory_job.get("user_id") == int(current_user.id)
        ) else {}
        if not job:
            return StyleProfileJobResponse(
                run_id="",
                project_id=project_id,
                status="idle",
                progress_stage="idle",
                progress_message="暂无可取消的文风画像生成任务",
            )

    try:
        runtime_task = await _request_style_runtime_cancel(
            str(run_id),
            project_id,
            int(current_user.id),
            "style_profile",
            session=session,
        )
    except TaskRuntimeNotFound as exc:
        raise HTTPException(status_code=404, detail="文风画像生成任务不存在") from exc
    except TaskRuntimeConflict as exc:
        raise HTTPException(status_code=409, detail=f"文风画像生成任务无法取消: {exc}") from exc

    runtime_status = str(getattr(runtime_task, "status", "") or "")
    async with _STYLE_PROFILE_JOB_LOCK:
        live_job = _STYLE_PROFILE_JOBS.get(str(run_id))
        if live_job is None:
            live_job = dict(job)
            _STYLE_PROFILE_JOBS[str(run_id)] = live_job
        if live_job.get("status") in _STYLE_PROFILE_ACTIVE_STATUSES:
            terminal = runtime_status in {"", TaskRuntimeStatus.CANCELLED.value}
            live_job.update({
                "status": "cancelled" if terminal else "cancelling",
                "progress_stage": "cancelled" if terminal else "cancelling",
                "progress_message": (
                    "文风画像生成任务已取消"
                    if terminal
                    else "已请求取消文风画像生成任务，等待后台收敛"
                ),
                "updated_at": _style_job_now_iso(),
                "error": _style_job_error(
                    "style_profile_generation_cancelled" if terminal else "style_profile_generation_cancelling",
                    "文风画像生成任务已取消"
                    if terminal
                    else "已请求取消文风画像生成任务，等待后台收敛",
                    retryable=True,
                ),
            })
        snapshot = dict(live_job)

    local_task = _STYLE_TASKS.get(str(run_id))
    if (
        runtime_status == TaskRuntimeStatus.CANCELLING.value
        and local_task is not None
        and not local_task.done()
    ):
        local_task.cancel()
    return _serialize_style_profile_job(snapshot)


@router.post("/profiles", response_model=dict, deprecated=True)
async def create_style_profile(
    project_id: str,
    request: CreateStyleProfileRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    try:
        profile = await style_service.create_profile_from_sources(
            current_user.id,
            source_ids=request.source_ids,
            name=request.name,
            append_to_profile_id=request.append_to_profile_id,
        )
        return {"success": True, "profile": profile.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/profiles/{profile_id}", response_model=dict)
async def update_style_profile(
    project_id: str,
    profile_id: str,
    request: UpdateStyleProfileRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    try:
        profile = await style_service.update_style_profile(
            current_user.id,
            profile_id=profile_id,
            name=request.name,
            summary=request.summary,
            extra=request.extra,
        )
        return {"success": True, "profile": profile.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/active", response_model=dict)
async def get_active_style_profile(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    project_profile = await style_service.get_project_applied_style_profile(project_id, current_user.id)
    global_profile = await style_service.get_global_active_style_profile(current_user.id)
    effective = project_profile or global_profile
    return {
        "has_active_style": effective is not None,
        "profile": effective.to_dict() if effective else None,
        "scope": "project" if project_profile else ("global" if global_profile else None),
    }


@router.post("/apply", response_model=dict)
async def apply_style_profile(
    project_id: str,
    request: ApplyStyleProfileRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    try:
        profile = await style_service.apply_style_profile(
            user_id=current_user.id,
            profile_id=request.profile_id,
            scope=request.scope,
            project_id=project_id if request.scope == "project" else None,
        )
        return {"success": True, "profile": profile.to_dict(), "scope": request.scope}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/active", response_model=dict)
async def clear_active_style_profile(
    project_id: str,
    scope: Literal["global", "project"] = Query("project"),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    style_service = StyleRAGService(session, LLMService(session))
    await style_service.clear_style_application(
        user_id=current_user.id,
        scope=scope,
        project_id=project_id if scope == "project" else None,
    )
    return {"success": True}


@router.post("/extract", response_model=ExtractStyleResponse)
async def extract_style_from_chapters(
    project_id: str,
    request: ExtractStyleRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """从指定章节提取写作风格特征"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    style_service = StyleRAGService(session, llm_service)

    try:
        style_feature = await style_service.extract_style_from_chapters(
            project_id=project_id,
            chapter_numbers=request.chapter_numbers,
            user_id=current_user.id
        )

        return ExtractStyleResponse(
            success=True,
            message=f"成功从 {len(request.chapter_numbers)} 章提取风格特征",
            style_summary=await style_service.get_style_summary(project_id, current_user.id)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"风格提取失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=StyleSummaryResponse)
async def get_project_style(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """获取项目当前风格配置"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    style_service = StyleRAGService(session, llm_service)

    summary = await style_service.get_style_summary(project_id, current_user.id)

    return StyleSummaryResponse(
        has_style=summary.get("has_style", False),
        summary=summary.get("summary"),
        source=summary.get("source")
    )


@router.delete("", response_model=dict)
async def clear_project_style(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """清除项目的风格配置"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    style_service = StyleRAGService(session, llm_service)

    await style_service.clear_style_for_project(project_id)

    return {"success": True, "message": "风格配置已清除"}


@router.post("/generate", response_model=StyleGenerateResponse)
async def generate_with_style(
    project_id: str,
    request: StyleGenerateRequest,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """带风格上下文的续写生成"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    style_service = StyleRAGService(session, llm_service)

    # 检查是否有风格配置（优先激活的外部文风，其次回退到项目内文风）
    has_style = await style_service.get_effective_style_for_project(project_id, current_user.id) is not None

    if not has_style:
        # 没有风格配置，使用普通生成
        return StyleGenerateResponse(
            content=request.existing_content,
            style_applied=False
        )

    try:
        content = await style_service.generate_with_style(
            project_id=project_id,
            existing_content=request.existing_content,
            direction=request.direction,
            user_id=current_user.id,
            max_tokens=request.max_tokens
        )

        return StyleGenerateResponse(
            content=content,
            style_applied=True
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"风格化生成失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
