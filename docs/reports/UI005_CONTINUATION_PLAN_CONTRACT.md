# UI005 阶段八批次：Continuation 冻结计划材料合同

## 1. 交付状态与边界

本批次完成独立纯函数合同与新测试，未修改 execution/runtime/worker/事务 producer/consumer 或其他既有源码，未访问持久数据库。阶段七“2358 绿”为主代理提供的上一批次状态，本报告不将其列为本批次执行结果；历史文件名中的日期数字仅视为本机历史标签。

本批次结果：先红（新模块不存在）→159项正常测试通过；initial 缺省 payload 新回归先红（3 failed / 166 passed）后绿→169 passed；最终17/17进程内变异检出→正常 pytest 169 passed。纯 helper 完成不等于持久化 continuation 完成；blocked 意图提交、source ACK、Run lease、激活 queued、消费幂等及状态收敛仍由主代理实现和验证。

| 文件 | 作用 |
|---|---|
| D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_plan.py | 纯校验与递归冻结输出 |
| D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_continuation_plan.py | 新增 169 项正常 pytest 用例 |
| D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_CONTINUATION_PLAN_CONTRACT.md | 本合同与交接说明 |
| D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan | 红绿日志、内存变异日志及摘要 |

## 2. 最终接口（供 producer / consumer）

~~~python
load_continuation_plan(
    *, run, revision, context_snapshot, capability_snapshot,
    approval, approval_step, source_job,
    expected_actor_user_id: int | None = None,
) -> FrozenContinuationPlan
~~~

- FrozenContinuationPlan.steps：tuple[FrozenContinuationStep, ...]。
- 每一步：order: int、tool_name: str、depends_on: tuple[int, ...]、arguments: Mapping、planner_arguments: Mapping、risk_level: str。
- 两类 dataclass 均 frozen=True, slots=True；返回的嵌套 Mapping 使用只读代理，数组转 tuple，不保留可变输入引用。
- FrozenContinuationPlan.payload：只读 Mapping；to_payload() 返回独立 dict，可直接 JSON 序列化。其内容都是定位/摘要标量，浅复制已足以完全分离。
- 错误：ContinuationPlanError(ValueError)，提供稳定 field；公开异常文本仅固定前缀和固定 field，不包含材料值。

### to_payload() 精确 15 个键

~~~text
schema_version
run_id
source_job_id
plan_revision_id
plan_revision_key
plan_revision_digest
context_snapshot_id
context_snapshot_key
context_snapshot_digest
capability_snapshot_id
capability_snapshot_key
capability_snapshot_digest
approval_id
step_id
outcome
~~~

schema_version=1；其余值来自本次校验的实际行。审批状态作为 outcome。早期沟通“16 个键”的计数已纠正，列出的键名始终一致。

**payload 不包含** steps、goal、arguments、planner_arguments、actor_user_id、业务文本。consumer 从冻结关系材料再次调用 helper 获取步骤，而非让持久化 intent 复制另一份未受验证的计划。

## 3. 校验合同与行号证据

下列行号指本次交付的 D:/小说写作/xuanqiong-wenshu/backend/app/agent/continuation_plan.py。输入是已加载行；helper 用 vars(row) 读取本地已加载属性，不触发 ORM descriptor/lazy SQL。缺失/过期字段抛固定合同错误，调用者负责 eager load/refresh。SimpleNamespace 和真实 transient ORM 模型均有测试。

### 3.1 身份、摘要和定位

