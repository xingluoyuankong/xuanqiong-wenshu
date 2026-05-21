# 玄穹文枢全功能缺陷地图与重构台账（2026-05-21）

## 本轮基线

- 工作目录：`D:\小说写作\xuanqiong-wenshu`
- 分支：`codex/final-continuity-20260520`
- 当前工作基线：`64e22fc feat: audit full product generation paths` 之后继续推进。
- 代码规模：后端 Python 约 153 文件 / 57626 行；前端 Vue 约 99 文件 / 27626 行；前端 TS 约 56 文件 / 8489 行。
- 未纳入提交：`CLAUDE.md`、`memory/`、2026-04/05 的旧未跟踪报告与 `托管优化计划-2026-04-28.txt`。

## 外部方法参考

只吸收方法，不复制实现：

- novelWriter：项目树、文档类型、状态标签、元数据索引适合借鉴为“章节/设定/笔记/任务”统一导航。
- Manuskript：人物、情节、世界、场景、Snowflake 式逐层细化，适合借鉴到蓝图/章节大纲的职责拆分。
- bibisco：角色深描、地点、物品、章节/场景管理，适合补强角色池、势力、场景账本。
- Novel Engine / agent pipeline：阶段门、任务产物、恢复点，适合蓝图、章节、风格学习、导入导出后台任务。
- GOAT Storytelling Agent / autonovel：foundation -> plan -> draft -> review 循环，适合首稿质量门和候选回退。
- graphify-novel / StoryWriter：Story Bible 与知识图谱双层状态、事件大纲、历史压缩，适合长期连续性和伏笔回收。

## 功能地图与缺陷台账

