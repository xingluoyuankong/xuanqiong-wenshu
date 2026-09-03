# 批 8-A 交叉核对：两个探针给出矛盾的 expected_dialogue 触发率。
# 语料探针（自己解析 chapter_mission）说 0/101 是 False；
# 键探针（读 guard 自己记的 expected_dialogue 字段）说 28/128 是 False。
# guard 字段是生产当时的真值，语料探针的 mission 解析路径可能不对（批 7-A 踩过同样的坑）。
import json
import sqlite3
import sys

sys.path.insert(0, ".")
from app.services.pipeline_orchestrator import PipelineOrchestrator as P  # noqa: E402

DB = "storage/xuanqiong_wenshu.db"
rows = sqlite3.connect(DB).execute("select content, metadata from chapter_versions").fetchall()

agree = disagree = no_mission = 0
mission_paths = {}
detail = {"guardT_mineT": 0, "guardT_mineF": 0, "guardF_mineT": 0, "guardF_mineF": 0}
zero_dialogue_and_guard_true = 0
guard_false_pool_sc = []

for content, meta in rows:
    md = json.loads(meta or "{}")
    rs = md.get("review_summaries") or {}
    g = rs.get("story_progression_guard")
    if not isinstance(g, dict) or "expected_dialogue" not in g:
        continue
    guard_expected = bool(g.get("expected_dialogue"))

    # 把 mission 可能藏身的所有路径都试一遍，记录哪条命中
    cands = {
        "md.chapter_mission": md.get("chapter_mission"),
        "md.runtime.chapter_mission": (md.get("runtime") or {}).get("chapter_mission"),
        "md.generation_context.chapter_mission": (md.get("generation_context") or {}).get("chapter_mission"),
        "md.chapter_draft_contract": md.get("chapter_draft_contract"),
        "md.longform_plan.chapter_mission": (md.get("longform_plan") or {}).get("chapter_mission"),
        "rs.chapter_mission": rs.get("chapter_mission"),
    }
    hit = next((k for k, v in cands.items() if isinstance(v, dict) and v), None)
    mission_paths[hit] = mission_paths.get(hit, 0) + 1
    if hit is None:
        no_mission += 1
        mine = False
    else:
        mine = P._chapter_mission_expects_dialogue(cands[hit])

    key = f"guard{'T' if guard_expected else 'F'}_mine{'T' if mine else 'F'}"
    detail[key] = detail.get(key, 0) + 1
    if guard_expected == mine:
        agree += 1
    else:
        disagree += 1

    if not guard_expected:
        # 这批就是「白给 +140」的样本：看它们的对话痕迹与状态标记
        dq = sum(content.count(m) for m in ("“", "”", "「", "」", "『", "』", '"')) if content else 0
        sc = P._count_dialogue_state_change_markers(content or "")
        guard_false_pool_sc.append((dq, sc))
        if dq == 0:
            zero_dialogue_and_guard_true += 1

print(f"=== 有 expected_dialogue 记录的样本 n={agree + disagree} ===")
print(f"  与我的解析一致 {agree}  不一致 {disagree}  完全解析不出 mission {no_mission}")
print(f"  交叉表 {detail}")
print("\n=== chapter_mission 实际藏在哪 ===")
for k, v in sorted(mission_paths.items(), key=lambda kv: -kv[1]):
    print(f"  {str(k):42s} n={v}")

print(f"\n=== guard 记录 expected_dialogue=False 的池（n={len(guard_false_pool_sc)}）===")
print("  这批在现行代码下无条件拿到 dialogue_changes_state=True 与 +140 分")
if guard_false_pool_sc:
    dqs = sorted(d for d, _ in guard_false_pool_sc)
    scs = sorted(s for _, s in guard_false_pool_sc)
    pct = lambda a, q: a[min(len(a) - 1, int(len(a) * q))]
    print(f"  对话引号数 p05={pct(dqs, .05)} p50={pct(dqs, .50)} p95={pct(dqs, .95)} min={dqs[0]} max={dqs[-1]}")
    print(f"  状态标记数 p05={pct(scs, .05)} p50={pct(scs, .50)} p95={pct(scs, .95)} min={scs[0]} max={scs[-1]}")
    print(f"  **零对话引号** n={zero_dialogue_and_guard_true}"
          f"（= 语义荒谬「零对话却说对话改变局势」的实际条数）")
    print(f"  拟改三态后这批的归属：None(零对话) n={sum(1 for d, _ in guard_false_pool_sc if d == 0)}  "
          f"True(有对话且 sc>=1) n={sum(1 for d, s in guard_false_pool_sc if d > 0 and s >= 1)}  "
          f"False(有对话但 sc==0) n={sum(1 for d, s in guard_false_pool_sc if d > 0 and s == 0)}")
