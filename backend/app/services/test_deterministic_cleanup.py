from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_deterministic_cleanup_removes_markdown_chrome_and_records_diff():
    original = "## 第三章\n**雨落在台阶上。**\n（本章完）"

    cleaned, metadata = PipelineOrchestrator._apply_deterministic_cleanup(
        content=original, chapter_mission=None, target_word_count=20, min_word_count=1,
    )

    assert "##" not in cleaned
    assert "**" not in cleaned
    assert "（本章完）" not in cleaned
    assert cleaned == "雨落在台阶上。"
    assert metadata["applied"] is True
    assert metadata["before_char_count"] > metadata["after_char_count"]
    assert metadata["removed_examples"]


def test_deterministic_cleanup_aborts_when_result_falls_below_minimum():
    original = "## 第三章\n雨落在台阶上。"

    cleaned, metadata = PipelineOrchestrator._apply_deterministic_cleanup(
        content=original, chapter_mission=None, target_word_count=20, min_word_count=100,
    )

    assert cleaned == original
    assert metadata["applied"] is False
    assert metadata["warning"] == "cleanup_would_drop_below_min_word_count"


def _assert_cleanup_is_wired_on_both_sides_of_structural_gate(source: str):
    assert source.count("self._apply_deterministic_cleanup(") == 2
    initial_cleanup = source.index("best_content, initial_cleanup = self._apply_deterministic_cleanup(")
    structural_gate = source.index("review_summaries, structural_quality_gate = self._evaluate_structural_quality_gate_for_content(")
    final_cleanup = source.index("best_content, final_cleanup = self._apply_deterministic_cleanup(")
    final_score = source.index("final_quality_guard = self._score_story_quality_candidate(", final_cleanup)
    persisted_versions = source.index("self.novel_service.append_chapter_versions(", final_cleanup)

    assert initial_cleanup < structural_gate < final_cleanup < final_score < persisted_versions
    assert 'best_content, initial_cleanup = self._apply_deterministic_cleanup(' in source
    assert '"initial": initial_cleanup,' in source
    assert '"final": None,' in source
    assert 'runtime_metadata["deterministic_cleanup_summary"] = {"initial": initial_cleanup, "final": final_cleanup}' in source


def test_deterministic_cleanup_is_wired_before_quality_processing_and_before_persistence():
    import inspect

    source = inspect.getsource(PipelineOrchestrator.generate_chapter)

    _assert_cleanup_is_wired_on_both_sides_of_structural_gate(source)


def test_cleanup_wiring_guard_fails_when_final_cleanup_is_removed():
    import inspect
    import pytest

    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    sabotaged = source.replace(
        "best_content, final_cleanup = self._apply_deterministic_cleanup(",
        "# final cleanup intentionally removed(",
        1,
    )

    with pytest.raises(AssertionError):
        _assert_cleanup_is_wired_on_both_sides_of_structural_gate(sabotaged)


def _assert_cleanup_runtime_metadata_keeps_bound_initial_diff(source: str) -> None:
    initial_assignment = source.index("best_content, initial_cleanup = self._apply_deterministic_cleanup(")
    initial_runtime = source.index('"initial": initial_cleanup,', initial_assignment)
    final_summary = source.index(
        'runtime_metadata["deterministic_cleanup_summary"] = {"initial": initial_cleanup, "final": final_cleanup}',
        initial_runtime,
    )
    assert initial_assignment < initial_runtime < final_summary


def test_t17_runtime_cleanup_summary_binds_and_preserves_initial_diff():
    import inspect

    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    _assert_cleanup_runtime_metadata_keeps_bound_initial_diff(source)


def test_t17_runtime_cleanup_summary_contract_detects_missing_initial_binding():
    import inspect

    source = inspect.getsource(PipelineOrchestrator.generate_chapter)
    sabotaged = source.replace(
        "best_content, initial_cleanup = self._apply_deterministic_cleanup(",
        "best_content, deterministic_cleanup = self._apply_deterministic_cleanup(",
        1,
    )

    import pytest
    with pytest.raises(ValueError):
        _assert_cleanup_runtime_metadata_keeps_bound_initial_diff(sabotaged)

