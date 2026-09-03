> **2026-08-23 T-16 legacy 时间证据兼容修正（总目标仍 active）**：严格比较器对新 live 批次使用 `generation_started_at`，对旧摘要兼容回退 `generated_at`，`ambiguous_time_pairs` 原因统一为 `missing_or_equal_generated_at`；专项 **34 passed**。当前只读扫描 41 个摘要、18 个完整指纹、9 个同条件组、9 个 candidate、1 个 comparable、0 个 ambiguous；唯一 comparable 是当前冻结评分器/请求契约的重复 batch，不是优化前后收益，未调用 Provider。

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

> **当前外部证据复核（总目标仍 active）**：对现有脱敏产物重新读取而非依赖历史叙述：T-16 严格可比性报告为 12 个完整指纹、**0 个合法改前/改后配对**；人工标注包为 19 行、8 个核心 `human_*` 字段全部空白（**0/19 labeled**）；质量趋势为 `exemption_counts={}`。相对地，E-08 v4 真实批次为 `passed`、10/10 正文、0 provider failures，最低字数、章末压力、事件密度、长章密度、状态变化均 10/10；其中 `benchmark-bridge-3000` 有真实 `attempts=2`，可作为重试观测，但不替代人工标签或 T-16 前后收益。

> **当前证据口径校正（总目标仍 active）**：E-06 真实 ASGI 证据 `backend/output/e06-three-candidate-asgi-20260822-gpt56-v4.json` 已达到 3 候选、8 维差异、选中 margin=319≥300；因此 T-12 的“真实候选择优对比”缺口已由单次真实证据补齐，但不代表 T-16 前后收益或全量误杀率已证明。E-08 v4 也已具备 10/10 正文、SSE 与核心结构门指标通过；人工评价、改前对照和跨题材人工真值仍缺。

> **本轮 T-18/D-14 观测更新（总目标仍 active）**：质量门新增 `critique_exemption_applied`，并写入 `quality_metric_snapshot` 与 `quality_gate_summary`；历史/简化 guard 缺失快照时也会创建兼容快照。相关质量门专项 **195 passed**，反向篡改验证通过；行为阈值和放行结果未改变。后端清缓存全量 **970 passed, 0 failed in 57.70s**。
> - 这只完成“观测接线”，没有制造真实豁免样本，也没有调高/调低豁免阈值；当前趋势仍 `exemption_counts={}`，T-18 真实触发率与质量真值继续缺失。

> **本轮最新实测（当前总目标仍 active；按当前任务日期记账）**：真实长篇 ASGI smoke 已完成第三轮闭环，使用 `gpt-5.6-sol`、目标 20,000 字、分段上限 4,500、请求与轮询统一 14,400 秒预算；结果 `LONGFORM_SMOKE_PASS`，`task=succeeded`、`segments=5`、`deltas=5`、正文 **39,406 字**、事件 **73** 条。此前两项真实生产缺陷均已修复并保留失败证据：
> - heartbeat/stale：长篇分段入口现在传递 Provider 等待回调；真实运行期间每约 60 秒刷新 `generate_variants` 心跳，未再出现 `STALE_TASK/heartbeat timeout`。
> - content delta：长篇分段事件从错误的 `content` 改为严格 `content_delta`，携带完整段正文、`segment_index` 与 `content_is_preview=false`；真实 smoke 统计 `deltas=5`。
> - 相关专项 **56 passed**，反向篡改验证通过；后端清缓存全量 **969 passed, 0 failed in 80.33s**；前端三件套仍为 type-check 通过、**48 files / 263 tests passed**、build-only 通过。
> - smoke 脚本新增 `LONGFORM_SMOKE_TIMEOUT_SECONDS`，默认仍为 1,800 秒；本次仅因真实长篇后处理耗时显式使用 14,400 秒，未降低质量门槛。
> - 总目标仍不可宣称完成：人工标签 0/19、T-16 合法改前配对 0、T-18 exemption 真值 0、E-09 跨题材人工真值仍缺；T-25/T-26 仍保留真实语料/产品语义交叉审计缺口。

> **前一轮最新全量门禁与趋势审计收束（总目标仍 active）**：
> - 后端清缓存全量 **965 passed, 0 failed in 80.06s**；前端全量 **48 files / 263 tests passed**，`npm run type-check` 与串行 `npm run build-only` 通过。
> - 修复趋势审计测试重复函数名造成的隐藏回归：显式承接锚点场景与缺失承接场景现在分别验证，审计专项 **12 passed**；不再让后定义测试覆盖前定义测试。
> - 最新趋势脱敏报告 `backend/output/quality-trend-audit-final-20260822T151540Z.json`：105 trend rows、69 selected metadata、56 mission-quality rows、50 continuity observations、2 missing、1 late、14 gates、0 exemptions。
> - 本轮仍未制造人工标签、T-16 改前 batch 或 T-18 exemption 真值；总目标继续 active。
> **2026-08-22 23:45（Asia/Shanghai）T-08/T-15/E-07/E-09/E-10 与前端质量链路收束（总目标仍 active）**：并行审计确认并修复历史/跨层质量字段丢失与空值误判：
> - 后端趋势 API 与脱敏审计现补齐旧嵌套 guard 的静态段/章末压力细粒度字段，并回填历史 continuity、任务书体检和相关诊断；受影响专项 **41 passed**。最新趋势报告：`backend/output/quality-trend-audit-final-20260822T151540Z.json`，105 trend rows、69 selected metadata、56 mission rows、50 continuity observations、2 missing、1 late、14 gates、0 exemptions。
> - 前端修复旧趋势 payload 缺少 `blocker_codes` 崩溃、缺失 score/word_count/chapter 数据渲染 undefined、`scene_fulfillment_rate=null` 误判为 0% 风险；前端全量 **48 files / 263 tests**，type-check、串行 build-only 通过。
> - 最新后端清缓存全量 **965 passed, 0 failed in 80.06s**；T-06/T-07 未发现生产缺陷，T-12/T-17/T-23 定向 214 passed。
> - 总目标仍 active：人工标签 0/19、T-16 合法改前配对 0、T-18 exemption 真值 0、E-09 跨题材人工真值仍缺。
> **2026-08-22 23:15（Asia/Shanghai）E-11/T-25/T-15 后门禁与台账更新（总目标仍 active）**：
> - E-11 warning patch 丢失缺陷已修复：独立可修复 warning 白名单确保 focus/continuity 等 patch 进入 `revise_chapter`；相关专项与调用链 **126 passed**。
> - T-25 非法 `next_segment_index` 已统一转换为 `LongformGenerationContractError`；T-25/长篇专项 **19 passed**，并已通过 Python 编译检查。
> - T-15 跨题材脱敏审计：E-08 七个正式题材组全部覆盖但各仅 1 条；E-09 无题材标签和正文，跨题材召回仍不可证实。审计报告：`backend/output/t15-cross-genre-marker-audit-20260822T134441Z.json`。
> - 后端最新清缓存全量 **953 passed, 0 failed in 61.57s**；前端最近完整门禁 48 files/256 tests、type-check、串行 build-only 通过。
> - 总目标继续 active：人工标签 0/19、T-16 合法改前配对 0、T-18 exemption 真值 0、E-09 跨题材人工真值仍未闭环。
> **2026-08-22 22:55（Asia/Shanghai）E-11/T-25/T-15 本轮修复与门禁收束（总目标仍 active）**：并行反向审计确认并修复三项本地质量链路问题/证据缺口：
> - E-11：`_build_quality_gate_patch_repair_issues()` 原先把仅含 blocker 的 `quality_issue_codes` 当 warning patch 白名单，导致 `focus_character_missing`、`continuity_inherit_missing` 等 warning 在进入 `revise_chapter` 前被丢弃；现改用独立可修复 warning 白名单，相关专项与调用链测试通过。
> - T-25：`LongformCheckpoint.from_dict()` 对非法 `next_segment_index` 原生抛 `ValueError`；现统一转换为 `LongformGenerationContractError`，专项回归通过。
> - T-15：新增脱敏跨题材标记审计；E-08 七个正式题材组全部覆盖，但每组仅 1 条；E-09 无题材标签/正文，不能证明跨题材覆盖。专项 3 passed，报告：`backend/output/t15-cross-genre-marker-audit-20260822T134441Z.json`。
> - 本轮相关专项 **126 passed**，T-25 专项 **19 passed**；最新后端清缓存全量 **953 passed, 0 failed in 61.57s**。前端最近有效门禁仍为 48 files/256 tests、type-check、串行 build-only 全通过。
> - 仍未闭环：人工标签 0/19、T-16 合法改前配对 0、T-18 exemption 真值 0、E-09 跨题材人工真值。总目标继续 active。
> **2026-08-22 22:25（Asia/Shanghai）外部质量证据全工作区搜寻（总目标仍 active）**：递归检查工作区内所有 `labels.csv`、人工审阅字段、benchmark summary 指纹和 exemption 记录；仅发现 `backend/output/quality-annotation-bundle-20260821/labels.csv` 这一份标签文件，19 行 `human_*`/`reviewer_id`/`review_notes` 全部为空；未发现额外人工副本、完整 request fingerprint 的改前 batch 或真实 exemption 样本。
> - 该搜寻只证明当前工作区没有遗漏证据，不把缺失当作完成；T-16、T-18 和人工真值继续保持未闭环。
> **2026-08-22 22:05（Asia/Shanghai）E-09 审计后门禁更新（总目标仍 active）**：新增 20 章 ASGI 脱敏一致性审计后，后端清缓存全量 **946 passed, 0 failed in 60.33s**。前端最近有效完整门禁仍为 48 files/256 tests、type-check、串行 build-only 通过。
> - E-09 真实批次内部一致性已证实；仍不替代人工质量标签、T-16 改前生成批次、T-18 exemption 真值或跨题材人工误杀评估。
> **2026-08-22 21:45（Asia/Shanghai）E-09 20 章证据一致性审计（总目标仍 active）**：新增只读 `backend/scripts/audit_multichapter_asgi_evidence.py`，兼容旧报告仅含 `chapters` 的格式，并验证计数、放行率、分布样本量及正文键泄漏。专项测试 **3 passed**；最新审计报告：`backend/output/e09-multichapter-evidence-audit-20260822T131656Z.json`，结果 valid=true。
> - 真实批次内部一致性：20 次尝试、19 放行、1 拒绝、放行率 0.95；拒绝样本保留，分布 n=19；报告未输出正文。该证据增强 E-09/E-02～E-05 的真实分布可信度，但不等于人工质量接受率、T-16 前后收益或 T-18 豁免真值。
> **2026-08-22 21:25（Asia/Shanghai）T-16 历史重建可行性核查（总目标仍 active）**：检查历史提交 `3e6406070af5a391deed7427198258691dd85ece` 与现有证据后确认：该提交不包含当前 `backend/scripts/quality_bench.py`、`backend/prompts/contracts/chapter_writing_contract.v1.md` 或 v4 生成请求契约；现有旧 benchmark batch 还缺完整 request fingerprint，且任务集合只有 3 个 smoke 任务。
> - 因此不能从历史提交合法重建“同任务、同模型、同 prompt/request contract”的改前真实生成批次；旧评分器对 151 条历史正文的重算仍只能证明评分行为差异，不是生成前后质量收益。T-16 继续保持部分完成，不伪造对照。
> - 当前可审计结论：严格 benchmark 扫描仍为 35 汇总、12 完整指纹、8 个单成员同条件组、0 个合法配对；人工标签 0/19；T-18 exemption 真值 0。
> **2026-08-22 21:05（Asia/Shanghai）T-17/E-09/E-10 继续审计与修复（总目标仍 active）**：并行审计构造出真实边界反例：最终确定性清理使同一正文 score 从 937 变为 919、字数从 931 变为 928，而旧 structural gate 仍保持原快照；现已在最终清理后重算 structural gate，并写回 runtime quality gate。T-17 定向 **213 passed**。
> - E-09/E-10 趋势审计已对齐 API 的 selected-version 语义，并对缺失 `mission_quality_codes` 的历史任务书只读重算；审计专项 **8 passed**。最新报告：`backend/output/quality-trend-audit-selected-mission-20260822T125059Z.json`，105 trend chapter rows、69 selected version metadata rows、56 mission-quality rows、14 gate rows、0 exemptions。
> - T-12/T-24/T-25/E-07/E-11 并行复核未发现新的已证实生产缺陷；T-24/T-25 68 passed，E-07/E-11 51 passed，T-12/T-17 213 passed。T-17 本轮已从“仅契约证据”提升为“有真实边界反例与修复回归”。
> - 最新后端清缓存全量 **943 passed, 0 failed in 62.74s**；前端最近完整门禁仍为 48 files/256 tests、type-check、串行 build-only 全通过。人工标签 0/19、T-16 合法改前配对 0、T-18 exemption 真值 0 仍未闭环。
> **2026-08-22 20:40（Asia/Shanghai）并行子线程审计与门禁收束（总目标仍 active）**：按用户要求开启 6 个独立线程，分别审计 T-06/T-07、T-09～T-11、E-02～E-05、E-07～E-11、T-24/T-25 和前端质量链路；均保留现有未提交成果，未使用 reset/stash/clean。
> - 确认并修复后端趋势脱敏审计漏合并 `story_progression_guard` 的跨层口径缺陷；仅回填缺失字段，不覆盖 `quality_metrics`，排除两个嵌套快照；定向趋势专项 17 passed，实际报告 `quality_metric_rows=150`、`gate_rows=35`、`exemption_counts={}`。
> - 确认并修复前端旧快照缺字段时把 `undefined` 当作已评估/可控的三态误判；涉及趋势面板、质量类型、章节质量摘要和版本详情；定向 18 passed，前端全量 **48 files / 256 tests passed**。
> - 修复 E-02～E-05 脱敏校准与生产评分器的人物动作口径不一致：读取 metadata、提取任务书焦点人物名、兼容缺列/坏 JSON；专项 3 passed。最新校准报告：`backend/output/quality-metric-corpus-calibration-20260822T122852Z.json`。
> - 并行审计未发现 T-06/T-07、T-09～T-11、T-24/T-25 已被证据证明的新增生产缺陷；相关线程分别完成 41/6、21/13/15、68 项定向核查。
> - 最新门禁：后端清缓存 **939 passed, 0 failed in 111.49s**；前端 type-check 通过、48 files/256 tests、串行 build-only 通过。总目标继续 active；人工标签 0/19、T-16 合法改前批次 0 配对、T-18 exemption 真值仍未闭环。
> **2026-08-22 20:25（Asia/Shanghai）本轮后端门禁更新（总目标仍 active）**：严格 T-16 可比性审计与 T-13/T-26 语义校准新增代码已完成验证；后端清缓存全量 **935 passed, 0 failed in 99.54s**。前端本轮无源码变更，上一轮 type-check、48 files/250 tests、串行 build-only 仍为最近有效门禁。
> - 当前没有合法 T-16 改前/改后候选配对，没有人工质量标签，没有真实 T-18 exemption 样本；这些缺口保持原样，不以自动化通过替代。
> **2026-08-22 20:10（Asia/Shanghai）T-13/T-26 语义标记校准收束（总目标仍 active）**：新增 `backend/scripts/audit_dialogue_state_marker_categories.py` 与回归测试，定向 T-13/T-26/质量门专项 **196 passed**。最新证据：`backend/output/dialogue-state-marker-category-audit-20260822T115213Z.json`、`backend/output/dialogue-state-marker-audit-20260822T114958Z.json`。
> - 151 条源记录中 149 条达到 800 字校准门槛；对话状态标记非零 148/149（0.9933），p05/p50/p95 为 3.0/12.0/27.6；112 条任务书声明对话样本全部有标记。揭示/选择/外部压力分类命中率分别为 66.44%/68.46%/54.36%。
> - 历史任务书没有 `expected_dialogue=false` 样本；候选新增词的影响模拟也没有把任何零标记样本抬成非零。因此没有足够证据安全修改生产词表或阈值；T-13/T-26 保持“本地逻辑已证实、真实语义真值待补”，不把词频覆盖率当人工质量真值。
> **2026-08-22 19:55（Asia/Shanghai）T-16 严格可比性审计（总目标仍 active）**：新增只读审计器 `backend/scripts/audit_quality_bench_comparability.py`，对 `backend/output` 的 35 个 `rescore-summary.json` 逐一检查任务集合、任务合同、生成请求契约、Provider、模型和评分器指纹；专项测试 **3 passed**。最新证据：`backend/output/t16-quality-bench-comparability-20260822T114639Z.json`。
> - 结果：35 个汇总、12 个完整指纹、8 个严格同条件分组、**0 个合法改前/改后候选配对**。8 个分组均只有 1 个批次；v3/v4、单任务复验和不同 prompt/请求契约均被正确分开，不能拼成 T-16 基线。
> - 审计只证明可比性缺失，不证明质量提升；没有制造改前批次，没有把评分器重算或相似任务当作前后收益。T-16 真实收益证据仍缺。
> - 同轮只读核查：质量趋势 `gate_rows=35`、`exemption_counts={}`；人工标注 `labeled_row_count=0/19`。T-18 与人工质量真值仍未闭环。
> **2026-08-22 19:45（Asia/Shanghai）本轮门禁收束（总目标仍 active）**：修复后的校准脚本反向验证已完成：临时恢复旧位置参数时新增测试按预期失败，恢复正确关键字参数后通过。完整门禁：后端清缓存 **931 passed, 0 failed in 111.85s**；前端 **48 files / 250 tests passed**；`npm run type-check` 通过；串行 `npm run build-only` 通过。

