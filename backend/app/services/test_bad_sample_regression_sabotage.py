"""T-07：坏样本回归的可复跑反向验证。

每项先验证当前生产评分结果，再以 monkeypatch 在进程内破坏单一关键链路；
pytest.raises(AssertionError) 证明既有回归断言在实现退化时会失败。
"""

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.test_generation_quality_guards import (
    BAD_FLAT_CHATTER,
    BAD_MUNDANE_SEQUENCE,
    GOOD_DRAMATIC,
)


_SCORE_KWARGS = {
    "violations": [],
    "chapter_mission": None,
    "target_word_count": 2500,
    "min_word_count": 2250,
}


def _score(content: str) -> dict:
    return PipelineOrchestrator._score_story_quality_candidate(content=content, **_SCORE_KWARGS)


def _assert_flat_chatter_density_is_blocked() -> None:
    result = _score(BAD_FLAT_CHATTER)
    assert result["event_density_passed"] is False, f"event_density_passed regression: {result}"
    assert result["state_change_interval_passed"] is False, f"state_change_interval_passed regression: {result}"
    assert "event_density_weak" in set(result["quality_issue_codes"]), result


def _assert_mundane_sequence_ending_is_blocked() -> None:
    result = _score(BAD_MUNDANE_SEQUENCE)
    assert result["ending_pressure_passed"] is False, f"ending_pressure_passed regression: {result}"
    assert "ending_pressure_missing" in set(result["quality_issue_codes"]), result


def _assert_bad_sample_score_gap() -> None:
    good = _score(GOOD_DRAMATIC)
    bad = _score(BAD_FLAT_CHATTER)
    assert good["score"] - bad["score"] >= 600, {"good": good["score"], "bad": bad["score"]}


def _assert_density_metric_reaches_snapshot() -> None:
    result = _score(BAD_FLAT_CHATTER)
    snapshot = result["quality_metric_snapshot"]
    assert snapshot["progression_unit_rate"] == 0.0, f"progression_unit_rate snapshot regression: {snapshot}"
    assert snapshot["event_density_per_1000"] == 0.0, snapshot


def test_t07_bad_density_assertion_detects_runtime_density_sabotage(monkeypatch):
    """把寒暄灌水的密度结果伪造成通过，原有坏样本拦截断言必须失败。"""
    _assert_flat_chatter_density_is_blocked()
    original_evaluate = PipelineOrchestrator._evaluate_event_density

    def falsify_density(cls, text: str, *, word_count: int):
        result = dict(original_evaluate(text, word_count=word_count))
        if text == BAD_FLAT_CHATTER:
            result.update(
                event_density_passed=True,
                state_change_interval_passed=True,
                progression_unit_rate=1.0,
                event_density_per_1000=99.0,
            )
        return result

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_evaluate_event_density",
        classmethod(falsify_density),
    )

    with pytest.raises(AssertionError, match="event_density_passed"):
        _assert_flat_chatter_density_is_blocked()


def test_t07_bad_ending_assertion_detects_runtime_ending_sabotage(monkeypatch):
    """把流水账的平淡收束伪造成有压力，原有章末门断言必须失败。"""
    _assert_mundane_sequence_ending_is_blocked()
    original_evaluate = PipelineOrchestrator._evaluate_ending_pressure

    def falsify_ending(cls, *args, **kwargs):
        result = dict(original_evaluate(*args, **kwargs))
        result["ending_pressure_passed"] = True
        return result

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_evaluate_ending_pressure",
        classmethod(falsify_ending),
    )

    with pytest.raises(AssertionError, match="ending_pressure_passed"):
        _assert_mundane_sequence_ending_is_blocked()


def test_t07_score_gap_assertion_detects_runtime_scoring_sabotage(monkeypatch):
    """抹平正负样本分差后，既有至少 600 分分差断言必须失败。"""
    _assert_bad_sample_score_gap()
    original_score = PipelineOrchestrator._score_story_quality_candidate
    current_gap = _score(GOOD_DRAMATIC)["score"] - _score(BAD_FLAT_CHATTER)["score"]
    # 用动态幅度真正抹平到 600 分以下；固定 +1000 会在评分器新增合法正向项后
    # 失去 sabotage 效果，导致“反向验证”实际上没有破坏任何验收条件。
    sabotage_delta = max(1000, current_gap - 599)

    def inflate_bad_score(cls, *, content: str, **kwargs):
        result = dict(original_score(content=content, **kwargs))
        if content == BAD_FLAT_CHATTER:
            result["score"] += sabotage_delta
        return result

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_score_story_quality_candidate",
        classmethod(inflate_bad_score),
    )

    with pytest.raises(AssertionError, match="good"):
        _assert_bad_sample_score_gap()


def test_t07_snapshot_assertion_detects_runtime_snapshot_sabotage(monkeypatch):
    """破坏快照字段透传后，既有诊断快照断言必须失败。"""
    _assert_density_metric_reaches_snapshot()
    original_score = PipelineOrchestrator._score_story_quality_candidate

    def corrupt_density_snapshot(cls, *, content: str, **kwargs):
        result = dict(original_score(content=content, **kwargs))
        if content == BAD_FLAT_CHATTER:
            snapshot = dict(result["quality_metric_snapshot"])
            snapshot["progression_unit_rate"] = 1.0
            snapshot["event_density_per_1000"] = 99.0
            result["quality_metric_snapshot"] = snapshot
        return result

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_score_story_quality_candidate",
        classmethod(corrupt_density_snapshot),
    )

    with pytest.raises(AssertionError, match="progression_unit_rate"):
        _assert_density_metric_reaches_snapshot()
