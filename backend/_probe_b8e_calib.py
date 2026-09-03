# -*- coding: utf-8 -*-
"""批 8-E 定标探针：量化 T-13/T-14 三分支在真实评分器上的分差。"""
from app.services.pipeline_orchestrator import PipelineOrchestrator as P
from app.services.test_generation_quality_guards import (
    GOOD_DRAMATIC,
    _SAMPLE_MIN_WORDS,
    _SAMPLE_TARGET_WORDS,
)

DIALOGUE_MISSION = {"dialogue_strategy": {"mode": "攻防"}}


def _score(content, mission):
    return P._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=mission,
        target_word_count=_SAMPLE_TARGET_WORDS,
        min_word_count=_SAMPLE_MIN_WORDS,
    )


def test_probe():
    print()
    for label, mission in (("mission=None", None), ("expect_dialogue", DIALOGUE_MISSION)):
        g = _score(GOOD_DRAMATIC, mission)
        print(label, "score=", g["score"], "dcs=", g["dialogue_changes_state"],
              "expected=", g["expected_dialogue"], "codes=", g["quality_issue_codes"])

    # 无对话 + 要求对话 → False
    no_dialogue = "\n".join(
        f"第{i}段，他推开门走进屋里，发现桌上的钥匙不见了，于是决定沿着走廊往下追查线索，脚步声在身后响起。"
        for i in range(1, 40)
    )
    for label, mission in (("no_dialogue/None", None), ("no_dialogue/expect", DIALOGUE_MISSION)):
        g = _score(no_dialogue, mission)
        print(label, "len=", len(no_dialogue), "score=", g["score"], "dcs=", g["dialogue_changes_state"],
              "applicable=", g["quality_metric_snapshot"].get("dialogue_state_applicable"),
              "codes=", g["quality_issue_codes"])

    # 有对话但无状态变化
    flat_lines = []
    for i in range(1, 20):
        flat_lines.append(f"“第{i}天天气不错。”他说。")
        flat_lines.append("“是啊。”她点头。")
        flat_lines.append("“吃了吗？”")
        flat_lines.append("“吃了。”")
    flat = chr(10).join(flat_lines)
    g = _score(flat, None)
    print("flat_dialogue len=", len(flat), "score=", g["score"], "dcs=", g["dialogue_changes_state"])


def test_probe_layers():
    print()
    no_dialogue = chr(10).join(
        f"第{i}段，他推开门走进屋里，发现桌上的钥匙不见了，于是决定沿着走廊往下追查线索，脚步声在身后响起。"
        for i in range(1, 40)
    )
    # 第 1 层：结构质量门
    for label, mission in (("gate/None", None), ("gate/expect", DIALOGUE_MISSION)):
        _s, gate = P._evaluate_structural_quality_gate_for_content(
            review_summaries={},
            content=no_dialogue,
            violations=[],
            chapter_mission=mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        print(label, "passed=", gate["passed"],
              "blockers=", sorted({b["code"] for b in gate["blockers"]}))
    # 第 2 层：定向修复清单
    for label, mission in (("repair/None", None), ("repair/expect", DIALOGUE_MISSION)):
        g = _score(no_dialogue, mission)
        issues = P._build_structural_reader_polish_issues(g)
        print(label, "dims=", sorted({i["dimension"] for i in issues}))
    # 第 3 层：首稿重试
    for label, mission in (("retry/None", None), ("retry/expect", DIALOGUE_MISSION)):
        needs, guard, reasons = P._evaluate_first_draft_retry(
            content=no_dialogue,
            violations=[],
            chapter_mission=mission,
            target_word_count=_SAMPLE_TARGET_WORDS,
            min_word_count=_SAMPLE_MIN_WORDS,
        )
        print(label, "dcs=", guard["dialogue_changes_state"], "reasons=", sorted(reasons))


def test_probe_override():
    """隔离 dcs 分支：其它 or 支路全部置成「无风险」，两稿分差 <180。"""
    print()
    base = {
        "word_count": 2000, "dialogue_marker_count": 8,
        "mission_hit_count": 5, "scene_count": 0,
        "expected_dialogue": True, "ending_pressure_passed": True,
        "guardrail_passed": True, "static_description_risk": False,
        "scene_fulfillment_rate": 1.0,
    }
    for dcs in (None, False, True):
        ai = dict(base, index=0, dialogue_changes_state=dcs, score=900)
        fb = dict(base, index=1, dialogue_changes_state=True, score=900)
        override, _detail = P._should_override_ai_review_choice(
            ai_index=0, fallback_index=1,
            fallback_summary={"candidates": [ai, fb]},
        )
        print("ai_dcs=", dcs, "-> override=", override)


def test_probe_density_scoring():
    """T-14：三分支 vs 旧两分支的分差。旧写法把 None 当失败，合计倒扣 490。"""
    print()
    short = "他推开门，屋里空无一人。桌上放着一把钥匙，他捡起来决定去追。" * 4
    g = _score(short, None)
    snap = g["quality_metric_snapshot"]
    print("len=", len(short), "score=", g["score"])
    for k in ("event_density_evaluated", "event_density_skip_reason",
              "event_density_passed", "state_change_interval_passed",
              "long_chapter_density_passed", "progression_unit_rate",
              "event_density_per_1000", "state_change_window_pass_rate",
              "max_plain_unit_run_ratio", "progression_unit_count",
              "story_unit_count", "max_plain_unit_run"):
        print("  ", k, "=", repr(snap.get(k, "<MISSING>")))
    # 800 字边界：刚好达到下限就必须评估
    boundary = "他推开门，屋里空无一人。桌上放着一把钥匙，他捡起来决定去追。" * 28
    gb = _score(boundary, None)
    print("boundary len=", len(boundary),
          "evaluated=", gb["quality_metric_snapshot"]["event_density_evaluated"],
          "ed=", gb["event_density_passed"])


def test_probe_score_deltas(monkeypatch):
    """把密度三判定分别钉成 True / False / None，看总分增量。"""
    print()
    real = P._evaluate_event_density.__func__

    def make(value):
        def fake(cls, text, *, word_count):
            out = dict(real(P, text, word_count=word_count))
            out["event_density_passed"] = value
            out["state_change_interval_passed"] = value
            out["long_chapter_density_passed"] = value
            out["event_density_evaluated"] = value is not None
            return out
        return classmethod(fake)

    scores = {}
    for value in (True, False, None):
        monkeypatch.setattr(P, "_evaluate_event_density", make(value))
        scores[value] = _score(GOOD_DRAMATIC, None)["score"]
    print("scores=", scores)
    print("True-None=", scores[True] - scores[None], "None-False=", scores[None] - scores[False])


def test_probe_dcs_score_deltas(monkeypatch):
    print()
    real = P._evaluate_dialogue_changes_state.__func__

    def make(value):
        def fake(cls, text, *, expected_dialogue, dialogue_markers):
            out = dict(real(P, text, expected_dialogue=expected_dialogue, dialogue_markers=dialogue_markers))
            out["dialogue_changes_state"] = value
            return out
        return classmethod(fake)

    scores = {}
    for value in (True, False, None):
        monkeypatch.setattr(P, "_evaluate_dialogue_changes_state", make(value))
        scores[value] = _score(GOOD_DRAMATIC, None)["score"]
    print("dcs scores=", scores)
    print("True-None=", scores[True] - scores[None], "None-False=", scores[None] - scores[False])
