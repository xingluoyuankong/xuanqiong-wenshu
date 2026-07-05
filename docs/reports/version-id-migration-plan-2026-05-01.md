# version_id 替代 version_index 安全迁移方案

生成时间：2026-05-01

## 目标

把章节版本选择、删除、评估、Diff 等操作从易错的数组下标 `version_index` 迁移为稳定的 `version_id`。

## 当前风险

- 前端展示顺序与后端 relationship 顺序可能不一致。
- 删除/新增/并发生成后 index 可能错位。
- 手工编辑和 Patch 生成新版本后，旧 index 链路容易误选版本。

## 分阶段实施

### 阶段 1：兼容 API

1. 后端新增按 `version_id` 操作的请求字段。
2. 保留 `version_index` 兼容旧前端。
3. 若同时传入，以 `version_id` 为准。
4. 所有响应返回 `version_id`、`display_index`、`created_at`。

### 阶段 2：前端迁移

1. VersionSelector 内部点击选择/删除/评估时传 `version.id`。
2. Diff 弹窗以版本 ID 配对。
3. index 只作为 UI 展示序号，不作为 API 参数。

### 阶段 3：测试

1. 构造 3 个版本。
2. 删除中间版本后选择最后版本。
3. 验证 selected_version_id 与用户选择一致。
4. 并发新增版本后继续选择旧版本，确保不被排序影响。

### 阶段 4：移除旧字段

当前端和 E2E 全部迁移后，后端标记 `version_index` deprecated。至少保留 1 个版本周期。

## 验收标准

- 所有版本操作 API 支持 version_id。
- 前端不再依赖 version_index 发起破坏性操作。
- 单测覆盖删除后选择、并发新增后选择、评估指定版本。
