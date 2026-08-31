
## 2026-08-22 T-15/E-11/T-25 追加审计

- E-08 七个正式题材组全部覆盖，但各组仅 1 条；E-09 无题材标签/正文，不能证明跨题材 marker 召回。
- E-11 warning patch 白名单已修复，避免 continuity/focus warning 在 revise_chapter 前丢失。
- T-25 非法 checkpoint 类型统一映射为 LongformGenerationContractError。


## 2026-08-22 T-16 历史重建可行性

- 历史提交 `3e6406070af5a391deed7427198258691dd85ece` 不包含当前 quality_bench runner、chapter writing contract snapshot 或 v4 request contract；旧 batch 也缺 request fingerprint。
- 旧 batch 仅有 3 个 smoke 任务，不能与当前中文 10-task benchmark 组成合法 T-16 改前对照。历史评分器重算不等于真实生成前后收益。
- 当前严格审计仍为 35 summaries / 12 complete fingerprints / 8 singleton groups / 0 candidate pairs；人工标签和 T-18 exemption 真值仍待外部真实证据。

## 2026-08-22 并行子线程审计与修复

- 6 个独立线程完成质量门、趋势、长篇 helper 和前端三态链路审计；未发现 T-06/T-07、T-09～T-11、T-24/T-25 的确定新增生产缺陷。
- `audit_quality_trend.py` 现与趋势 API 同口径回填 `story_progression_guard` 缺失指标；定向 17 passed，历史主库报告仍为 150 quality metric rows / 35 gate rows / 0 exemptions。
- 前端趋势/详情/摘要统一把 `undefined` 视为未提供而非通过/可控；全量 48 files / 256 tests、type-check、build-only 通过。
- `quality_metric_corpus_calibration.py` 读取 metadata 并传递 focus character names，兼容旧表和坏 JSON；最新脱敏报告 `backend/output/quality-metric-corpus-calibration-20260822T122852Z.json`。
- T-16 严格审计仍为 35 汇总 / 12 完整指纹 / 8 单成员同条件组 / 0 合法配对；人工标签 0/19，T-18 无 exemption 真值。

## 2026-08-22 T-13/T-26 语义标记校准

- 新增 `audit_dialogue_state_marker_categories.py`，输出分类命中率但不输出正文或词例；新增专项回归。
- 151 条源记录/149 条合格样本：状态标记非零率 0.9933，p05/p50/p95=3.0/12.0/27.6；声明对话样本 112/112 有标记。
- 揭示/选择/外部压力命中率=0.6644/0.6846/0.5436；未声明对话样本=0，不能据此调 `UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR`。候选词影响模拟没有改变零标记样本，因此暂不改词表。

## 2026-08-22 T-16 严格可比性审计

- 新增 `audit_quality_bench_comparability.py`，只读取 rescore-summary 元数据，不读取或输出正文。
- 最新扫描：35 个汇总、12 个完整 schema v2 指纹、8 个同任务/同请求/同 Provider/同模型分组、0 个跨评分器候选配对。
- 现有 v3 与 v4 10 任务批次虽任务集合相同，但生成请求契约和评分器指纹不同，且各自只有一个批次；严格 T-16 仍缺改前真实生成批次。
- 人工标签仍 0/19，历史豁免仍 0；不得以自动评分或历史重算替代人工真值。

## 2026-08-22 目标恢复与校准补充

- 已恢复总目标并持续登记为 active；本轮新增的校准证据不能替代同任务同模型同请求契约的改前生成批次。
- audit_historical_scorer_delta.py 最新只读结果：151/151 可比、0 failed；这是旧评分器与当前评分器对同一历史正文的行为差异，不是生成前后质量真值。
- quality_metric_corpus_calibration.py 已适配当前 _evaluate_content_balance(..., word_count=...) 签名，并加入回归测试；最新校准 151 条，报告不包含正文。
- 历史 exemption_counts={}，人工标签 19 条全部为空；T-18 不得凭统计调阈值。已有 3-task baseline 与当前 10-task 中文契约不一致，T-16 不得比较。
# E-08 quality_bench 使用说明

## 模式

- python scripts/quality_bench.py --smoke --output-dir output/quality-bench-smoke：固定 fixture 离线 smoke，不访问 Provider。
- python scripts/quality_bench.py --rescore-only <run_dir>：从独立正文文件重新评分，汇总 CSV/JSON 不嵌入正文。
- python scripts/quality_bench.py --provider-probe：只探测配置的 OpenAI-compatible /models，不生成正文。
- python scripts/quality_bench.py --live --output-dir <dir>：默认对前 3 个固定任务书执行真实 /chat/completions，正文写入独立 .txt，失败只写阻断证据。

