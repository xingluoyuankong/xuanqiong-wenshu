from __future__ import annotations

from dataclasses import replace
import json

import pytest

from app.agent.catalog_release import build_catalog_release
from app.agent.capability_resolver import (
    CapabilityResolutionError,
    CapabilityResolutionRequest,
    CapabilityResolver,
    SchemaValidationError,
    resolve_capabilities,
    validate_resolved_arguments,
    validate_tool_arguments,
)
from app.agent.registry import get_default_tool_registry_snapshot


@pytest.fixture()
def release():
    return build_catalog_release(get_default_tool_registry_snapshot())


def test_resolver_filters_by_project_user_and_requested_capability(release):
    resolver = CapabilityResolver(release)
    snapshot = resolver.resolve(
        user_id=42,
        project_id="novel-a",
        requested_capabilities="outline",
        user_allowed_tools=("outline.inspect", "project.context"),
        project_allowed_tools=("outline.inspect", "project.context"),
    )

    assert snapshot.tool_names == ("outline.inspect", "project.context")
    assert snapshot.request.user_id == 42
    assert snapshot.request.project_id == "novel-a"
    assert snapshot.get_tool("outline.inspect").project_scoped is True
    reasons = {item.tool_name: item.reason for item in snapshot.exclusions}
    assert "project.context" not in reasons
    assert reasons["chapter.generate"] == "user_tool_not_allowed"


def test_project_scoped_tools_require_project_context_but_unscoped_tools_can_resolve(release):
    snapshot = CapabilityResolver(release).resolve(user_id="user-1")

    assert snapshot.tool_names == ("project.list",)
    assert all(item.reason == "project_context_required" for item in snapshot.exclusions if item.tool_name != "project.list")


def test_requested_provider_tag_and_tool_name_are_matchable(release):
    resolver = CapabilityResolver(release)
    by_tag = resolver.resolve(user_id=1, project_id="p", requested_capabilities="graph")
    by_provider = resolver.resolve(user_id=1, project_id="p", requested_capabilities="memory-read")
    by_name = resolver.resolve(user_id=1, project_id="p", requested_capabilities="knowledge.inspect")

    assert by_tag.tool_names == ("knowledge.inspect",)
    assert by_provider.tool_names == by_tag.tool_names
    assert by_name.tool_names == by_tag.tool_names


def test_unavailable_provider_is_excluded_and_reason_is_serialized(release):
    broken_provider = replace(
        next(item for item in release.providers if item.provider_id == "memory-read"),
        status="failed",
        failure_code="provider_down",
    )
    broken_release = replace(
        release,
        providers=tuple(broken_provider if item.provider_id == "memory-read" else item for item in release.providers),
    )
    snapshot = CapabilityResolver(broken_release).resolve(
        user_id=1,
        project_id="p",
        requested_capabilities="knowledge.inspect",
    )

    assert snapshot.tools == ()
    target_exclusion = next(item for item in snapshot.exclusions if item.tool_name == "knowledge.inspect")
    assert target_exclusion.reason == "provider_unavailable"
    serialized = json.loads(json.dumps(snapshot.to_dict(), sort_keys=True))
    assert next(item for item in serialized["exclusions"] if item["tool_name"] == "knowledge.inspect")["reason"] == "provider_unavailable"


def test_optional_risk_and_confirmation_filters_do_not_erase_metadata(release):
    snapshot = CapabilityResolver(release).resolve(
        user_id=1,
        project_id="p",
        allowed_risk_levels=("read", "suggest"),
        include_confirmation_required=False,
    )

    assert all(tool.risk_level in {"read", "suggest"} for tool in snapshot.tools)
    assert all(not tool.requires_confirmation for tool in snapshot.tools)
    assert release.get_tool("chapter.generate").risk_level == "write"
    assert release.get_tool("chapter.generate").requires_confirmation is True
    assert any(item.reason == "risk_level_not_allowed" for item in snapshot.exclusions)


def test_resolver_snapshot_is_stable_and_deeply_serializable(release):
    request = CapabilityResolutionRequest(user_id=7, project_id="p", requested_capabilities=("outline", "graph"))
    first = CapabilityResolver(release).resolve(request)
    second = CapabilityResolver(release).resolve(request)

    assert first.digest == second.digest
    assert first.snapshot_id == second.snapshot_id
    assert first.tool_names == (
        "chapter.version.list",
        "entity.inspect",
        "knowledge.inspect",
        "outline.inspect",
        "project.context",
        "project.list",
        "research.inspect",
        "statistics.project",
    )
    encoded = json.dumps(first.to_dict(), ensure_ascii=False, sort_keys=True)
    assert json.loads(encoded)["digest"] == first.digest
    assert first.request.requested_capabilities == ("graph", "outline")


def test_request_can_be_used_through_functional_wrapper(release):
    snapshot = resolve_capabilities(
        release,
        user_id=9,
        project_id="p",
        requested_capabilities="statistics.project",
    )
    assert snapshot.tool_names == ("statistics.project",)


def test_schema_validation_uses_released_schema_for_valid_and_invalid_payloads(release):
    tool = release.get_tool("chapter.version.diff")
    validate_tool_arguments(
        tool,
        {"chapter_number": 3, "from_version_id": 10, "to_version_id": 11},
    )
    with pytest.raises(SchemaValidationError, match="missing required"):
        validate_tool_arguments(tool, {"chapter_number": 3, "from_version_id": 10})
    with pytest.raises(SchemaValidationError, match="unknown field"):
        validate_tool_arguments(tool, {"chapter_number": 3, "from_version_id": 10, "to_version_id": 11, "extra": 1})
    with pytest.raises(SchemaValidationError, match="expected integer"):
        validate_tool_arguments(tool, {"chapter_number": "3", "from_version_id": 10, "to_version_id": 11})


def test_schema_validation_is_bound_to_resolved_snapshot(release):
    snapshot = CapabilityResolver(release).resolve(
        user_id=1,
        project_id="p",
        requested_capabilities="chapter.version.diff",
    )
    validate_resolved_arguments(
        snapshot,
        "chapter.version.diff",
        {"chapter_number": 1, "from_version_id": 2, "to_version_id": 3},
    )
    with pytest.raises(KeyError, match="not resolved"):
        validate_resolved_arguments(snapshot, "chapter.generate", {})


def test_request_and_resolver_reject_ambiguous_or_invalid_inputs(release):
    with pytest.raises(CapabilityResolutionError, match="user_id is required"):
        CapabilityResolver(release).resolve(project_id="p")
    with pytest.raises(CapabilityResolutionError, match="either request"):
        CapabilityResolver(release).resolve(
            CapabilityResolutionRequest(user_id=1, project_id="p"),
            user_id=2,
        )
    with pytest.raises(CapabilityResolutionError, match="empty"):
        CapabilityResolutionRequest(user_id=1, project_id="p", requested_capabilities=("",))

