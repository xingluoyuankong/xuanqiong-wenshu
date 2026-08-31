import re
from pathlib import Path
from types import SimpleNamespace

import inspect

import pytest

from app.api.routers.optimizer import _continuity_guard_failure as optimizer_continuity_guard_failure
from app.services.ai_review_service import AIReviewService, ReviewResult
from app.services.consistency_service import ConsistencyService
from app.services.continuity_guard_utils import continuity_terms_guard_failure
from app.services.enrichment_service import ENRICH_CHAPTER_PROMPT, ENRICH_DIALOGUE_PROMPT, ENRICH_SCENE_PROMPT, EnrichmentService
from app.services.longform_context_service import CastPlan, ForeshadowingChapterTask, LongformContextPackage
from app.services.pipeline_orchestrator import PipelineConfig, PipelineOrchestrator
from app.services import pipeline_orchestrator as pipeline_orchestrator_module
from app.services.self_critique_service import SelfCritiqueService
from app.services.ultimate_writing_flow import _resolve_direct_generation_contract
from app.services.longform_generation_service import LongformGenerationContractError

# T-12 之后字数参数真正参与评分，这对常量必须**贴生产比例**，否则字数判罚会串进
# 每一条结构类断言里。完整定值依据见文件后半段 `_score_density_sample` 上方的注释；
# 一句话版本：生产里 min 恒为 target * 0.9，而全部结构类样本落在 2310-2810 字，
# 取 2500/2250 能让 preferred_floor（0.92*target=2300）低于所有样本，字数维度中性。
_SAMPLE_TARGET_WORDS = 2500
_SAMPLE_MIN_WORDS = 2250


