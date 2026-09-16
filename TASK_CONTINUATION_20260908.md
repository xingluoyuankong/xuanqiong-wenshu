# 玄穹文枢 — 小说生成主链路接续记录

> 当前接续会话：`01a083d5-3873-76e2-acf0-43acbe3e2b6e`
> 更新时间：2026-09-09 20:20 +08:00
> 范围：本地工程内的章节生成质量、长篇连续性、生成卡死/降级可观测性；不以 Docker 作为验收路径。

## 1. 本次接续的实际审查结论

2026-09-09 审查发现，提交 `d45b93b` 将 `PipelineOrchestrator.generate_chapter` 错误替换为 `_prepare_chapter_context`：主生成入口消失，质量门接口也被不完整地迁移。该状态下，生成质量定向测试出现 **29 failed / 200 passed**，不具备继续堆叠重构的条件。

已在当前工作树完成的稳定化处理：

1. 先备份被错误重构覆盖的工作文件；恢复 `d45b93b^` 中仍含完整 `generate_chapter` 的实现，再在此基础上做小范围、可回归的修改。
2. 将错误重构产生的 37 个未跟踪提取脚本、文本切片、失真计划文档移至仓库外归档；恢复前快照和归档清单位于：
   `D:\小说写作\xuanqiong-wenshu-agent-recovery\20260909_100033\ARCHIVE_MANIFEST.json`。
3. 当前主链路恢复和续写优化仍在工作树，尚未提交到 `HEAD=d45b93b`；不做 `reset --hard`、批量覆盖或 Docker 部署替代本地验证。
4. `_extract_quality_gate.py`、`_update_doc.py`、`quality_gate.py` 等文件的修改状态以当前 `git status --short` 和实际 diff 为准；完整清单不在本段重复，保留全部未提交改动，不擅自清除。

## 2. 已交付的主链路优化：长章节状态化、可止损续写

原多轮续写只把 `best_content_initial[-800:]` 作为助手消息，且每轮重复发送完整 `prompt_input`。这会丢失长篇承接，并可能在短回复、重复回复或 Provider 抖动时反复调用模型，表现为生成“卡住”。

当前工作树将续写收敛为受限、可观测的状态机：

- 最近正文尾部最多 1200 字符；
- 承接上一章摘要及 `continuity_anchor.inherit_from_previous`；
- 真实任务书 schema 的 `scene / goal / conflict / turn / outcome / payoff / bridge / dialogue_value / end_hook`；
- 已从正文中兑现的场景不再作为“待推进”任务重灌；
- 焦点人物、对白职责、本章长篇角色焦点、待回收及需强化伏笔；
- 首轮续写保留完整写前 prompt；后续轮次仅使用尾文和受限状态包；
- 每轮先后检查取消状态；按距续写完成线的剩余量计算输出 token / timeout 预算；
- Provider 返回内容先进行正文规范化，再拒绝空输出、低于 `multi_round_min_increment` 的增量、尾部重复和生成元话语；
- 每轮运行事件与最终元数据记录 raw/normalized/increment 字符数、重复率、耗时、剩余量、停止原因、状态包字符数。

第 2 节的改动重点是收紧多轮续写子循环；后续 2.1—2.4 已分别处理一致性复检、结构质量门复用、失败恢复和统一保障摘要，候选生成与各评审阶段仍保持职责边界。

## 2.1 本轮主链路修复（2026-09-09 18:20）

本轮只处理已由完整代码追踪确认的小说生成主链路问题，没有部署 Docker，也没有扩大到无关功能：

1. **一致性局部修订后的复检去重**
   - `_run_consistency_check` 增加兼容的 `mode="repair" | "check_only"`；默认仍是原完整修复模式。
   - 一致性发现问题后由 `SelfCritiqueService.revise_chapter` 产生局部修订时，修订后的验收只调用一次 `check_consistency`，不再再次触发自动修复包。
   - 新增调用计数回归：`check_only` 下 `check_consistency` 恰为 1 次、`auto_fix` 为 0 次；既有 repair 重试回归保持通过。

