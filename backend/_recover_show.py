# -*- coding: utf-8 -*-
"""打印指定序号的编辑内容，用来人工判断 9 条 count=0 是良性还是真丢。"""
import json
import pathlib
import sys

edits = json.loads(pathlib.Path("_recover_edits.json").read_text(encoding="utf-8"))
for arg in sys.argv[1:]:
    i = int(arg)
    h = edits[i - 1]
    inp = h["input"]
    print(f"===== #{i} {h['ts']} =====")
    print("--- old ---")
    print((inp.get("old_string") or "")[:600])
    print("--- new ---")
    print((inp.get("new_string") or "")[:600])
    print()
