# 玄穹文枢：领域 B 生产级生成管线审查与验收计划

> 责任域：小说生成管线、全书总纲、章节纲、短章/长章/20k 分段、跨章连续性、记忆/时间线/伏笔、质量门、候选评审、定稿闭环。
>
> 本文是审查与计划，不是业务代码修改记录。本轮只读代码、测试和真实验收脚本；不改变现有业务实现，不覆盖工作区已有未提交成果。
>
> 审查基线：2026-08-14，工作区当前存在大量未提交改动；结论以当前文件和可复核命令为准，不以历史“已完成”报告代替真实证据。

## 1. 结论摘要

### 1.1 已具备的生产化基础

- 已切换 DeepSeek 默认模型：`backend/.env:29` 为 `deepseek-v4-flash-free`，回退模型在 `backend/.env:30`，应用默认值在 `backend/app/core/config.py:86`。
- 正文生成已有统一编排入口 `PipelineOrchestrator.generate_chapter`（`backend/app/services/pipeline_orchestrator.py:2104`），并已拆出生成调用策略、长篇计划、上下文包、质量评分和定稿服务。
- 短章已有纯正文协议、元文本污染检测及一次受控清洁重试；回归证据见 `backend/app/services/test_generation_quality_guards.py:19`、`:84`、`:144`。
- 生成调用层已有错误分类、退避、JSON 能力降级、软超时和取消传播；证据见 `backend/app/services/generation_call_service.py:59`、`:230`、`:270`。
- 长章/20k 已有不可变计划、段预算、`plan_key` 校验、段级 checkpoint、段级质量门、取消检查和断点恢复契约；证据见 `backend/app/services/longform_generation_service.py:47`、`:129`、`:249`、`:321`。
- 上下文已覆盖全书—卷—章—记忆—时间线—知识图谱—角色池—伏笔/线索任务；证据见 `backend/app/services/longform_context_service.py:296`、`:353`、`:378`、`:708`。
- 定稿闭环已有摘要、人物状态、剧情线、向量摄取、章节快照和蓝图状态更新；证据见 `backend/app/services/finalize_service.py:204`、`:285`、`:611`。
- 已有 1→10 章连续性数据库测试、20k 分段单测、质量门回归、Provider 取消不挂起、运行 ID 重绑定测试；证据见 `backend/app/services/test_multi_chapter_continuity_production.py:422`、`backend/app/services/test_longform_generation_service.py:215`、`backend/app/services/test_provider_cancel_no_hang.py:24`、`backend/app/services/test_generation_run_rebind.py:34`。
- 已有真实 ASGI 短章、长篇分段、双项目并发脚本；分别见 `backend/scripts/real_asgi_generation_smoke.py:49`、`backend/scripts/real_asgi_longform_generation_smoke.py:37`、`backend/scripts/real_asgi_concurrent_generation_smoke.py:266`。

### 1.2 当前不能宣称完成的事项

以下均是“真实未完成项”，不是测试文字可以替代的完成项：

1. 真实 Provider 的短章虽曾出现成功样本，但也出现过 `evaluation_failed`；Provider 波动、质量门误报/真残留尚未形成连续两轮全绿证据。
2. 10 章连续测试使用隔离数据库和替身/注入的摘要与定稿依赖，尚未完成真实 DeepSeek 入口连续 1→10 章的正式验收。
3. 20k 真实脚本要求 `task.status == succeeded`，但未覆盖真实取消后再次恢复、模拟进程重启、恢复后的 SSE 续接和“不重复生成已完成段”的完整入口链。
4. 双项目并发脚本会并发提交 Provider 请求，但尚未形成多轮、不同长度、一个失败一个成功、跨用户权限隔离的稳定统计证据；一次并发波动不能作为生产级隔离证明。
5. 正文/大纲路由仍保留模块级 `_OUTLINE_JOBS`、`_OUTLINE_PROJECT_RUNS` 和调度集合（`backend/app/api/routers/writer.py:106`-`:112`），同时使用 `TaskRuntime`；状态真相源尚未完全统一。
6. `resume_chapter_generation` 只接受 `stale`（`backend/app/api/routers/writer.py:3961`-`:3979`），失败/取消任务虽可能可重试，但不是同一语义的 checkpoint 恢复验收。
7. 长篇计划虽写入 `TaskRuntime`（`backend/app/api/routers/writer.py:727`-`:817`），但真实 worker 的恢复、checkpoint 更新、正文版本原子收口必须继续以真实数据库证据确认。
8. 长篇大纲结构校验发现问题只记录 warning（`backend/app/api/routers/outline.py:321`-`:325`），仍可继续展平、保存和返回；fallback 含“待填充”内容（`backend/app/services/long_novel_outline_generator.py:375`-`:403`），不能作为高质量长篇成品。
9. 大纲生成路由仍是同步请求内调用 LLM、保存章节纲并提交（`backend/app/api/routers/outline.py:299`-`:374`），未完全接入统一任务协议、SSE、重启恢复和任务级幂等。
10. 定稿计算阶段会依次调用多个 LLM/向量操作，最后统一提交数据库（`backend/app/services/finalize_service.py:235`-`:336`），但外部向量写入无法与数据库事务原子化；当前失败时只能回滚数据库并返回失败，缺少正式 outbox/补偿记录。
11. 定稿摘要只取章节前 5000 字（`backend/app/services/finalize_service.py:577`-`:586`），20k 章节的章末、伏笔回收和后果可能不在摘要输入中。
12. 连续性质量门对缺失长篇上下文是 warning 而不是 blocker（`backend/app/services/longform_context_service.py:716`-`:720`），这符合降级可运行，但不符合“核心长篇生产门禁必须有上下文”的发布要求。
13. 质量评分以规则/关键词/启发式为主；现有测试验证检测器行为，但没有人工标注集、跨题材误报率、真实 Provider 质量分布和可重复基准。
14. “成功”之后实际仍可能是 `waiting_for_confirm`；真实脚本允许该状态（`backend/scripts/real_asgi_generation_smoke.py:109`、`:237`），是否自动定稿必须由产品契约明确，不能把候选生成等同正式章节完成。

