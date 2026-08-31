> **本轮 T-16 审计器口径修复（总目标仍 active）**：严格指纹审计新增 `comparable_pair_count` 与 `non_comparable_candidate_pair_count`，区分“时间顺序候选”与“真正同评分器可比较成员”；专项 **4 passed**，反向验证通过。全量当前报告为：37 summaries、14 完整指纹、9 同条件组、1 候选、**0 可比配对、1 不可比候选**；后端清缓存全量 **986 passed, 0 failed in 72.17s**。这修正了原先 `candidate_pair_count=0` 限制语句与实际候选数不一致的问题，不制造 T-16 前后收益。

> **T-16 候选配对复核（总目标仍 active）**：全量指纹审计现发现 1 个时间顺序候选配对（E-08 v4 10 任务 vs T-06 新 10 任务，任务/Provider/模型/请求契约相同），但严格 `--compare` 返回 `comparable=false`，不匹配字段为 `scorer_sha256`、`comparison_contract_sha256`。脱敏 provenance 报告：`backend/output/t16-candidate-pair-provenance-audit-current.json`。结论仍是 **0 个合法可比前后收益配对**；候选不能替代同评分器/同契约的改前生成基线。

> **本轮 E-11 多章拒绝诊断观测更新（总目标仍 active）**：多章真实采样脚本现在对每章脱敏投影 `patch_suggestions` 与 `quality_issue_codes`，并保留 `exemptions`/`critique_exemption_applied`；专项 **7 passed**，反向验证通过；后端清缓存全量 **985 passed, 0 failed in 88.00s**。该改动只增强拒绝样本的审计可见性，不改变质量门或 patch 修复行为；真实 patch 修复收益/误杀率仍缺。

> **本轮前端回归与 E-09/T-18 证据收束（总目标仍 active）**：
> - 前端 `RuntimeLogManagement` 修复旧 `runtime_snapshot.pipeline_total_duration_ms` 回退缺失导致的“未记录”误显示，并保留 `0` 字数/Token 值；针对性测试 2/2，全量前端 type-check、Vitest、build-only 均通过。
> - 后端清缓存全量 **985 passed, 0 failed in 96.89s**。
> - E-09 新增 20 章 `gpt-5.6-sol` 真实复验：16/20 放行、4/20 拒绝，放行率 0.8；拒绝均保留，`ending_pressure_missing=4`、`reversal_missing=1`，脱敏一致性 `valid=true`。
> - E-09/T-18 观测复跑已验证每章 `exemptions` 与 `critique_exemption_applied` 真实落盘；5/5 样本均为空数组，不能据 0 触发调整阈值。

> **T-18/E-09 豁免观测真实复跑**：多章采样脚本现已投影每章 `exemptions` 与 `critique_exemption_applied`。使用 `gpt-5.6-sol` 真实复跑 5 章：5/5 放行、5 章字段均为空数组；脱敏一致性审计 `backend/output/e09-multichapter-observability-audit-current.json` 为 `valid=true`。这证明观测链路真实落盘，但当前样本仍未触发豁免，不能据此调阈值；T-18 真值继续缺失。

> **E-09 20 章真实多章复验（gpt-5.6-sol）**：认证通过后使用可用模型 `gpt-5.6-sol` 完成 20 次隔离 ASGI 章节尝试；结果 **16/20 放行、4/20 拒绝、放行率 0.8**。拒绝样本均保留：`ending_pressure_missing=4`，第 16 章另有 `reversal_missing` warning；`exemption_counts={}`。脱敏一致性审计 `backend/output/e09-multichapter-evidence-audit-current.json` 为 `valid=true`，20/20 计数一致，正文键泄漏为空。该结果证明质量门真实拒绝路径和多章统计链路可运行，不等于人工接受率、跨题材召回率或 T-18 豁免真值。
> - 同轮默认 deepseek 通道曾返回 `No available channel`，3/3 无正文；该 provider 阻断未计入 gpt 质量批次，也未覆盖既有证据。

> **E-09 新采样阻断记录（总目标仍 active）**：尝试启动新的 20 章真实 ASGI 采样时，隔离应用登录返回 HTTP 401（`.env` 配置的 admin 凭据与隔离初始化用户不匹配），因此 **0 章生成、0 正文、未覆盖既有证据**。未绕过认证、未把阻断计入放行率或质量失败；既有 20 章脱敏证据继续作为当前有效 E-09 内部一致性证据，但仍不构成人工真值。

> **E-02～E-05 真实 batch 脱敏补证**：最新 10 任务 `gpt-5.6-sol` batch 已生成 `backend/output/e02-e05-live-batch-audit-20260822.json`，覆盖反转信号/晚段反转、说话人分布、对白/动作/描写比例、硬切/总结式切换；正文和任务书均未输出。该报告仅补充真实 LLM 分布，不构成人工质量真值、召回率、误杀率或 T-16 前后收益。

> **T-25 真实长篇合同审计**：对已通过的真实长篇隔离库生成脱敏报告 `backend/output/t25-real-longform-contract-audit-20260822.json`：任务 `succeeded`、5/5 segments checkpoint 完成、章节 39,406 字、目标/最低字数字段一致，`word_requirement_met=true`，事件密度/长章密度/状态变化和 `quality_gate_passed` 均为 true，`quality_gate_codes=[]`；正文仅保留 SHA-256 与长度。该样本补齐 T-25 的真实端到端证据，但不能证明跨任务误杀率，也不能用于 T-18 豁免触发率（运行发生在新增观测字段之前）。