| 功能 | 入口 | 当前状态 | 缺陷 | 影响 | 修复策略 | 验证 | 优先级 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 概念对话 | `InspirationMode.vue` -> `/concept/converse` | active | 对话状态和蓝图生成状态分离，失败后恢复提示仍偏散 | 用户不知道当前能否继续生成 | 保留现入口，增加阶段摘要、可恢复任务提示 | 灵感模式实跑、Vitest | P1 |
| 蓝图/总纲生成 | `BlueprintConfirmation.vue` -> `/blueprint/generate/start/status/cancel` | active | 前端 store/API 仍保留旧同步 `generateBlueprint()` | 旧调用可绕开后台进度和取消 | 旧前端 API 改为后台任务轮询；后端旧路由标记 legacy | 前端测试、接口实跑 | P0 |
| 旧蓝图同步路由 | `/blueprint/generate` | legacy | 已改为兼容转发后台任务，不再同步执行完整生成 | 外部旧客户端需适配任务响应 | 保留 Deprecation/Link 响应头，继续观察外部兼容 | 路由回归测试 | P1 |
| 章节大纲生成/重写 | `/writer/chapters/outline`、`outline/start/status/cancel`、`rewrite-outline/start/status/cancel` | active | 生成和重写都已任务化；下一步要把重写质量门细节写进更清晰 runtime events | 大纲生成/重写不再卡前端长请求 | 继续补重写前后锚点、伏笔任务和质量门解释的 UI 展示 | 后端测试、UI 轮询 | P1 |
| 正文生成 | `PipelineOrchestrator` | active | 首稿质量门已加强，长章 Provider 等待仍需更多真实样本 | 长章体验受 Provider 抖动影响 | 继续记录 heartbeat、软超时、降 token 重试和内容预览 | 7000-10000 字实跑 | P0 |
| 正文重写/优化 | `optimizer.py`、`self_critique_service.py`、`consistency_service.py` | active | 自动流程已局部化，但前端仍需更清楚解释拒稿原因 | 用户误以为优化失败或没效果 | 详细日志展示锚点、补丁建议、拒绝原因 | 优化实跑、日志页验证 | P0 |
| 候选版本选择/删除/评审 | `chapterWorkflow.ts`、`writer.py` | active | 前端仍同时发送 `version_index` 与 `version_id` | 删除/评审可能因排序变化错位 | 前端有 `version_id` 时只发送 `version_id`，index 仅兜底 | WriterDesk Vitest | P0 |
| 候选版本优化 | `OptimizerAPI.optimizeChapter` | active | store 总是发送 index 和 id | 同上 | store 构造稳定版本选择 payload | Store/API 测试 | P0 |
| 定稿与账本更新 | `/chapters/{n}/finalize`、`FinalizeService` | active | 角色/伏笔/图谱闭环已接入，失败详情还可更用户化 | 写后闭环失败难解释 | runtime event 增加账本更新统计和失败建议 | 章节定稿实跑 | P1 |
| 角色/势力 | 蓝图、`projects.py`、`faction_service.py` | active | 角色规模和势力关系已有补强，但 UI 缺“生命周期视图” | 长篇角色易失控 | 故事账本侧栏展示登场/退出/回归/状态 | 浏览器验证 | P1 |
| 伏笔/线索 | `foreshadowing.py`、`clue_tracker.py` | active | 回收任务已进写作链路，但 UI 未形成“逾期/下章必须处理”工作流 | 伏笔沉默遗忘 | 伏笔页增加待回收、逾期、补丁建议分组 | 后端与浏览器测试 | P1 |
| 记忆层 | `memory_layer_service.py`、`projects.py` | active | 压缩/回滚入口存在，用户不易知道压缩影响 | 长篇记忆治理不透明 | 管理页展示版本、压缩原因、回滚风险 | 单测、UI 验证 | P2 |
| 知识图谱 | `knowledge_graph.py`、图谱组件 | active | 同步来自蓝图/记忆，但“事实源 vs 关系查询”边界不显性 | 用户误把图谱当全文事实库 | UI 标注事实源、最新章节、关系置信度 | 图谱页验证 | P1 |
| 风格中心 | `StyleCenterView.vue`、`style_rag_service.py`、`/style/profiles/start/status/cancel`、`/style/sources/upload/start/status/cancel` | active | 文风画像生成和文件素材上传都已改为后台任务；超大素材仍需继续按批次规划学习 | 画像生成和大文件抽取不再卡住一次 HTTP 请求，用户能看到读取、抽取、保存阶段 | 继续把多批次学习建议和画像任务的结果、失败根因接入 UI 日志 | 风格画像/素材上传任务测试、风格学习实跑 | P1 |
| 导入 | `NovelWorkspace.vue`、`import_service.py`、`/import/start/status/cancel` | active | 旧稿导入已改为后台任务；导入后会进入 `import_ledger_rebuild` 阶段，重建项目记忆、章节快照、角色初始状态、时间线和知识图谱 | 文件读取、分章、角色普查、蓝图抽取、保存、账本重建不再沉默卡住一次 HTTP 请求 | 继续补伏笔/线索实体入库和旧稿导入实跑样本 | 导入任务测试、旧稿导入实跑 | P1 |
| 导出 | `/export/preflight`、`/export/txt`、`/export/docx`、`ExportService` | active | 已有导出硬校验，新增预检可展示缺章/未定稿/空章原因 | 还可继续补修复入口跳转 | 预检报告先阻止无效下载，并提示缺失章节 | 导出测试、构建 | P2 |
| Token 预算 | `token_budget.py` | active | 配置和统计存在，但 LLM 调用侧预算事件仍需统一 | 用户难判断花费来源 | `generation_call_service` 记录模块/阶段 usage | 单测 | P2 |
| LLM 设置 | `llm_config.py`、设置页 | active | 健康检查与最近失败归因没有聚合到生成日志 | Provider 抖动难复盘 | 设置页显示最近错误、Retry-After、模型/base_url | 手动验证 | P2 |
| 管理台日志 | `RuntimeLogManagement.vue`、`admin.py` | active | 已能看生成状态，但程序日志/生成状态边界仍需继续分层 | 用户被开发细节干扰 | 用户态默认显示内容/质量/账本，开发者详情折叠 | 管理台验证 | P1 |
| 全文阅读 | `NovelFullReaderView.vue` | active | 只读体验存在，导出/回到章节定位联动弱 | 审阅长文效率低 | 加章节目录、当前章节定位、导出入口 | 浏览器验证 | P2 |
| 提示词管理 | `admin.py` prompts | active | 缺少“影响哪些生成阶段”的可视化 | 改提示词风险高 | 提示词绑定阶段标签和最近使用记录 | 管理台测试 | P2 |
| 历史终极写作流 | `ultimate_writing_flow.py` | legacy | 像第二套小说引擎，仅测试引用直接生成契约 | 架构认知混乱 | 保留契约测试，标记 legacy；活跃生成只走 `PipelineOrchestrator` | `rg` 和测试 | P1 |

