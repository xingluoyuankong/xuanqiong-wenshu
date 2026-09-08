"""Transactional approval-outcome intents and narrow continuation activation."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select, update
from .continuation_scan import ContinuationScanCursor, scan_candidates

from ..models.agent import AgentApproval, AgentArtifactRef, AgentJob, AgentRun, AgentRunStep
from ..models.agent_catalog import AgentCatalogRelease, AgentCapabilityExecution
from ..models.agent_plan import PlanRevision
from ..services.agent_context_service import AgentContextService
from ..services.agent_execution_service import AgentExecutionService
from ..services.agent_plan_service import AgentPlanService
from ..services.agent_runtime import AgentConflict, AgentRuntimeService
from .approval_snapshot_integrity import validate_approval_snapshot_integrity
from .run_context_integrity import read_verified_run_context


class ContinuationConflict(AgentConflict):
    pass


def require_object(value, field):
    if not isinstance(value, dict):
        raise ContinuationConflict(f'{field} must be an object')
    return value


def require_identifier(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ContinuationConflict(f'{field} must be a nonempty identifier')
    return value


def validate_intent_payload(value):
    payload = require_object(value, 'continuation payload')
    for field in ('approval_id', 'source_job_id'):
        require_identifier(payload.get(field), field)
    if payload.get('return_phase') not in ('candidate_ready', 'quality_blocked'):
        raise ContinuationConflict('continuation return phase is invalid')
    return payload


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class AgentContinuationService:
    def __init__(self, session):
        self.session = session
        self.runtime = AgentRuntimeService(session)

    async def _lock(self, run_id, user_id):
        # SQLite ignores FOR UPDATE; a no-op UPDATE obtains its write lock too.
        changed = await self.session.execute(update(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
            .values(state_version=AgentRun.state_version).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise ContinuationConflict('continuation Run is unavailable')
        return (await self.session.execute(select(AgentRun).where(AgentRun.id == run_id)
            .execution_options(populate_existing=True))).scalar_one()

    async def load(self, run, approval, *, source_job_id=None):
        from .continuation_plan import load_continuation_plan
        context = require_object(run.context_json, 'Run context')
        revision_id = context.get('relational_plan_revision_id')
        revision_key = context.get('relational_plan_revision_key')
        if not revision_id and not revision_key:
            # Genuine plans created outside the durable planner keep the old
            # candidate-only path, rather than fabricating a PlanRevision.
            return None
        require_identifier(revision_id, 'plan revision id')
        revision = await self.session.get(PlanRevision, revision_id)
        if revision is None:
            raise ContinuationConflict('continuation revision is unavailable')
        await AgentPlanService(self.session).verify_revision(revision)
        snapshot, _ = await read_verified_run_context(context_service=AgentContextService(self.session), run=run, require_snapshot=True)
        capability = await AgentExecutionService(self.session).get_run_snapshot(run.id)
        catalog = await self.session.get(AgentCatalogRelease, capability.catalog_release_id) if capability else None
        validate_approval_snapshot_integrity(run=run, snapshot=capability, catalog_release=catalog)
        approval_step = await self.session.get(AgentRunStep, approval.step_id)
        bound_source = require_object(approval_step.input_json, 'approval checkpoint input').get('approval_source_job_id') if approval_step else None
        if bound_source is not None:
            require_identifier(bound_source, 'approval source job id')
        if source_job_id and bound_source and source_job_id != bound_source:
            raise ContinuationConflict('continuation source differs from approval checkpoint')
        source_id = require_identifier(source_job_id or bound_source or context.get('execution_job_id'), 'source job id')
        source = await self.session.get(AgentJob, source_id, populate_existing=True)
        if source is None:
            raise ContinuationConflict('continuation source job is unavailable')
        plan = load_continuation_plan(run=run, revision=revision, context_snapshot=snapshot,
                                     capability_snapshot=capability, approval=approval,
                                     approval_step=approval_step, source_job=source)
        return SimpleNamespace(plan=plan, revision=revision, context_snapshot=snapshot, capability_snapshot=capability, source=source)

    async def _cancel_remaining(self, run, *, except_step_id=None):
        steps = list((await self.session.execute(select(AgentRunStep).where(
            AgentRunStep.run_id == run.id, AgentRunStep.status.notin_({"completed", "cancelled"})
        ))).scalars())
        for step in steps:
            if step.id != except_step_id:
                step.status = "cancelled"
                step.finished_at = now()
                step.lease_owner = None
                step.lease_expires_at = None
        await self.session.execute(update(AgentApproval).where(AgentApproval.run_id==run.id,
            AgentApproval.status.in_({"pending","approved"})).values(status="cancelled"))
        await self.session.execute(update(AgentJob).where(AgentJob.run_id==run.id,
            AgentJob.status.in_({"blocked","queued"})).values(status="cancelled",finished_at=now()))

    async def record_rejected(self, *, approval):
        """Join the caller's decision transaction; never commit it independently."""
        run = await self._lock(approval.run_id, approval.user_id)
        loaded = await self.load(run, approval)
        if loaded is None:
            return None
        if approval.status != "rejected":
            raise ContinuationConflict("rejection outcome is not final")
        await self._cancel_remaining(run)
        job = await self._persist_intent(run, approval, loaded, return_phase="rejected")
        if run.status not in {"cancelled","failed","completed"}:
            run.cancel_requested_at = run.cancel_requested_at or now()
            await self.runtime.update_run(run_id=run.id, user_id=run.user_id, status="cancelling", phase="approval_rejected", commit=False)
            await self.runtime.update_run(run_id=run.id, user_id=run.user_id, status="cancelled", phase="cancelled", commit=False)
        return job

    async def fail_write(self, *, approval, step, execution, error, lease_owner, lease_generation):
        """Atomic failure outcome, facts and non-runnable intent; no best-effort enqueue."""
        try:
            run = await self._lock(approval.run_id, approval.user_id)
            # Callers may hold ORM instances loaded before another transaction
            # completed the approval. Refresh every mutable fact before checking
            # or projecting a terminal outcome; stale objects must never win.
            approval = await self.session.get(AgentApproval, approval.id, populate_existing=True)
            if approval is None:
                raise ContinuationConflict('continuation approval is unavailable')
            if step is not None:
                step = await self.session.get(AgentRunStep, step.id, populate_existing=True)
            if execution is not None:
                execution = await self.session.get(AgentCapabilityExecution, execution.id, populate_existing=True)
            if not (run.context_json or {}).get('relational_plan_revision_id'):
                if (run.context_json or {}).get('relational_plan_revision_key'):
                    raise ContinuationConflict('continuation revision locator is incomplete')
                return None
            if approval.status != 'executing':
                raise ContinuationConflict('terminal write outcome must not be overwritten')
            if step is not None:
                if step.status == 'completed':
                    raise ContinuationConflict('completed write step must not be failed')
                await self.runtime.fail_step(step_id=step.id,user_id=run.user_id,error_type=type(error).__name__,
                    lease_owner=lease_owner,lease_generation=lease_generation,commit=False)
            if execution is not None and execution.status != 'failed':
                await AgentExecutionService(self.session).fail_write_execution(execution=execution,
                    lease_generation=lease_generation,error=error,commit=False)
            await self.runtime.mark_approval_executed(approval_id=approval.id,user_id=run.user_id,status='execution_failed',commit=False)
            loaded=await self.load(run,approval)
            await self._cancel_remaining(run,except_step_id=step.id if step else None)
            job=await self._persist_intent(run,approval,loaded,return_phase='execution_failed')
            if run.status not in {'cancelled','failed','completed'}:
                await self.runtime.update_run(run_id=run.id,user_id=run.user_id,status='failed',phase='write_candidate_error',commit=False)
            await self.session.commit()
            await self.session.refresh(approval)
            return job
        except Exception:
            await self.session.rollback()
            raise

    async def _persist_intent(self, run, approval, loaded, *, return_phase):
        payload = loaded.plan.to_payload()
        key = f'continuation:v1:{loaded.revision.id}:{approval.id}:{approval.status}'
        if len(key) > 255:
            raise ContinuationConflict('continuation key exceeds storage contract')
        payload['return_phase'] = return_phase
        existing = (await self.session.execute(select(AgentJob).where(AgentJob.run_id == run.id, AgentJob.idempotency_key == key))).scalar_one_or_none()
        if existing:
            if existing.kind != 'agent_continuation' or existing.payload_json != payload:
                raise ContinuationConflict('continuation idempotency payload mismatch')
            return existing
        job = AgentJob(id=str(uuid4()), run_id=run.id, user_id=run.user_id, project_id=run.project_id,
                       correlation_id=run.correlation_id, transaction_id=run.transaction_id,
                       kind='agent_continuation', status='blocked' if approval.status == 'executed' else 'cancelled',
                       idempotency_key=key, payload_json=payload, result_json={}, available_at=now(),
                       finished_at=None if approval.status == 'executed' else now())
        self.session.add(job)
        await self.session.flush()
        return job

    async def complete_write(self, *, approval, step, execution, artifact, lease_owner, lease_generation, candidate_phase):
        """Commit terminal step/fact/approval, intent and Run state together.

        Provider/file/quality work is already durable; this method never calls
        the writer or accepts the candidate. None means no durable plan exists.
        """
        run = await self._lock(approval.run_id, approval.user_id)
        # Re-read the approval and execution facts after taking the Run lock.
        # This closes the late-writer race where a pre-approval object is reused
        # after the approval transaction already committed.
        approval = await self.session.get(AgentApproval, approval.id, populate_existing=True)
        if approval is None:
            raise ContinuationConflict('continuation approval is unavailable')
        if step is not None:
            step = await self.session.get(AgentRunStep, step.id, populate_existing=True)
        if execution is not None:
            execution = await self.session.get(AgentCapabilityExecution, execution.id, populate_existing=True)
        artifact = await self.session.get(AgentArtifactRef, artifact.id, populate_existing=True)
        if not (run.context_json or {}).get('relational_plan_revision_id'):
            if (run.context_json or {}).get('relational_plan_revision_key'):
                raise ContinuationConflict('continuation revision locator is incomplete')
            return None
        try:
            if approval.status != 'executing' or step is None or execution is None:
                raise ContinuationConflict('continuation write completion facts missing')
            if any(getattr(row, 'run_id', None) != run.id for row in (step, execution, artifact)):
                raise ContinuationConflict('continuation write facts cross Run')
            await self.runtime.complete_step(step_id=step.id, user_id=run.user_id, output={'artifact_id':artifact.id,'kind':artifact.kind},
                lease_owner=lease_owner, lease_generation=lease_generation, commit=False)
            await AgentExecutionService(self.session).complete_write_execution(execution=execution, lease_generation=lease_generation,
                output={'artifact_id':artifact.id,'kind':artifact.kind,'sha256':artifact.sha256},commit=False)
            await self.runtime.mark_approval_executed(approval_id=approval.id,user_id=run.user_id,status='executed',commit=False)
            loaded = await self.load(run, approval)
            job = await self._persist_intent(run, approval, loaded, return_phase=candidate_phase)
            # User control wins. The intent survives ordinary pause, and cancel
            # never revives the Run. Initial source ACK may still be pending.
            if run.cancel_requested_at is not None or run.status in {'cancelling','cancelled','failed','completed'}:
                job.status='cancelled';job.finished_at=now()
            elif run.status == 'paused' and run.pause_reason:
                pass
            elif loaded.source.status != 'succeeded':
                await self.runtime.update_run(run_id=run.id,user_id=run.user_id,status='awaiting_approval',phase='awaiting_approval',commit=False)
            else:
                await self.runtime.update_run(run_id=run.id,user_id=run.user_id,status='paused',phase=candidate_phase,progress=90,commit=False)
            await self.session.commit()
            await self.session.refresh(approval)
            return job
        except Exception:
            await self.session.rollback()
            raise

    async def activate_ready(self, limit=50, *, quarantine_invalid=False, scan_cursor: ContinuationScanCursor | None = None):
        """Only proven outcomes whose source is ACKed may re-enter scheduling."""
        cursor_before = scan_cursor.last_id if scan_cursor is not None else None
        query = select(AgentJob.id, AgentJob.run_id, AgentJob.user_id).where(
            AgentJob.kind == 'agent_continuation', AgentJob.status == 'blocked'
        ).order_by(AgentJob.created_at, AgentJob.id)
        candidates = await scan_candidates(self.session, query,
            limit=min(100, max(1, limit)), cursor=scan_cursor)
        activated=0
        last_examined = None
        for job_id,run_id,user_id in candidates:
            if activated >= limit:
                break
            last_examined = job_id
            try:
                run=await self._lock(run_id,user_id)
                job=await self.session.get(AgentJob,job_id,populate_existing=True)
                if job.status!='blocked':await self.session.rollback();continue
                if run.cancel_requested_at is not None or run.status in {'cancelling','cancelled','failed','completed'}:
                    job.status='cancelled';job.finished_at=now();await self.session.commit();continue
                if (run.status=='paused' and run.pause_reason) or (run.lease_owner and run.lease_expires_at and run.lease_expires_at>now()):
                    await self.session.rollback();continue
                payload = validate_intent_payload(job.payload_json)
                approval=await self.session.get(AgentApproval,payload['approval_id'],populate_existing=True)
                if approval is None or approval.status!='executed':
                    raise ContinuationConflict('continuation approval outcome mismatch')
                loaded=await self.load(run,approval,source_job_id=job.payload_json.get('source_job_id'))
                if loaded is None:
                    raise ContinuationConflict('continuation frozen plan is missing')
                expected={**loaded.plan.to_payload(),'return_phase':job.payload_json.get('return_phase')}
                if expected!=job.payload_json:raise ContinuationConflict('continuation frozen payload mismatch')
                if loaded.source.status != 'succeeded':
                    # A write approval may complete while the planning worker is
                    # still in its awaiting-approval branch. Only the persisted
                    # approval outcome plus verified write proof can recover an
                    # expired source ACK; timeout alone is never enough.
                    source = loaded.source
                    source_expired = source.status == 'running' and source.lease_expires_at is not None and source.lease_expires_at <= now() and source.cancel_requested_at is None
                    marker = (run.context_json or {}).get('approval_wait_handoff')
                    checkpoint_orders = {item.step_order for item in await self.runtime.list_steps(run_id=run.id,user_id=run.user_id)}
                    plan_orders = {item.order for item in loaded.plan.steps}
                    if isinstance(marker, dict) and 'step_orders' in marker:
                        orders = marker['step_orders']
                        if not isinstance(orders, list) or any(type(order) is not int or order < 1 for order in orders):
                            raise ContinuationConflict('approval handoff step orders are invalid')
                    handoff = (isinstance(marker,dict) and marker.get('job_id')==source.id
                               and type(marker.get('lease_generation')) is int
                               and marker.get('lease_generation')==source.lease_generation
                               and marker.get('plan_revision_id')==loaded.revision.id
                               and isinstance(marker.get('step_orders'),list)
                               and plan_orders.issubset(set(marker['step_orders']))
                               and plan_orders.issubset(checkpoint_orders))
                    if not (source_expired and handoff):
                        await self.session.rollback()
                        continue
                    await self.verify_write_proof(run, approval, loaded.capability_snapshot)
                    changed = await self.session.execute(update(AgentJob).where(
                        AgentJob.id == source.id, AgentJob.status == 'running',
                        AgentJob.lease_generation == marker['lease_generation'],
                        AgentJob.lease_owner == source.lease_owner,
                        AgentJob.lease_expires_at.is_not(None), AgentJob.lease_expires_at <= now(),
                        AgentJob.cancel_requested_at.is_(None),
                    ).values(status='succeeded', result_json={'status': 'awaiting_approval', 'handoff_recovered': True},
                        error_type=None, error_detail=None, finished_at=now(), lease_owner=None, lease_expires_at=None
                    ).execution_options(synchronize_session=False))
                    if changed.rowcount != 1:
                        await self.session.rollback()
                        continue
                if job.payload_json.get('return_phase') not in {'candidate_ready','quality_blocked'}:
                    raise ContinuationConflict('continuation return phase is invalid')
                await self.verify_write_proof(run, approval, loaded.capability_snapshot)
                await self.runtime.update_run(run_id=run.id,user_id=user_id,status='running',phase='continuation',commit=False)
                job.status='queued';job.available_at=now()
                await self.session.commit();activated+=1
            except Exception as exc:
                await self.session.rollback()
                from .continuation_plan import ContinuationPlanError
                from .approval_snapshot_integrity import ApprovalSnapshotIntegrityError
                from .run_context_integrity import RunContextIntegrityError
                from ..services.agent_plan_service import AgentPlanIntegrityError
                if not quarantine_invalid or not isinstance(exc, (ContinuationConflict, ContinuationPlanError, ApprovalSnapshotIntegrityError, RunContextIntegrityError, AgentPlanIntegrityError)):
                    if scan_cursor is not None:
                        scan_cursor.last_id = cursor_before
                    raise
                await self.session.execute(update(AgentJob).where(AgentJob.id==job_id, AgentJob.status=='blocked')
                    .values(status='failed',error_type=type(exc).__name__,error_detail='continuation activation contract failed',finished_at=now()))
                await self.session.commit()
        if scan_cursor is not None:
            scan_cursor.last_id = last_examined if last_examined is not None else None
        return activated

    async def verify_write_proof(self, run, approval, snapshot):
        step=await self.session.get(AgentRunStep,approval.step_id)
        execution=(await self.session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id==run.id,
            AgentCapabilityExecution.step_id==approval.step_id,AgentCapabilityExecution.idempotency_key==f'{run.id}:capability:approval:{approval.id}'))).scalar_one_or_none()
        if step is None or step.status!='completed' or execution is None or execution.status!='completed' or execution.snapshot_id!=snapshot.id:
            raise ContinuationConflict('continuation write proof is incomplete')
        step_output = require_object(step.output_json, 'write step output')
        execution_output = require_object(execution.output_json, 'write execution output')
        artifact_id = require_identifier(step_output.get('artifact_id'), 'write artifact id')
        artifact=await self.session.get(AgentArtifactRef,artifact_id)
        if artifact is None or artifact.run_id!=run.id or artifact.project_id!=run.project_id or artifact.user_id!=run.user_id:
            raise ContinuationConflict('continuation artifact proof is invalid')
        if execution_output.get('artifact_id')!=artifact.id or execution_output.get('sha256')!=artifact.sha256:
            raise ContinuationConflict('continuation artifact digest proof mismatch')
        if not artifact.sha256:
            raise ContinuationConflict('continuation artifact proof has no digest')
        from .write_executor import read_artifact_content
        try:
            await read_artifact_content(artifact_id=artifact.id,user_id=run.user_id,session=self.session)
        except Exception as exc:
            raise ContinuationConflict('continuation artifact integrity proof failed') from exc
        return artifact
