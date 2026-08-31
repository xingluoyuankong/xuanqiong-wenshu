from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.test_generation_quality_guards import (
    BAD_ALL_DESCRIPTION, BAD_FLAT_CHATTER, BAD_FLAT_CLOSURE,
    BAD_MUNDANE_SEQUENCE, BAD_PUNCTUATION_HOOK, GOOD_DRAMATIC,
)


def _score(content):
    return PipelineOrchestrator._score_story_quality_candidate(
        content=content, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250,
    )["score"]


def test_quality_score_gap_between_good_and_form_only_chatter_is_large():
    good = _score(GOOD_DRAMATIC)
    bad = _score(BAD_FLAT_CHATTER)

    assert good - bad >= 600


def test_eligibility_score_is_capped_at_thirty_five_percent_of_baseline():
    result = PipelineOrchestrator._score_story_quality_candidate(
        content=GOOD_DRAMATIC, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250,
    )

    assert result["eligibility_score"] <= 280


def test_score_gap_for_bad_samples_is_spread_across_quality_dimensions():
    good = PipelineOrchestrator._score_story_quality_candidate(
        content=GOOD_DRAMATIC, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250,
    )
    bad_samples = (BAD_ALL_DESCRIPTION, BAD_FLAT_CHATTER, BAD_FLAT_CLOSURE, BAD_MUNDANE_SEQUENCE, BAD_PUNCTUATION_HOOK)
    for content in bad_samples:
        bad = PipelineOrchestrator._score_story_quality_candidate(
            content=content, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250,
        )
        assert good["score"] - bad["score"] >= 600
    dimensions = {
        "static": PipelineOrchestrator._score_story_quality_candidate(content=BAD_ALL_DESCRIPTION, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250)["static_description_risk"],
        "density": PipelineOrchestrator._score_story_quality_candidate(content=BAD_FLAT_CHATTER, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250)["event_density_passed"] is False,
        "ending": PipelineOrchestrator._score_story_quality_candidate(content=BAD_FLAT_CLOSURE, violations=[], chapter_mission=None, target_word_count=2500, min_word_count=2250)["ending_pressure_passed"] is False,
    }
    assert sum(bool(value) for value in dimensions.values()) >= 3
