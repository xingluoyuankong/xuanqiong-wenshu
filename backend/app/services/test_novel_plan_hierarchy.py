from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.novel_plan_hierarchy import PlanHierarchyError, build_plan_hierarchy, validate_plan_hierarchy


def _project():
    blueprint = SimpleNamespace(
        title="雾港回声",
        genre="悬疑",
        style="克制",
        tone="冷峻",
        one_sentence_summary="追查记忆潮雾的真相。",
        full_synopsis="林七追查旧账册并面对被改写的记忆。",
        world_setting={
            "novel_outline": [
                {"stage": 1, "title": "潮痕初探", "expected_chapter_range": "1-2章", "goal": "建立谜团"},
                {"stage": 2, "title": "盟友裂痕", "expected_chapter_range": "3-4章", "goal": "关系转折"},
            ]
        },
    )
    outlines = [
        SimpleNamespace(id=1, chapter_number=1, title="潮痕", summary="发现账册。", metadata={"volume_number": 1, "volume_title": "潮痕初探", "word_count_estimate": 1200, "key_events": ["发现账册"]}),
        SimpleNamespace(id=2, chapter_number=2, title="雾门", summary="进入旧档案馆。", metadata={"volume_number": 1, "volume_title": "潮痕初探", "word_count_estimate": 1100, "scene_list": [{"scene": "档案馆", "goal": "寻找账册", "conflict": "守卫阻拦", "turn": "发现密门", "outcome": "进入"}]}),
        SimpleNamespace(id=3, chapter_number=3, title="裂痕", summary="盟友改变立场。", metadata={"volume_number": 2, "volume_title": "盟友裂痕", "word_count_estimate": 1300, "key_events": ["立场改变"]}),
        SimpleNamespace(id=4, chapter_number=4, title="回声", summary="线索进入下一阶段。", metadata={"volume_number": 2, "volume_title": "盟友裂痕", "word_count_estimate": 1400, "key_events": ["线索推进"]}),
    ]
    return SimpleNamespace(id="p-plan", title="项目", blueprint=blueprint, outlines=outlines)


def test_build_plan_derives_volumes_from_novel_outline_when_volume_plan_empty():
    hierarchy = build_plan_hierarchy(_project())
    assert hierarchy.book.target_text_units == 100_000
    assert len(hierarchy.volumes) == 2
    assert hierarchy.volumes[0].chapter_numbers == (1, 2)
    assert hierarchy.volumes[0].source == "chapter_outline.metadata"
    assert any(item["code"] == "volume_plan_derived_from_chapter_metadata" for item in hierarchy.diagnostics)
    assert hierarchy.chapters[1].scene_plans[0].goal == "寻找账册"
    assert hierarchy.content_digest


def test_build_plan_prefers_explicit_volume_plan():
    project = _project()
    project.blueprint.world_setting["volume_plan"] = [{"title": "明确卷", "chapter_range": "1-4章"}]
    hierarchy = build_plan_hierarchy(project)
    assert len(hierarchy.volumes) == 1
    assert hierarchy.volumes[0].title == "明确卷"
    assert hierarchy.volumes[0].source == "blueprint.volume_plan"


def test_validator_rejects_duplicate_chapter_numbers():
    hierarchy = build_plan_hierarchy(_project())
    duplicate = hierarchy.chapters + (hierarchy.chapters[0],)
    broken = type(hierarchy)(book=hierarchy.book, volumes=hierarchy.volumes, chapters=duplicate, diagnostics=hierarchy.diagnostics)
    with pytest.raises(PlanHierarchyError, match="chapter numbers"):
        validate_plan_hierarchy(broken)



def test_build_plan_reports_unassigned_chapters_when_metadata_has_gaps():
    project = _project()
    project.outlines.append(SimpleNamespace(id=5, chapter_number=5, title="尾声", summary="", metadata={}))
    hierarchy = build_plan_hierarchy(project)
    diagnostic = next(item for item in hierarchy.diagnostics if item["code"] == "chapters_without_volume_metadata")
    assert diagnostic["chapter_numbers"] == [5]