class TestGenerationQualityGuards:
    @pytest.mark.asyncio
    async def test_contamination_uses_one_clean_retry_without_sending_contaminated_text(self, monkeypatch):
        orchestrator = object.__new__(PipelineOrchestrator)
        calls = []
        responses = [
            "让我写出最终草稿。需要至少1200字。",
            "\n".join(
                [
                    "雨停时，林七握紧门把，听见门外的脚步停在第三阶。",
                    "‘开门。’门外的人低声说。林七拒绝回答，反手锁上了第二道门。",
                    "他发现门缝下多出一张潮湿的照片，决定把照片烧掉，却在火光里看见了自己的背影。",
                ]
                * 12
            ),
        ]

        class FakeLLM:
            async def get_generation_capabilities(self, _user_id):
                return {"model": "deepseek-v4-flash-free", "bounded_short_chapter": True}

        async def fake_call_generation_text(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                text=responses.pop(0),
                attempts=1,
                effective_max_tokens=2640,
                estimated_input_tokens=10,
                estimated_output_tokens=20,
                estimated_total_tokens=30,
                prompt_character_count=len(kwargs["conversation_history"][0]["content"]),
                output_character_count=len(calls[-1]["conversation_history"][0]["content"]),
            )

        class Guardrails:
            def check(self, **_kwargs):
                return SimpleNamespace(passed=True, violations=[])

        orchestrator.llm_service = FakeLLM()
        orchestrator.guardrails = Guardrails()
        from app.services import pipeline_orchestrator as module
        monkeypatch.setattr(module, "call_generation_text", fake_call_generation_text)

        result = await orchestrator._generate_single_version(
            index=0,
            prompt_input="[章节导演脚本](JSON)\n林七必须面对门外的脚步。",
            writer_prompt="你是一名小说作者。",
            style_hint=None,
            project_id="p1",
            chapter_number=1,
            outline_title="门外",
            outline_summary="脚步逼近",
            chapter_mission={"generation_source": "local_short_chapter_contract"},
            forbidden_characters=[],
            allowed_new_characters=[],
            user_id=1,
            writer_blueprint={},
            memory_context=None,
            analysis_guidance_context=None,
            enhanced_context=None,
            config=PipelineConfig(target_word_count=1200, min_word_count=900, version_count=1),
        )

        assert "雨停时" in result["content"]
        assert len(calls) == 2
        assert calls[0]["policy"].prompt_cache_key.endswith(":draft")
        assert calls[1]["policy"].prompt_cache_key.endswith(":draft:contamination-retry")
        assert "让我写出最终草稿" not in calls[1]["conversation_history"][0]["content"]
        assert "正文输出协议" in calls[0]["system_prompt"]
        assert "写作模板" not in calls[1]["system_prompt"]
        assert result["metadata"]["contamination_retry_used"] is True
        assert result["metadata"]["contamination_retry_result"] == "accepted"

    @pytest.mark.asyncio
    async def test_contamination_retry_is_bounded_and_surfaces_contract_error(self, monkeypatch):
        orchestrator = object.__new__(PipelineOrchestrator)
        calls = []

        class FakeLLM:
            async def get_generation_capabilities(self, _user_id):
                return {"model": "deepseek-v4-flash-free", "bounded_short_chapter": True}

        async def fake_call_generation_text(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="让我写。需要至少900字。", attempts=1)

        orchestrator.llm_service = FakeLLM()
        from app.services import pipeline_orchestrator as module
        monkeypatch.setattr(module, "call_generation_text", fake_call_generation_text)

        with pytest.raises(LongformGenerationContractError, match="让我写|需要至少"):
            await orchestrator._generate_single_version(
                index=0,
                prompt_input="[章节导演脚本](JSON)\n门外有人。",
                writer_prompt="写正文。",
                style_hint=None,
                project_id="p2",
                chapter_number=1,
                outline_title="门外",
                outline_summary="有人逼近",
                chapter_mission={"generation_source": "local_short_chapter_contract"},
                forbidden_characters=[],
                allowed_new_characters=[],
                user_id=1,
                writer_blueprint={},
                memory_context=None,
                analysis_guidance_context=None,
                enhanced_context=None,
                config=PipelineConfig(target_word_count=1200, min_word_count=900, version_count=1),
            )

        assert len(calls) == 2
        assert calls[0]["conversation_history"][0]["content"] != calls[1]["conversation_history"][0]["content"]
        assert "让我写。需要至少900字" not in calls[1]["conversation_history"][0]["content"]
    def test_generation_error_summary_is_bounded_and_keeps_provider_details_safe(self):
        summary = PipelineOrchestrator._summarize_generation_error(
            LongformGenerationContractError("正文输出包含生成说明：" + "x" * 2000)
        )

        assert summary.startswith("LongformGenerationContractError:")
        assert len(summary) <= 360

    def test_http_generation_error_summary_prefers_structured_code(self):
        from fastapi import HTTPException

        summary = PipelineOrchestrator._summarize_generation_error(
            HTTPException(
                status_code=503,
                detail={"code": "UPSTREAM_TIMEOUT", "message": "Provider 超时"},
            )
        )

        assert summary == "UPSTREAM_TIMEOUT: Provider 超时"

    def test_meta_leakage_rejects_provider_planning_without_rejecting_prose(self):
        leaked = "The user wants Chapter 1. Let's design the conflict. Need at least 1200 words."
        markers = {item.casefold() for item in PipelineOrchestrator._detect_generation_meta_leakage(leaked)}
        assert "the user wants" in markers
        assert "let's design" in markers
        assert "need at least" in markers
        assert "The lantern shook. 林七没有回头。" and not PipelineOrchestrator._detect_generation_meta_leakage(
            "The lantern shook. 林七没有回头。"
        )

    def test_meta_leakage_detects_chinese_planning_markers(self):
        assert "我来设计" in PipelineOrchestrator._detect_generation_meta_leakage("我来设计这一章的冲突")
        assert "让我写" in PipelineOrchestrator._detect_generation_meta_leakage("让我写出最终草稿")

    def test_generation_meta_leakage_rejects_chinese_word_budget_preamble(self):
        leaked = "\u672c\u7ae0\u5b57\u6570\u76ee\u6807 1200 \u5b57\uff0c\u6700\u4f4e\u5b57\u6570 900 \u5b57\u3002\u73b0\u5728\u5f00\u59cb\u5199\u4e00\u4e2a\u5c0f\u8bf4\u7ae0\u8282\u3002"
        markers = PipelineOrchestrator._detect_generation_meta_leakage(leaked)
        assert "\u672c\u7ae0\u5b57\u6570" in markers
        assert "\u6700\u4f4e\u5b57\u6570" in markers

    def test_meta_leakage_does_not_scan_deep_inside_valid_prose(self):
        prose = "林七沿着潮湿的石阶往下走。" * 180
        assert not PipelineOrchestrator._detect_generation_meta_leakage(
            prose + "The user wants the door opened."
        )

    def test_provider_planning_preamble_is_removed_at_draft_boundary(self):
        response = "They want:\n- Target: 1200 characters\n\nLet me design it.\n---\nDraft:\n顾沉推开门，看见火光贴着墙根逼近。"
        cleaned = PipelineOrchestrator._strip_leading_generation_meta(response)
        assert cleaned == "顾沉推开门，看见火光贴着墙根逼近。"
        assert PipelineOrchestrator._detect_generation_meta_leakage(cleaned) == []

    def test_short_clean_contamination_retry_is_not_accepted(self):
        cleaned = "门外的脚步停住了。"
        assert len(cleaned.replace("\n", "")) < 900
        assert PipelineOrchestrator._detect_generation_meta_leakage(cleaned) == []

    def test_short_chapter_uses_local_mission_contract_without_losing_continuity(self):
        mission = PipelineOrchestrator._build_lean_chapter_mission(
            previous_summary="林七发现潮汐记录被人替换。",
            previous_tail="门外传来三声不该出现的敲击。",
            outline_title="潮痕来客",
            outline_summary="林七必须判断敲门者是否知道旧档案的来源。",
            writing_notes="保持都市悬疑节奏。",
            introduced_characters=["林七"],
            planned_characters=["林七", "沈舟"],
            target_word_count=1200,
        )

        assert mission["generation_source"] == "local_short_chapter_contract"
        assert mission["continuity_anchor"]["inherit_from_previous"] == ["门外传来三声不该出现的敲击。"]
        assert mission["scene_list"]
        assert mission["scene_list"][0]["word_budget"] == 1200
        assert mission["scene_list"][0]["conflict"]
        assert mission["scene_list"][0]["end_hook"]

    def test_short_chapter_prompt_and_output_budgets_are_bounded(self):
        assert PipelineOrchestrator._resolve_writer_prompt_budget(1200) == 1800
        assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(1200) == 2640
        assert PipelineOrchestrator._resolve_chapter_generation_soft_timeout(1200) >= 135
        assert PipelineOrchestrator._resolve_writer_prompt_budget(5000) == 6000

    @pytest.mark.asyncio
    async def test_short_chapter_mission_skips_model_but_long_chapter_keeps_model_path(self):
        orchestrator = object.__new__(PipelineOrchestrator)
        cache_writes = []

        async def cache_get(_key):
            return None

        async def cache_set(key, value, expire):
            cache_writes.append((key, value, expire))

        class PromptService:
            async def get_prompt(self, _name):
                raise AssertionError("短章不应读取模型导演提示词")

        orchestrator._cache_get = cache_get
        orchestrator._cache_set = cache_set
        orchestrator.prompt_service = PromptService()
        orchestrator.llm_service = object()

        short = await orchestrator._generate_chapter_mission(
            blueprint_dict={}, previous_summary="摘要", previous_tail="尾巴", recent_track="", plot_arc_digest="",
            outline_title="短章", outline_summary="短章冲突", writing_notes="", introduced_characters=["甲"],
            planned_characters=[], all_characters=["甲"], target_word_count=1200, user_id=1,
        )
        assert short["generation_source"] == "local_short_chapter_contract"
        assert cache_writes

        class LongPromptService:
            async def get_prompt(self, _name):
                return "plan"

        orchestrator.prompt_service = LongPromptService()
        called = []

        async def model_call(**_kwargs):
            called.append(True)
            raise RuntimeError("expected model path")

        from app.services import pipeline_orchestrator as module
        original = module.call_generation_json
        module.call_generation_json = model_call
        try:
            long = await orchestrator._generate_chapter_mission(
                blueprint_dict={}, previous_summary="摘要", previous_tail="尾巴", recent_track="", plot_arc_digest="",
                outline_title="长章", outline_summary="长章冲突", writing_notes="", introduced_characters=["甲"],
                planned_characters=[], all_characters=["甲"], target_word_count=3000, user_id=1,
            )
        finally:
            module.call_generation_json = original
        assert called == [True]
        assert long is None

    def test_short_chapter_does_not_repeat_same_provider_in_stable_mode(self):
        short = PipelineConfig(preset="enhanced", target_word_count=1200, version_count=1)
        long = PipelineConfig(preset="enhanced", target_word_count=4500, version_count=2)

        assert PipelineOrchestrator._build_stable_retry_config(short) is None
        fallback = PipelineOrchestrator._build_stable_retry_config(long)
        assert fallback is not None
        assert fallback.preset == "stable"

    def test_stable_retry_success_threshold_clamps_to_requested_candidate_count(self):
        primary_required = PipelineOrchestrator._required_success_count(2)

        assert primary_required == 2
        assert PipelineOrchestrator._attempt_required_success_count(
            required_success_count=primary_required,
            requested_count=1,
        ) == 1
        assert PipelineOrchestrator._attempt_required_success_count(
            required_success_count=primary_required,
            requested_count=2,
        ) == 2

    def test_longform_never_builds_whole_chapter_stable_retry_config(self):
        longform = PipelineConfig(
            preset="enhanced",
            target_word_count=20000,
            version_count=1,
        )

        assert PipelineOrchestrator._build_stable_retry_config(longform) is None
        long_tier = PipelineConfig(preset="enhanced", target_word_count=7000, version_count=1)
        assert PipelineOrchestrator._build_stable_retry_config(long_tier) is None

    def test_runtime_event_keeps_developer_detail_separate_from_user_summary(self):
        compact = PipelineOrchestrator._compact_runtime_event({
            "at": "2026-05-21T00:00:00+00:00",
            "stage": "quality_gate",
            "level": "warning",
            "message": "质量门发现需要局部补丁的问题",
            "kind": "review",
            "summary": "事件密度不足，建议补强对话攻防。",
            "developer_detail": {
                "raw_provider": "cpa",
                "trace": "x" * 1200,
            },
        })

        assert compact["summary"] == "事件密度不足，建议补强对话攻防。"
        assert compact["developer_detail"]["raw_provider"] == "cpa"
        assert len(compact["developer_detail"]["trace"]) < 1200

    def test_ultimate_direct_generation_contract_scales_long_chapters(self):
        standard = _resolve_direct_generation_contract(5000)
        long_chapter = _resolve_direct_generation_contract(10000)

        assert standard["tier"] == "standard_high_quality"
        assert standard["min_word_count"] >= 4500
        assert standard["scene_min"] >= 3
        assert long_chapter["tier"] == "long_chapter"
        assert long_chapter["scene_max"] >= 8
        assert long_chapter["timeout_seconds"] > standard["timeout_seconds"]
        assert long_chapter["max_tokens"] > standard["max_tokens"]

    def test_quality_gate_does_not_mislabel_rich_scene_evidence_as_progression_weak(self):
        story_guard = {
            "word_count": 8387,
            "mission_hit_count": 0,
            "dialogue_marker_count": 302,
            "scene_count": 6,
            "scene_fulfillment_rate": 0.8333,
            "scene_structure_rate": 0.8333,
            "dialogue_changes_state": True,
            "ending_pressure_passed": True,
            "event_density_passed": True,
            "state_change_interval_passed": True,
            "long_chapter_density_passed": True,
            "static_description_risk": False,
        }

        warning_summary = PipelineOrchestrator._build_quality_issue_summary(story_guard=story_guard)
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "story_progression_guard": story_guard,
                "self_critique_after_consistency": {
                    "final_score": 75,
                    "critical_count": 0,
                    "major_count": 0,
                },
            }
        )

        assert "chapter_progression_weak" not in warning_summary["codes"]
        assert "chapter_progression_weak" not in gate["quality_issue_codes"]
        assert gate["passed"] is True

    def test_build_prompt_sections_prioritize_core_story_constraints(self):
        sections = PipelineOrchestrator._build_prompt_sections(
            writer_blueprint={"title": "测试书", "characters": [{"name": "林七"}], "extra": "设定" * 300},
            previous_summary="上一章里，林七带着伤离开地牢。",
            previous_tail="门外忽然传来三声敲击。",
            chapter_mission={
                "chapter_purpose": "逼问真相",
                "scene_list": [{"goal": "逼问真相", "conflict": "对方拒绝回答", "turn": "局面突然反转", "end_hook": "脚步声逼近"}],
            },
            macro_continuity_context="## 长线剧情压力\n- 黑潮疑云：继续逼近真相",
            rag_context={"chunks": ["检索片段A"], "summaries": ["检索摘要A"]},
            knowledge_context="精筛上下文",
            outline_title="逼问之夜",
            outline_summary="林七想逼问真相，却被对方反制。",
            writing_notes="强调对话压迫感",
            forbidden_characters=["沈舟"],
            project_memory_text="长期记忆",
            memory_context="记忆层",
            analysis_guidance_context="角色状态与未回收伏笔",
            style_context="文风摘要",
            target_word_count=3200,
            min_word_count=2400,
        )

        titles = [title for title, _ in sections]
        assert "[SCENE_EXECUTION_LEDGER]" in titles
        titles = [title for title in titles if title != "[SCENE_EXECUTION_LEDGER]"]
        assert titles[:8] == [
            "[当前章节目标]",
            "[章节导演脚本](JSON)",
            "[长线连续性摘要](安全压缩)",
            "[上一章摘要]",
            "[上一章结尾]",
            "[连续性硬性约束]",
            "[章节长度约束]",
            "[禁止角色](本章不允许提及)",
        ]
        assert titles[-1] == "[世界蓝图](JSON，已裁剪)"

    def test_apply_prompt_budget_keeps_core_sections_ahead_of_blueprint(self):
        orchestrator = object.__new__(PipelineOrchestrator)
        sections = [
            ("[世界蓝图](JSON，已裁剪)", "设定" * 1500),
            ("[当前章节目标]", "目标" * 30),
            ("[章节导演脚本](JSON)", "导演脚本" * 35),
            ("[长线连续性摘要](安全压缩)", "连续性摘要" * 25),
            ("[上一章摘要]", "摘要" * 25),
            ("[上一章结尾]", "结尾" * 25),
            ("[连续性硬性约束]", "约束" * 40),
            ("[章节长度约束]", "长度" * 20),
        ]

        budgeted = orchestrator._apply_prompt_budget(sections, max_tokens=120)
        titles = [title for title, _ in budgeted]
        if "[SCENE_EXECUTION_LEDGER]" in titles:
            titles = [title for title in titles if title != "[SCENE_EXECUTION_LEDGER]"]

        assert titles[:5] == [
            "[当前章节目标]",
            "[章节导演脚本](JSON)",
            "[长线连续性摘要](安全压缩)",
            "[上一章摘要]",
            "[上一章结尾]",
        ]
        if "[世界蓝图](JSON，已裁剪)" in titles:
            assert titles.index("[世界蓝图](JSON，已裁剪)") > titles.index("[章节长度约束]")

    def test_scene_execution_ledger_contains_budget_and_scene_requirements(self):
        ledger = PipelineOrchestrator._build_scene_execution_ledger(
            chapter_mission={
                "continuity_anchor": {
                    "inherit_from_previous": ["门外脚步声逼近"],
                    "deliver_to_next": ["危险正式落到主角身上"],
                },
                "dialogue_strategy": {"purpose": ["试探", "压迫"]},
                "scene_list": [
                    {
                        "scene": "1",
                        "goal": "逼问真相",
                        "conflict": "对方拒绝回答",
                        "turn": "对方突然翻脸",
                        "emotion_shift": "压抑转紧绷",
                        "dialogue_value": "试探",
                        "end_hook": "脚步声逼近",
                    }
                ],
                "sequel_required": True,
                "sequel_description": "短暂确认代价并决定下一步",
            },
            outline_title="逼问之夜",
            outline_summary="主角必须从沉默中撬出真相。",
            target_word_count=3200,
            min_word_count=2400,
        )

        assert ledger is not None
        assert "3200" in ledger
        assert "场景执行清单" in ledger
        assert "逼问真相" in ledger
        assert "对话硬要求" in ledger
        assert "短余波限制" in ledger

    def test_chapter_mission_schema_requires_scene_budget_and_payoff_fields(self):
        schema = PipelineOrchestrator._build_chapter_mission_schema()

        assert "scene_list" in schema["required"]
        scene_schema = schema["properties"]["scene_list"]["items"]
        for field in ("goal", "conflict", "turn", "outcome", "payoff", "bridge", "dialogue_value", "word_budget"):
            assert field in scene_schema["required"]
        assert "foreshadowing_tasks" in schema["required"]

    def test_normalize_chapter_mission_fills_missing_scene_contract_fields(self):
        mission = PipelineOrchestrator._normalize_chapter_mission(
            {
                "chapter_purpose": "逼问账册真相",
                "dialogue_strategy": {"purpose": "试探"},
                "scene_list": [{"goal": "逼问账册真相"}],
            },
            target_word_count=5200,
        )

        scene = mission["scene_list"][0]
        assert mission["schema_version"] == "chapter_mission.v2"
        assert mission["dialogue_strategy"]["purpose"] == ["试探"]
        assert scene["conflict"]
        assert scene["payoff"]
        assert scene["bridge"]
        assert scene["word_budget"] > 0
        assert mission["chapter_draft_contract"]["target_word_count"] == 5200

    def test_first_draft_retry_triggers_for_static_short_dialogue_light_copy(self):
        should_retry, story_guard, reason_codes = PipelineOrchestrator._evaluate_first_draft_retry(
            content="夜色沉沉，风从廊下穿过，灯影被一点点拉长。" * 120,
            violations=[],
            chapter_mission={
                "dialogue_strategy": {"purpose": ["试探", "压迫"]},
                "scene_list": [{"goal": "逼问真相", "conflict": "对方拒绝回答", "turn": "局势反转"}],
            },
            target_word_count=3200,
            min_word_count=2400,
        )

        assert should_retry is True
        assert story_guard["static_description_risk"] is True
        assert "static_description_risk" in reason_codes
        assert "dialogue_pressure_weak" in reason_codes

    def test_local_short_contract_does_not_retry_only_for_literal_mission_misses(self):
        content = (
            "雨夜里，林七推开档案室的门，先把录音笔按在桌上。\n"
            "“你知道这份潮汐记录是谁换的。”他盯住门卫。\n"
            "门卫没有回答，只把钥匙往后缩。林七伸手去拿，走廊的灯忽然灭了。\n"
            "黑暗中有人在门外说：别开灯，你会看见不该看的人。"
        ) * 12
        should_retry, story_guard, reason_codes = PipelineOrchestrator._evaluate_first_draft_retry(
            content=content,
            violations=[],
            chapter_mission={
                "generation_source": "local_short_chapter_contract",
                "dialogue_strategy": {"purpose": ["用对话或行动推进信息与主动权变化"]},
                "scene_list": [{
                    "goal": "让主角立刻面对与本章目标直接相关的阻碍或反制",
                    "conflict": "让主角立刻面对与本章目标直接相关的阻碍或反制",
                    "turn": "行动或对话必须改变已知信息、主动权或风险",
                }],
            },
            target_word_count=1200,
            min_word_count=900,
        )

        assert story_guard["mission_hit_count"] == 0
        assert "mission_progression_weak" not in reason_codes
        assert "scene_fulfillment_weak" not in reason_codes
        assert should_retry is False

    def test_local_short_contract_defers_under_length_repair_to_continuation(self):
        content = (
            "雨夜里，林七推开档案室的门，先把录音笔按在桌上。\n"
            "“你知道这份潮汐记录是谁换的。”他盯住门卫。\n"
            "门卫没有回答，只把钥匙往后缩。林七伸手去拿，走廊的灯忽然灭了。\n"
            "黑暗中有人在门外说：别开灯，你会看见不该看的人。\n"
        ) * 7
        should_retry, _, reason_codes = PipelineOrchestrator._evaluate_first_draft_retry(
            content=content,
            violations=[],
            chapter_mission={
                "generation_source": "local_short_chapter_contract",
                "dialogue_strategy": {"purpose": ["用对话或行动推进信息与主动权变化"]},
                "scene_list": [{"goal": "取得记录", "conflict": "门卫反制", "turn": "灯灭", "end_hook": "门外威胁"}],
            },
            target_word_count=2200,
            min_word_count=1800,
        )

        assert "word_count_far_below_target" not in reason_codes
        assert should_retry is False

    def test_generated_prose_normalization_extracts_json_continuation_without_envelope(self):
        prose = PipelineOrchestrator._normalize_generated_prose(
            '<think>忽略</think>\n```json\n{"continuation":"雨里有人敲门。"}\n```'
        )

        assert prose == "雨里有人敲门。"
        assert "continuation" not in prose

    def test_generated_prose_normalization_keeps_bracketed_story_text(self):
        prose = PipelineOrchestrator._normalize_generated_prose(
            "[草稿]\n雨没停。顾沉推开门，看见火光沿着墙根逼近。"
        )

        assert prose.startswith("[草稿]")
        assert "顾沉推开门" in prose

    def test_generation_meta_leakage_is_rejected_but_normal_prose_is_clean(self):
        leaked = "The user wants me to write Chapter 1. 我们需要续写至少810字。"
        assert "The user wants" in PipelineOrchestrator._detect_generation_meta_leakage(leaked)
        assert "我们需要续写" in PipelineOrchestrator._detect_generation_meta_leakage(leaked)
        assert PipelineOrchestrator._detect_generation_meta_leakage("门外传来三声敲门，林七握紧了钥匙。") == []

    def test_fallback_select_best_version_prefers_story_progression_over_raw_length(self):
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "continuity_anchor": {
                "inherit_from_previous": ["承接门外脚步声"],
                "deliver_to_next": ["把危险递给下一章"],
            },
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        long_but_empty = {
            "content": ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 120),
            "metadata": {},
        }
        shorter_but_progressive = {
            "content": (
                "门外脚步声一停，林七抬眼盯住对面。\n"
                "“你还想装到什么时候？”他开口就是试探。\n"
                "对方拒绝回答，只把杯盏轻轻一扣，语气却更冷。\n"
                "林七顺势逼问真相，步步压迫，想把上一章埋下的疑点撬开。\n"
                "谁知对方突然翻脸，桌角猛地一震。\n"
                "门外传来脚步声？林七这才意识到，危险已经递到了下一章。"
            ),
            "metadata": {},
        }

        best_index, summary = PipelineOrchestrator._fallback_select_best_version(
            [long_but_empty, shorter_but_progressive],
            chapter_mission=chapter_mission,
        )

        assert best_index == 1
        assert summary["strategy"] == "heuristic_story_progression_guardrails"
        assert summary["candidates"][0]["mission_hit_count"] >= summary["candidates"][1]["mission_hit_count"]
        assert summary["candidates"][0]["expected_dialogue"] is True

    def test_ai_review_input_includes_structured_longform_excerpts(self):
        service = AIReviewService(llm_service=None, prompt_service=None)
        version = (
            "开" * 1600 + "\n\n"
            + "“你到底知道什么？”林七盯着对方。\n对方却只是冷笑，不肯回答。" * 10 + "\n\n"
            + "中" * 1600 + "\n\n"
            + "谁知门外脚步声忽然停住。" * 10 + "\n\n"
            + "尾" * 1600
        )

        review_input = service._build_review_input([version], {"chapter_purpose": "测试"})

        assert "[中段片段]" in review_input
        assert "[首个冲突片段]" in review_input
        assert "[最长对话片段]" in review_input
        assert "[关键转折片段]" in review_input
        assert "中" * 50 in review_input

    def test_should_run_enrichment_when_far_below_target_even_if_minimum_met(self):
        should_enrich, effective_min = PipelineOrchestrator._should_run_enrichment(
            2500,
            target_word_count=3200,
            min_word_count=2400,
        )
        assert should_enrich is True
        assert effective_min == 2400

        should_enrich, effective_min = PipelineOrchestrator._should_run_enrichment(
            3000,
            target_word_count=3200,
            min_word_count=2400,
        )
        assert should_enrich is False
        assert effective_min == 2400

        should_enrich, effective_min = PipelineOrchestrator._should_run_enrichment(
            2200,
            target_word_count=3200,
            min_word_count=2400,
        )
        assert should_enrich is True
        assert effective_min == 2400

    def test_structural_quality_gate_records_self_critique_exemption_observability(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique": {"final_score": 82, "critical_count": 0, "major_count": 0},
                "story_progression_guard": {
                    "word_count": 2400,
                    "dialogue_marker_count": 12,
                    "mission_hit_count": 4,
                    "scene_count": 2,
                    "scene_fulfillment_rate": 1.0,
                    "scene_structure_rate": 1.0,
                    "dialogue_changes_state": True,
                    "ending_pressure_passed": False,
                    "event_density_passed": False,
                    "state_change_interval_passed": True,
                    "static_description_risk": False,
                },
            }
        )

        assert gate["exemptions"] == ["ending_pressure_missing", "event_density_weak"]
        assert gate["critique_exemption_applied"] == gate["exemptions"]

        guard = PipelineOrchestrator._attach_quality_gate_status_to_guard(
            {"quality_metric_snapshot": {}}, gate
        )
        assert guard["quality_metric_snapshot"]["critique_exemption_applied"] == gate["exemptions"]
        assert guard["quality_metric_snapshot"]["self_critique_final_score"] == 82
        assert guard["quality_metric_snapshot"]["self_critique_critical_count"] == 0
        assert guard["quality_metric_snapshot"]["self_critique_major_count"] == 0
        assert guard["quality_metric_snapshot"]["selected_critique_source"] == "self_critique"
        assert guard["quality_gate_summary"]["exemptions"] == gate["exemptions"]

    def test_structural_quality_gate_blocks_catastrophic_self_critique_and_consistency_failures(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique": {
                    "final_score": 28.9,
                    "critical_count": 4,
                    "major_count": 6,
                },
                "consistency": {
                    "auto_fix_applied": True,
                    "auto_fix_accepted": False,
                    "post_fix_check": {
                        "violations": [
                            {"severity": "critical", "description": "时间线重复回卷"},
                            {"severity": "major", "description": "名字前后不一致"},
                            {"severity": "major", "description": "设备前后不一致"},
                        ]
                    },
                },
            }
        )

        assert gate["passed"] is False
        assert gate["self_critique_final_score"] == 28.9
        assert gate["self_critique_critical_count"] == 4
        assert gate["consistency_unresolved_critical_count"] == 1
        assert gate["consistency_unresolved_major_count"] == 2
        blocker_codes = {item["code"] for item in gate["blockers"]}
        assert "critical_issues_remaining" in blocker_codes
        assert "critical_consistency_unresolved" in blocker_codes

    def test_structural_quality_gate_blocks_static_description_and_weak_progression(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique_after_consistency": {
                    "final_score": 83.5,
                    "critical_count": 0,
                    "major_count": 1,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "auto_fix_applied": True,
                    "auto_fix_accepted": True,
                    "post_fix_check": {
                        "violations": []
                    },
                },
                "story_progression_guard": {
                    "word_count": 2400,
                    "dialogue_marker_count": 0,
                    "mission_hit_count": 1,
                    "expected_dialogue": True,
                    "static_description_risk": True,
                },
            }
        )

        assert gate["passed"] is False
        blocker_codes = {item["code"] for item in gate["blockers"]}
        assert "static_description_risk" in blocker_codes
        assert "insufficient_dialogue_pressure" in blocker_codes
        assert "chapter_progression_weak" in blocker_codes

    def test_structural_quality_gate_allows_clean_post_consistency_result(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique_after_consistency": {
                    "final_score": 83.5,
                    "critical_count": 0,
                    "major_count": 1,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "auto_fix_applied": True,
                    "auto_fix_accepted": True,
                    "post_fix_check": {
                        "violations": []
                    },
                },
                "story_progression_guard": {
                    "word_count": 5200,
                    "dialogue_marker_count": 18,
                    "mission_hit_count": 5,
                    "expected_dialogue": True,
                    "static_description_risk": False,
                },
            }
        )

        assert gate["passed"] is True
        assert gate["blockers"] == []
        assert gate["consistency_unresolved_count"] == 0

    def test_structural_quality_gate_does_not_block_scene_keyword_miss_when_other_signals_pass(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique_after_consistency": {
                    "final_score": 82.0,
                    "critical_count": 0,
                    "major_count": 1,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "post_fix_check": {"violations": []},
                },
                "story_progression_guard": {
                    "word_count": 1822,
                    "dialogue_marker_count": 28,
                    "mission_hit_count": 5,
                    "expected_dialogue": True,
                    "static_description_risk": False,
                    "scene_count": 3,
                    "scene_fulfillment_rate": 0.3333,
                    "dialogue_changes_state": True,
                    "ending_pressure_passed": True,
                },
            }
        )

        assert gate["passed"] is True
        assert "scene_fulfillment_weak" not in {item["code"] for item in gate["blockers"]}
        assert gate["quality_issue_summary"]["passed"] is True

    def test_structural_quality_gate_allows_live_run_scene_false_negative_when_story_signals_are_strong(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique_after_consistency": {
                    "final_score": 75.0,
                    "critical_count": 0,
                    "major_count": 6,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "post_fix_check": {"violations": []},
                },
                "story_progression_guard": {
                    "word_count": 3534,
                    "dialogue_marker_count": 92,
                    "mission_hit_count": 3,
                    "expected_dialogue": True,
                    "static_description_risk": False,
                    "scene_count": 3,
                    "scene_fulfillment_rate": 0.3333,
                    "dialogue_changes_state": True,
                    "ending_pressure_passed": True,
                },
            }
        )

        assert gate["passed"] is True
        assert "scene_fulfillment_weak" not in {item["code"] for item in gate["blockers"]}

    def test_structural_quality_gate_uses_positive_ai_review_as_cross_check_for_scene_keyword_miss(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "ai_review": {
                    "evaluation": "这是完成度较高的正式候选稿，基本兑现了导演脚本；对话改变局势，结尾把危险压给下一章，能直接上正稿。",
                    "status": "single_version_reviewed",
                },
                "self_critique_after_consistency": {
                    "final_score": 79.5,
                    "critical_count": 0,
                    "major_count": 6,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "post_fix_check": {"violations": []},
                },
                "story_progression_guard": {
                    "word_count": 3459,
                    "dialogue_marker_count": 118,
                    "guardrail_violation_count": 1,
                    "mission_hit_count": 2,
                    "expected_dialogue": True,
                    "ending_hook_detected": True,
                    "static_description_risk": False,
                    "scene_fulfillment_rate": 0.3333,
                    "fulfilled_scene_count": 1,
                    "scene_count": 3,
                    "dialogue_changes_state": True,
                    "dialogue_state_change_markers": 12,
                    "ending_pressure_passed": True,
                },
            }
        )

        assert gate["passed"] is True
        assert "scene_fulfillment_weak" not in {item["code"] for item in gate["blockers"]}

    def test_structural_quality_gate_allows_semantic_scene_evidence_when_keyword_hits_miss(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "ai_review": {
                    "evaluation": (
                        "这版结构兑现度高，四场戏推进清晰：问价、抬价、脱身、手札显字，"
                        "每一段对话都在改变筹码关系，结尾也把潜入听潮祠的压力递给下一章。"
                    ),
                    "status": "single_version_reviewed",
                },
                "self_critique_after_consistency": {
                    "final_score": 75.0,
                    "critical_count": 0,
                    "major_count": 6,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "post_fix_check": {"violations": []},
                },
                "story_progression_guard": {
                    "word_count": 4213,
                    "dialogue_marker_count": 138,
                    "mission_hit_count": 0,
                    "expected_dialogue": True,
                    "ending_hook_detected": True,
                    "static_description_risk": False,
                    "scene_fulfillment_rate": 0.25,
                    "fulfilled_scene_count": 1,
                    "scene_count": 4,
                    "dialogue_changes_state": True,
                    "dialogue_state_change_markers": 11,
                    "ending_pressure_passed": True,
                    "event_density_passed": True,
                    "state_change_interval_passed": True,
                },
            }
        )

        assert gate["passed"] is True
        assert "scene_fulfillment_weak" not in {item["code"] for item in gate["blockers"]}

    def test_ending_pressure_recognizes_semantic_cliffhanger_without_punctuation(self):
        """结尾没有任何问号叹号时，靠中文实质压力词也必须判出章末压力。
        断言只看语义命中数量，不绑定某部小说的专有词（原先绑「见了地」「旧南渠」，换题材就失效）。"""
        content = ("沈砚把账页重新压平，逼问账册真相，旧案的线索被一点点推到桌面上。" * 80)
        content += "顾栖川看着他，只说了一句：这笔账再翻下去，真会死人。"

        guard = PipelineOrchestrator._score_story_quality_candidate(
            content=content,
            violations=[],
            chapter_mission={
                "continuity_anchor": {"deliver_to_next": ["账册"]},
                "scene_list": [{"goal": "逼问账册真相", "conflict": "对方试图遮掩", "turn": "转去追查上游"}],
            },
        )

        assert guard["ending_pressure_passed"] is True
        assert guard["ending_pressure"]["ending_semantic_hit_count"] >= 1
        assert guard["ending_pressure"]["ending_weak_hit_count"] == 0

    def test_structural_quality_gate_does_not_block_progression_keyword_miss_when_strong_signals_pass(self):
        gate = PipelineOrchestrator._build_structural_quality_gate(
            {
                "self_critique_after_consistency": {
                    "final_score": 78.3,
                    "critical_count": 0,
                    "major_count": 6,
                },
                "consistency_repair": {
                    "is_consistent": True,
                    "post_fix_check": {"violations": []},
                },
                "story_progression_guard": {
                    "word_count": 3009,
                    "dialogue_marker_count": 38,
                    "mission_hit_count": 0,
                    "expected_dialogue": True,
                    "static_description_risk": False,
                    "dialogue_changes_state": True,
                    "ending_pressure_passed": True,
                    "scene_count": 4,
                    "scene_fulfillment_rate": 0.0,
                },
            }
        )

        blocker_codes = {item["code"] for item in gate["blockers"]}
        assert "chapter_progression_weak" not in blocker_codes
        assert gate["quality_issue_summary"]["passed"] is True

    def test_structural_quality_gate_recomputes_story_progression_after_enrichment_like_revision(self):
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        base_summaries = {
            "self_critique_after_consistency": {
                "final_score": 83.5,
                "critical_count": 0,
                "major_count": 1,
            },
            "consistency_repair": {
                "is_consistent": True,
                "auto_fix_applied": True,
                "auto_fix_accepted": True,
                "post_fix_check": {
                    "violations": []
                },
            },
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        repaired_content = (
            "门外脚步声一停，林七抬眼盯住对面。\n"
            "“你还想装到什么时候？”他先试探，再压住对方的退路。\n"
            "对方拒绝回答，只把杯盏轻轻一扣，像是故意把沉默顶到林七脸上。\n"
            "林七顺势逼问真相，把上一章埋下的疑点一条条摁回桌面。\n"
            "谁知对方突然翻脸，桌角猛地一震，局面当场反转。\n"
            "门外传来脚步声，林七这才意识到，危险已经递到了下一章。"
        )

        weak_summaries, weak_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries=base_summaries,
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            story_guard_key="story_progression_guard_pre_enrichment",
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        repaired_summaries, repaired_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries=weak_summaries,
            content=repaired_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        assert weak_gate["passed"] is False
        weak_blocker_codes = {item["code"] for item in weak_gate["blockers"]}
        assert "static_description_risk" in weak_blocker_codes
        assert repaired_gate["passed"] is True
        assert repaired_summaries["story_progression_guard"]["mission_hit_count"] >= 2
        assert repaired_summaries["story_progression_guard_pre_enrichment"]["static_description_risk"] is True

    @pytest.mark.asyncio
    async def test_structural_gate_repair_adopts_revision_that_fixes_progression(self, monkeypatch):
        """结构质量门失败后，若定向修复能改善结构并通过重评，应采纳修复内容而非直接拦截。"""
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        repaired_content = (
            "门外脚步声一停，林七抬眼盯住对面。\n"
            "“你还想装到什么时候？”他先试探，再压住对方的退路。\n"
            "对方拒绝回答，只把杯盏轻轻一扣，像是故意把沉默顶到林七脸上。\n"
            "林七顺势逼问真相，把上一章埋下的疑点一条条摁回桌面。\n"
            "谁知对方突然翻脸，桌角猛地一震，局面当场反转。\n"
            "门外传来脚步声，林七这才意识到，危险已经递到了下一章。"
        )
        review_summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        assert gate["passed"] is False

        captured = {}

        async def fake_revise(self, chapter_content=None, issues=None, **kwargs):
            captured["issues"] = issues
            captured["chapter_content"] = chapter_content
            return repaired_content

        monkeypatch.setattr(SelfCritiqueService, "revise_chapter", fake_revise)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.session = None
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        result = await orchestrator._attempt_structural_gate_repair(
            best_content=weak_content,
            review_summaries=review_summaries,
            structural_quality_gate=gate,
            guardrail_violations=[],
            chapter_mission=chapter_mission,
            repair_context={"chapter_mission": chapter_mission},
            active_config=PipelineConfig(enable_self_critique=True, min_word_count=1),
            user_id=1,
        )

        assert result is not None
        assert result["content"] == repaired_content
        assert result["structural_quality_gate"]["passed"] is True
        assert result["review_summaries"]["story_progression_guard"]["mission_hit_count"] >= 2
        # 定向修复必须拿到结构问题清单，而不是空手调用
        assert captured["issues"], "结构定向修复应收到结构问题清单"
        assert captured["chapter_content"] == weak_content

    @pytest.mark.asyncio
    async def test_structural_gate_repair_keeps_diagnostics_when_no_improvement(self, monkeypatch):
        """修复毫无改善时不能采纳，但**必须留下诊断**。

        批 5（T-22）之前这里直接 `return None`，调用方只拿到原始 gate 的 codes，
        用户面对的是一个「无解的 422」——看不出系统到底试过没试过。
        现在改成：始终返回结构化诊断，用 `adopted` 表达是否采纳。
        """
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        still_weak_content = ("月光冷冷洒落，庭院里的石阶泛着湿意，檐角的铜铃始终一动不动地悬着。" * 140)
        review_summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        assert gate["passed"] is False

        call_count = {"n": 0}

        async def fake_revise(self, chapter_content=None, issues=None, **kwargs):
            call_count["n"] += 1
            return still_weak_content

        monkeypatch.setattr(SelfCritiqueService, "revise_chapter", fake_revise)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.session = None
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        result = await orchestrator._attempt_structural_gate_repair(
            best_content=weak_content,
            review_summaries=review_summaries,
            structural_quality_gate=gate,
            guardrail_violations=[],
            chapter_mission=chapter_mission,
            repair_context={"chapter_mission": chapter_mission},
            active_config=PipelineConfig(enable_self_critique=True, min_word_count=1),
            user_id=1,
        )

        assert result is not None, "修复失败也要返回诊断，不能让调用方只拿到原始 gate"
        assert result["adopted"] is False
        summary = result["repair_summary"]
        assert summary["repair_attempted"] is True
        assert summary["repair_outcome"] == "unchanged"
        assert summary["repair_rounds"] == PipelineOrchestrator.STRUCTURAL_GATE_REPAIR_MAX_ROUNDS
        # 两侧 codes 都要留档，前端才能显示「已尝试自动修复，仍有 N 项未达标」
        assert set(summary["issue_codes_before"]) == set(gate["quality_issue_codes"])
        assert set(summary["issue_codes_after"]) == set(gate["quality_issue_codes"])
        assert summary["remaining_issue_count"] == len(gate["quality_issue_codes"])
        # 没有改善就不能回写正文
        assert "content" not in result

    @pytest.mark.asyncio
    async def test_structural_gate_repair_adopts_partial_improvement(self, monkeypatch):
        """**T-22 的核心**：blocker 从 7 条降到 1 条但仍未通过门时，必须采纳这次修复。

        旧实现只认「重评完全通过」，5 个 blocker 修到剩 1 个也整章丢弃走 422。
        拒稿对用户价值为零，带标记的部分改善至少可用且可见（D-21 风险段的有意权衡）。
        改善判据是**严格子集收缩**：数量下降且不能引入新的 code 类型，
        否则「换了一种毛病」也会被算成改善（反例见下一条测试）。
        """
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        # 实测：codes 从 7 条（WEAK）降到 1 条（只剩 ending_pressure_missing），仍不通过门。
        partially_fixed = BAD_FLAT_CLOSURE
        review_summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        assert len(gate["quality_issue_codes"]) >= 3, "样本前提：起点必须有多个 blocker"

        async def fake_revise(self, chapter_content=None, issues=None, **kwargs):
            return partially_fixed

        monkeypatch.setattr(SelfCritiqueService, "revise_chapter", fake_revise)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.session = None
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        result = await orchestrator._attempt_structural_gate_repair(
            best_content=weak_content,
            review_summaries=review_summaries,
            structural_quality_gate=gate,
            guardrail_violations=[],
            chapter_mission=chapter_mission,
            repair_context={"chapter_mission": chapter_mission},
            active_config=PipelineConfig(enable_self_critique=True, min_word_count=1),
            user_id=1,
        )

        assert result is not None
        assert result["adopted"] is True
        assert result["content"] == partially_fixed
        # 部分改善：采纳内容，但门仍然是不通过，不能假装过门
        assert result["structural_quality_gate"]["passed"] is False
        summary = result["repair_summary"]
        assert summary["repair_outcome"] == "improved"
        assert summary["remaining_issue_count"] < len(summary["issue_codes_before"])
        assert summary["remaining_issue_count"] > 0

    @pytest.mark.asyncio
    async def test_structural_gate_repair_rejects_traded_issue_types(self, monkeypatch):
        """反例：blocker 数量变少但**引入了新的 code 类型**，不算改善。

        实测 `## 场景 1｜开场` 残留头的正文只有 1 条 blocker（`chapter_artifact_markers`），
        数量比起点的 7 条少得多，但那是一种全新的毛病。只看数量会把「换病」当成「治病」，
        修复循环就会朝着错误方向收敛。
        """
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        traded_content = "## 场景 1｜开场\n\n" + GOOD_DRAMATIC
        review_summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        async def fake_revise(self, chapter_content=None, issues=None, **kwargs):
            return traded_content

        monkeypatch.setattr(SelfCritiqueService, "revise_chapter", fake_revise)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.session = None
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        result = await orchestrator._attempt_structural_gate_repair(
            best_content=weak_content,
            review_summaries=review_summaries,
            structural_quality_gate=gate,
            guardrail_violations=[],
            chapter_mission=chapter_mission,
            repair_context={"chapter_mission": chapter_mission},
            active_config=PipelineConfig(enable_self_critique=True, min_word_count=1),
            user_id=1,
        )

        assert result is not None
        assert result["adopted"] is False, "引入新 code 类型不算改善，即使总数更少"
        summary = result["repair_summary"]
        assert summary["repair_outcome"] == "unchanged"
        assert "chapter_artifact_markers" in summary["new_issue_codes"]
        assert "content" not in result

    @pytest.mark.asyncio
    async def test_structural_gate_repair_stops_at_two_rounds(self, monkeypatch):
        """修复上限硬编码为 2 轮，且第 2 轮必须基于第 1 轮的产物继续修。

        每一轮都是一次 LLM 调用，成本与耗时线性增长（2.4 成本约束），所以不做配置项。
        第 2 轮若能让门通过，就应该在第 2 轮停下并采纳。
        """
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        calls = []

        async def fake_revise(self, chapter_content=None, issues=None, **kwargs):
            calls.append(chapter_content)
            # 第 1 轮只修到部分改善，第 2 轮才真正过门
            return BAD_FLAT_CLOSURE if len(calls) == 1 else GOOD_DRAMATIC

        monkeypatch.setattr(SelfCritiqueService, "revise_chapter", fake_revise)

        review_summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.session = None
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        result = await orchestrator._attempt_structural_gate_repair(
            best_content=weak_content,
            review_summaries=review_summaries,
            structural_quality_gate=gate,
            guardrail_violations=[],
            chapter_mission=chapter_mission,
            repair_context={"chapter_mission": chapter_mission},
            active_config=PipelineConfig(enable_self_critique=True, min_word_count=1),
            user_id=1,
        )

        assert PipelineOrchestrator.STRUCTURAL_GATE_REPAIR_MAX_ROUNDS == 2, "上限必须是硬编码的 2"
        assert len(calls) == 2, f"应当正好修复 2 轮，实际 {len(calls)} 轮"
        # 第 2 轮必须拿第 1 轮的产物做输入，否则等于两次独立重试而不是迭代修复
        assert calls[0] == weak_content
        assert calls[1] == BAD_FLAT_CLOSURE
        assert result is not None
        assert result["adopted"] is True
        assert result["content"] == GOOD_DRAMATIC
        assert result["structural_quality_gate"]["passed"] is True
        summary = result["repair_summary"]
        assert summary["repair_outcome"] == "passed"
        assert summary["repair_rounds"] == 2
        assert summary["issue_codes_after"] == []
        assert summary["remaining_issue_count"] == 0

    @pytest.mark.asyncio
    async def test_structural_gate_repair_skipped_when_self_critique_disabled(self, monkeypatch):
        """低配 preset（enable_self_critique=False）不做结构定向修复，保持原有拦截语义。"""
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探"]},
            "scene_list": [{"goal": "逼问真相", "conflict": "对方拒绝回答", "end_hook": "脚步声"}],
        }
        weak_content = ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140)
        review_summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=weak_content,
            violations=[],
            chapter_mission=chapter_mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        called = {"revise": False}

        async def fake_revise(self, chapter_content=None, issues=None, **kwargs):
            called["revise"] = True
            return weak_content

        monkeypatch.setattr(SelfCritiqueService, "revise_chapter", fake_revise)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.session = None
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        result = await orchestrator._attempt_structural_gate_repair(
            best_content=weak_content,
            review_summaries=review_summaries,
            structural_quality_gate=gate,
            guardrail_violations=[],
            chapter_mission=chapter_mission,
            repair_context={"chapter_mission": chapter_mission},
            active_config=PipelineConfig(enable_self_critique=False),
            user_id=1,
        )

        # 跳过也要可观测：前端要能区分「试过但没修好」和「这个 preset 压根没试」
        assert result is not None
        assert result["adopted"] is False
        summary = result["repair_summary"]
        assert summary["repair_attempted"] is False
        assert summary["repair_outcome"] == "skipped"
        assert summary["repair_skipped_reason"] == "self_critique_disabled"
        assert summary["repair_rounds"] == 0
        assert called["revise"] is False

    def test_structural_gate_repair_is_wired_into_generate_chapter(self):
        """接线回归防护：generate_chapter 的两处结构质量门失败分支都必须先尝试定向修复，
        再走落库拒稿；且修复成功后必须回写 best_content 与 structural_quality_gate，
        否则闸门会退回“只评分不自愈”，或改好了却因未回写 gate 仍被误拦截。

        批 5（T-22）之后返回值语义变了：非 None 不再等于「已采纳」，必须看 `adopted`；
        而 `repair_summary` 无论采纳与否都要落进 runtime_metadata。
        """
        import inspect

        source = inspect.getsource(PipelineOrchestrator.generate_chapter)

        # 早期门（enrichment 关闭路径）与最终必经门两处都接入定向修复
        assert source.count("_attempt_structural_gate_repair(") == 2
        # 采纳与否必须由 adopted 决定，不能再用 `is not None` 当采纳信号
        assert source.count('gate_repair_result.get("adopted")') == 2
        assert source.count("if gate_repair_result is not None:") == 0
        # 修复成功后必须回写正文与闸门结论，否则修复不生效或误拦截
        assert source.count('best_content = gate_repair_result["content"]') == 2
        assert (
            source.count('structural_quality_gate = gate_repair_result["structural_quality_gate"]')
            == 2
        )
        # 未采纳也要留诊断：两处都要把 repair_summary 记进 runtime_metadata
        assert source.count('runtime_metadata.setdefault("quality_gate_repairs", [])') == 2
        # 定向修复必须发生在落库拒稿（_persist_quality_gate_blocked_versions）之前
        first_repair = source.index("_attempt_structural_gate_repair(")
        first_persist = source.index("_persist_quality_gate_blocked_versions(")
        assert first_repair < first_persist

        assert source.count("quality_gate_repairs=runtime_metadata.get(\"quality_gate_repairs\")") == 2

    @pytest.mark.asyncio
    async def test_run_ai_review_overrides_static_ai_choice_with_progressive_fallback(self, monkeypatch):
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        weak_candidate = {
            "content": ("夜色沉沉，风从长廊尽头缓慢漫过，墙上的灯影被一寸寸拖长。" * 140),
            "metadata": {},
        }
        strong_candidate = {
            "content": (
                "门外脚步声一停，林七抬眼盯住对面。\n"
                "“你还想装到什么时候？”他开口就是试探。\n"
                "对方拒绝回答，只把杯盏轻轻一扣，语气却更冷。\n"
                "林七顺势逼问真相，步步压迫，想把上一章埋下的疑点撬开。\n"
                "谁知对方突然翻脸，桌角猛地一震。\n"
                "门外传来脚步声？林七这才意识到，危险已经递到了下一章。"
            ),
            "metadata": {},
        }

        async def fake_review_versions(self, versions, chapter_mission=None, user_id=None):
            return ReviewResult(
                best_version_index=0,
                scores={"immersion": 72, "pacing": 58, "hook": 55, "character": 68},
                overall_evaluation="文气稳定，但推进偏弱。",
                critical_flaws=[],
                refinement_suggestions="加强冲突推进",
                final_recommendation="保留版本0",
            )

        monkeypatch.setattr(AIReviewService, "review_versions", fake_review_versions)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        best_index, summary = await orchestrator._run_ai_review(
            versions=[weak_candidate, strong_candidate],
            chapter_mission=chapter_mission,
            user_id=1,
        )

        assert best_index == 1
        assert summary["status"] == "ai_review_overridden_by_story_guard"
        assert summary["ai_original_best_index"] == 0
        assert summary["selection_override"]["fallback_best_index"] == 1
        assert weak_candidate["metadata"]["ai_review"]["ai_original_best"] is True
        assert strong_candidate["metadata"]["ai_review"]["is_best"] is True
        assert weak_candidate["metadata"]["ai_review"]["heuristic_rank"] == 2
        assert strong_candidate["metadata"]["ai_review"]["heuristic_rank"] == 1
        assert strong_candidate["metadata"]["ai_review"]["heuristic_best"] is True
        assert isinstance(strong_candidate["metadata"]["ai_review"]["heuristic_score"], int)

    @pytest.mark.asyncio
    async def test_run_ai_review_keeps_ai_choice_when_story_guard_has_no_clear_reason_to_override(self, monkeypatch):
        chapter_mission = {
            "chapter_purpose": "逼问真相",
            "dialogue_strategy": {"purpose": ["试探", "压迫"]},
            "scene_list": [
                {
                    "goal": "逼问真相",
                    "conflict": "对方拒绝回答",
                    "turn": "对方突然翻脸",
                    "end_hook": "门外传来脚步声",
                }
            ],
        }
        candidate_a = {
            "content": (
                "门外脚步声一停，林七抬眼盯住对面。\n"
                "“你还想装到什么时候？”他先开口试探。\n"
                "对方不答，只冷笑一声。\n"
                "林七逼问真相，桌上的火漆印也跟着被扯开。\n"
                "门外忽然又有动静，局势继续收紧。"
            ),
            "metadata": {},
        }
        candidate_b = {
            "content": (
                "林七没有退，仍盯着对面。\n"
                "“那就别怪我继续问。”\n"
                "对方敲了敲杯沿，拒绝回答。\n"
                "气氛更紧，门外脚步声也越来越近。"
            ),
            "metadata": {},
        }

        async def fake_review_versions(self, versions, chapter_mission=None, user_id=None):
            return ReviewResult(
                best_version_index=0,
                scores={"immersion": 80, "pacing": 78, "hook": 76, "character": 75},
                overall_evaluation="版本0更完整。",
                critical_flaws=[],
                refinement_suggestions="保持当前方向",
                final_recommendation="保留版本0",
            )

        monkeypatch.setattr(AIReviewService, "review_versions", fake_review_versions)

        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator.llm_service = None
        orchestrator.prompt_service = None

        best_index, summary = await orchestrator._run_ai_review(
            versions=[candidate_a, candidate_b],
            chapter_mission=chapter_mission,
            user_id=1,
        )

        assert best_index == 0
        assert summary["status"] == "passed"
        assert summary["selection_override"] is None

    def test_reader_polish_triggers_when_continue_ratio_is_low_even_above_hard_score_floor(self):
        feedback = {
            "overall_score": 71,
            "abandon_risks": [],
            "diagnostic_summary": {
                "continue_ratio": 0.33,
                "priority_issues": [
                    {"problem": "对白攻防太弱"},
                    {"problem": "推进发散"},
                ],
            },
            "reader_stage_decision": {
                "passed": True,
                "continue_ratio": 0.33,
                "top_issue_count": 2,
            },
        }
        issues = [{"problem": "对白攻防太弱"}, {"problem": "推进发散"}]

        should_run, decision = PipelineOrchestrator._should_run_reader_polish(feedback, issues)

        assert should_run is True
        assert decision["reason"] == "low_continue_ratio"

    def test_reader_polish_skips_when_reader_feedback_is_within_tolerance(self):
        feedback = {
            "overall_score": 78,
            "abandon_risks": [],
            "diagnostic_summary": {
                "continue_ratio": 1.0,
                "priority_issues": [{"problem": "个别句子略平"}],
            },
            "reader_stage_decision": {
                "passed": True,
                "continue_ratio": 1.0,
                "top_issue_count": 1,
            },
        }
        issues = [{"problem": "个别句子略平"}]

        should_run, decision = PipelineOrchestrator._should_run_reader_polish(feedback, issues)

        assert should_run is False
        assert decision["reason"] == "reader_feedback_within_tolerance"

    def test_ai_review_structure_map_flags_static_description_risk(self):
        service = AIReviewService(llm_service=None, prompt_service=None)
        long_static_version = (
            "夜色铺在长廊上，灯影一点一点拉长，空气里只有潮湿的石味。" * 80
            + "\n\n"
            + "墙面沉默，窗纸沉默，连风也沉默，所有细节都在原地停着。" * 80
            + "\n\n"
            + "“你到底隐瞒了什么？”林七逼问。"
            + "\n\n"
            + "对方却忽然笑了，门外脚步声同时逼近。"
        )

        payload = AIReviewService._build_excerpt_payload(long_static_version)
        review_input = service._build_review_input([long_static_version], {"chapter_purpose": "测试结构地图"})

        assert payload["progression_marker_count"] >= 3
        assert payload["static_description_risk"]["max_static_run"] >= 2
        assert payload["structure_map"]
        assert "[整章结构地图]" in review_input
        assert "推进标记" in review_input
        assert "静态段落" in review_input

    def test_ai_review_mission_carries_longform_context_and_patch_rules(self):
        package = LongformContextPackage(
            project_id="project-1",
            chapter_number=8,
            prompt_text="previous chapter ends with the salt mark burning",
            cast_plan=CastPlan(
                target_character_count=18,
                planned_character_count=12,
                chapter_focus_names=["Lin Qi", "Archivist"],
            ),
            foreshadowing_task=ForeshadowingChapterTask(
                must_resolve=[{"name": "door handle"}],
                should_reinforce=[{"name": "salt mark"}],
                avoid_forgetting=[{"name": "ledger swap"}],
            ),
            memory_digest={"recent": ["the rival knows only half the secret"]},
            timeline_digest={"latest": ["chapter 7 night"]},
        )

        mission = PipelineOrchestrator._build_ai_review_mission(
            chapter_mission={"chapter_purpose": "force a decision"},
            longform_context=package,
        )
        checklist = AIReviewService._format_mission_checklist(mission)

        assert mission["longform_review_context"]["cast_plan"]["chapter_focus_names"] == ["Lin Qi", "Archivist"]
        assert any("局部锚点补丁" in rule for rule in mission["review_quality_rules"])
        assert "Lin Qi" in checklist
        assert "must_resolve=1" in checklist
        assert "伏笔/线索账本" in checklist

    def test_story_quality_metrics_reject_all_description_sample(self):
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content="\n\n".join(
                [
                    "夜色铺在长廊上，灯影一点一点拉长，空气里只有潮湿的石味。" * 40,
                    "墙面沉默，窗纸沉默，连风也沉默，所有细节都在原地停着。" * 40,
                    "远处像有一层雾，雾里有旧日的影子，影子又像没有说出口的命运。" * 40,
                ]
            ),
            violations=[],
            chapter_mission={
                "chapter_purpose": "逼问真相",
                "dialogue_strategy": {"purpose": ["试探", "压迫"]},
                "scene_list": [{"goal": "逼问真相", "conflict": "对方拒绝", "turn": "局势反转", "end_hook": "脚步逼近"}],
            },
        )

        assert guard["static_description_risk"] is True
        assert guard["dialogue_changes_state"] is False
        assert guard["scene_fulfillment_rate"] < 0.5

    def test_story_quality_metrics_reward_scene_dialogue_and_ending_pressure(self):
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content=(
                "门外脚步声一停，林七立刻抬头，决定逼问真相。\n"
                "“你到底隐瞒了什么？”他盯住对方，先把证据按在桌上。\n"
                "对方拒绝回答，却用旧案威胁反制，局势第一次失控。\n"
                "林七继续逼问，对方终于改口，暴露自己是在拖延时间。\n"
                "下一刻，门外又传来脚步声，新的消息把危险递给下一章。"
            ),
            violations=[],
            chapter_mission={
                "chapter_purpose": "逼问真相",
                "continuity_anchor": {"deliver_to_next": ["危险递给下一章"]},
                "dialogue_strategy": {"purpose": ["试探", "压迫"]},
                "scene_list": [{"goal": "逼问真相", "conflict": "对方拒绝", "turn": "局势反转", "end_hook": "脚步逼近"}],
            },
        )

        assert guard["scene_fulfillment_rate"] >= 0.5
        assert guard["dialogue_changes_state"] is True
        assert guard["ending_pressure_passed"] is True
        assert guard["quality_metric_snapshot"]["scene_count"] == 1
        # T-14：这段正文只有 ~120 字，远低于 800 字评估下限。改造前这里断言的是
        # `is True`——那正是被修掉的谎报：没测过却报「密度达标」。现在是「未评估」。
        assert guard["event_density_passed"] is None
        assert guard["event_density_evaluated"] is False
        assert guard["event_density_skip_reason"] == "sample_too_short"

    def test_dialogue_state_guard_recognizes_concrete_revelation_choice_and_external_pressure(self):
        """真实短章不能因未复述任务书抽象词而被质量门误杀。"""
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content=(
                "“老周，东西呢？”顾晚舟推门问。\n"
                "“老周已经死了。”男人把纸袋推给她，“北街的人正在上楼。”\n"
                "“你要我怎么做？”\n"
                "“拿走，或者烧掉。选一个，我带你从消防通道离开。”\n"
                "顾晚舟把纸袋塞进外套，跟着他走。楼下有人喊：医院那边收到消息了吗？”"
            ),
            violations=[],
            chapter_mission={
                "generation_source": "local_short_chapter_contract",
                "dialogue_strategy": {"purpose": ["用对话推进主动权变化"]},
                "continuity_anchor": {"deliver_to_next": ["医院那边的消息"]},
                "scene_list": [{"goal": "取得清单", "conflict": "追兵上楼", "turn": "二选一", "end_hook": "医院消息"}],
            },
        )

        assert guard["dialogue_marker_count"] >= 4
        assert guard["dialogue_state_change_markers"] >= 2
        assert guard["dialogue_changes_state"] is True

    def test_ending_pressure_guard_recognizes_countdown_after_external_threat(self):
        result = PipelineOrchestrator._evaluate_ending_pressure(
            "门外传来物业巡楼的声音。许晚宁看向陈朔，唇形无声地数：三、二。",
            chapter_mission={"continuity_anchor": {"deliver_to_next": []}},
        )

        assert result["ending_pressure_passed"] is True
        assert "倒计时" in result["ending_pressure_hits"]

    def test_story_quality_metrics_reject_keyword_padded_low_event_density(self):
        quiet_padding = "玉玺在北门的旧账旁沉默，赤伞和血契像旧纸上的灰影。" * 180
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content="\n\n".join(
                [
                    "玉玺、北门、旧账、赤伞、血契都被摆在案上。",
                    quiet_padding,
                    quiet_padding,
                    "玉玺仍在，北门仍在，旧账仍在，赤伞和血契仍在。",
                ]
            ),
            violations=[],
            chapter_mission={
                "chapter_purpose": "查明玉玺与北门旧账的关联",
                "scene_list": [
                    {
                        "goal": "玉玺",
                        "conflict": "北门旧账",
                        "turn": "赤伞",
                        "outcome": "血契",
                        "end_hook": "旧账",
                    }
                ],
            },
        )

        assert guard["scene_fulfillment_rate"] >= 0.5
        assert guard["event_density_passed"] is False
        assert guard["state_change_interval_passed"] is False
        assert "event_density_weak" in guard["quality_metric_snapshot"]["quality_issue_codes"]

    def test_event_density_allows_dense_progression_despite_local_plain_run(self):
        plain_run = "潮湿木板压着旧坞的水气，风灯在绳索旁一寸寸发白。" * 8
        progression_units = []
        for index in range(16):
            progression_units.append(
                f"第{index + 1}轮，沈文朝先逼问聂沧澜，聂沧澜拒绝交底，"
                "季阿七立刻反制封索，失税旧账暴露新证据，局势转而升级。"
            )
        text = "\n".join([progression_units[0], plain_run, *progression_units[1:]])

        density = PipelineOrchestrator._evaluate_event_density(text, word_count=len("".join(text.split())))

        assert density["max_plain_unit_run"] > 5
        assert density["event_density_passed"] is True
        assert density["state_change_interval_passed"] is True

    def test_first_draft_retry_triggers_for_long_chapter_low_event_density(self):
        inert_block = "玉玺在北门旧账旁沉默，赤伞压着血契，灯影沿着纸面缓慢移动。" * 260
        should_retry, story_guard, reason_codes = PipelineOrchestrator._evaluate_first_draft_retry(
            content="\n\n".join(
                [
                    "玉玺、北门、旧账、赤伞、血契同时出现。",
                    inert_block,
                    inert_block,
                    "北门旧账和赤伞血契还在原处。",
                ]
            ),
            violations=[],
            chapter_mission={
                "chapter_purpose": "查明玉玺与北门旧账的关联",
                "scene_list": [
                    {
                        "goal": "核对玉玺",
                        "conflict": "北门旧账被遮掩",
                        "turn": "赤伞牵出血契",
                        "outcome": "血契暴露新风险",
                        "end_hook": "北门旧账没有结束",
                    },
                    {
                        "goal": "追问赤伞来历",
                        "conflict": "证人拒绝回答",
                        "turn": "血契指向新势力",
                        "outcome": "主角必须改变下一步选择",
                    },
                ],
            },
            target_word_count=9000,
            min_word_count=8100,
        )

        assert should_retry is True
        assert story_guard["long_chapter_density_passed"] is False
        assert "event_density_weak" in reason_codes
        assert "long_chapter_event_density_weak" in reason_codes

    def test_story_quality_metrics_accept_dense_scene_sequel_progression(self):
        progressive_units = []
        for index in range(18):
            progressive_units.append(
                f"第{index + 1}轮，林七先逼问玉玺来源，对方拒绝回答，他立刻拿出北门旧账反制，"
                f"证据让赤伞线索暴露，局势转而升级，他必须改变下一步选择。"
            )
            progressive_units.append(
                f"短余波里，他意识到血契会带来代价，决定把风险压给下一章，而不是原地感慨。"
            )
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content="\n\n".join(progressive_units),
            violations=[],
            chapter_mission={
                "chapter_purpose": "查明玉玺与北门旧账的关联",
                "continuity_anchor": {"deliver_to_next": ["风险压给下一章"]},
                "dialogue_strategy": {"purpose": ["逼问", "反制"]},
                "scene_list": [
                    {
                        "goal": "逼问玉玺来源",
                        "conflict": "对方拒绝回答",
                        "turn": "北门旧账反制",
                        "outcome": "赤伞线索暴露",
                        "pressure_shift": "血契会带来代价",
                        "end_hook": "风险压给下一章",
                    }
                ],
            },
        )

        assert guard["event_density_passed"] is True
        assert guard["state_change_interval_passed"] is True
        assert guard["scene_structure_rate"] >= 1.0
        assert guard["quality_metric_snapshot"]["event_density_per_1000"] >= 1.0

    def test_structural_gate_accepts_dense_scene_evidence_when_structure_keywords_are_rephrased(self):
        # `* 5` 会把每个段落原样复制 5 遍。批 6 落地 T-10（重复段落检测）后，
        # 这样构造的样本自己就会触发 `repeated_paragraph_flood`（实测 4 个段落各 5 次、
        # 最长 48 字），测的就不再是「结构关键词被改写后仍然放行」了。
        # 加序数前缀让每轮的长段落各自唯一，与 `_grow` 的做法一致。
        _BLOCK = (
            "封索横在旧坞口，聂沧澜站在绳后。\n"
            "“跟我回听潮祠。”他说，“你父亲的旧案，我替你查。”\n"
            "沈文朝没有答应，先逼问：“查案，还是收印？”\n"
            "聂沧澜以父案为条件压迫他，季阿七立刻挡住刀柄。\n"
            "船板外有人递进失税旧账残页，盐商会也抛出价码，局势转而升级。\n"
            "沈文朝发现两边都只说半句，于是决定不跟任何一方走，先反向套话。\n"
            "雾中潮歌忽然响起，夜影替他们挡开追索，却不露真容。\n"
            "季阿七拒绝把夜影当成援手，沈文朝也意识到父亲手札警告被动摇。\n"
            "回到住处后，潮印映亮泡胀手札，旧痕指向听潮祠旧档夹层。\n"
            "章尾，潮宗缉印令落下，盐商会封锁水路，他只能在天亮前潜入听潮祠。"
        )
        _ROUND_PREFIXES = ("初", "次", "三", "四", "五")
        content = "".join(
            "\n".join(
                f"{prefix}、{line}" if len(re.sub(r"\s+", "", line)) >= 30 else line
                for line in _BLOCK.split("\n")
            )
            for prefix in _ROUND_PREFIXES
        )
        mission = {
            "chapter_purpose": "把旧坞封锁升级成三方争夺，主角通过手札夹层确认听潮祠旧档目标。",
            "suspense_hook": "潮宗缉印令与盐商会水路封锁同时落下，逼主角潜入听潮祠。",
            "continuity_anchor": {"deliver_to_next": ["潜入听潮祠", "缉印令", "水路封锁"]},
            "dialogue_strategy": {"purpose": ["逼问", "压迫", "反制"]},
            "scene_list": [
                {
                    "goal": "在旧坞封锁下保住自己与潮印",
                    "conflict": "聂沧澜以父案为条件控制主角",
                    "turn": "盐商会递进失税旧账残页",
                    "outcome": "主角不答应任何一方",
                    "bridge": "雾中潮歌夜影制造撤离窗口",
                    "end_hook": "潮歌夜影救场但不露真容",
                },
                {
                    "goal": "验证泡胀手札",
                    "conflict": "手札旧痕残缺且追索收紧",
                    "turn": "潮印映出听潮祠旧档夹层",
                    "outcome": "调查目标从沉鳞湾转向听潮祠",
                    "bridge": "缉印令与水路封锁压到下一章",
                    "end_hook": "天亮前潜入听潮祠",
                },
            ],
        }

        _, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={
                "self_critique": {"final_score": 76, "critical_count": 0, "major_count": 6},
                "consistency": {"violations": []},
            },
            content=content,
            violations=[],
            chapter_mission=mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        assert gate["passed"] is True

    def test_quality_gate_status_clears_rule_warnings_after_soft_pass(self):
        guard = {
            "quality_issue_codes": ["scene_fulfillment_weak"],
            "quality_issue_labels": ["场景兑现不足"],
            "quality_issue_summary": {
                "passed": False,
                "tone": "danger",
                "count": 1,
                "codes": ["scene_fulfillment_weak"],
                "labels": ["场景兑现不足"],
                "items": [{"code": "scene_fulfillment_weak"}],
            },
            "quality_metric_snapshot": {
                "quality_issue_codes": ["scene_fulfillment_weak"],
                "quality_issue_labels": ["场景兑现不足"],
                "quality_issue_summary": {
                    "passed": False,
                    "tone": "danger",
                    "count": 1,
                    "codes": ["scene_fulfillment_weak"],
                    "labels": ["场景兑现不足"],
                    "items": [{"code": "scene_fulfillment_weak"}],
                },
            },
        }

        normalized = PipelineOrchestrator._attach_quality_gate_status_to_guard(
            guard,
            {"passed": True, "quality_issue_codes": [], "quality_issue_labels": [], "blockers": []},
        )

        assert normalized["quality_gate_passed"] is True
        assert normalized["quality_issue_summary"]["passed"] is True
        assert normalized["quality_issue_codes"] == []
        assert normalized["quality_rule_warnings"]["codes"] == ["scene_fulfillment_weak"]

    def test_ending_pressure_recognizes_survival_risk_without_punctuation_hook(self):
        text = (
            "\u4ed6\u770b\u89c1\u9000\u6f6e\u7ebf\u6574\u9f50\u5f97\u50cf\u88ab\u7cbe\u786e\u4e08\u91cf\uff0c"
            "\u7901\u7f1d\u91cc\u8fd8\u5361\u7740\u4e00\u5757\u7edd\u975e\u73b0\u4ee3\u8239\u53ea\u80fd\u7559\u4e0b\u7684\u65e7\u6728\u7247\u3002"
            "\u82e5\u8fd8\u628a\u8fd9\u91cc\u5f53\u6210\u7b49\u6551\u63f4\u7684\u6d77\u96be\u73b0\u573a\uff0c"
            "\u4e0b\u4e00\u8f6e\u6da8\u6f6e\u4f1a\u5148\u628a\u4ed6\u6740\u6b7b\u5728\u8fd9\u7247\u4e0d\u81ea\u7136\u7684\u6f6e\u6c34\u91cc\u3002"
        )

        result = PipelineOrchestrator._evaluate_ending_pressure(text, chapter_mission={})

        assert result["ending_pressure_passed"] is True
        assert "\u4e0b\u4e00\u8f6e" in result["ending_pressure_hits"]

    def test_story_quality_metrics_match_compacted_named_mission_tokens(self):
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content=(
                "沈文朝把潮印按进袖中，潮宗的缉印令已经贴到渡口。\n"
                "盐商会的人同时封锁水路，季阿七拒绝冒险硬闯。\n"
                "沈文朝决定转向听潮祠，旧档夹层或许才是父案入口。\n"
                "章尾，缉印令和水路封锁同时落下，他只能在天亮前潜入听潮祠。"
            ),
            violations=[],
            chapter_mission={
                "chapter_purpose": "潮宗正式发缉印令，盐商会封锁常用水路，主角被迫转向听潮祠旧档夹层",
                "suspense_hook": "缉印令与水路封锁把下一章压力压到潜入听潮祠。",
                "continuity_anchor": {"deliver_to_next": ["潜入听潮祠"]},
                "scene_list": [
                    {
                        "goal": "确认潮宗正式发缉印令",
                        "conflict": "盐商会封锁常用水路",
                        "turn": "沈文朝决定转向听潮祠旧档夹层",
                        "outcome": "退路被封锁",
                        "end_hook": "天亮前潜入听潮祠",
                    }
                ],
            },
        )

        assert guard["mission_hit_count"] >= 2
        assert guard["scene_fulfillment_rate"] >= 0.5
        assert guard["ending_pressure_passed"] is True

    def test_story_quality_metrics_count_scene_characters_and_payoff_as_mission_anchors(self):
        guard = PipelineOrchestrator._score_story_quality_candidate(
            content=(
                "沈文朝和季阿七赶到黑帆旧坞，鲁百舵用旧式船匠刻线法重校半毁航图。"
                "聂沧澜质疑沧璃给出的半段潮歌路线，认为那会把众人引进封海外环裂口。"
                "季阿七抢在潮窗闭合前控舟，众人最终穿过外环边线，听见雾里有人叫他们回来。"
            ),
            violations=[],
            chapter_mission={
                "scene_list": [
                    {
                        "characters": ["沈文朝", "季阿七", "聂沧澜", "鲁百舵", "沧璃"],
                        "outcome": "半毁航图被重校，目标转为封海外环裂口",
                        "payoff": "回收旧图不是货路图，而是指向外环潮脉入口",
                        "bridge": "半段潮歌路线带众人进入下一章异潮环境",
                    }
                ],
            },
        )

        assert guard["mission_hit_count"] >= 4
        assert any(hit in guard["mission_hits"] for hit in ("鲁百舵", "沧璃", "半毁航图"))

    def test_ending_pressure_uses_outline_hook_when_deliver_to_next_is_sparse(self):
        text = (
            "沈文朝退到窗下时，外头的水路已经被盐商会封锁。"
            "下一刻，潮宗缉印令沿着街口一张张贴下，"
            "他终于明白自己没有退路，只能在天亮前潜入听潮祠。"
        )

        result = PipelineOrchestrator._evaluate_ending_pressure(
            text,
            chapter_mission={
                "suspense_hook": "潮宗缉印令与盐商会水路封锁同时落下，逼主角潜入听潮祠。",
                "continuity_anchor": {"deliver_to_next": []},
            },
        )

        assert result["ending_pressure_passed"] is True
        assert "缉印令" in result["ending_pressure_hits"] or "封锁" in result["ending_pressure_hits"]

    def test_rag_continuity_injection_forces_previous_tail_and_open_hooks(self):
        injected = PipelineOrchestrator._inject_continuity_into_rag(
            {"chunks": ["旧检索片段"], "summaries": ["旧摘要"]},
            {
                "previous_summary": "林七上一章已经拿到半枚印章。",
                "previous_tail": "门外的脚步声停在门槛前，有人低声喊出了林七的真名。",
                "plot_arc_digest": "- 未闭环钩子：真名泄露来源未知\n- 长线压力：印章会引来追杀",
                "recent_track": "近三章持续围绕印章和身份暴露推进。",
            },
        )

        assert injected["continuity_injection"] is True
        assert injected["chunks"][0].startswith("## 上一章摘要")
        assert "上一章结尾原文尾巴" in injected["chunks"][0]
        assert "未闭环钩子/长线压力" in injected["chunks"][0]
        assert "旧检索片段" == injected["chunks"][1]
        assert "强制连续性上下文" in injected["summaries"][0]

    def test_reader_polish_structural_issues_precede_sentence_polish(self):
        issues = PipelineOrchestrator._build_structural_reader_polish_issues(
            {
                "static_description_risk": True,
                "scene_count": 2,
                "scene_fulfillment_rate": 0.25,
                "expected_dialogue": True,
                "dialogue_changes_state": False,
                "ending_pressure_passed": False,
            }
        )

        assert [issue["dimension"] for issue in issues[:3]] == ["structure", "structure", "dialogue"]
        assert issues[0]["severity"] == "critical"
        assert "不能只做句子润色" in issues[1]["suggestion"]
        assert any(issue["location"] == "章末" for issue in issues)

    def test_enrichment_prompt_bans_empty_description_padding(self):
        prompt = ENRICH_CHAPTER_PROMPT

        assert "新增篇幅只能主要落在：行动回合、对话攻防、因果后果、短余波决断" in prompt
        assert "禁止把“感官/环境/心理描写”当作独立扩写材料" in prompt
        assert "对话攻防、动作回合、因果衔接、短余波应占新增内容的 85% 以上" in prompt