## 安全边界

- API key 只从环境变量读取，不接受命令行传入，也不写入报告。
- CSV/汇总 JSON 只保存质量指标、调用耗时和 token usage；正文只在同一 run 目录的独立文件中保存。
- /models 探测成功不等于 completion 可用。鉴权、额度、限流或返回结构失败时，live run 的 record_count 不会虚增。
- HTTP 429/5xx、网络错误和空响应均记录为 live_failures；阻断 run 同时写出 live-status.json 与 rescore-summary.json。

## 当前审计证据（2026-08-21）

- Provider host：api.xzxyuan.ccwu.cc。固定 direct benchmark 可用模型为 `deepseek/deepseek-v4-flash-free`，2026-08-21 实测 3/3 completion 成功，平均分 911、平均字数 1397。
- 完整 ASGI 端到端使用 `gpt-5.6-sol`，同一隔离项目连续生成 3 章成功；质量门、候选落库、SSE content 事件和 Last-Event-ID replay 均通过，趋势汇总见 `backend/output/e09-multichapter-trend-20260821.json`。
- 旧默认 free 模型曾出现 HTTP 429/无可用通道，provider 路由不稳定；运行时可用模型应通过 `--provider-probe` 与低成本 completion 复核。
- 当前仍缺 E-08 的同一固定任务书前后版本批量对比、20+ 章统计和人工质量评价；不能把 3 章 smoke 宣称为完整批量验收。
- 当前 runner 是 `provider_live_direct_completion`，用于验证 provider live 与评分落盘闭环；ASGI smoke 才是完整 PipelineOrchestrator.generate_chapter 端到端证据。

复测前先单独运行 --provider-probe，确认 completion 额度/限流恢复后，再运行 --live。


## 2026-08-21 扩展任务集

- `scripts/bench_missions/smoke-*.json` 固定 3 项，`--smoke` 永远只跑这 3 项。
- `scripts/bench_missions/benchmark-*.json` 新增 7 项，合计 10 项固定任务；`--live --all-missions` 才会运行全部 10 项。
- 2026-08-21 扩展 live batch 真实结果：10/10 provider HTTP 503 `No available channel`，record_count=0；不得把它记为质量门通过或失败率样本。
## 2026-08-22 SSE/v3 复验口径

- live 请求优先使用 SSE 分片收集，旧测试替身或兼容网关不支持 `stream` 时才走非流式兼容回退；每条记录写入 `response_transport`。
- 空正文、HTTP 429、HTTP 5xx 最多重试 1 次；重试耗尽后写入 `live_failures`，不虚增 `record_count`。
- 请求指纹 schema v2 包含 prompt contract、system prompt SHA-256、temperature、max_tokens、传输模式和重试策略；缺字段的旧批次不可用于 T-16 比较。
- v3 prompt 强调目标/阻碍/转折、`turn/end_hook`、最后 10% 递压和禁止总结收束。2026-08-22 v3 单任务因 provider HTTP 429 未产生正文，不能把 prompt 改动报为质量收益。
- 最新完整 v2 SSE+重试批次为 8/10 正文、2/10 重试后失败，质量指标聚合已写入 `rescore-summary.json`；E-08 仍未通过。
- Retry-After 仅用于计算一次重试等待，强制截断在 15 秒内；不会把重试后的空正文/429 计为成功。
## 2026-08-22 中文任务契约

- `bench_missions/*.json` 已改为语义等价中文任务书。此前英文任务书与中文正文的字符串 mission-hit 规则不兼容，会把已兑现任务误报为 `chapter_progression_weak`；旧英文 batch 不得同新中文任务契约作比较。
- 当前生产评分保留原有整句/人物锚点，并补充保守中文 2 字内容锚点；至少两个命中才影响推进判定，泛化词与功能词不计入。
- 中文契约 gpt-5.6-sol SSE v3 完整批次为 9/10 正文（唯一失败为 RemoteProtocolError）；失败任务的独立传输复验成功，但不能与 9/10 拼接成一个 10/10 批次。
## 2026-08-23 T-16 legacy 时间证据兼容修正

- `audit_quality_bench_comparability.py` 对新 live 批次优先读取 `generation_started_at`，旧摘要缺失时兼容使用 `generated_at`；相同时间仍进入 `ambiguous_time_pairs`，原因统一为 `missing_or_equal_generated_at`。
- 相关质量基准专项 **34 passed**；当前只读扫描 41 个摘要、18 个完整指纹、9 个同条件组、9 个 candidate、1 个 comparable、0 个 ambiguous。唯一 comparable 是当前冻结评分器/请求契约的重复 batch，不是 T-16 合法优化前后收益。

