from __future__ import annotations

import asyncio

import pytest

from app.agent.catalog_release import ToolRelease
from app.agent.policy import requires_confirmation
from app.agent.registry import DEFAULT_TOOL_REGISTRY, AgentToolRegistry, ToolContractViolation, build_tool_manifest, get_default_tool_registry_snapshot
from app.agent.schemas import AgentRiskLevel, AgentToolAccess, AgentToolCatalogItem, ToolManifest


def _manifest(**overrides) -> ToolManifest:
    values = {
        "name": "contract.read",
        "description": "contract test tool",
        "risk_level": AgentRiskLevel.READ,
        "requires_confirmation": False,
        "project_scoped": True,
        "input_schema": {"type": "object", "additionalProperties": False},
        "output_schema": {"type": "object"},
    }
    values.update(overrides)
    return ToolManifest(**values)


def test_manifest_derives_project_permission_metadata_from_risk():
    read = _manifest(name="read", risk_level=AgentRiskLevel.READ)
    suggest = _manifest(name="suggest", risk_level=AgentRiskLevel.SUGGEST)
    write = _manifest(
        name="write",
        risk_level=AgentRiskLevel.WRITE,
        requires_confirmation=True,
        idempotency_key="agent:write",
        idempotency_policy="required",
    )
    manage = _manifest(
        name="manage",
        risk_level=AgentRiskLevel.MANAGE,
        requires_confirmation=True,
        idempotency_key="agent:manage",
        idempotency_policy="required",
    )

    assert read.access_level is AgentToolAccess.READ
    assert suggest.access_level is AgentToolAccess.READ
    assert write.access_level is AgentToolAccess.WRITE
    assert manage.access_level is AgentToolAccess.MANAGE
    assert read.allowed_project_roles == ("viewer", "editor", "owner", "admin")
    assert write.allowed_project_roles == ("editor", "owner", "admin")
    assert manage.allowed_project_roles == ("owner", "admin")


def test_manifest_rejects_risk_permission_and_confirmation_drift():
    with pytest.raises(ValueError, match="access_level"):
        _manifest(
            access_level=AgentToolAccess.WRITE,
        )
    with pytest.raises(ValueError, match="requires_confirmation"):
        _manifest(requires_confirmation=True)
    with pytest.raises(ValueError, match="allowed_project_roles"):
        _manifest(allowed_project_roles=("viewer",))


def test_manifest_rejects_invalid_idempotency_and_cancellation_combinations():
    with pytest.raises(ValueError, match="idempotency_key"):
        _manifest(
            risk_level=AgentRiskLevel.WRITE,
            requires_confirmation=True,
            idempotency_policy="required",
        )
    with pytest.raises(ValueError, match="not_applicable"):
        _manifest(idempotency_key="unexpected", idempotency_policy="not_applicable")
    with pytest.raises(ValueError, match="supports_stream"):
        _manifest(supports_stream=True, cancellation_policy="not_supported")


def test_manage_confirmation_policy_matches_manifest_contract():
    assert requires_confirmation(AgentRiskLevel.MANAGE) is True


def test_registry_enforces_declared_schema_string_bounds():
    async def handler(**kwargs):
        return {}

    registry = AgentToolRegistry()
    registry.register(
        build_tool_manifest(
            "registry.bounds",
            "registry bounds",
            AgentRiskLevel.READ,
            project_scoped=False,
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {
                    "value": {"type": "string", "minLength": 3, "maxLength": 4},
                },
                "additionalProperties": False,
            },
        ),
        handler=handler,
    )

    with pytest.raises(ToolContractViolation, match="minLength"):
        registry.validate_planned_input("registry.bounds", {"value": "ab"})
    with pytest.raises(ToolContractViolation, match="maxLength"):
        registry.validate_planned_input("registry.bounds", {"value": "abcde"})

def test_build_manifest_does_not_silently_replace_zero_timeout():
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_tool_manifest(
            "timeout.zero",
            "invalid timeout",
            AgentRiskLevel.READ,
            project_scoped=False,
            timeout_seconds=0,
        )


def test_registry_exposes_permission_metadata_and_validates_handler_contract():
    async def handler(**kwargs):
        return {}

    registry = AgentToolRegistry()
    registry.register(
        build_tool_manifest(
            "registry.read",
            "registry read",
            AgentRiskLevel.READ,
            project_scoped=False,
        ),
        handler=handler,
    )
    manifest = registry.get("registry.read")
    assert manifest.access_level is AgentToolAccess.READ
    assert manifest.allowed_project_roles == ()
    assert registry.get_handler("registry.read") is handler


@pytest.mark.asyncio
async def test_registry_timeout_and_cancel_contracts_remain_enforced():
    async def slow_handler(**kwargs):
        await asyncio.sleep(1)
        return {}

    registry = AgentToolRegistry()
    registry.register(
        build_tool_manifest(
            "registry.timeout",
            "registry timeout",
            AgentRiskLevel.READ,
            project_scoped=False,
            timeout_seconds=1,
        ),
        handler=slow_handler,
    )
    with pytest.raises(ToolContractViolation):
        await registry.execute(
            "registry.timeout",
            session=None,
            user_id=1,
            project_id=None,
        )



def test_confirmation_policy_and_run_snapshot_keep_manage_semantics_centralized():
    assert requires_confirmation(AgentRiskLevel.MANAGE) is True
    snapshot = get_default_tool_registry_snapshot()
    chapter_generate = next(item for item in snapshot["tools"] if item["name"] == "chapter.generate")
    assert chapter_generate["access_level"] == "write"
    assert chapter_generate["allowed_project_roles"] == ["editor", "owner", "admin"]


def test_catalog_item_rejects_permission_metadata_drift():
    with pytest.raises(ValueError, match="access_level"):
        AgentToolCatalogItem(
            name="catalog.bad",
            description="catalog contract test",
            risk_level=AgentRiskLevel.WRITE,
            requires_confirmation=True,
            project_scoped=True,
            access_level=AgentToolAccess.READ,
            allowed_project_roles=("viewer",),
            source="legacy",
        )


def test_catalog_release_preserves_ui005_metadata_and_derives_legacy_defaults():
    manifest = build_tool_manifest("release.manage", "release contract test", AgentRiskLevel.MANAGE)
    current = ToolRelease.from_contract(manifest.model_dump(mode="json"))
    assert current.access_level == "manage"
    assert current.allowed_project_roles == ("owner", "admin")
    assert current.to_dict()["access_level"] == "manage"
    assert current.to_dict()["allowed_project_roles"] == ["owner", "admin"]

    legacy_contract = manifest.model_dump(mode="json")
    legacy_contract.pop("access_level")
    legacy_contract.pop("allowed_project_roles")
    legacy = ToolRelease.from_contract(legacy_contract)
    assert legacy.access_level == "manage"
    assert legacy.allowed_project_roles == ("owner", "admin")


def test_chapter_version_accept_manifest_allows_audit_actor_identity():
    DEFAULT_TOOL_REGISTRY.validate_planned_input(
        "chapter.version.accept",
        {"_approval_id": "approval-1", "artifact_id": "artifact-1", "actor_user_id": 1},
    )
