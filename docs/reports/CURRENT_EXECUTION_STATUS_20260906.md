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

# 当前执行摘要 — 阶段十一门禁与 MySQL 业务修复

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

> 本次以工作区证据批次 **2026-09-07** 更新。当前主线为审批后持久化续跑；阶段八486项是既有定向结果，边界回归已完成26项，正式后端门禁仍待完成。整体 **active / NO-GO**。探索性全量已在45%主动结束，观察到8失败；**正式冻结全量待执行完成**，不再笼统写“全面后端尚未跑”。

## 当前门禁与证据边界

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

## 已实现与尚待验收

- 已存在冻结计划读取器、终态intent事务服务、专用continuation消费者和CLI注册；写候选后按冻结DAG续跑read/suggest，不重新调用Planner，不自动接受候选。
- `execution_job_id`保留initial/replan来源，`continuation_job_id`记录续跑，step的`approval_source_job_id`用于绑定具体来源；顺序write→read→write已有回归，多并行审批仍待矩阵审查。
- pause/cancel门禁、source ACK/handoff证明、坏意图隔离与read step/fact重领已有实现或用例；畸形输入、跨任务活性、晚到提交和dead-letter完整收敛不提前标为通过。
- 本次读取期间continuation源码发生并行漂移；486项与五类反向均按各自运行快照归档，不向后续代码外推。

## 下一批执行计划

1. **边界回归已通过，进入冻结复核**：26项边界及213项相关组合日志已存在；复核`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundary-freeze.json`五文件指纹与冻结定向结果。畸形intent隔离、精确handoff/CAS、dead-letter、Run lease接管、晚到写终态、source绑定和并行审批已有新增回归，不重复当作未实现事项。
2. **复核冻结覆盖与有效反向**：保留26项边界结果，针对当前冻结源码复跑受影响反向并核对相关组合；独立进程恢复、真实数据库并发及部署结果仍单列，不由fixture回归外推。
3. **冻结后跑正式后端全量**：使用 `D:/小说写作/xuanqiong-wenshu/logs/run_backend_stage8_frozen_gate.py`，从头执行原始全量 `-m pytest -q`，不删测试、不跳测试。脚本在backend目录调用原虚拟环境python，以独占创建方式输出带时间戳的before/result JSON和日志；比较代码/配置及既有数据文件指纹。门禁须exit0、代码无漂移、既有资产无变化；session54497的探索性结果不替代这次冻结验收。
4. **归档与独立门禁**：保留旧失败、五类反向及探索日志；冻结结果出现后更新三个当前入口。Docker/MySQL实机与七项文学质量缺口分开推进，整体维持 **active / NO-GO**。

## 当前入口

- 实现、测试依据及五类反向：`D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_STAGE8_CONTINUATION_IMPLEMENTATION.md`。
- 阶段八计划：`D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_WORKER_CONTINUATION_PLAN_20260907.md`。
- 根入口：`D:/小说写作/xuanqiong-wenshu/TASK_HANDOFF_NOVEL_QUALITY.md`顶部已由主代理纠正历史“唯一下一任务”；本次只读核验，未编辑根文档。
- 此次只更新用户指定的三个Markdown文档，未运行测试、数据库操作或新task/thread。

---

# 以下为历史阶段记录

# 玄穹文枢：当前接续状态与执行计划

> **当前批次：阶段二。** 阶段一冻结后端全量已2017/2017通过；之后已开始质量完成保护器、reasoning请求隔离和结构残留评分修复，因此阶段一通过记录不是对新改动的全量背书。

> 更新日期：2026-09-06。此文件是本轮滚动更新的当前门禁表，不以旧附录的“最新”表述为准。
> 工作区：`D:\小说写作\xuanqiong-wenshu`；分支：`codex/bohrium-integration-20260831`；HEAD：`dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb`。
> 当前改动未提交。历史数据库、上传、日志和既有未提交成果保留。发布判定：**NO-GO；任务 active**。

## 1. 接续关系及证据纠偏

