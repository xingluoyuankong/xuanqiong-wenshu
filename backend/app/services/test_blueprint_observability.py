import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routers.novels import (
    _BLUEPRINT_JOB_HEARTBEAT_SECONDS,
    _BLUEPRINT_JOB_STALE_SECONDS,
    _blueprint_has_valid_character_names,
    _build_character_naming_profile,
    _build_chapter_outline_source_context,
    _build_compact_blueprint_context,
    _build_length_contract,
    _build_outline_source_context,
    _build_story_constraint_profile,
    _format_length_contract_instruction,
    _call_llm_with_stage_retries,
    _db_blueprint_job_to_payload,
    _fail_orphaned_blueprint_job,
    _generate_executable_chapter_outline,
    _has_complete_chapter_outline,
    _generate_novel_outline,
    _load_latest_blueprint_job,
    _load_latest_blueprint_job_from_db,
    _normalize_blueprint_error_detail,
    _polish_chapter_outline_quality,
    _recover_finished_blueprint_job_from_project,
    _recover_stale_blueprint_job,
    _is_recoverable_blueprint_schema,
    _repair_blueprint_character_names,
    _remap_outline_ranges_to_length_contract,
    _resolve_blueprint_chapter_outline_count,
    _resolve_novel_outline_min_stage_count,
    _resolve_novel_outline_timeout_seconds,
    _resolve_outline_chunk_timeout_seconds,
    _resolve_world_bible_timeout_seconds,
    _scan_longform_structure_gaps,
    _serialize_blueprint_job,
    _upsert_blueprint_job_record,
    _parse_expected_chapter_range,
    _validate_novel_outline_coherence,
    _validate_novel_outline_depth,
)
from app.db.base import Base
from app.models import BlueprintGenerationJob, NovelProject, User
from app.models.novel import BlueprintCharacter, ChapterOutline, NovelBlueprint
from app.schemas.novel import Blueprint, FinalizeChapterRequest
from app.services import llm_service as llm_service_module
from app.services import consistency_service as consistency_service_module
from app.services import novel_service as novel_service_module
from app.services.consistency_service import ConsistencyService, ConsistencyViolation, ViolationSeverity
from app.services.llm_service import LLMService
from app.services.novel_service import NovelService, _extract_generation_runtime_payload
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.self_critique_service import CritiqueDimension, SelfCritiqueService
from app.api.routers.writer import (
    _append_generation_runtime_event,
    _build_failed_generation_runtime_state,
    _build_finalized_runtime_summary,
    _build_ledger_sync_runtime_summary,
    _build_memory_layer_runtime_summary,
    _run_finalize_pipeline,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyChapter:
    def __init__(self, **values):
        self.__dict__.update(values)


class FakeLLMService:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get_llm_response(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, list):
            if not self.response:
                raise AssertionError("FakeLLMService response queue is empty")
            return self.response.pop(0)
        return self.response


class FakeRecoverService:
    def __init__(self, session):
        self.session = session

    async def get_project_schema(self, project_id: str, user_id: int):
        return type(
            "ProjectSchema",
            (),
            {
                "blueprint": Blueprint(
                    title="恢复后的蓝图",
                    one_sentence_summary="可用内容",
                    chapter_outline=[{"chapter_number": 1, "title": "第1章", "summary": "摘要"}],
                    characters=[{"name": "林七"}],
                )
            },
        )()


class FakeBrokenRecoverService:
    def __init__(self, session):
        self.session = session

    async def get_project_schema(self, project_id: str, user_id: int):
        return type(
            "ProjectSchema",
            (),
            {"blueprint": Blueprint(title="", one_sentence_summary="只剩残片", chapter_outline=[{"chapter_number": 1, "title": "残章", "summary": "残章摘要"}], characters=[{"name": "林七"}])},
        )()


class FakePartialRecoverService:
    def __init__(self, session):
        self.session = session

    async def get_project_schema(self, project_id: str, user_id: int):
        return type(
            "ProjectSchema",
            (),
            {
                "blueprint": Blueprint(
                    title="只有总纲的蓝图",
                    one_sentence_summary="可用内容",
                    novel_outline=[{"stage": 1, "title": "旧馆删号", "summary": "总纲"}],
                    chapter_outline=[],
                    characters=[{"name": "林七"}],
                )
            },
        )()


class RetryThenSuccessLLMService:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def get_llm_response(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise HTTPException(status_code=503, detail={"message": "provider jitter", "retryable": True})
        return self.response


class DummyAsyncSession:
    def __init__(self):
        self.rollback_calls = 0
        self.commit_calls = 0

    async def rollback(self):
        self.rollback_calls += 1

    async def commit(self):
        self.commit_calls += 1


class DummyExecuteSession(DummyAsyncSession):
    def __init__(self, chapter):
        super().__init__()
        self.chapter = chapter

    async def execute(self, *_args, **_kwargs):
        return self

    def scalars(self):
        return self

    def first(self):
        return self.chapter


class DummyPromptService:
    pass


@pytest.mark.anyio
async def test_finalize_chapter_defaults_to_background_ledger_sync(monkeypatch):
    from app.api.routers import writer as writer_router

    class FakeNovelService:
        def __init__(self, session):
            self.session = session

        async def ensure_project_owner(self, project_id, user_id):
            return DummyChapter(id=project_id, user_id=user_id)

    async def fail_if_sync_pipeline_runs(**_kwargs):
        raise AssertionError("finalize route should queue ledger sync by default")

    version = DummyChapter(id=333, chapter_id=77, content="定稿正文" * 40)
    chapter = DummyChapter(
        id=77,
        chapter_number=7,
        versions=[version],
        selected_version_id=None,
        status="waiting_for_confirm",
        word_count=0,
        real_summary=json.dumps({"generation_runtime": {"run_id": "run-finalize", "events": []}}, ensure_ascii=False),
    )
    session = DummyExecuteSession(chapter)
    background_tasks = BackgroundTasks()

    monkeypatch.setattr(writer_router, "NovelService", FakeNovelService)
    monkeypatch.setattr(writer_router, "_run_finalize_pipeline", fail_if_sync_pipeline_runs)

    response = await writer_router.finalize_chapter(
        7,
        FinalizeChapterRequest(project_id="project-1", selected_version_id=333),
        background_tasks,
        session,
        DummyChapter(id=42),
    )

    runtime = json.loads(chapter.real_summary)["generation_runtime"]
    assert response.result["queued"] is True
    assert response.result["async_finalize"] is True
    assert chapter.selected_version_id == 333
    assert chapter.status == "successful"
    assert session.commit_calls == 2
    assert len(background_tasks.tasks) == 1
    assert runtime["progress_stage"] == "finalize"
    assert runtime["events"][-1]["title"] == "定稿后台同步排队"


@pytest.mark.anyio
async def test_finalize_chapter_can_still_run_sync_when_requested(monkeypatch):
    from app.api.routers import writer as writer_router

    class FakeNovelService:
        def __init__(self, session):
            self.session = session

        async def ensure_project_owner(self, project_id, user_id):
            return DummyChapter(id=project_id, user_id=user_id)

    async def fake_pipeline(**kwargs):
        assert kwargs["project_id"] == "project-1"
        assert kwargs["chapter_number"] == 7
        assert kwargs["selected_version"].id == 333
        return {"finalize": {"success": True}, "memory_layer": {"success": True}}

    version = DummyChapter(id=333, chapter_id=77, content="同步定稿正文")
    chapter = DummyChapter(
        id=77,
        chapter_number=7,
        versions=[version],
        selected_version_id=None,
        status="waiting_for_confirm",
        word_count=0,
        real_summary=json.dumps({"generation_runtime": {"run_id": "run-sync", "events": []}}, ensure_ascii=False),
    )
    session = DummyExecuteSession(chapter)
    background_tasks = BackgroundTasks()

    monkeypatch.setattr(writer_router, "NovelService", FakeNovelService)
    monkeypatch.setattr(writer_router, "_run_finalize_pipeline", fake_pipeline)

    response = await writer_router.finalize_chapter(
        7,
        FinalizeChapterRequest(project_id="project-1", selected_version_id=333, async_finalize=False),
        background_tasks,
        session,
        DummyChapter(id=42),
    )

    assert response.result == {"finalize": {"success": True}, "memory_layer": {"success": True}}
    assert len(background_tasks.tasks) == 0
    assert chapter.selected_version_id == 333


@pytest.mark.anyio
async def test_run_finalize_pipeline_uses_explicit_chapter_number_without_touching_expired_chapter(monkeypatch):
    from app.api.routers import writer as writer_router

    calls = {}

    async def fake_finalize(self, project_id, chapter_number, chapter_text, user_id, skip_vector_update=False):
        calls["project_id"] = project_id
        calls["chapter_number"] = chapter_number
        calls["chapter_text"] = chapter_text
        calls["user_id"] = user_id
        calls["skip_vector_update"] = skip_vector_update
        return {"success": True, "chapter_number": chapter_number}

    monkeypatch.setattr(writer_router.FinalizeService, "finalize_chapter", fake_finalize)

    selected_version = type("SelectedVersion", (), {"content": "定稿正文"})()

    result = await _run_finalize_pipeline(
        session=DummyAsyncSession(),
        project_id="project-1",
        chapter_number=7,
        selected_version=selected_version,
        user_id=42,
        skip_vector_update=True,
        refresh_memory_layer=False,
    )

    assert calls == {
        "project_id": "project-1",
        "chapter_number": 7,
        "chapter_text": "定稿正文",
        "user_id": 42,
        "skip_vector_update": True,
    }
    assert result == {"finalize": {"success": True, "chapter_number": 7}}


@pytest.mark.anyio
async def test_run_finalize_pipeline_snapshots_selected_version_before_service_rollback(monkeypatch):
    from app.api.routers import writer as writer_router

    class ExpiringSelectedVersion:
        def __init__(self):
            self.expired = False
            self._content = "定稿正文"
            self._id = 12
            self._chapter_id = 34

        @property
        def content(self):
            if self.expired:
                raise AssertionError("selected_version.content was touched after finalize rollback")
            return self._content

        @property
        def id(self):
            if self.expired:
                raise AssertionError("selected_version.id was touched after finalize rollback")
            return self._id

        @property
        def chapter_id(self):
            if self.expired:
                raise AssertionError("selected_version.chapter_id was touched after finalize rollback")
            return self._chapter_id

    selected_version = ExpiringSelectedVersion()

    async def fake_finalize(self, project_id, chapter_number, chapter_text, user_id, skip_vector_update=False):
        selected_version.expired = True
        return {"success": True, "chapter_number": chapter_number}

    monkeypatch.setattr(writer_router.FinalizeService, "finalize_chapter", fake_finalize)
    chapter = DummyChapter(
        chapter_number=7,
        real_summary=json.dumps({"generation_runtime": {"run_id": "run-1", "events": []}}, ensure_ascii=False),
    )

    result = await _run_finalize_pipeline(
        session=DummyAsyncSession(),
        project_id="project-1",
        chapter_number=7,
        selected_version=selected_version,
        user_id=42,
        skip_vector_update=True,
        refresh_memory_layer=False,
        chapter=chapter,
    )

    assert result == {"finalize": {"success": True, "chapter_number": 7}}
    runtime = json.loads(chapter.real_summary)["generation_runtime"]
    assert runtime["progress_stage"] == "finalize"
    assert runtime["events"][-1]["content_preview"] == "定稿正文"


def test_blueprint_character_name_validator_rejects_placeholder_protagonist():
    assert _blueprint_has_valid_character_names({"characters": [{"name": "主角", "role": "主角"}]}) is False
    assert _blueprint_has_valid_character_names({"characters": [{"name": "林渡", "role": "主角"}]}) is True


def test_append_generation_runtime_event_records_finalize_ledger_preview():
    chapter = DummyChapter(
        chapter_number=3,
        real_summary=json.dumps({"generation_runtime": {"run_id": "run-1", "events": []}}, ensure_ascii=False),
    )

    _append_generation_runtime_event(
        chapter,
        stage="ledger_foreshadowing",
        message="伏笔闭环完成",
        title="伏笔闭环完成",
        summary="回收 1 条，强化 2 条。",
        content_preview="正文片段" * 140,
        metrics={"resolved": 1, "reinforced": 2},
        artifact_refs={"resolution_ids": [10]},
    )

    runtime = json.loads(chapter.real_summary)["generation_runtime"]
    event = runtime["events"][-1]
    assert runtime["progress_stage"] == "ledger_foreshadowing"
    assert event["kind"] == "ledger"
    assert event["content_preview"].endswith("...")
    assert event["metrics"]["resolved"] == 1
    assert event["artifact_refs"]["resolution_ids"] == [10]


def test_memory_layer_runtime_summary_reports_dynamic_characters():
    summary = _build_memory_layer_runtime_summary(
        {
            "character_states_updated": 2,
            "timeline_events_added": 1,
            "causal_chains_added": 1,
            "dynamic_characters_created": 1,
            "dynamic_character_names": ["林渡"],
        }
    )

    assert "角色状态 2 条" in summary
    assert "时间线事件 1 条" in summary
    assert "因果链 1 条" in summary
    assert "动态角色入池：林渡" in summary


def test_ledger_sync_runtime_summary_reports_graph_and_clue_counts():
    summary = _build_ledger_sync_runtime_summary(
        {"created": 2, "updated": 3},
        {"created_nodes": 1, "created_edges": 4, "removed_nodes": 1, "removed_edges": 2},
    )

    assert "线索新增 2 条" in summary
    assert "线索更新 3 条" in summary
    assert "图谱新增角色节点 1 个" in summary
    assert "图谱新增关系边 4 条" in summary
    assert "清理过期节点 1 个" in summary
    assert "清理过期关系 2 条" in summary


def test_finalized_runtime_summary_mentions_degraded_ledgers():
    summary = _build_finalized_runtime_summary(
        {
            "memory_layer": {"success": False},
            "foreshadowing_closure": {"success": True},
            "ledger_sync": {"success": False},
        }
    )

    assert "记忆层" in summary
    assert "线索/图谱同步" in summary
    assert "降级警告" in summary


def test_build_character_naming_profile_includes_style_constraints():
    profile = _build_character_naming_profile(
        {
            "genre": "航海冒险",
            "style": "长篇升级",
            "tone": "宏大",
            "target_audience": "男频",
            "one_sentence_summary": "主角在异海求生并建立新文明。",
            "full_synopsis": "一部长篇海洋文明成长故事。",
            "world_setting": {
                "core_rules": "海潮会周期性改写航路规则。",
                "key_locations": [{"name": "黑潮岛"}],
                "factions": [{"name": "潮汐商盟"}],
            },
        },
        "异海开拓史",
    )

    assert profile["genre"] == "航海冒险"
    assert profile["key_locations"] == ["黑潮岛"]
    assert profile["factions"] == ["潮汐商盟"]
    assert any("题材" in rule for rule in profile["naming_rules"])


def test_self_critique_structure_rewrite_collapses_to_contiguous_span_for_residue_issues():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    chapter = "\n\n".join([
        "林七在旧档案室翻到残页，先记下港北四巷十七号。",
        "他确认黑皮账册只有自己看得见，誊写也会坏死。",
        "他把借阅单压回压板下，决定先去问周师傅。",
        "雨声敲着玻璃，他沿着书架继续检查封底夹层。",
        "旧卷中间又像第一次那样滑出借阅单，仿佛线索重新开始。",
        "他再一次把港北四巷十七号当成新的发现，认知被重置。",
    ])
    issues = [
        {
            "dimension": "continuity",
            "severity": "critical",
            "location": "黑皮账册只有自己看得见",
            "problem": "前文已经确认账册异常性质，后文却重新第一次发现。",
            "suggestion": "合并为单一事件链，删除第一次发现的重复版本。",
        },
        {
            "dimension": "logic",
            "severity": "critical",
            "location": "港北四巷十七号当成新的发现",
            "problem": "同一线索被多次首次发现，形成明显时间线回卷与双版本拼接。",
            "suggestion": "保留一个正式发现节点，删掉重复发现残留。",
        },
    ]

    plan = service._build_local_rewrite_plan(chapter, issues, context=None, strategy_key="structure_guardrail")

    assert plan is not None
    assert plan["rewrite_mode"] == "contiguous_span"
    assert plan["window_indexes"] == [0, 1, 2, 3, 4, 5]
    assert any("重复" in hint or "拼接" in hint for hint in plan["residue_hints"])


def test_self_critique_residue_detection_ignores_suggestion_only_repeat_wording():
    issue = {
        "dimension": "writing",
        "severity": "major",
        "location": "对峙中段",
        "problem": "说明句偏多，动作压迫感不足。",
        "suggestion": "删掉重复铺陈，把威胁更早压到动作里。",
        "example": "门外的脚步声又近了一格。",
    }

    assert SelfCritiqueService._issue_indicates_structure_residue(issue) is False


def test_self_critique_matches_issue_by_example_snippet_before_falling_back_to_generic_dimension_guess():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    chapter = "\n\n".join([
        "林七先把借阅单压回压板，记住港北四巷十七号。",
        "周师傅否认见过那本黑皮账册。",
        "旧卷夹层里又滑出借阅单，像同一线索第二次第一次出现。",
        "他再次把港北四巷十七号当成全新的发现。",
    ])
    paragraphs = chapter.split("\n\n")
    issue = {
        "dimension": "logic",
        "severity": "major",
        "location": "未定位",
        "problem": "同一线索被重复发现，形成双版本拼接。",
        "suggestion": "保留一个正式发现节点。",
        "example": "旧卷夹层里又滑出借阅单，像同一线索第二次第一次出现。",
    }

    indexes = service._match_issue_to_paragraph_indexes(paragraphs, issue)

    assert indexes == [2]


def test_consistency_local_fix_window_collapses_for_duplicate_discovery_violations():
    service = ConsistencyService(db=None, llm_service=FakeLLMService(""))
    chapter = "\n\n".join([
        "林七先从账册封底摸出借阅单，压在压板下。",
        "他记住港北四巷十七号，准备查旧索引。",
        "周师傅否认见过那本账册。",
        "林七翻回旧卷，怀疑自己记错。",
        "旧卷夹层里又滑出借阅单，像是同一线索第二次第一次出现。",
        "他再次把港北四巷十七号当成全新的发现。",
    ])
    paragraphs = service._split_paragraphs(chapter)
    violations = [
        ConsistencyViolation(
            severity=ViolationSeverity.MAJOR,
            category="plot",
            description="借阅单被重复发现且来源不一致，形成双版本拼接。",
            location="旧卷夹层里又滑出借阅单",
            suggested_fix="只保留一个正式来源并删除重复发现残留。",
        ),
        ConsistencyViolation(
            severity=ViolationSeverity.MAJOR,
            category="plot",
            description="港北四巷十七号被多次呈现为第一次核对，造成时间线回卷。",
            location="再次把港北四巷十七号当成全新的发现",
            suggested_fix="保留一次正式核对，避免认知重置。",
        ),
    ]

    indexes = service._locate_violation_indexes(paragraphs, violations)
    window_indexes, rewrite_mode = service._resolve_local_fix_window(indexes, violations, len(paragraphs))

    assert indexes == [4, 5]
    assert rewrite_mode == "contiguous_span"
    assert window_indexes == [4, 5]
    assert service._build_residue_hints(violations)



def test_consistency_locate_violation_indexes_accumulates_multiple_distinct_violations():
    service = ConsistencyService(db=None, llm_service=FakeLLMService(""))
    chapter = "\n\n".join([
        "林七在第一排铁柜里翻到一张被烧卷边的借阅卡。",
        "他把借阅卡压回册页下，记住背面的旧编号。",
        "周师傅否认看过这张卡。",
        "地库门外突然响起敲门声，顾棠提前出现在登记本里。",
        "林七意识到第二条线索也被人动过手脚。",
    ])
    paragraphs = service._split_paragraphs(chapter)
    violations = [
        ConsistencyViolation(
            severity=ViolationSeverity.MAJOR,
            category="plot",
            description="借阅卡来源不稳定，前后记录对不上。",
            location="被烧卷边的借阅卡",
            suggested_fix="统一借阅卡首次出现的位置。",
        ),
        ConsistencyViolation(
            severity=ViolationSeverity.MAJOR,
            category="plot",
            description="敲门人与登记本提前写名之间缺少稳定承接。",
            location="顾棠提前出现在登记本里",
            suggested_fix="把敲门声与登记本异常合并到同一条事件链。",
        ),
    ]

    indexes = service._locate_violation_indexes(paragraphs, violations)

    assert indexes == [0, 3]


def test_consistency_locate_violation_indexes_supports_paragraph_number_locations():
    service = ConsistencyService(db=None, llm_service=FakeLLMService(""))
    paragraphs = [
        "第一段：林七检查借阅单。",
        "第二段：旧卷年份与新日期并列出现。",
        "第三段：顾棠追问来源。",
        "第四段：周尧改口承认有人动过卷宗。",
    ]
    violations = [
        ConsistencyViolation(
            severity=ViolationSeverity.MAJOR,
            category="plot",
            description="年份冲突需要合并成单一解释链。",
            location="第2段与第4段",
            suggested_fix="补一条旧封新页/二次篡改解释。",
        ),
    ]

    indexes = service._locate_violation_indexes(paragraphs, violations)

    assert indexes == [1, 3]



def test_consistency_build_violation_execution_requirements_covers_pronoun_conflicts():
    service = ConsistencyService(db=None, llm_service=FakeLLMService(""))
    violations = [
        ConsistencyViolation(
            severity=ViolationSeverity.MAJOR,
            category="character",
            description="主角林七的人称/性别指代前后冲突。前半段使用‘她’，后文又持续使用‘他’。",
            location="开头段落",
            suggested_fix="统一林七在本场景中的代词与称谓。",
        ),
    ]

    requirements = service._build_violation_execution_requirements(violations)

    assert any("称谓与代词" in item for item in requirements)



def test_self_critique_cohesion_check_allows_natural_reference_to_next_anchor_without_verbatim_tail_copy():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    plan = {
        "target_paragraphs": [
            "林七把借阅单按回压板下，决定先去找周师傅核对旧编号。",
            "雨声越压越低，地库门外像有人停住了呼吸。",
        ],
        "prev_anchor": "他已经确认账册会吞掉登记记录。",
        "next_anchor": "地库门外传来三下敲门声，沈舟的名字已经写在登记本上。",
        "rewrite_mode": "contiguous_span",
    }
    localized = (
        "林七没有再把借阅单当成新的发现，只把旧编号夹进袖口，准备去找周师傅核对。\n\n"
        "雨声越压越低，他听见门外先是一阵鞋跟摩擦，随后才意识到，那三下敲门声来得比预想更早。"
    )

    assert service._passes_local_cohesion_check(plan, localized) is True



def test_self_critique_salvages_localized_text_that_only_copies_next_anchor_tail():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    plan = {
        "target_paragraphs": [
            "林七压住借阅单，准备把保安叫来核对箱数。",
            "地库里只剩风扇和潮气。",
        ],
        "prev_anchor": "他已经确认旧编号对应码头。",
        "next_anchor": "地库门外传来三下敲门声，保安在门外应了一声。",
        "rewrite_mode": "contiguous_span",
        "residue_hints": ["保安问话场景重复拼接"],
    }
    localized = (
        "林七没有再把同一批转运箱问第二遍，只盯着保安鞋底的盐印，把问题压缩成一句：\n\n"
        "“你刚才到底送了几箱？”\n\n"
        "保安喉结滚了一下，先说六箱，又在他视线里改成五箱。地库门外传来三下敲门声，保安在门外应了一声。"
    )

    assert service._local_cohesion_failure_reason(plan, localized) == "tail_copies_next_anchor"
    salvaged = service._salvage_localized_anchor_overlap(plan, localized)

    assert salvaged is not None
    assert salvaged.endswith("先说六箱，又在他视线里改成五箱。")
    assert service._passes_local_cohesion_check(plan, salvaged) is True



def test_self_critique_normalizes_10_point_scores_to_100_point_scale():
    assert SelfCritiqueService._normalize_overall_score(8) == 80.0
    assert SelfCritiqueService._normalize_overall_score("7.4") == 74.0



def test_self_critique_keeps_100_point_scores_unchanged():
    assert SelfCritiqueService._normalize_overall_score(82) == 82.0
    assert SelfCritiqueService._normalize_overall_score(105) == 100.0



def test_self_critique_deduplicates_cross_dimension_duplicate_major_issues():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "logic",
            "severity": "critical",
            "location": "中段周尧盘问",
            "problem": "同一轮盘问被重复确认，形成双版本推进。",
            "suggestion": "压缩为单一正式问答链。",
            "example": "周尧先否认再改口的桥段出现两次。",
            "_critique_stage": "structural",
        },
        {
            "dimension": "pacing",
            "severity": "major",
            "location": "中段周尧盘问",
            "problem": "盘问回合重复，拖慢节奏。",
            "suggestion": "删去重复确认，只保留一次改口。",
            "example": "相同信息被来回追问。",
            "_critique_stage": "delivery",
        },
        {
            "dimension": "character",
            "severity": "major",
            "location": "章末越线决定",
            "problem": "林七的越线动机还不够锋利。",
            "suggestion": "补一笔更身体化的风险反应。",
            "example": "手心出汗或修复板割手。",
            "_critique_stage": "character",
        },
    ]

    deduped = service._deduplicate_issues(issues)

    assert len(deduped) == 2
    merged = next(item for item in deduped if item.get("location") == "中段周尧盘问")
    assert merged["merged_issue_count"] == 2
    assert set(merged["merged_dimensions"]) == {"logic", "pacing"}
    assert "delivery" in set(merged["merged_stages"])



