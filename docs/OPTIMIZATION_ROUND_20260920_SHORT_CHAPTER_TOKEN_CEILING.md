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

## 回滚

回滚本轮提交可恢复 3200 token 短章节 ceiling，不涉及数据库迁移或前端构建。