## 第一批已执行的收口

- 前端旧 `NovelAPI.generateBlueprint()` 已改为启动 `/blueprint/generate/start` 并轮询 `/status`，保留旧方法签名但不再绕过后台任务。
- 后端旧 `/blueprint/generate` 已改为兼容转发后台任务，旧调用也不再绕过进度、取消和状态模型。
- 章节大纲生成新增后台任务入口，前端旧 `generateChapterOutline()` 已改为启动 `/chapters/outline/start` 并轮询 `/status`。
- 导出新增 `/export/preflight`，前端下载全书前会展示缺章、未定稿、空正文和可导出字数，不再只报“导出失败”。
- `chapterWorkflow.ts` 版本选择/删除/评审改为有 `version_id` 时只发送稳定 ID，`version_index` 仅作为旧数据兜底。
- `novel.ts` store 的优化入口改为有 `version_id` 时只发送稳定 ID，避免排序变化导致优化错版本。
- 文风画像生成新增 `/style/profiles/start/status/cancel` 后台任务入口，前端旧 `createStyleProfile()` 已改为启动任务并轮询，不再让大素材画像生成阻塞一次 HTTP 请求。
- 文风素材文件上传新增 `/style/sources/upload/start/status/{run_id}/cancel` 后台任务入口，前端文风中心显示真实上传/抽取/保存阶段并允许取消；旧 `/sources/upload` 保留 deprecated 兼容。
- 旧稿导入新增 `/import/start/status/cancel` 后台任务入口，前端旧 `importNovel()` 已改为启动任务并轮询；导入阶段会回报读取、分章、采样、角色筛选、蓝图抽取和保存进度。
- 旧稿导入保存后新增 `import_ledger_rebuild` 阶段：基于导入蓝图和章节内容建立 ProjectMemory、ChapterSnapshot、CharacterState、TimelineEvent，并同步 KnowledgeGraph。
- 章节大纲重写新增 `/chapters/rewrite-outline/start/status/cancel` 后台任务入口，前端旧 `rewriteChapterOutline()` 已改为启动任务并轮询，不再让局部重写卡在同步请求里。

## 下一批执行顺序

1. 补旧稿导入后的伏笔/线索实体入库，并继续完善风格中心多批次学习建议。
2. 继续把日志页默认视图收敛到“生成状态”，开发者字段折叠。
3. 补 Provider 健康归因与 Token 预算事件。
4. 跑项目本体浏览器验证、完整实跑和反向修正。

## 2026-05-21 继续收口：旧稿导入伏笔/线索入库
- `ImportService._rebuild_import_ledgers()` 不再只把导入蓝图里的 `foreshadowing_system` 写进 `ProjectMemory.plot_arcs`，现在会复用现有 `Foreshadowing` 模型创建实体，并立即调用 `ClueTrackerService.sync_from_foreshadowings()` 同步到 `StoryClue`。
- 修复影响：旧稿导入后，伏笔页、线索页、长上下文包、后续章节任务都能读到导入文本里的 setup/payoff，不会出现“记忆里有摘要，但伏笔账本为空”的断链。
- 去重策略：按导入章节、伏笔名和内容摘要去重，避免账本重建重复插入。
- 验证：新增 `backend/app/services/test_import_service.py`，覆盖旧稿导入账本重建后同时产生 `Foreshadowing`、`StoryClue`、`ProjectMemory` 和 `ChapterSnapshot`。

## 2026-05-21 继续收口：生成调用指标进入候选 metadata
- `generation_call_service.py` 的 `GenerationTextResult/GenerationJsonResult` 新增本地估算的输入/输出/总 token、prompt/输出字符数、最终生效 `max_tokens` 和最近一次 Provider 错误归因。
- `PipelineOrchestrator` 在正文候选 metadata 写入 `generation_call_metrics`，后续详细日志、候选版本解释、预算页可以直接展示“尝试次数、是否因限额/超时降级、估算消耗”。
- 修复影响：Provider 抖动或模型拒绝过高 `max_tokens` 后，即使最终成功，候选版本 metadata 也不会丢掉这段降级历史。