- 第 146–180 行：所有输入行必须有本地 id、run_id；以 Run 为根严格比较实际模型拥有的 user/project/session/correlation/transaction 字段。数字和布尔值不混同。
- 字段按真实模型而非虚构属性检查：revision/context_snapshot 拥有全部关联字段；capability_snapshot 只有 run/user/project/transaction；approval/source_job 没有 session_id；approval_step 没有 project_id/session_id。
- 第 182–190 行：重算 PlanRevision canonical 材料的 SHA-256；材料与既有 agent_plan_service.plan_revision_material 同字段，包含 revision_id/run/session/context parent/parent revision/revision number/user/project/correlation/transaction/planner/status/rationale/plan_json，不含 SQL row id 或自身 digest。
- 材料采用 JSON ensure_ascii=False、sort_keys=True、紧凑 separators。list/tuple 往返等价；拒绝 NaN/Infinity、非字符串对象键、集合、任意 Python 对象，而非通过 default=str 偷做字符串化。测试以既有 canonical_digest(plan_revision_material(...)) 生成 golden 摘要。
- 第 191–221 行：plan schema 和 context schema 精确为整数 1；revision.context_snapshot_id 必须指向传入 context row；Run 当前 revision ID/key、context ID/key、capability ID/key/digest 都要匹配。context_kind 必须与 planning/replanning 对应；replan parent 非空且不自指，initial 不携带 parent。
- capability key 验证为 resolver-v<resolver_schema_version>:<digest 前16位>:run:<Run.id>，避免错误 Run-qualified key。context/capability digest 要求小写 64 位十六进制。

**明确分工**：这里独立重算的是 plan digest；context/capability 的内容摘要计算、catalog/provider 合同、ContextRef 资源实时权限仍由严格 reader 和既有 snapshot 校验负责。只传入伪造但语法正确的 digest 不构成其内容已被本 helper 证明。context refs 无需在此重复解析，从而不混淆 initial 自动小说上下文后缀与 replan 用户 refs。

### 3.2 冻结步骤、global order 和参数

- 第 223–250 行：非空步骤列表，order 严格正整数、递增且唯一，直接使用既存 global order；从不读取 replan_base_step_order 来二次偏移。
- depends_on 保持原列表顺序，转不可变 tuple。重复、自依赖、前向引用、未知节点拒绝；本批次采用同一冻结 revision 内的前序节点闭包。若将来允许显式引用旧 revision 的已完成节点，需要额外持久化的 parent-step 证明，不能直接放松这一检查。
- 每步工具必须在 capability_snapshot.selected_capability_ids_json 中，风险枚举保留 read/suggest/write/destructive/manage。
- arguments **从 revision.plan_json["tool_arguments"][tool_name] 提取**，不拿 planner_arguments 代替已经投影的业务参数。planner_arguments 单独递归冻结，避免丢失原决策材料。
- 同一个工具多次出现时共享原计划按 tool 存储的投影语义，但返回每步独立冻结材料；不按 tool 去重步骤、不丢 order。

### 3.3 审批必须对应冻结步骤

- 第 252–280 行：approval.step_id 等于 approval_step.id；真实 step_order 必须命中计划，approval/step 工具名都等于冻结工具。step idempotency_key 精确为 <run_id>:step:<global_order>:<tool_name>。
- 被审批步骤必须是 write/destructive/manage，而非 read/suggest。
- step.input_json["goal"] 与冻结 plan goal 一致，step.input_json["tool_arguments"] 与冻结投影一致。没有从 mutable Run tool_arguments 取值。
- outcome 仅 executed/rejected/execution_failed。pending、approved、executing、cancelled 和未知状态均拒绝生成 intent。
- 仅 executed 要求 approval_step.status=completed；rejected/execution_failed 不要求已完成，也不在本函数内把 step 改为 cancelled/failed。
- step completed 不是成功写入的充分证明：consumer 仍须核验对应 execution fact、lease generation、Artifact 完整性与绑定，且不能重新调用已成功 writer。

### 3.4 goal / actor / 其他系统项的精确规则

当前主循环使用 arguments={"goal": goal, **step_arguments} 创建审批（读取时 D:/小说写作/xuanqiong-wenshu/backend/app/agent/execution.py:804–811）。本 helper 复制相同合并优先级：

