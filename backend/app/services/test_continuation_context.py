"""Regression coverage for long-chapter continuation state packaging."""
from types import SimpleNamespace

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_continuation_context_keeps_tail_mission_and_longform_constraints():
    longform_context = SimpleNamespace(
        cast_plan=SimpleNamespace(chapter_focus_names=["林七", "沈舟"]),
        foreshadowing_task=SimpleNamespace(
            must_resolve=[{"name": "盐渍编号", "content": "账册编号必须兑现"}],
            should_reinforce=[{"name": "旧码头", "description": "码头线索需要加压"}],
        ),
    )
    context = PipelineOrchestrator._build_continuation_context(
        chapter_content=("前文" * 700) + "结尾：林七攥紧账册，门外脚步逼近。",
        chapter_mission={
            "continuity_anchor": {"inherit_from_previous": ["盐渍编号仍未解开"]},
            "scene_list": [
                {"scene": "档案馆对峙", "goal": "逼问沈舟", "conflict": "巡逻队封锁", "turn": "账册落入敌手", "outcome": "沈舟改口", "payoff": "逼出账册来源", "bridge": "追兵转向旧码头", "dialogue_value": "改变合作关系", "end_hook": "旧码头传来枪响"},
                {"scene": "旧码头追击", "goal": "夺回账册", "conflict": "潮雾遮断退路", "turn": "敌人烧毁账册", "outcome": "只留下半枚印章", "payoff": "线索指向盐仓", "bridge": "火光引来巡逻队", "dialogue_value": "逼出幕后人", "end_hook": "盐仓门内有人回应"},
            ],
            "focus_characters": ["林七", "沈舟"],
            "dialogue_strategy": {"purpose": ["逼出账册来源", "改变合作关系"]},
        },
        history_context={"previous_summary": "林七发现盐渍编号指向旧码头。"},
        longform_context=longform_context,
        continuation_constraints={
            "pov": "林七第一人称",
            "style_hint": "冷峻克制，短句推进",
            "writing_notes": "结尾必须交出新的选择",
            "forbidden_characters": ["顾临", "白昼"],
        },
    )

    assert context["assistant_tail"].endswith("门外脚步逼近。")
    assert len(context["assistant_tail"]) == 1200
    instruction = context["instruction"]
    assert "必须延续的承接锚点：" in instruction
    for expected in ("盐渍编号仍未解开", "档案馆对峙", "巡逻队封锁", "改变合作关系", "盐仓门内有人回应", "林七", "账册编号必须兑现", "林七第一人称", "冷峻克制", "结尾必须交出新的选择", "顾临"):
        assert expected in instruction
    metadata = context["metadata"]
    assert metadata["tail_chars"] == 1200
    assert metadata["inherit_anchor_count"] == 1
    assert metadata["scene_task_count"] == 2
    assert metadata["completed_scene_count"] == 0
    assert metadata["focus_character_count"] == 2
    assert metadata["longform_item_count"] == 4
    assert metadata["constraint_count"] == 4
    assert metadata["instruction_chars"] > 0
    assert metadata["state_chars"] == metadata["tail_chars"] + metadata["instruction_chars"]


def test_continuation_context_is_bounded_when_optional_context_is_missing():
    context = PipelineOrchestrator._build_continuation_context(
        chapter_content="结尾仍在雨里。",
        chapter_mission=None,
        history_context=None,
        longform_context=None,
    )

    assert context["assistant_tail"] == "结尾仍在雨里。"
    assert "禁止复述、重启场景" in context["instruction"]
    assert "长篇连续性账本" not in context["instruction"]
    assert context["metadata"]["scene_task_count"] == 0


def test_continuation_history_keeps_full_prompt_only_for_first_round():
    context = {"assistant_tail": "最新正文尾部"}
    first = PipelineOrchestrator._build_continuation_history(
        prompt_input="完整写前约束：禁用人物、视角、文风",
        continuation_context=context,
        continuation_prompt="状态包续写指令",
        include_full_prompt=True,
    )
    later = PipelineOrchestrator._build_continuation_history(
        prompt_input="完整写前约束：禁用人物、视角、文风",
        continuation_context=context,
        continuation_prompt="状态包续写指令",
        include_full_prompt=False,
    )

    assert first == [
        {"role": "user", "content": "完整写前约束：禁用人物、视角、文风"},
        {"role": "assistant", "content": "最新正文尾部"},
        {"role": "user", "content": "状态包续写指令"},
    ]
    assert later == [
        {"role": "assistant", "content": "最新正文尾部"},
        {"role": "user", "content": "状态包续写指令"},
    ]


def test_continuation_context_uses_only_unfinished_real_schema_scenes():
    context = PipelineOrchestrator._build_continuation_context(
        chapter_content="林七逼问沈舟，沈舟改口，账册落入敌手。",
        chapter_mission={
            "scene_list": [
                {"scene": "已完成对峙", "goal": "逼问沈舟", "conflict": "巡逻队封锁", "turn": "账册落入敌手", "outcome": "沈舟改口"},
                {"scene": "待推进追击", "goal": "夺回账册", "conflict": "潮雾遮断退路", "turn": "敌人烧毁账册", "payoff": "线索指向盐仓", "bridge": "火光引来巡逻队", "dialogue_value": "逼出幕后人", "end_hook": "盐仓门内有人回应"},
            ]
        },
        history_context={},
        longform_context=None,
    )

    assert "已完成对峙" not in context["instruction"]
    for expected in ("待推进追击", "潮雾遮断退路", "线索指向盐仓", "盐仓门内有人回应"):
        assert expected in context["instruction"]
    assert context["metadata"]["completed_scene_count"] == 1
    assert context["metadata"]["scene_task_count"] == 1


