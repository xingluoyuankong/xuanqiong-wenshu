"""Run/step/fact failure projection and Job failure share a transaction."""
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.agent.continuation import now
from app.agent.continuation_worker import handle_agent_continuation_job
from app.agent.jobs import AgentJobService
from app.agent.test_continuation_worker import pending_chain, approve_write
from app.agent.worker import AgentWorker
from app.models.agent import AgentJob, AgentRun, AgentRunStep
from app.models.agent_catalog import AgentCapabilityExecution

async def states(factory,run_id):
    async with factory() as session:
        run=await session.get(AgentRun,run_id)
        job=(await session.execute(select(AgentJob).where(AgentJob.run_id==run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
        step=(await session.execute(select(AgentRunStep).where(AgentRunStep.run_id==run_id,AgentRunStep.tool_name=='statistics.project'))).scalar_one()
        fact=(await session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.step_id==step.id))).scalar_one()
        return run.status,job.status,step.status,fact.status

@pytest.mark.asyncio
@pytest.mark.parametrize('transient,budget,expected',[
    (False,3,('failed','failed','failed','failed')),
    (True,1,('failed','dead_letter','failed','failed')),
    (True,3,('running','queued','pending','failed')),
])
async def test_failure_projection_and_job_are_invisible_until_same_commit(tmp_path,monkeypatch,transient,budget,expected):
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            job=(await session.execute(select(AgentJob).where(AgentJob.run_id==f.run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
            job.max_attempts=budget;await session.commit()
        class ProviderTimeout(Exception):pass
        async def fail_read(**kwargs):raise (ProviderTimeout if transient else RuntimeError)('read failure')
        monkeypatch.setattr('app.agent.continuation_worker.execute_read_tool',fail_read)
        original=AgentJobService.fail
        observed=[]
        async def audit_fail(self,**kwargs):
            if kwargs['job_id']!=job.id:return await original(self,**kwargs)
            assert kwargs.get('commit') is False
            assert await states(f.factory,f.run_id)==('running','running','running','started')
            result=await original(self,**kwargs)
            assert await states(f.factory,f.run_id)==('running','running','running','started')
            observed.append(result.status)
            return result
        monkeypatch.setattr(AgentJobService,'fail',audit_fail)
        worker=AgentWorker(f.factory,worker_id='atomic-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once()
        assert observed==[expected[1]]
        assert await states(f.factory,f.run_id)==expected
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_death_before_failure_commit_rolls_back_every_projection(tmp_path,monkeypatch):
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async def fail_read(**kwargs):raise RuntimeError('read failure')
        monkeypatch.setattr('app.agent.continuation_worker.execute_read_tool',fail_read)
        class ProcessDeath(BaseException):pass
        original=AgentJobService.fail
        async def die_after_job_update(self,**kwargs):
            assert kwargs.get('commit') is False
            await original(self,**kwargs)
            raise ProcessDeath('after conditional Job update, before atomic commit')
        monkeypatch.setattr(AgentJobService,'fail',die_after_job_update)
        worker=AgentWorker(f.factory,worker_id='crashing-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        with pytest.raises(ProcessDeath):await worker.poll_once()
        assert await states(f.factory,f.run_id)==('running','running','running','started')
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_worker_poll_reconciles_historical_orphan_without_reexecuting_tools(tmp_path,monkeypatch):
    from app.agent.test_continuation_failure_recovery import create_orphan
    f,job_id=await create_orphan(tmp_path,monkeypatch)
    try:
        async def unexpected(job,session):raise AssertionError('orphan recovery reexecuted continuation')
        worker=AgentWorker(f.factory,worker_id='orphan-recovery',handlers={'agent_continuation':unexpected})
        assert await worker.poll_once() is True
        async with f.factory() as session:
            job=await session.get(AgentJob,job_id)
            assert job.status=='failed' and job.lease_owner is None
        assert await worker.poll_once() is False
    finally:await f.engine.dispose()
