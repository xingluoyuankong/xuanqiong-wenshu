# 优化轮次 R48：短章节正文 Token Ceiling 收敛（2026-09-20）

## 触发证据

R47 真实 500 字章节在 `generate_variants` 阶段耗时约 59.4 秒，而当前短章节单次正文生成仍使用 `max_tokens=3200`。实际正文长度约 489 字，最低字数为 200，3200 token 上限存在过大的无效输出空间。

## 本轮变更

对于 `target_word_count < 1200`：

```text
旧：3200
新：max(1800, target_word_count × 2.5)
```

示例：

```text
500 -> 1800
700 -> 1800
1100 -> 2750
```

保留：

- 外层 Provider jitter retry；
- 最低字数门；
- 确定性 mission fallback；
- 质量门、连续性门、候选版本机制；
- 长章节 token 分档。

本轮没有减少正文目标字数或最低字数，只收敛单次 Provider 输出预算。

## 验收

```text
后端全量：285 passed, 1 warning
```

新增回归：

- 500 字短章节 ceiling 为 1800；
- 700 字短章节 ceiling 为 1800；
- 1100 字短章节 ceiling 为 2750；
- 1200 字及以上保持原长章节分档。

## Live 验收标准

部署后使用受控 500 字真实章节请求验证：

1. `generate_variants` 实际请求使用短章节 ceiling；
2. 候选版本非空且满足最低字数；
3. usage attribution 完整；
4. 项目删除后 SQLite 零残留；
5. 用 R45 报告收集新样本，不把单次耗时当作 p95 结论。

## R48 Live 证据

在提交 `fc80cc4` 部署后的公网 `8013` 上完成受控 500 字真实 Provider smoke：

```text
最终阶段：waiting_for_confirm
候选版本：1
正文长度：597 字符
generate_mission：20002.46ms
generate_variants：55661.75ms
prepare_context：961.75ms
pre_mission_context：85.87ms
post_mission_context：957.06ms
total_tokens：16011
usage records：2
```

项目删除：HTTP `200`；清理审计：

```text
novel_projects=0
chapters=0
token_budgets=0
orphan_project_rows={}
```

本轮证明短章节 token ceiling 调整没有破坏正文非空、候选落库、usage attribution 或清理流程。`generate_variants` 仍是当前短章主要耗时段，后续继续基于真实数据优化，不把单次样本当作 p95 结论。

## 回滚

回滚本轮提交可恢复 3200 token 短章节 ceiling，不涉及数据库迁移或前端构建。