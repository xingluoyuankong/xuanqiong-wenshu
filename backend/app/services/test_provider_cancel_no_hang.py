import asyncio
import time

import pytest
from fastapi import HTTPException

from app.services.generation_call_service import (
    GenerationCallPolicy,
    _await_provider_text_with_heartbeat,
    _cancel_provider_task,
)


@pytest.mark.anyio
async def test_cancel_provider_task_does_not_hang_on_uncooperative_await():
    async def never_ends():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # Simulate a provider client that ignores cancellation for a while.
            await asyncio.sleep(30)
            raise

    task = asyncio.create_task(never_ends())
    started = time.perf_counter()
    await _cancel_provider_task(task, grace_seconds=0.2)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0
    # Task may still be finishing in background; force hard cancel leftover.
    if not task.done():
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.5)


@pytest.mark.anyio
async def test_soft_timeout_raises_without_indefinite_await(monkeypatch):
    class DummyLLM:
        async def get_llm_response(self, **kwargs):
            await asyncio.sleep(3600)
            return "late"

    started = time.perf_counter()
    with pytest.raises(HTTPException) as exc:
        await _await_provider_text_with_heartbeat(
            llm_service=DummyLLM(),
            system_prompt="s",
            conversation_history=[{"role": "user", "content": "u"}],
            temperature=0.1,
            user_id=1,
            timeout=1.0,
            response_format_payload=None,
            policy=GenerationCallPolicy(
                stage_label="unit",
                progress_stage="unit",
                soft_timeout_seconds=0.2,
                allow_truncated_response=True,
            ),
            progress_callback=None,
        )
    elapsed = time.perf_counter() - started
    assert elapsed < 2.5
    assert exc.value.status_code == 504
    assert exc.value.detail["code"] == "PROVIDER_SOFT_TIMEOUT"
