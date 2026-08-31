from __future__ import annotations

import inspect

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator


def _cleanup_contract(source: str) -> dict[str, int]:
    calls = [index for index, line in enumerate(source.splitlines()) if 'self._apply_deterministic_cleanup(' in line]
    final_quality = source.find('final_quality_guard = self._score_story_quality_candidate(')
    metadata = source.find('runtime_metadata["deterministic_cleanup"]')
    if len(calls) < 2:
        raise AssertionError('generate_chapter must clean after selection and before final quality gate')
    if not any(index < source[:final_quality].count('\n') for index in calls):
        raise AssertionError('a cleanup call must happen before final quality guard')
    return {'cleanup_calls': len(calls), 'final_quality_offset': final_quality, 'metadata_offset': metadata}


def test_generate_chapter_keeps_both_cleanup_hooks_and_runtime_diff_recording():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    contract = _cleanup_contract(source)
    assert contract['cleanup_calls'] == 2
    assert contract['final_quality_offset'] > 0
    assert contract['metadata_offset'] > 0
    assert source.count('runtime_metadata["deterministic_cleanup"]') >= 2


def test_t17_integration_contract_fails_when_final_cleanup_hook_is_removed():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    sabotaged = source.replace('            best_content, final_cleanup = self._apply_deterministic_cleanup(', '            best_content, final_cleanup = self._apply_deterministic_cleanup_REMOVED(', 1)
    with pytest.raises(AssertionError):
        _cleanup_contract(sabotaged)


def test_t17_cleanup_helper_still_enforces_safe_diff_contract():
    original = '## 第三章\n**正文。**\n（本章完）'
    cleaned, metadata = PipelineOrchestrator._apply_deterministic_cleanup(
        content=original, chapter_mission=None, target_word_count=20, min_word_count=1
    )
    assert cleaned == '正文。'
    assert metadata['applied'] is True
    assert metadata['removed_examples']

def test_t17_final_cleanup_recomputes_gate_after_score_fields_change():
    content = "## 1\n" + (
        "林七推开门，发现账簿被换成空白纸。“谁拿走了它？”她问。"
        "楼下传来急刹声，电话说最后期限已经到了，门外脚步声再次逼近。"
    ) * 16
    cleaned, cleanup = PipelineOrchestrator._apply_deterministic_cleanup(
        content=content, chapter_mission=None, target_word_count=1200, min_word_count=900,
    )
    before_summary, before_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content=content, violations=[], chapter_mission=None,
        target_word_count=1200, min_word_count=900,
    )
    after_summary, after_gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content=cleaned, violations=[], chapter_mission=None,
        target_word_count=1200, min_word_count=900,
    )
    before_guard = before_summary["story_progression_guard"]
    after_guard = after_summary["story_progression_guard"]

    assert cleanup["applied"] is True
    assert cleaned != content
    assert isinstance(before_guard["score"], (int, float))
    assert isinstance(after_guard["score"], (int, float))
    assert before_guard["score"] != after_guard["score"]
    assert isinstance(before_guard["word_count"], int)
    assert isinstance(after_guard["word_count"], int)
    assert before_guard["word_count"] != after_guard["word_count"]
    assert before_gate["passed"] is after_gate["passed"] is True
    assert before_gate["quality_issue_codes"] == after_gate["quality_issue_codes"] == []

    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    final_cleanup = source.index("best_content, final_cleanup = self._apply_deterministic_cleanup(")
    final_recompute = source.index(
        "review_summaries, structural_quality_gate = self._evaluate_structural_quality_gate_for_content(",
        final_cleanup,
    )
    final_score = source.index("final_quality_guard = self._score_story_quality_candidate(", final_recompute)
    final_runtime_gate = source.index(
        'runtime_metadata["quality_gates"]["structural_gate"] = structural_quality_gate',
        final_recompute,
    )
    assert final_cleanup < final_recompute < final_runtime_gate < final_score

