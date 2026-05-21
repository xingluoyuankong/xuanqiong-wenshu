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
from ...services.style_rag_service import StyleRAGService, StyleFeature
from ...services.novel_service import NovelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/style", tags=["style-rag"])

_STYLE_PROFILE_JOBS: Dict[str, Dict[str, Any]] = {}
_STYLE_PROFILE_PROJECT_RUNS: Dict[str, str] = {}
_STYLE_PROFILE_JOB_LOCK = asyncio.Lock()
_STYLE_PROFILE_ACTIVE_STATUSES = {"queued", "extracting", "profiling", "saving"}
_STYLE_PROFILE_HEARTBEAT_SECONDS = 30


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


async def _set_style_profile_job_state(run_id: str, **updates: Any) -> Dict[str, Any]:
    async with _STYLE_PROFILE_JOB_LOCK:
        job = _STYLE_PROFILE_JOBS.get(run_id)
        if not job:
            job = {"run_id": run_id, "status": "idle", "progress_stage": "idle"}
            _STYLE_PROFILE_JOBS[run_id] = job
        if job.get("status") == "cancelled" and updates.get("status") != "cancelled":
            return dict(job)
        job.update(updates)
        job["updated_at"] = _style_job_now_iso()
        return dict(job)


async def _run_style_profile_job(
    run_id: str,
    project_id: str,
    user_id: int,
    request_payload: Dict[str, Any],
) -> None:
    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(_STYLE_PROFILE_HEARTBEAT_SECONDS)
            async with _STYLE_PROFILE_JOB_LOCK:
                job = _STYLE_PROFILE_JOBS.get(run_id)
                if not job or job.get("status") not in _STYLE_PROFILE_ACTIVE_STATUSES:
                    return
                stage = str(job.get("progress_stage") or "profiling")
                message = str(job.get("progress_message") or "正在生成文风画像")
            await _set_style_profile_job_state(
                run_id,
                status=stage if stage in _STYLE_PROFILE_ACTIVE_STATUSES else "profiling",
                progress_stage=stage,
                progress_message=message,
            )

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        request = CreateStyleProfileRequest(**request_payload)
        state = await _set_style_profile_job_state(
            run_id,
            status="extracting",
            progress_stage="extracting",
            progress_message="正在读取参考素材并整理风格样本",
        )
        if state.get("status") == "cancelled":
            return
        async with AsyncSessionLocal() as job_session:
            novel_service = NovelService(job_session)
            await novel_service.ensure_project_owner(project_id, user_id)
            style_service = StyleRAGService(job_session, LLMService(job_session))
            state = await _set_style_profile_job_state(
                run_id,
                status="profiling",
                progress_stage="profiling",
                progress_message="正在提炼叙事、句式、对话和节奏画像",
            )
            if state.get("status") == "cancelled":
                return
            profile = await style_service.create_profile_from_sources(
                user_id,
                source_ids=request.source_ids,
                name=request.name,
                append_to_profile_id=request.append_to_profile_id,
            )
            profile_payload = profile.to_dict()

        async with _STYLE_PROFILE_JOB_LOCK:
            current = _STYLE_PROFILE_JOBS.get(run_id)
            if current and current.get("status") == "cancelled":
                return

        await _set_style_profile_job_state(
            run_id,
            status="successful",
            progress_stage="successful",
            progress_message="文风画像生成完成",
            profile=profile_payload,
            error=None,
        )
    except ValueError as exc:
        await _set_style_profile_job_state(
            run_id,
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
    except Exception as exc:  # noqa: BLE001 - background task must surface failures
        logger.exception("文风画像后台任务失败: project=%s run_id=%s", project_id, run_id)
        await _set_style_profile_job_state(
            run_id,
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
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


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


@router.post("/sources/upload", response_model=dict)
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

    async with _STYLE_PROFILE_JOB_LOCK:
        existing_run_id = _STYLE_PROFILE_PROJECT_RUNS.get(project_id)
        existing = _STYLE_PROFILE_JOBS.get(existing_run_id or "")
        if existing and existing.get("status") in _STYLE_PROFILE_ACTIVE_STATUSES:
            return _serialize_style_profile_job(existing)

        run_id = str(uuid.uuid4())
        now = _style_job_now_iso()
        job = {
            "run_id": run_id,
            "project_id": project_id,
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "文风画像生成任务已入队",
            "started_at": now,
            "updated_at": now,
            "profile": None,
            "error": None,
            "request": request.model_dump(),
        }
        _STYLE_PROFILE_JOBS[run_id] = job
        _STYLE_PROFILE_PROJECT_RUNS[project_id] = run_id

    background_tasks.add_task(
        _run_style_profile_job,
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
        job = dict(_STYLE_PROFILE_JOBS.get(run_id or "") or {})
        if job and job.get("status") not in _STYLE_PROFILE_ACTIVE_STATUSES:
            _STYLE_PROFILE_JOBS.pop(str(job.get("run_id") or ""), None)
            _STYLE_PROFILE_PROJECT_RUNS.pop(project_id, None)

    if job:
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
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _STYLE_PROFILE_JOB_LOCK:
        run_id = _STYLE_PROFILE_PROJECT_RUNS.get(project_id)
        job = _STYLE_PROFILE_JOBS.get(run_id or "")
        if not job:
            return StyleProfileJobResponse(
                run_id="",
                project_id=project_id,
                status="idle",
                progress_stage="idle",
                progress_message="暂无可取消的文风画像生成任务",
            )
        if job.get("status") in _STYLE_PROFILE_ACTIVE_STATUSES:
            job.update({
                "status": "cancelled",
                "progress_stage": "cancelled",
                "progress_message": "文风画像生成任务已取消",
                "updated_at": _style_job_now_iso(),
                "error": _style_job_error(
                    "style_profile_generation_cancelled",
                    "文风画像生成任务已取消",
                    retryable=True,
                ),
            })
        snapshot = dict(job)

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
