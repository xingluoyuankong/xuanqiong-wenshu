from __future__ import annotations

import pytest

from app.services.longform_generation_service import (
    LongformGenerationContractError,
    append_segment,
    build_longform_generation_plan,
    execute_longform_segments,
    evaluate_chapter_quality,
    evaluate_segment_quality,
    restore_longform_generation_plan,
    start_longform_checkpoint,
    LongformGenerationCancelled,
)


def _plan():
    return build_longform_generation_plan(
        project_id="project-longform",
        chapter_number=12,
        target_word_count=20000,
        min_word_count=18000,
        segment_word_limit=4500,
        blueprint={
            "title": "潮印迷城",
            "world_setting": {"rule": "潮汐会改变旧城门的位置"},
            "novel_outline": [{"title": "全书主线"}],
            "long_term_threads": ["盐痕账册"],
            "volume_plan": [
                {"title": "远航卷", "chapter_range": "1-30章", "plot_arc": "从追查到账册反噬"},
            ],
        },
        chapter_outline={
            "title": "账册显影",
            "summary": "林七必须确认盐痕账册的来源。",
            "goals": ["确认来源", "让沈舟改变立场"],
            "continuity_anchor": "林七仍在旧档案馆",
        },
    )


def test_plan_covers_book_volume_chapter_paragraph_and_exact_budget():
    plan = _plan()

    assert len(plan.segments) == 5
    assert sum(segment.target_words for segment in plan.segments) == 20000
    assert sum(segment.min_words for segment in plan.segments) == 18000
    assert plan.book_context["title"] == "潮印迷城"
    assert plan.volume_context["title"] == "远航卷"
    assert plan.chapter_context["title"] == "账册显影"
    assert plan.segments[0].context_scope == ("book", "volume", "chapter", "paragraph")
    assert plan.plan_key


def test_checkpoint_serialization_resumes_in_order_and_tracks_budget():
    plan = build_longform_generation_plan(
        project_id="p-1", chapter_number=1, target_word_count=1000, min_word_count=8, segment_word_limit=500
    )
    checkpoint = start_longform_checkpoint(plan)
    checkpoint, gate = append_segment(
        checkpoint,
        plan,
        segment_index=0,
        content="林七推开旧档案馆的门，盐痕账册在灰尘里露出半角。沈舟没有阻止他。",
        token_usage=120,
        required_terms=["盐痕账册"],
    )

    restored = type(checkpoint).from_dict(checkpoint.as_dict(), plan)
    assert gate.passed
    assert restored.next_segment_index == 1
    assert restored.used_words == checkpoint.used_words
    assert restored.total_tokens == 120
    assert restored.completed_segments[0]["fingerprint"]


def test_checkpoint_restore_rejects_inconsistent_completed_segments():
    plan = build_longform_generation_plan(
        project_id="p-checkpoint", chapter_number=1, target_word_count=1000, min_word_count=1, segment_word_limit=500
    )
    checkpoint = start_longform_checkpoint(plan)
    checkpoint, _ = append_segment(
        checkpoint, plan, segment_index=0, content="林七确认盐痕账册仍在手中。沈舟在门外等候。", token_usage=3
    )
    tampered = checkpoint.as_dict()
    tampered["next_segment_index"] = 2
    with pytest.raises(LongformGenerationContractError, match="完成段数量"):
        type(checkpoint).from_dict(tampered, plan)

    tampered = checkpoint.as_dict()
    tampered["used_words"] += 1
    with pytest.raises(LongformGenerationContractError, match="累计用量"):
        type(checkpoint).from_dict(tampered, plan)


def test_segment_gate_rejects_short_duplicate_and_missing_anchor():
    gate = evaluate_segment_quality(
        "林七回到旧档案馆。",
        target_word_count=100,
        min_word_count=10,
        prior_content="林七回到旧档案馆。",
        required_terms=["盐痕账册"],
    )

    assert not gate.passed
    assert {item["code"] for item in gate.blockers} == {
        "segment_below_minimum",
        "duplicate_segment",
        "required_anchor_missing",
    }


def test_checkpoint_does_not_allow_skipping_segment():
    plan = build_longform_generation_plan(
        project_id="p-2", chapter_number=2, target_word_count=900, min_word_count=1, segment_word_limit=500
    )
    with pytest.raises(LongformGenerationContractError, match="按顺序"):
        append_segment(start_longform_checkpoint(plan), plan, segment_index=1, content="足够长的第一段正文。")


def test_chapter_gate_rejects_repetition_and_accepts_minimum_content():
    plan = build_longform_generation_plan(
        project_id="p-3", chapter_number=3, target_word_count=100, min_word_count=8, segment_word_limit=500
    )
    repeated = "林七看向旧门。林七看向旧门。林七看向旧门。"
    failed = evaluate_chapter_quality(plan, repeated, required_terms=["盐痕账册"])
    passed = evaluate_chapter_quality(
        plan,
        "林七拿起盐痕账册，沈舟终于说出旧门的位置。两人决定在潮汐前赶往码头。",
        required_terms=["盐痕账册"],
    )

    assert not failed.passed
    assert any(item["code"] == "chapter_duplicate_content" for item in failed.blockers)
    assert not passed.blockers
    assert passed.passed

