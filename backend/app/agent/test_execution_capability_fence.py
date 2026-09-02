from __future__ import annotations

import pytest

from app.agent.execution import _assert_plan_uses_resolved_capabilities
from app.agent.registry import DEFAULT_TOOL_REGISTRY, RunBoundToolRegistry
from app.agent.executor import build_agent_plan
from app.agent.schemas import AgentPlanRequest
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
