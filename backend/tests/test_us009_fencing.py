"""
US-009: Worker epoch / fencing 机制验证

背景（诚实陈述）：
  项目里**没有**名为 "epoch" 或 "fencing" 的字段/函数。但等价的 fencing 机制
  确实存在，就是章节生成任务每次分配的唯一 ``run_id``，它充当 fence token：

  - 原子 claim：writer.py:_try_claim_chapter_generation 用条件 UPDATE
    (WHERE status NOT IN busy_statuses) 做 compare-and-swap，只有一个调用者
    能抢到 run_id（rowcount=1），其余得 None -> already_generating。
  - 写入前校验：pipeline_orchestrator.py:_assert_generation_active 在 11 个
    关键节点（生成前/持久化前/候选落库前等）比对 chapter 当前 run_id 与
    本任务的 run_id，不匹配即抛 409 GENERATION_CANCELLED —— 这就是"旧 epoch
    写入被拒绝"。
  - 心跳降级：_record_generation_progress 在 run_id 不匹配时静默 return，
    避免旧任务污染新任务的进度事件。

  此前该机制**零测试覆盖**（grep tests/ 无命中）。本文件补上。

覆盖：
  A. 当前 run_id 匹配 -> 放行
  B. 旧 run_id（epoch 更早）-> 409，拒绝写入
  C. cancel_requested -> 409
  D. 章节状态已非 generating（被 stale 重置/已完成）-> 409
  E. generation_run_id 为 None -> 跳过校验（非生成路径调用）
  F. 心跳：旧 run_id 不写事件（不覆盖新 epoch 状态）

用法：/app/venv/bin/python3 -m pytest tests/test_us009_fencing.py --asyncio-mode=auto
"""

import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator  # noqa: E402

pytestmark = pytest.mark.asyncio

GENERATING = "generating"


class FakeChapter:
    def __init__(self, *, run_id, status=GENERATING, cancel_requested=False, chapter_number=1, content=None):
        runtime = {
            "run_id": run_id,
            "cancel_requested": cancel_requested,
        }
        self.real_summary = json.dumps({"generation_runtime": runtime}, ensure_ascii=False)
        self.status = status
        self.chapter_number = chapter_number
        self.id = 1
        self.content = content


class FakeSession:
    """最小 session：refresh 是 no-op（测试直接操纵 chapter 对象模拟并发写入）。"""

    async def refresh(self, obj, *a, **k):
        return obj

    async def commit(self):
        return None

    async def execute(self, *a, **k):
        raise AssertionError("该测试不应触发 DB 写入")


def orchestrator():
    # 绕过 __init__ 里对 DB session 的强依赖，只装该校验所需属性
    obj = PipelineOrchestrator.__new__(PipelineOrchestrator)
    obj.session = FakeSession()
    return obj


async def assert_active(run_id, *, task_run_id, status=GENERATING, cancel=False):
    ch = FakeChapter(run_id=run_id, status=status, cancel_requested=cancel)
    await orchestrator()._assert_generation_active(ch, generation_run_id=task_run_id, stage="unit_test")
    return ch


async def test_current_run_id_is_allowed():
    """A. 当前 run_id 匹配 -> 放行。"""
    await assert_active("run-A", task_run_id="run-A")


async def test_stale_run_id_is_rejected():
    """B. 旧 epoch（run_id 不匹配）写入必须被拒绝。"""
    with pytest.raises(HTTPException) as e:
        # 章节已属于 run-B（新 epoch），run-A（旧）试图继续写入
        await assert_active("run-B", task_run_id="run-A")
    assert e.value.status_code == 409
    assert e.value.detail["code"] == "GENERATION_CANCELLED"
    assert e.value.detail["retryable"] is False


async def test_cancel_requested_blocks_write():
    """C. 已请求取消 -> 拒绝。"""
    with pytest.raises(HTTPException) as e:
        await assert_active("run-A", task_run_id="run-A", cancel=True)
    assert e.value.status_code == 409


async def test_non_generating_status_blocks_write():
    """D. 章节状态已被重置（如 stale 判定为 failed）-> 拒绝旧任务继续写。"""
    with pytest.raises(HTTPException) as e:
        await assert_active("run-A", task_run_id="run-A", status="failed")
    assert e.value.status_code == 409
    assert e.value.detail["code"] == "GENERATION_CANCELLED"


async def test_missing_run_id_skips_check():
    """E. 非生成路径（无 run_id）跳过校验，不得误伤。"""
    await assert_active("run-A", task_run_id=None)


async def test_heartbeat_does_not_overwrite_new_epoch():
    """F. 旧 run_id 的心跳不得写入事件（否则会污染新任务的进度）。"""
    ch = FakeChapter(run_id="run-B")
    before = ch.real_summary
    await orchestrator()._update_generation_runtime(
        ch,
        generation_run_id="run-A",  # 旧 epoch
        stage="draft",
        progress_percent=50,
        message="旧任务的心跳",
    )
    assert ch.real_summary == before, "旧 epoch 心跳不应修改章节状态"


async def test_heartbeat_of_current_run_is_recorded():
    """F+. 当前 run_id 的心跳正常写入（证明上一条不是因为函数整体失效）。"""
    ch = FakeChapter(run_id="run-A")
    await orchestrator()._update_generation_runtime(
        ch,
        generation_run_id="run-A",
        stage="draft",
        progress_percent=50,
        message="当前任务的心跳",
    )
    payload = json.loads(ch.real_summary)
    events = payload["generation_runtime"]["events"]
    assert any(e["stage"] == "draft" for e in events), "当前 run_id 的心跳应被记录"
