"""Local scoring parity: structural residue, false positives, ranking and gate wiring."""
import json

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator


TASK_JSON = '{"chapter_purpose":"调查失踪"}'
BLUEPRINT_LINK = "[蓝图](memo)"
PROSE = "\n".join(
    f"第{index}轮，沈砚推开铁门，发现账簿被调换。“交出钥匙！”他质问，守卫拒绝，他拿出证据反制。"
    "门外脚步逼近，他必须在期限前找到退路，否则会有危险。"
    for index in range(1, 19)
)


def _detect(text):
    return PipelineOrchestrator._detect_chapter_artifact_markers(text)


def _score(text):
    return PipelineOrchestrator._score_story_quality_candidate(
        content=text, violations=[], chapter_mission=None,
        target_word_count=1600, min_word_count=900,
    )


def _gate(text):
    return PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={}, content=text, violations=[], chapter_mission=None,
        target_word_count=1600, min_word_count=900,
    )


@pytest.mark.parametrize("payload", [
    {"chapter_purpose": "调查失踪"},
    {"pov": "沈砚"},
    {"scene_list": []},
    {"continuity_anchor": {"deliver_to_next": ["账簿"]}},
    {"dialogue_strategy": {"purpose": ["逼问"]}},
])
@pytest.mark.parametrize("indent", [None, 2])
def test_standalone_task_json_is_detected(payload, indent):
    residue = json.dumps(payload, ensure_ascii=False, indent=indent)
    guard = _detect(PROSE + "\n" + residue)
    assert guard["chapter_artifact_markers"] is True
    assert 1 <= guard["chapter_artifact_marker_count"] <= 5
    assert guard["chapter_artifact_marker_examples"]


@pytest.mark.parametrize("label", ["蓝图", "章节导演脚本", "写作任务", "上下文", "历史摘要", "长篇上下文"])
def test_standalone_task_link_is_detected(label):
    guard = _detect(f"  [{label}](memo)  ")
    assert guard["chapter_artifact_markers"] is True
    assert label in guard["chapter_artifact_marker_examples"][0]


@pytest.mark.parametrize("residue", [
    "```json\n" + TASK_JSON + "\n```",
    json.dumps({"notes": "旧事" * 120, "scene_list": []}, ensure_ascii=False),
    "{\n  \"chapter_purpose\": \"调查失踪\"\n}",
])
def test_fenced_and_long_task_json_keep_bounded_evidence(residue):
    guard = _detect(residue)
    assert guard["chapter_artifact_markers"] is True
    assert all(0 < len(item) <= 100 for item in guard["chapter_artifact_marker_examples"])


@pytest.mark.parametrize("narrative", [
    "他在信里看见 chapter_purpose 和 scene_list，仍旧不明白它们的含义。",
    '他读到 {"chapter_purpose":"调查失踪"}，把这段文字抄进日记。',
    '“{\"chapter_purpose\":\"调查失踪\"}”',
    '> {"chapter_purpose":"调查失踪"}',
    '{"chapter_purpose":"调查失踪"} 是他记住的原话。',
    '{"chapter_purpose_hint":"调查失踪","scene_listing":[]}',
    '{"message":"chapter_purpose","archive":{"scene_list":[]}}',
    '{\n  "archive": {\n    "scene_list": []\n  }\n}',
    "他沿着[蓝图](memo)上的线条摸到暗门。",
    "“[章节导演脚本](memo)”是信上抄录的文件名。",
    "> [蓝图](memo)",
    "[城市蓝图](memo)",
    "[蓝图书店](memo)",
    "[旅行笔记](https://example.test/blueprint)",
    "[chapter_purpose](memo)",
    "![蓝图](memo)",
])
def test_narrative_quotations_ordinary_links_and_similar_keys_are_not_artifacts(narrative):
    guard = _detect(narrative)
    assert guard == {
        "chapter_artifact_markers": False,
        "chapter_artifact_marker_count": 0,
        "chapter_artifact_marker_examples": [],
    }


@pytest.mark.parametrize("residue", [
    "## 场景1：开场", "【场景2｜暗门】", "扩写部分3：转折",
    "修订说明：补足压力", "写作要求：只交正文", "约350字", "**修订后的正文**",
])
def test_existing_detector_enhancements_remain_active(residue):
    assert _detect(residue)["chapter_artifact_markers"] is True


def test_evidence_count_is_capped_with_mixed_old_and_new_residue():
    text = "\n".join([TASK_JSON, BLUEPRINT_LINK, "约350字", *[f"## 场景{i}：开场" for i in range(8)], "**修订后的正文**"])
    guard = _detect(text)
    assert guard["chapter_artifact_markers"] is True
    assert guard["chapter_artifact_marker_count"] == len(guard["chapter_artifact_marker_examples"]) == 5
    assert all(len(item) <= 100 for item in guard["chapter_artifact_marker_examples"])


