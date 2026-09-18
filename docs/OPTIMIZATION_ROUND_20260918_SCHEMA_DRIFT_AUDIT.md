# 优化轮次 US-010-R6：SQLite schema drift 只读审计

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`284b24b`

## 当前事实

- ORM metadata 期望表数：54。
- 生产 SQLite 实际表数：56。
- 缺失表：0。
- 缺失列：0。
- 额外表：`project_research_configs`、`research_artifacts`。
- 外键违规：0。

额外表来自数据库侧研究功能残留/扩展，当前不直接删除；它们会被审计工具显式列出，避免被误报成缺失或静默纳入模型。

## 本轮交付

- `scripts/audit_sqlite_schema.py`：只读 SQLite 与 ORM metadata 对照，输出 JSON，缺表/缺列/外键违规返回失败。
- `scripts/audit_sqlite_schema.sh`：使用统一服务器运行时入口执行审计。
- 默认允许额外表作为 advisory；`--strict-extra` 可把额外表升级为失败。

## 验收标准

- [x] 当前生产 SQLite：缺失表 0、缺失列 0、外键违规 0。
- [x] 额外表被显式报告。
- [x] 审计不写数据库、不创建 WAL/SHM、不修改业务数据。
- [ ] 后续补齐研究表 ORM 模型或明确废弃并迁移删除额外表。
- [ ] 建立正式 schema 版本/迁移工具，替代当前 `create_all + SQL fragments` 混合方式。
