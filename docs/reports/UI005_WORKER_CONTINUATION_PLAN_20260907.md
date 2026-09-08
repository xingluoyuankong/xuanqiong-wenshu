<!-- STAGE13_CURRENT_BEGIN -->
> **20:56文学输入包：**25个既有去重样本的双盲A/B空白表与空仲裁表已冻结，验证器valid=true，4种变异全部检出且原包恢复；R2反向审计只改临时副本，原包字节恢复；没有人工真值，7项文学hard gap仍在，整体active/NO-GO。

## 阶段十三当前状态（2026-09-07 20:47 +08:00）

原任务“全面优化重构玄穹文枢”在本任务接续，使用子智能体，不创建新任务。总目标 **active / 发布 NO-GO**。此块覆盖下方全部历史“当前/最终”措辞；历史证据保留。

### 工程门禁已闭环

- 后端最终冻结全量：**3103 passed / 1681.28s / exit0 / valid_gate=true**；648 backend/部署非秘密代码配置输入、2760既有资产无漂移。`logs/backend-stage13-frozen-20260907T195722318687+0800.result.json`
- 前端最终门禁：**type-check=0、654 tests、build-only=0、114产物**；包括进度语义、可读性和会话初始化竞态修复。`logs/stage13-session-ready-fix-20260907-190347/final-gates.json`
- 真实工作台R7(dev)与R8(preview)均通过：真实JWT/API/Alembic/SQLite/独立worker/SSE/UI；候选、continuation、当前进度、DOM可读性、接受版本、重复接受幂等、刷新终态均有证据。R8：`logs/stage13-real-workspace-20260907T195925-c6d74764/runner-result.json`
- F06原生备份：64项默认临时目录契约通过；真实MySQL完整88表/2trigger/revision030包恢复通过。S13-07真实read completion提交前/后强杀通过，变异检出。证据见`logs/stage13-native-manifest-fix/`、`logs/stage13-native-live/run-20260907T184417-e9677d71/`、`logs/stage13-mysql-transaction-crash/`

### 发布仍保持NO-GO的真实缺口

- Docker实际运行：只读预检确认`desktop-linux` Engine命名管道不可达、Docker Desktop服务Stopped、`deploy/.env`缺失；示例Compose静态解析exit0不替代运行验收。`logs/stage13-docker-preflight-20260907/`
- 文学质量：**7项hard gap仍在、completion_eligible=false**；阶段十三只做只读证据盘点，Provider调用/新样本/人工标签/正文/数据库改动均为0。最小下一批是既有去重25样本双人盲审+仲裁，再做严格T16/E01.2、T06、E11/T22。`logs/stage13-literary-next-audit-20260907/`
- 其他未闭合：原生writer停写协调、完整MySQL网络/故障切换/其他事务矩阵、商业Provider端到端证据。

最终聚合：`logs/stage13-final-gate-manifest-20260907T2026.json`；完整计划：`docs/reports/STAGE13_EXECUTION_PLAN_20260907.md`。
<!-- STAGE13_CURRENT_END -->

<!-- STAGE12_CURRENT_BEGIN -->
## 阶段十二当前权威状态（2026-09-07 16:43 +08:00）

**包含数据库回归的后端默认全量已通过：3005 passed / 2283.95s / exit0 / valid_gate=true**。`logs/backend-stage12-frozen-20260907T160529164332+0800.result.json`；637代码/配置、2749既有资产无漂移。此前2993项通过，但默认testpaths遗漏app/db；已扩展而非缩小范围，并新增收集守护回归。旧“最终通过”不外推到新增收集范围。

- 时区策略6项+既有db5项+收集守护1项：12通过，移除策略/移除收集范围的进程内负控制检出。
- 真实+08 MySQL R4四项通过；实际Alembic首DDL同连接UTC、TIMESTAMP/归一化DATETIME正确，单event loop干净退出。
- SQLite与MySQL迁移库工具执行前/中强杀均通过；read至少一次、候选与冻结计划保持，仅模拟lease expiry；其他故障窗口待补。
- 文学审计29项/7反向通过但七项hard gap不变，completion_eligible=false。
- 原生MySQL全87表备份恢复、121外键检查、026写入拒绝与迁移重入通过；下一步其他MySQL事务崩溃窗口、真实后端浏览器、Docker部署；整体active/NO-GO。

详见`docs/reports/STAGE12_RUNTIME_AND_GATE_20260907.md`及`docs/reports/STAGE12_EXECUTION_PLAN_20260907.md`。下方所有旧阶段数字和“final”结论属于历史时点。

当前前端三门禁已重新执行并通过：83文件/634项，type-check/test/build均exit0，`logs/stage12-frontend-final-gates-summary-20260907-164721.json`。Docker实际daemon与deploy/.env缺失，配置夹具五种分支仅解析通过，不是部署通过。
<!-- STAGE12_CURRENT_END -->

# UI005：Worker 审批依赖续跑与严格 Context 读取实施计划

> **日期口径**：部分证据文件名沿用既有 `20260907` 批次标签；它们是历史运行批次标识，不表示当前日期。具体运行时刻以各证据文件的 `recorded_at` / `finished_at` 及其时区偏移为准。

<!-- S12_FINAL_GATE_CURRENT_BEGIN -->
阶段十二新增源码后的原始后端全量已通过：`logs/backend-stage11-frozen-20260907T153311499845+0800.result.json`，2993 passed，636代码/配置与2746既有资产无漂移。S12-03时区真实验收四项通过，S12-04 SQLite live强杀两场景通过；MySQL强杀矩阵和Docker部署仍待完成。整体目标仍 active，文学质量 `completion_eligible=false`、7项hard gap保留。
<!-- S12_FINAL_GATE_CURRENT_END -->

