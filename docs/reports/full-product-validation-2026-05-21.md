# 玄穹文枢全功能重构验证记录（2026-05-21）

## 本轮代码收口

- 新增全功能缺陷地图：`docs/reports/full-product-function-map-2026-05-21.md`。
- 旧前端 `NovelAPI.generateBlueprint()` 已改为后台任务轮询，不再直接调用同步 `/blueprint/generate`。
- 后端同步 `/blueprint/generate` 已标记 deprecated，并返回 `Deprecation`、`Link`、`X-Xuanqiong-Legacy-Route` 响应头。
- 后端同步 `/blueprint/generate` 已进一步改为兼容转发：只启动/复用后台蓝图任务，不再直接执行完整同步生成。
- 章节大纲生成新增后台任务入口 `/chapters/outline/start/status/cancel`，前端默认通过后台任务启动和轮询结果，旧 `/chapters/outline` 仅保留 deprecated 兼容。
- 导出新增 `/export/preflight`，TXT/DOCX 下载前先返回缺章、未定稿、空版本和可导出字数，前端直接展示具体问题。
- 章节候选版本选择、删除、评审、优化改为 `version_id` 优先；没有稳定 ID 时才发送 `version_index`。
- `GenerationRuntimeEvent` 支持 `developer_detail`，日志页会把它折进“开发者详情”，不污染用户看的生成状态摘要。
- 文风画像生成新增 `/style/profiles/start/status/cancel` 后台任务入口；前端 `OptimizerAPI.createStyleProfile()` 改为启动任务并轮询状态，失败、取消、超时都有可读提示。
- 旧稿导入新增 `/import/start/status/cancel` 后台任务入口；前端 `NovelAPI.importNovel()` 改为启动任务并轮询状态，后端在读取、分章、采样、角色筛选、蓝图抽取和保存阶段回报进度。
- 章节大纲重写新增 `/rewrite-outline/start/status/cancel` 后台任务入口；前端 `rewriteChapterOutline()` 改为后台任务轮询，和章节大纲生成共用 outline 任务状态模型。

## 自动化验证

- `python -m compileall backend/app`：通过。
- `python -m pytest backend/app/services/test_generation_quality_guards.py -q`：57 passed。
- `python -m pytest backend -q`：242 passed。
- `cd frontend; npm run test:run`：124 passed。
- `cd frontend; npm run build`：通过。
- `python -m pytest backend/app/api/routers/test_blueprint_legacy_route.py backend/app/api/routers/test_outline_generation_job.py -q`：3 passed。
- `python -m pytest backend/app/services/test_export_service.py -q`：4 passed。
- `cd frontend; npm run test:run -- src/api/modules/chapterWorkflow.spec.ts`：5 passed。
- `python -m pytest backend/app/api/routers/test_style_profile_job.py -q`：1 passed。
- `python -m pytest backend/app/api/routers/test_import_novel_job.py backend/app/services/test_daily_limit_scopes.py::test_import_service_scope_reuses_outer_logical_run -q`：2 passed。
- `cd frontend; npm run test:run -- src/api/novel.spec.ts`：4 passed。

## 项目本体启动验证

- 后端：`http://127.0.0.1:8013/api/health` 返回 `{"status":"healthy","app":"玄穹文枢 API","version":"1.0.0"}`。
- 前端：`http://127.0.0.1:5174/` 返回 HTTP 200。
- CPA：`http://localhost:8317/` 当前仅作为 Provider 端点，不作为应用本体。
- 本地 web-validation 技能脚本目录缺失，且前端依赖中未安装 Playwright；本轮完成 HTTP 级页面可达性验证，未声明已完成截图级浏览器验证。
- 当前本地已有项目与 runtime 日志可通过 API 读取；历史数据库中部分旧项目标题存在旧编码痕迹，本轮不做历史数据迁移。

## 多视角评判转代码

- 作者视角：旧同步蓝图和章节大纲入口会让长任务卡在请求里，已改为前端旧方法也走后台任务。
- 编辑视角：候选版本按 index 操作有错位风险，已改为稳定 `version_id` 优先。
- 读者视角：日志应先看生成状态，不应被原始调试字段淹没，已新增 `developer_detail` 分层。
- 连续性审校视角：不改变现有局部补丁/锚点逻辑，只补可观测性和版本选择准确性。
- 系统稳定性视角：旧同步后端路由暂不删除，先 deprecated/兼容转发，避免破坏外部旧客户端。
- UI 可用性视角：本轮未大改布局，只把会影响操作稳定性的入口与日志字段先收口。
- 风格工作流视角：画像生成原本可能被长素材和 LLM 抽取卡在同步请求中，已改为后台任务，下一步需要把素材导入本身也拆成可观察批次。
- 导入工作流视角：旧稿导入原本把分章、角色普查、蓝图抽取、保存全塞进同步请求，已改为可轮询任务；下一步要把导入后的账本重建阶段继续接细。
- 章节大纲视角：重写章节大纲原本仍是同步调用，现已接入 outline 任务状态；取消态优先，避免用户取消后后台又覆盖状态。

