"""Repository for relational Agent Catalog, Resolver snapshots, and executions."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.capability_resolver import CapabilityResolverSnapshot
from ..agent.catalog_release import CatalogRelease
from ..models.agent import AgentRun, AgentRunStep
from ..models.agent_catalog import (
    AgentCapabilityDefinition,
    AgentCapabilityExecution,
    AgentCatalogRelease,
    AgentProviderRelease,
    AgentRunCapabilitySnapshot,
)


class AgentCatalogRepositoryError(RuntimeError):
    """Raised when immutable catalog persistence detects conflicting identity."""


def _jsonable(value: Any) -> Any:
    """Thaw immutable release payloads before SQLAlchemy JSON serialization."""
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value

class AgentCatalogRepository:
    """Persistence boundary for immutable releases and per-Run resolution facts."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_catalog_release(self, release_id: str) -> AgentCatalogRelease | None:
        return (
            await self.session.execute(
                select(AgentCatalogRelease).where(AgentCatalogRelease.release_id == release_id)
            )
        ).scalar_one_or_none()

    async def get_or_create_catalog_release(self, release: CatalogRelease) -> AgentCatalogRelease:
        existing = await self.get_catalog_release(release.release_id)
        if existing is not None:
            if existing.digest != release.digest:
                raise AgentCatalogRepositoryError("catalog release identity conflicts with a different digest")
            return existing

        release_row = AgentCatalogRelease(
            release_id=release.release_id,
            catalog_id=release.catalog_id,
            schema_version=release.schema_version,
            generation=release.generation,
            status="published",
            digest=release.digest,
            manifest_json=_jsonable(release.to_dict()),
        )
        self.session.add(release_row)
        await self.session.flush()

        provider_by_id: dict[str, AgentProviderRelease] = {}
        for provider in release.providers:
            provider_row = AgentProviderRelease(
                catalog_release_id=release_row.id,
                provider_id=provider.provider_id,
                provider_version=provider.provider_version,
                api_version=provider.api_version,
                status=provider.status,
                source=provider.source,
                failure_code=provider.failure_code,
                tools_json=list(provider.tools),
                capability_tags_json=list(provider.capability_tags),
                dependencies_json=list(provider.dependencies),
                metadata_json={},
            )
            self.session.add(provider_row)
            provider_by_id[provider.provider_id] = provider_row
        await self.session.flush()

        for tool in release.tools:
            provider_row = provider_by_id.get(tool.provider_id or "")
            self.session.add(
                AgentCapabilityDefinition(
                    catalog_release_id=release_row.id,
                    provider_release_id=provider_row.id if provider_row is not None else None,
                    capability_id=tool.name,
                    name=tool.name,
                    version=tool.manifest_version,
                    manifest_version=tool.manifest_version,
                    description=tool.description,
                    input_schema_json=_jsonable(tool.input_schema),
                    output_schema_json=_jsonable(tool.output_schema),
                    risk_level=tool.risk_level,
                    confirmation_policy="required" if tool.requires_confirmation else "none",
                    requires_confirmation=tool.requires_confirmation,
                    project_scoped=tool.project_scoped,
                    supports_stream=tool.supports_stream,
                    idempotency_key=tool.idempotency_key,
                    timeout_seconds=tool.timeout_seconds,
                    cancellation_policy=tool.cancellation_policy,
                    idempotency_policy=tool.idempotency_policy,
                    audit_event_type=tool.audit_event_type,
                    context_bindings_json=_jsonable([binding.to_dict() for binding in tool.context_bindings]),
                    capability_tags_json=list(tool.capability_tags),
                    handler_identity=tool.handler_identity,
                )
            )
        await self.session.flush()
        return release_row

    async def get_run_snapshot(self, run_id: str) -> AgentRunCapabilitySnapshot | None:
        return (
            await self.session.execute(
                select(AgentRunCapabilitySnapshot)
                .where(AgentRunCapabilitySnapshot.run_id == run_id)
                .order_by(AgentRunCapabilitySnapshot.created_at.desc())
            )
        ).scalars().first()

    async def create_run_snapshot(
        self,
        *,
        run: AgentRun,
        catalog_release: AgentCatalogRelease,
        snapshot: CapabilityResolverSnapshot,
    ) -> AgentRunCapabilitySnapshot:
        existing = await self.get_run_snapshot(run.id)
        if existing is not None:
            if existing.digest != snapshot.digest or existing.catalog_release_id != catalog_release.id:
                raise AgentCatalogRepositoryError("Run already has a different resolver snapshot")
            return existing

        # Resolver content IDs are intentionally deterministic.  The relational
        # row is per Run, so use a Run-qualified ID to satisfy the global unique
        # database key while retaining the canonical resolver ID in scope JSON.
        persisted_snapshot_id = f"{snapshot.snapshot_id}:run:{run.id}"
        selected = list(snapshot.tool_names)
        return await self._add_run_snapshot(
            snapshot_row=AgentRunCapabilitySnapshot(
                snapshot_id=persisted_snapshot_id,
                run_id=run.id,
                transaction_id=run.transaction_id,
                catalog_release_id=catalog_release.id,
                user_id=run.user_id,
                project_id=run.project_id,
                resolver_schema_version=snapshot.resolver_schema_version,
                generation=snapshot.generation,
                selection_reason="capability_resolver",
                resolved_version=str(snapshot.resolver_schema_version),
                release_digest=snapshot.release_digest,
                digest=snapshot.digest,
                request_json=snapshot.request.to_dict(),
                resolved_scope_json={
                    "resolver_snapshot_id": snapshot.snapshot_id,
                    "release_id": snapshot.release_id,
                    "tool_names": selected,
                },
                selected_capability_ids_json=selected,
                exclusions_json=[item.to_dict() for item in snapshot.exclusions],
            )
        )

    async def _add_run_snapshot(self, snapshot_row: AgentRunCapabilitySnapshot) -> AgentRunCapabilitySnapshot:
        self.session.add(snapshot_row)
        await self.session.flush()
        return snapshot_row

    async def get_capability_for_snapshot(
        self, *, snapshot: AgentRunCapabilitySnapshot, capability_id: str
    ) -> AgentCapabilityDefinition | None:
        if capability_id not in {str(value) for value in snapshot.selected_capability_ids_json}:
            return None
        return (
            await self.session.execute(
                select(AgentCapabilityDefinition).where(
                    AgentCapabilityDefinition.catalog_release_id == snapshot.catalog_release_id,
                    AgentCapabilityDefinition.capability_id == capability_id,
                )
            )
        ).scalar_one_or_none()

    async def get_execution_by_idempotency(
        self, *, run_id: str, idempotency_key: str
    ) -> AgentCapabilityExecution | None:
        return (
            await self.session.execute(
                select(AgentCapabilityExecution).where(
                    AgentCapabilityExecution.run_id == run_id,
                    AgentCapabilityExecution.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def create_execution(
        self,
        *,
        run: AgentRun,
        step: AgentRunStep | None,
        snapshot: AgentRunCapabilitySnapshot,
        capability: AgentCapabilityDefinition,
        idempotency_key: str,
        input_payload: dict[str, Any],
        input_digest: str,
        lease_generation: int,
    ) -> AgentCapabilityExecution:
        row = AgentCapabilityExecution(
            execution_id=str(uuid4()),
            run_id=run.id,
            transaction_id=run.transaction_id,
            step_id=step.id if step is not None else None,
            snapshot_id=snapshot.id,
            capability_definition_id=capability.id,
            provider_release_id=capability.provider_release_id,
            correlation_id=run.correlation_id,
            capability_id=capability.capability_id,
            resolved_version=capability.version,
            selection_reason=snapshot.selection_reason,
            status="started",
            attempt=1,
            idempotency_key=idempotency_key,
            input_json=input_payload,
            input_digest=input_digest,
            lease_generation=lease_generation,
        )
        self.session.add(row)
        await self.session.flush()
        return row