<!-- STAGE11_LIVE_STATUS_BEGIN -->
## 当前执行状态：阶段十二新增连接时区/强杀证据与最终全量已通过，继续收口未完成项

> 更新：2026-09-07 13:41 +08:00；以下覆盖旧“当前/最新”叙述。原任务 **全面优化重构玄穹文枢** 已只读核对，继续在当前任务 `01a06d1c-19e0-75e0-a30e-9c3d0bae9867` 执行，不新建任务。目标 **active**，发布 **NO-GO**。

| 范围 | 当前实测 | 证据及适用边界 |
|---|---|---|
| 阶段十二新增源码后最终后端冻结全量 | **2993 passed / 1547.77s / exit0 / valid_gate=true**；636代码/配置、2746既有资产无漂移 | `logs/backend-stage11-frozen-20260907T131232785321+0800.result.json`；原始pytest-q从头完整重跑，非拼接定向结果 |
| 当前前端三门禁 | type-check、build-only均exit0；**83文件 / 634 passed / 127.06s** | `frontend/audit/frontend-final-gates-20260907-112159/summary.verified.json`；重点8文件哈希一致，不声称全前端冻结 |
| SSE真实浏览器 | **2/2 passed**；独立29999端口，真实HTTP断流重连、60秒流、终态取消、Run切换隔离 | `frontend/audit/sse-isolation-20260907/final-sse-results.json`、`REPORT.md`；生产前端+受控HTTP流，不等于真实Provider全链路 |
| Continuation维护扫描 | 当前扫描15项通过；MySQL代次/时钟等组合 **141 passed** | `logs/stage11-mutation-audit/FINAL_SUMMARY.json`、`logs/stage11-mysql-claim-clock-directed.log` |
| 后端内存反向 | **旧修订10项7检出/3存活；新修订复验3/3检出**；无collection error | `logs/stage11-mutation-audit/FINAL_SUMMARY.json`；新增9项后扫描15项通过；M10默认正整数路径冗余，非正预算路径真实检出 |
| MySQL迁移及建表 | 独立MySQL 8.4.9；fresh upgrade exit0、head=030、实查87表；ORM新库83表 | `logs/stage11-mysql-fresh-readonly-verify.json`、`logs/stage11-mysql-alembic-upgrade-fresh.json`、`logs/stage11-mysql-create-all.json`；fresh库已单独只读复核，不混用旧head证据 |
| MySQL真实业务链 | **7/7通过**：Job/Run代次、旧完成拒绝、四实体CAS、双恢复者单赢家、UTC/expiry | `logs/stage11-mysql-continuation-business-20260907T122916-e70a7d19/result.json`；两类缺陷已修复；旧红测与真实MySQL反向结果均保留 |
| Docker | 2026-09-07 12:38只读探针exit1、daemon管道缺失；未改卷 | `logs/stage11-deployment-readonly-20260907T123803.json`；native MySQL不等于Docker部署矩阵 |
| 文学质量 | 七项hard gap仍保留；completion_eligible=false | `logs/stage11-quality-recheck-20260907T122447/gap-recheck.json`；四审计重算exit=0/2/2/0，标签与manifest未改；基础19条和T18六条均未填人工标签 |

### 当前执行计划与分工

1. **已修复 MySQL代次隔离**：`backend/app/agent/jobs.py` 的 claim 和 `backend/app/services/agent_runtime.py` 的 Run claim，采用明确赋值顺序；保留同owner未过期Run续租代次不变，换代后旧completion失效。定向141项、真实7/7、进程内Job/Run/clock三负控制及真实MySQL排序回退均检出。
2. **已补齐 反向覆盖闭环**：专属子智能体已补 `backend/app/agent/test_continuation_scan_fairness.py` 的activation扫描上限和异常游标回滚；3个旧存活变异均重新检出；正整数预算M10冗余与非正预算差异分开说明。
3. **阶段十二新增源码后最终门禁待重跑**：阶段十一第三轮历史基线为2993 passed；本轮新增MySQL连接UTC策略、时区测试及seed字节修复，必须重新执行原始pytest-q。S12-03专属18 passed，S12-04 live强杀通过，S12-07仍completion_eligible=false。
4. **P1 MySQL恢复矩阵**：同实例双连接与跨OS进程claim/recovery/CLI重启已通过，`logs/stage11-mysql-cross-process-20260907T125031-69e4e31d/result.json`；MySQL命令9项验收`logs/stage11-mysql-command-order-20260907T131017-9950da8c/result.json`。下一步为执行中强杀、部署默认时区和真实迁移建库启动路径；保留所有失败数据库和日志。
5. **P1 部署矩阵**：Docker daemon可用时另验迁移/备份/恢复/部署；不重置既有卷，不把native MySQL结果外推为Docker通过。
6. **P2 文学质量七项**：依次推进E01.2受控对照、E11/T22真实repair、T06统一cohort、T16严格before/after、T18豁免质量真值、T26真实语料校准、human标签；缺样本时记录缺口，不伪造收益。

阶段十一实施记录：`docs/reports/UI005_STAGE11_MYSQL_BUSINESS_AND_FINAL_GATE_20260907.md`及`docs/reports/UI005_STAGE11_SCAN_FAIRNESS.md`。下一阶段方案：`docs/reports/STAGE12_EXECUTION_PLAN_20260907.md`。所有历史失败与旧门禁继续保留。
<!-- STAGE11_LIVE_STATUS_END -->


> **交付时最新状态**：边界回归已从先前20项推进到 **26 passed / 135.59s**，见`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-final.log`；相关组合另有 **213 passed / 217.73s**，见`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-green3.log`。486项保留为边界修复前的历史定向，不与26或213累加。边界5文件指纹已记录在`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundary-freeze.json`，本次核验5/5与磁盘一致。正式后端冻结全量仍待完成，不再写“等待边界20项修复”。
> 探索性session54497已在45%主动结束，observed_failures=8、valid_gate=false，依据`D:/小说写作/xuanqiong-wenshu/logs/stage8-exploratory-full-status.json`；最终从头执行原始全量，不删测试、不跳测试。根任务入口保持主代理现状，本次未编辑。

