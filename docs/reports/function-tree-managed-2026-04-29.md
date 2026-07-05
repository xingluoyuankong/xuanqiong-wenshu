# ???????????????2026-04-29?

## 1. ?????
- AboutView (`frontend\src\views\AboutView.vue`)
- AdminNovelDetail (`frontend\src\views\AdminNovelDetail.vue`)
- AdminView (`frontend\src\views\AdminView.vue`)
  - route: `/admin` / `admin`
  - route: `/admin/novel/:id` / `admin-novel-detail`
- HomeView (`frontend\src\views\HomeView.vue`)
- InspirationMode (`frontend\src\views\InspirationMode.vue`)
- NovelDetail (`frontend\src\views\NovelDetail.vue`)
- NovelFullReaderView (`frontend\src\views\NovelFullReaderView.vue`)
- NovelWorkspace (`frontend\src\views\NovelWorkspace.vue`)
- SettingsView (`frontend\src\views\SettingsView.vue`)
  - route: `/settings` / `settings`
  - route: `/llm-settings` / `llm-settings`
- StyleCenterView (`frontend\src\views\StyleCenterView.vue`)
- SystemSettingsView (`frontend\src\views\SystemSettingsView.vue`)
- WorkspaceEntry (`frontend\src\views\WorkspaceEntry.vue`)
- WritingDesk (`frontend\src\views\WritingDesk.vue`)

## 2. ????????????/??/???
- `BlueprintCard.vue`
- `BlueprintConfirmation.vue`
- `BlueprintDisplay.vue`
- `BlueprintEditModal.vue`
- `GlobalNavBar.vue`
- `InspirationLoading.vue`
- `writing-desk\dialogs\WDEditChapterModal.vue`
- `writing-desk\dialogs\WDEvaluationDetailModal.vue`
- `writing-desk\dialogs\WDEvolveOutlineModal.vue`
- `writing-desk\dialogs\WDGenerateChapterModal.vue`
- `writing-desk\dialogs\WDGenerateOutlineModal.vue`
- `writing-desk\dialogs\WDMemoryManageModal.vue`
- `writing-desk\dialogs\WDPatchDiffModal.vue`
- `writing-desk\dialogs\WDSkillSelectorModal.vue`
- `writing-desk\dialogs\WDStyleExtractModal.vue`
- `writing-desk\dialogs\WDTextReaderModal.vue`
- `writing-desk\dialogs\WDTokenBudgetModal.vue`
- `writing-desk\dialogs\WDVersionDetailModal.vue`
- `writing-desk\dialogs\WDVersionDiffModal.vue`
- `writing-desk\layout\WDHeader.vue`
- `writing-desk\layout\WDSidebar.vue`
- `writing-desk\layout\WDWorkspace.vue`
- `writing-desk\workspace\content\ChapterContent.vue`
- `writing-desk\workspace\review\VersionSelector.vue`
- `writing-desk\workspace\states\ChapterEmpty.vue`
- `writing-desk\workspace\states\ChapterFailed.vue`
- `writing-desk\workspace\states\ChapterGenerating.vue`
- `writing-desk\workspace\states\WorkspaceInitial.vue`

## 3. ?? API ?
- admin.py
  - GET `/stats`
  - GET `/diagnostics/root-cause`
  - GET `/novel-projects`
  - GET `/novel-projects/{project_id}`
  - GET `/novel-projects/{project_id}/sections/{section}`
  - GET `/novel-projects/{project_id}/chapters/{chapter_number}`
  - GET `/runtime-logs`
  - GET `/prompts`
  - POST `/prompts`
  - GET `/prompts/{prompt_id}`
  - PATCH `/prompts/{prompt_id}`
  - DELETE `/prompts/{prompt_id}`
  - GET `/update-logs`
  - POST `/update-logs`
  - DELETE `/update-logs/{log_id}`
  - PATCH `/update-logs/{log_id}`
  - GET `/settings/daily-request-limit`
  - PUT `/settings/daily-request-limit`
  - GET `/system-configs`
  - GET `/system-configs/{key}`
  - PUT `/system-configs/{key}`
  - PATCH `/system-configs/{key}`
  - DELETE `/system-configs/{key}`
- analytics.py
  - GET `/{project_id}/emotion-curve`
  - GET `/{project_id}/foreshadowing`
  - POST `/{project_id}/analyze-emotion-ai`
- analytics_enhanced.py
  - GET `/projects/{project_id}/emotion-curve-enhanced`
  - GET `/projects/{project_id}/story-trajectory`
  - GET `/projects/{project_id}/creative-guidance`
  - GET `/projects/{project_id}/comprehensive-analysis`
  - POST `/projects/{project_id}/invalidate-cache`
