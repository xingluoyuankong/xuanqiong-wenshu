import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.test_generation_quality_guards import (
    REPEATED_PARAGRAPH_FLOOD,
    STATIC_TOKEN_DIALOGUE,
    _score_density_sample,
)


def test_t08_sabotage_zeroing_static_runs_breaks_mixed_description_guard(monkeypatch):
    expected = _score_density_sample(STATIC_TOKEN_DIALOGUE)
    assert expected["static_description_risk"] is True

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_estimate_static_description_runs",
        classmethod(lambda cls, _paragraphs: {"static_paragraph_count": 0, "max_static_run": 0}),
    )
    sabotaged = _score_density_sample(STATIC_TOKEN_DIALOGUE)
    with pytest.raises(AssertionError):
        assert sabotaged["static_description_risk"] is True


def test_t09_sabotage_treating_every_paragraph_as_action_breaks_scenery_guard(monkeypatch):
    scenery = ("晨雾漫过山谷，阳光洒在石阶上，芦苇轻轻摇曳，湖面看似平滑，云层却压得很低，但风铃始终没有声响。" * 3)
    expected = PipelineOrchestrator._estimate_static_description_runs([scenery])
    assert expected["static_paragraph_count"] == 1

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_paragraph_has_character_action",
        classmethod(lambda cls, _plain: True),
    )
    sabotaged = PipelineOrchestrator._estimate_static_description_runs([scenery])
    with pytest.raises(AssertionError):
        assert sabotaged["static_paragraph_count"] == 1


def test_t10_sabotage_disabling_repetition_risk_breaks_repeat_flood_guard(monkeypatch):
    paragraphs = REPEATED_PARAGRAPH_FLOOD.splitlines()
    expected = PipelineOrchestrator._evaluate_repetition_risk(paragraphs, word_count=2500)
    assert expected["repetition_risk"] is True

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_evaluate_repetition_risk",
        staticmethod(lambda _paragraphs, *, word_count: {
            "repetition_risk": False,
            "repeated_paragraph_count": 0,
            "repeated_paragraph_instances": 0,
            "max_repeated_paragraph_count": 1,
            "repeated_paragraph_ratio": 0.0,
            "longest_repeated_paragraph_chars": 0,
            "repeated_paragraph_examples": [],
        }),
    )
    sabotaged = PipelineOrchestrator._evaluate_repetition_risk(paragraphs, word_count=2500)
    with pytest.raises(AssertionError):
        assert sabotaged["repetition_risk"] is True