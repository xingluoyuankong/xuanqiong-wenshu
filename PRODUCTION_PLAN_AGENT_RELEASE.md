# 玄穹文枢：领域 E 发布审计与最终准入计划

> 负责领域：测试、发布审计、性能并发、数据库迁移、可观测性、反向验证、最终准入。
>
> 本文是审计与执行计划，不修改业务代码，不把未执行的计划写成已通过证据。所有结论以当前工作区文件、命令输出和真实运行记录为准。

## 1. 审计边界与当前基线

### 1.1 工作区状态

- 当前工作区存在大规模未提交变更；审计规则是只读盘点、保留全部现有成果，不执行 `git reset --hard`、`git checkout --`、批量删除或不可逆迁移。
- 本次只新增本文件；本文件中的“待执行”“未证实”不等同于通过。
- 静态盘点结果：后端测试模块 80 个，前端规格文件 40 个，Alembic 迁移版本 4 个，真实 ASGI 验收脚本 3 个，后端 Python 文件约 269 个（排除虚拟环境和缓存）。
- 当前审计不把历史报告中的“生产就绪”表述视为证据；必须有命令、时间、隔离数据库、任务 ID、事件数、正文长度和终态记录。

### 1.2 已发现的发布风险

| 编号 | 风险 | 当前证据 | 等级 | 处理要求 |
|---|---|---|---|---|
| R-001 | `verify.ps1 full` 运行旧的 `e2e_*` 与 `concurrency_smoke_validation.py`，而新真实入口是 `real_asgi_*.py` | `verify.ps1` 与 `backend/scripts/real_asgi_*.py` 静态盘点 | P0 | 发布前必须证明两套脚本的覆盖等价，或把真实入口纳入独立准入批次；不能仅以旧套件通过替代真实验收 |
| R-002 | 全量后端测试可能超过外部窗口，前端并行 Vitest 曾出现超时不稳定 | 既有任务基线与 `AdminView.spec.ts` 的耗时说明 | P0 | 分批串行执行并记录每批耗时；失败必须保留日志和失败测试，不得简单放宽超时 |
| R-003 | `verify.ps1` 的 quick 门禁包含类型检查、构建和 `app/services`，但不是根目录正式全量 pytest | `verify.ps1` 第 quick/full 分支 | P0 | 发布准入额外执行 `backend\\.venv\\Scripts\\python.exe -m pytest -q`，并连续两轮通过 |
| R-004 | 当前可观测性主要是日志、请求 ID、TaskRuntime、SSE 和 `/health`，未发现 Prometheus/OpenTelemetry 指标导出端点 | `backend/app/main.py`、TaskRuntime/SSE 代码和依赖静态盘点 | P1 | 发布前至少具备可查询的任务、Provider、SSE、迁移和错误证据；若无指标端点，必须在发布限制中明示 |
| R-005 | 真实 Provider 受外部服务波动影响，短章曾出现质量闸门失败 | 既有真实 DeepSeek 验收基线 | P0 | 失败必须收敛为结构化终态并保留诊断；短章、长篇、并发各自按成功率和证据门禁判定 |
| R-006 | “成功”与 `waiting_for_confirm` 的业务含义需要统一 | 真实验收脚本允许两种章节状态，TaskRuntime 长篇脚本要求 `succeeded` | P0 | 发布前定义唯一任务终态映射；不得把待确认状态无条件当作正式定稿成功 |
| R-007 | SQLite 迁移锁文件会遗留在 `backend/storage` | `backend/app/db/init_db.py` 的迁移锁实现及工作区锁文件 | P1 | 运行前后核对锁释放、文件可复用和异常退出恢复；不得清理用户数据库或把锁文件删除当作修复 |

## 2. 现有测试、脚本与门禁盘点

### 2.1 后端测试分区

正式运行目录由 `backend/pytest.ini` 管理，覆盖 `app/services` 与 `app/api/routers`；根目录 `pytest.ini` 只覆盖 `backend/app/services`。因此必须明确工作目录，不能使用系统 Python 或全局 pytest。

#### A. 任务运行时、恢复与幂等

- `backend/app/services/test_task_runtime.py`
- `backend/app/services/test_task_reconciliation.py`
- `backend/app/services/test_generation_run_rebind.py`
- `backend/app/services/test_finalize_session_safety.py`
- `backend/app/api/routers/test_task_runtime_route.py`
- `backend/app/api/routers/test_outline_job_restart_recovery.py`
- `backend/app/services/test_provider_cancel_no_hang.py`
- `backend/app/services/test_project_ledger_lease_service.py`