- clue_tracker.py
  - POST `/{project_id}/clues`
  - GET `/{project_id}/clues`
  - GET `/{project_id}/clues/threads`
  - GET `/{project_id}/clues/red-herring`
  - GET `/{project_id}/clues/unresolved`
  - GET `/{project_id}/clues/{clue_id}`
  - PUT `/{project_id}/clues/{clue_id}`
  - DELETE `/{project_id}/clues/{clue_id}`
  - POST `/{project_id}/clues/{clue_id}/link-chapter`
  - GET `/{project_id}/clues/{clue_id}/timeline`
- foreshadowing.py
  - POST `/{project_id}/foreshadowings`
  - GET `/{project_id}/foreshadowings`
  - POST `/{project_id}/foreshadowings/{foreshadowing_id}/resolve`
  - GET `/{project_id}/foreshadowings/reminders`
  - POST `/{project_id}/foreshadowings/reminders/{reminder_id}/dismiss`
  - GET `/{project_id}/foreshadowings/analysis`
- knowledge_graph.py
  - POST `/{project_id}/knowledge-graph/nodes`
  - GET `/{project_id}/knowledge-graph/nodes`
  - PUT `/{project_id}/knowledge-graph/nodes/{node_id}`
  - DELETE `/{project_id}/knowledge-graph/nodes/{node_id}`
  - POST `/{project_id}/knowledge-graph/edges`
  - GET `/{project_id}/knowledge-graph/edges`
  - DELETE `/{project_id}/knowledge-graph/edges/{edge_id}`
  - GET `/{project_id}/knowledge-graph`
  - GET `/{project_id}/knowledge-graph/character/{character_id}/timeline`
  - GET `/{project_id}/knowledge-graph/connected/{character_id}`
  - GET `/{project_id}/knowledge-graph/threads`
  - GET `/{project_id}/knowledge-graph/export`
- llm_config.py
  - POST `/models`
  - GET `/source-trace`
  - GET `/health-check`
  - POST `/auto-switch`
- novels.py
  - POST `/import`
  - GET `/current-user`
  - GET `/{project_id}`
  - GET `/{project_id}/sections/{section}`
  - GET `/{project_id}/chapters/{chapter_number}`
  - GET `/{project_id}/export/txt`
  - GET `/{project_id}/export/docx`
  - POST `/{project_id}/concept/converse`
  - POST `/{project_id}/blueprint/generate/start`
  - GET `/{project_id}/blueprint/generate/status`
  - POST `/{project_id}/blueprint/generate/cancel`
  - POST `/{project_id}/blueprint/generate`
  - POST `/{project_id}/blueprint/save`
  - PATCH `/{project_id}/blueprint`
- optimizer.py
  - POST `/optimize`
  - POST `/apply-optimization`
- outline.py
  - POST `/evolve`
  - POST `/next`
  - GET `/alternatives`
  - GET `/history`
- patch_diff.py
  - POST `/projects/{project_id}/chapters/{chapter_number}/patch/apply`
  - POST `/projects/{project_id}/chapters/{chapter_number}/diff`
  - GET `/projects/{project_id}/chapters/{chapter_number}/versions/{v1}/vs/{v2}`
  - GET `/projects/{project_id}/chapters/{chapter_number}/patch/history`
  - POST `/projects/{project_id}/chapters/{chapter_number}/patch/revert`
- projects.py
  - GET `/{project_id}/constitution`
  - PUT `/{project_id}/constitution`
  - GET `/{project_id}/persona`
  - PUT `/{project_id}/persona`
  - GET `/{project_id}/memory`
  - PUT `/{project_id}/memory`
  - POST `/{project_id}/memory/incremental`
  - GET `/{project_id}/memory/snapshots`
  - POST `/{project_id}/memory/compress`
  - POST `/{project_id}/memory/rollback`
  - GET `/{project_id}/characters/state`
  - GET `/{project_id}/factions`
  - PUT `/{project_id}/factions`
- review.py
  - POST `/six-dimension`
  - POST `/consistency`
- style.py
  - GET `/sources`
  - GET `/library`
  - POST `/sources`
  - DELETE `/sources/{source_id}`
  - POST `/sources/upload`
  - GET `/profiles`
  - POST `/profiles`
  - PATCH `/profiles/{profile_id}`
  - GET `/active`
  - POST `/apply`
  - DELETE `/active`
  - POST `/extract`
  - POST `/generate`