> **本轮 T-06 真实重试 batch 结果（总目标仍 active）**：固定 10 任务使用 `gpt-5.6-sol` 完成真实 batch，结果 **10/10 正文、0 provider failure**；最低字数、章末压力、事件密度、长章密度、状态变化均 **10/10**。`benchmark-scifi-investigation-6000` 第 1 次收到 Provider **HTTP 524**（`Retry-After=120`），第 2 次 SSE 成功，真实 `retry_events` 已保存，退避仍受代码 15 秒上限约束。批次审计 `backend/output/t06-retry-batch-comparability-20260822.json`：完整指纹 1、同条件组 1、**合法前后配对 0**；这是当前批次/重试证据，不是 T-16 改前后收益或人工质量真值。

> **T-06 单任务真实 schema 验证**：使用 `gpt-5.6-sol` 独立运行 `benchmark-bridge-3000`，结果 `passed`、SSE、1 次尝试、0 provider failure；新产物 `backend/output/quality-bench-t06-retry-real-20260822/provider-live-20260822T185002Z/` 已写入 `retry_events=[]`。这证明新审计字段在真实产物中生效，但本次没有触发重试，故 T-06 仍不宣称已有真实降级样本。

> **本轮 T-06 benchmark 重试审计更新（总目标仍 active）**：真实 benchmark 运行器现为每次成功调用保存脱敏 `retry_events`（attempt、异常类型、截断原因、retryable），覆盖空正文、HTTP 429 和传输中断重试；重试上限/退避/质量判定不变。专项 **28 passed**，反向验证通过；后端清缓存全量 **970 passed, 0 failed in 83.73s**。现有 E-08 v4 的 `benchmark-bridge-3000` 仅有历史 `attempts=2`，旧产物没有该新增字段，不能回填伪造 retry reason；下一次 live 批次才会产生完整 `retry_events`。

# Memory

## Active Project
| Name | What |
|------|------|
| xuanqiong-wenshu | Novel generation quality and continuity overhaul. |

## Current Priorities
- Make first-draft novel generation satisfy quality requirements before later polish.
- Reduce static description, increase natural dialogue, causal progression, reversals, and chapter continuity.
- Keep quality metrics visible in API responses, metadata, logs, and frontend review surfaces.
- Use repeatable regression tests for bad samples such as all-description, no-logic, no-reversal, flat endings.

