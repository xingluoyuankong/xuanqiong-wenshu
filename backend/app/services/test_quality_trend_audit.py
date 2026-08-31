from __future__ import annotations

import inspect

import pytest

from scripts import audit_quality_trend


def test_quality_trend_audit_falls_back_from_empty_version_gate_to_runtime_gate():
    result = audit_quality_trend.audit_metadata_rows([{
        "chapter_id": 88,
        "metadata": {"quality_gate": {}},
        "real_summary": {
            "generation_runtime": {
                "quality_gate": {"blockers": [{"code": "runtime_only_blocker"}]}
            }
        },
    }])
    assert result["gate_rows"] == 1
    assert result["gate_source_counts"] == {"chapter_runtime": 1}
    assert result["blocker_counts"] == {"runtime_only_blocker": 1}


def test_quality_trend_audit_includes_runtime_gate_when_version_metadata_has_none():
    result = audit_quality_trend.audit_metadata_rows([
        {
            "metadata": {"quality_metrics": {}},
            "real_summary": {},
        },
        {
            "metadata": {"quality_metrics": {"score": 10}},
            "real_summary": {
                "generation_runtime": {
                    "quality_gate": {
                        "blockers": [{"code": "ending_pressure_missing"}],
                        "warnings": [{"code": "continuity_inherit_missing"}],
                        "exemptions": ["event_density_weak"],
                    }
                }
            },
        }
    ])
    assert result["quality_metric_rows"] == 1
    assert result["gate_rows"] == 1
    assert result["gate_source_counts"] == {"chapter_runtime": 1}
    assert result["blocker_counts"] == {"ending_pressure_missing": 1}
    assert result["warning_counts"] == {"continuity_inherit_missing": 1}
    assert result["exemption_counts"] == {"event_density_weak": 1}


def test_quality_trend_audit_deduplicates_runtime_gate_per_chapter():
    runtime_row = {
        "chapter_id": 7,
        "metadata": {"quality_metrics": {}},
        "real_summary": {
            "generation_runtime": {
                "quality_gate": {
                    "blockers": [{"code": "ending_pressure_missing"}],
                    "warnings": [{"code": "continuity_inherit_missing"}],
                    "exemptions": ["event_density_weak"],
                }
            }
        },
    }
    result = audit_quality_trend.audit_metadata_rows([runtime_row, dict(runtime_row)])
    assert result["gate_rows"] == 1
    assert result["gate_source_counts"] == {"chapter_runtime": 1}
    assert result["blocker_counts"] == {"ending_pressure_missing": 1}
    assert result["warning_counts"] == {"continuity_inherit_missing": 1}
    assert result["exemption_counts"] == {"event_density_weak": 1}


def test_quality_trend_audit_uses_selected_version_for_multichapter_aggregation():
    result = audit_quality_trend.audit_metadata_rows([
        {
            "chapter_id": 11,
            "chapter_number": 2,
            "version_id": 101,
            "selected_version_id": 102,
            "metadata": {"quality_metrics": {"quality_issue_codes": ["old_candidate"]}},
            "real_summary": {},
        },
        {
            "chapter_id": 11,
            "chapter_number": 2,
            "version_id": 102,
            "selected_version_id": 102,
            "metadata": {"quality_metrics": {"quality_issue_codes": ["selected_candidate"]}},
            "real_summary": {},
        },
    ])

    assert result["quality_metric_rows"] == 1
    assert result["quality_issue_counts"] == {"selected_candidate": 1}


def test_quality_trend_audit_recomputes_mission_health_and_preserves_first_chapter_exemption():
    empty_mission = {"chapter_mission": {"scene_list": []}, "quality_metrics": {"target_word_count": 2500}}
    result = audit_quality_trend.audit_metadata_rows([
        {"chapter_id": 1, "chapter_number": 1, "metadata": empty_mission, "real_summary": {}},
        {"chapter_id": 2, "chapter_number": 2, "metadata": empty_mission, "real_summary": {}},
    ])

    assert result["mission_quality_rows"] == 2
    assert result["mission_quality_counts"]["mission_scene_too_few"] == 2
    assert result["mission_quality_counts"]["mission_inherit_empty"] == 1
    assert result["first_chapter_mission_inherit_violations"] == 0


def test_quality_trend_audit_selected_version_and_mission_contracts_have_reverse_guards():
    source = inspect.getsource(audit_quality_trend.audit_metadata_rows)
    for required in (
        '"selected_version_id"',
        'metrics.get("mission_quality_codes") is None',
        'chapter_number=max(1, chapter_number)',
    ):
        assert required in source
    sabotaged = source.replace('metrics.get("mission_quality_codes") is None', 'metrics.get("removed_mission_quality_codes") is None', 1)
    with pytest.raises(AssertionError):
        assert 'metrics.get("mission_quality_codes") is None' in sabotaged