> - 本轮没有修改人工标签、没有制造 T-16 改前批次、没有调整 T-18 豁免阈值，也没有把历史评分重算当成真实质量收益。下一轮继续优先寻找合法同条件改前批次；若仍不存在，保持缺口记录。
> **2026-08-22 19:30（Asia/Shanghai）目标恢复与本轮校准更新（总目标仍 active）**：已重新恢复总目标并登记当前执行目标：继续依据本接续文档完成 T/E 审计、生产重构、真实验证和证据闭环；每阶段更新目标，不以几十万字任务表或自动化绿灯冒充完成。工作区现有未提交改动全部保留。
> - 连续性/质量语料只读校准已完成：历史数据库 151 条版本，评分器旧版/当前版 151/151 comparable、0 failed；新证据为 backend/output/evaluator-rescore-comparison-20260822T112728Z.json。这只证明评分行为差异，不是改前/改后真实生成收益。
> - E-02～E-05 脱敏分布校准脚本曾因生产函数签名演进而失败；已修复为显式关键字参数并新增回归测试，专项 1 passed。最新证据：backend/output/quality-metric-corpus-calibration-20260822T112939Z.json，151 条、正文和说话人均未写入报告。
> - 合法 T-16 改前基线仍不存在：已有 baseline 只有 3 个 smoke 任务，与当前 10 个中文 benchmark 任务、模型/请求契约不一致，不能比较。T-18 趋势审计仍为 exemption_counts={}；人工标注包仍 labeled_row_count=0/19。
> - 因此本轮完成的是校准脚本修复、脱敏统计和缺口核验；T-16 真实前后收益、T-18 豁免真值、人工质量标签仍未闭环，目标不得标记 complete。
# 小说生成质量执行审计台账


> **2026-08-22 连续性语义回退重评分复验（目标仍 active）**：对 v4 10 条已落盘正文使用当前连续性观测器 `--rescore-only` 重算：原唯一 `continuity_inherit_missing` warning 被保守的“两项中文内容锚点”回退消除，质量问题记录由 `1` 降为 `0`；最低字数/章末压力/事件密度/长章密度/状态变化仍全部 `10/10`。这是对既有正文的评分器回归证据，不是重新生成或人工真值，故仍不关闭 T-16/T-18。



> **2026-08-22 当前权威状态收束（总目标仍 active）**：E-08 v4 固定中文 10 任务已真实完成核心验收：10/10 正文、SSE、0 provider 失败；最低字数/章末压力/事件密度/长章密度/状态变化均 10/10，唯一保留 `continuity_inherit_missing` warning。E-06 严格三候选已通过（3候选、8维差异、margin 319）。最新后端 925 passed；前端 type-check、48 files/247 tests、串行 build-only 均通过。尚未完成的硬缺口仅剩：19 条人工标签为空、T-16 无同任务同模型同请求契约改前批次、T-18 无真实 exemption 质量真值；因此不得关闭总目标或宣称整份接续文档完成。



> **2026-08-22 E-06 严格三候选复验通过（目标仍 active）**：新证据 `backend/output/e06-three-candidate-asgi-20260822-gpt56-v4.json`：临时使用 provider 已列出的 `gpt-5.6-sol`、中文任务契约、显式 `versions=3`，真实结果 `successful/waiting_for_confirm`；候选数 `3`，差异维度 `8`，流水线选中 v3=1301，最佳落选 v2=982，margin **319 >= 300**；三项 E-06 标志均 true。E-06 现可标记“已证实”，但这不是 T-16 改前后收益，也不替代人工标签/T-18 exemption 真值。



