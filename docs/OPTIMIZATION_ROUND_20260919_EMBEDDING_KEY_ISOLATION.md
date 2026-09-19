# 优化轮次 R40：Embedding 专用凭据隔离（2026-09-19）

## 根因

R39 直接探针确认 embedding 请求使用 OpenAI provider、`text-embedding-3-large`，返回 `401 invalid_api_key`。原实现当 `embedding.api_key` 缺失时回退复用 chat completion 的 API key，导致：

- embedding 配置缺失被误表现为远端鉴权失败；
- chat key 被发送到不一定支持该 key 的 embedding endpoint；
- 管理员无法区分“没有 embedding 配置”和“embedding 服务拒绝有效配置”。

## 本轮变更

`LLMService.get_embedding()` 的 OpenAI 分支现在要求独立的 `embedding.api_key`：

- 已配置：继续使用 `embedding.api_key`，base URL 可使用 embedding 专用配置或兼容的 chat base URL；
- 未配置：本地直接返回空向量并设置：

```json
{
  "status": "degraded",
  "code": "EMBEDDING_CONFIG_MISSING"
}
```

不再回退使用 chat completion key，也不发起错误凭据的远端请求。现有调用方仍收到空列表并走 RAG 降级，不影响正文生成。

新增回归验证：

- 缺少 embedding key 时不发 provider 请求；
- 状态码为 `EMBEDDING_CONFIG_MISSING`；
- R39 的 401/403/普通错误分类仍保持稳定。

## 验收结果

```text
Embedding/RAG/质量/取消专项：75 passed, 1 warning
后端全量：283 passed, 1 warning
```

唯一警告仍为 passlib 使用 Python `crypt` 的弃用提示。

R38/R39 的 live evidence 仍保留：

- RAG runtime 可记录 `degraded=true`；
- 已配置但被上游拒绝时分类为 `EMBEDDING_AUTHENTICATION_FAILED`；
- 未配置独立 key 时 R40 本地分类为 `EMBEDDING_CONFIG_MISSING`。

## 后续任务

1. 在管理端增加 embedding 专用 key/base URL 的能力探测入口；
2. 为 embedding probe 增加最近状态、时间和 model 记录，但不记录密钥；
3. 配置有效后做一次真实非空 embedding 和维度验收；
4. migration runner、依赖可重建性和 Naive UI 首屏拆分继续推进。

## 回滚

回滚本轮提交会恢复 chat key fallback；不涉及数据库迁移，不影响正文质量门和取消 drain。