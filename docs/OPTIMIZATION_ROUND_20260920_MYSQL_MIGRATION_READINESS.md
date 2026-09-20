# 优化轮次 R53：MySQL migration 只读 readiness audit（2026-09-20）

## 目标

SQLite copy dry-run 已完成，但项目当前 `DB_PROVIDER` 仍是 SQLite，且 MySQL migration runner 会创建数据库、创建 schema 并复制数据，不能在缺少目标库审查时直接调用。本轮增加只读 readiness audit，不连接 MySQL、不创建数据库、不写入目标库。

## 新增入口

```bash
bash scripts/audit_mysql_migration_readiness.sh
```

检查：

- 当前 `db_provider`；
- MySQL host/port/database/user/password 是否配置；
- `asyncmy` 依赖是否存在；
- migration manifest hash/size provenance；
- fragment 中 MySQL-only 和 destructive tokens；
- 明确输出 `execute=false`、`connected=false`、`writes_performed=false`。

## 当前预期结论

服务器当前使用 SQLite；MySQL 密码/目标服务没有进入已验证可执行状态，因此 audit 应保持 `BLOCKED`，而不是尝试连接或运行迁移。

## 通过标准

只有同时满足以下条件才进入 `READY_FOR_REVIEW`：

1. provenance 无失败；
2. MySQL password/目标配置完整；
3. `asyncmy` 已安装；
4. fragment 风险已人工审阅；
5. 后续仍需独立 copy dry-run、备份、rollback 和人工批准，才考虑执行。