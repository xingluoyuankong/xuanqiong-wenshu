# AIMETA P=管理员API_用户管理和系统配置|R=管理员CRUD_系统配置_统计|NR=不含普通用户功能|E=route:POST_GET_/api/admin/*|X=http|A=用户CRUD_配置_统计|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_admin
from ...db.session import get_session
from ...models import NovelProject, UsageMetric
from ...schemas.admin import (
    AdminNovelSummary,
    ChapterRuntimeLogItem,
    DailyRequestLimit,
    NovelRuntimeLogItem,
    RootCauseDiagnosticsResponse,
    Statistics,
    UpdateLogCreate,
    UpdateLogRead,
    UpdateLogUpdate,
)
from ...schemas.config import SystemConfigCreate, SystemConfigRead, SystemConfigUpdate
from ...schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from ...schemas.novel import (
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    NovelProject as NovelProjectSchema,
    NovelSectionResponse,
    NovelSectionType,
)
from ...services.admin_setting_service import AdminSettingService
from ...services.config_service import ConfigService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.root_cause_diagnostics_service import RootCauseDiagnosticsService
from ...services.update_log_service import UpdateLogService
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def get_prompt_service(session: AsyncSession = Depends(get_session)) -> PromptService:
    return PromptService(session)


def get_update_log_service(session: AsyncSession = Depends(get_session)) -> UpdateLogService:
    return UpdateLogService(session)


def get_admin_setting_service(session: AsyncSession = Depends(get_session)) -> AdminSettingService:
    return AdminSettingService(session)


def get_config_service(session: AsyncSession = Depends(get_session)) -> ConfigService:
    return ConfigService(session)


def get_novel_service(session: AsyncSession = Depends(get_session)) -> NovelService:
    return NovelService(session)



def get_root_cause_diagnostics_service() -> RootCauseDiagnosticsService:
    return RootCauseDiagnosticsService()


