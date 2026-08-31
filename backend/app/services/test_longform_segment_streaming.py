"""长篇分段生成必须把每段正文作为 content_delta 真正流出，且不重复推送整章。"""
from __future__ import annotations

import re

import pytest

from app.services.longform_generation_service import (
    LongformCheckpoint,
    LongformGenerationCancelled,
    append_segment,
    build_longform_generation_plan,
    execute_longform_segments,
    restore_longform_generation_plan,
    start_longform_checkpoint,
)
from app.services.pipeline_orchestrator import PipelineOrchestrator


def _plan(target: int = 9000, limit: int = 3000):
    return build_longform_generation_plan(
        project_id="p-stream",
        chapter_number=1,
        target_word_count=target,
        segment_word_limit=limit,
    )


_ACTIONS = (
    "握紧长剑向前踏出一步",
    "翻手扣住对方腕脉",
    "退开三尺横刀在胸",
    "抬手打散逼近的寒气",
    "低头避过当胸一击",
    "掌心结印压住阵纹",
    "抢步夺下悬空的令牌",
)
_TURNS = (
    "局势因此彻底反转",
    "阵法随之崩开一角",
    "对峙的两人同时变色",
    "远处传来第三方脚步",
    "旧盟约在此刻作废",
    "被隐瞒的线索浮出水面",
    "谁也没料到会是这个结果",
)


def _measure(text: str) -> int:
    """与生产实现同源的字数口径：统计中文字与连续英数串。"""
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", text))


def _segment_body(marker: str, words: int) -> str:
    """构造能通过段落质量门的正文：字数达标、句子互不重复、含对话与动作。"""
    parts: list[str] = []
    idx = 0
    while _measure("".join(parts)) < words:
        idx += 1
        action = _ACTIONS[idx % len(_ACTIONS)]
        turn = _TURNS[(idx * 3) % len(_TURNS)]
        parts.append(
            # 每个句子都必须带 marker：切句符号是。！？；，若某句缺少 marker，
            # 不同段落在相同 idx 上会生成完全相同的句子，触发 duplicate_content 段落门。
            f"{marker}第{idx}节，他{action}，问道：“{marker}你究竟想要什么，为何偏偏是今夜{idx}？”"
            f"{marker}对面的人后退半步，神色骤变，随即抛出一枚刻着旧纹的玉符，{turn}{idx}。"
        )
    return "".join(parts)


def test_extract_segment_text_returns_only_last_segment():
    plan = _plan()
    checkpoint = start_longform_checkpoint(plan)
    first = _segment_body("甲", plan.segments[0].min_words + 50)
    checkpoint, _ = append_segment(
        checkpoint, plan, segment_index=0, content=first, token_usage=10
    )
    second = _segment_body("乙", plan.segments[1].min_words + 50)
    checkpoint, _ = append_segment(
        checkpoint, plan, segment_index=1, content=second, token_usage=10
    )

    tail = PipelineOrchestrator._extract_segment_text(checkpoint, 1)

    assert tail.startswith("乙")
    assert "甲" not in tail, "第二段的 delta 不能夹带第一段正文，否则前端会重复显示"
    head = PipelineOrchestrator._extract_segment_text(checkpoint, 0)
    assert head.startswith("甲")
    assert "乙" not in head


def test_char_count_recorded_for_each_segment():
    """char_count 是精确切段的前提，缺失会导致 delta 错位。"""
    plan = _plan()
    checkpoint = start_longform_checkpoint(plan)
    body = _segment_body("甲", plan.segments[0].min_words + 50)
    checkpoint, _ = append_segment(
        checkpoint, plan, segment_index=0, content=body, token_usage=5
    )

    record = checkpoint.completed_segments[0]
    assert record["char_count"] == len(body.strip())


def test_extract_middle_segment_does_not_leak_neighbors():
    """中间段必须按累计偏移定位；只切尾段会在各段等长时串段。"""
    plan = _plan()
    checkpoint = start_longform_checkpoint(plan)
    for index, marker in enumerate(("甲", "乙", "丙")):
        body = _segment_body(marker, plan.segments[index].min_words + 50)
        checkpoint, _ = append_segment(
            checkpoint, plan, segment_index=index, content=body, token_usage=3
        )

    for index, marker in enumerate(("甲", "乙", "丙")):
        chunk = PipelineOrchestrator._extract_segment_text(checkpoint, index)
        assert chunk.startswith(marker)
        for other in {"甲", "乙", "丙"} - {marker}:
            assert other not in chunk, f"第{index}段 delta 夹带了 {other} 段正文"


