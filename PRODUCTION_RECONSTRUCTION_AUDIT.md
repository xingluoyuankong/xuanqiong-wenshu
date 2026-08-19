# 玄穹文枢生产级重构审计台账

> 基线日期：2026-08-13（上一轮 2026-08-12）。该台账替代所有“已全绿/生产就绪”的未验证结论；保留现有未提交改动，不执行 reset、硬删除或不可逆数据变更。

## 1. 已验证基线

| 门禁 | 实测结果 | 结论 |
|---|---:|---|
| 后端测试（本轮实测） | 524 通过，0 跳过 | 基础回归全绿，但不等于生产验收完成 |
| 后端 Python 编译 | `python -m compileall -q app` 通过 | 静态导入门禁通过 |
| 应用真实启动（2026-08-12 实测） | lifespan 启动 + `/api/health` 200 + 干净关闭 | 迁移链 000→003 实跑升级；启动巡检与定期巡检已挂载 |
| 前端类型（2026-08-13 实测） | `npm run type-check` 通过 | 仍需真实链路验收 |
| 前端单测（2026-08-13 实测） | 37 个文件、138 个测试全部通过 | Vitest 已限制 maxWorkers=2、minWorkers=1 |
| 前端生产构建（2026-08-13 实测） | `npm run build-only` 通过 | 仍需运行时与主流程验收 |
| 工作区 | 以 `git status --short` 为准 | 必须逐项验证，禁止回滚覆盖 |

### 2026-08-13 本轮：长篇分段切片串段与前端正文分流

本轮修复两个此前未被任何测试覆盖的 P0 缺陷，均属“看起来在工作但实际错误”的类型。

**1. 分段 delta 切片会串段（后端）**

`PipelineOrchestrator._extract_segment_text` 原实现用 `assembled[-char_count:]` 取正文，
只有末段可能正确；各段长度接近时，第 N 段会切出邻段内容，导致推送给前端的 `content_delta`
夹带其他段正文。改为按累计偏移 `offset += char_count + len("\n\n")` 定位任意段起点，
旧快照缺 `char_count` 时回落到按 `\n\n` 切分取对应位置。
新增 `test_extract_middle_segment_does_not_leak_neighbors`（三段等长）锁死该回归。

**2. 前端完全丢弃 content_delta（前端）**

后端已按 `content_delta` / `log` 严格分流并通过 SSE 下发，但前端此前**没有任何消费者**：
`taskRuntimeEventToChapterEvent` 只把 payload 塞进 `metadata`，正文分片既不进正文区也不入日志区，
等于正文流在 UI 层静默丢失。本轮：

- 正文提取与事件映射从 `WritingDesk.vue` 抽到 `utils/chapterGeneration.ts`
  （`extractContentDelta` / `taskRuntimeEventToChapterEvent`），使分流判定可脱离视图单测；
- 严格分流以 `event_type === 'content_delta'` 为唯一判据：日志/进度事件即使 payload 夹带
  `delta`/`content_delta`/`content`，也一律不得冒充正文；
- `ChapterGenerating.vue` 新增 `streamedChapterBody`，按 `segment_index` 累积并去重多段正文
  （同段重试覆盖，保证幂等），替代原先“只显示最新一条 content_preview”导致只能看到最后一段的行为；
  `preview=true` 的整章预览分片不参与累积，仅作兜底显示。
- 删除 `ChapterGenerating.vue` 内一段永不生效的 SSE 死代码（依赖从未传入的 `projectId` prop，
  且写入的两个 ref 无人读取）。SSE 订阅者现在唯一，由 `WritingDesk.vue` 按 `task_id` 持有。

因两条路径（`applyTaskRuntimeSnapshot` 事件回放与实时 SSE）共用同一映射函数，
刷新、断线重连与后端重启后的正文续接行为一致。新增 9 项前端回归（组件 3 项 + 工具 6 项）。

仍未验收：真实 Provider 下 2 万字分段章节的端到端正文流、10 章连续链路。

### 2026-08-13 本轮：连续性链路从 5 章扩到 10 章

`test_production_multi_chapter_short_and_long_continuity_chain` 此前只跑 1→5 章
（循环 `range(1, 5)` + 第 5 章单独收口），与目标“正式路径连续生成至少 10 章”不符，
属于用窄验证支撑宽结论。本轮把 `CHAPTER_BEATS` 从 5 拍扩到 10 拍（旧京验档、顾棠断线、
血契三日、诏狱夺人、夜雨归令），循环改为 1→9 且第 10 章单独收口，并新增三条更强断言：

