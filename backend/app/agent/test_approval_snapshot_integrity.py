"""Frozen-content integrity, independent of approval routing and live registry."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.approval_snapshot_integrity import (
    ApprovalSnapshotIntegrityError, validate_approval_snapshot_integrity,
)
from app.agent.catalog_release import build_catalog_release
from app.agent.capability_resolver import resolve_capabilities
from app.agent.registry import get_default_tool_registry_snapshot


def _case(*, project_id="digest-project", user_id=1701):
    release = build_catalog_release(get_default_tool_registry_snapshot())
    resolved = resolve_capabilities(release, user_id=user_id, project_id=project_id,
                                    project_role="owner" if project_id else None,
                                    requested_capabilities=["project.list", "chapter.generate"])
    run = SimpleNamespace(id="digest-run", user_id=user_id, project_id=project_id,
                          transaction_id="digest-transaction")
    catalog = SimpleNamespace(id="catalog-row", catalog_id=release.catalog_id,
        release_id=release.release_id, schema_version=release.schema_version,
        generation=release.generation, digest=release.digest, manifest_json=release.to_dict())
    snapshot = SimpleNamespace(id="snapshot-row", run_id=run.id, user_id=user_id,
        project_id=project_id, transaction_id=run.transaction_id,
        catalog_release_id=catalog.id, generation=resolved.generation,
        resolver_schema_version=resolved.resolver_schema_version,
        resolved_version=str(resolved.resolver_schema_version), digest=resolved.digest,
        release_digest=release.digest, snapshot_id=f"{resolved.snapshot_id}:run:{run.id}",
        request_json=resolved.request.to_dict(), selected_capability_ids_json=list(resolved.tool_names),
        exclusions_json=[x.to_dict() for x in resolved.exclusions],
        resolved_scope_json={"resolver_snapshot_id": resolved.snapshot_id,
                             "release_id": release.release_id, "tool_names": list(resolved.tool_names)})
    run.context_json = {"catalog_release": release.to_dict(), "capability_resolution": resolved.to_dict(),
        "catalog_release_id": release.release_id, "capability_resolution_id": resolved.snapshot_id,
        "relational_catalog_release_id": catalog.id, "relational_capability_snapshot_id": snapshot.id,
        "relational_capability_snapshot_key": snapshot.snapshot_id,
        "relational_capability_snapshot_digest": snapshot.digest}
    return SimpleNamespace(run=run, snapshot=snapshot, catalog_release=catalog)


def _validate(f):
    return validate_approval_snapshot_integrity(**vars(f))


def _expect(f, field):
    with pytest.raises(ApprovalSnapshotIntegrityError) as exc:
        _validate(f)
    assert exc.value.field == field
    assert "PRIVATE_PAYLOAD" not in str(exc.value)
    assert len(str(exc.value)) < 180


def _redigest_catalog(f):
    release = f.run.context_json["catalog_release"]
    payload = {k: release[k] for k in ("schema_version", "catalog_id", "generation", "providers", "tools")}
    release["digest"] = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    release["release_id"] = f'{release["catalog_id"]}:{release["digest"][:16]}'
    f.catalog_release.manifest_json = deepcopy(release)
    f.catalog_release.digest = release["digest"]
    f.catalog_release.release_id = release["release_id"]
    f.run.context_json["catalog_release_id"] = release["release_id"]
    resolver = f.run.context_json["capability_resolution"]
    resolver.update(release_id=release["release_id"], release_digest=release["digest"])
    f.snapshot.release_digest = release["digest"]
    f.snapshot.resolved_scope_json["release_id"] = release["release_id"]
    _redigest_resolver(f)


def _redigest_resolver(f):
    resolution = f.run.context_json["capability_resolution"]
    keys = ("resolver_schema_version", "release_id", "release_digest", "generation", "request", "tools", "exclusions")
    resolution["digest"] = sha256(json.dumps({k: resolution[k] for k in keys}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    resolution["snapshot_id"] = f'resolver-v{resolution["resolver_schema_version"]}:{resolution["digest"][:16]}'
    f.snapshot.digest = resolution["digest"]
    f.snapshot.snapshot_id = f'{resolution["snapshot_id"]}:run:{f.run.id}'
    f.snapshot.resolved_scope_json["resolver_snapshot_id"] = resolution["snapshot_id"]
    f.run.context_json.update(capability_resolution_id=resolution["snapshot_id"],
        relational_capability_snapshot_key=f.snapshot.snapshot_id,
        relational_capability_snapshot_digest=f.snapshot.digest)


@pytest.mark.parametrize("project_id,user_id", [("digest-project", 1701), (None, 1701), ("digest-project", "actor-1701")])
def test_builder_contract_valid_and_pure(project_id, user_id, monkeypatch):
    f = _case(project_id=project_id, user_id=user_id)
    before = deepcopy(vars(f))
    def forbidden(*args, **kwargs):
        raise AssertionError("live registry must not be consulted")
    monkeypatch.setattr("app.agent.registry.get_default_tool_registry_snapshot", forbidden)
    monkeypatch.setattr("app.agent.catalog_release.build_catalog_release", forbidden)
    assert _validate(f) is None
    assert vars(f) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("project_scoped", [True, False])
async def test_real_runtime_json_roundtrip(task_session, project_scoped):
    from app.models.user import User
    from app.models.novel import NovelProject
    from app.models.agent_catalog import AgentCatalogRelease, AgentRunCapabilitySnapshot
    from app.services.agent_runtime import AgentRuntimeService
    key = uuid4().hex
    user = User(username=key, email=f"{key}@example.com", hashed_password="x", is_active=True)
    task_session.add(user)
    await task_session.flush()
    project_id = key if project_scoped else None
    if project_scoped:
        task_session.add(NovelProject(id=key, user_id=user.id, title="摘要往返"))
        await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id=project_id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id,
        project_id=project_id, context={"requested_tools": ["project.list", "chapter.generate"]})
    await task_session.refresh(run)
    snapshot = (await task_session.execute(select(AgentRunCapabilitySnapshot).where(
        AgentRunCapabilitySnapshot.run_id == run.id))).scalar_one()
    catalog = await task_session.get(AgentCatalogRelease, snapshot.catalog_release_id)
    assert validate_approval_snapshot_integrity(run=run, snapshot=snapshot, catalog_release=catalog) is None


def test_nested_tuple_list_and_key_order_equivalent():
    f = _case()
    def freeze(value):
        if isinstance(value, dict): return {k: freeze(v) for k, v in reversed(list(value.items()))}
        if isinstance(value, list): return tuple(freeze(x) for x in value)
        return value
    f.run.context_json = freeze(f.run.context_json)
    f.snapshot.request_json = freeze(f.snapshot.request_json)
    f.snapshot.selected_capability_ids_json = tuple(f.snapshot.selected_capability_ids_json)
    f.snapshot.exclusions_json = freeze(f.snapshot.exclusions_json)
    f.snapshot.resolved_scope_json = freeze(f.snapshot.resolved_scope_json)
    assert _validate(f) is None


@pytest.mark.parametrize("part", ["tools", "providers"])
def test_catalog_payload_old_digest_rejected(part):
    f = _case()
    release = f.run.context_json["catalog_release"]
    key = "description" if part == "tools" else "source"
    release[part][0][key] += " PRIVATE_PAYLOAD"
    f.catalog_release.manifest_json = deepcopy(release)
    _expect(f, "catalog_release.digest")


@pytest.mark.parametrize("part", ["request", "tools", "exclusions"])
def test_resolver_payload_old_digest_rejected(part):
    f = _case()
    resolution = f.run.context_json["capability_resolution"]
    if part == "request": resolution[part]["include_confirmation_required"] = False
    elif part == "tools": resolution[part][0]["description"] += " PRIVATE_PAYLOAD"
    else:
        assert resolution[part]
        resolution[part][0]["reason"] += " PRIVATE_PAYLOAD"
    _expect(f, "capability_resolution.digest")


@pytest.mark.parametrize("owner,field,value", [
    ("catalog_release", "release_id", "wrong"), ("catalog_release", "digest", "x"*64),
    ("catalog_release", "schema_version", True), ("catalog_release", "catalog_id", "other"),
    ("catalog_release", "generation", 999),
    ("snapshot", "request_json", {}), ("snapshot", "selected_capability_ids_json", []),
    ("snapshot", "exclusions_json", []), ("snapshot", "generation", 999),
    ("snapshot", "resolver_schema_version", True), ("snapshot", "resolved_version", "99"),
    ("snapshot", "run_id", "other"), ("snapshot", "user_id", 999),
    ("snapshot", "project_id", "other"), ("snapshot", "transaction_id", "other"),
    ("snapshot", "catalog_release_id", "other"), ("snapshot", "digest", "f"*64),
    ("snapshot", "release_digest", "f"*64), ("snapshot", "snapshot_id", "other"),
])
def test_relational_fields_rejected(owner, field, value):
    f = _case()
    setattr(getattr(f, owner), field, value)
    _expect(f, f"{owner}.{field}")


@pytest.mark.parametrize("field,value", [("resolver_snapshot_id", "other"), ("release_id", "other"), ("tool_names", [])])
def test_scope_fields_rejected(field, value):
    f = _case()
    f.snapshot.resolved_scope_json[field] = value
    _expect(f, f"snapshot.resolved_scope_json.{field}")


@pytest.mark.parametrize("key", ["catalog_release_id", "capability_resolution_id", "relational_catalog_release_id",
    "relational_capability_snapshot_id", "relational_capability_snapshot_key", "relational_capability_snapshot_digest"])
def test_context_locator_missing_or_wrong(key):
    f = _case()
    f.run.context_json.pop(key)
    _expect(f, f"run.context_json.{key}")


@pytest.mark.parametrize("section,field", [("catalog_release", "release_id"), ("capability_resolution", "snapshot_id")])
def test_content_address_id_rejected(section, field):
    f = _case()
    f.run.context_json[section][field] = "wrong-content-id"
    _expect(f, f"{section}.{field}")


@pytest.mark.parametrize("section", ["catalog_release", "capability_resolution"])
def test_missing_payload_field(section):
    f = _case()
    f.run.context_json[section].pop("tools")
    _expect(f, f"{section}.tools")


@pytest.mark.parametrize("field,value", [("user_id", 999), ("project_id", "foreign-project")])
def test_rehashed_request_scope_cannot_change_actor(field, value):
    f = _case()
    f.run.context_json["capability_resolution"]["request"][field] = value
    f.snapshot.request_json[field] = value
    _redigest_resolver(f)
    _expect(f, f"capability_resolution.request.{field}")


def test_rehashed_resolver_tool_must_equal_frozen_catalog_tool():
    f = _case()
    f.run.context_json["capability_resolution"]["tools"][0]["description"] += "changed"
    _redigest_resolver(f)
    _expect(f, "capability_resolution.tools")


@pytest.mark.parametrize("key,value", [("release_id", "foreign-release"), ("release_digest", "a"*64), ("generation", 999)])
def test_rehashed_resolver_release_reference_rejected(key, value):
    f = _case()
    f.run.context_json["capability_resolution"][key] = value
    _redigest_resolver(f)
    _expect(f, f"capability_resolution.{key}")


@pytest.mark.parametrize("section", ["catalog_release", "capability_resolution"])
def test_rehashed_duplicate_or_noncanonical_tools_rejected(section):
    f = _case()
    f.run.context_json[section]["tools"].reverse()
    if section == "catalog_release": _redigest_catalog(f)
    else: _redigest_resolver(f)
    _expect(f, f"{section}.tools")


@pytest.mark.parametrize("section,key,value", [
    ("catalog_release", "generation", True), ("catalog_release", "schema_version", 0),
    ("catalog_release", "tools", {}), ("catalog_release", "providers", None),
    ("capability_resolution", "request", []), ("capability_resolution", "exclusions", {}),
    ("capability_resolution", "resolver_schema_version", False),
    ("capability_resolution", "generation", "3"),
])
def test_invalid_payload_types(section, key, value):
    f = _case()
    f.run.context_json[section][key] = value
    _expect(f, f"{section}.{key}")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {"bad-set"}, object()])
def test_unsupported_json_is_controlled_and_private(value):
    f = _case()
    f.run.context_json["catalog_release"]["tools"][0]["input_schema"]["PRIVATE_PAYLOAD"] = value
    with pytest.raises(ApprovalSnapshotIntegrityError) as exc:
        _validate(f)
    assert "PRIVATE_PAYLOAD" not in str(exc.value)
    assert len(str(exc.value)) < 180


def test_bool_is_not_integer_in_request_or_row():
    f = _case(user_id=1)
    f.snapshot.user_id = True
    _expect(f, "snapshot.user_id")
    f = _case(user_id=1)
    f.run.context_json["capability_resolution"]["request"]["user_id"] = True
    _redigest_resolver(f)
    _expect(f, "capability_resolution.request.user_id")


@pytest.mark.parametrize("arg", ["snapshot", "catalog_release"])
def test_required_relation_missing(arg):
    f = _case()
    setattr(f, arg, None)
    _expect(f, arg)
