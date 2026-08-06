# 审计历史汇总

整合 2026-03 至 2026-08 全部审计报告。

---

### AI-Novel 代码审计报告
- 文件: `docs\reports\CODE_AUDIT_REPORT.md`
- 简况: 计结果  ### 1.1 已修复问题  | 问题 | 修复方案 | 状态 | |------|---------|------| | `outline.md` 与代码引用 `outline_generation` 不一致 | 重命名为 `outline_generation.md` | ✅ | | `editor_review.md` 未被代码调用 | 新增 `ai_review_service....

### 玄穹文枢代码审查报告
- 文件: `docs\reports\CODE_REVIEW_20260329.md`
- 简况: 问题 | 文件 | 行号 | 严重程度 | |------|------|------|---------| | 轮询计数器不重置 | `WDWorkspace.vue` | 514-527 | 中 | | `fetchUser` 错误处理不完整 | `auth.ts` | 148-183 | 中 | | `loadProject` 静默模式状态不一致 | `novel.ts` | 62-84 |...

### AI-Novel 深度优化功能报告
- 文件: `docs\reports\DEEP_OPTIMIZATION_REPORT.md`
- 简况: w` 服务中。  ---  ## 一、新增功能清单  ### 1. 记忆层架构（Memory Layer）  **解决的问题**：AI 无法主动追踪角色状态，导致角色"瞬移"、情绪断层、物品凭空出现等一致性问题。  **核心组件**：  | 组件 | 职责 | 文件 | |------|------|------| | 角色状态表 | 追踪每个角色在每章结束时的状态（位置、情绪、物品、关系等） |...

### AI小说创作增强功能集成报告
- 文件: `docs\reports\INTEGRATION_REPORT.md`
- 简况: 现有功能的前提下，增加了三大增强模块。  ## ✅ 已完成的集成  ### 1. 角色DNA档案系统 🧬  **功能描述**：为每个角色建立深层的"DNA档案"，让AI生成的角色更加立体、真实。  **八大维度**： | 维度 | 说明 | 示例 | |------|------|------| | 童年经历/创伤 | 角色人格形成的根基 | 父母离异后由祖母抚养，从小学会察言观色 | | 核心恐...

### Novel-Kit 功能融合报告
- 文件: `docs\reports\NOVEL_KIT_FUSION_REPORT.md`
- 简况: Kit 优势 | 融合后状态 | |----------|-------------|----------------|------------| | 创作规则 | 无 | 小说宪法系统 | ✅ 已实现 | | 文本风格 | 基础提示词 | Writer 人格系统 | ✅ 已实现 | | 质量审查 | 单维度评审 | 六维度审查 | ✅ 已实现 | | 伏笔管理 | 基础记录 | 状态追踪+提醒...

### 玄穹文枢项目优化报告
- 文件: `docs\reports\OPTIMIZATION_REPORT_20260329.md`
- 简况: 化前 | 优化后 | |------|--------|--------| | 总文件数（含依赖） | 34,803 | 29,895 | | 源代码文件 | 362 | 359 | | 日志文件 | 85 | 0 | | `__pycache__` 目录 | 490 | 0 | | `README.ai` 文件 | 37 | 0 |  ### 1.2 代码问题发现  通过三个并行代理的分析，发现...

### ﻿蓝图生成路径异步统一方案
- 文件: `docs\reports\blueprint-async-unification-plan-2026-05-01.md`
- 简况: erate` 仅保留为兼容或内部调试，不再由主 UI 直接调用。  ## 当前风险  - 前端存在同步旧路径和后台任务路径并存。 - 取消任务不能真正中断已进入的 LLM 调用。 - job 主状态在进程内，重启后恢复依赖 conversation_history system 记录。  ## 分阶段实施  ### 阶段 1：前端统一  1. InspirationMode 在 ready_for...

### 玄穹文枢剩余任务最终收口报告
- 文件: `docs\reports\final-closure-2026-05-21.md`
- 简况: ion runtime ledger loop`  ## 本轮结论  剩余收口任务已完成一轮可验证闭环：项目本体后端/前端可运行，章节 8 和章节 9 已完成真实生成、定稿和账本回写；长章压力样例完成；导入、导出、风格中心、管理台日志和核心页面完成验证；发现的真实问题已转成代码修正或记录为明确限制。  本轮没有新建平行小说引擎。继续沿用现有 `PipelineOrchestrator`、`gene...

### 玄穹文枢深度功能审计与前端完全重构计划
- 文件: `docs\reports\frontend-generation-audit-2026-04-28.md`
- 简况: http://127.0.0.1:8013`   原始实测记录：`docs/reports/deep-audit-raw-2026-04-28.json`（本地审计原始产物，默认不入库）  > 说明：本次不是只看代码。已在你启动前后端后对真实后端接口、数据库、日志、构建、测试、核心生成链路进行了实际测试。浏览器插件的 Codex IAB backend 当前未暴露可连接实例，因此本轮页面视觉验收未...