## 2. 功能清单与逐功能审查

### B1. 全书总纲/长篇蓝图

**现状与证据**

- `LongNovelOutlineGenerator` 的提示词要求多卷、主线、暗线、人物弧、伏笔和节奏（`backend/app/services/long_novel_outline_generator.py:20`-`:111`）。
- 规模估算按总字数选择卷数、每卷章数和章均字数（`:210`-`:249`）。
- 生成失败回退到规则大纲；结构验证只检查卷、标题、摘要和章节数量（`:328`-`:353`）。
- `outline/generate-long` 负责调用、校验、展平和保存章节纲（`backend/app/api/routers/outline.py:260`-`:389`）。

**逻辑链**

`项目蓝图/类型/目标字数`
→ `规模估算`
→ `多卷 JSON prompt`
→ `LLM JSON 解析`
→ `结构校验`
→ `卷-章展平`
→ `ChapterOutline 持久化`
→ `章节生成读取本章纲`

**树状依赖**

```text
全书总纲
├─ NovelProject / Blueprint
│  ├─ 世界观与规则
│  ├─ 主角、角色弧、势力
│  ├─ 主线/暗线
│  └─ 伏笔系统
├─ LongNovelOutlineGenerator
│  ├─ estimate_structure
│  ├─ build_prompt / parse_outline_response
│  ├─ validate_outline_structure
│  └─ flatten_outline
├─ outline 路由
│  ├─ LLMService
│  ├─ ChapterOutline
│  └─ 当前仍有同步请求与 warning 后继续保存
└─ 下游
   ├─ ChapterMission
   ├─ LongformGenerationPlan.book_context / volume_context
   └─ 连续性、伏笔、质量门
```

**未完成与方案**

- P0：把“结构存在”提升为“长篇可执行契约”：卷目标、卷内弧线、章节依赖、角色状态转移、伏笔埋收映射、章均字数和节奏预算必须全部校验；任何 blocker 不得保存为正式大纲。
- P0：长篇大纲改为任务化生成，按“规模规划→卷骨架→章节骨架→依赖校验→保存”分阶段 checkpoint；LLM 输出只接受 schema 校验后的对象。
- P1：章节纲每章增加 `mission/conflict/information_delta/state_delta/foreshadowing_task/ending_hook/next_constraint`，并生成可供 writer 直接消费的版本化快照。
- P1：fallback 只能生成“可继续编辑的草稿”，必须带 `degraded=true`、缺失字段清单和禁止直接生产的提示；禁止用“待填充”冒充高质量完成。

### B2. 章节纲与 ChapterMission

**现状与证据**

- writer 路由声明 L1 Planner、L2 Director、L3 Writer 分层，并强调信息可见性过滤（`backend/app/api/routers/writer.py:3`-`:13`）。
- 编排器会构建章节 overview bundle、变更等级和复用判断（`backend/app/services/pipeline_orchestrator.py:175`-`:245`）。
- 短章可走本地 mission contract，测试验证冲突、场景预算和章末钩子（`backend/app/services/test_generation_quality_guards.py:158`-`:175`）。

**逻辑链**

`总纲/上一章账本`
→ `章节纲`
→ `ChapterMission`
→ `有限视角与可见角色过滤`
→ `Writer prompt`
→ `正文`
→ `mission/scene/ending 质量门`

**树状依赖**

```text
章节纲
├─ 章节使命
│  ├─ 目标/冲突/转折
│  ├─ 信息增量
│  ├─ 人物状态变化
│  └─ 下一章交付约束
├─ 场景列表
│  ├─ goal / conflict / turn
│  ├─ dialogue_value / payoff
│  └─ bridge / end_hook
├─ 角色与视角边界
└─ 质量门输入
   ├─ scene_fulfillment
   ├─ event_density
   ├─ ending_pressure
   └─ continuity terms
```

