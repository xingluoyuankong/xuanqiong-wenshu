"""Read-only, minimal project-entity summaries for the Agent workspace."""

from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.faction import Faction
from ..models.foreshadowing import Foreshadowing
from ..models.knowledge_graph import CharacterNode
from ..models.novel import BlueprintCharacter
from ..models.research import ResearchArtifact
from .novel_service import NovelService

AgentEntityKind = Literal[
    "character",
    "faction",
    "foreshadowing",
    "knowledge_node",
    "research_artifact",
]


class AgentEntitySummary(TypedDict):
    kind: AgentEntityKind
    entity_id: int
    label: str
    status: str | None
    detail: str | None


class AgentEntityContextService:
    """Expose only selection-safe identifiers and display labels to Chat-first UI."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_project_entity_summaries(
        self,
        *,
        project_id: str,
        user_id: int,
        per_kind_limit: int = 40,
    ) -> list[AgentEntitySummary]:
        """Return bounded entity rows without prose, raw research sources, or metadata."""
        await NovelService(self.session).ensure_project_owner(project_id, user_id)
        limit = max(1, min(int(per_kind_limit), 100))

        characters = list(
            (await self.session.scalars(
                select(BlueprintCharacter)
                .where(BlueprintCharacter.project_id == project_id)
                .order_by(BlueprintCharacter.position.asc(), BlueprintCharacter.id.asc())
                .limit(limit)
            )).all()
        )
        factions = list(
            (await self.session.scalars(
                select(Faction)
                .where(Faction.project_id == project_id)
                .order_by(Faction.name.asc(), Faction.id.asc())
                .limit(limit)
            )).all()
        )
        foreshadowings = list(
            (await self.session.scalars(
                select(Foreshadowing)
                .where(Foreshadowing.project_id == project_id)
                .order_by(Foreshadowing.chapter_number.asc(), Foreshadowing.id.asc())
                .limit(limit)
            )).all()
        )
        nodes = list(
            (await self.session.scalars(
                select(CharacterNode)
                .where(CharacterNode.project_id == project_id)
                .order_by(CharacterNode.name.asc(), CharacterNode.id.asc())
                .limit(limit)
            )).all()
        )
        research = list(
            (await self.session.scalars(
                select(ResearchArtifact)
                .where(ResearchArtifact.project_id == project_id, ResearchArtifact.user_id == user_id)
                .order_by(ResearchArtifact.created_at.desc(), ResearchArtifact.id.desc())
                .limit(limit)
            )).all()
        )

        rows: list[AgentEntitySummary] = []
        rows.extend(
            {
                "kind": "character",
                "entity_id": int(entity.id),
                "label": str(entity.name),
                "status": str(entity.identity) if entity.identity else None,
                "detail": None,
            }
            for entity in characters
        )
        rows.extend(
            {
                "kind": "faction",
                "entity_id": int(entity.id),
                "label": str(entity.name),
                "status": str(entity.faction_type) if entity.faction_type else None,
                "detail": None,
            }
            for entity in factions
        )
        rows.extend(
            {
                "kind": "foreshadowing",
                "entity_id": int(entity.id),
                "label": str(entity.name or f"伏笔 #{entity.id}"),
                "status": str(entity.status) if entity.status else None,
                "detail": f"第 {entity.chapter_number} 章",
            }
            for entity in foreshadowings
        )
        rows.extend(
            {
                "kind": "knowledge_node",
                "entity_id": int(entity.id),
                "label": str(entity.name),
                "status": str(entity.status) if entity.status else None,
                "detail": str(entity.role_type) if entity.role_type else None,
            }
            for entity in nodes
        )
        rows.extend(
            {
                "kind": "research_artifact",
                "entity_id": int(entity.id),
                "label": f"研究 #{entity.id} · {entity.scope}",
                "status": str(entity.status),
                "detail": f"第 {entity.chapter_number} 章" if entity.chapter_number else None,
            }
            for entity in research
        )
        return rows
