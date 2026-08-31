import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.test_generation_quality_guards import BAD_FLAT_CHATTER, BAD_FLAT_CLOSURE, GOOD_DRAMATIC


def _score(content):
    return PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=None,
        target_word_count=2500,
        min_word_count=2250,
    )


def _patch_evaluator(monkeypatch, name, updates):
    original = getattr(PipelineOrchestrator, name)

    def patched(cls, *args, **kwargs):
        result = dict(original(*args, **kwargs))
        result.update(updates)
        return result

    monkeypatch.setattr(PipelineOrchestrator, name, classmethod(patched))


def test_t16_bad_sample_gap_has_numeric_components_across_at_least_three_dimensions(monkeypatch):
    good = _score(GOOD_DRAMATIC)
    bad = _score(BAD_FLAT_CHATTER)
    quality_gap = (
        good["quality_positive_score"] - bad["quality_positive_score"]
        + bad["quality_penalty"] - good["quality_penalty"]
    )

    impacts = {}
    cases = (
        ("dialogue_state", "_evaluate_dialogue_changes_state", {"dialogue_changes_state": True}, 280),
        ("ending_pressure", "_evaluate_ending_pressure", {"ending_pressure_passed": True}, 600),
        ("event_density", "_evaluate_event_density", {"event_density_passed": True}, 260),
        ("state_change_interval", "_evaluate_event_density", {"state_change_interval_passed": True}, 190),
        ("content_balance", "_evaluate_content_balance", {"content_balance_penalty": 0}, 120),
    )
    for name, evaluator, updates, expected in cases:
        with monkeypatch.context() as scoped:
            _patch_evaluator(scoped, evaluator, updates)
            repaired = _score(BAD_FLAT_CHATTER)
        impacts[name] = repaired["score"] - bad["score"]
        assert impacts[name] == expected

    controlled_component_gap = sum(impacts.values())
    assert sum(impact > 0 for impact in impacts.values()) >= 3
    # 五项明确的可控维度必须始终贡献 1450 分；总质量分还包含段落、
    # 推进单元等独立正向项，因此不能错误地要求它恰好等于这五项之和。
    assert controlled_component_gap == 1450
    assert quality_gap >= controlled_component_gap
    assert good["score"] - bad["score"] == (
        good["eligibility_score"] - bad["eligibility_score"] + quality_gap
    )


def test_t16_quality_penalty_includes_continuity_inherit_failure(monkeypatch):
    """承接缺失已影响总分时，必须同步进入可审计 quality_penalty。"""
    content = "顾沉推开档案室的门，追兵已经逼近，他决定翻查旧账。" * 90
    original = PipelineOrchestrator._evaluate_continuity_inherit

    def with_continuity(value):
        def patched(_text, _mission):
            result = dict(original(_text, _mission))
            result["continuity_inherit_missing"] = value
            return result
        return staticmethod(patched)

    with monkeypatch.context() as scoped:
        scoped.setattr(PipelineOrchestrator, "_evaluate_continuity_inherit", with_continuity(False))
        present = _score(content)
    with monkeypatch.context() as scoped:
        scoped.setattr(PipelineOrchestrator, "_evaluate_continuity_inherit", with_continuity(True))
        missing = _score(content)

    assert missing["score"] == present["score"] - 280
    assert missing["quality_penalty"] == present["quality_penalty"] + 280
    assert missing["quality_positive_score"] == present["quality_positive_score"]


def test_t16_continuity_penalty_audit_contract_is_not_removed():
    import inspect
    source = inspect.getsource(PipelineOrchestrator._score_story_quality_candidate)
    marker = '+ (280 if continuity_inherit.get("continuity_inherit_missing") else 0)'
    assert marker in source
    sabotaged = source.replace(marker, '+ (280 if continuity_inherit.get("removed_continuity_inherit_missing") else 0)', 1)
    with pytest.raises(AssertionError):
        assert marker in sabotaged


def test_t16_quality_penalty_includes_long_chapter_density_failure(monkeypatch):
    """长章密度失败的总分扣减必须同步进入可审计 quality_penalty。"""
    content = "\n".join(
        f"第{index}段，顾沉推开门，追兵已经逼近，他拒绝交出钥匙，决定从后窗反制。"
        for index in range(1, 260)
    )
    assert len("".join(content.split())) >= 7000
    original = PipelineOrchestrator._evaluate_event_density

    def with_long_density(value):
        def patched(cls, *args, **kwargs):
            result = dict(original(*args, **kwargs))
            result["long_chapter_density_passed"] = value
            return result
        return classmethod(patched)

    with monkeypatch.context() as scoped:
        scoped.setattr(PipelineOrchestrator, "_evaluate_event_density", with_long_density(True))
        passed = _score(content)
    with monkeypatch.context() as scoped:
        scoped.setattr(PipelineOrchestrator, "_evaluate_event_density", with_long_density(False))
        failed = _score(content)

    # 总分同时撤销长章通过奖励 90，并记录失败惩罚 180；
    # quality_penalty 只负责后者，不能把两种构成混为一项。
    assert failed["score"] == passed["score"] - 270
    assert failed["quality_penalty"] == passed["quality_penalty"] + 180
    assert failed["quality_positive_score"] == passed["quality_positive_score"] - 90


def test_t16_sabotage_removing_eligibility_cap_breaks_existing_upper_bound(monkeypatch):
    original = PipelineOrchestrator._score_story_quality_candidate

    def sabotaged(cls, *args, **kwargs):
        result = dict(original(*args, **kwargs))
        result["eligibility_score"] = 281
        return result

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_score_story_quality_candidate",
        classmethod(sabotaged),
    )
    with pytest.raises(AssertionError):
        assert _score(GOOD_DRAMATIC)["eligibility_score"] <= 280


def test_t16_sabotage_removing_key_ending_penalty_breaks_existing_score_gap(monkeypatch):
    good = _score(GOOD_DRAMATIC)
    _patch_evaluator(monkeypatch, "_evaluate_ending_pressure", {"ending_pressure_passed": True})
    sabotaged_bad = _score(BAD_FLAT_CLOSURE)

    with pytest.raises(AssertionError):
        assert good["score"] - sabotaged_bad["score"] >= 600