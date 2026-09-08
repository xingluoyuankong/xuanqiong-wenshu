"""UI005 F1/F4 regressions: real Runtime facts and a real registry execution edge."""
from copy import deepcopy
from functools import wraps
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.agent import registry as registry_module
from app.agent import catalog_release as catalog_module
from app.agent.catalog_release import build_catalog_release
from app.agent.execution import ApprovalRunContractError, validate_approval_run_contract
from app.agent.registry import DEFAULT_TOOL_REGISTRY
from app.api.routers import agent as agent_router
from app.models.agent import AgentArtifactRef, AgentRun
from app.models.agent_catalog import AgentCapabilityExecution, AgentCatalogRelease, AgentProviderRelease
from app.models.novel import NovelProject
from app.models.user import User
from app.repositories.agent_catalog_repository import AgentCatalogRepository
from app.services.agent_execution_service import AgentExecutionService
from app.services.agent_runtime import AgentRuntimeService


# These are actual keys emitted by AgentRuntimeService.create_run, not a new
# discriminator invented by the test. Each case asserts runtime emitted its key.
MODERN_MARKERS = (
    "catalog_release", "capability_resolution", "catalog_release_id",
    "capability_resolution_id", "relational_catalog_release_id",
    "relational_capability_snapshot_id", "relational_capability_snapshot_key",
    "relational_capability_snapshot_digest", "relational_context_snapshot_id",
    "relational_context_snapshot_key",
)


async def _fixture(session, monkeypatch, *, legacy=False, provider_backed=False, manifest_override=()):
    if provider_backed:
        # Use the real built-in provider catalog and Runtime builders. Attribute
        # the write capability to an existing loaded provider in memory, before
        # the release/resolver are generated; no fabricated hashes or JSON repair.
        health = deepcopy(registry_module.DEFAULT_TOOL_PROVIDER_HEALTH)
        provider = next(item for item in health if item["provider_id"] == "project-read")
        provider["tools"].append("chapter.generate")
        monkeypatch.setattr(registry_module, "DEFAULT_TOOL_PROVIDER_HEALTH", health)
    if manifest_override:
        original_builder = catalog_module.build_catalog_release

        def versioned_release(*args, **kwargs):
            raw = deepcopy(args[0] if args else registry_module.get_default_tool_registry_snapshot())
            provider = next(p for p in raw["providers"] if p["provider_id"] == "project-read")
            provider["provider_version"] = manifest_override[0]
            return original_builder(raw, **kwargs)

        monkeypatch.setattr(catalog_module, "build_catalog_release", versioned_release)
    key = uuid4().hex
    user = User(username=f"integrity-{key}", email=f"{key}@example.com",
                hashed_password="fixture-password", is_active=True)
    session.add(user)
    await session.flush()
    project = NovelProject(id=key, user_id=user.id, title="UI005 integrity")
    session.add(project)
    await session.flush()
    runtime = AgentRuntimeService(session)
    agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
    if legacy:
        # A real persisted old-shape Run, never modernized and then mislabeled.
        run = AgentRun(id=str(uuid4()), correlation_id=str(uuid4()),
                       transaction_id=str(uuid4()), session_id=agent_session.id,
                       user_id=user.id, project_id=project.id, status="created",
                       context_json={"goal": "legacy approval"})
        session.add(run)
        await session.commit()
    else:
        run = await runtime.create_run(session_id=agent_session.id, user_id=user.id,
                                       project_id=project.id,
                                       context={"requested_tools": ["chapter.generate"]})
    facts = AgentExecutionService(session)
    snapshot = await facts.get_run_snapshot(run.id)
    capability = catalog = provider = None
    if not legacy:
        assert snapshot is not None
        capability = await facts.repository.get_capability_for_snapshot(
            snapshot=snapshot, capability_id="chapter.generate")
        assert capability is not None
        catalog = await session.get(AgentCatalogRelease, snapshot.catalog_release_id)
        assert catalog is not None
        # Assert rather than repairing creation results.
        assert run.context_json["catalog_release"] == catalog.manifest_json
        assert run.context_json["relational_capability_snapshot_digest"] == snapshot.digest
        if capability.provider_release_id is not None:
            provider = await session.get(AgentProviderRelease, capability.provider_release_id)
        assert (provider is not None) is provider_backed
    arguments = {"chapter_number": 1}
    step = await runtime.ensure_step(run_id=run.id, user_id=user.id, step_order=1,
                                    tool_name="chapter.generate", idempotency_key=f"{run.id}:integrity",
                                    input_payload=arguments)
    step.status = "awaiting_approval"
    await session.commit()
    approval = await runtime.request_approval(run_id=run.id, user_id=user.id,
                                              step_id=step.id, tool_name="chapter.generate",
                                              project_id=project.id, arguments=arguments)
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True,
                                  reason="UI005 integrity regression")
    await session.refresh(run)
    calls = []
    original = DEFAULT_TOOL_REGISTRY.get_handler("chapter.generate")

    @wraps(original)
    async def sentinel(**kwargs):
        calls.append(kwargs)
        return {"artifact": SimpleNamespace(id="integrity-artifact")}

    monkeypatch.setitem(DEFAULT_TOOL_REGISTRY._handlers, "chapter.generate", sentinel)
    assert DEFAULT_TOOL_REGISTRY.get_handler_identity("chapter.generate") == (
        f"{original.__module__}:{original.__qualname__}")
    return SimpleNamespace(user=user, run=run, step=step, approval=approval,
                           snapshot=snapshot, capability=capability, catalog=catalog,
                           provider=provider, calls=calls)


