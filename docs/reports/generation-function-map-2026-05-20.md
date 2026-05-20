# 玄穹文枢生成/重写与工作台重构报告（2026-05-20）

## 外部借鉴

- Sudowrite Story Bible：把 synopsis、characters、outline、scenes/prose 当作写前事实源分层注入，适合作为“长篇上下文包”的方法参考。参考：https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC
- StoryLine：核心启发是 setup/payoff 伏笔闭环和 Validator，不照搬架构，只把“写前任务 + 写后检查”接入现有蓝图、章节和记忆模型。参考：https://storyline.pixero.com/
- OpenAI Structured Outputs、429/backoff、Prompt Caching：用于约束 JSON、provider 抖动重试、长上下文稳定复用。参考：https://platform.openai.com/docs/guides/structured-outputs 、https://help.openai.com/en/articles/5955604-how-can-i-solve-429-too-many-requests-errors 、https://platform.openai.com/docs/guides/prompt-caching

## 可靠调用工具箱说明

`generation_call_service.py` 不是“中央调度员”。大白话说，它只是把每个生成服务都会重复踩坑的脏活做成一把公用扳手：重试、退避、JSON 修复、超时、错误归因、运行进度上报。大纲、蓝图、章节大纲、正文、评审、抽取这些业务流程仍然由各自服务决定怎么生成，不把所有创作决策塞进一个中心。

## 功能地图

| 功能 | 前端入口 | API 路由 | 核心服务 | 关键改造 |
| --- | --- | --- | --- | --- |
| 大纲/蓝图生成与重写 | 蓝图页、写作台生成入口 | `backend/app/api/routers/novels.py` | `NovelService`、`generation_call_service.py` | 增加长度 contract，阶段拆成概念、设定锁定、角色规模、主支线、伏笔规划、章节计划；修复 12 章误扩为 390 章。 |
| 章节大纲生成/重写 | 章节大纲按钮、写作台章节区 | `backend/app/api/routers/novels.py`、`writer.py` | `NovelService`、`writer.py` | 分批生成可执行章节大纲，重写时保留 `narrative_phase`、`chapter_role`、`foreshadowing_tasks`、`continuity_notes` 等执行字段。 |
| 正文生成/重写 | `WritingDesk.vue`、`ChapterGenerating.vue` | `backend/app/api/routers/writer.py` | `pipeline_orchestrator.py`、`longform_context_service.py`、`finalize_service.py` | 写前装配项目记忆、章节快照、角色状态、时间线、伏笔/线索和知识图谱；默认整章连贯输出，超长才允许场景组并强制融合验收。 |
| 优化/局部重写 | 写作台优化入口 | `backend/app/api/routers/optimizer.py` | `self_critique_service.py`、`consistency_service.py`、`enrichment_service.py`、`preview_generation_service.py` | 局部窗口 + 前后锚点 + 修后连续性验收；自动流程不把整章重写当兜底。 |
| 伏笔/线索闭环 | 伏笔页、线索页、写作台故事账本 | `foreshadowing.py`、`clue_tracker.py`、`writer.py` | `foreshadowing_tracker_service.py`、`longform_context_service.py` | 写前注入必须回收/强化/禁忘任务，写后弱回收给 warning 和局部补丁建议。 |
| 角色/势力/图谱 | 蓝图角色、知识图谱页、写作台侧栏 | `knowledge_graph.py`、`novels.py` | `novel_service.py`、`knowledge_graph_service.py` | 角色规模受长度 contract 控制，旧占位角色清洗；蓝图关系同步为图谱边，删除被裁掉的旧占位图谱节点。 |
| 生成状态日志 | `ChapterGenerating.vue` | `writer.py` runtime events | `pipeline_orchestrator.py`、`generation_call_service.py` | 扩展 `kind/title/summary/content_preview/metrics/artifact_refs`，详细日志显示生成状态、草稿片段、评审修复和连续性检查，不再只看程序日志。 |

## Active 与 Legacy 路径

- Active 路径：`novels.py`、`writer.py`、`optimizer.py`、各评审/抽取/记忆服务都逐步接入 `call_generation_text/json` 或 prompt 包装函数。
- Legacy 风险已清理：`rg "llm_service\.(generate|get_llm_response)|get_llm_response\(|\.generate\(" backend/app -g "*.py"` 当前只剩 `generation_call_service.py`、底层 `llm_service.py` 和测试替身。
- 保持兼容：对外 API 尽量只新增可选字段和更清晰的 runtime event，不改用户主要操作方式。

## 生成/重写质量改造

