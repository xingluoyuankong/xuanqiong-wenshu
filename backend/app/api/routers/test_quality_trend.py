from __future__ import annotations

import json

from types import SimpleNamespace

import pytest

from app.api.routers.novels import _redact_quality_trend_patch_suggestions, get_quality_trend
from app.models.novel import Chapter, ChapterVersion, NovelProject
from app.models.user import User


@pytest.mark.asyncio
async def test_quality_trend_aggregates_chapter_metrics_and_exemptions(task_session):
    user = User(id=920, username="quality-trend", email="quality-trend@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-trend-project", user_id=user.id, title="趋势测试")
    task_session.add_all([user, project])
    await task_session.flush()
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add(chapter)
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id, content="正文", metadata_={
            "quality_metrics": {
                "score": 880, "word_count": 2400, "event_density_passed": False,
                "long_chapter_density_passed": False, "state_change_interval_passed": None,
                "repetition_risk": True, "repeated_paragraph_count": 3,
                "max_repeated_paragraph_count": 4, "repeated_paragraph_ratio": 0.125,
                "longest_repeated_paragraph_chars": 680,
                "focus_character_names": ["沈砚", "陆明"],
                "focus_character_hit_count": 1,
                "missing_focus_characters": ["陆明"],
                "target_word_count": 3000, "min_word_count": 2400,
                "preferred_word_floor": 2760, "upper_word_ceiling": 3900,
                "word_count_below_min": False, "word_count_far_above_target": False,
                "word_count_far_below_target": False, "word_requirement_met": True,
                "event_density_evaluated": True, "event_density_skip_reason": None,
                "ending_pressure_passed": False, "quality_issue_codes": ["event_density_weak", "ending_pressure_missing"],
            },
            "quality_gate": {
                "blockers": [{"code": "event_density_weak"}],
                "warnings": [{"code": "focus_character_missing"}],
                "patch_suggestions": [{"code": "focus_character_missing", "suggestion": "补足视角人物的主动选择。"}],
                "exemptions": ["ending_pressure_missing"],
                "critique_exemption_applied": ["ending_pressure_missing"],
                "self_critique_final_score": 82,
                "self_critique_critical_count": 0,
                "self_critique_major_count": 1,
                "selected_critique_source": "self_critique_after_consistency",
            },
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    assert payload["chapter_count"] == 1
    item = payload["chapters"][0]
    assert item["chapter_number"] == 1
    assert item["score"] == 880
    assert item["repetition_risk"] is True
    assert item["repeated_paragraph_count"] == 3
    assert item["max_repeated_paragraph_count"] == 4
    assert item["repeated_paragraph_ratio"] == 0.125
    assert item["longest_repeated_paragraph_chars"] == 680
    assert item["focus_character_names"] == ["沈砚", "陆明"]
    assert item["focus_character_hit_count"] == 1
    assert item["missing_focus_characters"] == ["陆明"]
    assert item["target_word_count"] == 3000
    assert item["min_word_count"] == 2400
    assert item["preferred_word_floor"] == 2760
    assert item["upper_word_ceiling"] == 3900
    assert item["word_count_below_min"] is False
    assert item["word_count_far_above_target"] is False
    assert item["word_count_far_below_target"] is False
    assert item["word_requirement_met"] is True
    assert item["event_density_evaluated"] is True
    assert item["event_density_skip_reason"] is None
    assert item["long_chapter_density_passed"] is False
    assert item["state_change_interval_passed"] is None
    assert item["blocker_codes"] == ["event_density_weak"]
    assert item["warning_codes"] == ["focus_character_missing"]
    assert item["patch_suggestions"] == [{"code": "focus_character_missing", "suggestion": "补足视角人物的主动选择。"}]
    assert payload["blocker_counts"] == {"event_density_weak": 1}
    assert payload["warning_counts"] == {"focus_character_missing": 1}
    assert payload["exemption_counts"] == {"ending_pressure_missing": 1}
    assert item["exemptions"] == ["ending_pressure_missing"]
    assert item["critique_exemption_applied"] == ["ending_pressure_missing"]
    assert item["self_critique_final_score"] == 82
    assert item["self_critique_critical_count"] == 0
    assert item["self_critique_major_count"] == 1
    assert item["selected_critique_source"] == "self_critique_after_consistency"


@pytest.mark.asyncio
async def test_quality_trend_defaults_critique_exemption_applied_to_empty_list(task_session):
    user = User(id=931, username="quality-trend-no-exemption", email="quality-trend-no-exemption@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-trend-no-exemption-project", user_id=user.id, title="无豁免趋势测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="正文",
        metadata_={"quality_metrics": {"word_count": 1000}, "quality_gate": {"passed": True}},
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    assert payload["chapters"][0]["exemptions"] == []
    assert payload["chapters"][0]["critique_exemption_applied"] == []


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_quality_trend_backfills_t18_critique_fields_from_metric_snapshot(task_session):
    user = User(id=932, username="quality-trend-t18-legacy", email="quality-trend-t18@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-trend-t18-legacy-project", user_id=user.id, title="T18 旧快照趋势测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="evaluation_failed")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="脱敏测试正文",
        metadata_={
            "quality_metrics": {
                "quality_gate_summary": {"exemptions": ["ending_pressure_missing"]},
                "critique_exemption_applied": ["ending_pressure_missing"],
                "self_critique_final_score": 77.1,
                "self_critique_critical_count": 1,
                "self_critique_major_count": 5,
                "selected_critique_source": "self_critique_after_consistency",
            },
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    item = payload["chapters"][0]
    assert item["exemptions"] == ["ending_pressure_missing"]
    assert item["critique_exemption_applied"] == ["ending_pressure_missing"]
    assert item["self_critique_final_score"] == 77.1
    assert item["self_critique_critical_count"] == 1
    assert item["self_critique_major_count"] == 5
    assert item["selected_critique_source"] == "self_critique_after_consistency"
    assert payload["exemption_counts"] == {"ending_pressure_missing": 1}
async def test_quality_trend_preserves_t08_static_and_t15_ending_diagnostics(task_session):
    """T-08/T-15 细粒度快照字段不能在趋势层丢失。"""
    user = User(id=929, username="quality-t08-t15", email="quality-t08-t15@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-t08-t15-project", user_id=user.id, title="静态与章末趋势测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="正文",
        metadata_={
            "quality_metrics": {
                "static_description_risk": True,
                "static_paragraph_count": 4,
                "max_static_run": 3,
                "ending_pressure_passed": False,
                "ending_semantic_hit_count": 0,
                "ending_weak_hit_count": 2,
                "flat_closure_markers": ["终于结束"],
                "ending_core_chars": 168,
                "ending_core_semantic_hit_count": 0,
                "ending_core_weak_hit_count": 2,
                "ending_core_deflating": True,
            },
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    item = payload["chapters"][0]
    assert item["static_description_risk"] is True
    assert item["static_paragraph_count"] == 4
    assert item["max_static_run"] == 3
    assert item["ending_pressure_passed"] is False
    assert item["ending_semantic_hit_count"] == 0
    assert item["ending_weak_hit_count"] == 2
    assert item["flat_closure_markers"] == ["终于结束"]
    assert item["ending_core_chars"] == 168
    assert item["ending_core_semantic_hit_count"] == 0
    assert item["ending_core_weak_hit_count"] == 2
    assert item["ending_core_deflating"] is True


@pytest.mark.asyncio
async def test_quality_trend_backfills_nested_t08_t15_guard_fields_for_legacy_rows(task_session):
    """旧版只保存嵌套 guard 时，趋势仍应还原 T-08/T-15 指标。"""
    user = User(id=930, username="quality-legacy-t08-t15", email="quality-legacy-t08-t15@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-legacy-t08-t15-project", user_id=user.id, title="旧快照静态章末测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="历史正文",
        metadata_={
            "quality_metrics": {},
            "story_progression_guard": {
                "static_description_risk": True,
                "static_description_runs": {"static_paragraph_count": 5, "max_static_run": 4},
                "ending_pressure": {
                    "ending_pressure_passed": False,
                    "ending_semantic_hit_count": 0,
                    "ending_weak_hit_count": 2,
                    "flat_closure_markers": ["终于结束"],
                    "ending_core_chars": 180,
                    "ending_core_semantic_hit_count": 0,
                    "ending_core_weak_hit_count": 2,
                    "ending_core_deflating": True,
                },
            },
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    item = payload["chapters"][0]
    assert item["static_paragraph_count"] == 5
    assert item["max_static_run"] == 4
    assert item["ending_pressure_passed"] is False
    assert item["ending_semantic_hit_count"] == 0
    assert item["ending_weak_hit_count"] == 2
    assert item["flat_closure_markers"] == ["终于结束"]
    assert item["ending_core_chars"] == 180
    assert item["ending_core_deflating"] is True


def test_quality_trend_t08_t15_field_contract_has_reverse_guard():
    import inspect
    from app.api.routers import novels as novels_module

    source = inspect.getsource(novels_module.get_quality_trend)
    required = (
        '"static_paragraph_count": metrics.get("static_paragraph_count")',
        '"max_static_run": metrics.get("max_static_run")',
        '"ending_semantic_hit_count": metrics.get("ending_semantic_hit_count")',
        '"ending_core_deflating": metrics.get("ending_core_deflating")',
    )
    for item in required:
        assert item in source
    sabotaged = source.replace(required[0], "", 1)
    with pytest.raises(AssertionError):
        assert required[0] in sabotaged


@pytest.mark.asyncio
async def test_quality_trend_aggregates_warning_codes_and_redacts_invalid_or_excess_patch_suggestions(task_session):
    user = User(id=921, username="quality-warning-trend", email="quality-warning-trend@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-warning-trend-project", user_id=user.id, title="告警趋势测试")
    task_session.add_all([user, project])
    await task_session.flush()

    chapter_one = Chapter(project_id=project.id, chapter_number=1, status="successful")
    chapter_two = Chapter(project_id=project.id, chapter_number=2, status="successful")
    task_session.add_all([chapter_one, chapter_two])
    await task_session.flush()
    patch_suggestions = [
        {"code": f"patch_{index}", "suggestion": f"修复建议 {index}"}
        for index in range(9)
    ]
    version_one = ChapterVersion(
        chapter_id=chapter_one.id,
        content="第一章正文",
        metadata_={
            "quality_gate": {
                "warnings": [
                    {"code": "continuity_inherit_missing"},
                    {"code": "focus_character_missing"},
                    "not-a-warning",
                    {"code": ""},
                ],
                "patch_suggestions": [*patch_suggestions, "not-a-patch"],
            },
        },
    )
    version_two = ChapterVersion(
        chapter_id=chapter_two.id,
        content="第二章正文",
        metadata_={
            "quality_gate": {
                "warnings": [
                    {"code": "focus_character_missing"},
                    {"code": "scene_fulfillment_uncertain"},
                ],
            },
        },
    )
    task_session.add_all([version_one, version_two])
    await task_session.flush()
    chapter_one.selected_version_id = version_one.id
    chapter_two.selected_version_id = version_two.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    assert payload["warning_counts"] == {
        "continuity_inherit_missing": 1,
        "focus_character_missing": 2,
        "scene_fulfillment_uncertain": 1,
    }
    first_chapter, second_chapter = payload["chapters"]
    assert first_chapter["warning_codes"] == ["continuity_inherit_missing", "focus_character_missing"]
    assert second_chapter["warning_codes"] == ["focus_character_missing", "scene_fulfillment_uncertain"]
    assert first_chapter["patch_suggestions"] == patch_suggestions[:8]
    assert second_chapter["patch_suggestions"] == []


@pytest.mark.asyncio
async def test_quality_trend_preserves_short_sample_event_density_and_optional_metrics(task_session):
    user = User(id=922, username="quality-short-trend", email="quality-short-trend@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-short-trend-project", user_id=user.id, title="短样本趋势测试")
    task_session.add_all([user, project])
    await task_session.flush()
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add(chapter)
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="短正文",
        metadata_={
            "quality_metrics": {
                "word_count": 120,
                "event_density_evaluated": False,
                "event_density_skip_reason": "sample_too_short",
            },
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    item = payload["chapters"][0]
    assert item["event_density_evaluated"] is False
    assert item["event_density_skip_reason"] == "sample_too_short"
    assert item["focus_character_names"] == []
    assert item["focus_character_hit_count"] is None
    assert item["missing_focus_characters"] == []
    assert item["repeated_paragraph_count"] is None


@pytest.mark.asyncio
async def test_quality_trend_uses_runtime_gate_for_rejected_chapter_without_selected_version(task_session):
    user = User(id=923, username="quality-runtime-gate", email="quality-runtime-gate@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-runtime-gate-project", user_id=user.id, title="运行态趋势测试")
    rejected = Chapter(
        project_id=project.id,
        chapter_number=1,
        status="evaluation_failed",
        real_summary=json.dumps({
            "generation_runtime": {
                "quality_gate": {
                    "blockers": [{"code": "ending_pressure_missing"}],
                    "warnings": [{"code": "continuity_inherit_missing"}],
                    "patch_suggestions": [{"code": "ending_pressure_missing", "suggestion": "补一个未解风险。"}],
                    "exemptions": ["short_chapter"],
                }
            }
        }, ensure_ascii=False),
    )
    malformed = Chapter(
        project_id=project.id,
        chapter_number=2,
        status="evaluation_failed",
        real_summary="{not-json",
    )
    task_session.add_all([user, project, rejected, malformed])
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    first, second = payload["chapters"]
    assert first["blocker_codes"] == ["ending_pressure_missing"]
    assert first["warning_codes"] == ["continuity_inherit_missing"]
    assert first["patch_suggestions"] == [{"code": "ending_pressure_missing", "suggestion": "补一个未解风险。"}]
    assert first["exemptions"] == ["short_chapter"]
    assert second["blocker_codes"] == []
    assert second["warning_codes"] == []
    assert payload["blocker_counts"] == {"ending_pressure_missing": 1}
    assert payload["warning_counts"] == {"continuity_inherit_missing": 1}
    assert payload["exemption_counts"] == {"short_chapter": 1}


def test_quality_trend_redacts_previous_chapter_text_from_runtime_patch():
    patch = {
        "code": "continuity_inherit_missing",
        "suggestion": "在开篇承接风险。（待承接：秘密正文不得出现在趋势 API）",
    }
    assert _redact_quality_trend_patch_suggestions([patch]) == [{
        "code": "continuity_inherit_missing",
        "suggestion": "在开篇承接风险。（待承接：上一章遗留）",
    }]
    assert _redact_quality_trend_patch_suggestions(["bad", {"code": "", "suggestion": "x"}]) == []

@pytest.mark.asyncio
async def test_quality_trend_backfills_score_and_scene_warning_from_historical_story_guard(task_session):
    user = User(id=924, username="quality-history-fallback", email="quality-history-fallback@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-history-fallback-project", user_id=user.id, title="历史快照兼容测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="历史正文",
        metadata_={
            "quality_metrics": {
                "word_count": 1300,
                "ending_pressure_passed": True,
                "reversal_signal_count": 2,
                "reversal_in_late_section": True,
                "speaker_count": 2,
                "dominant_speaker_ratio": 0.5,
                "hard_scene_cut_count": 1,
                "summary_scene_cut_count": 1,
                "scene_transition_warning": True,
            },
            "story_progression_guard": {"score": 777},
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    item = payload["chapters"][0]
    assert item["score"] == 777
    assert item["reversal_signal_count"] == 2
    assert item["reversal_in_late_section"] is True
    assert item["speaker_count"] == 2
    assert item["dominant_speaker_ratio"] == 0.5
    assert item["hard_scene_cut_count"] == 1
    assert item["summary_scene_cut_count"] == 1
    assert item["scene_transition_warning"] is True

@pytest.mark.asyncio
async def test_quality_trend_readonly_backfills_observability_from_historical_content(task_session):
    user = User(id=925, username="quality-history-observability", email="quality-history-observability@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-history-observability-project", user_id=user.id, title="历史观测回填测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    content = "\n".join([
        "“先走。”林七说。",
        "“别回头。”沈舟说。",
        "这一切都平静下来，谁也没有再开口。",
        "第二天，林七来到旧码头。",
        "她沿楼梯往下走。" * 60 + "后来她发现账簿是伪造的，真正的钥匙在照片背面。",
    ])
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content=content,
        metadata_={"quality_metrics": {"word_count": 1300}},
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    item = payload["chapters"][0]
    assert item["reversal_signal_count"] >= 1
    assert item["reversal_in_late_section"] is True
    assert item["speaker_count"] == 2
    assert item["hard_scene_cut_count"] == 1
    assert item["summary_scene_cut_count"] == 1
    # Read-only contract: the historical version metadata remains untouched.
    assert version.metadata["quality_metrics"] == {"word_count": 1300}


def test_quality_trend_backfill_contract_detects_removed_content_recompute():
    import inspect
    import pytest
    from app.api.routers import novels as novels_module
    source = inspect.getsource(novels_module._backfill_quality_observability_metrics)
    assert "PipelineOrchestrator._evaluate_reversal_quality" in source
    sabotaged = source.replace("PipelineOrchestrator._evaluate_reversal_quality(text)", "{}", 1)
    with pytest.raises(AssertionError):
        assert "PipelineOrchestrator._evaluate_reversal_quality(text)" in sabotaged

@pytest.mark.asyncio
async def test_quality_trend_backfills_explicit_null_observability_fields(task_session):
    user = User(id=926, username="quality-null-observability", email="quality-null-observability@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-null-observability-project", user_id=user.id, title="显式空值回填测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    content = "\n".join([
        "“先走。”林七说。",
        "“别回头。”沈舟说。",
        "这一切都平静下来，谁也没有再开口。",
        "第二天，林七来到旧码头。",
        "她沿楼梯往下走。" * 60 + "后来她发现账簿是伪造的，真正的钥匙在照片背面。",
    ])
    null_metrics = {
        "word_count": 1300,
        "reversal_signal_count": None,
        "reversal_in_late_section": None,
        "speaker_count": None,
        "dominant_speaker_ratio": None,
        "hard_scene_cut_count": None,
        "summary_scene_cut_count": None,
        "scene_transition_warning": None,
        "dialogue_ratio": None,
        "action_ratio": None,
        "description_ratio": None,
    }
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(chapter_id=chapter.id, content=content, metadata_={"quality_metrics": null_metrics})
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    item = payload["chapters"][0]
    assert item["reversal_signal_count"] >= 1
    assert item["reversal_in_late_section"] is True
    assert item["speaker_count"] == 2
    assert item["hard_scene_cut_count"] == 1
    assert item["summary_scene_cut_count"] == 1
    assert item["dialogue_ratio"] is not None
    assert item["action_ratio"] is not None
    assert item["description_ratio"] is not None
    assert version.metadata["quality_metrics"]["speaker_count"] is None

@pytest.mark.asyncio
async def test_quality_trend_readonly_backfills_event_density_evaluated_without_mutating_metadata(task_session):
    user = User(id=928, username="quality-density-history", email="quality-density-history@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-density-history-project", user_id=user.id, title="历史密度状态测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    original_metrics = {
        "word_count": 2400,
        "event_density_passed": True,
        "state_change_interval_passed": True,
        "long_chapter_density_passed": True,
        "event_density_evaluated": None,
    }
    version = ChapterVersion(chapter_id=chapter.id, content="历史正文", metadata_={"quality_metrics": original_metrics})
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    item = payload["chapters"][0]
    assert item["event_density_evaluated"] is True
    assert item["event_density_passed"] is True
    assert version.metadata["quality_metrics"]["event_density_evaluated"] is None


@pytest.mark.asyncio
async def test_quality_trend_readonly_backfills_historical_mission_quality_codes(task_session):
    user = User(id=927, username="quality-history-mission", email="quality-history-mission@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-history-mission-project", user_id=user.id, title="历史任务书体检测试")
    chapter = Chapter(project_id=project.id, chapter_number=2, status="successful")
    mission = {
        "scene_list": [{"turn": "让局势发生变化"}],
        "focus_characters": ["主角", "男主"],
        "dialogue_strategy": {"purpose": ["试探"]},
        "continuity_anchor": {"inherit_from_previous": []},
    }
    version = ChapterVersion(
        chapter_id=None,
        content="历史正文",
        metadata_={
            "chapter_mission": mission,
            "quality_metrics": {"target_word_count": 2500, "mission_quality_codes": None},
        },
    )
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version.chapter_id = chapter.id
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )
    item = payload["chapters"][0]
    assert set(item["mission_quality_codes"]) == {
        "mission_scene_too_few", "mission_turn_placeholder", "mission_inherit_empty",
        "mission_focus_placeholder",
    }
    assert version.metadata["quality_metrics"]["mission_quality_codes"] is None



@pytest.mark.asyncio
async def test_quality_trend_readonly_backfills_historical_continuity_metrics(task_session):
    user = User(id=928, username="quality-history-continuity", email="quality-history-continuity@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-history-continuity-project", user_id=user.id, title="历史承接观测测试")
    chapter = Chapter(project_id=project.id, chapter_number=2, status="successful")
    mission = {"continuity_anchor": {"inherit_from_previous": ["门外脚步声逼近"]}}
    content = "林七翻查旧账，始终没有提到前章的危险。" * 80 + "门外脚步声逼近，他终于握紧钥匙。"
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content=content,
        metadata_={
            "chapter_mission": mission,
            "quality_metrics": {"word_count": 1600},
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    item = payload["chapters"][0]
    assert item["continuity_inherit_missing"] is False
    assert item["continuity_inherit_late"] is True
    assert item["continuity_inherit_hit_count"] == 0
    assert item["inherit_hit_count"] == 0
    assert item["continuity_inherit_total_hit_count"] == 1
    assert item["continuity_inherit_match_mode"] == "exact_or_two_term_semantic"
    assert version.metadata["quality_metrics"] == {"word_count": 1600}


def test_quality_trend_continuity_backfill_contract_detects_removed_e07_recompute():
    import inspect
    import pytest
    from app.api.routers import novels as novels_module
    source = inspect.getsource(novels_module._backfill_quality_observability_metrics)
    assert "PipelineOrchestrator._evaluate_continuity_inherit" in source
    sabotaged = source.replace("PipelineOrchestrator._evaluate_continuity_inherit(", "{}(", 1)
    with pytest.raises(AssertionError):
        assert "PipelineOrchestrator._evaluate_continuity_inherit(" in sabotaged

def test_quality_trend_mission_backfill_contract_detects_removed_e10_recompute():
    import inspect
    import pytest
    from app.api.routers import novels as novels_module
    source = inspect.getsource(novels_module._backfill_quality_observability_metrics)
    assert "PipelineOrchestrator._evaluate_mission_quality" in source
    sabotaged = source.replace("PipelineOrchestrator._evaluate_mission_quality(", "{}(", 1)
    with pytest.raises(AssertionError):
        assert "PipelineOrchestrator._evaluate_mission_quality(" in sabotaged


@pytest.mark.asyncio
async def test_quality_trend_reads_exemptions_from_quality_gates_snapshot(task_session):
    user = User(id=936, username="quality-trend-gates-snapshot", email="quality-trend-gates-snapshot@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-trend-gates-snapshot-project", user_id=user.id, title="质量门快照趋势测试")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful")
    task_session.add_all([user, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        content="正文",
        metadata_={
            "quality_metrics": {
                "word_count": 1200,
                "quality_gate_passed": True,
                "self_critique_final_score": 77.1,
                "self_critique_critical_count": 1,
                "self_critique_major_count": 5,
                "selected_critique_source": "self_critique_after_consistency",
            },
            "quality_gates": {
                "structural_gate": {
                    "passed": True,
                    "blockers": [],
                    "warnings": [],
                    "patch_suggestions": [],
                    "exemptions": ["ending_pressure_missing"],
                    "critique_exemption_applied": ["ending_pressure_missing"],
                },
            },
        },
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    assert payload["chapters"][0]["exemptions"] == ["ending_pressure_missing"]
    assert payload["chapters"][0]["critique_exemption_applied"] == ["ending_pressure_missing"]
    assert payload["chapters"][0]["quality_gate_passed"] is True
    assert payload["chapters"][0]["self_critique_final_score"] == 77.1
    assert payload["chapters"][0]["self_critique_critical_count"] == 1
    assert payload["chapters"][0]["self_critique_major_count"] == 5
    assert payload["chapters"][0]["selected_critique_source"] == "self_critique_after_consistency"
    assert payload["exemption_counts"] == {"ending_pressure_missing": 1}


@pytest.mark.asyncio
async def test_quality_trend_reports_rejected_runtime_gate_as_false(task_session):
    user = User(id=937, username="quality-trend-rejected-gate", email="quality-trend-rejected-gate@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-trend-rejected-gate-project", user_id=user.id, title="拒绝质量门趋势测试")
    chapter = Chapter(
        project_id=project.id, chapter_number=1, status="evaluation_failed",
        real_summary=json.dumps({"generation_runtime": {"quality_gate": {
            "passed": False, "blockers": [{"code": "critical_consistency_unresolved"}],
            "warnings": [], "exemptions": ["ending_pressure_missing"],
            "critique_exemption_applied": ["ending_pressure_missing"],
            "self_critique_final_score": 77.1,
            "self_critique_critical_count": 1,
            "self_critique_major_count": 5,
            "selected_critique_source": "self_critique_after_consistency",
        }, "runtime_metadata": {"actual_word_count": 1000}}}, ensure_ascii=False),
    )
    task_session.add_all([user, project, chapter])
    await task_session.commit()

    payload = await get_quality_trend(
        project.id, session=task_session, current_user=SimpleNamespace(id=user.id),
    )

    assert payload["chapters"][0]["quality_gate_passed"] is False
    assert payload["chapters"][0]["exemptions"] == ["ending_pressure_missing"]
    assert payload["chapters"][0]["critique_exemption_applied"] == ["ending_pressure_missing"]
    assert payload["chapters"][0]["self_critique_final_score"] == 77.1
    assert payload["chapters"][0]["self_critique_critical_count"] == 1
    assert payload["chapters"][0]["self_critique_major_count"] == 5
    assert payload["chapters"][0]["selected_critique_source"] == "self_critique_after_consistency"