## Latest Progress
- 2026-08-22 continuation: real `gpt-5.6-sol` longform ASGI smoke passed after fixing production heartbeat/content-delta wiring: 20,000-word target, 5/5 segments, 5 content deltas, 39,406 characters, 73 runtime events; backend full cache-cleared gate **970 passed, 0 failed**. T-18/D-14 now records `critique_exemption_applied` in `quality_metric_snapshot` and supports legacy guards without snapshots; thresholds and gate outcomes were unchanged. Remaining external evidence gaps are human labels 0/19, no legal T-16 before-batch pair, no real T-18 exemption truth, and missing E-09 cross-genre human truth.
- 2026-08-21 continuation: runner unified to pytest-asyncio (`-p no:anyio` in backend/pytest.ini plus 225 marker migrations); T-24/T-25/T-26 completed; T-16 two-stage capped scoring, T-17 deterministic cleanup, and T-19 orphan scoring removal completed. Verified backend `769 passed, 0 failed`; frontend type-check, 46 Vitest files/241 tests, and production build all pass.
- Backend story quality guards now score scene fulfillment, dialogue state change, ending pressure, static description risk, and quality metric snapshots.
- Frontend writing desk now exposes quality summaries in chapter header/sidebar, failed-state diagnostics, version detail modal, candidate cards, and active version preview.
- Enrichment prompts are constrained to action, dialogue, consequence, and short sequel decisions instead of empty descriptive padding.
- Verified core quality tests: backend quality guards and frontend quality display regression suites pass.
- 提交信息必须引用当前完整后端门禁的原始结果，写成 `N passed, M failed` 完整形态；不得只写 passed 数或沿用旧数。执行 `.\venv\Scripts\python.exe -m pytest app -q -rf`（`backend/pytest.ini` 已固定 `-p no:anyio`），并在提交前重跑。
- Batch 1 of the quality rollout is done: dead `_score_fallback_candidate` removed from `pipeline_orchestrator.py`, EXTRACTABLE module-boundary comments stripped of stale line numbers and moved out of literals (they were sitting inside a tuple and a dict).
- Batch 2 is done (T-02 / T-03 / T-15, ending-pressure gate): the three ending-hook word lists are now `PipelineOrchestrator` class attributes (`ENDING_WEAK_HOOK_MARKERS` / `ENDING_SEMANTIC_HOOK_MARKERS` / `ENDING_CLOSURE_MARKERS`), written as Chinese literals instead of `\uXXXX` escapes so they stay greppable, with story-specific nouns removed so the gate works across genres. Punctuation and bare adverbs are now weak signals that can no longer stand in for semantic pressure, and `"一切都"` was replaced by complete closure phrases so real hooks like `一切都还是未知` stop being killed. Two new counters (`ending_semantic_hit_count` / `ending_weak_hit_count`) are exposed through the `quality_metric_snapshot` allowlist, which is the only place a new field can silently get dropped before reaching the API and frontend.
- Batch 3 is done (T-04 / T-05 / T-06, event-density gate). Three root causes fixed: `_unit_has_progression` no longer counts a sentence as progression just because it contains quote marks (a quoted line must also carry a state-change or action marker), bare conjunctions and the single character `"活"` are out of `STORY_PROGRESSION_MARKERS`, and the sliding-window check now uses a real window-level function `_window_has_state_change` plus tail-window merging (`WINDOW_TAIL_MERGE_RATIO = 0.4`) instead of reusing the sentence-level predicate.
- Batch 3's real lesson: **never calibrate production thresholds against synthetic samples.** The first threshold set was derived from hand-written samples, passed the targeted suite (101) and the full suite (676) green, and still rejected 96% of real generated chapters. All thresholds were re-derived from 147 real `chapter_versions` rows (107 historically-passing after dedup and dropping degenerate looping text): `density_floor` 1.5/1.8/2.0, `unit_rate_floor` 0.025/0.028/0.03, and `WINDOW_PROGRESSION_RATIO_FLOOR` dropped 0.25 → 0.05 with `WINDOW_PROGRESSION_MIN_HITS = 2` carrying the "progression must not all sit at the front" requirement. Real-corpus pass rate went 3.7% → 95.0%.
- Absolute run lengths cannot be thresholds: `max_plain_unit_run` grows linearly with chapter length (real p50=36, p95=104, max=167), so `plain_run_limit` was deleted outright and replaced by the ratio `plain_run_ratio_limit` (0.75/0.72/0.70) over the new `max_plain_unit_run_ratio` field (real p50=0.218, max=0.681; pure-chatter filler hits 1.0). The new field also had to be added to the `quality_metric_snapshot` allowlist.
- When changing any threshold, run the two-layer probe described in TASK_HANDOFF_NOVEL_QUALITY.md §11.2.1: layer one calls the classmethod directly, layer two feeds real `chapter_versions` content from `backend/storage/xuanqiong_wenshu.db` and prints percentiles only — never chapter text, per the redaction rule. That corpus is gitignored, so the percentile tables must live in the doc, not in a script.
- Batch 4 is done (T-07, bad-sample regression suite). `class TestBadSampleRegression` in `app/services/test_generation_quality_guards.py` holds 9 tests over 5 bad samples plus one positive control: all-description, flat chatter, mundane action sequence, punctuation-only ending hook, and flat closure. The suite is now the fast guard before any quality-gate change — `pytest -k "BadSampleRegression"` runs in seconds and covers both directions (bad samples must be blocked, `GOOD_DRAMATIC` must stay at zero blockers). Full suite 688 passed; reverse verification broke 6 production conditions in 11 ways and every one turned the expected test red.
- Batch 4 also fixed a batch-2 observability miss: `flat_closure_markers` was in neither the top-level result nor the snapshot, so a user saw "章末未递出压力" without knowing which sentence triggered the veto. It is now in the `quality_metric_snapshot` allowlist, with a test asserting the positive control gets an empty list rather than a missing key. Same lesson as batch 3 — that allowlist is the single silent-drop point for any new field.
- Two new defects found while building batch 4's samples, both scheduled for batch 6. **D-24 (the important one)**: `_evaluate_ending_pressure` only inspects `condensed_text[-260:]`, a fixed character window, so a short flat ending lets the body's own hooks leak into the window and cancel it out — the same bad ending scored 1302 with `codes=[]` behind a 38-char tail and 1042 with `ending_pressure_missing` behind a 275-char tail. Real chapter endings are 1-3 sentences, so this masking is the normal case in production, not an edge case. **D-25**: only the first of the three `static_description_risk` or-branches has any test coverage; `BAD_ALL_DESCRIPTION` has `max_static_run == 0` and passes through branch 1, so zeroing out `_estimate_static_description_runs` breaks nothing visible.
- Two T-07 deviations worth knowing before touching the score model: ending-class bad samples sit exactly 260 points below the control (not the ≥300 the plan assumed) because one ending is only worth that much in the total — the real defense there is the `ending_pressure_missing` blocker, not the score gap. And `BAD_MUNDANE_SEQUENCE` has `event_density_passed is True` on purpose: the density gate is a floor gate that catches "no action at all", not "action without meaning", so the flat-daily-routine sample is caught by the ending gate instead. That assertion is written down so anyone raising density thresholds to catch filler gets a red test pointing at T-16 instead.
- Batch 5 is done (T-22, targeted-repair loop). `_attempt_structural_gate_repair` **no longer returns `None`** — it always returns a diagnostic dict and callers read the `adopted` flag, because "keep diagnostics on failure" has nowhere to live inside a `None`. Adoption is now `_is_structural_repair_improvement`: `len(after) < len(before) and not (after - before)`, capped at `STRUCTURAL_GATE_REPAIR_MAX_ROUNDS = 2` (hardcoded — it is a cost ceiling, not a tuning knob, since every round is one more LLM call). Four skip reasons are surfaced through `repair_skipped_reason` (`self_critique_disabled` / `story_guard_missing` / `no_structural_issue` / `revise_failed`) so the frontend can tell "tried and failed" from "never tried". Both call sites append `repair_summary` to `runtime_metadata["quality_gate_repairs"]` whether or not the revision was adopted. Full suite 691 passed; reverse verification broke 4 production conditions in 12 ways and every one turned the expected test red.
- Batch 5's lesson, which generalizes to any "did it get better" predicate: **a drop in blocker count is not an improvement.** Measured counterexample — prefixing `GOOD_DRAMATIC` with a `## 场景 1｜开场` header takes the blocker set from 7 codes down to 1, but that 1 is `chapter_artifact_markers`, a failure mode absent from the starting set. Adopting it would steer the repair loop toward killing artifact markers while every original structural problem survives. The `not (after - before)` half of the predicate is the substance, not defensive padding — E-11's severity tiers will need it even more, since tiering makes "trading one class of flaw for another" easier to hit.
- Reverse-verification note for source-text assertions: `test_structural_gate_repair_is_wired_into_generate_chapter` asserts on `inspect.getsource(...)` **text**, so breaking it means replacing `inspect.getsource` itself to return mutated source. Replacing the `generate_chapter` attribute only raises `TypeError` — a false red, where the test fails for a reason unrelated to the defect being probed.
- Handoff plan for the remaining quality work (defects D-01..D-25, tasks T-01..T-22, enhancements E-01..E-11, 10 batches): TASK_HANDOFF_NOVEL_QUALITY.md. Batches 1-5 are done (659 → 691). Next up is batch 6 (T-08 / T-09 / T-10 plus D-24 ending-window masking and D-25 static-run coverage), baseline 691, target 696 — the repair-loop gate is now in place, so batches may raise blocker rates. Appendix A.1's line numbers were fully recalibrated in batch 5 (it inserted ~130 lines around 2035, invalidating every later number); recalibrate again after the next change to `pipeline_orchestrator.py`. Still outstanding from batch 3: the §8.4 real-generation end-to-end check, blocked on LLM quota (`403 pre-consume quota failed`).

