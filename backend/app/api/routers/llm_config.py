import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.llm_config import (
    LLMAutoSwitchResponse,
    LLMConfigCreate,
    LLMConfigRead,
    LLMHealthCheckResponse,
    ModelListRequest,
)
from ...schemas.user import UserInDB
from ...services.llm_config_service import LLMConfigService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-config", tags=["LLM Configuration"])


def get_llm_config_service(session: AsyncSession = Depends(get_session)) -> LLMConfigService:
    return LLMConfigService(session)


def _empty_config(user_id: int) -> LLMConfigRead:
    return LLMConfigRead(
        user_id=user_id,
        llm_provider_url=None,
        llm_provider_model=None,
        llm_provider_api_key_masked=None,
        llm_provider_api_key_configured=False,
        llm_provider_profiles=[],
    )


@router.get("", response_model=LLMConfigRead)
async def read_llm_config(
    service: LLMConfigService = Depends(get_llm_config_service),
    current_user: UserInDB = Depends(get_current_user),
) -> LLMConfigRead:
    config = await service.get_config(current_user.id)
    if not config:
        logger.info("用户 %s 尚未保存 LLM 配置", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "LLM_CONFIG_NOT_FOUND",
                "message": "当前用户还没有保存 LLM 配置",
                "hint": "请在设置页保存至少一个可用的配置组。",
            },
        )

    logger.info("已读取用户 %s 的 LLM 配置", current_user.id)
    return config


@router.put("", response_model=LLMConfigRead)
async def upsert_llm_config(
    payload: LLMConfigCreate,
    service: LLMConfigService = Depends(get_llm_config_service),
    current_user: UserInDB = Depends(get_current_user),
) -> LLMConfigRead:
    logger.info("正在写入用户 %s 的 LLM 配置", current_user.id)
    return await service.upsert_config(current_user.id, payload)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    service: LLMConfigService = Depends(get_llm_config_service),
    current_user: UserInDB = Depends(get_current_user),
) -> None:
    deleted = await service.delete_config(current_user.id)
    if not deleted:
        logger.warning("用户 %s 没有可删除的 LLM 配置，已跳过删除", current_user.id)
        raise HTTPException(
            status_code=404,
            detail={
                "code": "LLM_CONFIG_NOT_FOUND",
                "message": "当前用户还没有保存 LLM 配置",
                "hint": "当前没有可删除的配置，请先确认是否已保存过配置。",
            },
        )

    logger.info("已删除用户 %s 的 LLM 配置", current_user.id)


@router.post("/models", response_model=List[str])
async def list_models(
    payload: ModelListRequest,
    service: LLMConfigService = Depends(get_llm_config_service),
    current_user: UserInDB = Depends(get_current_user),
) -> List[str]:
    try:
        models = await service.get_available_models(
            api_key=payload.llm_provider_api_key,
            base_url=payload.llm_provider_url,
        )
        logger.info("已为用户 %s 获取到 %s 个可用模型", current_user.id, len(models))
        return models
    except ValueError as exc:
        logger.warning("用户 %s 的模型列表请求无效：%s", current_user.id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "LLM_MODELS_REQUEST_INVALID",
                "message": "模型列表请求无效",
                "hint": "请至少提供一个可用的 API Key。",
                "rootCause": str(exc),
            },
        )
    except Exception as exc:
        logger.warning("用户 %s 的模型列表探测失败：%s", current_user.id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "LLM_MODELS_FETCH_FAILED",
                "message": "模型列表获取失败",
                "hint": "请检查 API 地址、API Key 和上游服务状态。",
                "rootCause": str(exc),
            },
        )


@router.get("/source-trace")
async def trace_llm_config_source(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> dict:
    logger.info("正在追踪用户 %s 的 LLM 配置来源", current_user.id)
    from ...services.llm_service import LLMService

    service = LLMService(session)
    return await service.trace_llm_config_source(
        current_user.id,
        username=current_user.username,
    )


@router.get("/health-check", response_model=LLMHealthCheckResponse)
async def health_check_llm_config(
    include_disabled: bool = True,
    service: LLMConfigService = Depends(get_llm_config_service),
    current_user: UserInDB = Depends(get_current_user),
) -> LLMHealthCheckResponse:
    logger.info("正在执行用户 %s 的 LLM 健康检查", current_user.id)
    return await service.run_health_check(
        user_id=current_user.id,
        include_disabled=include_disabled,
    )


@router.post("/auto-switch", response_model=LLMAutoSwitchResponse)
async def auto_switch_llm_provider(
    service: LLMConfigService = Depends(get_llm_config_service),
    current_user: UserInDB = Depends(get_current_user),
) -> LLMAutoSwitchResponse:
    logger.info("正在执行用户 %s 的 LLM 自动切换", current_user.id)
    return await service.auto_switch_provider(user_id=current_user.id)
