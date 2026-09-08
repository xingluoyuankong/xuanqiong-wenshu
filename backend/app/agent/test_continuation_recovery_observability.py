"""Operational recovery logs are factual, bounded and omit private details."""
from contextlib import contextmanager
import logging

import pytest
from sqlalchemy import select

from app.agent import continuation_failure_recovery as recovery
from app.agent.test_continuation_failure_recovery import create_orphan
from app.models.agent import AgentJob, AgentRunStep
from app.models.agent_catalog import AgentCapabilityExecution


@pytest.fixture(autouse=True, params=[False, True], ids=['logging-enabled', 'logging-disabled-by-migration'])
def logger_disabled_by_previous_configuration(request, monkeypatch):
    # Alembic fileConfig disables existing loggers during earlier full-suite tests.
    monkeypatch.setattr(recovery.logger, 'disabled', request.param)


@contextmanager
def captured_recovery_logs():
    class Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

    handler = Capture()
    logger = recovery.logger
    old_level, old_propagate, old_disabled = logger.level, logger.propagate, logger.disabled
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        logger.disabled = old_disabled


@pytest.mark.asyncio
async def test_recovery_emits_one_committed_summary_without_error_details(tmp_path, monkeypatch):
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            fact = (await session.execute(select(AgentCapabilityExecution).join(
                AgentRunStep, AgentRunStep.id == AgentCapabilityExecution.step_id
            ).where(AgentRunStep.run_id == f.run_id, AgentRunStep.step_order == 2))).scalar_one()
            fact.error_detail = 'SECRET_SENTINEL provider response body'
            await session.commit()
        with captured_recovery_logs() as captured:
            async with f.factory() as session:
                assert len(await recovery.recover_failed_continuations(session)) == 1
                assert await recovery.recover_failed_continuations(session) == []
        records = [r for r in captured if r.getMessage() == 'continuation_failure_recovered']
        assert len(records) == 1
        record = records[0]
        assert (record.job_id, record.run_id, record.job_status, record.lease_generation) == (job_id, f.run_id, 'failed', 1)
        assert 'SECRET_SENTINEL' not in repr(record.__dict__)
        assert 'error_detail' not in record.__dict__
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_recovery_logs_only_sanitized_reason_for_unproven_orphan(tmp_path, monkeypatch):
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            job = await session.get(AgentJob, job_id)
            job.payload_json = {'approval_id': 'SECRET_SENTINEL'}
            await session.commit()
        with captured_recovery_logs() as captured:
            async with f.factory() as session:
                assert await recovery.recover_failed_continuations(session) == []
        records = [r for r in captured if r.getMessage() == 'continuation_recovery_skipped']
        assert len(records) == 1
        assert records[0].reason_code == 'ContinuationConflict'
        assert 'SECRET_SENTINEL' not in repr(records[0].__dict__)
        async with f.factory() as session:
            assert (await session.get(AgentJob, job_id)).status == 'running'
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_recovery_never_logs_success_before_failed_cas_transaction(tmp_path, monkeypatch):
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async def failed_cas(*args, **kwargs):
            raise RuntimeError('SECRET_SENTINEL infrastructure failure')
        monkeypatch.setattr(recovery, '_cas_mark_failed', failed_cas)
        with captured_recovery_logs() as captured:
            async with f.factory() as session:
                with pytest.raises(RuntimeError):
                    await recovery.recover_failed_continuations(session)
        assert not [r for r in captured if r.getMessage() in {
            'continuation_failure_recovered', 'continuation_recovery_skipped'}]
        async with f.factory() as session:
            assert (await session.get(AgentJob, job_id)).status == 'running'
    finally:
        await f.engine.dispose()
