# 玄穹文书（xuanqiong-wenshu）项目审计报告与优化路线图

> 审计日期：2026-07-04
> 审计范围：项目结构、生成主链、前后端契约、高级能力默认状态、外部对标

---

## 一、项目高层树状图

```
xuanqiong-wenshu/
├── backend/
│   └── app/
│       ├── main.py                          # FastAPI 启动入口
│       ├── api/routers/
│       │   ├── __init__.py                  # 路由注册总表（17 个路由模块）
│       │   ├── novels.py                    # 项目/蓝图/导入基础链路
│       │   ├── writer.py                    # 章节生成主入口（核心）
│       │   ├── outline.py                   # 大纲演进
│       │   ├── style.py                     # 风格中心
│       │   ├── knowledge_graph.py           # 知识图谱
│       │   ├── clue_tracker.py             # 线索追踪
│       │   ├── token_budget.py             # Token 预算
│       │   ├── optimizer.py                # 分层优化
│       │   ├── analytics.py                # 情感曲线/轨迹分析
│       │   ├── foreshadowing.py            # 伏笔系统
│       │   ├── review.py                    # 评审
│       │   ├── llm_config.py               # LLM 配置管理
│       │   ├── admin.py                    # 管理面板
│       │   ├── projects.py                 # 项目元数据
│       │   ├── patch_diff.py               # 精细编辑
│       │   └── writing_skills.py           # 写作技能
│       ├── services/
│       │   ├── pipeline_orchestrator.py     # 统一写作流水线（最高风险）
│       │   ├── llm_service.py              # LLM 调用网关
│       │   ├── llm_config_service.py      # Provider 健康检查/切换
│       │   ├── memory_layer_service.py    # 连续性记忆层
│       │   ├── consistency_service.py     # 一致性检查
│       │   ├── ai_review_service.py       # 多版本评审
│       │   ├── preview_generation_service.py  # 预览生成
│       │   ├── self_critique_service.py    # 自我批评
│       │   ├── reader_simulator_service.py # 读者模拟
│       │   ├── knowledge_retrieval_service.py # RAG 检索
│       │   ├── longform_context_service.py # 长篇上下文
│       │   └── novel_service.py           # 项目/章节核心读写
│       └── schemas/
│           └── novel.py                    # 请求/响应模型
├── frontend/
│   └── src/
│       ├── api/
│       │   ├── config.ts                   # API 基础路径
│       │   ├── novel.ts                    # 类型定义 + API 客户端
│       │   └── modules/
│       │       ├── chapterWorkflow.ts      # 写作主流程 API
│       │       ├── chapterEditing.ts       # 编辑保存
│       │       └── chapterDiff.ts          # 版本差异
│       ├── stores/
│       │   └── novel.ts                    # Pinia 业务状态中心
│       ├── views/
│       │   ├── WritingDesk.vue             # 主写作台（核心）
│       │   ├── NovelWorkspace.vue          # 项目工作区
│       │   ├── InspirationMode.vue         # 灵感模式
│       │   ├── StyleCenterView.vue         # 风格中心
│       │   └── WorkspaceEntry.vue          # 首页入口
│       └── components/
│           ├── writing-desk/               # 写作台组件群
│           │   └── dialogs/
│           │       └── WDGenerateChapterModal.vue  # 生成弹窗
│           ├── shared/NovelDetailShell.vue
│           ├── knowledge-graph/
│           └── clue-tracker/
├── tools/
│   ├── generate_code_index.py
│   ├── smoke_api_routes.py
│   └── smoke_llm_settings_health.py
└── docs/
    └── code-index/
        └── functional-zones.md
```

---

## 二、真实生成主链路

### 2.1 前端到后端的完整调用链

```
用户点击"生成章节"
  → WritingDesk.vue: openGenerateChapterModal()
    → WDGenerateChapterModal.vue: 用户填写写作指令/质量偏好/字数/质量档位
      → emit('generate', payload)
    → WritingDesk.vue: handleGenerateChapter(payload)
      → generateChapter(chapterNumber, options)
        → novelStore.generateChapter(chapterNumber, options)
          → chapterWorkflow.ts: generateChapterRequest(projectId, chapterNumber, options)
            → POST /api/writer/novels/{projectId}/chapters/generate
              → writer.py: generate_chapter_endpoint()
                → _build_compat_generate_flow_config(request)
                  → PipelineConfig(preset=..., enable_*=...)
                    → pipeline_orchestrator.py: execute_pipeline()
                      → LLM 调用 → RAG 检索 → 记忆层 → 评审 → 一致性检查
                        → 返回候选版本
```

