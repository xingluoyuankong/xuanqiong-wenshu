from app.services.pipeline_orchestrator import PipelineOrchestrator


def _guard():
    return {
        "word_count": 1600, "dialogue_marker_count": 8, "mission_hit_count": 3,
        "scene_count": 1, "scene_fulfillment_rate": 0.2, "scene_structure_rate": 0.8,
        "expected_dialogue": True, "dialogue_changes_state": False,
        "static_description_risk": False, "chapter_artifact_markers": False, "repetition_risk": False,
        "ending_pressure_passed": True, "event_density_passed": True,
        "state_change_interval_passed": True, "long_chapter_density_passed": True,
        "focus_character_missing": False,
    }


def test_gate_demotes_uncertain_scene_and_dialogue_issues_to_warnings(monkeypatch):
    monkeypatch.setattr(PipelineOrchestrator, "_score_story_quality_candidate", classmethod(lambda cls, **_kwargs: _guard()))
    _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content="正文", violations=[], chapter_mission={"dialogue_strategy": {"purpose": ["试探"]}},
        target_word_count=1600, min_word_count=1200,
    )
    assert gate["passed"] is True
    assert gate["blockers"] == []
    assert {item["code"] for item in gate["warnings"]} == {"scene_fulfillment_weak", "dialogue_does_not_change_state"}
    assert all(item["patch_suggestion"] for item in gate["warnings"])


def test_gate_keeps_reliable_repetition_as_blocker(monkeypatch):
    guard = _guard()
    guard["repetition_risk"] = True
    monkeypatch.setattr(PipelineOrchestrator, "_score_story_quality_candidate", classmethod(lambda cls, **_kwargs: guard))
    _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content="正文", violations=[], chapter_mission={}, target_word_count=1600, min_word_count=1200,
    )
    assert gate["passed"] is False
    assert "repeated_paragraph_flood" in {item["code"] for item in gate["blockers"]}


def test_gate_records_high_critique_exemptions(monkeypatch):
    guard = _guard()
    guard.update({"word_count": 1800, "ending_pressure_passed": False, "event_density_passed": False, "dialogue_changes_state": True})
    monkeypatch.setattr(PipelineOrchestrator, "_score_story_quality_candidate", classmethod(lambda cls, **_kwargs: guard))
    _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={"self_critique": {"final_score": 80, "critical_count": 0, "major_count": 0}},
        content="正文", violations=[], chapter_mission={}, target_word_count=1800, min_word_count=1200,
    )
    assert set(gate["exemptions"]) == {"ending_pressure_missing", "event_density_weak"}


def test_gate_emits_focus_and_continuity_warnings_with_mission_specific_patches(monkeypatch):
    """E-11：此前这两类只停留在 guard 摘要，必须进入 gate warnings 且带任务书事实。"""
    guard = _guard()
    guard.update({
        "focus_character_missing": True,
        "continuity_inherit_missing": True,
        "continuity_inherit_late": False,
    })
    monkeypatch.setattr(PipelineOrchestrator, "_score_story_quality_candidate", classmethod(lambda cls, **_kwargs: guard))
    mission = {
        "focus_characters": ["沈决", "楚昭"],
        "continuity_anchor": {"inherit_from_previous": ["门外脚步声逼近"]},
    }

    _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content="正文", violations=[], chapter_mission=mission,
        target_word_count=1600, min_word_count=1200,
    )

    warnings = {item["code"]: item for item in gate["warnings"]}
    assert gate["passed"] is True
    assert gate["blockers"] == []
    assert warnings["focus_character_missing"]["severity"] == "warning"
    assert "沈决、楚昭" in warnings["focus_character_missing"]["patch_suggestion"]
    assert "门外脚步声逼近" in warnings["continuity_inherit_missing"]["patch_suggestion"]
    patches = {item["code"]: item["suggestion"] for item in gate["patch_suggestions"]}
    assert patches["focus_character_missing"] == warnings["focus_character_missing"]["patch_suggestion"]
    assert patches["continuity_inherit_missing"] == warnings["continuity_inherit_missing"]["patch_suggestion"]