Details: memory/projects/novel-generation-quality.md
> **2026-08-22 T-17 真实持久化闭环（总目标仍 active）**：`gpt-5.6-sol` 真实 ASGI smoke 成功后，隔离库 `backend/storage/real-asgi-1787439711798466400.db` 的最新 `chapter_versions.metadata` 已核验包含 `deterministic_cleanup`、`quality_gates`、`quality_metrics`，且 `quality_gate_passed=true`；脱敏证据为 `backend/output/t17-real-asgi-metadata-persistence-audit-20260822.json`。T-17 专项 **196 passed**，后端完整门禁 **987 passed, 0 failed**。这是单次真实持久化证据，不得替代人工标签、T-16 合法改前批次、T-18 豁免真值或 E-11 patch 修复收益；总目标保持 active。
> **2026-08-22 T-17 smoke 自动验收护栏补强（总目标仍 active）**：真实生成 smoke 现在自动断言候选版本的 `metadata.deterministic_cleanup`、`metadata.quality_gates`、`metadata.quality_metrics` 均存在；第二次 `gpt-5.6-sol` 真实运行全部通过，`quality_gate_passed=true`，隔离库为 `backend/storage/real-asgi-1787440094145467900.db`。新增反向回归后质量门专项 **197 passed**；完整后端门禁需在本轮改动后复跑，不能提前宣称全量通过。
> **2026-08-22 本轮门禁实测修正**：T-17 smoke 自动护栏改动后，按项目规定运行 `backend\\.venv\\Scripts\\python.exe -m pytest -q`，当前实测 **974 passed, 0 failed in 77.52s**；以本次结果为准，旧记录中的 987/986 仅作历史参考。总目标仍 active，不能把门禁通过等同于人工真值或 T-16/T-18/E-11 等硬验收完成。
> **2026-08-22 T-25 真实长篇阻断证据（总目标仍 active）**：20,000 字目标的 `gpt-5.6-sol` 长篇真实运行完成 5 段、5 次增量、34,211 字符和完整 checkpoint，但因 3 critical/4 major 一致性冲突被 `CHAPTER_QUALITY_GATE_FAILED` 拒绝；两轮自动修复前后加权仍为 13，未采纳。脱敏报告：`backend/output/t25-real-longform-failure-audit-20260822.json`。这是质量闸门拒绝有效性的证据，不是 T-25 通过；不得降低 critical 阻断条件。
> **2026-08-22 T-25 失败链路专项回归**：长篇、一致性、质量门相关专项 **223 passed**；脱敏失败报告字段已校正并通过 JSON 校验。critical 冲突未改善时继续拒绝，未降低生产门槛。
> **2026-08-23 E-07/E-10 真实多章复验（总目标仍 active）**：`gpt-5.6-sol` 隔离 5 章真实生成 5/5 成功，放行率 1.0；脱敏证据 `backend/output/e09-multichapter-trend-5chapters-20260823T002431Z.json`，一致性 `valid=true`。本批连续性缺失 1、偏晚 0，任务书体检行 5、`mission_focus_placeholder` 5；趋势 API 已稳定输出 `exemptions=[]` 与 `critique_exemption_applied=[]`，并显式区分字符数和质量词数。专项 **28 passed**；因本批 `gate_rows=0`，不得把它冒充 T-18 豁免真值或人工质量验证。
> **2026-08-23 本轮全量门禁实测**：后端 **981 passed, 0 failed in 92.69s**；前端 type-check、Vitest **48 files / 291 tests**、build-only 均通过。以此为当前门禁实测值；旧计数仅作历史参考，不能替代人工真值与合法前后对照。
> **2026-08-23 T-06 第二批真实重试分布**：同契约 live batch 10/10 单次成功、0 failure、0 retry_events；脱敏报告 `backend/output/t06-second-live-retry-distribution-audit-20260823.json`。它与首批 524→重试成功共同说明重试证据可落盘，但零重试不等于已证明降级可靠性或质量收益；T-06/T-16 仍不能据此关闭。
> **2026-08-23 E-11/T-22 真实修复可观测性补强**：候选版本 metadata 现在始终保存 `quality_gate_repairs`；最新真实 ASGI smoke 自动核验该字段为 `[]`，表示本次样本未触发 repair，证据 `backend/output/e11-t22-real-asgi-repair-observability-audit-20260823.json`。专项 **207 passed**，后端全量 **987 passed, 0 failed in 68.82s**；不得把负控当作 patch 收益或真实修复率。
> **2026-08-23 E-11/T-22 真实 repair 探针**：默认短章拒绝样本已记录 `repair_skipped_reason=self_critique_disabled`；显式 self-critique 与诱导平静收束样本均未触发 repair，`quality_gate_repairs=[]`。脱敏报告 `backend/output/e11-t22-real-repair-probe-audit-20260823.json`；真实 patch 注入和前后收益仍未证明。
> **2026-08-23 本轮后端门禁实测修正**：后端全量测试当前为 **993 passed, 0 failed in 71.41s**。E-11/T-22 的真实 patch repair 尚未触发，不能把全量绿灯当成修复收益证据。
> **2026-08-23 T-16 当前冻结口径重复配对**：两次当前 10 任务 batch 在同 scorer、同 comparison contract、同请求契约下成功比较，`comparable=true`，平均分 delta `+222.7`；报告 `backend/output/t16-current-repeat-pair-audit-20260823.json`。这不是优化前后收益；审计现要求 scorer 与 comparison contract 双一致，T-16 合法前后配对仍为 0。
> **2026-08-23 T-18/E-09 趋势投影修复**：趋势 API 已读取成功版本 `quality_gates.structural_gate`，新增质量门与 self-critique 字段；真实 5 章复核 self-critique 均生效、分数 72.5～83.6，但 exemption 仍为 0。报告 `backend/output/t18-real-asgi-exemption-observability-audit-20260823.json`；专项 **20 passed**，不得将零触发当作豁免质量真值。
> **2026-08-23 本轮最终门禁实测修正**：后端全量 **1002 passed, 0 failed in 77.59s**；前端 type-check、Vitest 48 files/291 tests、build-only 均通过。T-16/T-18/E-11 的剩余证据边界不因门禁绿灯而改变。
> **2026-08-23 T-18 exemption 触发证据修正**：T-25 真实长篇失败样本已确认 `ending_pressure_missing` exemption 与 `critique_exemption_applied` 各 1 次；该章仍因 3 个 critical consistency 冲突拒绝。报告 `backend/output/t18-real-exemption-triggered-longform-audit-20260823.json`。这不是人工豁免质量真值，也不能替代成功率/误杀率评估。
> **2026-08-23 T-18 拒绝章趋势投影最终修复**：质量趋势 API 现在正确输出拒绝章的 `quality_gate_passed=false` 与 `ending_pressure_missing` exemption；真实 API 复核通过，专项 **21 passed**。这不是人工豁免质量结论。
> **2026-08-23 本轮最终门禁与 T-18 证据收束**：后端 **1003 passed, 0 failed in 95.32s**；前端 type-check、Vitest 48 files/295 tests、串行 build-only 均通过。T-18 已有 1 个真实 exemption 触发样本并正确投影到拒绝章趋势；人工真值、T-16 合法前后收益、E-11 真 repair 仍未闭环。
> **2026-08-23 当前硬缺口总账**：新增 `backend/output/novel-quality-gap-register-20260823.json`，明确人工真值、T-16 合法前后对照、E-01.2、T-18 人工质量判断、E-11 真 repair、T-06 degrade 率仍未完成。门禁虽通过后端 1003、前端 48 files/295 tests，但总目标保持 active。
> **2026-08-23 E-11/T-22 结构薄弱负控**：显式写作约束仍被流程修正为 2/2 通过，`quality_gate_repairs=[]`，未观察到 `repair_attempted=true`。不能把该负控当作 patch 收益证据。
> **2026-08-23 T-06 provider probe 更新**：`--provider-probe` 返回 ready/HTTP 200/27 个模型；报告 `backend/output/t06-provider-probe-audit-20260823.json`。这不是质量或稳定性验收，T-06 继续未完成。
> **2026-08-23 T-24 真实长篇 runtime contract 审计**：真实长篇成功库已验证 5 段 checkpoint、5 个 content_delta、task_completed、heartbeat 与 runtime events；证据 `backend/output/t24-real-longform-runtime-contract-audit-20260823.json`。scene-split timeout 当前生产路径 N/A，不伪造接线完成。

