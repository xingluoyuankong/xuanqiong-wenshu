# 优化轮次 R60：MySQL 迁移默认执行闸门（2026-09-20）

## 触发证据

现有 `backend/scripts/migrate_sqlite_to_mysql.py` 包含：

- 创建 MySQL 数据库；
- 创建目标 schema；
- 关闭/恢复 foreign key checks；
- 复制 SQLite 全部 ORM 表数据。

原入口缺少显式 apply 闸门，误调用可能直接进入目标库写入路径。

## 本轮变更

迁移脚本现在默认只输出 preview：

```text
execute=false
connected=false
writes_performed=false
status=preview_only
```

只有显式传入：

```bash
--apply --backup-manifest BACKUP.json
```

才进入真实迁移函数；backup manifest 必须存在且包含：

```json
{"backup_completed": true}
```

新增回归验证：

- 默认 preview 永远不连接、不写入；
- preview 输出隐藏密码；
- apply 缺少 backup manifest 时直接失败。

## 验收

```text
迁移 guard + 质量回归：69 passed, 1 warning
后端全量：289 passed, 1 warning
```

SQLite 生产库未修改，MySQL 未连接，未创建数据库，未复制任何数据。

## 现有 readiness 结论

当前服务器仍为：

```text
db_provider=sqlite
mysql_password_set=false
status=BLOCKED
```

因此本轮不会执行真实 MySQL migration。要进入 apply 阶段，还需：

1. 目标 MySQL 配置；
2. 生产 SQLite 备份 manifest；
3. MySQL copy dry-run；
4. upgrade/rollback fingerprint；
5. 人工 review。

## 回滚

回滚本轮提交会恢复原迁移入口；默认 preview 闸门是本轮新增的安全不变量。