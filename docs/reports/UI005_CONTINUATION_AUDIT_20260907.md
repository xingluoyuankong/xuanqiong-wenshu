# UI005 Continuation 状态/幂等审查（2026-09-07）

## 0. 审查结论

本次只读审查限定在续接链路：

- `backend/app/agent/continuation.py`
- `backend/app/agent/continuation_worker.py`
- `backend/app/agent/continuation_plan.py`
- `backend/app/agent/write_executor.py`
- `backend/app/agent/worker.py`
- `backend/app/agent/test_continuation_worker.py`
- 为确认租约与事实语义，补读 `backend/app/agent/jobs.py`、`backend/app/services/agent_runtime.py`、`backend/app/services/agent_execution_service.py`。

主代理回报的 source 绑定修订已核对：`load()` 优先从 approval step 的 `input_json.approval_source_job_id` 取来源，initial/replan 的 `execution_job_id` 保留，consumer 写入 `continuation_job_id`。真实成功链、reject/fail terminal 事务不再列为本轮风险。

| 编号 | 严重度 | 未修风险 | 主要影响 |
|---|---|---|---|
| F1 | P1 | activation poison | 单条损坏/不一致的 blocked intent 阻断同一轮全部续接，并阻断后续 Job claim |
| F2 | P1 | 过期 source ACK 无恢复闭环 | source 在 ACK 前过期时，Run/Job 进入互相等待，intent 留在 blocked/不可领取 |
| F3 | P1 | step lease 重领与 read execution fact 不收敛；consumer 失败态不闭合 | 重试重复读、stale generation，Job 可能 dead-letter 而 step/execution 仍 started/running |

## 1. F1 — activation poison 阻断整个 worker

### Evidence → Finding → Path

**Evidence**

- `continuation.py:192-196` 扫描最多 50 个 `status == "blocked"` 的 intent。
- `continuation.py:207-215` 校验 approval、source、冻结 payload、return phase；任一失败抛出 `ContinuationConflict`。
- `continuation.py:220-222` rollback 后重新抛出，没有隔离坏 intent 或继续下一候选。
- `worker.py:138-142` 在 Job claim 前直接调用 `activate_ready()`；该调用位于 worker handler 异常处理块之外。

**Finding**

第一条坏 intent 会让 `poll_once()` 在 `claim_next_job()` 之前退出，健康 intent 没有机会被领取。坏记录仍是 `blocked`，下一次轮询再次命中；共用 worker 的其他 Run 会被饥饿。

**Path**

`blocked(bad) -> activate_ready -> approval/source/frozen check raises -> rollback -> poll_once exits -> no Job claim -> bad remains blocked -> repeat`。

### 复现条件

1. 准备两个按 `created_at` 排序的 blocked continuation intent。
2. 把第一个 intent 的 `approval_id` 指向不存在记录，或把 `plan_revision_digest` 改为错误值；第二个保持有效且 source 已 `succeeded`。
3. 使用带 `agent_continuation` handler 的 `AgentWorker.poll_once()`。
4. 预期当前行为：抛出 `ContinuationConflict`，第二个 intent 仍为 `blocked`，本轮没有 Job 被领取。

只读 AST/内存桩结果：`F1 poison: raised before healthy candidate; rollback=1`。

当前测试中的 `test_modified_frozen_intent_is_rejected_before_read`（`test_continuation_worker.py:220-231`）只断言直接调用 activation 会报错，没有断言坏记录不得阻断健康记录。

### 最小修复

- 每个 candidate 使用 savepoint/独立事务；校验失败时把该 intent 原子标记为 `failed` 或 `dead_letter`，记录固定错误类型并继续下一候选。
- `poll_once()` 保留兜底处理，activation 单条失败不得阻断整个 Job poll；同时保留可检索错误事件。
- quarantine 使用 job id 与当前状态条件更新，保证重复 worker 不重复改写。

### 测试清单

- `test_activation_poison_does_not_starve_valid_intent`
- `test_activation_poison_is_quarantined_idempotently`
- `test_poll_once_claims_other_job_after_activation_conflict`

## 2. F2 — 过期 source ACK 无恢复闭环

### Evidence → Finding → Path

**Evidence**

- `continuation.py:181-184`：source 尚未 `succeeded` 时，Run 置为 `awaiting_approval`，intent 保持 `blocked`。
- `continuation.py:213`：activation 只有 `loaded.source.status == "succeeded"` 才能继续。
- `jobs.py:31-35`：普通 Job 可领取的 Run 只有 `created/planning/running`，另加 `paused + recovery_ready`。
- `jobs.py:394-491` 的 handoff reconciliation 只处理 terminal Run 下的 `visible_response` 与 `agent_execution` ACK，不处理审批交接的 blocked continuation source。
- `agent_runtime.py:2324-2340` 的 stale-run sweeper 只扫描 `planning/running`，不会回收 `awaiting_approval`。
- 即使 Run 被置为 `paused/recovery_ready`，`continuation.py:205-206` 仍把“paused 且有 pause_reason”统一跳过，恢复标记也被阻断。