- 全部 10 章摘要都必须出现在第 11 章的历史摘要链中，缺任意一章即失败（长程上下文不得断裂）；
- 第 10 章上下文包的 `recent_snapshots` 最大章号必须等于 9（近期快照必须跟到最新已完成章）；
- 库中必须存在第 1—10 章的完整 `ChapterSnapshot` 集合（逐章定稿不得中途丢章）。

每章仍逐章走 FinalizeService 定稿并校验摘要、`ProjectMemory.global_summary`、
`last_updated_chapter`、章节快照、时间线、因果边、伏笔任务与连续性质量门。
实测：`app/services/test_multi_chapter_continuity_production.py` 2 passed；后端全量 509 passed。

仍未验收（不因本轮扩容而降低标准）：该链路使用受控 beat 内容与 monkeypatch 的定稿依赖，
驱动的是 FinalizeService/LongformContextService 而非 HTTP 任务中心入口；
真实 Provider 下的 10 章正文生成、单章 2 万字分段实跑、导出再导入一致性仍未完成。

## 1.1 本轮已完成并确认的修复

- 共享 `task_session` fixture 已移至 `backend/conftest.py`。
- 后端长期跳过项已清零：云端 Provider、缓存键、取消、run 重绑定、流式 reasoning 兜底、项目账本租约、线索/知识图谱、章节配置、结构质量门、多章节连续性。
- 已增加 `ProjectLedgerSyncLease` 与线索/知识图谱一致性 overview 接口。
- LLM Provider 字段清洗、流式 reasoning 兜底、生成 run 重绑定、定稿摘要回写、历史上下文污染修复已通过现有回归。
- 已有 `TaskRuntime` 模型、服务、API 和 Alembic `000`—`003` 迁移链；新增按用户/项目/章节筛选的任务恢复查询、持久化日志事件适配器、SQLite 时间戳兼容和长篇分段计划、真实分段执行器/质量门/断点恢复契约。章节正文、蓝图、章节纲、研究、导入、文风任务已开始镜像到 TaskRuntime，但仍存在内存兼容索引，不能宣称唯一任务中心或生产就绪。

### 2026-08-12 本轮：重启恢复真相源

已修复一个此前未记录的 P0 缺陷：`main.py` 的 `cleanup_stuck_chapters_on_startup` 会在每次启动时
无条件把所有 `generating` 章节改写为 `draft`。该逻辑不查 TaskRuntime，因此会：

1. 杀掉其他实例/仍持有活跃租约的运行中任务；
2. 丢弃 run_id、阶段与事件游标，使断点恢复不可能；
3. 静默改状态，前端无法区分“被重置”与“从未生成”。

替换为 `app/services/task_reconciliation.py` 的 `TaskReconciliationService`，以持久化租约/心跳为唯一判据：

- 心跳超时的 `running`/`cancelling` 任务标记为 `stale`，可由 `recover` 重新领取；
- 章节 TaskRuntime 仍活跃时**保留**该章节，不再误杀；
- 仅当任务已终态或无任务记录时，才把 busy 章节释放为 `failed`，并保留 run_id、阶段、事件历史与
  `allowed_actions`，前端可展示“可重试/可恢复”。

同时新增周期性僵尸任务巡检（`TASK_RECONCILE_*` 配置，默认 180s 超时 / 120s 间隔），
以及 7 项回归测试（`app/services/test_task_reconciliation.py`），显式覆盖“活跃任务不得被启动清理杀掉”。

### 2026-08-12 本轮：章节大纲任务重启去重

`start_chapters_outline_generation` / `start_chapter_outline_rewrite` 此前只查内存
`_OUTLINE_JOBS`，进程重启后内存清空即可对同一项目**重复入队**，造成重复 LLM 调用与大纲互相覆盖；
`.../outline/status` 也会在重启后错报 `idle`。

已按旧稿导入的既有模式补齐持久化恢复：新增 `_load_active_outline_job_from_runtime`，
在内存未命中时按 `owner_user_id + project_id + 未完成状态` 查 TaskRuntime 并还原任务视图
（run_id / 阶段 / 进度 / 事件历史）。三处入口（生成 start、重写 start、status）统一接入。

