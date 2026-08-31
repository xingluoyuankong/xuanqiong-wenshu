"""T-09：任务书焦点人物必须参与静态描写的行动主体识别。"""

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator


_FOCUS_NAME = "陆清言"
_ACTION_PARAGRAPH = (
    "陆清言推开锈门，转身握住裂开的门闩，又伸手按住桌上的旧账簿。"
    "雨水沿着他的袖口往下滴，他没有停住脚步，仍把钥匙塞进暗格。"
) * 3


def _assert_task_focus_name_counts_as_action() -> None:
    result = PipelineOrchestrator._estimate_static_description_runs(
        [_ACTION_PARAGRAPH],
        character_names=[_FOCUS_NAME],
    )
    assert result["static_paragraph_count"] == 0, result
    assert result["max_static_run"] == 0, result


def test_t09_task_focus_name_counts_as_character_action():
    """任意已解析焦点名执行动作时，不能因不在硬编码样例名单而判成静态。"""
    without_task_context = PipelineOrchestrator._estimate_static_description_runs([_ACTION_PARAGRAPH])
    assert without_task_context["static_paragraph_count"] == 1
    _assert_task_focus_name_counts_as_action()


def test_t09_focus_name_propagation_sabotage_is_detected(monkeypatch):
    """反向验证：丢掉任务书焦点名后，人物动作回归断言必须失败。"""
    _assert_task_focus_name_counts_as_action()
    original = PipelineOrchestrator._estimate_static_description_runs.__func__

    def drop_focus_names(cls, paragraphs, *, character_names=None):
        return original(cls, paragraphs)

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_estimate_static_description_runs",
        classmethod(drop_focus_names),
    )

    with pytest.raises(AssertionError):
        _assert_task_focus_name_counts_as_action()


def test_t09_scoring_passes_parsed_focus_names_to_static_detection(monkeypatch):
    """生产评分路径必须把任务书解析出的焦点名接入静态段检测。"""
    observed = {}
    original = PipelineOrchestrator._estimate_static_description_runs.__func__

    def capture_focus_names(cls, paragraphs, *, character_names=None):
        observed["character_names"] = list(character_names or [])
        return original(cls, paragraphs, character_names=character_names)

    monkeypatch.setattr(
        PipelineOrchestrator,
        "_estimate_static_description_runs",
        classmethod(capture_focus_names),
    )
    PipelineOrchestrator._score_story_quality_candidate(
        content=_ACTION_PARAGRAPH,
        violations=[],
        chapter_mission={"focus_characters": [_FOCUS_NAME]},
        target_word_count=500,
        min_word_count=450,
    )

    assert observed["character_names"] == [_FOCUS_NAME]