- 历史任务：**全面优化重构玄穹文枢**，ID `01a02410-94af-7002-9585-3532293aa587`。
- 工作在当前任务 `01a06d1c-19e0-75e0-a30e-9c3d0bae9867` 接续；使用子智能体，未创建新任务。
- 旧附录曾将 CLI / ASGI / AdminView 测试等待扩大至 180 秒并视为通过；这些结果不构成本轮原门槛验收。本轮已恢复 **CLI 30秒、ASGI 60秒、AdminView 30000ms**。
- 单次重试成功仅证明该次通过；不证明资源争用是唯一根因，也不证明所有 cancel 503 均来自 catalog。
- 历史后端 `1765 passed / 4 failed`、历史 acceptance `6/6`、旧 OpenAPI smoke 数字均非当前迁移030工作树的最终证据。
- 最近正式栈 acceptance 启动失败，日志目录 `D:\小说写作\xuanqiong-wenshu\logs\run-20260906-111829`。不得写成新一轮6/6通过。

## 2. 当前门禁

| 门禁 | 实测结果 | 范围与剩余项 |
|---|---|---|
| 前端原阈值全量 | **81文件 / 545测试通过，116.92s** | 当前审批修复与新增回归已覆盖 |
| 前端type-check / build | **通过；build 17.46s** | 当前新批次，未放宽阈值 |
| 审批空值定向 | 2通过 | Vite内存变异去除归一化：1失败/1通过，exit1，缺陷被检测 |
| Artifact lifecycle / registry / catalog | 17通过 / 10.60s | 真实accept路由函数、accepted内容/hash、历史snapshot冲突 |
| smoke配置与错误边界 | 17通过 / 0.79s | 现有配置不覆盖、并发配置保留、accept非200导致失败、finalizers |
| 独立TCP Artifact链 | **r5：1通过 / 19.21s** | 生成/接受/7个GET、表计数恢复、FK检查、文件sentinel全部通过 |
| 项目删除隔离 | **41项定向通过；含TCP组合42项通过** | FK ON/OFF、Agent图、11类写入域、identity map同步、非目标项目保留；含30条反向验证 |
| research迁移030 | **12通过 / 117.20s** | fresh、029缺表、已有数据、repeat、降升往返；临时副本反向验证检测到3个预期失败 |
| head030集成定向 | **34通过 / 68.04s** | Alembic、历史029专项、durable replay、Artifact生命周期、smoke错误边界 |
| 部署/回滚 | **冻结版95项通过（纳入202项集成）** | 原失败项保留并通过复测；SQLite/内部和外部MySQL均保留；真实Docker另验 |
| 启动进程归属 | **冻结版42项通过（纳入202项集成）** | 父子创建时间/父生命周期/句柄验证；子先父清理，证据缺失保留 |
| 消息分页fixture清理 | **主代理冻结版23项通过（纳入202项集成）** | 恢复旧实现检出19项失败；错误删除ID检出5项失败；只清理本次ID |
| SQLite备份验收 | 新增22项+research12项：34通过/257.07s | 真实脚本exit0；backup API覆盖WAL，FK/内容/计数强断言；13个变异被检出 |
| 后端原阈值全量（集成中快照） | **1989通过 / 9失败 / 1300.38s** | 1项SQLite回滚fixture失败，8项启动合同失败；保留完整失败，不记通过。冻结版仍待复核 |
| 原默认端口栈acceptance | 历史最近启动失败 | 不将隔离栈结果冒充历史库/默认端口部署结果 |
| 当前隔离生产配置acceptance | **6/6通过，脚本与包装器exit0** | 当前030、真实TCP/JWT、10表完整行内容保持一致、FK通过，临时进程已回收 |
| 阶段一冻结版后端全量 | **2017通过 / 1193.34s / exit0** | 结束后核验34文件指纹一致，保存frozen-2017-passed-fingerprint-20260906.json |
| 阶段二质量完成保护器 | **55项回归通过；旧实现检出32项失败** | 修复manifest来源、一致标签、完整裁决验证及原merge遮挡；真实7项硬缺口仍保留 |
| 阶段二reasoning请求隔离 | **26项通过；8/8变异检出** | 代次、Run/page/item身份、旧success/catch/finally、cursor和双击锁；前端全量随后570项通过 |
| 阶段二结构残留评分 | **54项通过；4项审计快照变异失败** | 任务JSON/蓝图链接边界、artifact penalty 480、fallback、清洗证据和快照字段；后续补掉1个重复staticmethod回归 |
| 阶段二全量（修复前快照） | **2104通过 / 1失败 / 1120.25s** | 唯一失败为评分新增方法的重复staticmethod；已修复，需在UI005变更后重新冻结全量 |
| Docker / MySQL runtime | 尚无新通过证据 | 需实测引擎和服务；静态Compose配置非替代品 |