新增 4 项回归（`app/api/routers/test_outline_job_restart_recovery.py`）覆盖：
活跃任务不重复入队且不新建 TaskRuntime、重启后 status 不报 idle、
终态任务不得阻塞新任务、他人任务不得占用当前用户入口。

## 1.2 当前边界

当前结果是“基础测试与构建全绿 + 迁移链已版本化 + 生产化重构进行中”，不是最终生产就绪。任务中心主链、SSE 正文分流、长篇分段恢复、10 章正式链路和导入导出一致性仍需继续实测。

## 2. 全功能矩阵与现状

| 功能域 | 已有模块 | 当前生产风险 | 优先级 |
|---|---|---|---|
| 项目、小说、导入导出、阅读、版本 | `novels.py`、项目/写作台视图 | API 字段和前端类型漂移 | P0 |
| 灵感、蓝图、总纲、章节纲 | `novels.py`、`writer.py`、蓝图/长篇大纲服务 | 仍有内存调度，尚未全部接入 TaskRuntime | P0 |
| 正文生成、续写、改写、候选、评审 | `writer.py`、`pipeline_orchestrator.py` | 进程内调度；自动按最长正文覆写评审语义 | P0 |
| 长篇连续性、记忆、账本、伏笔、时间线 | longform/memory/consistency 服务 | 基础回归已覆盖；10章正式链路和原子恢复仍未完成 | P0 |
| 研究资料、文风、人物、势力、图谱 | research/style/graph 服务 | overview 快照已接入；研究主链仍有内存任务状态 | P1 |
| 实时日志、正文流、进度、取消恢复 | updates、writer SSE、TaskRuntime | 日志已桥接到持久化 LOG 事件并支持游标续接；正文 SSE 支持鉴权、Last-Event-ID、心跳；前端已统一 fetch-SSE 续接，但正式入口仍保留兼容内存索引 | P0 |
| 并发、配置、模型、限额 | 配置服务/同步管理 | 进程内订阅、锁和信号量，跨实例无效 | P0 |
| 管理、权限、系统配置 | admin/auth 及管理视图 | AdminView 已通过当前单测；权限与生产部署边界仍需实跑 | P1 |
| 前端工作台、导航与可访问性 | WritingDesk、WDSidebar、WDWorkspace | 左侧导航事件未接线；重复进度面板；大组件难维护 | P1 |

## 3. 已确认缺陷

### P0：必须先清零
1. 蓝图、章节纲、正文、研究、文风、导入已接入 TaskRuntime 镜像。去重路径现状（2026-08-12 逐行核对）：
   - 蓝图 `start`：已通过 `_load_latest_blueprint_job` 读库去重，不依赖内存，无重启重复入队问题；
   - 旧稿导入：已有 `_load_persisted_import_job` + `_rebuild_import_job_from_runtime`；
   - 章节大纲（生成/重写/status）：本轮补齐 `_load_active_outline_job_from_runtime`；
   - 研究 `status`/`cancel`：内存未命中即回落 DB artifact + `TaskRuntimeService.get_task`；
   - 文风：已有 `_load_persisted_style_job` + `_rebuild_style_job_from_runtime`。

   即六类任务入口均已具备"重启后不重复入队/不错报 idle"的读库去重路径。内存字典退化为热路径缓存，
   但尚未物理移除，仍需在真实多章链路上验收后才可宣称唯一任务中心。
2. 正文内容增量与运行日志尚未在所有正式入口彻底分流，需完成 SSE 主链路与断线恢复实测。
3. 长篇多卷连续生成、单章 2 万字分段、取消/重启恢复、导入导出一致性尚未完成正式验收。
4. 配置版本回读、跨实例租约、僵尸任务巡检和多项目并发隔离仍需生产模式验证。

### P1：进入发布前清零
1. Alembic 已建立 `000_initial_schema` 至 `003_schema_compatibility` 链，并实测 fresh/重复升级/降级/旧库兼容；后续仍需把所有业务任务入口迁入唯一 TaskRuntime。
2. `pipeline_orchestrator.py`、`writer.py`、`novels.py` 仍职责混杂，需在不破坏主流程的前提下拆分。
3. 记忆、伏笔、图谱等定稿后更新仍缺少完整可恢复 outbox。
4. 前端 overview 快照已接入，工作台完整导航、状态统一和长文本增量保存仍需运行时验收。

