import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.test_generation_quality_guards import BAD_FLAT_CHATTER


def _density(text):
    return PipelineOrchestrator._evaluate_event_density(
        text, word_count=PipelineOrchestrator._count_words(text)
    )


def test_t02_sabotage_readding_neutral_closure_prefix_breaks_hook_guard(monkeypatch):
    text = "追兵已经堵住了退路，她攥紧照片冲向后窗，玻璃在身后炸裂，而幕后是谁，一切都还是未知。"
    expected = PipelineOrchestrator._evaluate_ending_pressure(text, None)
    assert expected["ending_pressure_passed"] is True

    monkeypatch.setattr(
        PipelineOrchestrator,
        "ENDING_CLOSURE_MARKERS",
        PipelineOrchestrator.ENDING_CLOSURE_MARKERS + ("一切都",),
    )
    sabotaged = PipelineOrchestrator._evaluate_ending_pressure(text, None)
    with pytest.raises(AssertionError):
        assert sabotaged["flat_closure_markers"] == []


def test_t03_sabotage_promoting_weak_word_to_semantic_hook_breaks_punctuation_guard(monkeypatch):
    text = "他喝完了茶，把杯子放回原处，觉得这一天过得很舒服。真的很舒服吗？当然很舒服！"
    expected = PipelineOrchestrator._evaluate_ending_pressure(text, None)
    assert expected["ending_pressure_passed"] is False

    monkeypatch.setattr(
        PipelineOrchestrator,
        "ENDING_SEMANTIC_HOOK_MARKERS",
        PipelineOrchestrator.ENDING_SEMANTIC_HOOK_MARKERS + ("舒服",),
    )
    sabotaged = PipelineOrchestrator._evaluate_ending_pressure(text, None)
    with pytest.raises(AssertionError):
        assert sabotaged["ending_pressure_passed"] is False


def test_t04_sabotage_making_every_sentence_progression_breaks_small_talk_guard(monkeypatch):
    expected = _density(BAD_FLAT_CHATTER)
    assert expected["event_density_passed"] is False

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_unit_has_progression",
        classmethod(lambda cls, _unit: True),
    )
    sabotaged = _density(BAD_FLAT_CHATTER)
    with pytest.raises(AssertionError):
        assert sabotaged["event_density_passed"] is False


def test_t05_sabotage_making_every_window_pass_breaks_window_discrimination(monkeypatch):
    expected = _density(BAD_FLAT_CHATTER)
    assert expected["state_change_window_pass_rate"] < 1.0

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_window_has_state_change",
        classmethod(lambda cls, _window: True),
    )
    sabotaged = _density(BAD_FLAT_CHATTER)
    with pytest.raises(AssertionError):
        assert sabotaged["state_change_window_pass_rate"] < 1.0
