from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.command_recovery import (
    COMMAND_APPLIED,
    COMMAND_APPLYING,
    COMMAND_FAILED,
    COMMAND_REJECTED,
    COMMAND_REQUESTED,
    AgentCommandRecovery,
    CommandLeaseConflict,
)
from app.agent.command_worker import CommandWorker
from app.agent.jobs import AgentJobService
from app.db.base import Base
from app.models import AgentEventRecord, AgentJob, AgentRun, AgentRunCommand, User
from app.services.agent_runtime import AgentRuntimeService


async def _factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'command-worker.sqlite').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _command(factory, user_id: int, command_type: str = "pause"):
    async with factory() as session:
        user = User(
            id=user_id,
            username=f"command-worker-{user_id}",
            email=f"command-worker-{user_id}@example.com",
            hashed_password="x",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        runtime = AgentRuntimeService(session)
        agent_session = await runtime.create_session(user_id=user.id)
        run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
        await runtime.update_run(run_id=run.id, user_id=user.id, status="running", phase="command_test")
        run = await runtime.get_run(run.id, user.id)
        command = await runtime.request_run_command(
            run_id=run.id,
            user_id=user.id,
            command_type=command_type,
            idempotency_key=f"command-worker-{user_id}",
            expected_state_version=int(run.state_version or 0),
        )
        return run.id, command.id


@pytest.mark.asyncio
async def test_command_worker_claims_applying_and_applies_pause(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, command_id = await _command(factory, 2401)
        worker = CommandWorker(factory, worker_id="command-worker-a", lease_seconds=30)

        assert await worker.poll_once() is True

        async with factory() as session:
            command = (await session.execute(select(AgentRunCommand).where(AgentRunCommand.id == command_id))).scalar_one()
            run = (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            events = list(
                (
                    await session.execute(
                        select(AgentEventRecord)
                        .where(AgentEventRecord.run_id == run_id)
                        .order_by(AgentEventRecord.sequence.asc())
                    )
                ).scalars().all()
            )
            assert command.status == COMMAND_APPLIED
            assert command.attempt_count == 1
            assert command.lease_owner is None
            assert run.status == "paused"
            assert [event.event_type for event in events] == [
                "run_command_requested",
                "run_paused",
                "run_command_applied",
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_recovery_requeues_expired_applying_and_preserves_attempt(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, command_id = await _command(factory, 2402)
        async with factory() as session:
            recovery = AgentCommandRecovery(session, lease_seconds=30)
            claimed = await recovery.claim(command_id=command_id, lease_owner="crashed-command-worker")
            assert claimed.status == COMMAND_APPLYING
            assert claimed.attempt_count == 1
            assert claimed.lease_generation == 1
            claimed.lease_expires_at = recovery.now() - timedelta(seconds=1)
            await session.commit()

            recovered = await recovery.recover_stale_commands()
            assert [item.id for item in recovered] == [command_id]
            current = await recovery.get(command_id=command_id)
            assert current is not None
            assert current.status == COMMAND_REQUESTED
            assert current.attempt_count == 1
            assert current.lease_generation == 1
            assert current.lease_owner is None
            assert current.error_type == "CommandLeaseExpired"
            events = list(
                (
                    await session.execute(
                        select(AgentEventRecord)
                        .where(AgentEventRecord.run_id == run_id)
                        .order_by(AgentEventRecord.sequence.asc())
                    )
                ).scalars().all()
            )
            assert [event.event_type for event in events] == [
                "run_command_requested",
                "command_recovered",
            ]

        replacement = CommandWorker(factory, worker_id="command-worker-replacement", lease_seconds=30)
        assert await replacement.poll_once() is True
        async with factory() as session:
            command = (await session.execute(select(AgentRunCommand).where(AgentRunCommand.id == command_id))).scalar_one()
            assert command.status == COMMAND_APPLIED
            assert command.attempt_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_worker_cancel_converges_run_and_outstanding_job(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, command_id = await _command(factory, 24031, command_type="cancel")
        async with factory() as session:
            run = (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            job = await AgentJobService(session).create_job(
                run_id=run.id,
                user_id=run.user_id,
                project_id=run.project_id,
                kind="agent_execution",
                idempotency_key="cancelled-by-command-worker",
            )
            job_id = job.id

        worker = CommandWorker(factory, worker_id="command-worker-cancel", lease_seconds=30)
        assert await worker.poll_once() is True

        async with factory() as session:
            run = (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            assert run.status == "cancelled"
            assert job.status == "cancelled"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_worker_rejects_stale_state_version(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, command_id = await _command(factory, 2403)
        async with factory() as session:
            command = (await session.execute(select(AgentRunCommand).where(AgentRunCommand.id == command_id))).scalar_one()
            command.expected_state_version = 999999
            await session.commit()

        worker = CommandWorker(factory, worker_id="command-worker-reject", lease_seconds=30)
        assert await worker.poll_once() is True
        async with factory() as session:
            command = (await session.execute(select(AgentRunCommand).where(AgentRunCommand.id == command_id))).scalar_one()
            assert command.status == COMMAND_REJECTED
            assert command.error_type == "AgentStateVersionConflict"
            assert command.lease_owner is None
            events = list(
                (
                    await session.execute(
                        select(AgentEventRecord)
                        .where(AgentEventRecord.run_id == run_id)
                        .order_by(AgentEventRecord.sequence.asc())
                    )
                ).scalars().all()
            )
            assert events[-1].event_type == "run_command_rejected"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_worker_persists_unexpected_failure(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, command_id = await _command(factory, 2404)

        async def broken_applier(command, session, worker_id):
            raise RuntimeError("synthetic command applier failure")

        worker = CommandWorker(
            factory,
            worker_id="command-worker-failed",
            lease_seconds=30,
            applier=broken_applier,
        )
        assert await worker.poll_once() is True

        async with factory() as session:
            command = (await session.execute(select(AgentRunCommand).where(AgentRunCommand.id == command_id))).scalar_one()
            assert command.status == COMMAND_FAILED
            assert command.error_type == "RuntimeError"
            assert "synthetic command applier failure" in (command.error_detail or "")
            assert command.lease_owner is None
            events = list(
                (
                    await session.execute(
                        select(AgentEventRecord)
                        .where(AgentEventRecord.run_id == run_id)
                        .order_by(AgentEventRecord.sequence.asc())
                    )
                ).scalars().all()
            )
            assert events[-1].event_type == "run_command_failed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_lease_heartbeat_and_owner_fence(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        _, command_id = await _command(factory, 2405)
        async with factory() as session:
            recovery = AgentCommandRecovery(session, lease_seconds=30)
            await recovery.claim(command_id=command_id, lease_owner="owner-a")
            with pytest.raises(CommandLeaseConflict, match="active"):
                await recovery.heartbeat(command_id=command_id, lease_owner="owner-b")
            heartbeated = await recovery.heartbeat(command_id=command_id, lease_owner="owner-a")
            assert heartbeated.status == COMMAND_APPLYING
            assert heartbeated.lease_owner == "owner-a"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_job_lease_generation_fences_old_completion_after_reclaim(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, _ = await _command(factory, 2499, command_type="pause")
        async with factory() as session:
            run = (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            jobs = AgentJobService(session)
            job = await jobs.create_job(run_id=run.id, user_id=run.user_id, project_id=run.project_id, kind="agent_execution", idempotency_key="job-generation-fence")
            first = await jobs.claim_job(job_id=job.id, user_id=run.user_id, lease_owner="reused-job-owner", lease_seconds=60)
            first_generation = int(first.lease_generation or 0)
            first.lease_expires_at = jobs._now() - timedelta(seconds=1)
            await session.commit()
            second = await jobs.claim_job(job_id=job.id, user_id=run.user_id, lease_owner="reused-job-owner", lease_seconds=60, lease_generation=first_generation)
            assert second.lease_generation == first_generation + 1
            with pytest.raises(Exception, match="lost its lease"):
                await jobs.complete(job_id=job.id, user_id=run.user_id, lease_owner="reused-job-owner", lease_generation=first_generation, result={"late": True})
    finally:
        await engine.dispose()
