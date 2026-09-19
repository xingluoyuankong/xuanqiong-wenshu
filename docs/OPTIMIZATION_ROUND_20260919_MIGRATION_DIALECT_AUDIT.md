# 优化轮次 US-010-R25：migration fragment 方言与执行风险审计

- 日期：2026-09-19
- 分支：`codex/server-us010-r1`
- 目标：在正式 migration runner 建立前，明确现有 SQL fragment 的目标方言和 SQLite 执行边界。

## 当前发现

- `add_deep_optimization_features.sql`、`add_novel_kit_features.sql` 含 `AUTO_INCREMENT`、`ENGINE=InnoDB`、`COLLATE`、MySQL 风格 JSON/ALTER 语句。
- `alter_chapters_real_summary_to_longtext.sql` 含 `MODIFY COLUMN`。
- `add_chapter_outline_metadata.sql` 是最接近 SQLite 可转换的 fragment，但仍不应直接在生产执行。

## 新工具

```text
scripts/audit_migration_fragments.py
```

工具只读扫描 SQL，不执行任何 migration，输出：

- `mysql_only_translation_required`
- `dialect_neutral_candidate`
- `manual_review_required`
- MySQL-only token
- dangerous token
- execute_on_sqlite=false

## 验收标准

- [x] 4 个 fragment 全部被扫描。
- [x] MySQL-only 语法被显式报告。
- [x] SQLite 执行策略明确为 never execute。
- [x] 不修改生产数据库。
- [ ] 后续为 SQLite/MySQL 分别设计正式 migration runner。
- [ ] 副本数据库完成 upgrade/rollback 演练后再考虑生产切换。