> **2026-08-23 目标恢复后的并行续审（总目标仍 active）**：已重新对账接续文档、gap register 与真实工作区，并启动多个子智能体分别审查未完成矩阵、T-16 严格对照和 E-11/T-22 repair。新增 T-06 真实 10 任务 batch：使用当前可用 `deepseek/deepseek-v4-flash-free`，**9 成功、1 最终空正文失败**；4 个成功调用在第一次空正文后重试成功，5 个单次成功。脱敏证据：`backend/output/t06-additional-live-batch-audit-20260823.json`。这是 retry/failure 分布补证，不可与 `gpt-5.6-sol` 混合估计稳定性，更不足以关闭 degrade rate。
>
> **2026-08-23 T-16 时间 provenance 回归修复（总目标仍 active）**：严格审计器对新报告优先读取 `generation_started_at`，旧报告缺该字段时才回退 `live-status`/`generated_at`，不再按路径推断 before/after；空或相等时间只记为 ambiguous。专项质量基准/repair **43 passed**，故意删除 legacy 时间回退后预期断言失败（`comparable_pair_count=0`），证明护栏有效。最终审计：41 summaries、18 完整指纹、9 同条件组、9 不可比候选、1 个当前冻结重复可比配对、0 ambiguous；仍无合法优化前后收益。报告：`backend/output/t16-quality-bench-comparability-final-20260823.json`。
>
> **2026-08-23 当前门禁（总目标仍 active）**：后端 `backend/.venv/Scripts/python.exe -m pytest -q` **1007 passed, 0 failed in 72.77s**；前端 `npm run type-check` 通过，`npm run test:run` **48 files / 305 tests passed**，`npm run build-only` 串行通过。期间 Vitest 真实发现两个“仅 null 三态指标被显示为质量通过”的前端回归；已由 `chapterQuality` 的有效质量信号判定与回归测试修复，未降低断言。人工标签、T-16 合法 before/after、E-01.2 prompt A/B、T-18 人工豁免真值、E-11 真 repair gain 和 T-06 长期 degrade rate 仍未完成。