## 4. 实施顺序、准入与评分

1. **契约与测试基础**：统一响应/错误/分页/任务事件 DTO；修复前端 type-check、build、测试；后端默认收集 services 与 routers。
2. **持久化基础**：建立 Alembic；补任务、事件、租约、outbox 的迁移及索引/外键/幂等约束。
3. **唯一任务中心**：所有生成/研究任务以 TaskRuntime 创建、心跳、取消、重试、恢复；移除模块级 dict/Lock/Semaphore 作为真相源。
4. **事件与实时体验**：统一 `task_id + event_id(cursor) + stage + progress + log + artifact_ref`，SSE 断线回放、心跳、权限校验；轮询仅降级。
5. **长篇生成链路**：拆为 mission、上下文包、分段草稿、评审选择、定稿/outbox；章节数万字用可恢复分段，禁止单次超长调用。
6. **逐项生产化**：每项执行实现 → 单测 → 集成 → 实跑 → 评分 → 修复 → 复测。评分：可用性20、契约15、错误恢复15、性能并发15、一致性15、测试10、体验10；单项不得低于90。
7. **真实验收**：正式应用路径完成新建、长篇总纲、10章章节纲、连续1–10章、取消、重启恢复、配置生效、2万字分段章节、导入导出。无 P0、无静默失败、无跨项目串状态才可发布。

## 5. 本轮新增修复闭环

- `TaskRuntimeService.list_tasks` 与 `/api/task-runtime/tasks` 支持按用户、项目、章节、状态筛选，供刷新/重启恢复使用。
- `PersistentGenerationLogService` 将旧日志 API 写入持久化 LOG/终态事件；未知任务读取不会隐式创建，且 `/stream/tasks` 路由顺序已修正。
- 长篇正式章节入口在任务中心写入分段计划、plan key、段数和初始 checkpoint；该计划契约已通过单测，但正式多段 LLM 编排已接入 PipelineOrchestrator，支持每段取消检查与 checkpoint；但真实 Provider 下的 2 万字章节、重启续跑和原子定稿仍未完成验收。
- 后端全量实测：527 passed，0 skipped；compileall 通过；本轮未把项目误写成生产就绪。

下一轮继续从唯一 TaskRuntime 真相源、正式分段执行器、进程重启恢复和真实主流程验收推进，禁止以报告替代验证。

## 6. 2026-08-14 本轮：核查结论与新发现缺口

### 6.1 复核为「已满足」（有代码证据，不再重做）

| 待办 | 证据 | 结论 |
|---|---|---|
| `_rebind_generation_run_if_needed` 是否只存在于测试 | `app/services/pipeline_orchestrator.py:2120` 在 `generate_chapter` 内调用；`app/api/routers/writer.py:2806` 是唯一后台生成调用点，重试/恢复共用该入口 | 正式路径已生效 |
| LLM sanitizer 是否流式与非流式都清洗 | `app/utils/llm_tool.py:93`（`stream_chat`）与 `:177`（`chat`）都在 `completions.create` 前调用 `_sanitize_chat_payload` | 两条路径均已清洗 |
| overview 是否单次一致性快照 | `components/clue-tracker/ClueTrackerView.vue:192`、`components/knowledge-graph/KnowledgeGraphView.vue:273` 各仅一处 `getOverview`，由 `onMounted` + `watch(projectId)` 触发 | 无重复同步链 |
| `ProjectLedgerSyncLease` 迁移 | `alembic/versions/002_ledger_lease_and_runtime_metrics.py`，链 `000→001→002→003`，有 `test_alembic_migrations.py` | 已有正式迁移 |

### 6.2 新发现的真实缺口

**1. 内存任务字典仍是状态真相源，「唯一任务中心」不成立（P0，未修完）**

六处进程内字典仍与 TaskRuntime 并存：`_RESEARCH_JOBS`/`_RESEARCH_TASKS`（`research.py:22-23`）、
`_BLUEPRINT_JOBS`/`_IMPORT_JOBS`（`novels.py:49,66`）、`_OUTLINE_JOBS`（`writer.py:100`）、
`_STYLE_PROFILE_JOBS`/`_STYLE_SOURCE_UPLOAD_JOBS`（`style.py:36,41`）。
其中 `get_research_job_status` 命中内存即直接返回，完全绕过 TaskRuntime，
进程内与持久化状态可长期分叉。目标状态是内存字典仅作 asyncio.Task 句柄与读缓存，
对外状态一律以 TaskRuntime 为准。