> **阶段八当前状态（证据批次2026-09-07）**：批次A/B已完成，批次C持久化交接核心已实现，批次D新增边界26项已通过，进入冻结门禁验证。既有定向 **486 passed / 232.44s**，五类worker反向保留；正式冻结后端全量待执行完成。整体 **active / NO-GO**。
> 后附原阶段七审查文本、旧行号与哈希仅为历史记录，其中“未实施”“本轮未执行”及旧执行窗口不覆盖本顶部状态。

## 阶段八证据与进度

| 项目 | 核验结果 | 证据与适用范围 |
|---|---|---|
| 阶段八既有定向组合 | **486 passed / 232.44s** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-final-targeted.log`；日志只有进度及pytest汇总，没有独立exit code、完整命令或节点清单；不据此补写退出码，也不覆盖随后边界修复 |
| 五类worker反向 | **旧3类保留，新增2类检出** | 两份脚本及五份JSON详见阶段八报告；`source_unchanged=true`只证明各次变异前后被检查文件未变，不证明之后工作树冻结 |
| 前端阶段八指纹复核 | **267文件，changed_files=[]** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-frontend-baseline-recheck.json`；保留601项/type-check/build历史基线，不宣称本次重新执行前端测试 |
| Docker阶段八只读探针 | **exit1 / Server=null** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-docker-readonly-probe.json`；read_only=true、reset_or_volume_changes=false，未改卷；MySQL实机门禁仍未通过 |
| 后端上一全量基线 | **2358 passed / 1020.08s** | `D:/小说写作/xuanqiong-wenshu/logs/backend-full-stage7-20260907.log`；仅阶段七冻结批次，不是当前阶段八源码全量背书 |
| 阶段八探索性全量 | **session54497约45%主动结束；新增红测8失败；非冻结** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-exploratory-full-status.json`：执行中源码发生漂移，`valid_gate=false`；仅作边界修复线索，不作为全量结论 |
| 阶段八正式冻结门禁 | **边界26项通过后执行正式冻结全量** | `D:/小说写作/xuanqiong-wenshu/logs/run_backend_stage8_frozen_gate.py`已存在；本次仅阅读脚本，未启动runner |
| 文学质量 | **七项硬缺口仍保留** | E01.2 prompt gain、E11/T22 repair gain、T06 degrade rate、T16真实before/after、T18 exemption truth、T26 dialogue marker calibration、human labels；工程回归不替代收益证据 |

## 批次C/D当前实现与设计决策

- 复用AgentJob承载`agent_continuation`；key按PlanRevision/Approval/outcome去重，同key异payload报冲突。只有executed/rejected/execution_failed形成终态意图，approved不是执行证明。
- 从关系PlanRevision、ContextSnapshot、CapabilitySnapshot、Approval、Step、source Job验证冻结材料；独立消费者复用原始global order、依赖、参数和step key，不重新调用Planner。
- 写候选已生成后的step/fact/approval/intent/Run状态采用统一数据库提交；Provider调用、文件生成和质量工作在此前发生，不属于跨数据库与文件的原子事务。
- 保留initial/replan的`execution_job_id`，续跑另写`continuation_job_id`；后续写审批绑定step的`approval_source_job_id`，每次write独立审批；真实legacy/direct路径保留candidate-only。
- 用户pause/cancel优先，source ACK需成功或精确过期handoff+完整写证明；registry执行时仍校验能力关系。已存在隔离与lease保护分支，剩余竞态按以下退出标准验证。

## 下一批计划与退出标准

1. **边界回归已通过，进入冻结复核**：26项边界及213项相关组合日志已存在；复核`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundary-freeze.json`五文件指纹与冻结定向结果。畸形intent隔离、精确handoff/CAS、dead-letter、Run lease接管、晚到写终态、source绑定和并行审批已有新增回归，不重复当作未实现事项。
2. **复核冻结覆盖与有效反向**：保留26项边界结果，针对当前冻结源码复跑受影响反向并核对相关组合；独立进程恢复、真实数据库并发及部署结果仍单列，不由fixture回归外推。
3. **冻结后跑正式后端全量**：使用 `D:/小说写作/xuanqiong-wenshu/logs/run_backend_stage8_frozen_gate.py`，从头执行原始全量 `-m pytest -q`，不删测试、不跳测试。脚本在backend目录调用原虚拟环境python，以独占创建方式输出带时间戳的before/result JSON和日志；比较代码/配置及既有数据文件指纹。门禁须exit0、代码无漂移、既有资产无变化；session54497的探索性结果不替代这次冻结验收。
4. **归档与独立门禁**：保留旧失败、五类反向及探索日志；冻结结果出现后更新三个当前入口。Docker/MySQL实机与七项文学质量缺口分开推进，整体维持 **active / NO-GO**。

## 追加反向证据（已完成，不重复列为待新增）

- `D:/小说写作/xuanqiong-wenshu/logs/stage8-continuation-additional-mutation.py`：source-ack-no-recovery为**1个业务断言失败+1个正常对照通过**；read-fact-no-failure为**1个业务断言失败**。
- 两份对应JSON均为`source_unchanged=true`；旧producer-no-intent、reject-no-cancel、consumer-no-read三类证据保留。
- 追加反向覆盖的是精确用例，不代表source/Run lease所有并发排列或重试耗尽矩阵已通过。五类完整文件、用例与结果见`D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_STAGE8_CONTINUATION_IMPLEMENTATION.md`。

## 接续入口