**未完成与方案**

- P0：为 ChapterMission 定义版本化 schema 和必填/可选字段，禁止编排器在多个位置自行拼接同名任务字段。
- P0：将“任务命中率”从关键词命中升级为可审计的事件证据：每个场景必须关联正文片段、状态变化和因果后果。
- P1：章节纲生成与正文生成共享同一 `outline_version_id`、`mission_hash`，任务详情可追溯实际使用版本。

### B3. 短章生成（约 1200 字）

**现状与证据**

- `PipelineConfig` 默认启用最小字数门、可控多轮补足和候选数量边界（`backend/app/services/pipeline_orchestrator.py:93`-`:123`）。
- 真实脚本要求最少 900 字、正文 SSE、终态、落库和一次首稿 Provider 调用（`backend/scripts/real_asgi_generation_smoke.py:88`-`:109`、`:245`-`:285`）。
- 污染重试只允许一次且不携带污染正文，已有单测证据（`backend/app/services/test_generation_quality_guards.py:19`-`:81`）。

**逻辑链**

`提交配置`
→ `项目/章节 claim`
→ `短章 mission`
→ `DeepSeek 正文调用`
→ `元文本/JSON/标签污染检测`
→ `一次清洁重试（如需要）`
→ `结构/连续性/字数质量门`
→ `候选版本持久化`
→ `waiting_for_confirm 或 finalized`

**未完成与方案**

- P0：明确短章默认产品终态：若目标是生产章节，质量门通过后应进入“待确认候选”还是自动定稿，API、前端和验收脚本必须统一。
- P0：真实 DeepSeek 串行跑 10 次短章，记录首稿调用数、污染率、质量门 blocker、延迟、正文长度和终态；并发压力不能替代串行基线。
- P1：将短章污染检测拆为“硬协议泄漏”和“正常叙事误报”两类，建立真实样本回归集；失败必须保留原始诊断但不得把诊断写入正文。
- P1：短章禁止无意义候选并行和同源重写；默认一首稿，只有明确配置才允许候选评审。

### B4. 中长章与候选评审

**现状与证据**

- 版本数量有 1-4 的边界（`backend/app/services/pipeline_orchestrator.py:70`-`:73`）。
- 编排器存在多阶段结构门、自我批判、连续性门、富化和候选保存逻辑（`backend/app/services/pipeline_orchestrator.py:3597`-`:3657`、`:3775`-`:3901`）。
- `SelfCritiqueService` 按逻辑、连续性、人物、节奏、对白等维度分策略，且设置绝对迭代上限（`backend/app/services/self_critique_service.py:22`-`:59`）。

**逻辑链**

`正文候选`
→ `基础护栏`
→ `AI/规则评审`
→ `结构质量门`
→ `一致性/长篇连续性门`
→ `局部修订或富化`
→ `修订前后比较`
→ `候选保存/阻断`

**未完成与方案**

- P0：把每次修订限制为明确预算：单候选最多首稿 1 次、受控重试 1 次、局部修订 1 次；任何重写都必须记录原因、输入版本、输出版本和分数变化。
- P0：评分门必须 fail closed：缺失评分不等于通过；真实 Provider 输出出现“提纲/标签残留”时保存 blocked candidate，不得静默落库。
- P1：候选评审改为差异化抽样，避免同一模型同一上下文生成多个低信息增益版本；短章关闭候选，长章按质量/成本阈值开启。

### B5. 20k 分段生成与恢复

**现状与证据**

- 计划按目标字数拆分固定预算，计划 hash 防篡改（`backend/app/services/longform_generation_service.py:129`-`:194`、`:201`-`:246`）。
- 每段成功后保存 checkpoint；段质量门失败只重试当前段，不推进断点（`:249`-`:318`）。
- 段门检查空正文、最低字数、重复、必要锚点；章门检查总字数、内部重复和必要锚点（`:375`-`:462`）。
- 20k 单测验证第 2 段中断、从持久化快照恢复、已完成段不重复、最终达到 20k（`backend/app/services/test_longform_generation_service.py:215`-`:285`）。
- 真实脚本检查 checkpoint、正文增量、终态事件和正文长度（`backend/scripts/real_asgi_longform_generation_smoke.py:103`-`:140`）。

**逻辑链**

`目标字数/分段上限`
→ `LongformGenerationPlan(plan_key)`
→ `TaskRuntime payload + checkpoint`
→ `逐段 Provider 调用`
→ `段级质量门`
→ `checkpoint 持久化`
→ `content_delta`
→ `下一段`
→ `整章质量门`
→ `版本/定稿`

**树状依赖**