def test_specialized_enrichment_prompts_do_not_reopen_description_padding():
    assert "改变局势" in ENRICH_DIALOGUE_PROMPT
    assert "不能独立铺陈气氛" in ENRICH_DIALOGUE_PROMPT
    assert "行动、对话、后果驱动" in ENRICH_SCENE_PROMPT
    assert "不能独立成段" in ENRICH_SCENE_PROMPT
    assert "明确后果" in ENRICH_SCENE_PROMPT


def test_enrichment_guard_rejects_lost_motifs_and_sequence_anchors():
    service = EnrichmentService(db=None, llm_service=None)
    original = "\n\n".join(
        [
            "林七把账册按在桌上，逼问药行为何少了一页。",
            "掌柜拒绝回答，只说旧南渠昨夜死了人。",
            "林七发现药渣里有血契粉末，决定改查南渠。",
            "门外脚步逼近，他必须立刻带走证据。",
        ]
    )
    motif_lost = "\n\n".join(
        [
            "林七把账册按在桌上，逼问药行为何少了一页。他在桌边看着风，心里泛起很多旧事，灯影把他的沉默拉得很长。",
            "掌柜沉默很久，屋内气氛越来越冷，连窗纸上的影子都像要压下来。",
            "他想起远处的水声，觉得命运正在逼近，却仍然只在原地反复思量。",
            "门外脚步逼近，他必须立刻带走证据。夜色在背后慢慢合拢。",
        ]
    )

    assert service._enrichment_continuity_guard_failure(original, motif_lost).startswith("lost_required_motifs")

    reordered = "\n\n".join(reversed(original.split("\n\n")))
    assert service._enrichment_continuity_guard_failure(original, reordered) == "original_sequence_reordered"


