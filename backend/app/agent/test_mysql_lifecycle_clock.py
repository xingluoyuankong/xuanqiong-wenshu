"""UTC-second lifecycle timestamps must not be rounded differently by MySQL."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import app.services.agent_runtime as runtime_module
import app.services.agent_execution_service as execution_module
from app.agent.continuation_failure_recovery import _stored_at_or_after


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 7, 4, 23, 16, 750000, tzinfo=timezone.utc)
        return value if tz is not None else value.replace(tzinfo=None)


def test_runtime_utc_seconds_prevent_datetime_zero_rounding(monkeypatch):
    monkeypatch.setattr(runtime_module, 'datetime', Clock)
    value = runtime_module.AgentRuntimeService._now()
    assert value == datetime(2026,9,7,4,23,16,tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['fail', 'complete'])
async def test_fact_finish_persists_utc_seconds(monkeypatch, operation):
    monkeypatch.setattr(execution_module, 'datetime', Clock)
    service = execution_module.AgentExecutionService(SimpleNamespace())
    fact = SimpleNamespace(lease_generation=1,status='started',
        started_at=datetime(2026,9,7,4,23,16,tzinfo=timezone.utc))
    if operation == 'fail':
        await service.fail_read_execution(execution=fact,lease_generation=1,error=RuntimeError('x'),commit=False)
    else:
        await service.complete_read_execution(execution=fact,lease_generation=1,output={},commit=False)
    assert fact.finished_at == datetime(2026,9,7,4,23,16,tzinfo=timezone.utc)
    # Keep duration accounting at its original precision.
    assert fact.duration_ms == 750


@pytest.mark.asyncio
@pytest.mark.parametrize('retry', [False, True])
async def test_fact_start_uses_same_utc_clock_including_retry(monkeypatch, retry):
    monkeypatch.setattr(execution_module, 'datetime', Clock)
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    service = execution_module.AgentExecutionService(session)
    row = SimpleNamespace(capability_id='read',step_id='step',status='failed',attempt=1,
        started_at=datetime(2026,9,6,tzinfo=timezone.utc))
    service.repository = SimpleNamespace(
        get_capability_for_snapshot=AsyncMock(return_value=SimpleNamespace()),
        get_execution_by_idempotency=AsyncMock(return_value=row if retry else None),
        create_execution=AsyncMock(return_value=row))
    result = await service.begin_read_execution(run=SimpleNamespace(id='run'),step=SimpleNamespace(id='step'),
        snapshot=SimpleNamespace(),capability_id='read',arguments={},lease_generation=2,idempotency_key='key')
    assert result.started_at == datetime(2026,9,7,4,23,16,tzinfo=timezone.utc)


def test_proof_still_rejects_real_reverse_second_order():
    instant = datetime(2026,9,7,4,23,17,tzinfo=timezone.utc)
    assert not _stored_at_or_after(instant, instant-timedelta(seconds=1))
