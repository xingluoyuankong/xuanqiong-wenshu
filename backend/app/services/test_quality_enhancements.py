from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_reversal_quality_observes_late_reversal_without_blocking():
    result = PipelineOrchestrator._evaluate_reversal_quality("前半段只是追查旧账。" * 20 + "后来他发现账簿是伪造的，真正的钥匙在照片背面。")
    assert result["reversal_signal_count"] >= 1
    assert result["reversal_in_late_section"] is True


def test_content_balance_penalizes_only_extreme_dialogue():
    dialogue = "\n".join(["“你看见他了吗？”\n“没有。”"] * 30)
    balance = PipelineOrchestrator._evaluate_content_balance(dialogue.splitlines(), word_count=1600)
    assert balance["dialogue_ratio"] > 0.8
    assert balance["content_balance_penalty"] >= 200


def test_mission_quality_marks_all_five_empty_mission_warnings():
    quality = PipelineOrchestrator._evaluate_mission_quality({}, 2500, chapter_number=2)
    assert set(quality["mission_quality_codes"]) == {
        "mission_scene_too_few", "mission_turn_placeholder", "mission_inherit_empty",
        "mission_dialogue_strategy_empty", "mission_focus_placeholder",
    }


def test_mission_quality_accepts_complete_mission():
    quality = PipelineOrchestrator._evaluate_mission_quality({
        "scene_list": [{"turn": "主角发现伪造账簿"}, {"turn": "证人反手交出钥匙"}],
        "continuity_anchor": {"inherit_from_previous": ["门外脚步声"]},
        "dialogue_strategy": {"purpose": ["试探"]},
        "focus_characters": ["林七"],
    }, 2500)
    assert quality["mission_quality_codes"] == []


def test_mission_quality_does_not_require_inherit_on_first_chapter():
    quality = PipelineOrchestrator._evaluate_mission_quality({}, 2500, chapter_number=1)
    assert "mission_inherit_empty" not in quality["mission_quality_codes"]

def test_quality_metric_snapshot_persists_the_same_total_score_as_the_story_guard():
    content = "顾沉推开门，发现账簿被换成空白纸。\n\n“谁拿走了它？”他问。\n\n楼下传来急刹声，电话说最后期限已经到了。" * 30
    result = PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission={"scene_list": [{"goal": "找到账簿", "conflict": "门卫阻拦", "turn": "线索反转", "end_hook": "期限已到"}]},
        target_word_count=1200,
        min_word_count=900,
    )
    assert result["quality_metric_snapshot"]["score"] == result["score"]


def _assert_e04_three_way_balance_contract() -> None:
    paragraphs = [
        "陆清言推开锈门，转身握住门闩，又伸手按住桌上的旧账簿。" * 3,
        "“钥匙交出来。”陆清言说。“你先说是谁出卖了我。”对方答道。" * 3,
        "雨雾压住空巷，潮气漫过石阶，远处没有半点人声。" * 3,
        "陆清言走进暗室，抬手拨开蛛网，把纸条塞进袖口。" * 3,
    ]
    result = PipelineOrchestrator._evaluate_content_balance(
        paragraphs,
        word_count=1600,
        character_names=["陆清言"],
    )
    assert result["action_paragraph_count"] == 2, result
    assert result["dialogue_paragraph_count"] == 1, result
    assert result["description_paragraph_count"] == 1, result
    assert result["action_ratio"] == 0.5, result
    assert result["dialogue_ratio"] == 0.25, result
    assert result["description_ratio"] == 0.25, result
    assert result["content_balance_penalty"] == 0, result


def test_e04_balance_exposes_all_three_mutually_exclusive_ratios():
    _assert_e04_three_way_balance_contract()


def test_e04_balance_flags_only_extreme_mix_without_blocker_side_effect():
    description = ["雾气压住空巷，潮水漫过石阶，远处灯影一动不动。" * 3] * 4
    result = PipelineOrchestrator._evaluate_content_balance(description, word_count=1600)
    assert result["description_ratio"] == 1.0
    assert result["action_ratio"] == 0.0
    assert result["content_balance_penalty"] == 320


def test_e04_balance_sabotage_dropping_action_classification_breaks_contract(monkeypatch):
    _assert_e04_three_way_balance_contract()
    original = PipelineOrchestrator._paragraph_has_character_action.__func__

    def ignore_actions(cls, plain, *, character_names=None):
        return False

    monkeypatch.setattr(PipelineOrchestrator, "_paragraph_has_character_action", classmethod(ignore_actions))
    import pytest
    with pytest.raises(AssertionError):
        _assert_e04_three_way_balance_contract()


