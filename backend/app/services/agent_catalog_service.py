"""Application service for publishing immutable Catalog and Resolver facts per Agent Run."""
from __future__ import annotations

from ..agent.capability_resolver import CapabilityResolverSnapshot
from ..agent.catalog_release import CatalogRelease
from ..models.agent import AgentRun
from ..models.agent_catalog import AgentRunCapabilitySnapshot
from ..repositories.agent_catalog_repository import AgentCatalogRepository


class AgentCatalogService:
    """Creates and reads the relational Catalog/Resolver control-plane records."""

    def __init__(self, session):
        self.session = session
        self.repository = AgentCatalogRepository(session)

    async def persist_run_resolution(
        self,
        *,
        run: AgentRun,
        catalog_release: CatalogRelease,
        resolver_snapshot: CapabilityResolverSnapshot,
    ) -> AgentRunCapabilitySnapshot:
        release_row = await self.repository.get_or_create_catalog_release(catalog_release)
        return await self.repository.create_run_snapshot(
            run=run,
            catalog_release=release_row,
            snapshot=resolver_snapshot,
        )

    async def get_run_snapshot(self, run_id: str) -> AgentRunCapabilitySnapshot | None:
        return await self.repository.get_run_snapshot(run_id)

    async def resolved_capability_names(self, run_id: str) -> set[str] | None:
        snapshot = await self.get_run_snapshot(run_id)
        if snapshot is None:
            return None
        return {str(item) for item in snapshot.selected_capability_ids_json}
