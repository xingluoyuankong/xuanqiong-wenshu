from app.services.pipeline_orchestrator import PipelineOrchestrator


def _mission():
    return {
        "chapter_purpose": "找回遗失的账簿",
        "scene_list": [{
            "goal": "取回账簿",
            "conflict": "门卫拦住档案室",
            "turn": "一张湿照片揭露背叛",
            "end_hook": "门外脚步停住",
        }],
    }


def test_chinese_mission_keywords_extract_distinct_story_anchors_not_generic_words():
    keywords = PipelineOrchestrator._collect_fallback_mission_keywords(_mission())
    assert {"账簿", "照片"}.issubset(keywords)
    assert sum(anchor in keywords for anchor in ("账簿", "照片", "脚步")) >= 2
    assert "主角" not in keywords
    assert "冲突" not in keywords
    assert all(len(item) >= 2 for item in keywords)
    assert "突然" not in keywords
    assert "一张" not in keywords


def test_chinese_mission_anchor_hits_prevent_false_progression_penalty():
    content = "\n".join(
        f"第{index}段，沈砚攥紧账簿，发现湿照片背后的签名被人换过。门外脚步停住，他只能在倒计时结束前砸开档案室的窗。"
        for index in range(1, 19)
    )
    result = PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=_mission(),
        target_word_count=1200,
        min_word_count=900,
    )
    assert result["mission_hit_count"] >= 2
    assert {"账簿", "照片", "脚步"} & set(result["mission_hits"])


def test_generic_chinese_mission_words_do_not_create_false_hits():
    mission = {
        "chapter_purpose": "让主角推动局势变化",
        "scene_list": [{"goal": "完成目标", "conflict": "面对冲突", "turn": "局势变化", "end_hook": "继续推进"}],
    }
    keywords = PipelineOrchestrator._collect_fallback_mission_keywords(mission)
    assert not ({"主角", "局势", "变化", "目标", "冲突", "推进"} & set(keywords))

def test_chinese_mission_anchor_regression_detects_removed_term_extraction(monkeypatch):
    content = "\n".join(
        f"第{index}段，沈砚攥紧账簿，发现湿照片背后的签名被人换过。门外脚步停住，他只能在倒计时结束前砸开档案室的窗。"
        for index in range(1, 19)
    )
    control = PipelineOrchestrator._score_story_quality_candidate(
        content=content, violations=[], chapter_mission=_mission(), target_word_count=1200, min_word_count=900,
    )
    monkeypatch.setattr(PipelineOrchestrator, "_extract_chinese_mission_terms", staticmethod(lambda _value: []))
    degraded = PipelineOrchestrator._score_story_quality_candidate(
        content=content, violations=[], chapter_mission=_mission(), target_word_count=1200, min_word_count=900,
    )
    assert control["mission_hit_count"] >= 2
    assert degraded["mission_hit_count"] < 2
    assert control["score"] - degraded["score"] >= 360