`D:/小说写作/xuanqiong-wenshu/TASK_HANDOFF_NOVEL_QUALITY.md`顶部已纠正历史入口；当前门禁以`D:/小说写作/xuanqiong-wenshu/docs/reports/CURRENT_EXECUTION_STATUS_20260906.md`为准。本次只改指定三个文档，不启动正式runner或新task/thread。

---

## 历史阶段七审查与原始设计（原文保留，非当前实现结论）

# UI005：Worker 审批依赖续跑与严格 Context 读取实施计划

> **阶段七进度覆盖**：批次A严格worker读取和批次B等待语义已落地，267项组合、有效反向与全量2358通过（481文件一致）。后续批次C/D持久化continuation/并发恢复未实施。旧行号和“仍存在”描述是修改前审查记录；实现证据见UI005_STAGE7_WORKER_CONTEXT_WAITING.md。

> 主代理阶段六验收补记：正确backend目录全量已2273通过/956.63s，476文件指纹一致，原session62065自然exit0。以下worker修复尚未实施；历史冻结期间的只读审查记录保留。

- 日期：2026-09-07（项目本地日期；文件名按委托指定）。
- 性质：只读源码审查 + 解冻后的有界实施设计；不是修复完成报告。
- 冻结约束：阶段六 session62065 保持原状；本轮未运行测试、应用/worker 子进程，未访问数据库，未修改源码、测试、既有报告及数据。唯一写入为本文件。
- 结论：原审计 F02、F03 在本次读取的 worker 代码中仍存在。审批专项 context helper 已严格化，不代表 worker 已接入。原审计中的内存探针及阶段六运行状态均非本轮实测结果。
- 功能底线：保留 chapter.generate → statistics.project（depends_on=[1]）以及多节点 write→read DAG；不改成只支持 read→write 或写工具必须末步，也不通过删依赖/删断言缩小验收。

## 1. 行号证据索引

所有行号来自当前工作区而非原审计旧行号；文件 SHA-256 在附录保留。下文 E 编号均指此表中的绝对路径。

| 证据 | 文件（绝对路径）与行号 | 静态事实 |
|---|---|---|
| E01 | D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_REQUIREMENT_AUDIT_20260906.md:95–111 | 原 F02/F03 定义、历史探针范围及预期验收 |
| E02 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/execution.py:730–805 | completed 集合从空开始；未完成依赖统一 fail；write 创建审批后 continue |
| E03 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/execution.py:1214–1256 | 保存 context，Run 转 awaiting_approval，handler 正常返回 |
| E04 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/execution.py:308–327,411–488 | 缺 key、缺 row、session/user 不符、digest 错误均返回 None；后续仍解析 Run JSON refs |
| E05 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/approval_context_contract.py:19–103 | 严格 refs、schema=1、定位与身份、摘要、用户 refs 前缀及参数投影检查 |
| E06 | D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_runtime.py:2340–2357,2375–2448 | 审批建立、approved→executing CAS、executed/execution_failed、decision 与事件分别提交 |
| E07 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/write_executor.py:126–181,285–364,617–620 | 写前 claim；写成功逐次完成 step/fact/approval 后 paused；异常失败；接受候选另行完成 Run |
| E08 | D:/小说写作/xuanqiong-wenshu/backend/app/models/agent.py:83–110,159–175,228–259 | step、approval、job 唯一约束；attempt/lease_generation 字段 |
| E09 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/jobs.py:20–35,83–118,138–217,276–311,344–380,383–480 | 入队/claim/ACK/retry 门禁、唯一键返回 existing、有限 handoff reconciliation |
| E10 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/worker.py:70–94,131–191 | execution 异常先投影 Run failed；poll_once claim、调用 handler、complete/fail |
| E11 | D:/小说写作/xuanqiong-wenshu/backend/scripts/agent_worker.py:26–64 | CLI 实际注册 agent_execution、visible_response 两类 handler |
| E12 | D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_runtime.py:963–1002,1033–1124 | ensure_step 身份复用；claim_step 对非 completed 广泛可重领；完成/失败 fence |
| E13 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/execution.py:538–570,602–666,1045–1065,1119–1161,1385–1411 | 每次普通 execution 调 Planner；冻结计划、replan 新 job、恢复仅 queued/running |
| E14 | D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_runtime.py:780–827,1870–1888 | initial 用户 refs 后附自动 novel refs；resume 仅恢复生命周期状态 |
| E15 | D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_plan_service.py:19–35,45–96,144–165 | PlanRevision digest、context parent、revision parent；已有按 planner/Run 查询 |
| E16 | D:/小说写作/xuanqiong-wenshu/backend/app/api/routers/agent.py:121–193,453–458,1276–1296,1484–1489 | 注册审批执行与 decision 分离；初始 execution job key |
| E17 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/state_machine.py:10–37；D:/小说写作/xuanqiong-wenshu/backend/app/agent/retry_policy.py:6–37 | Run 状态图、claimable 状态与 retry 分类 |
| E18 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/command_worker.py:110–131 | resume 命令调用生命周期 service；不是审批 DAG continuation |
| E19 | D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_worker.py:223–318,361–503,505–651,758–844,857–953 | 可复用真实 worker fixture、依赖实际失败、replan、重试与 ACK 恢复测试模式；本轮未运行 |

## 2. 当前状态与缺口（Evidence → Finding → Path）

### 2.1 审批成功、拒绝、失败必须分层理解