> **2026-08-22 E-08 v4 核心门禁最终状态（目标仍 active）**：
> - 固定中文任务书 + `gpt-5.6-sol` + v4 prompt + SSE/一次重试的完整批次：`backend/output/quality-bench-live-e08-gpt56-localized-v4-final-20260822/provider-live-20260822T100955Z/`。结果 `10/10` 有正文、`10/10` SSE、0 provider failure、0 retry exhausted；平均 5588.4 字、平均分 3713.3。最低字数、章末压力、事件密度、长章密度、状态变化均 `10/10`。
> - 唯一质量问题为 `benchmark-bridge-3000` 的 `continuity_inherit_missing` warning；不影响本批核心门禁通过，但说明连续性精确匹配仍有真实告警，不能报为零问题或人工质量真值。
> - 最新前后端门禁：后端 `925 passed, 0 failed`；前端 type-check 通过、`48 files / 247 tests` 通过、单独 build-only 通过。并发 build/type-check 曾触发 `components.d.ts` 写冲突，串行 build 已通过。
> - E-08 核心 provider/生成批次证据已具备；T-16 仍缺同任务同模型同请求契约的改前批次，人工 labels 仍 `19/19` 空白，E-06 仍选优差 `240<300`，T-18 仍无 exemption 真值。总目标继续 `active`。



> **2026-08-22 E-08 v4 完整中文批次（目标仍 active）**：
> - v4 prompt 在 v3 基础上增加“未达最低字数不得收束”和末段 `turn/end_hook/下一步压力` checklist；v4 prompt 回归 25 passed。
> - 最新完整证据：`backend/output/quality-bench-live-e08-gpt56-localized-v4-final-20260822/provider-live-20260822T100955Z/`。临时使用 provider 已列出的 `gpt-5.6-sol`（不改默认模型），固定中文 10 任务结果 **10/10 有正文、10/10 SSE、0 失败、0 重试耗尽**；平均字数 `5588.4`，最低字数达成 `10/10`，章末压力 `10/10`，事件密度 `10/10`，长章密度 `10/10`，状态变化 `10/10`，平均分 `3713.3`。
> - 仍有 1 条 `continuity_inherit_missing` warning（bridge 任务），因此这是“核心质量维度 10/10、仍有连续性告警”的通过证据，不是人工真值、误杀率或前后收益证明；不能关闭 T-16/T-18，也不能把临时模型批次当改前对照。
> - 先前 v3 中文批次 9/10 和独立传输复验均保留，不与 v4 拼接；新 v4 fingerprint 为 schema v2，任务书/请求契约/评分器均可追溯。



> **2026-08-22 T-16 指纹顺序与全量稳定性复核（目标仍 active）**：生成请求契约哈希现按 `mission_id` 与任务合同共同排序，任务文件遍历顺序变化不会制造伪“不一致”；benchmark 回归 23 passed。服务测试+趋势组合 819 passed，全量清缓存复跑 **918 passed, 0 failed in 87.44s**。中文 E-08 批次仍为 9/10 正文，独立失败任务传输复验成功但不得拼批；人工 19/19 空标签、改前基线、E-06 >=300、T-18 真值仍缺。



> **2026-08-22 E-08 中文契约最终批次与质量门修复（目标仍 active）**：
> - 固定 10 个 benchmark 任务已中文本地化，生产 mission-hit 增加保守中文 2 字内容锚点；旧英文批次不再与新契约比较。中文锚点专项/反向 **25 passed**。
> - 中文任务 + gpt-5.6-sol + SSE v3 批次证据：`backend/output/quality-bench-live-e08-gpt56-localized-v3-20260822/provider-live-20260822T080650Z/`。结果 **9/10 有正文、1/10 RemoteProtocolError**；9 条最低字数、章末压力、事件密度、状态变化均 100%，仅 2 条有 warning 级问题。失败任务独立传输复验成功，但不与 9/10 拼接。
> - `httpx.TransportError` 已加入一次有界重试；传输回归 21 passed。最新后端全量 **917 passed, 0 failed in 87.25s（--cache-clear）**。
> - 该批仍不是稳定 10/10，且没有改前同任务同模型批次，因此 E-08/T-16 仍未关闭；人工标签 19/19 空白，E-06 选优差 240<300，T-18 无豁免真值。



> **2026-08-22 中文任务契约与传输复验（目标仍 active）**：
> - **根因修复**：固定 benchmark 任务书原为英文，而中文小说正文与 `mission_hit_count` 使用字符串锚点，导致真实兑现“账簿/照片/脚步”等仍可能 0 命中并误报 `chapter_progression_weak`。10 份 `bench_missions/*.json` 已语义等价本地化为中文；生产评分新增保守中文 2 字锚点（保留旧整句/人物 token 优先、过滤功能/泛化词、上限 48、至少 2 命中）。专项含篡改反证 **25 passed**，后端全量 **915 passed, 0 failed in 83.75s**。旧英文任务 batch 与新契约不可比较。
> - **中文契约 10 任务 gpt-5.6-sol SSE v3**：证据 `backend/output/quality-bench-live-e08-gpt56-localized-v3-20260822/provider-live-20260822T080650Z/`；**9/10 有正文、1/10 RemoteProtocolError**。9 条的最低字数、章末压力、事件密度、状态变化均 `100%`，仅 2 条留 warning 级问题（承接缺失、静态风险）。该批不是 10/10，不关闭 E-08。
> - **传输复验**：`httpx.TransportError` 现纳入一次有界重试（定向 benchmark 21 passed）；此前失败的 `benchmark-climax-6000` 在独立复验 `backend/output/quality-bench-e08-transport-single-20260822/provider-live-20260822T084925Z/` 成功，13,894 字且最低字数/章末/密度/状态变化均通过。此独立单任务不得与 9/10 批次拼接成同批 10/10。
> - **外部缺口仍存**：人工标签 19/19 空白；T-16 没有同任务同模型同请求契约的改前生成批次；E-06 选优差仍 240<300；T-18 缺真实 exemption 真值；E-08 还缺同一中文契约下稳定完整 10/10 批次和人工评价。


 > **2026-08-22 UTF-8 门禁复核**：中文任务关键词异常在两种测试顺序下均未复现；UTF-8 环境后端全量 **911 passed, 0 failed in 83.44s**。记录为 Windows GBK 输出解码噪声，不作为代码缺陷。

 > **2026-08-22 E-08 compact 指标字段补齐**：benchmark JSON/CSV 现覆盖反转、对白/动作/描写配比、说话人、场景切换、承接、任务书体检等已实现观测；专项 20 passed。UTF-8 后端全量 **911 passed, 0 failed in 81.21s**；未发起新的 provider 请求。

 > **2026-08-22 E-06 脚本恢复与 margin 口径修复**：恢复被异常覆盖的真实三候选 ASGI 审计脚本，并将候选 margin 的 score 权威固定为完整 story guard；compact snapshot 只覆盖观测维度。冲突与反向测试已补；定向 229 passed，后端全量 **907 passed, 0 failed in 73.84s**。现有 E-06 postfix 结果仍 3 candidates / margin 240 / evaluation_failed，未通过 >=300。

 > **2026-08-22 E-08 真实十任务复验**：probe=`HTTP 200/model_listed=true` 后固定 10 任务 live 全部被 chat provider 阻断：5×429、1×567、4×503，0/10 正文；证据目录 `backend/output/quality-bench-live-e08-current-20260822/provider-live-20260822T071453Z/`。记录为 provider 阻断，不计文本质量结果，不伪造 E-08 或 T-16 对照。

 > **2026-08-22 E-08 benchmark 模型别名一致性**：直连 benchmark 现在复用生产 `LLMClient._resolve_model`，保证已知兼容网关的 bare alias 在 `/models`、chat completion 和证据模型字段中均为同一实际 ID；同时修复 standalone script 的 ROOT 路径导入顺序。离线契约 45 passed；后端全量 **904 passed, 0 failed in 102.71s**。没有调用 provider，不新增 live 成功证据。


> **2026-08-22 T-17 路径复核（目标仍 active）**：确认 `generate_chapter` 在 self-critique 开关前后均无条件执行 deterministic cleanup；`_attempt_structural_gate_repair` 在关闭 self-critique 时只跳过语义局部修复，不影响清理和质量门。已移除过时 TODO 注释，相关 cleanup/benchmark 回归 19 passed；后端全量仍 **902 passed, 0 failed in 98.91s**。


 > **2026-08-22 收尾审计**：历史 `chapter_mission` 统计为 113 个有效 dict / 38 个 null，无额外可解析嵌套来源；E-10 趋势只读回填和 blocker/warning/issue 分级审计已覆盖。清理两处重复 `@staticmethod` 装饰器并用反向源码契约锁定。当前后端全量 **902 passed, 0 failed in 103.89s**；人工/provider/T-16 改前批次/T-18 真值仍未闭环。


> **2026-08-22 E-08 重试策略最终复核（目标仍 active）**：benchmark 现尊重 `Retry-After` 但限制最多 15 秒，并与生产 429/5xx/空响应一次重试策略一致；定向质量 benchmark **16 passed**，后端完整门禁 **902 passed, 0 failed in 113.65s**。最新 v2 SSE+重试批次仍为 8/10 正文、2/10 耗尽重试后失败；v3 prompt 单任务仍被 HTTP 429 阻断，未产生可评价正文。没有人工标签、同条件改前批次或 E-06 >=300 证据，因此总目标继续 active。



> **2026-08-22 E-08 SSE/v3 续接复验（目标仍 active）**：
> - `quality_bench.py` 已对齐生产传输：优先 SSE 分片收集，兼容旧 client 的非流式回退；空正文、HTTP 429、5xx 最多重试 1 次，耗尽后仍写入真实 failure。逐任务记录 `response_transport`、`attempts`，请求指纹包含 `response_transport` 与 retry policy。
> - v2 SSE+重试完整批次证据：`backend/output/quality-bench-live-e08-sse-retry-v2-20260822/provider-live-20260822T055038Z/`。结果 **8/10 有正文、2/10 两次尝试后失败**（空正文、HTTP 429）；8 条平均字数 `2972.88`，平均分 `-46.38`；最低字数达成率 `6/8=75%`，章末压力通过率 `0/8`，事件密度通过率 `6/7=85.71%`，状态变化区间通过率 `5/7=71.43%`，7/8 有质量问题。该批只证明 SSE/重试工程改善，不关闭 E-08/T-16。
> - v3 prompt 已明确最后 10% 必须留下未解决压力、兑现 `turn/end_hook`、禁止总结收束，测试 `15 passed`；但 v3 单任务 `smoke-opening` 在两次尝试后均 HTTP 429，未产生正文，不能声称 prompt 质量收益。
> - 前缀模型 probe：HTTP 200、`model_listed=true`、可见模型 28；裸默认模型仍 `model_listed=false`。后端最新全量 **900 passed, 0 failed**。
> - 仍未闭环：19 条人工标签为空、T-16 无同条件改前生成批次、E-06 选优差 240<300、T-18 无豁免质量真值、E-08 稳定性与质量放行未达标。


 > **2026-08-22 历史趋势 E-10 体检回填**：质量趋势现从已保存 `chapter_mission` 只读重算 `mission_quality_codes`，覆盖长目标单场景、短/占位转折、继承缺失、对话策略缺失和焦点占位等 warning；无任务书不补空结果。路由 11 passed、审计专项 7 passed；后端全量 **900 passed, 0 failed in 82.03s**。

 > **2026-08-22 质量趋势审计 blocker 分级修复**：审计脚本不再把所有 `quality_issue_codes` 冒充 blocker，现分开统计 gate blockers、warnings、quality issues、exemptions；主库只读审计结果已生成 `backend/output/quality-trend-audit-current-20260822.json`。专项 7 passed；后端全量 **897 passed, 0 failed in 95.69s**。

 > **2026-08-22 历史趋势 null 兼容修复**：质量趋势回填现同时处理缺键和显式 `None`，避免旧快照 null 阻断 E-02/E-03/E-04/E-05 只读重算；回归确认原 metadata 不变。路由 9 passed；后端全量 **894 passed, 0 failed in 96.45s**。

 > **2026-08-22 历史趋势只读观测回填**：主库 151 个质量快照不含 E-02/E-03/E-05 顶层/嵌套字段，趋势接口现只读按需从已存正文计算缺失观测，优先原字段且不落库、不返回正文。路由测试确认历史 metadata 不变；后端全量 **892 passed, 0 failed in 81.24s**。外部 provider/人工验收不受影响。

 > **2026-08-22 E-10 任务书质量规则补齐**：`_evaluate_mission_quality` 现按 E-10 条件检查长目标单场景、短/兜底转折与全占位焦点人物，结果仍为 warning-only；新增正向、短篇边界和反向契约测试。定向 210 passed；后端全量 **890 passed, 0 failed in 79.74s**。未修改 provider、人工或质量 blocker。


