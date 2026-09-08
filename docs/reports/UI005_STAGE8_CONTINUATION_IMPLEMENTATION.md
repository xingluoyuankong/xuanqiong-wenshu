# UI005 阶段八：审批后持久化 Continuation 实现报告

> **日期口径**：部分证据文件名沿用既有 `20260907` 批次标签；它们是历史运行批次标识，不表示当前日期。具体运行时刻以各证据文件的 `recorded_at` / `finished_at` 及其时区偏移为准。

<!-- STAGE11_LIVE_STATUS_BEGIN -->
## 当前执行状态：阶段十一维护扫描活性、MySQL与SSE/E2E

> 本块覆盖下方旧“当前/最新”措辞；历史结果和失败复现均保留。当前任务继续在本工作区，目标 **active**，整体发布 **NO-GO**。

| 范围 | 当前实测 | 证据 |
|---|---|---|
| 阶段十后端全量基线 | **2720 passed / 1209.75s / exit0**；621代码/配置与2734既有数据无漂移 | `logs/backend-stage10-frozen-20260907T084230072041+0800.result.json`；阶段十一前基线 |
| 阶段十一扫描活性修复 | **103 passed / 36.47s**；暂停/未证明前缀不再永久遮挡健康 continuation | `logs/stage11-scan-cursor-green1.log`、`docs/reports/UI005_STAGE11_SCAN_FAIRNESS.md` |
| MySQL/跨实例 | **NO-GO**；Docker Server=null、3306不可达、客户端/凭据缺失 | `docs/reports/MYSQL_CROSS_INSTANCE_RECOVERY_AUDIT_20260907.md`、`logs/stage10-mysql-docker-readonly-probe.json` |
| SSE/E2E | backend 40 passed、frontend相关52 passed；fresh浏览器长运行因5174已有node进程未执行 | `docs/reports/UI005_SSE_E2E_AUDIT_20260907.md`、`logs/sse-e2e-audit-20260907.json` |
| 阶段十一最终后端全量 | **待执行**；扫描游标改动触及 backend worker/recovery 核心 | 新冻结 runner 完成后再记有效结果 |

### 下一步

1. 先执行阶段十一定向与内存反向，确认轮转游标、边界上限和旧恢复证据不回归。
2. 以当前代码重新执行原始后端全量；不使用2720作为新源码背书。
3. Docker/MySQL条件可用后完成迁移、时区、InnoDB锁等待、双实例CAS与stale worker矩阵。
4. 使用新的独立端口完成fresh浏览器SSE/E2E；不终止5174既有进程。
5. 最后回到文学质量七项硬缺口。

<!-- STAGE11_LIVE_STATUS_END -->


> **交付时最新状态**：边界回归已从先前20项推进到 **26 passed / 135.59s**，见`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-final.log`；相关组合另有 **213 passed / 217.73s**，见`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-green3.log`。486项保留为边界修复前的历史定向，不与26或213累加。边界5文件指纹已记录在`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundary-freeze.json`，本次核验5/5与磁盘一致。正式后端冻结全量仍待完成，不再写“等待边界20项修复”。
> 探索性session54497已在45%主动结束，observed_failures=8、valid_gate=false，依据`D:/小说写作/xuanqiong-wenshu/logs/stage8-exploratory-full-status.json`；最终从头执行原始全量，不删测试、不跳测试。根任务入口保持主代理现状，本次未编辑。

> 证据批次：**2026-09-07（项目本地日志）**。文档范围：基于当前代码、测试定义、既有日志及主代理追加反馈更新，不执行测试或修改源码。整体 **active / NO-GO**。
> **486 passed / 232.44s** 是本轮已落地核心的既有定向结果；边界修复已形成5文件指纹，须以冻结门禁确认最终一致性。探索性全量session54497已在约45%主动结束，新增红测8失败且执行中源码发生漂移；状态见 `D:/小说写作/xuanqiong-wenshu/logs/stage8-exploratory-full-status.json`，`valid_gate=false`，属非冻结结果。正式冻结runner已准备，边界回归完成后从头执行原始全量，不删测试、不跳测试。

