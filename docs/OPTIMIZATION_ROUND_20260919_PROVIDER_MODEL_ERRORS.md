# 优化轮次 US-010-R26：Provider 模型不可用错误分类

- 日期：2026-09-19
- 分支：`codex/server-us010-r1`
- 目标：避免把上游 `model_not_found / no available channel` 当作可重试的 503 jitter。

## 真实证据

当前 Provider 对无效模型返回：

```text
HTTP 503
error.code=model_not_found
message=No available channel for model ...
```

## 修复

- LLM 出口识别 `model_not_found`、`no available channel`、`unknown model` 等明确模型路由错误。
- 转换为 `HTTP 404`、`code=PROVIDER_MODEL_UNAVAILABLE`、`retryable=false`。
- GenerationCallPolicy 不再对该错误重试或执行非流式 fallback。
- 真正的 500/502/503 网络/上游抖动继续保留 retry/fallback。

## 验收

- [ ] 无效模型真实 Provider 探针仍得到上游 503 原始证据。
- [x] 应用分类回归得到 model_unavailable。
- [x] retryable=false。
- [x] 后端全量：`272 passed in 18.33s`。
- [ ] R26 推送 GitHub。

## 最终验证

- 真实 Provider 无效模型探针：HTTP 503，`error.code=model_not_found`，message 含 `No available channel`。
- 应用层定向回归：14 passed。
- 应用层将该类错误分类为 `model_unavailable`、`PROVIDER_MODEL_UNAVAILABLE`、`retryable=false`，不执行无意义 retry/fallback。