> **2026-08-22 审阅包可交付性复验（目标仍 active）**：现有 `backend/output/quality-annotation-bundle-20260821/README.md` 已补双审阅复制、独立验证和人工裁决命令；导出脚本生成的 README 同步包含这些步骤。`--validate-labels` CLI 不再要求无关 database/--output-dir。真实 labels 仍是 19 行、0 已标注；后端全量门禁 **886 passed, 0 failed in 55.75s**。


 > **2026-08-22 E-02/E-03/E-05 观测字段断链修复**：修复评分器已计算但 compact snapshot/趋势消费丢失的顶层字段，补齐反转、说话人和场景切换指标；新增后端快照、趋势路由、前端显示与反向契约测试。定向 23 passed；后端全量 **886 passed, 0 failed in 55.67s**；前端三项门禁通过。未改变质量 blocker、provider 或人工验收口径。


> **2026-08-22 人工标注流程补强（目标仍 active）**：`export_quality_annotation_bundle.py --validate-labels <labels.csv>` 现可脱离 database/--output-dir 直接运行；定向标注/合并测试 **5 passed**。当前 `quality-annotation-bundle-20260821/labels.csv` 仍为 19 行、`labeled_row_count=0`，验证工具只证明格式合法，不构成人工质量真值。



> **2026-08-22 长预算与可比性护栏复验（目标仍 active）**：
> - **E-08 请求缺陷修复**：此前 `quality_bench.py` 对 6000 字任务硬截 `max_tokens=3000`，与最低 5400 字契约先天冲突；现改为 `min(max(target_word_count*2,1200),12000)`，prompt 明示目标/最低字数。固定 10 任务长预算批次证据：`backend/output/quality-bench-live-e08-prefix-10-20260822-longbudget/provider-live-20260822T045106Z/`。
> - **长预算真实结果**：6/10 有正文、4/10 失败（3 个 HTTP 524、1 个空正文）；成功 6 条平均 2744.17 字、平均分 193.33。6000 字任务单次达到 4883 字，较旧 3000-token 截断改善但仍未达到 5400 最低值；结构问题仍有推进弱、章末压力、静态风险等。E-08 继续失败，且该批没有新 v2 请求指纹，不能用于 T-16 前后比较。
> - **T-16 防伪护栏**：live 逐任务记录现写入 `request_contract`（prompt 契约版本、system prompt SHA-256、temperature、max_tokens、预算策略）；`comparison_fingerprint` 升为 schema v2 并包含生成请求契约哈希。缺此字段的旧批次一律 `missing_comparison_fingerprint`，禁止比较。`rescore-only` 现保留已有 provider/probe/live failure 元数据，防止离线重算擦除真实失败证据。
> - **回归可靠性**：T-07 sabotage 改按当前真实分差动态抹平，T-16 仍固定验证五项可控数值分量（1450），不再错误要求它等于含其他结构正向项的总 gap。后端全量 **883 passed, 0 failed**；benchmark/E-06/T-07/T-16 专项 **22 passed**。
> - **持续缺口**：人工双审阅标签、同任务同参数改前生成批次、T-18 exemption 真值、E-08 稳定 10/10 与质量放行仍未满足；总目标保持 `active`。


> **2026-08-22 E-04 配比观测闭环**：修复 `PipelineOrchestrator._evaluate_content_balance` 未输出动作/描写比例、而趋势 API/前端已读取这些字段的断链。现以互斥段落分类计算 `dialogue_ratio` / `action_ratio` / `description_ratio`，展开到 compact snapshot 并在趋势面板显示三项；仅极端失衡给弱排序判罚，不新增 blocker。定向后端 211 passed；完整后端 **883 passed, 0 failed in 122.24s**；前端 type-check、48 files / 245 tests、build-only 通过。人工/provider/前后生成对照缺口未改写。

> **2026-08-22 T-20～T-26 续接审计**：T-20～T-25 的当前本地生产接线与专项回归已复核（24 passed）。T-26 只读审计产物为 `backend/output/dialogue-state-marker-audit-current-20260822.json`：151 源记录 / 149 合格 / 112 声明对话预期 / 0 未声明对话预期，故当前数据不能校准未声明分支，也不足以证明具体揭示、选择、外部压力三类语义召回；未修改生产 marker 词表或阈值。


> **2026-08-22 继续复验（目标仍 active，未宣称整份完成）**：
> - **生产修复**：`backend/app/utils/llm_tool.py` 对 `api.xzxyuan.ccwu.cc` 的裸模型别名 `deepseek-v4-flash-free` 做请求层规范化为 `deepseek/deepseek-v4-flash-free`；`LLMService.is_deepseek_free_model` 同时识别带命名空间模型。其他网关和显式模型保持原样。另补 T-09 焦点人物动作接线与反向回归。
> - **E-08 合规 live**：固定 10 任务、命名空间模型、provider probe=`HTTP 200/model_listed=true`；证据目录 `backend/output/quality-bench-live-e08-prefix-10-20260822-post-helper/provider-live-20260822T043024Z/`。结果 **8/10 有正文、2/10 provider 空正文失败**，批次状态 `failed`；8 条平均字数 `1968`、平均重评分 `-364.62`，`6/8` 触发 `chapter_progression_weak`、`5/8` 触发 `static_description_risk`。该批证明通道部分可用但质量未达标，不关闭 E-08，也不能用于 T-16 前后收益。
> - **E-06 严格三候选**：新证据 `backend/output/e06-three-candidate-asgi-20260822-postfix.json`；`candidate_count=3`、差异维度 `3`，但运行状态 `evaluation_failed`，选中候选相对最佳落选候选差值 **240**，低于硬阈值 `>=300`，故 E-06 仍未完成。`real_asgi_three_candidate_smoke.py` 已改为唯一输出、拒绝越界/覆盖旧证据。
> - **门禁**：后端最新全量 `876 passed, 0 failed`；前端 `npm run type-check`、`npm run test:run`（48 files / 245 tests）、单独执行 `npm run build-only` 均通过。并行执行 build/type-check 的一次 `components.d.ts` 写冲突不计为失败，单独重跑已通过。
> - **仍未闭环**：19 条人工标注仍为空；T-16 无同任务同模型改前生成批次；T-18 无真实 exemption 质量样本；E-08 质量与稳定性不达标；E-06 未达 `>=300`。总目标继续保持 `active`。


> **2026-08-22 T-06～T-19 续接审计**：新增两项本地闭环修复：T-09 将任务书中已解析的焦点人物名传入静态行动识别，避免任意项目人名执行明确动作时被误判静态；T-17 修复终态 deterministic-cleanup 摘要引用未定义 `initial_cleanup` 的成功路径 `NameError`，初次/终态 diff 均保留。T-16 仍缺同任务改前生成批次，T-18 仍缺真实豁免质量真值，未以自动化替代外部验收。当前后端完整门禁：**876 passed, 0 failed in 73.93s**。

> **2026-08-22 恢复后门禁更新**：`pipeline_orchestrator.py` 误写恢复后按定向回归逐项补回运行重绑、T-24、连续性、确定性清理、长篇 checkpoint、T-16、E-11、T-22；后端完整门禁为 **869 passed, 0 failed in 47.34s**，前端 type-check、48 files / 245 tests、build-only 均通过。总目标仍 active：人工双审阅标签、同任务改前生成批次、E-06 ≥300、E-08 10 任务 provider 成功、T-18 与 E-11 的真实质量收益均未获证，不得据自动化绿灯宣称完成。

> **2026-08-22 provider 阻断复验**：E-06 严格三候选隔离 ASGI=`failed/0 candidates`；低成本 5 章多章 ASGI=0/5 正文，均为 `No available channel for model deepseek-v4-flash-free`。记录为外部 provider 阻断，不计为质量失败、质量通过或 E-08 成功率。

> **2026-08-22 provider probe**：`quality_bench.py --provider-probe` 实测 HTTP 200、24 个模型可见，但目标模型 `deepseek-v4-flash-free` 未列出（`model_listed=false`）；E-08 live 仍不可合法启动。

> **2026-08-22 E-08 前缀模型 partial batch**：使用 provider 已列出的 `deepseek/deepseek-v4-flash-free` 执行固定 10 任务，7/10 有正文、3/10 provider 空正文失败；7 条成功记录平均 2114 字、平均分 101，5/7 有 `chapter_progression_weak`，长档仍低于任务字数且伴随章末/静态风险。此为部分可用和质量未达标证据，不是 E-08 通过或 T-16 前后对照。

> **证据目录**：`backend/output/quality-bench-live-e08-prefix-10-20260822/provider-live-20260822T034312Z/`（含 `rescore-summary.json`、`live-status.json`、7 个脱敏正文与逐任务记录）。

> 来源：TASK_HANDOFF_NOVEL_QUALITY.md。建立日期：2026-08-21。
> 状态定义：**已证实**=当前源码与对应测试/运行证据已核对；**历史声称**=文档称已完成但尚未在本次逐项复核；**部分完成**=代码存在但缺少文档要求的真实语料/端到端/反向证据；**待实现**=未发现实现。
> 此台账优先于交接文档中各处相互矛盾的历史 passed 数；不得凭“全量绿”推断每一项都完成。

## T 系列