## 1. 实现概况与证据限制

当前工作区已有审批终态意图生产者、冻结Plan加载器、专用continuation消费者及CLI注册。现代关系计划的写候选成功后，将step、execution fact、approval、intent与Run状态组合提交，替换“只有等待而没有持久化续跑”的缺口；新worker对象及新DB session可读取冻结DAG继续执行read/suggest，不重新规划。write→read→write保留第二次独立审批，候选没有自动接受。

已有测试使用临时数据库、实际AgentWorker/审批/执行事实与统计工具；Planner及writer流为受控fixture替身。因此这证明应用内持久化链路及重开session恢复，不等于真实Provider调用、独立操作系统进程崩溃恢复或生产数据库并发验收。CLI注册是静态核验，不据此写“真实CLI续跑验收通过”。

本次读取期间continuation.py、continuation_worker.py及后续边界文件发生并行变更；下文使用函数名而非易漂移行号定位。486日志没有附完整启动命令、节点清单或独立退出码，本报告仅引用其pytest原文，不反推486项的精确文件组成。新增边界26项及213项组合已通过；正式全量和最终指纹一致性仍须单独验收。

## 2. Evidence → Finding → Path

| 证据入口 | 当前可确认事实 | 验收/后续路径 |
|---|---|---|
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_plan.py`：FrozenContinuationPlan、FrozenContinuationStep、load_continuation_plan | 验证计划摘要、身份、上下文父关系、source、参数与依赖；不可变步骤及可脱离ORM的payload | 精确计划契约回归；不重新调用Planner |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation.py`：load、_persist_intent、complete_write、record_rejected、fail_write | 严格context/snapshot校验接线；写成功、拒绝、失败分别持久化终态意图 | rollback及终态用例；旧direct/legacy分流 |
| 同文件：activate_ready、verify_write_proof | source ACK/handoff、Run门禁、写step/fact/artifact证明、坏意图隔离分支 | 单项证明已有；畸形输入、健康任务活性和跨lease竞态仍待完整矩阵 |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_worker.py`：handle_agent_continuation_job | 按冻结计划推进read/suggest、创建下一次写审批；step/fact恢复与条件ACK | 重领、失败、重试、双worker和多写链回归 |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/worker.py`：poll_once、_heartbeat；`D:/小说写作/xuanqiong-wenshu/backend/scripts/agent_worker.py`：_run | 调用激活器、处理专用ACK/defer、延长续跑lease，注册agent_continuation | 静态接线已核验；独立进程/真实部署另验 |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/write_executor.py`；`D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_runtime.py`；`D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_execution_service.py` | producer接入，支持commit=False及审批拒绝/读写执行事实投影 | 原子提交指数据库终态，不涵盖之前的Provider/文件写入 |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_plan.py`；`D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_worker.py` | 计划契约和临时DB worker回归定义可读 | 映射第4节用例；不向新增边界代码外推旧结果 |
| `D:/小说写作/xuanqiong-wenshu/logs/stage8-final-targeted.log` | 486 passed in 232.44s (0:03:52) | 既有阶段八定向结果，非当前正式冻结全量 |

## 3. 设计决策

| 决策 | 当前采用方案与边界 |
|---|---|
| 意图载体与幂等 | 复用AgentJob，kind=agent_continuation；key为continuation:v1:PlanRevision.id:Approval.id:outcome。同key要校验kind及payload，冲突不覆盖 |
| 终态含义 | approved不是执行证明；executed意图初始blocked，rejected/execution_failed产生取消状态的终态意图并处理下游，不触发成功read |
| 冻结关系 | PlanRevision/ContextSnapshot/CapabilitySnapshot/Approval/Step/source Job相互校验；服务层另调用严格context reader及approval snapshot validator，职责不混写成单个helper包办 |
| payload最小化 | 只传schema、归属/定位、摘要、审批结果及return_phase；不复制正文、Provider凭据或任意未验证参数 |
| source绑定 | execution_job_id保留initial/replan；最新续跑写continuation_job_id；step的approval_source_job_id绑定后续写来源，避免用最新Job猜测并行审批 |
| 事务 | step/fact/approval/intent/Run数据库终态同一提交；Provider、文件、质量工作此前已发生，未声称跨文件与数据库原子化 |
| 消费者 | 使用冻结global order、依赖和arguments，复用step/checkpoint；不重新Planner；真实registry继续检查执行合同 |
| ACK与恢复 | source已ACK，或过期source+精确approval_wait_handoff+完整写证明才恢复；Run活lease及用户pause/cancel优先；不是只凭超时重领 |
| 候选与多写链 | 不自动accept，不新增正文版本；write→read→write的第二次write独立审批；顺序链通过不代表并行汇合全部验收 |
| 兼容与重试 | 真实legacy/direct无关系PlanRevision保留candidate-only；read瞬时重试不重调writer，最终耗尽状态收敛仍须专项确认 |

