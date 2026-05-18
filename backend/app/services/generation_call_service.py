# AIMETA P=Generation call reliability|R=LLM retry JSON parsing|NR=No business orchestration|E=GenerationCallPolicy|X=internal|A=LLM helper|D=fastapi|S=net|RD=./README.ai
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException

from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json
from .llm_service import LLMService

logger = logging.getLogger(__name__)


ProgressCallback = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class GenerationCallPolicy:
    stage_label: str
    progress_stage: str = "generating"
    retry_attempts: int = 2
    response_format: Optional[str] = "json_object"
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    allow_truncated_response: bool = False
    retry_same_model_once: bool = True
    json_repair_attempts: int = 1


@dataclass(frozen=True)
class GenerationTextResult:
    text: str
    attempts: int


@dataclass(frozen=True)
class GenerationJsonResult:
    data: Dict[str, Any]
    raw_text: str
    normalized_text: str
    attempts: int


class GenerationJSONDecodeError(ValueError):
    def __init__(self, message: str, *, raw_text: str, normalized_text: str):
        super().__init__(message)
        self.raw_text = raw_text
        self.normalized_text = normalized_text


def is_retryable_http_exception(exc: HTTPException) -> bool:
    if exc.status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("retryable") is True:
        return True
    return False


def normalize_llm_json_text(raw_text: str) -> str:
    return sanitize_json_like_text(unwrap_markdown_json(remove_think_tags(raw_text or ""))).strip()


def parse_llm_json_object(raw_text: str) -> tuple[Dict[str, Any], str]:
    normalized = normalize_llm_json_text(raw_text)
    try:
        data = json.loads(normalized)
    except Exception as exc:  # noqa: BLE001 - caller needs the original model text for repair.
        raise GenerationJSONDecodeError(
            f"LLM response is not valid JSON: {exc}",
            raw_text=raw_text,
            normalized_text=normalized,
        ) from exc
    if not isinstance(data, dict):
        raise GenerationJSONDecodeError(
            "LLM response JSON root must be an object",
            raw_text=raw_text,
            normalized_text=normalized,
        )
    return data, normalized


async def call_generation_text(
    *,
    llm_service: LLMService,
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    temperature: float,
    user_id: int,
    timeout: float,
    policy: GenerationCallPolicy,
    progress_callback: ProgressCallback | None = None,
) -> GenerationTextResult:
    attempts = max(1, policy.retry_attempts)
    last_http_exc: HTTPException | None = None
    for attempt in range(1, attempts + 1):
        try:
            text = await llm_service.get_llm_response(
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                temperature=temperature,
                user_id=user_id,
                timeout=timeout,
                response_format=policy.response_format,
                max_tokens=policy.max_tokens,
                top_p=policy.top_p,
                allow_truncated_response=policy.allow_truncated_response,
                retry_same_model_once=policy.retry_same_model_once,
            )
            return GenerationTextResult(text=text, attempts=attempt)
        except HTTPException as exc:
            last_http_exc = exc
            if attempt >= attempts or not is_retryable_http_exception(exc):
                raise
            if progress_callback is not None:
                await progress_callback(
                    policy.progress_stage,
                    f"{policy.stage_label}遇到上游抖动，正在进行第 {attempt}/{attempts - 1} 次重试",
                )
            logger.warning(
                "Retrying generation stage after provider jitter: stage=%s attempt=%s/%s status=%s detail=%s",
                policy.stage_label,
                attempt,
                attempts,
                exc.status_code,
                exc.detail,
            )
            await asyncio.sleep(min(8.0, 1.5 * attempt))
    if last_http_exc is not None:
        raise last_http_exc
    raise HTTPException(status_code=500, detail=f"{policy.stage_label}失败，重试流程异常退出")


async def call_generation_json(
    *,
    llm_service: LLMService,
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    temperature: float,
    user_id: int,
    timeout: float,
    policy: GenerationCallPolicy,
    progress_callback: ProgressCallback | None = None,
) -> GenerationJsonResult:
    repair_attempts = max(0, policy.json_repair_attempts)
    history = [dict(item) for item in conversation_history]
    total_text_attempts = 0
    last_decode_error: GenerationJSONDecodeError | None = None

    for repair_index in range(repair_attempts + 1):
        text_result = await call_generation_text(
            llm_service=llm_service,
            system_prompt=system_prompt,
            conversation_history=history,
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            policy=policy,
            progress_callback=progress_callback,
        )
        total_text_attempts += text_result.attempts
        try:
            data, normalized = parse_llm_json_object(text_result.text)
            return GenerationJsonResult(
                data=data,
                raw_text=text_result.text,
                normalized_text=normalized,
                attempts=total_text_attempts,
            )
        except GenerationJSONDecodeError as exc:
            last_decode_error = exc
            if repair_index >= repair_attempts:
                break
            if progress_callback is not None:
                await progress_callback(
                    policy.progress_stage,
                    f"{policy.stage_label}返回格式不完整，正在进行第 {repair_index + 1}/{repair_attempts} 次格式修复",
                )
            history.extend(
                [
                    {"role": "assistant", "content": text_result.text[:8000]},
                    {
                        "role": "user",
                        "content": (
                            "上一条回复不是可解析的 JSON 对象。请只输出一个合法 JSON 对象，"
                            "不要 Markdown，不要解释，不要省略必要字段。"
                        ),
                    },
                ]
            )

    if last_decode_error is not None:
        raise last_decode_error
    raise GenerationJSONDecodeError(
        "LLM response JSON repair loop exited unexpectedly",
        raw_text="",
        normalized_text="",
    )