def test_quality_trend_audit_recomputes_explicit_null_mission_and_continuity_metrics():
    mission = {"continuity_anchor": {"inherit_from_previous": ["门外脚步声逼近"]}, "scene_list": []}
    result = audit_quality_trend.audit_metadata_rows([{
        "chapter_id": 4,
        "chapter_number": 2,
        "metadata": {
            "chapter_mission": mission,
            "quality_metrics": {"target_word_count": 2500, "mission_quality_codes": None},
        },
        "content": "林七翻查旧账。" * 80 + "门外脚步声逼近，他握紧钥匙。",
        "real_summary": {},
    }])
    assert result["mission_quality_rows"] == 1
    assert result["mission_quality_counts"]["mission_scene_too_few"] == 1
    assert "mission_inherit_empty" not in result["mission_quality_counts"]
    assert result["continuity_observed_rows"] == 1
    assert result["continuity_missing_rows"] == 0
    assert result["continuity_late_rows"] == 1


def test_quality_trend_audit_recomputes_missing_inherit_mission_and_keeps_unavailable_continuity_unobserved():
    mission = {"scene_list": []}
    result = audit_quality_trend.audit_metadata_rows([{
        "chapter_id": 4,
        "chapter_number": 2,
        "metadata": {
            "chapter_mission": mission,
            "quality_metrics": {"target_word_count": 2500, "mission_quality_codes": None},
        },
        "content": "林七翻查旧账。" * 80 + "门外脚步声逼近，他握紧钥匙。",
        "real_summary": {},
    }])
    assert result["mission_quality_rows"] == 1
    assert result["mission_quality_counts"]["mission_scene_too_few"] == 1
    assert result["mission_quality_counts"]["mission_inherit_empty"] == 1
    assert result["continuity_observed_rows"] == 0


def test_quality_trend_audit_backfills_guard_only_into_missing_metrics():
    result = audit_quality_trend.audit_metadata_rows([
        {
            "metadata": {
                "quality_metrics": {
                    "quality_issue_codes": ["existing_issue"],
                    "score": 701,
                },
                "story_progression_guard": {
                    "quality_issue_codes": ["guard_issue_should_not_override"],
                    "continuity_inherit_missing": True,
                    "score": 999,
                    "quality_metric_snapshot": {
                        "quality_issue_codes": ["nested_snapshot_must_not_copy"],
                    },
                    "quality_issue_summary": {
                        "codes": ["nested_summary_must_not_copy"],
                    },
                },
            }
        }
    ])

    assert result["quality_metric_rows"] == 1
    assert result["quality_issue_counts"] == {"existing_issue": 1}


def test_quality_trend_audit_guard_backfill_contract_cannot_be_removed():
    source = inspect.getsource(audit_quality_trend._backfill_story_progression_guard)
    for required in ("if key in excluded or key in result", "quality_metric_snapshot", "quality_issue_summary"):
        assert required in source
    sabotaged = source.replace("if key in excluded or key in result", "if key in excluded", 1)
    with pytest.raises(AssertionError):
        assert "if key in excluded or key in result" in sabotaged


def test_quality_trend_audit_runtime_gate_source_is_not_removed():
    source = inspect.getsource(audit_quality_trend.audit_metadata_rows)
    runtime_source = 'real_summary.get("generation_runtime")'
    assert runtime_source in source
    sabotaged = source.replace(runtime_source, 'real_summary.get("removed_generation_runtime")', 1)
    with pytest.raises(AssertionError):
        assert runtime_source in sabotaged


def test_quality_trend_audit_flattens_legacy_t08_t15_nested_fields():
    metadata = {
        "quality_metrics": {},
        "story_progression_guard": {
            "static_description_runs": {"static_paragraph_count": 5, "max_static_run": 4},
            "ending_pressure": {
                "ending_pressure_passed": False,
                "ending_semantic_hit_count": 0,
                "ending_core_deflating": True,
            },
        },
    }
    flattened = audit_quality_trend._backfill_story_progression_guard(
        metadata["quality_metrics"], metadata,
    )
    assert flattened["static_paragraph_count"] == 5
    assert flattened["max_static_run"] == 4
    assert flattened["ending_pressure_passed"] is False
    assert flattened["ending_semantic_hit_count"] == 0
    assert flattened["ending_core_deflating"] is True

    source = inspect.getsource(audit_quality_trend._backfill_story_progression_guard)
    assert '"static_description_runs"' in source
    assert '"ending_pressure"' in source