@pytest.mark.anyio
async def test_segment_executor_persists_checkpoint_and_resumes_after_cancel():
    plan = build_longform_generation_plan(
        project_id="p-executor", chapter_number=4, target_word_count=1000, min_word_count=700, segment_word_limit=500
    )
    stored = []
    cancel = {"value": False}
    calls = []

    def make_content(index: int) -> str:
        return "".join(
            f"林七在第{index}段推进了新的线索和行动，沈舟记录下编号{i}。\n"
            for i in range(180)
        )

    async def generate(segment, _checkpoint, attempt):
        calls.append((segment.index, attempt))
        return {"content": make_content(segment.index), "token_usage": 12}

    async def store(checkpoint):
        stored.append(checkpoint.as_dict())

    async def progress(done, _total, _checkpoint):
        if done == 1:
            cancel["value"] = True

    with pytest.raises(LongformGenerationCancelled):
        await execute_longform_segments(
            plan, generate_segment=generate, checkpoint_store=store, cancel_check=lambda: cancel["value"],
            progress_callback=progress, max_attempts=1
        )

    assert stored and stored[-1]["next_segment_index"] == 1
    assert calls == [(0, 1)]

    cancel["value"] = False
    restored = type(start_longform_checkpoint(plan)).from_dict(stored[-1], plan)
    resumed = await execute_longform_segments(
        plan, generate_segment=generate, checkpoint=restored, checkpoint_store=store,
        cancel_check=lambda: cancel["value"], max_attempts=1
    )
    assert resumed.next_segment_index == len(plan.segments)
    assert [item[0] for item in calls] == [0, 1]
    assert resumed.total_tokens == 24


def test_longform_plan_round_trip_rejects_tampering():
    plan = _plan()
    restored = restore_longform_generation_plan(plan.as_dict())
    assert restored.plan_key == plan.plan_key
    tampered = plan.as_dict()
    tampered["segments"][0]["target_words"] += 1
    with pytest.raises(LongformGenerationContractError, match="校验和"):
        restore_longform_generation_plan(tampered)


def _segment_prose(segment_index: int, target_words: int) -> str:
    """生成一段可通过质量门的正文：足量中文字数、句子不重复、含连续性锚点。"""
    lines: list[str] = []
    produced = 0
    counter = 0
    while produced < target_words:
        counter += 1
        line = (
            f"林七在旧档案馆第{segment_index}段第{counter}处翻检盐痕账册，"
            f"沈舟核对第{segment_index}-{counter}号编号后改口指认新的来源。"
        )
        lines.append(line)
        produced += _measure_chinese_words(line)
    return "\n".join(lines)


def _measure_chinese_words(text: str) -> int:
    return len([ch for ch in text if "\u4e00" <= ch <= "\u9fff"])


@pytest.mark.anyio
async def test_twenty_thousand_word_chapter_generates_by_segments_and_resumes_after_restart():
    """单章 2 万字必须靠分段产出，并能在中断后从断点续跑到达标。

    覆盖目标硬要求：不允许依赖单次超长请求；每段有字数预算与断点快照；
    进程中断后可从 checkpoint 恢复并最终满足整章字数门。
    """
    plan = _plan()
    assert len(plan.segments) == 5
    assert sum(s.target_words for s in plan.segments) == 20000
    # 任何单段预算都必须远小于整章目标，证明不是单次超长请求。
    assert max(s.target_words for s in plan.segments) <= 4500

    stored: list[dict] = []
    calls: list[int] = []
    interrupt = {"value": False}

    async def generate(segment, _checkpoint, _attempt):
        calls.append(segment.index)
        content = _segment_prose(segment.index, segment.target_words)
        assert _measure_chinese_words(content) >= segment.min_words
        return {"content": content, "token_usage": 100}

    async def store(checkpoint):
        stored.append(checkpoint.as_dict())

    async def progress(done, _total, _checkpoint):
        # 模拟第 2 段完成后进程被打断。
        if done == 2:
            interrupt["value"] = True

    with pytest.raises(LongformGenerationCancelled):
        await execute_longform_segments(
            plan,
            generate_segment=generate,
            checkpoint_store=store,
            cancel_check=lambda: interrupt["value"],
            progress_callback=progress,
            max_attempts=2,
        )

    # 断点必须记录已完成 2 段，且已累积部分正文。
    assert stored[-1]["next_segment_index"] == 2
    partial_words = _measure_chinese_words(stored[-1].get("assembled_text") or "")
    assert 0 < partial_words < 20000
    assert calls == [0, 1]

    # 模拟重启：仅凭持久化快照恢复，继续跑完剩余段。
    interrupt["value"] = False
    restored_plan = restore_longform_generation_plan(plan.as_dict())
    restored_ckpt = type(start_longform_checkpoint(restored_plan)).from_dict(stored[-1], restored_plan)
    final = await execute_longform_segments(
        restored_plan,
        generate_segment=generate,
        checkpoint=restored_ckpt,
        checkpoint_store=store,
        cancel_check=lambda: False,
        max_attempts=2,
    )

    assert final.next_segment_index == len(restored_plan.segments)
    # 恢复不得重复已完成段：整体只应产出 5 段。
    assert calls == [0, 1, 2, 3, 4]
    assert len(final.completed_segments) == 5

    total_words = _measure_chinese_words(final.assembled_text or "")
    assert total_words >= 20000, f"整章仅 {total_words} 字，未达 2 万字硬目标"

    gate = evaluate_chapter_quality(restored_plan, final.assembled_text or "")
    assert gate.passed, gate.issues