验收重点：状态机终态不可复活、取消竞态、重启后的 stale/recovery、租约、幂等键、事件游标和权限隔离。

#### B. 正文生成、质量闸门与连续性

- `backend/app/services/test_pipeline_orchestrator.py`
- `backend/app/services/test_pipeline_orchestrator_overview_reuse.py`
- `backend/app/services/test_generation_call_service.py`
- `backend/app/services/test_generation_quality_guards.py`
- `backend/app/services/test_longform_generation_service.py`
- `backend/app/services/test_longform_segment_streaming.py`
- `backend/app/services/test_longform_package_e2e.py`
- `backend/app/services/test_multi_chapter_continuity_production.py`
- `backend/app/services/test_longform_causal_gate.py`
- `backend/app/services/test_long_novel_outline_generator.py`
- `backend/app/services/test_chapter_context_service.py`
- `backend/app/services/test_consistency_service.py`
- `backend/app/services/test_self_critique_service.py`
- `backend/app/services/test_chapter_guardrails.py`
- `backend/app/services/test_chapter_review_service.py`

验收重点：正文与日志隔离、元文本污染、分段 checkpoint、上下文复用、质量失败不静默落库、版本与记忆原子边界。

#### C. Provider、配置、预算和流式调用

- `backend/app/services/test_llm_service.py`
- `backend/app/services/test_llm_stream_reasoning_fallback.py`
- `backend/app/services/test_cloud_provider_resilience.py`
- `backend/app/services/test_compat_generation_config.py`
- `backend/app/services/test_config_sync_manager.py`
- `backend/app/services/test_llm_config_persistence.py`
- `backend/app/services/test_prompt_cache_key_skip.py`
- `backend/app/services/test_token_budget_service.py`
- `backend/app/utils/test_llm_tool_reasoning.py`

验收重点：DeepSeek 配置读取、请求参数版本、超时/错误码、重试预算、缓存键、reasoning fallback、前端配置保存后的下一任务生效。

#### D. 研究、风格、知识和辅助业务

- `backend/app/services/test_research_service.py`
- `backend/app/services/test_project_research_service.py`
- `backend/app/services/test_import_service.py`
- `backend/app/services/test_export_service.py`
- `backend/app/services/test_novel_export_import_roundtrip.py`
- `backend/app/services/test_vector_store_service.py`
- `backend/app/services/test_embedding_service.py`
- `backend/app/services/test_knowledge_graph_causal_chain.py`
- `backend/app/services/test_foreshadowing_service.py`
- `backend/app/services/test_foreshadowing_runtime_events.py`
- `backend/app/services/test_emotion_service.py`
- `backend/app/services/test_emotion_curve_service.py`
- `backend/app/services/test_faction_service.py`
- `backend/app/services/test_writer_persona_service.py`
- `backend/app/services/test_writer_context_builder.py`

验收重点：项目隔离、失败可恢复、研究来源与产物绑定、导入导出往返、图谱/伏笔/情绪账本不污染正文生成上下文。

#### E. 路由、鉴权与数据库

- `backend/app/api/routers/test_auth_route.py`
- `backend/app/api/routers/test_research_job.py`
- `backend/app/api/routers/test_style_profile_job.py`
- `backend/app/api/routers/test_import_novel_job.py`
- `backend/app/api/routers/test_longform_plan_registration.py`
- `backend/app/api/routers/test_outline_generation_job.py`
- `backend/app/api/routers/test_blueprint_job_metrics.py`
- `backend/app/api/routers/test_outline_job_metrics.py`
- `backend/app/api/routers/test_knowledge_graph_route.py`
- `backend/app/api/routers/test_clue_tracker_route.py`
- `backend/app/api/routers/test_foreshadowing_route.py`
- `backend/app/api/routers/test_updates.py`
- `backend/app/api/routers/test_writer_route_regressions.py`
- `backend/app/core/test_dependencies_auth.py`
- `backend/app/db/test_init_db_idempotency.py`
- `backend/app/services/test_alembic_migrations.py`

验收重点：成功、非法输入、权限拒绝、异常恢复四类契约；迁移 repeatability、legacy adoption、并发升级、降级保留数据。

### 2.2 前端测试分区