### ﻿玄穹文枢功能与生成能力深度审计报告（托管轮次）
- 文件: `docs\reports\full-function-generation-audit-2026-05-01.md`
- 简况: 。  ## 一、功能树  ```text 玄穹文枢 ├─ 创作入口 │  ├─ 首页 / 工作台入口 │  ├─ 项目工作台 │  ├─ 灵感模式 │  │  ├─ 创建项目 │  │  ├─ 概念对话 │  │  ├─ 会话恢复 │  │  ├─ AI 收束判断 │  │  ├─ 蓝图生成 start/status/cancel │  │  ├─ 蓝图确认 │  │  ├─ 蓝图保存 │  │...

### 玄穹文枢全功能缺陷地图与重构台账（2026-05-21）
- 文件: `docs\reports\full-product-function-map-2026-05-21.md`
- 简况: ity-20260520` - 当前工作基线：`64e22fc feat: audit full product generation paths` 之后继续推进。 - 代码规模：后端 Python 约 153 文件 / 57626 行；前端 Vue 约 99 文件 / 27626 行；前端 TS 约 56 文件 / 8489 行。 - 未纳入提交：`CLAUDE.md`、`memory/`、20...

### 玄穹文枢全功能重构验证记录（2026-05-21）
- 文件: `docs\reports\full-product-validation-2026-05-21.md`
- 简况: 21.md`。 - 旧前端 `NovelAPI.generateBlueprint()` 已改为后台任务轮询，不再直接调用同步 `/blueprint/generate`。 - 后端同步 `/blueprint/generate` 已标记 deprecated，并返回 `Deprecation`、`Link`、`X-Xuanqiong-Legacy-Route` 响应头。 - 后端同步 `/blu...

### ???????????????2026-04-29?
- 文件: `docs\reports\function-tree-managed-2026-04-29.md`
- 简况: velDetail (`frontend\src\views\AdminNovelDetail.vue`) - AdminView (`frontend\src\views\AdminView.vue`)   - route: `/admin` / `admin`   - route: `/admin/novel/:id` / `admin-novel-detail` - HomeView (`f...

### 已生成小说文学质量只读审计
- 文件: `docs\reports\generated-novel-literary-audit-2026-05-01.md`
- 简况: 有章节项目数：19 - 章节数：35 - 无选中版本章节：0 - 平均综合分：73.4 - 最低/最高综合分：37.7 / 85.2 ## 风险标记统计 - 大纲关键词覆盖偏低: 14 - 正文过短: 12 - 重复意象偏多: 8 - 疑似乱码: 6 - 占位/错误提示混入正文: 2 - 情节推进密度偏弱: 2  ## 项目均分最低样本 - ????_90fw7q：avg=37.7，章节=1，fl...

### 生成小说与输出资产深度审计报告（托管模式）
- 文件: `docs\reports\generated-novel-quality-audit-2026-04-29.md`
- 简况: arboris.db` - 输出目录：`D:\小说写作\xuanqiong-wenshu\output`  ## 1. 总览  | 指标 | 数量 | |---|---:| | 项目数 | 40 | | 章节大纲数 | 254 | | 章节数 | 35 | | 正文版本数 | 68 | | 存在问题的项目数 | 33 | | 失败章节 | 0 | | 卡在生成中章节 | 0 | | 空正文版本 |...

### 玄穹文枢生成/重写与工作台重构报告（2026-05-20）
- 文件: `docs\reports\generation-function-map-2026-05-20.md`
- 简况: es/prose 当作写前事实源分层注入，适合作为“长篇上下文包”的方法参考。参考：https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC - StoryLine：核心启发是 setup/payoff 伏笔闭环和 Validator，不照...

### 生成/重写质量重构实跑报告（2026-05-20）
- 文件: `docs\reports\generation-quality-rerun-2026-05-20.md`
- 简况: - OpenAI Structured Outputs：结构化输出应有 schema 约束和失败修复。 - OpenAI rate limit/backoff：429/瞬时失败需要退避、重试和 token 上限控制。 - Chapter.pub 章节长度参考：常见章节约 1500-5000 词，幻想类可更长，关键是篇幅服务节奏。 - Story Planner scene/sequel：场景应...

### 生成/重写质量收口验证报告（2026-05-21）
- 文件: `docs\reports\generation-rewrite-final-validation-2026-05-21.md`
- 简况: - 优化/重写阶段默认局部锚点补丁，不再把整章重写当自动兜底；只有显式允许时才进入整章级 fallback。 - 把一致性修复、扩写、自检精修和优化都接入连续性关键词守卫，防止丢失章节任务、角色状态、关键物品地点、伏笔和因果压力。 - 写后账本继续闭环：角色状态、动态角色入池、时间线、因果链、伏笔/线索、知识图谱同步均写入 runtime metadata 和详细日志。 - 前端生成状态日志可以直...

### AI小说创作提示词体系集成方案
- 文件: `docs\reports\integration_design.md`
- 简况: 用习惯 3. **渐进增强**：用户可以选择使用新功能，也可以继续使用原有流程 4. **提示词驱动**：主要通过增强提示词来实现功能，减少代码改动  ## 二、功能模块设计  ### 模块1：角色DNA档案（Character DNA Profile）  **目标**：让用户能够为角色建立更深层的背景档案，使AI生成更立体的人物  **实现方式**： - 利用 `BlueprintCharact...

