# AIMETA P=LLM服务_大模型调用封装|R=API调用_流式生成|NR=不含业务逻辑|E=LLMService|X=internal|A=服务类|D=openai,httpx|S=net|RD=./README.ai
import asyncio
import logging
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

import httpx
from fastapi import HTTPException, status
from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

from ..core.config import settings
from ..repositories.llm_config_repository import LLMConfigRepository
from ..repositories.system_config_repository import SystemConfigRepository
from ..repositories.user_repository import UserRepository
from ..services.admin_setting_service import AdminSettingService
from ..services.prompt_service import PromptService
from ..services.usage_service import UsageService
from ..utils.llm_tool import ChatMessage, LLMClient

logger = logging.getLogger(__name__)

_PROVIDER_SEMAPHORES: Dict[str, asyncio.Semaphore] = {}

try:  # pragma: no cover - 运行环境未安装时兼容
    from ollama import AsyncClient as OllamaAsyncClient
except ImportError:  # pragma: no cover - Ollama 为可选依赖
    OllamaAsyncClient = None


class LLMService:
    """封装与大模型交互的所有逻辑，包括配额控制与配置选择。"""

    def __init__(self, session):
        self.session = session
        self.llm_repo = LLMConfigRepository(session)
        self.system_config_repo = SystemConfigRepository(session)
        self.user_repo = UserRepository(session)
        self.admin_setting_service = AdminSettingService(session)
        self.usage_service = UsageService(session)
        self._embedding_dimensions: Dict[str, int] = {}

    @staticmethod
    def _extract_provider_error_detail(exc: Exception, default: str) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    error_data = payload.get("error", payload)
                    if isinstance(error_data, dict):
                        return error_data.get("message_zh") or error_data.get("message") or default
            except Exception:
                pass
        return str(exc) or default

    @staticmethod
    def _build_error_detail(
        code: str,
        message: str,
        *,
        hint: Optional[str] = None,
        retryable: Optional[bool] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        detail: Dict[str, Any] = {
            "code": code,
            "message": message,
        }
        if hint:
            detail["hint"] = hint
        if retryable is not None:
            detail["retryable"] = retryable
        if extra:
            detail.update(extra)
        return detail

    @staticmethod
    def _detail_to_message(detail: Any) -> str:
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            code = detail.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()
            return json.dumps(detail, ensure_ascii=False)
        if isinstance(detail, str):
            return detail.strip()
        return str(detail or "").strip()

    @classmethod
    def _normalize_config_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or cls._is_placeholder_config_value(normalized):
            return None
        return normalized

    def _build_provider_auth_detail(self, message: str, *, status_code: int) -> Dict[str, Any]:
        normalized_message = self._detail_to_message(message) or "AI Provider 鉴权失败，请检查 API Key、模型权限和网关认证配置"
        status_label = "401" if status_code == 401 else "403"
        return self._build_error_detail(
            code="PROVIDER_AUTH_FAILED" if status_code == 401 else "PROVIDER_PERMISSION_DENIED",
            message="AI Provider 鉴权失败，请检查 API Key、模型权限和网关认证配置",
            hint="请优先检查当前配置组的 API Key 是否有效、模型是否有权限、以及中转网关是否已正确注入上游认证头。",
            retryable=False,
            extra={"root_cause": normalized_message, "provider_status": status_label},
        )

    @staticmethod
    def _is_placeholder_config_value(value: Optional[str]) -> bool:
        if value is None:
            return False
        normalized = value.strip().lower()
        return normalized in {
            "",
            "none",
            "null",
            "sk-placeholder",
            "your-api-key",
            "your_api_key",
            "your-openai-api-key",
            "your_openai_api_key",
            "changeme",
        }

    @staticmethod
    def _should_retry_without_json_mode(detail: str) -> bool:
        lowered = (detail or "").lower()
        return (
            ("json mode" in lowered and "not supported" in lowered)
            or ("response_format" in lowered and "not supported" in lowered)
            or ("json_object" in lowered and "not supported" in lowered)
            or ("enable_thinking is true" in lowered and "json" in lowered)
        )

    @staticmethod
    def _get_llm_env_value(key: str) -> Optional[str]:
        alias_map = {
            "llm.api_key": ("OPENAI_API_KEY",),
            "llm.base_url": ("OPENAI_API_BASE_URL", "OPENAI_BASE_URL"),
            "llm.model": ("OPENAI_MODEL_NAME",),
        }
        env_names = alias_map.get(key, (key.upper().replace(".", "_"),))
        for env_name in env_names:
            value = os.getenv(env_name)
            if value and value.strip():
                return value
        return None

    async def get_llm_response(
        self,
        system_prompt: str,
        conversation_history: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        user_id: Optional[int] = None,
        timeout: float = 180.0,  # 默认3分钟超时
        response_format: Optional[str] = "json_object",
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        allow_truncated_response: bool = False,
        retry_same_model_once: bool = True,
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}, *conversation_history]
        hard_timeout = max(10.0, float(timeout) + 8.0)
        try:
            return await asyncio.wait_for(
                self._stream_and_collect(
                    messages,
                    temperature=temperature,
                    user_id=user_id,
                    timeout=timeout,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    allow_truncated_response=allow_truncated_response,
                    retry_same_model_once=retry_same_model_once,
                ),
                timeout=hard_timeout,
            )
        except asyncio.TimeoutError as exc:
            logger.error(
                "LLM hard timeout exceeded: user_id=%s configured_timeout=%ss hard_timeout=%ss",
                user_id,
                timeout,
                hard_timeout,
            )
            raise HTTPException(
                status_code=504,
                detail=self._build_error_detail(
                    code="PROVIDER_TIMEOUT",
                    message="AI 服务在限定时间内未完成响应，系统已主动中止本次调用。",
                    hint="上游网关长时间无响应，请稍后重试、切换 Provider，或降低当前阶段复杂度。",
                    retryable=True,
                    extra={"configured_timeout": timeout, "hard_timeout": hard_timeout},
                ),
            ) from exc

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        user_id: Optional[int] = None,
        timeout: float = 300.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        top_p: Optional[float] = None,
        allow_truncated_response: bool = False,
    ) -> str:
        """兼容旧版接口的文本生成入口，统一走 get_llm_response。"""
        return await self.get_llm_response(
            system_prompt=system_prompt or "你是一位专业写作助手。",
            conversation_history=[{"role": "user", "content": prompt}],
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            response_format=response_format,
            max_tokens=max_tokens,
            top_p=top_p,
            allow_truncated_response=allow_truncated_response,
        )

    async def get_summary(
        self,
        chapter_content: str,
        *,
        temperature: float = 0.2,
        user_id: Optional[int] = None,
        timeout: float = 180.0,
        system_prompt: Optional[str] = None,
    ) -> str:
        if not system_prompt:
            prompt_service = PromptService(self.session)
            system_prompt = await prompt_service.get_prompt("extraction")
        if not system_prompt:
            logger.error("未配置名为 'extraction' 的摘要提示词，无法生成章节摘要")
            raise HTTPException(status_code=500, detail="未配置摘要提示词，请联系管理员配置 'extraction' 提示词")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chapter_content},
        ]
        return await self._stream_and_collect(messages, temperature=temperature, user_id=user_id, timeout=timeout)

    @staticmethod
    def _get_provider_semaphore(base_url: Optional[str]) -> asyncio.Semaphore:
        key = (base_url or 'default').rstrip('/').lower() or 'default'
        semaphore = _PROVIDER_SEMAPHORES.get(key)
        if semaphore is None:
            semaphore = asyncio.Semaphore(2)
            _PROVIDER_SEMAPHORES[key] = semaphore
        return semaphore

    async def _stream_and_collect(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        user_id: Optional[int],
        timeout: float,
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        allow_truncated_response: bool = False,
        retry_same_model_once: bool = True,
    ) -> str:
        config = await self._resolve_llm_config(user_id)
        chat_messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages]

        primary_api_key = (config.get("api_key") or "").strip()
        primary_model = (config.get("model") or "").strip()
        primary_base_url = config.get("base_url")

        if not primary_api_key:
            raise HTTPException(status_code=500, detail="未配置可用的 API Key，请联系管理员检查当前用户的 LLM 配置")
        if not primary_model:
            raise HTTPException(status_code=500, detail="未配置可用的模型名称，请联系管理员检查当前用户的 LLM 配置")

        logger.debug(
            "Streaming LLM response in single-config mode: model=%s base_url=%s user_id=%s messages=%d",
            primary_model,
            primary_base_url,
            user_id,
            len(messages),
        )

        full_response = ""
        finish_reason: Optional[str] = None
        last_exception: Optional[HTTPException] = None
        client = LLMClient(api_key=primary_api_key, base_url=primary_base_url)
        provider_semaphore = self._get_provider_semaphore(primary_base_url)

        try:
            async with provider_semaphore:
                full_response, finish_reason = await self._stream_single_model(
                    client=client,
                    chat_messages=chat_messages,
                    model_name=primary_model,
                    temperature=temperature,
                    user_id=user_id,
                    timeout=timeout,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    retry_same_model_once=retry_same_model_once,
                )
        except HTTPException as exc:
            last_exception = exc

        if not full_response and last_exception:
            raise HTTPException(status_code=last_exception.status_code, detail=last_exception.detail) from last_exception

        logger.debug(
            "LLM response collected: model=%s api_key=%s base_url=%s user_id=%s finish_reason=%s preview=%s",
            primary_model,
            self._mask_api_key(primary_api_key),
            primary_base_url,
            user_id,
            finish_reason,
            full_response[:500],
        )

        if finish_reason == "length":
            logger.warning(
                "LLM response truncated: model=%s user_id=%s response_length=%d",
                selected_model,
                user_id,
                len(full_response),
            )
            if not allow_truncated_response:
                raise HTTPException(
                    status_code=500,
                    detail=f"AI 响应因长度限制被截断（已生成 {len(full_response)} 字符），请缩短输入内容或调整模型参数"
                )

        if not full_response:
            logger.error(
                "LLM returned empty response: model=%s user_id=%s finish_reason=%s",
                selected_model,
                user_id,
                finish_reason,
            )
            raise HTTPException(
                status_code=500,
                detail=f"AI 未返回有效内容（结束原因: {finish_reason or '未知'}），请稍后重试或联系管理员"
            )

        try:
            await self.usage_service.increment("api_request_count")
        except Exception as exc:  # noqa: BLE001 - usage 统计失败不应阻断主流程
            logger.warning("Usage metric increment failed without blocking response: key=%s error=%s", "api_request_count", exc)
        logger.debug(
            "LLM response success: model=%s base_url=%s user_id=%s chars=%d",
            primary_model,
            primary_base_url,
            user_id,
            len(full_response),
        )
        return full_response

    async def _stream_single_model(
        self,
        *,
        client: LLMClient,
        chat_messages: List[ChatMessage],
        model_name: str,
        temperature: float,
        user_id: Optional[int],
        timeout: float,
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        retry_same_model_once: bool = True,
    ) -> tuple[str, Optional[str]]:
        stream_response_format = response_format
        full_response = ""
        finish_reason = None
        network_retry_used = False

        max_attempts = 2 if retry_same_model_once else 1
        for _ in range(max_attempts):
            full_response = ""
            finish_reason = None
            try:
                async for part in client.stream_chat(
                    messages=chat_messages,
                    model=model_name,
                    temperature=temperature,
                    timeout=int(timeout),
                    response_format=stream_response_format,
                    max_tokens=max_tokens,
                    top_p=top_p,
                ):
                    if part.get("content"):
                        full_response += part["content"]
                    if part.get("finish_reason"):
                        finish_reason = part["finish_reason"]
                return full_response, finish_reason
            except RateLimitError as exc:
                detail = self._extract_provider_error_detail(exc, "AI 服务当前限流，请稍后重试或切换模型")
                logger.warning(
                    "LLM stream rate limited: model=%s user_id=%s detail=%s",
                    model_name,
                    user_id,
                    detail,
                )
                raise HTTPException(status_code=429, detail=detail) from exc
            except BadRequestError as exc:
                detail = self._extract_provider_error_detail(exc, "AI 服务请求失败，请检查模型、API Key 或输入内容")
                if stream_response_format and self._should_retry_without_json_mode(detail):
                    logger.warning(
                        "LLM model does not support response_format=%s, retry without JSON mode: model=%s user_id=%s detail=%s",
                        stream_response_format,
                        model_name,
                        user_id,
                        detail,
                    )
                    stream_response_format = None
                    continue
                logger.warning(
                    "LLM stream rejected: model=%s user_id=%s status=400 detail=%s",
                    model_name,
                    user_id,
                    detail,
                )
                raise HTTPException(status_code=400, detail=detail) from exc
            except AuthenticationError as exc:
                detail = self._extract_provider_error_detail(exc, "AI 服务请求失败，请检查模型、API Key 或输入内容")
                logger.warning(
                    "LLM stream rejected: model=%s user_id=%s status=401 detail=%s",
                    model_name,
                    user_id,
                    detail,
                )
                raise HTTPException(status_code=401, detail=self._build_provider_auth_detail(detail, status_code=401)) from exc
            except PermissionDeniedError as exc:
                detail = self._extract_provider_error_detail(exc, "AI 服务请求失败，请检查模型、API Key 或输入内容")
                logger.warning(
                    "LLM stream rejected: model=%s user_id=%s status=403 detail=%s",
                    model_name,
                    user_id,
                    detail,
                )
                raise HTTPException(status_code=403, detail=self._build_provider_auth_detail(detail, status_code=403)) from exc
            except InternalServerError as exc:
                detail = "AI 服务内部错误，请稍后重试"
                response = getattr(exc, "response", None)
                if response is not None:
                    try:
                        payload = response.json()
                        error_data = payload.get("error", {}) if isinstance(payload, dict) else {}
                        detail = error_data.get("message_zh") or error_data.get("message") or detail
                    except Exception:
                        detail = str(exc) or detail
                else:
                    detail = str(exc) or detail
                logger.error(
                    "LLM stream internal error: model=%s user_id=%s detail=%s",
                    model_name,
                    user_id,
                    detail,
                    exc_info=exc,
                )
                lowered_detail = detail.lower()
                if "auth_unavailable" in lowered_detail or "missing authentication header" in lowered_detail or "no auth available" in lowered_detail:
                    raise HTTPException(
                        status_code=401,
                        detail=self._build_provider_auth_detail(detail, status_code=401),
                    ) from exc
                if retry_same_model_once and not network_retry_used:
                    network_retry_used = True
                    logger.warning(
                        "LLM stream internal error, retrying once with same model: model=%s user_id=%s detail=%s",
                        model_name,
                        user_id,
                        detail,
                    )
                    await asyncio.sleep(0.8)
                    continue
                fallback_result = await self._try_non_stream_fallback_once(
                    client=client,
                    chat_messages=chat_messages,
                    model_name=model_name,
                    temperature=temperature,
                    timeout=timeout,
                    response_format=stream_response_format,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    user_id=user_id,
                    trigger=detail,
                )
                if fallback_result is not None:
                    return fallback_result
                raise HTTPException(
                    status_code=503,
                    detail=self._build_error_detail(
                        code="PROVIDER_INTERNAL_ERROR",
                        message=self._detail_to_message(detail),
                        hint="上游流式服务异常，系统已自动重试并尝试非流式兜底，仍失败请稍后重试或切换 Provider。",
                        retryable=True,
                    ),
                ) from exc
            except APIStatusError as exc:
                detail = self._extract_provider_error_detail(exc, "AI 服务调用失败，请稍后重试")
                status_code = exc.status_code or 502
                logger.error(
                    "LLM stream status error: model=%s user_id=%s status=%s detail=%s",
                    model_name,
                    user_id,
                    status_code,
                    detail,
                    exc_info=exc,
                )
                if status_code >= 500:
                    if retry_same_model_once and not network_retry_used:
                        network_retry_used = True
                        logger.warning(
                            "LLM stream 5xx status error, retrying once with same model: model=%s user_id=%s status=%s detail=%s",
                            model_name,
                            user_id,
                            status_code,
                            detail,
                        )
                        await asyncio.sleep(0.8)
                        continue
                    fallback_result = await self._try_non_stream_fallback_once(
                        client=client,
                        chat_messages=chat_messages,
                        model_name=model_name,
                        temperature=temperature,
                        timeout=timeout,
                        response_format=stream_response_format,
                        max_tokens=max_tokens,
                        top_p=top_p,
                        user_id=user_id,
                        trigger=detail,
                    )
                    if fallback_result is not None:
                        return fallback_result
                    raise HTTPException(
                        status_code=503,
                        detail=self._build_error_detail(
                            code="PROVIDER_STATUS_ERROR",
                            message=self._detail_to_message(detail),
                            hint="上游服务返回 5xx，系统已自动重试并尝试非流式兜底，仍失败请稍后重试。",
                            retryable=True,
                        ),
                    ) from exc
                raise HTTPException(status_code=status_code, detail=detail) from exc
            except APIError as exc:
                detail = self._extract_provider_error_detail(exc, "AI 服务调用失败，请稍后重试")
                logger.error(
                    "LLM stream API error: model=%s user_id=%s detail=%s",
                    model_name,
                    user_id,
                    detail,
                    exc_info=exc,
                )
                if retry_same_model_once and not network_retry_used:
                    network_retry_used = True
                    logger.warning(
                        "LLM API error, retrying once with same model: model=%s user_id=%s detail=%s",
                        model_name,
                        user_id,
                        detail,
                    )
                    await asyncio.sleep(0.8)
                    continue
                raise HTTPException(
                    status_code=503,
                    detail=self._build_error_detail(
                        code="PROVIDER_API_ERROR",
                        message=self._detail_to_message(detail),
                        hint="请检查 Provider 状态或稍后重试。",
                        retryable=True,
                    ),
                ) from exc
            except (
                httpx.RemoteProtocolError,
                httpx.ReadTimeout,
                httpx.ReadError,
                httpx.ConnectError,
                APIConnectionError,
                APITimeoutError,
            ) as exc:
                if isinstance(exc, httpx.RemoteProtocolError):
                    detail = "AI 服务连接被意外中断，请稍后重试"
                elif isinstance(exc, (httpx.ReadTimeout, APITimeoutError)):
                    detail = "AI 服务响应超时，请稍后重试"
                elif isinstance(exc, httpx.ReadError):
                    detail = "AI 服务响应流读取失败，请稍后重试"
                else:
                    detail = "无法连接到 AI 服务，请稍后重试"
                logger.error(
                    "LLM stream failed: model=%s user_id=%s detail=%s",
                    model_name,
                    user_id,
                    detail,
                    exc_info=exc,
                )
                if retry_same_model_once and not network_retry_used:
                    network_retry_used = True
                    logger.warning(
                        "LLM transient network error, retrying once with same model: model=%s user_id=%s detail=%s",
                        model_name,
                        user_id,
                        detail,
                    )
                    await asyncio.sleep(0.8)
                    continue
                fallback_result = await self._try_non_stream_fallback_once(
                    client=client,
                    chat_messages=chat_messages,
                    model_name=model_name,
                    temperature=temperature,
                    timeout=timeout,
                    response_format=stream_response_format,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    user_id=user_id,
                    trigger=detail,
                )
                if fallback_result is not None:
                    return fallback_result
                raise HTTPException(
                    status_code=503,
                    detail=self._build_error_detail(
                        code="PROVIDER_NETWORK_ERROR",
                        message=detail,
                        hint="网络异常时系统已自动重试并执行非流式兜底，仍失败请稍后重试或切换 Provider",
                        retryable=True,
                    ),
                ) from exc
            except httpx.HTTPError as exc:
                detail = "AI 服务网络异常，请稍后重试"
                logger.error(
                    "LLM stream httpx error: model=%s user_id=%s detail=%s",
                    model_name,
                    user_id,
                    detail,
                    exc_info=exc,
                )
                if retry_same_model_once and not network_retry_used:
                    network_retry_used = True
                    logger.warning(
                        "LLM httpx error, retrying once with same model: model=%s user_id=%s detail=%s",
                        model_name,
                        user_id,
                        detail,
                    )
                    await asyncio.sleep(0.8)
                    continue
                fallback_result = await self._try_non_stream_fallback_once(
                    client=client,
                    chat_messages=chat_messages,
                    model_name=model_name,
                    temperature=temperature,
                    timeout=timeout,
                    response_format=stream_response_format,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    user_id=user_id,
                    trigger=detail,
                )
                if fallback_result is not None:
                    return fallback_result
                raise HTTPException(
                    status_code=503,
                    detail=self._build_error_detail(
                        code="PROVIDER_HTTP_ERROR",
                        message=detail,
                        hint="请求链路异常，建议执行 Provider 健康检查后重试",
                        retryable=True,
                    ),
                ) from exc

        return full_response, finish_reason

    async def _try_non_stream_fallback_once(
        self,
        *,
        client: LLMClient,
        chat_messages: List[ChatMessage],
        model_name: str,
        temperature: float,
        timeout: float,
        response_format: Optional[str],
        max_tokens: Optional[int],
        top_p: Optional[float],
        user_id: Optional[int],
        trigger: str,
    ) -> Optional[tuple[str, Optional[str]]]:
        logger.warning(
            "Attempting non-stream fallback after stream failure: model=%s user_id=%s trigger=%s",
            model_name,
            user_id,
            trigger,
        )
        try:
            result = await client.chat(
                messages=chat_messages,
                model=model_name,
                temperature=temperature,
                timeout=int(timeout),
                response_format=response_format,
                max_tokens=max_tokens,
                top_p=top_p,
            )
            content = (result.get("content") or "").strip()
            if not content:
                logger.warning(
                    "Non-stream fallback returned empty content: model=%s user_id=%s",
                    model_name,
                    user_id,
                )
                return None
            logger.debug(
                "Non-stream fallback succeeded: model=%s user_id=%s chars=%d",
                model_name,
                user_id,
                len(content),
            )
            return content, result.get("finish_reason")
        except Exception as exc:  # noqa: BLE001 - fallback should not break the primary path
            logger.warning(
                "Non-stream fallback failed: model=%s user_id=%s error=%s",
                model_name,
                user_id,
                exc,
            )
            return None

    @staticmethod
    def _parse_model_list(raw_value: Optional[str]) -> List[str]:
        if not raw_value:
            return []
        items = re.split(r"[,，;\n\r\t ]+", str(raw_value))
        return [item.strip() for item in items if item and item.strip()]

    @staticmethod
    def _take_first_config_value(raw_value: Optional[str]) -> Optional[str]:
        values = LLMService._parse_model_list(raw_value)
        return values[0] if values else None

    @classmethod
    def _summarize_values(
        cls,
        values: List[str],
        *,
        masker: Optional[Callable[[Optional[str]], str]] = None,
    ) -> Dict[str, Any]:
        normalized = [item for item in values if item]
        sample = None
        if normalized:
            sample = masker(normalized[0]) if masker else normalized[0]
        return {
            "count": len(normalized),
            "sample": sample,
            "values": [masker(item) if masker else item for item in normalized],
        }

    @classmethod
    def _build_source_bucket(
        cls,
        values: List[str],
        *,
        source: Optional[str],
        masker: Optional[Callable[[Optional[str]], str]] = None,
    ) -> Dict[str, Any]:
        summary = cls._summarize_values(values, masker=masker)
        return {
            "source": source,
            **summary,
        }

    async def trace_llm_config_source(self, user_id: Optional[int], *, username: Optional[str] = None) -> Dict[str, Any]:
        warnings: List[str] = []
        user_bucket: Optional[Dict[str, Any]] = None

        if user_id:
            user_config = await self.llm_repo.get_by_user(user_id)
            if user_config:
                parsed_profiles = self._parse_provider_profiles(getattr(user_config, "llm_provider_profiles", None))
                if parsed_profiles:
                    primary_profile = parsed_profiles[0]
                    user_bucket = {
                        "level": "user_config",
                        "base_url": primary_profile.get("base_url"),
                        "api_keys": self._summarize_values(primary_profile.get("api_keys") or [], masker=self._mask_api_key),
                        "models": self._summarize_values(primary_profile.get("models") or []),
                    }
                else:
                    api_key = self._take_first_config_value(getattr(user_config, "llm_provider_api_key", None))
                    model = self._take_first_config_value(getattr(user_config, "llm_provider_model", None))
                    user_bucket = {
                        "level": "user_config",
                        "base_url": getattr(user_config, "llm_provider_url", None),
                        "api_keys": self._summarize_values([api_key] if api_key else [], masker=self._mask_api_key),
                        "models": self._summarize_values([model] if model else []),
                    }
            else:
                warnings.append("当前用户在 llm_configs 中没有自定义配置记录")

        env_api_key = self._get_llm_env_value("llm.api_key")
        env_base_url = self._get_llm_env_value("llm.base_url")
        env_model = self._get_llm_env_value("llm.model")
        env_bucket = {
            "level": "env_runtime",
            "api_keys": self._build_source_bucket(
                [self._take_first_config_value(env_api_key)] if self._take_first_config_value(env_api_key) else [],
                source="env:OPENAI_API_KEY" if env_api_key else None,
                masker=self._mask_api_key,
            ),
            "base_url": {
                "value": env_base_url,
                "source": "env:OPENAI_API_BASE_URL/OPENAI_BASE_URL" if env_base_url else None,
            },
            "models": self._build_source_bucket(
                [self._take_first_config_value(env_model)] if self._take_first_config_value(env_model) else [],
                source="env:OPENAI_MODEL_NAME" if env_model else None,
            ),
        }

        resolved = await self._resolve_llm_config(
            user_id,
            enforce_daily_limit=False,
            require_primary_api_key=False,
        )
        if not resolved.get("api_key"):
            warnings.append("当前未解析出可用的主 API Key")
        if not resolved.get("model"):
            warnings.append("当前未解析出可用的主模型")
        if not user_bucket and not env_bucket["api_keys"]["count"]:
            warnings.append("当前用户配置与运行时环境变量中都没有检测到 API Key")

        resolved_source = {
            "api_key": "user_config" if user_bucket and user_bucket.get("api_keys", {}).get("count") else "env_runtime" if env_bucket["api_keys"]["count"] else None,
            "base_url": "user_config" if user_bucket and user_bucket.get("base_url") else "env_runtime" if env_bucket["base_url"]["value"] else None,
            "model": "user_config" if user_bucket and user_bucket.get("models", {}).get("count") else "env_runtime" if env_bucket["models"]["count"] else None,
        }

        return {
            "binding": {
                "resolved_user_id": user_id,
                "resolved_username": username,
            },
            "resolved": {
                "api_key": self._mask_api_key(resolved.get("api_key")),
                "base_url": resolved.get("base_url"),
                "model": resolved.get("model"),
                "source": resolved_source,
            },
            "layers": {
                "user_config": user_bucket,
                "env_runtime": env_bucket,
            },
            "warnings": warnings,
        }

    @staticmethod
    def _mask_api_key(api_key: Optional[str]) -> str:
        key = (api_key or "").strip()
        if not key:
            return "<empty>"
        if len(key) <= 10:
            return "***"
        return f"{key[:6]}...{key[-4:]}"


    @staticmethod
    def _parse_profile_items(raw_items: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []
        parsed: List[Dict[str, Any]] = []
        for raw in raw_items:
            if isinstance(raw, str):
                value = raw.strip()
                if value:
                    parsed.append({"value": value, "enabled": True})
                continue
            if not isinstance(raw, dict):
                continue
            value = str(raw.get("value", "")).strip()
            if not value:
                continue
            parsed.append({"value": value, "enabled": bool(raw.get("enabled", True))})
        return parsed

    def _parse_provider_profiles(self, raw_profiles: Any) -> List[Dict[str, Any]]:
        if not raw_profiles:
            return []

        payload: Any = raw_profiles
        if isinstance(raw_profiles, str):
            try:
                payload = json.loads(raw_profiles)
            except Exception:
                logger.warning("Failed to parse llm_provider_profiles JSON, ignore profiles field")
                return []

        if not isinstance(payload, list):
            return []

        normalized_profiles: List[Dict[str, Any]] = []
        for idx, profile in enumerate(payload):
            if not isinstance(profile, dict):
                continue
            enabled = bool(profile.get("enabled", True))
            base_url = str(
                profile.get("llm_provider_url")
                or profile.get("base_url")
                or ""
            ).strip() or None
            profile_id = str(profile.get("id") or f"profile-{idx + 1}").strip() or f"profile-{idx + 1}"
            profile_name = str(profile.get("name") or f"Profile {idx + 1}").strip() or f"Profile {idx + 1}"

            raw_api_items = self._parse_profile_items(profile.get("api_keys"))
            raw_model_items = self._parse_profile_items(profile.get("models"))

            if not raw_api_items:
                first_api_key = self._take_first_config_value(profile.get("llm_provider_api_key") or profile.get("api_key"))
                if first_api_key:
                    raw_api_items.append({"value": first_api_key, "enabled": True})
            if not raw_model_items:
                first_model = self._take_first_config_value(profile.get("llm_provider_model") or profile.get("model"))
                if first_model:
                    raw_model_items.append({"value": first_model, "enabled": True})

            api_keys = [item["value"] for item in raw_api_items if item.get("enabled", True)][:1]
            models = [item["value"] for item in raw_model_items if item.get("enabled", True)][:1]

            if not api_keys or not models:
                continue

            normalized_profiles.append(
                {
                    "id": profile_id,
                    "name": profile_name,
                    "enabled": enabled,
                    "base_url": base_url,
                    "api_keys": api_keys,
                    "models": models,
                }
            )

        return [profile for profile in normalized_profiles if profile.get("enabled", True)]

    async def _resolve_llm_config(
        self,
        user_id: Optional[int],
        *,
        enforce_daily_limit: bool = True,
        require_primary_api_key: bool = True,
    ) -> Dict[str, Any]:
        if user_id:
            config = await self.llm_repo.get_by_user(user_id)
            if config:
                parsed_profiles = self._parse_provider_profiles(getattr(config, "llm_provider_profiles", None))
                if parsed_profiles:
                    primary_profile = parsed_profiles[0]
                    return {
                        "api_key": primary_profile["api_keys"][0],
                        "base_url": primary_profile.get("base_url"),
                        "model": primary_profile["models"][0],
                    }

                normalized_user_api_key = self._normalize_config_text(config.llm_provider_api_key)
                if normalized_user_api_key:
                    primary_api_key = self._take_first_config_value(normalized_user_api_key)
                    normalized_user_model = self._normalize_config_text(config.llm_provider_model)
                    primary_model = self._take_first_config_value(normalized_user_model)
                    return {
                        "api_key": primary_api_key,
                        "base_url": config.llm_provider_url,
                        "model": primary_model,
                    }

        if user_id and enforce_daily_limit:
            await self._enforce_daily_limit(user_id)

        api_key = self._normalize_config_text(self._get_llm_env_value("llm.api_key"))
        base_url = self._normalize_config_text(self._get_llm_env_value("llm.base_url"))
        model = self._normalize_config_text(self._get_llm_env_value("llm.model"))
        primary_api_key = self._take_first_config_value(api_key) or api_key
        primary_model = self._take_first_config_value(model) or model

        if require_primary_api_key and not primary_api_key:
            logger.error("未配置默认 LLM API Key，且用户 %s 未设置自定义 API Key", user_id)
            raise HTTPException(
                status_code=500,
                detail="未配置默认 LLM API Key，请联系管理员配置系统默认 API Key 或在个人设置中配置自定义 API Key"
            )

        return {
            "api_key": primary_api_key,
            "base_url": base_url,
            "model": primary_model,
        }

    async def get_embedding(
        self,
        text: str,
        *,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
    ) -> List[float]:
        """生成文本向量，用于章节 RAG 检索，支持 openai 与 ollama 双提供方。"""
        provider = await self._get_config_value("embedding.provider") or "openai"
        default_model = (
            await self._get_config_value("ollama.embedding_model") or "nomic-embed-text:latest"
            if provider == "ollama"
            else await self._get_config_value("embedding.model") or "text-embedding-3-large"
        )
        target_model = model or default_model

        if provider == "ollama":
            if OllamaAsyncClient is None:
                logger.error("未安装 ollama 依赖，无法调用本地嵌入模型。")
                raise HTTPException(status_code=500, detail="缺少 Ollama 依赖，请先安装 ollama 包。")

            base_url = (
                await self._get_config_value("ollama.embedding_base_url")
                or await self._get_config_value("embedding.base_url")
            )
            client = OllamaAsyncClient(host=base_url)
            try:
                response = await client.embeddings(model=target_model, prompt=text)
            except Exception as exc:  # pragma: no cover - 本地服务调用失败
                logger.error(
                    "Ollama 嵌入请求失败: model=%s base_url=%s error=%s",
                    target_model,
                    base_url,
                    exc,
                    exc_info=True,
                )
                return []
            embedding: Optional[List[float]]
            if isinstance(response, dict):
                embedding = response.get("embedding")
            else:
                embedding = getattr(response, "embedding", None)
            if not embedding:
                logger.warning("Ollama 返回空向量: model=%s", target_model)
                return []
            if not isinstance(embedding, list):
                embedding = list(embedding)
        else:
            config = await self._resolve_llm_config(user_id)
            api_key = await self._get_config_value("embedding.api_key") or config["api_key"]
            base_url = await self._get_config_value("embedding.base_url") or config.get("base_url")
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            try:
                response = await client.embeddings.create(
                    input=text,
                    model=target_model,
                )
            except Exception as exc:  # pragma: no cover - 网络或鉴权失败
                logger.error(
                    "OpenAI 嵌入请求失败: model=%s base_url=%s user_id=%s error=%s",
                    target_model,
                    base_url,
                    user_id,
                    exc,
                    exc_info=True,
                )
                return []
            if not response.data:
                logger.warning("OpenAI 嵌入请求返回空数据: model=%s user_id=%s", target_model, user_id)
                return []
            embedding = response.data[0].embedding

        if not isinstance(embedding, list):
            embedding = list(embedding)

        dimension = len(embedding)
        if not dimension:
            vector_size_str = await self._get_config_value("embedding.model_vector_size")
            if vector_size_str:
                dimension = int(vector_size_str)
        if dimension:
            self._embedding_dimensions[target_model] = dimension
        return embedding

    async def get_embedding_dimension(self, model: Optional[str] = None) -> Optional[int]:
        """获取嵌入向量维度，优先返回缓存结果，其次读取配置。"""
        provider = await self._get_config_value("embedding.provider") or "openai"
        default_model = (
            await self._get_config_value("ollama.embedding_model") or "nomic-embed-text:latest"
            if provider == "ollama"
            else await self._get_config_value("embedding.model") or "text-embedding-3-large"
        )
        target_model = model or default_model
        if target_model in self._embedding_dimensions:
            return self._embedding_dimensions[target_model]
        vector_size_str = await self._get_config_value("embedding.model_vector_size")
        return int(vector_size_str) if vector_size_str else None

    async def _enforce_daily_limit(self, user_id: int) -> None:
        limit_str = await self.admin_setting_service.get("daily_request_limit", "100")
        limit = int(limit_str or 10)
        used = await self.user_repo.get_daily_request(user_id)
        if used >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日请求次数已达上限，请明日再试或设置自定义 API Key。",
            )
        await self.user_repo.increment_daily_request(user_id)
        await self.session.commit()

    async def _get_config_value(self, key: str) -> Optional[str]:
        if key.startswith("llm."):
            return self._get_llm_env_value(key)
        record = await self.system_config_repo.get_by_key(key)
        if record and not self._is_placeholder_config_value(record.value):
            return record.value
        return None