```text
20k 章节
├─ LongformGenerationPlan
│  ├─ book_context
│  ├─ volume_context
│  ├─ chapter_context
│  └─ SegmentBudget[0..n]
├─ LongformCheckpoint
│  ├─ next_segment_index
│  ├─ completed_segments / fingerprint
│  ├─ assembled_text
│  └─ used_words / total_tokens
├─ TaskRuntime
│  ├─ generation_spec
│  ├─ longform_generation
│  └─ event cursor
└─ 终态
   ├─ succeeded / waiting_for_confirm
   ├─ stale → resume
   ├─ cancelled
   └─ failed / evaluation_failed
```

**未完成与方案**

- P0：真实入口加入“段 2 完成后断开/进程重启”测试，恢复必须读取同一 `plan_key` 和 checkpoint，不能从请求参数新建计划覆盖旧计划。
- P0：每段落库正文产物或可验证 offset；当前 `assembled_text` 大对象直接放任务 payload，需评估 SQLite/数据库行大小、并发写入和事件膨胀风险。
- P0：恢复任务必须有唯一租约；旧 worker 的迟到回调只能因 run/lease 版本不匹配被拒绝。
- P1：段级上下文只携带必要的前段尾部、已确认账本和本段使命；禁止每段重复发送整章正文导致成本和超时线性失控。
- P1：真实验收将目标设置为 20,000±允许阈值，按统一字数口径核验，而不是仅用 `len(content)` 字符数。

### B6. 跨章连续性与上下文构建

**现状与证据**

- `LongformContextService` 读取项目记忆、最近快照、时间线事件、因果链、角色状态、知识图谱、伏笔和线索（`backend/app/services/longform_context_service.py:296`-`:351`、`:353`-`:420`）。
- 上下文 prompt 明确要求角色状态、物品、伤势、知识边界、势力、伏笔和下一章承接（`:697`-`:706`）。
- 连续性门能检测章节号错配、死亡角色异常行动、到期伏笔可见性和回收强度（`:709`-`:810`）。
- 1→10 章隔离数据库测试验证摘要、快照、全局记忆、时间线、因果边和下一章上下文（`backend/app/services/test_multi_chapter_continuity_production.py:423`-`:500`）。

**逻辑链**

`前章定稿`
→ `章节摘要/全局摘要/快照`
→ `角色状态/时间线/因果/伏笔/线索/图谱账本`
→ `LongformContextPackage`
→ `当前章节使命`
→ `Writer context`
→ `正文`
→ `continuity gate`
→ `定稿后账本更新`

**未完成与方案**

- P0：建立“事实账本”与“LLM 摘要”双层模型；硬事实（死亡、位置、物品、时间、已知秘密、伏笔状态）必须结构化，摘要只能辅助，不得覆盖硬事实。
- P0：连续性门区分 blocker、warning、degraded；生产长篇缺少 context、章节号错配、账本版本冲突必须 blocker。
- P1：增加跨卷和远距离伏笔回收测试，不仅验证最近 10 个 snapshot；验证第 1 章埋伏笔在第 10/20 章仍可检索且状态不漂移。
- P1：每个正文版本记录 `context_snapshot_id`、账本版本、outline/mission hash，出现冲突可重放。

### B7. 记忆、人物状态、时间线和因果

**现状与证据**

- 定稿会更新全局摘要、角色状态、剧情线、快照和蓝图状态（`backend/app/services/finalize_service.py:245`-`:334`）。
- 长篇上下文读取 `ProjectMemory`、`ChapterSnapshot`、`TimelineEvent` 和 `CausalChain`（`backend/app/services/longform_context_service.py:353`-`:420`）。
- 真实/生产连续性测试会在每章注入角色状态、时间线和图谱边，并验证下一章读取（`backend/app/services/test_multi_chapter_continuity_production.py:252`-`:335`、`:451`-`:483`）。

**逻辑链**

`正文确认`
→ `事实抽取/LLM 摘要`
→ `状态变更候选`
→ `冲突校验`
→ `ProjectMemory/CharacterState/TimelineEvent/CausalChain`
→ `ChapterSnapshot`
→ `下一章上下文`

**未完成与方案**

- P0：更新采用 append-only 事件 + 版本化投影，禁止直接覆盖导致无法追溯；同章重复定稿必须幂等。
- P0：状态变更必须带来源章节、正文版本、证据片段和置信度；低置信度进入待确认，不直接成为硬约束。
- P1：时间线加入故事时间与现实生成时间的明确区分，因果链加入前置事件存在性和顺序校验。

### B8. 伏笔、线索与回收

**现状与证据**

- 上下文服务按“到期回收 > 逾期补偿 > 临近强化 > 新埋”构建任务（`backend/app/services/longform_context_service.py:701`-`:706`）。
- 连续性门能区分“命中但未揭示”和“完全不可见”，并产生补丁建议（`:779`-`:810`）。
- 伏笔模型和任务服务已接入生成上下文，路由/分析层还存在从正文和摘要推断伏笔的兼容逻辑，需逐步统一为数据库账本。

**未完成与方案**

