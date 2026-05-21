# 玄穹文枢全功能重构验证记录（2026-05-21）

## 本轮代码收口

- 新增全功能缺陷地图：`docs/reports/full-product-function-map-2026-05-21.md`。
- 旧前端 `NovelAPI.generateBlueprint()` 已改为后台任务轮询，不再直接调用同步 `/blueprint/generate`。
- 后端同步 `/blueprint/generate` 已标记 deprecated，并返回 `Deprecation`、`Link`、`X-Xuanqiong-Legacy-Route` 响应头。
- 章节候选版本选择、删除、评审、优化改为 `version_id` 优先；没有稳定 ID 时才发送 `version_index`。
- `GenerationRuntimeEvent` 支持 `developer_detail`，日志页会把它折进“开发者详情”，不污染用户看的生成状态摘要。

## 自动化验证

- `python -m compileall backend/app`：通过。
- `python -m pytest backend/app/services/test_generation_quality_guards.py -q`：57 passed。
- `python -m pytest backend -q`：236 passed。
- `cd frontend; npm run test:run`：120 passed。
- `cd frontend; npm run build`：通过。
- `cd frontend; npm run test:run -- src/api/modules/chapterWorkflow.spec.ts`：3 passed。

## 项目本体启动验证

- 后端：`http://127.0.0.1:8013/api/health` 返回 `{"status":"healthy","app":"玄穹文枢 API","version":"1.0.0"}`。
- 前端：`http://127.0.0.1:5174/` 返回 HTTP 200。
- CPA：`http://localhost:8317/` 当前仅作为 Provider 端点，不作为应用本体。
- 当前本地已有项目与 runtime 日志可通过 API 读取；历史数据库中部分旧项目标题存在旧编码痕迹，本轮不做历史数据迁移。

## 多视角评判转代码

- 作者视角：旧同步蓝图入口会让长任务卡在请求里，已改为前端旧方法也走后台任务。
- 编辑视角：候选版本按 index 操作有错位风险，已改为稳定 `version_id` 优先。
- 读者视角：日志应先看生成状态，不应被原始调试字段淹没，已新增 `developer_detail` 分层。
- 连续性审校视角：不改变现有局部补丁/锚点逻辑，只补可观测性和版本选择准确性。
- 系统稳定性视角：旧同步后端路由暂不删除，先 deprecated，避免破坏外部旧客户端。
- UI 可用性视角：本轮未大改布局，只把会影响操作稳定性的入口与日志字段先收口。

## 保留风险

- 尚未完成 2-3 轮完整 AI 生成实跑；本轮完成了项目本体健康检查、自动化测试和接口级验证。
- 风格学习、旧稿导入、章节大纲生成任务化仍是下一批 P1。
- 历史数据库旧数据存在乱码样本，需要单独做数据清理/迁移，不能混进本轮代码重构。