2. **定稿正文页保留降级与风险可见性**
   - `WDWorkspace` 将真实 `chapterRuntime` 传入 `ChapterContent`。
   - 正文完成态新增紧凑“定稿保障状态”卡：展示正文已保留、评审/连续性跳过或降级、账本阶段原因、字数门槛和最终质量门风险。
   - 按后端 `allowed_actions` 展示刷新、重试保障流程、候选复审或确认动作；质量正常且无降级时卡片不渲染。
   - 新增组件回归覆盖有降级显示和正常状态静默两条路径。

3. **完整入口集成回归已补齐**
   - 新增 `test_pipeline_generate_chapter_continuation_integration.py`，真实穿过 `PipelineOrchestrator.generate_chapter`，覆盖首轮候选不足、两轮状态化续写、首轮完整 prompt、后续压缩 history、运行事件、停止原因和 `append_chapter_versions`。

本轮代表性新增/修改文件（完整清单以 `git status --short` 为准）：
- `backend/app/services/pipeline_orchestrator.py`
- `backend/app/services/test_consistency_check_only.py`
- `backend/app/services/test_pipeline_generate_chapter_continuation_integration.py`
- `frontend/src/components/writing-desk/layout/WDWorkspace.vue`
- `frontend/src/components/writing-desk/workspace/content/ChapterContent.vue`
- `frontend/src/components/writing-desk/workspace/content/ChapterContent.spec.ts`

## 2.2 本轮边界收口与重复评估消除（2026-09-09 19:20）

本轮继续围绕小说生成主链路收口，不涉及 Docker 或无关部署：

1. **完整 `generate_chapter` 续写边界已覆盖**
   - `test_pipeline_generate_chapter_continuation_integration.py` 现覆盖成功两轮续写、低增量止损、Provider 异常降级保留首稿、续写调用后取消立即中断且不落库。
   - 取消控制流保持 `409 / GENERATION_CANCELLED`，不被降级逻辑吞掉；低增量和 Provider 异常会写入 continuation stop reason、运行事件和降级记录。

2. **消除正文未变化时的重复结构质量门评估**
   - 启用扩写时，扩写前门结果仅在扩写后正文与扩写前正文**原始字符串完全相同**时复用；会把预扩写 guard 复制到标准 `story_progression_guard` 键。
   - 最终 deterministic cleanup 仅在原始正文完全相同时复用当前 gate；清理改动任意字符（包括换行、段落空白和标点）仍强制重算。
   - 不使用会归一化空白的 `_content_fingerprint()` 作为结构质量门缓存键，避免段落结构变化被错误判为相同。
   - 完整入口调用计数回归确认：扩写/清理均 no-op 时结构门只执行 1 次；最终清理改变空白时执行 2 次。

3. **失败恢复语义闭环**
   - `GenerationRuntime` 增加显式 `GenerationDiagnostics` 类型，包含 `retryable` 等后端诊断字段。
   - `ChapterFailed` 依据章节级优先的 `allowed_actions` 和 `retryable` 显示：可直接重试、候选正文仍可恢复、确认/复审候选、先处理根因或刷新状态。
   - 失败页提供刷新状态与打开候选版本事件；`WDWorkspace` 已实际接收并转发。
   - `evaluation_failed` 有候选时仍优先进入 VersionSelector；无可预览候选时改为进入 ChapterFailed，避免落到空白页丢失诊断。

本轮新增文件：
- `backend/app/services/test_pipeline_structural_gate_reuse.py`

本轮扩展文件：
- `backend/app/services/test_pipeline_generate_chapter_continuation_integration.py`
- `frontend/src/api/types/novel.ts`
- `frontend/src/components/writing-desk/layout/WDWorkspace.vue`
- `frontend/src/components/writing-desk/layout/WDWorkspace.spec.ts`
- `frontend/src/components/writing-desk/workspace/states/ChapterFailed.vue`
- `frontend/src/components/writing-desk/workspace/states/ChapterFailed.spec.ts`

## 2.4 统一保障摘要收敛（2026-09-09 20:05）