当前前端规格文件约 40 个，主要覆盖 API 模块、路由、Pinia store、写作台、章节状态、进度卡、日志、设置、导入/研究/图谱等组件。

- API 与流式：`frontend/src/api/*.spec.ts`、`frontend/src/api/modules/chapterWorkflow.spec.ts`、`frontend/src/utils/sseStream.spec.ts`。
- 写作台主链路：`frontend/src/views/WritingDesk.spec.ts`、`frontend/src/views/NovelWorkspace.spec.ts`、`frontend/src/views/InspirationMode.spec.ts`。
- 进度与章节状态：`frontend/src/components/writing-desk/widgets/FloatingProgressCard.spec.ts`、`workspace/states/ChapterGenerating.spec.ts`、`ChapterFailed.spec.ts`、`ChapterEmpty.spec.ts`。
- 业务卡片：`frontend/src/components/novel-detail/*.spec.ts`、`clue-tracker/ClueTrackerView.spec.ts`、`knowledge-graph/KnowledgeGraphView.spec.ts`。
- 管理与配置：`frontend/src/views/AdminView.spec.ts`、`frontend/src/components/LLMSettings.spec.ts`、`admin/RuntimeLogManagement.spec.ts`。
- 状态与工具：`frontend/src/stores/*.spec.ts`、`frontend/src/utils/*.spec.ts`、`frontend/src/router/index.spec.ts`。

现状判断：存在较多组件级与存在性测试，但真实浏览器 E2E、键盘/可访问性、窄屏布局、真实 SSE 断线和多任务切换仍须单独列为发布证据，不得由组件挂载测试替代。

### 2.3 现有门禁与脚本

| 层级 | 入口 | 当前覆盖 | 审计要求 |
|---|---|---|---|
| 前端类型 | `npm run type-check` | Vue/TypeScript 类型构建 | 独立执行，记录 Node/npm 版本和耗时 |
| 前端构建 | `npm run build-only` | Vite 生产构建 | 检查产物生成、警告、大小趋势 |
| 前端单测 | `npm run test:run` | Vitest 全量 | 串行资源隔离；超时必须定位，不得只增 timeout |
| 后端单测 | `backend\\.venv\\Scripts\\python.exe -m pytest -q` | 正式全量 | 以该命令为唯一全量基线；分批后再跑总量 |
| 后端编译 | `backend\\.venv\\Scripts\\python.exe -m compileall -q backend\\app` | Python 语法/导入编译 | 每轮全量门禁前执行 |
| 变更检查 | `git diff --check` | 空白/补丁格式 | 每轮记录 |
| quick | `verify.ps1 quick` | 前端类型、构建、`app/services` | 不是全量发布门禁 |
| smoke | `verify.ps1 smoke` | 正式端口、健康、OpenAPI、LLM 设置 | 不包含真实 DeepSeek 章节完整链路 |
| full | `verify.ps1 full` | quick + smoke + 旧 E2E 脚本 | 需核验脚本是否存在且覆盖新 TaskRuntime 真实入口 |
| 真实短章 | `backend/scripts/real_asgi_generation_smoke.py` | 1200 字、SSE、游标续接、质量调用次数、数据库证据 | DeepSeek 串行执行 |
| 真实长篇 | `backend/scripts/real_asgi_longform_generation_smoke.py` | 默认 2 万字、分段、checkpoint、正文事件、落库 | 独立 SQLite，长窗口执行 |
| 真实并发 | `backend/scripts/real_asgi_concurrent_generation_smoke.py` | 双项目、双任务、事件/正文隔离 | 与长篇分开执行，避免 Provider 竞争误判 |
| 迁移 | `backend\\.venv\\Scripts\\python.exe -m alembic ...` | upgrade/current/heads/downgrade | fresh、legacy、并发升级、回滚均需证据 |

## 3. 测试分批与资源隔离策略

### 3.1 总原则

1. 单元/契约测试、集成测试、真实 Provider、性能并发、前端构建不得在同一资源池同时运行。
2. 每个真实批次使用唯一 SQLite 文件，例如 `backend/storage/audit/<run-id>.db`；禁止指向用户当前数据库。
3. 每批固定 `run_id`，记录 Python/Node/npm/pytest/Vitest/SQLite 版本、启动参数、环境变量名（不记录密钥值）、开始结束时间。
4. 真实 Provider 批次串行；只有并发验收脚本内部允许并发请求。不得同时启动多个真实 smoke 脚本。
5. 后端全量 pytest 按模块分组串行；前端 Vitest 首先按目录分组定位，再执行全量。
6. 失败批次不自动无限重试：最多 2 次复跑。第二次仍失败即登记缺陷；若为 Provider 波动，必须保留原始失败和脱敏诊断。

