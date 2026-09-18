# 优化轮次 US-010-R15：schema drift metadata 注册一致性

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`619694b`

## 发现

运行时 `app_schema_state` 已记录 ORM 57 表，但独立 `audit_sqlite_schema.sh` 只加载到 55 个模型，导致研究表 `project_research_configs` 与 `research_artifacts` 被误报为额外表。根因是 `backend/app/models/__init__.py` 未显式导入 `research.py`，模型注册依赖 router 导入顺序。

## 修复

- 显式注册 `ProjectResearchConfig` 和 `ResearchArtifact`。
- ORM metadata、启动 schema fingerprint、只读 schema audit 现在使用同一份 57 表 metadata。

## 验收

```text
metadata_table_count=57
research_registered=True True
expected_table_count=57
actual_table_count=57
missing_tables=[]
extra_tables=[]
missing_columns={}
extra_columns={}
foreign_key_violations=[]
backend_full_pytest=270 passed in 19.15s
```

后续仍需正式 migration history；本轮只收口 metadata registration 和 drift 观测一致性，不向数据库写迁移版本号。
