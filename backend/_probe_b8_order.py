# 批 8-A 第三问：交接文档 D-07 给的三态代码把「零对话」判在最前面：
#   if dialogue_markers == 0: passed = None
#   elif not expected_dialogue: passed = (sc >= 1)
#   elif ...
# 这个顺序意味着「任务书要求对话 + 正文零对话」→ None →
# `dialogue_does_not_change_state` blocker 不再触发（现在会触发 False）。
# 那是把门改松，与 T-13 的目的相反。这里量化两种顺序的差异。
import json
import sqlite3
import sys

sys.path.insert(0, ".")
from app.services.pipeline_orchestrator import PipelineOrchestrator as P  # noqa: E402

DQ = ("“", "”", "「", "」", "『", "』", '"')
DB = "storage/xuanqiong_wenshu.db"
rows = sqlite3.connect(DB).execute("select content, metadata from chapter_versions").fetchall()

seen = set()
pool = []
for content, meta in rows:
    if not content or content in seen:
        continue
    seen.add(content)
    md = json.loads(meta or "{}")
    g = (md.get("review_summaries") or {}).get("story_progression_guard")
    if not isinstance(g, dict) or "expected_dialogue" not in g:
        continue
    pool.append((bool(g.get("expected_dialogue")),
                 sum(content.count(m) for m in DQ),
                 P._count_dialogue_state_change_markers(content),
                 len("".join(content.split()))))

print(f"=== 样本 n={len(pool)} ===")


def cur(exp, dq, sc):
    return True if not exp else (dq >= 2 and sc >= 2)


def doc_order(exp, dq, sc):
    """交接文档 D-07 给的顺序：零对话优先判 None。"""
    if dq == 0:
        return None
    if not exp:
        return sc >= 1
    return dq >= 2 and sc >= 2


def fixed_order(exp, dq, sc):
    """修正顺序：先看任务书有没有要求，「不适用」只在没要求且没对话时成立。"""
    if exp:
        return dq >= 2 and sc >= 2
    if dq == 0:
        return None
    return sc >= 1


for name, fn in (("现行 bool", cur), ("文档顺序", doc_order), ("修正顺序", fixed_order)):
    t = sum(1 for e, d, s, _ in pool if fn(e, d, s) is True)
    f = sum(1 for e, d, s, _ in pool if fn(e, d, s) is False)
    n = sum(1 for e, d, s, _ in pool if fn(e, d, s) is None)
    print(f"  {name}: True={t} False={f} None={n}")

print("\n=== 关键差异：expected=True 且零对话（现在会触发 blocker）===")
risky = [(e, d, s, w) for e, d, s, w in pool if e and d == 0]
print(f"  真实语料里 n={len(risky)}")
print("  这批在「文档顺序」下 → None → dialogue_does_not_change_state blocker 不再触发（门变松）")
print("  在「修正顺序」下 → False → blocker 照旧触发（门不变松）")

print("\n=== 关键差异：expected=False 且零对话（真正的「不适用」）===")
na = [(e, d, s, w) for e, d, s, w in pool if not e and d == 0]
print(f"  真实语料里 n={len(na)}  两种顺序都判 None，无差异")

print("\n=== expected=False 且有对话（白给 +140 的主体）===")
give = [(e, d, s, w) for e, d, s, w in pool if not e and d > 0]
print(f"  n={len(give)}  现行全判 True；改后按 sc>=1 判 → "
      f"True n={sum(1 for _, _, s, _ in give if s >= 1)} False n={sum(1 for _, _, s, _ in give if s == 0)}")
