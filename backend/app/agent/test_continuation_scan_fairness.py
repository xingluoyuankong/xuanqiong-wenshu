"""Live scheduling must reach healthy work beyond an indefinitely blocked prefix."""
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.agent.continuation import now
from app.agent.test_continuation_failure_recovery import create_orphan
from app.agent.test_continuation_worker import pending_chain, approve_write
from app.agent.worker import AgentWorker, handle_agent_continuation_job
from app.models.agent import AgentJob, AgentRun

def clone_values(row): return {col.key: getattr(row, col.key) for col in row.__mapper__.columns}
async def add_prefix(factory, run_id, *, blocked, count):
    async with factory() as session:
        original=await session.get(AgentRun,run_id); values=clone_values(original); bad_run_id=str(uuid4())
        values.update(id=bad_run_id,correlation_id=str(uuid4()),transaction_id=str(uuid4()))
        if blocked: values.update(status='paused',pause_reason='user_requested',current_phase='paused')
        bad_run=AgentRun(**values);session.add(bad_run);await session.flush()
        good=(await session.execute(select(AgentJob).where(AgentJob.run_id==run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
        bad_ids=[]
        for i in range(count):
            vals=clone_values(good);jid=str(uuid4());vals.update(id=jid,run_id=bad_run_id,correlation_id=bad_run.correlation_id,transaction_id=bad_run.transaction_id,idempotency_key=f'prefix-{i}',created_at=now()-timedelta(days=2,seconds=count-i));session.add(AgentJob(**vals));bad_ids.append(jid)
        gid=good.id;await session.commit()
    return gid,bad_ids
@pytest.mark.asyncio
async def test_live_worker_rotates_past_user_paused_blocked_prefix(tmp_path,monkeypatch):
 f=await pending_chain(tmp_path,monkeypatch)
 try:
  await approve_write(f);gid,bids=await add_prefix(f.factory,f.run_id,blocked=True,count=105)
  worker=AgentWorker(f.factory,worker_id='rotating-live-worker',handlers={'agent_continuation':handle_agent_continuation_job})
  results=[await worker.poll_once() for _ in range(4)]
  assert any(results);assert f.calls==['planner','writer','statistics']
  async with f.factory() as s:
   assert (await s.get(AgentJob,gid)).status=='succeeded';assert set((await s.execute(select(AgentJob.status).where(AgentJob.id.in_(bids)))).scalars())=={'blocked'}
 finally:await f.engine.dispose()
@pytest.mark.asyncio
async def test_live_worker_rotates_past_unproven_failed_orphan_prefix(tmp_path,monkeypatch):
 f,_=await create_orphan(tmp_path,monkeypatch)
 try:
  gid,bids=await add_prefix(f.factory,f.run_id,blocked=False,count=205)
  worker=AgentWorker(f.factory,worker_id='rotating-recovery-worker',handlers={'agent_continuation':handle_agent_continuation_job})
  results=[await worker.poll_once() for _ in range(3)]
  assert any(results)
  async with f.factory() as s:
   assert (await s.get(AgentJob,gid)).status=='failed';assert set((await s.execute(select(AgentJob.status).where(AgentJob.id.in_(bids)))).scalars())=={'running'}
 finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_scan_cursor_pages_wraps_and_survives_deleted_anchor(tmp_path, monkeypatch):
 from app.agent.continuation_scan import ContinuationScanCursor, scan_candidates
 from sqlalchemy import delete
 f,_=await create_orphan(tmp_path,monkeypatch)
 try:
  _,bids=await add_prefix(f.factory,f.run_id,blocked=False,count=5)
  cursor=ContinuationScanCursor()
  async with f.factory() as s:
   q=select(AgentJob.id,AgentJob.run_id).where(AgentJob.id.in_(bids)).order_by(AgentJob.created_at)
   first=await scan_candidates(s,q,limit=2,cursor=cursor)
   assert [row[0] for row in first]==sorted(bids)[:2]
   anchor=cursor.last_id
   await s.execute(delete(AgentJob).where(AgentJob.id==anchor));await s.commit()
   second=await scan_candidates(s,q,limit=2,cursor=cursor)
   third=await scan_candidates(s,q,limit=2,cursor=cursor)
   assert [row[0] for row in second+third]==sorted(bids)[2:]
   assert cursor.last_id is None
   wrapped=await scan_candidates(s,q,limit=2,cursor=cursor)
   assert [row[0] for row in wrapped]==sorted(set(bids)-{anchor})[:2]
   untouched=ContinuationScanCursor()
   assert untouched.last_id is None
 finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_scan_cursor_rechecks_empty_and_changed_eligibility(tmp_path, monkeypatch):
 from app.agent.continuation_scan import ContinuationScanCursor,scan_candidates
 f,jid=await create_orphan(tmp_path,monkeypatch)
 try:
  cursor=ContinuationScanCursor(last_id='zzzz')
  async with f.factory() as s:
   q=select(AgentJob.id,AgentJob.run_id).where(AgentJob.id==jid,AgentJob.status=='running')
   assert [row[0] for row in await scan_candidates(s,q,limit=1,cursor=cursor)]==[jid]
   j=await s.get(AgentJob,jid);j.status='cancelled';await s.commit()
   assert await scan_candidates(s,q,limit=1,cursor=cursor)==[]
   assert cursor.last_id is None
   j.status='running';await s.commit()
   assert [row[0] for row in await scan_candidates(s,q,limit=1,cursor=cursor)]==[jid]
 finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_recovery_return_budget_does_not_skip_unprocessed_page_tail(tmp_path,monkeypatch):
 from types import SimpleNamespace
 from app.agent import continuation_failure_recovery as recovery
 from app.agent.continuation_scan import ContinuationScanCursor
 f,_=await create_orphan(tmp_path,monkeypatch)
 try:
  await add_prefix(f.factory,f.run_id,blocked=False,count=5)
  # Isolate the scheduler budget from proof validation (covered by the full
  # recovery suite). CAS here settles only the job ID presented by the scheduler.
  async def proof(session,job,run):
   return SimpleNamespace(job_id=job.id,run_id=run.id,lease_generation=job.lease_generation)
  async def settle(session,*,proof):
   job=await session.get(AgentJob,proof.job_id);job.status='failed';await session.commit();return job
  monkeypatch.setattr(recovery,'_failure_proof',proof);monkeypatch.setattr(recovery,'_cas_mark_failed',settle)
  cursor=ContinuationScanCursor();seen=[]
  async with f.factory() as s:
   expected=list((await s.execute(select(AgentJob.id).where(AgentJob.kind=='agent_continuation',AgentJob.status=='running',AgentJob.lease_expires_at.is_not(None),AgentJob.lease_expires_at <= now()).order_by(AgentJob.id))).scalars())
   for _ in range(6):
    rows=await recovery.recover_failed_continuations(s,limit=1,scan_cursor=cursor)
    assert len(rows)==1
    seen.extend(row.id for row in rows)
   assert seen==expected
   assert await recovery.recover_failed_continuations(s,limit=1,scan_cursor=cursor)==[]
 finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_recovery_scan_failure_keeps_cursor_for_retry(tmp_path,monkeypatch):
 from app.agent import continuation_failure_recovery as recovery
 from app.agent.continuation_scan import ContinuationScanCursor
 f,_=await create_orphan(tmp_path,monkeypatch)
 try:
  cursor=ContinuationScanCursor(last_id='zzzz')
  async def offline(*args,**kwargs):raise RuntimeError('temporary database failure')
  monkeypatch.setattr(recovery,'_get',offline)
  async with f.factory() as s:
   with pytest.raises(RuntimeError):await recovery.recover_failed_continuations(s,scan_cursor=cursor)
  assert cursor.last_id=='zzzz'
 finally:await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('limit,expected_page_size', [(-1, 1), (0, 1), (1, 1), (100, 100), (101, 100)])
async def test_activation_scan_limit_bounds_use_real_candidate_page(tmp_path, monkeypatch, limit, expected_page_size):
    from app.agent import continuation
    from app.agent.continuation_scan import ContinuationScanCursor

    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        good_id, paused_ids = await add_prefix(f.factory, f.run_id, blocked=True, count=105)
        async with f.factory() as session:
            run = await session.get(AgentRun, f.run_id)
            run.status = 'paused'
            run.pause_reason = 'user_requested'
            await session.commit()
        original_scan = continuation.scan_candidates
        observed = []

        async def observe_scan(session, statement, *, limit, cursor):
            # Delegate unchanged to production SQL and retain the exact returned page.
            rows = await original_scan(session, statement, limit=limit, cursor=cursor)
            observed.append((limit, [row[0] for row in rows]))
            return rows

        monkeypatch.setattr(continuation, 'scan_candidates', observe_scan)
        cursor = ContinuationScanCursor()
        async with f.factory() as session:
            activated = await continuation.AgentContinuationService(session).activate_ready(
                limit=limit, scan_cursor=cursor)
            assert observed == [(expected_page_size, sorted([good_id, *paused_ids])[:expected_page_size])]
            assert activated == 0
            assert cursor.last_id == (observed[0][1][-1] if limit > 0 else None)
            statuses = (await session.execute(select(AgentJob.status).where(
                AgentJob.id.in_([good_id, *paused_ids])))).scalars().all()
            assert len(statuses) == 106 and set(statuses) == {'blocked'}
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('quarantine_invalid', [False, True])
async def test_activation_infrastructure_failure_restores_cursor_and_retries(tmp_path, monkeypatch, quarantine_invalid):
    from app.agent.continuation import AgentContinuationService
    from app.agent.continuation_scan import ContinuationScanCursor

    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            job_id = (await session.execute(select(AgentJob.id).where(
                AgentJob.run_id == f.run_id, AgentJob.kind == 'agent_continuation'))).scalar_one()
        cursor = ContinuationScanCursor(last_id='zzzz')
        async with f.factory() as session:
            service = AgentContinuationService(session)
            original_lock = service._lock
            observed = []

            async def fail_after_real_lock(run_id, user_id):
                run = await original_lock(run_id, user_id)
                observed.append((cursor.last_id, session.in_transaction()))
                if len(observed) == 1:
                    raise RuntimeError('temporary activation database failure')
                return run

            monkeypatch.setattr(service, '_lock', fail_after_real_lock)
            with pytest.raises(RuntimeError, match='temporary activation database failure'):
                await service.activate_ready(limit=1, scan_cursor=cursor,
                    quarantine_invalid=quarantine_invalid)
            # Real scan wrapped and advanced the cursor before real SQL locking failed.
            assert observed == [(job_id, True)]
            assert not session.in_transaction()
            assert cursor.last_id == 'zzzz'
            async with f.factory() as observer:
                assert (await observer.get(AgentJob, job_id)).status == 'blocked'
            assert await service.activate_ready(limit=1, scan_cursor=cursor,
                quarantine_invalid=quarantine_invalid) == 1
            assert observed == [(job_id, True), (job_id, True)]
            assert cursor.last_id == job_id
            async with f.factory() as observer:
                assert (await observer.get(AgentJob, job_id)).status == 'queued'
            assert f.calls == ['planner', 'writer']
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [-1, 0])
async def test_activation_nonpositive_budget_leaves_real_ready_job_blocked(tmp_path, monkeypatch, limit):
    from app.agent.continuation import AgentContinuationService
    from app.agent.continuation_scan import ContinuationScanCursor

    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        cursor = ContinuationScanCursor()
        async with f.factory() as session:
            service = AgentContinuationService(session)
            assert await service.activate_ready(limit=limit, scan_cursor=cursor) == 0
            assert cursor.last_id is None
            job = (await session.execute(select(AgentJob).where(
                AgentJob.run_id == f.run_id, AgentJob.kind == 'agent_continuation'))).scalar_one()
            assert job.status == 'blocked'
            await session.rollback()
            # Positive control proves this is genuinely ready work, not poison/paused work.
            assert await service.activate_ready(limit=1, scan_cursor=cursor) == 1
            assert (await session.get(AgentJob, cursor.last_id)).status == 'queued'
            assert f.calls == ['planner', 'writer']
    finally:
        await f.engine.dispose()
