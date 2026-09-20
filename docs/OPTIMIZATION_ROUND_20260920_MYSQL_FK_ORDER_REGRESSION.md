# 优化轮次 R63：MySQL FK 只读规划器回归锁定（2026-09-20）

## 目标

为 R62 的 MySQL FK dependency planner 增加回归测试，锁定当前 schema 的真实统计、cycle 识别和只读边界，防止后续把阻断状态误报为可执行迁移。

## 验证范围

测试文件：

```text
backend/app/services/test_mysql_fk_order.py
```

测试通过仓库根目录下的 `scripts/plan_mysql_fk_order.py` 执行 planner，并断言：

```text
table_count=57
edge_count=76
execute=false
connected=false
writes_performed=false
status=BLOCKED_BY_FK_CYCLES
```

当前识别的两个阻断环：

```text
chapters <-> chapter_versions
timeline_events -> timeline_events
```

具体关系：

```text
chapters.selected_version_id -> chapter_versions.id
chapter_versions.chapter_id -> chapters.id
timeline_events.caused_by_event_id -> timeline_events.id
```

## 安全边界

- planner 只读取 ORM metadata；
- 测试不建立 MySQL 连接；
- 测试不执行 migration，不创建表，不写数据库；
- `BLOCKED_BY_FK_CYCLES` 是当前正确的审查状态，不代表 planner 本身失败；
- MySQL apply 仍受 `--apply --backup-manifest` 与 backup manifest 闸门控制。

## 运行命令

```bash
bash scripts/test_backend.sh
```

本轮提交前记录实际 pytest 输出、当前 commit、服务重启结果和 topology/runtime audit；若环境或外部依赖导致失败，保留原始失败证据，不通过修改断言降低验收标准。
