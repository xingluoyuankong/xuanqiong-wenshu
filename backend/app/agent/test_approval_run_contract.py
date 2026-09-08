from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select
from unittest.mock import AsyncMock

import pytest

from app.agent.execution import ApprovalRunContractError, validate_approval_run_contract
from app.api.routers import agent as agent_router
from app.models.agent_catalog import AgentCapabilityExecution, AgentCatalogRelease, AgentProviderRelease, AgentRunCapabilitySnapshot
from app.services.agent_execution_service import AgentExecutionService
from app.services.agent_runtime import AgentRuntimeService


def _fixture(**overrides):
    context = {
        "relational_capability_snapshot_id": "snap-row",
        "relational_capability_snapshot_key": "snap-key",
        "relational_capability_snapshot_digest": "snapshot-digest",
        "relational_catalog_release_id": "catalog-row",
        "catalog_release": {
            "release_id": "release-1",
            "generation": 7,
            "digest": "release-digest",
            "schema_version": 3,
            "providers": [{"provider_id": "builtin", "provider_version": "1.2", "status": "loaded", "tools": ["chapter.generate"]}],
            "tools": [{"name": "chapter.generate", "handler_identity": "handler:v1", "provider_id": "builtin", "provider_version": "1.2", "input_schema": {"type": "object"}, "context_bindings": [{"source": "selected_chapter_number", "argument_name": "chapter_number"}]}],
        },
        "capability_resolution": {
            "resolver_schema_version": 3,
            "schema_version": 3,
            "generation": 7,
            "release_digest": "release-digest",
            "release_id": "release-1",
            "snapshot_id": "resolver-v3:abc",
            "tools": [{"name": "chapter.generate", "handler_identity": "handler:v1", "provider_id": "builtin", "schema": {"type": "object"}, "context_bindings": [{"source": "selected_chapter_number", "argument_name": "chapter_number"}]}],
        },
        "context_bindings": {"selected_chapter_number": 12},
    }
    run = SimpleNamespace(id="run-1", session_id="session-1", correlation_id="corr-1", transaction_id="txn-1", user_id=11, project_id="project-1", context_json=context, lease_generation=4)
    step = SimpleNamespace(id="step-1", run_id="run-1", user_id=11, project_id="project-1", tool_name="chapter.generate", lease_generation=4)
    approval = SimpleNamespace(id="approval-1", run_id="run-1", correlation_id="corr-1", transaction_id="txn-1", step_id="step-1", user_id=11, project_id="project-1", tool_name="chapter.generate", request_json={"chapter_number": 12})
    snapshot = SimpleNamespace(id="snap-row", snapshot_id="snap-key", run_id="run-1", user_id=11, project_id="project-1", generation=7, resolver_schema_version=3, release_digest="release-digest", digest="snapshot-digest", catalog_release_id="catalog-row", selected_capability_ids_json=["chapter.generate"], resolved_scope_json={"resolver_snapshot_id": "resolver-v3:abc"})
    catalog_release = SimpleNamespace(id="catalog-row", release_id="release-1", schema_version=3, generation=7, digest="release-digest", manifest_json=context["catalog_release"])
    provider_release = SimpleNamespace(id="provider-row", catalog_release_id="catalog-row", provider_id="builtin", provider_version="1.2", status="loaded", tools_json=["chapter.generate"])
    capability = SimpleNamespace(capability_id="chapter.generate", provider_release_id="provider-row", version="1.0", input_schema_json={"type": "object"}, schema_json={"type": "object"}, context_bindings_json=[{"source": "selected_chapter_number", "argument_name": "chapter_number"}], handler_identity="handler:v1")
    return SimpleNamespace(run=run, step=step, approval=approval, snapshot=snapshot, capability=capability, provider_release=provider_release, catalog_release=catalog_release, **overrides)


@pytest.mark.asyncio
async def test_relationship_run_contract_rejects_drift_before_any_execution():
    f = _fixture()
    f.snapshot.release_digest = "tampered"
    registry = SimpleNamespace(execute=AsyncMock(), get_handler_identity=lambda name: "handler:v1", get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()))

    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(session=SimpleNamespace(), registry=registry, **vars(f))

    assert exc.value.code == "run_contract_mismatch"
    registry.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["generation", "resolver_schema_version", "digest"])
async def test_each_snapshot_identity_field_is_checked(field):
    f = _fixture()
    setattr(f.snapshot, field, getattr(f.snapshot, field) + 1 if field != "digest" else "other")
    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(session=SimpleNamespace(), registry=SimpleNamespace(get_handler_identity=lambda name: "handler:v1", get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=())), **vars(f))
    assert exc.value.code == "run_contract_mismatch"