| 情形 | 当前 Approval | 当前 Step / Run | continuation 决策 |
|---|---|---|---|
| 等待决策 | pending | write step awaiting_approval；首轮结束 Run awaiting_approval | 依赖只等待；不得认定失败 |
| 用户同意 | approved | decision 方法未完成 step，也未自动调用写执行 | 仅批准不是依赖完成，不触发下游 read |
| 正在执行 | executing | 写执行 CAS 后 claim step，Run running/write_candidate | 下游继续等待 |
| 候选执行成功 | executed | step completed；写事实完成；Run paused/candidate_ready 或 paused/quality_blocked | 若仍有可执行依赖，持久化续跑意图；候选接受保持独立 |
| 用户拒绝 | rejected | decision 只保存审批与公开事件；未显式结束依赖 step/Run | 确定性终止受影响依赖并落事实，不放行 read |
| 写执行 try 内失败 | execution_failed | step 尝试 fail；Run failed/write_candidate_error | 终止该计划，不自动重放写入 |
| 写前合同/权限校验失败 | 通常仍 approved（取决于异常位置） | handler 前失败不等于 execution_failed | 记录合同拒绝；禁止误发“写成功”续跑 |
| 执行途中崩溃/取消 | 可能停留 executing | claim 已提交，step 可能 running；CancelledError 分支只更新 provenance 并重抛 | 需要有界对账；不把 executing 当成功，也不自动重新生成候选 |

证据 E06/E07/E16。成功输出是候选 Artifact，不等于正文版本已接受；quality_blocked 仍可属于“候选生成成功”。statistics.project 后续读取当前项目事实，不应声称读到了未接受候选的新正文。依赖生成成功与依赖接受成功应是不同语义，本次保持既有生成依赖，不添加自动接受。

重要事务边界：E07:285–302 依次调用会提交的 complete_step、complete_write_execution、mark_approval_executed、update_run。存在 step completed 但 approval 尚 executing、approval executed 但 Run 尚未 paused 等窗口。E07:149–180 的 claim 与部分准备在主 try 之前，异常也可能留下 executing；本计划不承诺外部 Provider exactly-once。

### 2.2 F02：等待被误记失败，恢复入口不等于续跑

- Evidence：E02:754–769 将所有不在 completed 集合的前置统一记为 DependencyNotCompleted；E02:785–805 刚把 write 挂起等待审批。
- Finding：write→read 第二步首轮就 failed；其后仅改变 Run 状态不会纠正持久化依赖事实。
- Path：真实 AgentWorker.poll_once → agent_execution → pending write approval → downstream failed。
- E03 的正常返回经 E10/E09.complete 将原 job 标记 succeeded（Run awaiting_approval 属于 ACK 允许状态）。因此 E13:1385–1411 只恢复 queued/running 的原 job，并不继续 succeeded job。
- E13 有因 read failure 创建 revision job 的 replan 路径，但它会重新规划；不是审批后精确复用原 DAG。E14/E18 的 resume 只变更 Run 状态。
- 在本次界定入口中，decision 和写成功均未创建审批 continuation。此结论限定于上述调用链，不宣称仓库任意未来入口都不存在。

### 2.3 现有 worker / step 契约

1. 真实 CLI 注册任务仅 agent_execution、visible_response（E11）；AgentJob.kind 是普通字符串，并非数据库枚举。AgentRunCommand 的 pause/resume/cancel 是另一条命令队列（E18）。
2. Job 唯一键是 (run_id, idempotency_key)；初始 key 为 {run.id}:agent_execution，replan 为 {run.id}:agent_execution:revision:{revision_number}（E08/E13/E16）。create_job 命中 existing 即返回，未核验相同 key 的 kind/payload；新 continuation 必须额外核验材料，不能仅凭“拿到一行”当正确去重。
3. Step 唯一键有 (run_id, step_order) 与 (run_id, idempotency_key)；现有 key 为 {run.id}:step:{index}:{tool_name}。ensure_step 复用 existing 并核验工具/key，不覆盖已冻结 input。Approval 对 (run_id, step_id) 唯一（E08/E12）。
4. claim_step：completed 直接返回；其他状态只要 lease 空/过期或相同 owner 就可能重新 claim，attempt_count、lease_generation 加一；没有 step 自身最大重试预算，也未内置“rejected/cancelled 不重跑”的 DAG 策略。故调度器必须先校验依赖与终态再 claim。完成/失败传 owner+generation；旧 lease 不得覆盖新结果（E12）。
5. Job claim 仅 queued 或 lease 过期 running，受 available_at、Run claimability、cancel gate 和条件 UPDATE fence 约束。普通 paused、awaiting_approval 不可 claim；paused/recovery_ready 仅为已持久化任务的显式恢复例外，不能拿来绕过审批或用户暂停（E09/E17）。
6. Job 默认 max_attempts=3（限制 1–10）；已分类瞬时错误退避后 queued，预算耗尽 dead_letter，非重试错误 failed。attempt 上限在 fail 分类分支执行，不是每次 lease reclaim 前的统一限额（E09/E17）。
7. E10:74–90 对 execution 任意异常先把 Run failed；即使队列把 job 重新 queued，也可能被 Run 终态门禁卡住。新 continuation 的瞬时异常应保持 Run 可恢复，完整性错误则终止；不照搬此包装器。
8. E09.complete 不接受 paused/failed/cancelled 的父 Run。新续跑结束要回 paused/candidate_ready 时，应原子 ACK + Run 迁移，或添加只针对有持久化证明的交接 ACK；不要全局放开 paused 的 job completion/claim。现有 reconciliation 仅处理 completed Run 的 visible_response 及其 execution handoff，不覆盖 approval wait/candidate handoff（E09:383–480）。

## 3. 最小持久化 continuation 设计（解冻后实施）

### 3.1 复用现有表，增加专用 job kind 和冻结材料

建议新增 agent_continuation handler，复用 AgentJob 为持久化意图，不新增消息代理/定时内存任务。与普通 agent_execution 分入口，避免续跑再次调用 Planner。

