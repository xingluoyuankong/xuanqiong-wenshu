import json
from types import SimpleNamespace

import pytest

from app.services import llm_service as llm_service_module
from app.services.ai_review_service import AIReviewService
from app.services.chapter_review_service import ChapterReviewService
from app.services.consistency_service import ConsistencyService, ViolationSeverity
from app.services.import_service import ImportService
from app.services.knowledge_retrieval_service import KnowledgeRetrievalService, RetrievedKnowledge
from app.services.llm_service import LLMService
from app.services.memory_layer_service import MemoryLayerService
from app.services.preview_generation_service import PreviewGenerationService
from app.services.reader_simulator_service import ReaderSimulatorService, ReaderType
from app.services.self_critique_service import CritiqueDimension, SelfCritiqueService
from app.services.style_rag_service import StyleFeature, StyleRAGService, StyleSource


@pytest.fixture
def anyio_backend():
    return "asyncio"


class ScopeAwareLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.scope_ids = []

    def _pop_response(self):
        scope = llm_service_module._DAILY_LIMIT_SCOPE_STATE.get()
        self.scope_ids.append(id(scope) if scope is not None else None)
        if not self.responses:
            raise AssertionError("ScopeAwareLLM response queue is empty")
        return self.responses.pop(0)

    async def get_llm_response(self, **kwargs):
        return self._pop_response()

    async def generate(self, **kwargs):
        return self._pop_response()


class PromptStub:
    async def get_prompt(self, name):
        return f"prompt:{name}"


def test_daily_limit_scope_reuses_parent_scope_when_nested():
    assert llm_service_module._DAILY_LIMIT_SCOPE_STATE.get() is None

    with LLMService.daily_limit_scope("outer") as outer_scope:
        outer_scope.add(1)
        with LLMService.daily_limit_scope("inner") as inner_scope:
            assert inner_scope is outer_scope
            inner_scope.add(2)
        assert outer_scope == {1, 2}

    assert llm_service_module._DAILY_LIMIT_SCOPE_STATE.get() is None


@pytest.mark.anyio
async def test_preview_generation_scope_reuses_outer_logical_run():
    expanded_chapter = "\n\n".join(
        [
            "complete chapter draft " + "action dialogue consequence " * 90,
            "character makes a choice " + "conflict escalates " * 80,
            "ending pressure carries forward " + "visible cost " * 80,
        ]
    )
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "preview_text": "预览正文",
                    "key_plot_points": [{"order": 1, "description": "冲突开启", "purpose": "建立压力", "emotion_target": "紧张"}],
                    "opening": {"time": "夜", "location": "地库", "character_states": ["警觉"]},
                    "ending_hook": {"type": "悬念", "description": "门外有人"},
                    "expected_emotions": ["紧张"],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "overall_score": 88,
                    "scores": {
                        "outline_compliance": 90,
                        "plot_arrangement": 88,
                        "emotion_rhythm": 86,
                        "hook_effectiveness": 89,
                    },
                    "issues": [],
                    "approved": True,
                    "revision_needed": False,
                    "revision_suggestions": [],
                },
                ensure_ascii=False,
            ),
            expanded_chapter,
        ]
    )
    service = PreviewGenerationService(db=None, llm_service=llm, prompt_service=object())

    with LLMService.daily_limit_scope("outer-preview") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.generate_with_preview(
            project_id="proj-1",
            chapter_number=3,
            outline={"title": "第3章", "summary": "摘要"},
            blueprint_context="蓝图",
            emotion_context="情绪",
            memory_context="记忆",
            target_word_count=1200,
            user_id=7,
        )

    assert result["status"] == "success"
    assert result["full_chapter"] == expanded_chapter.strip()
    assert len(llm.scope_ids) == 3
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


def test_preview_expansion_guard_rejects_short_or_fragmented_full_chapter():
    assert (
        PreviewGenerationService._expanded_chapter_failure_reason("too short", 3000)
        == "expanded_chapter_under_target_floor"
    )
    assert (
        PreviewGenerationService._expanded_chapter_failure_reason("single paragraph " * 260, 3000)
        == "expanded_chapter_too_fragmented"
    )
    assert PreviewGenerationService._expanded_chapter_failure_reason(
        "\n\n".join(["scene action consequence " * 80 for _ in range(4)]),
        3000,
    ) == ""