**2. 历史基线：研究任务取消状态机不一致（本轮已修）**

`research.py` 取消时把内存态直接写成终态 `cancelled`，而 TaskRuntime 侧 `request_cancel`
只会置 `cancelling`。协作状态语义要求「请求取消 → cancelling → worker 收敛 → cancelled」，
否则前端会在 worker 仍在跑时看到终态，取消与恢复语义失真。

**3. 历史基线：导出再导入往返一致性无实现也无测试（当前已补 TXT 结构元数据与基础回归，但深度业务表集成仍未修完）**

`ExportService` 只做 TXT/DOCX 文本拼接，导出格式为 `\n{title}\n` + `-`*30；
`ImportService._split_into_chapters` 用 `^\s*第[数字][章卷回节]` 正则切章。
两者未做契约对齐，且摘要、账本、版本在往返中无任何校验。
验收标准「导出全文并重新导入后，章节、摘要、账本和版本数据一致」目前无证据支撑。

## 本轮续接实测门禁（以当前工作区为准）

- 后端全量：`backend/.venv/Scripts/python.exe -m pytest -q` → **527 passed**。
- 前端类型：`npm run type-check` → **通过**。
- 前端单测：`npm run test:run` → **37 files / 138 tests passed**。
- 前端构建：`npm run build-only` → **通过**；自动组件声明已改写入 `src/components.d.ts`，规避 Windows 根目录写入失败。
- 研究任务：已接入持久化 claim、heartbeat、取消检查、终态收敛及 queued/stale 轮询续跑；定向测试和租约拒绝反向验证通过。
- 文风任务：画像/素材 worker 已接入 claim、heartbeat、取消事件和画像任务恢复调度；上传 bytes 已按项目/run_id 持久化，状态轮询可恢复 queued/stale worker；新增路径隔离、去重和 finally 清理回归，定向测试 **7 passed**。
- 旧稿导入任务：上传正文已按 user_id/run_id 持久化到 `backend/storage/novel_imports`；TaskRuntime payload 保存 storage_path，status 可在进程重启后恢复 queued/stale worker；新增严格路径隔离、单次调度和 finally 清理回归，定向测试 **12 passed**，并完成路径校验故障反向验证。
- 导出导入：TXT 机读元数据已覆盖项目基本信息、蓝图、角色、关系、章节大纲、章节多版本、正式伏笔与时间线；正式 ImportService 主链路已在真实 SQLite 集成测试中恢复项目、正文、版本、蓝图、角色、关系、伏笔、线索、时间线、快照和项目记忆。仍未覆盖所有附属账本字段及 DOCX 往返。

以上证据证明的是已验证范围，不代表整个项目最终生产就绪。真实 Provider 的多章连续生成、单章数万字实跑、重启后所有任务恢复及全功能评分仍未完成验收。

## 2026-08-13 追加实测与修复（当前工作区）

### 已完成的状态机修复

- `TaskRuntimeService.append_event` 现在禁止 `cancelling` 被迟到的
  `running/succeeded/failed` 事件复活，只允许继续保持 `cancelling` 或收敛为
  `cancelled`；新增反向回归测试，故意写入成功事件会失败。
- 章节取消接口先向 TaskRuntime 写入取消请求，再释放章节占用；研究完成事件写入
  被取消竞态拒绝时转入取消收敛；持久化日志不会把 `cancelling` 任务写回 running。
- 正式章节 worker 启动时先领取持久化租约，再写 started/running 事件，修复“活 worker
  被误判为未领取队列任务”的取消与重启恢复竞态。

### 验证结果

- 后端正确工作目录全量：`backend/.venv/Scripts/python.exe -m pytest -q`
  **557 passed**。
- 前端：`npm run type-check` 通过；`npm run test:run` **40 files / 148 tests
  passed**；`npm run build-only` 通过。