**Finding**

source worker 在最终 ACK 前退出或租约过期时，审批已执行、continuation intent 已落库，但 source 仍为 `running`。Run 若保持 `awaiting_approval`，source 与 continuation 都不满足普通领取条件；若进入 `recovery_ready`，activation 又被 pause gate 拦住。现有 reconciliation 没有该审批交接路径，因此没有自动收敛点。

**Path**

`source running + lease expired -> continuation blocked -> Run awaiting_approval -> claim_next_job excludes Run -> reconciler ignores non-terminal approval handoff -> blocked remains`。

恢复标记路径：`stale-run -> paused/recovery_ready -> activate_ready sees pause_reason -> rollback/continue -> blocked remains`。

### 复现条件

1. 用 `pending_chain` 建立初始计划并完成审批写入。
2. 在写入完成前/期间把初始 source job 置为 `running`，设置已过期 `lease_expires_at`；使 `complete_write()` 生成 blocked intent 并把 Run 保持在 `awaiting_approval`。
3. 轮询 worker：activation 因 source 非 succeeded 跳过，`claim_next_job()` 因 Run 状态不可领取返回空，source 也没有被现有 handoff reconciliation 回收。
4. 独立恢复标记场景：令 Run 原本处于 running 且 Run lease 过期，再由 stale-run sweeper 转为 paused/recovery_ready；即使 source 已 ACK，该 intent 仍因 paused + pause_reason 保持 blocked。对 awaiting_approval 本身运行 sweeper 不会改变状态。

只读 AST/内存桩结果：`F2 expired ACK: awaiting_approval not claimable; activation requires succeeded; reconciler has no approval handoff branch`。

现有 `test_source_ack_and_live_run_lease_gate_continuation`（`test_continuation_worker.py:189-216`）只验证手动清空 source 和 Run lease 后成功，没有验证 source 过期后的自动回收。

### 最小修复

增加按 continuation payload 的 `source_job_id` 精确绑定的 source-ACK recovery/reconciliation：

1. 原子锁定 source 与 intent，确认 source 属于同一 Run/用户，并确认已有可验证 handoff 证据。
2. source lease 过期且 handoff 证据完整时补齐 durable ACK；没有完整证据时只把 source 重排队，不得凭超时直接写 `succeeded`。
3. 允许 `awaiting_approval` 下的 source recovery 走专用回收路径，但 continuation activation 仍必须等待 source ACK。
4. 区分用户暂停和租约恢复：`paused + recovery_ready` 可自动 activation，用户暂停继续等显式 resume。

### 测试清单

- `test_expired_source_ack_recovery_activates_intent`
- `test_expired_source_without_handoff_is_requeued_not_succeeded`
- `test_awaiting_approval_source_recovery_bypasses_only_source_gate`
- `test_recovery_ready_allows_activation_but_user_pause_does_not`

## 3. F3 — 并发 step lease 与 consumer retry/失败态不收敛

### Evidence A：generation 重领与 execution fact 不匹配

- `agent_runtime.py:1046-1067` 的 `claim_step()` 允许过期 lease 重领，并递增 `AgentRunStep.lease_generation`。
- `agent_execution_service.py:56-63` 的 `begin_read_execution()` 遇到同一 idempotency key 的 `started` execution 时直接返回旧 fact，未将 generation 与当前 step claim 对齐，也未确认旧 execution 仍由有效 lease 持有。
- `continuation_worker.py:83-87` 先以新 step generation claim，再调用 `begin_read_execution()`；`92-95` 以新 generation 完成 step/fact。
- `agent_execution_service.py:169-174` 会拒绝旧 generation 的完成并抛出 `execution lease generation is stale`。

### Evidence B：consumer 异常没有事实终结

- `continuation_worker.py:90-95` 的 read tool、step completion、fact completion 之间没有 per-step 失败投影。
- `continuation_worker.py:118-120` 异常只 rollback 后重新抛出。
- `worker.py:188-196` 之后只调用 `AgentJobService.fail()`；不会同步标记当前 `AgentRunStep` 或 `AgentCapabilityExecution`。
- `worker.py:118-131` 的 heartbeat 只延长 Job lease；consumer 在 `continuation_worker.py:31` 取得的 Run lease 没有对应 heartbeat，长 read 期间 Run lease 可能过期，另一 Job 可重新取得 Run lease，旧 consumer 到 `continuation_worker.py:97-99` 才在 ACK fence 发现变化。

