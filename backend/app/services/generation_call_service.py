# AIMETA P=Generation call reliability|R=LLM retry JSON parsing|NR=No business orchestration|E=GenerationCallPolicy|X=internal|A=LLM helper|D=fastapi|S=net|RD=./README.ai
import asyncio
import json
import logging
import random
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    json_schema: Optional[Dict[str, Any]] = None
    json_schema_name: Optional[str] = None
    json_schema_strict: bool = True
    prompt_cache_key: Optional[str] = None
    runtime_event_kind: Optional[str] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    allow_truncated_response: bool = False
    retry_same_model_once: bool = True
    json_repair_attempts: int = 1
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 12.0


@dataclass(frozen=True)
class GenerationTextResult:
    text: str
    attempts: int
    response_format_used: Optional[Any] = None
    provider_error_type: Optional[str] = None


@dataclass(frozen=True)
class GenerationJsonResult:
    data: Dict[str, Any]
    raw_text: str
    normalized_text: str
    attempts: int
    response_format_used: Optional[Any] = None
    schema_validated: bool = False


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


def _coerce_retry_after_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        if not isinstance(value, str):
            return None
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        parsed = (retry_at - datetime.now(timezone.utc)).total_seconds()
    if parsed < 0:
        return None
    return parsed


def _resolve_retry_after_seconds(exc: HTTPException) -> Optional[float]:
    detail = exc.detail
    if isinstance(detail, dict):
        for key in ("retry_after", "retry_after_seconds", "retryAfter", "retryAfterSeconds"):
            parsed = _coerce_retry_after_seconds(detail.get(key))
            if parsed is not None:
                return parsed
    headers = getattr(exc, "headers", None) or {}
    if isinstance(headers, dict):
        return _coerce_retry_after_seconds(headers.get("Retry-After") or headers.get("retry-after"))
    return None


def resolve_retry_delay_seconds(exc: HTTPException, attempt: int, policy: GenerationCallPolicy) -> float:
    """Bounded exponential backoff for transient provider failures."""

    retry_after = _resolve_retry_after_seconds(exc)
    if retry_after is not None:
        return min(float(policy.backoff_max_seconds), retry_after)
    base = max(0.1, float(policy.backoff_base_seconds or 1.0))
    cap = max(base, float(policy.backoff_max_seconds or 12.0))
    exponential = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0, min(exponential * 0.25, 1.0))
    return min(cap, exponential + jitter)


def _looks_like_output_token_limit_error(exc: HTTPException) -> bool:
    if exc.status_code != 400:
        return False
    detail = exc.detail
    text = json.dumps(detail, ensure_ascii=False).lower() if isinstance(detail, (dict, list)) else str(detail).lower()
    markers = (
        "max_tokens",
        "max output",
        "output token",
        "context length",
        "maximum context",
        "too many tokens",
        "token limit",
    )
    return any(marker in text for marker in markers)


def classify_provider_error(exc: HTTPException) -> str:
    detail = exc.detail
    text = json.dumps(detail, ensure_ascii=False).lower() if isinstance(detail, (dict, list)) else str(detail).lower()
    if exc.status_code == 429 or "rate limit" in text or "too many requests" in text:
        return "rate_limit"
    if exc.status_code in {408, 504} or "timeout" in text or "timed out" in text:
        return "timeout"
    if exc.status_code in {500, 502, 503} or "overload" in text or "temporarily unavailable" in text:
        return "provider_jitter"
    if exc.status_code in {401, 403} or "api key" in text or "auth" in text or "permission" in text:
        return "provider_auth"
    if _looks_like_output_token_limit_error(exc):
        return "output_token_limit"
    if _looks_like_structured_output_unsupported(exc):
        return "structured_output_unsupported"
    if exc.status_code == 400:
        return "bad_request"
    return "unknown"


def _looks_like_structured_output_unsupported(exc: HTTPException) -> bool:
    if exc.status_code not in {400, 404, 422}:
        return False
    detail = exc.detail
    text = json.dumps(detail, ensure_ascii=False).lower() if isinstance(detail, (dict, list)) else str(detail).lower()
    markers = (
        "json_schema",
        "structured output",
        "structured_outputs",
        "schema is not supported",
        "response_format",
        "unsupported response format",
        "not support response_format",
        "does not support response_format",
    )
    return any(marker in text for marker in markers)


def build_response_format_payload(policy: GenerationCallPolicy) -> Optional[Any]:
    if policy.json_schema:
        schema_name = (policy.json_schema_name or policy.stage_label or "generation_schema").strip()
        schema_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in schema_name)[:64] or "generation_schema"
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": policy.json_schema,
                "strict": bool(policy.json_schema_strict),
            },
        }
    return policy.response_format


