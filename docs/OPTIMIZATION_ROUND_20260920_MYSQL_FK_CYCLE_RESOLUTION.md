# 优化轮次 R63：MySQL FK cycle 两阶段解析方案（2026-09-20）

## 目标

把 R62 发现的 FK cycle 转成可审阅、可回滚的 MySQL 迁移顺序设计；本轮只形成 review 方案，不连接、不创建、不写入 MySQL。

## 已确认的 cycle

### `chapters` ↔ `chapter_versions`

```text
chapters.selected_version_id -> chapter_versions.id
chapter_versions.chapter_id -> chapters.id
```

`selected_version_id` 可为空，适合延迟添加约束；`chapter_versions.chapter_id` 为必填，章节行必须先存在。

### `timeline_events` 自引用

```text
timeline_events.caused_by_event_id -> timeline_events.id ON DELETE SET NULL
```

该列可为空，适合先建表/导入，再添加自引用约束。

## 建议迁移阶段

### Phase 0：前置证据

- 新鲜 SQLite backup manifest；
- source schema fingerprint；
- migration fragment hash；
- 目标 MySQL database 为空且连接信息通过 readiness audit；
- 人工确认目标字符集、排序规则、JSON/LONGTEXT 类型映射。

### Phase 1：创建无 cycle 的基础表

先创建所有不依赖 cycle 的表和基础外键。对 `chapters` 和 `chapter_versions`：

- 创建 `chapters`，暂不添加 `selected_version_id -> chapter_versions` 外键；
- 创建 `chapter_versions`，保留 `chapter_id -> chapters` 外键，或在 copy 阶段临时 deferred；
- 创建 `timeline_events`，暂不添加 `caused_by_event_id` 自引用外键。

### Phase 2：数据复制

按项目/主表到子表顺序复制：

1. `novel_projects` 及基础用户/配置表；
2. `chapters`（`selected_version_id` 暂时允许为空）；
3. `chapter_versions`；
4. 其余 chapter 子表、评审、预算和 memory/timeline 数据；
5. 校验每个外键候选值存在且行数与 SQLite snapshot 一致。

### Phase 3：回填并添加 cycle constraints

- 校验所有非空 `chapters.selected_version_id` 都指向对应 `chapter_versions.id`；
- 添加 `chapters.selected_version_id -> chapter_versions.id ON DELETE SET NULL`；
- 校验所有 `timeline_events.caused_by_event_id` 都指向现有 event；
- 添加 `timeline_events.caused_by_event_id -> timeline_events.id ON DELETE SET NULL`；
- 运行 `FOREIGN_KEY_CHECKS`/information_schema 约束审计；
- 记录 post-migration schema fingerprint。

## Rollback 方案

- 生产 apply 前只允许在独立目标库副本执行；
- 失败时销毁目标库副本并从备份恢复，不在生产库执行逐表反向删除；
- upgrade、rollback 前后分别记录 schema fingerprint、表行数和约束清单；
- 只有人工 review 通过后才允许使用 R60 的 `--apply --backup-manifest` 闸门。

## 当前状态

```text
execute=false
connected=false
writes_performed=false
status=BLOCKED_BY_FK_CYCLES
```

原因：当前仍为 SQLite，MySQL password 未配置，且 cycle 的目标建表/约束顺序尚未在 MySQL copy 上演练。该文档不代表迁移已执行。