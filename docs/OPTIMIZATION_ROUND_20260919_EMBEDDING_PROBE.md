# 优化轮次 R41：Embedding 能力只读探针（2026-09-19）

## 目标

R40 已将 embedding 专用 key 缺失和远端鉴权失败分开，但此前只能通过章节生成或临时 Python 命令观察状态。本轮增加可重复的服务器只读探针，不创建项目、不写数据库、不消耗正文生成额度。

## 新增入口

```bash
bash scripts/probe_embedding.sh
bash scripts/probe_embedding.sh --text "探针文本" --user-id 1
```

输出只包含：

- `vector_nonempty`；
- `vector_dimension`；
- provider；
- model；
- status；
- 稳定 failure code。

不会输出 API key、Authorization header 或响应正文。

返回码：

- `0`：得到非空 embedding；
- `10`：探针执行成功但 embedding 不可用；
- 其他非零：运行时/配置执行错误。

## 当前服务器实测

R40 当前配置没有独立 embedding key，因此探针结果应为：

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

## 验收标准

1. 探针不创建 `novel_projects`、`chapters` 或预算记录；
2. 缺 key 时本地返回 `EMBEDDING_CONFIG_MISSING`，不发起远端请求；
3. 配置有效时返回非空向量和维度；
4. 401/403/timeout/connection 使用 R39 稳定码；
5. API key 不出现在 stdout、日志摘要或文档中；
6. `git diff`、后端回归、拓扑审计和远端同步全部通过。

## 后续

配置专用 embedding key 后，用同一探针做真实非空向量和维度验收，再进入 RAG 命中质量评估。