def _downgrade_schema_policy(policy: GenerationCallPolicy) -> GenerationCallPolicy:
    return replace(
        policy,
        json_schema=None,
        json_schema_name=None,
        response_format="json_object",
    )


def normalize_llm_json_text(raw_text: str) -> str:
    return sanitize_json_like_text(unwrap_markdown_json(remove_think_tags(raw_text or ""))).strip()


def parse_llm_json_value(raw_text: str) -> tuple[Any, str]:
    normalized = normalize_llm_json_text(raw_text)
    try:
        return json.loads(normalized), normalized
    except Exception as exc:  # noqa: BLE001 - caller needs the original model text for repair.
        object_start = normalized.find("{")
        array_start = normalized.find("[")
        candidates: List[tuple[int, str]] = []
        if object_start >= 0:
            candidates.append((object_start, "}"))
        if array_start >= 0:
            candidates.append((array_start, "]"))
        candidates.sort(key=lambda item: item[0])
        for json_start, closing in candidates:
            json_end = normalized.rfind(closing) + 1
            if json_end <= json_start:
                continue
            candidate = normalized[json_start:json_end]
            try:
                return json.loads(candidate), candidate
            except Exception:
                continue
        raise GenerationJSONDecodeError(
            f"LLM response is not valid JSON: {exc}",
            raw_text=raw_text,
            normalized_text=normalized,
        ) from exc


def parse_llm_json_object(raw_text: str) -> tuple[Dict[str, Any], str]:
    try:
        data, normalized = parse_llm_json_value(raw_text)
    except GenerationJSONDecodeError:
        raise
    except Exception as exc:  # noqa: BLE001 - caller needs the original model text for repair.
        normalized = normalize_llm_json_text(raw_text)
        json_start = normalized.find("{")
        json_end = normalized.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            candidate = normalized[json_start:json_end]
            try:
                data = json.loads(candidate)
                normalized = candidate
            except Exception as nested_exc:  # noqa: BLE001 - keep original model text for repair.
                raise GenerationJSONDecodeError(
                    f"LLM response is not valid JSON: {nested_exc}",
                    raw_text=raw_text,
                    normalized_text=normalized,
                ) from nested_exc
        else:
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