### Finding

存在两个可叠加的重试故障：

1. Worker A 的 step lease 过期后，Worker B 重领同一步并得到更高 generation；B 复用 A 的 `started` execution fact，最终完成时报 stale generation。
2. read tool 或 fact completion 失败时，Job 可按 attempt policy 进入 queued/dead_letter，而 step 仍是 running、execution 仍是 started；下一次重试又复用旧 started fact。长任务期间 Run lease 还可能先过期，造成并发 consumer 与最终 ACK 失败。

Job lease 字段本身没有传错：consumer 在 defer/最终 ACK 使用 `job.lease_owner` 与 `job.lease_generation` 是正确的 Job fence。未修点是 Job、step、execution、Run 四套状态没有统一恢复和失败投影。

### Path

`claim step gen=1 -> execution started gen=1 -> lease expires -> claim step gen=2 -> begin returns execution gen=1 -> read executes again -> complete rejects stale -> rollback -> Job retry/dead-letter, step/execution remain non-terminal`。

只读 AST/内存桩结果：

- `F3 retry: requested generation=2, returned fact generation=1, completion=stale conflict`
- `F3 failure cleanup: consumer has no fail_read_execution/fail_step call`

### 复现条件

**重领路径**

1. 创建一个 pending read step 和同一 idempotency key 的 execution。
2. Worker A claim step，得到 generation=1，创建 `execution(status=started, generation=1)`，随后停止心跳并让 step lease 过期。
3. Worker B claim 同一步，得到 generation=2。
4. B 调用 `begin_read_execution(... lease_generation=2)`；当前实现返回旧 started execution，generation 仍为 1。
5. B 完成 read fact 时抛 `AgentCapabilityExecutionConflict`；后续重试重复进入该路径。

**工具异常路径**

令 `execute_read_tool()` 或 `complete_read_execution()` 抛异常，观察 Job retry/dead-letter 与 step/execution：Job 可能已不再 running，但 step/execution 没有对应 terminal/retry projection。

现有成功链测试（`test_continuation_worker.py:99-117`）只断言两个 step 最终 completed 和 `attempt_count=1`，没有覆盖 lease expiry、read tool exception、stale generation 或 dead-letter 后事实状态。

### 最小修复

- 将 step claim 与 execution fact claim 绑定为同一 fenced transition；当前 step generation 必须核验，旧 `started` fact 只有在确认原 step lease 已失效后才可原子重置到新 generation。
- 为 execution fact 增加可验证的 lease owner/expiry，或由 service 在 step lease fence 成功后原子更新 generation；旧 worker 的完成必须稳定落入 stale 分支。
- 在每个 read step 周围增加失败投影：当前 owner/generation 有效时调用 `fail_read_execution()` 与 `fail_step()`；generation 已变化时只记录 stale/丢失 lease，不覆盖新 owner 的事实。
- Job 进入 `dead_letter` 时必须同步得到 Run-local 的 step/execution terminal 或明确可重试状态，禁止 Job terminal 而事实永久 started/running。
- 为 Run lease 增加与 Job heartbeat 同节奏的 heartbeat，或改成统一的可续租 Run/Job fence。

### 测试清单

- `test_step_reclaim_advances_generation_and_rebinds_execution`
- `test_read_tool_failure_projects_step_and_execution_failure`
- `test_stale_generation_does_not_mark_new_owner_failed`
- `test_job_dead_letter_converges_run_facts`
- `test_long_read_heartbeats_run_lease`

## 4. 已核对并关闭的点

- 当前 consumer 写入的是 `context_json["continuation_job_id"]`（`continuation_worker.py:106-107`），没有覆盖 initial/replan `execution_job_id`。
- `load()` 从 approval step 读取 `approval_source_job_id`（`continuation.py:58-67`），显式 source 与 checkpoint source 不一致时拒绝。
- Job ACK 条件匹配 Job 自身的 `lease_owner/lease_generation`（`continuation_worker.py:110-112`）；Run 的 owner/generation 只用于 Run lease fence。
- 未主动编辑业务源码、未创建新 Codex task。只读约束执行偏差详见验证记录。

## 5. 验证记录

- 未运行全量测试。
- 执行偏差：误启动了一次 `python -m pytest -q app/agent/test_continuation_worker.py`，随后主动中止（退出码 1，仅见进度点，无完整结果）。该测试的 `_factory(tmp_path)` 会创建临时 SQLite 数据与 artifacts，pytest/导入也可能生成缓存，因此本轮不应表述为“零文件/零数据写入”；未做清理，以免覆盖并发成果。未连接或操作业务数据库。后续探针仅使用 `python -B`、标准库 AST 与内存对象，不导入应用，也不运行 pytest。
- 已执行只读 AST/内存桩，结果为：
  - `F1 poison: raised before healthy candidate; rollback=1`
  - `F2 expired ACK: awaiting_approval not claimable; activation requires succeeded; reconciler has no approval handoff branch`
  - `F3 retry: requested generation=2, returned fact generation=1, completion=stale conflict`
  - `F3 failure cleanup: consumer has no fail_read_execution/fail_step call`

