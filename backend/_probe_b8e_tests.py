# -*- coding: utf-8 -*-
"""批 8-E 反向验证：把 T-13 / T-14 的每一处判据改回坏写法，确认有测试变红。

方法与批 6 / 批 7-C 相同 —— **文本变异**，不是 `setattr`：这两个缺陷的判据全部
写在函数体里（`is False` / `is not False` / 三分支 if），换掉类属性碰不到它们。
所以这里直接改 pipeline_orchestrator.py 的源码字符串，跑一次目标测试，然后在
`finally` 里还原，最后比对 sha256 —— 变异脚本本身就是最危险的东西，必须证明它
没有把源文件留在改动过的状态。

判定标准：每一个变异都必须让**至少一个**测试变红。一个变异全绿 = 那处判据没有
测试守着，改回坏写法不会被发现。
"""
import hashlib
import subprocess
import sys
from pathlib import Path

TARGET = Path("app/services/pipeline_orchestrator.py")
TEST_FILE = "app/services/test_generation_quality_guards.py"

# (编号, 说明, 原文片段, 变异后片段, 期望变红的测试选择器)
CASES = [
    # ---------- T-13：判定本身 ----------
    (
        "T13-1",
        "把「不适用」改回无条件 True（原始缺陷形态）",
        '        elif dialogue_markers <= 0:\n            # 没要求对话，正文也确实没有对话 → 该维度不适用，不加分也不减分\n            passed = None\n            applicable = False',
        '        elif dialogue_markers <= 0:\n            passed = True\n            applicable = True',
        "TestDialogueStateTriState",
    ),
    (
        "T13-2",
        "把判定顺序改成交接文档 D-07 的写法（零对话优先判 None）",
        '        marker_count = cls._count_dialogue_state_change_markers(text)\n        if expected_dialogue:',
        '        marker_count = cls._count_dialogue_state_change_markers(text)\n        if dialogue_markers <= 0:\n            return {\n                "expected_dialogue": expected_dialogue,\n                "dialogue_expectation_declared": bool(expected_dialogue),\n                "dialogue_state_applicable": False,\n                "dialogue_marker_count": dialogue_markers,\n                "state_change_marker_count": marker_count,\n                "dialogue_changes_state": None,\n            }\n        if expected_dialogue:',
        "TestDialogueStateTriState",
    ),
    (
        "T13-3",
        "把未声明预期的门槛从 1 提到 2（追认一个没提过的要求）",
        "    UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR = 1",
        "    UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR = 2",
        "TestDialogueStateTriState",
    ),
    # ---------- T-13：计分 ----------
    (
        "T13-4",
        "计分改回两分支真假判断（None 被当失败倒扣 140）",
        "        if dialogue_changes_state is True:\n            score += 140\n        elif dialogue_changes_state is False:\n            score -= 140",
        "        score += 140 if dialogue_changes_state else -140",
        "TestDialogueStateTriState",
    ),
    # ---------- T-13：四层消费点 ----------
    (
        "T13-5",
        "第 1 层 gate blocker 判据改成真假判断（None 进 blocker）",
        '                and "dialogue_changes_state" in story_guard\n                and story_guard.get("dialogue_changes_state") is False',
        '                and "dialogue_changes_state" in story_guard\n                and not story_guard.get("dialogue_changes_state")',
        "TestDialogueStateTriStateWiringAcrossLayers",
    ),
    (
        "T13-6",
        "第 2 层定向修复清单判据改成真假判断（给不适用维度派返修）",
        '        if guard.get("expected_dialogue") and guard.get("dialogue_changes_state") is False:',
        '        if guard.get("expected_dialogue") and not guard.get("dialogue_changes_state"):',
        "TestDialogueStateTriStateWiringAcrossLayers",
    ),
    (
        "T13-7",
        "第 3 层重试原因码判据改成真假判断（凭没测过触发重试）",
        '        if story_guard.get("expected_dialogue") and story_guard.get("dialogue_changes_state") is False:\n            reasons.append("dialogue_does_not_change_state")',
        '        if story_guard.get("expected_dialogue") and not story_guard.get("dialogue_changes_state"):\n            reasons.append("dialogue_does_not_change_state")',
        "TestDialogueStateTriStateWiringAcrossLayers",
    ),
    (
        "T13-8",
        "第 4 层 AI 复核覆盖判据改成真假判断（凭不适用换稿）",
        '            or (ai_candidate.get("expected_dialogue") and ai_candidate.get("dialogue_changes_state") is False)',
        '            or (ai_candidate.get("expected_dialogue") and not ai_candidate.get("dialogue_changes_state"))',
        "TestDialogueStateTriStateWiringAcrossLayers",
    ),
    (
        "T13-9",
        "guard/snapshot 重新套上 bool()（把 None 压回 False）",
        '            "dialogue_changes_state": dialogue_state.get("dialogue_changes_state"),\n            "dialogue_expectation_declared": dialogue_state.get("dialogue_expectation_declared"),',
        '            "dialogue_changes_state": bool(dialogue_state.get("dialogue_changes_state")),\n            "dialogue_expectation_declared": dialogue_state.get("dialogue_expectation_declared"),',
        "TestDialogueStateTriState",
    ),
    # ---------- T-14：短路分支 ----------
    (
        "T14-1",
        "短路分支改回报「达标」（原始缺陷形态）",
        '                    "event_density_passed": None,\n                    "long_chapter_density_passed": None,\n                    "state_change_interval_passed": None,',
        '                    "event_density_passed": True,\n                    "long_chapter_density_passed": True,\n                    "state_change_interval_passed": True,',
        "TestEventDensityNotEvaluated",
    ),
    (
        "T14-2",
        "比率兜底成矛盾数值（推进单元 0 个却推进率 100%）",
        '                    "progression_unit_rate": None,\n                    "event_density_per_1000": None,',
        '                    "progression_unit_rate": 1.0,\n                    "event_density_per_1000": 0.0,',
        "TestEventDensityNotEvaluated",
    ),
    (
        "T14-3",
        "去掉 event_density_evaluated 标记（逼消费方靠 passed is None 反推）",
        '                    "event_density_evaluated": False,\n                    "event_density_skip_reason": "sample_too_short",',
        '                    "event_density_skip_reason": "sample_too_short",',
        "TestEventDensityNotEvaluated",
    ),
    (
        "T14-4",
        "下调评估下限到 200 字（分位统计失去意义）",
        "    EVENT_DENSITY_MIN_SAMPLE_CHARS = 800",
        "    EVENT_DENSITY_MIN_SAMPLE_CHARS = 200",
        "TestEventDensityNotEvaluated",
    ),
    (
        "T14-5",
        "正常路径不再标 evaluated=True",
        '            "event_density_evaluated": True,\n            "event_density_passed": event_density_passed,',
        '            "event_density_passed": event_density_passed,',
        "TestEventDensityNotEvaluated",
    ),
    # ---------- T-14：计分 ----------
    (
        "T14-6",
        "密度计分改回两分支（None 被当失败倒扣 490）",
        "            _metric_value = event_density.get(_metric_key)\n            if _metric_value is True:\n                score += _bonus\n            elif _metric_value is False:\n                score -= _penalty",
        "            _metric_value = event_density.get(_metric_key)\n            score += _bonus if _metric_value else -_penalty",
        "TestEventDensityNotEvaluated",
    ),
    # ---------- T-14：快照与消费点 ----------
    (
        "T14-7",
        "快照给三个 passed 重新套 bool()",
        '            "event_density_passed": event_density.get("event_density_passed"),\n            "chapter_artifact_markers": artifact_markers.get("chapter_artifact_markers"),',
        '            "event_density_passed": bool(event_density.get("event_density_passed")),\n            "chapter_artifact_markers": artifact_markers.get("chapter_artifact_markers"),',
        "TestEventDensityNotEvaluated",
    ),
    (
        "T14-8",
        "快照比率恢复 `, 0` 兜底（前端会画出一根 0 的进度条）",
        '            "progression_unit_rate": event_density.get("progression_unit_rate"),\n            "event_density_per_1000": event_density.get("event_density_per_1000"),',
        '            "progression_unit_rate": event_density.get("progression_unit_rate", 0),\n            "event_density_per_1000": event_density.get("event_density_per_1000", 0),',
        "TestEventDensityNotEvaluated",
    ),
    (
        "T14-9",
        "定向修复清单的 pacing 判据改成真假判断",
        '        if guard.get("event_density_passed") is False or guard.get("state_change_interval_passed") is False:',
        '        if not guard.get("event_density_passed") or not guard.get("state_change_interval_passed"):',
        "TestEventDensityNotEvaluatedWiringAcrossLayers",
    ),
    (
        "T14-10",
        "gate 密度 blocker 判据改成真假判断（短章被密度门拦）",
        '                and story_guard.get("event_density_passed") is False\n                and not density_soft_pass\n                and (critique_score is None or critique_score < 70)',
        '                and not story_guard.get("event_density_passed")\n                and not density_soft_pass\n                and (critique_score is None or critique_score < 70)',
        "TestEventDensityNotEvaluatedWiringAcrossLayers",
    ),
    (
        "T14-11",
        "重试原因码的密度判据改成真假判断",
        '            and story_guard.get("event_density_passed") is False\n            and not density_soft_pass\n        ):\n            reasons.append("event_density_weak")',
        '            and not story_guard.get("event_density_passed")\n            and not density_soft_pass\n        ):\n            reasons.append("event_density_weak")',
        "TestEventDensityNotEvaluatedWiringAcrossLayers",
    ),
    (
        "T14-12",
        "把密度 blocker 的字数门槛降到 800 以下（软放行的安全前提失效）",
        "                story_word_count >= 1800\n                and story_guard.get(\"event_density_passed\") is False",
        "                story_word_count >= 600\n                and story_guard.get(\"event_density_passed\") is False",
        "TestEventDensityNotEvaluatedWiringAcrossLayers",
    ),
]


