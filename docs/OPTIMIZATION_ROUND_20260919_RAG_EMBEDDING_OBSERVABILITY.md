# 优化轮次 R38：RAG embedding 降级可观测性（2026-09-19）

## 触发证据

R37 真实 Provider 章节生成成功，但日志记录 embedding 请求返回 `401 invalid_api_key`，章节上下文服务随后静默返回空向量上下文。正文仍能生成，但运行结果无法区分：

- 向量库被有意关闭；
- 向量库开启但 embedding provider 不可用；
- embedding 成功但当前项目没有命中片段。

## 本轮变更

### `ChapterRAGContext`

新增：

```text
degraded: bool
degradation_reason: Optional[str]
```

当向量库开启、查询 embedding 为空时，返回：

```json
{
  "degraded": true,
  "degradation_reason": "EMBEDDING_UNAVAILABLE"
}
```

向量库主动关闭时保持：

```json
{
  "degraded": false,
  "degradation_reason": null
}
```

这样“功能关闭”和“能力故障”不会混为一谈。

### Pipeline runtime metadata

`PipelineOrchestrator` 将 `retrieval_stats` 写入持久化 `runtime_metadata`，并在最终运行事件的 metadata 中保留：

- mode
- chunks
- summaries
- continuity_injection
- degraded
- degradation_reason

前端状态轮询和后续审计可以直接识别 embedding 降级，不需要依赖日志 grep。

### 回归测试

新增：

```text
backend/app/services/test_chapter_context_service.py
```

覆盖：

1. 空 embedding 明确标记 `EMBEDDING_UNAVAILABLE`；
2. 向量库关闭不误报 embedding 降级。

## 验收结果

### 后端专项与全量

```text
RAG/质量/取消专项：71 passed, 1 warning
后端全量：279 passed, 1 warning
```

唯一警告为 passlib 使用 Python `crypt` 的弃用提示。

### Live budget smoke

```text
login=200
create=201
budget_update=200
blueprint=200
generate=200
status=budget_not_allocated
budget_gate_reason=budget_not_allocated
allowed_actions=['pause']
queued=False
delete=200
```

### 未在本轮宣称完成的内容

本轮解决的是降级可观测性，不是 embedding provider 修复本身。R37 的 `401 invalid_api_key` 仍需下一轮完成：

1. chat completion 与 embedding 配置/凭据能力探测分离；
2. 启动或首次能力探测时明确记录 embedding availability；
3. embedding 可用性与正文 Provider 可用性分别验收；
4. RAG 命中质量和 embedding 维度单独做真实请求验证。

## 发布与回滚

- 只修改 RAG runtime metadata 和测试；
- 不执行数据库迁移；
- 不改变生成质量门或 Provider timeout；
- 回滚提交即可恢复原有空上下文返回行为。