## 4. 已有正常回归与剩余覆盖

用例均位于`D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_worker.py`；列出的是可核验测试定义及相关日志证据，不声称覆盖全部边界。

| 范围 | 可定位用例（test_前缀省略） | 证明边界 |
|---|---|---|
| 写终态/回滚 | real_writer_persists_intent_with_executed_approval；intent_failure_rolls_back_terminal_completion | 有intent及数据库终态rollback；未证明跨文件回滚 |
| 新worker读取 | fresh_worker_replays_original_plan_once_after_approved_write | 一次Planner/一次writer/真实统计；唯一候选、无新ChapterVersion；新对象/DB session，非独立进程重启 |
| pause/cancel | user_pause_blocks_continuation_until_explicit_resume；cancelled_run_never_activates_blocked_intent | 常规生命周期门禁；竞态排列另验 |
| 审批终态 | rejected_approval_atomically_stops_dependents_and_persists_outcome；failed_writer_records_terminal_intent_without_read | 拒绝/写失败停止下游 |
| source门禁 | source_ack_and_live_run_lease_gate_continuation；expired_source_ack_recovery_requires_durable_handoff | 活Run lease和有/无handoff；不等于完整source/Run并发矩阵 |
| 损坏材料 | modified_frozen_intent_is_rejected_before_read；invalid_intent_is_quarantined_without_crashing_worker_loop；corrupt_candidate_file_prevents_continuation | 单坏意图/文件证明；坏意图与健康任务同批活性另验 |
| 读失败及恢复 | continuation_read_failure_converges_job_step_and_run；transient_continuation_failure_retries_read_not_writer；expired_read_checkpoint_and_fact_reclaim_use_new_generation | 普通失败、瞬时重试、新generation重领；dead-letter与跨事务竞态另验 |
| 多写/双worker/ACK | write_read_write_chain_requires_second_approval_and_original_plan；two_workers_claim_one_continuation_without_duplicate_read；retry_after_read_commit_reuses_checkpoint_before_final_ack | 顺序多写、两个worker对象竞争、读提交后ACK故障重试；非所有进程崩溃窗口 |

修复过程中的失败证据继续保留，例如`D:/小说写作/xuanqiong-wenshu/logs/stage8-terminal-after.log`（2 failed / 7 passed）、`D:/小说写作/xuanqiong-wenshu/logs/stage8-recovery-final.log`（1 failed / 15 passed）；后续局部复测见`D:/小说写作/xuanqiong-wenshu/logs/stage8-read-reclaim-fixed.log`（2 passed / 14 deselected）、`D:/小说写作/xuanqiong-wenshu/logs/stage8-write-read-write.log`（1 passed / 16 deselected）、`D:/小说写作/xuanqiong-wenshu/logs/stage8-parallel-ack-retry.log`（2 passed / 17 deselected）。不把这些数字累加到486，也不抹掉失败历史。

## 5. 五类有效内存反向（旧三类保留，新增两类已核验）

原脚本：`D:/小说写作/xuanqiong-wenshu/logs/stage8-continuation-mutation-20260906.py`。追加脚本：`D:/小说写作/xuanqiong-wenshu/logs/stage8-continuation-additional-mutation.py`。两者都在进程内替换函数，finally恢复引用，并记录被检查源码的SHA-256。以下均为预期业务断言失败，不是测试导入或语法错误。