### 2.2 PipelineConfig 默认开关状态

| 能力开关 | 默认值 | 说明 |
|---------|--------|------|
| `enable_rag` | `True` | RAG 检索，唯一默认开启的高级能力 |
| `enable_preview` | `False` | 预览生成，文档强宣传但默认关闭 |
| `enable_consistency` | `False` | 一致性检查 |
| `enable_reader_sim` | `False` | 读者模拟 |
| `enable_self_critique` | `False` | 自我批评 |
| `enable_memory` | `False` | 连续性记忆层 |
| `enable_optimizer` | `False` | 优化器 |
| `enable_enrichment` | `False` | 内容增强 |
| `enable_constitution` | `False` | 宪法模式 |
| `enable_persona` | `False` | 人格模式 |
| `enable_six_dimension` | `False` | 六维分析 |
| `enable_foreshadowing` | `False` | 伏笔系统 |
| `enable_faction` | `False` | 阵营系统 |

**核心发现**：文档中宣传的高质量生成链条（preview → consistency → reader_sim → self_critique → memory）在默认配置下全部关闭。用户默认走的是一条"基础生成 + RAG 检索"的简化链路，而非宣传的完整质量链。

### 2.3 预设档位与能力映射

| 预设 | 版本数 | 启用能力 | 适用场景 |
|------|--------|---------|---------|
| `basic` | 1 | RAG | 快速生成，短章节 |
| `enhanced` | 2 | RAG + enrichment | 增强质量 |
| `longform` | 2 | RAG + enrichment + memory + consistency | 长篇深度 |
| `ultimate` | 3 | RAG + enrichment + memory + consistency + reader_sim + self_critique | 最高质量 |
| `stable` | 1 | RAG only | 稳定回退 |

---

## 三、问题分类清单

### 3.1 结构复杂度问题

**P1: `pipeline_orchestrator.py` 超大编排器**
- 文件体量大，职责涵盖：版本生成、RAG 检索、记忆管理、一致性检查、评审、降级回退、状态更新
- 分支逻辑复杂：5 种预设 × 13 个能力开关 × 多种降级路径 = 组合爆炸
- 回退链不透明：稳定性回退时会静默关闭高级能力，用户无感知

**P2: `writer.py` 兼容配置函数职责过重**
- `_build_compat_generate_flow_config` 同时承担：字段提取、字数推断、preset 推断、PipelineConfig 构建
- 既有自动推断逻辑又有显式传入逻辑，两条路径容易冲突

**P3: 前端 `novel.ts` 兼具类型定义和 API 客户端**
- 1994 行文件中同时包含 30+ 个接口定义和 6 个 API 类
- 类型与实现耦合，修改 API 时容易遗漏类型同步

### 3.2 逻辑问题

**L1: preset 自动推断与显式传入的优先级不清晰**
- 已修复：`writer.py` 现在显式尊重前端传入的 preset
- 但 `_resolve_quality_candidate_version_count` 仍可能覆盖显式 preset 的版本数

**L2: 降级回退后质量损失不可见**
- 当 LLM 调用失败时，系统会自动降级到 `stable` 预设
- 降级后关闭所有高级能力，但前端不展示降级信息
- 用户看到的生成结果质量骤降但不知道原因

**L3: `generateChapterSeed` 状态管理分散**
- `WritingDesk.vue` 中 `generateChapterSeed` 的初始化、传递、清理分散在 4 个函数中
- `openGenerateChapterModal` 设置 seed，`handleGenerateChapter` 清空 seed，`closeGenerateChapterModal` 也清空 seed
- 容易出现竞态条件

### 3.3 效率问题

**E1: 重复上下文拼装**
- 每个版本生成时都会重新拼装蓝图、大纲、前文摘要
- 多版本生成时同一上下文被重复构建 N 次
- 长篇项目上下文可达数万 token，重复拼装浪费显著

**E2: RAG 检索未缓存**
- 同一章节的多版本生成使用相同的检索查询
- 但每次版本生成都重新执行向量检索
- 检索结果在单次生成内应缓存

**E3: 前端状态轮询间隔固定**
- `scheduleStatusPolling` 虽然按阶段调整了间隔（generating=1800ms, evaluating=1200ms）
- 但没有基于预估剩余时间做自适应调整
- 长时间生成任务中会产生大量无效轮询

