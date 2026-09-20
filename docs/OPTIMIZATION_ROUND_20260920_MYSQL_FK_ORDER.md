# 优化轮次 R62：MySQL FK 依赖顺序只读规划（2026-09-20）

## 目标

R60 的 MySQL preview 已暴露 `chapters` 与 `chapter_versions` FK cycle。本轮从当前 ORM metadata 生成只读 dependency plan，识别可按拓扑创建的阶段和必须人工处理的强连通环。

## 新增

```text
scripts/plan_mysql_fk_order.py
scripts/plan_mysql_fk_order.sh
docs/OPTIMIZATION_ROUND_20260920_MYSQL_FK_ORDER.md
```

运行：

```bash
bash scripts/plan_mysql_fk_order.sh
```

输出：

- table_count/edge_count；
- acyclic_phases；
- blocked_cycles；
- cycle_edge_details；
- `execute=false`、`connected=false`、`writes_performed=false`。

## 验收标准

1. 只读取 ORM metadata，不连接 MySQL；
2. 不创建表、不写数据库；
3. cycle 被显式列出，不把不可排序 schema 误报成可执行；
4. acyclic tables 提供可审阅 phase 顺序；
5. MySQL apply 仍由 R60 的显式 `--apply --backup-manifest` 闸门控制。