| 变异 | 实际结果 | 对应证据 |
|---|---|---|
| producer-no-intent：移除intent持久化 | **1个业务断言失败** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-producer-no-intent-mutation-20260906.log`；`D:/小说写作/xuanqiong-wenshu/logs/stage8-producer-no-intent-mutation-20260906.json` |
| reject-no-cancel：移除rejected终态取消 | **1个业务断言失败** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-reject-no-cancel-mutation-20260906.log`；`D:/小说写作/xuanqiong-wenshu/logs/stage8-reject-no-cancel-mutation-20260906.json` |
| consumer-no-read：移除consumer read执行 | **1个业务断言失败** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-consumer-no-read-mutation-20260906.log`；`D:/小说写作/xuanqiong-wenshu/logs/stage8-consumer-no-read-mutation-20260906.json` |
| source-ack-no-recovery：保留source为running，破坏过期ACK恢复 | **1个业务断言失败 + 1个正常对照通过** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-source-ack-no-recovery-mutation.log`；`D:/小说写作/xuanqiong-wenshu/logs/stage8-source-ack-no-recovery-mutation.json` |
| read-fact-no-failure：省略fail_read_execution，破坏fact失败投影 | **1个业务断言失败** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-read-fact-no-failure-mutation.log`；`D:/小说写作/xuanqiong-wenshu/logs/stage8-read-fact-no-failure-mutation.json` |

五份JSON均记录**source_unchanged=true**。追加source ACK失败节点为有handoff的[True]用例，无handoff分支为正常对照通过；read fact追加变异没有正常对照通过项，保持1个业务断言失败原数。

这一标记只证明每次变异运行前后的所列文件一致。文档核验初期追加两份报告的三项文件哈希与磁盘相符；随后边界agent继续修改continuation源码，故不把五份反向报告称为当前工作树的最终冻结证明。

计划加载器另有`D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/mutation_summary.json`：本次读到**14条mutations均killed=true**，各条collected=159、source_unchanged=true。这是该JSON自己的历史快照；交接摘要的“17/17”没有在此JSON中核实，本报告不照抄，也不与486或五类worker变异混计。

## 6. 当前门禁与新增外部证据

| 项目 | 核验结果 | 证据与适用范围 |
|---|---|---|
| 阶段八既有定向组合 | **486 passed / 232.44s** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-final-targeted.log`；日志只有进度及pytest汇总，没有独立exit code、完整命令或节点清单；不据此补写退出码，也不覆盖随后边界修复 |
| 五类worker反向 | **旧3类保留，新增2类检出** | 两份脚本及五份JSON详见阶段八报告；`source_unchanged=true`只证明各次变异前后被检查文件未变，不证明之后工作树冻结 |
| 前端阶段八指纹复核 | **267文件，changed_files=[]** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-frontend-baseline-recheck.json`；保留601项/type-check/build历史基线，不宣称本次重新执行前端测试 |
| Docker阶段八只读探针 | **exit1 / Server=null** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-docker-readonly-probe.json`；read_only=true、reset_or_volume_changes=false，未改卷；MySQL实机门禁仍未通过 |
| 后端上一全量基线 | **2358 passed / 1020.08s** | `D:/小说写作/xuanqiong-wenshu/logs/backend-full-stage7-20260907.log`；仅阶段七冻结批次，不是当前阶段八源码全量背书 |
| 阶段八探索性全量 | **session54497约45%主动结束；新增红测8失败；非冻结** | `D:/小说写作/xuanqiong-wenshu/logs/stage8-exploratory-full-status.json`：源码发生漂移，`valid_gate=false`；不作为正式全量结论 |
| 阶段八正式冻结门禁 | **边界26项通过后执行正式冻结全量** | `D:/小说写作/xuanqiong-wenshu/logs/run_backend_stage8_frozen_gate.py`已存在；本次仅阅读脚本，未启动runner |
| 文学质量 | **七项硬缺口仍保留** | E01.2 prompt gain、E11/T22 repair gain、T06 degrade rate、T16真实before/after、T18 exemption truth、T26 dialogue marker calibration、human labels；工程回归不替代收益证据 |

