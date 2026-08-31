"""T-06：事件密度校准的可复跑反向验证。

这些测试先断言当前校准对正向锚点有效，再只在运行时收紧阈值或破坏窗口命中，
并确认同一断言会抛出 AssertionError。不得通过修改生产源码制造反向结果。
"""

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.test_generation_quality_guards import GOOD_DRAMATIC


def _word_count(content: str) -> int:
    return len("".join(content.split()))


def _assert_positive_density_anchor() -> None:
    result = PipelineOrchestrator._evaluate_event_density(
        GOOD_DRAMATIC,
        word_count=_word_count(GOOD_DRAMATIC),
    )

    assert result["event_density_evaluated"] is True
    assert result["event_density_passed"] is True, f"event_density_passed regression: {result}"
    assert result["state_change_interval_passed"] is True, f"state_change_interval_passed regression: {result}"
    assert result["progression_unit_rate"] > 0
    assert result["event_density_per_1000"] > 0


def test_t06_density_anchor_detects_runtime_floor_sabotage(monkeypatch):
    """收紧已校准阈值后，正向锚点的既有「密度通过」断言必须明确变红。"""
    _assert_positive_density_anchor()

    original_floors = PipelineOrchestrator._event_density_floors

    def impossible_floors(cls, word_count: int):
        floors = dict(original_floors(word_count))
        # 正向样本当前密度约 19/千字；20.0 是故意不可接受的运行时篡改值。
        floors["density_floor"] = 20.0
        return floors

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_event_density_floors",
        classmethod(impossible_floors),
    )

    with pytest.raises(AssertionError, match="event_density_passed"):
        _assert_positive_density_anchor()


def test_t06_density_anchor_detects_runtime_window_sabotage(monkeypatch):
    """把窗口状态变化判定篡改为永不命中后，既有窗口通过断言必须明确变红。"""
    _assert_positive_density_anchor()

    def no_window_can_hit(cls, _window: str) -> bool:
        return False

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_window_has_state_change",
        classmethod(no_window_can_hit),
    )

    with pytest.raises(AssertionError, match="state_change_interval_passed"):
        _assert_positive_density_anchor()