def test_enrichment_guard_extracts_project_specific_motifs_without_sample_keywords():
    service = EnrichmentService(db=None, llm_service=None)
    original = "\n\n".join(
        [
            "阿岚在星潮核心前按下零号航标，逼问舰长为何隐瞒第七枚晶钥。",
            "舰长拒绝回答，只说雾环港昨夜已经封锁。",
            "阿岚发现航标背面的银蓝印记，决定改查雾环港。",
            "警报逼近，她必须立刻带走零号航标。",
        ]
    )
    motif_lost = "\n\n".join(
        [
            "阿岚在控制台前逼问舰长为何隐瞒秘密，舰桥灯光被拉得很长，她再次追问，对方的手指终于停住。",
            "舰长拒绝回答，只说昨夜已经封锁，随即反问她是否承担后果，局势立刻压紧。",
            "阿岚发现背面的痕迹，决定改查港口，并抓住对方语气里的破绽夺回主动权。",
            "警报逼近，她必须立刻离开，把危险压给下一章。",
        ]
    )

    missing = service._missing_required_motifs(original, motif_lost)

    assert missing
    assert any("航标" in item or "晶钥" in item or "雾环港" in item for item in missing)


def test_enrichment_guard_accepts_anchored_dramatic_supplement():
    service = EnrichmentService(db=None, llm_service=None)
    original_parts = [
        "林七把账册按在桌上，逼问药行为何少了一页。",
        "掌柜拒绝回答，只说旧南渠昨夜死了人。",
        "林七发现药渣里有血契粉末，决定改查南渠。",
        "门外脚步逼近，他必须立刻带走证据。",
    ]
    enriched_parts = [
        original_parts[0] + "他追问第二遍，指尖压住缺页边缘，掌柜的手终于停住。",
        original_parts[1] + "林七反制地念出账册数目，对方脸色一变，风险立刻升级。",
        original_parts[2] + "这条线索暴露后，他意识到继续留在药行只会失去主动权。",
        original_parts[3] + "他抓起账册转身，决定先保住证据，把危险压给下一章。",
    ]

    assert service._enrichment_continuity_guard_failure(
        "\n\n".join(original_parts),
        "\n\n".join(enriched_parts),
    ) is None


def test_fragment_enrichment_guard_rejects_unanchored_local_rewrite():
    service = EnrichmentService(db=None, llm_service=None)
    original = "\n\n".join(
        [
            "Lin Qi pressed the tide ledger on the table and forced the clerk to answer why the seal was missing.",
            "The clerk refused twice, but his hand paused when Lin Qi named the south pier archive.",
            "A knock landed outside the door, so Lin Qi had to take the ledger before the patrol arrived.",
        ]
    )
    unanchored = (
        "Rain rolled across the distant hills while the hero thought about fate. "
        "The room felt quiet, poetic, and unchanged. "
    ) * 8
    anchored = "\n\n".join(
        [
            original.split("\n\n")[0] + " He pressed harder until the answer changed the leverage.",
            original.split("\n\n")[1] + " The refusal became a bargain instead of a dead end.",
            original.split("\n\n")[2] + " The next choice now carried a visible cost.",
        ]
    )

    assert service._fragment_enrichment_guard_failure(original, unanchored) == "fragment_lost_front_and_back_anchors"
    assert service._fragment_enrichment_guard_failure(original, anchored) is None


def test_guardrail_rewrite_guard_rejects_partial_chapter_replacement():
    original = "\n\n".join(
        [
            "Opening anchor: Lin Qi blocks the archive door and keeps the ledger in sight.",
            "The clerk tries to bargain, the patrol knocks twice, and the seal clue changes hands.",
            "Lin Qi realizes the missing seal points toward the south pier, but the patrol forces him to move.",
            "Ending anchor: he hides the ledger under his coat as the door breaks inward.",
        ]
    )
    bad_rewrite = "A short corrected fragment removes the forbidden name but loses the chapter."
    good_rewrite = original.replace("patrol", "guards")

    assert PipelineOrchestrator._guardrail_rewrite_guard_failure(original * 8, bad_rewrite) == "rewrite_shrank_too_much"
    assert PipelineOrchestrator._guardrail_rewrite_guard_failure(original, good_rewrite) is None


def test_guardrail_rewrite_guard_rejects_lost_mission_continuity_terms():
    original = "\n\n".join(
        [
            "Opening anchor: Lin Qi waits near the archive gate while rain gathers.",
            "The clerk says the ledger code points to the south pier, and Shen Fang is being traced.",
            "Ending anchor: Lin Qi keeps walking into the rain with the next pressure still unresolved.",
        ]
    )
    bad_rewrite = "\n\n".join(
        [
            "Opening anchor: Lin Qi waits near the archive gate while rain gathers.",
            "The clerk says the situation is dangerous and asks him to leave soon.",
            "Ending anchor: Lin Qi keeps walking into the rain with the next pressure still unresolved.",
        ]
    )
    good_rewrite = original.replace("clerk", "archivist")
    mission = {
        "continuity_anchor": {
            "inherit_from_previous": ["ledger code", "south pier"],
            "deliver_to_next": ["Shen Fang is being traced"],
        }
    }

    assert (
        PipelineOrchestrator._guardrail_rewrite_guard_failure(original, bad_rewrite, chapter_mission=mission)
        == "rewrite_lost_mission_continuity_terms"
    )
    assert PipelineOrchestrator._guardrail_rewrite_guard_failure(original, good_rewrite, chapter_mission=mission) is None


def test_shared_continuity_guard_only_requires_terms_present_in_original():
    original = (
        "Lin Qi names the ledger code and points toward the south pier. "
        "Shen Fang is being traced before the gate closes."
    )
    candidate = "Lin Qi says the matter is dangerous before the gate closes."
    context = {
        "chapter_mission": {
            "continuity_anchor": {
                "inherit_from_previous": ["ledger code", "south pier", "unseen clue"],
                "deliver_to_next": ["Shen Fang is being traced"],
            }
        }
    }

    failure = continuity_terms_guard_failure(
        original=original,
        candidate=candidate,
        context=context,
        reason_code="lost_terms",
    )
    assert failure is not None
    assert failure.startswith("lost_terms:")
    assert continuity_terms_guard_failure(
        original=original,
        candidate=original.replace("gate", "archive gate"),
        context=context,
        reason_code="lost_terms",
    ) is None


def test_consistency_guard_rejects_fixes_that_drop_context_terms():
    service = ConsistencyService(db=None, llm_service=None)
    original = "\n\n".join(
        [
            "Opening anchor: Lin Qi waits near the archive gate.",
            "The ledger code points to the south pier, while Shen Fang is being traced.",
            "Ending anchor: he leaves with the pressure unresolved.",
        ]
    )
    fixed = "\n\n".join(
        [
            "Opening anchor: Lin Qi waits near the archive gate.",
            "The clerk says the situation is dangerous and asks him to leave.",
            "Ending anchor: he leaves with the pressure unresolved.",
        ]
    )
    context = {
        "chapter_mission": {
            "continuity_anchor": {
                "inherit_from_previous": ["ledger code", "south pier"],
                "deliver_to_next": ["Shen Fang is being traced"],
            }
        }
    }

    assert service._fix_continuity_guard_failure(original, fixed, context=context).startswith(
        "fixed_lost_continuity_terms"
    )
    assert service._fix_continuity_guard_failure(original, original.replace("clerk", "archivist"), context=context) is None


def test_enrichment_guard_rejects_expansion_that_loses_context_terms():
    service = EnrichmentService(db=None, llm_service=None)
    original = "\n\n".join(
        [
            "Opening anchor: Lin Qi waits near the archive gate.",
            "The ledger code points to the south pier, while Shen Fang is being traced.",
            "Ending anchor: he leaves with the pressure unresolved.",
        ]
    )
    enriched = "\n\n".join(
        [
            "Opening anchor: Lin Qi waits near the archive gate. He listens to the rain for a long time.",
            "The clerk refuses and speaks vaguely about danger, adding a few tense gestures.",
            "Ending anchor: he leaves with the pressure unresolved. The next choice feels heavy.",
        ]
    )
    context = {
        "chapter_mission": {
            "continuity_anchor": {
                "inherit_from_previous": ["ledger code", "south pier"],
                "deliver_to_next": ["Shen Fang is being traced"],
            }
        }
    }

    assert service._enrichment_continuity_guard_failure(original, enriched, context=context).startswith(
        "enrichment_lost_continuity_terms"
    )


def test_optimizer_guard_rejects_optimization_that_loses_context_terms():
    original = (
        "Lin Qi keeps the ledger code and tells Shen Fang they must reach the south pier before dawn."
    )
    optimized = (
        "Lin Qi walks through the market and thinks about leaving before dawn. "
        "He reviews the danger, changes his route, and decides the next move must stay quiet."
    )
    reason = optimizer_continuity_guard_failure(
        original,
        optimized,
        context={
            "longform_context": {
                "memory_digest": {"inherit_from_previous": ["ledger code", "south pier"]},
                "character_focus": ["Shen Fang"],
            },
            "continuity_contract": {
                "hard_rules": ["keep ledger code", "keep south pier", "keep Shen Fang"],
            },
        },
    )

    assert reason is not None
    assert reason.startswith("optimized_content_lost_continuity_terms")


def test_self_critique_local_guard_rejects_lost_context_terms():
    service = SelfCritiqueService(db=None, llm_service=None, prompt_service=None)
    plan = {
        "target_paragraphs": [
            "The ledger code points to the south pier, while Shen Fang is being traced."
        ],
        "prev_anchor": "Opening anchor: Lin Qi waits near the archive gate.",
        "next_anchor": "Ending anchor: he leaves with the pressure unresolved.",
        "context": {
            "chapter_mission": {
                "continuity_anchor": {
                    "inherit_from_previous": ["ledger code", "south pier"],
                    "deliver_to_next": ["Shen Fang is being traced"],
                }
            }
        },
    }

    assert service._local_cohesion_failure_reason(
        plan,
        "The clerk says the matter is risky and refuses to explain more.",
    ).startswith("localized_lost_continuity_terms")
    assert service._local_cohesion_failure_reason(
        plan,
        "The ledger code points to the south pier, and Shen Fang is being traced more aggressively.",
    ) is None


def test_self_critique_keeps_major_only_revision_local_after_content_changes():
    service = SelfCritiqueService(db=None, llm_service=None, prompt_service=None)

    should_stagewide = service._should_attempt_stagewide_rewrite(
        before_counts={"critical": 0, "major": 5, "minor": 2},
        strategy_issues=[
            {"severity": "major", "dimension": "scene", "problem": "节奏拖沓"},
            {"severity": "major", "dimension": "writing", "problem": "表达重复"},
        ],
        best_content_changed=True,
    )

    assert should_stagewide is False
    assert service._should_attempt_stagewide_rewrite(
        before_counts={"critical": 0, "major": 8, "minor": 2},
        strategy_issues=[
            {"severity": "major", "dimension": "scene", "problem": "节奏拖沓"},
            {"severity": "major", "dimension": "writing", "problem": "表达重复"},
        ],
        best_content_changed=False,
    ) is False


def test_self_critique_flags_stagewide_need_but_requires_manual_confirmation():
    service = SelfCritiqueService(db=None, llm_service=None, prompt_service=None)

    assert service._should_attempt_stagewide_rewrite(
        before_counts={"critical": 1, "major": 0, "minor": 0},
        strategy_issues=[{"severity": "critical", "dimension": "logic", "problem": "因果断裂"}],
        best_content_changed=False,
    ) is True
    assert service._should_attempt_stagewide_rewrite(
        before_counts={"critical": 0, "major": 1, "minor": 0},
        strategy_issues=[{"severity": "major", "dimension": "continuity", "problem": "时间线重复回卷"}],
        best_content_changed=True,
    ) is True
    assert service._stagewide_rewrite_explicitly_confirmed(None) is False
    assert service._stagewide_rewrite_explicitly_confirmed({"manual_stagewide_rewrite": True}) is True
    assert service._stagewide_rewrite_explicitly_confirmed({"manual_stagewide_rewrite": {"confirmed": True}}) is True


def test_quality_issue_summary_exposes_frontend_ready_labels():
    summary = PipelineOrchestrator._build_quality_issue_summary(
        story_guard={
            "word_count": 1800,
            "expected_dialogue": True,
            "dialogue_marker_count": 1,
            "mission_hit_count": 0,
            "scene_count": 2,
            "scene_fulfillment_rate": 0.25,
            "dialogue_changes_state": False,
            "ending_pressure_passed": False,
            "static_description_risk": True,
        }
    )

    assert summary["tone"] == "danger"
    assert "static_description_risk" in summary["codes"]
    assert "静态描写过多" in summary["labels"]
    assert "对白未改变局势" in summary["labels"]


def test_pipeline_has_no_dead_fallback_scorer():
    """_score_fallback_candidate 的函数体引用了签名里不存在的 target_word_count / min_word_count，
    一旦被调用必然 NameError。它在生产路径上零调用，属于错位粘贴留下的死代码，必须删除而不是留着。"""
    assert not hasattr(PipelineOrchestrator, "_score_fallback_candidate")


def test_extractable_comments_have_no_line_numbers():
    """EXTRACTABLE 模块边界注释不能带行号：行号在文件变动后立刻过期，
    照着过期行号切模块会切错位置（其中一条原先就落在 STORY_PROGRESSION_MARKERS 元组字面量内部）。"""
    source = Path(pipeline_orchestrator_module.__file__).read_text(encoding="utf-8")
    stale = re.findall(r"EXTRACTABLE.*?L\d+", source)
    assert stale == [], f"EXTRACTABLE 注释里仍带行号：{stale}"


def test_ending_pressure_keeps_hook_when_closure_prefix_appears():
    """「一切都」是中性前缀，后面接什么才决定语义。
    「一切都还是未知」是真钩子，不能被当成平淡收束一票否决。"""
    result = PipelineOrchestrator._evaluate_ending_pressure(
        "追兵已经堵住了退路，她攥紧照片冲向后窗，玻璃在身后炸裂，而幕后是谁，一切都还是未知。",
        None,
    )

    assert result["flat_closure_markers"] == []
    assert result["ending_pressure_passed"] is True


def test_ending_pressure_still_blocks_complete_flat_closure():
    """把「一切都」换成完整的收束表达时，仍然必须判平淡——修 T-02 不能把平淡放行。"""
    result = PipelineOrchestrator._evaluate_ending_pressure(
        "追兵撤走了，她把照片收进抽屉，门外再没有脚步声，一切都平静下来。",
        None,
    )

    assert result["flat_closure_markers"] != []
    assert result["ending_pressure_passed"] is False


def test_ending_pressure_rejects_punctuation_only_hook():
    """两个问号叹号不构成章末压力：标点是辅助信号，不能顶替语义压力。"""
    result = PipelineOrchestrator._evaluate_ending_pressure(
        "他喝完了茶，把杯子放回原处，觉得这一天过得很舒服。真的很舒服吗？当然很舒服！",
        None,
    )

    assert result["ending_pressure_passed"] is False
    assert result["ending_semantic_hit_count"] == 0
    assert result["ending_weak_hit_count"] >= 2


def test_ending_pressure_still_accepts_semantic_hook_without_punctuation():
    """防误杀：纯陈述句的强钩子（没有任何问号叹号）必须通过。"""
    result = PipelineOrchestrator._evaluate_ending_pressure(
        "追兵已经堵住了退路，她攥紧照片冲向后窗，玻璃在身后炸裂，而幕后是谁，仍旧无人知道。",
        None,
    )

    assert result["ending_pressure_passed"] is True
    assert result["ending_weak_hit_count"] == 0
    assert result["ending_semantic_hit_count"] >= 2


def test_ending_pressure_uses_genre_neutral_markers_for_urban_story():
    """都市题材的章末压力不该依赖某部小说的专有词（药渣 / 旧南渠 之类）才能被认出来。"""
    result = PipelineOrchestrator._evaluate_ending_pressure(
        "她把辞职信压在键盘下，手机又亮了一次，是那个陌生号码发来的照片。"
        "楼下保安说，有人已经在门外等了两个小时，说必须今天见到她。",
        None,
    )

    assert result["ending_pressure_passed"] is True


def test_ending_hook_markers_are_genre_neutral_and_greppable():
    """章末压力词表的两条硬约束：
    ① 不含只属于某一部小说的专有词（否则换题材就判不出压力）；
    ② 在源码里必须是中文字面量而不是 \\uXXXX 转义（否则 grep 不到，没人能维护）。"""
    markers = set(PipelineOrchestrator.ENDING_SEMANTIC_HOOK_MARKERS)
    story_specific = {
        "旧木片", "旧南渠", "药渣", "药味", "药耗", "见了地", "病人", "缉印令", "涨潮", "潮水",
    }
    leaked = story_specific & markers
    assert leaked == set(), f"章末压力词表混入了专有词：{sorted(leaked)}"

    source = Path(pipeline_orchestrator_module.__file__).read_text(encoding="utf-8")
    block = re.search(
        r"ENDING_SEMANTIC_HOOK_MARKERS = \((.*?)\n    \)", source, re.S
    )
    assert block is not None, "找不到 ENDING_SEMANTIC_HOOK_MARKERS 定义"
    assert "\\u" not in block.group(1), "章末压力词表里仍有 \\uXXXX 转义，grep 不到"


def test_t17_final_version_metadata_persists_cleanup_and_quality_gate_snapshots():
    import inspect
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    assert 'best_version_metadata["deterministic_cleanup"]' in source
    assert 'best_version_metadata["quality_gates"]' in source
    sabotaged = source.replace('best_version_metadata["deterministic_cleanup"]', 'best_version_metadata["removed_cleanup"]', 1)
    with pytest.raises(AssertionError):
        assert 'best_version_metadata["deterministic_cleanup"]' in sabotaged


def test_e11_quality_gate_repairs_are_persisted_in_final_version_metadata_with_reverse_guard():
    import inspect
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    assert 'quality_gate_repairs = runtime_metadata.get("quality_gate_repairs")' in source
    assert 'best_version_metadata["quality_gate_repairs"] = deepcopy(' in source
    sabotaged = source.replace('best_version_metadata["quality_gate_repairs"] = deepcopy(', 'best_version_metadata["removed_quality_gate_repairs"] = deepcopy(', 1)
    with pytest.raises(AssertionError):
        assert 'best_version_metadata["quality_gate_repairs"] = deepcopy(' in sabotaged

    assert "quality_gate_repairs if isinstance(quality_gate_repairs, list) else []" in source
    missing_default = source.replace(
        "quality_gate_repairs if isinstance(quality_gate_repairs, list) else []",
        "quality_gate_repairs",
        1,
    )
    with pytest.raises(AssertionError):
        assert "quality_gate_repairs if isinstance(quality_gate_repairs, list) else []" in missing_default


def test_t17_real_smoke_asserts_persisted_metadata_snapshots_with_reverse_guard():
    source = (Path(__file__).parents[2] / "scripts" / "real_asgi_generation_smoke.py").read_text(encoding="utf-8")
    for marker in (
        'cleanup_snapshot = metadata.get("deterministic_cleanup")',
        'quality_gates_snapshot = metadata.get("quality_gates")',
        'quality_metrics_snapshot = metadata.get("quality_metrics")',
        'quality_gate_repairs = metadata.get("quality_gate_repairs")',
        'and isinstance(quality_gate_repairs, list)',
        'PERSISTENCE_ERROR selected chapter version is missing T-17 metadata snapshots',
    ):
        assert marker in source
    sabotaged = source.replace('quality_metrics_snapshot = metadata.get("quality_metrics")', 'quality_metrics_snapshot = None', 1)
    with pytest.raises(AssertionError):
        assert 'quality_metrics_snapshot = metadata.get("quality_metrics")' in sabotaged


def test_quality_metric_snapshot_exposes_ending_pressure_hit_counts():
    """章末压力的语义/弱信号命中数必须进 quality_metric_snapshot。
    前端和 API 读的是这份扁平快照（metadata.quality_metrics），
    只把计数留在嵌套的 ending_pressure 里，评审界面就看不到判定依据。"""
    content = "追兵已经堵住了退路，她攥紧照片冲向后窗，玻璃在身后炸裂，而幕后是谁，仍旧无人知道。" * 20
    guard = PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=None,
    )

    snapshot = guard["quality_metric_snapshot"]
    assert snapshot["ending_semantic_hit_count"] == guard["ending_pressure"]["ending_semantic_hit_count"]
    assert snapshot["ending_weak_hit_count"] == guard["ending_pressure"]["ending_weak_hit_count"]
    assert snapshot["ending_semantic_hit_count"] >= 2


# ====== 批 3（T-04 / T-05 / T-06）事件密度门样本 ======
# 样本三条硬约束：① 字数 ≥800，否则 _evaluate_event_density 直接短路，拿到的数据无效；
# ② 用序数前缀扩写而不是整段复制，否则会触发重复段落判罚污染断言；
# ③ 正文只用「他 / 她 / 照片 / 钥匙」这类通用词，不用人名地名，避免词表被样本绑死。
_ORD = ("初", "次", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")


def _grow(block: str, times: int) -> str:
    """把一段样本复制 times 次，并保证**每一个会进入重复统计的段落都是唯一的**。

    上面第 ② 条硬约束说的就是这件事，但批 3 的实现只替换了首行的 `＃` 占位符，
    其余各行是逐字复制——批 6 落地 T-10（重复段落检测）时立刻暴露：`GOOD_DRAMATIC`
    实测有 6 个段落各重复 8 次（最长 46 字），`BAD_FLAT_CHATTER` 有 2 个各重复 10 次，
    于是**正向对照自己带上了 `repeated_paragraph_flood`**。

    所以这里给「归一化后 >= 30 字」的行——也就是 `_evaluate_repetition_risk` 会计入
    统计的那些行——加上逐轮不同的序数前缀。短行（对话应答之类）不动：它们本来就
    低于 30 字门槛，加前缀反而会把引号从行首挪走，影响对话痕迹判定。
    """
    chunks = []
    for index in range(times):
        ordinal = _ORD[index % len(_ORD)]
        lines = []
        for line in block.replace("＃", ordinal).split("\n"):
            if len(re.sub(r"\s+", "", line)) >= 30:
                line = f"{ordinal}、{line}"
            lines.append(line)
        chunks.append("\n".join(lines))
    return "".join(chunks)


# 纯寒暄灌水：全是引号对话，但没有任何目标、阻力、代价或状态改变。
BAD_FLAT_CHATTER = _grow(
    "“＃天天气真不错啊。”他笑着说。\n"
    "“是啊，阳光很好。”她点点头，“适合出去走走。”\n"
    "“你早饭吃了吗？”\n"
    "“吃了，还是老样子，粥和小菜。”她答道，“你呢？”\n"
    "“我也差不多，随便对付了一下。”\n"
    "“最近还好吗？”\n"
    "“挺好的，一切照旧，没什么变化。”他望着窗外，慢悠悠地说。\n"
    "“那就好，那就好。”她微笑着，“平平淡淡才是真。”\n"
    "两人有一搭没一搭地闲聊，时间就这样悠闲流过，谁也没有多说什么，和往常一样平静。\n"
    "又是寻常的一天，和昨天一样，和明天一样，没有什么特别，日子就这样过去了。\n",
    10,
)

# 正向对照：有目标、有阻力、有反转、有代价、章末留压力。
# 所有调阈值的改动都必须保证它是绿的——这是防误杀的唯一自动化防线。
GOOD_DRAMATIC = _grow(
    "“把刀放下。”＃轮交锋里她冷冷开口，指尖已经扣住扳机。\n"
    "他没有动，反而向前逼近一步：“你不敢开枪。”\n"
    "话音未落，她扣动扳机，子弹擦着他的耳畔钉进门框。他脸色骤变，终于停住脚步。\n"
    "“下一发不会偏。”她逼问，“钥匙在哪里？”\n"
    "他咬牙从怀里掏出钥匙扔在地上：“拿去，但你打开它就死定了。”\n"
    "她捡起钥匙插进锁孔，猛地拧开——箱子里不是黄金，而是一张照片，照片上是她以为早已死去的妹妹。\n"
    "她的手开始发抖：“这不可能……”\n"
    "他冷笑：“现在你明白了？三天后午夜，老码头，不来，她就真的死了。”\n"
    "远处警笛声越来越近。她攥紧照片，转身冲向后窗，玻璃在身后炸裂。\n"
    "究竟是谁在幕后操纵，妹妹又为何落入他们手中，来不及细想，追兵已经堵住了退路。\n",
    8,
)


# T-12 之后字数参数真正参与评分了，这对助手函数取的值必须**贴生产比例**，
# 否则字数判罚会串进每一条结构类断言里。
#
# 为什么是 2500/2250 而不是原来的 3000/2000：
# - 比例：生产里 `min` 恒等于 `target * 0.9`（`_resolve_config` 与
#   `_resolve_chapter_draft_contract` 两条路都是），真实语料 82 条的
#   `min/target` 唯一取值就是 0.900。3000/2000 的比例是 0.667，**生产从不产生**。
# - 绝对值：全部结构类样本落在 2310-2810 字。preferred_floor = 0.92 * target，
#   取 3000 时 floor=2760，于是连正向对照 GOOD_DRAMATIC（2504 字）都会被判
#   `word_count_far_below_target` 吃掉 −180——而密度类坏样本（2331/2310/2399）
#   同样被扣，判罚在两边抵消，`BAD_PUNCTUATION_HOOK`（2810 字，唯一没被扣的）
#   的分差反而从 260 塌到 80。取 2500 时 floor=2300，所有样本一律中性。
#
# 也就是说：这一对数字的作用是**把字数维度从结构类断言里摘出去**。想测字数判罚
# 本身，用下面 TestWordCountPenalties 里的显式取值，不要动这里。
# （常量本身定义在文件头部，因为前面的 gate 类测试也要用。）


def _score_density_sample(content: str) -> dict:
    return PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=None,
        target_word_count=_SAMPLE_TARGET_WORDS,
        min_word_count=_SAMPLE_MIN_WORDS,
    )


