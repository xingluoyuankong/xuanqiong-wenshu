# OpenAPI Smoke Fixture 回收 Dry-Run 清单

> 盘点时间：2026-09-06 00:04:54 +08:00
>
> 数据来源：默认 SQLite `D:\小说写作\xuanqiong-wenshu\backend\storage\xuanqiong_wenshu.db` 的只读查询，以及未跟踪运行证据 `.audit-openapi-smoke-fixtures-20260905.jsonl`。
>
> 本文档只记录候选项和回收前置条件；本轮未删除项目、运行任务、章节或任何关联数据。

## 核心统计

| 维度 | 结果 |
| --- | --- |
| OpenAPI Smoke 项目总数 | 21 |
| 历史无 marker 的 `OpenAPI Smoke 0` | 20 |
| 带显式 marker 的 UUID fixture | 1，标题 `OpenAPI Smoke b75a2a7299bd` |
| owner | 21/21 为 `user_id=1` / `XZXyuan` / `3211280448@qq.com` |
| 项目状态 | 21/21 为 `draft` |
| TaskRuntime | 21/21 各 1 个 `chapter_generation`，共 21 个 |
| TaskRuntime 状态 | 21/21 为 `stale` |
| 阶段/进度 | 21/21 为 `waiting_for_confirm` / `97.0` |
| 错误 | 21/21 为 `STALE_TASK` / `heartbeat timeout` |
| 每项目关联记录 | 1 chapter、1 chapter outline、1 novel blueprint、1 project member、1 token budget |
| 创建年龄 | 0.743 至 1.288 天（截至盘点时间） |

## Dry-Run 分组

| 分组 | 数量 | 判定 | 依据 |
| --- | ---: | --- | --- |
| `LEGACY_UNMARKED_STALE` | 20 | 回收候选，等待 owner 确认 | 标题为 `OpenAPI Smoke 0`、没有 `xq-smoke-fixture:*` marker、项目为 `draft`、唯一运行任务已 stale |
| `MARKED_FIXTURE_STALE` | 1 | 保留观察，不进入默认回收 | 含 `xq-smoke-fixture:b75a2a7299bd`，marker 可追溯 fixture 创建与清理链路 |

## 逐项清单

年龄按 `2026-09-06 00:04:54 +08:00` 计算，单位为天。所有条目的 runtime 均为唯一的 `chapter_generation` 任务，阶段 `waiting_for_confirm`、进度 `97.0`、状态 `stale`。

