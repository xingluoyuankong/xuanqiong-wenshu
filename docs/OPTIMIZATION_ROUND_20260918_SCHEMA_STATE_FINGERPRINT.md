# 优化轮次 US-010-R13：运行时 schema state 指纹

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`798b94f`

## 目标

在正式 migration 工具尚未建立前，为每次应用启动保留可追踪的 ORM/database schema 状态，不伪造 Alembic revision，也不删除现有额外研究表。

## 实现

- 新增 `app_schema_state` ORM 表。
- `backend/app/db/schema_fingerprint.py` 计算：
  - ORM metadata SHA-256。
  - 实际 database schema SHA-256。
  - expected/actual table count。
  - missing/extra tables。
  - missing/extra columns。
  - status=`match`/`drift`。
- `init_db()` 在 `create_all + schema updates` 后写入 `runtime_schema` 状态。
- 原有 `scripts/audit_sqlite_schema.sh` 继续只读审计。

## 验收

- [x] schema fingerprint 定向测试 2 passed。
- [x] 后端全量测试 `270 passed in 17.88s`。
- [x] 重启 8013/8099 后 `app_schema_state` 实际落库。
- [x] 启动日志输出 `SCHEMA-STATE status=match` 和 ORM/DB hash 前缀。
- [x] schema drift 仍将两个额外研究表标记为 advisory。
- [ ] 本轮推送 GitHub。

## 约束

这不是正式 migration history；仍需后续设计可回滚 schema version/migration manifest，避免把当前快照误当成历史迁移链。

## 最终线上验收

- R13 全量后端：`270 passed in 17.88s`。
- `app_schema_state`：1 行，status=`match`，expected/actual tables=57。
- 8013/8099 重启后日志输出 schema fingerprint，不再触发旧 Alembic warning。
- 8013/8099/5174 health 均 HTTP 200。
- 运行时 manifest 检测 `working_tree_dirty=true`，提交后将重新对齐。