- Job key：continuation:v1:<PlanRevision.id>:<Approval.id>:<outcome>；run_id 已在唯一约束中，outcome 只允许 executed/rejected/execution_failed。按现有 UUID 长度小于 255；写入前检查长度而非靠截断去重。
- payload 必填并版本化：schema_version=1、run_id、source_job_id、plan_revision_id/key/digest、context_snapshot_id/key/digest、capability_snapshot_id/key/digest、approval_id、step_id、outcome。全部从可信关系行取值；同 key 不同材料应明确冲突。
- 原计划与依赖以已验证 PlanRevision.plan_json 为准（E13/E15），step 参数取已持久化 input_json，保持 global step_order 和现有 step key。未创建的后续 checkpoint 从冻结 revision 材料创建；禁止按“工具名→参数”重建出另一份计划。
- intent 只传定位与摘要，不复制正文、Provider 凭据或任意请求参数。pending/approved/executing 不进入成功通知。
- 无关系 PlanRevision 的真实旧 Run 不伪造现代 continuation。保留其原恢复路径；需要对旧待审批计划升级时，另行审查可验证材料和显式迁移，本批不静默重造原计划。

### 3.2 生产者、Run 门禁与 ACK 必须闭环

按 Run 加事务级互斥/条件更新，围绕终态建立单一“结果提交”服务；不要从多个 HTTP 路由各塞一条 job。

1. **成功提交**：在已有候选与质量结果落地后，将 step 完成、execution fact 成功、approval executed、continuation intent 与 Run 调度状态放入同一数据库事务。为相关 service 增加受控 commit=False/事务组合接口；不能在 mark_approval_executed 已提交之后仅 best-effort create_job。
2. **拒绝提交**：approval rejected + 写 step cancelled（保留 ApprovalRejected 原因事件）+ 传递依赖 cancelled + 终止 outcome intent/事实同事务。最小版本按整份计划确定性停止，不偷偷选择新计划或调用下游。Run 经状态图合法转入 cancelling→cancelled；保留既有已完成步骤和 Artifact。
3. **失败提交**：execution_failed + step/fact 失败 + DependencyFailed 终止结果及 intent 同事务；Run failed。终止 outcome intent 不应作为可运行的 read job 留在 failed Run 上：在同一事务结算为 cancelled 并保留 result 中的终止原因，成功 intent 才 queued。
4. **用户暂停/取消优先**：queued intent 可先持久化但不 dispatch；普通 pause、cancel_requested、终态保持门禁。由于现有 create_job 拒绝 paused/awaiting_approval 新任务，新增窄化 intent 持久化接口，核验上述审批终态、原计划归属与材料；不放开通用 create_job。
5. **首轮 worker 交接屏障**：approval UI 在原 worker ACK 前即可操作。成功 intent 先保存，只有 source job 已 succeeded 且 Run lease 已释放，或过期 lease 已通过等待边界事实对账，才激活为 Run running/continuation。原 worker 的 waiting context/状态写入也须同一 Run fence，防止晚到的 awaiting_approval 覆盖已成功写入/续跑。
6. **调度激活**：无用户 pause/cancel、前置已提交且交接成立时，CAS 把候选等待/审批等待门禁转 running/continuation；保留 candidate_ready/quality_blocked 为返回阶段，候选 Artifact 状态不改变。不能借普通 resume 把 rejected 或 executing 当 executed。
7. **消费者结束**：有下一道 write 则新建/复用 pending approval 并回 awaiting_approval；仅剩候选接受则回 paused/candidate_ready 或 quality_blocked，而非 completed。job succeeded ACK 与该状态落地原子化，poll_once 对已完成的受 fence 交接不重复 ACK。没有候选等待才沿现有完成/响应路径。
8. **对账入口**：worker 每轮 claim 前做有界批次（例如最多 100 个终态审批/待交接 intent）检查，按唯一键补齐历史断点并核验材料；同时处理 paused/failed 的终止 intent，不能依赖这些 Run 被普通 claim。禁止全表无限扫描。事件不是唯一真相，终态关系事实才是依据。

外部 Provider/文件写入不属于同一数据库原子事务。executing 且无完整完成证明的崩溃只进入待人工处理/明确重试授权状态，不盲目再次调用 writer；只有已完成 step + 对应成功 execution fact + 可校验 Artifact 足以支持无重写的终态补齐。并发唯一键冲突需 savepoint/回滚后重新读取并验证，不丢失调用者整笔事务。

### 3.3 依赖调度表与最小执行算法

| 前置状态 | 下游处理 |
|---|---|
| 全部 completed，且 write 对应 approval=executed、成功事实完整 | ready；claim 自己的 step；执行一次 |
| pending / awaiting_approval / running / approved / executing | 保持 pending，记录 blocked_by 和稳定等待事件；不调用 fail_step，不消耗下游 attempt |
| rejected / cancelled | cancelled + DependencyRejected/DependencyCancelled 事件；不调用 handler |
| failed / execution_failed | failed + DependencyFailed；保留原失败，禁止普通续跑重领 |
| 缺失 dependency 节点、循环、跨 revision/Run 引用 | InvalidPlanDependency 合同错误，不视为暂时等待 |

消费者先读取所有原 revision checkpoint，建立持久化状态索引，再做拓扑判断；不是从本轮循环里的空 completed 集合推断历史完成。completed 输出按 step_id 去重复用；相同 capability 多次出现在计划时仍分别按 step 定位。消费者绝不重新执行已成功 writer，不因为 claim_step 返回 completed 就再次调用 handler。

多个独立可执行节点可以推进；汇合节点要等全部前置完成。多个审批 intent 串行获得 Run fence，避免 A/B 成功通知各自唤醒同一下游；job 去重只是第一层，step lease/fact 唯一性是第二层。

## 4. F03：复用严格 context 读取，而非复制审批入口

### 4.1 抽取职责

从 E05 抽出中性、无审批依赖的 strict Run context reader，返回 verified snapshot + 严格解析/解析后的 refs；审批 helper 保留其 arguments 投影校验。worker initial/replan/continuation 在 Planner、read handler、Provider 调用之前统一进入 reader。worker 不应构造假 approval 或假 manifest 来复用校验。

