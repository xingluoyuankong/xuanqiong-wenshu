# 批 8-A 探针：灌真实历史正文，量化 T-13 / T-14 的影响面。
# 遵守 §11.2.1 四条硬规矩：只打印统计量、剔退化文本、分历史池、写完即删。
import io
import json
import sqlite3
import sys

sys.path.insert(0, ".")
from app.services.pipeline_orchestrator import PipelineOrchestrator as P  # noqa: E402

DB = "storage/xuanqiong_wenshu.db"

rows = sqlite3.connect(DB).execute("select content, metadata from chapter_versions").fetchall()

seen = set()
samples = []          # (content, word_count, chapter_mission, 历史 event_density_passed, 历史 dialogue_changes_state)
short_total = 0       # <800 字的样本数（含被 shingle 剔掉的，单独计）
for content, meta in rows:
    if not content:
        continue
    wc = len("".join(content.split()))
    if content in seen:
        continue
    seen.add(content)
    sh = {content[i:i + 20] for i in range(0, max(1, len(content) - 19))}
    if len(sh) / max(1, len(content) - 19) < 0.90:
        continue
    md = json.loads(meta or "{}")
    guard = (md.get("review_summaries") or {}).get("story_progression_guard") or {}
    mission = md.get("chapter_mission") or (md.get("runtime") or {}).get("chapter_mission") or {}
    if wc < 800:
        short_total += 1
    samples.append((content, wc, mission if isinstance(mission, dict) else {},
                    guard.get("event_density_passed"), guard.get("dialogue_changes_state")))

print(f"=== 取样 ===\n  去重+剔退化后 n={len(samples)}  其中 <800 字 n={short_total}")

# --- T-14：短样本占比 = 事件密度门失效的触发率 ---
print("\n=== T-14：word_count < 800 的分布 ===")
if samples:
    print(f"  <800 字占比 {short_total / len(samples):.3f}")
    wcs = sorted(w for _, w, _, _, _ in samples)
    pct = lambda q: wcs[min(len(wcs) - 1, int(len(wcs) * q))]
    print(f"  word_count p03={pct(.03)} p05={pct(.05)} p10={pct(.10)} p25={pct(.25)} "
          f"p50={pct(.50)} p75={pct(.75)} p95={pct(.95)} min={wcs[0]} max={wcs[-1]}")
    # 短样本里历史被标成 passed=True 的有多少（= 谎报满分的实际发生次数）
    lied = sum(1 for _, w, _, ed, _ in samples if w < 800 and ed is True)
    print(f"  <800 字且历史 event_density_passed is True（谎报满分）n={lied}")

# --- T-13：expected_dialogue=False 的占比 = 白给 +140 的触发率 ---
print("\n=== T-13：expected_dialogue 分布 ===")
have_mission = [s for s in samples if s[2]]
print(f"  能解析出 chapter_mission 的样本 n={len(have_mission)}（占 {len(have_mission) / max(1, len(samples)):.3f}）")
if have_mission:
    exp_true = sum(1 for _, _, m, _, _ in have_mission if P._chapter_mission_expects_dialogue(m))
    print(f"  expected_dialogue=True  n={exp_true}")
    print(f"  expected_dialogue=False n={len(have_mission) - exp_true} "
          f"（触发率 {(len(have_mission) - exp_true) / len(have_mission):.3f} ← 这批就是白给 +140 的）")

# --- 三态改造后：有多少样本的判定会变 ---
print("\n=== T-13 改造前后对比（现行 bool vs 拟改三态）===")
DQ = ("“", "”", "「", "」", "『", "』", '"')  # 与 7906 行同源
now_true = now_false = new_none = new_true = new_false = 0
zero_dialogue_but_true = 0
for content, wc, mission, _, _ in samples:
    markers = sum(content.count(m) for m in DQ)
    expected = P._chapter_mission_expects_dialogue(mission) if mission else False
    cur = P._evaluate_dialogue_changes_state(content, expected_dialogue=expected, dialogue_markers=markers)
    cur_passed = cur.get("dialogue_changes_state")
    if cur_passed:
        now_true += 1
    else:
        now_false += 1
    # 拟改三态：无对话痕迹 → None；未声明预期但有对话 → 按内容判；声明了 → 原判据
    sc = cur.get("state_change_marker_count") or 0
    if markers == 0:
        new_none += 1
    elif not expected:
        if sc >= 1:
            new_true += 1
        else:
            new_false += 1
    else:
        if markers >= 2 and sc >= 2:
            new_true += 1
        else:
            new_false += 1
    if markers == 0 and cur_passed:
        zero_dialogue_but_true += 1

print(f"  现行：True n={now_true}  False n={now_false}")
print(f"  拟改：True n={new_true}  False n={new_false}  None n={new_none}")
print(f"  **零对话痕迹却被判 True** n={zero_dialogue_but_true} "
      f"（触发率 {zero_dialogue_but_true / max(1, len(samples)):.3f} ← D-07 语义荒谬的实际发生次数）")

# --- 状态变化标记数分布：定「未声明预期时按内容判」的门槛要用 ---
print("\n=== state_change_marker_count 分布（全池）===")
scs = [P._count_dialogue_state_change_markers(c) for c, _, _, _, _ in samples]
if scs:
    scs.sort()
    pct = lambda q: scs[min(len(scs) - 1, int(len(scs) * q))]
    print(f"  n={len(scs)} p03={pct(.03)} p05={pct(.05)} p10={pct(.10)} p25={pct(.25)} "
          f"p50={pct(.50)} p75={pct(.75)} p95={pct(.95)} min={scs[0]} max={scs[-1]}")
    print(f"  ==0 的样本 n={sum(1 for v in scs if v == 0)}  >=1 n={sum(1 for v in scs if v >= 1)}  "
          f">=2 n={sum(1 for v in scs if v >= 2)}")