def validate_json_schema_subset(data: Dict[str, Any], schema: Optional[Dict[str, Any]]) -> List[str]:
    """Small local schema guard for providers that fall back from strict JSON schema.

    It intentionally validates only the contract pieces this project depends on:
    object roots, required fields, object properties, arrays, scalar JSON types,
    and nested required properties. Full JSON Schema stays the provider's job.
    """

    if not schema:
        return []

    errors: List[str] = []

    def check(value: Any, node: Dict[str, Any], path: str) -> None:
        expected_type = node.get("type")
        if isinstance(expected_type, list):
            if "null" in expected_type and value is None:
                return
            expected_type = next((item for item in expected_type if item != "null"), None)
        if expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"{path} must be object")
                return
            for key in node.get("required") or []:
                if key not in value:
                    errors.append(f"{path}.{key} is required")
            properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            for key, child in properties.items():
                if key in value and isinstance(child, dict):
                    check(value[key], child, f"{path}.{key}")
        elif expected_type == "array":
            if not isinstance(value, list):
                errors.append(f"{path} must be array")
                return
            item_schema = node.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value[:40]):
                    check(item, item_schema, f"{path}[{index}]")
        elif expected_type == "string" and not isinstance(value, str):
            errors.append(f"{path} must be string")
        elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            errors.append(f"{path} must be integer")
        elif expected_type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            errors.append(f"{path} must be number")
        elif expected_type == "boolean" and not isinstance(value, bool):
            errors.append(f"{path} must be boolean")

    check(data, schema, "$")
    return errors


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
    active_policy = policy
    last_http_exc: HTTPException | None = None
    for attempt in range(1, attempts + 1):
        response_format_payload = build_response_format_payload(active_policy)
        try:
            text = await llm_service.get_llm_response(
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                temperature=temperature,
                user_id=user_id,
                timeout=timeout,
                response_format=response_format_payload,
                max_tokens=active_policy.max_tokens,
                top_p=active_policy.top_p,
                prompt_cache_key=active_policy.prompt_cache_key,
                allow_truncated_response=active_policy.allow_truncated_response,
                retry_same_model_once=active_policy.retry_same_model_once,
            )
            return GenerationTextResult(text=text, attempts=attempt, response_format_used=response_format_payload)
        except HTTPException as exc:
            last_http_exc = exc
            provider_error_type = classify_provider_error(exc)
            if (
                active_policy.json_schema
                and _looks_like_structured_output_unsupported(exc)
                and attempt < attempts
            ):
                logger.warning(
                    "Retrying generation stage with JSON mode after structured output rejection: stage=%s detail=%s",
                    active_policy.stage_label,
                    exc.detail,
                )
                active_policy = _downgrade_schema_policy(active_policy)
                if progress_callback is not None:
                    await progress_callback(
                        active_policy.progress_stage,
                        f"{active_policy.stage_label} 的结构化 schema 被当前 Provider 拒绝，已回退到 JSON 模式重试",
                    )
                await asyncio.sleep(resolve_retry_delay_seconds(exc, attempt, active_policy))
                continue
            if (
                active_policy.max_tokens
                and active_policy.max_tokens > 12000
                and _looks_like_output_token_limit_error(exc)
                and attempt < attempts
            ):
                reduced_max_tokens = max(12000, int(active_policy.max_tokens * 0.72))
                logger.warning(
                    "Retrying generation stage with reduced max_tokens after provider token-limit rejection: stage=%s max_tokens=%s reduced=%s detail=%s",
                    active_policy.stage_label,
                    active_policy.max_tokens,
                    reduced_max_tokens,
                    exc.detail,
                )
                active_policy = replace(active_policy, max_tokens=reduced_max_tokens)
                if progress_callback is not None:
                    await progress_callback(
                        active_policy.progress_stage,
                        f"{active_policy.stage_label} 上游模型拒绝当前输出上限，已降低 max_tokens 后重试",
                    )
                await asyncio.sleep(resolve_retry_delay_seconds(exc, attempt, active_policy))
                continue
            if attempt >= attempts or not is_retryable_http_exception(exc):
                raise
            if progress_callback is not None:
                await progress_callback(
                    active_policy.progress_stage,
                    f"{active_policy.stage_label}遇到上游抖动，正在进行第 {attempt}/{attempts - 1} 次重试",
                )
            logger.warning(
                "Retrying generation stage after provider jitter: stage=%s attempt=%s/%s status=%s type=%s detail=%s",
                active_policy.stage_label,
                attempt,
                attempts,
                exc.status_code,
                provider_error_type,
                exc.detail,
            )
            await asyncio.sleep(resolve_retry_delay_seconds(exc, attempt, active_policy))
    if last_http_exc is not None:
        raise last_http_exc
    raise HTTPException(status_code=500, detail=f"{active_policy.stage_label}失败，重试流程异常退出")


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
            schema_errors = validate_json_schema_subset(data, policy.json_schema)
            if schema_errors:
                raise GenerationJSONDecodeError(
                    "LLM response JSON failed local schema guard: " + "; ".join(schema_errors[:8]),
                    raw_text=text_result.text,
                    normalized_text=normalized,
                )
            return GenerationJsonResult(
                data=data,
                raw_text=text_result.text,
                normalized_text=normalized,
                attempts=total_text_attempts,
                response_format_used=text_result.response_format_used,
                schema_validated=bool(policy.json_schema),
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
                            "上一条回复不是可解析的 JSON 对象，或未通过本地结构验收。请只输出一个合法 JSON 对象，"
                            "不要 Markdown，不要解释，不要省略必要字段。"
                            + (
                                "\n必须满足本地 schema 关键约束："
                                + json.dumps(policy.json_schema, ensure_ascii=False)[:4000]
                                if policy.json_schema
                                else ""
                            )
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


async def call_generation_prompt_text(
    *,
    llm_service: LLMService,
    prompt: str,
    system_prompt: str,
    temperature: float,
    user_id: int,
    timeout: float,
    policy: GenerationCallPolicy,
    progress_callback: ProgressCallback | None = None,
) -> GenerationTextResult:
    """Convenience wrapper for single-prompt text generation.

    This keeps business services in charge of their own flow while routing the
    fragile network/provider work through the shared reliability toolbox.
    """

    return await call_generation_text(
        llm_service=llm_service,
        system_prompt=system_prompt,
        conversation_history=[{"role": "user", "content": prompt}],
        temperature=temperature,
        user_id=user_id,
        timeout=timeout,
        policy=policy,
        progress_callback=progress_callback,
    )


async def call_generation_prompt_json(
    *,
    llm_service: LLMService,
    prompt: str,
    system_prompt: str,
    temperature: float,
    user_id: int,
    timeout: float,
    policy: GenerationCallPolicy,
    progress_callback: ProgressCallback | None = None,
) -> GenerationJsonResult:
    """Convenience wrapper for single-prompt JSON generation."""

    return await call_generation_json(
        llm_service=llm_service,
        system_prompt=system_prompt,
        conversation_history=[{"role": "user", "content": prompt}],
        temperature=temperature,
        user_id=user_id,
        timeout=timeout,
        policy=policy,
        progress_callback=progress_callback,
    )