| 任务 | 当前审计状态 | 当前证据 / 缺口 |
|---|---|---|
| T-01 | 已证实 | `PipelineOrchestrator` 无 `_score_fallback_candidate`，`app/` 内无该定义/调用；删除护栏与孤儿模块不可导入测试共 2 passed。历史恢复材料中的残留不属于生产路径。 |
| T-02 | 已证实（代码/定向/反向） | 中性前缀“一切都”已不在收束词表；真钩子与完整平淡收束均有回归，sabotage 通过。 |
| T-03 | 已证实（代码/定向/反向） | 语义命中是章末压力必要条件，标点/弱词不能单独放行；正向与标点灌水回归及 sabotage 通过。 |
| T-04 | 已证实（代码/定向/反向） | 引号不再无条件计推进，弱连词/“活”移出主词表；寒暄拒绝与戏剧正向回归及 sabotage 通过。 |
| T-05 | 已证实（代码/真实语料护栏/反向） | 窗口按句子推进比例与至少 2 个命中判定；平淡窗口区分、长句单命中、真实比例护栏及 sabotage 通过。 |
| T-06 | 部分完成（真实 524 重试已观测，系统性降级/误杀仍缺） | 脱敏 151 条统计与定向校准/反向测试已通过；新 10 任务 batch 10/10 成功，`benchmark-scifi-investigation-6000` 首次 HTTP 524 后重试成功，`retry_events` 已真实落盘。批次可比性审计仍为 candidate_pair_count=0；仍缺系统性降级样本与跨批误杀率。 |
| T-07 | 部分完成（本轮复核） | 5 类坏样本分差与快照回归已证实；新增可复跑 sabotage 4 项，6 passed。历史 8 类统一池仍未完全重组。 |
| T-08 | 部分完成（跨层诊断已证实） | 四条静态风险分支、阈值哨兵、快照、趋势细粒度字段及历史嵌套回填已核对；仍缺真实新生成三档误杀率。 |
| T-09 | 部分完成（本地逻辑已证实） | 主体/非主体动作约束与防回归存在；新增脱敏 151 版本统计（1082 段、静态率 p05/p50/p95=0/0.25/1.0、ambient-only=53）与专项 sabotage。无人工真值，精确率/召回率仍不可宣称。 |
| T-10 | 部分完成（后端已证实） | 精确重复检测、−420 判罚、blocker、快照与趋势 API/UI字段已核对；新增运行时 sabotage。仍缺真实生成触发率复跑。 |
| T-11 | 已证实（本地前后端闭环） | 四来源采集、占位符过滤、−240/warning 与趋势人物名单/命中数/缺席名单均已核对；仍缺别名误判率校准。 |
| T-12 | 部分完成（真实候选择优已补，收益泛化仍缺） | 字数四层接线、反证、趋势目标/边界/判罚展示已核对；E-06 真实 ASGI 已提供 3 候选、8 维差异、margin=319≥300。仍缺跨任务误杀率/前后收益泛化证据。 |
| T-13 | 部分完成（当前本地逻辑已证实） | 三态消费、专项反证和 196 passed 定向集已核对；149 条合格脱敏样本的状态标记非零率为 0.9933，但任务书未声明对话样本为 0，仍缺人工语义真值，不能将覆盖率当召回率。 |
| T-14 | 已证实（本地前后端闭环） | 短样本 None/skip、评分、前端摘要与趋势 `event_density_evaluated/skip_reason` 均已核对；仍缺真实端到端数据。 |
| T-15 | 部分完成（脱敏跨题材审计已证实） | E-08 七个正式题材组全部覆盖但各仅 1 条；E-09 无题材标签/正文，无法证明跨题材召回率；趋势细粒度章末字段已补齐。 |
| T-16 | 部分完成（候选/可比口径已分离） | 全量 37 summaries、14 完整指纹、9 同条件组；1 个时间顺序候选、`comparable_pair_count=0`、`non_comparable_candidate_pair_count=1`，差异为 scorer/comparison contract。仍缺同评分器/同契约改前生成批次。 |
| T-17 | 部分完成（边界反例与本地修复已证实） | 已实测最终清理前后 score 937→919、字数 931→928；现最终清理后重算 structural gate 并写回 runtime，T-17 定向 213 passed。仍缺真实 provider 异步生成链端到端证据。 |
| T-18 | 部分完成（观测已接入，真实样本未触发） | `critique_exemption_applied` 已写入质量门快照/summary，多章脚本按章投影；真实 5 章复跑 5/5 字段为空数组，审计 valid=true。当前仍无真实 exemption 真值，不得凭 0 触发调整阈值。 |
| T-19 | 已证实 | 孤儿模块删除测试通过；生产目录引用复查为 0（仅保留测试护栏与历史注释/恢复材料）。 |
| T-20 | 已证实 | 当前三处 EXTRACTABLE 注释均无行号且处于语句边界；`test_extractable_comments_have_no_line_numbers` 通过，`STORY_PROGRESSION_MARKERS` 当前为 55 项。 |
| T-21 | 已证实（流程约定） | `CLAUDE.md` 已要求提交信息引用当前完整门禁的 `N passed, M failed` 原始结果，并指定实际后端命令与 pytest.ini 的 no:anyio 配置；无代码测试适用。 |
| T-22 | 部分完成（代码/定向/反向/patch 消费已证实） | 严格子集改善、禁止问题置换、2 轮上限与诊断均有回归；E-11 patch 已受 code/去重/条数/长度约束并转换为 revision issues，实际传入 revise_chapter(issues=...)，捕获/篡改测试通过。仍缺真实生成放行/误杀率。 |
| T-23 | 已证实 | pytest 配置固定禁用 anyio，标记迁移与反向护栏已核对；最新清缓存后端全量为 935 passed, 0 failed。 |
| T-24 | 部分完成（真实长篇 ASGI 已闭环，scene-split 无适用执行器） | `_summarize_generation_error`、writer prompt budget、segment extract、checkpoint persistence 与长篇 heartbeat/content_delta 已接入真实路径；第三轮真实 smoke `LONGFORM_SMOKE_PASS`：succeeded、5/5 segments、5 deltas、39,406 字、73 events。scene split timeout 未接入，因为生产只有段落分段、无 scene-split 执行器。仍需按任务书完成其余证据项。 |
| T-25 | 部分完成（真实长篇合同样本已补，语义泛化仍缺） | mission timeout/max tokens、短 retry、原因码与 progression blocker 已核对；7000 字 long tier 禁用整章 stable retry，含反向证据。脱敏真实长篇审计显示 5/5 checkpoint、目标/最低字数、事件/长章/状态变化和质量门均通过。仍缺多任务真实语料/产品语义交叉审计。 |
| T-26 | 部分完成（真实脱敏统计已落盘） | 新增分类审计脚本与测试；151 条源记录/149 条合格样本，state_change_markers p05/p50/p95=3.0/12.0/27.6，带对白样本非零率=0.9933；揭示/选择/外部压力命中率=0.6644/0.6846/0.5436。expected_dialogue=false 样本为 0，候选扩词未改变零标记样本，暂不改生产词表；仍缺人工真值。 |

## E 系列

| 任务 | 当前审计状态 | 下一步 |
|---|---|---|
| E-01 | 部分完成（E-01.1 已证实） | `writing_v2` seed 已落盘，字节/SHA-256 与现有 prompt 一致；init_db 遵守缺失插入、已存在不覆盖，4 项测试及反向验证通过。E-01.2 提示词正文优化仍待 E-08 live 前后比较。 |
| E-02 | 部分完成（历史+真实 batch 分布已证实） | 现有 151 版本校准与最新 10 任务真实 batch 均有脱敏反转分布；最新 batch late reversal rate=1.0。仍缺人工质量标签与真实前后对比。 |
| E-03 | 部分完成（历史+真实 batch 分布已证实） | 趋势展示与脱敏校准已覆盖 speaker_count/dominant ratio；最新 10 任务 batch 也已落盘。仍缺人工声音区分标签与真实前后对比。 |
| E-04 | 部分完成（历史+真实 batch 分布已证实） | 三比例、极端弱判罚和趋势展示已存在；最新 10 任务 batch 脱敏分布已落盘。仍缺人工质量标签和误杀率评估。 |
| E-05 | 部分完成（历史+真实 batch 分布已证实） | 硬切/总结式切换观测与趋势展示已存在；最新真实 batch 场景切换 warning rate=0.2。仍缺人工场景承接真值与任务书可靠关联。 |
| E-06 | 已证实（当前真实 ASGI） | `e06-three-candidate-asgi-20260822-gpt56-v4.json`：3 候选、8 维差异、选中 margin=319≥300，successful/waiting_for_confirm；不替代 T-16 前后收益。 |
| E-07 | 部分完成（历史回填已证实） | 趋势 API/审计对历史 continuity 字段只读回填；当前主库 50 条观测、2 条缺失、1 条偏晚；仍缺真实生成放行率。 |
| E-08 | 已证实（核心批次；仍保留告警） | v4 中文固定 10 任务、gpt-5.6-sol、SSE：10/10 正文且核心最低字数/章末压力/事件密度/长章密度/状态变化均10/10；唯一 `continuity_inherit_missing` warning。仍缺人工评价与改前对照，不能据此关闭总目标。 |
| E-09 | 部分完成（20 章真实放行/拒绝链路已补） | selected-version 趋势与脱敏审计闭环；最新 gpt-5.6-sol 20 章复验 16/20 放行、4 拒绝、放行率 0.8，`ending_pressure_missing=4`、`reversal_missing=1`，内部一致性 valid=true。仍缺题材标签/人工正文真值，不能支持跨题材召回或 T-18 阈值决策。 |
| E-10 | 部分完成（本地与历史审计闭环） | 五项任务书体检、首章继承豁免和趋势 mission_quality_counts 已接线；最新 selected-version 审计 mission_quality_rows=56、first_chapter_mission_inherit_violations=0。仍缺真实任务书分布与质量收益证据，保持 warning-only。
| E-11 | 部分完成（多章拒绝 patch 观测已补） | warning patch 消费、趋势 patch 脱敏、历史字段回填和多章脚本 `patch_suggestions/quality_issue_codes` 投影均有正反向证据；真实 LLM 放行率、误杀率、patch 修复收益仍缺。 |

## 2026-08-21 续接实证更新

- E-08 live runner 已真实探测 provider：models 端点 HTTP 200、目标模型可见；completion 三任务均 HTTP 429，产出 0 条，状态文件保存在 backend/output/quality-bench-live-e08-verify/provider-live-20260821T170520Z/live-status.json。该结果是阻断证据，不是 live 通过。
- E-11 趋势面板现展示 warning_counts、逐章 patch_suggestions，以及 E-03 speaker 分布、E-05 场景切换、E-10 mission_quality_codes。
- T-06/T-07 新增 6 项可复跑反向测试，均通过；T-16 新增 3 项评分构成/篡改反证，T-17 新增 3 项清理接线契约/篡改反证。
- T-01～T-05 当前源码与 19 项定向回归已复核，均未发现需改生产逻辑；真实生成统计和部分专项反向证据仍是完整验收缺口。
- T-08～T-15 当前定向复核：后端质量门 188 passed；本轮趋势 API/UI 已补 T-10/T-11/T-12/T-14 诊断字段，前端定向 4 tests/type-check 通过。T-26 新增真实脱敏 JSON 校准，但人工真值与真实 LLM 校准仍未完成。
- 本台账仍不把 fixture smoke、定向测试或历史 passed 数当作完整任务验收。