@router.get("/stats", response_model=Statistics)
async def read_statistics(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> Statistics:
    novel_count = await session.scalar(select(func.count(NovelProject.id))) or 0
    usage = await session.get(UsageMetric, "api_request_count")
    api_request_count = usage.value if usage else 0
    logger.info("管理员获取统计数据：小说=%s，请求=%s", novel_count, api_request_count)
    return Statistics(novel_count=novel_count, api_request_count=api_request_count)


@router.get("/diagnostics/root-cause", response_model=RootCauseDiagnosticsResponse)
async def read_root_cause_diagnostics(
    diagnostics_service: RootCauseDiagnosticsService = Depends(get_root_cause_diagnostics_service),
    _: None = Depends(get_current_admin),
) -> RootCauseDiagnosticsResponse:
    diagnostics = diagnostics_service.diagnose_root_cause()
    logger.info("管理员请求根因诊断，返回事件数=%s", len(diagnostics.get("incidents") or []))
    return RootCauseDiagnosticsResponse.model_validate(diagnostics)



@router.get("/novel-projects", response_model=List[AdminNovelSummary])
async def list_novel_projects(
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> List[AdminNovelSummary]:
    projects = await service.list_projects_for_admin()
    logger.info("管理员查看项目列表，共 %s 个", len(projects))
    return projects


@router.get("/novel-projects/{project_id}", response_model=NovelProjectSchema)
async def get_novel_project(
    project_id: str,
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> NovelProjectSchema:
    logger.info("管理员查看项目详情：%s", project_id)
    return await service.get_project_schema_for_admin(project_id)


@router.get("/novel-projects/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_project_section(
    project_id: str,
    section: NovelSectionType,
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> NovelSectionResponse:
    logger.info("管理员查看项目 %s 的 %s 区段", project_id, section)
    return await service.get_section_data_for_admin(project_id, section)


@router.get("/novel-projects/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_novel_project_chapter(
    project_id: str,
    chapter_number: int,
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> ChapterSchema:
    logger.info("管理员查看项目 %s 第 %s 章详情", project_id, chapter_number)
    return await service.get_chapter_schema_for_admin(project_id, chapter_number)


@router.get("/runtime-logs", response_model=List[NovelRuntimeLogItem])
async def list_runtime_logs(
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> List[NovelRuntimeLogItem]:
    projects = await service.list_projects_for_admin()
    results: List[NovelRuntimeLogItem] = []

    for summary in projects:
        project = await service.repo.get_by_id(summary.id)
        if not project:
            continue

        project_schema = await service._serialize_project(project)
        chapter_items: List[ChapterRuntimeLogItem] = []
        latest_updated_at = None
        active_chapter = None

        for chapter in project_schema.chapters:
            runtime = chapter.generation_runtime if isinstance(chapter.generation_runtime, dict) else {}
            summary_snapshot = {
                "target_word_count": runtime.get("target_word_count"),
                "min_word_count": runtime.get("min_word_count"),
                "actual_word_count": runtime.get("actual_word_count"),
                "generation_mode": runtime.get("generation_mode") or runtime.get("preset"),
                "review_status": runtime.get("review_status"),
                "review_skip_reason": runtime.get("review_skip_reason"),
                "diagnosis_stage_label": runtime.get("diagnosis_stage_label"),
                "optimization_stage_label": runtime.get("optimization_stage_label"),
                "word_requirement_met": runtime.get("word_requirement_met"),
                "word_requirement_reason": runtime.get("word_requirement_reason"),
                "pipeline_total_duration_ms": runtime.get("pipeline_total_duration_ms"),
                "stage_timings_ms": runtime.get("stage_timings_ms"),
                "degraded_stages": runtime.get("degraded_stages"),
                "last_error_summary": chapter.last_error_summary,
            }
            summary_snapshot = {key: value for key, value in summary_snapshot.items() if value not in (None, "", [], {})}
            runtime_snapshot = {key: value for key, value in runtime.items() if key != "events"}
            runtime_events = runtime.get("events") if isinstance(runtime.get("events"), list) else []

            should_include = (
                chapter.generation_status != ChapterGenerationStatus.NOT_GENERATED
                or bool(runtime_snapshot)
                or bool(runtime_events)
                or bool(summary_snapshot)
                or chapter.word_count > 0
            )
            if not should_include:
                continue

            chapter_items.append(
                ChapterRuntimeLogItem(
                    chapter_number=chapter.chapter_number,
                    chapter_title=chapter.title,
                    generation_status=str(chapter.generation_status.value if hasattr(chapter.generation_status, 'value') else chapter.generation_status),
                    word_count=chapter.word_count,
                    run_id=str(runtime.get("run_id")) if runtime.get("run_id") else None,
                    progress_stage=str(runtime.get("progress_stage") or chapter.progress_stage or chapter.generation_status),
                    progress_message=str(runtime.get("progress_message") or chapter.progress_message or ""),
                    started_at=chapter.started_at,
                    updated_at=chapter.updated_at,
                    summary_snapshot=summary_snapshot,
                    runtime_snapshot=runtime_snapshot,
                    runtime_events=runtime_events,
                )
            )
            if chapter.updated_at and (latest_updated_at is None or chapter.updated_at > latest_updated_at):
                latest_updated_at = chapter.updated_at
            if active_chapter is None and str(chapter.generation_status) in {
                ChapterGenerationStatus.GENERATING.value,
                ChapterGenerationStatus.EVALUATING.value,
                ChapterGenerationStatus.SELECTING.value,
                ChapterGenerationStatus.WAITING_FOR_CONFIRM.value,
                ChapterGenerationStatus.FAILED.value,
                ChapterGenerationStatus.EVALUATION_FAILED.value,
            }:
                active_chapter = chapter.chapter_number

        if not chapter_items:
            continue

        chapter_items.sort(key=lambda item: item.chapter_number)
        results.append(
            NovelRuntimeLogItem(
                project_id=project_schema.id,
                project_title=project_schema.title,
                user_id=project_schema.user_id,
                chapter_count=len(chapter_items),
                active_chapter=active_chapter,
                updated_at=latest_updated_at,
                chapters=chapter_items,
            )
        )

    results.sort(key=lambda item: item.updated_at or datetime.min, reverse=True)
    logger.info("管理员查看运行日志列表，共 %s 个项目", len(results))
    return results


@router.get("/prompts", response_model=List[PromptRead])
async def list_prompts(
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> List[PromptRead]:
    prompts = await service.list_prompts()
    logger.info("管理员请求提示词列表，共 %s 条", len(prompts))
    return prompts


@router.post("/prompts", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: PromptCreate,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> PromptRead:
    prompt = await service.create_prompt(payload)
    logger.info("管理员创建提示词：%s", prompt.id)
    return prompt


@router.get("/prompts/{prompt_id}", response_model=PromptRead)
async def get_prompt(
    prompt_id: int,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> PromptRead:
    prompt = await service.get_prompt_by_id(prompt_id)
    if not prompt:
        logger.warning("提示词 %s 不存在", prompt_id)
        raise HTTPException(status_code=404, detail="提示词不存在")
    logger.info("管理员获取提示词：%s", prompt_id)
    return prompt


@router.patch("/prompts/{prompt_id}", response_model=PromptRead)
async def update_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> PromptRead:
    result = await service.update_prompt(prompt_id, payload)
    if not result:
        logger.warning("提示词 %s 不存在，无法更新", prompt_id)
        raise HTTPException(status_code=404, detail="提示词不存在")
    logger.info("管理员更新提示词：%s", prompt_id)
    return result


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: int,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> None:
    deleted = await service.delete_prompt(prompt_id)
    if not deleted:
        logger.warning("提示词 %s 不存在，无法删除", prompt_id)
        raise HTTPException(status_code=404, detail="提示词不存在")
    logger.info("管理员删除提示词：%s", prompt_id)


@router.get("/update-logs", response_model=List[UpdateLogRead])
async def list_update_logs(
    service: UpdateLogService = Depends(get_update_log_service),
    _: None = Depends(get_current_admin),
) -> List[UpdateLogRead]:
    logs = await service.list_logs()
    logger.info("管理员查看更新日志列表，共 %s 条", len(logs))
    return [UpdateLogRead.model_validate(log) for log in logs]


@router.post("/update-logs", response_model=UpdateLogRead, status_code=status.HTTP_201_CREATED)
async def create_update_log(
    payload: UpdateLogCreate,
    service: UpdateLogService = Depends(get_update_log_service),
    current_admin=Depends(get_current_admin),
) -> UpdateLogRead:
    log = await service.create_log(
        payload.content,
        creator=current_admin.username,
        is_pinned=payload.is_pinned or False,
    )
    logger.info("管理员 %s 创建更新日志：%s", current_admin.username, log.id)
    return UpdateLogRead.model_validate(log)


@router.delete("/update-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_update_log(
    log_id: int,
    service: UpdateLogService = Depends(get_update_log_service),
    _: None = Depends(get_current_admin),
) -> None:
    await service.delete_log(log_id)
    logger.info("管理员删除更新日志：%s", log_id)


@router.patch("/update-logs/{log_id}", response_model=UpdateLogRead)
async def update_update_log(
    log_id: int,
    payload: UpdateLogUpdate,
    service: UpdateLogService = Depends(get_update_log_service),
    _: None = Depends(get_current_admin),
) -> UpdateLogRead:
    log = await service.update_log(
        log_id,
        content=payload.content,
        is_pinned=payload.is_pinned,
    )
    logger.info("管理员更新日志 %s", log_id)
    return UpdateLogRead.model_validate(log)


@router.get("/settings/daily-request-limit", response_model=DailyRequestLimit)
async def get_daily_limit(
    service: AdminSettingService = Depends(get_admin_setting_service),
    _: None = Depends(get_current_admin),
) -> DailyRequestLimit:
    value = await service.get("daily_request_limit", "100")
    logger.info("管理员查询每日请求上限：%s", value)
    return DailyRequestLimit(limit=int(value or 100))


@router.put("/settings/daily-request-limit", response_model=DailyRequestLimit)
async def update_daily_limit(
    payload: DailyRequestLimit,
    service: AdminSettingService = Depends(get_admin_setting_service),
    _: None = Depends(get_current_admin),
) -> DailyRequestLimit:
    await service.set("daily_request_limit", str(payload.limit))
    logger.info("管理员设置每日请求上限为 %s", payload.limit)
    return payload


@router.get("/system-configs", response_model=List[SystemConfigRead])
async def list_system_configs(
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> List[SystemConfigRead]:
    configs = await service.list_configs()
    logger.info("管理员获取系统配置，共 %s 条", len(configs))
    return configs


@router.get("/system-configs/{key}", response_model=SystemConfigRead)
async def get_system_config(
    key: str,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> SystemConfigRead:
    config = await service.get_config(key)
    if not config:
        logger.warning("系统配置 %s 不存在", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    logger.info("管理员查询系统配置：%s", key)
    return config


@router.put("/system-configs/{key}", response_model=SystemConfigRead)
async def upsert_system_config(
    key: str,
    payload: SystemConfigCreate,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> SystemConfigRead:
    logger.info("管理员写入系统配置：%s", key)
    config = await service.upsert_config(
        SystemConfigCreate(key=key, value=payload.value, description=payload.description)
    )
    if not config:
        logger.warning("系统配置 %s 已隐藏，无法写入", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    return config


@router.patch("/system-configs/{key}", response_model=SystemConfigRead)
async def patch_system_config(
    key: str,
    payload: SystemConfigUpdate,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> SystemConfigRead:
    config = await service.patch_config(key, payload)
    if not config:
        logger.warning("系统配置 %s 不存在，无法更新", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    logger.info("管理员部分更新系统配置：%s", key)
    return config


@router.delete("/system-configs/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_config(
    key: str,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> None:
    deleted = await service.remove_config(key)
    if not deleted:
        logger.warning("系统配置 %s 不存在，无法删除", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    logger.info("管理员删除系统配置：%s", key)


