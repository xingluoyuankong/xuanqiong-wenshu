# -*- coding: utf-8 -*-
"""从会话 jsonl 里扫描针对 pipeline_orchestrator.py 的所有 Edit/Write 调用。

目的不是马上重放，而是先量清损失面：哪几个会话动过这个文件、各有多少次编辑、
时间顺序如何。重放必须按时间正序，且必须逐条校验 old_string 能在当前文本里
唯一命中——命中不到就说明中间有一次编辑没被记录到（比如 linter 改写），
这时候只能停下人工看，不能跳过继续。
"""
import json
import pathlib
import sys

SESS = pathlib.Path(r"C:\Users\XZXyuan\.claude\projects\D-------xuanqiong-wenshu")
TARGET_TAIL = "pipeline_orchestrator.py"


def scan(path: pathlib.Path):
    hits = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw or TARGET_TAIL not in raw:
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name")
                if name not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                    continue
                inp = block.get("input") or {}
                fp = str(inp.get("file_path") or "")
                if not fp.endswith(TARGET_TAIL):
                    continue
                hits.append(
                    {
                        "session": path.stem,
                        "jsonl_line": lineno,
                        "ts": rec.get("timestamp"),
                        "uuid": rec.get("uuid"),
                        "tool": name,
                        "input": inp,
                    }
                )
    return hits


def main() -> int:
    all_hits = []
    # 子 agent 的编辑也要算：主会话只记录自己发出的 tool_use，子 agent 在
    # subagents/ 下另有一份 transcript。第一版只扫顶层 *.jsonl，漏掉了
    # `_detect_generation_meta_leakage` 这类完全由子 agent 写入的方法。
    for p in sorted(SESS.rglob("*.jsonl")):
        h = scan(p)
        if h:
            print(f"{p.stem}  {len(h)} 次编辑  {h[0]['ts']} .. {h[-1]['ts']}")
            all_hits.extend(h)
    all_hits.sort(key=lambda x: (x["ts"] or "", x["jsonl_line"]))
    out = pathlib.Path("_recover_edits.json")
    out.write_text(json.dumps(all_hits, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n合计 {len(all_hits)} 次 → {out}")
    kinds = {}
    for h in all_hits:
        kinds[h["tool"]] = kinds.get(h["tool"], 0) + 1
    print("按工具：", kinds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