def _assert_penalty_contract(monkeypatch, content):
    detected = _score(content)
    assert detected["chapter_artifact_markers"] is True
    with monkeypatch.context() as scoped:
        scoped.setattr(PipelineOrchestrator, "_detect_chapter_artifact_markers", staticmethod(lambda _text: {
            "chapter_artifact_markers": False,
            "chapter_artifact_marker_count": 0,
            "chapter_artifact_marker_examples": [],
        }))
        neutral = _score(content)
    # Same text isolates the deduction from changes in length, dialogue or density.
    assert neutral["score"] - detected["score"] == 480
    assert detected["quality_penalty"] - neutral["quality_penalty"] == 480
    assert detected["eligibility_score"] == neutral["eligibility_score"]
    assert detected["quality_positive_score"] == neutral["quality_positive_score"]
    assert detected["chapter_artifact_penalty"] == 480
    assert neutral["chapter_artifact_penalty"] == 0
    for guard in (detected, neutral):
        snapshot = guard["quality_metric_snapshot"]
        for key in ("score", "quality_penalty", "quality_positive_score", "eligibility_score", "chapter_artifact_penalty", "chapter_artifact_marker_count"):
            assert snapshot[key] == guard[key]
        assert guard["score"] == guard["eligibility_score"] + guard["quality_positive_score"] - guard["quality_penalty"]
    for key in ("ending_pressure", "event_density", "static_description_runs", "focus_character_missing", "repetition_risk", "content_balance_penalty"):
        assert detected[key] == neutral[key]


@pytest.mark.parametrize("residue", [TASK_JSON, BLUEPRINT_LINK, "约350字", TASK_JSON + "\n" + BLUEPRINT_LINK])
def test_artifact_penalty_is_exactly_480_once_and_auditable(monkeypatch, residue):
    _assert_penalty_contract(monkeypatch, residue + "\n" + PROSE)


@pytest.mark.parametrize("residue", [TASK_JSON, BLUEPRINT_LINK])
@pytest.mark.parametrize("dirty_first", [True, False])
def test_fallback_ranking_demotes_actual_residue(residue, dirty_first):
    clean = {"content": PROSE, "metadata": {"guardrail": {"passed": True}}}
    dirty = {"content": residue + "\n" + PROSE, "metadata": {"guardrail": {"passed": True}}}
    versions = [dirty, clean] if dirty_first else [clean, dirty]
    best, summary = PipelineOrchestrator._fallback_select_best_version(
        versions, chapter_mission=None, target_word_count=1600, min_word_count=900,
    )
    assert versions[best] is clean
    assert [item["heuristic_rank"] for item in summary["candidates"]] == [1, 2]
    assert summary["candidates"][0]["chapter_artifact_penalty"] == 0
    assert summary["candidates"][1]["chapter_artifact_penalty"] == 480


@pytest.mark.parametrize("residue", [TASK_JSON, BLUEPRINT_LINK])
def test_cleanup_preserves_actual_task_residue_and_gate_rejects_it(residue):
    original = "## 第三章\n" + residue + "\n" + PROSE
    cleaned, cleanup = PipelineOrchestrator._apply_deterministic_cleanup(
        content=original, chapter_mission=None, target_word_count=1600, min_word_count=900,
    )
    assert cleanup["applied"] is True
    assert "## 第三章" in cleanup["removed_examples"]
    assert residue in cleaned
    assert residue not in cleanup["removed_examples"]
    clean_summaries, clean_gate = _gate(PROSE)
    assert clean_gate["passed"] is True
    summaries, gate = _gate(cleaned)
    guard = summaries["story_progression_guard"]
    assert guard["chapter_artifact_markers"] is True
    assert guard["quality_metric_snapshot"]["chapter_artifact_marker_examples"]
    assert gate["passed"] is False
    assert {item["code"] for item in gate["blockers"]} == {"chapter_artifact_markers"}
    assert "chapter_artifact_markers" in gate["quality_issue_codes"]


def test_presentation_cleanup_and_ordinary_link_remain_penalty_free():
    original = "## 第三章\n[旅行笔记](memo)\n" + PROSE
    cleaned, cleanup = PipelineOrchestrator._apply_deterministic_cleanup(
        content=original, chapter_mission=None, target_word_count=1600, min_word_count=900,
    )
    assert cleanup["applied"] is True
    assert "[旅行笔记](memo)" in cleaned
    assert _score(cleaned)["chapter_artifact_penalty"] == 0
    assert _gate(cleaned)[1]["passed"] is True