- 隔离 SQLite + Alembic `000 -> 003` + 真实 FastAPI `/api/health`：通过。
- 真实应用入口章节烟测：登录、临时项目创建、任务入队通过；任务真实进入
  `running/generate_variants` 并持续写入心跳和 Provider 等待事件，但在本次烟测窗口
  结束前未得到正文终态。该项**不判定通过**，仍需继续验证 Provider 慢响应最终是否
  按软超时收敛为成功或结构化失败。

### 当前阻塞发布的缺口

1. 真实 Provider 的短章成功终态、正文落库、SSE 增量正文和失败收敛仍未完成正式验收。
2. 多章连续生成、2 万字以上分段、重启续跑、并发多项目隔离尚未完成真实 Provider 验收。
3. 研究/文风/导入/大纲虽有持久化恢复单测，仍需分别做真实入口长等待、取消和重启烟测。
4. 内存任务字典仍存在；当前已降低为句柄/兼容缓存，但尚未完成全部入口的物理清理。

## 2026-08-13 续接：短章真实生成性能与状态源修复

### 已确认的真实行为

- 隔离 SQLite + 真实 FastAPI 应用入口的 1200 字 `enhanced` 章节曾成功落库：
  单候选、正文约 2205 字、TaskRuntime `succeeded`、正文增量事件与终态事件均存在。
- 该成功任务总耗时 **425.9 秒**，分段计时为：导演脚本约 45 秒、写前上下文约 82.5 秒、
  候选正文约 342.7 秒。后者实际为首次 Provider 超时后又进入同一上游的 stable 重试，
  不是多候选评审造成的等待。
- 第二次真实验收在短章策略收紧后，任务在首次正文调用约 108 秒软超时后又进入 stable 重试，
  最终以 TaskRuntime `failed`、`PROVIDER_SOFT_TIMEOUT` 终态收敛；无无限轮询、无僵尸 running。
  此结果证明成功率仍未达标，不能判定真实短章生产验收通过。

### 本轮已完成修复与反向验证

1. `enhanced` / `longform` 在低于 2800 字时改为单候选，避免短章无意义的评审成本；
   故意恢复旧的双候选返回值后，新增 1200 字回归用例失败。
2. 章节大纲状态查询改为按同一 `run_id` 优先重建 TaskRuntime 快照，防止旧内存
   `generating` 缓存遮蔽已取消/失败的持久化终态；故意删除该分支后回归失败。
3. `<2500` 字短章默认关闭宪法、人格、伏笔、势力四个写前 Provider 账本，前端明确传入
   开关仍优先；导演脚本不再进行额外 Provider 重试。
4. 免费兼容网关的短章软超时按目标字数收紧，1200 字正文输出上限缩至 3600；短章不再创建
   stable 同源二次重试，超时后直接返回结构化、可重试失败。故意恢复 stable 回退后测试失败。

### 本轮门禁

- 相关后端回归：**107 passed**；Python `compileall` 通过。
- 此前本轮全量门禁：后端 **568 passed**；前端类型检查、**148** 项测试及生产构建通过。
- 仍需继续：在可用 Provider 下实跑短章成功终态、10 章连续生成、2 万字分段恢复、两个项目并发，
  并逐步让研究/蓝图/文风/导入的对外状态彻底以 TaskRuntime 为真相源。

## 2026-08-13 续接：真实短章正式入口验收通过（范围有限）

### 修复与回归

- 短章质量门的“对白改变局势”由抽象任务书词匹配扩展为可验证的剧情信号：死亡揭露、二选一、离开、外部逼近等；避免真实剧情推进因未复述任务书而被误杀。
- 章末压力识别新增明确倒计时（如“三、二”）信号，修复“门外威胁 + 倒计时”被误判为平收、继而整章重写的问题。
- 新增真实剧情结构的质量门回归；两项修复均做反向验证：临时移除新增判断后对应测试分别失败，随后恢复实现。
- 验收脚本改为从数据库按 `project_id + chapter_number` 定位持久化章节，避免公开 DTO 没有数据库主键导致的假失败；同时校验版本调用指标、任务书泄漏和任务事件计数。

### 本次真实证据