def digest() -> str:
    return hashlib.sha256(TARGET.read_bytes()).hexdigest()


def run(selector: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_FILE, "-k", selector, "-q", "-p", "no:randomly", "--no-header"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (proc.stdout or "").strip().splitlines()
    return proc.returncode == 0, tail[-1] if tail else "<no output>"


def main() -> int:
    before = digest()
    # 必须走二进制：read_text/write_text 会把 CRLF 归一成 LF 再写回 LF，
    # 于是即使内容"还原"了，文件的行尾也被整体改写过——摘要对不上，
    # git diff 会显示整个文件被重写。变异脚本改坏源文件是最不能接受的失败。
    original = TARGET.read_bytes()

    baseline_ok, baseline_line = run("TriState or NotEvaluated")
    print(f"基线：{'绿' if baseline_ok else '红'}  {baseline_line}")
    if not baseline_ok:
        print("基线就是红的，反向验证无意义。先修好再跑。")
        return 1

    failures = []
    for code, note, old, new, selector in CASES:
        old_bytes, new_bytes = old.encode("utf-8"), new.encode("utf-8")
        # 锚点也要按当前文件的行尾编码，否则 CRLF 文件里 
 一个都匹配不到
        if b"
" in original:
            old_bytes = old_bytes.replace(b"
", b"
")
            new_bytes = new_bytes.replace(b"
", b"
")
        if original.count(old_bytes) != 1:
            print(f"[{code}] 变异锚点不唯一（count={original.count(old_bytes)}）—— 脚本需要重新对齐源码")
            failures.append(code)
            continue
        try:
            TARGET.write_bytes(original.replace(old_bytes, new_bytes, 1))
            ok, line = run(selector)
        finally:
            TARGET.write_bytes(original)
        status = "漏网" if ok else "已捕获"
        print(f"[{code}] {status}  {note}")
        print(f"        {line}")
        if ok:
            failures.append(code)

    after = digest()
    print()
    print(f"源码摘要 before={before[:16]} after={after[:16]} {'一致' if before == after else '不一致！'}")
    if before != after:
        print("源文件没有被完整还原，立刻 git checkout。")
        return 2
    if failures:
        print(f"有 {len(failures)} 个变异没被任何测试捕获：{failures}")
        return 3
    print(f"全部 {len(CASES)} 个变异都被捕获。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