## 保留风险

- 尚未完成 2-3 轮完整 AI 生成实跑；本轮完成了项目本体健康检查、自动化测试和接口级验证。
- 风格画像生成、旧稿导入、章节大纲生成/重写均已任务化；风格素材导入、导入后账本重建仍是下一批 P1。章节大纲还需要把质量门和锚点解释写进更细粒度进度事件。
- 历史数据库旧数据存在乱码样本，需要单独做数据清理/迁移，不能混进本轮代码重构。

## 2026-05-21 工作区导入进度补充

- `NovelWorkspace.vue` 新增旧稿导入浮动进度条，直接展示后端 `progress_message`，用户能看到读取、分章、采样、角色筛选、蓝图抽取、保存等阶段。
- 导入取消改为调用 `/api/novels/import/{run_id}/cancel`；如果后端进入保存等不可取消阶段，前端不再假装已取消，而是继续展示真实任务状态。
- 前端验证：`cd frontend; npm run test:run` 通过，`cd frontend; npm run build` 通过，`git diff --check` 仅提示 Windows 工作区换行将被 Git 规范化。

## 2026-05-21 文风素材上传任务化补充

- `style.py` 新增 `/style/sources/upload/start/status/{run_id}/cancel` 任务链路，上传大文件时会展示读取、正文抽取、保存素材库等阶段；旧 `/sources/upload` 保留 deprecated 兼容。
- `StyleCenterView.vue` 的文件素材导入改为轮询后台任务，进度条显示后端 `progress_message`，并提供取消按钮；保存阶段不可安全取消时会继续展示真实状态。
- 定向验证：`python -m pytest backend/app/api/routers/test_style_profile_job.py -q` 通过，`python -m compileall backend/app/api/routers/style.py` 通过，`cd frontend; npm run test:run -- src/api/novel.spec.ts` 通过。
- 全量验证：`python -m pytest backend -q` 通过（244 passed），`cd frontend; npm run test:run` 通过（125 passed），`cd frontend; npm run build` 通过；`git diff --check` 仅提示工作区换行规范化。

## 2026-05-21 旧稿导入账本重建补充

- `ImportService` 在旧稿导入保存章节后新增 `import_ledger_rebuild` 阶段，基于导入蓝图和章节内容建立项目记忆、章节快照、角色初始状态、时间线事件，并调用 `KnowledgeGraphService.sync_from_story_memory()` 同步知识图谱。
- 导入任务取消保护扩展到 `import_ledger_rebuild`，进入保存/账本重建后不再中途取消，避免写一半造成账本缺口。
- 定向验证：`python -m pytest backend/app/services/test_daily_limit_scopes.py::test_import_service_scope_reuses_outer_logical_run backend/app/api/routers/test_import_novel_job.py -q` 通过，`python -m compileall backend/app/services/import_service.py backend/app/api/routers/novels.py` 通过，`cd frontend; npm run test:run -- src/api/novel.spec.ts` 通过。
- 全量验证：`python -m pytest backend -q` 通过（245 passed），`cd frontend; npm run test:run` 通过（125 passed），`cd frontend; npm run build` 通过；`git diff --check` 仅提示工作区换行规范化。

## 2026-05-21 旧稿导入伏笔/线索闭环验证
- 代码收口：`ImportService._rebuild_import_ledgers()` 现在把导入蓝图里的 `foreshadowing_system` 落成 `Foreshadowing`，再同步到 `StoryClue`，并在导入完成 metrics 中返回 `foreshadowing_count` 与 `clue_tracker`。
- 自动化验证：`python -m pytest backend/app/services/test_import_service.py backend/app/api/routers/test_import_novel_job.py -q` 通过，覆盖导入任务取消保护和旧稿账本重建后伏笔/线索实体存在。
- 编译验证：`python -m compileall backend/app/services/import_service.py backend/app/services/test_import_service.py` 通过。
- 后端全量验证：`python -m pytest backend -q` 通过（246 passed），`python -m compileall backend/app` 通过。