### 3.2 推荐批次顺序

| 批次 | 资源 | 命令/范围 | 通过条件 |
|---|---|---|---|
| B0 环境冻结 | 只读 | `git status --short`、版本探针、密钥存在性检查 | 工作区变更清单固定；无密钥泄漏输出 |
| B1 静态门禁 | CPU | `compileall`、`git diff --check`、前端 `type-check` | 全部退出码 0 |
| B2 后端快速契约 | 1 个 Python 进程、临时 DB | 认证、迁移、TaskRuntime、配置、Provider mock | 目标分组全绿，无跳过核心测试 |
| B3 后端业务集成 | 1 个 Python 进程、临时 DB | 生成、长篇、连续性、研究、风格、导入导出、账本 | 全绿；失败可定位到测试模块 |
| B4 前端组件/API | 1 个 Vitest worker 起步 | API、SSE、store、写作台、进度卡和业务卡片 | 全绿；无超时/未处理异常 |
| B5 前端全量 | 独占 Node 资源 | `npm run test:run` | 全量稳定通过；重复运行结果一致 |
| B6 构建 | 独占 Node 资源 | `npm run build-only` | 构建成功，产物和警告可审计 |
| B7 迁移矩阵 | 每场景独立 SQLite | Alembic fresh/legacy/upgrade/downgrade/concurrent | schema、版本、数据计数、约束全部符合契约 |
| B8 真实短章 | 独立 SQLite + DeepSeek | `real_asgi_generation_smoke.py` | 1200 字下限、SSE、重连、单次首稿、持久化终态全证实 |
| B9 真实连续性 | 独立 SQLite + DeepSeek | 1–10 章串行入口脚本/浏览器流程 | 每章定稿，摘要/快照/人物/伏笔/时间线连续，无串线 |
| B10 真实长篇 | 独立 SQLite + DeepSeek | `real_asgi_longform_generation_smoke.py` | >=2 万字、checkpoint 完整、顺序正确、事件和落库一致 |
| B11 真实并发 | 独立 SQLite + DeepSeek | `real_asgi_concurrent_generation_smoke.py` | 双项目各自成功，任务/事件/正文/产物无交叉 |
| B12 浏览器验收 | 独立正式栈/测试账号 | 创建→总纲→章节纲→正文→日志→取消/恢复→定稿→导出 | 所有入口可访问，UI 状态与 TaskRuntime 一致 |
| B13 双轮全量 | 所有资源清理后重新执行 B1–B12 | 同一版本、不同 run_id | 连续两轮证据完整且无 P0/P1 阻断 |

### 3.3 资源隔离清单

- 数据库：`fresh.sqlite`、`legacy.sqlite`、`concurrent.sqlite`、真实短章/长篇/并发各一份；禁止共享 WAL/SHM 文件。
- Provider：mock 批次禁止读取真实 Key；真实批次只使用配置的 DeepSeek 模型，禁止与人工任务同时压测。
- 进程：后端 pytest、迁移、真实脚本不并行；Vitest 与 Vite build 不并行；前端浏览器验收独占服务端口。
- 文件产物：每个批次使用独立 `artifacts/<run-id>/`；日志、SSE 原文、DB 摘要和测试输出不覆盖旧证据。
- 用户数据：测试账号、测试项目、测试上传文件独立；任何 smoke 结束后不得删除作为审计证据的 DB，按保留策略归档。

## 4. 性能、并发与稳定性验收

### 4.1 必测场景

