"""T-24 helper 采用闭环：只验证已存在的短章/长篇生产链路。"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from app.services.longform_generation_service import (
    build_longform_generation_plan,
    start_longform_checkpoint,
)
from app.services.pipeline_orchestrator import PipelineConfig, PipelineOrchestrator


_ACTIONS = (
    "握紧长剑向前踏出一步",
    "翻手扣住对方腕脉",
    "退开三尺横刀在胸",
    "抬手打散逼近的寒气",
)
_TURNS = (
    "局势因此彻底反转",
    "阵法随之崩开一角",
    "对峙的两人同时变色",
    "被隐瞒的线索浮出水面",
)


def _segment_prose(marker: str, required_words: int) -> str:
    """构造通过长篇服务段落质量门的、彼此不重复的正文。"""
    chunks: list[str] = []
    index = 0
    while PipelineOrchestrator._count_words("".join(chunks)) < required_words:
        index += 1
        chunks.append(
            f"{marker}第{index}回，他{_ACTIONS[index % len(_ACTIONS)]}，问道：\"{marker}今夜究竟谁在撒谎？\""
            f"{marker}对面的人神色骤变，随即抛出一枚旧纹玉符，{_TURNS[index % len(_TURNS)]}{index}。"
        )
    return "".join(chunks)


def _writer_registered_runtime(plan, checkpoint) -> dict:
    return {
        "checkpoint_enabled": True,
        "plan": plan.as_dict(),
        "checkpoint": checkpoint.as_dict(),
    }


def _assert_short_writer_budget_and_error_summary_adoption(source: str) -> None:
    if "max_tokens=self._resolve_writer_prompt_budget(config.target_word_count)" not in source:
        raise AssertionError("正文 prompt 预算必须调用 T-24 writer budget helper")
    if '"writer_prompt_budget_tokens": self._resolve_writer_prompt_budget(config.target_word_count)' not in source:
        raise AssertionError("运行态必须记录实际采用的 writer prompt budget")
    if '"error_summaries": [' not in source or "self._summarize_generation_error(error)" not in source:
        raise AssertionError("候选失败必须保存受限的 generation error summary")


def test_t24_short_generation_helpers_are_wired_to_real_candidate_path():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    _assert_short_writer_budget_and_error_summary_adoption(source)

def test_t24_longform_checkpoint_state_is_consumed_by_generate_chapter():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    longform_source = inspect.getsource(PipelineOrchestrator._generate_longform_version)
    assert "self._restore_longform_execution_state(" in source
    assert "self._generate_longform_version(" in source
    assert "progress_callback=report_generation_call_progress" in source
    assert "progress_callback=progress_callback" in longform_source
    sabotaged = source.replace("self._generate_longform_version(", "self._generate_single_version(", 1)
    with pytest.raises(AssertionError):
        assert "self._generate_longform_version(" in sabotaged


def test_t24_short_generation_helper_contract_rejects_removed_adoption():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    sabotaged = source.replace(
        "max_tokens=self._resolve_writer_prompt_budget(config.target_word_count)",
        "max_tokens=6000",
        1,
    ).replace(
        "self._summarize_generation_error(error)",
        "str(error)",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_short_writer_budget_and_error_summary_adoption(sabotaged)


def test_t24_restores_only_router_registered_longform_plan_and_checkpoint():
    plan = build_longform_generation_plan(
        project_id="project-t24",
        chapter_number=8,
        target_word_count=20000,
        min_word_count=18000,
        segment_word_limit=4500,
    )
    checkpoint = start_longform_checkpoint(plan)

    restored = PipelineOrchestrator._restore_longform_execution_state(
        flow_config={"longform_runtime": _writer_registered_runtime(plan, checkpoint)},
        project_id="project-t24",
        chapter_number=8,
        target_word_count=20000,
    )

    assert restored is not None
    restored_plan, restored_checkpoint = restored
    assert restored_plan.plan_key == plan.plan_key
    assert restored_checkpoint.next_segment_index == 0

    with pytest.raises(HTTPException) as excinfo:
        PipelineOrchestrator._restore_longform_execution_state(
            flow_config={"longform_runtime": _writer_registered_runtime(plan, checkpoint)},
            project_id="other-project",
            chapter_number=8,
            target_word_count=20000,
        )
    assert excinfo.value.detail["code"] == "LONGFORM_RUNTIME_MISMATCH"


@pytest.mark.asyncio
async def test_t24_longform_generation_persists_each_accepted_segment_and_replays_checkpoint_delta(monkeypatch):
    plan = build_longform_generation_plan(
        project_id="project-t24",
        chapter_number=8,
        target_word_count=1200,
        min_word_count=1000,
        segment_word_limit=600,
    )
    checkpoint = start_longform_checkpoint(plan)
    orchestrator = object.__new__(PipelineOrchestrator)
    generated_indices: list[int] = []
    persisted_indexes: list[int] = []
    extracted_indexes: list[int] = []
    runtime_events: list[dict] = []
    provider_progress: list[tuple[str, str]] = []

    async def fake_generate_single_version(**kwargs):
        index = int(kwargs["index"])
        generated_indices.append(index)
        callback = kwargs.get("progress_callback")
        if callback is not None:
            await callback("generate_variants", f"segment {index} waiting")
        segment = plan.segments[index]
        return {
            "content": _segment_prose(f"SEG{index}", segment.min_words + 360),
            "metadata": {"timings": {"total_tokens": 17}},
        }

    async def fake_persist(**kwargs):
        persisted_indexes.append(kwargs["next_checkpoint"].next_segment_index)

    async def fake_runtime(*_args, **kwargs):
        runtime_events.append(kwargs)

    async def fake_progress(stage: str, message: str):
        provider_progress.append((stage, message))

    async def fake_active(*_args, **_kwargs):
        return None

    original_extract = PipelineOrchestrator._extract_segment_text

    def track_extract(snapshot, index):
        extracted_indexes.append(index)
        return original_extract(snapshot, index)

    monkeypatch.setattr(orchestrator, "_generate_single_version", fake_generate_single_version)
    monkeypatch.setattr(orchestrator, "_persist_longform_checkpoint", fake_persist)
    monkeypatch.setattr(orchestrator, "_update_generation_runtime", fake_runtime)
    monkeypatch.setattr(orchestrator, "_assert_generation_active", fake_active)
    monkeypatch.setattr(orchestrator, "_extract_segment_text", track_extract)

    runtime: dict = {}
    result = await orchestrator._generate_longform_version(
        plan=plan,
        checkpoint=checkpoint,
        runtime_metadata=runtime,
        generation_run_id="run-t24",
        chapter=object(),
        prompt_input="[章节任务] 承接上一章的密室对峙。",
        writer_prompt="只写小说正文。",
        project_id="project-t24",
        chapter_number=8,
        outline_title="断页",
        outline_summary="主角必须揭开玉符来历。",
        chapter_mission={"scene_list": []},
        forbidden_characters=[],
        allowed_new_characters=[],
        user_id=1,
        writer_blueprint={},
        memory_context=None,
        analysis_guidance_context=None,
        enhanced_context=None,
        config=PipelineConfig(target_word_count=1200, min_word_count=1000, version_count=1),
        progress_callback=fake_progress,
    )

    assert generated_indices == [0, 1]
    assert provider_progress == [
        ("generate_variants", "segment 0 waiting"),
        ("generate_variants", "segment 1 waiting"),
    ]
    assert persisted_indexes == [1, 2], "每个已接受段必须先持久化，才能继续下一段"
    assert extracted_indexes == [0, 1], "运行态增量必须由持久化 checkpoint 重建"
    assert result["content"].startswith("SEG0")
    assert "SEG1" in result["content"]
    assert runtime["longform_generation"]["checkpoint"]["next_segment_index"] == 2
    assert [event["stage"] for event in runtime_events] == ["longform_segment", "longform_segment"]
    assert [event["event_kind"] for event in runtime_events] == ["content_delta", "content_delta"]
    assert [event["extra"]["segment_index"] for event in runtime_events] == [0, 1]
    assert all(event["content_delta"] for event in runtime_events)


@pytest.mark.asyncio
async def test_t24_longform_stops_before_next_segment_when_checkpoint_persistence_fails(monkeypatch):
    plan = build_longform_generation_plan(
        project_id="project-t24",
        chapter_number=8,
        target_word_count=1200,
        min_word_count=1000,
        segment_word_limit=600,
    )
    orchestrator = object.__new__(PipelineOrchestrator)
    generated_indices: list[int] = []

    async def fake_generate_single_version(**kwargs):
        index = int(kwargs["index"])
        generated_indices.append(index)
        segment = plan.segments[index]
        return {"content": _segment_prose(f"SEG{index}", segment.min_words + 360), "metadata": {}}

    async def persist_failure(**_kwargs):
        raise HTTPException(
            status_code=503,
            detail={"code": "LONGFORM_CHECKPOINT_PERSISTENCE_FAILED"},
        )

    async def fake_runtime(*_args, **_kwargs):
        return None

    async def fake_active(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_generate_single_version", fake_generate_single_version)
    monkeypatch.setattr(orchestrator, "_persist_longform_checkpoint", persist_failure)
    monkeypatch.setattr(orchestrator, "_update_generation_runtime", fake_runtime)
    monkeypatch.setattr(orchestrator, "_assert_generation_active", fake_active)

    with pytest.raises(HTTPException) as excinfo:
        await orchestrator._generate_longform_version(
            plan=plan,
            checkpoint=start_longform_checkpoint(plan),
            runtime_metadata={},
            generation_run_id="run-t24",
            chapter=object(),
            prompt_input="[章节任务]",
            writer_prompt="只写小说正文。",
            project_id="project-t24",
            chapter_number=8,
            outline_title="断页",
            outline_summary="主角必须揭开玉符来历。",
            chapter_mission={"scene_list": []},
            forbidden_characters=[],
            allowed_new_characters=[],
            user_id=1,
            writer_blueprint={},
            memory_context=None,
            analysis_guidance_context=None,
            enhanced_context=None,
            config=PipelineConfig(target_word_count=1200, min_word_count=1000, version_count=1),
        )

    assert excinfo.value.detail["code"] == "LONGFORM_CHECKPOINT_PERSISTENCE_FAILED"
    assert generated_indices == [0], "断点未落盘时，生产流程不得开始下一段"


def test_t24_real_longform_smoke_uses_backend_normalized_timeout():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "real_asgi_longform_generation_smoke.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = []
    wanted_assignments = {"SMOKE_MIN_TIMEOUT_SECONDS", "SMOKE_MAX_TIMEOUT_SECONDS"}
    wanted_functions = {"_coerce_timeout_seconds", "_resolve_smoke_timeout_seconds"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted_assignments
            for target in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            selected.append(node)
    namespace = {"Any": Any}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "longform_smoke_helpers", "exec"), namespace)
    resolve = namespace["_resolve_smoke_timeout_seconds"]

    assert resolve({"generation_runtime": {"timeout_seconds": 3300}}, 0) == 3300
    assert resolve({}, 0) == 4 * 60 * 60
    assert resolve({"generation_runtime": {"timeout_seconds": 3300}}, 1800) == 1800


def test_t24_real_longform_smoke_uses_one_explicit_timeout_budget():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "real_asgi_longform_generation_smoke.py").read_text(encoding="utf-8")
    assert "LONGFORM_SMOKE_TIMEOUT_SECONDS" in source
    assert '"generation_timeout_seconds": requested_timeout_seconds' in source
    assert "time.monotonic() + smoke_timeout_seconds" in source