- P0：伏笔状态转移限定为 `planted → reinforced/developing → partial/resolved/overdue`，每次转移带章节、版本、证据和操作者。
- P0：回收必须验证“揭示 + 因果 + 后果”三件套，关键词命中不得单独通过。
- P1：建立跨卷伏笔矩阵：埋设章、强化章、预期回收章、实际回收章、影响角色和后果；发布门禁止 major 伏笔逾期未处理。

### B9. 质量门、护栏、评审与定稿

**现状与证据**

- `ChapterGuardrails` 检测禁止角色、全知视角 cue、新角色介绍（`backend/app/services/chapter_guardrails.py:38`-`:131`）。
- `story_quality_scoring` 汇总 blocker、规则警告和前端可读标签，并 fail closed 处理缺失 gate（`backend/app/services/story_quality_scoring.py:207`-`:249`）。
- 编排器会持久化质量门阻断候选并发出事件（`backend/app/services/pipeline_orchestrator.py:1952`-`:2016`、`:3613`-`:3657`）。
- 定稿有 LLM 摘要、人物状态、剧情线和快照，但外部向量更新在数据库提交前后缺少统一 outbox（`backend/app/services/finalize_service.py:270`-`:336`）。

**逻辑链**

`候选正文`
→ `协议污染门`
→ `章节护栏`
→ `场景/事件/节奏/钩子评分`
→ `一致性/伏笔门`
→ `自我批判`
→ `局部修订`
→ `前后分数比较`
→ `blocked candidate 或 waiting_for_confirm`
→ `用户确认`
→ `FinalizeService`
→ `正文版本 + 记忆快照 + 账本 + outbox`

**未完成与方案**

- P0：发布门统一为硬 blocker、可修复 warning、降级 warning 三类；质量门、护栏和连续性门必须输出统一 DTO。
- P0：最终提交采用 `finalization_session` + outbox：正文版本、选中版本、摘要、账本快照、事件和向量任务引用必须有同一 commit id。
- P0：定稿 LLM 输入必须覆盖长章首/中/尾和结构化事件，不得只截前 5000 字。
- P1：建立人工标注集和分题材阈值；先验证误报/漏报，再调整阈值，不能只降低门槛。

## 3. 统一生产逻辑树

```text
用户配置与项目版本
├─ 模型/Provider/参数/提示词版本
├─ 目标字数/最小字数/分段/候选数
├─ 质量门/记忆/伏笔/检索开关
└─ config_version + idempotency_key
   ↓
任务登记与租约
├─ TaskRuntime: queued → running → cancelling → terminal
├─ chapter/project 唯一 claim
├─ generation_spec 持久化
└─ 长章生成计划 + checkpoint
   ↓
上下文构建
├─ 全书总纲 / 当前卷 / 章节纲
├─ 前章摘要 / 最近尾部 / 快照
├─ 人物状态 / 知识边界 / 势力
├─ 时间线 / 因果链 / 伏笔 / 线索 / 图谱
└─ 上下文 hash + 版本证据
   ↓
导演脚本
├─ chapter mission
├─ scene list
├─ conflict / turn / information delta
└─ ending hook / next constraint
   ↓
正文生成
├─ 短章：单首稿 + 一次清洁重试上限
├─ 中长章：候选预算 + 局部修订
└─ 20k：固定分段 + 段级 checkpoint + content_delta
   ↓
质量闭环
├─ 元文本/JSON/标签污染
├─ 角色/PОV/禁止名护栏
├─ 字数/重复/事件密度/场景兑现
├─ 连续性/时间线/伏笔回收
└─ 分数前后比较与 blocker 收敛
   ↓
版本与定稿
├─ blocked candidate / waiting_for_confirm
├─ 用户选择/确认
├─ 原子正文版本
├─ 记忆/时间线/伏笔/快照投影
└─ outbox → 向量/导出/通知
   ↓
SSE 与恢复
├─ event cursor / Last-Event-ID
├─ content_delta 与 log 分流
├─ stale → lease recovery
└─ 终态关闭且迟到回调被拒绝
```

## 4. Provider 策略（DeepSeek）

### 4.1 模型分层

| 场景 | 默认策略 | 预算 | 禁止行为 |
|---|---|---:|---|
| 短章正文 | `deepseek-v4-flash-free`，单首稿 | 目标字数的 1.8-2.2 倍输出 token | 默认多候选、同章整篇重复重写 |
| 章节纲/结构 JSON | DeepSeek，JSON object；失败先降级 response format 再有限修复 | 2 次结构修复 | 无限 JSON 修复、解析失败后伪造完整纲 |
| 中长章 | Flash 首稿；只有 blocker 且可定位时局部修订 | 首稿 1 + 修订 1 | 无证据的全章重写 |
| 20k 分段 | 每段 3k-4.5k 目标，段间带 checkpoint | 每段最多 2 次 | 单次 20k 请求、失败后整章重跑 |
| 定稿摘要/账本 | 低温度、结构化输出优先 | 每个子任务独立预算 | 让摘要失败阻塞正文但不留诊断 |