> **2026-08-23 E-01.2 首轮真实 prompt A/B（总目标仍 active）**：新增非生产 benchmark prompt variant 能力，默认 baseline 保持旧行为，candidate 必须显式 `--live --prompt-variant candidate`，variant 与 system/user/prompt SHA-256 进入 request contract。真实固定 10 任务、同 Provider/model/scorer 的 baseline 与 candidate 均 **10/10 成功、0 provider failure**；两批任务集合相同，但 request/comparison contract 按 prompt 变化而不同，不能冒充 T-16 strict comparable。当前冻结评分器下 candidate 相对 baseline：平均分 **-79.5**、平均字数 **-304.9**，`ending_pressure_missing` 由 1 增至 2；结论为首轮负收益，**未改生产 prompt**。脱敏证据：`backend/output/e012-prompt-ab-audit-20260823.json`。
>
> **2026-08-23 E-11/T-22 真实 repair 触发证据（总目标仍 active）**：使用隔离 ASGI、`basic`、显式 self-critique 和当前可用 deepseek 通道完成两次真实 blocker 探针；两次均真实落盘 `repair_attempted=true`、`repair_rounds=2`，但 `repair_outcome=unchanged`，`issue_codes_after` 与 before 相同，严格子集改善 **0**，没有 `improved/passed` 收益样本。第二次同时真实触发 `exemptions=[event_density_weak]` 与 `critique_exemption_applied`，但仍因其他 blocker 拒绝；不能据此调阈值。脱敏证据：`backend/output/e11-t22-real-repair-triggered-audit-20260823.json`。

> **2026-08-23 门禁复验（总目标仍 active）**：用户中断前的后端全量测试已重新完整执行，结果 **1009 passed, 0 failed in 64.33s**。E-01.2 非生产 A/B 与 E-11/T-22 真实 repair 触发的相关专项另为 **45 passed**。这些门禁不替代人工双评标签、T-16 同请求契约的真实优化前后对照、E-11 strict-subset gain、T-18 人工豁免真值或 T-06 长期 degrade rate；目标继续保持 active。

> **2026-08-23 T-16/E-01.2 验收契约矛盾正式审计（总目标仍 active）**：独立复核确认：E-01.2 的真实 prompt 干预必然改变 `prompt_variant`、prompt SHA、`generation_request_contract_sha256` 与 `comparison_contract_sha256`；T-16 的 scorer 权重/反转项干预必然改变 `scorer_sha256` 与 comparison contract，但现行 strict comparator 同时要求这些字段不变。因此“优化变量改变”与“strict same contract”不能同时成立。脱敏报告：`backend/output/t16-e012-contract-contradiction-audit-20260823.json`。修正记录：T-16 应使用独立冻结 evaluator 比较 scorer 改前/改后；E-01.2 应标记 `controlled_prompt_ab=true`、`strict_t16_comparable=false`，不能继续把严格 comparable 当作必需完成条件。

> **2026-08-23 T-16 修正模型 selector simulation（总目标仍 active）**：对当前冻结数据库 151 条历史正文重新执行旧 scorer/当前 scorer 同正文 simulation：旧平均分 **1234.8543**，当前平均分 **953.0397**，平均 delta **-281.8146**，无失败记录。该报告只能证明 scorer 行为差异及 selector 研究输入，不能证明真实生成 before/after、人工质量提升或误杀率。证据：`backend/output/t16-frozen-selector-simulation-20260823.json`。

> **2026-08-23 T-16 selector simulation 扩展（总目标仍 active）**：将真实 baseline/candidate 两批各 10 个任务正文作为同任务候选池，分别用历史 scorer 与当前 scorer 模拟选优：旧 scorer 选择 baseline **3** / candidate **7**，当前 scorer 选择 baseline **4** / candidate **6**，选优变化 **1/10**。该证据说明 scorer 行为会影响候选选择，但 prompt contract 不同，且没有人工标签；不能当作生成 before/after 或质量收益。证据：`backend/output/t16-selector-simulation-e012-prompt-pool-20260823.json`。

> **2026-08-23 T-18 专项人工双审包（总目标仍 active）**：新增脱敏标注目录 `backend/output/quality-annotation-bundle-t18-exemption-20260823/`，包含 **6** 条样本：1 条真实 `triggered_rejected` exemption 触发拒绝样本、5 条真实 `not_triggered_success` 对照样本；正文未输出（`content_emitted=false`）。`labels.csv` manifest 校验通过，故意破坏 sample_id 后反向校验失败。标签仍保持空白，等待两名独立审阅人完成后再 merge/adjudicate；不会据未标注样本调整阈值。

