import pytest

from app.services.ai_review_service import AIReviewService, ReviewResult
from app.services.enrichment_service import ENRICH_CHAPTER_PROMPT, ENRICH_DIALOGUE_PROMPT, ENRICH_SCENE_PROMPT
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.self_critique_service import SelfCritiqueService


class TestGenerationQualityGuards:
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


def test_self_critique_allows_stagewide_for_critical_or_residue():
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