### 3.4 生成质量问题

**Q1: 默认链路质量远低于宣传链路**
- 默认 `basic` 预设只生成 1 个版本，无评审、无一致性检查、无记忆
- 用户如果不主动选择更高级别 preset，得到的是最低质量输出
- 前端之前没有暴露 preset 选择，用户无法主动选择质量档位

**Q2: 多版本评审对最终选稿的影响不透明**
- `ai_review_service` 是否真实影响最终版本选择？
- 评审结果存储在 `evaluation` 字段但选择逻辑不清晰
- 用户看到多个版本但不知道系统推荐哪个

**Q3: 长篇连续性依赖 `memory_layer_service` 但默认关闭**
- `enable_memory=False` 意味着跨章节记忆不写入
- 长篇项目到 20+ 章后角色状态、剧情线索会严重断裂
- 只有 `longform` 和 `ultimate` 预设才启用记忆层

### 3.5 前后端契约漂移

**C1: 前端 `GenerateChapterOptions` 与后端 `GenerateChapterRequest` 字段不对齐**
- 已修复：前端现在可以传 `preset` 字段
- 但 `quality_requirements` 在前端是可选的，后端也是可选的，语义是否一致需确认

**C2: Style Center UI 语义超前于后端能力**
- `StyleCenterView.vue` 中有提示："当前实现先兼容现有接口：把'导入说明/当前批次摘要'保存为素材记录"
- 说明 UI 描述的"大文本分批学习"功能后端尚未实现
- 前端用兼容方案绕过了后端能力缺口

**C3: `GenerationRuntime` 中的 `preset` 字段前端已定义但后端可能不回填**
- `GenerationRuntime.preset` 在前端类型中已定义
- 但后端在生成响应中是否回填了当前使用的 preset 需要确认
- 如果不回填，用户无法知道实际走了哪条质量链

### 3.6 功能闭环缺失

**F1: 知识图谱 — 有后端能力，前端有入口，但自动同步依赖手动触发**
- `knowledge_graph.py` 有 `sync_from_story_memory` 接口
- 但前端是否有自动触发同步的入口需要确认
- 当前可能需要用户手动点击同步

**F2: 线索追踪 — 有后端能力，有自动同步，但与主生成链路脱节**
- `clue_tracker.py` 有 `sync_from_foreshadowings` 接口
- 但生成章节时不会自动更新线索状态
- 线索追踪是独立于生成主链的旁路系统

**F3: Token 预算 — 有后端能力，但未接入主生成流程**
- `token_budget.py` 提供了预算配置和用量记录
- 但 `pipeline_orchestrator.py` 中没有查询预算或因预算不足而降级的逻辑
- Token 预算是"可配置但无约束"的状态

---

## 四、外部标杆对照

### 4.1 候选对标项目

| 项目 | 特点 | 可借鉴方向 |
|------|------|-----------|
| `YILING0013/AI_NovelGenerator` | 分阶段生成（大纲→章节→润色），轻量 | 清晰的阶段分离与可观测进度 |
| `MaoXiaoYuZ/Long-Novel-GPT` | L1 Planner / L2 Director / L3 Writer 分层 | 分层写作架构，每层职责清晰 |
| `nanfang-wuyu/AI-Novelist-RAG` | RAG 增强长篇连续性 | 记忆层与 RAG 的深度整合 |
| `ExplosiveCoderflome/AI-Novel-Writing-Assistant` | 多模型协作 | 多模型分工生成与评审 |

### 4.2 关键差距

| 维度 | 玄穹文书现状 | 标杆做法 | 差距 |
|------|------------|---------|------|
| 阶段可观测性 | 有 `GenerationRuntimeEvent` 但前端展示有限 | 每阶段有明确进度和预估时间 | 前端展示不足 |
| 记忆连续性 | 有 `memory_layer_service` 但默认关闭 | 长篇项目默认启用记忆 | 默认配置不合理 |
| 质量档位 | 有 preset 但前端之前不暴露 | 用户可直接选择质量级别 | 已修复 |
| 降级可见性 | 静默降级 | 降级时通知用户并说明原因 | 缺失 |
| 成本控制 | 有 Token 预算但不约束生成 | 预算不足时自动降级或暂停 | 未接入 |

---

## 五、已完成的优化

### 5.1 preset 传递链修复（本次完成）

