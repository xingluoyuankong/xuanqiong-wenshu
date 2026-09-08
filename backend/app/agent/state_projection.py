"""Read-only, correlation-safe state projection for the Agent workspace.

This service never mutates workflow state. It joins only rows owned by the
requesting user and belonging to the requested run, so a guessed correlation ID
is not a cross-run or cross-user read capability.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentApproval, AgentArtifactRef, AgentJob, AgentRun, AgentRunCommand, AgentRunStep
from ..models.task_runtime import TaskRuntime
from .command_ordering import command_order_by
from ..services.agent_runtime import AgentRuntimeService, allowed_commands_for_run, command_projection

_TERMINAL = {"completed", "succeeded", "failed", "cancelled", "dead_letter"}


def _artifact_projection(item: AgentArtifactRef) -> dict[str, Any]:
    metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
    return {
        "id": item.id,
        "kind": item.kind,
        "created_at": item.created_at,
        "accepted_version_id": metadata.get("accepted_version_id"),
        "acceptance_approval_id": metadata.get("acceptance_approval_id"),
    }


class AgentStateProjectionService:
    """Build an idempotent UI state snapshot from durable Agent records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_run_state(self, *, run_id: str, user_id: int) -> dict[str, Any]:
        # Resolve readability through the same project-membership policy used by
        # reasoning and activity replay. The durable rows themselves remain
        # attributed to the run owner, not the viewing member.
        run = await AgentRuntimeService(self.session).get_readable_run(run_id, user_id)
        source_user_id = run.user_id
        can_control = source_user_id == user_id
        if run.project_id:
            from ..services.project_access_service import ProjectAccessService
            access = await ProjectAccessService(self.session).require_project_read(run.project_id, user_id)
            can_control = access.can_write

        correlation_id = run.correlation_id
        steps = list((await self.session.execute(
            select(AgentRunStep).where(
                AgentRunStep.run_id == run.id,
                AgentRunStep.user_id == source_user_id,
                AgentRunStep.correlation_id == correlation_id,
            ).order_by(AgentRunStep.step_order.asc(), AgentRunStep.id.asc())
        )).scalars().all())
        approvals = list((await self.session.execute(
            select(AgentApproval).where(
                AgentApproval.run_id == run.id,
                AgentApproval.user_id == source_user_id,
                AgentApproval.correlation_id == correlation_id,
            ).order_by(AgentApproval.decision_at.is_(None).desc(), AgentApproval.decision_at.asc(), AgentApproval.id.asc())
        )).scalars().all())
        artifacts = list((await self.session.execute(
            select(AgentArtifactRef).where(
                AgentArtifactRef.run_id == run.id,
                AgentArtifactRef.user_id == source_user_id,
                AgentArtifactRef.correlation_id == correlation_id,
            ).order_by(AgentArtifactRef.created_at.asc(), AgentArtifactRef.id.asc())
        )).scalars().all())
        jobs = list((await self.session.execute(
            select(AgentJob).where(
                AgentJob.run_id == run.id,
                AgentJob.user_id == source_user_id,
                AgentJob.correlation_id == correlation_id,
            ).order_by(AgentJob.created_at.asc(), AgentJob.id.asc())
        )).scalars().all())
        commands = list((await self.session.execute(
            select(AgentRunCommand).where(
                AgentRunCommand.run_id == run.id,
                AgentRunCommand.user_id == source_user_id,
                AgentRunCommand.correlation_id == correlation_id,
            ).order_by(*command_order_by())
        )).scalars().all())
        tasks = list((await self.session.execute(
            select(TaskRuntime).where(
                TaskRuntime.correlation_id == correlation_id,
                TaskRuntime.owner_user_id == source_user_id,
            ).order_by(TaskRuntime.created_at.asc(), TaskRuntime.task_id.asc())
        )).scalars().all())

        last_sequence = max(0, int(run.event_sequence or 0))
        latest_public_summary = (
            dict(run.latest_public_summary_json)
            if isinstance(run.latest_public_summary_json, dict) and run.latest_public_summary_json
            else None
        )
        accepted_versions = [item["accepted_version_id"] for item in map(_artifact_projection, artifacts) if item["accepted_version_id"] is not None]
        blocked_reason = next((job.error_type for job in reversed(jobs) if job.status in {"failed", "dead_letter"} and job.error_type), None)
        active_command = next((item for item in reversed(commands) if item.status == "requested"), None)
        allowed_commands = (
            []
            if not can_control or (run.status == "paused" and run.current_phase == "recovery_ready")
            else allowed_commands_for_run(run.status, run.current_phase)
        )
        return {
            "correlation_id": correlation_id,
            "run_id": run.id,
            "project_id": run.project_id,
            "user_id": run.user_id,
            "status": run.status,
            "phase": run.current_phase,
            "state_version": max(0, int(run.state_version or 0)),
            "pause_reason": run.pause_reason,
            "resume_target_status": run.resume_target_status,
            "active_command": command_projection(active_command) if active_command else None,
            "allowed_commands": allowed_commands,
            "progress": max(0.0, min(100.0, float(run.progress or 0.0))),
            "current_step": run.current_step,
            "terminal_status": run.status if run.status in _TERMINAL else None,
            "recoverable": run.status in {"paused", "running", "created"},
            "cancellation_requested": run.cancel_requested_at is not None,
            "blocked_reason": blocked_reason,
            "capability_snapshot": run.context_json.get("capability_snapshot", {}) if isinstance(run.context_json, dict) else {},
            "last_event_sequence": last_sequence,
            # Explicit resume cursor for clients opening activity replay or
            # SSE after a state refresh. Keep the legacy field for compatibility.
            "resume_after_sequence": last_sequence,
            "latest_public_summary": latest_public_summary,
            "latest_public_summary_sequence": max(0, int(run.latest_public_summary_sequence or 0)),
            "latest_public_summary_at": run.latest_public_summary_at,
            "steps": [
                {"id": item.id, "order": item.step_order, "tool_name": item.tool_name, "status": item.status, "attempt_count": item.attempt_count}
                for item in steps
            ],
            "approvals": [
                {"id": item.id, "step_id": item.step_id, "tool_name": item.tool_name, "status": item.status, "decision_at": item.decision_at}
                for item in approvals
            ],
            "artifacts": [_artifact_projection(item) for item in artifacts],
            "accepted_version_ids": accepted_versions,
            "jobs": [
                {"id": item.id, "kind": item.kind, "status": item.status, "attempt_count": item.attempt_count, "max_attempts": item.max_attempts, "error_type": item.error_type}
                for item in jobs
            ],
            "commands": [command_projection(item) for item in commands],
            "task_runtime_refs": [
                {"task_id": item.task_id, "task_type": item.task_type, "status": item.status, "stage": item.stage, "progress": item.progress}
                for item in tasks
            ],
        }