def test_extract_segment_text_falls_back_without_char_count():
    """旧快照没有 char_count 时仍要能切出末段，不能返回空。"""
    plan = _plan()
    checkpoint = start_longform_checkpoint(plan)
    body = _segment_body("甲", plan.segments[0].min_words + 50)
    checkpoint, _ = append_segment(
        checkpoint, plan, segment_index=0, content=body, token_usage=5
    )
    checkpoint.completed_segments[0].pop("char_count", None)

    tail = PipelineOrchestrator._extract_segment_text(checkpoint, 0)

    assert tail.startswith("甲")


def test_extract_segment_text_empty_snapshot():
    plan = _plan()
    checkpoint = start_longform_checkpoint(plan)
    assert PipelineOrchestrator._extract_segment_text(checkpoint, 0) == ""


def test_resumed_checkpoint_reconstructs_segment_text():
    """重启恢复后从序列化快照仍能还原段正文，保证断线续接不丢正文。"""
    plan = _plan()
    checkpoint = start_longform_checkpoint(plan)
    body = _segment_body("甲", plan.segments[0].min_words + 50)
    checkpoint, _ = append_segment(
        checkpoint, plan, segment_index=0, content=body, token_usage=7
    )

    restored_plan = restore_longform_generation_plan(plan.as_dict())
    restored = LongformCheckpoint.from_dict(checkpoint.as_dict(), restored_plan)

    assert PipelineOrchestrator._extract_segment_text(restored, 0).startswith("甲")
@pytest.mark.asyncio
async def test_executor_streams_content_delta_in_order_and_resume_does_not_repeat():
    """服务层 content_delta 契约：按段串行流出、断点续跑只流新段、整段内容不重复。"""
    plan = _plan(target=1500, limit=600)  # 3 段
    stored: list[dict] = []
    deltas: list[tuple[int, str]] = []
    resume_deltas: list[tuple[int, str]] = []
    cancel = {"value": False}
    calls: list[int] = []

    def body(index: int) -> str:
        return _segment_body(chr(ord("甲") + index), plan.segments[index].min_words + 80)

    async def generate(segment, _snapshot, _attempt):
        calls.append(segment.index)
        return {"content": body(segment.index), "token_usage": 2}

    async def store(checkpoint):
        stored.append(checkpoint.as_dict())

    async def on_delta(index, text, _snapshot):
        deltas.append((index, text))
        if index == 1:
            cancel["value"] = True

    with pytest.raises(LongformGenerationCancelled):
        await execute_longform_segments(
            plan,
            generate_segment=generate,
            checkpoint_store=store,
            content_delta_callback=on_delta,
            cancel_check=lambda: cancel["value"],
            max_attempts=1,
        )

    assert calls == [0, 1], "取消后不得继续生成下一段"
    assert [index for index, _ in deltas] == [0, 1], "content_delta 必须按段序号顺序输出"
    assert "\n\n".join(text for _, text in deltas) == stored[-1]["assembled_text"]
    assert stored[-1]["next_segment_index"] == 2

    # 模拟进程重启：仅凭持久化 payload 恢复计划与断点后继续。
    payload = {
        "plan": plan.as_dict(),
        "plan_key": plan.plan_key,
        "checkpoint": stored[-1],
        "next_segment_index": stored[-1]["next_segment_index"],
        "segment_count": len(plan.segments),
    }
    restored_plan = restore_longform_generation_plan(payload["plan"])
    restored = LongformCheckpoint.from_dict(payload["checkpoint"], restored_plan)

    async def on_resume_delta(index, text, _snapshot):
        resume_deltas.append((index, text))

    final = await execute_longform_segments(
        restored_plan,
        generate_segment=generate,
        checkpoint=restored,
        checkpoint_store=store,
        content_delta_callback=on_resume_delta,
        cancel_check=lambda: False,
        max_attempts=1,
    )

    assert calls == [0, 1, 2], "恢复续跑不得重生成已确认段"
    assert [index for index, _ in resume_deltas] == [2], "只应流出尚未确认的第 3 段"
    all_deltas = [*deltas, *resume_deltas]
    assert [index for index, _ in all_deltas] == [0, 1, 2]
    assert "\n\n".join(text for _, text in all_deltas) == final.assembled_text
    texts = [text for _, text in all_deltas]
    assert len(set(texts)) == len(texts), "任何段正文不得重复输出"
    assert restored_plan.plan_key == plan.plan_key
    assert final.completed_segments[-1]["fingerprint"]

