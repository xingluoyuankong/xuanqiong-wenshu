"""Replay a persisted plan after a committed approval outcome; never re-plan."""
from collections.abc import Mapping
from sqlalchemy import select,update

from .continuation import AgentContinuationService,ContinuationConflict,now,validate_intent_payload
from .dependency_state import classify_dependencies
from .jobs import AgentJobService
from .retry_policy import classify_error
from ..models.agent_catalog import AgentCapabilityExecution
from .registry import DEFAULT_TOOL_REGISTRY,bind_run_tool_registry
from .run_context_integrity import read_verified_run_context
from .tool_adapters import execute_read_tool
from ..models.agent import AgentApproval,AgentJob,AgentRun
from ..services.agent_context_service import AgentContextService
from ..services.agent_execution_service import AgentExecutionService
from ..services.agent_runtime import AgentConflict,AgentRuntimeService


def _json_copy(value):
    if isinstance(value, Mapping):
        return {key: _json_copy(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(child) for child in value]
    return value


async def handle_agent_continuation_job(job,session):
    runtime=AgentRuntimeService(session)
    service=AgentContinuationService(session)
    job_id,user_id,run_id,job_owner,job_generation=job.id,job.user_id,job.run_id,job.lease_owner,job.lease_generation
    job_attempt,job_max_attempts=job.attempt_count,job.max_attempts
    owner=f'continuation:{job_id}:{job_generation}'[:128]
    active_step_id=active_execution_id=active_step_generation=None
    run=await runtime.get_run(job.run_id,job.user_id)
    try:
        run=await runtime.claim_run(run_id=run.id,user_id=run.user_id,lease_owner=owner,lease_seconds=120)
    except AgentConflict:
        await AgentJobService(session).defer(job_id=job.id,user_id=job.user_id,lease_owner=job.lease_owner,lease_generation=job.lease_generation,reason='continuation_run_busy')
        return {'continuation_deferred':True}
    run_generation=run.lease_generation
    try:
        payload=validate_intent_payload(job.payload_json)
        approval=await session.get(AgentApproval,payload['approval_id'])
        if approval is None or approval.status!='executed':raise ContinuationConflict('continuation outcome is not executed')
        loaded=await service.load(run,approval,source_job_id=job.payload_json.get('source_job_id'))
        if loaded is None or {**loaded.plan.to_payload(),'return_phase':job.payload_json.get('return_phase')}!=job.payload_json:
            raise ContinuationConflict('continuation immutable payload mismatch')
        await service.verify_write_proof(run,approval,loaded.capability_snapshot)
        registry=bind_run_tool_registry(DEFAULT_TOOL_REGISTRY,run.context_json)
        registry.assert_compatible()
        # Shared reader also validates Run/Context identity and reference rows.
        await read_verified_run_context(context_service=AgentContextService(session),run=run,require_snapshot=True)
        pending=False
        results=[]
        for frozen in loaded.plan.steps:
            await session.refresh(run)
            if run.lease_owner != owner or run.lease_generation != run_generation or run.lease_expires_at is None or run.lease_expires_at <= now():
                raise ContinuationConflict('continuation Run lease changed before step')
            if run.cancel_requested_at is not None or run.status in {'cancelling','cancelled','failed','completed'}:
                raise ContinuationConflict('continuation stopped by Run lifecycle')
            if run.status=='paused' and run.pause_reason:
                await AgentJobService(session).defer(job_id=job.id,user_id=job.user_id,lease_owner=job.lease_owner,lease_generation=job.lease_generation,reason='run_paused')
                return {'continuation_deferred':True}
            checkpoint=await runtime.ensure_step(run_id=run.id,user_id=run.user_id,step_order=frozen.order,tool_name=frozen.tool_name,
                idempotency_key=f'{run.id}:step:{frozen.order}:{frozen.tool_name}',
                input_payload={'goal':loaded.revision.plan_json.get('goal',''),'context_refs':run.context_json.get('context_refs',[]),'tool_arguments':_json_copy(frozen.arguments)})
            if checkpoint.tool_name!=frozen.tool_name or checkpoint.input_json.get('tool_arguments')!=_json_copy(frozen.arguments):
                raise ContinuationConflict('continuation checkpoint arguments differ from frozen plan')
            if checkpoint.status=='completed':
                if frozen.risk_level not in {'read', 'suggest'}:
                    completed_approval=(await session.execute(select(AgentApproval).where(AgentApproval.run_id==run.id, AgentApproval.step_id==checkpoint.id))).scalar_one_or_none()
                    if completed_approval is None or completed_approval.status!='executed':
                        raise ContinuationConflict('completed write checkpoint lacks executed approval')
                    await service.verify_write_proof(run, completed_approval, loaded.capability_snapshot)
                results.append({'tool_name':frozen.tool_name,'result':dict(checkpoint.output_json or {})})
                continue
            if checkpoint.status in {'failed','cancelled'}:raise ContinuationConflict('continuation plan contains terminal failed step')
            statuses={step.step_order:step.status for step in await runtime.list_steps(run_id=run.id,user_id=run.user_id)}
            dependency=classify_dependencies(list(frozen.depends_on),statuses)
            if dependency.state=='waiting':pending=True;continue
            if dependency.state!='ready':raise ContinuationConflict('continuation dependency is terminal')
            manifest=registry.get(frozen.tool_name)
            if manifest.risk_level.value not in {'read','suggest'}:
                # Another approval may already be executing in a writer session.
                # Its step lease and source binding belong to that writer, not
                # to this continuation. Only a genuinely pending checkpoint is
                # eligible to become a new approval request.
                current_approval = (await session.execute(select(AgentApproval).where(
                    AgentApproval.run_id == run.id, AgentApproval.step_id == checkpoint.id
                ).execution_options(populate_existing=True))).scalar_one_or_none()
                if checkpoint.status == 'running' or (current_approval is not None and current_approval.status in {'pending','approved','executing'}):
                    pending=True
                    continue
                if checkpoint.status not in {'pending', 'awaiting_approval'}:
                    raise ContinuationConflict('write checkpoint is not eligible for approval')
                if checkpoint.status != 'awaiting_approval':
                    checkpoint.input_json={**dict(checkpoint.input_json or {}),'approval_source_job_id':job.id}
                    checkpoint.status='awaiting_approval'
                    await session.commit()
                await runtime.request_approval(run_id=run.id,user_id=run.user_id,step_id=checkpoint.id,tool_name=frozen.tool_name,
                    project_id=run.project_id,arguments={'goal':loaded.revision.plan_json.get('goal',''),**_json_copy(frozen.arguments)})
                pending=True;continue
            if checkpoint.status=='running' and checkpoint.lease_owner not in (None,owner) and checkpoint.lease_expires_at and checkpoint.lease_expires_at>now():
                await AgentJobService(session).defer(job_id=job_id,user_id=user_id,lease_owner=job_owner,lease_generation=job_generation,reason='continuation_step_busy')
                return {'continuation_deferred':True}
            previous_generation=checkpoint.lease_generation
            previous_status=checkpoint.status
            previous_expiry=checkpoint.lease_expires_at
            checkpoint=await runtime.claim_step(step_id=checkpoint.id,user_id=run.user_id,lease_owner=owner,lease_seconds=120)
            active_step_id,active_step_generation=checkpoint.id,checkpoint.lease_generation
            facts=AgentExecutionService(session)
            existing=await facts.repository.get_execution_by_idempotency(run_id=run.id,idempotency_key=f'{run.id}:capability:{checkpoint.id}')
            if existing is not None and existing.status=='started' and existing.lease_generation!=checkpoint.lease_generation:
                if previous_status!='running' or previous_expiry is None or previous_expiry>now() or existing.lease_generation!=previous_generation:
                    raise ContinuationConflict('read recovery facts do not match expired checkpoint')
                # Only after winning the new step lease may the prior read fact
                # transition to retryable failure. Never re-run a write here.
                changed=await session.execute(update(AgentCapabilityExecution).where(AgentCapabilityExecution.id==existing.id,
                    AgentCapabilityExecution.status=='started',AgentCapabilityExecution.lease_generation==previous_generation)
                    .values(status='failed',error_type='LeaseExpired',finished_at=now()))
                if changed.rowcount!=1:raise ContinuationConflict('read recovery fact changed concurrently')
                await session.commit()
                await session.refresh(existing)
            execution=await facts.begin_read_execution(run=run,step=checkpoint,snapshot=loaded.capability_snapshot,capability_id=frozen.tool_name,
                arguments={'goal':loaded.revision.plan_json.get('goal',''),'tool_arguments':_json_copy(frozen.arguments)},
                lease_generation=checkpoint.lease_generation,idempotency_key=f'{run.id}:capability:{checkpoint.id}')
            # No model choice or Planner call occurs here. The real registry still
            # performs schema, role and frozen provider checks at execution.
            active_step_id,active_execution_id,active_step_generation=checkpoint.id,execution.id,checkpoint.lease_generation
            output=await execute_read_tool(tool_name=frozen.tool_name,session=session,user_id=run.user_id,project_id=run.project_id,
                arguments=_json_copy(frozen.arguments),registry=registry)
            run=await service._lock(run_id,user_id)
            if run.lease_owner != owner or run.lease_generation != run_generation or run.lease_expires_at is None or run.lease_expires_at <= now():
                raise ContinuationConflict('continuation Run lease changed before read completion')
            if run.cancel_requested_at is not None or run.status in {'cancelling','cancelled','failed','completed'}:
                raise ContinuationConflict('continuation lifecycle changed before read completion')
            await runtime.complete_step(step_id=checkpoint.id,user_id=run.user_id,lease_owner=owner,lease_generation=checkpoint.lease_generation,
                output=output,commit=False)
            await facts.complete_read_execution(execution=execution,lease_generation=checkpoint.lease_generation,output=output,commit=False)
            await session.commit()
            active_step_id=active_execution_id=active_step_generation=None
            results.append({'tool_name':frozen.tool_name,'result':output})
        run=await service._lock(run.id,run.user_id)
        if run.lease_owner!=owner or run.lease_generation!=run_generation:
            raise ContinuationConflict('continuation Run lease changed')
        if run.cancel_requested_at is not None or run.status in {'cancelling','cancelled','failed','completed'}:
            raise ContinuationConflict('continuation lifecycle changed before ACK')
        if run.status=='paused' and run.pause_reason:
            await session.rollback()
            await AgentJobService(session).defer(job_id=job.id,user_id=job.user_id,lease_owner=job.lease_owner,lease_generation=job.lease_generation,reason='run_paused')
            return {'continuation_deferred':True}
        context=dict(run.context_json or {});context['tool_results']=results;context['continuation_job_id']=job.id
        run.context_json=context
        await runtime.update_run(run_id=run.id,user_id=run.user_id,status='awaiting_approval' if pending else 'paused',
            phase='awaiting_approval' if pending else job.payload_json['return_phase'],commit=False)
        changed=await session.execute(update(AgentJob).where(AgentJob.id==job.id,AgentJob.status=='running',
            AgentJob.lease_owner==job.lease_owner,AgentJob.lease_generation==job.lease_generation,AgentJob.cancel_requested_at.is_(None))
            .values(status='succeeded',result_json={'continuation_completed':True,'pending_approval':pending},finished_at=now(),lease_owner=None,lease_expires_at=None)
            .execution_options(synchronize_session=False))
        if changed.rowcount!=1:raise ContinuationConflict('continuation ACK lost job lease')
        run.lease_owner=None;run.lease_expires_at=None
        await session.commit()
        return {'continuation_acknowledged':True}
    except Exception as exc:
        await session.rollback()
        try:
            retry=classify_error(type(exc).__name__,attempt_count=job_attempt,max_attempts=job_max_attempts)
            run=await service._lock(run_id,user_id)
            owns_run=run.lease_owner==owner and run.lease_generation==run_generation
            if owns_run and active_step_id is not None:
                from ..models.agent import AgentRunStep
                checkpoint=await session.get(AgentRunStep,active_step_id)
                execution=await session.get(AgentCapabilityExecution,active_execution_id)
                if checkpoint and checkpoint.status=='running' and checkpoint.lease_owner==owner and checkpoint.lease_generation==active_step_generation:
                    await runtime.fail_step(step_id=checkpoint.id,user_id=user_id,lease_owner=owner,lease_generation=active_step_generation,error_type=type(exc).__name__,commit=False)
                    if retry.retryable and job_attempt<job_max_attempts:
                        checkpoint.status='pending';checkpoint.finished_at=None
                    if execution and execution.status=='started' and execution.lease_generation==active_step_generation:
                        await AgentExecutionService(session).fail_read_execution(execution=execution,lease_generation=active_step_generation,error=exc,commit=False)
            if owns_run and run.status not in {'paused','cancelling','cancelled','failed','completed'} and (not retry.retryable or job_attempt>=job_max_attempts):
                await runtime.update_run(run_id=run_id,user_id=user_id,status='failed',phase='continuation_error',commit=False)
            # The job transition and failure facts form one durable outcome.
            # A process death before commit leaves all four rows reclaimable.
            failed_job = await AgentJobService(session).fail(
                job_id=job_id, user_id=user_id, lease_owner=job_owner,
                lease_generation=job_generation, error_type=type(exc).__name__,
                detail='durable continuation handler failed', commit=False,
            )
            failure_status = failed_job.status
            await session.commit()
            return {'continuation_failed': True, 'continuation_job_status': failure_status}
        except BaseException:
            # Also prevent release_run's finally commit from flushing a partial
            # projection after cancellation or simulated process interruption.
            await session.rollback()
            raise
    finally:
        try:await runtime.release_run(run_id=run_id,user_id=user_id,lease_owner=owner,lease_generation=run_generation)
        except AgentConflict:pass
