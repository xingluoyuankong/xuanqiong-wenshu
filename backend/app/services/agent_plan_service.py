"""Application service for immutable, parent-linked Agent plan revisions."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from ..models.agent import AgentRun, AgentSession
from ..models.agent_context import ContextSnapshot
from ..models.agent_plan import PlanRevision
from .agent_context_service import AgentContextIntegrityError, AgentContextService, canonical_digest


class AgentPlanIntegrityError(ValueError):
    """Raised when a plan revision crosses immutable Run/Context parentage boundaries."""


def plan_revision_material(revision: PlanRevision) -> dict[str, Any]:
    return {
        "revision_id": revision.revision_id,
        "run_id": revision.run_id,
        "session_id": revision.session_id,
        "context_snapshot_id": revision.context_snapshot_id,
        "parent_revision_id": revision.parent_revision_id,
        "revision_number": revision.revision_number,
        "user_id": revision.user_id,
        "project_id": revision.project_id,
        "correlation_id": revision.correlation_id,
        "transaction_id": revision.transaction_id,
        "planner_id": revision.planner_id,
        "status": revision.status,
        "rationale": revision.rationale,
        "plan_json": revision.plan_json,
    }


class AgentPlanService:
    """Creates append-only plan revisions and enforces same-Run parentage."""

    def __init__(self, session: Any):
        self.session = session
        self.context_service = AgentContextService(session)

    async def create_revision(
        self,
        *,
        run: AgentRun,
        session: AgentSession,
        context_snapshot: ContextSnapshot,
        plan_json: dict[str, Any],
        parent_revision: PlanRevision | None = None,
        planner_id: str | None = None,
        status: str = "created",
        rationale: str | None = None,
    ) -> PlanRevision:
        if run.session_id != session.id or run.user_id != session.user_id:
            raise AgentPlanIntegrityError("run and session association do not match")
        if context_snapshot.run_id != run.id or context_snapshot.session_id != session.id:
            raise AgentPlanIntegrityError("context snapshot is not scoped to the target run/session")
        try:
            await self.context_service.verify_snapshot(context_snapshot)
        except AgentContextIntegrityError as exc:
            raise AgentPlanIntegrityError(str(exc)) from exc
        if not isinstance(plan_json, dict):
            raise AgentPlanIntegrityError("plan_json must be a JSON object")
        if parent_revision is not None:
            if parent_revision.run_id != run.id or parent_revision.session_id != session.id:
                raise AgentPlanIntegrityError("parent revision must belong to the same run/session")
            if parent_revision.revision_number < 1:
                raise AgentPlanIntegrityError("parent revision number is invalid")
        revision_number = await self._next_revision_number(run.id)
        if parent_revision is not None and parent_revision.revision_number >= revision_number:
            raise AgentPlanIntegrityError("parent revision must precede its child revision")
        revision = PlanRevision(
            revision_id=str(uuid4()),
            run_id=run.id,
            session_id=session.id,
            context_snapshot_id=context_snapshot.id,
            parent_revision_id=parent_revision.id if parent_revision is not None else None,
            revision_number=revision_number,
            user_id=run.user_id,
            project_id=run.project_id,
            correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,
            planner_id=(str(planner_id).strip() or None) if planner_id is not None else None,
            status=str(status).strip() or "created",
            rationale=rationale,
            plan_json=plan_json,
            digest="",
        )
        revision.digest = canonical_digest(plan_revision_material(revision))
        self.session.add(revision)
        await self.session.flush()
        await self.verify_revision(revision)
        return revision

    async def _next_revision_number(self, run_id: str) -> int:
        value = (await self.session.execute(
            select(func.max(PlanRevision.revision_number)).where(PlanRevision.run_id == run_id)
        )).scalar_one()
        return int(value or 0) + 1

    async def get_revision(self, revision_id: str) -> PlanRevision | None:
        return (await self.session.execute(
            select(PlanRevision).where(PlanRevision.revision_id == revision_id)
        )).scalar_one_or_none()

    async def get_latest_revision_for_run(
        self,
        *,
        run_id: str,
        session_id: str,
        user_id: int,
    ) -> PlanRevision | None:
        """Return the newest append-only plan revision inside one verified Run scope."""
        statement = (
            select(PlanRevision)
            .where(
                PlanRevision.run_id == run_id,
                PlanRevision.session_id == session_id,
                PlanRevision.user_id == user_id,
            )
            .order_by(PlanRevision.revision_number.desc(), PlanRevision.created_at.desc(), PlanRevision.id.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_latest_revision(self, *, run_id: str) -> PlanRevision | None:
        """Return the newest immutable revision for Run recovery and replan parentage."""
        return (await self.session.execute(
            select(PlanRevision)
            .where(PlanRevision.run_id == run_id)
            .order_by(PlanRevision.revision_number.desc(), PlanRevision.id.desc())
            .limit(1)
        )).scalar_one_or_none()

    async def get_revision_for_planner(self, *, run_id: str, planner_id: str) -> PlanRevision | None:
        """Make retry/recovery of one durable planner action idempotent."""
        return (await self.session.execute(
            select(PlanRevision).where(
                PlanRevision.run_id == run_id,
                PlanRevision.planner_id == planner_id,
            )
        )).scalar_one_or_none()

    async def verify_revision(self, revision: PlanRevision) -> None:
        expected = canonical_digest(plan_revision_material(revision))
        if revision.digest != expected:
            raise AgentPlanIntegrityError("plan revision digest mismatch")