@pytest.mark.anyio
async def test_self_critique_full_critique_tracks_raw_vs_deduped_issue_counts():
    responses = [
        json.dumps(
            {
                "overall_score": 80,
                "issues": [
                    {
                        "dimension": "logic",
                        "severity": "major",
                        "location": "中段周尧盘问",
                        "problem": "同一轮盘问被重复确认，形成双版本推进。",
                        "suggestion": "压缩为单一正式问答链。",
                        "example": "周尧先否认再改口的桥段出现两次。",
                    }
                ],
                "strengths": ["结构线清楚"],
                "summary": "结构阶段发现一个 major 问题。",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "overall_score": 82,
                "issues": [
                    {
                        "dimension": "character",
                        "severity": "major",
                        "location": "章末越线决定",
                        "problem": "林七的越线动机还不够锋利。",
                        "suggestion": "补一笔更身体化的风险反应。",
                        "example": "手心出汗或修复板割手。",
                    }
                ],
                "strengths": ["人物关系有压迫感"],
                "summary": "人物阶段发现一个 major 问题。",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "overall_score": 79,
                "issues": [
                    {
                        "dimension": "pacing",
                        "severity": "major",
                        "location": "中段周尧盘问",
                        "problem": "盘问回合重复，拖慢节奏。",
                        "suggestion": "删去重复确认，只保留一次改口。",
                        "example": "相同信息被来回追问。",
                    }
                ],
                "strengths": ["章末钩子有效"],
                "summary": "表达阶段命中了与结构阶段重叠的问题。",
            },
            ensure_ascii=False,
        ),
    ]
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(responses), DummyPromptService())

    result = await service.full_critique("林七逼问周尧，盘问回合出现了两次。")

    assert result["raw_issue_count"] == 3
    assert result["deduped_issue_count"] == 2
    assert result["merged_issue_count"] == 1
    merged = next(item for item in result["all_issues"] if item.get("location") == "中段周尧盘问")
    assert merged["merged_issue_count"] == 2
    assert "delivery" in set(merged["merged_stages"])



def test_self_critique_match_issue_to_paragraph_indexes_supports_paragraph_number_locations():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    paragraphs = [
        "第一段：林七翻开修复日志。",
        "第二段：周尧改口，说卷宗昨夜被调走过。",
        "第三段：顾棠盯着他袖口的动作。",
        "第四段：门外传来钥匙碰撞声。",
    ]

    indexes = service._match_issue_to_paragraph_indexes(
        paragraphs,
        {
            "dimension": "continuity",
            "location": "第2段与第4段",
            "problem": "同一推进回合被拆成两个段落重复呈现。",
            "suggestion": "保留一条正式事件链。",
            "example": "无",
        },
    )

    assert indexes == [1, 3]


@pytest.mark.anyio
async def test_self_critique_full_critique_adds_rule_based_duplicate_residue_issue():
    responses = [
        json.dumps({"overall_score": 82, "issues": [], "strengths": ["结构清楚"], "summary": "结构阶段未报问题。"}, ensure_ascii=False),
        json.dumps({"overall_score": 84, "issues": [], "strengths": ["人物稳定"], "summary": "人物阶段未报问题。"}, ensure_ascii=False),
        json.dumps({"overall_score": 83, "issues": [], "strengths": ["节奏正常"], "summary": "表达阶段未报问题。"}, ensure_ascii=False),
    ]
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(responses), DummyPromptService())
    chapter_content = "\n\n".join(
        [
            "林七把借阅单按在台灯下，一行一行核对盐渍编号，确认每一处退墨都对应同一个旧仓号。周尧先说清单从未外借，下一秒又被编号逼得改口，说昨夜有人临时调走过一批卷宗。",
            "顾棠站在门口，没有立刻插话，只盯着周尧改口时下意识摸向袖口的动作。",
            "林七把借阅单按在台灯下，一行一行核对盐渍编号，确认每一处退墨都对应同一个旧仓号。周尧先说清单从未外借，下一秒又被编号逼得改口，说昨夜有人临时调走过一批卷宗。",
        ]
    )

    result = await service.full_critique(chapter_content)

    assert result["raw_issue_count"] == 1
    assert result["deduped_issue_count"] == 1
    assert result["major_count"] == 1
    assert result["needs_revision"] is True
    assert result["priority_fixes"][0]["location"] == "第1段与第3段"
    assert "双版本拼接" in result["priority_fixes"][0]["problem"]
    heuristic_summary = next(item for item in result["stage_summaries"] if item.get("stage") == "heuristic_guard")
    assert heuristic_summary["issue_count"] == 1
    assert heuristic_summary["weighted_score"] is None



def test_quality_gate_prefers_stable_pre_consistency_self_critique_for_same_content():
    gate = PipelineOrchestrator._build_structural_quality_gate(
        {
            "self_critique": {
                "final_score": 77.8,
                "critical_count": 0,
                "major_count": 7,
                "minor_count": 5,
                "content_fingerprint": "same-content",
                "raw_issue_count": 11,
                "deduped_issue_count": 7,
                "merged_issue_count": 4,
            },
            "self_critique_after_consistency": {
                "final_score": 77.3,
                "critical_count": 0,
                "major_count": 10,
                "minor_count": 1,
                "content_fingerprint": "same-content",
                "raw_issue_count": 11,
                "deduped_issue_count": 10,
                "merged_issue_count": 1,
            },
            "consistency": {"violations": []},
        }
    )

    assert gate["passed"] is True
    assert gate["selected_critique_source"] == "self_critique_same_content_more_stable"
    assert gate["self_critique_major_count"] == 7
    assert gate["baseline_self_critique_major_count"] == 7
    assert gate["post_consistency_self_critique_major_count"] == 10



def test_quality_gate_still_blocks_when_eight_unique_majors_remain():
    gate = PipelineOrchestrator._build_structural_quality_gate(
        {
            "self_critique": {
                "final_score": 74.5,
                "critical_count": 0,
                "major_count": 8,
                "minor_count": 1,
                "content_fingerprint": "chapter-a",
                "raw_issue_count": 9,
                "deduped_issue_count": 8,
                "merged_issue_count": 1,
            },
            "consistency": {"violations": []},
        }
    )

    assert gate["passed"] is False
    assert gate["selected_critique_source"] == "self_critique"
    assert any(item["code"] == "too_many_major_issues" for item in gate["blockers"])


@pytest.mark.anyio
async def test_post_consistency_self_critique_reuses_baseline_summary_when_content_unchanged(monkeypatch):
    orchestrator = PipelineOrchestrator(DummyAsyncSession())
    chapter_content = "林七把盐渍编号压进灯下，意识到旧账册已经反向盯住了自己。"
    baseline_summary = {
        "final_score": 78.4,
        "improvement": 6.2,
        "status": "optimized",
        "critical_count": 0,
        "major_count": 5,
        "minor_count": 2,
        "priority_fixes": [{"dimension": "logic", "problem": "线索落点不够硬"}],
        "final_critique": {"weighted_score": 78.4, "critical_count": 0, "major_count": 5, "minor_count": 2},
        "stage_summaries": [{"stage": "structural", "issue_count": 2}],
        "content_fingerprint": orchestrator._content_fingerprint(chapter_content),
        "raw_issue_count": 8,
        "deduped_issue_count": 5,
        "merged_issue_count": 3,
    }

    async def fail_if_recritique(*args, **kwargs):
        raise AssertionError("same-content post-consistency summary should reuse baseline critique")

    monkeypatch.setattr(SelfCritiqueService, "full_critique", fail_if_recritique)

    summary = await orchestrator._run_post_consistency_self_critique_summary(
        chapter_content=chapter_content,
        context={"consistency_issues": []},
        user_id=1,
        baseline_summary=baseline_summary,
    )

    assert summary["status"] == "post_consistency_reused_same_content"
    assert summary["reused_from"] == "self_critique"
    assert summary["final_score"] == 78.4
    assert summary["major_count"] == 5
    assert summary["content_fingerprint"] == baseline_summary["content_fingerprint"]
    assert summary["raw_issue_count"] == 8
    assert summary["deduped_issue_count"] == 5
    assert summary["merged_issue_count"] == 3


