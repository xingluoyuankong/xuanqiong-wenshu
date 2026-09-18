# 优化轮次 US-010-R3：Provider 异常回归契约收口

- 执行日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线提交：`c8d97e0f300554bad5b4854a46f8cfee8a0f7e84`

## 发现

上一轮服务器后端全量门禁为 `259 passed / 4 failed`。逐条审计后确认：

1. `test_provider_exception_handling.py` 的两个测试直接调用 fake service，绕过生产 `GenerationCallPolicy`，却断言重试次数；测试自身没有覆盖生产重试路径。
2. `test_provider_exception_handling_v2.py` 按旧 OpenAI SDK 签名构造 `RateLimitError`，当前 SDK 要求 `httpx.Response` 和 `body` 参数。
3. v2 attempt ledger 测试对同一 `attempt_id=2` 追加两条记录，却断言最终只有两条；真实账本语义是更新同一物理尝试。

## 修复

- 两个 fake retry 测试改用生产 `call_generation_text` + `GenerationCallPolicy`，保留 429/503、重试次数和最终结果断言。
- OpenAI 异常测试使用当前 SDK 要求的 `httpx.Response` 和 `body=None`。
- Mock ledger 按 `attempt_id` 更新已有尝试，验证失败状态覆盖 pending 状态。

## 最终验证

- [x] Provider 定向回归：`12 passed in 8.12s`。
- [x] 后端全量回归：`263 passed in 19.50s`。
- [x] Provider 429/503 重试、fallback、attempt ledger 与当前生产路径一致。
- [x] 未降低 retry、错误分类或账本断言标准。
- [x] 仅剩 `passlib` 对 Python `crypt` 的弃用 warning，无失败用例。

## 后续

- 继续做真实 Provider 章节生成与 token usage 对账。
- 独立收口 SQLite schema 版本追踪，当前 checkout 尚未包含 Alembic 配置/版本目录。