| # | project_id | 标题 | created_at | updated_at | 年龄 | marker | 判定 |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | `9dca8c63-7416-4aaa-a65b-6b983aad5a61` | `OpenAPI Smoke 0` | 2026-09-04 17:10:21 | 2026-09-04 17:11:08.008623 | 1.288 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 2 | `3e98e50a-4556-4f87-80d2-c8890f3e4e65` | `OpenAPI Smoke 0` | 2026-09-04 19:05:41 | 2026-09-04 19:06:48.231869 | 1.208 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 3 | `72ed8d25-6cf8-4f11-80f8-432cf8ccc8af` | `OpenAPI Smoke 0` | 2026-09-04 20:43:28 | 2026-09-04 20:44:00.253043 | 1.140 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 4 | `91519eb0-5b4d-4f3c-a61c-c4ce1ca9e42b` | `OpenAPI Smoke 0` | 2026-09-04 21:33:42 | 2026-09-04 21:34:18.427087 | 1.105 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 5 | `f950cb98-07c2-4d5a-ba2d-31954cae0163` | `OpenAPI Smoke 0` | 2026-09-04 21:36:05 | 2026-09-04 21:36:42.839336 | 1.103 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 6 | `ecb7a7fc-77dc-4c95-85e5-747762cf2211` | `OpenAPI Smoke 0` | 2026-09-04 22:58:51 | 2026-09-04 22:59:26.779531 | 1.046 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 7 | `281ccd80-e2ef-4284-994c-2dceee7ab15b` | `OpenAPI Smoke 0` | 2026-09-04 22:59:31 | 2026-09-04 23:00:38.246045 | 1.045 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 8 | `79d46fa0-c38a-4a00-bbe2-94426fee0103` | `OpenAPI Smoke 0` | 2026-09-04 23:01:20 | 2026-09-04 23:01:51.118731 | 1.044 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 9 | `068abf69-67d8-4d16-b51e-9541bf6d0f58` | `OpenAPI Smoke 0` | 2026-09-04 23:09:29 | 2026-09-04 23:09:59.951929 | 1.038 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 10 | `af196722-ebf7-4afc-8720-04611dc97542` | `OpenAPI Smoke 0` | 2026-09-04 23:30:55 | 2026-09-04 23:31:19.927409 | 1.024 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 11 | `649d32cd-3298-4907-874d-60e81b7b52d5` | `OpenAPI Smoke 0` | 2026-09-04 23:44:37 | 2026-09-04 23:45:15.209138 | 1.014 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 12 | `81162fca-8a53-4246-9828-7ea3091c7716` | `OpenAPI Smoke 0` | 2026-09-05 00:10:41 | 2026-09-05 00:11:03.974713 | 0.996 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 13 | `3e85f19e-1998-4c0a-b3af-fbd7b748e5fe` | `OpenAPI Smoke 0` | 2026-09-05 00:12:08 | 2026-09-05 00:12:53.748687 | 0.995 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 14 | `5f941743-edd5-4cef-bb7f-88a0400ea912` | `OpenAPI Smoke 0` | 2026-09-05 00:20:45 | 2026-09-05 00:21:26.880928 | 0.989 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 15 | `a12adb7e-f7a9-42c7-821e-7fb76528a5ae` | `OpenAPI Smoke 0` | 2026-09-05 00:59:47 | 2026-09-05 01:00:08.482073 | 0.962 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 16 | `e852504c-6ef0-45a8-ae8b-06677a7b239c` | `OpenAPI Smoke 0` | 2026-09-05 01:50:12 | 2026-09-05 01:50:55.665109 | 0.927 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 17 | `e9dc03fe-dc7b-4f8d-ba86-c0469cc87e1d` | `OpenAPI Smoke 0` | 2026-09-05 02:42:56 | 2026-09-05 02:43:49.581514 | 0.890 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 18 | `453e4fba-8fd2-4a41-8831-0ae4ed3aadca` | `OpenAPI Smoke 0` | 2026-09-05 03:08:50 | 2026-09-05 03:09:57.929654 | 0.872 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 19 | `67637b55-79f2-43d6-b222-9ea36c2130b6` | `OpenAPI Smoke 0` | 2026-09-05 03:20:13 | 2026-09-05 03:20:59.801877 | 0.864 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 20 | `fd6d585d-2821-4d34-a655-99f379ac76e8` | `OpenAPI Smoke 0` | 2026-09-05 04:08:04 | 2026-09-05 04:08:22.705864 | 0.831 | `<none>` | `LEGACY_UNMARKED_STALE` |
| 21 | `a9b66d93-79b8-4053-80b6-3a56bcf02fae` | `OpenAPI Smoke b75a2a7299bd` | 2026-09-05 06:15:09 | 2026-09-05 06:15:46.367776 | 0.743 | `xq-smoke-fixture:b75a2a7299bd` | `MARKED_FIXTURE_STALE` |

## 动作边界与复核要求

1. 本清单是 dry-run，不执行 DELETE，不更新项目状态，不重置或重试 TaskRuntime。
2. 后续动作必须以 `project_id` 精确定位，并在动作前再次读取 owner、marker、关联记录、runtime 任务和事件。
3. 只有 `LEGACY_UNMARKED_STALE` 且 owner 确认不再需要的项目进入实际回收队列；带 marker 的项目默认保留。
4. 实际回收前先导出项目及关联记录摘要并校验备份，再走应用层级联删除；禁止直接批量修改数据库文件。
5. 删除前后记录项目、关联资源、TaskRuntime 任务/事件和审计日志计数，并将实际动作清单与本 dry-run 清单分开保存。

证据脚本：`D:\小说写作\xuanqiong-wenshu\backend\scripts\audit_smoke_fixtures.py`。原始 `.audit-openapi-smoke-fixtures-20260905.jsonl` 保留为未跟踪运行证据，不纳入提交。