保留 E05 已有严格 schema=1（排除 bool/字符串）、双 locator 字符串校验、run/session/user/project/correlation/transaction 关系、digest、用户 refs 与 current JSON 一致性。错误使用稳定 code+field，不把 refs、正文、摘要材料或原始异常拼进公开 message。未知 context/schema 版本明确报错，不“尽量 JSON 恢复”。

### 4.2 modern 与真实 legacy

- modern 证据：任一现代标记（含损坏/null 值），或 Run 已有关联 catalog/capability/context/plan 事实。缺任一必要 locator、缺 row、错误归属或摘要错误都终止，绝不返回 legacy None。
- 真正 legacy 正例：按旧模型最小字段直接建立的历史形态 Run；无现代声明且查询不存在现代关系事实，有合法 JSON refs 时仍执行严格类型、项目归属和资源存在性校验。不要用当前 create_run 后删除两个 key 冒充历史兼容。
- 仅“所有现代 key 都不存在”不够；删除 key 但关系事实仍在应判损坏。若 key 和关系事实都被完全清空，仅现有字段未必足以识别原年代，应明确此识别极限；不要编造生产迁移时间阈值。后续可用可信迁移版本/导入来源补强。
- require_snapshot 应来自关系事实与声明联合判断，而不是调用者随意传 false。session 缺失是入口错误，不降级。

### 4.3 initial / replan / continuation 一致性

- **initial**：E14 的 refs 为用户 refs 前缀 + 自动 novel refs；自动 refs 不一定属于 AgentContextRef schema。校验前缀与 frozen context_refs 对齐，整组 refs 顺序与摘要成立，自动 novel 材料按其自身合同校验；不强制所有 refs 都是用户 refs。
- **replan**：E13:1119–1125 仅写 canonical 用户 refs，context_kind=replan_context。严格类型与默认 role 规范化后相等应接受，不因 initial 的自动后缀缺席而误报。按当前 replan 的明确 locator 读取，不“取最新”来掩盖 key 损坏。
- **continuation**：锁定 intent 的 PlanRevision/context_snapshot 及 digest，校验 PlanRevision.context_snapshot_id 与指定 snapshot；若 Run 已进入另一 revision，旧 intent 标为 superseded/cancelled，不把旧 approval 套到新 revision。E05 注释已说明当前审批只绑定 current Run snapshot，并未记录独立 approval-version；本设计在 continuation intent 中补齐冻结关联，不倒称现状已有。
- 只比较合同相关 refs/关系，不要求整个可变 run.context_json 等于初始 frozen JSON：goal 外的运行进度、tool_results、plan/job locator 会正常增加。原计划参数、digest 与 refs 由各自冻结事实验证。
- 永久完整性错误：Run failed + job 非重试失败 + 稳定错误事件，Planner/工具/Provider 零调用。瞬时 DB 故障：走 retry policy，不吞成 None，不先把 Run 永久 failed。

## 5. 解冻后的真实 worker 测试清单（本轮全部未执行）

统一用临时数据库 + 真实 AgentRuntimeService/AgentWorker.poll_once/job service/关系模型，重新打开 session 模拟恢复。仅 Planner 决策与昂贵 Provider 叶子用确定性替身，审批走实际注册执行入口；不抽取循环替代真实 worker，不以伪造 context 字典替代现代 Runtime fixture。

| 编号 | 场景 | 必须断言 |
|---|---|---|
| W01 | write→read 首轮 | approval pending；write awaiting_approval；read pending/blocked；read attempt=0；无 DependencyNotCompleted；原 job 可 ACK |
| W02 | approved 但未 execute；executing 未完成 | 无下游执行；不因为决定成功就派发成功 continuation |
| W03 | 写候选成功后再 poll | 1 个匹配 intent；read 真执行一次；writer/Artifact 不重复；原 PlanRevision、参数、step key 不变；Planner 无新增调用 |
| W04 | 重复成功投递、重复 poll/重开 session | 相同 key 复用，同 key 异 payload 冲突；read 结果/完成事实去重 |
| W05 | rejected | 不调用 writer/read；下游终止原因与审批一致；不重新 pending 审批；Run 合法终止 |
| W06 | writer try 内失败、实际 read 前置失败 | 保留原错误；下游不执行；非等待错误；不利用 claim_step 将 failed 重新跑成成功 |
| W07 | 双 worker / 两个批准汇合 | 条件 claim/fence 生效；仅一次 downstream；活 lease 冲突不标 Run failed |
| W08 | 终态提交前/后、ACK 前崩溃 | 同事务回滚或重开 session 后发现 intent；原 worker 过期 ACK 对账；不依赖请求内 asyncio task |
| W09 | approval 执行早于首轮 worker ACK | 等待交接屏障；晚到 waiting 状态不覆盖结果；无重复 Planner/失败依赖 |
| W10 | candidate_ready 与 quality_blocked 各自续跑 | read 继续，候选仍未接受；结束回对应 paused 阶段；ACK 成功；正文版本数不增加 |
| W11 | 用户 pause/cancel 与成功提交/claim 竞争 | intent 可存但 pause 下不执行；resume 才恢复；cancel 获胜不复活；旧 lease 不写新结果 |
| W12 | 瞬时 DB/Provider 类错误、重试耗尽 | queued+退避且 Run 可恢复；预算耗尽 dead_letter；完整性错误不重试；旧 generation ACK 被拒 |
| W13 | write→read→write，多前置等待/独立分支 | DAG 保留；第二个 write 单独审批；汇合等全部完成；独立节点按冻结计划推进 |
| W14 | replan revision 与旧 continuation 竞争 | global order 不重复加 offset；旧 intent 不跨 revision；当前 PlanRevision/context 关联正确 |
| C01 | 真实旧 Run，无 key/关系事实，有/无 refs | 保留合法 legacy；非法类型、跨项目和失效 refs 仍拒绝 |
| C02 | 真实 modern initial，有自动 novel 后缀 | 严格 reader 成功；前缀/后缀语义不混淆；JSON list 与 canonical 往返正常 |
| C03 | 真实 initial→replan→continuation | initial/replan 各自 key/digest/refs 正确；不误取 initial/最新快照 |
| C04 | 缺/null/空白/错误类型 locator、缺 row | 显式现代合同失败；单删/双删 locator 但保留关系同样失败 |
| C05 | schema True/字符串/0/未知版本；refs 非数组/错误整数类型 | 严格拒绝，无宽松类型转换绕过 |
| C06 | run/session/user/project/correlation/transaction 错配 | 全部 fail closed；Planner/read/write/Provider 零调用 |
| C07 | digest 错；refs 内容改并重算 digest；乱序/重复/缺前缀 | 分别验证内容完整性与关系一致性，不只测试旧 digest 损坏 |
| C08 | 敏感哨兵 refs/正文进入异常 | 公共错误和事件仅 code/field；不泄露材料；无 visible_response 后续 job |