> **2026-08-23 T-06 第三批真实重试分布（总目标仍 active）**：新增同固定任务集合、`gpt-5.6-sol` 第三批 live benchmark，**10/10 成功、0 provider failure、全部单次成功**。与此前批次合并的脱敏统计为 **29 个成功记录、1 个最终失败、4 个 retry_events**；其中包含不同模型批次，不能估计单一模型长期 degrade rate，也没有人工质量误杀率。证据：`backend/output/t06-multi-batch-retry-distribution-audit-20260823.json`。

> **2026-08-23 T-06 全量 gpt-5.6-sol inventory 复核（总目标仍 active）**：扫描当前 `output` 全部真实摘要，发现 **19 批、122 条成功记录、16 条最终失败记录**；但其中 **51 次调用缺少 retry_events 字段**，且历史批次含重复任务与不同 request/scorer/comparison contract，不能把原始计数直接当标准化长期 degrade rate。脱敏报告：`backend/output/t06-full-gpt56-inventory-audit-20260823.json`。

> **2026-08-23 T-18 标注包一致性修复（总目标仍 active）**：复核发现专项包 `T18-01` 的 `exemption_status=triggered_rejected` 与版本 metadata 的空 exemption 数组不一致；现按权威 runtime/trend 报告补正 `detected_exemption_codes=ending_pressure_missing`，manifest 增加来源说明。重新执行 labels/manifest 校验通过；标签仍为空，不据此计算指标或调阈值。

> **2026-08-23 T-16 selector simulation 可复跑修正（总目标仍 active）**：新增 `backend/scripts/audit_frozen_selector_simulation.py` 与专项 **2 passed**。复跑发现此前一次性统计遗漏 benchmark 顶层 `target_word_count/min_word_count` 映射；按真实契约修正后，旧 scorer 选 baseline **3** / candidate **7**，当前 scorer 选 baseline **5** / candidate **5**，选择变化 **2/10**。新报告 `backend/output/t16-selector-simulation-reproducible-20260823.json` 覆盖旧的一次性 4/6 统计；仍只是 scorer selector 行为证据，不是生成 before/after 收益。

> **2026-08-23 T-18 双审模板交付（总目标仍 active）**：在专项 6 条脱敏包中预生成 `reviewer-a-template.csv` 与 `reviewer-b-template.csv` 两份独立模板；两份均为 6 行、0 labeled，manifest 校验分别通过。未填写任何人工判断，等待两名独立审阅人实际输入后再 merge/adjudicate。

> **2026-08-23 E-01.2 prompt A/B 可复跑审计（总目标仍 active）**：新增 `backend/scripts/audit_quality_bench_prompt_ab.py` 与专项 **2 passed**；脚本明确校验同任务/provider/model/scorer、baseline/candidate variant，以及 request/comparison contract 必须不同。真实复跑 delta 保持：candidate 平均分 **-79.5**、平均字数 **-304.9**；状态明确为 controlled A/B、非 strict T-16 comparable，生产 prompt 未改变。报告：`backend/output/e012-prompt-ab-audit-reproducible-20260823.json`。

> **2026-08-23 完整 T/E 任务矩阵修正（总目标仍 active）**：生成 `backend/output/novel-quality-task-matrix-current-20260823.json`，完整索引 **26 个 T 任务、12 个 E 任务、39 个条目**（含 1 个外部人工标签缺口），去重后 **6 个唯一硬缺口**：人工标签、T-16、E-01.2、T-18、E-11/T-22、T-06。首次解析漏掉 E 表格行，已修正并重新生成；矩阵仍不把自动化/受控 A/B/selector simulation 当完成。

> **2026-08-23 当前任务矩阵一致性审计（总目标仍 active）**：新增 `backend/output/novel-quality-task-matrix-consistency-20260823.json`，结果 `valid`：26 个 T、12 个 E、1 个外部人工标签条目；无重复/缺失/额外编号，hard-gap 键与 gap register 完全一致，所有引用证据路径存在。此前出现的 `T-1..T-9` 只是审计脚本格式错误，已修正为 `T-01..T-26`。索引有效不等于硬缺口完成。

> **2026-08-23 E-11/T-22 repair diagnostics 接线（总目标仍 active）**：`_attempt_structural_gate_repair` 现在请求 `return_diagnostics=true`，兼容旧式字符串返回；仅将策略名、问题数、attempt mode/changed/accepted/reason、前后计数和安全计数脱敏写入 `repair_summary.revision_diagnostics`，不保存正文或指纹。定向 repair 专项 **12 passed**，后端全量 **1016 passed**。这增强了未来真实 repair 的可审计性，但不改变质量门，也不构成 `improved/passed` gain；既有真实两次 repair 仍均 unchanged。

> **2026-08-23 E-11 diagnostics 新探针阻断记录（总目标仍 active）**：一次新的隔离 deepseek repair diagnostics 探针在 Provider/生成阶段失败，未进入质量门、未调用 repair、未产生正文或 diagnostics；已单独脱敏记录 `backend/output/e11-t22-real-repair-diagnostics-probe-blocked-20260823-late-run.json`。该阻断不改变既有真实 repair 统计：2 次 attempted、4 轮、均 unchanged，improved/passed 仍为 0。

