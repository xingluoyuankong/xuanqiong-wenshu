# 优化轮次 R37：真实 Provider 章节端到端复验（2026-09-19）

## 目标

在当前服务器提交 `917cfd3`、公网入口 `8013` 上重新验证真实 Provider 链路，区分健康检查、队列响应、确定性 fallback 和真实非空章节产物，并记录 token usage 归属与失败证据。

## 测试流程

- 创建临时项目并保存单章蓝图；
- 配置总预算/章节预算各 `100.0`；
- 通过 `/api/writer/novels/{project_id}/chapters/generate` 发起真实章节生成；
- 轮询章节状态并读取版本与 usage；
- 不把 `HTTP 200` 或队列状态计为成功；
- 完成后删除临时项目并做 SQLite integrity/orphan audit。

## 当前成功证据

临时项目：`20b1a94a-95c9-4188-88cb-300e898d3bec`。

服务日志显示：

```text
stage=generate_mission duration_ms=30001.41
stage=prepare_context duration_ms=31074.84
stage=generate_variants duration_ms=71216.55
stage=ai_review duration_ms=0.6
stage=continuity_gate duration_ms=35.47
stage=persist_versions duration_ms=69.95
pipeline total duration_ms=103430.88
```

结果接口/账本证据：

- status HTTP：`200`；
- 最终运行阶段：`waiting_for_confirm`，进度 `97`；
- 候选版本数：`1`；
- 非空版本正文长度：`588` 字符；
- token usage HTTP：`200`；
- `total_tokens=18183`；
- `total_cost=0.0247`；
- `content` 模块：`18183 tokens`；
- usage 记录数：`2`；
- 临时项目删除：HTTP `200`；
- 删除后：`novel_projects=0`、`chapters=0`、`token_budgets=0`、`orphan_project_rows={}`。

这证明当前真实 Provider 能返回可持久化的非空章节候选，并完成 usage attribution；最终是等待人工确认，不把候选稿误报为已选定最终版本。

## 失败/降级证据

同一轮日志还记录了向量 embedding 调用使用当前 provider 凭据时返回 `401 invalid_api_key`，`ChapterContextService` 捕获后降级继续生成；这不是正文 Provider 成功，也不是生产级 embedding 可用证据。

当前阶段耗时瓶颈为：

1. 导演脚本约 30 秒；
2. 上下文准备约 31 秒；
3. 正文候选生成约 71 秒。

## 下一步优化

### P0：embedding provider 能力隔离

- 为 chat completion 与 embeddings 分离配置/能力探测；
- 启动时记录 embedding availability，不再等真实生成阶段才暴露 401；
- embedding 不可用时明确标记 `vector_context_degraded`，但不把章节生成降级误报为完整 RAG 成功；
- 对成功正文和向量上下文分别验收。

### P1：阶段耗时收敛

- 为 `generate_mission`、`prepare_context`、`generate_variants` 建立按 provider/model 的 p50/p95 统计；
- 评估导演脚本/上下文是否可缓存或并行，保持质量门和取消 drain 不变量；
- 不通过降低质量门或缩短硬超时制造假绿灯。

### P1：候选稿与最终稿状态显示

- 继续确认 status schema 对 `waiting_for_confirm` 的字段映射，确保前端显示候选稿而非空章节；
- 保持 `selected_version_id=null` 时不宣称已选定最终版本。

## 本轮结论

- 真实 Provider：PASS（非空候选 + usage attribution）；
- SSE/人工确认终态：候选稿已落库，最终确认流程仍需单独验收；
- embedding/RAG：PARTIAL，存在 401 降级；
- 取消/删除生命周期：已由 R36 live 验证 PASS；
- 迁移 runner、依赖可重建性、Naive UI 首屏拆分仍未完成。