| 场景 | 负载 | 关键指标 | 初始准入目标 |
|---|---|---|---|
| 单短章 | 1 项目、1200 字 | 端到端耗时、首片延迟、正文长度、Provider 次数 | 无永久卡死；首片可见；下限达标；调用不超策略 |
| 双项目并发 | 2 项目各 1200 字 | 成功率、总耗时、任务隔离、事件隔离 | 2/2 完成；无跨项目标记；无任务 ID 复用 |
| 同项目重复提交 | 同章节相同幂等键 | 去重数、返回任务 ID | 只产生一个持久化任务 |
| 取消竞态 | Provider 正在输出时取消 | 取消响应、最终状态、迟到回调 | `cancelling` 后只能到 `cancelled`；不得复活 |
| 断线续接 | 消费部分 SSE 后以游标重连 | 游标单调性、漏片/重片数、终态事件 | 无漏片、无重片、无跨任务事件 |
| 长篇分段 | >=2 万字、多段 | 段数、checkpoint、段间重复、最终顺序 | 每段确认后持久化；重启从 checkpoint 继续 |
| 重启恢复 | 运行中终止/重启应用 | stale 标记、任务恢复、章节占用 | 无重复入队；可继续或结构化失败 |
| 导入导出 | 完整项目往返 | 计数、顺序、正文 hash、版本/账本覆盖 | 隔离库恢复一致；不支持项有告警 |

### 4.2 性能记录格式

每个场景至少记录：`run_id`、场景、并发数、项目数、任务数、Provider 模型、请求数、成功数、失败数、p50/p95/p99（若样本足够）、首事件延迟、总耗时、正文字符数、事件数、重试数、数据库大小、CPU/内存峰值、错误码和退出原因。

性能目标是验收基线，不得在无历史样本时伪造百分位数。样本少于 5 次时标记 `insufficient_sample`，不能宣称达成 p95。

## 5. 每功能评分模型（100 分）

每项核心功能独立评分，低于 90 分不得进入下一阶段；任何 P0 缺陷直接阻断，不因总分高而豁免。

| 维度 | 权重 | 评分依据 |
|---|---:|---|
| 功能正确性 | 25 | 主流程、输入校验、终态、产物和边界条件 |
| 数据一致性 | 20 | API/schema/DB 对齐、原子落库、重启后真相一致 |
| 连续性与质量 | 15 | 章节连续、账本同步、正文纯净、质量闸门可解释 |
| 错误恢复 | 15 | 超时、取消、断线、重试、stale、恢复/失败收敛 |
| 性能并发 | 10 | 耗时、资源、并发隔离、无竞态和永久等待 |
| 可观测性 | 5 | request_id、task_id、阶段、事件、错误码、可追溯产物 |
| 测试强度 | 5 | 单元、契约、集成、真实入口、反向验证覆盖 |
| 用户体验/可访问性 | 5 | 状态可理解、进度可见、键盘/窄屏、错误可行动 |

评分证据要求：每个分项附命令/脚本、run_id、输入摘要、输出摘要、DB 查询摘要、日志路径、失败重现方式。人工质量评分必须有两名评审或明确单人评审限制，不得以“看起来正常”计满分。

## 6. 故障注入矩阵

故障注入只允许在隔离环境和测试账号执行，注入前记录基线，注入后必须验证终态、数据和恢复。禁止对用户数据库、生产 Provider 任务或未备份的真实项目注入。

| 故障 | 注入位置 | 预期行为 | 必查证据 | 阻断条件 |
|---|---|---|---|---|
| Provider 首次超时 | LLM 调用 mock/代理 | 按预算重试或结构化失败 | `error_code`、attempt、耗时、无假进度 | 无限等待、无终态、重复整章 |
| Provider 429/5xx | Provider 适配层 | 可解释退避/切换，预算耗尽后失败 | 状态事件、重试次数、模型记录 | 静默吞错、重试风暴 |
| Provider 返回 JSON/提纲污染 | 正文返回 fixture | 质量闸门拒绝或一次受控重试 | 命中规则、原文不落正式正文、retry metadata | 污染正文成功落库 |
| Provider 流中断 | SSE/HTTP 流 | 保留 checkpoint，可恢复或失败 | 最后确认段、事件游标、任务终态 | 整章从头重复 |
| 用户断开浏览器 | SSE 客户端 | 后台任务继续；重连可回放 | Last-Event-ID、事件 ID 单调、无漏片 | 重复片段或跨任务事件 |
| 用户取消 | 任务取消 API | `queued/running→cancelling→cancelled` | 取消事件、章节占用、迟到回调 | 取消后 success/running |
| 进程重启 | 运行中任务/应用 | stale/reconcile，按 checkpoint 恢复 | 重启前后 task、lease、章节状态 | 重复入队、孤儿 busy |
| 数据库锁竞争 | 两个启动/迁移 worker | 迁移串行且最终 head | migration lock、version、schema | 损坏、死锁、半迁移 |
| 迁移中断 | 每个 revision 前后 | 可重跑/失败可诊断 | alembic_version、表/列计数 | 版本号虚假前进 |
| 旧 schema | legacy fixture | upgrade 保留数据和唯一约束 | 行数、hash、列、约束 | 静默丢数据 |
| 双项目并发 | 两个真实项目 | 完成且事件/正文/产物隔离 | task/project/event/content 关联 | 任一跨项目泄漏 |
| 重复提交 | 同一 idempotency key | 单任务，重复请求可查询原任务 | task 数、响应 ID | 多任务或状态分叉 |
| 日志写入失败 | 文件/持久日志层 | 业务不静默失败，至少控制台/DB 可追踪 | request_id、task_id、fallback | 无诊断 |
| SSE 心跳中断 | stream iterator | 客户端重连，服务端终态可查询 | heartbeat、reconnect、cursor | 永久空转 |
| 前端接口 401/403 | API mock | 展示可理解错误，不清空现有任务状态 | UI 状态、request_id | 错误污染正文/状态 |
| 前端慢请求 | 网络延迟/响应乱序 | 防止旧响应覆盖新任务 | task_id/run_id 绑定 | 旧任务回调改写新任务 |

