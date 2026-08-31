from types import SimpleNamespace

import pytest
import httpx
from fastapi import FastAPI, HTTPException

from app.agent.executor import UnknownAgentTool, build_agent_plan
from app.agent.policy import ProjectScopeViolation, requires_confirmation, validate_project_scope
from app.agent.registry import AgentToolRegistry, DEFAULT_TOOL_REGISTRY
from app.agent.schemas import AgentPlanRequest, AgentRiskLevel, AgentToolDefinition
from app.api.routers.agent import list_agent_tool_health, list_agent_tools, router
from app.core.dependencies import get_current_admin, get_current_user


def _app_with_user(user=SimpleNamespace(id=42, username="agent-user")):
    app = FastAPI()
    app.include_router(router)

    async def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user
    return app


def test_registry_and_confirmation_policy_are_complete():
    tools = DEFAULT_TOOL_REGISTRY.list_tools()
    assert {tool.risk_level for tool in tools} == {AgentRiskLevel.READ, AgentRiskLevel.SUGGEST, AgentRiskLevel.WRITE}
    assert all(tool.requires_confirmation == requires_confirmation(tool.risk_level) for tool in tools)
    tool = AgentToolDefinition(name="test.tool", description="测试", risk_level=AgentRiskLevel.WRITE, requires_confirmation=True)
    registry = AgentToolRegistry([tool])
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(tool)
    with pytest.raises(ValueError, match="confirmation policy"):
        AgentToolRegistry([tool.model_copy(update={"name": "bad.tool", "requires_confirmation": False})])


def test_project_scope_policy_has_negative_regressions():
    with pytest.raises(ProjectScopeViolation):
        validate_project_scope(None)
    with pytest.raises(ProjectScopeViolation):
        validate_project_scope("project-a", "project-b")
    assert validate_project_scope("project-a", "project-a") is True
    assert validate_project_scope(None, project_scoped=False) is True


def test_plan_is_structured_and_never_calls_provider():
    plan = build_agent_plan(AgentPlanRequest(goal="整理", project_id="project-a", tools=["project.context", "quality.inspect"]), user_id=7)
    assert plan.created_by_user_id == 7
    assert [step.tool_name for step in plan.steps] == ["project.context", "quality.inspect"]
    assert plan.provider_called is False
    assert plan.events[0].event_type == "plan_created"
    assert all("thought" not in event.data for event in plan.events)
    with pytest.raises(UnknownAgentTool):
        build_agent_plan(AgentPlanRequest(goal="x", tools=["not.registered"]), user_id=1)
    with pytest.raises(ProjectScopeViolation):
        build_agent_plan(AgentPlanRequest(goal="x", tools=["chapter.inspect"]), user_id=1)


@pytest.mark.asyncio
async def test_tools_endpoint_returns_registry():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app_with_user()), base_url="http://test") as client:
        response = await client.get("/api/agent/tools")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == len(payload["tools"])
    assert payload["generation"] >= 1
    assert {item["risk_level"] for item in payload["tools"]} == {"read", "suggest", "write"}
    by_name = {item["name"]: item for item in payload["tools"]}
    assert by_name["project.context"] == {
        **by_name["project.context"],
        "provider_id": "project-read",
        "provider_version": "1.0.0",
        "source": "builtin",
    }
    assert by_name["knowledge.inspect"]["provider_id"] == "memory-read"
    assert by_name["foreshadowing.inspect"]["provider_id"] == "foreshadowing-read"
    assert by_name["chapter.inspect"]["provider_id"] == "structure-read"
    assert by_name["chapter.version.diff"]["provider_id"] == "structure-read"
    assert by_name["chapter.inspect"]["source"] == "builtin"
    assert all("path" not in item for item in payload["tools"])


@pytest.mark.asyncio
async def test_plan_endpoint_returns_provider_free_plan():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app_with_user()), base_url="http://test") as client:
        response = await client.post("/api/agent/plan", json={"goal": "检查", "project_id": "project-a", "tools": ["chapter.inspect"]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_called"] is False
    assert payload["steps"][0]["tool_name"] == "chapter.inspect"


@pytest.mark.asyncio
async def test_plan_endpoint_rejects_scope_and_unknown_tool():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app_with_user()), base_url="http://test") as client:
        response = await client.post("/api/agent/plan", json={"goal": "越权", "tools": ["chapter.inspect"]})
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "AGENT_PROJECT_SCOPE_VIOLATION"
        response = await client.post("/api/agent/plan", json={"goal": "未知", "tools": ["not.registered"]})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "AGENT_TOOL_NOT_FOUND"


@pytest.mark.asyncio
async def test_agent_endpoints_require_current_user():
    app = FastAPI()
    app.include_router(router)

    async def reject_user():
        raise HTTPException(status_code=401, detail="auth required")

    app.dependency_overrides[get_current_user] = reject_user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/agent/tools")).status_code == 401
        assert (await client.post("/api/agent/plan", json={"goal": "x"})).status_code == 401


@pytest.mark.asyncio
async def test_tools_handler_accepts_authenticated_user_without_provider():
    result = await list_agent_tools(SimpleNamespace(id=9))
    assert result.count == len(result.tools)
    assert result.generation >= 1
    assert next(item for item in result.tools if item.name == "project.context").provider_id == "project-read"


@pytest.mark.asyncio
async def test_tool_health_endpoint_is_admin_only_and_sanitized():
    app = _app_with_user()

    async def override_current_admin():
        return SimpleNamespace(id=1, username="admin", is_superuser=True)

    app.dependency_overrides[get_current_admin] = override_current_admin
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/agent/tools/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["registry_status"] == "healthy"
    assert payload["providers"][0]["path"] == "app.agent.providers.project_read:register_agent_tools"
    assert "OPENAI_API_KEY" not in str(payload)


@pytest.mark.asyncio
async def test_tool_health_handler_returns_sanitized_provider_state():
    payload = await list_agent_tool_health(SimpleNamespace(id=1, username="admin", is_superuser=True))
    assert payload["provider_count"] >= 1
    assert all("failure_detail" not in item for item in payload["providers"])