async def _execute(session, f):
    return await agent_router._execute_registered_approval(
        approval_id=f.approval.id, session=session, user_id=f.user.id)


async def _counts(session, f):
    return tuple([await session.scalar(select(func.count()).select_from(model).where(
        model.run_id == f.run.id)) for model in (AgentCapabilityExecution, AgentArtifactRef)])


async def _rejected(session, f, field):
    before = await _counts(session, f)
    with pytest.raises(ApprovalRunContractError) as exc:
        await _execute(session, f)
    assert exc.value.field == field
    assert exc.value.detail["code"] == "run_contract_mismatch"
    assert f.calls == []
    assert await _counts(session, f) == before == (0, 0)


@pytest.mark.asyncio
async def test_modern_missing_snapshot_rejected_at_real_route(task_session, monkeypatch):
    f = await _fixture(task_session, monkeypatch)
    original = deepcopy(f.run.context_json)
    await task_session.delete(f.snapshot)
    await task_session.commit()
    assert f.run.context_json == original
    assert await AgentExecutionService(task_session).get_run_snapshot(f.run.id) is None
    await _rejected(task_session, f, "snapshot")


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", MODERN_MARKERS)
@pytest.mark.parametrize("null_value", [False, True], ids=["runtime-value", "damaged-null"])
async def test_each_runtime_marker_blocks_missing_snapshot(task_session, monkeypatch, marker, null_value):
    f = await _fixture(task_session, monkeypatch)
    assert marker in f.run.context_json
    value = deepcopy(f.run.context_json[marker])
    assert value is not None
    # Deliberate damaged-state input, derived from the real Runtime context.
    f.run.context_json = {marker: None if null_value else value}
    await task_session.delete(f.snapshot)
    await task_session.commit()
    await _rejected(task_session, f, "snapshot")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["legacy", "providerless", "provider-backed"])
