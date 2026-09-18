# 优化轮次 US-010-R17：生产 SQLite schema baseline

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线提交：`699e16c`

## 目的

在正式 migration history 建立前，保存一份不含业务数据的生产 schema 锚点，用于后续迁移设计、回滚前后差异检查和部署验收。

## Baseline 文件

```text
docs/schema_baselines/20260918-production-sqlite.json
```

文件只包含：

- Git commit
- capture 时间
- ORM metadata 表/列结构
- SQLite 实际表/列结构
- ORM/database 两个 SHA-256
- missing/extra tables
- missing/extra columns
- match/drift 状态

不包含用户项目、章节正文、token、密钥或账号数据。

## 当前结果

```text
git_commit=699e16c155f1cd8014a508fb0e9f8a3003272c2f
expected_table_count=57
actual_table_count=57
missing_tables=[]
extra_tables=[]
missing_columns={}
extra_columns={}
status=match
```

## 验收标准

- [x] baseline 只读采集完成。
- [x] 当前 ORM 与生产 SQLite 表/列一致。
- [x] baseline 不含业务数据。
- [x] 可在副本数据库上用于后续 migration diff。
- [ ] 正式 migration version/history 仍需独立设计和回滚演练。
