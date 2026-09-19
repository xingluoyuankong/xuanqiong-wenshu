# 优化轮次 US-010-R30：非执行 migration plan

- 日期：2026-09-19
- 分支：`codex/server-us010-r1`
- 目标：为正式 migration runner 建立前置计划和阻断门禁，禁止直接把 MySQL SQL fragment 打到 SQLite。

## 新工具

```text
scripts/plan_migration.py --target sqlite
scripts/plan_migration.py --target mysql
```

工具只读读取：

- migration manifest
- SQL fragment hash
- production schema baseline
- 当前 Git commit

输出有序 steps、MySQL-only token、destructive token、执行阻断原因和正式 runner 缺口。它从不执行 SQL。

## 当前计划结论

- SQLite target：4 个 fragment 全部 `execute=false`，需要 dialect-specific translation。
- MySQL target：含 MySQL 专用语法的 fragment 仍需备份、copy dry-run、rollback 证据和人工 review；当前仍 `execute=false`。
- 正式 migration runner/history 尚未建立，因此计划状态为 `blocked_by_missing_runner`，不是失败。

## 后续验收

- [x] provenance hash 校验。
- [x] baseline hash 绑定。
- [x] SQLite 直接执行被明确禁止。
- [x] MySQL-only/危险 token 显式报告。
- [ ] 副本数据库 upgrade/rollback。
- [ ] 正式 runner/history。
- [ ] 生产切换。
