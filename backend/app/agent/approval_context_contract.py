"""Approval-specific argument projection after shared strict Run context reads."""
from fastapi import HTTPException
from .context_refs import ContextRefValidationError, resolve_agent_context_refs
from .policy import ProjectScopeViolation
from .run_context_integrity import RunContextIntegrityError, read_verified_run_context
from ..services.agent_context_service import AgentContextService
from ..services.agent_runtime import AgentConflict


class ApprovalContextContractError(ValueError):
    def __init__(self, field: str):
        self.field = field
        super().__init__(f"approval context contract mismatch for {field}")


async def validate_approval_context_contract(*, session, run, approval, manifest, require_snapshot: bool):
    """Validate current Run context, not an unrecorded approval-time version."""
    if session is None:
        raise ApprovalContextContractError('context_snapshot')
    try:
        _, selected_refs = await read_verified_run_context(
            context_service=AgentContextService(session), run=run, require_snapshot=require_snapshot,
        )
    except RunContextIntegrityError as exc:
        raise ApprovalContextContractError(exc.field) from exc
    try:
        resolved = await resolve_agent_context_refs(session=session, user_id=run.user_id,
                                                   session_project_id=run.project_id, refs=selected_refs)
    except (ContextRefValidationError, ProjectScopeViolation, AgentConflict, HTTPException) as exc:
        raise ApprovalContextContractError('context_refs') from exc
    try:
        arguments = dict(approval.request_json or {})
        projected = resolved.project_arguments(manifest, explicit=arguments)
    except (ContextRefValidationError, ValueError, TypeError) as exc:
        raise ApprovalContextContractError('approval.context_arguments') from exc
    if projected != arguments:
        raise ApprovalContextContractError('approval.context_arguments')
