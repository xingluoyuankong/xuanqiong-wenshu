# 优化轮次 R51：候选耗时 Runtime 序列化修复（2026-09-20）

## 触发证据

R50 的日志已记录完整候选耗时：

```text
generation_ms=61358.25
guardrail_check_ms=0.22
guardrail_rewrite_ms=0.0
total_ms=61363.72
```

但章节 status runtime 将嵌套 `candidate_timings` 压缩为：

```text
["[object:5]"]
```

原因是 runtime compact 的嵌套深度保护将 attempt -> timings -> dict 结构折叠，前端和审计无法读取新增诊断数字。

## 本轮变更

将 runtime `candidate_timings` 改为扁平列表：

```json
[
  {
    "attempt_index": 1,
    "index": 0,
    "generation_ms": 0,
    "guardrail_check_ms": 0,
    "guardrail_rewrite_ms": 0,
    "total_ms": 0
  }
]
```

这样保留 `_compact_runtime_value` 的全局深度限制，同时候选数值可直接进入 status runtime 和最终 event metadata。

## 验收

```text
后端全量：285 passed, 1 warning
```

下一条受控真实短章节 smoke 验证 status runtime 中不再出现 `[object:5]`，且项目清理、usage attribution、SQLite integrity 保持通过。

## 回滚

回滚本轮提交会恢复嵌套结构；不涉及数据库、Provider 参数或质量门。