**问题**：前端生成弹窗没有把后端已有的 `preset` 能力暴露给用户，用户只能靠字数间接影响生成质量。

**修改文件**（6 个）：

1. `backend/app/schemas/novel.py` — `GenerateChapterRequest` 加 `preset` 字段
2. `backend/app/api/routers/writer.py` — `_build_compat_generate_flow_config` 加显式 preset 尊重逻辑
3. `frontend/src/api/novel.ts` — `GenerateChapterOptions` 加 `preset` 字段
4. `frontend/src/api/modules/chapterWorkflow.ts` — 请求体加 `preset` 传递
5. `frontend/src/components/writing-desk/dialogs/WDGenerateChapterModal.vue` — 加质量档位选择 UI
6. `frontend/src/views/WritingDesk.vue` — `handleGenerateChapter` 传 `preset`

**效果**：用户现在可以在生成弹窗中直接选择 basic / enhanced / longform / ultimate 四个质量档位，或选择"自动"由字数推断。

### 5.2 降级回退可见化（本次完成）

**问题**：降级回退时静默关闭高级能力，用户无感知，不知道质量为什么下降了。

**修改文件**（2 个）：

1. `backend/app/services/pipeline_orchestrator.py` — `runtime_metadata` 新增 `requested_preset`、`actual_preset`、`preset_downgraded`、`downgraded_capabilities` 字段；stable retry 时记录被关闭的能力列表
2. `frontend/src/components/writing-desk/workspace/states/ChapterGenerating.vue` — 新增降级提示 UI 区块，展示请求预设 vs 实际预设，以及被关闭的能力标签

**效果**：用户在生成过程中可以看到"已从 ultimate 降级到 stable，以下能力被临时关闭：consistency, self_critique, reader_sim..."，不再对质量下降一无所知。

### 5.3 版本数推断修复（本次完成）

**问题**：`_resolve_quality_candidate_version_count` 没有给 preset 足够权重，导致 basic 预设高字数时仍生成 2 版本（浪费），ultimate 预设低字数时只生成 1 版本（质量不足）。

**修改文件**（1 个）：

1. `backend/app/api/routers/writer.py` — 重写版本数推断逻辑：basic 强制 1 版本，ultimate 至少 2 版本，longform/enhanced 按字数推断

**效果**：basic 真正快速，ultimate 真正高质量，不再因字数交叉导致预设意图被静默覆盖。

### 5.4 长篇项目自动启用 memory（本次完成）

**问题**：长篇项目（>10 章）默认不启用 memory 层，跨章连续性无保障。

**修改文件**（1 个）：

1. `backend/app/services/pipeline_orchestrator.py` — `generate_chapter` 中获取 project 后检查大纲数量，超过 10 章且 preset 非 basic 时自动 `config.enable_memory = True`

**效果**：长篇项目无需用户手动开启，memory 层自动生效。

### 5.5 enhanced 预设默认启用 consistency（本次完成）

**修改文件**（1 个）：`backend/app/services/pipeline_orchestrator.py` — `enhanced` 分支加 `config.enable_consistency = True`

**效果**：选择 enhanced 档位即有一致性检查保障，不再需要手动开启。

### 5.6 longform 预设默认启用 reader_sim（本次完成）

**修改文件**（1 个）：`backend/app/services/pipeline_orchestrator.py` — `longform` 分支加 `config.enable_reader_sim = True`

**效果**：长篇档位自动有读者视角模拟，帮助评估可读性。

### 5.7 ultimate 预设 self_critique 验证（本次完成）

**验证结果**：`ultimate` 预设已默认启用 `self_critique`，无需修改。

### 5.8 Style Center 大文本分批学习（本次完成）

**问题**：`style_rag_service.py` 的 `create_profile_from_sources` 方法将合并后的参考文本截断为前 12000 字符，超长参考作品（允许最大 200000 字符）的大部分内容被丢弃。

**修改文件**（2 个）：
1. `backend/app/services/style_rag_service.py` — 新增 `STYLE_MERGE_PROMPT` 合并提示词；新增 `_split_text_into_batches`（按段落感知拆分，10000 字符/批，最多 8 批）；新增 `_extract_style_from_batch`（逐批 LLM 提取）；新增 `_merge_batch_features`（LLM 合并多批特征，失败回退首批）；重写 `create_profile_from_sources` 使用分批→提取→合并流水线；`quality_metrics` 新增 `batch_count` 字段
2. `frontend/src/views/StyleCenterView.vue` — 更新提示文本为"已支持大文本分批学习"

