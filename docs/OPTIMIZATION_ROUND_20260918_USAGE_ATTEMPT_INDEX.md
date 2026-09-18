# 优化轮次 US-010-R8：真实 usage 物理尝试序号

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`7894ba5`

## 发现

真实 Provider E2E 已经落账 prompt/completion usage，但 `TokenUsage.attempt_index` 仍由 `record_llm_usage` 固定写成 `None`，重试后的真实成本无法按物理尝试区分。

## 修复

- `LLMService._stream_single_model` 在 Provider usage 到达时记录当前物理 attempt（从 1 开始）。
- `LLMService` 出口把 `usage_sink.attempt_index` 传给 `record_llm_usage`。
- `usage_attribution_service.record_llm_usage` 接受并写入 `attempt_index`。
- 新增 `test_records_physical_attempt_index` 回归。

## 验收标准

- [x] 真实 Provider E2E usage 正常返回时 `attempt_index=1`。
- [x] 失败→重试→成功回归覆盖 usage_sink `attempt_index=2`；真实 E2E 覆盖正常 attempt=1。
- [x] 真实 Provider E2E 的 usage 行包含 `attempt_indexes=[1]`。
- [x] 后端全量测试：`267 passed`。
- [ ] R8 提交推送 GitHub。

## 最终真实 E2E

- run_id：`aff6d25e-3b09-4b97-8544-f7cee4611f63`。
- 正文：594 字，SSE terminal complete。
- TokenUsage：2 行，总 16664；prompt 11769；completion 4895；estimated rows 0。
- attempt indexes：`[1]`；stage=`chapter_generation`；model=`GLM-5.3-Flash`。
- E2E exit：0。

## 生产入口最终验收

- R8 提交：`d69b444`。
- 8013 重启后 PID：`38940`。
- 8013/8099/5174：HTTP 200。
- 真实 budget smoke：通过并自动删除测试项目。
- SQLite integrity：foreign_keys=1、orphan_project_rows={}。
- schema drift audit：缺表/缺列/外键违规为 0，额外表 2 个 advisory。
- 启动日志 warning grep：无 legacy admin email schema fallback。

## Retry 回归

- 新增 `backend/app/services/test_usage_attempt_index.py`。
- 使用真实 OpenAI `RateLimitError` 类型模拟第一次物理调用失败。
- 第二次调用成功并携带 usage，断言 `attempt_index=2`。
- 定向结果：`13 passed`。