### 4.2 错误分类与收敛

- `rate_limit/provider_jitter`：读取 Retry-After，指数退避 + 抖动，消耗重试预算。
- `timeout`：正文默认不对同一大请求重发；长篇改为缩小当前段或恢复下一尝试。
- `structured_output_unsupported`：记录模型能力，降级为 `json_object`/纯文本解析，并限制修复次数。
- `provider_auth/bad_request`：立即结构化失败，不重试。
- `contamination/quality_gate`：只允许受控、带新 cache key 的局部/清洁重试；不携带污染原文。
- 所有 Provider 调用必须记录模型、阶段、尝试次数、输入/输出估算 token、耗时、错误码和 request fingerprint；不得记录密钥或完整敏感 prompt。

## 5. 恢复边界与状态契约

### 5.1 状态机

```text
queued → running → cancelling → cancelled
                  ├→ succeeded → waiting_for_confirm → finalized
                  ├→ evaluation_failed → retryable/confirmed_blocked
                  ├→ failed → retryable/terminal_failed
                  └→ stale → recovered(running) / terminal_failed
```

约束：终态不可复活；取消请求先写 TaskRuntime，再释放章节 claim；worker 每次写入前校验 `task_id + lease_version + run_id`；迟到回调只能写诊断，不能推进正文或终态。

### 5.2 恢复矩阵

| 中断点 | 可恢复数据 | 恢复动作 | 验收结果 |
|---|---|---|---|
| 队列入队前 | generation_spec | 任务失败并可重试 | 不留下 generating |
| Provider 调用中 | 当前段未确认 | 取消当前调用，不推进 checkpoint | 不重复确认段 |
| 段完成、checkpoint 前 | 段正文在内存 | 任务不可宣称成功，需重试该段 | 可能重复 Provider，但不重复落库段 |
| checkpoint 已提交 | plan + checkpoint + 段记录 | 从 `next_segment_index` 继续 | 已确认段不重写 |
| 质量门阻断 | blocked candidate + gate | 重试当前候选/人工处理 | 不进入正式正文 |
| 定稿计算中 | finalization session/outbox | 重放或补偿 | 正文与账本不出现半提交 |
| 进程重启 | TaskRuntime + lease | stale reconcile → claim → resume | 无重复入队、可观测终态 |

## 6. 分阶段优化计划

### 阶段 G0：证据与契约冻结（P0，先做）

1. 固定统一任务 DTO、终态、错误码、事件类型和配置版本字段。
2. 为总纲、章节纲、ChapterMission、正文版本、checkpoint、质量门、定稿 session 定义 schema 和 hash。
3. 盘点所有正文/大纲入口，标明是否真实接入 TaskRuntime；模块字典仅保留协程句柄。
4. 建立 DeepSeek 串行短章基线和真实证据目录，清理并发 smoke 造成的误判。

**退出条件**：契约测试全部通过；任一字段漂移有失败测试；真实短章 5 次连续达到终态且无跨任务事件。

### 阶段 G1：生成与任务中心收敛（P0）

1. 将长篇总纲、章节纲、正文、研究上下文等生成任务统一登记、查询、取消、恢复、重试。
2. 消除 `_OUTLINE_JOBS` 作为 API 真相源；保留内存句柄但状态来自 TaskRuntime。
3. 完成租约、幂等、取消竞态、迟到回调、重启恢复和 stale 恢复的路由级测试。
4. SSE 统一鉴权、游标回放、心跳、终态关闭，正文 delta 与日志分离。

**退出条件**：同一幂等键一个任务；双项目 20 轮并发无串线；重启后任务可查、可恢复或给出明确终态。

### 阶段 G2：长篇大纲与章节纲工程化（P0）

1. 多卷骨架先结构化生成，再章节骨架生成；每阶段有 checkpoint 和 schema 校验。
2. 完成长线、卷线、章节依赖、角色弧、伏笔矩阵和节奏预算校验。
3. 章节纲派生 ChapterMission，绑定版本 hash 和下一章约束。
4. fallback 改为显式草稿，不得保存为生产级完成。

**退出条件**：目标 120 章的模拟大纲包含完整卷、章、主线、至少 2 条暗线、角色弧和伏笔映射；非法字段能阻断保存。

### 阶段 G3：短章/中长章质量与成本（P0/P1）

1. 短章默认单首稿；污染重试和质量门按预算收敛。
2. 中长章启用局部修订优先，保留前后版本差异和评分。
3. 建立人工标注质量集，校准事件密度、场景兑现、钩子、重复和污染规则。
4. 明确 waiting_for_confirm 与 finalized 的产品语义，前后端统一。

**退出条件**：真实短章 10 次串行成功率 ≥90%，正文下限 100%，污染正文 0，单次无意义整章重写 0；核心质量评分 ≥90/100。

### 阶段 G4：20k 分段与恢复（P0）