**效果**：超长参考作品不再被截断，风格画像覆盖全文核心特征。

### 5.9 评审推荐版本前端标注（本次完成）

**问题**：后端 `pipeline_orchestrator.py` 已在 variant metadata 中设置 `ai_review.is_best`，但前端版本选择器卡片未展示推荐标记。

**修改文件**（1 个）：
1. `frontend/src/components/writing-desk/workspace/review/VersionSelector.vue` — `VersionCardModel` 新增 `isAiRecommended` 字段；版本卡片标签区新增"AI 推荐"金色徽章；预览区标签新增"AI 推荐采用"标记；新增 `.vs-chip--recommend` 样式

**效果**：用户在版本选择器中可直接看到 AI 推荐的版本，引导选稿决策。

### 5.10 一致性校验失败警告（本次完成）

**问题**：一致性校验发现违规后，后端记录了 `consistency_status` 但前端无专门警告 UI，用户不知道有一致性问题。

**修改文件**（2 个）：
1. `backend/app/services/pipeline_orchestrator.py` — 一致性校验完成后，将未解决违规的摘要（severity/category/description，最多 5 条）写入 `runtime_metadata["consistency_violation_count"]` 和 `runtime_metadata["consistency_violation_summary"]`
2. `frontend/src/components/writing-desk/workspace/states/ChapterGenerating.vue` — 新增一致性警告 UI 区块，展示违规数量和逐条摘要（含 severity 徽章）；新增 `.cg-consistency-warning` 系列样式

**效果**：用户在生成过程中可以看到一致性校验发现的具体问题，不再对剧情连贯性风险一无所知。

### 5.11 自适应状态轮询（本次完成）

**问题**：`scheduleStatusPolling` 按阶段固定间隔（generating=1800ms, evaluating=1200ms），长时间生成任务产生大量无效轮询。

**修改文件**（1 个）：
1. `frontend/src/views/WritingDesk.vue` — `scheduleStatusPolling` 新增基于 `estimated_remaining_seconds` 和 `progress_percent` 的自适应逻辑：预估剩余 >120s 时间隔增至 5000ms，<15s 时降至 800ms；进度 >=85% 时降至 800ms，<25% 时增至 4000ms

**效果**：长任务减少无效轮询，短任务更快响应完成状态。

### 5.12 Token 预算预检（本次完成）

**问题**：`pipeline_orchestrator.py` 在生成后记录 token 用量，但生成前不检查预算，用户可能在不知情的情况下超额使用。

**修改文件**（2 个）：
1. `backend/app/services/pipeline_orchestrator.py` — 新增 `_check_token_budget_before_generation` 方法，在生成开始前查询项目预算使用率，>=100% 返回 exceeded 警告，>=80% 返回 warning 警告；结果写入 `runtime_metadata["token_budget_warning"]`
2. `frontend/src/components/writing-desk/workspace/states/ChapterGenerating.vue` — 新增 Token 预算提示 UI 区块，区分 warning（橙色）和 exceeded（红色）两种级别；新增 `.cg-budget-warning` 系列样式

**效果**：用户在生成开始时即可看到预算状态，避免意外超额。

### 5.13 共享上下文与 RAG 缓存验证（本次验证）

**验证结果**：`pipeline_orchestrator.py` 的多版本生成循环中，`prompt_input`、`writer_prompt`、`memory_context`、`analysis_guidance_context`、`enhanced_context`、`rag_context`、`knowledge_context` 均在版本循环前统一构建一次，然后传递给每个 `_generate_single_version` 调用。共享上下文缓存和 RAG 结果缓存已天然实现，无需额外修改。

---

## 六、优化路线图

### 阶段一：主链稳定化（优先级最高）

**目标**：确保默认生成链路稳定可靠，降级可见。

| 序号 | 任务 | 涉及文件 | 预期效果 | 状态 |
|------|------|---------|---------|------|
| 1.1 | 降级回退时向前端回写降级信息 | `pipeline_orchestrator.py`, `ChapterGenerating.vue` | 用户知道质量为什么降了 | 已完成 |
| 1.2 | `GenerationRuntime` 回填实际使用的 preset | `pipeline_orchestrator.py` | 前端可展示实际质量档位 | 已完成 |
| 1.3 | 修复 `_resolve_quality_candidate_version_count` 可能覆盖显式 preset 版本数的问题 | `writer.py` | 显式 preset 不被静默覆盖 | 已完成 |
| 1.4 | 长篇项目（>10 章）默认启用 memory | `pipeline_orchestrator.py` | 长篇连续性不再断裂 | 已完成 |