def test_progression_marker_table_excludes_bare_conjunctions():
    """纯连词与高频语素不能留在推进词主词表里。
    「但 / 却 / 然而 / 转而 / 下一步」只是转折修饰，不代表状态改变；
    「活」会被「生活 / 干活 / 活动」命中，任何日常段落都能骗过事件密度门。
    它们只能作为辅助信号放在 WEAK_TRANSITION_MARKERS 里。"""
    markers = set(PipelineOrchestrator.STORY_PROGRESSION_MARKERS)
    banned = {"但", "却", "然而", "转而", "下一步", "活"}
    leaked = banned & markers
    assert leaked == set(), f"推进词主词表里仍有弱信号词：{sorted(leaked)}"
    assert banned <= set(PipelineOrchestrator.WEAK_TRANSITION_MARKERS)


def test_event_density_rejects_pure_small_talk_dialogue():
    """纯寒暄对话灌水必须被事件密度门拦住。
    修复前引号无条件返回推进，210 个句子全部命中，event_density_per_1000 高到 83.7，
    比真有冲突的样本（49.8）还高，于是灌水稿反而拿到更高分。"""
    guard = _score_density_sample(BAD_FLAT_CHATTER)

    assert guard["event_density"]["progression_unit_count"] <= 20
    assert guard["event_density_passed"] is False
    assert "event_density_weak" in guard["quality_issue_codes"]


def test_event_density_still_accepts_dramatic_scene():
    """防误杀锚点：有目标、阻力、反转、代价、章末压力的场景必须继续通过。
    这条比拦住坏样本更重要——门一过严，所有真实章节都会被拒稿。"""
    guard = _score_density_sample(GOOD_DRAMATIC)

    assert guard["event_density_passed"] is True
    assert guard["state_change_interval_passed"] is True
    assert guard["quality_issue_codes"] == []


def test_state_change_window_rate_discriminates_flat_chatter():
    """千字窗口要按「窗口内推进句占比」判定，而不是「整个窗口里有没有出现过一次」。
    修复前把句子级的 _unit_has_progression 直接套在 950 字窗口上，
    好坏样本的 state_change_window_pass_rate 都恒为 1.0，这个指标完全没有鉴别力。"""
    bad = _score_density_sample(BAD_FLAT_CHATTER)["quality_metric_snapshot"]
    good = _score_density_sample(GOOD_DRAMATIC)["quality_metric_snapshot"]

    assert bad["state_change_window_pass_rate"] < 1.0
    assert good["state_change_window_pass_rate"] > bad["state_change_window_pass_rate"]


def test_progression_rate_ranks_dramatic_above_flat_chatter():
    """指标方向必须为正：真冲突的推进句占比要高于寒暄灌水。
    修复前灌水样本 progression_unit_rate = 1.0，好样本只有 0.69，
    指标越高反而质量越差，任何基于它的软放行都会放行错的那一边。"""
    good = _score_density_sample(GOOD_DRAMATIC)["quality_metric_snapshot"]["progression_unit_rate"]
    bad = _score_density_sample(BAD_FLAT_CHATTER)["quality_metric_snapshot"]["progression_unit_rate"]

    assert good > bad
    assert bad <= 0.1


def test_event_density_floor_is_calibrated_to_real_corpus_distribution():
    """门槛必须落在真实生成语料的实测分布内，两个方向都要防。

    往下：留在 1.0 / 0.16 那种历史值时，句子级切分让这个门在数学上不可能失败。
    往上：第一版修复用合成样本把门槛定到 6.0 / 0.14 / 绝对连段 12 句，
    在 147 条真实章节上误杀 96%——合成样本每句都是冲突，真实章节的推进句占比
    中位数只有 0.079、最长无推进连段中位数 36 句。

    实测分位（历史合格池 n=107）：density p05=2.01 p50=4.60；
    rate p05=0.026 p50=0.079；plain_run_ratio p50=0.22 p95=0.45 max=0.68。
    """
    floors = [PipelineOrchestrator._event_density_floors(word_count) for word_count in (1500, 3000, 8000)]
    density_floors = [item["density_floor"] for item in floors]
    rate_floors = [item["unit_rate_floor"] for item in floors]
    ratio_limits = [item["plain_run_ratio_limit"] for item in floors]

    assert min(density_floors) >= 1.2, f"密度门槛过低，门会恒真：{density_floors}"
    assert max(density_floors) <= 2.5, f"密度门槛超过真实语料 p10，会大面积误杀：{density_floors}"
    assert density_floors == sorted(density_floors), "字数越长门槛不应更松"
    assert min(rate_floors) >= 0.02, f"推进占比门槛过低：{rate_floors}"
    assert max(rate_floors) <= 0.04, f"推进占比门槛超过真实语料 p15，会大面积误杀：{rate_floors}"
    # 无推进连段必须按比例判定，绝对句数会按章节长度歧视长章。
    assert all("plain_run_limit" not in item for item in floors), "不应再用绝对连段句数"
    assert min(ratio_limits) >= 0.6, f"连段比例上限低于真实语料 max=0.68，会误杀：{ratio_limits}"
    assert max(ratio_limits) <= 0.9, f"连段比例上限过松，拦不住纯寒暄的 1.0：{ratio_limits}"


def test_event_density_uses_plain_run_ratio_not_absolute_run():
    """最长无推进连段要按占全章句数的比例透出，供前端与日志直接消费。
    绝对句数随章节长度线性膨胀（真实语料 p50=36、max=167），不能直接当阈值。"""
    unit = "她逼问他钥匙在哪里，他拒绝回答，她立刻掀开箱子反制，照片暴露了旧案，他必须改口。"
    plain = "夜色铺在长廊上，灯影一点一点拉长，空气里只有潮湿的石味。"
    text = "\n".join([f"第{index + 1}轮，{unit}" for index in range(6)]
                     + [f"第{index + 1}处，{plain}" for index in range(24)])
    word_count = len("".join(text.split()))

    density = PipelineOrchestrator._evaluate_event_density(text, word_count=word_count)

    assert word_count >= 800, "样本必须超过短路阈值"
    expected = round(density["max_plain_unit_run"] / max(1, density["story_unit_count"]), 4)
    assert density["max_plain_unit_run_ratio"] == expected
    assert 0.0 < density["max_plain_unit_run_ratio"] < 1.0
    # 新字段必须穿过 quality_metric_snapshot 的白名单，否则前端与日志拿不到。
    snapshot = _score_density_sample(text)["quality_metric_snapshot"]
    assert snapshot["max_plain_unit_run_ratio"] == density["max_plain_unit_run_ratio"]


def test_state_change_window_rate_survives_real_corpus_ratio():
    """窗口占比门槛必须让真实密度的正文过关。

    真实合格章节整章推进句占比中位数 0.079，千字窗口约 50 句、推进 3-4 句。
    第一版把窗口占比定到 0.25，107 条真实合格正文只有 6.5% 能让
    state_change_window_pass_rate 达到 0.5，这个指标等于恒假。
    """
    assert PipelineOrchestrator.WINDOW_PROGRESSION_RATIO_FLOOR <= 0.08
    assert PipelineOrchestrator.WINDOW_PROGRESSION_MIN_HITS >= 2

    unit = "她逼问他钥匙在哪里，他拒绝回答，照片暴露了旧案。"
    plain = "夜色铺在长廊上，灯影一点一点拉长，空气里只有潮湿的石味。"
    # 每 10 句一句推进：整章推进句占比 0.1，贴着真实合格章节的中位数 0.079。
    lines = [
        f"第{index + 1}轮，{unit}" if (index + 1) % 10 == 0 else f"第{index + 1}处，{plain}"
        for index in range(80)
    ]
    text = "\n".join(lines)
    word_count = len("".join(text.split()))

    density = PipelineOrchestrator._evaluate_event_density(text, word_count=word_count)

    assert word_count > 950, "样本必须超过单窗口长度"
    assert density["progression_unit_rate"] <= 0.12, "样本推进密度必须贴近真实语料，不能是合成的满冲突文本"
    assert density["state_change_window_pass_rate"] == 1.0
    assert density["state_change_interval_passed"] is True
    assert density["event_density_passed"] is True


def test_state_change_window_requires_sustained_progression_not_one_line():
    """一个窗口里只有一句推进、其余全是静态描写，不能算「这一千字有状态推进」。
    修复前窗口判定是「这个窗口里出现过推进词吗」，局部灌水会被直接放行，
    state_change_window_pass_rate 恒为 1.0。"""
    opening = "她逼问他钥匙在哪里，他拒绝回答，照片暴露了旧案。"
    plain = "夜色铺在长廊上，灯影一点一点拉长，空气里只有潮湿的石味。"
    text = "\n".join([opening] + [f"第{index + 1}处，{plain}" for index in range(34)])
    word_count = len("".join(text.split()))

    density = PipelineOrchestrator._evaluate_event_density(text, word_count=word_count)

    assert word_count > 950, "样本必须超过单窗口长度"
    assert density["state_change_window_pass_rate"] == 0.0
    assert density["state_change_interval_passed"] is False


def test_state_change_window_needs_two_hits_when_sentences_are_long():
    """长句正文里，窗口只装得下十几句，一句推进就能超过占比门槛。
    这时唯一的防线是「窗口至少要有两句推进」——占比阈值按真实语料降到 0.05 之后，
    单句推进在短句正文里还会被占比拦住，在长句正文里只有句数条件能拦。"""
    opening = "她当着所有人逼问他钥匙到底藏在哪里，他一口拒绝回答，直到那张旧照片被翻出来暴露了当年的案子，他才不得不改口。"
    plain = "夜色沿着长廊一寸一寸铺开，灯影在潮湿的石墙上缓慢拉长，空气里只剩下陈年木料与雨水混在一起的气味，安静得连呼吸都显得多余。"
    text = "\n".join([opening] + [f"第{index + 1}处，{plain}" for index in range(29)])
    word_count = len("".join(text.split()))

    density = PipelineOrchestrator._evaluate_event_density(text, word_count=word_count)

    assert word_count > 950, "样本必须超过单窗口长度"
    assert density["story_unit_count"] <= 40, "样本必须是长句正文，否则测不到句数条件"
    assert density["progression_unit_count"] == 1
    assert density["state_change_window_pass_rate"] == 0.0
    assert density["state_change_interval_passed"] is False


def test_state_change_window_ignores_short_tail_fragment():
    """切窗口时最后那点余量不能单独成窗。
    950 字切完只剩十几个字，再要求「这十几个字里有两句推进」必然不达标，
    会把通篇密集推进的正文判成一半窗口不合格。"""
    unit = "她逼问他钥匙在哪里，他拒绝回答，她立刻掀开箱子反制，照片暴露了旧案，他必须改口。"
    text = "\n".join(f"第{index + 1}轮，{unit}" for index in range(22))
    word_count = len("".join(text.split()))

    density = PipelineOrchestrator._evaluate_event_density(text, word_count=word_count)

    assert word_count > 950, "样本必须超过单窗口长度，否则测不到尾窗合并"
    assert density["state_change_window_count"] == 1
    assert density["state_change_window_pass_rate"] == 1.0
    assert density["state_change_interval_passed"] is True


# ====== 批 4（T-07）坏样本回归套件 ======
# 存在的意义：现有测试几乎全是「好样本应通过」方向，缺「坏样本必须被拦住」方向。
# 没有这一套，下一次有人为了压误杀把阈值调松，不会有任何测试变红。
# 样本 6-8（重复段落 / 焦点人物缺席 / 承接缺失）依赖 D-10 / D-12 / E-07 的实现，
# 留到对应批次再补，这里只覆盖已经实现的 5 种失败形态。

# 1. 全景物描写：无对话、无动作、无状态改变。
BAD_ALL_DESCRIPTION = _grow(
    "＃时，晨雾漫过山谷，苍翠松林在灰白的光里静静矗立。空气微凉，带着湿润泥土气息。"
    "远处湖面平滑如镜，倒映天边淡淡云影。岸边芦苇轻轻摇曳，无声诉说岁月宁静。"
    "阳光透过云层，洒在斑驳石阶上，泛起温暖金色光晕。庭院深处，一株老梅静默伫立，枝干虬曲。"
    "青苔覆满井沿，井水幽深清冽。廊檐下风铃一动不动，四周一片安详寂静。"
    "时光仿佛凝固，一切显得那样安宁美好，没有什么值得担忧，也没有什么需要改变。"
    "这是一个平静清晨，如同过去无数清晨一样，安稳地开始，又将安稳地结束。"
    "山谷依旧沉睡，湖水依旧平静，岁月静好，现世安稳，令人心生眷恋满足之情。",
    9,
)

# 3. 流水账：动作一大堆，但没有目标、阻力、代价，也没有任何局势改变。
BAD_MUNDANE_SEQUENCE = _grow(
    "＃日早上七点他起床，先去洗手间刷牙，然后洗脸。\n"
    "接着他走进厨房，烧了一壶水，泡了一杯茶。\n"
    "他坐在桌前，慢慢喝完了茶，又吃了两片面包。\n"
    "吃完早饭，他把碗筷洗干净，摆回原处。\n"
    "然后他换好衣服，穿上鞋子，拿起包，出了门。\n"
    "他走到公交站，等了一会儿，上了车，找了个座位坐下。\n"
    "车子一路平稳行驶，窗外街景缓缓后退。\n"
    "到站后他下了车，走进办公楼，乘电梯上了六楼。\n"
    "他打开电脑，泡了杯咖啡，开始慢慢处理邮件。\n"
    "一天就这样平静开始了，和过去每一天没有什么不同，波澜不惊。\n",
    11,
)

# 4/5 号样本的公用尾巴（实测 275 字）：章末压力的语义判定看 condensed_text[-260:]。
# 批 4 建这两个样本时，尾巴短于 260 字，正文里的强钩子会漏进尾窗把坏结尾盖过去，
# 那就是 D-24。批 6 已修：末段（按换行切出的最后一段）单独再判一次「泄气」，
# 短尾巴不再能被正文钩子掩护——证明见 `TestEndingCoreWindow`，那里的
# `SHORT_FLAT_*` 样本尾巴只有 24/31 字，同样被拦。
# 这两个长尾样本保留原样，作为「长填充 + 泄气结尾」的历史对照；
# 填充刻意不含任何 ENDING_SEMANTIC_HOOK_MARKERS 与 ENDING_CLOSURE_MARKERS——
# 只有动作，没有压力。
_FLAT_ENDING_FILLER = (
    "他把杯子放回原处，又给自己添了半杯温水，慢慢地喝完。"
    "他伸手拉开抽屉，把钥匙和照片一起塞进最里面，再推回去。"
    "桌上的台灯还亮着，他抬手关掉，屋里只剩下窗帘缝里漏进来的一点光。"
    "他坐下又站起来，把椅子摆正，把散在桌角的纸张收拢成一叠，摞得整整齐齐。"
    "他走到水池边洗了手，擦干，把毛巾挂回架子上。"
    "他看了看墙上的挂钟，指针刚过十点。"
    "他把窗帘拉严，顺手将地上的一双鞋摆到墙边，又用抹布把桌面擦了一遍。"
    "他翻开桌上那本旧账簿，一页一页翻到末尾，合上，放回原来的位置。"
    "他倒掉剩下的半杯水，把杯子冲干净，倒扣在架子上晾着。"
    "他数了数抽屉里的零钱，凑成一小叠，压在台灯底座下面。"
)

# 4. 结尾只有标点：正文本身是合格的戏剧场面，唯一的毛病是结尾泄气成「舒服吗？舒服！」。
#    这样构造是为了让唯一的失败维度就是章末压力，而不是密度或静态描写。
BAD_PUNCTUATION_HOOK = (
    GOOD_DRAMATIC + _FLAT_ENDING_FILLER
    + "他伸了个懒腰，觉得这一天过得很舒服。真的很舒服吗？当然很舒服！\n"
)

# 5. 结尾完整收束：同一个合格正文，结尾换成「一切都平静下来」这类彻底泄压的表达。
BAD_FLAT_CLOSURE = (
    GOOD_DRAMATIC + _FLAT_ENDING_FILLER
    + "他关灯躺下，屋里再没有别的动静，一切都平静下来。\n"
)

BAD_SAMPLES_DENSITY_CLASS = (
    ("BAD_ALL_DESCRIPTION", BAD_ALL_DESCRIPTION),
    ("BAD_FLAT_CHATTER", BAD_FLAT_CHATTER),
    ("BAD_MUNDANE_SEQUENCE", BAD_MUNDANE_SEQUENCE),
)

BAD_SAMPLES_ENDING_CLASS = (
    ("BAD_PUNCTUATION_HOOK", BAD_PUNCTUATION_HOOK),
    ("BAD_FLAT_CLOSURE", BAD_FLAT_CLOSURE),
)


# ===== 批 6 样本（T-08 / T-09 / T-10 + D-24 + D-25）=====
#
# 这一组样本的构造原则：**一个样本只精确命中一条判定**。
# `static_description_risk` 是四条 or，如果样本同时命中两条，改坏任何一条都不会
# 让测试变红——D-25 就是这么漏出来的（三条判定只有第 1 条有覆盖）。
# 每个样本下面的注释写的都是实测归因，不是设计意图。

# T-09 逃逸样本：130 字纯风景，刻意含「看 / 却 / 但 / 发现」四个汉语超高频字。
# 旧词表把这四个字当动作词，于是整段被判「有动作」，static_paragraph_count 恒为 0。
_T09_ESCAPE_SCENERY = (
    "远处湖面看似平滑，实则被风搅出一层极细的纹。云影却淡，淡得像谁用湿布抹过一遍，"
    "但风铃始终不动，铜舌垂在檐下，蒙着灰。石阶上的水痕看不出深浅，"
    "青苔沿着井沿一圈圈铺开，颜色越往里越深。发现不了任何动静，"
    "整座院子就这样停在灰白的天色里，安静得近乎凝固，久久没有变化。"
)

# 同一段接一句真动作，用来证明词表不是「全判静态」——有主体行为时必须判非静态。
_T09_WITH_ACTION = _T09_ESCAPE_SCENERY + "他伸手推开院门，转身走进雾里。"

# 静态段落基元：每段归一化后 >=100 字（`_estimate_static_description_runs` 的门槛），
# 纯景物、无任何 STATIC_ACTION_MARKERS。四段各不相同，避免撞上 T-10 的重复检测。
_STATIC_PARAGRAPHS = (
    "雾气在谷口停住，白得没有边界，天光被压成一层薄薄的灰，落在瓦脊上，"
    "又沿着檐角散开。湖面平得像一块凉透的铁，没有一丝纹路，倒映着淡淡云影，"
    "远处山脊只剩一道模糊的轮廓，安静得近乎凝固，连一点声音也不肯留下。",
    "青苔覆满井沿，井水幽深而清冽，井口的石缝里嵌着几粒去年的草籽。"
    "廊檐下的风铃一动不动，铜舌垂着，蒙了一层薄薄的灰。院墙根下堆着几块碎瓦，"
    "缝隙里长出细弱的野草，颜色淡得几乎与土同色，像是从来就长在那里，"
    "谁也不曾挪动过它们分毫。",
    "老梅的枝干虬曲如铁，皮上裂着深褐的纹，一片叶子也没有。它的影子斜斜地铺在石阶上，"
    "边缘被雾气化开，模糊成一团。石阶的第三级缺了一角，那个缺口里积着一小汪水，"
    "水面上浮着一层极薄的浮尘，静止不动，也没有半点起伏的意思。",
    "天色又暗了一分，谷底的白雾往上抬起，把整座院子裹进一种没有方向的光里。"
    "屋瓦、井沿、梅枝、石阶，全都失去了各自的轮廓，只剩下浓淡不同的灰。"
    "这种灰一直铺到视线的尽头，铺成一整片没有尽头的寂静，久久停在那里。",
)

# 打断静态连段用的动作句：足够短（不进重复统计），但含 STATIC_ACTION_MARKERS。
_STATIC_BREAKER = "他伸手推开院门，把门轴按住，转身走了两步。"


def _static_blocks(rounds: int, breaker: str | None) -> str:
    """按「静态段 + 静态段 + 可选打断句」的节奏拼出多段样本。

    每段加逐轮不同的序数前缀，理由同 `_grow`：否则会撞上 T-10 的重复段落检测，
    测试就分不清红的是静态描写还是重复灌水。
    """
    lines: list[str] = []
    for index in range(rounds):
        ordinal = _ORD[index % len(_ORD)]
        lines.append(f"{ordinal}甲、{_STATIC_PARAGRAPHS[index % 4]}")
        lines.append(f"{ordinal}乙、{_STATIC_PARAGRAPHS[(index + 1) % 4]}")
        if breaker is not None:
            lines.append(breaker)
    return "\n".join(lines)


# D-25 第 2 条专用：静态连段一路铺到底，实测 wc=1708 / max_static_run=16 / 无对话。
# 段数 16 > 4 所以躲开第 1 条，密度过关所以躲开第 3 条，无对话所以躲开第 4 条。
STATIC_RUN_FLOOD = _static_blocks(8, None)

# D-25 第 3 条专用：动作句打断，让 max_static_run 恰好停在 2；段落全是纯景物，
# 事件密度不过关。实测 wc=2227 / run=2 / sp=15 / event_density_passed=False。
# 打断句刻意只有 7 字（低于 30 字重复门槛，且不含动作词也不含语义钩子）。
_DENSITY_STATIC_PARAGRAPHS = (
    "晨雾漫过山谷，苍翠松林在灰白的光里静静矗立。空气微凉，带着湿润泥土气息。"
    "远处湖面平滑如镜，倒映天边淡淡云影。岸边芦苇轻轻摇曳，无声诉说岁月宁静。"
    "雾色一层压着一层，把远山的轮廓化成淡墨，天与水的界线也随之模糊不清。",
    "阳光透过云层，斑驳石阶上泛起温暖金色光晕。庭院深处，一株老梅静默伫立，枝干虬曲。"
    "青苔覆满井沿，井水幽深清冽。廊檐下风铃一动不动，四周一片安详寂静。"
    "墙头的瓦缝里嵌着几粒草籽，颜色淡得几乎与土同色，仿佛从来就长在那里。",
    "时光仿佛凝固，一切显得那样安宁美好，没有什么值得担忧，也没有什么需要改变。"
    "这是一个平静清晨，如同过去无数清晨一样，安稳地开始，又将安稳地结束。"
    "檐下的水痕早已干透，井台的凉意一如往年，连一丝声响也不肯留在院子里。",
    "山谷依旧沉睡，湖水依旧平静，岁月静好，现世安稳，令人心生眷恋满足之情。"
    "檐角的雨痕早已干透，墙根的野草纹丝不动，连一丝风也没有留下痕迹。"
    "天光缓缓沉下来，落在瓦脊边缘，整座院子被裹进一种没有方向的灰白里。",
)
STATIC_LOW_DENSITY = "\n".join(
    line
    for index in range(10)
    for line in (
        f"{_ORD[index % len(_ORD)]}甲、{_DENSITY_STATIC_PARAGRAPHS[index % 4]}",
        f"{_ORD[index % len(_ORD)]}乙、{_DENSITY_STATIC_PARAGRAPHS[(index + 1) % 4]}",
        "此外别无声息。",
    )
)

# 第 2 条的下边界样本：动作句把静态连段打断在 2，无对话，密度过关。
# 实测 wc=1908 / run=2 / sp=16 / dlg=0 → 四条判定全 False。
# 它存在的唯一目的是钉住「第 2 条门槛是 3 不是 2」这个阈值本身：
# 反向验证时把门槛改成 >= 2，只有这个样本会变红（归因用的 `_clause_flags`
# 在测试里重算逻辑，检测不到生产端阈值漂移）。
STATIC_RUN_AT_LIMIT = _static_blocks(8, _STATIC_BREAKER)

# T-08 第 4 条专用（本批新增的那条判定）：大段静态描写 + 几句纯寒暄对话。
# 前三条判定一见对话就放过，只有第 4 条能抓住这种「插几句话掩护景物灌水」。
# 实测 wc=1934 / run=2 / sp=16 / dlg=4 / 密度过关 —— c1..c3 全 False，只有 c4 True。
STATIC_TOKEN_DIALOGUE = (
    STATIC_RUN_AT_LIMIT + "\n“今天雾好大。”他说。\n“是啊，看不见对面山。”她答。\n"
)

