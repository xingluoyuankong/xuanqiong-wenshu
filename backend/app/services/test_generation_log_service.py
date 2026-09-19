import pytest
from app.services.generation_log_service import GenerationLogService

@pytest.mark.asyncio
async def test_fail_task_emits_error_terminal_event():
    service = GenerationLogService()
    service.create_task("run-failed")
    await service.fail_task("run-failed", "model unavailable", code="PROVIDER_MODEL_UNAVAILABLE")
    event = (await service.get_history("run-failed"))[-1]
    assert event.level == "error"
    assert event.metadata["event_kind"] == "terminal"
    assert event.metadata["type"] == "failed"
    assert event.metadata["code"] == "PROVIDER_MODEL_UNAVAILABLE"
    assert event.metadata["retryable"] is False
