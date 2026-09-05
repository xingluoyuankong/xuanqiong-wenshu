from __future__ import annotations

import pytest

from app.agent.execution import _assert_plan_uses_resolved_capabilities
from app.agent.registry import DEFAULT_TOOL_REGISTRY, RunBoundToolRegistry
from app.agent.executor import build_agent_plan
from app.agent.schemas import AgentPlanRequest, AgentToolAccess
from app.services.agent_runtime import AgentConflict


def _plan(tool: str):
    return build_agent_plan(AgentPlanRequest(goal="fence", project_id="project", tools=[tool]), user_id=1)


def test_run_bound_registry_enforces_snapshot_names_and_handler_identity():
    handler_identity = DEFAULT_TOOL_REGISTRY.get_handler_identity("project.context")
    bound = RunBoundToolRegistry.from_context(
        DEFAULT_TOOL_REGISTRY,
        {
            "capability_resolution": {"tools": [{"name": "project.context"}]},
            "catalog_release": {
                "tools": [{"name": "project.context", "handler_identity": handler_identity}],
            },
        },
    )

    assert bound.get("project.context").name == "project.context"
    with pytest.raises(Exception, match="outside the Run capability snapshot"):
        bound.get("chapter.inspect")


def test_run_bound_registry_rejects_handler_identity_drift():
    bound = RunBoundToolRegistry.from_context(
        DEFAULT_TOOL_REGISTRY,
        {
            "capability_resolution": {"tools": [{"name": "project.context"}]},
            "catalog_release": {
                "tools": [{"name": "project.context", "handler_identity": "fixture:stale_handler"}],
            },
        },
    )

    with pytest.raises(Exception, match="handler identity differs"):
        bound.get("project.context")


def test_executor_accepts_capability_in_run_resolver_snapshot():
    _assert_plan_uses_resolved_capabilities(
        _plan("project.context"),
        {"capability_resolution": {"tools": [{"name": "project.context"}]}},
    )


def test_executor_rejects_capability_outside_run_resolver_snapshot():
    with pytest.raises(AgentConflict, match="outside the Run resolver snapshot"):
        _assert_plan_uses_resolved_capabilities(
            _plan("chapter.inspect"),
            {"capability_resolution": {"tools": [{"name": "project.context"}]}},
        )


def test_legacy_run_without_resolver_snapshot_keeps_compatibility():
    _assert_plan_uses_resolved_capabilities(_plan("project.context"), {})


def _full_run_context(tool_name: str) -> dict:
    from app.agent.catalog_release import build_catalog_release
    from app.agent.registry import get_default_tool_registry_snapshot

    release = build_catalog_release(get_default_tool_registry_snapshot()).to_dict()
    return {
        "capability_resolution": {"tools": [{"name": tool_name}]},
        "catalog_release": release,
    }


@pytest.mark.parametrize(
    ("tool_name", "update", "expected_field"),
    [
        ("project.context", {"input_schema": {"type": "object", "required": ["unexpected"], "properties": {"unexpected": {"type": "string"}}, "additionalProperties": False}}, "input_schema"),
        ("chapter.version.list", {"context_bindings": ()}, "context_bindings"),
        ("project.context", {"access_level": AgentToolAccess.WRITE}, "access_level"),
    ],
)
def test_run_bound_registry_rejects_frozen_manifest_contract_drift(monkeypatch, tool_name, update, expected_field):
    """Reverse validation: a live manifest cannot change beneath a Run release."""
    context = _full_run_context(tool_name)
    frozen = DEFAULT_TOOL_REGISTRY.get(tool_name)
    monkeypatch.setitem(DEFAULT_TOOL_REGISTRY._tools, tool_name, frozen.model_copy(update=update))

    bound = RunBoundToolRegistry.from_context(DEFAULT_TOOL_REGISTRY, context)
    with pytest.raises(Exception, match=expected_field):
        bound.get(tool_name)


def test_run_bound_registry_rejects_active_provider_version_drift(monkeypatch):
    """Provider identity/version is a live execution fence, not only catalog audit data."""
    import app.agent.registry as registry_module

    context = _full_run_context("project.context")
    current = registry_module.get_default_tool_registry_snapshot()
    changed = {**current, "tools": [dict(item) for item in current["tools"]]}
    tool = next(item for item in changed["tools"] if item["name"] == "project.context")
    tool["provider_version"] = "runtime-drift"
    monkeypatch.setattr(registry_module, "get_default_tool_registry_snapshot", lambda: changed)

    bound = RunBoundToolRegistry.from_context(DEFAULT_TOOL_REGISTRY, context)
    with pytest.raises(Exception, match="provider metadata differs"):
        bound.assert_compatible()


def test_run_bound_registry_rejects_active_generation_drift(monkeypatch):
    """A changed registry generation invalidates every new Run's frozen release."""
    import app.agent.registry as registry_module

    context = _full_run_context("project.context")
    current = registry_module.get_default_tool_registry_snapshot()
    changed = {**current, "generation": int(current["generation"]) + 1}
    monkeypatch.setattr(registry_module, "get_default_tool_registry_snapshot", lambda: changed)

    bound = RunBoundToolRegistry.from_context(DEFAULT_TOOL_REGISTRY, context)
    with pytest.raises(Exception, match="generation differs"):
        bound.assert_compatible()