# T-10 样本。两个都要先垫够字数：`_evaluate_repetition_risk` 有 word_count >= 800 的
# 启用门槛，字数不够时 risk 恒为 False，那样测试是「因为对的理由绿的」的反面。
_REPEAT_FILLER_UNIT = (
    "他把{n}号抽屉拉开一寸，指腹压住里面那张对折的纸，又缓缓推回去，锁舌轻轻咬上。"
    "窗外的雨顺着铁皮檐口往下淌，敲在水泥台阶上，一下接一下，谁也没有开口。"
)
_REPEAT_FILLER = "\n".join(_REPEAT_FILLER_UNIT.format(n=index) for index in range(1, 13))

# 整段照抄 4 次，每段 77 字（>=30 字门槛）。实测 max_repeat=4 / longest=77 → 命中
# 「同段 >= 3 次且 >= 30 字」这一条。
_REPEATED_UNIT = (
    "他把钥匙压在账簿下面，指节抵着桌沿，一寸一寸把抽屉推回去，直到锁舌轻轻咬上。"
    "屋里没有别的声音，只有窗外雨水顺着铁皮檐口往下淌，敲在水泥台阶上，一下接一下。"
)
REPEATED_PARAGRAPH_FLOOD = (
    _REPEAT_FILLER
    + "\n"
    + "\n".join([_REPEATED_UNIT] * 4)
    + "\n他终于抬头，看向门口那道影子。"
)

# 防误杀：短对话应答重复 5 次是正常写法（每段 3 字，低于 30 字门槛），必须不判。
SHORT_LINE_REPEAT = _REPEAT_FILLER + "\n" + "\n".join(["“好。”"] * 5)

# D-24 样本：正文用正向对照，只在末尾接一句泄气的短结尾。
# 关键是**不加长填充**——这正是批 4 当时做不到的事：38 字的尾巴会被正文钩子盖住。
SHORT_FLAT_PUNCTUATION_TAIL = "他伸了个懒腰，觉得这一天过得很舒服。真的很舒服吗？当然很舒服！\n"
SHORT_FLAT_CLOSURE_TAIL = "他关灯躺下，屋里再没有别的动静，一切都平静下来。\n"
SHORT_TAIL_PUNCTUATION_HOOK = GOOD_DRAMATIC + SHORT_FLAT_PUNCTUATION_TAIL
SHORT_TAIL_FLAT_CLOSURE = GOOD_DRAMATIC + SHORT_FLAT_CLOSURE_TAIL


class TestBadSampleRegression:
    """坏样本必须被拦住。每条断言的期望值都是实测出来的，不是照文档猜的。

    评分入口与生产完全一致（`_score_density_sample` → `_score_story_quality_candidate`，
    `chapter_mission=None`、`target=3000`、`min=2000`），所以这里的 code 就是用户在
    前端会看到的那批 code。
    """

    def test_all_description_sample_is_blocked(self):
        """全景物描写：静态描写 + 事件密度双杀，`max_plain_unit_run_ratio` 应该顶到 1.0
        （整章没有任何一句推进）。"""
        result = _score_density_sample(BAD_ALL_DESCRIPTION)
        codes = set(result["quality_issue_codes"])

        assert "static_description_risk" in codes
        assert "event_density_weak" in codes
        assert result["static_description_risk"] is True
        assert result["event_density_passed"] is False
        assert result["progression_unit_count"] == 0
        assert result["quality_metric_snapshot"]["max_plain_unit_run_ratio"] == 1.0

    def test_flat_chatter_sample_is_blocked(self):
        """纯寒暄灌水：批 3 之前它靠「有引号就算推进」拿到 rate 1.0，现在必须归零。"""
        result = _score_density_sample(BAD_FLAT_CHATTER)
        codes = set(result["quality_issue_codes"])

        assert "event_density_weak" in codes
        assert result["event_density_passed"] is False
        assert result["state_change_interval_passed"] is False
        assert result["quality_metric_snapshot"]["progression_unit_rate"] == 0.0

    def test_mundane_sequence_sample_is_blocked(self):
        """流水账：动作词足够多，事件密度门放行——这是**有意**的（密度门是底线门，
        不承担质量优选）。拦住它的是章末压力门，说明两道门的分工是可用的。"""
        result = _score_density_sample(BAD_MUNDANE_SEQUENCE)
        codes = set(result["quality_issue_codes"])

        assert "ending_pressure_missing" in codes
        assert result["ending_pressure_passed"] is False
        assert result["event_density_passed"] is True, "流水账不该由密度门负责，改这里前先看 T-06"

    def test_punctuation_only_hook_sample_is_blocked(self):
        """结尾只剩「舒服吗？舒服！」：标点是辅助信号，顶不了语义压力。
        正文本身合格（密度、静态描写全过），唯一的失败维度就是章末压力。"""
        result = _score_density_sample(BAD_PUNCTUATION_HOOK)
        codes = set(result["quality_issue_codes"])
        snapshot = result["quality_metric_snapshot"]

        assert "ending_pressure_missing" in codes
        assert result["ending_pressure_passed"] is False
        assert snapshot["ending_semantic_hit_count"] == 0
        assert snapshot["ending_weak_hit_count"] >= 2, "样本必须真的带问号叹号，否则测的不是这条"
        assert result["event_density_passed"] is True, "正文部分必须是合格的，否则失败维度不唯一"
        assert result["static_description_risk"] is False

    def test_flat_closure_sample_is_blocked(self):
        """结尾「一切都平静下来」：完整收束表达是一票否决，强正文救不回来。"""
        result = _score_density_sample(BAD_FLAT_CLOSURE)
        codes = set(result["quality_issue_codes"])

        assert "ending_pressure_missing" in codes
        assert result["ending_pressure_passed"] is False
        assert result["quality_metric_snapshot"]["flat_closure_markers"] != []
        assert result["event_density_passed"] is True, "正文部分必须是合格的，否则失败维度不唯一"

    def test_flat_closure_markers_reach_quality_metric_snapshot(self):
        """一票否决必须可解释。批 2 把 `ending_semantic_hit_count` /
        `ending_weak_hit_count` 补进了快照白名单，却漏了 `flat_closure_markers`
        这个 list——结果用户只看到「章末未递出压力」，既不知道是哪句话触发的，
        也没法判断是不是误杀。本批补上，并且**正向对照必须是空 list 而不是缺键**。"""
        blocked = _score_density_sample(BAD_FLAT_CLOSURE)["quality_metric_snapshot"]
        control = _score_density_sample(GOOD_DRAMATIC)["quality_metric_snapshot"]

        assert "flat_closure_markers" in blocked, "新字段必须穿过快照白名单"
        assert any("一切都" in marker for marker in blocked["flat_closure_markers"])
        assert len(blocked["flat_closure_markers"]) <= 4, "只透出前 4 个，别把整张词表倒给前端"
        assert control["flat_closure_markers"] == []

    def test_positive_control_triggers_no_blocker(self):
        """防误杀锚点：**任何调阈值的改动都必须保证这一条是绿的。**
        它有目标、阻力、反转、代价，章末留压力，一个 blocker 都不该有。"""
        result = _score_density_sample(GOOD_DRAMATIC)

        assert result["quality_issue_codes"] == []
        assert result["quality_issue_summary"]["tone"] == "success"
        assert result["static_description_risk"] is False
        assert result["event_density_passed"] is True
        assert result["ending_pressure_passed"] is True
        assert result["dialogue_changes_state"] is True

    def test_density_class_samples_score_far_below_control(self):
        """密度类坏样本与正向对照的分差要够大（≥300，与 T-16 的验收标准对齐），
        否则「优选最好版本」在候选里根本挑不出来。实测 1578 / 1001 / 493。"""
        good = _score_density_sample(GOOD_DRAMATIC)["score"]

        for label, sample in BAD_SAMPLES_DENSITY_CLASS:
            gap = good - _score_density_sample(sample)["score"]
            assert gap >= 300, f"{label} 与正向对照的分差只有 {gap}，优选挑不出好版本"

    def test_ending_class_samples_score_below_control(self):
        """结尾类坏样本只差在最后一段，分差比密度类小得多——实测两个都正好是 260，
        够不到 300。这不是缺陷，是「一处结尾」在总分里本来就只值这么多；
        真正的防线是它们必然带上 `ending_pressure_missing` 这个 blocker（见上面两条）。
        阈值写 200 是为了留出评分权重微调的余量，同时仍能拦住「分数不降」的回归。"""
        good = _score_density_sample(GOOD_DRAMATIC)["score"]

        for label, sample in BAD_SAMPLES_ENDING_CLASS:
            gap = good - _score_density_sample(sample)["score"]
            assert gap >= 200, f"{label} 与正向对照的分差只有 {gap}，结尾泄气几乎没有代价"


class TestStaticActionMarkerTable:
    """T-09：静态段落判定的动作词表。

    这张表决定 `max_static_run` / `static_paragraph_count` 有没有值，而那两个指标
    又是 `static_description_risk` 后三条判定的唯一输入。表一坏，三条判定同时哑掉，
    而且不会有任何报错——所以词表本身需要断言，不能只测下游。
    """

    def test_high_frequency_single_chars_are_not_action_markers(self):
        """D-08 第一层根因：「看 / 却 / 但 / 发现」是汉语超高频字，纯风景里随手就有。
        它们留在动作词表里，等于把景物段落全判成「有动作」。"""
        forbidden = ("看", "却", "但", "发现")

        for marker in forbidden:
            assert marker not in PipelineOrchestrator.STATIC_ACTION_MARKERS, (
                f"「{marker}」是高频单字，不能当动作词——"
                "它会让纯景物段落逃过静态判定（D-08）"
            )

    def test_ambient_motion_markers_never_leak_into_action_markers(self):
        """自然现象动词没有行为主体，不构成情节推进。单列一张表就是为了能断言它没混进来。"""
        overlap = set(PipelineOrchestrator.AMBIENT_MOTION_MARKERS) & set(
            PipelineOrchestrator.STATIC_ACTION_MARKERS
        )

        assert overlap == set(), f"自然现象动词漏进动作词表：{sorted(overlap)}"

    def test_pure_scenery_with_high_frequency_chars_counts_as_static(self):
        """T-09 的验收样本：130 字纯风景，含那四个高频字，必须判静态。
        修复前实测 static_paragraph_count=0，修复后是 1。"""
        runs = PipelineOrchestrator._estimate_static_description_runs([_T09_ESCAPE_SCENERY])

        assert runs["static_paragraph_count"] == 1
        assert runs["max_static_run"] == 1

    def test_paragraph_with_real_action_is_not_static(self):
        """反方向防误杀：同一段接一句真动作就不该判静态，否则整张表就是「全判静态」，
        等于没有判定。"""
        runs = PipelineOrchestrator._estimate_static_description_runs([_T09_WITH_ACTION])

        assert runs["static_paragraph_count"] == 0
        assert runs["max_static_run"] == 0

    def test_short_scenery_paragraph_is_not_static(self):
        """100 字门槛的下边界：短景物句是正常的场景切换，不算静态灌水。"""
        runs = PipelineOrchestrator._estimate_static_description_runs(["晨雾漫过山谷，湖面平得像镜子。"])

        assert runs["static_paragraph_count"] == 0


class TestStaticDescriptionRiskBranches:
    """T-08 + D-25：`static_description_risk` 四条 or 逐条覆盖。

    D-25 说的就是这里：修复前只有第 1 条有覆盖，把 `_estimate_static_description_runs`
    整个清零都不会有测试变红。所以每条判定都配一个**只命中它自己**的样本，
    并且断言其余三条是 False——这样改坏任何一条都能定位到具体是哪条。
    """

    @staticmethod
    def _clause_flags(result: dict) -> dict:
        """把四条判定各自算一遍，用于定位。逻辑必须与生产端逐字对应。"""
        word_count = result["word_count"]
        paragraphs = result["paragraph_count"]
        dialogue = result["dialogue_marker_count"]
        runs = result["static_description_runs"]
        max_run = runs["max_static_run"]
        static_paragraphs = runs["static_paragraph_count"]
        return {
            "c1_no_dialogue_few_paragraphs": dialogue == 0
            and paragraphs <= 4
            and word_count >= 1200,
            "c2_long_static_run": word_count >= 1200 and max_run >= 3,
            "c3_low_density_static": word_count >= 2000
            and result["event_density_passed"] is False
            and max_run >= 2,
            "c4_token_dialogue_cover": word_count >= 1600
            and dialogue > 0
            and max_run >= 2
            and static_paragraphs >= 3,
        }

    def _assert_only_clause(self, sample: str, clause: str) -> dict:
        result = _score_density_sample(sample)
        flags = self._clause_flags(result)

        assert result["static_description_risk"] is True
        assert flags[clause] is True, f"{clause} 没命中，实测 {flags}"
        others = {name: hit for name, hit in flags.items() if name != clause}
        assert not any(others.values()), f"样本串味了，同时命中 {others}——改坏 {clause} 测试也不会红"
        return result

    def test_clause_1_whole_chapter_description_without_dialogue(self):
        """第 1 条：无对话 + 段数 <= 4 + 字数 >= 1200。批 4 唯一覆盖到的那条。"""
        self._assert_only_clause(BAD_ALL_DESCRIPTION, "c1_no_dialogue_few_paragraphs")

    def test_clause_2_long_static_paragraph_run(self):
        """第 2 条：静态连段 >= 3。门槛保持 >= 3 而不是照抄孤儿版的 >= 2——
        真实语料（n=136）里 >= 2 触发 4.4%、>= 3 触发 2.9%，都可接受，
        取宽的那个符合「宁可漏判不要误杀」。"""
        result = self._assert_only_clause(STATIC_RUN_FLOOD, "c2_long_static_run")

        assert result["static_description_runs"]["max_static_run"] >= 3
        assert result["dialogue_marker_count"] == 0

    def test_clause_2_threshold_stays_at_three_static_paragraphs(self):
        """第 2 条的门槛值本身要钉住，光测「命中」测不出阈值漂移。

        样本是 max_static_run 恰好 2、无对话、密度过关的静态连段：门槛是 3 时它必须
        放行，门槛一旦松到孤儿版的 2 就会被判风险。反向验证里把 `>= 3` 改成 `>= 2`，
        只有这一条会红——其余覆盖判定命中的测试全绿，因为放松门槛不会让它们漏掉。
        """
        result = _score_density_sample(STATIC_RUN_AT_LIMIT)

        assert result["static_description_runs"]["max_static_run"] == 2
        assert result["dialogue_marker_count"] == 0
        assert result["event_density_passed"] is True
        assert result["static_description_risk"] is False, (
            "静态连段只有 2 段就判风险，门槛松到了孤儿版的 >= 2："
            "真实语料触发率会从 2.9% 涨到 4.4%，属于误杀方向"
        )

    def test_clause_3_low_density_with_static_pairs(self):
        """第 3 条：字数 >= 2000 + 密度不过关 + 静态连段 >= 2。
        比第 2 条松，靠密度门一起兜——所以样本必须是 event_density_passed False。"""
        result = self._assert_only_clause(STATIC_LOW_DENSITY, "c3_low_density_static")

        assert result["event_density_passed"] is False
        assert result["static_description_runs"]["max_static_run"] == 2

    def test_clause_4_token_dialogue_cannot_cover_description_flood(self):
        """第 4 条（T-08 本批新增）：唯一能抓「插几句寒暄对话掩护大段描写」的判定。
        前三条一有对话就放过，这条要求 dlg > 0 且静态段落总数 >= 3。"""
        result = self._assert_only_clause(STATIC_TOKEN_DIALOGUE, "c4_token_dialogue_cover")

        assert result["dialogue_marker_count"] > 0, "样本必须有对话，否则测的还是前三条"
        assert result["static_description_runs"]["static_paragraph_count"] >= 3
        assert "static_description_risk" in result["quality_issue_codes"]

    def test_static_run_metrics_reach_quality_metric_snapshot(self):
        """两个指标必须穿过快照白名单——那是新字段唯一会被静默丢掉的地方。"""
        snapshot = _score_density_sample(STATIC_RUN_FLOOD)["quality_metric_snapshot"]

        assert snapshot["max_static_run"] >= 3
        assert snapshot["static_paragraph_count"] >= 3

    def test_positive_control_hits_no_static_clause(self):
        """防误杀：正向对照四条判定都不该命中。"""
        flags = self._clause_flags(_score_density_sample(GOOD_DRAMATIC))

        assert not any(flags.values()), f"正向对照被静态判定误杀：{flags}"


class TestRepeatedParagraphFlood:
    """T-10：精确重复段落检测。

    为什么必须有：重复段落同样贡献 `paragraph_count` 与 `progression_unit_count`，
    也就是说这道门落地之前，**复制粘贴同一段能刷高分**。
    真实语料 n=136 实测触发率 0.000，所以它不会碰到正常文本。
    """

    def test_repeated_paragraph_flood_is_detected(self):
        result = _score_density_sample(REPEATED_PARAGRAPH_FLOOD)

        assert result["repetition_risk"] is True
        assert result["max_repeated_paragraph_count"] >= 3
        assert result["longest_repeated_paragraph_chars"] >= 30
        assert "repeated_paragraph_flood" in result["quality_issue_codes"]

    def test_repeated_paragraph_flood_is_a_hard_blocker(self):
        """精确重复是字符串完全相同，判定 100% 可靠，所以直接做 blocker，
        不走 soft_pass 兜底——没有任何正当理由让整段照抄的正文过门。"""
        _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=REPEATED_PARAGRAPH_FLOOD,
            violations=[],
            chapter_mission=None,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        assert gate["passed"] is False
        codes = [blocker["code"] for blocker in gate.get("blockers") or []]
        assert "repeated_paragraph_flood" in codes

    def test_repetition_penalty_outweighs_the_score_it_can_farm(self):
        """判罚必须大于重复段落自身能刷到的正分，否则复制粘贴仍然划算。
        实测灌水样本 score=-260，短应答样本 score=273。"""
        flood = _score_density_sample(REPEATED_PARAGRAPH_FLOOD)["score"]
        clean = _score_density_sample(SHORT_LINE_REPEAT)["score"]

        assert flood < 0, f"重复灌水的总分还是正的（{flood}），凑字数依然划算"
        assert clean > flood

    def test_short_repeated_dialogue_lines_are_not_flagged(self):
        """防误杀：「好。」这类短应答重复是正常写法，30 字门槛就是为它留的。"""
        result = _score_density_sample(SHORT_LINE_REPEAT)

        assert result["repetition_risk"] is False
        assert result["repeated_paragraph_count"] == 0
        assert "repeated_paragraph_flood" not in result["quality_issue_codes"]

    def test_existing_bad_samples_are_not_repetition_false_positives(self):
        """其余坏样本都不该带重复码——否则「它为什么被拦」这个问题就没有唯一答案了。
        批 6 落地这道门时，`GOOD_DRAMATIC` 与 `BAD_FLAT_CHATTER` 双双误报，
        根因是 `_grow` 只替换首行占位符（见该函数的注释）。"""
        for label, sample in (
            ("GOOD_DRAMATIC", GOOD_DRAMATIC),
            ("BAD_ALL_DESCRIPTION", BAD_ALL_DESCRIPTION),
            ("BAD_FLAT_CHATTER", BAD_FLAT_CHATTER),
            ("BAD_MUNDANE_SEQUENCE", BAD_MUNDANE_SEQUENCE),
        ):
            result = _score_density_sample(sample)
            assert result["repetition_risk"] is False, (
                f"{label} 被重复检测误判，实测重复实例 {result['repeated_paragraph_instances']} 个"
            )

    def test_repetition_metrics_reach_quality_metric_snapshot(self):
        """五个新字段都要穿过白名单，用户才知道「重复灌水」是凭什么判的。"""
        snapshot = _score_density_sample(REPEATED_PARAGRAPH_FLOOD)["quality_metric_snapshot"]

        for field in (
            "repetition_risk",
            "repeated_paragraph_count",
            "max_repeated_paragraph_count",
            "repeated_paragraph_ratio",
            "longest_repeated_paragraph_chars",
        ):
            assert field in snapshot, f"{field} 没穿过快照白名单"
        assert snapshot["repetition_risk"] is True

    def test_short_text_stays_below_the_word_count_gate(self):
        """word_count >= 800 才启用：短文本统计量不稳，不该在那里下判断。"""
        tiny = "\n".join([_REPEATED_UNIT] * 4)
        result = _score_density_sample(tiny)

        assert result["word_count"] < 800
        assert result["repetition_risk"] is False


class TestEndingCoreWindow:
    """D-24：章末压力的末段判定。

    修复前 `_evaluate_ending_pressure` 只看 `condensed_text[-260:]` 这一个定长尾窗，
    于是 38 字的泄气结尾会被正文自己的钩子漏进来盖掉：同一个坏结尾在短尾巴下
    score=1302 / codes=[]，在 275 字长尾巴下才是 score=1042 / ending_pressure_missing。
    真实语料末段 p50 只有 24 字、p95 是 151 字，所以这种掩护是生产常态，不是边缘情况。

    修法是**保留尾窗、另加末段否决**：把窗口改小反而更差——真实通过池的
    通过率从 0.812 掉到 0.475~0.782，那是误杀不是召回。
    """

    def test_short_punctuation_only_tail_is_no_longer_masked(self):
        """D-24 的验收样本：31 字尾巴，无长填充。修复前 codes=[]，现在必须被拦。"""
        result = _score_density_sample(SHORT_TAIL_PUNCTUATION_HOOK)

        assert result["ending_pressure_passed"] is False
        assert "ending_pressure_missing" in result["quality_issue_codes"]
        assert result["ending_pressure"]["ending_core_deflating"] is True

    def test_short_flat_closure_tail_is_blocked_by_closure_markers(self):
        """另一条路径：末段是完整收束语（「一切都平静下来」），由 closure 词表直接否决，
        不依赖末段泄气判定。断言 deflating 是 False，是为了说明这两条路径互相独立。"""
        result = _score_density_sample(SHORT_TAIL_FLAT_CLOSURE)
        pressure = result["ending_pressure"]

        assert result["ending_pressure_passed"] is False
        assert pressure["flat_closure_markers"], "收束词表应当命中"
        assert pressure["ending_core_deflating"] is False

    def test_ending_core_is_the_last_paragraph_not_a_fixed_window(self):
        """末段按换行切，长度就是最后一段的长度，跟 260 这个定长窗口无关。
        调用方必须传原文：condensed 已经没有换行了，切不出末段。"""
        control = _score_density_sample(GOOD_DRAMATIC)["ending_pressure"]
        short_tail = _score_density_sample(SHORT_TAIL_PUNCTUATION_HOOK)["ending_pressure"]

        assert control["ending_core_chars"] < 260
        assert short_tail["ending_core_chars"] == len(
            "".join(SHORT_FLAT_PUNCTUATION_TAIL.split())
        )

    def test_weak_only_ending_needs_two_hits_to_be_deflating(self):
        """`ENDING_CORE_WEAK_ONLY_LIMIT = 2` 是标定出来的，不是拍的：
        真实通过池 w_min=1 → 0.762、w_min=2 → 0.802、w_min=3 → 0.812 但放过了坏样本。
        取 2 的净代价是 1 个真实样本，换来短泄气结尾被拦住。"""
        assert PipelineOrchestrator.ENDING_CORE_WEAK_ONLY_LIMIT == 2

        pressure = _score_density_sample(SHORT_TAIL_PUNCTUATION_HOOK)["ending_pressure"]
        assert pressure["ending_core_semantic_hit_count"] == 0
        assert pressure["ending_core_weak_hit_count"] >= 2

    def test_long_flat_ending_is_deflating_even_without_weak_markers(self):
        """`ENDING_CORE_FLAT_CHARS = 150` 覆盖另一种形态：末段又长又平，
        连标点小把戏都没有。真实语料零额外代价（末段 p95 = 151 字）。"""
        assert PipelineOrchestrator.ENDING_CORE_FLAT_CHARS == 150

        pressure = _score_density_sample(BAD_FLAT_CLOSURE)["ending_pressure"]
        assert pressure["ending_core_chars"] >= 150
        assert pressure["ending_core_deflating"] is True

    def test_positive_control_ending_still_passes(self):
        """防误杀锚点：正向对照的末段自己就带语义钩子，不该被末段判定牵连。
        实测末段 40 字、语义命中 3 个。"""
        result = _score_density_sample(GOOD_DRAMATIC)
        pressure = result["ending_pressure"]

        assert result["ending_pressure_passed"] is True
        assert pressure["ending_core_semantic_hit_count"] >= 1
        assert pressure["ending_core_deflating"] is False
        assert result["quality_issue_codes"] == []

    def test_ending_core_metrics_reach_quality_metric_snapshot(self):
        """四个新字段都要穿过白名单，否则用户只看到「章末未递出压力」，
        不知道是哪一段泄的气——这正是批 4 在 `flat_closure_markers` 上踩过的坑。"""
        blocked = _score_density_sample(SHORT_TAIL_PUNCTUATION_HOOK)["quality_metric_snapshot"]
        control = _score_density_sample(GOOD_DRAMATIC)["quality_metric_snapshot"]

        for field in (
            "ending_core_chars",
            "ending_core_semantic_hit_count",
            "ending_core_weak_hit_count",
            "ending_core_deflating",
        ):
            assert field in blocked, f"{field} 没穿过快照白名单"
        assert blocked["ending_core_deflating"] is True
        assert control["ending_core_deflating"] is False

    def test_short_tail_samples_score_below_control(self):
        """短尾巴的分差要和长填充版一致（实测都是 260），
        否则「掩护」只是从判定挪到了评分里。"""
        good = _score_density_sample(GOOD_DRAMATIC)["score"]

        for label, sample in (
            ("SHORT_TAIL_PUNCTUATION_HOOK", SHORT_TAIL_PUNCTUATION_HOOK),
            ("SHORT_TAIL_FLAT_CLOSURE", SHORT_TAIL_FLAT_CLOSURE),
        ):
            gap = good - _score_density_sample(sample)["score"]
            assert gap >= 200, f"{label} 与正向对照的分差只有 {gap}，短泄气结尾几乎没有代价"


