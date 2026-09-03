# 批 8-A 第二问：`get(key, True)` 的真实风险不在「值是 True」，而在「键根本不存在」。
# 量化历史 story_progression_guard 里两个键的缺失率，以及缺失时软放行是否被白给激活。
import json
import sqlite3
import sys

sys.path.insert(0, ".")

DB = "storage/xuanqiong_wenshu.db"
rows = sqlite3.connect(DB).execute("select metadata from chapter_versions").fetchall()

KEYS = [
    "dialogue_changes_state", "event_density_passed", "state_change_interval_passed",
    "long_chapter_density_passed", "ending_pressure_passed", "expected_dialogue",
]

guards = []
snaps = []
for (meta,) in rows:
    md = json.loads(meta or "{}")
    rs = md.get("review_summaries") or {}
    g = rs.get("story_progression_guard")
    if isinstance(g, dict) and g:
        guards.append(g)
        snap = g.get("quality_metric_snapshot")
        if isinstance(snap, dict) and snap:
            snaps.append(snap)
    fq = rs.get("final_quality_metrics")
    if isinstance(fq, dict) and fq:
        snaps.append(fq)

print(f"=== 样本 ===\n  story_progression_guard n={len(guards)}   快照/最终指标 n={len(snaps)}")


def report(name, pool):
    print(f"\n=== {name}（n={len(pool)}）键缺失率 ===")
    if not pool:
        return
    for k in KEYS:
        absent = sum(1 for d in pool if k not in d)
        nulls = sum(1 for d in pool if k in d and d[k] is None)
        trues = sum(1 for d in pool if d.get(k) is True)
        falses = sum(1 for d in pool if d.get(k) is False)
        print(f"  {k:32s} 缺失 {absent:4d}（{absent / len(pool):.3f}）  "
              f"None {nulls:3d}  True {trues:4d}  False {falses:3d}")


report("guard 顶层", guards)
report("快照", snaps)

# 缺键时 `get(k, True)` 与 `is not False` 的判定差异：
# 前者把「缺失」当正向证据，后者也当"不反对"。真正的差异只在值为 None 时。
print("\n=== 缺键 → 白给正向证据的样本数（4 条软放行的共同前提）===")
for pool, label in ((guards, "guard 顶层"), (snaps, "快照")):
    if not pool:
        continue
    both = sum(1 for d in pool if "dialogue_changes_state" not in d and "event_density_passed" not in d)
    either = sum(1 for d in pool if "dialogue_changes_state" not in d or "event_density_passed" not in d)
    print(f"  {label}: 两键都缺 n={both}  至少缺一个 n={either}")

# 短样本在历史快照里留下的矛盾证据：rate=1.0 且 count=0
print("\n=== T-14 矛盾字段在历史数据里的实际条数 ===")
bad = [d for d in snaps
       if d.get("progression_unit_count") == 0 and d.get("progression_unit_rate") in (1.0, 1)]
print(f"  progression_unit_count=0 且 progression_unit_rate=1.0 → n={len(bad)}")
lie = [d for d in snaps
       if d.get("event_density_passed") is True and (d.get("event_density_per_1000") in (0.0, 0))]
print(f"  event_density_passed=True 且 density_per_1000=0.0 → n={len(lie)}")
wc_short = [d for d in snaps if isinstance(d.get("word_count"), int) and d["word_count"] < 800]
print(f"  快照里 word_count<800 → n={len(wc_short)}")
