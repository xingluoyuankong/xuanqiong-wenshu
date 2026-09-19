# 优化轮次 US-010-R22：SQL migration fragment provenance

- 日期：2026-09-19
- 分支：`codex/server-us010-r1`
- 目标：在正式 migration history 尚未建立前，锁定现有 SQL fragment 来源与 hash，防止迁移文件静默漂移。

## 交付

- `backend/db/migration_manifest.json`：记录 migration SQL 文件顺序、大小、SHA-256、schema baseline hash 和生成 commit。
- `scripts/verify_migration_manifest.py`：只读校验文件存在、大小和 hash；漂移返回 exit 10。

## 边界

这不是正式数据库 migration runner，不会自动执行 SQL，也不向生产数据库写版本号；它是迁移来源完整性门禁。