1. 无 per-tool goal 时，approval.request_json 必须携带并精确匹配 plan goal。
2. 冻结 tool arguments 自身有 goal 时，以冻结 per-tool goal 覆盖；这不是忽略 goal，而是忠实于实际生产者合并顺序。checkpoint 外层 goal 仍精确等于 plan goal。
3. actor_user_id 已经在冻结 arguments 中：保留且要求严格正整数；审批值精确匹配冻结值。若传 expected_actor_user_id，还必须与冻结 actor 相等。
4. actor 只在审批请求中额外出现：仅在传入独立可信 expected_actor_user_id 且严格正整数、精确相等时接受；不要求 actor 等于 execution owner，从而不破坏合法成员 actor/owner 分离。
5. expected_actor_user_id 不得由待校验 request_json 自行取回；纯函数只比较声明，实时成员权限验证留给调用者。没有独立可信 actor 时，额外 actor 拒绝。
6. 其他额外字段（system/token/未知 key 等）不自动剔除，整个审批请求与预期映射严格相等；冻结业务字段则必须原样保留，不能凭名称随意忽略。
7. 系统 actor 白名单校验不会把 actor 注入 FrozenContinuationStep.arguments，payload 也不持久化 actor。

既有独立候选接受路径的 chapter.version.accept 会创建无 step_id、带 actor 的审批（读取时 D:/小说写作/xuanqiong-wenshu/backend/app/api/routers/agent.py:1416–1425）。它不是本合同中的原计划 step continuation，缺少计划步骤证明时本 helper 明确拒绝；不伪造步骤来承接。

### 3.5 source_job：支持初始执行、replan 和 continuation

- 第 289–314 行的来源分支接受 agent_execution/agent_continuation；不检查 source.status 是否 succeeded，不读取 Run lease，不激活 queued。
- agent_execution：必须等于 Run 保留的 execution_job_id。initial 的 planner_id 精确为 agent_execution:<source.id>:initial。initial source.payload_json 可以是空对象，run_id 缺省时由实际行身份、Run locator 和精确 planner_id 共同绑定；一旦 payload 含 run_id（包括 null），仍严格匹配。replan/continuation 则仍必须含正确 run_id。
- replan 的 revision.planner_id 记录发起修订的旧 job，而 source 是执行修订的新 job，二者不应强行相等。通过冻结 context.context_json.execution_job_id 绑定新 source，再核对其 payload.phase=replanning、严格正整数 revision，以及 planner_id 的 replan 后缀。
- agent_continuation：不能再套 initial planner_id，也不能要求 Run execution_job_id 改成 continuation job id。改为精确核验其持久化 payload 的 schema/run/plan/context/capability 定位与摘要，保持同一冻结计划链。
- 上一个 source intent 的 approval_id/step_id/source_job_id 与当前被触发审批可以不同，因此不误比较为当前审批；source 自身的合法激活/终态证明由 producer/consumer 负责。

### 3.6 并行审批的集成注意（按主代理确认，helper 不放宽）

execution_job_id 应保留 initial/replan 来源，不被最新 consumer 覆盖。最新 consumer 单独用 continuation_job_id 记录。两个并行审批可能都创建于同一 initial source；若先完成的 consumer 覆盖 execution_job_id，后发审批的合法 initial source 会与 helper 的精确绑定冲突。producer 必须按具体 approval 创建时的实际来源选择 source_job，而不是将所有审批绑定到最新 job。

continuation 来源分支通过其持久化 payload 的冻结计划/context/capability 绑定，不要求 execution_job_id 等于 continuation job id。以上是集成责任提示；本批次未修改主代理 producer/consumer，也未为兼容覆盖行为放宽 source 身份验证。主代理报告的“真实初始 writer→统计 worker 链3项通过”作为外部集成状态记录，本批次未运行这3项，不与独立169项重复计数。

## 4. 实测与证据

工作目录：D:/小说写作/xuanqiong-wenshu/backend。只运行新增测试，保留仓库 pytest.ini/conftest 正常加载；禁用字节码和 pytest cache 落盘以限制写集，不跳过测试或降低断言阈值。

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider app/agent/test_continuation_plan.py
~~~

| 阶段 | 实际结果 | 日志 |
|---|---|---|
| 红：先创建新测试，模块缺失 | exit=2，ModuleNotFoundError，1 个收集错误 | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/red.log |
| 初版第一次绿 | exit=0，159 passed in 0.68s | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/green_attempt_1.log |
| 初版14次内存变异 | 每次收集159项，exit=1且有真实call断言失败 | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/mutation_summary.json、mutation_*.log |
| 初版再绿（非最终版本） | exit=0，159 passed in 0.79s | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/final_green.log |

