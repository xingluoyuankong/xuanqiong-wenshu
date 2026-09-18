"""
US-010: 预算门 —— 超过预算时 allowed_actions = pause

验证 writer.py:_evaluate_budget_gate 的真实行为：
  - 未超预算 -> 放行（返回 None）
  - 已超预算 -> 返回暂停快照，含 allowed_actions=["pause"] 所需字段
  - 预算检查本身出错 -> 放行（不得因预算系统故障阻断生成）
"""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routers.writer import _evaluate_budget_gate  # noqa: E402

pytestmark = pytest.mark.asyncio


class FakeBudgetService:
    """可配置用量百分比的替身。"""

    usage_percent = 0.0
    total_budget = 100.0
    raise_on_stats = False
    alerts = 0

    def __init__(self, session):
        pass

    async def get_usage_stats(self, project_id):
        if FakeBudgetService.raise_on_stats:
            raise RuntimeError("db down")
        return {
            "project_id": project_id,
            "total_budget": FakeBudgetService.total_budget,
            "usage_percent": FakeBudgetService.usage_percent,
            "total_cost": FakeBudgetService.usage_percent,
        }

    async def check_and_create_alert(self, project_id):
        FakeBudgetService.alerts += 1
        return None


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    FakeBudgetService.usage_percent = 0.0
    FakeBudgetService.total_budget = 100.0
    FakeBudgetService.raise_on_stats = False
    FakeBudgetService.alerts = 0
    import app.services.token_budget_service as mod

    monkeypatch.setattr(mod, "TokenBudgetService", FakeBudgetService)
    yield


async def test_under_budget_allows_generation():
    FakeBudgetService.usage_percent = 42.0
    assert await _evaluate_budget_gate(None, "p") is None


async def test_at_threshold_allows_generation():
    """恰好 100% 以下（99.9）应放行 —— 门槛是 100。"""
    FakeBudgetService.usage_percent = 99.9
    assert await _evaluate_budget_gate(None, "p") is None


async def test_over_budget_pauses():
    FakeBudgetService.usage_percent = 150.0
    block = await _evaluate_budget_gate(None, "p")
    assert block is not None
    assert block["budget_exceeded"] is True
    assert block["usage_percent"] == 150.0
    assert block["total_budget"] == 100.0


async def test_over_budget_creates_alert():
    FakeBudgetService.usage_percent = 120.0
    await _evaluate_budget_gate(None, "p")
    assert FakeBudgetService.alerts == 1, "超预算应落一条告警供审计"


async def test_budget_check_failure_does_not_block_generation():
    """预算系统故障必须放行 —— 绝不能因为记账子系统挂掉而停掉写作。"""
    FakeBudgetService.raise_on_stats = True
    assert await _evaluate_budget_gate(None, "p") is None

async def test_unallocated_budget_pauses_generation():
    FakeBudgetService.total_budget = 0.0
    FakeBudgetService.usage_percent = 0.0
    block = await _evaluate_budget_gate(None, "p")
    assert block is not None
    assert block["budget_unallocated"] is True
    assert block["budget_gate_reason"] == "budget_not_allocated"
    assert block["budget_exceeded"] is False