- T-18（本轮）：脱敏库 151 条版本/35 条 quality_gate 记录中 exemptions=0；该结果证明历史数据不足，不构成收紧阈值依据。
- E-02～E-05（本轮）：新增无正文输出的 151 版本统一校准报告，覆盖反转、说话人、内容配比和场景切换分布；不把分布误称为质量真值。
- T-11～T-14（本轮）：质量趋势后端/跨层定向 `39 passed`；前端 type-check 通过，趋势 API/UI `4 passed`。
- T-08～T-10（本轮）：新增静态/动作脱敏校准脚本（151 版本、无正文输出）及 3 项 sabotage；相关定向 `9 passed`。
- T-02～T-05（本轮）：相关正向/防误杀定向 `10 passed`；新增四项可复跑 sabotage，和选定正向回归合计 `8 passed`。
- T-01/T-22（本轮）：死 fallback scorer 护栏与孤儿模块不可导入共 `2 passed`；T-22 质量门回归 `188 passed`，新增严格子集/新问题类型 sabotage `2 passed`。
- T-17（本轮）：`test_deterministic_cleanup.py` 新增两处生产接线顺序断言与删除最终清理的篡改反证；与质量门回归共 `192 passed`（2026-08-21）。
- T-20/T-21（本轮）：EXTRACTABLE 护栏单测及确定性清理测试共 `5 passed`；当前标记词表长度为 55；CLAUDE 提交结果约定已更新为完整 `N passed, M failed`。

## 2026-08-21 本轮最终门禁更新
- E-08 live 重试：2026-08-21T18:01:29Z 新 run 的 `/models` 仍 HTTP 200、目标模型可见，但 3 次 `/chat/completions` 仍全部 HTTP 429，`record_count=0`；状态文件：`backend/output/quality-bench-live-e08-retry/provider-live-20260821T180129Z/live-status.json`。
- E-01.1/T-24：`writing_v2` seed SHA-256 为 `D0DC175C322738F394BED0142C5B2BB9B6B829F7C606754A6B0A94FA3154FFDA`；E-01.1 4 passed，T-24 采用/反向专项 211 passed。

- 后端：`python -m pytest app -q -rf` => **850 passed, 0 failed in 47.40s**。
- 前端：`npm run test:run` => **48 files / 245 tests passed**；`npm run type-check` 通过；`npm run build-only` 串行重跑通过。初次与 test 并发时，组件声明文件出现 Windows `UNKNOWN open` 竞争；串行 build 正常，因此不视为产品代码失败。
- E-11/T-22：质量门 patch 已受 code/去重/条数/长度约束，并转换为 revision issues 实际传入 `revise_chapter(issues=...)`；捕获式正向与篡改式反向测试包含在 200 passed 定向集内。
- T-10/T-11/T-12/T-14：质量趋势 API 与面板已新增重复、焦点命中/缺席、字数边界/判罚、密度未评估原因；后端 API 3 passed、前端相关 4 tests/type-check 通过。

## 当前可靠基线

- 后端：旧基线（新增 T-09/E-02～E-05 校准与 E-11 接线前）：`823 passed`；最新完整门禁见上方最终更新。
- 前端：2026-08-21 type-check、test:run（**48 files / 245 tests**）、build-only 通过。
- T-06 脱敏校准：storage/xuanqiong_wenshu.db 读取 151 条版本、149 条合格样本；事件密度通过率 0.9262，event_density_per_1000 p05/p50/p95=1.7542/4.1351/9.3329，progression_unit_rate=0.0255/0.0734/0.2017，plain_run_ratio=0.0974/0.2254/0.4438。
- T-18：历史快照没有结构化 exemptions，当前新代码已记录 ending_pressure_missing/event_density_weak 豁免；尚无真实豁免样本，暂不调阈值。
- 此基线证明当前测试集合通过，不证明上表的“历史声称”任务已逐项完成。

## 2026-08-21 多章真实 ASGI 追加记录（运行中）

- 先前 20 章尝试在第 2 章真实触发质量门：`evaluation_failed`，唯一 blocker 为 `ending_pressure_missing`，另有 `continuity_inherit_missing` warning。该样本已保留于隔离库，**不是系统异常，也不得靠放宽阈值消除**。
- 多章 smoke 已改为保留每次尝试的 runtime、blocker/warning、字数与放行率；章节被拒绝后继续采样，避免只挑成功样本。该脚本只改审计输出，不改生产质量门。
- 同一隔离项目 5 章真实 ASGI 已完成：尝试/放行/拒绝 = `5/5/0`，API 层候选字数均值 1431.0（1534/1349/1252/1642/1378）；趋势落库字数均值 1313.0。趋势中事件密度 `5/5=true`、对白改变局势 `5/5=true`、章末压力 `4/5=true`（第 3 章为 false，但没有被质量门拦截）；blocker/warning/exemption 聚合均为空。证据：`backend/output/e09-multichapter-trend-5chapters-20260821.json`。
- 20 章原始样本采集已启动；在该运行结束并汇总成功/拒绝分布前，E-02～E-05、E-09、E-11 仍维持“部分完成”，绝不宣称整体完成。

## 2026-08-21 20 章真实 ASGI 终态记录

- 使用同一隔离项目、`gpt-5.6-sol`、enhanced、target/min=1200/900 完成原始 20 次章节尝试：**19 放行、1 拒绝，放行率 0.95**。第 19 章被 `ending_pressure_missing` 拦截，运行态 warnings 为 `continuity_inherit_missing`、`reversal_missing`；拒绝样本没有被排除。原始脱敏证据：`backend/output/e09-multichapter-trend-20chapters-20260821.json`。
- 放行的 19 章：事件密度 `19/19=true`；对白改变局势 `19/19=true`；章末压力 `17/19=true`；晚段反转 `13/19=true`。这说明“成功放行”与单项观测通过不是同义关系，章末压力 false 的 2 章未触发 blocker。
- E-02：reversal_signal_count p05/p50/p95=`0.9/2/3.1`；E-03：speaker_count=`1/5/9.1`、dominant_speaker_ratio=`0.1411/0.3333/1.0`；E-04：dialogue/action/description p50=`0.4032/0.1333/0.4359`；E-05：hard/summary scene cut 均为 0、scene_transition_warning=`0/19`。这些是同项目短章的真实分布，**没有人工标签，不得改称质量真值或误杀率**。
- 实测发现并修复 E-09 可观测性缺口：`quality-trend` 以前只读 selected-version metadata，`evaluation_failed` 章节会丢失 runtime quality_gate 的 blocker/warning。现仅在 version gate 缺失时回退到 `real_summary.generation_runtime.quality_gate`；真实隔离项目 API 已返回上述 1 blocker/2 warnings。
- 同次实测发现 patch suggestion 会携带“待承接”中的上章正文；现将其替换为“上一章遗留”，真实 API 断言正文片段不再出现。质量趋势仍保留可执行的 code/提示语，不回传正文。定向回归：quality-trend + smoke audit `8 passed`。
- E-02～E-05/E-09/E-11 仍为**部分完成**：已具备 20 章真实分布和拒绝原因，但缺跨题材、前后对照与人工质量/误杀标签；T-18 仍无真实 exemption 样本，禁止凭统计调整阈值。

## 2026-08-21 收束门禁与当前目标状态

- 本轮生产改动后后端全量：`python -m pytest app -q -rf` => **855 passed, 0 failed**。
- 本轮前端门禁串行执行：`npm run type-check`、`npm run test:run`、`npm run build-only` 均退出码 0；构建成功。
- 新增/修改的趋势 API 回归（运行态拒绝回退、坏 JSON 安全忽略、patch 正文脱敏）与多章 smoke 审计回归均通过；没有跳过测试或降低质量阈值。
- 当前总目标仍为 **active**，不能标记 complete。已完成的是代码重构、真实 20 章分布采集、拒绝原因可观测性和门禁验证；未完成的是人工质量真值、跨题材泛化、T-16/E-06 真实前后对照、E-11 patch 修复收益、T-18 真实豁免质量评估。

## 2026-08-21 人工真值与候选选择补证

- 新增 `backend/scripts/export_quality_annotation_bundle.py`：默认导出 hash、指标、检测结果和空白标签表，不输出正文；只有显式 `--include-content --content-output` 才能生成本地私有正文文件。真实 20 章隔离库已生成 19 个待审样本（blocker=1、ending_pressure_false=2、late_reversal_false=5、clean_pass=11），输出目录受 `.gitignore` 保护。该包**尚无人工标签**，不能把其称为人工真值。
- T-16/E-06 历史审计：`backend/output/evaluator-rescore-comparison-20260821.json` 的 `comparable_rows=0`，旧产物没有同任务、同模型、同候选数的改前快照；不能形成合法前后比较。
- E-06 当前真实 ASGI（固定 1200/900、enhanced、显式 versions=3）：3 个候选均落库，指标差异维度=8（action/description/dialogue ratio、speaker、reversal、word_count、score）；但 pipeline AI review 选中 v3=1004，最佳落选 v2=1111，选优差 `-107`，未满足任务书的 `>=300`。`confirmed_version_id=v1` 是用户确认指针，不能与 pipeline_best 混为一谈。证据：`backend/output/e06-three-candidate-asgi-20260821.json`。
- 因此 E-06、T-16、人工真值、T-18 仍保持未完成/部分完成；禁止通过把 selected 指针、AI review 或当前评分器自评改写为“人工质量提升”。新增脚本定向回归共 5 passed（E-06 3、标注包 2）。

## 2026-08-21 E-08 扩展 benchmark 与 provider 阻断

- 固定 benchmark 已从 3 个 smoke fixture 扩展为 10 个任务：保留 `smoke-*` 三项供低成本 smoke，新增动作/桥接/收束/对话关系/惊悚过渡/科幻调查等任务，覆盖 1200/1500/3000/6000 字档。`quality_bench --smoke` 仍严格只跑 3 项；新增回归确认 10 个任务存在、四档字数覆盖，quality-bench 定向 `7 passed`。
- 2026-08-21 真实 10 任务 direct batch：provider `/models` HTTP 200 但目标模型未列出；10 次 completion 全部 HTTP 503 `No available channel for model deepseek/deepseek-v4-flash-free`，`record_count=0`，未生成正文。证据：`backend/output/quality-bench-live-e08-10-20260821/provider-live-20260821T212731Z/`。这是 provider 阻断证据，不能宣称 E-08 批量通过。
- 3 项 direct benchmark 的既有 3/3 成功证据仍保留；完整 ASGI 20 章和 E-06 三候选证据也不受该阻断影响。

## 2026-08-21 本轮继续门禁