@pytest.mark.anyio
async def test_run_self_critique_preserves_rejected_candidate_diagnostics(monkeypatch):
    orchestrator = PipelineOrchestrator(DummyAsyncSession())
    chapter_content = "林七把借阅单压回压板下，决定先去核对终端记录。"
    candidate_content = chapter_content + "\n\n门外人提前报出编号，反而暴露了新的硬伤。"
    initial_snapshot = {
        "weighted_score": 78.0,
        "critical_count": 0,
        "major_count": 6,
        "minor_count": 0,
        "needs_revision": True,
        "priority_fixes": [{"dimension": "logic", "problem": "承接仍有断裂"}],
        "stage_summaries": [{"stage": "structural", "issue_count": 2}],
        "raw_issue_count": 6,
        "deduped_issue_count": 6,
        "merged_issue_count": 6,
    }
    candidate_critique = {
        "weighted_score": 79.8,
        "critical_count": 1,
        "major_count": 6,
        "minor_count": 0,
        "needs_revision": True,
        "priority_fixes": [{"dimension": "suspense", "problem": "新 critical"}],
        "stage_summaries": [{"stage": "delivery", "issue_count": 1}],
        "raw_issue_count": 7,
        "deduped_issue_count": 7,
        "merged_issue_count": 7,
    }

    async def fake_loop(self, **kwargs):
        return {
            "iterations": [{"critique": initial_snapshot}],
            "final_content": candidate_content,
            "final_critique": candidate_critique,
            "status": "optimized",
            "improvement": 1.8,
            "optimization_logs": [
                {
                    "stage": "structural",
                    "strategy_logs": [
                        {
                            "strategy": "structure_guardrail",
                            "attempts": [
                                {
                                    "mode": "stagewide",
                                    "manual_confirmation_required": True,
                                    "patch_suggestions": [
                                        {
                                            "dimension": "logic",
                                            "severity": "major",
                                            "location": "章末",
                                            "problem": "承接仍有断裂",
                                            "suggestion": "补一条可观察因果链",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(SelfCritiqueService, "critique_and_revise_loop", fake_loop)

    final_content, summary = await orchestrator._run_self_critique(
        DummyChapter(id=1),
        generation_run_id=None,
        chapter_content=chapter_content,
        user_id=1,
        context={},
    )

    assert final_content == chapter_content
    assert summary["status"] == "reverted_to_original"
    assert summary["accepted_revision"] is False
    assert summary["acceptance_reason"] == "critical_issues_increased"
    assert summary["final_critique"]["critical_count"] == 0
    assert summary["rejected_candidate_critique"] == candidate_critique
    assert summary["manual_stagewide_confirmation_required"] is True
    assert summary["stagewide_deferred_count"] == 1
    assert summary["manual_patch_suggestions"][0]["stage"] == "structural"
    assert summary["manual_patch_suggestions"][0]["strategy"] == "structure_guardrail"
    assert summary["rejected_candidate_content_fingerprint"] == orchestrator._content_fingerprint(candidate_content)
    assert summary["before_revision_stats"] == {
        "score": 78.0,
        "critical": 0,
        "major": 6,
        "minor": 0,
        "needs_revision": True,
    }
    assert summary["after_revision_stats"] == {
        "score": 79.8,
        "critical": 1,
        "major": 6,
        "minor": 0,
        "needs_revision": True,
    }


def test_self_critique_builds_strategy_specific_execution_requirements():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())

    structural_requirements = service._build_issue_execution_requirements(
        [
            {
                "dimension": "logic",
                "severity": "major",
                "location": "章末门外人精准报出编号",
                "problem": "异常规则边界偏模糊，门外来人的到达因果链也不够扎实。",
                "suggestion": "补一条当前可观察规则，并补出同步或监控痕迹。",
                "example": "编号一挂上去，按规程会同步值班与保全端。",
            }
        ],
        strategy_key="structure_guardrail",
    )
    assert any("可观察规则" in item for item in structural_requirements)
    assert any("同步" in item or "监控" in item for item in structural_requirements)

    structural_focus_requirements = service._build_issue_execution_requirements(
        [
            {
                "dimension": "logic",
                "severity": "major",
                "location": "从系统条目消失到库管改口，再到主角怀疑公共记忆被删改的中段",
                "problem": "“公共记忆被删改”的命题跳得偏快，中间还缺一个够硬的客观证据踏板。",
                "suggestion": "先补同一事实被客观捕获后再发生消失或改口的桥梁，再决定是否上升到公共记忆层。",
                "example": "他先手抄下借阅栏，回头再看时，同一行已经只剩空白。",
            },
            {
                "dimension": "logic",
                "severity": "major",
                "location": "中后段多种异常机制并列出现",
                "problem": "多种异常机制并列出现，世界规则边界还不够清。",
                "suggestion": "收束为一条主异常链。",
                "example": "先锁定制度删改，其他异常只做暗示。",
            },
            {
                "dimension": "logic",
                "severity": "major",
                "location": "口头复述、手背记录与物理书写的规则展示",
                "problem": "规则像临时变动，触得到与手背记录为什么有效还不够清。",
                "suggestion": "补一次对照验证。",
                "example": "同一信息用记录单与手背各试一次。",
            },
            {
                "dimension": "logic",
                "severity": "major",
                "location": "原页编号与登记栏同时退墨的段落",
                "problem": "这一退墨很容易被误读为正常修复损耗或拓印后果，异常是否独立于他的操作发生还不够清。",
                "suggestion": "补一个专业对照判断，排除常规水损。",
                "example": "没碰过的登记栏也在一起消。",
            },
            {
                "dimension": "continuity",
                "severity": "major",
                "location": "原件、残页、同批卷宗与外借清单的关系",
                "problem": "对象边界不清，读者难判断整批都被借走了，还是只调走了同批主卷。",
                "suggestion": "用一句流程说明澄清物件追踪。",
                "example": "修复台上的散页不在外借清单里。",
            },
            {
                "dimension": "logic",
                "severity": "major",
                "location": "离线照片、便签和物证袋的保全流程",
                "problem": "证据保全不够专业，当前仍偏单线备份，真要被抹可能会一锅端。",
                "suggestion": "先测试载体，再分散备份。",
                "example": "名字、编号、物证分三处放。",
            },
            {
                "dimension": "logic",
                "severity": "major",
                "location": "值班员的高度具体预警",
                "problem": "预警跳得过远，像剧透式铺垫。",
                "suggestion": "降级成低确定性警告或补来源。",
                "example": "你要是真去B区，别先报号。",
            },
            {
                "dimension": "logic",
                "severity": "major",
                "location": "同事准备离场的段落",
                "problem": "同事退场略像作者调度，缺少主动恐慌或生理反应。",
                "suggestion": "补一个当场失控点，逼出退场。",
                "example": "我得先确认我脑子还在不在。",
            },
            {
                "dimension": "continuity",
                "severity": "major",
                "location": "章节后段覆拓到章末",
                "problem": "第三场核心兑现没有真正落地，当前更像停在准备做事，钩子偏软。",
                "suggestion": "把关键动作写完并兑现反咬。",
                "example": "灯再亮时，账纸已翻到林七名字那一栏。",
            },
        ],
        strategy_key="structure_guardrail",
        limit=14,
    )
    assert any("公共记忆被删改" in item and "客观证据踏板" in item for item in structural_focus_requirements)
    assert any("主异常链" in item for item in structural_focus_requirements)
    assert any("对照验证" in item for item in structural_focus_requirements)
    assert any("正常修复损耗" in item or "独立于主角操作发生" in item for item in structural_focus_requirements)
    assert any("主卷、散页、外借清单" in item or "哪些件被调走" in item for item in structural_focus_requirements)
    assert any("分散保存" in item or "分散备份" in item for item in structural_focus_requirements)
    assert any("低确定性警告" in item for item in structural_focus_requirements)
    assert any("主动退场" in item or "当场失控" in item for item in structural_focus_requirements)
    assert any("关键动作必须真正做完" in item for item in structural_focus_requirements)

    character_requirements = service._build_issue_execution_requirements(
        [
            {
                "dimension": "relationship",
                "severity": "major",
                "location": "值班记录口与门外取页者对话",
                "problem": "关系张力不足，当前更像功能性对峙。",
                "suggestion": "把对话改成带试探和压迫的博弈。",
                "example": "你这种人会先留压痕，不会先上报。",
            },
            {
                "dimension": "character",
                "severity": "major",
                "location": "决定越线前的转折点",
                "problem": "人物转折和越线临界点不够锋利。",
                "suggestion": "补一个差点服从又被刺回去的动作节点。",
                "example": "热封条在掌心慢慢冷下去。",
            },
            {
                "dimension": "relationship",
                "severity": "major",
                "location": "匿名值班口与回呼处置令对话",
                "problem": "制度压迫成立，但对手过于抽象，匿名声音缺少人际特征。",
                "suggestion": "补固定措辞或权限痕迹，让施压方可被记住。",
                "example": "林修复师，您总是问得比流程多一步。",
            },
            {
                "dimension": "relationship",
                "severity": "major",
                "location": "林七与同事交接的前半段",
                "problem": "熟人关系过薄，异常爆发前几乎看不出工作默契和固定称呼，后续关系断裂不够疼。",
                "suggestion": "补一笔互怼习惯或固定称呼。",
                "example": "你又把外页夹反了，林七。",
            },
            {
                "dimension": "character",
                "severity": "major",
                "location": "决定先藏证据再决定是否上报的那一下",
                "problem": "林七从按流程的人转成先藏证据，仍略偏功能性，职业代价和身体记忆落得不够实。",
                "suggestion": "补一个签过字的修复记录被改成另一版的旧伤回弹。",
                "example": "他忽然想起那次补报后，连自己签过字的记录都换成了另一页。",
            },
            {
                "dimension": "relationship",
                "severity": "major",
                "location": "库管催封袋又频频改口的整段对手戏",
                "problem": "对手更像服务悬念的工具人，自保动机和个人代价都还不够可感知。",
                "suggestion": "补一个具体的担责或被调离风险，让回避像具体避祸。",
                "example": "再碰这页，最后签字的人就会是我。",
            },
            {
                "dimension": "relationship",
                "severity": "major",
                "location": "值班员与送件同事连续回避的段落",
                "problem": "两名对手位功能过于接近，更多像同一张脸的复写，缺少具体人际拉扯；最好一人像制度代言人，另一人像明知却不敢说。",
                "suggestion": "把压迫与回避分层。",
                "example": "一个只守规程，一个先躲监控再改口。",
            },
        ],
        strategy_key="character_dynamics",
        limit=12,
    )
    assert any("功能性对话" in item or "试探" in item for item in character_requirements)
    assert any("上交流程=证据离开视野" in item or "非这么做不可" in item for item in character_requirements)
    assert any("压迫台词" in item for item in character_requirements)
    assert any("差点服从" in item for item in character_requirements)
    assert any("具体职业伤口回弹" in item or "签字记录" in item for item in character_requirements)
    assert any("人际锚点" in item or "固定措辞" in item for item in character_requirements)
    assert any("工作默契" in item or "固定称呼" in item for item in character_requirements)
    assert any("制度代言人" in item or "统一口径" in item for item in character_requirements)
    assert any("自保代价" in item or "具体避祸" in item for item in character_requirements)

    delivery_requirements = service._build_issue_execution_requirements(
        [
            {
                "dimension": "pacing",
                "severity": "major",
                "location": "中段终端核验到实物比对之间的连续检索",
                "problem": "验证步骤偏多、同质信息连续堆叠，像在看主角把正确流程做完。",
                "suggestion": "压缩平行验证，保留 2-3 个最有杀伤力的证据。",
                "example": "他连查工号、遗物封存码和事故关联条目，结果全是同一句——无匹配人员。",
            },
            {
                "dimension": "pacing",
                "severity": "major",
                "location": "中后段停下来解释为什么不能交卷",
                "problem": "内心归纳与回忆说明过多，像在停下来解释为什么这个决定重要。",
                "suggestion": "把重复归纳压成一次最短触发，并立刻推进到动作。",
                "example": "他没再犹豫，把封存袋摆上台面，另一只手去拉抽屉。",
            },
            {
                "dimension": "pacing",
                "severity": "major",
                "location": "值班台查无此人到领器材之间的连续追问",
                "problem": "同型冲突回合数偏多，像在同一堵墙前反复试探，张力进入平台期。",
                "suggestion": "删并一轮重复追问，让每次交锋都只对应一个升级结果。",
                "example": "查无此人后直接切到卷宗外借，再立刻决定藏证。",
            },
            {
                "dimension": "scene",
                "severity": "major",
                "location": "覆拓动作场景前插入耗材与老话说明",
                "problem": "高潮前动作场景被说明性内容挤压。",
                "suggestion": "把器具和设定信息嵌回动作里一闪带出。",
                "example": "旧麻纸一覆上去，账页自己往前窜了半寸。",
            },
            {
                "dimension": "writing",
                "severity": "major",
                "location": "门外人出现前的黑潮求助单回忆",
                "problem": "高压节点插入较长背景回忆，压迫感被说明性回溯打断。",
                "suggestion": "压成最短创伤闪回，别展开补设定。",
                "example": "那张求助单只在他眼前闪了一下。",
            },
            {
                "dimension": "scene",
                "severity": "major",
                "location": "门锁、门把手与门外人对峙的章末",
                "problem": "章末危险更多停留在语言试探，缺少可见物理障碍和即时选择。",
                "suggestion": "补门内外物理局势与倒计时选择。",
                "example": "门栓正在一点点回弹，他只有三秒决定藏证还是开门。",
            },
            {
                "dimension": "suspense",
                "severity": "major",
                "location": "章末借阅签反转之后又追加乱码异动",
                "problem": "章末主钩子被分流，重心从借阅签反咬滑到了系统又怪一下。",
                "suggestion": "章末只保留一个主钩子，次级异动前置或删除。",
                "example": "那是他自己的字。而那一天，在他的记忆里，根本不存在。",
            },
        ],
        strategy_key="delivery_polish",
        limit=12,
    )
    assert any("2-3 个最有杀伤力的证据" in item for item in delivery_requirements)
    assert any("删并或压缩至少一轮追问回合" in item or "查无此人 / 卷宗外借 / 决定藏证" in item for item in delivery_requirements)
    assert any("最短触发" in item for item in delivery_requirements)
    assert any("嵌在动作里" in item for item in delivery_requirements)
    assert any("最短创伤闪回" in item for item in delivery_requirements)
    assert any("可见物理障碍" in item or "倒计时选择" in item for item in delivery_requirements)
    assert any("章末只能保留一个主钩子" in item for item in delivery_requirements)


@pytest.mark.anyio
async def test_stagewide_revision_prompt_keeps_dense_delivery_requirements_visible():
    chapter_content = "\n\n".join([
        "林七先在值班终端核对工号，结果第一条记录就显示查无此人。",
        "他翻出封存袋里的旧票据，又去对照遗物封码和事故时间。",
        "门外人还没出现前，他脑子里已经闪过那张求助单留下的旧阴影。",
        "覆拓台边堆着耗材和老记录，他一边操作一边强迫自己别停下来解释。",
        "门外终于响起敲门声，门锁轻轻回弹，像有人正从外面试探力道。",
        "他刚确认借阅签反咬，走廊尽头又亮起一串乱码提示。",
    ])
    revised_content = chapter_content + "\n\n门栓又回弹了一寸，林七只能在藏证和开门之间立刻做决定。"
    llm = FakeLLMService(revised_content)
    service = SelfCritiqueService(DummyAsyncSession(), llm, DummyPromptService())

    await service._revise_chapter_stagewide(
        chapter_content,
        [
            {
                "dimension": "pacing",
                "severity": "major",
                "location": "中段终端核验到实物比对之间的连续检索",
                "problem": "验证步骤偏多、同质信息连续堆叠，像在看主角把正确流程做完。",
                "suggestion": "压缩平行验证，保留 2-3 个最有杀伤力的证据。",
            },
            {
                "dimension": "pacing",
                "severity": "major",
                "location": "中后段停下来解释为什么不能交卷",
                "problem": "内心归纳与回忆说明过多，像在停下来解释为什么这个决定重要。",
                "suggestion": "把重复归纳压成一次最短触发，并立刻推进到动作。",
            },
            {
                "dimension": "writing",
                "severity": "major",
                "location": "门外人出现前的黑潮求助单回忆",
                "problem": "高压节点插入较长背景回忆，压迫感被说明性回溯打断。",
                "suggestion": "压成最短创伤闪回，别展开补设定。",
            },
            {
                "dimension": "scene",
                "severity": "major",
                "location": "覆拓动作场景前插入耗材与老话说明",
                "problem": "高潮前动作场景被说明性内容挤压。",
                "suggestion": "把器具和设定信息嵌回动作里一闪带出。",
            },
            {
                "dimension": "scene",
                "severity": "major",
                "location": "门锁、门把手与门外人对峙的章末",
                "problem": "章末危险更多停留在语言试探，缺少可见物理障碍和即时选择。",
                "suggestion": "补门内外物理局势与倒计时选择。",
            },
            {
                "dimension": "suspense",
                "severity": "major",
                "location": "章末借阅签反转之后又追加乱码异动",
                "problem": "章末主钩子被分流，重心从借阅签反咬滑到了系统又怪一下。",
                "suggestion": "章末只保留一个主钩子，次级异动前置或删除。",
            },
        ],
        context=None,
        user_id=1,
        strategy_key="delivery_polish",
    )

    prompt = llm.calls[0]["conversation_history"][0]["content"]
    assert "最短创伤闪回" in prompt
    assert "可见物理障碍或倒计时选择" in prompt
    assert "章末只能保留一个主钩子" in prompt



def test_stagewide_revision_guard_reports_precise_failure_reason():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    original = "\n\n".join([
        "第一段铺设调查场。",
        "第二段继续核验。",
        "第三段给出反转。",
        "第四段保留章末压力。",
        "第五段收束到未完成决断。",
        "第六段留下余波。",
    ])
    too_short = "第一段改完。\n\n第二段改完。"

    reason = service._stagewide_revision_guard_failure_reason(
        original,
        too_short,
        residue_cleanup_mode=False,
    )

    assert reason is not None
    assert reason.startswith("too_short:")


def test_stagewide_revision_guard_rejects_dangling_end_punctuation():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    original = "\n\n".join([
        "第一段铺设调查场。",
        "第二段继续核验。",
        "第三段给出反转。",
        "第四段保留章末压力。",
        "第五段收束到未完成决断。",
        "第六段留下余波。",
    ])
    dangling = "\n\n".join([
        "第一段铺设调查场，但换成更稳的写法。",
        "第二段继续核验，并补上新阻碍。",
        "第三段给出反转，让值守态度骤变。",
        "第四段保留章末压力，并让林七准备追出去，",
    ])

    reason = service._stagewide_revision_guard_failure_reason(
        original,
        dangling,
        residue_cleanup_mode=False,
    )

    assert reason == "dangling_ending_punctuation"


def test_self_critique_skips_local_plan_for_broad_character_stage_issue():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    chapter = "\n\n".join([
        "林七先核对终端记录，确认异常页进入地库流程。",
        "值班记录口在电话里先承认后改口，林七意识到异常开始外溢。",
        "他把原件压进防潮夹，门外有人开始试探门禁。",
    ])
    issues = [
        {
            "dimension": "relationship",
            "severity": "major",
            "location": "全章整体，尤其值班记录口通话段与章末门外取页者对话段",
            "problem": "关系张力不足，当前更像功能性对峙。",
            "suggestion": "把对话改成带试探和压迫的博弈。",
            "example": "你这种人会先留压痕，不会先上报。",
        }
    ]

    plan = service._build_local_rewrite_plan(chapter, issues, context=None, strategy_key="character_dynamics")

    assert plan is None


@pytest.mark.anyio
async def test_critique_dimension_batch_focus_prompt_only_verifies_selected_issues():
    llm = FakeLLMService(
        json.dumps(
            {
                "stage": "verify_character_dynamics",
                "dimensions": ["character", "relationship"],
                "overall_score": 84,
                "issues": [],
                "strengths": ["人物动机与对抗都已补足"],
                "summary": "原问题已基本修好",
            },
            ensure_ascii=False,
        )
    )
    service = SelfCritiqueService(DummyAsyncSession(), llm, DummyPromptService())

    result = await service.critique_dimension_batch(
        "林七把原件压进防潮夹，隔着门与门外人短促试探。",
        "verify_character_dynamics",
        [CritiqueDimension.CHARACTER, CritiqueDimension.RELATIONSHIP],
        focus_issues=[
            {
                "dimension": "relationship",
                "severity": "major",
                "location": "章末门外对话",
                "problem": "关系张力不足，当前更像功能性对峙。",
                "suggestion": "补试探与压迫回合。",
                "example": "你这种人会先留压痕，不会先上报。",
            }
        ],
    )

    prompt = llm.calls[0]["conversation_history"][0]["content"]
    assert "[待验证的原始问题]" in prompt
    assert "只验证上面列出的原始问题是否仍然成立" in prompt
    assert result["issues"] == []


@pytest.mark.anyio
async def test_critique_dimension_batch_sanitizes_json_like_response_before_parsing():
    raw_response = """```json
    {
      "stage": "verify_stagewide_safety",
      "dimensions": ["logic"],
      "overall_score": 82,
      "issues": [
        {
          "dimension": "logic",
          "severity": "major",
          "location": "门外脚步声贴近的一段",
          "problem": "门栓被拨动时，角色仍停留在旧判断里\n导致威胁升级没有及时传导。",
          "suggestion": "让角色立刻把门外变化并入当前决策链。",
          "example": "笃声一变，他立刻收口，不再继续追问。"
        }
      ],
      "strengths": ["章末危险感明确"],
      "summary": "仍需补上威胁传导"
    }
    ```"""
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(raw_response), DummyPromptService())

    result = await service.critique_dimension_batch(
        "门外笃笃作响，林七却还停在上一个判断里。",
        "verify_stagewide_safety",
        [CritiqueDimension.LOGIC],
        focus_issues=[
            {
                "dimension": "logic",
                "severity": "major",
                "location": "门外脚步声贴近的一段",
                "problem": "威胁升级后，人物决策没有同步变化。",
                "suggestion": "把外部危险及时并入当前动作链。",
            }
        ],
    )

    assert result["issues"]
    assert result["issues"][0]["dimension"] == "logic"
    assert "威胁升级" in result["issues"][0]["problem"]


def test_self_critique_context_is_more_aggressively_trimmed_for_delivery_stage():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    context = {
        "chapter_mission": "导演脚本" * 800,
        "previous_chapter_bundle": "前一章依据包" * 800,
        "project_memory": "长期记忆" * 600,
        "character_profiles": "角色设定" * 600,
    }

    structural_context = service._build_context_str(context, stage_name="structural")
    delivery_context = service._build_context_str(context, stage_name="delivery")

    assert len(delivery_context) < len(structural_context)
    assert len(delivery_context) < 5000


def test_self_critique_limits_stage_issues_to_distinct_root_causes():
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "logic",
            "severity": "major",
            "location": "中段追问库管",
            "problem": "同一轮追问被重复确认，形成双版本推进。",
            "suggestion": "合并为一次正式问答链。",
            "example": "库管先否认再重复否认。",
            "_critique_stage": "structural",
        },
        {
            "dimension": "pacing",
            "severity": "major",
            "location": "中段追问库管",
            "problem": "相同追问来回重复，拖慢节奏。",
            "suggestion": "删去重复确认，只保留一次改口。",
            "example": "同一信息被来回追问。",
            "_critique_stage": "delivery",
        },
        {
            "dimension": "writing",
            "severity": "major",
            "location": "中段心理判断",
            "problem": "作者判断过满，接近替读者总结。",
            "suggestion": "改成更动作化的表达。",
            "example": "这一步一做，意思就变了。",
            "_critique_stage": "delivery",
        },
        {
            "dimension": "suspense",
            "severity": "major",
            "location": "章末门铃响起",
            "problem": "章末压力仍可再压紧半拍。",
            "suggestion": "让行动意志更锋利。",
            "example": "门外来人前再顶一次决定。",
            "_critique_stage": "delivery",
        },
    ]

    limited = service._limit_stage_issues(issues, limit=3)

    assert len(limited) == 3
    assert sum(1 for item in limited if item.get("location") == "中段追问库管") == 1


@pytest.mark.anyio
async def test_critique_and_revise_loop_runs_multiple_iterations_when_issues_remain(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    critiques = [
        {
            "all_issues": [{"dimension": "logic", "severity": "major", "location": "中段", "problem": "问题1", "suggestion": "修复"}],
            "weighted_score": 70.0,
            "critical_count": 1,
            "major_count": 3,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 4,
            "deduped_issue_count": 4,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [{"dimension": "logic", "severity": "major", "location": "中段", "problem": "问题2", "suggestion": "继续修"}],
            "weighted_score": 76.0,
            "critical_count": 0,
            "major_count": 2,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 2,
            "deduped_issue_count": 2,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [],
            "weighted_score": 83.0,
            "critical_count": 0,
            "major_count": 0,
            "minor_count": 0,
            "needs_revision": False,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 0,
            "deduped_issue_count": 0,
            "merged_issue_count": 0,
        },
    ]

    async def fake_full_critique(*args, **kwargs):
        return critiques.pop(0)

    revise_calls = []

    async def fake_revise(content, issues, context=None, user_id=0, return_diagnostics=False, allow_stagewide=True):
        revise_calls.append(content)
        next_content = content + f"\n\n修订{len(revise_calls)}"
        logs = [{"strategy": "structure_guardrail", "accepted": True}]
        return (next_content, logs) if return_diagnostics else next_content

    monkeypatch.setattr(service, "full_critique", fake_full_critique)
    monkeypatch.setattr(service, "revise_chapter", fake_revise)

    result = await service.critique_and_revise_loop("原始正文", max_iterations=2)

    assert len(result["iterations"]) == 2
    assert len(revise_calls) == 2
    assert result["final_score"] == 83.0
    assert result["status"] == "optimized"


@pytest.mark.anyio
async def test_revise_chapter_defers_stagewide_fallback_without_manual_confirmation(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "logic",
            "severity": "major",
            "location": "中段盘问",
            "problem": "同一轮盘问出现双版本推进。",
            "suggestion": "合并为一次正式盘问。",
            "example": "周尧先否认再改口出现两次。",
        }
    ]

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fake_stagewide(*args, **kwargs):
        raise AssertionError("stagewide rewrite requires explicit manual confirmation")

    async def fake_snapshot(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("\n\n修正后的正式版本。"):
            return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        return {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}

    async def fake_report(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("\n\n修正后的正式版本。"):
            return {"issues": []}
        return {
            "issues": [
                {"dimension": "logic", "severity": "major", "location": "中段对话", "problem": "同一轮问答出现双版本推进。", "suggestion": "合并为一个正式问答链。", "example": "韩峤先确认，再改口处理。"}
            ]
        }

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fake_stagewide)
    monkeypatch.setattr(service, "_critique_strategy_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_critique_strategy_report", fake_report)

    revised, logs = await service.revise_chapter(
        "原始正文",
        issues,
        return_diagnostics=True,
        allow_stagewide=True,
    )

    assert revised == "原始正文"
    assert logs[0]["accepted"] is False
    assert logs[0]["stagewide_allowed"] is False
    assert logs[0]["stagewide_requested"] is True
    assert logs[0]["manual_stagewide_confirmation_required"] is True
    deferred = next(item for item in logs[0]["attempts"] if item["mode"] == "stagewide")
    assert deferred["reason"] == "stagewide_deferred"
    assert deferred["manual_confirmation_required"] is True
    assert deferred["patch_suggestions"]


@pytest.mark.anyio
async def test_revise_chapter_uses_stagewide_fallback_only_with_manual_confirmation(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "logic",
            "severity": "major",
            "location": "中段盘问",
            "problem": "同一轮盘问出现双版本推进。",
            "suggestion": "合并为一次正式盘问。",
            "example": "周尧先否认再改口出现两次。",
        }
    ]

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fake_stagewide(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content + "\n\n修正后的正式版本。"

    async def fake_snapshot(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("\n\n修正后的正式版本。"):
            return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        return {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}

    async def fake_report(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("\n\n修正后的正式版本。"):
            return {"issues": []}
        return {
            "issues": [
                {"dimension": "logic", "severity": "major", "location": "中段对话", "problem": "同一轮问答出现双版本推进。", "suggestion": "合并为一个正式问答链。", "example": "韩峤先确认，再改口处理。"}
            ]
        }

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fake_stagewide)
    monkeypatch.setattr(service, "_critique_strategy_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_critique_strategy_report", fake_report)

    revised, logs = await service.revise_chapter(
        "原始正文",
        issues,
        context={"manual_stagewide_rewrite": {"confirmed": True}},
        return_diagnostics=True,
        allow_stagewide=True,
    )

    assert revised.endswith("修正后的正式版本。")
    assert logs[0]["accepted"] is True
    assert logs[0]["stagewide_allowed"] is True
    assert any(item["mode"] == "stagewide" and item["accepted"] is True for item in logs[0]["attempts"])


@pytest.mark.anyio
async def test_revise_chapter_rejects_stagewide_candidate_when_targeted_major_issues_increase(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "logic",
            "severity": "major",
            "location": "中段盘问",
            "problem": "同一轮盘问出现双版本推进。",
            "suggestion": "合并为一次正式盘问。",
            "example": "周尧先否认再改口出现两次。",
        }
    ]

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fake_stagewide(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content + "\n\n一个更糟的版本。"

    async def fake_snapshot(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        return {"critical": 0, "major": 2, "minor": 0, "total": 2, "weighted": 20}

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fake_stagewide)
    monkeypatch.setattr(service, "_critique_strategy_snapshot", fake_snapshot)

    revised, logs = await service.revise_chapter(
        "原始正文",
        issues,
        context={"manual_stagewide_rewrite": {"confirmed": True}},
        return_diagnostics=True,
        allow_stagewide=True,
    )

    assert revised == "原始正文"
    assert logs[0]["accepted"] is False
    assert any(item["mode"] == "stagewide" and item["reason"] == "major_issues_increased" for item in logs[0]["attempts"])


@pytest.mark.anyio
async def test_revise_chapter_rejects_stagewide_candidate_when_safety_snapshot_regresses(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "character",
            "severity": "critical",
            "location": "中后段对手戏",
            "problem": "人物动机仍偏功能性。",
            "suggestion": "补个人代价与旧伤回声。",
            "example": "他盯着封存袋，没有立刻接话。",
        }
    ]

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fake_stagewide(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content + "\n\n候选版本在章末断掉。"

    async def fake_snapshot(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("候选版本在章末断掉。"):
            return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        return {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}

    async def fake_report(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("候选版本在章末断掉。"):
            return {"issues": []}
        return {
            "issues": [
                {"dimension": "character", "severity": "major", "location": "中后段对手戏", "problem": "人物动机仍偏功能性。", "suggestion": "补个人代价与旧伤回声。", "example": "他盯着封存袋，没有立刻接话。"}
            ]
        }

    async def fake_stagewide_safety(content, *, context=None, user_id=0):
        if content.endswith("候选版本在章末断掉。"):
            return {"critical": 1, "major": 2, "minor": 0, "total": 3, "weighted": 120}
        return {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fake_stagewide)
    monkeypatch.setattr(service, "_critique_strategy_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_critique_strategy_report", fake_report)
    monkeypatch.setattr(service, "_critique_stagewide_safety_snapshot", fake_stagewide_safety)

    revised, logs = await service.revise_chapter(
        "原始正文",
        issues,
        context={"manual_stagewide_rewrite": {"confirmed": True}},
        return_diagnostics=True,
        allow_stagewide=True,
    )

    assert revised == "原始正文"
    assert logs[0]["accepted"] is False
    assert any(item["mode"] == "stagewide" and item["reason"] == "safety_critical_issues_increased" for item in logs[0]["attempts"])


@pytest.mark.anyio
async def test_revise_chapter_rejects_candidate_when_aggregate_strategy_snapshot_is_not_improved(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "writing",
            "severity": "major",
            "location": "中段总结句",
            "problem": "解释性总结仍然过满。",
            "suggestion": "把结论压回动作与留白。",
            "example": "他先把残页抽了回来。",
        }
    ]

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content + "\n\n候选版本删掉了原总结句。"

    async def fake_snapshot(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("候选版本删掉了原总结句。"):
            return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        return {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}

    async def fake_report(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("候选版本删掉了原总结句。"):
            return {
                "issues": [
                    {"dimension": "writing", "severity": "major", "location": "中段总结句", "problem": "解释性总结仍然过满。", "suggestion": "把结论压回动作与留白。", "example": "他先把残页抽了回来。"}
                ]
            }
        return {
            "issues": [
                {"dimension": "writing", "severity": "major", "location": "中段总结句", "problem": "解释性总结仍然过满。", "suggestion": "把结论压回动作与留白。", "example": "他先把残页抽了回来。"}
            ]
        }

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_critique_strategy_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_critique_strategy_report", fake_report)

    revised, logs = await service.revise_chapter("原始正文", issues, return_diagnostics=True)

    assert revised == "原始正文"
    assert logs[0]["accepted"] is False
    localized_attempt = next(item for item in logs[0]["attempts"] if item["mode"] == "localized")
    assert localized_attempt["accepted"] is False
    assert localized_attempt["reason"] == "aggregate_not_improved_enough"
    assert localized_attempt["aggregate_before"] == {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}
    assert localized_attempt["aggregate_after"] == {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}


@pytest.mark.anyio
async def test_revise_chapter_retries_stagewide_with_aggregate_feedback(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "character",
            "severity": "critical",
            "location": "对手戏中段",
            "problem": "人物反应仍然偏功能性。",
            "suggestion": "补人物伤口与关系代价。",
            "example": "他先看了一眼核验条，才继续说话。",
        }
    ]
    call_state = {"stagewide": 0}

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fake_stagewide(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        call_state["stagewide"] += 1
        if call_state["stagewide"] == 1:
            return content + "\n\n第一次候选。"
        assert len(issues) >= 2
        return content + "\n\n第二次候选。"

    async def fake_snapshot(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("第一次候选。"):
            return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        if content.endswith("第二次候选。"):
            return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        return {"critical": 0, "major": 1, "minor": 0, "total": 1, "weighted": 10}

    async def fake_report(content, *, strategy_key, context=None, user_id=0, focus_issues=None):
        if content.endswith("第一次候选。"):
            return {
                "issues": [
                    {"dimension": "character", "severity": "major", "location": "旧伤缺失", "problem": "私人伤口仍缺失。", "suggestion": "补一记失去过的代价。", "example": "他想起上次空白名单。"},
                    {"dimension": "relationship", "severity": "major", "location": "对手压迫", "problem": "关系试探仍然不够。", "suggestion": "补一句识别性施压台词。", "example": "对方先报出他的习惯。"},
                ]
            }
        if content.endswith("第二次候选。"):
            return {"issues": []}
        return {
            "issues": [
                {"dimension": "character", "severity": "major", "location": "对手戏中段", "problem": "人物反应仍然偏功能性。", "suggestion": "补人物伤口与关系代价。", "example": "他先看了一眼核验条，才继续说话。"},
                {"dimension": "relationship", "severity": "major", "location": "对手压迫", "problem": "关系试探仍然不够。", "suggestion": "补一句识别性施压台词。", "example": "对方先报出他的习惯。"},
            ]
        }

    async def fake_stagewide_safety(content, *, context=None, user_id=0):
        return {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fake_stagewide)
    monkeypatch.setattr(service, "_critique_strategy_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_critique_strategy_report", fake_report)
    monkeypatch.setattr(service, "_critique_stagewide_safety_snapshot", fake_stagewide_safety)

    revised, logs = await service.revise_chapter(
        "原始正文",
        issues,
        context={"manual_stagewide_rewrite": {"confirmed": True}},
        return_diagnostics=True,
        allow_stagewide=True,
    )

    assert revised.endswith("第二次候选。")
    assert logs[0]["accepted"] is True
    stagewide_attempts = [item for item in logs[0]["attempts"] if item["mode"] == "stagewide"]
    assert len(stagewide_attempts) == 2
    assert stagewide_attempts[0]["accepted"] is False
    assert stagewide_attempts[0]["reason"] == "aggregate_not_improved_enough"
    assert stagewide_attempts[1]["accepted"] is True
    assert stagewide_attempts[1]["retry_source"] == "aggregate_feedback"
    assert stagewide_attempts[1]["aggregate_after"] == {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}


@pytest.mark.anyio
async def test_revise_chapter_marks_stagewide_as_deferred_when_iteration_budget_is_locked(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "character",
            "severity": "critical",
            "location": "对手戏中段",
            "problem": "人物反应仍然偏功能性，需要更大范围重写才能补足。",
            "suggestion": "补人物伤口与关系代价。",
            "example": "他先看了一眼核验条，才继续说话。",
        }
    ]

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("stagewide rewrite should be deferred instead of executed")

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fail_if_called)

    revised, logs = await service.revise_chapter("原始正文", issues, return_diagnostics=True)

    assert revised == "原始正文"
    assert logs[0]["stagewide_allowed"] is False
    assert logs[0]["stagewide_deferred"] is True
    assert any(item["mode"] == "stagewide" and item["reason"] == "stagewide_deferred" for item in logs[0]["attempts"])


@pytest.mark.anyio
async def test_revise_chapter_skips_stagewide_for_long_form_delivery_polish_with_limited_issues(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    issues = [
        {
            "dimension": "writing",
            "severity": "major",
            "location": "对峙中段",
            "problem": "说明句偏多，动作压迫感不足。",
            "suggestion": "压缩解释并把信息回收到动作与对白。",
            "example": "他先把纸页压平，才继续往下说。",
        },
        {
            "dimension": "pacing",
            "severity": "major",
            "location": "逼问后半段",
            "problem": "节奏略拖，钩子抬升不够快。",
            "suggestion": "删掉重复铺陈，让威胁更早落地。",
            "example": "门外的脚步声又近了一格。",
        },
    ]
    long_content = ("原始正文" * 900) + "\n\n章末钩子。"

    async def fake_local(content, issues, context=None, user_id=0, strategy_key="delivery_polish"):
        return content

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("stagewide rewrite should be skipped for this long-form low-ROI delivery pass")

    monkeypatch.setattr(service, "_revise_chapter_locally", fake_local)
    monkeypatch.setattr(service, "_revise_chapter_stagewide", fail_if_called)

    revised, logs = await service.revise_chapter(long_content, issues, return_diagnostics=True, allow_stagewide=True)

    assert revised == long_content
    assert logs[0]["stagewide_allowed"] is False
    assert logs[0]["stagewide_requested"] is True
    assert logs[0]["stagewide_attempted"] is False
    assert logs[0]["stagewide_accepted"] is False


@pytest.mark.anyio
async def test_critique_and_revise_loop_frontloads_deferred_stage_on_next_iteration(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    logic_issue = {"dimension": "logic", "severity": "major", "location": "中段", "problem": "规则边界没钉实", "suggestion": "补规则后果"}
    character_issue = {"dimension": "character", "severity": "major", "location": "后段", "problem": "失忆伤口不够具体", "suggestion": "补身体反应"}
    critiques = [
        {
            "all_issues": [logic_issue, character_issue],
            "weighted_score": 72.0,
            "critical_count": 0,
            "major_count": 2,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 2,
            "deduped_issue_count": 2,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [logic_issue, character_issue],
            "weighted_score": 74.0,
            "critical_count": 0,
            "major_count": 2,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 2,
            "deduped_issue_count": 2,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [],
            "weighted_score": 83.0,
            "critical_count": 0,
            "major_count": 0,
            "minor_count": 0,
            "needs_revision": False,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 0,
            "deduped_issue_count": 0,
            "merged_issue_count": 0,
        },
    ]

    async def fake_full_critique(*args, **kwargs):
        return critiques.pop(0)

    call_sequence = []

    async def fake_revise(content, issues, context=None, user_id=0, return_diagnostics=False, allow_stagewide=True):
        dimension = issues[0]["dimension"]
        call_sequence.append((dimension, allow_stagewide))
        changed = allow_stagewide
        next_content = content + f"\n\n{dimension}-修订" if changed else content
        strategy = "structure_guardrail" if dimension == "logic" else "character_dynamics"
        logs = [
            {
                "strategy": strategy,
                "accepted": changed,
                "stagewide_allowed": allow_stagewide,
                "stagewide_accepted": changed and allow_stagewide,
                "stagewide_deferred": not allow_stagewide,
                "attempts": [
                    {
                        "mode": "stagewide",
                        "changed": changed,
                        "accepted": changed,
                        "reason": "reduced_major_issues" if changed else "stagewide_deferred",
                    }
                ],
            }
        ]
        return (next_content, logs) if return_diagnostics else next_content

    monkeypatch.setattr(service, "full_critique", fake_full_critique)
    monkeypatch.setattr(service, "revise_chapter", fake_revise)

    result = await service.critique_and_revise_loop("原始正文", max_iterations=2)

    assert call_sequence == [
        ("logic", False),
        ("character", False),
    ]
    assert len(result["iterations"]) == 1
    assert result["final_score"] == 72.0
    assert all(log["stagewide_deferred"] is True for log in result["optimization_logs"])


@pytest.mark.anyio
async def test_critique_and_revise_loop_adds_one_extra_iteration_to_drain_deferred_stagewide_work(monkeypatch):
    service = SelfCritiqueService(DummyAsyncSession(), FakeLLMService(""), DummyPromptService())
    logic_issue = {"dimension": "logic", "severity": "major", "location": "中段", "problem": "规则边界没钉实", "suggestion": "补规则后果"}
    character_issue = {"dimension": "character", "severity": "major", "location": "后段", "problem": "人物伤口不够具体", "suggestion": "补身体反应"}
    critiques = [
        {
            "all_issues": [logic_issue, character_issue],
            "weighted_score": 72.0,
            "critical_count": 0,
            "major_count": 2,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 2,
            "deduped_issue_count": 2,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [logic_issue, character_issue],
            "weighted_score": 74.0,
            "critical_count": 0,
            "major_count": 2,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 2,
            "deduped_issue_count": 2,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [logic_issue],
            "weighted_score": 76.0,
            "critical_count": 0,
            "major_count": 1,
            "minor_count": 0,
            "needs_revision": True,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 1,
            "deduped_issue_count": 1,
            "merged_issue_count": 0,
        },
        {
            "all_issues": [],
            "weighted_score": 84.0,
            "critical_count": 0,
            "major_count": 0,
            "minor_count": 0,
            "needs_revision": False,
            "priority_fixes": [],
            "stage_summaries": [],
            "raw_issue_count": 0,
            "deduped_issue_count": 0,
            "merged_issue_count": 0,
        },
    ]

    async def fake_full_critique(*args, **kwargs):
        return critiques.pop(0)

    call_sequence = []

    async def fake_revise(content, issues, context=None, user_id=0, return_diagnostics=False, allow_stagewide=True):
        dimension = issues[0]["dimension"]
        call_sequence.append((dimension, allow_stagewide))
        changed = allow_stagewide
        next_content = content + f"\n\n{dimension}-修订" if changed else content
        strategy = "structure_guardrail" if dimension == "logic" else "character_dynamics"
        logs = [
            {
                "strategy": strategy,
                "accepted": changed,
                "stagewide_allowed": allow_stagewide,
                "stagewide_accepted": changed and allow_stagewide,
                "stagewide_deferred": not allow_stagewide,
                "attempts": [
                    {
                        "mode": "stagewide",
                        "changed": changed,
                        "accepted": changed,
                        "reason": "reduced_major_issues" if changed else "stagewide_deferred",
                    }
                ],
            }
        ]
        return (next_content, logs) if return_diagnostics else next_content

    monkeypatch.setattr(service, "full_critique", fake_full_critique)
    monkeypatch.setattr(service, "revise_chapter", fake_revise)

    result = await service.critique_and_revise_loop("原始正文", max_iterations=2)

    assert len(result["iterations"]) == 1
    assert call_sequence == [
        ("logic", False),
        ("character", False),
    ]
    assert "deferred_stage_replay_extension" not in result["iterations"][0]
    assert result["final_score"] == 72.0


def test_failed_generation_runtime_state_preserves_debug_payload_for_quality_gate_failures():
    chapter = DummyChapter(
        chapter_number=1,
        real_summary=json.dumps(
            {
                "generation_runtime": {
                    "run_id": "run-1",
                    "progress_stage": "review",
                    "review_summaries": {
                        "self_critique": {"final_score": 25.5, "critical_count": 1},
                        "consistency": {"unresolved_count": 2},
                    },
                    "runtime_metadata": {
                        "quality_gates": {"structural_gate": {"passed": False}},
                        "stage_timings_ms": {"generate_variants": 392776.84},
                    },
                    "events": [{"stage": "review", "message": "结构质量闸门未通过"}],
                }
            },
            ensure_ascii=False,
        ),
    )

    payload = json.loads(
        _build_failed_generation_runtime_state(
            chapter,
            run_id="run-1",
            reason="章节仍存在严重结构/一致性问题，已阻止静默成功落库。",
        )
    )
    runtime = payload["generation_runtime"]

    assert runtime["progress_stage"] == "failed"
    assert runtime["review_summaries"]["self_critique"]["final_score"] == 25.5
    assert runtime["runtime_metadata"]["quality_gates"]["structural_gate"]["passed"] is False
    assert runtime["events"][-1]["stage"] == "failed"



def test_preserve_non_regressive_content_allows_revision_stage_to_remove_duplicate_residue():
    previous = "\n".join(["旧片段残留"] * 100)
    candidate = "\n".join(["去重后正文"] * 74)

    kept, guard = PipelineOrchestrator._preserve_non_regressive_content(
        previous_content=previous,
        candidate_content=candidate,
        stage_label="consistency_repair",
        min_word_count=None,
    )

    assert kept == candidate
    assert guard is None


def test_preserve_non_regressive_content_still_blocks_catastrophic_shrinkage_in_revision_stage():
    previous = "\n".join(["旧片段残留"] * 100)
    candidate = "\n".join(["去重后正文"] * 60)

    kept, guard = PipelineOrchestrator._preserve_non_regressive_content(
        previous_content=previous,
        candidate_content=candidate,
        stage_label="consistency_repair",
        min_word_count=None,
    )

    assert kept == previous
    assert guard is not None
    assert guard["reason"] == "catastrophic_shrinkage"
    assert guard["preserved_floor_ratio"] == 0.72


def test_collect_unresolved_consistency_violations_prefers_post_fix_snapshot_even_when_fix_was_adopted():
    report = {
        "auto_fix_applied": True,
        "auto_fix_accepted": True,
        "violations": [
            {"severity": "major", "category": "plot", "description": "旧冲突", "location": "旧位置"},
        ],
        "post_fix_check": {
            "violations": [
                {"severity": "major", "category": "plot", "description": "新冲突", "location": "新位置"},
            ]
        },
    }

    unresolved = PipelineOrchestrator._collect_unresolved_consistency_violations(report)

    assert len(unresolved) == 1
    assert unresolved[0]["description"] == "新冲突"
    assert unresolved[0]["location"] == "新位置"


def test_normalize_consistency_issues_for_local_fix_prefers_post_fix_unresolved_violations():
    report = {
        "auto_fix_applied": True,
        "auto_fix_accepted": False,
        "violations": [
            {"severity": "major", "category": "plot", "description": "旧卷年份冲突", "location": "第2段"},
        ],
        "post_fix_check": {
            "violations": [
                {
                    "severity": "major",
                    "category": "plot",
                    "description": "借阅单来源仍像两条并行事件链。",
                    "location": "第2段与第4段",
                    "suggested_fix": "统一物件流转来源，只保留一个正式版本。",
                },
            ]
        },
    }

    normalized = PipelineOrchestrator._normalize_consistency_issues_for_local_fix(report)

    assert len(normalized) == 1
    assert normalized[0]["problem"] == "借阅单来源仍像两条并行事件链。"
    assert normalized[0]["location"] == "第2段与第4段"
    assert normalized[0]["suggestion"] == "统一物件流转来源，只保留一个正式版本。"


def test_should_accept_self_critique_revision_when_critical_issues_drop():
    before_report = {
        "weighted_score": 58.0,
        "critical_count": 2,
        "major_count": 5,
        "minor_count": 1,
        "needs_revision": True,
    }
    after_report = {
        "weighted_score": 46.0,
        "critical_count": 1,
        "major_count": 5,
        "minor_count": 1,
        "needs_revision": True,
    }

    accepted, reason, before_stats, after_stats = PipelineOrchestrator._should_accept_self_critique_revision(
        before_report,
        after_report,
    )

    assert accepted is True
    assert reason == "reduced_critical_issues"
    assert before_stats["critical"] == 2
    assert after_stats["critical"] == 1



def test_should_reject_self_critique_revision_when_score_collapses_without_issue_reduction():
    before_report = {
        "weighted_score": 55.7,
        "critical_count": 2,
        "major_count": 4,
        "minor_count": 1,
        "needs_revision": True,
    }
    after_report = {
        "weighted_score": 5.1,
        "critical_count": 5,
        "major_count": 6,
        "minor_count": 0,
        "needs_revision": True,
    }

    accepted, reason, before_stats, after_stats = PipelineOrchestrator._should_accept_self_critique_revision(
        before_report,
        after_report,
    )

    assert accepted is False
    assert reason == "critical_issues_increased"
    assert before_stats["score"] == 55.7
    assert after_stats["score"] == 5.1



def test_should_reject_self_critique_revision_when_score_improves_but_critical_issues_increase():
    before_report = {
        "weighted_score": 8.0,
        "critical_count": 0,
        "major_count": 7,
        "minor_count": 2,
        "needs_revision": True,
    }
    after_report = {
        "weighted_score": 27.8,
        "critical_count": 3,
        "major_count": 7,
        "minor_count": 1,
        "needs_revision": True,
    }

    accepted, reason, before_stats, after_stats = PipelineOrchestrator._should_accept_self_critique_revision(
        before_report,
        after_report,
    )

    assert accepted is False
    assert reason == "critical_issues_increased"
    assert before_stats["critical"] == 0
    assert after_stats["critical"] == 3


def test_consistency_fallback_fix_guard_rejects_partial_or_collapsed_repair():
    service = ConsistencyService(db=None, llm_service=None)
    original = "\n\n".join(
        [
            "第一段保留前锚点，主角带着旧卷宗进入听潮祠。"*2,
            "第二段说明上一章留下的缉印令压力仍在。"*2,
            "第三段对话推进冲突，对手要求他交出证据。"*2,
            "第四段主角发现账页编号和旧案编号重合。"*2,
            "第五段他决定暂时隐瞒发现，把风险压给下一步行动。"*2,
            "第六段保留后锚点，门外水路封锁的锣声逼近。"*2,
        ]
    )
    partial = "只修复中段冲突，但丢掉章首章尾和多数原有段落。"*80

    assert service._fix_continuity_guard_failure(original, partial).startswith(
        "fixed_content_collapsed_paragraphs"
    )


def test_consistency_fallback_fix_guard_accepts_anchored_full_chapter_repair():
    service = ConsistencyService(db=None, llm_service=None)
    original_parts = [
        "第一段保留前锚点，主角带着旧卷宗进入听潮祠。",
        "第二段说明上一章留下的缉印令压力仍在。",
        "第三段对话推进冲突，对手要求他交出证据。",
        "第四段主角发现账页编号和旧案编号重合。",
        "第五段他决定暂时隐瞒发现，把风险压给下一步行动。",
        "第六段保留后锚点，门外水路封锁的锣声逼近。",
    ]
    fixed_parts = list(original_parts)
    fixed_parts[2] = "第三段对话推进冲突，对手先要求交证据，主角再用编号反制，冲突链只保留一个正式版本。"

    assert service._fix_continuity_guard_failure(
        "\n\n".join(original_parts),
        "\n\n".join(fixed_parts),
    ) is None


@pytest.mark.anyio
async def test_consistency_auto_fix_skips_full_chapter_fallback_without_confirmation(monkeypatch):
    service = ConsistencyService(db=None, llm_service=FakeLLMService(""))

    async def fake_context(*args, **kwargs):
        return {"novel_setting": "设定", "character_state": "角色状态", "global_summary": "前文"}

    async def fake_local(*args, **kwargs):
        return None

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("full-chapter consistency fallback should require explicit confirmation")

    monkeypatch.setattr(service, "_get_check_context", fake_context)
    monkeypatch.setattr(service, "_auto_fix_locally", fake_local)
    monkeypatch.setattr(consistency_service_module, "call_generation_text", fail_if_called)

    result = await service.auto_fix(
        project_id="project-1",
        chapter_text="第一段保留前锚点。\n\n第二段存在冲突。\n\n第三段保留后锚点。",
        violations=[
            ConsistencyViolation(
                severity=ViolationSeverity.MAJOR,
                category="plot",
                description="来源存在双版本残留。",
                location="第2段",
                suggested_fix="统一来源，只保留一个正式版本。",
            )
        ],
        user_id=1,
    )

    assert result is None


@pytest.mark.anyio
async def test_consistency_auto_fix_allows_full_chapter_fallback_when_confirmed(monkeypatch):
    service = ConsistencyService(db=None, llm_service=FakeLLMService(""))
    original = "\n\n".join(
        [
            "第一段保留前锚点，主角带着旧卷宗进入听潮祠。",
            "第二段说明上一章留下的缉印令压力仍在。",
            "第三段对话存在两个来源版本，需要统一。",
            "第四段保留后锚点，门外水路封锁的锣声逼近。",
        ]
    )
    fixed = original.replace("第三段对话存在两个来源版本，需要统一。", "第三段对话只保留借阅单这一条正式来源，并让主角用编号反制。")

    async def fake_context(*args, **kwargs):
        return {"novel_setting": "设定", "character_state": "角色状态", "global_summary": "前文"}

    async def fake_local(*args, **kwargs):
        return None

    async def fake_call_generation_text(*args, **kwargs):
        return type("Result", (), {"text": fixed})()

    monkeypatch.setattr(service, "_get_check_context", fake_context)
    monkeypatch.setattr(service, "_auto_fix_locally", fake_local)
    monkeypatch.setattr(consistency_service_module, "call_generation_text", fake_call_generation_text)

    result = await service.auto_fix(
        project_id="project-1",
        chapter_text=original,
        violations=[
            ConsistencyViolation(
                severity=ViolationSeverity.CRITICAL,
                category="plot",
                description="来源存在双版本残留。",
                location="第3段",
                suggested_fix="统一来源，只保留一个正式版本。",
            )
        ],
        user_id=1,
        allow_full_chapter_fallback=True,
    )

    assert result == fixed



def test_should_accept_consistency_improvement_when_unresolved_severity_drops():
    before_report = {
        "violations": [
            {"severity": "critical", "category": "plot", "description": "双版本事件链"},
            {"severity": "major", "category": "plot", "description": "承接跳切"},
        ]
    }
    after_report = {
        "status": "warning",
        "is_consistent": False,
        "violations": [
            {"severity": "major", "category": "plot", "description": "只剩一个 major"},
        ],
    }

    accepted, reason, before_counts, after_counts = PipelineOrchestrator._should_accept_consistency_improvement(
        before_report,
        after_report,
    )

    assert accepted is True
    assert reason == "reduced_unresolved_severity"
    assert before_counts == {"critical": 1, "major": 1, "total": 2, "weighted": 4}
    assert after_counts == {"critical": 0, "major": 1, "total": 1, "weighted": 1}


def test_should_reject_consistency_improvement_when_only_swapping_one_critical_for_many_majors():
    before_report = {
        "violations": [
            {"severity": "critical", "category": "plot", "description": "双版本事件链"},
        ]
    }
    after_report = {
        "status": "warning",
        "is_consistent": False,
        "violations": [
            {"severity": "major", "category": "plot", "description": "major-1"},
            {"severity": "major", "category": "plot", "description": "major-2"},
            {"severity": "major", "category": "plot", "description": "major-3"},
            {"severity": "major", "category": "plot", "description": "major-4"},
        ],
    }

    accepted, reason, before_counts, after_counts = PipelineOrchestrator._should_accept_consistency_improvement(
        before_report,
        after_report,
    )

    assert accepted is False
    assert reason == "not_improved_enough"
    assert before_counts == {"critical": 1, "major": 0, "total": 1, "weighted": 3}
    assert after_counts == {"critical": 0, "major": 4, "total": 4, "weighted": 4}


@pytest.mark.anyio
async def test_run_consistency_check_retries_with_post_fix_feedback(monkeypatch):
    orchestrator = PipelineOrchestrator(DummyAsyncSession())
    orchestrator.llm_service = FakeLLMService("")

    initial_violation = ConsistencyViolation(
        severity=ViolationSeverity.MAJOR,
        category="plot",
        description="旧卷年份与黑潮登陆夜日期直接冲突。",
        location="第2段",
        suggested_fix="补一条旧封新页或二次篡改解释。",
    )
    retry_violation = ConsistencyViolation(
        severity=ViolationSeverity.MAJOR,
        category="plot",
        description="借阅单来源仍像两条并行事件链。",
        location="第2段与第4段",
        suggested_fix="统一物件流转来源，只保留一个正式版本。",
    )

    async def fake_check_consistency(self, project_id, chapter_text, user_id, include_foreshadowing=True):
        if chapter_text == "原稿":
            return type(
                "CheckResult",
                (),
                {
                    "is_consistent": False,
                    "violations": [initial_violation],
                    "summary": "首次检查发现时间冲突。",
                    "check_time_ms": 12,
                    "status": "warning",
                },
            )()
        if chapter_text == "第一次修复":
            return type(
                "CheckResult",
                (),
                {
                    "is_consistent": False,
                    "violations": [retry_violation],
                    "summary": "第一次修复后仍残留来源冲突。",
                    "check_time_ms": 18,
                    "status": "warning",
                },
            )()
        if chapter_text == "第二次修复":
            return type(
                "CheckResult",
                (),
                {
                    "is_consistent": True,
                    "violations": [],
                    "summary": "第二次修复后通过。",
                    "check_time_ms": 10,
                    "status": "passed",
                },
            )()
        raise AssertionError(f"unexpected chapter_text: {chapter_text}")

    async def fake_auto_fix(self, project_id, chapter_text, violations, user_id):
        if chapter_text == "原稿":
            return "第一次修复"
        if chapter_text == "第一次修复":
            assert len(violations) == 1
            assert violations[0].description == "借阅单来源仍像两条并行事件链。"
            return "第二次修复"
        raise AssertionError(f"unexpected auto_fix input: {chapter_text}")

    monkeypatch.setattr(ConsistencyService, "check_consistency", fake_check_consistency)
    monkeypatch.setattr(ConsistencyService, "auto_fix", fake_auto_fix)

    fixed, report = await orchestrator._run_consistency_check(
        project_id="project-1",
        chapter_text="原稿",
        user_id=1,
    )

    assert fixed == "第二次修复"
    assert report["auto_fix_applied"] is True
    assert report["auto_fix_accepted"] is True
    assert report["auto_fix_acceptance_reason"] == "fully_consistent"
    assert report["post_fix_check"]["status"] == "passed"
    assert len(report["repair_attempts"]) == 2
    assert report["repair_attempts"][0]["accepted"] is False
    assert report["repair_attempts"][1]["accepted"] is True
    assert report["repair_attempts"][1]["retry_source"] == "post_fix_feedback"


@pytest.mark.anyio
async def test_run_consistency_check_reports_deferred_full_chapter_fallback(monkeypatch):
    orchestrator = PipelineOrchestrator(DummyAsyncSession())
    orchestrator.llm_service = FakeLLMService("")
    violation = ConsistencyViolation(
        severity=ViolationSeverity.MAJOR,
        category="plot",
        description="来源仍像两条并行事件链。",
        location="第2段",
        suggested_fix="统一来源，只保留一个正式版本。",
    )

    async def fake_check_consistency(self, project_id, chapter_text, user_id, include_foreshadowing=True):
        return type(
            "CheckResult",
            (),
            {
                "is_consistent": False,
                "violations": [violation],
                "summary": "发现一致性问题。",
                "check_time_ms": 12,
                "status": "warning",
            },
        )()

    async def fake_auto_fix(self, project_id, chapter_text, violations, user_id):
        return None

    monkeypatch.setattr(ConsistencyService, "check_consistency", fake_check_consistency)
    monkeypatch.setattr(ConsistencyService, "auto_fix", fake_auto_fix)

    fixed, report = await orchestrator._run_consistency_check(
        project_id="project-1",
        chapter_text="原稿",
        user_id=1,
    )

    assert fixed == "原稿"
    assert report["auto_fix_applied"] is False
    assert report["auto_fix_accepted"] is False
    assert report["repair_attempts"] == [
        {
            "attempt": 1,
            "mode": "local_patch",
            "accepted": False,
            "acceptance_reason": "local_repair_failed_full_chapter_deferred",
            "content_changed": False,
            "full_chapter_fallback_deferred": True,
            "manual_confirmation_required": True,
        }
    ]


@pytest.mark.anyio
async def test_call_llm_with_stage_retries_recovers_from_retryable_provider_jitter():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    llm = RetryThenSuccessLLMService('{"ok": true}')
    raw = await _call_llm_with_stage_retries(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        user_id=1,
        timeout=30.0,
        response_format="json_object",
        stage_label="测试阶段",
        progress_callback=progress_callback,
        progress_stage="generating",
        retry_attempts=3,
    )

    assert raw == '{"ok": true}'
    assert llm.calls == 2
    assert stages == [("generating", "测试阶段遇到上游抖动，正在进行第 1/2 次重试")]


@pytest.mark.anyio
async def test_repair_blueprint_character_names_assigns_concrete_name():
    llm = FakeLLMService(
        json.dumps(
            {
                "title": "异海开拓史",
                "one_sentence_summary": "林渡在异海求生并建立新文明。",
                "full_synopsis": "林渡从孤岛求生开始，逐步建立航路、势力与新文明秩序。",
                "characters": [
                    {"name": "林渡", "role": "主角", "importance": "main"},
                    {"name": "沈砚秋", "role": "核心同伴", "importance": "core"},
                ],
                "relationships": [
                    {"character_a": "林渡", "character_b": "沈砚秋", "relation_type": "盟友", "description": "共同开拓航路"}
                ],
                "novel_outline": [
                    {
                        "stage": 1,
                        "title": "孤岛立足",
                        "core_theme": "生存",
                        "goal": "林渡建立据点",
                        "main_conflict": "资源匮乏",
                        "background": "孤岛危机四伏",
                        "character_progression": "林渡开始学会统筹同伴",
                        "world_progression": "揭示海域规则",
                        "faction_progression": "海盗试探靠近",
                        "power_progression": "林渡摸索修炼体系",
                        "key_events": ["建立营地", "发现遗迹", "击退试探", "收拢同伴", "锁定航图"],
                        "stage_climax": "林渡守住营地",
                        "foreshadowing_and_payoff": "埋下身世与航图伏笔",
                        "ending_hook": "更深海域坐标浮现",
                        "expected_chapter_range": "1-60章"
                    }
                ],
                "chapter_outline": [],
            },
            ensure_ascii=False,
        )
    )

    repaired = await _repair_blueprint_character_names(
        llm_service=llm,
        blueprint_data={
            "title": "异海开拓史",
            "one_sentence_summary": "主角在异海求生并建立新文明。",
            "full_synopsis": "主角从孤岛求生开始，逐步建立航路、势力与新文明秩序。",
            "characters": [{"name": "主角", "role": "主角", "importance": "main"}],
            "relationships": [],
            "novel_outline": [],
            "chapter_outline": [],
        },
        user_id=1,
        project_title="异海开拓史",
    )

    assert repaired["characters"][0]["name"] == "林渡"
    assert repaired["one_sentence_summary"].startswith("林渡")


@pytest.mark.anyio
async def test_resolve_llm_config_falls_back_to_settings_when_process_env_missing(monkeypatch):
    session = DummyAsyncSession()
    service = LLMService(session)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
    monkeypatch.setattr("app.services.llm_service.settings.openai_api_key", "settings-key")
    monkeypatch.setattr("app.services.llm_service.settings.openai_base_url", "http://127.0.0.1:8317/v1")
    monkeypatch.setattr("app.services.llm_service.settings.openai_model_name", "settings-model")

    config = await service._resolve_llm_config(None, enforce_daily_limit=False)

    assert config["api_key"] == "settings-key"
    assert config["base_url"] == "http://127.0.0.1:8317/v1"
    assert config["model"] == "settings-model"


@pytest.mark.anyio
async def test_resolve_llm_config_recovers_from_stale_db_session():
    session = DummyAsyncSession()
    service = LLMService(session)

    class BrokenRepo:
        async def get_by_user(self, user_id: int):
            raise OperationalError("SELECT 1", {"user_id": user_id}, Exception("Lost connection to MySQL server during query"))

    async def fake_load_user_llm_config_fresh(user_id: int):
        return type(
            "Config",
            (),
            {
                "llm_provider_profiles": None,
                "llm_provider_api_key": "fresh-key",
                "llm_provider_model": "fresh-model",
                "llm_provider_url": "https://example.invalid/v1",
            },
        )()

    service.llm_repo = BrokenRepo()
    service._load_user_llm_config_fresh = fake_load_user_llm_config_fresh

    config = await service._resolve_llm_config(1, enforce_daily_limit=False)

    assert config["api_key"] == "fresh-key"
    assert config["model"] == "fresh-model"
    assert session.rollback_calls == 1


@pytest.mark.anyio
async def test_resolve_llm_config_recovers_from_session_contention():
    session = DummyAsyncSession()
    service = LLMService(session)

    class BusyRepo:
        async def get_by_user(self, user_id: int):
            raise RuntimeError("This session is provisioning a new connection; concurrent operations are not permitted")

    async def fake_load_user_llm_config_fresh(user_id: int):
        return type(
            "Config",
            (),
            {
                "llm_provider_profiles": None,
                "llm_provider_api_key": "fresh-busy-key",
                "llm_provider_model": "fresh-busy-model",
                "llm_provider_url": "https://busy.example.invalid/v1",
            },
        )()

    service.llm_repo = BusyRepo()
    service._load_user_llm_config_fresh = fake_load_user_llm_config_fresh

    config = await service._resolve_llm_config(1, enforce_daily_limit=False)

    assert config["api_key"] == "fresh-busy-key"
    assert config["model"] == "fresh-busy-model"
    assert session.rollback_calls == 1


@pytest.mark.anyio
async def test_resolve_llm_config_caches_user_specific_result():
    session = DummyAsyncSession()
    service = LLMService(session)

    class CountingRepo:
        def __init__(self):
            self.calls = 0

        async def get_by_user(self, user_id: int):
            self.calls += 1
            return type(
                "Config",
                (),
                {
                    "llm_provider_profiles": None,
                    "llm_provider_api_key": "cached-key",
                    "llm_provider_model": "cached-model",
                    "llm_provider_url": "https://cache.example.invalid/v1",
                },
            )()

    repo = CountingRepo()
    service.llm_repo = repo

    first = await service._resolve_llm_config(7, enforce_daily_limit=False)
    first["api_key"] = "mutated-locally"
    second = await service._resolve_llm_config(7, enforce_daily_limit=False)

    assert repo.calls == 1
    assert second["api_key"] == "cached-key"
    assert second["model"] == "cached-model"


@pytest.mark.anyio
async def test_get_config_value_recovers_from_session_contention():
    session = DummyAsyncSession()
    service = LLMService(session)

    class BusySystemRepo:
        async def get_by_key(self, key: str):
            raise RuntimeError("This session is provisioning a new connection; concurrent operations are not permitted")

    async def fake_load_system_config_value_fresh(key: str):
        assert key == "embedding.model"
        return "fresh-embedding-model"

    service.system_config_repo = BusySystemRepo()
    service._load_system_config_value_fresh = fake_load_system_config_value_fresh

    value = await service._get_config_value("embedding.model")

    assert value == "fresh-embedding-model"
    assert session.rollback_calls == 1


@pytest.mark.anyio
async def test_resolve_llm_config_charges_daily_limit_once_per_async_task(monkeypatch):
    session = DummyAsyncSession()
    service = LLMService(session)

    llm_service_module._DAILY_LIMIT_SCOPE_STATE.set(None)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_API_BASE_URL", "http://127.0.0.1:8317/v1")
    monkeypatch.setenv("OPENAI_MODEL_NAME", "env-model")

    class EmptyRepo:
        async def get_by_user(self, user_id: int):
            return None

    class AdminSettingStub:
        async def get(self, key: str, default: str = "100"):
            return "100"

    class UserRepoStub:
        def __init__(self):
            self.used = 0
            self.increment_calls = 0

        async def get_daily_request(self, user_id: int):
            return self.used

        async def increment_daily_request(self, user_id: int):
            self.increment_calls += 1
            self.used += 1

    user_repo = UserRepoStub()
    service.llm_repo = EmptyRepo()
    service.admin_setting_service = AdminSettingStub()
    service.user_repo = user_repo

    first = await service._resolve_llm_config(1)
    second = await service._resolve_llm_config(1)

    async def resolve_in_child_task():
        return await service._resolve_llm_config(1)

    third = await asyncio.create_task(resolve_in_child_task())

    assert first["api_key"] == "env-key"
    assert second["api_key"] == "env-key"
    assert third["api_key"] == "env-key"
    assert user_repo.increment_calls == 1
    assert session.commit_calls == 1


@pytest.mark.anyio
async def test_stream_single_model_retries_once_after_rate_limit(monkeypatch):
    session = DummyAsyncSession()
    service = LLMService(session)
    llm_service_module._PROVIDER_COOLDOWNS.clear()

    sleep_calls = []

    async def fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr("app.services.llm_service.asyncio.sleep", fake_sleep)

    class FakeResponse:
        headers = {"retry-after": "0.01"}

        def json(self):
            return {"error": {"message": "provider busy"}}

    class DummyRateLimitError(Exception):
        def __init__(self):
            self.response = FakeResponse()
            super().__init__("provider busy")

    monkeypatch.setattr("app.services.llm_service.RateLimitError", DummyRateLimitError)

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def stream_chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise DummyRateLimitError()
            yield {"content": "retry-ok", "finish_reason": None}
            yield {"content": "", "finish_reason": "stop"}

    client = FakeClient()
    response, finish_reason = await service._stream_single_model(
        client=client,
        chat_messages=[],
        model_name="test-model",
        provider_key="http://127.0.0.1:8317/v1::test-model",
        temperature=0.3,
        user_id=1,
        timeout=30,
        retry_same_model_once=True,
    )

    assert response == "retry-ok"
    assert finish_reason == "stop"
    assert client.calls == 2
    assert sleep_calls


def test_blueprint_job_error_string_is_normalized_to_structured_error():
    response = _serialize_blueprint_job(
        {
            "run_id": "run-1",
            "project_id": "project-1",
            "status": "failed",
            "error": "llm timeout",
        }
    )

    assert response.error is not None
    assert response.error.code == "blueprint_generation_failed"
    assert response.error.detail == "llm timeout"
    assert response.error.retryable is True


def test_stale_blueprint_job_only_warns_and_keeps_active_status():
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=_BLUEPRINT_JOB_STALE_SECONDS + 5)

    recovered = _recover_stale_blueprint_job(
        {
            "run_id": "run-2",
            "project_id": "project-1",
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "正在补全世界体系",
            "updated_at": stale_time.isoformat(),
        }
    )

    assert recovered["status"] == "generating"
    assert recovered["progress_stage"] == "generating"
    assert "仅提示，不再自动判死" in recovered["progress_message"]
    assert recovered["error"] is None


def test_blueprint_stale_threshold_is_extended_beyond_legacy_thirty_minutes():
    assert _BLUEPRINT_JOB_STALE_SECONDS > 30 * 60
    assert _BLUEPRINT_JOB_HEARTBEAT_SECONDS < _BLUEPRINT_JOB_STALE_SECONDS


def test_runtime_stale_uses_chapter_updated_at_when_runtime_timestamp_missing():
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    chapter = DummyChapter(
        real_summary=json.dumps(
            {
                "generation_runtime": {
                    "progress_stage": "generating",
                    "progress_message": "running",
                }
            }
        ),
        status="generating",
        updated_at=old_time,
        created_at=old_time,
    )

    runtime = _extract_generation_runtime_payload(chapter)

    assert runtime["stale"] is True
    assert runtime["stale_seconds"] >= 15 * 60
    assert runtime["stale_reason"] == "generation_runtime_has_not_updated"


def test_runtime_stale_reports_unknown_when_no_timestamp_available():
    chapter = DummyChapter(
        real_summary=json.dumps({"generation_runtime": {"progress_stage": "generating"}}),
        status="generating",
        updated_at=None,
        created_at=None,
    )

    runtime = _extract_generation_runtime_payload(chapter)

    assert runtime["stale"] is None
    assert runtime["stale_reason"] == "generation_runtime_missing_update_timestamp"


def test_build_chapter_schema_uses_runtime_actual_word_count_and_exposes_version_word_counts(monkeypatch):
    monkeypatch.setattr(
        novel_service_module,
        "build_chapter_progress_snapshot",
        lambda *args, **kwargs: {
            "progress_stage": "waiting_for_confirm",
            "progress_message": "候选版本已准备完成，等待确认最终版本",
            "started_at": None,
            "updated_at": None,
            "allowed_actions": ["confirm_version"],
            "last_error_summary": None,
        },
    )

    version_one = DummyChapter(id=11, content="甲" * 120, version_label="v1", metadata={}, created_at=datetime.now(timezone.utc))
    version_two = DummyChapter(
        id=12,
        content="乙" * 80,
        version_label="v2",
        metadata={
            "quality_metrics": {
                "scene_fulfillment_rate": 0.75,
                "dialogue_changes_state": True,
            }
        },
        created_at=datetime.now(timezone.utc),
    )
    chapter = DummyChapter(
        chapter_number=1,
        status="waiting_for_confirm",
        word_count=0,
        real_summary=json.dumps(
            {
                "generation_runtime": {
                    "progress_stage": "waiting_for_confirm",
                    "actual_word_count": 5072,
                    "progress_message": "候选版本已准备完成，等待确认最终版本",
                }
            },
            ensure_ascii=False,
        ),
        selected_version_id=12,
        selected_version=version_one,
        versions=[version_one, version_two],
        evaluations=[],
        updated_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    outline = DummyChapter(chapter_number=1, title="雾夜来客", summary="测试摘要")
    project = DummyChapter(outlines=[outline], chapters=[chapter])

    service = NovelService(None)
    result = service._build_chapter_schema(project, 1, include_content=True)

    assert result.word_count == 5072
    assert result.selected_version_id == 12
    assert result.content == "乙" * 80
    assert result.versions is not None
    assert result.versions[0].word_count == 120
    assert result.versions[1].word_count == 80
    assert result.generation_runtime["quality_metrics"]["scene_fulfillment_rate"] == 0.75
    assert result.generation_runtime["quality_metrics_source_version_id"] == 12


def test_history_active_blueprint_job_only_warns_when_worker_missing():
    recovered = _fail_orphaned_blueprint_job(
        {
            "run_id": "run-orphan",
            "project_id": "project-1",
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "正在生成小说总大纲",
        }
    )

    assert recovered["status"] == "generating"
    assert recovered["progress_stage"] == "generating"
    assert "当前进程未找到活跃执行器" in recovered["progress_message"]
    assert recovered["error"] is None



def test_blueprint_schema_without_content_is_not_usable():
    service = NovelService(None)

    assert service._is_blueprint_schema_usable(Blueprint(title="")) is False



def test_blueprint_schema_with_summary_is_usable():
    service = NovelService(None)

    assert service._is_blueprint_schema_usable(
        Blueprint(title="", one_sentence_summary="一个能继续创作的故事核心")
    ) is True


def test_build_compact_blueprint_context_prefers_latest_conversation_state():
    context = _build_compact_blueprint_context(
        formatted_history=[
            {"role": "user", "content": "想写海洋文明"},
            {"role": "assistant", "content": "继续补充"},
        ],
        structured_dialogue=[
            {
                "role": "assistant",
                "conversation_state": {
                    "checklist": {"working_title": True},
                    "collected_info": {"working_title": "异海开拓史", "chapter_count": "500-1000章"},
                },
            }
        ],
        existing_blueprint=Blueprint(title="异海开拓史", one_sentence_summary="摘要"),
    )

    assert context["collected_info"]["working_title"] == "异海开拓史"
    assert context["checklist"]["working_title"] is True
    assert context["existing_blueprint"]["title"] == "异海开拓史"


def test_build_outline_source_context_compacts_large_blueprint_payload():
    context = _build_outline_source_context(
        {
            "title": "异海开拓史",
            "full_synopsis": "海潮与旧文明" * 600,
            "world_setting": {
                "core_rules": "海潮会周期性改写航路规则。" * 80,
                "key_locations": [{"name": f"地点{i}", "description": "描述" * 40} for i in range(12)],
                "factions": [{"name": f"势力{i}", "goal": "扩张" * 40} for i in range(11)],
            },
            "characters": [{"name": f"角色{i}", "role": "核心角色", "description": "背景" * 50} for i in range(15)],
            "relationships": [{"character_a": "甲", "character_b": "乙", "relation_type": "盟友", "description": "关系" * 40} for _ in range(20)],
            "story_arcs": [{"title": f"弧线{i}", "summary": "剧情" * 40} for i in range(9)],
            "volume_plan": [{"title": f"卷{i}", "summary": "卷摘要" * 40} for i in range(10)],
            "foreshadowing_system": [{"summary": "伏笔" * 40} for _ in range(14)],
        }
    )

    assert len(context["full_synopsis"]) <= 1500
    assert len(context["world_setting"]["key_locations"]) == 8
    assert len(context["world_setting"]["factions"]) == 8
    assert len(context["characters"]) == 10
    assert len(context["relationships"]) == 12
    assert len(context["story_arcs"]) == 8
    assert len(context["volume_plan"]) == 8
    assert len(context["foreshadowing_system"]) == 10


def test_build_story_constraint_profile_and_gap_scan_capture_missing_longform_slots():
    profile = _build_story_constraint_profile(
        formatted_history=[
            {"role": "user", "content": "想写一个在断裂时代重建秩序的长篇故事"},
            {"role": "assistant", "content": "继续补充主角与世界规则"},
            {"role": "user", "content": "主角想从边陲小人物一路改写旧秩序"},
        ],
        structured_dialogue=[
            {
                "role": "assistant",
                "conversation_state": {
                    "collected_info": {"theme": "秩序重建", "protagonist_goal": "改写旧秩序"},
                    "checklist": {"world_rule": False, "core_conflict": True},
                },
            }
        ],
        project_title="断界新秩序",
        existing_blueprint=None,
    )

    gaps = _scan_longform_structure_gaps(
        {
            "title": "断界新秩序",
            "one_sentence_summary": "边陲小人物卷入旧秩序崩裂。",
            "full_synopsis": "",
            "world_setting": {},
            "characters": [{"name": "林渡"}],
            "relationships": [],
            "story_arcs": [],
            "volume_plan": [],
            "foreshadowing_system": [],
        }
    )

    assert profile["project_title"] == "断界新秩序"
    assert profile["explicit_constraints"]
    assert "world_rule" in profile["unresolved_slots"]
    assert "对话内容是约束来源，不是内容上限。" in profile["generation_principles"]
    assert "era_background" in gaps["world_slots_missing"]
    assert "full_synopsis" in gaps["story_slots_missing"]
    assert gaps["coverage_summary"]["world_slots_missing_count"] >= 10


def test_length_contract_keeps_short_projects_from_becoming_forced_longform():
    contract = _build_length_contract(
        formatted_history=[
            {"role": "user", "content": "写一部12章左右的东方玄幻冒险小说，章节要连续推进。"},
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=None,
    )

    assert contract["target_chapter_count"] == 12
    assert contract["stage_count_min"] == 4
    assert contract["stage_count_max"] <= 6
    assert contract["chapter_outline_seed_count"] == 12
    assert "约 12 章" in _format_length_contract_instruction(contract)

    oversized_outline = [
        {"stage": 1, "title": "起", "core_theme": "起", "expected_chapter_range": "1-35章"},
        {"stage": 2, "title": "承", "core_theme": "承", "expected_chapter_range": "36-70章"},
        {"stage": 3, "title": "转", "core_theme": "转", "expected_chapter_range": "71-105章"},
        {"stage": 4, "title": "合", "core_theme": "合", "expected_chapter_range": "106-140章"},
    ]
    remapped = _remap_outline_ranges_to_length_contract(oversized_outline, contract)

    assert [item["expected_chapter_range"] for item in remapped] == ["1-3章", "4-6章", "7-9章", "10-12章"]
    assert _resolve_blueprint_chapter_outline_count(
        {"world_setting": {"system_blueprint": {"length_contract": contract}}}
    ) == 12


def test_length_contract_allows_three_act_outline_for_very_short_projects():
    contract = _build_length_contract(
        formatted_history=[
            {"role": "user", "content": "写一部8章左右的东方玄幻短篇，章节要连续推进。"},
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=None,
    )

    assert contract["target_chapter_count"] == 8
    assert contract["stage_count_min"] == 3
    assert contract["stage_count_max"] <= 5
    assert _resolve_novel_outline_min_stage_count(
        {"world_setting": {"system_blueprint": {"length_contract": contract}}}
    ) == 3
    _validate_novel_outline_coherence(
        [
            {"stage": 1, "core_theme": "开端", "expected_chapter_range": "1-2章"},
            {"stage": 2, "core_theme": "对抗", "expected_chapter_range": "3-5章"},
            {"stage": 3, "core_theme": "收束", "expected_chapter_range": "6-8章"},
        ],
        min_stage_count=contract["stage_count_min"],
    )


def test_length_contract_does_not_compress_long_projects_to_twelve_chapters():
    contract_120 = _build_length_contract(
        formatted_history=[
            {"role": "user", "content": "写一部120章左右的东方玄幻长篇，章节之间要连续推进。"},
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=None,
    )
    contract_300 = _build_length_contract(
        formatted_history=[
            {"role": "user", "content": "写一部300章左右的群像长篇，不要压缩成短纲。"},
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=None,
    )

    assert contract_120["target_chapter_count"] == 120
    assert contract_120["chapter_outline_seed_count"] == 60
    assert contract_120["stage_count_max"] >= 12
    assert _resolve_blueprint_chapter_outline_count(
        {"world_setting": {"system_blueprint": {"length_contract": contract_120}}}
    ) == 60
    assert "不会被压缩成 12 章骨架" in _format_length_contract_instruction(contract_120)

    assert contract_300["target_chapter_count"] == 300
    assert contract_300["chapter_outline_seed_count"] == 80
    assert contract_300["stage_count_max"] >= 16
    assert _resolve_blueprint_chapter_outline_count(
        {"world_setting": {"system_blueprint": {"length_contract": contract_300}}}
    ) == 80


def test_length_contract_prefers_user_request_over_existing_outline_ranges():
    existing_blueprint = Blueprint(
        title="旧蓝图",
        one_sentence_summary="旧版已经被错误扩成长篇。",
        world_setting={
            "system_blueprint": {
                "length_contract": {
                    "target_chapter_count": 390,
                    "stage_count_min": 8,
                    "stage_count_max": 12,
                    "chapter_outline_seed_count": 12,
                }
            }
        },
        novel_outline=[
            {
                "stage": 1,
                "title": "旧阶段",
                "core_theme": "旧扩容",
                "expected_chapter_range": "346-390章",
            }
        ],
    )

    contract = _build_length_contract(
        formatted_history=[
            {"role": "user", "content": "写一部12章左右的东方玄幻冒险小说，章节要连续推进。"},
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=existing_blueprint,
    )

    assert contract["target_chapter_count"] == 12
    assert contract["source"] == "explicit_user_or_project_length"


def test_length_contract_understands_hyphenated_english_chapter_count():
    existing_blueprint = Blueprint(
        title="旧蓝图",
        one_sentence_summary="旧版已经被错误扩成长篇。",
        world_setting={
            "system_blueprint": {
                "length_contract": {
                    "target_chapter_count": 390,
                    "chapter_outline_seed_count": 12,
                }
            }
        },
    )

    contract = _build_length_contract(
        formatted_history=[
            {
                "role": "user",
                "content": '{"value": "A 12-chapter eastern fantasy adventure with continuous chapter progression."}',
            },
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=existing_blueprint,
    )

    assert contract["target_chapter_count"] == 12
    assert contract["source"] == "explicit_user_or_project_length"


def test_length_contract_does_not_infer_from_existing_generated_ranges():
    existing_blueprint = Blueprint(
        title="旧蓝图",
        one_sentence_summary="旧版总纲残留。",
        novel_outline=[
            {
                "stage": 1,
                "title": "旧阶段",
                "core_theme": "旧扩容",
                "expected_chapter_range": "346-390章",
            }
        ],
    )

    contract = _build_length_contract(
        formatted_history=[],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=existing_blueprint,
    )

    assert contract["target_chapter_count"] == 60
    assert contract["source"] == "inferred_project_scale"
    assert contract["target_chapter_count"] != 390


def test_length_contract_infers_longform_from_total_word_count():
    contract = _build_length_contract(
        formatted_history=[
            {"role": "user", "content": "写一部百万字左右的玄幻长篇，跨章节伏笔和角色状态要持续。"},
        ],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=None,
    )

    assert contract["source"] == "inferred_project_scale"
    assert contract["target_chapter_count"] >= 180
    assert contract["chapter_outline_seed_count"] >= 80


def test_length_contract_reuses_stored_contract_when_user_does_not_restates_length():
    existing_blueprint = Blueprint(
        title="旧蓝图",
        one_sentence_summary="已保存明确篇幅。",
        world_setting={
            "system_blueprint": {
                "length_contract": {
                    "target_chapter_count": 20,
                    "chapter_outline_seed_count": 20,
                }
            }
        },
    )

    contract = _build_length_contract(
        formatted_history=[{"role": "user", "content": "继续完善这个故事。"}],
        structured_dialogue=[],
        project_title="潮印迷城",
        existing_blueprint=existing_blueprint,
    )

    assert contract["target_chapter_count"] == 20
    assert contract["chapter_outline_seed_count"] == 20
    assert contract["source"] == "stored_blueprint_length_contract"


def test_gap_scan_treats_whitespace_world_slots_as_missing_and_scales_world_timeout():
    blueprint_data = {
        "title": "断界新秩序",
        "one_sentence_summary": "边陲小人物卷入旧秩序崩裂。",
        "full_synopsis": "旧秩序崩裂后，主角在边陲地带重建文明接口。" * 60,
        "characters": [{"name": "林渡", "role": "主角"} for _ in range(6)],
        "relationships": [{"character_a": "林渡", "character_b": "顾岚", "relation_type": "盟友"} for _ in range(4)],
        "story_arcs": [{"title": "边陲立足", "summary": "建立秩序"} for _ in range(3)],
        "volume_plan": [{"title": "裂界初卷", "summary": "从生存到建制"} for _ in range(3)],
        "foreshadowing_system": [{"summary": "旧秩序遗留接口"} for _ in range(3)],
        "world_setting": {
            "era_background": "   ",
            "world_structure": "\n\n",
            "power_system": {"core": " ", "limits": "\t"},
            "survival_system": {"food": "", "risk": "  "},
            "life_system": "  ",
            "culture_system": {"customs": "\n"},
            "civilization_system": " ",
            "economy_system": {"trade": "\t"},
            "social_structure": " ",
            "resource_system": " ",
            "belief_system": " ",
            "geography_system": " ",
            "faction_order": " ",
        },
    }

    gaps = _scan_longform_structure_gaps(blueprint_data)

    assert gaps["coverage_summary"]["world_slots_missing_count"] == 13
    assert _resolve_world_bible_timeout_seconds(blueprint_data) >= 420.0


def test_build_chapter_outline_source_context_compacts_total_outline_and_timeout_scales():
    context = _build_chapter_outline_source_context(
        {
            "full_synopsis": "长梗概" * 400,
            "characters": [{"name": f"角色{i}"} for i in range(12)],
            "relationships": [{"character_a": "甲", "character_b": "乙"} for _ in range(15)],
            "story_arcs": [{"title": f"弧线{i}"} for i in range(8)],
            "volume_plan": [{"title": f"卷{i}"} for i in range(8)],
            "foreshadowing_system": [{"summary": "伏笔"} for _ in range(8)],
            "novel_outline": [{"stage": i, "title": f"阶段{i}", "background": "背景" * 80} for i in range(1, 8)],
        }
    )

    assert len(context["novel_outline"]) == 6
    assert len(context["story_arcs"]) == 8
    assert len(context["volume_plan"]) == 8
    assert len(context["foreshadowing_system"]) == 8
    blueprint_data = {
        "full_synopsis": "长梗概" * 400,
        "characters": [{"name": f"角色{i}"} for i in range(12)],
        "relationships": [{"character_a": "甲", "character_b": "乙"} for _ in range(15)],
        "story_arcs": [{"title": f"弧线{i}"} for i in range(8)],
        "volume_plan": [{"title": f"卷{i}"} for i in range(8)],
        "foreshadowing_system": [{"summary": "伏笔"} for _ in range(8)],
    }
    assert _resolve_novel_outline_timeout_seconds(blueprint_data) == 600.0
    assert _resolve_world_bible_timeout_seconds(blueprint_data) >= 360.0
    assert _resolve_outline_chunk_timeout_seconds(blueprint_data, 3) >= 300.0


def test_parse_expected_chapter_range_and_validate_outline_coherence():
    assert _parse_expected_chapter_range("1-60章") == (1, 60)
    assert _parse_expected_chapter_range("61至120章") == (61, 120)
    assert _parse_expected_chapter_range("无效") is None

    coherent_outline = [
        {"stage": 1, "core_theme": "立足", "expected_chapter_range": "1-60章"},
        {"stage": 2, "core_theme": "扩张", "expected_chapter_range": "61-140章"},
        {"stage": 3, "core_theme": "远航", "expected_chapter_range": "141-260章"},
        {"stage": 4, "core_theme": "重组", "expected_chapter_range": "261-520章"},
    ]
    _validate_novel_outline_coherence(coherent_outline)

    with pytest.raises(Exception):
        _validate_novel_outline_coherence(
            [
                {"stage": 1, "core_theme": "立足", "expected_chapter_range": "2-60章"},
                {"stage": 2, "core_theme": "扩张", "expected_chapter_range": "61-140章"},
                {"stage": 3, "core_theme": "远航", "expected_chapter_range": "141-260章"},
                {"stage": 4, "core_theme": "重组", "expected_chapter_range": "261-520章"},
            ]
        )

    with pytest.raises(Exception):
        _validate_novel_outline_coherence(
            [
                {"stage": 1, "core_theme": "立足", "expected_chapter_range": "1-60章"},
                {"stage": 2, "core_theme": "扩张", "expected_chapter_range": "62-140章"},
                {"stage": 3, "core_theme": "远航", "expected_chapter_range": "141-260章"},
                {"stage": 4, "core_theme": "重组", "expected_chapter_range": "261-520章"},
            ]
        )

    with pytest.raises(Exception):
        _validate_novel_outline_coherence(
            [
                {"stage": 1, "core_theme": "立足", "expected_chapter_range": "1-60章"},
                {"stage": 3, "core_theme": "远航", "expected_chapter_range": "61-140章"},
                {"stage": 4, "core_theme": "重组", "expected_chapter_range": "120-200章"},
                {"stage": 5, "core_theme": "终局", "expected_chapter_range": "201-260章"},
            ]
        )


def test_validate_novel_outline_depth_rejects_shell_outline():
    rich_outline = [
        {
            "stage": 1,
            "survival_and_life_progression": "建立淡水与值夜制度",
            "cultural_and_civilizational_progression": "形成最初共享规则",
            "resource_and_operation_line": "围绕淡水、补给与安全区展开",
            "emotional_core": "从恐惧转向秩序",
            "major_setpiece": "夜潮保卫战",
            "story_function": "把故事从求生推进到文明主线入口",
            "turning_points": ["发现潮汐异常"],
            "stage_tasks": ["建立营地制度"],
        },
        {
            "stage": 2,
            "survival_and_life_progression": "建立食物储备与工位分工",
            "cultural_and_civilizational_progression": "从互助走向奖惩共识",
            "resource_and_operation_line": "围绕营地扩建与航标搜索展开",
            "emotional_core": "从不安转向控制感",
            "major_setpiece": "海兽冲击营地",
            "story_function": "把主角从幸存者推向组织者",
            "turning_points": ["修炼试验成功"],
            "stage_tasks": [],
        },
    ]
    _validate_novel_outline_depth(rich_outline)

    with pytest.raises(Exception):
        _validate_novel_outline_depth(
            [
                {
                    "stage": 1,
                    "survival_and_life_progression": "建立淡水与值夜制度",
                    "cultural_and_civilizational_progression": "形成最初共享规则",
                    "resource_and_operation_line": "围绕淡水、补给与安全区展开",
                    "emotional_core": "从恐惧转向秩序",
                    "major_setpiece": "夜潮保卫战",
                    "story_function": "把故事从求生推进到文明主线入口",
                    "turning_points": [],
                    "stage_tasks": [],
                }
            ]
        )


def test_normalize_blueprint_error_detail_extracts_provider_timeout_message():
    message, detail, retryable = _normalize_blueprint_error_detail(
        {
            "code": "PROVIDER_TIMEOUT",
            "message": "AI 服务在限定时间内未完成响应，系统已主动中止本次调用。",
            "hint": "上游网关长时间无响应，请稍后重试。",
            "retryable": True,
        }
    )

    assert message == "AI 服务在限定时间内未完成响应，系统已主动中止本次调用。"
    assert "上游网关长时间无响应" in detail
    assert retryable is True


@pytest.mark.anyio
async def test_generate_novel_outline_builds_total_outline_when_missing():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    initial_outline = {
        "novel_outline": [
            {
                "stage": 1,
                "title": "孤岛立足",
                "core_theme": "从求生到建立最初秩序",
                "goal": "先活下来并建立最初秩序",
                "main_conflict": "资源匮乏与未知海域规则",
                "background": "主角流落孤岛，外部海域危险未明，岛上资源有限，旧文明残迹还处于不可解释状态。",
                "character_progression": "主角从单纯求生转向主动观察环境，并与最早的同伴建立互信分工。",
                "world_progression": "读者第一次理解海潮、岛屿异常与海域规则并非自然现象，而是与更大文明遗产有关。",
                "faction_progression": "本阶段主要是零散幸存者的临时结盟，外部势力还未正式登场，但其痕迹已经出现。",
                "power_progression": "主角开始摸索基础修炼反馈机制，明白生存、认知与修炼体系是绑定的。",
                "key_events": ["搭建营地", "搜集淡水", "发现潮汐异常", "夜探残迹", "第一次资源危机"],
                "stage_climax": "主角在夜潮中进入残迹边缘，确认岛屿背后存在被封存的文明线索。",
                "foreshadowing_and_payoff": "埋下岛屿非自然形成、潮汐带有筛选机制、主角体质与遗迹存在呼应等伏笔。",
                "ending_hook": "主角在夜潮中看到不该出现的旧文明残迹",
                "expected_chapter_range": "1-60章",
            },
            {
                "stage": 2,
                "title": "经营扩张",
                "core_theme": "从求生据点走向可持续经营",
                "goal": "建立小型聚落并试探修炼体系",
                "main_conflict": "内部分工与外部海兽威胁同步升级",
                "background": "孤岛生存进入相对稳定期，但物资循环、居住秩序与安全边界都开始暴露短板。",
                "character_progression": "主角学会统筹资源与人心，核心同伴开始形成各自位置，彼此关系也出现裂痕与磨合。",
                "world_progression": "读者进一步看到海洋生态、残迹技术与修炼资源之间存在系统性联系。",
                "faction_progression": "岛内形成初步阵营分工，外部未知势力通过痕迹、遗物和海路封锁间接施压。",
                "power_progression": "主角与同伴完成修炼体系的第一次可复制试验，开始从个体摸索转向小规模实践。",
                "key_events": ["结识同伴", "重整营地", "首次海兽冲击", "修炼试验成功", "发现被破坏的旧航标"],
                "stage_climax": "海兽袭击迫使聚落第一次全面协同，主角因此确认单靠求生思维已经不够。",
                "foreshadowing_and_payoff": "回收前期异常潮汐会吸引海兽的伏笔，并埋下外部势力长期监视这片海域的线索。",
                "ending_hook": "主角确认岛屿与航道存在人为封锁",
                "expected_chapter_range": "61-140章",
            },
            {
                "stage": 3,
                "title": "航路开启",
                "core_theme": "从孤岛经营走向外海探索",
                "goal": "正式踏上外海并触及文明主线",
                "main_conflict": "旧文明遗产争夺与新势力围猎",
                "background": "岛内体系暂稳，主角必须离开舒适区，进入真正的海域秩序与航路竞争。",
                "character_progression": "主角从地方性领头人转变为真正的探索者，团队内部也开始因道路选择出现分化。",
                "world_progression": "外海航路、海图体系、文明碎片和失落港口逐步露出，世界尺度明显放大。",
                "faction_progression": "多个海上势力与旧文明继承者正式出现，围绕航图、遗产与主角展开争夺。",
                "power_progression": "修炼体系从生存辅助升级为航海、战斗和文明解译的核心能力框架。",
                "key_events": ["拿到航图", "修复旧船", "第一次出海", "接触外海港口", "卷入遗产争夺", "踏入第一条外海航道"],
                "stage_climax": "主角在外海首次正面击败围猎者，同时确认自己已被卷入更大的文明博弈。",
                "foreshadowing_and_payoff": "回收岛屿封锁并非个例的伏笔，埋下主角身世、遗产权限与航道核心秘密。",
                "ending_hook": "真正的大航海时代只露出冰山一角",
                "expected_chapter_range": "141-260章",
            },
            {
                "stage": 4,
                "title": "文明重组",
                "core_theme": "在时代裂变中争夺新秩序",
                "goal": "在时代裂变中争夺新秩序位置",
                "main_conflict": "多方文明路线碰撞与主角道路定型",
                "background": "旧秩序开始崩裂，海域各地都因遗产复苏、航路开放与资源重分配而进入动荡。",
                "character_progression": "主角必须决定自己是成为征服者、守护者还是重建者，核心角色也将站到不同立场。",
                "world_progression": "海域文明的历史真相、体系源头与时代终局逐步揭开，世界观进入总回收阶段。",
                "faction_progression": "联盟、帝国、商会、遗民与新兴势力全面洗牌，形成最终阵营对抗。",
                "power_progression": "主角把早期零散体系整合成真正可影响时代格局的新道路。",
                "key_events": ["联盟裂变", "真相揭露", "新体系定名", "旧秩序崩塌", "终局前哨战", "决定海域未来规则"],
                "stage_climax": "主角在终局碰撞中用自己建立的新体系改写海域规则。",
                "foreshadowing_and_payoff": "集中回收主角体质、旧文明权限、外海封锁源头与航路真相等长线伏笔。",
                "ending_hook": "主角被迫决定整个海域的未来规则",
                "expected_chapter_range": "261-520章",
            },
        ]
    }
    world_bible = {
        "world_bible": {
            "era_background": "旧文明断裂后进入群岛争夺时代，海潮周期性改写航路与资源分布。",
            "world_structure": "世界由多层海域、残迹岛链、旧港网络与潮汐航路构成。",
            "power_system": {"core": "修炼需绑定潮汐反馈", "levels": "以航阶与权限阶并行提升"},
            "survival_system": {"food": "淡水、渔获、盐储构成基础命脉"},
            "life_system": {"daily_routine": "潮汐时刻决定作息、出航和防灾"},
            "culture_system": {"customs": "海祭、潮历、航名制度塑造身份认同"},
            "civilization_system": {"origins": "旧文明依靠潮汐权限统治海域"},
            "economy_system": {"trade": "航图、盐、修炼材料与遗物构成贸易核心"},
            "social_structure": "聚落、船团、商盟与遗民议会构成多层权力网络",
            "resource_system": "淡水、稳固锚地、遗物权限和潮汐矿是核心稀缺资源",
            "belief_system": "海神传说与旧文明遗训共同影响决策",
            "geography_system": "海域按潮区、禁区、旧港走廊分层",
            "faction_order": "商盟控制流通，海盗扰动秩序，遗民掌握旧权限残片",
        }
    }
    enriched_chunk_one = {
        "novel_outline": [
            dict(initial_outline["novel_outline"][0], survival_and_life_progression="主角从抢水、搭棚、守夜逐步建立淡水储备、火种轮值、渔获分配与避潮制度。", cultural_and_civilizational_progression="幸存者从各自为战转向形成最早的海祭、值夜和资源共享规则。", resource_and_operation_line="重点争夺淡水、火种、可食物资与残迹边缘安全区。", emotional_core="恐惧中的求生意志", major_setpiece="夜潮侵袭孤岛营地", turning_points=["发现潮汐异常不是自然现象", "确认残迹与主角体质存在呼应"], story_function="负责把故事从求生题材推进到文明伏笔题材", key_events=["搭建营地", "搜集淡水", "发现潮汐异常", "夜探残迹", "第一次资源危机", "建立守夜制度"]),
            dict(initial_outline["novel_outline"][1], survival_and_life_progression="聚落开始形成食物储备、捕猎协作、工位分工、基础医护与潮汐预警。", cultural_and_civilizational_progression="营地内部从临时互助过渡到早期秩序与奖惩共识。", resource_and_operation_line="围绕营地扩建、海兽处理、工具修补与航标搜索展开。", emotional_core="从不安到建立控制感", major_setpiece="海兽冲击与营地总动员", turning_points=["修炼试验成功", "确认外部势力长期监视岛屿"], story_function="负责把主角从幸存者推向组织者", key_events=["结识同伴", "重整营地", "首次海兽冲击", "修炼试验成功", "发现被破坏的旧航标", "建立物资轮换制度"]),
            dict(initial_outline["novel_outline"][2], survival_and_life_progression="生存重心从岛内稳态转向跨海补给、船员协作与远航损耗控制。", cultural_and_civilizational_progression="团队形成真正的船团文化与航海纪律。", resource_and_operation_line="围绕航图、船体、港口准入、遗产权限与海路补给展开。", emotional_core="兴奋与危险并行的开拓冲动", major_setpiece="首次外海突破围猎", turning_points=["第一次出海成功", "被更大文明博弈盯上"], story_function="负责把故事正式推入大航海与文明争夺主线", key_events=["拿到航图", "修复旧船", "第一次出海", "接触外海港口", "卷入遗产争夺", "踏入第一条外海航道"]),
        ]
    }
    enriched_chunk_two = {
        "novel_outline": [
            dict(initial_outline["novel_outline"][3], survival_and_life_progression="生存问题上升为文明层面的秩序再分配，后勤、航道与人口安置成为核心。", cultural_and_civilizational_progression="不同文明传统、统治逻辑与价值观全面碰撞并重组。", resource_and_operation_line="围绕战略海域、权限节点、新体系传播与联盟维持成本展开。", emotional_core="承担时代选择的压迫感", major_setpiece="终局秩序会战", turning_points=["旧文明真相彻底揭露", "主角必须决定海域未来规则"], story_function="负责完成终局秩序重组与长线伏笔总回收", key_events=["联盟裂变", "真相揭露", "新体系定名", "旧秩序崩塌", "终局前哨战", "决定海域未来规则"]),
        ]
    }
    llm = FakeLLMService([
        json.dumps(world_bible, ensure_ascii=False),
        json.dumps(world_bible, ensure_ascii=False),
        json.dumps(world_bible, ensure_ascii=False),
        json.dumps(initial_outline, ensure_ascii=False),
        json.dumps(enriched_chunk_one, ensure_ascii=False),
        json.dumps(enriched_chunk_two, ensure_ascii=False),
    ])

    result = await _generate_novel_outline(
        llm_service=llm,
        blueprint_data={
            "title": "异海开拓史",
            "one_sentence_summary": "从孤岛生存开始的异海长篇",
            "full_synopsis": "长篇慢热海洋文明故事",
            "world_setting": {"core": "海洋文明 + 修炼反馈生态"},
            "characters": [{"name": "主角"}],
            "relationships": [],
            "story_arcs": [],
            "volume_plan": [],
            "foreshadowing_system": [],
            "novel_outline": [],
        },
        user_id=1,
        progress_callback=progress_callback,
    )

    assert stages == [
        ("blueprint_setting_lock", "正在补全世界体系（历史背景 / 世界结构 / 地理秩序）（1/3）"),
        ("blueprint_setting_lock", "正在补全世界体系（力量体系 / 生存生活逻辑）（2/3）"),
        ("blueprint_setting_lock", "正在补全世界体系（文化文明 / 经济社会 / 信仰秩序）（3/3）"),
        ("blueprint_setting_lock", "正在锁定设定与长篇目标（世界规则 / 角色规模 / 伏笔回收）"),
        ("blueprint_plot_threads", "正在生成小说总大纲（阶段骨架首轮）"),
        ("blueprint_plot_threads", "正在解析小说总大纲骨架"),
        ("blueprint_foreshadowing", "正在校验小说总大纲骨架连续性"),
        ("blueprint_foreshadowing", "正在细化角色生命周期、伏笔回收窗口和阶段任务"),
        ("blueprint_plot_threads", "正在细化小说总大纲（第 1/2 段）"),
        ("blueprint_plot_threads", "正在细化小说总大纲（第 2/2 段）"),
    ]
    assert len(result["novel_outline"]) == 4
    assert result["novel_outline"][0]["title"] == "孤岛立足"
    assert result["novel_outline"][0]["background"]
    assert len(result["novel_outline"][0]["key_events"]) >= 6
    assert result["novel_outline"][0]["survival_and_life_progression"]
    assert result["novel_outline"][0]["story_function"]
    assert result["novel_outline"][0]["expected_chapter_range"] == "1-60章"
    assert result["world_setting"]["power_system"]["core"] == "修炼需绑定潮汐反馈"
    assert result["world_setting"]["system_blueprint"]["geography_system"] == "海域按潮区、禁区、旧港走廊分层"
    assert len(llm.calls) == 6
    assert llm.calls[0]["timeout"] >= 220.0
    assert llm.calls[1]["timeout"] >= 220.0
    assert llm.calls[2]["timeout"] >= 220.0
    assert llm.calls[3]["timeout"] >= 360.0
    assert llm.calls[4]["timeout"] >= 300.0
    assert "本轮只允许输出的字段" in llm.calls[0]["conversation_history"][0]["content"]
    assert "历史与世界格局" in llm.calls[0]["conversation_history"][0]["content"]
    assert "力量与生存运行" in llm.calls[1]["conversation_history"][0]["content"]
    assert "文明与社会规则" in llm.calls[2]["conversation_history"][0]["content"]
    assert "压缩整理过的蓝图关键信息" in llm.calls[3]["conversation_history"][0]["content"]
    assert "严格根据蓝图材料本身" in llm.calls[3]["conversation_history"][0]["content"]
    assert "固定题材模板" in llm.calls[3]["conversation_history"][0]["content"]
    assert "大航海主线" not in llm.calls[3]["conversation_history"][0]["content"]
    assert "世界系统总表" in llm.calls[4]["conversation_history"][0]["content"]


def test_has_complete_chapter_outline_uses_expected_count_when_available():
    complete = [{"chapter_number": index, "title": f"第{index}章", "summary": "摘要"} for index in range(1, 13)]
    partial = complete[:4]
    broken = complete[:11] + [{"chapter_number": 13, "title": "第13章", "summary": "摘要"}]

    assert _has_complete_chapter_outline(complete, expected_count=12) is True
    assert _has_complete_chapter_outline(partial, expected_count=12) is False
    assert _has_complete_chapter_outline(broken, expected_count=12) is False
    assert _has_complete_chapter_outline(partial, expected_count=4) is True


@pytest.mark.anyio
async def test_generate_executable_chapter_outline_builds_outline_when_missing():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    outline_items = []
    for chapter_number in range(1, 13):
        outline_items.append(
            {
                "chapter_number": chapter_number,
                "title": f"第{chapter_number}章标题",
                "summary": "主角先稳住生存，再发现岛屿异常，并在章末遇到新的阻碍与钩子。" * 3,
                "narrative_phase": "孤岛求生",
                "chapter_role": "推进生存与异常线索",
                "suspense_hook": "新的异常显露",
                "emotional_progression": "紧张→镇定→不安",
                "character_focus": ["主角"],
                "conflict_escalation": ["资源不足", "环境异常"],
                "continuity_notes": ["承接上一章的生存压力", "为下一章异常升级埋钩子"],
                "foreshadowing": {"plant": ["岛屿非自然"], "payoff": []},
                "metadata": {"pace": "slow_burn"},
            }
        )
    llm = FakeLLMService([
        json.dumps({"chapter_outline": outline_items[:4]}, ensure_ascii=False),
        json.dumps({"chapter_outline": outline_items[4:8]}, ensure_ascii=False),
        json.dumps({"chapter_outline": outline_items[8:12]}, ensure_ascii=False),
    ])

    result = await _generate_executable_chapter_outline(
        llm_service=llm,
        blueprint_data={
            "title": "异海开拓史",
            "one_sentence_summary": "从孤岛生存开始的异海长篇",
            "full_synopsis": "长篇慢热海洋文明故事",
            "world_setting": {
                "core": "海洋文明 + 修炼反馈生态",
                "system_blueprint": {
                    "length_contract": {
                        "target_chapter_count": 12,
                        "stage_count_min": 4,
                        "stage_count_max": 6,
                        "chapter_outline_seed_count": 12,
                    }
                },
            },
            "characters": [{"name": "主角"}],
            "relationships": [],
            "story_arcs": [],
            "volume_plan": [],
            "foreshadowing_system": [],
            "chapter_outline": [],
        },
        user_id=1,
        progress_callback=progress_callback,
    )

    assert stages == [
        ("blueprint_chapter_plan", "正在生成可执行章节大纲（第 1/3 批，第 1-4 章）"),
        ("blueprint_chapter_plan", "正在解析章节大纲批次（第 1-4 章）"),
        ("blueprint_chapter_plan", "正在生成可执行章节大纲（第 2/3 批，第 5-8 章）"),
        ("blueprint_chapter_plan", "正在解析章节大纲批次（第 5-8 章）"),
        ("blueprint_chapter_plan", "正在生成可执行章节大纲（第 3/3 批，第 9-12 章）"),
        ("blueprint_chapter_plan", "正在解析章节大纲批次（第 9-12 章）"),
    ]
    assert len(result["chapter_outline"]) == 12
    assert result["chapter_outline"][0]["title"] == "第1章标题"
    assert len(llm.calls) == 3


@pytest.mark.anyio
async def test_polish_outline_reports_polishing_progress_and_sanitizes_json():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    blueprint = {
        "one_sentence_summary": "一句话梗概",
        "full_synopsis": "长梗概",
        "characters": [],
        "relationships": [],
        "chapter_outline": [
            {
                "chapter_number": chapter_number,
                "title": f"旧标题{chapter_number}",
                "summary": "旧摘要",
            }
            for chapter_number in range(1, 13)
        ],
    }
    long_summary = "冲突推进" * 50
    llm = FakeLLMService([
        "```json\n{\"chapters\":[{\"chapter_number\":1,\"title\":\"新标题\",\"summary\":\""
        + long_summary
        + "\",\"character_focus\":[\"主角\"]},{\"chapter_number\":2,\"title\":\"第2章新标题\",\"summary\":\""
        + long_summary
        + "\",\"character_focus\":[\"主角\"]},{\"chapter_number\":3,\"title\":\"第3章新标题\",\"summary\":\""
        + long_summary
        + "\",\"character_focus\":[\"主角\"]},{\"chapter_number\":4,\"title\":\"第4章新标题\",\"summary\":\""
        + long_summary
        + "\",\"character_focus\":[\"主角\"]}]}\n```",
        "```json\n{\"chapters\":[]}\n```",
        "```json\n{\"chapters\":[]}\n```",
    ])

    result = await _polish_chapter_outline_quality(
        llm_service=llm,
        blueprint_data=blueprint,
        user_id=1,
        progress_callback=progress_callback,
    )

    assert stages == [
        ("blueprint_chapter_plan", "正在润色章节大纲（第 1/3 批，第 1-4 章）"),
        ("blueprint_chapter_plan", "正在解析润色结果（第 1-4 章）"),
        ("blueprint_chapter_plan", "正在润色章节大纲（第 2/3 批，第 5-8 章）"),
        ("blueprint_chapter_plan", "正在解析润色结果（第 5-8 章）"),
        ("blueprint_chapter_plan", "正在润色章节大纲（第 3/3 批，第 9-12 章）"),
        ("blueprint_chapter_plan", "正在解析润色结果（第 9-12 章）"),
    ]
    assert result["chapter_outline"][0]["title"] == "新标题"
    assert result["chapter_outline"][0]["summary"] == long_summary
    assert result["chapter_outline"][1]["title"] == "第2章新标题"
    assert result["chapter_outline"][4]["title"] == "旧标题5"


def test_recoverable_blueprint_schema_requires_core_fields():
    usable = Blueprint(
        title="恢复后的蓝图",
        one_sentence_summary="可用内容",
        chapter_outline=[{"chapter_number": 1, "title": "第1章", "summary": "摘要"}],
        characters=[{"name": "林七"}],
    )
    broken = Blueprint(
        title="",
        one_sentence_summary="只剩残片",
        chapter_outline=[{"chapter_number": 1, "title": "残章", "summary": "残章摘要"}],
        characters=[{"name": "林七"}],
    )

    assert _is_recoverable_blueprint_schema(usable) is True
    assert _is_recoverable_blueprint_schema(broken) is False


@pytest.mark.anyio
async def test_finished_blueprint_job_recovers_from_persisted_project(monkeypatch):
    monkeypatch.setattr("app.api.routers.novels.NovelService", FakeRecoverService)

    recovered = await _recover_finished_blueprint_job_from_project(
        "project-1",
        session=None,
        user_id=1,
        job={
            "run_id": "run-finished",
            "project_id": "project-1",
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "正在生成",
        },
    )

    assert recovered is not None
    assert recovered["status"] == "successful"
    assert recovered["progress_stage"] == "successful"
    assert recovered["error"] is None
    assert recovered["blueprint"].title == "恢复后的蓝图"


@pytest.mark.anyio
async def test_finished_blueprint_job_does_not_recover_broken_project_blueprint(monkeypatch):
    monkeypatch.setattr("app.api.routers.novels.NovelService", FakeBrokenRecoverService)

    recovered = await _recover_finished_blueprint_job_from_project(
        "project-broken",
        session=None,
        user_id=1,
        job={
            "run_id": "run-broken",
            "project_id": "project-broken",
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "正在生成",
        },
    )

    assert recovered is None


@pytest.mark.anyio
async def test_chapter_outline_job_does_not_recover_from_total_outline_only(monkeypatch):
    monkeypatch.setattr("app.api.routers.novels.NovelService", FakePartialRecoverService)

    recovered = await _recover_finished_blueprint_job_from_project(
        "project-partial",
        session=None,
        user_id=1,
        job={
            "run_id": "run-chapter-outline",
            "project_id": "project-partial",
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "正在生成章节大纲",
            "force_stage": "chapter_outline",
        },
    )

    assert recovered is None


@pytest.mark.anyio
async def test_replace_blueprint_serializes_nested_pydantic_models(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'replace_blueprint.db'}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(
                User(
                    id=1,
                    username="tester",
                    email="tester@example.com",
                    hashed_password="hashed",
                )
            )
            session.add(
                NovelProject(
                    id="project-blueprint-1",
                    user_id=1,
                    title="测试项目",
                    initial_prompt="灵感",
                    status="draft",
                )
            )
            await session.commit()

        blueprint = Blueprint(
            title="测试蓝图",
            one_sentence_summary="一句话摘要",
            world_setting={
                "core_rules": "记忆会被潮雾吞没",
                "key_locations": [{"name": "旧档案馆地库"}],
            },
            story_arcs=[{"title": "黑潮账册线", "conflict": "证据不断消失"}],
            novel_outline=[{"title": "第一阶段", "main_conflict": "抢在记忆抹除前留下证据", "expected_chapter_range": "1-260章"}],
            foreshadowing_system=[{"plant": "盐渍编号", "payoff": "渡雾码头旧仓库"}],
            chapter_outline=[
                {
                    "chapter_number": 1,
                    "title": "雾夜来客",
                    "summary": "林七第一次摸到被篡改的残页。",
                    "cast_delta": {"new": ["林七"], "returning": [], "exit_or_absent": [], "faction_roles": []},
                    "foreshadowing_tasks": {"plant": ["盐渍编号"], "reinforce": [], "payoff": [], "avoid_forgetting": []},
                    "payoff_window": "第8-12章",
                }
            ],
        )

        async with session_factory() as session:
            service = NovelService(session)
            await service.replace_blueprint("project-blueprint-1", blueprint)

        async with session_factory() as session:
            record = await session.get(NovelBlueprint, "project-blueprint-1")
            assert isinstance(record.world_setting, dict)
            assert record.world_setting["core_rules"] == "记忆会被潮雾吞没"
            assert record.world_setting["story_arcs"][0]["title"] == "黑潮账册线"
            assert record.world_setting["novel_outline"][0]["title"] == "第一阶段"
            assert record.world_setting["foreshadowing_system"][0]["plant"] == "盐渍编号"

            outline_result = await session.execute(
                select(ChapterOutline).where(
                    ChapterOutline.project_id == "project-blueprint-1",
                    ChapterOutline.chapter_number == 1,
                )
            )
            outline = outline_result.scalars().first()
            assert outline is not None
            assert outline.title == "雾夜来客"
            assert outline.metadata["cast_delta"]["new"] == ["林七"]
            assert outline.metadata["foreshadowing_tasks"]["plant"] == ["盐渍编号"]
            assert outline.metadata["payoff_window"] == "第8-12章"

            character_count = await session.scalar(
                select(func.count(BlueprintCharacter.id)).where(BlueprintCharacter.project_id == "project-blueprint-1")
            )
            assert character_count >= 40

            schema = await NovelService(session).get_project_schema("project-blueprint-1", 1)
            chapter_schema = next(item for item in schema.chapters if item.chapter_number == 1)
            assert chapter_schema.cast_delta["new"] == ["林七"]
            assert chapter_schema.foreshadowing_tasks["plant"] == ["盐渍编号"]
            assert chapter_schema.payoff_window == "第8-12章"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_upsert_and_load_blueprint_job_from_db(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'blueprint_jobs.db'}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(
                User(
                    id=1,
                    username="tester",
                    email="tester@example.com",
                    hashed_password="hashed",
                )
            )
            session.add(
                NovelProject(
                    id="project-db-1",
                    user_id=1,
                    title="测试项目",
                    initial_prompt="灵感",
                    status="draft",
                )
            )
            await session.commit()

        job = {
            "run_id": "run-db-1",
            "project_id": "project-db-1",
            "user_id": 1,
            "status": "successful",
            "progress_stage": "successful",
            "progress_message": "蓝图生成完成",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "blueprint": {"title": "数据库蓝图", "one_sentence_summary": "测试摘要"},
            "ai_message": "蓝图已生成",
            "error": None,
        }

        async with session_factory() as session:
            await _upsert_blueprint_job_record(session, job)

        async with session_factory() as session:
            loaded = await _load_latest_blueprint_job_from_db("project-db-1", session)

        assert loaded is not None
        assert loaded["run_id"] == "run-db-1"
        assert loaded["user_id"] == 1
        assert loaded["status"] == "successful"
        assert loaded["blueprint"]["title"] == "数据库蓝图"
        assert loaded["ai_message"] == "蓝图已生成"
    finally:
        await engine.dispose()


def test_db_blueprint_job_payload_preserves_user_id_and_blueprint():
    now = datetime.now(timezone.utc)
    record = BlueprintGenerationJob(
        run_id="run-db-2",
        project_id="project-db-2",
        user_id=7,
        status="successful",
        progress_stage="successful",
        progress_message="完成",
        started_at=now,
        updated_at=now,
        blueprint_payload={"title": "持久化蓝图", "one_sentence_summary": "摘要"},
        ai_message="已完成",
        error_payload=None,
    )

    payload = _db_blueprint_job_to_payload(record)

    assert payload["user_id"] == 7
    assert payload["blueprint"]["title"] == "持久化蓝图"
    assert payload["ai_message"] == "已完成"


@pytest.mark.anyio
async def test_load_latest_blueprint_job_prefers_db_over_history(monkeypatch):
    db_payload = {"run_id": "db-run", "project_id": "project-1", "status": "successful"}
    history_payload = {"run_id": "history-run", "project_id": "project-1", "status": "failed"}

    async def fake_db_loader(project_id, session):
        return db_payload

    async def fake_history_loader(project_id, session):
        return history_payload

    monkeypatch.setattr("app.api.routers.novels._load_latest_blueprint_job_from_db", fake_db_loader)
    monkeypatch.setattr("app.api.routers.novels._load_latest_blueprint_job_from_history", fake_history_loader)

    loaded = await _load_latest_blueprint_job("project-1", session=None)

    assert loaded == db_payload


@pytest.mark.anyio
async def test_load_latest_blueprint_job_falls_back_to_history_when_db_missing(monkeypatch):
    history_payload = {"run_id": "history-run", "project_id": "project-1", "status": "failed"}

    async def fake_db_loader(project_id, session):
        return None

    async def fake_history_loader(project_id, session):
        return history_payload

    monkeypatch.setattr("app.api.routers.novels._load_latest_blueprint_job_from_db", fake_db_loader)
    monkeypatch.setattr("app.api.routers.novels._load_latest_blueprint_job_from_history", fake_history_loader)

    loaded = await _load_latest_blueprint_job("project-1", session=None)

    assert loaded == history_payload