## 7. 反向验证（故意破坏）规程

每个新增修复至少做一次受控反向验证，验证完成后立即恢复改动；恢复操作必须只针对本次临时补丁，不能覆盖用户既有改动。

1. 选定一个已有回归测试及其业务不变量。
2. 在临时副本或工作树中故意破坏一个关键判断，例如移除任务 ID 绑定、改变终态、删除事件游标过滤、跳过迁移列检查。
3. 运行最小测试，必须失败且失败消息能指向不变量。
4. 恢复临时破坏，重新运行最小测试，再进入批次门禁。
5. 记录 `sabotage_id`、破坏点摘要、预期失败、实际失败、恢复证明。禁止用降低断言、删除测试、屏蔽测试文件或增加宽泛 timeout 代替反向验证。

最低反向验证集合：

- TaskRuntime：终态复活、迟到回调、重复幂等键。
- SSE：游标重连漏片/重片、跨任务事件。
- 长篇：checkpoint 回退、段序错乱、重复整章。
- 质量：污染正文落库、失败任务错误地写成功版本。
- 数据库：迁移遗漏列、重复唯一键、并发升级竞态。
- 配置：前端新配置未被下一任务读取。
- 前端：旧请求回调覆盖新 task、日志事件进入正文区。

## 8. 数据库迁移审计计划

### 8.1 迁移链

当前迁移目录为 `backend/alembic/versions/`，包含：

- `000_initial_schema.py`
- `001_task_runtime.py`
- `002_ledger_lease_and_runtime_metrics.py`
- `003_schema_compatibility.py`

运行时数据库 URI 来自 `app.core.config.settings.sqlalchemy_database_uri`；`backend/app/db/init_db.py` 通过跨进程锁串行执行 Alembic upgrade，并在迁移后初始化管理员、系统配置和默认提示词。

### 8.2 必测矩阵

- fresh SQLite：`upgrade head` 两次，检查 `alembic_version`、表、列、索引、唯一约束。
- downgrade：`downgrade -1` 与 `downgrade base`，重复 downgrade 不应破坏数据或报不可解释错误。
- legacy schema：含旧 TaskRuntime/lease 表和重复/空租约值，升级后检查数据保留、唯一值补齐和列契约。
- concurrent upgrade：两个协程/进程同时启动，检查锁、最终版本和默认表。
- MySQL dry-run/隔离实例：至少验证 URL、方言、字符集、索引和 JSON/TIMESTAMP 兼容；没有实例时标记未完成，不得用 SQLite 结果替代。
- 应用启动：迁移失败必须阻断启动或给出明确错误；迁移完成后默认配置初始化不得破坏已有用户配置。

### 8.3 迁移发布阻断

- `alembic_version` 非唯一 head、版本无法重放或 downgrade 后 schema 残留不符合契约。
- 任一 legacy 行数、正文/版本 hash、TaskRuntime 事件数无法解释。
- 并发迁移出现死锁、锁未释放、半迁移或服务误报健康。
- 未提供备份、回滚/前向修复方案和迁移后校验 SQL。

## 9. 可观测性与证据采集

### 9.1 当前能力盘点