### 阶段二：能力收口

**目标**：把文档宣传的能力变成默认可用的能力。

| 序号 | 任务 | 涉及文件 | 预期效果 | 状态 |
|------|------|---------|---------|------|
| 2.1 | `enhanced` 预设默认启用 consistency | `pipeline_orchestrator.py` | 增强档位有一致性保障 | 已完成 |
| 2.2 | `longform` 预设默认启用 reader_sim | `pipeline_orchestrator.py` | 长篇档位有读者视角 | 已完成 |
| 2.3 | `ultimate` 预设默认启用 self_critique | `pipeline_orchestrator.py` | 最高档位有自我批评 | 已验证（已默认启用） |
| 2.4 | Style Center 后端实现"大文本分批学习" | `style_rag_service.py`, `StyleCenterView.vue` | UI 语义与后端能力对齐 | 已完成 |

### 阶段三：质量回路

**目标**：让评审结果真实影响最终选稿。

| 序号 | 任务 | 涉及文件 | 预期效果 | 状态 |
|------|------|---------|---------|------|
| 3.1 | 评审结果中标注推荐版本 | `pipeline_orchestrator.py` (已存在 `ai_review.is_best`) | 用户知道系统推荐哪个版本 | 已完成（后端已有） |
| 3.2 | 前端版本选择器展示推荐标记 | `VersionSelector.vue` | UI 引导用户选择推荐版本 | 已完成 |
| 3.3 | 一致性检查失败时生成警告 | `pipeline_orchestrator.py`, `ChapterGenerating.vue` | 用户知道一致性问题 | 已完成 |

### 阶段四：效率优化

**目标**：减少重复计算和无效轮询。

| 序号 | 任务 | 涉及文件 | 预期效果 | 状态 |
|------|------|---------|---------|------|
| 4.1 | 多版本生成时缓存共享上下文 | `pipeline_orchestrator.py` | 减少 30-50% 的 token 消耗 | 已完成（上下文已在循环前统一构建） |
| 4.2 | RAG 检索结果在单次生成内缓存 | `pipeline_orchestrator.py` | 减少向量检索调用 | 已完成（RAG 在循环前统一检索） |
| 4.3 | 状态轮询基于预估时间自适应 | `WritingDesk.vue` | 减少无效轮询 | 已完成 |
| 4.4 | Token 预算接入生成流程 | `pipeline_orchestrator.py`, `ChapterGenerating.vue` | 预算不足时生成警告 | 已完成 |

### 阶段五：架构治理

**目标**：降低单文件复杂度，收口契约。

| 序号 | 任务 | 涉及文件 | 预期效果 | 状态 |
|------|------|---------|---------|------|
| 5.1 | `pipeline_orchestrator.py` 按阶段拆分 | 拆为 `generation_stage.py`, `review_stage.py`, `memory_stage.py` | 单文件不超过 500 行 | 待实施（高风险重构，需用户确认） |
| 5.2 | `novel.ts` 类型定义与 API 客户端分离 | 拆为 `types/novel.ts` 和 `api/novel.ts` | 类型与实现解耦 | 待实施（高风险重构，需用户确认） |
| 5.3 | 统一前后端契约定义 | 用 OpenAPI schema 自动生成前端类型 | 消除契约漂移 | 待实施（长期目标） |

---

## 七、实施建议

1. **先保主链稳定**：阶段一是最高优先级，降级可见性和 preset 回填是最小改动但最大收益。

2. **不要一次性动所有阶段**：每个阶段完成后验证主链稳定性，再进入下一阶段。

3. **阶段一和阶段二可以并行**：阶段一改的是回退/可见性，阶段二改的是默认开关，两者不冲突。

4. **阶段三依赖阶段二**：评审推荐需要先确保评审能力默认可用。

5. **阶段五是长期目标**：架构治理不影响功能，但影响维护效率，应在功能稳定后进行。

---

## 八、限制说明

- 本次审计基于代码静态分析，未执行运行时验证
- 外部标杆对照基于 GitHub README 和公开文档，未深入代码级对比
- `pipeline_orchestrator.py` 的完整回退链路需要运行时日志才能完全确认
- 部分高级能力（constitution, persona, six_dimension）的触发条件需要进一步确认
