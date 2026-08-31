from __future__ import annotations

import ast
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "real_asgi_multichapter_trend_smoke.py"


def _load_compact_failure_diagnostics():
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "compact_failure_diagnostics")
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(_SCRIPT), "exec"), namespace)
    return namespace["compact_failure_diagnostics"]


def test_multichapter_smoke_keeps_gate_rejection_diagnostics_without_content():
    compact = _load_compact_failure_diagnostics()
    result = compact({
        "generation_runtime": {
            "progress_stage": "evaluation_failed",
            "progress_message": "quality gate rejected",
            "error_code": "CHAPTER_QUALITY_GATE_FAILED",
            "quality_gate": {
                "passed": False,
                "blockers": [{"code": "ending_pressure_missing"}],
                "warnings": [{"code": "continuity_inherit_missing"}],
            },
        }
    })
    assert result == {
        "runtime_stage": "evaluation_failed",
        "error_code": "CHAPTER_QUALITY_GATE_FAILED",
        "quality_gate_passed": False,
        "self_critique_final_score": None,
        "self_critique_critical_count": None,
        "self_critique_major_count": None,
        "selected_critique_source": None,
        "exemptions": [],
        "critique_exemption_applied": [],
        "patch_suggestions": [],
        "quality_issue_codes": [],
        "blocker_codes": ["ending_pressure_missing"],
        "warning_codes": ["continuity_inherit_missing"],
    }


def test_multichapter_smoke_does_not_emit_arbitrary_progress_message():
    compact = _load_compact_failure_diagnostics()
    result = compact({"generation_runtime": {"progress_message": "PRIVATE PROSE OR PROVIDER RESPONSE"}})

    assert "progress_message" not in result
    assert "PRIVATE PROSE OR PROVIDER RESPONSE" not in str(result)


def test_multichapter_smoke_does_not_restore_fail_fast_rejection_branch():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "MULTICHAPTER_CHAPTER_REJECTED" in source
    assert "MULTICHAPTER_FAILED" not in source
    assert "return 0 if rejected == 0 else 1" in source

def test_multichapter_smoke_projects_all_cross_chapter_metric_fields():
    source = _SCRIPT.read_text(encoding="utf-8")
    for field in (
        "reversal_signal_count", "reversal_in_late_section",
        "dialogue_ratio", "action_ratio", "description_ratio",
        "self_critique_final_score", "self_critique_critical_count",
        "self_critique_major_count", "selected_critique_source",
        "speaker_count", "dominant_speaker_ratio",
        "hard_scene_cut_count", "summary_scene_cut_count",
        "event_density_skip_reason", "mission_quality_codes",
        "exemptions", "critique_exemption_applied",
        "patch_suggestions", "quality_issue_codes",
    ):
        assert f'"{field}"' in source



def test_multichapter_smoke_projects_quality_gate_exemptions_without_content():
    compact = _load_compact_failure_diagnostics()
    result = compact({
        "generation_runtime": {
            "quality_gate": {
                "self_critique_final_score": 82,
                "self_critique_critical_count": 0,
                "self_critique_major_count": 1,
                "selected_critique_source": "self_critique_after_consistency",
                "passed": True,
                "exemptions": ["ending_pressure_missing"],
                "critique_exemption_applied": ["ending_pressure_missing"],
                "patch_suggestions": [{"code": "ending_pressure_missing", "suggestion": "补一段递压。"}],
                "quality_issue_codes": ["ending_pressure_missing"],
            }
        }
    })
    assert result["exemptions"] == ["ending_pressure_missing"]
    assert result["critique_exemption_applied"] == ["ending_pressure_missing"]
    assert result["self_critique_final_score"] == 82
    assert result["self_critique_critical_count"] == 0
    assert result["self_critique_major_count"] == 1
    assert result["selected_critique_source"] == "self_critique_after_consistency"
    assert result["patch_suggestions"] == [{"code": "ending_pressure_missing", "suggestion": "补一段递压。"}]
    assert result["quality_issue_codes"] == ["ending_pressure_missing"]
    assert "content" not in result


def test_multichapter_smoke_declares_distinct_word_count_semantics():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert '"content_char_count"' in source
    assert '"quality_metric_word_count"' in source
    assert '"word_count_semantics"' in source


def test_multichapter_smoke_does_not_hardcode_historical_evidence_date():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "20260821.json" not in source
    assert "datetime.now(timezone.utc).strftime" in source


def test_multichapter_smoke_exposes_explicit_self_critique_repair_probe():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "enable_self_critique" in source
    assert '"flow_config"' in source
    assert "--enable-self-critique" in source