- 应用启动时配置日志，支持控制台/滚动文件等级和文件日志开关。
- HTTP 请求生成或接收 `X-Request-ID`，响应回传同一 ID；错误响应包含结构化 `code`、`message`、`request_id`，服务端记录根因。
- TaskRuntime 持久化任务状态、阶段、进度、事件游标、错误、payload、产物引用和运行指标；启动巡检/周期 sweeper 处理 stale 任务。
- SSE 支持鉴权、事件游标和 `Last-Event-ID` 续接；正文 `content_delta` 与日志事件在前端分别处理。
- `/health` 与 `/api/health` 返回应用健康状态。
- 当前未发现独立 Prometheus/OpenTelemetry exporter 或集中式 trace backend；发布时必须把这一限制写进运行手册和告警方案。

### 9.2 每次验收的最小证据包

目录格式：`artifacts/release-audit/<YYYYMMDD-HHMMSS>-<run-id>/`

```text
manifest.json              # 版本、提交/工作区摘要、环境版本、批次和脱敏配置名
command.log                # 原始命令、开始结束时间、退出码
test-output.log            # pytest/Vitest/build 原始输出
smoke-output.log           # 真实入口原始输出，不含令牌/密钥
runtime-events.jsonl       # task_id、event_id、event_type、stage、progress、时间
task-snapshots.json        # 关键轮询时刻的 TaskRuntime 脱敏快照
database-evidence.json     # schema/version/row counts/hash/constraint 查询结果
sse-summary.json           # 首片、事件数、游标范围、重连、漏片/重片判定
quality-evidence.json      # 字数、污染/质量闸门、Provider 调用与重试预算
performance.json           # 耗时、并发、资源、样本量和百分位状态
fault-injection.json       # 故障、预期、实际、恢复证据
scorecard.json             # 100 分模型的逐项评分与评审人
known-risks.md             # 未解决风险、影响、临时措施和阻断状态
```

### 9.3 真实 Provider 证据格式

```json
{
  "run_id": "20260814T120000Z-short-001",
  "scenario": "real_short_chapter",
  "provider": {"name": "deepseek", "model": "deepseek-v4-flash-free", "key_present": true},
  "isolation": {"db_file": "<redacted-path>", "test_user": "audit-user", "project_id": "<id>"},
  "task": {"task_id": "<id>", "task_type": "chapter_generation", "final_status": "succeeded", "retry_count": 0},
  "content": {"characters": 0, "min_required": 900, "content_delta_events": 0, "forbidden_markers": []},
  "sse": {"event_count": 0, "cursor_first": 0, "cursor_last": 0, "reconnect_after": 0, "gaps": [], "duplicates": []},
  "database": {"version_id": "<id>", "task_rows": 1, "event_rows": 0, "persisted_hash": "<sha256>"},
  "timing": {"started_at": "<iso8601>", "ended_at": "<iso8601>", "duration_ms": 0, "sample_status": "single_sample"},
  "result": "pass",
  "blockers": []
}
```

示例中的数值均为 schema，不是本项目的实测结果；生成证据时必须填真实值。禁止写入 Provider Key、JWT、完整 prompt、用户正文全文或可识别个人数据。

## 10. 双轮全量门禁

### 第 1 轮：定位轮

- 执行 B1–B12，按批次隔离资源。
- 任一批次失败，保留原始证据并定位；最多允许一次针对同一失败的复跑。
- 修复后必须重新跑受影响批次、反向验证和从该批次起的后续批次。

### 第 2 轮：发布确认轮

- 清理运行进程和临时缓存，但保留第 1 轮证据；建立新的 `run_id` 和独立数据库。
- 严格串行执行后端全量、前端类型/测试/构建、迁移矩阵、真实短章、10 章连续、2 万字长篇、双项目并发、配置生效、导入导出和浏览器主链路。
- 第 2 轮不得跳过因资源耗时而被认为“非核心”的真实测试；可分时段执行，但必须保持版本和证据链一致。
- 两轮均通过才允许进入最终准入评审；一次通过、一次失败按失败处理。

## 11. 发布阻断条件与放行条件

### 11.1 立即阻断（P0）

- 永久卡死、无终态、假进度、静默失败。
- 取消后任务复活为运行/成功，迟到回调覆盖终态。
- 任务、事件、正文、日志、产物跨项目/跨用户泄漏。
- 重启后重复入队、丢失已确认 checkpoint、整章从头重写。
- 真实 Provider 短章、10 章连续、>=2 万字分段或双项目并发任一核心场景未通过。
- 配置修改后下一任务仍使用旧值，或任务记录无法追溯模型/提示词/参数版本。
- 正式全量 pytest、前端 type-check/test/build 任一失败或未执行。
- 数据迁移损坏、数据丢失、版本漂移、并发升级不可复现。
- 证据缺少 task_id、DB 证据、SSE 游标或终态，无法复核。

