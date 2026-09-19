# 优化轮次 R39：Embedding Provider 失败能力分层（2026-09-19）

## 目标

R38 已经把 embedding 降级暴露为 `EMBEDDING_UNAVAILABLE`，但真实日志显示具体原因是 Provider 返回 `401 invalid_api_key`。本轮在保持 `get_embedding() -> List[float]` 兼容契约的前提下，细分 embedding 能力失败类型，供 RAG runtime metadata 和后续运维诊断使用。

## 本轮变更

### LLMService

新增最近一次 embedding 能力状态：

```json
{
  "status": "healthy|probing|degraded",
  "provider": "openai|ollama",
  "model": "...",
  "code": "..."
}
```

失败码：

- `EMBEDDING_AUTHENTICATION_FAILED`：401 或鉴权失败；
- `EMBEDDING_PERMISSION_DENIED`：403 或权限拒绝；
- `EMBEDDING_TIMEOUT`：上游超时；
- `EMBEDDING_CONNECTION_FAILED`：网络连接失败；
- `EMBEDDING_EMPTY_RESPONSE`：Provider 返回空向量；
- `EMBEDDING_REQUEST_FAILED`：其他请求错误；
- `EMBEDDING_DEPENDENCY_MISSING`：Ollama 依赖缺失。

原有调用方仍收到空列表并走既有降级路径，不把 embedding 故障升级成章节正文失败。

### RAG runtime metadata

`ChapterRAGContext` 现在同时携带：

- `degraded`；
- `degradation_reason`；
- `embedding_status`。

这些字段进入持久化 `runtime_metadata.retrieval_stats`，前端和审计可以区分具体能力故障。

## 验收结果

```text
Embedding/RAG/质量/取消专项：71 passed, 1 warning
Embedding failure code regression：5 passed
后端全量：279 passed, 1 warning
```

唯一警告仍为 passlib 使用 Python `crypt` 的弃用提示。

R38 live smoke 已证明持久化结构能够记录：

```json
{
  "degraded": true,
  "degradation_reason": "EMBEDDING_UNAVAILABLE",
  "chunks": 1,
  "summaries": 1
}
```

R39 的细分码将在下一次真实 401 请求中验证为 `EMBEDDING_AUTHENTICATION_FAILED`，不把静态配置推断当作 live 证据。

## 未完成项

1. 为 chat completion 与 embedding 配置做独立能力探测；
2. 在不消耗正文额度的前提下，提供管理员可触发的 embedding probe；
3. 真实 401/403/timeout/connection 分类各做一条 live 证据；
4. 评估 embedding 专用 key/base URL 是否需要独立轮换；
5. migration runner、依赖可重建性和 Naive UI 首屏拆分继续保留在总队列。

## 回滚

回滚本轮提交会恢复统一 `EMBEDDING_UNAVAILABLE` 语义；不涉及数据库迁移、正文生成质量门或 Provider timeout。