# ============================================================================
# 批 7 / T-11：焦点人物缺席进入候选评分
#
# 判罚的定位是 **warning 而不是 blocker**：LLM 常用别名或称谓替代本名
# （「顾家小姐」代「顾棠」），字符串匹配天生会误判。所以下面所有测试都同时
# 断言「分数被压」与「gate 里没有多出 blocker」两件事——只测前者的话，
# 有人把它升级成硬 blocker 也不会红。
#
# 正文样本沿用 GOOD_DRAMATIC（2504 字，零 blocker 的正向对照）：焦点人物
# 判罚必须能在一个各维度都健康的样本上单独显形，否则测的是别的东西。
# 人名用「沈决」「楚昭」这类不出现在样本正文里的通用双字名，理由见 8.3 铁律 5。
# ============================================================================

_T11_MISSION_TWO_NAMES = {"focus_characters": ["沈决", "楚昭"]}


def _score_with_mission(content: str, mission) -> dict:
    """与 _score_density_sample 的唯一区别是能传任务书。字数参数共用同一对常量，
    理由见 _SAMPLE_TARGET_WORDS 的注释：让字数判罚在这些断言里保持中性。"""
    return PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=mission,
        target_word_count=_SAMPLE_TARGET_WORDS,
        min_word_count=_SAMPLE_MIN_WORDS,
    )


class TestFocusCharacterAbsence:
    def test_focus_character_missing_penalizes_candidate(self):
        """两个焦点人物一个都没出场（正文 2504 字 ≥ 1200）→ 判罚 −240。

        实测：mission=None 时 score=1302 / codes=[]；两名全缺席时 score=1062。
        差额精确等于 240，说明没有别的维度被顺带影响。
        """
        base = _score_with_mission(GOOD_DRAMATIC, None)
        absent = _score_with_mission(GOOD_DRAMATIC, _T11_MISSION_TWO_NAMES)

        assert base["focus_character_missing"] is False
        assert base["focus_character_names"] == []
        assert absent["focus_character_missing"] is True
        assert absent["focus_character_names"] == ["沈决", "楚昭"]
        assert absent["focus_character_hit_count"] == 0
        assert absent["missing_focus_characters"] == ["沈决", "楚昭"]
        assert base["score"] - absent["score"] == 240, (
            f"判罚不是 240 而是 {base['score'] - absent['score']}，"
            "要么系数被改，要么焦点人物影响到了别的维度"
        )

    def test_focus_character_placeholder_is_ignored(self):
        """任务书写「主角」「男主」这类占位符 → 解析结果为空，零判罚。

        这是最容易误杀的一类：占位符永远不会字面出现在正文里，
        不过滤就等于每一章都判「焦点角色缺席」。
        """
        base = _score_with_mission(GOOD_DRAMATIC, None)
        for mission in (
            {"focus_characters": ["主角", "男主"]},
            {"focus_characters": ["女主", "角色A", "角色B"]},
            {"pov_character": "POV"},          # 大小写不敏感
            {"character_focus": "protagonist"},
        ):
            result = _score_with_mission(GOOD_DRAMATIC, mission)
            assert result["focus_character_names"] == [], f"{mission} 没被过滤掉"
            assert result["focus_character_missing"] is False
            assert result["score"] == base["score"], f"{mission} 产生了判罚"

    def test_partial_hit_does_not_penalize(self):
        """一个命中就不判罚——配角某章不出场是正常叙事。

        「照片」是 GOOD_DRAMATIC 正文里确实存在的词，拿它当人物名可以
        在不改样本的前提下构造「部分命中」。实测 hit_count=1、missing=False，
        分数反而比 base 高 180（`mission_hit_count` 也命中了同一个词）——
        这里只断言没有 −240 判罚，不断言绝对分。
        """
        result = _score_with_mission(
            GOOD_DRAMATIC, {"focus_characters": ["照片", "楚昭"]}
        )
        assert result["focus_character_hit_count"] == 1
        assert result["missing_focus_characters"] == ["楚昭"]
        assert result["focus_character_missing"] is False, (
            "有人出场了还判缺席，判罚条件被从 `not hits` 改成了 `missing_names`"
        )

    def test_short_chapter_is_not_penalized(self):
        """1200 字门槛：短文本不判罚。

        名字解析照常进行（`focus_character_names` 非空），只有 `missing` 为假，
        这样才能区分「没解析到人物」和「解析到了但样本太短不该判」。
        """
        short = "他推开门。\n她抬头看了一眼。\n"
        result = _score_with_mission(short, {"focus_characters": ["沈决"]})
        assert result["word_count"] < 1200
        assert result["focus_character_names"] == ["沈决"]
        assert result["focus_character_missing"] is False

    def test_name_collection_covers_four_sources_and_filters(self):
        """四个数据源都要能出名字，三条约束都要生效。

        每一行都是实测值。`scene_list` 和 dict 嵌套这两条尤其重要：
        生产路径此前从未用过 `chapter_mission` 这条通路，只要有一个源没接上，
        对应形状的任务书就会静默退化成「没有焦点人物」。
        """
        collect = PipelineOrchestrator._collect_focus_character_names

        assert collect({"focus_characters": ["沈决", "楚昭"]}) == ["沈决", "楚昭"]
        assert collect({"character_focus": {"main": "沈决", "second": "楚昭"}}) == ["沈决", "楚昭"]
        assert collect({"pov_character": "沈决"}) == ["沈决"]
        assert collect(
            {"scene_list": [{"characters": ["沈决"]}, {"characters": "楚昭/裴渊"}]}
        ) == ["沈决", "楚昭", "裴渊"]
        # 逗号/顿号/斜杠混排要能切开，占位符要在切开之后再过滤
        assert collect({"focus_characters": "沈决，主角、楚昭"}) == ["沈决", "楚昭"]
        # 单字被丢弃（标点残渣），13 字以上被丢弃（被误切的句子不是人名）
        assert collect({"focus_characters": ["甲"]}) == []
        assert collect({"focus_characters": ["她在雨里站了很久很久很久很久"]}) == []
        # 去重后取前 8
        assert len(collect({"focus_characters": [f"人物{i}{i}" for i in range(12)]})) == 8
        # 非法输入不炸
        assert collect(None) == []
        assert collect("沈决") == []

    def test_snapshot_exposes_all_four_focus_fields(self):
        """四个字段必须都穿过 quality_metric_snapshot 白名单。

        白名单是新字段唯一的静默丢弃点。只透 `focus_character_missing` 的话，
        用户看到「焦点角色缺席」却不知道系统认为焦点是谁——而这个判定恰恰
        最容易因别名误判，没有 `focus_character_names` 就无法判断是不是误杀。
        """
        snapshot = _score_with_mission(
            GOOD_DRAMATIC, _T11_MISSION_TWO_NAMES
        )["quality_metric_snapshot"]

        assert snapshot["focus_character_names"] == ["沈决", "楚昭"]
        assert snapshot["focus_character_hit_count"] == 0
        assert snapshot["missing_focus_characters"] == ["沈决", "楚昭"]
        assert snapshot["focus_character_missing"] is True

    def test_focus_absence_is_warning_not_blocker(self):
        """全员缺席只进 warning 摘要，绝不进 blockers。

        这条是 T-11 的核心约束：别名匹配不可靠，升级成 blocker 就会拦下
        用称谓写人物的正常章节。实测 gate.passed=True、blockers=[]，
        而 `quality_rule_warnings.codes` 里能看到 focus_character_missing。
        """
        guard = _score_with_mission(GOOD_DRAMATIC, _T11_MISSION_TWO_NAMES)
        assert guard["quality_issue_codes"] == ["focus_character_missing"]
        assert guard["quality_issue_labels"] == ["焦点角色缺席"]

        _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=GOOD_DRAMATIC,
            violations=[],
            chapter_mission=_T11_MISSION_TWO_NAMES,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        assert gate.get("passed") is True, "焦点人物缺席把章节拦下了，它应该只是 warning"
        blocker_codes = [item.get("code") for item in gate.get("blockers") or []]
        assert "focus_character_missing" not in blocker_codes

        attached = PipelineOrchestrator._attach_quality_gate_status_to_guard(guard, gate)
        warnings = attached.get("quality_rule_warnings") or {}
        assert warnings.get("codes") == ["focus_character_missing"], (
            "gate 通过时 warning 通道丢了 focus_character_missing，前端就看不到这条提示"
        )
        assert warnings.get("labels") == ["焦点角色缺席"]

    def test_focus_missing_has_label_and_hint(self):
        """标签与修复指引都要有，否则前端显示原始 code。"""
        assert PipelineOrchestrator.QUALITY_ISSUE_LABELS["focus_character_missing"] == "焦点角色缺席"
        hint = PipelineOrchestrator.QUALITY_ISSUE_HINTS["focus_character_missing"]
        assert hint and "出场" in hint

    def test_placeholder_table_stays_lowercase_comparable(self):
        """占位符表必须能被 `.lower()` 命中，否则 "POV" / "Protagonist" 漏过。"""
        table = PipelineOrchestrator.FOCUS_CHARACTER_PLACEHOLDERS
        for ascii_word in ("protagonist", "pov"):
            assert ascii_word in table
            assert ascii_word == ascii_word.lower(), (
                f"{ascii_word} 在表里不是小写，`name.lower() in table` 这条分支就失效了"
            )


def _score_words(content: str, target: int, minimum: int) -> dict:
    """字数维度专用打分助手：这里**故意显式传字数**，与 `_score_density_sample`
    的中性取值相对——结构类断言要字数中性，字数类断言要能精确控制三个标志。"""
    return PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=None,
        target_word_count=target,
        min_word_count=minimum,
    )


class TestWordCountPenalties:
    """T-12：字数维度四层断链。

    修复前 `_score_story_quality_candidate` 收了 `target_word_count` /
    `min_word_count` 两个参数却在函数体里**零引用**——字数是 CLAUDE.md 的第一
    目标，却完全没进候选评分，同时四个调用层各自漏传或传硬编码 3000/2000。

    这一组断言全部用 `GOOD_DRAMATIC`（2504 字）做载体，**只改配置不改正文**，
    这样分差就只可能来自字数判罚。中性基线 score=1302（2026-08-19 实测）。
    """

    NEUTRAL_TARGET = 2500
    NEUTRAL_MIN = 2250

    def _neutral_score(self) -> int:
        return _score_words(GOOD_DRAMATIC, self.NEUTRAL_TARGET, self.NEUTRAL_MIN)["score"]

    def test_word_params_actually_reach_the_score(self):
        """最核心的一条：同一份正文、只改字数配置，分数必须变。

        修复前这条必红——两个参数进不了函数体，任何配置都得同一个分。"""
        neutral = _score_words(GOOD_DRAMATIC, 2500, 2250)["score"]
        below = _score_words(GOOD_DRAMATIC, 4000, 3600)["score"]
        assert neutral != below, (
            "字数配置改了分数没变，说明 target/min 又变回了签名里的死参数"
        )
        assert neutral - below == 620, f"below_min 判罚应为 620，实测分差 {neutral - below}"

    def test_below_min_is_the_heaviest_of_the_three(self):
        """三判罚的相对量级：below_min(620) > far_above(520) > far_below(180)。

        排序依据：低于 min 是**硬性违约**（用户明确要求的最低字数没达到）；
        超上限是**跑题风险**（2 倍目标通常意味着写散了）；只是没够 0.92*target
        属于**够用但偏薄**，判罚最轻，不该压过任何结构缺陷。"""
        neutral = self._neutral_score()
        below_min = neutral - _score_words(GOOD_DRAMATIC, 4000, 3600)["score"]
        far_above = neutral - _score_words(GOOD_DRAMATIC, 1000, 900)["score"]
        far_below = neutral - _score_words(GOOD_DRAMATIC, 2726, 2453)["score"]
        assert (below_min, far_above, far_below) == (620, 520, 180)
        assert below_min > far_above > far_below

    def test_far_below_does_not_stack_on_below_min(self):
        """低于 min 时 far_below 恒为 True，但**不许叠加**。

        判罚表达式里有 `and not word_count_below_min`。没有这个约束，
        一篇字数不足的稿子会被扣 620+180=800，超过任何单项结构缺陷，
        字数维度就从「一个维度」变成「压倒性维度」。"""
        result = _score_words(GOOD_DRAMATIC, 4000, 3600)
        assert result["word_count_below_min"] is True
        assert result["word_count_far_below_target"] is True, (
            "min 高于实际字数时 far_below 必然也成立，这是前提"
        )
        gap = self._neutral_score() - result["score"]
        assert gap == 620, f"叠加了 far_below（应 620，实测 {gap}）"

    def test_far_below_alone_costs_180(self):
        """far_below 单独触发：需要 min <= wc < 0.92*target。

        t=2726 / m=2453 时 floor=2507，而正文 2504 字——差 3 个字，
        刚好落在「达到最低要求但没够优选线」的区间。"""
        result = _score_words(GOOD_DRAMATIC, 2726, 2453)
        assert result["word_count_below_min"] is False
        assert result["word_count_far_below_target"] is True
        assert result["preferred_word_floor"] == 2507
        assert self._neutral_score() - result["score"] == 180

    def test_upper_ceiling_uses_2x_below_2500_and_1_6x_above(self):
        """upper 系数 2.0 / 1.6 来自孤儿版，**不要换成死代码里的 1.25**。

        真实语料敏感性实测（n=82 历史通过池）：2.0/1.6 → 0.012、
        1.6/1.4 → 0.134、1.25/1.25 → 0.305。1.25 会把三成正常章节判成
        「字数远超目标」，是 25 倍的误杀差距。"""
        assert _score_words(GOOD_DRAMATIC, 2500, 2250)["upper_word_ceiling"] == 5000
        assert _score_words(GOOD_DRAMATIC, 2000, 1800)["upper_word_ceiling"] == 4000
        assert _score_words(GOOD_DRAMATIC, 5000, 4500)["upper_word_ceiling"] == 8000
        assert _score_words(GOOD_DRAMATIC, 10000, 9000)["upper_word_ceiling"] == 16000

    def test_upper_ceiling_is_known_non_monotonic_at_2500(self):
        """已知不单调，**这不是待修缺陷**：t=2500 时 upper=5000，
        t=2501 时 upper=4001，目标涨 1 个字上限反而降 999。

        保留原因：2500 是短章/长章的分界，两侧「超长」的含义本就不同。
        这条测试的作用是**把这个反直觉行为钉住**，避免后人"顺手修单调性"
        时无声改掉短章的上限。真要改，先按 §11.2.1 灌真实语料看误杀率。"""
        assert _score_words(GOOD_DRAMATIC, 2500, 2250)["upper_word_ceiling"] == 5000
        assert _score_words(GOOD_DRAMATIC, 2501, 2250)["upper_word_ceiling"] == 4001

    def test_min_above_target_is_clamped_to_target(self):
        """min > target 是配置错误，钳到 target 而不是照着错值判罚。"""
        result = _score_words(GOOD_DRAMATIC, 2000, 5000)
        assert result["min_word_count"] == 2000
        assert result["preferred_word_floor"] == 2000
        assert result["word_count_below_min"] is False

    def test_zero_config_is_fully_neutral(self):
        """零配置 = 字数维度整体缺席，分数必须与中性基线**完全相等**。

        这是第 4 层 `_fallback_select_best_version` 默认 0/0 的安全性依据：
        缺配置时排序退化成 T-12 之前的行为，不会把某个候选单独判死。"""
        result = _score_words(GOOD_DRAMATIC, 0, 0)
        assert (
            result["word_count_below_min"],
            result["word_count_far_below_target"],
            result["word_count_far_above_target"],
        ) == (False, False, False)
        assert result["score"] == self._neutral_score()

    def test_word_requirement_met_is_tri_state(self):
        """`word_requirement_met` 是**三态**：没配 min 时是 None。

        "没配最低字数"不等于"没达标"，前端要显示成「不适用」而不是「未通过」。
        写成 bool 会让所有未配置 min 的章节显示成字数未达标。"""
        assert _score_words(GOOD_DRAMATIC, 2500, 2250)["word_requirement_met"] is True
        assert _score_words(GOOD_DRAMATIC, 4000, 3600)["word_requirement_met"] is False
        assert _score_words(GOOD_DRAMATIC, 2500, 0)["word_requirement_met"] is None
        assert _score_words(GOOD_DRAMATIC, 0, 0)["word_requirement_met"] is None

    def test_word_fields_are_mirrored_into_snapshot(self):
        """七个字数字段必须同时出现在顶层与 `quality_metric_snapshot`。

        snapshot 是前端与 `metadata["quality_metrics"]` 的数据源（见附录 C.1），
        只加顶层字段，前端就永远看不到字数判定。"""
        result = _score_words(GOOD_DRAMATIC, 4000, 3600)
        snapshot = result["quality_metric_snapshot"]
        for field in (
            "target_word_count",
            "min_word_count",
            "preferred_word_floor",
            "upper_word_ceiling",
            "word_count_below_min",
            "word_count_far_below_target",
            "word_count_far_above_target",
            "word_requirement_met",
        ):
            assert field in snapshot, f"snapshot 缺 {field}，前端拿不到"
            assert snapshot[field] == result[field], f"{field} 顶层与 snapshot 不同源"

    def test_word_penalties_do_not_become_gate_blockers(self):
        """字数判罚只影响**评分排序**，不得进 blockers 把章节拦死。

        理由：字数不足有专门的受控续写路径（`enrich` / 首稿重试），
        质量门是底线门，把字数升级成 blocker 会让「偏短但写得好」的稿子
        走不到续写就被判失败。真实语料上 below_min 触发 22%（n=82 通过池），
        升级成 blocker 等于让每五章就有一章直接失败。"""
        result = _score_words(GOOD_DRAMATIC, 4000, 3600)
        assert result["word_count_below_min"] is True
        assert result["quality_issue_codes"] == []

        _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=GOOD_DRAMATIC,
            violations=[],
            chapter_mission=None,
            target_word_count=4000,
            min_word_count=3600,
        )
        assert gate.get("passed") is True
        assert [item.get("code") for item in gate.get("blockers") or []] == []