@pytest.mark.anyio
async def test_chapter_review_scope_reuses_outer_logical_run():
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "overall_pacing_score": 82,
                    "emotion_curve": "波动",
                    "high_points": ["第3章"],
                    "low_points": [],
                    "issues": [],
                    "suggestions": ["保持转折密度"],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "character_screentime": {"林七": {"appearance_count": 3, "importance": "主角", "development": "被迫越线"}},
                    "relationship_changes": [],
                    "issues": [],
                    "suggestions": ["加强对手压迫"],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "consistency_score": 84,
                    "timeline_issues": [],
                    "character_issues": [],
                    "setting_issues": [],
                    "plot_holes": [],
                    "suggestions": ["维持物件流转清晰"],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "chapter_adjustments": [{"chapter_number": 4, "original_focus": "追查", "adjusted_focus": "追查+压迫", "additions": ["时限"], "removals": []}],
                    "global_adjustments": ["提前兑现一条关系裂缝"],
                    "foreshadowing_plan": {"to_reveal": [], "to_develop": [], "to_plant": []},
                    "character_focus": {"increase_screentime": ["值班员"], "develop_relationship": ["林七-同事"]},
                },
                ensure_ascii=False,
            ),
        ]
    )
    service = ChapterReviewService(db=None, llm_service=llm, prompt_service=object())

    with LLMService.daily_limit_scope("outer-review") as outer_scope:
        outer_scope_id = id(outer_scope)
        review_result = await service.conduct_periodic_review(
            project_id="proj-9",
            start_chapter=1,
            end_chapter=3,
            chapter_summaries=[
                {"chapter_number": 1, "title": "灰烬里的编号", "summary": "建立异常规则"},
                {"chapter_number": 2, "title": "借卷流转", "summary": "追查卷宗"},
            ],
            character_profiles="林七：谨慎而执拗",
            foreshadowing_status=None,
            user_id=9,
        )
        adjustment_plan = await service.generate_adjustment_plan(
            review_result=review_result,
            upcoming_outlines=[{"chapter_number": 4, "title": "追查升级", "summary": "继续施压"}],
            user_id=9,
        )

    assert review_result["review_range"] == "第 1 - 3 章"
    assert adjustment_plan["global_adjustments"] == ["提前兑现一条关系裂缝"]
    assert len(llm.scope_ids) == 4
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_reader_simulation_scope_reuses_outer_logical_run():
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "thrill_points": [
                        {"type": "揭示", "description": "编号浮现", "intensity": 8, "position": "中段", "quote": "编号显形"}
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "satisfaction": 78,
                    "emotions": ["紧张"],
                    "highlights": ["推进清晰"],
                    "complaints": ["钩子还可更狠"],
                    "would_continue": True,
                    "abandon_risk": 4,
                    "comment": "愿意继续看",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "satisfaction": 72,
                    "emotions": ["压迫"],
                    "highlights": ["关系有火花"],
                    "complaints": ["中段略满"],
                    "would_continue": True,
                    "abandon_risk": 5,
                    "comment": "整体在线",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "hook_strength": 7,
                    "hook_type": "悬念",
                    "hook_description": "警告落地",
                    "improvement_suggestion": "再压短前置分析",
                },
                ensure_ascii=False,
            ),
        ]
    )
    service = ReaderSimulatorService(db=None, llm_service=llm, prompt_service=object())

    with LLMService.daily_limit_scope("outer-reader") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.simulate_reading_experience(
            chapter_content="林七压住残页，看着编号一点点浮出来。",
            chapter_number=1,
            reader_types=[ReaderType.CASUAL, ReaderType.CRITIC],
            previous_summary=None,
            user_id=11,
        )

    assert result["overall_score"] == 75.0
    assert result["hook_strength"]["hook_type"] == "悬念"
    assert len(llm.scope_ids) == 4
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_memory_update_scope_reuses_outer_logical_run(monkeypatch):
    class CommitOnlyDB:
        async def commit(self):
            return None

    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "character_states": [
                        {
                            "character_name": "林七",
                            "location": "地库",
                            "emotion": "紧张",
                            "emotion_intensity": 8,
                            "emotion_reason": "发现编号",
                            "health_status": "healthy",
                            "injuries": [],
                            "inventory_changes": {"gained": [], "lost": []},
                            "relationship_changes": [],
                            "new_knowledge": ["编号存在异常"],
                            "goal_progress": [{"goal": "保住证据", "progress": "已取得部分编号"}],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "events": [
                        {
                            "event_title": "编号浮现",
                            "event_description": "林七通过拓印保住部分编号",
                            "event_type": "major",
                            "story_time": "凌晨",
                            "involved_characters": ["林七"],
                            "location": "地库",
                            "importance": 8,
                            "is_turning_point": True,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "causal_chains": [
                        {
                            "cause_description": "鏋椾竷鎶笅缂栧彿",
                            "cause_chapter": 5,
                            "effect_description": "缂栧彿浼氬湪涓嬩竴绔犲紩鏉ュ鎶楁柟杩借釜",
                            "effect_chapter": None,
                            "cause_type": "action",
                            "effect_type": "plot_pressure",
                            "involved_characters": ["鏋椾竷"],
                            "importance": 8,
                            "status": "pending",
                            "resolution_description": None,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        ]
    )
    service = MemoryLayerService(db=CommitOnlyDB(), llm_service=llm, prompt_service=object())

    async def fake_update_character_state(*args, **kwargs):
        return None

    async def fake_add_timeline_event(*args, **kwargs):
        return None

    async def fake_causal_chain_exists(*args, **kwargs):
        return False

    async def fake_add_causal_chain(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "update_character_state", fake_update_character_state)
    monkeypatch.setattr(service, "add_timeline_event", fake_add_timeline_event)
    monkeypatch.setattr(service, "_causal_chain_exists", fake_causal_chain_exists)
    monkeypatch.setattr(service, "add_causal_chain", fake_add_causal_chain)

    with LLMService.daily_limit_scope("outer-memory") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.update_memory_after_chapter(
            project_id="proj-memory",
            chapter_number=5,
            chapter_content="林七压住残页，在地库抢下那串编号。",
            character_names=["林七"],
            user_id=15,
        )

    assert result["character_states_updated"] == 1
    assert result["timeline_events_added"] == 1
    assert result["causal_chains_added"] == 1
    assert len(llm.scope_ids) == 3
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_self_critique_full_scope_reuses_outer_logical_run():
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "overall_score": 82,
                    "issues": [
                        {
                            "dimension": "logic",
                            "severity": "major",
                            "location": "前半段",
                            "problem": "制度边界没钉实",
                            "suggestion": "补制度代价",
                            "example": "封库后果先压下来",
                        }
                    ],
                    "strengths": ["抓点稳"],
                    "summary": "结构段仍需收紧",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "overall_score": 84,
                    "issues": [],
                    "strengths": ["人物反应成立"],
                    "summary": "人物段整体稳定",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "overall_score": 81,
                    "issues": [],
                    "strengths": ["章末有牵引"],
                    "summary": "表达段可用",
                },
                ensure_ascii=False,
            ),
        ]
    )
    service = SelfCritiqueService(db=None, llm_service=llm, prompt_service=PromptStub())

    with LLMService.daily_limit_scope("outer-self-critique") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.full_critique(
            chapter_content="林七先留证，再决定截留残页。",
            dimensions=[
                CritiqueDimension.LOGIC,
                CritiqueDimension.CHARACTER,
                CritiqueDimension.PACING,
            ],
            context={"outline_summary": "封库前截留证据"},
            user_id=21,
        )

    assert result["major_count"] == 1
    assert len(llm.scope_ids) == 3
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_ai_review_scope_reuses_outer_logical_run():
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "best_version_index": 1,
                    "scores": {
                        "immersion": 86,
                        "pacing": 88,
                        "hook": 90,
                        "character": 84,
                    },
                    "overall_evaluation": "第二版推进更稳。",
                    "critical_flaws": [],
                    "refinement_suggestions": "收一收中段说明。",
                    "final_recommendation": "采用第二版",
                },
                ensure_ascii=False,
            )
        ]
    )
    service = AIReviewService(llm_service=llm, prompt_service=PromptStub())

    with LLMService.daily_limit_scope("outer-ai-review") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.review_versions(
            versions=["版本一正文", "版本二正文"],
            chapter_mission={"chapter_purpose": "压迫感升级"},
            user_id=31,
        )

    assert result is not None
    assert result.best_version_index == 1
    assert len(llm.scope_ids) == 1
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_consistency_scope_reuses_outer_logical_run(monkeypatch):
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "is_consistent": False,
                    "violations": [
                        {
                            "severity": "critical",
                            "category": "plot",
                            "description": "前后记录冲突",
                            "location": "中段终端核验",
                            "suggested_fix": "统一为单一事件链",
                            "confidence": 0.9,
                        }
                    ],
                    "summary": "存在关键冲突",
                },
                ensure_ascii=False,
            ),
            "修复后的完整正文",
        ]
    )
    service = ConsistencyService(db=None, llm_service=llm)

    async def fake_get_check_context(project_id, include_foreshadowing=True):
        return {
            "novel_setting": "封存档案存在异常规则",
            "character_state": "林七：紧张",
            "global_summary": "前文已出现来源缺失",
            "plot_arcs": "附纸去向未明",
        }

    monkeypatch.setattr(service, "_get_check_context", fake_get_check_context)

    with LLMService.daily_limit_scope("outer-consistency") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.check_and_fix(
            project_id="proj-consistency",
            chapter_text="第一段。\n\n第二段。",
            user_id=41,
            auto_fix_threshold=ViolationSeverity.CRITICAL,
            allow_full_chapter_fallback=True,
        )

    assert result["check_result"].is_consistent is False
    assert result["fixed_content"] == "修复后的完整正文"
    assert len(llm.scope_ids) == 2
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_knowledge_retrieval_scopes_reuse_outer_logical_run(monkeypatch):
    llm = ScopeAwareLLM(
        [
            "档案 异常\n附纸 流转",
            json.dumps(
                {
                    "plot_fuel": ["借阅记录前后不一致，足以支撑进一步追查"],
                    "character_info": ["林七只能确认流程被改写，尚不能断定公共记忆被改写"],
                    "world_fragments": ["档案司会优先接管原件"],
                    "narrative_techniques": ["把判断落在可见证据上"],
                    "warnings": ["▲避免过早上升到公共记忆层"],
                },
                ensure_ascii=False,
            ),
            "当前章节摘要: 林七先抓住借阅记录异常，再意识到流程层面的改写比她预想得更近。",
        ]
    )

    class SyncQueryStub:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    class SyncDBStub:
        def __init__(self, memory):
            self.memory = memory

        def query(self, model):
            return SyncQueryStub(self.memory)

    memory = SimpleNamespace(global_summary="前文已有借阅异常，但尚未证实公共记忆层面的改写。")
    service = KnowledgeRetrievalService(db=SyncDBStub(memory), llm_service=llm, vector_store_service=object())
    blueprint = SimpleNamespace(
        chapter_number=6,
        brief_summary="消失的借阅栏",
        chapter_focus="核验借阅记录",
        chapter_function="把怀疑从直觉推进到证据",
        suspense_density="高",
        foreshadowing_ops="兑现档案司压力",
        cognitive_twist_level=2,
    )

    monkeypatch.setattr(service, "_get_chapter_blueprint", lambda project_id, chapter_number: blueprint)

    async def fake_retrieve_from_vector_store(**kwargs):
        return [
            RetrievedKnowledge(
                content="借阅栏在十分钟内从完整编号变成空白。",
                source="chapter",
                relevance_score=0.91,
                chapter_number=5,
            )
        ]

    async def fake_recent_chapter_content(project_id, current_chapter, count):
        return [{"number": 5, "content": "林七先抄下借阅栏，再回头确认时发现同一行已经空了。"}]

    monkeypatch.setattr(service, "_retrieve_from_vector_store", fake_retrieve_from_vector_store)
    monkeypatch.setattr(service, "_get_recent_chapter_content", fake_recent_chapter_content)

    with LLMService.daily_limit_scope("outer-knowledge") as outer_scope:
        outer_scope_id = id(outer_scope)
        filtered = await service.retrieve_and_filter(
            project_id="proj-knowledge",
            chapter_number=6,
            user_id=51,
            pov_character="林七",
            top_k=3,
        )
        summary = await service.generate_chapter_summary(
            project_id="proj-knowledge",
            chapter_number=6,
            user_id=51,
        )

    assert filtered.plot_fuel == ["借阅记录前后不一致，足以支撑进一步追查"]
    assert filtered.stats["retrieved_count"] == 1
    assert summary.startswith("当前章节摘要:")
    assert len(llm.scope_ids) == 3
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_style_rag_scopes_reuse_outer_logical_run(monkeypatch):
    llm = ScopeAwareLLM(
        [
            json.dumps(
                {
                    "vocabulary_preference": {"description": "偏冷静、偏制度词汇"},
                    "sentence_pattern": {"description": "中短句切换，偶尔压长句"},
                    "narrative_voice": {"description": "贴近主角感官的近距离三人称"},
                    "dialogue_style": {"description": "对话克制，带试探"},
                    "description_technique": {"description": "重物件细节与动作反馈"},
                    "rhythm_pacing": {"description": "推进偏紧，段尾常留压迫"},
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "vocabulary_preference": {"description": "制度词和现场感并用"},
                    "sentence_pattern": {"description": "短句起压，关键处拉长"},
                    "narrative_voice": {"description": "贴身观察，少解释"},
                    "dialogue_style": {"description": "问答里藏试探"},
                    "description_technique": {"description": "偏动作证据锚点"},
                    "rhythm_pacing": {"description": "节奏紧，收尾留钩"},
                },
                ensure_ascii=False,
            ),
            "林七把残页压进档案袋，仍旧没松开指节。",
        ]
    )

    class AsyncScalarResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return self

        def all(self):
            return self.items

    class AsyncDBStub:
        def __init__(self, chapters):
            self.chapters = chapters

        async def execute(self, stmt):
            return AsyncScalarResult(self.chapters)

    chapters = [
        SimpleNamespace(
            selected_version=SimpleNamespace(content="林七摸到档案袋边缘时，先听见门外钥匙碰撞。"),
            versions=[],
        )
    ]
    service = StyleRAGService(db=AsyncDBStub(chapters), llm_service=llm)

    async def fake_save_style_feature(project_id, style_feature):
        return None

    monkeypatch.setattr(service, "_save_style_feature", fake_save_style_feature)

    with LLMService.daily_limit_scope("outer-style") as outer_scope:
        outer_scope_id = id(outer_scope)
        extracted = await service.extract_style_from_chapters(
            project_id="proj-style",
            chapter_numbers=[1],
            user_id=61,
        )

        source = StyleSource(
            {
                "id": "source-1",
                "title": "参考文本",
                "content_text": "制度、编号、门锁、借阅栏。" * 40,
                "char_count": len("制度、编号、门锁、借阅栏。" * 40),
            }
        )

        async def fake_list_style_sources(user_id):
            return [source]

        async def fake_list_style_profiles(user_id):
            return []

        async def fake_save_user_profiles(user_id, profiles):
            return None

        async def fake_get_effective_style_for_project(project_id, user_id):
            return extracted if isinstance(extracted, StyleFeature) else StyleFeature(extracted.style_feature)

        monkeypatch.setattr(service, "list_style_sources", fake_list_style_sources)
        monkeypatch.setattr(service, "list_style_profiles", fake_list_style_profiles)
        monkeypatch.setattr(service, "_save_user_profiles", fake_save_user_profiles)
        monkeypatch.setattr(service, "get_effective_style_for_project", fake_get_effective_style_for_project)

        profile = await service.create_profile_from_sources(
            user_id=61,
            source_ids=["source-1"],
            name="外部参考文风",
        )
        generated = await service.generate_with_style(
            project_id="proj-style",
            existing_content="林七收拢残页，没有立刻抬头。",
            direction="继续写她如何在门外脚步逼近时保住证据",
            user_id=61,
            max_tokens=600,
        )

    assert extracted.to_summary_dict()["dialogue"] == "对话克制，带试探"
    assert profile.summary["rhythm"] == "节奏紧，收尾留钩"
    assert generated == "林七把残页压进档案袋，仍旧没松开指节。"
    assert len(llm.scope_ids) == 3
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_import_service_scope_reuses_outer_logical_run(monkeypatch):
    llm = ScopeAwareLLM(
        [
            json.dumps(["林七", "沈舟"], ensure_ascii=False),
            json.dumps(
                {
                    "title": "雾港回声",
                    "one_sentence_summary": "林七在失忆雾港追查会吞掉公共记忆的账册。",
                    "full_synopsis": "黑潮过后，林七沿着残页和借阅记录追查失忆真相。",
                    "world_setting": {
                        "core_rules": "黑潮会抹除公共记忆，旧纸证据可短暂对抗抹除。",
                        "key_locations": [{"name": "旧档案馆地库", "description": "证据暂存处"}],
                        "factions": [{"name": "市政档案司", "description": "控制异常卷宗流转"}],
                    },
                    "characters": [{"name": "林七", "identity": "修复师"}],
                    "relationships": [],
                    "chapter_outline": [{"chapter_number": 1, "title": "盐渍编号", "summary": "残页显字。"}],
                },
                ensure_ascii=False,
            ),
        ]
    )

    class SessionStub:
        async def commit(self):
            return None

    class NovelServiceStub:
        async def create_project(self, user_id, title, initial_prompt):
            return SimpleNamespace(id="proj-import", status="draft")

        async def replace_blueprint(self, project_id, blueprint):
            return None

        async def get_or_create_chapter(self, project_id, chapter_number):
            return SimpleNamespace(id=chapter_number)

        async def replace_chapter_versions(self, chapter, versions, metadata=None):
            return None

        async def select_chapter_version(self, chapter, version_index):
            return None

    service = ImportService(session=SessionStub())
    service.llm_service = llm
    service.prompt_service = PromptStub()
    service.novel_service = NovelServiceStub()

    async def fake_read_file_content(file):
        return "林七在地库修复残页。沈舟在门口观察。"

    monkeypatch.setattr(service, "_read_file_content", fake_read_file_content)
    monkeypatch.setattr(service, "_split_into_chapters", lambda content: [("第一章 雾起", content)])
    monkeypatch.setattr(service, "_extract_potential_characters", lambda content, top_n=150: ["林七", "沈舟"])
    monkeypatch.setattr(
        service,
        "_extract_character_highlights",
        lambda content, potential_characters, context_window=200: "林七压住残页，沈舟在门边观察。",
    )

    file_stub = SimpleNamespace(filename="雾港回声.txt")

    async def fake_rebuild_import_ledgers(project_id, blueprint_data, chapters, filename):
        return {"snapshot_count": len(chapters)}

    monkeypatch.setattr(service, "_rebuild_import_ledgers", fake_rebuild_import_ledgers)

    with LLMService.daily_limit_scope("outer-import") as outer_scope:
        outer_scope_id = id(outer_scope)
        project_id = await service.import_novel_from_file(user_id=71, file=file_stub)

    assert project_id == "proj-import"
    assert len(llm.scope_ids) == 2
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)


