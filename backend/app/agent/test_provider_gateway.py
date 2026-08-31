from __future__ import annotations

import pytest

from app.agent.provider_attempt import ProviderAttemptLedger
from app.agent.provider_gateway import call_with_attempt, collect_stream_with_attempt, provider_call_scope


async def _stream(parts):
    for part in parts:
        yield part


@pytest.mark.asyncio
async def test_gateway_records_stream_success_and_empty_stream():
    ledger = ProviderAttemptLedger(run_id="run-gateway")
    with provider_call_scope(ledger, role="response", provider_ref="fixture", model_ref="model"):
        received = [part async for part in collect_stream_with_attempt(_stream([{"content": "甲"}, {"content": "乙"}]), role="response", provider_ref="fixture", model_ref="model")]
    assert len(received) == 2
    snapshot = ledger.snapshot()
    assert snapshot["provider_attempts"][0]["status"] == "succeeded"
    assert snapshot["provider_attempts"][0]["output_digest"]

    empty = ProviderAttemptLedger(run_id="run-empty")
    with provider_call_scope(empty, role="quality", provider_ref="fixture", model_ref="model"):
        _ = [part async for part in collect_stream_with_attempt(_stream([]), role="quality", provider_ref="fixture", model_ref="model")]
    assert empty.snapshot()["provider_attempts"][0]["error_category"] == "EMPTY_STREAM"


@pytest.mark.asyncio
async def test_gateway_records_non_stream_failure_without_raw_error():
    ledger = ProviderAttemptLedger(run_id="run-failure")

    async def fail():
        raise TimeoutError("secret raw provider response")

    with provider_call_scope(ledger, role="planner", provider_ref="fixture", model_ref="model"):
        with pytest.raises(TimeoutError):
            await call_with_attempt(fail, role="planner", provider_ref="fixture", model_ref="model")
    record = ledger.snapshot()["provider_attempts"][0]
    assert record["error_category"] == "TIMEOUT"
    assert "secret raw" not in str(record)