@pytest.mark.anyio
async def test_longform_checkpoint_persistence_failure_stops_pipeline(monkeypatch):
    """checkpoint 落库失败必须返回可识别错误，不能伪造完成或继续下一段。"""
    from unittest.mock import AsyncMock
    from fastapi import HTTPException
    from app.services import pipeline_orchestrator as pipeline_module
    from app.services.pipeline_orchestrator import PipelineOrchestrator

    plan = build_longform_generation_plan(
        project_id="p-checkpoint-failure",
        chapter_number=8,
        target_word_count=1000,
        min_word_count=700,
        segment_word_limit=500,
    )
    checkpoint = start_longform_checkpoint(plan)
    content = _segment_prose(0, plan.segments[0].target_words)
    checkpoint, gate = append_segment(
        checkpoint,
        plan,
        segment_index=0,
        content=content,
        token_usage=11,
    )
    assert gate.passed

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.session = AsyncMock()
    orchestrator._safe_session_rollback = AsyncMock()
    merge_calls = []

    class _FailingRuntime:
        def __init__(self, _session):
            pass

        async def merge_payload(self, *args, **kwargs):
            merge_calls.append((args, kwargs))
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(pipeline_module, "TaskRuntimeService", _FailingRuntime)

    with pytest.raises(HTTPException) as caught:
        await orchestrator._persist_longform_checkpoint(
            runtime={"generation_mode": "longform"},
            plan=plan,
            next_checkpoint=checkpoint,
            generation_run_id="run-checkpoint-failure",
            user_id=42,
        )

    assert caught.value.status_code == 503
    assert caught.value.detail == {
        "code": "LONGFORM_CHECKPOINT_PERSISTENCE_FAILED",
        "message": "长篇生成断点保存失败，已停止继续生成；请重试恢复任务。",
        "retryable": True,
        "stage": "checkpoint_persistence",
        "segment_index": 1,
    }
    assert len(merge_calls) == 1
    orchestrator._safe_session_rollback.assert_awaited_once_with("longform_checkpoint")

    generated_segments = []

    async def generate_segment(segment, _checkpoint, _attempt):
        generated_segments.append(segment.index)
        return {"content": _segment_prose(segment.index, segment.target_words), "token_usage": 1}

    async def failed_store(_checkpoint):
        raise caught.value

    with pytest.raises(HTTPException) as execution_error:
        await execute_longform_segments(
            plan,
            generate_segment=generate_segment,
            checkpoint_store=failed_store,
            max_attempts=1,
        )

    assert execution_error.value.detail["code"] == "LONGFORM_CHECKPOINT_PERSISTENCE_FAILED"
    assert generated_segments == [0], "checkpoint 失败后不得生成后续分段"
@pytest.mark.anyio
async def test_cancel_before_first_segment_runs_no_generation_and_resume_completes():
    """每段开启前的持久化取消检查：取消状态从首段就成立时不得发起任何段调用。"""
    plan = build_longform_generation_plan(
        project_id="p-cancel-first", chapter_number=9, target_word_count=1000, min_word_count=700, segment_word_limit=500
    )
    calls: list[int] = []
    cancel = {"value": True}

    async def generate(segment, _snapshot, _attempt):
        calls.append(segment.index)
        return {"content": _segment_prose(segment.index, segment.target_words), "token_usage": 1}

    async def store(_checkpoint):
        pass

    with pytest.raises(LongformGenerationCancelled):
        await execute_longform_segments(
            plan,
            generate_segment=generate,
            checkpoint_store=store,
            cancel_check=lambda: cancel["value"],
            max_attempts=1,
        )
    assert calls == [], "取消状态下不得开始任何段的 LLM 调用"

    cancel["value"] = False
    final = await execute_longform_segments(
        plan,
        generate_segment=generate,
        checkpoint_store=store,
        cancel_check=lambda: cancel["value"],
        max_attempts=1,
    )
    assert calls == [0, 1], "恢复后应从第 0 段完整跑完，不跳过任何段"
    assert final.next_segment_index == len(plan.segments)