- 命令：`backend/.venv/Scripts/python.exe -u scripts/real_asgi_generation_smoke.py`
- 隔离库：`real-asgi-1786618314405492300.db`。
- 登录、创建项目、正式章节提交、轮询、章节流、项目读取均通过。
- 章节：`successful`，**1221** 字；TaskRuntime：`succeeded/completed/100%`，无 error code。
- SSE：共 **29** 个事件，`content_delta=3`，`task_completed=1`，终态正常关闭；正文与日志事件保持分离。
- Provider 调用：首稿低于最低字数时发生一次可审计的 `word_count_far_below_target` 补足重试；没有 stable 同源超时重试、没有抽象任务书命中失败导致的重写。
- 本轮最新门禁：后端全量 **582 passed**；前端 `type-check` 通过、Vitest **40 files / 148 tests** 通过、`build-only` 通过。

### 仍未通过发布准入的项目

本节只证明真实 Provider 的 1200 字短章单项目入口已可完成，不代表整体生产就绪。仍缺少：真实 1–10 章连续生成与账本承接、单章 ≥2 万字分段 checkpoint/取消/重启恢复、双项目并发隔离、SSE Last-Event-ID 断线回放、配置版本真实回读、DOCX 往返与其余后台任务的真实入口恢复验收。

## 2026-08-13 续接：短章正文 JSON 规范化与 SSE 游标回放验收

### 修复范围

- 外层续写 Provider 偶发返回 `{"continuation":"正文"}` 时，旧实现会把 JSON 外壳直接拼入正式章节，继而污染质量门和最终正文。`PipelineOrchestrator._normalize_generated_prose` 现统一移除思考标签、Markdown JSON 包装并提取 `content`、`chapter_content`、`text`、`story`、`continuation` 等正文字段；首稿、兜底、分段和续写共用该入口。
- 1200 字短章的字数不足不再触发整章首稿重写，而是交由至多一次可审计续写补足；本次真实调用未触发续写。新增两条回归覆盖短章策略与 JSON 续写提取，并已临时破坏解析实现确认提取测试会失败后恢复。

### 本次真实证据

- 命令：`backend/.venv/Scripts/python.exe -u scripts/real_asgi_generation_smoke.py`。
- 隔离库：`real-asgi-1786619340789338600.db`；真实 FastAPI 入口完成登录、创建项目、章节提交、轮询、SSE 和项目读取。
- 章节终态：`successful`，正文 **1140** 字；TaskRuntime 已持久化为成功，运行阶段 `waiting_for_confirm`、进度 97%。
- SSE 全量回放：28 个事件，`content_delta=3`、`task_completed=1`；以最后正文事件游标 `27` 作为 `Last-Event-ID` 重连，只得到 1 个更大 ID 的终态事件、0 个重复正文片段，证明断线续接不重放已消费正文。
- 调用审计：`draft_calls=1`、`continuation_calls=0`、`first_draft_retry=False`，无 JSON 外壳和本地任务书文案泄漏。

### 结论与剩余限制

本项满足“真实 Provider 短章 + 持久化任务终态 + 流式正文 + Last-Event-ID 续接”的限定验收。它不覆盖双项目并发、1–10 章连续性、2 万字 checkpoint、进程重启恢复、配置版本回读和其余异步业务任务，以上仍保持 P0/P1 未完成状态。

## 2026-08-13 续接：任务中心恢复与取消竞态修复

- 研究任务 worker 不再以 `_RESEARCH_JOBS` 内存快照作为启动前提；持久化 `TaskRuntime` 成功领取租约后，即使进程重启清空缓存也会继续执行。新增回归覆盖“仅有 TaskRuntime、无内存任务”恢复，并完成反向破坏验证。
- 章节大纲取消入口在内存索引为空时会从 TaskRuntime 重建任务；新增重启后取消回归。另修复 queued 任务“已登记后台协程但尚未领取租约”的取消竞态：调用 `request_cancel(..., finalize_unclaimed=True)` 原子收敛为 `cancelled`，避免永久停留 `cancelling`。
- 定向证据：研究路由 **10 passed**；章节大纲重启/取消 **14 passed**；Python compileall 与 `git diff --check` 通过。反向验证分别证明移除研究缓存绕过和 queued 最终化会使新增测试失败。

以上只收敛了研究与章节大纲两个入口；蓝图、导入、文风已经具备持久化状态查询/取消恢复覆盖，但仍需继续做真实跨进程与双项目并发验收，不能据此宣称所有任务中心缺口已关闭。

## 2026-08-13 续接：双项目并发真实 Provider 验收通过（范围有限）