- token_budget.py
  - GET `/{project_id}/token-budget`
  - PUT `/{project_id}/token-budget`
  - POST `/{project_id}/token-budget/usage`
  - GET `/{project_id}/token-budget/usage`
  - GET `/{project_id}/token-budget/usage-by-module`
  - GET `/{project_id}/token-budget/alerts`
  - POST `/{project_id}/token-budget/alerts/{alert_id}/resolve`
  - POST `/{project_id}/token-budget/allocate`
- updates.py
  - GET `/latest`
- writer.py
  - POST `/advanced/generate`
  - POST `/chapters/{chapter_number}/finalize`
  - POST `/novels/{project_id}/chapters/generate`
  - POST `/novels/{project_id}/chapters/cancel`
  - GET `/novels/{project_id}/chapters/{chapter_number}/status`
  - POST `/novels/{project_id}/chapters/select`
  - POST `/novels/{project_id}/chapters/delete-version`
  - POST `/novels/{project_id}/chapters/evaluate`
  - POST `/novels/{project_id}/chapters/update-outline`
  - POST `/novels/{project_id}/chapters/rewrite-outline`
  - POST `/novels/{project_id}/chapters/delete`
  - POST `/novels/{project_id}/chapters/outline`
  - POST `/novels/{project_id}/chapters/edit`
  - POST `/novels/{project_id}/chapters/edit-fast`
- writing_skills.py
  - GET `/skills`
  - GET `/skills/catalog`
  - GET `/skills/{skill_id}`
  - POST `/skills/{skill_id}/install`
  - DELETE `/skills/{skill_id}/uninstall`
  - POST `/skills/{skill_id}/execute`

## 4. ????????
- ???????/?????????ready_for_blueprint ????????
- ???????? start/status/cancel ???????????????/???????
- ????????????????????????? 3000?stale runtime ????
- ????????????????????? generation_runtime???? cancel/status ???
- ???????????????????????????

## 5. ??????
- ?? pytest?11 passed?
- ?? vitest?9 files / 65 tests passed?
- ?? build????
- dev-smoke?health/frontend/create/status/screenshot ???
## 追加：2026-04-29 07:33 功能树对齐更新

- 写作桌面 / 工作区 / 项目健康检查
  - 大纲数量：读取 `project.blueprint.chapter_outline`
  - 章节数量：读取 `project.chapters`
  - 候选版本数量：聚合 `chapter.versions`
  - 可导出章节：`generation_status=successful` 且有正文
  - 导出阻断：非成功状态或正文为空
  - 处理中：`generating/evaluating/selecting/waiting_for_confirm`
- 导出服务 / TXT-DOCX
  - 导出前硬校验：章节必须 successful、必须有 selected_version、选中正文必须非空
  - 失败响应：HTTP 409，结构化 `code=novel_export_not_ready` 与 issues 列表
- 生成资产审计
  - `tools/audit_generated_novels.py`：扫描 SQLite 与 output JSON，输出 Markdown/JSON
  - `tools/repair_generation_state.py`：备份后修复历史 stale 状态与 selected_version 断链

## 追加：2026-04-29 07:45 写作桌面状态组件

- 写作桌面 / 章节空态
  - 展示章节号视觉标识
  - 展示“确认前文 → 生成本章 → 评审确认”三步路径
  - 支持顺序锁保护说明
  - 可生成时触发 `generateChapter(chapterNumber)`
- 写作桌面 / 章节失败态
  - 展示异常恢复说明
  - 明确“先确认 / 再恢复 / 导出保护”
  - 失败章节不再被 UI 暗示为可正常交付
  - 支持重试生成，重试中按钮禁用

## 追加：2026-04-29 20:41 正文/候选/E2E/环境

- 写作桌面 / 正文内容区
  - 正文健康检查：正文状态、段落数、预览比例、精修队列
  - 正文阅读：更清晰的卡片层次、可交付提示、导出/精修入口
- 写作桌面 / 候选版本区
  - 决策辅助：候选版本数、已评审、当前正文、平均字数
  - 候选卡片：选中态、当前正文态、对比对象、删除/评审/查看全文
- E2E
  - `tools/e2e-inspiration-to-export.ps1`
  - 链路：创建项目 → 保存蓝图 → 写入章节 → 打开写作桌面 → 校验健康面板 → 导出 TXT
- MySQL / 测试隔离
  - 正式 MySQL 3309 可连接
  - smoke/E2E 使用 SQLite 隔离库，避免污染正式数据
- 历史内容修复
  - `tools/repair_export_blockers.py`
  - 剩余导出阻断章节已恢复为可读人工恢复稿，导出阻断归零

# 2026-04-29 21:08 功能树增量：写作桌面弹窗与验证链路