async def test_real_approval_positive_contracts(task_session, monkeypatch, kind):
    f = await _fixture(task_session, monkeypatch, legacy=kind == "legacy",
                       provider_backed=kind == "provider-backed")
    if kind == "legacy":
        assert f.snapshot is None
        assert not set(MODERN_MARKERS).intersection(f.run.context_json)
    elif kind == "providerless":
        assert f.capability.provider_release_id is None
        tool = next(x for x in f.catalog.manifest_json["tools"] if x["name"] == "chapter.generate")
        assert tool["provider_id"] is None and tool["provider_version"] is None
    artifact = await _execute(task_session, f)
    assert artifact.id == "integrity-artifact"
    assert len(f.calls) == 1
    assert f.calls[0]["arguments"] == {"chapter_number": 1, "_approval_id": f.approval.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("fk_kind", ["dangling", "empty-string", "other-catalog"])
async def test_providerless_nonnull_fk_missing_row_rejected(task_session, monkeypatch, fk_kind):
    if fk_kind == "other-catalog":
        connection = await task_session.connection()
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        assert (await connection.exec_driver_sql("PRAGMA foreign_keys")).scalar_one() == 1
    f = await _fixture(task_session, monkeypatch)
    if fk_kind == "other-catalog":
        # A valid FK to a genuine second release; the route's catalog predicate
        # excludes it. Its hashes are generated by the canonical release builder.
        raw = deepcopy(registry_module.get_default_tool_registry_snapshot())
        raw["generation"] += 1
        release = build_catalog_release(raw)
        assert release.digest != f.catalog.digest
        assert release.release_id != f.catalog.release_id
        other = await AgentCatalogRepository(task_session).get_or_create_catalog_release(release)
        provider = (await task_session.execute(select(AgentProviderRelease).where(
            AgentProviderRelease.catalog_release_id == other.id))).scalars().first()
        assert provider is not None
        assert provider.catalog_release_id != f.catalog.id
        assert await task_session.get(AgentProviderRelease, provider.id) is provider
        f.capability.provider_release_id = provider.id
    else:
        f.capability.provider_release_id = "missing-provider-row" if fk_kind == "dangling" else ""
    await task_session.commit()
    if fk_kind == "other-catalog":
        connection = await task_session.connection()
        assert (await connection.exec_driver_sql("PRAGMA foreign_keys")).scalar_one() == 1
        assert (await connection.exec_driver_sql("PRAGMA foreign_key_check")).all() == []
    await _rejected(task_session, f, "capability.provider_release_id")


@pytest.mark.asyncio
async def test_providerless_existing_same_catalog_row_rejected(task_session, monkeypatch):
    f = await _fixture(task_session, monkeypatch)
    provider = (await task_session.execute(select(AgentProviderRelease).where(
        AgentProviderRelease.catalog_release_id == f.catalog.id))).scalars().first()
    assert provider is not None
    f.capability.provider_release_id = provider.id
    await task_session.commit()
    await _rejected(task_session, f, "provider.provider_id")


@pytest.mark.asyncio
async def test_provider_required_missing_fk_is_rejected(task_session, monkeypatch):
    f = await _fixture(task_session, monkeypatch, provider_backed=True)
    f.capability.provider_release_id = None
    await task_session.commit()
    await _rejected(task_session, f, "provider_release")


@pytest.mark.asyncio
async def test_provider_row_version_must_match_frozen_tool(task_session, monkeypatch):
    f = await _fixture(task_session, monkeypatch, provider_backed=True)
    f.provider.provider_version = "row-version-drift"
    await task_session.commit()
    await _rejected(task_session, f, "provider.provider_version")


@pytest.mark.asyncio
@pytest.mark.parametrize("manifest_version", ["manifest-version-drift", None])
async def test_provider_row_version_must_match_provider_manifest(task_session, monkeypatch, manifest_version):
    f = await _fixture(task_session, monkeypatch, provider_backed=True,
                       manifest_override=(manifest_version,))
    # Runtime generated the entire catalog, resolver, relational rows and their
    # real digests. Only the persisted row is now changed to match the tool,
    # leaving its version inconsistent with the provider manifest.
    tool = next(x for x in f.catalog.manifest_json["tools"] if x["name"] == "chapter.generate")
    assert f.provider.provider_version == manifest_version
    assert tool["provider_version"] != manifest_version
    f.provider.provider_version = tool["provider_version"]
    await task_session.commit()
    await _rejected(task_session, f, "provider.manifest_provider_version")