class TestWordCountWiringAcrossLayers:
    """T-12 的四层接线，逐层各一条。断链的表现是"评分器收了参数但上游没传"，
    只测评分器本身测不出来。"""

    def test_gate_helper_refuses_to_default_word_config(self):
        """第 3 层：`_evaluate_structural_quality_gate_for_content` 的两个字数参数
        **不许有默认值**。

        原来默认 3000/2000，而 `_resolve_config` 产出的是 target/min=0.9 的任意
        档位（800/720 到 20000/18000）——默认值一旦存在，新调用点忘记传就静默
        按 3000/2000 判，真实语料上 `below_min` 会触发 24.1%。现在忘记传是
        TypeError，测试阶段就炸。"""
        import inspect

        signature = inspect.signature(
            PipelineOrchestrator._evaluate_structural_quality_gate_for_content
        )
        for name in ("target_word_count", "min_word_count"):
            parameter = signature.parameters[name]
            assert parameter.default is inspect.Parameter.empty, (
                f"{name} 又有默认值了，会让漏传的调用点静默按错值判字数"
            )

        with pytest.raises(TypeError):
            PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
                review_summaries={},
                content=GOOD_DRAMATIC,
                violations=[],
                chapter_mission=None,
            )

    def test_first_draft_retry_passes_word_config_into_the_guard(self):
        """第 2 层：`_evaluate_first_draft_retry` 原来漏传字数参数。

        后果是同一份 story_guard 自相矛盾：`reason_codes` 里有
        `word_count_far_below_target`，而 guard 的字数标志全是 False
        （按 0/0 判）。前端读 guard 字段，重试提示读 reason_codes，两边打架。"""
        needs_retry, guard, reasons = PipelineOrchestrator._evaluate_first_draft_retry(
            content=GOOD_DRAMATIC,
            violations=[],
            chapter_mission=None,
            target_word_count=4000,
            min_word_count=3600,
        )
        assert needs_retry is True
        assert "word_count_far_below_target" in reasons
        assert guard["target_word_count"] == 4000
        assert guard["min_word_count"] == 3600
        assert guard["word_count_below_min"] is True, (
            "reason_codes 说字数不足，guard 字段却说没问题——就是修复前的断链形态"
        )

    def test_fallback_selection_ranks_with_word_config(self):
        """第 4 层：`_fallback_select_best_version` 的字数配置要能影响候选分数。

        用「完整版 vs 砍半版」两个候选：零配置时两者分差 23（只有结构差异），
        传了 2500/2250 后砍半版额外吃 620 的 below_min 判罚，分差拉到 643。
        best_index 两种情况都是完整版——字数判罚在这里是**加固**已有排序，
        不是改写它。"""
        halved = {"content": GOOD_DRAMATIC[: len(GOOD_DRAMATIC) // 2], "metadata": {}}
        full = {"content": GOOD_DRAMATIC, "metadata": {}}

        bare_index, bare_summary = PipelineOrchestrator._fallback_select_best_version(
            [halved, full], None
        )
        wired_index, wired_summary = PipelineOrchestrator._fallback_select_best_version(
            [halved, full], None, target_word_count=2500, min_word_count=2250
        )

        def score_of(summary, index):
            return next(
                item["score"] for item in summary["candidates"] if item["index"] == index
            )

        assert bare_index == wired_index == 1, "完整版始终该被选中"
        bare_gap = score_of(bare_summary, 1) - score_of(bare_summary, 0)
        wired_gap = score_of(wired_summary, 1) - score_of(wired_summary, 0)
        assert bare_gap > 0, f"无字数配置时完整版仍应凭结构质量胜出（实测分差 {bare_gap}）"
        assert wired_gap - bare_gap == 620, f"字数配置没进候选排序（实测分差 {wired_gap}）"

    def test_fallback_defaults_stay_neutral_not_hardcoded(self):
        """第 4 层的默认值必须是 0（中性），不是 3000/2000。

        这一层与第 3 层的取舍相反：第 3 层判「通过与否」，缺配置必须报错；
        这一层只做**候选排序**，所有候选共享同一份配置，缺配置时字数维度
        整体缺席即可，不会把某个候选单独判死。"""
        import inspect

        signature = inspect.signature(PipelineOrchestrator._fallback_select_best_version)
        assert signature.parameters["target_word_count"].default == 0
        assert signature.parameters["min_word_count"].default == 0

        _index, summary = PipelineOrchestrator._fallback_select_best_version(
            [{"content": GOOD_DRAMATIC, "metadata": {}}], None
        )
        candidate = summary["candidates"][0]
        assert candidate["word_count_below_min"] is False
        assert candidate["word_requirement_met"] is None


# ============================================================================
# 批 8（T-13 / T-14）三态字段。
#
# 两个缺陷同源：**用两态（真/假）表达三态（通过/不通过/不适用）**，于是
# 「没评估」被迫伪装成其中一个，两个方向都撒谎过：
# - T-13 原写法 `True if not expected_dialogue else ...`：任务书没要求对话就报「合格」。
# - T-14 原写法 `word_count < 800` 时返回 `passed=True` + `progression_unit_rate=1.0`
#   + `event_density_per_1000=0.0`——三个互相矛盾的数（推进单元 0 个却推进率 100%）。
#
# 三态之后，**每一个消费点都必须显式区分 `is False` 和 `is not False`**，绝不能用
# 真假判断。下面两个类按「判定本身」+「四层消费点」分别钉住，因为这两类回归的
# 表现完全不同：判定错了是数据错，消费点错了是数据对但用错——后者只测判定测不出来。
#
# 实测分差（GOOD_DRAMATIC，2584 字，mission=None）：
# - dialogue_changes_state：True 1302 / None 1162 / False 1022，每档相差 140。
#   改造前 None 这一档不存在，全部按 True 记 1302（白送 140）；若照真假判断改成
#   `if ... else -140`，None 会落到 1022（倒扣 140）——摆动幅度 280，占好样本 11%。
# - 密度三判定同时钉值：True 1302 / None 1072 / False 582。None 与 False 相差 490，
#   这 490 正是「凭章节短到测不了就判它密度不合格」的代价。
# ============================================================================

# 只声明 dialogue_strategy，不带 scene_list：让 expected_dialogue=True 而
# 场景兑现维度保持缺席（scene_count=0），把断言限制在对话维度上。
_T13_DIALOGUE_MISSION = {"dialogue_strategy": {"mode": "攻防"}}

# 零对话但推进充分的正文（2018 字 ≥ 800 字密度评估下限）。
# 这是 T-13 的 None 分支唯一的成立条件：**任务书没要求对话 + 正文确实没有对话**。
_T13_NO_DIALOGUE = "\n".join(
    f"第{index}段，他推开门走进屋里，发现桌上的钥匙不见了，"
    f"于是决定沿着走廊往下追查线索，脚步声在身后越来越近。"
    for index in range(1, 40)
)

# 有对话痕迹但对话不改变任何局势：纯寒暄应答，state_change_marker_count=0。
_T13_FLAT_DIALOGUE = "\n".join(
    line
    for index in range(1, 20)
    for line in (
        f"“第{index}天天气不错。”他说。",
        "“是啊。”她点头。",
        "“吃了吗？”",
        "“吃了。”",
    )
)


class TestDialogueStateTriState:
    """T-13：`_evaluate_dialogue_changes_state` 的三态判定与判定顺序。"""

    def test_no_dialogue_requirement_and_no_dialogue_is_not_applicable(self):
        """没要求对话 + 正文确实零对话 → `None`（不适用），不是 `True`。

        改造前这一支返回 `True`，等于「本章没被要求写对话」被记成「对话质量合格」。
        分数上白送 140（实测 1162 → 1302），但真正严重的是它会连带激活 4 条软放行
        （gate 的 rich_progression_evidence / semantic_scene_soft_pass /
        dense_scene_soft_pass 与重试侧的 scene_soft_pass），那些软放行能豁免**其它**
        维度的 blocker——凭一个没测过的维度去豁免别的门，才是这个缺陷的实际杀伤面。
        """
        state = PipelineOrchestrator._evaluate_dialogue_changes_state(
            _T13_NO_DIALOGUE, expected_dialogue=False, dialogue_markers=0
        )

        assert state["dialogue_changes_state"] is None
        assert state["dialogue_state_applicable"] is False
        assert state["dialogue_expectation_declared"] is False

    def test_declared_expectation_with_zero_dialogue_is_a_real_failure(self):
        """任务书要求了对话、正文零对话 → `False`，**不许落进 None**。

        这一条钉的是**判定顺序**，不是判定结果。交接文档 D-07 的示例代码把
        `dialogue_markers == 0 → None` 判在最前面，那样这个样本会变成「不适用」，
        而 `dialogue_does_not_change_state` blocker 用的是 `is False`——门会静默失效。
        真实语料里这种样本恰好 0 条，两种顺序跑分完全一样、测不出差别，正因为
        测不出来才必须由这条测试把顺序固定住。
        """
        state = PipelineOrchestrator._evaluate_dialogue_changes_state(
            _T13_NO_DIALOGUE, expected_dialogue=True, dialogue_markers=0
        )

        assert state["dialogue_changes_state"] is False, (
            "判定顺序被改成「先看有没有对话」了，会让这道 blocker 静默失效"
        )
        assert state["dialogue_state_applicable"] is True
        assert state["dialogue_expectation_declared"] is True

    def test_single_overlapping_state_marker_does_not_count_twice(self):
        """T-13：同一处“拒绝”只能算一个状态变化，不能被重叠词表刷成通过。"""
        content = "“你愿意交出钥匙吗？”他拒绝了。"
        dialogue_markers = sum(content.count(mark) for mark in ("“", "”"))

        state = PipelineOrchestrator._evaluate_dialogue_changes_state(
            content, expected_dialogue=True, dialogue_markers=dialogue_markers
        )

        assert state["state_change_marker_count"] == 1
        assert state["dialogue_changes_state"] is False

    def test_duplicate_marker_count_sabotage_is_detected(self, monkeypatch):
        """反向验证：重新把一处状态变化抬成两个时，上述失败判定必须变红。"""
        content = "“你愿意交出钥匙吗？”他拒绝了。"
        dialogue_markers = sum(content.count(mark) for mark in ("“", "”"))

        baseline = PipelineOrchestrator._evaluate_dialogue_changes_state(
            content, expected_dialogue=True, dialogue_markers=dialogue_markers
        )
        assert baseline["dialogue_changes_state"] is False

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_count_dialogue_state_change_markers",
            staticmethod(lambda _text: 2),
        )
        sabotaged = PipelineOrchestrator._evaluate_dialogue_changes_state(
            content, expected_dialogue=True, dialogue_markers=dialogue_markers
        )
        with pytest.raises(AssertionError):
            assert sabotaged["dialogue_changes_state"] is False

    def test_undeclared_but_dialogue_present_still_gets_judged(self):
        """没要求对话但正文有对话 → 仍然判，只是门槛降到 1 个状态变化标记。

        「不适用」的成立条件是两个都满足，缺一不可。正文里写了 152 个引号却全是
        寒暄应答（状态变化标记 0 个），不能因为任务书没提对话就放过。
        """
        markers = sum(_T13_FLAT_DIALOGUE.count(mark) for mark in ("“", "”"))
        state = PipelineOrchestrator._evaluate_dialogue_changes_state(
            _T13_FLAT_DIALOGUE, expected_dialogue=False, dialogue_markers=markers
        )

        assert markers >= 100
        assert state["state_change_marker_count"] == 0
        assert state["dialogue_changes_state"] is False
        assert state["dialogue_state_applicable"] is True

    def test_undeclared_floor_is_looser_than_declared_floor(self):
        """未声明预期时的状态标记门槛是 1，声明时是 2——这个差是刻意的。

        没被要求写对话场的章节，用同样严的判据等于追认一个没提过的要求。
        真实语料（n=28，expected_dialogue=False 的全部样本）状态标记分布
        p05=1 / p50=14 / p95=31 / min=0：门槛取 1 时 27 条判 True，取 2 会多罚 1 条。
        """
        assert PipelineOrchestrator.UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR == 1

        # 「承认」只出现在 _count_dialogue_state_change_markers 的第二张表里，所以
        # 计数恰好是 1。两张表大面积重叠（「让步」「决定」这类词各表一份，一次出现
        # 计 2），想造 sc == 1 的样本必须挑单表词——这是写这类边界用例的隐形前提。
        one_marker = "屋里很安静。\n“钥匙呢？”\n她承认了。"
        markers = sum(one_marker.count(mark) for mark in ("“", "”"))
        undeclared = PipelineOrchestrator._evaluate_dialogue_changes_state(
            one_marker, expected_dialogue=False, dialogue_markers=markers
        )
        declared = PipelineOrchestrator._evaluate_dialogue_changes_state(
            one_marker, expected_dialogue=True, dialogue_markers=markers
        )

        assert undeclared["state_change_marker_count"] == 1
        assert undeclared["dialogue_changes_state"] is True
        assert declared["dialogue_changes_state"] is False

    def test_score_treats_none_as_neither_bonus_nor_penalty(self, monkeypatch):
        """三档分数必须是「True 加 140 / False 扣 140 / None 不动」。

        实测 GOOD_DRAMATIC：True 1302 / None 1162 / False 1022。两个方向的错法
        都在这条测试的射程内——把 None 当真值是白送 140（改造前的形态），
        写成 `if ... else -140` 把 None 当假值是倒扣 140（比原缺陷更远）。
        """
        real = PipelineOrchestrator._evaluate_dialogue_changes_state.__func__

        def pinned(value):
            def fake(cls, text, *, expected_dialogue, dialogue_markers):
                result = dict(
                    real(cls, text, expected_dialogue=expected_dialogue, dialogue_markers=dialogue_markers)
                )
                result["dialogue_changes_state"] = value
                return result

            return classmethod(fake)

        scores = {}
        for value in (True, False, None):
            monkeypatch.setattr(PipelineOrchestrator, "_evaluate_dialogue_changes_state", pinned(value))
            scores[value] = _score_density_sample(GOOD_DRAMATIC)["score"]

        assert scores[True] - scores[None] == 140
        assert scores[None] - scores[False] == 140

    def test_guard_and_snapshot_expose_the_none_without_bool_coercion(self):
        """`None` 必须原样透到 guard 顶层和 quality_metric_snapshot。

        这份白名单是新字段唯一的静默丢弃点，而 `bool()` 是这里最容易复发的写法：
        它把 None 压成 False，前端严格比较 `=== false` 就会把「本章不适用对话」
        显示成「对白未改局势」——凭没测过的维度对用户报红。
        """
        guard = _score_density_sample(_T13_NO_DIALOGUE)
        snapshot = guard["quality_metric_snapshot"]

        assert guard["dialogue_changes_state"] is None
        assert snapshot["dialogue_changes_state"] is None
        assert snapshot["dialogue_state_applicable"] is False
        assert snapshot["dialogue_expectation_declared"] is False
        assert "对白未改变局势" not in snapshot["quality_issue_labels"]
        assert "dialogue_does_not_change_state" not in snapshot["quality_issue_codes"]


class TestDialogueStateTriStateWiringAcrossLayers:
    """T-13 的四层消费点，逐层各一条。

    判定本身正确、消费点写成真假判断，是这类缺陷最常见的复发形态——上一个类
    全绿也测不出来。四层各有自己的错法：
    第 1 层（结构质量门 blocker / 软放行）：None 进 blocker = 凭没测过拦章；
    第 2 层（定向修复清单）：None 进清单 = 给不适用的维度派返修指令；
    第 3 层（首稿重试原因码）：None 进 reasons = 凭没测过触发重试，多烧一次调用；
    第 4 层（AI 复核覆盖）：None 算硬伤 = 凭不适用换掉 AI 选中的稿。
    """

    def test_gate_does_not_block_on_not_applicable_dialogue(self):
        """第 1 层：`None` 不进 blocker，`False` 必须进。

        同一份零对话正文，只改任务书有没有声明对话预期：
        - 没声明（dcs=None）→ gate passed=True，blockers=[]
        - 声明了（dcs=False）→ blockers 含 dialogue_does_not_change_state
        分界完全由 `is False` 与 `is not False` 的区分承担。
        """
        _summaries, undeclared_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=_T13_NO_DIALOGUE,
            violations=[],
            chapter_mission=None,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        _summaries, declared_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=_T13_NO_DIALOGUE,
            violations=[],
            chapter_mission=_T13_DIALOGUE_MISSION,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        undeclared_codes = {item["code"] for item in undeclared_gate["blockers"]}
        declared_codes = {item["code"] for item in declared_gate["blockers"]}

        assert undeclared_gate["passed"] is True
        assert undeclared_codes == set(), f"不适用的对话维度被拦章了：{sorted(undeclared_codes)}"
        assert "dialogue_does_not_change_state" not in declared_codes
        declared_warnings = {item["code"] for item in declared_gate["warnings"]}
        assert "dialogue_does_not_change_state" in declared_warnings
        assert declared_gate["warnings"]
        assert all(item.get("patch_suggestion") for item in declared_gate["warnings"])

    def test_repair_list_skips_not_applicable_dialogue(self):
        """第 2 层：定向修复清单不给「不适用」派返修指令。

        `_build_structural_reader_polish_issues` 产出的 dimension 集合：
        dcs=None 时不含 dialogue，dcs=False 时含。给一个本章根本没有对话场的
        章节发「把对白改成两轮攻防」，是纯粹的无效返工，还要多烧一次 LLM 调用。
        """
        undeclared_issues = PipelineOrchestrator._build_structural_reader_polish_issues(
            _score_with_mission(_T13_NO_DIALOGUE, None)
        )
        declared_issues = PipelineOrchestrator._build_structural_reader_polish_issues(
            _score_with_mission(_T13_NO_DIALOGUE, _T13_DIALOGUE_MISSION)
        )

        assert "dialogue" not in {item["dimension"] for item in undeclared_issues}
        assert "dialogue" in {item["dimension"] for item in declared_issues}

    def test_first_draft_retry_reason_codes_ignore_not_applicable(self):
        """第 3 层：重试原因码与 gate blocker 同判据。

        两侧判据不一致的表现是「gate 放行了但重试还在要求改对话」，用户看到的是
        无缘无故多出来的一轮重写。所以这里断言的是**与第 1 层完全对应**的分界。
        """
        _needs, undeclared_guard, undeclared_reasons = PipelineOrchestrator._evaluate_first_draft_retry(
            content=_T13_NO_DIALOGUE,
            violations=[],
            chapter_mission=None,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        _needs, declared_guard, declared_reasons = PipelineOrchestrator._evaluate_first_draft_retry(
            content=_T13_NO_DIALOGUE,
            violations=[],
            chapter_mission=_T13_DIALOGUE_MISSION,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        assert undeclared_guard["dialogue_changes_state"] is None
        assert "dialogue_does_not_change_state" not in undeclared_reasons
        assert declared_guard["dialogue_changes_state"] is False
        assert "dialogue_does_not_change_state" in declared_reasons

    def test_ending_pressure_none_is_not_a_failure_across_quality_paths(self, monkeypatch):
        """T-13：章末压力三态字段的 None 不能被摘要、质量门或重试路径当成 False。"""
        guard = {
            "word_count": 1800,
            "dialogue_marker_count": 8,
            "mission_hit_count": 4,
            "scene_count": 1,
            "scene_fulfillment_rate": 0.9,
            "scene_structure_rate": 0.9,
            "expected_dialogue": False,
            "dialogue_changes_state": None,
            "ending_pressure_passed": None,
            "event_density_passed": True,
            "state_change_interval_passed": True,
            "long_chapter_density_passed": True,
            "static_description_risk": False,
            "repetition_risk": False,
        }

        summary = PipelineOrchestrator._build_quality_issue_summary(story_guard=guard)
        assert "ending_pressure_missing" not in summary["codes"]

        gate = PipelineOrchestrator._build_structural_quality_gate(
            {"story_progression_guard": guard}
        )
        assert "ending_pressure_missing" not in {item["code"] for item in gate["blockers"]}

        repair_issues = PipelineOrchestrator._build_structural_reader_polish_issues(guard)
        assert "suspense" not in {item["dimension"] for item in repair_issues}

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_score_story_quality_candidate",
            classmethod(lambda cls, **_kwargs: guard),
        )
        needs_retry, _guard, reasons = PipelineOrchestrator._evaluate_first_draft_retry(
            content="正文",
            violations=[],
            chapter_mission=None,
            target_word_count=1800,
            min_word_count=1600,
        )
        assert needs_retry is False
        assert "ending_pressure_missing" not in reasons

    def test_ai_review_override_requires_explicit_ending_failure(self):
        """T-13：AI 选稿只能把明确 False 当章末缺陷，不能把 None 当缺陷。"""
        base = {
            "word_count": 2000,
            "dialogue_marker_count": 8,
            "mission_hit_count": 5,
            "scene_count": 0,
            "expected_dialogue": False,
            "guardrail_passed": True,
            "static_description_risk": False,
            "scene_fulfillment_rate": 1.0,
            "score": 900,
        }

        def override_for(ai_ending):
            ai_candidate = dict(base, index=0, ending_pressure_passed=ai_ending)
            fallback_candidate = dict(base, index=1, ending_pressure_passed=True)
            override, _detail = PipelineOrchestrator._should_override_ai_review_choice(
                ai_index=0,
                fallback_index=1,
                fallback_summary={"candidates": [ai_candidate, fallback_candidate]},
            )
            return override

        assert override_for(None) is False
        assert override_for(False) is True
        assert override_for(True) is False

    def test_ai_review_override_does_not_treat_none_as_a_defect(self):
        """第 4 层：`None` 不算「AI 稿有硬伤」，`False` 算。

        其余 or 支路全部置成无风险、两稿同分（分差 0 < 180），把断言隔离到
        dialogue_changes_state 这一支上。实测 None → override=False，
        False → override=True。改造前用真假判断，None 会走进 False 的分支，
        于是凭「本章不适用对话」把 AI 复核选中的稿换成兜底稿。
        """
        base = {
            "word_count": 2000,
            "dialogue_marker_count": 8,
            "mission_hit_count": 5,
            "scene_count": 0,
            "expected_dialogue": True,
            "ending_pressure_passed": True,
            "guardrail_passed": True,
            "static_description_risk": False,
            "scene_fulfillment_rate": 1.0,
            "score": 900,
        }

        def override_for(ai_state):
            ai_candidate = dict(base, index=0, dialogue_changes_state=ai_state)
            fallback_candidate = dict(base, index=1, dialogue_changes_state=True)
            override, _detail = PipelineOrchestrator._should_override_ai_review_choice(
                ai_index=0,
                fallback_index=1,
                fallback_summary={"candidates": [ai_candidate, fallback_candidate]},
            )
            return override

        assert override_for(None) is False, "凭「不适用」就换掉 AI 选稿"
        assert override_for(False) is True
        assert override_for(True) is False


# 120 字的短样本：远低于 EVENT_DENSITY_MIN_SAMPLE_CHARS = 800。
# 用整段复制没关系——这里要测的是「短到不评估」，正文形态本身不参与判定。
_T14_SHORT_SAMPLE = "他推开门，屋里空无一人。桌上放着一把钥匙，他捡起来决定去追。" * 4


class TestEventDensityNotEvaluated:
    """T-14：短样本必须报「未评估」，不能报「达标」。"""

    def test_short_sample_reports_not_evaluated_instead_of_passed(self):
        """三个 passed 全 None，并显式说明「为什么没测」。

        改造前这一支返回 `passed=True` + `progression_unit_rate=1.0` +
        `event_density_per_1000=0.0`：推进单元 0 个、推进率 100%、密度 0——
        三个数互相矛盾，而结论是「达标」。历史库里有 2 条快照长这个样子。
        """
        density = PipelineOrchestrator._evaluate_event_density(
            _T14_SHORT_SAMPLE, word_count=len(_T14_SHORT_SAMPLE)
        )

        assert len(_T14_SHORT_SAMPLE) < PipelineOrchestrator.EVENT_DENSITY_MIN_SAMPLE_CHARS
        assert density["event_density_evaluated"] is False
        assert density["event_density_skip_reason"] == "sample_too_short"
        assert density["event_density_min_sample_chars"] == 800
        for key in ("event_density_passed", "state_change_interval_passed", "long_chapter_density_passed"):
            assert density[key] is None, f"{key} 又变成两态了"

    def test_rates_are_none_but_counts_stay_real_zero(self):
        """比率是 `None`（没有分母），计数是真实的 `0`（确实一个都没数出来）。

        这个区分是这次修复的核心：把没测过的比率写成 0.0 或 1.0 都是编数据，
        而计数写成 None 又会让前端 `count || 0` 之类的写法一起坏掉。
        """
        density = PipelineOrchestrator._evaluate_event_density(
            _T14_SHORT_SAMPLE, word_count=len(_T14_SHORT_SAMPLE)
        )

        for key in ("progression_unit_rate", "event_density_per_1000",
                    "state_change_window_pass_rate", "max_plain_unit_run_ratio"):
            assert density[key] is None, f"{key} 被兜底成了数值，等于编造未测数据"
        for key in ("progression_unit_count", "story_unit_count", "max_plain_unit_run"):
            assert density[key] == 0

    def test_evaluation_floor_boundary_is_exact(self):
        """799 字不评估、800 字评估——边界是闭区间下限，不是「约 800」。

        **不要下调这个下限**：800 字以下切不出足够 story_unit，分位统计没有意义，
        密度会被单句噪声主导。真实语料（n=138）里 <800 字只有 2 条（0.014），
        p03 已经是 950，下调换不到覆盖率。
        """
        long_enough = _T14_SHORT_SAMPLE * 30

        assert PipelineOrchestrator._evaluate_event_density(
            long_enough, word_count=799
        )["event_density_evaluated"] is False
        assert PipelineOrchestrator._evaluate_event_density(
            long_enough, word_count=800
        )["event_density_evaluated"] is True

    def test_normal_path_marks_itself_as_evaluated(self):
        """正常路径要显式标 `event_density_evaluated=True`。

        消费方判断「有没有测过」只看这个字段，不靠 `passed is None` 反推——
        反推会在将来新增其它 skip 原因时静默失配。
        """
        density = PipelineOrchestrator._evaluate_event_density(
            GOOD_DRAMATIC, word_count=len(GOOD_DRAMATIC)
        )

        assert density["event_density_evaluated"] is True
        assert density.get("event_density_skip_reason") is None
        assert density["event_density_passed"] is True

    def test_long_chapter_density_is_not_applicable_below_long_chapter_floor(self):
        """T-14：长章密度只适用于 7000+ 字，短/中章必须保留 None。"""
        density = PipelineOrchestrator._evaluate_event_density(
            GOOD_DRAMATIC, word_count=3200
        )

        assert density["event_density_evaluated"] is True
        assert density["event_density_passed"] is True
        assert density["state_change_interval_passed"] is True
        assert density["long_chapter_density_passed"] is None

    def test_long_chapter_density_is_evaluated_at_exact_floor(self):
        density = PipelineOrchestrator._evaluate_event_density(
            GOOD_DRAMATIC, word_count=7000
        )

        assert density["event_density_evaluated"] is True
        assert density["long_chapter_density_passed"] in (True, False)

    def test_score_gives_none_neither_bonus_nor_penalty(self, monkeypatch):
        """三个密度判定同时钉值时：True 1302 / None 1072 / False 582。

        None 与 False 相差 490——那 490 正是改造前「凭章节短到测不了就判它
        密度不合格」的代价（80+130+180 三项判罚，另加 True 侧 230 的加分差）。
        **必须显式三分支，不能写 `if ... else -负分`。**
        """
        real = PipelineOrchestrator._evaluate_event_density.__func__

        def pinned(value):
            def fake(cls, text, *, word_count):
                result = dict(real(cls, text, word_count=word_count))
                for key in ("event_density_passed", "state_change_interval_passed",
                            "long_chapter_density_passed"):
                    result[key] = value
                result["event_density_evaluated"] = value is not None
                return result

            return classmethod(fake)

        scores = {}
        for value in (True, False, None):
            monkeypatch.setattr(PipelineOrchestrator, "_evaluate_event_density", pinned(value))
            scores[value] = _score_density_sample(GOOD_DRAMATIC)["score"]

        assert scores[True] - scores[None] == 230
        assert scores[None] - scores[False] == 490

    def test_snapshot_carries_the_none_and_the_skip_reason(self):
        """快照白名单必须原样带 `None` 和 skip 原因，不许 `bool()` / `, 0` 兜底。

        `bool(None)` → False（前端 `=== false` 报「密度不足」）与
        `get(..., 0)` → 0.0（前端画出一根 0 的进度条）是同一个错误的两半，
        合起来就是历史库里那 2 条矛盾快照的成因。这份白名单是新字段唯一的
        静默丢弃点，所以两个解释字段也必须在。
        """
        guard = _score_density_sample(_T14_SHORT_SAMPLE)
        snapshot = guard["quality_metric_snapshot"]

        assert snapshot["event_density_evaluated"] is False
        assert snapshot["event_density_skip_reason"] == "sample_too_short"
        for key in ("event_density_passed", "state_change_interval_passed",
                    "long_chapter_density_passed"):
            assert snapshot[key] is None, f"snapshot[{key!r}] 被压成两态了"
            assert guard[key] is None, f"guard[{key!r}] 被压成两态了"
        for key in ("progression_unit_rate", "event_density_per_1000",
                    "state_change_window_pass_rate", "max_plain_unit_run_ratio"):
            assert snapshot[key] is None, f"snapshot[{key!r}] 被兜底成了数值"

    def test_not_evaluated_density_produces_no_quality_issue_codes(self):
        """未评估的维度不进 quality_issue_codes / labels。

        这是用户实际看到的那一层：短章在评审界面上不该出现「事件密度不足」
        「状态变化间隔过长」「长章事件密度不足」这三条红字。
        """
        snapshot = _score_density_sample(_T14_SHORT_SAMPLE)["quality_metric_snapshot"]

        for code in ("event_density_weak", "state_change_interval_weak",
                     "long_chapter_event_density_weak"):
            assert code not in snapshot["quality_issue_codes"]
        for label in ("事件密度不足", "状态变化间隔过长", "长章事件密度不足"):
            assert label not in snapshot["quality_issue_labels"]


class TestEventDensityNotEvaluatedWiringAcrossLayers:
    """T-14 的消费点。与 T-13 的四层不同，密度的软放行有一条**区间不相交**的
    安全论证需要被钉住，否则将来有人下调 blocker 门槛就会静默放过样本。"""

    def test_density_soft_passes_use_is_not_false_safely(self):
        """密度软放行用 `is not False`，靠「区间不相交」保证安全。

        `None` 只在 word_count < 800 时产生，而三条密度 blocker 的字数门槛分别是
        1800 / 2500 / 7000，两个区间不相交——所以「未评估也算不反对」在当前配置下
        不会放过任何该拦的样本。这条测试把这个前提变成断言：**谁把 blocker 门槛
        下调到 800 以下，这里就会红**，提醒他先把软放行改成 `is True`。
        """
        import inspect

        source = inspect.getsource(PipelineOrchestrator._build_structural_quality_gate)
        assert PipelineOrchestrator.EVENT_DENSITY_MIN_SAMPLE_CHARS == 800
        for threshold in ("story_word_count >= 1800", "story_word_count >= 2500",
                          "story_word_count >= 7000"):
            assert threshold in source, (
                f"密度 blocker 的字数门槛 {threshold!r} 变了。"
                "如果新门槛低于 800，`is not False` 的软放行就不再安全，必须改成 `is True`"
            )

    def test_short_chapter_is_not_blocked_for_density(self):
        """短章走完整条质量门也不该因为密度被拦。

        端到端的确认：`_evaluate_structural_quality_gate_for_content` 对
        120 字样本给出的 blockers 里没有任何密度类 code。字数不足会不会拦是
        另一个维度的事，这里只断言密度三条不出现。
        """
        _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=_T14_SHORT_SAMPLE,
            violations=[],
            chapter_mission=None,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        codes = {item["code"] for item in gate["blockers"]}
        for code in ("event_density_weak", "state_change_interval_weak",
                     "long_chapter_event_density_weak"):
            assert code not in codes, f"短章被密度门拦了：{code}"

    def test_repair_list_skips_not_evaluated_density(self):
        """定向修复清单不给未评估的密度派 pacing 返修。

        `_build_structural_reader_polish_issues` 的 pacing 分支判据是
        `event_density_passed is False or state_change_interval_passed is False`；
        写成真假判断时，短章会拿到一条「把空转段改成行动、阻碍、反制」的指令——
        而那一章根本没被测过密度。
        """
        short_issues = PipelineOrchestrator._build_structural_reader_polish_issues(
            _score_density_sample(_T14_SHORT_SAMPLE)
        )
        flat_issues = PipelineOrchestrator._build_structural_reader_polish_issues(
            _score_density_sample(BAD_FLAT_CHATTER)
        )

        assert "pacing" not in {item["dimension"] for item in short_issues}
        assert "pacing" in {item["dimension"] for item in flat_issues}, (
            "真正的密度不达标必须仍然派返修——否则这条测试只证明了门被关掉了"
        )

    def test_repair_list_ignores_stale_density_failures_when_not_evaluated(self):
        """历史快照残留 false 时，未评估状态仍不得派发 pacing 修复。"""
        stale_guard = {
            "word_count": 420,
            "event_density_evaluated": False,
            "event_density_passed": False,
            "state_change_interval_passed": False,
            "long_chapter_density_passed": False,
            "dialogue_changes_state": None,
            "ending_pressure_passed": True,
            "static_description_risk": False,
            "scene_count": 0,
        }
        issues = PipelineOrchestrator._build_structural_reader_polish_issues(stale_guard)
        assert "pacing" not in {item["dimension"] for item in issues}

    def test_repair_list_density_guard_requires_evaluation_state(self):
        import inspect
        source = inspect.getsource(PipelineOrchestrator._build_structural_reader_polish_issues)
        guard = 'guard.get("event_density_evaluated") is not False'
        assert guard in source
        sabotaged = source.replace(guard, 'True', 1)
        with pytest.raises(AssertionError):
            assert guard in sabotaged

    def test_first_draft_retry_does_not_fire_on_not_evaluated_density(self):
        """重试原因码不因「未评估」触发。

        密度类 reason 会驱动一次定向重写，凭没测过的维度触发就是白烧一次调用。
        短章的 reasons 里允许有字数类原因（120 字确实远低于目标），断言只针对
        三条密度 code。
        """
        _needs, guard, reasons = PipelineOrchestrator._evaluate_first_draft_retry(
            content=_T14_SHORT_SAMPLE,
            violations=[],
            chapter_mission=None,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )

        assert guard["event_density_passed"] is None
        for code in ("event_density_weak", "state_change_interval_weak",
                     "long_chapter_event_density_weak"):
            assert code not in reasons
        assert "word_count_far_below_target" in reasons, (
            "字数维度必须照常报——否则这条测试可能是因为整个 guard 空了才绿的"
        )

def test_explicit_candidate_count_contract_rejects_partial_provider_salvage_before_review():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    assert "REQUESTED_CANDIDATE_COUNT_UNMET" in source
    assert "len(versions) < config.version_count" in source
    assert "strict_requested_count" in source