def test_continuation_output_audit_rejects_empty_short_duplicate_and_meta():
    base = "前文" * 300
    cases = [
        ("   ", "empty_output"),
        ("短句", "low_increment"),
        (base[-120:] + "新的内容", "duplicate_tail"),
        ("<think>规划</think>\nThe user wants a plan.", "generation_meta_leakage"),
    ]
    for raw, reason in cases:
        audit = PipelineOrchestrator._audit_continuation_output(
            existing_content=base,
            raw_output=raw,
            minimum_increment=20,
        )
        assert audit["accepted"] is False
        assert audit["stop_reason"] == reason
        assert audit["text"] == PipelineOrchestrator._normalize_generated_prose(raw)


def test_continuation_output_audit_accepts_normalized_real_prose():
    audit = PipelineOrchestrator._audit_continuation_output(
        existing_content="雨声压过了门轴。",
        raw_output="<think>忽略</think>\n```\n林七推门而入，火光在巷口骤然熄灭。\n```",
        minimum_increment=10,
    )

    assert audit["accepted"] is True
    assert audit["stop_reason"] is None
    assert "林七推门而入" in audit["text"]
    assert "<think>" not in audit["text"]
    assert "```" not in audit["text"]
    assert audit["increment_chars"] >= 10


@pytest.mark.asyncio
async def test_continuation_provider_requests_use_real_history_and_remaining_budget(monkeypatch):
    from app.services import pipeline_orchestrator as module

    calls = []

    async def fake_call_generation_text(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="有效续写正文" * 30)

    monkeypatch.setattr(module, "call_generation_text", fake_call_generation_text)
    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.llm_service = object()
    first_history = PipelineOrchestrator._build_continuation_history(
        prompt_input="完整写前约束：视角、文风、禁止角色",
        continuation_context={"assistant_tail": "第一轮尾文"},
        continuation_prompt="第一轮状态化续写",
        include_full_prompt=True,
    )
    later_history = PipelineOrchestrator._build_continuation_history(
        prompt_input="完整写前约束：视角、文风、禁止角色",
        continuation_context={"assistant_tail": "第二轮尾文"},
        continuation_prompt="第二轮状态化续写",
        include_full_prompt=False,
    )

    first = await orchestrator._call_continuation_generation(
        writer_prompt="小说作者",
        conversation_history=first_history,
        user_id=7,
        remaining_to_floor=960,
        minimum_increment=400,
        round_number=1,
    )
    later = await orchestrator._call_continuation_generation(
        writer_prompt="小说作者",
        conversation_history=later_history,
        user_id=7,
        remaining_to_floor=80,
        minimum_increment=400,
        round_number=2,
    )

    assert first.text.startswith("有效续写正文")
    assert later.text.startswith("有效续写正文")
    assert calls[0]["conversation_history"] == first_history
    assert calls[1]["conversation_history"] == later_history
    assert calls[0]["conversation_history"][0]["content"] == "完整写前约束：视角、文风、禁止角色"
    assert all(item["content"] != "完整写前约束：视角、文风、禁止角色" for item in calls[1]["conversation_history"])
    assert calls[0]["policy"].stage_label == "续写轮1"
    assert calls[1]["policy"].stage_label == "续写轮2"
    assert calls[0]["policy"].max_tokens == PipelineOrchestrator._resolve_chapter_generation_max_tokens(1200)
    assert calls[1]["policy"].max_tokens == PipelineOrchestrator._resolve_chapter_generation_max_tokens(400)
    assert calls[1]["timeout"] == PipelineOrchestrator._resolve_chapter_generation_timeout(400)


def test_generate_chapter_keeps_cancellation_and_observability_hooks_for_continuation():
    import inspect
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    for marker in (
        "_call_continuation_generation(",
        "_audit_continuation_output(",
        "_before_call",
        "_after_call",
        '"stop_reason": continuation_stop_reason',
        'event_kind="continuation"',
    ):
        assert marker in source


def test_continuation_context_only_marks_scene_complete_from_recent_evidence():
    context = PipelineOrchestrator._build_continuation_context(
        chapter_content="旧转折已经发生。" + ("后续推进" * 900),
        chapter_mission={
            "scene_list": [
                {"scene": "旧场景", "goal": "旧目标", "turn": "旧转折", "outcome": "旧后果"},
            ]
        },
        history_context={},
        longform_context=None,
    )

    assert "旧场景" in context["instruction"]
    assert context["metadata"]["completed_scene_count"] == 0


def test_continuation_minimum_increment_shrinks_to_remaining_gap():
    assert PipelineOrchestrator._resolve_continuation_min_increment(400, 960) == 400
    assert PipelineOrchestrator._resolve_continuation_min_increment(400, 80) == 80
    assert PipelineOrchestrator._resolve_continuation_min_increment(400, 0) == 1
    audit = PipelineOrchestrator._audit_continuation_output(
        existing_content="旧正文。",
        raw_output="新收尾" * 30,
        minimum_increment=80,
    )
    assert audit["accepted"] is True