| initial payload兼容红阶段 | exit=1，3 failed / 166 passed；3个缺省正例精确失败于source payload run_id | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/initial_payload_red.log |
| initial payload兼容绿阶段 | exit=0，169 passed in 2.78s | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/initial_payload_green.log |
| 最终17次进程内变异 | 每次收集169项，exit=1且有真实call断言失败 | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/final_mutation_summary.json、final_mutation_*.log |
| 最终正常pytest | exit=0，169 passed in 2.66s | D:/小说写作/xuanqiong-wenshu/logs/ui005_stage8_continuation_plan/initial_payload_final_green.log |

红阶段为真实缺模块收集失败，不虚称已有业务逻辑断言失败；逻辑敏感性由后续变异验证。

| 最终内存变异 | 失败用例数 | 检出 |
|---|---:|---|
| skip_plan_digest | 9 | 是 |
| skip_context_parent | 1 | 是 |
| ignore_current_revision | 4 | 是 |
| ignore_approval_arguments | 8 | 是 |
| ignore_step_arguments | 1 | 是 |
| skip_completed_gate | 4 | 是 |
| allow_approved_outcome | 1 | 是 |
| double_global_offset | 42 | 是 |
| use_planner_suggestions_as_arguments | 42 | 是 |
| keep_mutable_nested_json | 7 | 是 |
| omit_dependency_membership | 2 | 是 |
| skip_continuation_payload_binding | 1 | 是 |
| skip_replan_source_binding | 1 | 是 |
| untrusted_actor_allowance | 1 | 是 |
| reject_initial_omitted_run_id | 3 | 是 |
| ignore_initial_present_run_id | 5 | 是 |
| allow_replan_omitted_run_id | 1 | 是 |

机制：只读 helper 源码，在内存替换目标片段；AST 提取函数定义，在独立 namespace 编译；pytest collection 插件替换新测试模块中的 loader 引用，finally 恢复。没有写磁盘 mutation 源码，没有修改共享模块函数或既有测试。证据日志仅含合成 fixture 数据。

变异前后 helper SHA-256 一致：b9e4f5773b345838f96e227948ed630c4dd3ac0e096ae121417675a3741f2f07。

真实 public Runtime/JobService 正例使用仓库 task_session 提供的 sqlite+aiosqlite:///:memory:，以正式 create_session/create_run/create_job(payload=None)/create_revision/ensure_step/request_approval/decide_approval 建立拒绝态审批，再 refresh 实际关系行调用 helper。没有写持久数据库、没有改 status 假造 executed、没有调用 writer/外部 Provider。两个 transient ORM 缺省正例及5个存在但错误 run_id 反例、2个非initial缺失反例同时保留。

## 5. 主代理集成检查清单

1. producer 提供实际 approval_step 以及全部已加载 scalar 字段；replan/continuation 使用上述差异化 source 绑定，不另加不成立的 initial planner-ID 等式。
2. producer 若额外注入 actor，应提供独立可信 expected_actor_user_id；没有独立来源就保持当前冻结参数合同，不从 request 自证。
3. consumer 将 intent payload 的计划/context/capability 定位与读取结果对比后调用 helper；旧 revision 已被替换时应终止旧意图，不重新解释成新计划。
4. executed 同时要求成功执行事实与 Artifact 证明，且履行既有 Run/step lease fence；rejected/execution_failed 路径只收敛终态，不创建 read 执行。
5. source ACK 与 Run lease 交接屏障、pause/cancel、blocked→queued 都由事务模块处理；本 helper 无此副作用，不能因为校验成功就认定允许 claim。
6. initial 自动 ContextRef 后缀、replan 当前 refs 的完整内容验证继续走主代理严格 reader；不要把此计划校验替代 context/capability 完整性验证。
7. 本批次只跑新测试。后续真实 worker 写→读、多审批/replan、并发/崩溃/恢复及全量门禁仍需主代理集成验证；不将169个合同测试用例等同续跑完成。