### 证据文件

以下均位于 `D:\小说写作\xuanqiong-wenshu\logs`：

- `frontend-full-original-threshold-20260906.log`
- `frontend-typecheck-original-threshold-20260906.log`
- `frontend-build-original-threshold-20260906.log`
- `frontend-approval-normalization-20260906.log`
- `reverse-frontend-approval-20260906.log`
- `reverse-accept-actor-contract-20260906.log`
- `tcp-artifact-smoke-20260906-r4.log`（修复前失败）
- `tcp-artifact-smoke-20260906-r5.log`（修复后通过）
- `frontend-full-current-20260906.log`
- `frontend-typecheck-current-20260906.log`
- `frontend-build-current-20260906.log`
- `integrated-head030-targeted-20260906.log`

## 3. 已定位问题 → 修复 → 验证路径

1. **accept路由契约遗漏actor_user_id** → registry/schema及catalog同步，generation升3 → lifecycle真实路由调用，删除字段的进程内变异导致失败。
2. **显式生成Run未预留accept能力** → generate/rewrite resolver额外选择accept，原requested_tools及执行步骤保持不变 → 只读Run不扩权，旧immutable snapshot在创建审批前409。
3. **已接受版本内容无文件storage_key** → chapter-version协议按项目/章节解析数据库版本并核对hash → content/diff读取及篡改拒绝。
4. **冒烟覆盖配置后用脱敏值恢复** → Artifact模式只允许独立账号无配置状态，创建自身fixture并核对归属清理 → 现有配置、并发编辑和异常finalizer回归。
5. **研究表依赖模型导入顺序** → models显式注册，新增030兼容修复迁移 → 独立Alembic进程验证，保留既有研究数据。
6. **删除项目留下跨表引用与孤儿** → 显式按依赖顺序清理，仅限目标项目 → FK ON/OFF与TCP全链外键检查。
7. **部署停机/备份/迁移/回滚顺序不可靠** → 修复流程并加入可执行故障注入 → 真实容器矩阵单列，未完成前保持NO-GO。

## 4. 持续执行计划

### P0：当前集成闭环（进行中）

1. 已收取删除、迁移、部署、启动、fixture清理子智能体成果并关闭已完成子智能体；已进入主代理串行门禁队列，避免内存压力下并行启动新测试。
2. 独立TCP Artifact r5已通过，表计数/FK/sentinel强断言保持；resolver归一化新增测试后仍需在冻结代码上复核。
3. 对照030逐条更新head断言，历史029专项用例保持原目标。
4. 串行执行后端全量、前端全量、type-check和build；任何失败均先定位再修复，并追加回归。
5. 验证迁移/备份/恢复脚本：临时SQLite中保留研究和运行数据sentinel、降升往返、重复迁移。

### P1：运行与发布门禁

1. 核验现有进程和端口，不按等待过期盲目重启；记录实际配置问题而不打印凭据。
2. 执行当前工作树的正式acceptance；明确使用的数据库、服务PID、构建与日志。
3. 检查Docker Engine与MySQL可用性；可用后跑fresh/upgrade/backup/restore/worker容器矩阵，不直接操作历史数据库。
4. 审核残留fixture归属；只处理本轮精确ID和路径，不扫描删除历史资料。

### P2：业务质量与结构优化

1. 在P0/P1稳定基线上复核小说质量主线：评分集中化、生成/重写/接受、质量阻断、上下文溯源、任务取消和恢复。
2. 优先修复可重现问题，再拆分大服务职责；每次小范围变更均配行为回归和反向验证，避免大规模无证据重写。
3. 梳理provider/研究流程、模型选择和错误呈现；明确真实外部调用与本地fixture证据的边界。
4. 收拢前端异步加载、分页、Run切换、审批、Artifact检查器的状态一致性；以可观察用户行为验证。
5. 更新本表与权威入口，保持一份当前结论，旧附录只保留历史。完成资格以当前全部要求的证据闭环为准。

## 5. 执行命令