@pytest.mark.anyio
async def test_memory_compress_scope_reuses_outer_logical_run():
    llm = ScopeAwareLLM(["压缩后的早期剧情摘要"])

    class CompressExecuteResult:
        def __init__(self, scalars_list=None, scalar=None):
            self.scalars_list = scalars_list
            self.scalar = scalar

        def scalars(self):
            return self

        def all(self):
            return self.scalars_list

        def scalar_one_or_none(self):
            return self.scalar

    class CompressionDBStub:
        def __init__(self, results):
            self.results = list(results)

        async def execute(self, stmt):
            if not self.results:
                raise AssertionError("CompressionDBStub result queue is empty")
            return self.results.pop(0)

        async def commit(self):
            return None

    memory = SimpleNamespace(global_summary="现有章节摘要", version=1)
    long_summary_one = "早期摘要一" * 700
    long_summary_two = "早期摘要二" * 700
    snapshots = [
        SimpleNamespace(global_summary_snapshot="最近摘要"),
        SimpleNamespace(global_summary_snapshot=long_summary_one),
        SimpleNamespace(global_summary_snapshot=long_summary_two),
    ]
    db = CompressionDBStub(
        [
            CompressExecuteResult(scalars_list=snapshots),
            CompressExecuteResult(scalar=memory),
        ]
    )
    service = MemoryLayerService(db=db, llm_service=llm, prompt_service=object())

    with LLMService.daily_limit_scope("outer-memory-compress") as outer_scope:
        outer_scope_id = id(outer_scope)
        result = await service.compress_memory(
            project_id="proj-memory",
            preserve_chapters=1,
            user_id=81,
        )

    assert result["compressed"] is True
    assert result["compressed_count"] == 2
    assert memory.version == 2
    assert "压缩后的早期剧情摘要" in memory.global_summary
    assert len(llm.scope_ids) == 1
    assert all(scope_id == outer_scope_id for scope_id in llm.scope_ids)
