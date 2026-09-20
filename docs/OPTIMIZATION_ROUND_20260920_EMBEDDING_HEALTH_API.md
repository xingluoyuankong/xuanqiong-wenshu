# 优化轮次 R55：Embedding Health Check API（2026-09-20）

## 目标

R41 已有服务器 CLI embedding probe，但管理员/前端没有不启动正文生成就读取 embedding 能力状态的 HTTP 入口。本轮复用现有用户鉴权和 `LLMService`，增加只读接口：

```text
GET /api/llm-config/embedding-health-check
```

## 返回内容

```json
{
  "checked_at": "...",
  "vector_nonempty": false,
  "vector_dimension": 0,
  "status": {
    "provider": "openai",
    "model": "text-embedding-3-large",
    "status": "degraded",
    "code": "EMBEDDING_CONFIG_MISSING"
  }
}
```

不返回：

- API key；
- Authorization header；
- 上游响应正文；
- 正文生成项目数据。

## 验收

- 新增路由回归覆盖鉴权后的脱敏 capability status；
- 后端全量：`287 passed, 1 warning`；
- 缺少 embedding key 时调用仍是本地分类，不外发 chat key；
- SQLite、topology、runtime dependency audit 继续通过。

## 后续

配置独立 embedding key/base URL 后，可直接调用该接口验证非空向量和维度，再进入 RAG 命中质量验收。

## 当前线上 Live 证据

部署 `bb6c624` 后，使用管理员登录调用：

```text
GET /api/llm-config/embedding-health-check
```

结果：

```json
{
  "vector_nonempty": false,
  "vector_dimension": 0,
  "status": {
    "provider": "openai",
    "model": "text-embedding-3-large",
    "status": "degraded",
    "code": "EMBEDDING_CONFIG_MISSING"
  }
}
```

HTTP `200`，未创建章节、项目或预算记录，响应未包含 API key。