def test_e04_score_snapshot_flattens_balance_metrics_for_trend_consumers():
    content = "\n".join([
        "陆清言推开锈门，转身握住门闩，又伸手按住桌上的旧账簿。" * 3,
        "“钥匙交出来。”陆清言说。“你先说是谁出卖了我。”对方答道。" * 3,
        "雨雾压住空巷，潮气漫过石阶，远处没有半点人声。" * 3,
        "陆清言走进暗室，抬手拨开蛛网，把纸条塞进袖口。" * 3,
    ])
    result = PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission={"focus_characters": ["陆清言"]},
        target_word_count=1000,
        min_word_count=800,
    )
    snapshot = result["quality_metric_snapshot"]
    for key in ("dialogue_ratio", "action_ratio", "description_ratio", "content_balance_penalty"):
        assert snapshot[key] == result[key]
    assert snapshot["action_ratio"] == 0.5
    assert snapshot["description_ratio"] == 0.25


def test_e02_e03_e05_score_snapshot_flattens_observability_metrics():
    content = "\n".join([
        "“先走。”林七说。",
        "“别回头。”沈舟说。",
        "这一切都平静下来，谁也没有再开口。",
        "第二天，林七来到旧码头。",
        "她沿楼梯往下走。" * 60 + "后来她发现账簿是伪造的，真正的钥匙在照片背面。",
    ])
    result = PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=None,
        target_word_count=1200,
        min_word_count=900,
    )
    snapshot = result["quality_metric_snapshot"]
    assert snapshot["reversal_signal_count"] >= 1
    assert snapshot["reversal_in_late_section"] is True
    assert snapshot["speaker_count"] == 2
    assert snapshot["dominant_speaker_ratio"] == 0.5
    assert snapshot["hard_scene_cut_count"] == 1
    assert snapshot["summary_scene_cut_count"] == 1
    for key in (
        "reversal_signal_count", "reversal_in_late_section", "speaker_count",
        "dominant_speaker_ratio", "hard_scene_cut_count", "summary_scene_cut_count",
        "scene_transition_warning",
    ):
        assert snapshot[key] == result[key]


def _assert_e02_e03_e05_flattening_contract(source: str) -> None:
    required = (
        '"reversal_signal_count": reversal_quality.get("reversal_signal_count", 0)',
        '"speaker_count": speaker_distribution.get("speaker_count", 0)',
        '"hard_scene_cut_count": scene_transition.get("hard_scene_cut_count", 0)',
    )
    for needle in required:
        assert source.count(needle) >= 2, needle


def test_e02_e03_e05_flattening_reverse_contract_detects_removed_snapshot_fields():
    import inspect
    import pytest
    source = inspect.getsource(PipelineOrchestrator._score_story_quality_candidate)
    _assert_e02_e03_e05_flattening_contract(source)
    sabotaged = source.replace(
        '"reversal_signal_count": reversal_quality.get("reversal_signal_count", 0)',
        '"reversal_quality": reversal_quality',
        1,
    )
    with pytest.raises(AssertionError):
        _assert_e02_e03_e05_flattening_contract(sabotaged)


def test_e10_mission_quality_flags_low_information_longform_mission():
    quality = PipelineOrchestrator._evaluate_mission_quality({
        "scene_list": [{"turn": "让局势发生变化"}],
        "focus_characters": ["主角", "男主"],
        "dialogue_strategy": {"purpose": ["试探"]},
        "continuity_anchor": {"inherit_from_previous": ["门外脚步声"]},
    }, 2500, chapter_number=2)
    assert set(quality["mission_quality_codes"]) == {
        "mission_scene_too_few", "mission_turn_placeholder", "mission_focus_placeholder",
    }


def test_e10_mission_quality_does_not_flag_one_scene_short_target_as_too_few():
    quality = PipelineOrchestrator._evaluate_mission_quality({
        "scene_list": [{"turn": "主角发现线索"}],
        "focus_characters": ["林七"],
        "dialogue_strategy": {"purpose": ["试探"]},
        "continuity_anchor": {"inherit_from_previous": ["门外脚步声"]},
    }, 1500, chapter_number=2)
    assert "mission_scene_too_few" not in quality["mission_quality_codes"]
    assert "mission_turn_placeholder" not in quality["mission_quality_codes"]


def _assert_e10_mission_contract(source: str) -> None:
    assert "len(scene_items) < 2" in source
    assert "placeholder_turns" in source
    assert "cls._collect_focus_character_names(focus_probe)" in source


def test_e10_mission_contract_reverse_detects_removed_placeholder_checks():
    import inspect
    import pytest
    source = inspect.getsource(PipelineOrchestrator._evaluate_mission_quality)
    _assert_e10_mission_contract(source)
    sabotaged = source.replace("len(scene_items) < 2", "len(scene_items) < 1", 1)
    with pytest.raises(AssertionError):
        _assert_e10_mission_contract(sabotaged)

