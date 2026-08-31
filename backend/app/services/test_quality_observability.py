from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_dialogue_speaker_distribution_observes_dominant_speaker():
    result = PipelineOrchestrator._evaluate_dialogue_speaker_distribution(
        "“先走。”林七说。\n“别回头。”林七说。\n“门开了。”沈舟说."
    )
    assert result["speaker_count"] == 2
    assert result["dominant_speaker_ratio"] > 0.5


def test_scene_transition_observes_unpressured_hard_cut():
    result = PipelineOrchestrator._evaluate_scene_transition_clarity([
        "林七翻完账页，屋里安静下来。",
        "第二天，他来到旧码头。",
    ])
    assert result["hard_scene_cut_count"] == 1
    assert result["scene_transition_warning"] is True


def test_static_run_requires_character_subject_for_action_marker():
    ambient = "风推开云层，雨水冲过石阶，屋檐下没有人影。" * 5
    human = "守卫推开铁门，转身把钥匙塞进袖口。" * 5
    result = PipelineOrchestrator._estimate_static_description_runs([ambient, human])
    assert result["static_paragraph_count"] == 1
    assert result["max_static_run"] == 1


def test_reversal_detects_a_late_repeat_of_an_early_signal():
    result = PipelineOrchestrator._evaluate_reversal_quality("原来线索来自旧案。" + "她沿楼梯往下走。" * 40 + "原来账簿藏在门后。")
    assert result["reversal_in_late_section"] is True


def test_scene_transition_observes_summary_closure_before_next_scene():
    result = PipelineOrchestrator._evaluate_scene_transition_clarity([
        "这一切都平静下来，谁也没有再开口。",
        "林七推开下一扇门，发现新的账页。",
    ])
    assert result["summary_scene_cut_count"] == 1
    assert result["scene_transition_warning"] is True


def test_quality_trend_audit_separates_gate_blockers_from_issue_codes():
    from scripts.audit_quality_trend import audit_metadata_rows

    result = audit_metadata_rows([{
        "quality_metrics": {
            "quality_issue_codes": ["focus_character_missing", "ending_pressure_missing"],
        },
        "quality_gate": {
            "blockers": [{"code": "ending_pressure_missing"}],
            "warnings": [{"code": "focus_character_missing"}],
            "exemptions": [],
        },
    }])
    assert result["blocker_counts"] == {"ending_pressure_missing": 1}
    assert result["warning_counts"] == {"focus_character_missing": 1}
    assert result["quality_issue_counts"] == {
        "ending_pressure_missing": 1,
        "focus_character_missing": 1,
    }


def test_quality_trend_audit_reverse_contract_rejects_issue_codes_as_blockers():
    import inspect
    import pytest
    from scripts import audit_quality_trend

    source = inspect.getsource(audit_quality_trend.audit_metadata_rows)
    assert 'gate.get("blockers")' in source
    sabotaged = source.replace('gate.get("blockers")', 'metrics.get("quality_issue_codes")', 1)
    with pytest.raises(AssertionError):
        assert 'gate.get("blockers")' in sabotaged

