# 优化轮次 R42：SQLite 迁移副本 dry-run 与 rollback 验收（2026-09-19）

## 目标

R30 已能生成 migration plan，但所有 fragment 都保持 `execute=false`。本轮增加只针对 SQLite 的副本演练工具：从生产 SQLite 只读备份到临时副本，在副本上执行无 MySQL 方言且无破坏性 token 的 fragment，验证 schema fingerprint 变化和 rollback，生产库始终零写入。

## 新增入口

```bash
bash scripts/migration_copy_dry_run.sh
```

脚本行为：

1. 通过 SQLite backup API 创建一致性副本，不复制 WAL/SHM 文件；
2. 校验 migration manifest 中的 fragment hash/size；
3. 跳过含 MySQL 方言或破坏性 token 的 fragment；
4. 仅在临时 working copy 执行可执行 SQL；
5. 从 before copy 生成 restored copy，比较 rollback fingerprint；
6. 对生产源库前后做只读 schema fingerprint 比对；
7. 输出 `source_unchanged`、`rollback_verified`、`applied`、`skipped` 和 `provenance_failures`。

## 验收标准

- 生产源库 schema fingerprint 前后相同；
- rollback fingerprint 等于 before fingerprint；
- manifest provenance 无失败；
- SQLite 可执行 fragment 才进入 `applied`；
- B/C/D 等 MySQL fragment 保持 `skipped`，不被强行转换或执行；
- SQLite integrity、schema baseline、topology audit 和 Git remote sync 全部通过。

本工具不执行 MySQL 迁移，不修改生产 SQLite，不生成可直接应用生产的 SQL。