from app.services.pipeline_orchestrator import PipelineOrchestrator


MISSION = {"continuity_anchor": {"inherit_from_previous": ["门外脚步声逼近"]}}


def _score(content: str):
    return PipelineOrchestrator._score_story_quality_candidate(
        content=content, violations=[], chapter_mission=MISSION, target_word_count=1500, min_word_count=1200,
    )


def test_continuity_inherit_missing_is_warning_and_penalty():
    result = _score("林七走进档案室，翻开被雨水浸湿的账页，决定查清是谁改了记录。" * 55)
    snapshot = result["quality_metric_snapshot"]
    assert result["continuity_inherit_missing"] is True
    assert result["continuity_inherit_hit_count"] == 0
    assert "continuity_inherit_missing" in snapshot["quality_issue_codes"]
    assert result["quality_penalty"] >= 280


def test_continuity_inherit_exact_match_in_opening_is_recognized():
    result = _score("门外脚步声逼近，林七先锁上档案室的门。" + "他继续翻查账页，发现每一页都少了一行记录。" * 55)
    assert result["continuity_inherit_missing"] is False
    assert result["continuity_inherit_hit_count"] >= 1
    assert "continuity_inherit_missing" not in result["quality_metric_snapshot"]["quality_issue_codes"]


def test_continuity_inherit_late_is_a_weak_warning():
    content = "林七翻查旧账，始终没有提到前章的危险。" * 45 + "门外脚步声逼近，他终于握紧钥匙。"
    result = _score(content)
    assert result["continuity_inherit_late"] is True
    assert result["inherit_hit_count"] == 0
    assert "continuity_inherit_late" in result["quality_metric_snapshot"]["quality_issue_codes"]

def test_continuity_inherit_semantic_two_term_rewrite_is_recognized_in_opening():
    result = _score("脚步声已经到了门外，林七先锁上档案室的门。" + "他继续翻查账页，发现每一页都少了一行记录。" * 55)
    assert result["continuity_inherit_missing"] is False
    assert result["continuity_inherit_hit_count"] >= 1
    assert result["continuity_inherit_match_mode"] == "exact_or_two_term_semantic"


def test_continuity_inherit_single_generic_term_does_not_count_as_semantic_match():
    result = _score("雨水浸湿了账页，林七继续查找记录。" * 55)
    assert result["continuity_inherit_missing"] is True
    assert result["continuity_inherit_hit_count"] == 0

