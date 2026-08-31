"""Bounded project-Agent planning with public structured PlanDraft metadata."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .executor import UnknownAgentTool, build_agent_plan
from .policy import ProjectScopeViolation, enforce_tool_scope
from .registry import DEFAULT_TOOL_REGISTRY, AgentToolRegistry
from .schemas import AgentPlan, AgentPlanRequest
from .provider_attempt import ProviderAttemptLedger


_FORBIDDEN_ARGUMENT_KEYS = {
    "thought",
    "reasoning",
    "chain_of_thought",
    "private_reasoning",
    "system_prompt",
    "provider_secret",
    "api_key",
    "authorization",
}


class PlannerProvider(Protocol):
    async def get_llm_response(self, system_prompt: str, conversation_history: list[dict[str, str]], **kwargs: Any) -> str: ...


@dataclass(frozen=True)
class AgentPlannerDecision:
    plan: AgentPlan
    visible_summary: str
    provider_called: bool
    fallback_reason: str | None = None


class AgentOrchestrator:
    """Translate user intent into a bounded public PlanDraft without hidden reasoning."""

    def __init__(self, provider: PlannerProvider, registry: AgentToolRegistry = DEFAULT_TOOL_REGISTRY):
        self.provider = provider
        self.registry = registry

    def _system_prompt(self, project_id: str | None, context_summary: dict[str, Any] | None = None) -> str:
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level.value,
                "project_scoped": tool.project_scoped,
                "input_property_names": sorted(
                    str(name) for name in (tool.input_schema.get("properties") or {}).keys()
                )[:40],
            }
            for tool in self.registry.list_tools()
        ]
        return (
            "你是玄穹文枢的受限项目内 Agent 规划器。只从给定工具注册表选择工具，"
            "不得输出 Python、SQL、shell、URL、文件路径或未注册工具。不要解释隐藏推理，"
            "只能给用户可见的短工作摘要。写入和破坏性工具只可规划，绝不能执行。"
            "严格输出 JSON 对象："
            "{\"summary\":string,\"steps\":[{\"tool_name\":string,\"intent\":string,"
            "\"expected_result\":string,\"depends_on\":[earlier step order],\"arguments\":object}]}。"
            "steps 最多 8 项，依赖只能指向更早步骤；arguments 只能使用工具 input_property_names，"
            "不得包含项目/版本上下文绑定字段的猜测值、密钥、Prompt 或隐藏推理。"
            "兼容旧格式 {\"summary\":string,\"tools\":[string]}。"
            f"当前 project_id：{project_id or '无（仅可 project.list）'}；"
            f"当前安全上下文：{json.dumps(context_summary or {}, ensure_ascii=False)}；工具注册表："
            + json.dumps(tools, ensure_ascii=False)
        )

    @staticmethod
    def _clean_arguments(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("planner step arguments must be an object")
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key).strip()
            if not name or name.lower() in _FORBIDDEN_ARGUMENT_KEYS:
                raise ValueError("planner step arguments contain forbidden field")
            result[name] = item
        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("planner step arguments must be JSON serializable") from exc
        return result

    @classmethod
    def _parse(cls, raw: str) -> tuple[str, list[dict[str, Any]]]:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("provider planner returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("provider planner response is not an object")
        summary = str(payload.get("summary") or "已生成受控工具计划。").strip()[:500]
        raw_steps = payload.get("steps")
        if isinstance(raw_steps, list) and raw_steps:
            if len(raw_steps) > 8:
                raise ValueError("provider planner returned too many steps")
            drafts: list[dict[str, Any]] = []
            seen_tools: set[str] = set()
            for order, raw_step in enumerate(raw_steps, start=1):
                if not isinstance(raw_step, dict):
                    raise ValueError("provider planner step is not an object")
                tool_name = str(raw_step.get("tool_name") or "").strip()
                if not tool_name:
                    raise ValueError("provider planner step is missing tool_name")
                if tool_name in seen_tools:
                    raise ValueError("provider planner must not repeat one tool in PlanDraft v1")
                seen_tools.add(tool_name)
                raw_dependencies = raw_step.get("depends_on") or []
                if not isinstance(raw_dependencies, list):
                    raise ValueError("planner step depends_on must be a list")
                dependencies = [int(value) for value in raw_dependencies]
                if any(value < 1 or value >= order for value in dependencies):
                    raise ValueError("planner step dependencies must reference earlier steps")
                if len(set(dependencies)) != len(dependencies):
                    raise ValueError("planner step dependencies must be unique")
                drafts.append(
                    {
                        "tool_name": tool_name,
                        "intent": str(raw_step.get("intent") or "").strip()[:500] or None,
                        "expected_result": str(raw_step.get("expected_result") or "").strip()[:500] or None,
                        "depends_on": dependencies,
                        "planner_arguments": cls._clean_arguments(
                            raw_step.get("arguments", raw_step.get("planner_arguments"))
                        ),
                    }
                )
            return summary or "已生成受控工具计划。", drafts
        selected = payload.get("tools")
        if not isinstance(selected, list):
            raise ValueError("provider planner requires steps or tools")
        names = [str(item).strip() for item in selected if isinstance(item, str) and str(item).strip()]
        return summary or "已生成受控工具计划。", [
            {"tool_name": name, "intent": None, "expected_result": None, "depends_on": [], "planner_arguments": {}}
            for name in names[:8]
        ]

    def _validate_tools(self, tool_names: list[str], project_id: str | None) -> list[str]:
        valid: list[str] = []
        for name in tool_names:
            try:
                tool = self.registry.get(name)
            except KeyError as exc:
                raise UnknownAgentTool(str(exc)) from exc
            enforce_tool_scope(tool, project_id)
            if name not in valid:
                valid.append(name)
        if not valid:
            valid = ["project.context"] if project_id else ["project.list"]
        return valid

    def _build_plan_from_drafts(
        self,
        *,
        goal: str,
        user_id: int,
        project_id: str | None,
        drafts: list[dict[str, Any]],
        provider_called: bool,
        planner_fallback_reason: str | None = None,
    ) -> AgentPlan:
        names = self._validate_tools([str(item["tool_name"]) for item in drafts], project_id)
        # Duplicates are rejected in structured PlanDraft. Legacy tools retain
        # their old de-duplication behavior; align metadata to the final names.
        metadata_by_tool = {str(item["tool_name"]): item for item in drafts}
        for tool_name, metadata in metadata_by_tool.items():
            tool = self.registry.get(tool_name)
            planner_arguments = dict(metadata.get("planner_arguments") or {})
            properties = tool.input_schema.get("properties") if isinstance(tool.input_schema, dict) else {}
            allowed_names = set(properties) if isinstance(properties, dict) else set()
            if tool.input_schema.get("additionalProperties") is False:
                unknown = sorted(set(planner_arguments) - allowed_names)
                if unknown:
                    raise ValueError(f"planner arguments are outside {tool_name} schema: {', '.join(unknown)}")
            bound_names = {binding.argument_name for binding in tool.context_bindings}
            conflicts = sorted(set(planner_arguments) & bound_names)
            if conflicts:
                raise ValueError(f"planner must not guess context-bound arguments for {tool_name}: {', '.join(conflicts)}")
        plan = build_agent_plan(
            AgentPlanRequest(goal=goal, project_id=project_id, tools=names),
            user_id=user_id,
            registry=self.registry,
            provider_called=provider_called,
            planner_fallback_reason=planner_fallback_reason,
        )
        for step in plan.steps:
            metadata = metadata_by_tool.get(step.tool_name, {})
            intent = metadata.get("intent")
            expected_result = metadata.get("expected_result")
            step.intent = intent
            step.expected_result = expected_result
            step.depends_on = list(metadata.get("depends_on") or [])
            step.planner_arguments = dict(metadata.get("planner_arguments") or {})
            if intent:
                step.description = intent
        return plan

    async def plan(
        self,
        *,
        goal: str,
        user_id: int,
        project_id: str | None,
        context_summary: dict[str, Any] | None = None,
        requested_tools: list[str] | None = None,
        attempt_ledger: ProviderAttemptLedger | None = None,
    ) -> AgentPlannerDecision:
        # Explicit tool selection is a user instruction, not a Provider decision.
        if requested_tools:
            tools = self._validate_tools(requested_tools, project_id)
            return AgentPlannerDecision(
                plan=build_agent_plan(
                    AgentPlanRequest(goal=goal, project_id=project_id, tools=tools),
                    user_id=user_id,
                    registry=self.registry,
                ),
                visible_summary="已按用户指定的项目内工具生成计划。",
                provider_called=False,
            )
        try:
            raw = await self.provider.get_llm_response(
                self._system_prompt(project_id, context_summary),
                [{"role": "user", "content": f"{goal}\n请严格返回 JSON 对象，优先使用 summary 和 steps。"}],
                user_id=user_id,
                temperature=0.1,
                timeout=90,
                response_format="json_object",
                max_tokens=900,
                allow_non_stream_fallback=True,
                attempt_ledger=attempt_ledger,
                attempt_role="planner",
            )
            summary, drafts = self._parse(raw)
            plan = self._build_plan_from_drafts(
                goal=goal,
                user_id=user_id,
                project_id=project_id,
                drafts=drafts,
                provider_called=True,
            )
            return AgentPlannerDecision(
                plan=plan,
                visible_summary=summary,
                provider_called=True,
            )
        except (UnknownAgentTool, ProjectScopeViolation):
            raise
        except Exception as exc:  # Provider error must remain visible, never be reported as success.
            tools = ["project.context"] if project_id else ["project.list"]
            return AgentPlannerDecision(
                plan=build_agent_plan(
                    AgentPlanRequest(goal=goal, project_id=project_id, tools=tools),
                    user_id=user_id,
                    registry=self.registry,
                    planner_fallback_reason=type(exc).__name__,
                ),
                visible_summary="Provider 规划不可用，已降级为最小只读项目检查。",
                provider_called=False,
                fallback_reason=type(exc).__name__,
            )