## 6. Evidence index

| ID | 证据 |
|---|---|
| E1 | `continuation.py:192-223` activation 批处理、异常 rollback/rethrow、source ACK gate |
| E2 | `worker.py:138-142` activation 位于 claim 前且不在 handler try 内 |
| E3 | `jobs.py:31-35,394-491` Run claim gate 与 handoff reconciliation 覆盖范围 |
| E4 | `agent_runtime.py:1046-1073,2324-2340` step generation 与 stale-run recovery |
| E5 | `agent_execution_service.py:56-75,169-184` started fact idempotency 与 generation completion fence |
| E6 | `continuation_worker.py:83-120` consumer read/ACK/rollback 路径 |
| E7 | `test_continuation_worker.py:99-117,189-216,220-231` 现有成功、source gate、payload corruption 覆盖及缺口 |

## 7. 快照、绝对路径与反向验证

行号基于北京时间 2026-09-07 04:57:00 的只读内存快照；交付前业务文件 SHA-256 与该快照一致，测试文件继续被其他进程修改。上述测试覆盖描述仅针对该快照，不把后续新增测试归为缺失。用户回报的成功链通过不作为本审查独立 pytest 通过结果。

| 绝对路径 | 快照 SHA-256 |
|---|---|
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation.py` | `21d60992703b199ceaccd05f741b58232fda15752b8397e0193848377befbd5b` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_worker.py` | `749fabfd237084c23625c1b9d72d87ab2763af0ff7339b5e2b287ca2cc74f3f8` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_plan.py` | `b9e4f5773b345838f96e227948ed630c4dd3ac0e096ae121417675a3741f2f07` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/write_executor.py` | `faa74a45929aab18c6362f73114c532071b5b28e5d24214e8fda48545213337b` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/worker.py` | `c99872eb62907766a698cd96292ba24c49f634e03250d4e09f8750957649837e` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_worker.py` | `ce1ba86cbeefbaeba7305ec945898ec763a6d85908200f6ed34dce34f90ec989` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/agent/jobs.py` | `166d2077845c90d1ba8bee871a0e8b2641c7ef7b35d068ea4f07b550d5dd7f72` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_runtime.py` | `1e520337bf192bf20415dd319ef632b5eba04f2f1ed5b0d8c912279865addd91` |
| `D:/小说写作/xuanqiong-wenshu/backend/app/services/agent_execution_service.py` | `13dc134b032db8584a8fe0df02ffc7363cac410b95f365d6fc8246b799a0da93` |

建议修复后使用限定测试逐项做反向验证（本轮未修改实现或测试）：

- F1：恢复原始 rollback/rethrow，健康候选继续执行的断言必须失败；另测前 50 个 intent 全被暂停/等待 source 时，第 51 个健康候选仍有调度机会。
- F2：删去专用 source ACK recovery，过期 source 的自动收敛断言必须失败；恢复“所有 pause_reason 均拦截”后 recovery-ready 正例失败，但 user pause/cancel 负例继续通过。
- F3：恢复直接返回旧 started fact，generation 接管正例必须失败；移除 read step/fact 失败投影后 terminal 一致性断言必须失败。并用两个独立 session/barrier 验证旧 owner 的完成/失败不会覆盖新 owner。

补充核对：`AgentContinuationService.load()` 当前确实显式传入 approval_step，故“缺少必填 approval_step”不是当前缺陷。completed read checkpoint 仍只读取 step.output_json，未验证对应 read execution 的 snapshot/input/output digest；它属于 F3 的事实一致性边界，应一并补充“completed step 但 fact 缺失/started/digest 不匹配”负例，而非另开审查范围。

交付最后一次哈希复核：并发修改继续发生。以下文件已不同于 04:57 审查快照；三项结论定位以快照为准，未对这些新修订重新宣告缺陷仍存：

- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation.py`：`716eaf956f2ef3050bc00c1daacea5e1fb39e1bd17963534988b2176e6065a16`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_worker.py`：`68a5a2532668ab0d2847a6e31e0e1d56d2a82741320ce7ce05fed6ae1d93eebc`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/worker.py`：`cf5c05c9f1dd71859bb90aae5bbe153a5b8e2fe8b2ec62c1e091d2add607a960`
- `D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_worker.py`：`f470847ad3f1233c464f9a442d2dbf3d52e586f89d8a21bb55b30542af133faf`