1. 真实分段任务记录每段 checkpoint、content_delta、token、耗时和质量门。
2. 增加可控故障注入：段 2 后断进程、Provider 超时、数据库 checkpoint 失败、取消竞态。
3. 验证恢复同一 plan key、同一项目、同一版本上下文，禁止整章回退。
4. 将大正文产物从任务 payload 中拆到可寻址产物/段表，事件只存引用和摘要。

**退出条件**：真实 20k 任务 3 次连续完成；至少一次段中断后恢复；最终正文顺序正确、无重复段、SSE 无漏片/重片；核心评分 ≥90/100。

### 阶段 G5：连续 10 章与定稿闭环（P0）

1. 用真实 DeepSeek 生成并正式定稿 1→10 章，不注入摘要/记忆替身。
2. 每章确认后写入版本、摘要、人物状态、时间线、因果、伏笔、快照和质量报告。
3. 引入 finalization session/outbox，支持定稿后账本失败补偿和重放。
4. 逐章验证下一章读取前序全部必要事实，尤其远距伏笔和角色知识边界。

**退出条件**：10 章无丢章、无串线、无硬事实回滚；任意一章定稿后重启，下一章上下文一致；所有核心项 ≥90/100。

### 阶段 G6：发布审计（P0）

1. 后端全量 pytest、compileall；前端三项门禁连续两轮通过。
2. 串行真实短章、10 章连续、20k 分段、双项目并发、配置生效、导入导出全部留存脱敏证据。
3. 统计 P50/P95 延迟、Provider 错误率、重试次数、任务恢复成功率、SSE 事件完整率、正文重复率和质量分。
4. 未完成项必须有用户可见提示、可重试动作、错误码和审计记录。

## 7. 质量评分模型（100 分）

| 维度 | 权重 | 90 分门槛 |
|---|---:|---|
| 内容可用性 | 20 | 字数达标；正文无协议污染；场景有行动、冲突和后果 |
| 跨章连续性 | 20 | 前章事实、人物状态、时间线、知识边界不矛盾 |
| 长线/伏笔 | 15 | 本章任务兑现；到期伏笔有揭示与后果；无 major 逾期 |
| 结构与节奏 | 15 | 事件密度达标；章内状态变化；章末压力/钩子有效 |
| 质量门与评审 | 10 | blocker 归零；修订不丢锚点；评分证据可复核 |
| 恢复与数据一致性 | 10 | checkpoint、版本、账本、任务终态一致；重启不重写 |
| 性能与成本 | 5 | 调用次数在预算内；无无限等待；P95 在目标内 |
| 可观测与体验 | 5 | SSE delta/log 分离；阶段、错误、剩余动作清晰 |

**硬性扣分/直接不准入**：跨项目串线、取消复活、终态伪造、正文污染、章节丢失、checkpoint 跳段、major 伏笔状态伪造、定稿半提交任一项出现，直接判 P0，不得用平均分抵消。

## 8. 真实验收脚本设计

### 8.1 串行短章脚本

基于 `backend/scripts/real_asgi_generation_smoke.py`，新增可重复运行模式：

1. 每轮创建隔离 SQLite、登录、创建项目、提交 1200 字短章。
2. 轮询持久化状态，记录阶段变化、耗时、终态和错误码。
3. 直接消费认证 SSE，验证 `content_delta`、终态事件、游标单调递增。
4. 使用 `Last-Event-ID` 重连，验证无旧事件、无漏片、无跨任务 ID。
5. 查询数据库验证正文版本、调用指标、质量门、配置版本和任务状态。
6. 连续运行 10 轮；任一 `evaluation_failed` 必须打印 blocker 和命中片段，不能只输出失败字符串。

### 8.2 真实 1→10 章连续脚本

1. 创建一个长篇项目并调用真实总纲/章节纲入口。
2. 逐章提交、等待质量门、确认/定稿；每章保存任务、版本、摘要、快照和账本证据。
3. 第 n+1 章开始前重启应用或清空进程内缓存，再从数据库恢复上下文。
4. 验证人物状态、时间线事件、因果边、伏笔状态、最近快照和前章尾部均来自同一项目。
5. 最终输出章节缺口、摘要链 hash、账本版本链、Provider 调用总数和质量评分。

### 8.3 真实 20k 分段脚本

1. `target_word_count=20000`、`segment_word_limit=4000`，固定 5 段计划。
2. 第 2 段 checkpoint 成功后故意中断 worker/关闭 lifespan；重新启动同一 SQLite。
3. 查询任务必须为 `stale` 或可恢复状态；调用 resume，验证使用同一 `plan_key`。
4. 继续消费 SSE，验证已消费段不重发；最终正文按段 fingerprint 顺序拼接。
5. 故意在第 3 段制造 Provider 超时和 checkpoint 写入失败，验证只失败当前边界、有结构化错误和可重试动作。
6. 最终验证 `TaskRuntime`、章节版本、checkpoint、事件和质量报告互相引用完整。

### 8.4 双项目并发与失败隔离脚本