```text
玄穹文枢
├─ 灵感模式到导出主链路
│  ├─ 灵感问答：首轮创建/继续对话/失败保留历史
│  ├─ 蓝图生成：后台任务 start/status/cancel/failed/stale
│  ├─ 蓝图确认：保存大纲/进入写作桌面/错误结构化展示
│  ├─ 写作桌面：章节导航/正文健康/项目健康/候选版本/导出入口
│  └─ 导出：TXT/DOCX 前置硬校验；失败/空正文/无选中版本均 409 阻断
├─ 写作桌面弹窗系统
│  ├─ 已结构化重构
│  │  ├─ 编辑章节弹窗：标题/摘要/AI 重写方向/保存
│  │  ├─ 生成大纲弹窗：后续章节数量/全书目标/单章字数/生成
│  │  ├─ 剧情推演弹窗：候选走向/应用演进
│  │  ├─ Token 预算弹窗：预算状态/模块消耗/风险提示
│  │  ├─ 记忆管理弹窗：快照/压缩/回滚/更新
│  │  └─ 文风学习弹窗：章节学习/外部文本/风格档案
│  ├─ 已完成视觉统一，待结构级重构
│  │  ├─ 生成章节弹窗：方向/质量/字数/预设/高级策略
│  │  ├─ 版本详情弹窗：正文/自评/一致性/优化链路
│  │  ├─ 评估详情弹窗：评分/问题/修复建议
│  │  ├─ 版本 diff 弹窗：左右版本差异
│  │  ├─ patch diff 弹窗：补丁差异与应用说明
│  │  ├─ 技能选择弹窗：生成技能组合
│  │  └─ 文本阅读弹窗：沉浸阅读/复制/关闭
│  └─ 全局设计系统
│     ├─ xq-dialog-overlay：统一遮罩与背景氛围
│     ├─ xq-dialog-shell：玻璃拟态卡片和尺寸规范
│     ├─ xq-dialog-header/body/footer：标题、滚动正文、操作区
│     ├─ xq-field-panel：输入配置区
│     └─ xq-soft-grid：柔和网格背景
├─ 数据与环境治理
│  ├─ SQLite 隔离烟测库：dev-smoke/e2e 使用，不污染正式 MySQL
│  ├─ MySQL 正式环境：3309 可连接；select 1 通过
│  ├─ 生成状态修复：stale generating/waiting/evaluating 已闭环
│  └─ 导出阻断修复：失败/空正文/未绑定版本清零
└─ 当前测试证据
   ├─ 前端单测：11 files / 69 tests passed
   ├─ 后端单测：14 passed
   ├─ 前端构建：vue-tsc + vite build passed
   ├─ 浏览器烟测：home 200，无乱码，无 console error
   └─ Playwright E2E：创建项目 -> 保存蓝图 -> 写入章节 -> 写作桌面健康检查 -> TXT 导出 200
```

# 2026-04-29 21:44 功能树增量：弹窗验证与管理页面视觉系统

```text
写作桌面弹窗验证矩阵
├─ version-detail：版本详情 / 生成链路摘要 / 正文阅读 / 选用版本
├─ evaluation-detail：AI 综合评审 / 推荐版本 / 优点 / 缺点 / 修复建议
├─ version-diff：候选版本只读差异 / 新增 / 删除 / 修改 / 未变统计
├─ patch-diff：原文与修改稿行级差异 / 编辑区 / diff 预览 / 应用入口
├─ skill-selector：技能编排台 / 技能目录 / 执行说明 / 结果区
├─ reader：沉浸阅读面 / 完整正文 / 字数 / 返回写作台
├─ generate-chapter：生成章节 / 写作方向 / 质量偏好 / 字数预算 / 配置保存
├─ edit-chapter：编辑章节大纲 / 标题 / 摘要 / 重写方向
└─ generate-outline：生成后续大纲 / 章节数 / 全书目标 / 单章目标

页面视觉系统增量
├─ 管理后台：侧栏、顶部、内容滚动区进入玻璃拟态和渐变背景体系
├─ 设置/LLM：配置工作台卡片、按钮、section 统一高级视觉
├─ 知识图谱：页面级背景、卡片、统计区统一
├─ 线索追踪：页面级背景、线索卡片、统计区统一
└─ 风格中心：外部文风学习台、流程卡、摘要卡统一高级视觉

验证证据
├─ e2e-writing-desk-dialogs-2026-04-29-214144.json：9/9 探针通过
├─ e2e-inspiration-to-export-2026-04-29-214354.json：灵感到导出通过
├─ frontend-home-smoke-2026-04-29-214348.png：首页烟测截图
├─ frontend vitest：69 passed
└─ backend pytest：14 passed
```