- `frontend/src/utils/chapterGeneration.ts` 新增 `buildGenerationAssuranceSummary()`，统一归一化评审/连续性跳过或降级、阶段降级、字数门槛、最终质量门和可用动作。
- 摘要现在提供结构化 `kind/state/severity/reason/actionIds/attentionItems`，同时保留页面既有展示字段；`buildChapterTaskUiModel()`、`ChapterGenerating` 与 `ChapterContent` 共同消费该摘要。
- 正常通过状态保持不显示风险卡；显式字数或质量门失败为 danger，核心/辅助保障跳过或降级为 warning。
- 统一摘要定向回归：`50 passed`；此前前端全量：`83 files / 662 passed`；`npm run type-check`、`npm run build-only` 均通过。

## 2.3 失败恢复与质量门复用验收（2026-09-09 19:45）

本轮新增验收结论：

- 完整 `generate_chapter` 边界测试已覆盖 4 条路径：正常两轮续写、低增量止损、Provider 异常保留首稿、取消后立即中断且不持久化。
- 结构质量门已按原始正文全等复用 no-op 结果；正文内容、换行或段落空白发生变化时强制重算。
- `evaluation_failed` 无候选时进入失败恢复页；失败页根据章节级优先的 `allowed_actions` 和 `retryable` 呈现候选恢复、直接重试、刷新状态或先处理根因。
- 前端恢复事件已接回工作区刷新和候选版本入口，`GenerationDiagnostics` 已形成显式类型契约。

最新全量证据：
- 后端：`3127 passed in 1462.20s`。
- 前端：`83 files / 662 passed`，`npm run type-check`、`npm run build-only` 均通过。

## 2.5 当前收尾审计（2026-09-09 20:20）

- 统一保障摘要结构化契约已通过最新定向 `50 passed`、`npm run type-check`，并通过前端全量 `83 files / 662 passed` 与 `npm run build-only`。
- 结构质量门/续写/一致性去重最新定向 `26 passed`；后端最近一次配置范围全量 `3127 passed in 1462.20s`，之后未再修改后端生产代码。
- 本地服务最近复验：后端 `127.0.0.1:8013/api/health`、前端 `127.0.0.1:5174/`、代理 `127.0.0.1:5174/api/health` 均为 HTTP 200。
- 当前仍保留未提交工作树和 `backend/storage` 用户生成资产；未执行 reset、批量删除或 Docker 部署。
- 功能性剩余工作主要是 HTTP/worker 跨层集成回归、真实 Provider 文学样本双盲验收和生成中告警的视觉人工复核；工程收尾仍包括未提交 diff、测试证据和用户资产核对。

## 3. 证据与门禁

| 验证 | 结果 | 说明 |
|---|---:|---|
| Python 编译 | 通过 | `pipeline_orchestrator.py`、`quality_gate.py`；证据：`backend/logs/continuation-hardening-20260909/py_compile.txt` |
| 本轮一致性与主入口定向回归 | `19 passed in 4.59s` | 含 `test_consistency_check_only.py`、完整 `generate_chapter` 续写入口集成、续写和运行事件 |
| 本轮完成态组件回归 | `4 passed` | `ChapterContent.spec.ts`：降级风险可见、正常状态不渲染 |
| 本轮完整入口/结构门定向回归 | `27 passed in 3.65s` | 覆盖续写成功、取消、低增量、Provider 异常、结构门复用、续写与一致性 |
| 本轮前端恢复/完成态定向回归 | `13 passed` | 失败恢复、工作区事件路由和定稿保障卡 |
| 本轮前端类型检查 | 通过 | `npm run type-check` |
| 本轮前端构建 | 通过 | `npm run build-only`；4918 modules transformed |
| 本地运行复验 | 三端点 HTTP 200 | `127.0.0.1:8013/api/health`、`127.0.0.1:5174/`、`127.0.0.1:5174/api/health` |
| 续写/质量门/连续性/运行控制联合定向回归 | `266 passed in 29.41s` | 当前 longform continuation digest 源码；覆盖续写、质量门、长篇包、运行态与本地脚本契约 |
| 新增续写与长篇账本测试 | `12+` | 真实 mission schema、近邻场景判断、后续轮硬约束、动态最低增量、Provider stub、人物状态/关系/时间线/逾期线索 continuation digest |
| 反向验证 | 已检出 | 承接锚点、普通文本围栏、续写规范化和动态最低增量变异均使目标测试失败；变异后源码已恢复 |
| 后端配置范围全量 | `3127 passed in 1462.20s` | 当前 longform digest 源码，未与变异测试并行；证据：`backend/logs/continuation-hardening-20260909/full_pytest_after_digest.txt`；pytest 配置仍排除若干真实 Provider/大模型专用测试 |
| 前端 type-check | 通过 | `npm run type-check`，在 `frontend` 目录执行 |
| 前端测试 | `83 files / 662 passed` | `npm run test:run` |
| 前端构建 | 通过 | `npm run build-only`，4918 modules transformed |
| 本地运行编排（历史证据） | 三项通过 | `start.ps1`；历史运行目录 `logs/run-20260909-130409-bd02113c` |
| 本地运行复验（最新人工复验） | 三端点 HTTP 200 | 2026-09-09 20:20：`127.0.0.1:8013/api/health`、`127.0.0.1:5174/`、`127.0.0.1:5174/api/health` |

