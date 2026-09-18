# 优化轮次 US-010-R4：SQLite 外键与项目删除孤儿数据

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`de12d36b5ac3762b2ff52e60063b2a2ee359619c`

## 发现

重新审查数据库后发现，`novel_projects` 已为 0，但 `chapters=1`、`token_budgets=3`，均为本轮预算 smoke 创建的项目残留。模型定义带有 `ON DELETE CASCADE`，但 SQLite 每连接没有开启 `PRAGMA foreign_keys=ON`，导致项目删除后外键级联没有执行。

## 修复

- `backend/app/db/session.py`：在 SQLite 初始化连接和每个新连接的 PRAGMA hook 中启用 `foreign_keys=ON`。
- `backend/app/services/test_sqlite_generation_pool.py`：增加真实连接 `PRAGMA foreign_keys == 1` 回归。
- 删除前数据库快照：
  `backups/us010-r4-before-orphan-cleanup-20260918-202012.db`

## 已知残留处理

只针对本轮已知 smoke 项目 ID 做后续清理，不触碰其他用户项目；清理后复核所有主要 project_id 外键表的 orphan count。

## 验收标准

- [x] SQLite 新连接 `PRAGMA foreign_keys=1`。
- [x] 删除项目后 chapters/token_budgets/token_usages/alerts 等关联行自动级联。
- [x] 已知 smoke 残留清理后 orphan count 全部为 0。
- [x] 后端定向 8 passed；全量 265 passed in 18.64s。
- [x] 已推送 GitHub；R4 修复后重启 8013，健康 200，真实 budget smoke 通过。

## 当前结果

- 数据库快照：`backups/us010-r4-before-orphan-cleanup-20260918-202012.db`。
- 定点删除：`chapters=1`、`token_budgets=3`，只对应已知 smoke 项目 ID。
- 清理后：`chapters=0`、`token_budgets=0`、`token_usages=0`、`token_budget_alerts=0`。
- 所有带 `project_id` 的关联表 orphan count：`{}`。
- 新增只读审计：`scripts/audit_sqlite_integrity.py`。

## 最终线上验收

- R4 提交：`d8a7833`。
- R4 重启后 8013 PID：`38242`。
- 8013/8099/5174：均 HTTP 200。
- 真实预算 smoke：登录/创建/预算/蓝图/生成/删除全部通过。
- 日志未出现 SQLite 外键错误。
