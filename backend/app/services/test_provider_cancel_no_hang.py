from __future__ import annotations

import asyncio

import pytest

from app.services.generation_call_service import (
    GenerationCallPolicy,
    _await_provider_text_with_heartbeat,
)


class _HangingProvider:
    def __init__(self):
        self.cancelled = asyncio.Event()

    async def get_llm_response(self, **_kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


@pytest.mark.anyio
async def test_cancelling_generation_wait_cancels_provider_without_hanging():
    provider = _HangingProvider()
    wait_task = asyncio.create_task(
        _await_provider_text_with_heartbeat(
            llm_service=provider,
            system_prompt="system",
            conversation_history=[{"role": "user", "content": "chapter"}],
            temperature=0.2,
            user_id=1,
            timeout=30,
            response_format_payload=None,
            policy=GenerationCallPolicy(
                stage_label="chapter",
                retry_attempts=1,
                heartbeat_interval_seconds=None,
                soft_timeout_seconds=None,
            ),
            progress_callback=None,
        )
    )
    await asyncio.sleep(0.01)
    wait_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(wait_task, timeout=0.5)
    await asyncio.wait_for(provider.cancelled.wait(), timeout=0.5)