- 大纲/蓝图：新增 `_make_length_contract`、`_normalize_length_contract_candidate`、`_extract_stored_length_contract`，用户显式篇幅优先；旧蓝图只能读取已保存的 `length_contract`，不能从 `expected_chapter_range: 346-390章` 反向污染新任务。
- 章节大纲：按真实章节数分批，12 章项目生成 1-4、5-8、9-12 三批，并进行润色；重写后补齐执行字段，避免章节大纲只是摘要。
- 正文：所有篇幅都启用跨章连续性包，不再是“百万字特供”；第 2、3 章实跑能承接前章事件、案件和角色动向。
- 优化：`optimizer.py` 加入开头/结尾锚点保护，丢失锚点时回退原文；优化提示强调保留事件顺序、因果链和章尾钩子。
- 伏笔：弱回收不判失败，但记录 `due_foreshadowing_payoff_weak` 和 `strengthen_payoff_patch`，让系统给局部补丁而不是整章推翻。
- 角色：短篇也有角色池控制；12 章项目保留 11 个有效角色，不再残留“线索持有者13/补强角色位13”这类占位。
- 知识图谱：`BlueprintRelationship` 同步为 `EventEdge`；清洗旧占位节点后，实跑项目图谱为 11 节点、26 边。

## 前端与日志

- 写作台：重排 `WDHeader.vue`、`WDSidebar.vue`、`WDWorkspace.vue`，保留一个主命令栏；侧栏转为章节导航/故事账本；项目体检默认收敛。
- 生成日志：`ChapterGenerating.vue` 改成“生成状态日志”，分为简略日志、生成进展、草稿预览、评审修复、诊断详情；简略日志加入轻量图案和短句，详细日志显示内容预览。
- 按钮与视觉：加入 `lucide-vue-next`，统一按钮大小、间距、圆角和字体层级，减少重复主按钮。
- 验证截图：
  - `docs/reports/web-validation-writing-desk-desktop-final-2026-05-20.png`
  - `docs/reports/web-validation-writing-desk-mobile-final-2026-05-20.png`
  - `docs/reports/web-validation-writing-desk-desktop-final-rerun-2026-05-20.png`
  - `docs/reports/web-validation-writing-desk-mobile-final-rerun-2026-05-20.png`

## 真实实跑

测试项目：`35cbd8ec-6fdb-47d1-bf6d-437970143d4e`，`Codex实跑验证-20260520`。

- 蓝图/总纲：强制重跑 novel_outline 后，`length_contract.target_chapter_count=12`，总纲 6 阶段，范围为 1-2、3-4、5-6、7-8、9-10、11-12。
- 章节大纲：强制重跑 chapter_outline 后，章节数 12，首章 1、末章 12，缺失执行字段 0。
- 正文：第 1、2、3 章生成并确认，约 3273 / 2474 / 4164 字；第 2、3 章能承接前章事件。
- 章节大纲重写：第 2 章重写成功，标题变为“泡胀手札、铜钥与追来的人”，保留伏笔和连续性字段。
- 优化：第 1 章 rhythm 优化成功，明确保护开头/结尾锚点、事件顺序、因果链和章尾钩子。
- 账本：伏笔 4 条，线索 4 条，记忆快照含第 1、2 章，当前 memory version 为 3。
- 修复后清洗：蓝图角色 42 -> 11，旧占位 0；知识图谱 42 节点/88 边 -> 11 节点/26 边。

## 多视角评判与代码修正

- 作者视角：12 章作品被旧蓝图污染成 390 章会直接毁掉创作节奏。修正为显式长度 contract 优先，并新增英文 `12-chapter` 解析测试。
- 编辑视角：章节大纲只有摘要不够执行。重写保留叙事阶段、情绪推进、冲突升级、伏笔任务和连续性备注。
- 读者视角：优化阶段切太碎会破坏阅读连续性。改为局部锚点修补，丢锚点时不接受优化稿。
- 连续性审校视角：不能只看相邻章节。所有篇幅写前都装配长期上下文，写后更新记忆/伏笔/图谱。
- 系统稳定性视角：provider 抖动、JSON 坏格式和散落调用会导致失败难定位。统一接入可靠调用工具箱，并扩展 429/5xx 重试、JSON 修复失败提示和错误归因测试。

## 测试与验证

- 已通过：`python -m pytest backend/app/services/test_longform_context_service.py -q`，6 passed。
- 已通过：`python -m pytest backend/app/services/test_blueprint_observability.py -q`，96 passed。
- 已通过：`python -m compileall backend/app`。
- 已通过：`python -m pytest backend/app/services/test_generation_call_service.py backend/app/services/test_longform_context_service.py backend/app/services/test_generation_quality_guards.py backend/app/services/test_blueprint_observability.py backend/app/services/test_writer_route_regressions.py -q`，141 passed。
- 已通过：`cd frontend; npm run test:run`，108 passed。
- 已通过：`cd frontend; npm run build`。
- 浏览器验证：桌面、移动写作台均可加载，控制台 error 为 0，横向溢出为 false；生成日志面板由 `ChapterGenerating.spec.ts` 覆盖，实跑章节 runtime events 已确认包含 `content_preview`。
- 待最终收口：本地提交并推送。