`D:/小说写作/xuanqiong-wenshu/TASK_HANDOFF_NOVEL_QUALITY.md`顶部“当前接续入口：阶段八持久化审批续跑”已核验，覆盖下方历史“当前权威入口”“唯一下一任务”等旧措辞；该文件由主代理更新，本次未编辑。

边界agent新测试先红；探索性session54497已由主代理在约45%主动结束，状态JSON明确记录8项失败、执行中源码漂移及`valid_gate=false`。本报告把它作为非冻结修复线索，不把它写成正式全量结果；最终冻结runner必须从头跑原始全量，不删测试、不跳测试。`D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_boundaries.py`已出现，但本次没有执行它；26项通过数来自现有final日志。

## 7. 下一批计划与退出条件

1. **边界回归已通过，进入冻结复核**：26项边界及213项相关组合日志已存在；复核`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundary-freeze.json`五文件指纹与冻结定向结果。畸形intent隔离、精确handoff/CAS、dead-letter、Run lease接管、晚到写终态、source绑定和并行审批已有新增回归，不重复当作未实现事项。
2. **复核冻结覆盖与有效反向**：保留26项边界结果，针对当前冻结源码复跑受影响反向并核对相关组合；独立进程恢复、真实数据库并发及部署结果仍单列，不由fixture回归外推。
3. **冻结后跑正式后端全量**：使用 `D:/小说写作/xuanqiong-wenshu/logs/run_backend_stage8_frozen_gate.py`。脚本在backend目录调用原虚拟环境python的 `-m pytest -q`，以独占创建方式输出带时间戳的before/result JSON和日志；比较代码/配置及既有数据文件指纹。门禁须exit0、代码无漂移、既有资产无变化；探索性session不替代这次冻结验收。
4. **归档与独立门禁**：保留旧失败、五类反向及探索日志；冻结结果出现后更新三个当前入口。Docker/MySQL实机与七项文学质量缺口分开推进，整体维持 **active / NO-GO**。

已完成的source ACK/read fact两项追加反向不再列为待实现；后续要求针对边界修复后的新源码确认是否要重跑并补足矩阵。正式冻结runner只有退出码0且代码和既有资产一致时才将valid_gate置为true；“脚本已准备”不等于“门禁已运行或已通过”。

## 8. 文档任务交付范围

本次仅更新`D:/小说写作/xuanqiong-wenshu/docs/reports/CURRENT_EXECUTION_STATUS_20260906.md`和`D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_WORKER_CONTINUATION_PLAN_20260907.md`顶部状态/计划，并新增本报告`D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_STAGE8_CONTINUATION_IMPLEMENTATION.md`。旧状态文件的历史章节、旧计划原文保留；未修改源码、测试、根任务入口、runner、日志、数据库或上传文件，未创建新task/thread。

本次没有运行pytest、前端门禁或反向脚本；所有测试结果均来自已存在日志/JSON，主代理转述单独标注。阶段八全部源码修复、正式冻结全量、部署及文学质量验收仍由主任务继续推进。

### 边界批次交付补记

- 已核验`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-final.log`：26 passed in 135.59s；比先前反馈20项更新，不覆盖旧日志。
- `D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-green3.log`：213 passed in 217.73s；冻结定向另在`D:/小说写作/xuanqiong-wenshu/logs/continuation-boundaries-frozen-targeted.log`推进，读取时只有进度，未宣称终局通过。
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_boundaries.py`新增覆盖畸形intent与健康任务共存、精确handoff、重试耗尽dead-letter、Run lease接管、source续租CAS、checkpoint来源绑定、陈旧writer终态覆盖和并行审批。
- 边界26项只关闭上述fixture范围的回归；正式后端全量由`D:/小说写作/xuanqiong-wenshu/logs/run_backend_stage8_frozen_gate.py`从头运行原始门禁，保留所有测试，验证源码与既有资产一致。
