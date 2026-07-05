# 蓝图生成路径异步统一方案

生成时间：2026-05-01

## 目标

灵感模式生成小说蓝图只走后台任务路径：`start/status/cancel`。同步 `/blueprint/generate` 仅保留为兼容或内部调试，不再由主 UI 直接调用。

## 当前风险

- 前端存在同步旧路径和后台任务路径并存。
- 取消任务不能真正中断已进入的 LLM 调用。
- job 主状态在进程内，重启后恢复依赖 conversation_history system 记录。

## 分阶段实施

### 阶段 1：前端统一

1. InspirationMode 在 ready_for_blueprint 后只显示 BlueprintConfirmation。
2. BlueprintConfirmation 只调用 start/status/cancel。
3. 删除或隐藏同步 `generateBlueprint()` 主流程调用。
4. 超时、失败、取消都展示结构化错误和重试按钮。

### 阶段 2：后端副作用控制

1. 将蓝图任务拆为：生成草稿 → job successful → 用户保存。
2. 取消后不得写入项目正式 blueprint。
3. 若为了兼容仍在 generate_blueprint 中写库，需要拆出 pure_generate_blueprint。

### 阶段 3：任务持久化

1. 新增 blueprint_generation_jobs 表。
2. 保存 status、progress、error、started_at、finished_at、request_id。
3. 服务重启后通过 job 表恢复状态，而不是扫描 conversation_history。

### 阶段 4：测试

1. start 后 status queued/running/successful。
2. cancel 后后台完成也不能写入正式蓝图。
3. 服务重启模拟后 status 可恢复。
4. LLM JSON 解析失败返回 retryable 错误。

## 验收标准

- 主灵感流程无同步蓝图生成长请求。
- 取消任务无正式蓝图写入副作用。
- job 状态可持久恢复。
- 前端 E2E 覆盖 start/status/success/fail/cancel。