反向验证仅在解冻后：进程内 monkeypatch/加载时 mutation 恢复“等待→failed”、抑制 intent 入队、恢复 F03 吞异常、跳过依赖终态或 snapshot 关系校验，分别要求 W01/W03/C04–C07 等失败。不得改共享源码落盘，不删既有失败前置/replan/审批测试；测试数据只用临时数据库。本轮没有运行这些 mutation。

## 6. 有界交付顺序与退出标准

1. **批次 A / F03**：先写 C01–C08 红测，再抽中性 reader 并接 worker，保留审批 wrapper；initial/replan 均绿后结束这一批。不要顺手重构整个 context 系统。
2. **批次 B / F02 等待**：W01/W02/W06/W13 红测；实现 pending-blocked/terminal 区分及 persisted checkpoint 索引。尚无 continuation 时只能标记“等待语义完成”，不关闭 F02。
3. **批次 C / 持久化交接**：W03–W05/W08–W10 红测；实现专用 intent/handler、终态事务组合、原计划复用、Run/ACK 门禁；明确审批 outcome 成功不是批准成功。
4. **批次 D / 并发恢复**：W07/W11/W12/W14、进程内反向；审查新 job kind CLI 注册、错误分类及有限对账。真实 CLI/进程级重启验证须另获解冻执行窗口，不在本轮启动。
5. **结束条件**：新增真实 worker 矩阵与既有依赖失败/replan/审批回归通过，反向测试按设计失败，仍支持 write→read，且不增正文版本/重复候选。然后由主代理安排冻结解除后的集成门禁；本报告不推断 session62065 结果，不据此关闭原 F02/F03。

需要主代理在实施前确认的两个有界决策：拒绝采用本计划“整份计划确定性停止”还是仅停止后代分支；quality_blocked 候选生成后的 read 是否照常继续。本计划默认前者整计划停止、后者继续 read 但禁止接受/正文写入，均保持原 write→read 功能。若要不同产品语义，只调整终止/质量门规则，不把等待误写成失败。

## 附录：本轮只读材料 SHA-256

用于后续发现源码变化后重新定位行号；不是 git clean 证明，也不是测试通过证明。

- `D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_REQUIREMENT_AUDIT_20260906.md`
  - SHA-256: `332f39dddf2b721d0e334449b38e144228a3861ea857a52fa2cf251ae364b50c`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/execution.py`
  - SHA-256: `1141609b1bea198cd9efb234a1213acc9d19c1ba448745276b8f5e0815ad04a9`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/approval_context_contract.py`
  - SHA-256: `89d15f47b9a6c79cd4e83a340059a2feed15dc4e1a68e8b66a6fa0003333f0a8`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/jobs.py`
  - SHA-256: `166d2077845c90d1ba8bee871a0e8b2641c7ef7b35d068ea4f07b550d5dd7f72`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/worker.py`
  - SHA-256: `38f34fe34c13b2bc05a4470b75b30f0a9b73892d1eb1d53bff8af1ffa5cac1dd`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/write_executor.py`
  - SHA-256: `025eb6858fb566e02c5f07dcf87c8ef5f87bfde680664e7e2ee3e35f18750867`
- `D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_runtime.py`
  - SHA-256: `ceeccf7afba96b7ea4cfffedeb2a2e98a6c50f7256f7ef12ca60d8c0bb1cdb5f`
- `D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_plan_service.py`
  - SHA-256: `98aa78245af6c37c026f2a82e64692e51a0659c2e575881597404b37fa82f2bf`
- `D:/小说写作/xuanqiong-wenshu/backend/app/api/routers/agent.py`
  - SHA-256: `7403a155bad4f7ada7b2f924d769efdd0caf6ec5f6350bc757edca2880db5e54`
- `D:/小说写作/xuanqiong-wenshu/backend/scripts/agent_worker.py`
  - SHA-256: `fbeb6216738ef845d0adafcf5c0e6aa47d2faa7ddb7e60234fb6995a38fbff2f`
- `D:/小说写作/xuanqiong-wenshu/backend/app/models/agent.py`
  - SHA-256: `d2928b51b031dc6db43497bbd3d4e12d11a8b1d05ecbb28ce741ab169760e77a`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/state_machine.py`
  - SHA-256: `44d14308f5251a75c838372e1816bfea7e48a5c270afdde82bf375dadbbfe215`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/retry_policy.py`
  - SHA-256: `6b16f6d73c78415500901c9ba56af69f043b2e88f0bd39b9814b3b5ef665b7b4`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_worker.py`
  - SHA-256: `de22472a1ac73c5f3b228c4833b0e3c283eeb9d8c0deb13b5b7ab408c04c42b2`
