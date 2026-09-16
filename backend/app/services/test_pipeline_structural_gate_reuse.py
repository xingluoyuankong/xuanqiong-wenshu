import inspect

from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_noop_gate_reuse_keeps_raw_text_equality_not_normalized_fingerprint():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    assert 'best_content == pre_enrichment_content' in source
    assert 'best_content == pre_final_cleanup_content' in source
    assert 'pre_enrichment_structural_gate' in source
    assert 'pre_final_cleanup_structural_gate' in source
    assert '_content_fingerprint(best_content)' not in source


def test_noop_gate_reuse_copies_pre_enrichment_guard_to_standard_key():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    reuse_offset = source.index('structural_quality_gate["reused_from"] = "pre_enrichment_structural_gate"')
    guard_copy_offset = source.index('review_summaries["story_progression_guard"] = deepcopy(pre_guard)')
    assert guard_copy_offset < reuse_offset


def test_final_cleanup_still_recomputes_gate_when_any_character_changes():
    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    condition = 'if best_content == pre_final_cleanup_content:'
    recompute = 'else:\n                review_summaries, structural_quality_gate = self._evaluate_structural_quality_gate_for_content('
    assert condition in source
    assert recompute in source
    assert PipelineOrchestrator._content_fingerprint('甲\n\n乙') == PipelineOrchestrator._content_fingerprint('甲 乙')
    assert '甲\n\n乙' != '甲 乙'