### 长篇生成与重写重构交付报告
- 文件: `docs\reports\longform-generation-refactor-2026-05-20.md`
- 简况: 性和长篇连续性展开，不另起一套小说引擎。已有的记忆层、伏笔、线索、势力、知识图谱、章节快照、终稿流水线继续作为主账本；新增能力只作为现有流程的接线、补强和验收。  外部借鉴重点来自成熟长篇写作工具的 Story Bible、setup/payoff 伏笔账本、Validator、结构化输出和 provider 抖动退避：  - [Sudowrite Story Bible](https://doc...

### ﻿托管优化进度报告（2026-04-29）
- 文件: `docs\reports\managed-progress-2026-04-29.md`
- 简况: 。 - 修复全局 Alert 默认中文文案。 - 修复章节大纲追加起始章号覆盖风险。 - 增加蓝图取消/失败单测、Alert 单测。 - 清理 WritingDesk 测试 Pinia 注入噪音。  ## 验证 - `npm run build`：通过。 - `npm run test:run`：9 files / 65 tests passed。 - `backend pytest -q`：10...

### ﻿MySQL 环境隔离与修复记录（2026-04-29）
- 文件: `docs\reports\mysql-environment-2026-04-29.md`
- 简况: MYSQL_PORT：3309 - 当前端口状态：$mysqlStatus - 启动脚本：	ools/start_local_mysql.ps1 - 隔离策略：   - 正式启动 start.ps1 使用本地 MySQL 3309。   - 自动化 smoke/E2E 不污染正式 MySQL，分别通过环境变量覆盖为 SQLite：     - 	ools/dev-smoke.ps1 使用 stor...

### 玄穹文枢剩余任务收口报告 2026-05-21
- 文件: `docs\reports\remaining-task-closure-2026-05-21.md`
- 简况: ` - 后端：`http://127.0.0.1:8013/` - Provider：CPA `/v1`，只作为模型供应方。 - 实跑项目：`35cbd8ec-6fdb-47d1-bf6d-437970143d4e`，`Codex实跑验证-20260520` - 实跑章节：第 7 章，目标 2600，最低 2200，候选版本 `333`，定稿正文约 5260 字。  ## 实跑发现的问题与代码修正...

### ﻿version_id 替代 version_index 安全迁移方案
- 文件: `docs\reports\version-id-migration-plan-2026-05-01.md`
- 简况: on_index` 迁移为稳定的 `version_id`。  ## 当前风险  - 前端展示顺序与后端 relationship 顺序可能不一致。 - 删除/新增/并发生成后 index 可能错位。 - 手工编辑和 Patch 生成新版本后，旧 index 链路容易误选版本。  ## 分阶段实施  ### 阶段 1：兼容 API  1. 后端新增按 `version_id` 操作的请求字段。 2...


## 2026-08-06 全量优化

| 功能 | 改动 |
|------|------|
| 质量门死循环 | target_score 82->60, 门槛 60->42 |
| 长篇大纲 | 多卷提示词 8x25章, 超时300s |
| 并行生成 | 默认3版本 asyncio.gather |
| 前端UI | 卡片160px, 侧边栏220px, 导航55px, SSE |
| 清理 | 20 tmp文件 7 backup |

编译/测试: compileall PASS, vue-tsc PASS, build PASS


## 历史报告归档索引

共 24 份审计报告已归档至 `docs/reports/archive/`。

- `CODE_AUDIT_REPORT.md` — unknown
- `CODE_REVIEW_20260329.md` — unknown
- `DEEP_OPTIMIZATION_REPORT.md` — unknown
- `INTEGRATION_REPORT.md` — unknown
- `NOVEL_KIT_FUSION_REPORT.md` — unknown
- `OPTIMIZATION_REPORT_20260329.md` — unknown
- `blueprint-async-unification-plan-2026-05-01.md` — 2026-05-01
- `final-closure-2026-05-21.md` — 2026-05-21
- `frontend-generation-audit-2026-04-28.md` — 2026-04-28
- `full-function-generation-audit-2026-05-01.md` — 2026-05-01
- `full-product-function-map-2026-05-21.md` — 2026-05-21
- `full-product-validation-2026-05-21.md` — 2026-05-21
- `function-tree-managed-2026-04-29.md` — 2026-04-29
- `generated-novel-literary-audit-2026-05-01.md` — 2026-05-01
- `generated-novel-quality-audit-2026-04-29.md` — 2026-04-29
- `generation-function-map-2026-05-20.md` — 2026-05-20
- `generation-quality-rerun-2026-05-20.md` — 2026-05-20
- `generation-rewrite-final-validation-2026-05-21.md` — 2026-05-21
- `integration_design.md` — unknown
- `longform-generation-refactor-2026-05-20.md` — 2026-05-20
- `managed-progress-2026-04-29.md` — 2026-04-29
- `mysql-environment-2026-04-29.md` — 2026-04-29
- `remaining-task-closure-2026-05-21.md` — 2026-05-21
- `version-id-migration-plan-2026-05-01.md` — 2026-05-01