from __future__ import annotations

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.provider_attempt import ProviderAttemptLedger
from app.agent.policy import ProjectScopeViolation


class FakeProvider:
    def __init__(self, response: str | Exception):
        self.response = response
        self.calls = 0
        self.args = None
        self.kwargs = None

    async def get_llm_response(self, *args, **kwargs):
        self.calls += 1
        self.args = args
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_provider_plan_is_limited_to_registered_tools_and_visible_summary():
    provider = FakeProvider('{"summary":"先读取章节质量。","tools":["quality.inspect","chapter.inspect"]}')
    decision = await AgentOrchestrator(provider).plan(goal="检查质量", user_id=9, project_id="p1")
    assert provider.calls == 1
    assert decision.provider_called is True
    assert decision.plan.provider_called is True
    assert decision.plan.planner_fallback_reason is None
    assert decision.visible_summary == "先读取章节质量。"
    assert [item.tool_name for item in decision.plan.steps] == ["quality.inspect", "chapter.inspect"]
    assert "json" in provider.args[0].lower()
    assert "json" in provider.args[1][0]["content"].lower()


@pytest.mark.asyncio
async def test_provider_cannot_select_unknown_tool_or_cross_scope_tool():
    provider = FakeProvider('{"summary":"bad","tools":["os.system"]}')
    with pytest.raises(Exception):
        await AgentOrchestrator(provider).plan(goal="bad", user_id=9, project_id="p1")
    provider = FakeProvider('{"summary":"bad","tools":["chapter.inspect"]}')
    with pytest.raises(ProjectScopeViolation):
        await AgentOrchestrator(provider).plan(goal="bad", user_id=9, project_id=None)


@pytest.mark.asyncio
async def test_provider_failure_falls_back_to_minimal_read_only_plan_without_false_success():
    provider = FakeProvider(RuntimeError("provider offline"))
    decision = await AgentOrchestrator(provider).plan(goal="检查", user_id=9, project_id="p1")
    assert decision.provider_called is False
    assert decision.fallback_reason == "RuntimeError"
    assert decision.plan.provider_called is False
    assert decision.plan.planner_fallback_reason == "RuntimeError"
    assert [item.tool_name for item in decision.plan.steps] == ["project.context"]


@pytest.mark.asyncio
async def test_explicit_user_tools_do_not_call_provider():
    provider = FakeProvider('{"summary":"ignored","tools":["project.list"]}')
    decision = await AgentOrchestrator(provider).plan(goal="读取", user_id=9, project_id="p1", requested_tools=["quality.inspect"])
    assert provider.calls == 0
    assert decision.provider_called is False
    assert [item.tool_name for item in decision.plan.steps] == ["quality.inspect"]


@pytest.mark.asyncio
async def test_provider_structured_plan_draft_preserves_public_step_metadata_and_dependencies():
    provider = FakeProvider(
        '{"summary":"先读取项目，再统计进度。","steps":['
        '{"tool_name":"project.context","intent":"读取项目当前状态","expected_result":"项目摘要","depends_on":[],"arguments":{}},'
        '{"tool_name":"statistics.project","intent":"统计章节进度","expected_result":"统计摘要","depends_on":[1],"arguments":{}}]}'
    )

    decision = await AgentOrchestrator(provider).plan(goal="整理项目状态", user_id=9, project_id="p1")

    assert decision.provider_called is True
    assert [(step.tool_name, step.intent, step.expected_result, step.depends_on) for step in decision.plan.steps] == [
        ("project.context", "读取项目当前状态", "项目摘要", []),
        ("statistics.project", "统计章节进度", "统计摘要", [1]),
    ]


@pytest.mark.asyncio
async def test_provider_plan_draft_rejects_context_bound_or_schema_external_arguments_by_falling_back():
    provider = FakeProvider(
        '{"summary":"bad","steps":[{'
        '"tool_name":"chapter.inspect","intent":"猜测章节","depends_on":[],"arguments":{"chapter_number":3}}]}'
    )

    decision = await AgentOrchestrator(provider).plan(goal="检查章节", user_id=9, project_id="p1")

    assert decision.provider_called is False
    assert decision.fallback_reason == "ValueError"
    assert [step.tool_name for step in decision.plan.steps] == ["project.context"]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError("planner timeout"), RuntimeError("provider 5xx fixture")])
async def test_provider_failure_classes_remain_durable_planner_fallback_facts(error):
    """P2-4: a Planner transport failure must be explicit, never a false Provider success."""
    decision = await AgentOrchestrator(FakeProvider(error)).plan(
        goal="检查项目", user_id=9, project_id="p1"
    )

    assert decision.provider_called is False
    assert decision.fallback_reason == type(error).__name__
    assert decision.plan.provider_called is False
    assert decision.plan.planner_fallback_reason == type(error).__name__
    assert [step.tool_name for step in decision.plan.steps] == ["project.context"]


@pytest.mark.asyncio
async def test_planner_forwards_attempt_ledger_with_planner_role():
    provider = FakeProvider('{"summary":"读取项目","tools":["project.context"]}')
    ledger = ProviderAttemptLedger(run_id="planner-attempt")
    decision = await AgentOrchestrator(provider).plan(
        goal="读取", user_id=9, project_id="p1", attempt_ledger=ledger
    )
    assert decision.provider_called is True
    assert provider.kwargs["attempt_ledger"] is ledger
    assert provider.kwargs["attempt_role"] == "planner"