PowerShell工具调用使用 `login:false`；此项是本轮减少启动开销的操作观察，不是业务修复或唯一根因结论。

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\backend'
.\.venv\Scripts\python.exe -m pytest -q
Set-Location 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run test:run
npm run type-check
npm run build-only
```

子智能体沿用当前执行环境权限；不虚构提升权限。遇到卡点由主代理检查进程、输出、依赖并重分配工作，不另开用户任务。

## 6. 本轮新增执行风险与后续修复

- `start.ps1` 原流程会按端口和仓库路径终止Python/Node进程，可能影响其他测试；已交由独立子智能体改为复用健康服务、拒绝不明端口占用、仅清理本次拥有进程，并配PowerShell可执行合同。主代理未运行旧清理逻辑。
- 消息分页acceptance失败兜底按固定title删除最新session，存在误删另一fixture风险；已交由独立子智能体收口到创建后取得的精确session ID。
- SQLite备份脚本的final counts原本只打印未断言，且session sentinel缺用户外键；已交由迁移子智能体修复并纳入研究数据往返。
- 部署脚本评审拦下了仅支持内部MySQL导致默认SQLite功能回退的中间版本；要求补齐SQLite和外部MySQL分支，不以删减能力制造通过。
- 2026-09-06 12:07尝试隐藏启动Docker Desktop后，Engine仍未就绪；本地日志记录Inference manager的dockerInference socket初始化失败，12:08 backend退出。未重置Docker、改全局设置或触碰历史卷；真实Docker/MySQL矩阵仍待环境恢复。

### 集成冻结与下一条命令

- 源码指纹：`D:\小说写作\xuanqiong-wenshu\logs\current-code-fingerprint-20260906.json`。该指纹记录子智能体交付及主代理归一化修复后的34个代码文件；全量启动早于末尾新增用例，勿把旧收集集合作为最后完整证据。
- 主代理追加resolver归一化修复：预留accept的判断跟随resolver使用`str(value).strip()`；空格包围的生成/重写名保留正确accept能力，嵌套JSON值不触发集合hash异常，原context不改动。新增4条正向回归已通过；独立进程撤掉归一化后4条全部失败，mutation exit1。
- 全量终态后顺序：新增/改动定向集成 → resolver反向验证 → 冻结版后端全量 → `logs/isolated-acceptance-runner-20260906.py`驱动真实`verify.ps1 -Suite acceptance`。后者使用临时DB、独立端口、10表原始行快照及FK检查，只终止其拥有的子进程，不调用旧进程扫除逻辑。
- 另两份分页acceptance在`try/finally`外调用seed的风险已登记；先检查seed是否仅在单事务末尾commit，再决定是否修复，避免无证据扩写。

### 2026-09-06 12:36 批次切换

后端集成中快照全量自然结束：`9 failed, 1989 passed in 1300.38s`。其中SQLite回滚记录`PermissionError [WinError 5]`发生在临时数据库原子替换；启动合同旧stub将新增的父PID限定查询记录为`forbidden_scan`。本批存在测试收集后源码更新，故失败证据保留，并以冻结后的同等/更强断言复核，不删除失败项或扩大超时。

当前排队顺序（每步等待前一步结束，无并行pytest）：

1. **202项集成回归**：部署95、启动42、消息fixture23、备份22、研究迁移12、Artifact生命周期7、TCP1。日志`D:\小说写作\xuanqiong-wenshu\logs\post-full-integrated-regression-20260906.log`。
2. **resolver反向验证**：只在独立进程中撤掉归一化，预期测试exit1；源文件不被改坏。日志`D:\小说写作\xuanqiong-wenshu\logs\reverse-resolver-normalization-20260906.log`。
3. 上述证据成功后，独立临时栈执行原`verify.ps1 -Suite acceptance`，核对10表完整行快照和FK。日志`D:\小说写作\xuanqiong-wenshu\logs\isolated-verify-acceptance-20260906.log`。
4. 处理真实失败后再执行最终冻结版后端全量。前端代码自545项/type/build通过后保持不变。

冻结启动脚本SHA256：`7A71DAD7467C1C60CDC46229A7FDD908BC0FE20E6F12528E717B6E03FCE0F3F1`；启动合同SHA256：`439C23F810318656B7BA783E501435C90AF685A9A331275D044714BEC56E1474`。

### 冻结集成终态

`post-full-integrated-regression-20260906.log`：**202 passed in 406.79s**，工具进程exit0。九个前批失败项及新后代场景全部在冻结文件上执行，不沿用旧结果。

`reverse-resolver-normalization-20260906.log`：**4 failed / 3 deselected / 6.88s，MUTATION_EXIT 1**；故意撤掉归一化后，空格工具名缺accept预留、嵌套字典触发TypeError都被测试检出。该变异只驻留独立进程，工作区源码保持正常。

真实隔离`verify.ps1 acceptance`已6/6通过；阶段一冻结版后端全量取得2017项通过；阶段二修复前全量为2104通过/1失败，重复staticmethod已修复，后续继续冻结复验。

### 当前最终验收与持续工作入口

- `D:\小说写作\xuanqiong-wenshu\logs\isolated-verify-acceptance-20260906.log`：原`verify.ps1 -Suite acceptance` **6/6通过**；外层包装器 **exit0**。消息180条/3页、成员125条/3页、Run125条/3页；两个worker只处理临时库。
- 包装器终态：`ISOLATED_VERIFY_ACCEPTANCE_PASSED`，revision=`030_research_schema_repair`，10表原始行快照保持一致，`PRAGMA foreign_key_check=[]`。本轮自建backend/frontend进程已回收，临时库已清理。
- 备份验收使用SQLite backup API；物理文件SHA不同不代表内容丢失，**完整逻辑dump SHA及所有sentinel相同**才是本验收的数据合同。029往返保留完整数据；028往返由于原membership迁移删除再重建，核验owner grant语义并保留研究完整行。
- **阶段一冻结版后端全量已完成2017项通过**：`D:\小说写作\xuanqiong-wenshu\logs\backend-full-frozen-20260906.log`。该批期间保持源码冻结且结束后核验指纹一致；当前已进入阶段二，不将本结果外推到后续变更。
- 源码指纹与机器可读门禁：`D:\小说写作\xuanqiong-wenshu\logs\current-code-fingerprint-20260906.json`、`D:\小说写作\xuanqiong-wenshu\logs\current-release-gates-20260906.json`。
- 发布判定仍是**active / NO-GO**：阶段二变更尚待新的综合验证；Docker启动失败及MySQL真实运行矩阵、七项真实质量硬缺口尚未闭合。P2质量主线和结构优化继续按第4节推进，不用本轮本地Provider fixture代替真实模型内容质量评估。

## 原质量目标专项复核（2026-09-06）

已新增`D:\小说写作\xuanqiong-wenshu\docs\reports\QUALITY_REQUIREMENT_AUDIT_20260906.md`。纯元数据重算仍有7项硬缺口；实际读取人工标签为通用0/19、专项A/B各0/6。既有controlled A/B重算+144.4分不等于文学质量增益。

临时样本复现完成资格保护器两项误放行：manifest六条样本却接受不相关单条审阅；合并结果反转两位审阅人的一致false仍被接受。真实标签未改动；冻结全量自然结束后优先补失败回归并修复QG-01/QG-02。

同时进行UI-005、UI-006和main/当前分支评分方法级只读审查，子智能体仅写独立报告；不修改冻结源码、不启动额外pytest或Provider调用。

## 阶段二精确接续队列

1. **已完成主代理QG-01/02/03局部修复**：`backend/scripts/audit_novel_quality_completion.py`绑定manifest全量样本/身份；一致标签原样保留；优先选择并回放验证裁决文件，核对原merge、裁决CSV、原值、结论、说明及hash，原始证据不用删除。对应`test_novel_quality_completion.py`保留旧用例并新增失败回归。
2. **质量保护器证据**：修复前30项新增断言失败；当前四个相关测试文件55项通过（1.64s）；用保存的旧保护器运行最新用例，32失败/8通过，mutation exit1。真实数据复算仍completion_eligible=false、7项blocker、112条空标签诊断。修复工具不等于人工标签/文学增益已完成。
3. **Halley子智能体**：修复`frontend/src/features/agent/composables/useAgentReasoningHistory.ts`及spec的代次/Run隔离，单独交付正反向验证；不混入虚拟化/抽屉。
4. **Euler子智能体**：补当前pipeline结构残留检测/计分缺口，写域为`pipeline_orchestrator.py`相关方法和新`test_scoring_artifact_parity.py`；保留现有三态/防刷/压力/人名动作/清洗重算能力。
5. 收取两位子智能体稳定成果后，先审diff与反向测试，再串行执行后端相关集成、前端全量/type/build，最后形成新的冻结全量证据；不在全量收集后改源码。
6. **UI005下一批已派发给当前任务子智能体**：在主代理最终全量期间只读/准备，待明确GO后修改审批入口与专属回归；目标是完整校验Run的generation/provider/schema/context binding，并保持legacy兼容及actor/owner分离。先做实际路由/worker反例验证，不只按局部probe下结论。
7. **UI006尚未完成项**：reasoning有界/虚拟化渲染、窄屏双抽屉互斥与真实点击/焦点测试，继续保持原需求，不以仅修复请求竞态替代。

审计入口：`D:\小说写作\xuanqiong-wenshu\docs\reports\QUALITY_REQUIREMENT_AUDIT_20260906.md`、`UI005_REQUIREMENT_AUDIT_20260906.md`、`UI006_REQUIREMENT_AUDIT_20260906.md`、`SCORING_PARITY_AUDIT_20260906.md`（后三份也位于同一reports目录）。

新日志：`D:\小说写作\xuanqiong-wenshu\logs\quality-guard-red-20260906.log`、`quality-guard-green-r3-20260906.log`、`reverse-quality-guard-20260906.log`、`novel-quality-completion-after-qg-fix-20260906.json`。阶段一源码指纹独立保留，不覆盖作新代码的验证凭据。


### 阶段二定向收口（2026-09-06）

- 后端质量保护器/标注合同/结构残留评分：`109 passed in 4.20s`；后续评分快照字段修复后追加兼容性定向，总计`70 passed in 4.68s`。
- 前端 reasoning C2：`26 passed`，源码正常复跑通过；反向变异8/8检出。前端阶段二全量：`81 files / 570 passed`；UI006后新全量：`81 files / 573 passed`；type-check与build通过，UI006后build `28.39s`。
- 已保存阶段二代码指纹：`D:\小说写作\xuanqiong-wenshu\logs\stage2-code-fingerprint-20260906.json`；最终后端全量已自然结束并记录`2104 passed / 1 failed in 1120.25s`，日志`D:\小说写作\xuanqiong-wenshu\logs\backend-full-stage2-final-20260906.log`；重复staticmethod已修复，UI005变更后需重新冻结。
- 质量完成资格重算仍是false，七项真实质量硬缺口与人工标签空白保持；本轮只修复了“证据验证器误放行/误阻断”，没有伪造人工真值。


### UI005 执行契约已收口

Mencius 已完成 UI005 审批执行契约。修改文件：`backend\app\api\routers\agent.py`、`backend\app\agent\execution.py`、`backend\app\services\agent_runtime.py`、`backend\app\agent\test_approval_run_contract.py`。关系化 Run 校验 catalog row、release manifest/digest/generation/schema、resolver snapshot、Provider relation、handler identity、schema、context binding、approval/step/run/user/project；legacy snapshot=None 保持兼容。

证据：`ui005-approval-contract-current-final-20260906.log` 及 `ui005-approval-route-fixed-r5-20260906.log` 最新源码下 `31 passed`；完整契约函数内存变异 `20 failed / 4 passed`，`MUTATION_EXIT 1`；`git diff --check` 通过。真实 route fixture 已修正为使用真实无Provider的 `chapter.generate` Catalog，不伪造不一致 Provider。


### 阶段二全量终态纠偏

- 阶段二全量（质量保护器、评分残留、reasoning C2及相关回归均已纳入）自然结束：`2104 passed / 1 failed in 1120.25s`。失败定位为`test_pipeline_has_no_duplicate_staticmethod_decorators`，当前已删除重复装饰器。
- 删除重复装饰器后的评分+兼容性定向：`70 passed in 4.68s`。这不是全量结果；Mencius接下来会修改UI005审批入口，完成后必须重新跑最终后端全量。
- 当前活动子智能体只剩Mencius；其余子智能体已收口/关闭，避免空转和额外资源占用。


### UI006 C3 窄屏面板收口（2026-09-06）

Jason 子智能体因余额错误退出，未留下代码；主代理接管并修改：
- `frontend/src/features/agent/composables/useAgentPanelState.ts`
- `frontend/src/features/agent/AgentWorkspaceShell.vue`
- 对应两个 spec。

当前行为：≤650px 只保留单一活动抽屉；打开左侧关闭右侧，打开右侧关闭左侧；持久化双开恢复时确定性保留左侧；桌面仍允许双开；窗口缩放触发归一化；Escape 关闭当前活动抽屉。定向回归 `14 passed`。真实浏览器最窄视口点击/焦点/E2E仍待执行，不把 jsdom 通过外推为移动端全闭环。

阶段三：UI006后前端 `573 passed`、type-check、build 已通过；UI005 后端定向复跑通过；后端冻结全量首次为`2130 passed / 1 failed`，唯一失败为worker CLI 30秒子进程超时；单测独立重跑`1 passed in 9.14s`；最终复跑已取得`2131/2131 passed`。随后继续真实浏览器移动端验证和七项质量硬缺口。


### 阶段三 UI005/UI006 当前证据（2026-09-06）

- UI005 当前路由+写执行定向：`31 passed`，日志 `D:\小说写作\xuanqiong-wenshu\logs\ui005-approval-contract-current-final-20260906.log`；真实路由路径进入 registry，正常路径无额外 execution fact，漂移路径在 handler 前失败。
- UI005 反向：移除 validator 的独立进程测试 `20 failed / 4 passed`，`MUTATION_EXIT 1`；日志 `reverse-ui005-contract-current-20260906.log`。
- UI005 生产上下文修复：新 Run 现在持久化 `relational_capability_snapshot_digest`；关系化 catalog/provider 行在 route 入口重新加载并比对。
- UI006 C3：窄屏面板互斥/持久化归一化/Escape，定向 `14 passed`；Jason 子智能体因余额错误退出，主代理直接接管写入。
- UI006后前端全量：`81 files / 573 passed`；type-check/build通过，日志分别为 `frontend-full-after-ui005-ui006-20260906.log`、`frontend-typecheck-after-ui005-ui006-20260906.log`、`frontend-build-after-ui005-ui006-20260906.log`。
- UI006真实浏览器几何、320/375/390px点击命中和焦点闭环仍未完成；当前14项是jsdom/组件证据，不冒充完整移动端验收。


### 阶段三后端全量首次终态与最终复跑

- `backend-full-stage3-final-after-digest-20260906.log`：`2130 passed / 1 failed in 1623.54s`。
- 唯一失败：`app/agent/test_worker_cli.py::test_worker_cli_once_mode_exits_cleanly`，子进程30秒超时；失败未形成业务断言。
- 同一源码、单独串行复测：`worker-cli-once-stage3-recheck-20260906.log`，该测试 `1 passed in 9.14s`。这证明失败具有资源/进程窗口特征，但最终发布证据仍需再次全量。
- 当前没有修改 worker timeout，也没有用扩大阈值替代定位；下一步直接重跑同一原门槛全量，取得最终稳定结果。


- 最终复跑日志：`D:\小说写作\xuanqiong-wenshu\logs\backend-full-stage3-final-rerun-20260906.log`，结果 **2131 passed in 1188.97s，exit0**。
- 最终代码指纹：`D:\小说写作\xuanqiong-wenshu\logs\final-stage3-code-fingerprint-20260906.json`。
- 当前阶段三工程门禁结论：后端最终全量、前端573全量、type-check、build均有当前工作树证据；UI006真实浏览器移动端和reasoning虚拟化仍未闭环；七项真实质量硬缺口、Docker/MySQL实机矩阵仍未闭合。


### 阶段四 UI006 C1 reasoning 有界渲染（2026-09-07）

主代理接管 Jason 子智能体余额错误后的 UI006 C1 实施，修改：`frontend/src/features/agent/AgentReasoningCard.vue` 与对应 spec。

- 维护完整 `displayText`，复制动作始终复制全量历史，不读取可见窗口。
- 使用测量高度/估算高度、前后 spacer、overscan 和 scrollTop 计算实际可见 chunk；2000段历史 DOM 保持有界。
- 保留分页加载、sequence 去重、C2 generation/Run/page/item 校验和流式尾部跟随。
- 折叠仍保留现有用户行为；组件只在展开时显示内容，缓存数据不丢失。
- 定向 C1/C2/C3：`44 passed`。
- C1 反向：把 `visibleItems` 恢复为全量 `props.chunks` 后窗口测试失败；恢复正常实现后`2 passed`。
- 当前没有真实浏览器的布局/节点/锚点/内存性能数字；不要把 jsdom 通过外推为完整性能验收。

阶段四下一步：前端全量/type/build；再执行浏览器窄屏点击、焦点、Escape 和 reasoning 窗口验收；随后重新生成最终代码指纹。