@pytest.mark.asyncio
async def test_relationship_run_requires_step_run_user_project_and_context_binding_match():
    for field in ("run_id", "user_id", "tool_name"):
        f = _fixture()
        setattr(f.step, field, "drifted" if field != "user_id" else 999999)
        with pytest.raises(ApprovalRunContractError):
            await validate_approval_run_contract(
                session=SimpleNamespace(),
                registry=SimpleNamespace(
                    get_handler_identity=lambda name: "handler:v1",
                    get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
                ),
                **vars(f),
            )

    f = _fixture()
    f.approval.request_json = {"chapter_number": 99}
    with pytest.raises(ApprovalRunContractError):
        await validate_approval_run_contract(session=SimpleNamespace(), registry=SimpleNamespace(get_handler_identity=lambda name: "handler:v1", get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=())), **vars(f))


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["provider_id", "provider_version", "catalog_release_id"])
async def test_provider_relation_drift_is_rejected(mutation):
    f = _fixture()
    setattr(f.provider_release, mutation, "drifted")
    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(
            registry=SimpleNamespace(
                get_handler_identity=lambda name: "handler:v1",
                get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
            ),
            **vars(f),
        )
    assert exc.value.field in {f"provider.{mutation}", "provider"}


@pytest.mark.asyncio
async def test_missing_provider_relation_is_rejected():
    f = _fixture()
    f.provider_release = None
    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(
            registry=SimpleNamespace(
                get_handler_identity=lambda name: "handler:v1",
                get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
            ),
            **vars(f),
        )
    assert exc.value.field == "provider_release"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["catalog_release", "capability_resolution", "relational_capability_snapshot_digest"])
async def test_relationship_run_rejects_missing_contract_fields(missing):
    f = _fixture()
    f.run.context_json.pop(missing)
    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(
            registry=SimpleNamespace(
                get_handler_identity=lambda name: "handler:v1",
                get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
            ),
            **vars(f),
        )
    assert exc.value.code == "run_contract_mismatch"


@pytest.mark.asyncio
async def test_relationship_run_rejects_missing_binding_and_invalid_approval_parameter():
    f = _fixture()
    f.run.context_json["context_bindings"].pop("selected_chapter_number")
    result = await validate_approval_run_contract(
        registry=SimpleNamespace(
            get_handler_identity=lambda name: "handler:v1",
            get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
        ),
        **vars(f),
    )
    assert result is f.snapshot
    f = _fixture()
    f.approval.request_json = {}
    with pytest.raises(ApprovalRunContractError):
        await validate_approval_run_contract(
            registry=SimpleNamespace(
                get_handler_identity=lambda name: "handler:v1",
                get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
            ),
            **vars(f),
        )

@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["id", "release_id", "schema_version", "generation", "digest", "manifest_json"])
async def test_catalog_release_row_drift_is_rejected(field):
    f = _fixture()
    setattr(f.catalog_release, field, {"drift": True} if field == "manifest_json" else "drifted")
    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(
            registry=SimpleNamespace(
                get_handler_identity=lambda name: "handler:v1",
                get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
            ),
            **vars(f),
        )
    assert exc.value.code == "run_contract_mismatch"


@pytest.mark.asyncio
async def test_missing_catalog_release_row_is_rejected_for_relationship_run():
    f = _fixture()
    f.catalog_release = None
    with pytest.raises(ApprovalRunContractError) as exc:
        await validate_approval_run_contract(
            registry=SimpleNamespace(
                get_handler_identity=lambda name: "handler:v1",
                get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=()),
            ),
            **vars(f),
        )
    assert exc.value.field == "catalog_release_row"


@pytest.mark.asyncio
async def test_legacy_run_without_relationship_snapshot_remains_compatible():
    f = _fixture()
    f.run.context_json = {"goal": "legacy"}
    f.snapshot = None
    result = await validate_approval_run_contract(session=SimpleNamespace(), registry=SimpleNamespace(get_handler_identity=lambda name: "handler:v1", get=lambda name: SimpleNamespace(input_schema={"type": "object"}, context_bindings=())), **vars(f))
    assert result is None


