"""Shared strict read of a Run-bound context fact for approval and durable execution."""
from collections.abc import Mapping
from pydantic import ValidationError
from .schemas import AgentContextRef
from ..services.agent_context_service import AgentContextIntegrityError, canonical_context_refs


class RunContextIntegrityError(AgentContextIntegrityError):
    def __init__(self, field: str):
        self.field = field
        super().__init__(f"run context integrity mismatch for {field}")


def _parse_refs(payload):
    if not isinstance(payload, Mapping):
        raise RunContextIntegrityError('context_refs')
    raw = payload.get('context_refs', [])
    if not isinstance(raw, list):
        raise RunContextIntegrityError('context_refs')
    try:
        return [AgentContextRef.model_validate(item, strict=True) for item in raw]
    except (ValidationError, ValueError, TypeError) as exc:
        raise RunContextIntegrityError('context_refs') from exc


def _values(refs):
    return [ref.model_dump(mode='json') for ref in refs]


async def read_verified_run_context(*, context_service, run, require_snapshot=False):
    """Return (snapshot, user refs); true legacy has no relational snapshot.

    No failure in a modern locator, identity, digest, or reference relation may
    be interpreted as legacy fallback. Automatic initial novel references are
    permitted after the exact user-reference prefix.
    """
    snapshot = None
    if context_service is None:
        raise RunContextIntegrityError('context_snapshot')
    context = run.context_json
    current_refs = _parse_refs(context)
    markers = ('catalog_release', 'capability_resolution', 'relational_catalog_release_id',
               'relational_capability_snapshot_id', 'relational_capability_snapshot_key',
               'relational_capability_snapshot_digest', 'relational_context_snapshot_id',
               'relational_context_snapshot_key')
    modern = require_snapshot or any(key in context for key in markers)
    selected_refs = current_refs
    if modern:
        row_id = context.get('relational_context_snapshot_id')
        key = context.get('relational_context_snapshot_key')
        if not isinstance(row_id, str) or not row_id.strip() or not isinstance(key, str) or not key.strip():
            raise RunContextIntegrityError('context_snapshot')
        service = context_service
        snapshot = await service.get_run_snapshot(run_id=run.id, snapshot_id=key)
        if snapshot is None:
            raise RunContextIntegrityError('context_snapshot')
        if type(snapshot.schema_version) is not int or snapshot.schema_version != 1:
            raise RunContextIntegrityError('context_snapshot')
        expected = {'id': row_id, 'snapshot_id': key, 'run_id': run.id,
                    'session_id': run.session_id, 'user_id': run.user_id,
                    'project_id': run.project_id, 'correlation_id': run.correlation_id,
                    'transaction_id': run.transaction_id}
        if any(getattr(snapshot, field) != value for field, value in expected.items()):
            raise RunContextIntegrityError('context_snapshot')
        try:
            await service.verify_snapshot(snapshot)
        except (AgentContextIntegrityError, TypeError, ValueError) as exc:
            raise RunContextIntegrityError('context_snapshot') from exc
        selected_refs = _parse_refs(snapshot.context_json)
        if _values(selected_refs) != _values(current_refs):
            raise RunContextIntegrityError('context_refs')
        # Runtime writes user references first, followed by automatic novel
        # context. Replan writes canonical user refs only. Validate the user
        # prefix, not all auto-selected novel facts as AgentContextRef objects.
        rows = sorted(snapshot.refs, key=lambda item: item.ref_order)
        if len(rows) < len(selected_refs):
            raise RunContextIntegrityError('context_snapshot.refs')
        try:
            prefix = [AgentContextRef.model_validate(row.payload_json, strict=True) for row in rows[:len(selected_refs)]]
        except (ValidationError, ValueError, TypeError) as exc:
            raise RunContextIntegrityError('context_snapshot.refs') from exc
        if _values(prefix) != _values(selected_refs) or any(row.ref_order != index for index, row in enumerate(rows)):
            raise RunContextIntegrityError('context_snapshot.refs')
        expected_rows = canonical_context_refs(snapshot.context_json.get('context_refs', []))
        for row, expected_row in zip(rows, expected_rows):
            if any(getattr(row, field) != expected_row[field] for field in ('ref_order', 'ref_type', 'ref_key', 'ref_version', 'role')):
                raise RunContextIntegrityError('context_snapshot.refs')
    return snapshot, selected_refs