`cd backend; .\.venv\Scripts\python.exe -m pytest -q` 是项目 `pytest.ini` 定义的后端配置范围全量门禁；它不替代真实 Provider 端到端验收。

## 4. 当前执行与后续计划

### 已完成

- [x] 找出并撤回破坏 `generate_chapter` 主入口的伪重构，并保留可恢复归档。
- [x] 恢复生成主链路后通过 229 项既有定向回归。
- [x] 增加状态化续写、长篇 continuation digest 和直接回归：Provider stub、近邻场景判定、动态收尾阈值、人物状态/关系/时间线/逾期线索均有覆盖。
- [x] 接受两路独立审查，补齐低增量循环、续写文本污染、真实 schema 字段、完成场景重演、取消检查、可观测性和预算收敛缺口。
- [x] 当前树前端三项门禁通过。

### 当前状态

- [x] 最新续写硬化及 longform continuation digest 后端配置范围全量：`3130 passed`。
- [x] 本地后端/前端服务已由 `start.ps1` 启动：后端 `127.0.0.1:8013/api/health`、前端 `127.0.0.1:5174/`、代理 `127.0.0.1:5174/api/health` 均已复验 200。
- [ ] 当前恢复后的主入口、前端状态链路和新增回归仍是未提交工作树变更；提交前须再次核对完整 diff 与用户新增二进制资产。

### 下一轮（以最新全量不回归为前提）

1. [x] 将异步 Provider stub 扩展到完整 `generate_chapter`：已覆盖两轮续写实际请求、状态落库、运行事件、停止原因、正文持久化、取消、低增量和 Provider 异常边界。
2. [x] 长篇状态包已收敛为 `LongformContextService.continuation_digest`，续写与优化器统一消费有界人物状态、关系、时间线、知识边界与逾期线索。
3. [x] 已完成高置信度一致性重复修复：局部修订后的验收改为 `check_only`；并完成结构质量门 no-op 复用，正文或段落结构发生任意变化时仍强制重算。
4. [x] 已将定稿正文页、生成中页面和失败态的降级阶段、正文保留状态、质量风险和可重试动作统一投影到前端；失败态已按 allowed_actions/retryable 展示恢复路径，且 evaluation_failed 无候选不再落空白页。
5. [x] 已补齐 HTTP POST → BackgroundTasks → worker → `generate_chapter` → status/SSE 的单一跨层集成回归；后续进行本地真实 Provider 可用时的章节端到端样本验收，记录 before/after 的连续性、字数、重复率和阶段耗时；文学双盲审阅包继续保持冻结状态。

## 5. 不可外推的历史结论

