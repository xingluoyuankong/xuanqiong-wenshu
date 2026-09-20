# 优化轮次 R47：Prepare Context 子阶段可观测性（2026-09-20）

## 触发证据

R45 报告显示 `prepare_context` p95 约 32.5 秒，但该计时此前从历史摘要开始、跨越 `generate_mission`，导致导演脚本等待被 `generate_mission` 和 `prepare_context` 双重统计，无法判断真实上下文组装长尾。

## 本轮变更

将上下文阶段拆分为：

```text
pre_mission_context
post_mission_context
```

- `pre_mission_context`：历史上下文、writer blueprint、角色可见范围；
- `generate_mission`：独立保留；
- `post_mission_context`：可见性上下文、长篇上下文、增强写作上下文、记忆、项目记忆、风格、故事指引和 RAG；
- `prepare_context` 从 mission 结束后开始计时，避免与 mission 重叠；
- 子阶段 timing 写入 `runtime_metadata.context_phase_timings_ms`，并进入最终 runtime event metadata；
- 日志增加 `Pipeline context phases completed`，仅包含毫秒数字，不包含正文或凭据。

## 回归

新增非负 timing helper 回归。

```text
后端全量：284 passed, 1 warning
```

唯一警告仍为 passlib 使用 Python `crypt` 的弃用提示。

## 验收标准

部署后用受控真实短章节请求验证：

1. runtime 中存在 `context_phase_timings_ms`；
2. 至少含 `pre_mission_context`、`post_mission_context`；
3. `prepare_context` 不再包含 mission 30/20 秒等待；
4. 候选版本、usage attribution 和清理流程继续正常；
5. SQLite integrity 和 topology audit 通过。

## 后续

R47 先消除阶段统计双计数。拿到新样本后再针对真正较慢的上下文子阶段做缓存、并行或降级优化，不通过删除上下文质量约束制造表面提速。