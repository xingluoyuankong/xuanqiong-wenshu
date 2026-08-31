"""Read-only queries for durable Agent quality facts and Artifact lineage."""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from ..models.agent import AgentArtifactRef, AgentRun
from ..models.agent_lineage import ArtifactLineage
from ..models.agent_quality import QualityFinding, QualityGate, QualityResult
from .agent_quality_service import AgentQualityService
from .agent_runtime import AgentNotFound


@dataclass(frozen=True)
class ArtifactQualityFacts:
    artifact: AgentArtifactRef
    result: QualityResult | None
    gate: QualityGate | None
    findings: tuple[QualityFinding, ...]


@dataclass(frozen=True)
class ArtifactLineageFacts:
    artifact: AgentArtifactRef
    upstream: tuple[ArtifactLineage, ...]
    downstream: tuple[ArtifactLineage, ...]


class AgentQualityQueryService:
    """Return owner-scoped immutable quality and lineage facts without content bodies."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_owned_artifact(self, *, artifact_id: str, user_id: int) -> AgentArtifactRef:
        artifact = (
            await self.session.execute(
                select(AgentArtifactRef)
                .join(AgentRun, AgentRun.id == AgentArtifactRef.run_id)
                .where(
                    AgentArtifactRef.id == artifact_id,
                    AgentArtifactRef.user_id == user_id,
                    AgentRun.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise AgentNotFound("artifact not found")
        return artifact

    async def get_quality_facts(self, *, artifact_id: str, user_id: int) -> ArtifactQualityFacts:
        artifact = await self._get_owned_artifact(artifact_id=artifact_id, user_id=user_id)
        result = (
            await self.session.execute(
                select(QualityResult)
                .where(
                    QualityResult.artifact_ref_id == artifact.id,
                    QualityResult.user_id == user_id,
                )
                .options(selectinload(QualityResult.findings), selectinload(QualityResult.gates))
                .order_by(QualityResult.evaluated_at.desc(), QualityResult.id.desc())
            )
        ).scalars().first()
        if result is None:
            return ArtifactQualityFacts(artifact=artifact, result=None, gate=None, findings=())
        gate = next(
            (item for item in result.gates if item.gate_name == AgentQualityService.GATE_NAME),
            None,
        )
        if gate is None and result.gates:
            gate = max(result.gates, key=lambda item: ((item.evaluated_at or item.created_at), item.id))
        return ArtifactQualityFacts(
            artifact=artifact,
            result=result,
            gate=gate,
            findings=tuple(result.findings),
        )

    async def get_lineage_facts(self, *, artifact_id: str, user_id: int) -> ArtifactLineageFacts:
        artifact = await self._get_owned_artifact(artifact_id=artifact_id, user_id=user_id)
        source = aliased(AgentArtifactRef)
        derived = aliased(AgentArtifactRef)
        rows = (
            await self.session.execute(
                select(ArtifactLineage)
                .join(AgentRun, AgentRun.id == ArtifactLineage.run_id)
                .join(source, source.id == ArtifactLineage.source_artifact_ref_id)
                .join(derived, derived.id == ArtifactLineage.derived_artifact_ref_id)
                .where(
                    AgentRun.user_id == user_id,
                    source.user_id == user_id,
                    derived.user_id == user_id,
                    or_(
                        ArtifactLineage.source_artifact_ref_id == artifact.id,
                        ArtifactLineage.derived_artifact_ref_id == artifact.id,
                    ),
                )
                .options(
                    selectinload(ArtifactLineage.source_artifact_ref),
                    selectinload(ArtifactLineage.derived_artifact_ref),
                )
                .order_by(ArtifactLineage.created_at.asc(), ArtifactLineage.id.asc())
            )
        ).scalars().all()
        upstream = tuple(item for item in rows if item.derived_artifact_ref_id == artifact.id)
        downstream = tuple(item for item in rows if item.source_artifact_ref_id == artifact.id)
        return ArtifactLineageFacts(artifact=artifact, upstream=upstream, downstream=downstream)
