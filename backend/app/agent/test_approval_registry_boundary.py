from __future__ import annotations

from copy import deepcopy
from functools import wraps
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

import app.agent.registry as registry_module
from app.agent.registry import DEFAULT_TOOL_REGISTRY, ToolContractViolation
from app.agent.test_approval_run_contract import _route_fixture
from app.api.routers import agent as agent_router
from app.models.agent_catalog import AgentCapabilityExecution


def leaf_handler(monkeypatch, calls):
    # Preserve real registry, manifest, handler identity, access checks and output validation.
    original = DEFAULT_TOOL_REGISTRY.get_handler
    @wraps(original("chapter.generate"))
    async def sentinel(**kwargs):
        calls.append(kwargs)
        return {"artifact": SimpleNamespace(id="bound-route-artifact")}
    monkeypatch.setattr(DEFAULT_TOOL_REGISTRY, "get_handler", lambda name: sentinel if name == "chapter.generate" else original(name))


@pytest.mark.asyncio
async def test_approval_route_real_registry_normal_contract_reaches_leaf(task_session, monkeypatch):
    user, run, step, approval = await _route_fixture(task_session, requested_tools=["chapter.generate", "project.context"])
    calls = []
    leaf_handler(monkeypatch, calls)
    artifact = await agent_router._execute_registered_approval(approval_id=approval.id, session=task_session, user_id=user.id)
    assert artifact.id == "bound-route-artifact"
    assert len(calls) == 1
    assert calls[0]["arguments"]["_approval_id"] == approval.id


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["generation", "context_bindings", "output_schema", "allowed_project_roles", "provider_version"])
async def test_approval_route_run_bound_drift_stops_real_registry_leaf(task_session, monkeypatch, drift):
    user, run, step, approval = await _route_fixture(task_session, requested_tools=["chapter.generate", "project.context"])
    calls = []
    leaf_handler(monkeypatch, calls)
    if drift in ("generation", "provider_version"):
        changed = deepcopy(registry_module.get_default_tool_registry_snapshot())
        if drift == "generation":
            changed["generation"] += 1
        else:
            # project.context is genuinely provider-backed and belongs to this Run's resolved read set.
            tool = next(tool for tool in changed["tools"] if tool["name"] == "project.context")
            assert tool["provider_id"]
            assert any(tool["name"] == "project.context" for tool in run.context_json["capability_resolution"]["tools"])
            tool["provider_version"] = "changed-after-approval"
        monkeypatch.setattr(registry_module, "get_default_tool_registry_snapshot", lambda: changed)
    else:
        updates = {
            "context_bindings": {"context_bindings": ()},
            "output_schema": {"output_schema": {"type": "object", "properties": {"artifact": {}}, "additionalProperties": False}},
            "allowed_project_roles": {"allowed_project_roles": ("owner", "admin")},
        }
        original = DEFAULT_TOOL_REGISTRY.get("chapter.generate")
        monkeypatch.setitem(DEFAULT_TOOL_REGISTRY._tools, "chapter.generate", original.model_copy(update=updates[drift]))
    before = await task_session.scalar(select(func.count()).select_from(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id == run.id))
    with pytest.raises(ToolContractViolation, match="differs"):
        await agent_router._execute_registered_approval(approval_id=approval.id, session=task_session, user_id=user.id)
    after = await task_session.scalar(select(func.count()).select_from(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id == run.id))
    assert calls == []
    assert before == after == 0


@pytest.mark.asyncio
async def test_bound_registry_rechecks_generation_at_execute_boundary(task_session, monkeypatch):
    user, run, step, approval = await _route_fixture(task_session, requested_tools=["chapter.generate", "project.context"])
    bound = registry_module.bind_run_tool_registry(DEFAULT_TOOL_REGISTRY, run.context_json)
    calls = []
    leaf_handler(monkeypatch, calls)
    changed = deepcopy(registry_module.get_default_tool_registry_snapshot())
    changed["generation"] += 1
    monkeypatch.setattr(registry_module, "get_default_tool_registry_snapshot", lambda: changed)
    with pytest.raises(ToolContractViolation, match="generation differs"):
        await bound.execute("chapter.generate", session=task_session, user_id=user.id, project_id=run.project_id, arguments={"chapter_number": 1, "_approval_id": approval.id})
    assert calls == []
