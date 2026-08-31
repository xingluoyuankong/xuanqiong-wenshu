from __future__ import annotations

import pytest

from app.agent.execution import _assert_plan_uses_resolved_capabilities
from app.agent.executor import build_agent_plan
from app.agent.schemas import AgentPlanRequest
from app.services.agent_runtime import AgentConflict


def _plan(tool: str):
    return build_agent_plan(AgentPlanRequest(goal="fence", project_id="project", tools=[tool]), user_id=1)


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