> **2026-08-23 人工标签最终完整性门（总目标仍 active）**：`export_quality_annotation_bundle.py` 新增可选 `--require-complete`；模板阶段普通校验仍允许空白，但最终校验要求每行 8 个 `human_*` 字段均为 `true/false/na`。T-18 reviewer-A/B 空模板普通校验通过，追加 `--require-complete` 正确失败并报告 **0/6 complete rows**；专项标注测试 **6 passed**，后端全量 **1017 passed**。这只是防止误报完成，未填充人工标签。

> **2026-08-23 schema-aware 证据批量审计（总目标仍 active）**：对当前 E-09 trend 与 E-11 repair 报告执行 schema-aware 脱敏/计数审计：**19 个当前报告全部通过**；2 个旧 legacy 摘要被显式标记为 schema 不兼容并跳过，未误判为当前证据失败。报告：`backend/output/novel-quality-evidence-batch-consistency-audit-20260823.json`。该审计只证明证据结构和脱敏一致，不证明人工质量或 repair gain。

> **2026-08-23 通用人工标注包说明同步（总目标仍 active）**：通用 19 条标注包 README 已补充“模板校验 vs `--require-complete` 最终验收”区别，并新增 CLI 回归；标注专项 **7 passed**，后端最新全量 **1018 passed**。空白模板仍未被当成人工真值，等待两名审阅人填写。

> **2026-08-23 完成资格保护器（总目标仍 active）**：新增 `backend/scripts/audit_novel_quality_completion.py` 与专项测试；当前输出 `completion_eligible=false`，明确列出 6 个硬阻塞：人工标签、T-16、E-01.2、T-18、E-11/T-22、T-06。该保护器只防止误宣称完成，不替代人工真值或 Provider 收益证据。

> **2026-08-23 完成保护器门禁复验（总目标仍 active）**：新增完成资格保护器后，后端全量测试最新为 **1019 passed, 0 failed in 80.88s**；保护器仍报告 `completion_eligible=false`，六项硬缺口未被绿灯掩盖。

> **2026-08-23 完成保护器双审/仲裁校验补强（总目标仍 active）**：完成门现在拒绝单边完整、空白模板、缺失/错误 source_files、身份不一致或未解决 `adjudicate`；专项 **17 passed**，后端全量 **1024 passed**，前端三项门禁通过。不得用自动化测试绿灯替代人工标签或 Provider 收益证据。

> **2026-08-23 E-01.2 Provider 阻断证据收束（总目标仍 active）**：baseline/candidate 各 10 任务均因 Provider SSE HTTP 503 阻断，0 条 live record；prompt A/B 审计器现在明确输出 `ab_success=false` 与 `aggregate_delta=null`，专项 4 passed、后端全量 1026 passed；不得把阻断批次当收益证据。

> **2026-08-23 T-16 corrected acceptance 接口补齐（总目标仍 active）**：新增固定输入/双 scorer/独立冻结 evaluator 的结构审计与 6 项回归；它只能证明证据可进入 T-16 评审，不能证明质量收益。没有真实双 scorer 批次前不得关闭 T-16。

> **2026-08-23 T-06 标准化 rate 审计接口补齐（总目标仍 active）**：新增显式 summary/manifest 聚合器与 7 项回归；契约混杂、缺 retry_events、Provider 阻断和最终失败不会被偷偷计入 rate，insufficient/blocked 必须输出 null。不得用 inventory 计数宣称长期 degrade rate。

> **2026-08-23 E-11/T-22 repair gain 审计接口补齐（总目标仍 active）**：新增 11 项回归，缺 diagnostics、unchanged、未严格子集改善、未最终 passed 或 Provider 阻断均只能输出 insufficient/blocked，gain=false；不得用自动化接口代替真实 Provider repair gain。

> **2026-08-23 本轮后端/前端门禁复验（总目标仍 active）**：后端 `pytest -q` **1043 passed**；前端 type-check 通过、Vitest **48 files/305 tests**、build-only 通过。门禁绿灯不关闭六项真实质量证据缺口。

> **2026-08-23 Provider 最小 baseline 续探针（总目标仍 active）**：仅执行 `smoke-dialogue` 仍实际 SSE HTTP 503、0 条记录；不得把 `/models` 200 或 probe ready 当作 completion/质量证据。

> **2026-08-23 总任务接续与 Provider 恢复（总目标仍 active）**：`TASK_HANDOFF_NOVEL_QUALITY.md` 已写入项目全貌、Agent 创作工作台架构、动态工具注册、分级审批、聊天主界面、SSE 过程摘要、数据模型、分阶段实施和验收方案。T-26 现独立列为第 7 个硬缺口；E-02/T-25 降为 partial。用户更新 `.env` 后 Provider 解析为 `gpt-5.6-sol`，baseline/candidate 各 10/10 成功；controlled A/B 平均分 +144.4、字数 -695.1，仍无人工真值且不进入生产。

> **2026-08-23 Agent Phase 1 最小闭环落地（总目标仍 active）**：新增后端 Agent 工具注册、风险策略、项目范围校验、provider-free 计划 API（`/api/agent/tools`、`/api/agent/plan`）及 8 项回归；新增前端 `AgentWorkspace`、`/agent` 路由、首页入口和 3 项回归。后端全量 **1051 passed**；前端 type-check、Vitest **49 files/308 tests**、build-only 通过。下一阶段才接入真实 service 工具、会话持久化、SSE 运行流和审批执行。
