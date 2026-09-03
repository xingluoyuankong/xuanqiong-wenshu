# -*- coding: utf-8 -*-
"""把 97 次 Edit 按时间正序重放回 pipeline_orchestrator.py。

安全前提，缺一个都不能跑：
1. 只在 HEAD 版文本上重放（工作区已经被 checkout 回 HEAD，正好是重放起点）。
2. 每一条都要求 old_string 在当前文本里**恰好出现一次**。出现 0 次 = 前面漏了一
   步或这条编辑后来被另一条覆盖；出现多次 = 锚点不唯一，替换位置不确定。两种
   情况都停下来记账，不猜。
3. 行尾：jsonl 里的 old/new 都是 LF。工作区文件是 CRLF。所以统一在 LF 空间里做
   替换，最后按原文件行尾写回——这正是上一轮把源文件搞坏的那个坑。
4. dry-run 模式默认开启，先看能命中多少条，再决定是否落盘。
"""
import json
import pathlib
import sys

TARGET = pathlib.Path("app/services/pipeline_orchestrator.py")
EDITS = pathlib.Path("_recover_edits.json")


def main() -> int:
    apply = "--apply" in sys.argv
    raw = TARGET.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")

    edits = json.loads(EDITS.read_text(encoding="utf-8"))
    ok = 0
    skipped = []
    for i, h in enumerate(edits, 1):
        inp = h["input"]
        old = inp.get("old_string")
        new = inp.get("new_string")
        if old is None or new is None:
            skipped.append((i, h["ts"], "no_old_or_new", 0))
            continue
        old = old.replace("\r\n", "\n")
        new = new.replace("\r\n", "\n")
        n = text.count(old)
        if inp.get("replace_all"):
            if n == 0:
                skipped.append((i, h["ts"], "replace_all_miss", 0))
                continue
            text = text.replace(old, new)
            ok += 1
            continue
        if n != 1:
            # 区分两种 count=0：new_string 已在文本里 = 这条编辑的效果已经存在
            # （前几批已提交，或后来的编辑覆盖了它），属于良性跳过；new_string 也
            # 不在 = 真的丢了一段，必须人工看。
            why = "count"
            if n == 0 and new.strip() and new in text:
                why = "already_applied"
            skipped.append((i, h["ts"], why, n))
            continue
        text = text.replace(old, new, 1)
        ok += 1

    print(f"命中重放 {ok}/{len(edits)}")
    if skipped:
        print(f"未重放 {len(skipped)} 条：")
        for i, ts, why, n in skipped:
            print(f"  #{i:>3} {ts} {why}={n}")

    probes = (
        "EVENT_DENSITY_MIN_SAMPLE_CHARS",
        "UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR",
        "event_density_evaluated",
        "dialogue_state_applicable",
        "is not False",
    )
    print("\n关键标记计数：")
    for p in probes:
        print(f"  {p} = {text.count(p)}")

    if apply:
        out = text.replace("\n", "\r\n") if crlf else text
        TARGET.write_bytes(out.encode("utf-8"))
        print("\n已写回。")
    else:
        print("\n（dry-run，未写回；加 --apply 落盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
