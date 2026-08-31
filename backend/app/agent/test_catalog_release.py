from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.agent.catalog_release import (
    CATALOG_RELEASE_ID,
    CatalogReleaseError,
    build_catalog_release,
)
from app.agent.registry import DEFAULT_TOOL_REGISTRY, get_default_tool_registry_snapshot
from app.agent.schemas import AgentRiskLevel, ToolManifest


def _custom_registry(description: str = "demo"):
    tool = ToolManifest(
        name="demo.inspect",
        description=description,
        input_schema={
            "type": "object",
            "required": ["chapter_number"],
            "properties": {"chapter_number": {"type": "integer"}},
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        risk_level=AgentRiskLevel.READ,
        requires_confirmation=False,
        project_scoped=True,
        supports_stream=False,
        idempotency_key="demo:inspect",
        manifest_version="2.0",
        timeout_seconds=45,
        cancellation_policy="cooperative",
        idempotency_policy="safe_read",
        audit_event_type="demo_tool_call",
    )
    from app.agent.registry import AgentToolRegistry

    return AgentToolRegistry([tool])


def _custom_snapshot(description: str = "demo", *, generation: int = 4):
    return {
        "generation": generation,
        "providers": [],
        "tools": [
            {
                "name": "demo.inspect",
                "risk_level": "read",
                "manifest_version": "2.0",
                "supports_stream": False,
                "provider_id": None,
                "provider_version": None,
                "source": "legacy",
            }
        ],
    }, _custom_registry(description)


def test_default_registry_snapshot_becomes_content_addressed_release():
    release = build_catalog_release(get_default_tool_registry_snapshot())

    assert release.catalog_id == CATALOG_RELEASE_ID
    assert release.generation == get_default_tool_registry_snapshot()["generation"]
    assert len(release.tools) == 19
    assert len(release.providers) == 4
    assert release.release_id.endswith(release.digest[:16])
    assert release.get_tool("chapter.generate").risk_level == "write"
    assert release.get_tool("chapter.generate").requires_confirmation is True
    assert release.get_tool("chapter.generate").project_scoped is True
    assert release.get_tool("chapter.generate").input_schema["required"] == ("_approval_id", "chapter_number")


def test_release_is_deeply_immutable_and_serializes_as_plain_json():
    release = build_catalog_release(get_default_tool_registry_snapshot())
    before = release.digest
    serialized = release.to_dict()
    serialized["tools"][0]["input_schema"]["type"] = "tampered"
    serialized["providers"].clear()

    assert release.digest == before
    assert len(release.providers) == 4
    with pytest.raises(TypeError):
        release.get_tool("chapter.version.diff").input_schema["type"] = "array"
    encoded = json.dumps(release.to_dict(), ensure_ascii=False, sort_keys=True)
    assert json.loads(encoded)["digest"] == before


def test_same_snapshot_has_stable_release_digest_and_json():
    snapshot = get_default_tool_registry_snapshot()
    first = build_catalog_release(snapshot)
    second = build_catalog_release(deepcopy(snapshot))

    assert first.digest == second.digest
    assert first.release_id == second.release_id
    assert first.canonical_json() == second.canonical_json()


def test_manifest_change_changes_digest_without_touching_live_registry():
    first_snapshot, first_registry = _custom_snapshot("demo")
    second_snapshot, second_registry = _custom_snapshot("demo changed")

    first = build_catalog_release(first_snapshot, registry=first_registry)
    second = build_catalog_release(second_snapshot, registry=second_registry)

    assert first.digest != second.digest
    assert first.get_tool("demo.inspect").description == "demo"
    assert second.get_tool("demo.inspect").description == "demo changed"


def test_snapshot_validation_rejects_generation_and_tool_contract_drift():
    snapshot = get_default_tool_registry_snapshot()
    invalid_generation = {**snapshot, "generation": 0}
    with pytest.raises(CatalogReleaseError, match="generation"):
        build_catalog_release(invalid_generation)

    invalid_tools = {**snapshot, "tools": [*snapshot["tools"], snapshot["tools"][0]]}
    with pytest.raises(CatalogReleaseError, match="duplicate"):
        build_catalog_release(invalid_tools)

    drifted_tools = {**snapshot, "tools": snapshot["tools"][:-1]}
    with pytest.raises(CatalogReleaseError, match="mismatch"):
        build_catalog_release(drifted_tools)


def test_release_uses_snapshot_provider_metadata_and_omits_runtime_path():
    release = build_catalog_release(get_default_tool_registry_snapshot())
    provider = next(item for item in release.providers if item.provider_id == "project-read")
    tool = release.get_tool("project.context")

    assert provider.status == "loaded"
    assert "project-context" in provider.capability_tags
    assert tool.provider_id == "project-read"
    assert tool.provider_version == "1.0.0"
    assert tool.source == "builtin"
    assert all("path" not in item for item in release.to_dict()["providers"])
    assert DEFAULT_TOOL_REGISTRY.get("project.context").name == "project.context"