旧文档中“3103 后端全绿 / 654 前端全绿 / 最终状态”等描述只代表其当时源码。当前修复尚未提交，任何提交、切换分支或清理工作树前必须保留 `pipeline_orchestrator.py` 与 `test_continuation_context.py` 的当前差异，并以本文件所列命令重新验证。

## 2.5 跨层链路与前端失败分流收口（2026-09-09）

本轮不再堆叠无数据依据的评审重构，也没有使用 Docker；只处理已经由审查和回归证明的小说生成主功能缺口。

### 已完成

1. **新增真实 HTTP → BackgroundTasks → worker → Pipeline → status/SSE 回归**
   - 文件：backend/app/api/routers/test_writer_http_worker_generation_integration.py
   - 真实走 JWT、FastAPI 路由、隔离 SQLite、章节 claim、_schedule_generate_task、_generate_chapter_async、确定性编排器桩、版本自动选择、章节 status 和 SSE。
   - 已证明：HTTP 首先返回 generation_runtime.status=queued；执行实际后台 scheduler 后，章节为 successful，TaskRuntime 为 succeeded/completed，SSE 能回放 task_started 与 task_completed，run_id 保持一致。
   - 当前单测证据：1 passed。

2. **修复旧 run 被 supersede 后迟到版本串写**
   - 文件：backend/app/services/novel_service.py
   - append_chapter_versions() 在创建任何版本和 flush() 之前解析 generation_runtime.run_id，要求它与 expected_generation_run_id 精确相等并且章节仍为 generating。
   - 不再使用字符串包含判断；superseded_run_id 只保留为诊断字段，不具有写入授权。
   - 文件：backend/app/services/test_generation_run_rebind.py
   - 新增旧 run 拒绝且零版本写入、当前 run 正常写入两条反向回归；该文件当前证据：6 passed。

3. **修复无候选评审失败被空版本选择器遮挡**
   - 文件：frontend/src/components/writing-desk/layout/WDWorkspace.vue
   - 版本选择器现在必须有可预览候选；evaluation_failed、selecting、waiting_for_confirm 无候选时直接进入失败或恢复态。
   - 无候选 evaluation_failed 的顶部状态文案改为“评审未通过，请先处理根因或重试”；有候选时保持原候选确认语义。
   - 文件：frontend/src/components/writing-desk/layout/WDWorkspace.spec.ts
   - 新增无候选回归。
   - 当前写作相关前端证据：38 passed；npm run type-check 通过；npm run build-only 通过（4918 modules transformed）。

4. **生成主链路定向回归复验**
   - HTTP/worker、旧 run fencing、续写、运行事件、writer stream、TaskRuntime 和启动巡检的组合定向集当前为 63 passed。

### 仍开放、禁止假报完成的项目

1. **本机服务被强制停止或重启后的死亡 worker 快速回收**：当前仍按持久化 lease/heartbeat 和生成预算判断；没有新增未经迁移和回归验证的实例心跳协议。需要完成带实例 epoch、跨实例不误杀、启动停止 manifest 和 MySQL/SQLite 迁移的完整闭环后再实现。
2. **增强评审与 self-critique 的调用预算优化**：当前已有阶段计时、部分调用统计，但尚未形成统一的 provider attempt 和阶段预算账本；在采集真实样本前不直接删除或合并质量阶段。
3. **真实 Provider 文学质量验收、文学双盲标签和视觉人工检查**：工程链路已验证，文学质量仍需真实样本人工验收。
4. **本地停止脚本的 npm/cmd 包装进程精确收尾**：当前端口可释放，完整 start-time manifest 仍待补齐。

### 下一步执行顺序

1. 先为生成运行态补统一 provider 调用、重试和阶段耗时预算汇总，只增加可观测性和回归，不先改评审职责。
2. 为启动和停止生命周期设计并验证实例 epoch + manifest；先写失败回归，再接入生产代码。
3. 补充质量门失败和普通 Provider 异常的真实 HTTP → worker → status/SSE 跨层回归。
4. 运行完整后端和前端验证，最后核对全部未提交代码与 backend/storage 用户资产。

> 文档更新时间：2026-09-09 22:38:27 +08:00
