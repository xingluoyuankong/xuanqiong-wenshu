"""Deterministic Phase 1 planner; intentionally provider-free."""

from __future__ import annotations

from uuid import UUID

from .policy import enforce_tool_scope
from .registry import DEFAULT_TOOL_REGISTRY, AgentToolRegistry
from .schemas import AgentEvent, AgentPlan, AgentPlanRequest, AgentPlanStep


class UnknownAgentTool(ValueError):
    """The requested tool is not registered in this project runtime."""


def build_agent_plan(
    request: AgentPlanRequest,
    *,
    user_id: int,
    registry: AgentToolRegistry = DEFAULT_TOOL_REGISTRY,
    plan_id: UUID | None = None,
    provider_called: bool = False,
    planner_fallback_reason: str | None = None,
) -> AgentPlan:
    """Build a plan from registered capabilities without invoking a provider."""

    tool_names = request.tools or (["project.context"] if request.project_id else ["project.list"])
    steps: list[AgentPlanStep] = []
    events: list[AgentEvent] = [AgentEvent(
        sequence=1,
        event_type="plan_created",
        phase="planning",
        message=(
            "已创建由 Provider 选择工具的受控 Agent 执行计划。"
            if provider_called else "已创建 Agent 执行计划，尚未调用 Provider。"
        ),
        data={
            "tool_count": len(tool_names),
            "mode": request.mode,
            "provider_called": provider_called,
            **({"planner_fallback_reason": planner_fallback_reason} if planner_fallback_reason else {}),
        },
    )]
    for order, tool_name in enumerate(tool_names, start=1):
        try:
            tool = registry.get(tool_name)
        except KeyError as exc:
            raise UnknownAgentTool(str(exc)) from exc
        enforce_tool_scope(tool, request.project_id)
        steps.append(AgentPlanStep(
            order=order,
            tool_name=tool.name,
            description=tool.description,
            risk_level=tool.risk_level,
            requires_confirmation=tool.requires_confirmation,
        ))
        events.append(AgentEvent(
            sequence=len(events) + 1,
            event_type="approval_required" if tool.requires_confirmation else "plan_step_pending",
            phase="planning",
            message=(
                f"工具 {tool.name} 需要用户确认后执行。"
                if tool.requires_confirmation else f"工具 {tool.name} 已加入待执行计划。"
            ),
            data={"tool_name": tool.name, "risk_level": tool.risk_level.value},
        ))
    values = {
        "goal": request.goal,
        "project_id": request.project_id,
        "mode": request.mode,
        "created_by_user_id": user_id,
        "steps": steps,
        "events": events,
        "provider_called": provider_called,
        "planner_fallback_reason": planner_fallback_reason,
    }
    if plan_id is not None:
        values["plan_id"] = plan_id
    return AgentPlan(**values)