1. 同一用户创建项目 A/B，提交不同题材、不同专属标记和不同字数。
2. 并发生成至少 20 轮，其中插入 A 取消、B 超时、A 重试、B 正常完成。
3. 验证每个 SSE 的 task id、project id、正文 marker、日志和版本完全隔离。
4. 使用另一用户请求 A/B 的任务、事件、版本和恢复接口，必须 403/404，不泄露存在性信息。
5. 汇总成功率、串线数、重复任务数、取消复活数、P95 延迟；任一串线/复活直接失败。

## 9. 必备回归测试矩阵

| 类别 | 必测用例 | 当前证据 | 下一步补齐 |
|---|---|---|---|
| Provider | JSON 降级、超时、限流、取消、污染清洁重试 | `test_generation_call_service.py`、`test_provider_cancel_no_hang.py` | 真实 DeepSeek 多轮统计 |
| 短章 | 字数、污染、正文流、终态、调用预算 | `test_generation_quality_guards.py`、`real_asgi_generation_smoke.py` | 10 次串行全链路 |
| 长章 | 候选、局部修订、长章密度、质量阻断 | `test_generation_quality_guards.py` | 真实中长章基准集 |
| 长篇 | 计划 hash、段门、checkpoint、取消恢复 | `test_longform_generation_service.py` | 真实进程重启恢复 |
| 连续性 | 1→10 摘要/快照/记忆/时间线/图谱 | `test_multi_chapter_continuity_production.py` | 真实 Provider 1→10 |
| 大纲 | 规模、解析、结构校验、展平 | `test_long_novel_outline_generator.py` | 非法结构阻断和任务化路由 |
| 定稿 | 失败回滚、摘要、快照、幂等 | `test_finalize_session_safety.py` 等 | outbox/补偿和真实长章定稿 |
| 任务 | 取消竞态、重复提交、租约、stale、SSE 回放 | `test_task_runtime.py`、路由测试 | 全入口统一 TaskRuntime |

## 10. 验收门禁与发布准入

### 领域 B 阶段验收

- G0/G1：任务状态与事件一致性 100%，无终态复活、无跨项目事件。
- G2：长篇总纲和章节纲结构 blocker 为 0；每章可导出 ChapterMission 和版本 hash。
- G3：真实短章 1200 字，正文不少于 900 字；连续 10 次成功率 ≥90%；污染 0；单章首稿调用不超过预算。
- G4：真实 20k 章节至少 3 次连续成功；至少一次中断恢复；无重复段、无漏段、无 checkpoint 跳跃。
- G5：真实 1→10 章全部正式定稿；每章下一章上下文读取正确；major 伏笔无未处理。
- 所有核心功能评分 ≥90/100；任何 P0 直接阻断，不得以平均分放行。

### 发布前总门禁

1. 后端正式命令 `backend\\.venv\\Scripts\\python.exe -m pytest -q` 连续两轮通过。
2. `backend\\.venv\\Scripts\\python.exe -m compileall -q backend\\app` 或等价后端目录命令通过。
3. 前端 `npm run type-check`、`npm run test:run`、`npm run build-only` 连续两轮通过。
4. 真实 DeepSeek 短章、10 章连续、20k 分段、双项目并发、配置即时生效和导入导出往返均有脱敏数据库证据。
5. 剩余风险必须列出影响、触发条件、用户提示、重试动作、负责人和下一阶段关闭条件。

## 11. 本轮审查验证记录

- 已执行代码静态盘点：核心编排、长篇契约、上下文、质量门、定稿、路由和真实脚本均已逐文件核对。
- 已确认模型配置：`deepseek-v4-flash-free`。
- 已确认历史交接基线：回归测试曾为 76 项全通过，但真实短章曾同时出现成功与 `evaluation_failed`，故本计划不将其写成全绿。
- 本轮首次验证命令因在 `backend` 工作目录下错误使用了 `backend\\.venv` 相对路径而未执行测试；正确命令应为：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\\.venv\\Scripts\\python.exe -m pytest -q app/services/test_longform_generation_service.py app/services/test_long_novel_outline_generator.py app/services/test_multi_chapter_continuity_production.py app/services/test_generation_quality_guards.py app/services/test_provider_cancel_no_hang.py app/services/test_generation_run_rebind.py
.\\.venv\\Scripts\\python.exe -m compileall -q app/services app/api/routers
```

- 本文没有修改任何业务代码；只新增本审查计划文件。

## 12. 下一执行顺序

1. 先按正确路径重跑领域 B 定向测试与 compileall，并记录真实结果。
2. 修复/统一大纲、章节纲、正文三类入口的 TaskRuntime 真相源和终态语义。
3. 做串行 DeepSeek 短章基线，再做真实 1→10 章连续验收。
4. 增加 20k 进程重启与故障注入验收，再做双项目并发统计。
5. 最后实现定稿 outbox/补偿和长章完整摘要输入，才可进入领域 B 发布准入。