- 新增固定 benchmark 任务、E-06 三候选审计器、人工标注包和 provider 阻断记录后，后端全量 `python -m pytest app -q -rf` => **861 passed, 0 failed**。
- 前端本轮没有源码变更；最近一次完整 `type-check` / `test:run` / `build-only` 均退出码 0，仍有效。
- 当前总目标保持 **active**：自动化代码与证据持续推进，但人工标签、同任务改前批次、provider 可用的 10 任务 live 批次和 E-06 ≥300 选优差仍未满足。

## 2026-08-21 E-08 partial batch 与总分观测修复

- 使用 `gpt-5.6-sol` 的真实固定 10 任务 direct batch：**3 成功、7 provider 阻断**。成功样本为 1500 字对话关系任务与两个 1200 字 smoke；3 条均观测到 `chapter_progression_weak`。失败的 3000/6000 字任务多为 HTTP 524，另有 1 条 HTTP 503。证据：`backend/output/quality-bench-live-e08-gpt56-10-20260821/provider-live-20260821T213530Z/rescore-summary.json`。因此这是 partial provider/评分证据，**不是**10 章质量放行率或 T-16 前后对照。
- 实测发现 `story_progression_guard.score` 没有进入持久化 `quality_metric_snapshot`，使 trend/candidate 审计读到 score=null。现快照持久化同一总分；回归断言快照分数必须等于 guard 总分。既有历史版本不回填，未来生成与趋势将带 score。
- 生产改动后后端全量：`python -m pytest app -q -rf` => **862 passed, 0 failed**；score snapshot + trend + E-06 定向 `14 passed`。
- 总目标继续 active：E-06 真实候选差值仍未达到 300，T-16 没有同任务改前基线，人工标注包为 0 标签，T-18 无真实 exemptions；不得借 partial batch 或当前评分器自评宣称完成。

## 2026-08-21 显式多候选契约修复

- 真实 3000 字 E-06 运行首次暴露：显式 `versions=3` 在 Provider 只返回 1 个候选时，生产 stable retry 会静默降级成单候选 `successful`，使 E-06 失去验收意义。
- 已修复：仅高级入口显式请求 `versions>1` 时启用 `require_requested_candidate_count`；候选不足返回 `REQUESTED_CANDIDATE_COUNT_UNMET`/失败可重试，不影响默认自动候选的 provider 抖动 salvage。配置回归与源码契约回归通过；真实 3000 字复验最终为 `failed`、0 候选，提示明确拒绝降级。
- 该修复不改变 AI 选优阈值，也不伪造 E-06 通过；短章真实三候选仍有 8 维差异但评分差为 -49，E-06 继续未通过。

## 2026-08-21 E-08/T-16 可比性指纹护栏

- `quality_bench` 汇总现写入脱敏 `comparison_fingerprint`：固定任务/字数/任务书 contract SHA-256、当前 `pipeline_orchestrator.py` 评分器 SHA-256 与组合 contract hash。
- `--compare` 只在任务集与评分器指纹一致时输出 delta；旧汇总缺少指纹或任一契约不一致时返回 `comparable=false` 和明确原因。真实用旧 gpt-5.6-sol 3 任务汇总比较，结果为 `missing_comparison_fingerprint`，不再生成伪前后差值。
- quality-bench 定向 `8 passed`；该护栏为未来同任务基线提供可验证前提，但不能补造 T-16 的改前批次。

## 2026-08-21 最新门禁与 active 缺口

- 候选级 AI/启发式审计字段、显式多候选严格契约、质量总分快照和 benchmark 可比性指纹全部接入后，后端全量 `python -m pytest app -q -rf` => **864 passed, 0 failed**。
- 当前仍不能完成总目标：人工标注包 19 行均未填写；同任务改前 benchmark 缺失；E-06 最近短章真实三候选选优差 -49，3000 字档因显式候选不足按新契约失败；E-08 10 任务 direct 仅 3/10 成功且 7 次 provider 阻断。

## 2026-08-21 人工标注双审阅闭环

- 新增 `backend/scripts/merge_quality_annotations.py`：只合并两个已填写的脱敏 labels.csv，要求样本集合相同、审阅人不同、每项为 true/false/na；分歧标为 `adjudicate`，不自动“多数通过”。
- 标注导出 + 合并定向回归 `4 passed`。当前真实标注包仍为 19 行、0 人工标签，故该工具只补齐流程，不构成真值证据。

## 2026-08-21 本轮最终自动化门禁

- 新增人工双审阅合并器后，后端全量 `python -m pytest app -q -rf` => **866 passed, 0 failed**。
- 本轮自动化闭环已覆盖：质量总分快照、候选级启发式排名、显式多候选不足拒绝、benchmark 可比性指纹、人工标注导出与双审阅合并。
- 仍未关闭的真实验收项：19 个标注样本尚无人工标签；没有同任务改前批次；E-06 最近三候选差值为 -49，3000 字档按严格契约候选不足失败；E-08 10 任务仅 3/10 direct 成功且 provider/长请求阻断。总目标保持 active。

## 2026-08-21 当前可比 benchmark 基线

- 使用当前固定 3 个 smoke 任务、`gpt-5.6-sol` 生成 direct benchmark：3/3 成功；当前重评分平均分 `763.33`、平均字数 `2433.33`，汇总已包含 comparison fingerprint。
- 对同一批独立正文执行 `--rescore-only --compare`，真实结果 `comparable=true`、平均分 delta=`0.0`、字数 delta=`0.0`，证明新指纹链路可合法比较同批正文。
- 该批是**当前基线**，不是改前基线；没有旧版本同任务同配置批次，T-16/E-01.2 仍不能宣称前后收益。

## 2026-08-21 历史评分器行为差异（非质量真值）

- 新增 `backend/scripts/audit_historical_scorer_delta.py`，只读加载 `3e640^` 旧评分器，对 `storage/xuanqiong_wenshu.db` 151 条版本与当前评分器同参数复算，覆盖 **151/151**，正文只保留 SHA-256。
- 旧评分平均 `1234.8543`、p50=`1475`；当前平均 `874.457`、p50=`1215`；平均 delta=`-360.3974`。当前新增 `continuity_inherit_missing=94` 等问题码。
- 这是评分器行为变化证据，不是生成前后、人工质量、误杀率或用户偏好证据；数据库没有旧/新同任务生成配对，禁止据此调阈值或宣称质量下降/提升。回归 `3 passed`。

## 2026-08-21 历史评分审计门禁

- 新增历史评分器行为审计与回归后，后端全量 `python -m pytest app -q -rf` => **867 passed, 0 failed**。
- 当前总目标仍 active：历史复算只补强了评分变化证据；人工双审阅标签、同任务改前生成批次、E-06 ≥300 选优差、以及稳定的跨档 provider 批次仍未满足。

## 2026-08-21 E-09 历史趋势字段兼容

