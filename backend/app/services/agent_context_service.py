"""Application service for immutable Agent context snapshots and normalized references."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.agent import AgentRun, AgentSession
from ..models.agent_context import ContextSnapshot, ContextSnapshotRef


class AgentContextIntegrityError(ValueError):
    """Raised when a context snapshot violates scope or digest integrity."""


def canonical_digest(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _json_object(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentContextIntegrityError(f"{name} must be a JSON object")
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _ref_key(ref: dict[str, Any]) -> str:
    for key in ("ref_key", "ref_id", "id", "artifact_id", "version_id", "chapter_id", "project_id"):
        value = ref.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise AgentContextIntegrityError("every context ref needs a stable ref_key/ref_id/id/artifact_id/version_id/chapter_id/project_id")


def canonical_context_refs(refs: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for position, raw in enumerate(refs or []):
        ref = _json_object(raw, name=f"context_refs[{position}]")
        ref_type = str(ref.get("ref_type") or ref.get("kind") or "context").strip()
        if not ref_type:
            raise AgentContextIntegrityError("context ref type must not be blank")
        normalized.append(
            {
                "ref_order": position,
                "ref_type": ref_type,
                "ref_key": _ref_key(ref),
                "ref_version": (str(ref.get("ref_version") or ref.get("version") or "").strip() or None),
                "role": (str(ref.get("role") or "").strip() or None),
                "payload_json": ref,
            }
        )
    return normalized


def context_snapshot_material(snapshot: ContextSnapshot, refs: Iterable[ContextSnapshotRef] | None = None) -> dict[str, Any]:
    ordered_refs = sorted(list(refs if refs is not None else snapshot.refs), key=lambda item: item.ref_order)
    return {
        "schema_version": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "run_id": snapshot.run_id,
        "session_id": snapshot.session_id,
        "user_id": snapshot.user_id,
        "project_id": snapshot.project_id,
        "correlation_id": snapshot.correlation_id,
        "transaction_id": snapshot.transaction_id,
        "context_kind": snapshot.context_kind,
        "context_json": snapshot.context_json,
        "refs": [
            {
                "ref_order": item.ref_order,
                "ref_type": item.ref_type,
                "ref_key": item.ref_key,
                "ref_version": item.ref_version,
                "role": item.role,
                "payload_json": item.payload_json,
                "digest": item.digest,
            }
            for item in ordered_refs
        ],
    }


class AgentContextService:
    """Creates and verifies append-only context facts without changing runtime JSON behavior."""

    def __init__(self, session: Any):
        self.session = session

    async def create_snapshot(
        self,
        *,
        run: AgentRun,
        session: AgentSession,
        context_json: dict[str, Any],
        refs: Iterable[dict[str, Any]] | None = None,
        context_kind: str = "run_context",
        schema_version: int = 1,
    ) -> ContextSnapshot:
        if run.session_id != session.id:
            raise AgentContextIntegrityError("run and session association do not match")
        if run.user_id != session.user_id:
            raise AgentContextIntegrityError("run and session ownership do not match")
        if schema_version < 1:
            raise AgentContextIntegrityError("schema_version must be >= 1")
        normalized_context = _json_object(context_json, name="context_json")
        normalized_refs = canonical_context_refs(refs)
        snapshot = ContextSnapshot(
            snapshot_id=str(uuid4()),
            run_id=run.id,
            session_id=session.id,
            user_id=run.user_id,
            project_id=run.project_id,
            correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,
            schema_version=schema_version,
            context_kind=str(context_kind).strip() or "run_context",
            context_json=normalized_context,
            digest="",
        )
        snapshot.refs = [
            ContextSnapshotRef(
                ref_order=item["ref_order"],
                ref_type=item["ref_type"],
                ref_key=item["ref_key"],
                ref_version=item["ref_version"],
                role=item["role"],
                payload_json=item["payload_json"],
                digest=canonical_digest(item),
            )
            for item in normalized_refs
        ]
        snapshot.digest = canonical_digest(context_snapshot_material(snapshot, snapshot.refs))
        self.session.add(snapshot)
        await self.session.flush()
        await self.verify_snapshot(snapshot)
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> ContextSnapshot | None:
        return (await self.session.execute(
            select(ContextSnapshot).where(ContextSnapshot.snapshot_id == snapshot_id)
        )).scalar_one_or_none()

    async def get_latest_snapshot_for_run(
        self,
        *,
        run_id: str,
        session_id: str,
        user_id: int,
    ) -> ContextSnapshot | None:
        """Return the newest immutable context fact only inside the verified Run/Session/User scope."""
        statement = (
            select(ContextSnapshot)
            .options(selectinload(ContextSnapshot.refs))
            .where(
                ContextSnapshot.run_id == run_id,
                ContextSnapshot.session_id == session_id,
                ContextSnapshot.user_id == user_id,
            )
            .order_by(ContextSnapshot.created_at.desc(), ContextSnapshot.id.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_run_snapshot(
        self,
        *,
        run_id: str,
        snapshot_id: str | None = None,
    ) -> ContextSnapshot | None:
        """Read one immutable context fact scoped to a Run for recovery/planning."""
        statement = select(ContextSnapshot).options(selectinload(ContextSnapshot.refs)).where(ContextSnapshot.run_id == run_id)
        if snapshot_id is not None:
            statement = statement.where(ContextSnapshot.snapshot_id == snapshot_id)
        else:
            statement = statement.order_by(ContextSnapshot.created_at.desc(), ContextSnapshot.id.desc()).limit(1)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def verify_snapshot(self, snapshot: ContextSnapshot) -> None:
        expected = canonical_digest(context_snapshot_material(snapshot, snapshot.refs))
        if snapshot.digest != expected:
            raise AgentContextIntegrityError("context snapshot digest mismatch")
        for ref in snapshot.refs:
            material = {
                "ref_order": ref.ref_order,
                "ref_type": ref.ref_type,
                "ref_key": ref.ref_key,
                "ref_version": ref.ref_version,
                "role": ref.role,
                "payload_json": ref.payload_json,
            }
            if ref.digest != canonical_digest(material):
                raise AgentContextIntegrityError("context snapshot ref digest mismatch")