def test_gate_warning_patch_includes_scene_and_dialogue_mission_context(monkeypatch):
    """E-11：降档不等于只报 code；场景/对白告警应可直接指导局部修复。"""
    monkeypatch.setattr(PipelineOrchestrator, "_score_story_quality_candidate", classmethod(lambda cls, **_kwargs: _guard()))
    mission = {
        "dialogue_strategy": {"purpose": ["逼问账簿去向"]},
        "scene_list": [{"goal": "夺回伪造账簿"}],
    }

    _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content="正文", violations=[], chapter_mission=mission,
        target_word_count=1600, min_word_count=1200,
    )

    warnings = {item["code"]: item for item in gate["warnings"]}
    assert "逼问账簿去向" in warnings["dialogue_does_not_change_state"]["patch_suggestion"]
    assert "夺回伪造账簿" in warnings["scene_fulfillment_weak"]["patch_suggestion"]


def test_gate_reports_missing_mission_turn_as_permanent_warning(monkeypatch):
    """E-11：反转检测表达方式不稳定，只能告警，绝不能变成拒稿条件。"""
    guard = _guard()
    guard.update({"reversal_in_late_section": False})
    monkeypatch.setattr(PipelineOrchestrator, "_score_story_quality_candidate", classmethod(lambda cls, **_kwargs: guard))
    mission = {"scene_list": [{"turn": "账簿被掉包，证人反咬主角"}]}

    _summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content="正文", violations=[], chapter_mission=mission,
        target_word_count=1600, min_word_count=1200,
    )

    warnings = {item["code"]: item for item in gate["warnings"]}
    assert gate["passed"] is True
    assert "reversal_missing" not in {item["code"] for item in gate["blockers"]}
    assert "账簿被掉包，证人反咬主角" in warnings["reversal_missing"]["patch_suggestion"]


def test_e11_severity_matrix_covers_all_structural_issue_classes():
    """E-11：锁住当前生产分档，防止任一可靠 blocker 被意外降成 warning。"""
    cases = []
    for code, updates, expected_level in (
        ("static_description_risk", {"static_description_risk": True}, "blocker"),
        ("chapter_artifact_markers", {"chapter_artifact_markers": True}, "blocker"),
        ("repeated_paragraph_flood", {"repetition_risk": True}, "blocker"),
        ("insufficient_dialogue_pressure", {"expected_dialogue": True, "dialogue_marker_count": 0}, "blocker"),
        ("chapter_progression_weak", {"mission_hit_count": 0, "dialogue_marker_count": 0, "expected_dialogue": True}, "blocker"),
        ("scene_fulfillment_weak", {"scene_fulfillment_rate": 0.2}, "warning"),
        ("scene_structure_weak", {"word_count": 1800, "scene_structure_rate": 0.2}, "warning"),
        ("dialogue_does_not_change_state", {"dialogue_changes_state": False}, "warning"),
        ("ending_pressure_missing", {"ending_pressure_passed": False}, "blocker"),
        ("event_density_weak", {"word_count": 1800, "event_density_passed": False}, "blocker"),
        ("state_change_interval_weak", {"word_count": 2500, "state_change_interval_passed": False}, "blocker"),
        ("long_chapter_event_density_weak", {"word_count": 7000, "long_chapter_density_passed": False}, "blocker"),
    ):
        guard = _guard()
        guard.update(updates)
        if code == "scene_structure_weak":
            guard["scene_fulfillment_rate"] = 0.8
        if code == "dialogue_does_not_change_state":
            guard["scene_fulfillment_rate"] = 0.8
        cases.append((code, guard, expected_level, {}))

    warning_mission = {
        "focus_characters": ["沈决"],
        "continuity_anchor": {"inherit_from_previous": ["门外脚步声"]},
        "scene_list": [{"turn": "证人突然反咬"}],
    }
    warning_guard = _guard()
    warning_guard.update({
        "focus_character_missing": True,
        "continuity_inherit_missing": True,
        "continuity_inherit_late": False,
        "reversal_in_late_section": False,
    })
    for code in ("focus_character_missing", "continuity_inherit_missing", "reversal_missing"):
        cases.append((code, warning_guard, "warning", warning_mission))

    for code, guard, expected_level, mission in cases:
        gate = PipelineOrchestrator._build_structural_quality_gate({
            "story_progression_guard": guard,
            "chapter_mission": mission,
        })
        levels = {
            item["code"]: "blocker" for item in gate["blockers"]
        }
        levels.update({item["code"]: "warning" for item in gate["warnings"]})
        assert levels.get(code) == expected_level, (code, levels, gate)

