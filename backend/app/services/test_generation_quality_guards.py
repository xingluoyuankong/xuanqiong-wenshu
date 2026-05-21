import pytest

from app.api.routers.optimizer import _continuity_guard_failure as optimizer_continuity_guard_failure
from app.services.ai_review_service import AIReviewService, ReviewResult
from app.services.consistency_service import ConsistencyService
from app.services.continuity_guard_utils import continuity_terms_guard_failure
from app.services.enrichment_service import ENRICH_CHAPTER_PROMPT, ENRICH_DIALOGUE_PROMPT, ENRICH_SCENE_PROMPT, EnrichmentService
from app.services.longform_context_service import CastPlan, ForeshadowingChapterTask, LongformContextPackage
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.self_critique_service import SelfCritiqueService
from app.services.ultimate_writing_flow import _resolve_direct_generation_contract


class TestGenerationQualityGuards:
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

    def test_ending_pressure_recognizes_specific_chinese_cliffhanger_markers(self):
        content = ("沈砚把账页重新压平，逼问账册真相，旧案的线索被一点点推到桌面上。" * 80)
        content += "顾栖川看着他，只说了一句：有些账，见了地，才真会死人。"

        guard = PipelineOrchestrator._score_story_quality_candidate(
            content=content,
            violations=[],
            chapter_mission={
                "continuity_anchor": {"deliver_to_next": ["旧南渠"]},
                "scene_list": [{"goal": "逼问账册真相", "conflict": "地方试图遮掩", "turn": "转去旧南渠"}],
            },
        )

        assert guard["ending_pressure_passed"] is True
        assert any(hit in {"死人", "见了地", "真会死"} for hit in guard["ending_pressure"]["ending_pressure_hits"])

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
        )
        repaired_summaries, repaired_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
            review_summaries=weak_summaries,
            content=repaired_content,
            violations=[],
            chapter_mission=chapter_mission,
        )

        assert weak_gate["passed"] is False
        weak_blocker_codes = {item["code"] for item in weak_gate["blockers"]}
        assert "static_description_risk" in weak_blocker_codes
        assert repaired_gate["passed"] is True
        assert repaired_summaries["story_progression_guard"]["mission_hit_count"] >= 2
        assert repaired_summaries["story_progression_guard_pre_enrichment"]["static_description_risk"] is True

    @pytest.mark.anyio
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

    @pytest.mark.anyio
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
        assert guard["event_density_passed"] is True

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
        content = (
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
        ) * 5
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
