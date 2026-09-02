from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from .provider_attempt import ProviderAttemptLedger, ProviderAttemptRecord


@dataclass(frozen=True)
class ProviderCallContext:
    ledger: ProviderAttemptLedger
    role: str
    provider_ref: str | None = None
    model_ref: str | None = None
    action_id: str | None = None


_CURRENT_PROVIDER_CONTEXT: ContextVar[ProviderCallContext | None] = ContextVar(
    "agent_provider_call_context", default=None
)


@contextmanager
def provider_call_scope(
    ledger: ProviderAttemptLedger,
    *,
    role: str,
    provider_ref: str | None = None,
    model_ref: str | None = None,
    action_id: str | None = None,
):
    """Bind a redacted attempt ledger to nested LLM calls."""
    token = _CURRENT_PROVIDER_CONTEXT.set(
        ProviderCallContext(
            ledger=ledger,
            role=str(role or "unknown"),
            provider_ref=provider_ref,
            model_ref=model_ref,
            action_id=action_id,
        )
    )
    try:
        yield
    finally:
        _CURRENT_PROVIDER_CONTEXT.reset(token)


def current_provider_call_context() -> ProviderCallContext | None:
    return _CURRENT_PROVIDER_CONTEXT.get()


def begin_attempt(
    *,
    role: str,
    provider_ref: Any,
    model_ref: Any,
    retry_index: int = 0,
    fallback_from_attempt: int | None = None,
    attempt_id: str | None = None,
) -> ProviderAttemptRecord | None:
    context = current_provider_call_context()
    if context is None:
        return None
    return context.ledger.begin(
        role=role,
        provider_ref=provider_ref,
        model_ref=model_ref,
        retry_index=retry_index,
        fallback_from_attempt=fallback_from_attempt,
        attempt_id=attempt_id,
    )


async def collect_stream_with_attempt(
    source: AsyncIterator[dict[str, Any]],
    *,
    role: str,
    provider_ref: Any,
    model_ref: Any,
    ledger: ProviderAttemptLedger | None = None,
    retry_index: int = 0,
    fallback_from_attempt: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Wrap a provider stream and record one attempt without storing raw text."""
    context = current_provider_call_context()
    active_ledger = ledger or (context.ledger if context is not None else None)
    record = active_ledger.begin(
        role=role,
        provider_ref=provider_ref,
        model_ref=model_ref,
        retry_index=retry_index,
        fallback_from_attempt=fallback_from_attempt,
    ) if active_ledger is not None else None
    output: list[str] = []
    try:
        async for part in source:
            content = part.get("content") if isinstance(part, dict) else None
            if isinstance(content, str) and content:
                output.append(content)
                if record is not None and active_ledger is not None:
                    active_ledger.mark_first_token(record.attempt_id)
            reasoning = part.get("reasoning_content") if isinstance(part, dict) else None
            if isinstance(reasoning, str) and reasoning:
                output.append(reasoning)
                if record is not None and active_ledger is not None:
                    active_ledger.mark_first_token(record.attempt_id)
            yield part
    except BaseException as exc:
        if record is not None:
            if active_ledger is not None:
                if isinstance(exc, GeneratorExit):
                    active_ledger.fail(record.attempt_id, category="CANCELLED", output="".join(output))
                else:
                    active_ledger.fail(record.attempt_id, exc, output="".join(output))
        raise
    else:
        if record is not None:
            if active_ledger is not None:
                if output:
                    active_ledger.finish(record.attempt_id, output="".join(output))
                else:
                    active_ledger.fail(record.attempt_id, category="EMPTY_STREAM")


async def call_with_attempt(
    call: Callable[[], Any],
    *,
    role: str,
    provider_ref: Any,
    model_ref: Any,
    ledger: ProviderAttemptLedger | None = None,
    retry_index: int = 0,
    fallback_from_attempt: int | None = None,
) -> Any:
    """Record a non-stream Provider call using the same redacted ledger."""
    context = current_provider_call_context()
    active_ledger = ledger or (context.ledger if context is not None else None)
    record = active_ledger.begin(
        role=role,
        provider_ref=provider_ref,
        model_ref=model_ref,
        retry_index=retry_index,
        fallback_from_attempt=fallback_from_attempt,
    ) if active_ledger is not None else None
    try:
        result = await call()
    except BaseException as exc:
        if record is not None and active_ledger is not None:
            active_ledger.fail(record.attempt_id, exc)
        raise
    if record is not None and active_ledger is not None:
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, str) and content:
            active_ledger.mark_first_token(record.attempt_id)
            active_ledger.finish(record.attempt_id, output=content)
        else:
            active_ledger.fail(record.attempt_id, category="EMPTY_STREAM")
    return result