### 11.2 默认阻断（P1）

- 核心功能评分低于 90/100。
- 关键错误没有结构化错误码、请求 ID、用户可行动提示或重试路径。
- 全量测试不稳定、同版本重复结果不一致，且原因未定位。
- 性能明显退化且没有容量边界或降级策略。
- 浏览器主链路存在不可访问入口、键盘无法操作、进度卡遮挡正文或日志污染正文。
- 迁移只验证 SQLite，未对声明支持的 MySQL 进行任何隔离验证且未明确限制。

### 11.3 可带风险放行（仅 P2/P3）

- 有用户可见限制、替代操作、负责人、截止日期、回滚方案和审计条目。
- 不影响核心生成、数据安全、任务终态、恢复、配置一致性和导入导出完整性。
- 发布委员会明确签字，风险不计入“全绿”。

## 12. 持续任务台账

| ID | 领域 E 任务 | 优先级 | 完成定义 | 证据 | 状态 |
|---|---|---:|---|---|---|
| E-001 | 校准 `verify.ps1` 与新真实入口的覆盖关系 | P0 | 旧脚本存在性/覆盖差异表 + B8–B11 独立结果 | `known-risks.md`、脚本输出 | 待执行 |
| E-002 | 建立后端测试分组与串行资源策略 | P0 | B2/B3 分组命令、耗时、失败归因 | `command.log`、`test-output.log` | 待执行 |
| E-003 | 稳定前端 Vitest 全量 | P0 | 连续两次 `npm run test:run` 无超时/未处理异常 | Vitest 输出 | 待执行 |
| E-004 | 完成迁移 fresh/legacy/concurrent/rollback 矩阵 | P0 | 所有 schema/数据/锁断言通过 | `database-evidence.json` | 待执行 |
| E-005 | 完成真实 DeepSeek 短章 | P0 | 1200 字、正文 SSE、游标重连、调用预算、落库 | `smoke-output.log` + DB | 部分已有，待复核 |
| E-006 | 完成 1–10 章连续性 | P0 | 章节定稿、账本连续、无丢章/串线 | 连续性报告 | 待执行 |
| E-007 | 完成 >=2 万字分段 | P0 | checkpoint、重启/断线、顺序和持久化完整 | 长篇报告 | 待执行 |
| E-008 | 完成双项目真实并发 | P0 | 双项目成功且全证据隔离 | 并发报告 | 待执行 |
| E-009 | 完成配置即时生效与可追溯 | P0 | 前端保存版本 = 下一任务读取版本 | 配置快照/TaskRuntime | 待执行 |
| E-010 | 完成导入导出隔离库往返 | P0 | 正文、版本、蓝图、账本、顺序和告警完整 | 往返报告 | 待执行 |
| E-011 | 建立故障注入与反向验证记录 | P0 | 最低集合每项都能先失败后恢复 | `fault-injection.json` | 待执行 |
| E-012 | 建立领域 E 评分卡和发布签字 | P1 | 每功能 >=90，无 P0，双轮全量证据齐 | `scorecard.json` | 待执行 |
| E-013 | 明确指标/追踪能力边界 | P1 | 有可执行日志查询和缺口声明 | 运行手册/风险台账 | 待执行 |
| E-014 | 形成最终准入包 | P0 | manifest、命令、结果、风险、签字齐全 | 发布归档目录 | 待执行 |

## 13. 最终验收签字表

| 角色 | 必须确认 | 姓名/时间 | 结论 |
|---|---|---|---|
| 测试负责人 | 后端全量、前端三门禁、反向验证 |  |  |
| 可靠性负责人 | 取消、重启、断线、stale、并发无 P0 |  |  |
| 数据库负责人 | 迁移、回滚、legacy、并发锁、数据保留 |  |  |
| 质量负责人 | 短章、连续性、长篇、质量闸门和评分 |  |  |
| 发布负责人 | 两轮全量、证据完整、阻断项关闭 |  |  |

最终结论只能取：`通过`、`有条件通过`、`阻断`。缺少真实 Provider 证据、任一核心评分低于 90、任一 P0 未关闭或双轮全量未完成时，结论必须为 `阻断`。