async def _route_fixture(session, *, requested_tools=None):
    from app.models.user import User
    from app.models.novel import NovelProject

    user = User(
        username="ui005-route-owner",
        email="ui005-route-owner@example.com",
        hashed_password="fixture-password",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    project = NovelProject(
        id="ui005-route-project",
        user_id=user.id,
        title="UI005 route contract",
    )
    session.add(project)
    await session.flush()
    runtime = AgentRuntimeService(session)
    agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
    run = await runtime.create_run(
        session_id=agent_session.id,
        user_id=user.id,
        project_id=project.id,
        context={"requested_tools": requested_tools or ["chapter.generate"]},
    )
    facts = AgentExecutionService(session)
    snapshot = await facts.get_run_snapshot(run.id)
    capability = await facts.repository.get_capability_for_snapshot(
        snapshot=snapshot,
        capability_id="chapter.generate",
    )
    catalog = (
        await session.execute(
            select(AgentCatalogRelease).where(AgentCatalogRelease.id == snapshot.catalog_release_id)
        )
    ).scalar_one()
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=user.id,
        step_order=1,
        tool_name="chapter.generate",
        idempotency_key=f"{run.id}:ui005-route",
        input_payload={"chapter_number": 1},
    )
    step.status = "awaiting_approval"
    await session.commit()
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=user.id,
        step_id=step.id,
        tool_name="chapter.generate",
        project_id=project.id,
        arguments={"chapter_number": 1},
    )
    await runtime.decide_approval(
        approval_id=approval.id,
        user_id=user.id,
        approved=True,
        reason="route fixture",
    )
    await session.refresh(run)
    persisted_catalog = (
        await session.execute(
            select(AgentCatalogRelease).where(AgentCatalogRelease.id == snapshot.catalog_release_id)
        )
    ).scalar_one()
    assert run.context_json["catalog_release"] == persisted_catalog.manifest_json
    return user, run, step, approval


@pytest.mark.asyncio
async def test_router_approval_relationship_path_enters_registry_without_execution_fact_side_effect(
    task_session,
    monkeypatch,
):
    user, run, step, approval = await _route_fixture(task_session)
    facts = AgentExecutionService(task_session)
    snapshot = await facts.get_run_snapshot(run.id)
    capability = await facts.repository.get_capability_for_snapshot(
        snapshot=snapshot,
        capability_id=approval.tool_name,
    )
    catalog = (
        await task_session.execute(
            select(AgentCatalogRelease).where(AgentCatalogRelease.id == snapshot.catalog_release_id)
        )
    ).scalar_one()
    calls = []

    # Keep the real registry/Run-bound checks; replace only the expensive leaf.
    from functools import wraps
    original_get_handler = agent_router.DEFAULT_TOOL_REGISTRY.get_handler

    @wraps(original_get_handler(approval.tool_name))
    async def leaf_handler(**kwargs):
        calls.append((approval.tool_name, kwargs))
        return {"artifact": SimpleNamespace(id="route-artifact")}

    monkeypatch.setattr(
        agent_router.DEFAULT_TOOL_REGISTRY,
        "get_handler",
        lambda name: leaf_handler if name == approval.tool_name else original_get_handler(name),
    )
    monkeypatch.setattr(agent_router.AgentArtifactRead, "model_validate", staticmethod(lambda value: value))
    before = await task_session.scalar(
        select(func.count()).select_from(AgentCapabilityExecution).where(
            AgentCapabilityExecution.run_id == run.id
        )
    )
    result = await agent_router._execute_registered_approval(
        approval_id=approval.id,
        session=task_session,
        user_id=user.id,
    )
    after = await task_session.scalar(
        select(func.count()).select_from(AgentCapabilityExecution).where(
            AgentCapabilityExecution.run_id == run.id
        )
    )
    assert result.id == "route-artifact"
    assert calls and calls[0][0] == approval.tool_name
    assert before == after == 0
    assert catalog.id == snapshot.catalog_release_id


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["catalog", "snapshot"])
async def test_router_approval_relationship_drift_fails_before_handler_and_execution_fact(
    task_session,
    monkeypatch,
    mutation,
):
    user, run, step, approval = await _route_fixture(task_session)
    facts = AgentExecutionService(task_session)
    snapshot = await facts.get_run_snapshot(run.id)
    capability = await facts.repository.get_capability_for_snapshot(
        snapshot=snapshot,
        capability_id=approval.tool_name,
    )
    catalog = (
        await task_session.execute(
            select(AgentCatalogRelease).where(AgentCatalogRelease.id == snapshot.catalog_release_id)
        )
    ).scalar_one()
    if mutation == "catalog":
        catalog.digest = "f" * 64
    else:
        snapshot.digest = "e" * 64
    await task_session.commit()
    calls = []

    class RegistryStub:
        def get_handler_identity(self, name):
            return capability.handler_identity

        def get(self, name):
            return SimpleNamespace(input_schema=capability.input_schema_json)

        async def execute(self, name, **kwargs):
            calls.append(name)
            return {"artifact": SimpleNamespace(id="should-not-exist")}

    monkeypatch.setattr(agent_router, "DEFAULT_TOOL_REGISTRY", RegistryStub())
    before = await task_session.scalar(
        select(func.count()).select_from(AgentCapabilityExecution).where(
            AgentCapabilityExecution.run_id == run.id
        )
    )
    with pytest.raises(ApprovalRunContractError):
        await agent_router._execute_registered_approval(
            approval_id=approval.id,
            session=task_session,
            user_id=user.id,
        )
    after = await task_session.scalar(
        select(func.count()).select_from(AgentCapabilityExecution).where(
            AgentCapabilityExecution.run_id == run.id
        )
    )
    assert calls == []
    assert before == after == 0