- `quality-trend` 现以完整 `story_progression_guard` 回填历史 `quality_metrics` 缺失字段，且保持 compact snapshot 优先；显式返回 `scene_transition_warning`。这补齐了旧版本 score 与场景切换告警的趋势可见性，不输出正文。
- 后端历史兼容回归 `6 passed`；前端类型/趋势面板展示场景切换告警，type-check、全量前端 `48 files / 245 tests`、build 通过。后端全量为 **868 passed, 0 failed**。
- 真实 20 章隔离项目 API 复验：20/20 返回 score；被拒绝章仍含 `ending_pressure_missing` blocker、两条 warning 与已脱敏 patch，不因趋势聚合丢诊断。
> **2026-08-22 T-17 真实持久化闭环（总目标仍 active）**：真实 `gpt-5.6-sol` ASGI smoke 通过，隔离数据库 `backend/storage/real-asgi-1787439711798466400.db` 最新候选版本的 `metadata` 同时含 `deterministic_cleanup`、`quality_gates`、`quality_metrics`；质量门快照为 passed，清理 initial/final 诊断可审计。脱敏报告：`backend/output/t17-real-asgi-metadata-persistence-audit-20260822.json`。专项 `app/services/test_generation_quality_guards.py` 为 **196 passed**，并保留源码接线反向验证；后端完整门禁最新 **987 passed, 0 failed**。限制：单样本只证明真实 provider 任务结束后的版本元数据持久化，不证明跨题材泛化、人工接受率、T-16 前后收益或 T-18/E-11 真值。
> **2026-08-22 T-17 smoke 自动验收护栏补强（总目标仍 active）**：真实 smoke 现在会在成功任务结束时自动检查 `deterministic_cleanup`、`quality_gates`、`quality_metrics` 三个版本元数据快照；第二次真实 `gpt-5.6-sol` 运行全部为 true，`quality_gate_passed=true`，隔离库 `backend/storage/real-asgi-1787440094145467900.db`。新增护栏与反向测试后，定向专项 **197 passed**；完整后端门禁尚待本轮改动后复跑。该项仍只证明持久化链路，不替代人工真值、T-16 合法前后配对、T-18 豁免真值或 E-11 patch 收益。
> **2026-08-22 本轮门禁实测修正**：T-17 自动 smoke 护栏之后按规定命令执行完整后端门禁，实测 `974 passed, 0 failed in 77.52s`；这是当前可复核结果，较早记录的 987/986 为不同时间或范围的历史计数，不作为本轮门禁数字。总目标仍 active，人工标注、T-16 合法改前批次等硬缺口未被自动化绿灯替代。
> **2026-08-22 T-25 真实长篇阻断证据（总目标仍 active）**：真实长篇 smoke 产生 5 段/5 增量/34,211 字符并完整推进 checkpoint，但统一质量门最终拒绝：`critical_consistency_unresolved`，3 critical、4 major、总 7 项，加权 13；两轮自动修复均未改善且未采纳，章节 `evaluation_failed`、候选版本未选中。报告 `backend/output/t25-real-longform-failure-audit-20260822.json` 仅保存脱敏指标与冲突指纹。当前结论是“拒绝链路有效、长篇样本被真实质量问题阻断”，不是 T-25 通过，也不允许用阈值调整替代上下文/实体一致性修复。
> **2026-08-22 T-25 失败链路专项回归**：长篇生成/分段流/长篇包 E2E/一致性/质量门专项 **223 passed**；失败报告经 JSON 校验，项目哈希已按隔离库实测修正。回归只证明拒绝与诊断链路，T-25 多任务泛化仍未完成。
> **2026-08-23 E-07/E-10 真实多章复验与观测口径修复（总目标仍 active）**：隔离 ASGI 真实 5 章全部成功，`pass_rate=1.0`；证据与一致性审计分别为 `backend/output/e09-multichapter-trend-5chapters-20260823T002431Z.json`、`backend/output/e09-multichapter-evidence-audit-20260823T002431Z.json`，后者 `valid=true`。连续性观测为 1 缺失/0 偏晚；任务书健康度 5/5 有行、`mission_focus_placeholder=5`；趋势章节现同时返回 `exemptions` 与 `critique_exemption_applied` 空数组，避免 null 歧义。专项 **28 passed**。审计注意：`audit_quality_trend.py` 本批 `gate_rows=0`，因此不构成 T-18 豁免真值或人工质量结论。
> **2026-08-23 本轮全量门禁实测**：当前改动后后端 **981 passed, 0 failed in 92.69s**；前端 type-check、Vitest **48 files / 291 tests**、build-only 全部退出码 0。较早的 974/987/986 为历史范围计数，不覆盖本轮；总目标仍 active。
> **2026-08-23 T-06 第二批真实重试分布（总目标仍 active）**：第二批同契约 10 任务 Provider live batch 为 10/10 成功、0 provider failure、全部 attempts=1、全部 `retry_events=[]`；脱敏报告 `backend/output/t06-second-live-retry-distribution-audit-20260823.json`。这补充了“无重试”真实运行分布，结合首批 524→重试成功仅证明可观测性与有限恢复路径，不能宣称稳定降级覆盖、误杀率或质量前后收益。
> **2026-08-23 E-11/T-22 真实修复可观测性补强（总目标仍 active）**：修复摘要从 runtime-only 改为成功候选版本 metadata 顶层始终保存 `quality_gate_repairs`，空数组代表真实未触发而非字段丢失。真实 smoke 自动断言通过，隔离库 `backend/storage/real-asgi-1787448945833891500.db` 为 `quality_gate_repairs=[]`；脱敏报告 `backend/output/e11-t22-real-asgi-repair-observability-audit-20260823.json`。专项 **207 passed**，完整后端 **987 passed, 0 failed in 68.82s**。这只是可观测性/负控闭环，E-11/T-22 的真实修复收益仍缺。
> **2026-08-23 E-11/T-22 真实 repair 触发探针结论（总目标仍 active）**：真实多章默认拒绝样本记录 `self_critique_disabled` skipped 诊断；显式开启 self-critique 的 3 章及诱导平收 prompt 的 3 章均通过，版本 metadata 的 `quality_gate_repairs` 均为 `[]`，未触发真实 repair。报告 `backend/output/e11-t22-real-repair-probe-audit-20260823.json`。结论保守为“观测链路和边界已证实，真实 patch 收益仍缺”，不能用未触发样本冒充 E-11 完成。
> **2026-08-23 本轮后端门禁实测修正**：当前改动后后端全量 **993 passed, 0 failed in 71.41s**；旧的 987/986 等数字仅为历史轮次。E-11/T-22 仍只有 skipped/未触发真实探针，没有 `repair_attempted=true` 的 Provider 样本。
> **2026-08-23 T-16 当前冻结口径重复配对（总目标仍 active）**：严格比较现有 1 个合法配对，来自同一当前 scorer/请求契约的两次 10 任务 batch；`comparable=true`，平均分 delta `+222.7`、平均词数 delta `+296.3`。新增审计护栏要求 scorer 与 comparison contract 同时一致；专项 **5 passed**。报告 `backend/output/t16-current-repeat-pair-audit-20260823.json`。这是可重复性/审计链路证据，不是 T-16 改前改后收益，合法优化前后配对仍为 0。
> **2026-08-23 T-18/E-09 真实 exemption 趋势投影修复与复核（总目标仍 active）**：成功版本的 `quality_gates.structural_gate` 现在被趋势 API 正确读取，并投影质量门结果与 self-critique 诊断。真实 5 章复核为 5/5 成功，self-critique 均实际为 `self_critique_after_consistency`，分数 72.5～83.6，但 exemptions/critique_exemption_applied 全部为空；报告 `backend/output/t18-real-asgi-exemption-observability-audit-20260823.json`，专项 **20 passed**。观测链路已补强，T-18 真值与人工接受率仍未完成。
> **2026-08-23 本轮最终门禁实测修正**：当前工作区后端 **1002 passed, 0 failed in 77.59s**；前端三件套均通过（Vitest 48 files/291 tests）。本轮 T-16 已有 1 个当前冻结口径重复配对但非优化前后收益；T-18 真实 5 章仍 0 exemption；E-11 真实 repair_attempted=true 仍缺。总目标保持 active。
> **2026-08-23 T-18 exemption 触发证据修正（总目标仍 active）**：T-25 真实长篇失败库中已确认 1 个真实 exemption 触发：`ending_pressure_missing`，并同步 `critique_exemption_applied`；质量门仍因 3 个 critical consistency 冲突拒绝。报告 `backend/output/t18-real-exemption-triggered-longform-audit-20260823.json`。成功多章样本仍为 0 触发，但不能再把全工作区 T-18 触发数概括为 0；人工真值和质量收益仍缺。
> **2026-08-23 T-18 拒绝章趋势投影最终修复**：真实 T-25 失败样本通过趋势 API 可见为 `quality_gate_passed=false`，并保留 exemption 与 `critique_exemption_applied` 各 1 个 `ending_pressure_missing`；专项 **21 passed**。观测链路已一致，豁免质量/误杀率仍无人工真值。
> **2026-08-23 本轮最终门禁与 T-18 证据收束**：后端最新全量 **1003 passed, 0 failed in 95.32s**；前端 type-check、Vitest **48 files/295 tests**、串行 build-only 全部通过。T-18 真实触发样本已由 T-25 长篇失败库确认 1 次，且拒绝章趋势 API 正确输出 `quality_gate_passed=false` 与 exemption 字段。该证据仍不等于人工豁免质量真值；T-16 只有当前冻结口径重复配对，E-11 尚无真实 repair_attempted=true 样本。
> **2026-08-23 当前硬缺口总账（总目标仍 active）**：`backend/output/novel-quality-gap-register-20260823.json` 固化了当前证据矩阵。未闭环项没有被绿灯掩盖：人工标签 0/19、T-16 合法前后收益 0、E-01.2 prompt A/B 缺失、T-18 仅 1 个触发且无人工判断、E-11 真 repair 0、T-06 degrade 分布不足。当前门禁后端 1003 passed，前端 48/295 通过。
> **2026-08-23 E-11/T-22 结构薄弱 writing_notes 负控补证（总目标仍 active）**：真实 2 章显式 self-critique 探针要求弱结构生成，仍 2/2 成功、repair 数组均为空、未触发真实 repair；E-11 脱敏报告已追加该 probe。结论仍是观测/负控有效，真实 patch 注入与收益缺失。
> **2026-08-23 T-06 provider probe 更新（总目标仍 active）**：provider 探测 HTTP 200、模型列表 27 个，脱敏报告 `backend/output/t06-provider-probe-audit-20260823.json`；仅为外部可用性证据，不替代真实 completion/retry/degrade 分布或人工质量结论。
> **2026-08-23 T-24 真实长篇 runtime contract 审计（总目标仍 active）**：真实成功长篇运行的 plan/checkpoint/content_delta/task_completed/heartbeat/事件计数已脱敏固化，证据 `backend/output/t24-real-longform-runtime-contract-audit-20260823.json`；相关专项 **222 passed**。当前 scene-split timeout 无生产执行器，按 N/A 契约保留，不视为已实现。

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

> **2026-08-23 完成资格保护器双审/仲裁校验补强（总目标仍 active）**：完成审计现同时检查 reviewer-A/B 完整标签、样本与身份、独立 reviewer、合法 merge/adjudicated 结果、正确 `source_files` 与无 `adjudicate`；新增 5 项回归（含错误 source_files 反向验证），专项 **17 passed**，后端全量 **1024 passed**，前端 type-check、Vitest **48/305**、build-only 均通过。当前审计仍 `completion_eligible=false`，六个硬缺口不变。

> **2026-08-23 E-01.2 Provider 阻断证据收束（总目标仍 active）**：追加 baseline/candidate 各 10 个固定任务的真实尝试，均收到 Provider SSE HTTP 503，0 条 redacted live record；阻断审计器专项 **4 passed**，后端全量 **1026 passed**，输出 `provider_blocked_or_no_records`、`ab_success=false`、`aggregate_delta=null`，不制造 prompt gain 或 T-16 证据。E-01.2 仍为硬缺口。

> **2026-08-23 T-16 corrected acceptance 接口补齐（总目标仍 active）**：新增 `audit_t16_corrected_acceptance.py`，专项 **6 passed**，仅验证固定输入、生产 scorer 版本差异、同一独立冻结 evaluator 和输入指纹一致；不调用 Provider、不读取正文、不计算收益。当前真实双 scorer 生成批次仍缺，T-16 保持硬缺口。

> **2026-08-23 T-06 标准化 rate 审计接口补齐（总目标仍 active）**：新增 `audit_t06_standardized_rate.py`，专项 **7 passed**；当前三批显式输入因模型/契约混杂被判 `insufficient`，eligible 20 calls 但 `degrade_rate=null`。该接口证明“证据不足时不报数”的护栏有效，不关闭 T-06。

> **2026-08-23 E-11/T-22 repair gain 审计接口补齐（总目标仍 active）**：新增 `audit_e11_repair_gain.py`，专项 **11 passed**；当前真实触发报告为 `insufficient/gain=false`，Provider 前置阻断为 `blocked/gain=false`，严格防止 unchanged、缺 diagnostics 或未放行样本被误报为 repair gain。

> **2026-08-23 本轮后端/前端门禁复验（总目标仍 active）**：后端全量 **1043 passed**；前端 type-check、Vitest **48 files/305 tests**、build-only 均通过。完成审计仍 false，六项硬缺口未因门禁绿灯而改变。

> **2026-08-23 Provider 最小 baseline 续探针（总目标仍 active）**：单任务 `smoke-dialogue` 实际生成阶段 HTTP 503，0 条正文/记录；该阻断只作为 E-01.2 Provider 状态证据，不计入 prompt gain、T-06 rate 或 E-11 repair 样本。

> **2026-08-23 总任务接续、T-26 分级与 Provider 恢复（总目标仍 active）**：接续文档已补齐 Agent Workspace 的整体设计和落地分期。矩阵/登记册将 T-26 dialogue marker 真实语义校准补为第 7 个 hard-gap，E-02/T-25 仅保留 partial 证据状态。`.env` 当前解析 `gpt-5.6-sol`，真实 baseline/candidate 各 10/10 成功；`e012-prompt-ab-current-20260823.json` 的 controlled A/B 平均分 delta +144.4、字数 delta -695.1。因 prompt contract 改变且无人工标签，E-01.2/T-16 仍不完成；completion audit 为 false、7 blockers。

> **2026-08-23 Agent Phase 1 最小闭环落地（总目标仍 active）**：后端 Agent registry/policy/executor/schemas 与 `/api/agent/tools`、`/api/agent/plan` 已落地，项目范围越权和未注册工具均有反向测试；前端 AgentWorkspace、工具列表、计划展示、项目上下文和旧 WritingDesk 入口已落地。后端 **1051 passed**，前端 **49 files/308 tests**、type-check、build-only 通过。该阶段只生成 provider-free 计划，不等于完整 Agent 执行系统。