### 本次真实证据

- 命令：`backend/.venv/Scripts/python.exe -u scripts/real_asgi_concurrent_generation_smoke.py`
- 隔离库：`real-asgi-concurrent-1786620954731573100.db`；真实 FastAPI lifespan + 登录 + 双项目创建 + `asyncio.gather` 并发入队与轮询。
- 新脚本 `backend/scripts/real_asgi_concurrent_generation_smoke.py` 已通过 `py_compile` 与后端 `compileall`。
- 结论行：`CONCURRENT_SMOKE_PASS`；两任务 ID 不同；每个项目只出现自身 `task_id`。
- 项目 A：章节正文 **2229 字**，TaskRuntimeEvent **28 条**，状态 `succeeded`；项目 B：正文 **1331 字**，事件 **27 条**，状态 `succeeded`。
- 数据库断言：`Chapter`、`ChapterVersion`、`TaskRuntime`、`TaskRuntimeEvent` 的归属全部正确；项目 A 正文/事件不包含项目 B 专属 marker，反向亦然。
- SSE 断言：每个项目流只包含自己的任务事件，无跨任务正文泄漏。

### 修复与回归

- 蓝图任务的持久化 `queued/stale` 记录在进程重启后复用时不重新派发 worker，导致任务永久排队。新增 `_schedule_persisted_blueprint_recovery_if_needed`，只在同 run 的 TaskRuntime 仍为 `queued/stale` 时幂等调度；`running/cancelling` 由原租约持有者继续。
- 回归：`test_persisted_blueprint_recovery_is_scheduled_after_restart`（复用 queued 任务必须派发、running 任务不得重复派发）与 `test_blueprint_recovery_schedules_once`；反向验证：临时移除 `queued` 分支后测试失败，随后恢复。
- 定向证据：蓝图 2 passed；导入/文风 24 passed；章节大纲恢复/研究/导入/文风合计 41 passed；长篇分段/任务中心 48 passed；多章连续性/配置/日志 8 passed；SSE/取消竞态 20 passed；定稿/路由 37 passed；写作路由全量 26 passed。Python `compileall` 与 `git diff --check` 通过。

### 说明

本项证明双项目并发、正文/事件隔离、持久化任务归属隔离在真实 Provider 下可用。它不覆盖 1–10 章连续性、单章 ≥2 万字真实分段 checkpoint/重启续跑、DOCX 往返、配置版本真实回读与其余后台任务的长等待真实入口验收，以上仍保持 P0/P1 未完成。

## 2026-08-13 续接：长篇章节同任务断点恢复正式闭环

### 缺口

- 长篇分段计划与 checkpoint 已写入 TaskRuntime，但正文 worker 的生成参数（writing_notes、flow_config）只存在于调用栈；通用 `/retry` 只改状态不重新派发业务 worker，启动巡检只把心跳超时任务标记为 `stale`。

### 修复

- 普通与高级章节入口新增 `_persist_generation_execution_spec`：把最小可恢复执行规格写入同一 TaskRuntime 的 `payload.generation_spec`，持久化失败时拒绝启动任务，避免产生不可恢复的队列项。
- 新增章节专用恢复接口 `POST /api/writer/novels/{project_id}/chapters/resume`：仅接受同一用户、同一项目、同 `chapter_generation` 的 `stale` 任务，先持久化领取（`retry` 状态机），再以同一 `run_id` 与 TaskRuntime 内最新 `longform_generation.checkpoint` 重新派发 worker；不新建任务、不覆盖断点、不整章重写。
- 前端 `chapterWorkflow.ts`/`novel.ts` 新增 `resumeChapterGeneration`；写作台“重新生成”在存在持久任务 ID 时优先调用恢复接口，失败才回退全新生成，保证旧任务兼容。
- 回归：执行规格持久化、checkpoint 恢复、恢复路由复用同一 run 共 3 条定向测试；API 契约测试 1 条；类型检查通过。反向验证：临时移除 checkpoint 注入后恢复测试立即失败，随后恢复实现并重新通过。

### 仍待验收

真实 Provider 下的 1–10 章连续生成和单章 ≥2 万字分段 checkpoint/取消/进程重启续跑仍是正式验收对象；本闭环保留了同一任务断点续跑的执行路径，但尚不能宣称已用真实 Provider 完成该验收。

