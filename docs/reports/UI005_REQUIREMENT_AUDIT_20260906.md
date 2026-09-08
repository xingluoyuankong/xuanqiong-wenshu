> **阶段七覆盖说明**：原F03 worker快照降级已改为共享严格读取，原F02的等待误判已修；正确backend全量2358通过。F02审批后持久化continuation仍未接线，因此完整工具依赖闭环尚未完成。下方原始复核与阶段六状态保留为历史。

> **本地2026-09-07更新**：本报告原F01审批边界已在阶段五/六修复并获190项组合验证（阶段六全量2273通过）；原F02等待审批依赖与F03 worker快照降级经当前源码重新检查仍存在。不要把后续审批细审F1—F5的完成误写成本报告三个编排缺口全部关闭。当前门禁见CURRENT_EXECUTION_STATUS_20260906.md顶部。

# UI-005 工具注册 schema / 自主工具编排需求审查

> 审查日期：2026-09-06。工作区：`D:\小说写作\xuanqiong-wenshu`。
> 读取时 HEAD：`dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb`；当前未提交改动属于证据基线，未作恢复、覆盖或提交。
> 唯一新增文件：`D:\小说写作\xuanqiong-wenshu\docs\reports\UI005_REQUIREMENT_AUDIT_20260906.md`。
> 方法：只读需求、当前源码和测试；使用标准库 AST 抽取未修改的函数/循环，在纯内存替身上验证分支。未导入应用模块、连接数据库、请求 Provider、启动服务/浏览器或 pytest；未编辑源码/测试。本文没有新增全量测试结论。

## 1. 结论与证据边界

UI-005 已有实质实现：声明式工具契约、内容寻址 Catalog Release、按 Run 解析的能力集合、读工具执行闸门、上下文参数投影、结构化 PlanDraft、持久化步骤及一次性失败重规划均已接线。历史“UI-005 已完成”适用于当时提交和专项覆盖，不代表当前所有执行入口满足同一合同。本次确认三个局部、可操作的缺口：**审批执行入口未复用完整 Run 契约闸门；等待审批被下游依赖误判为失败；新 Run 上下文完整性错误被降级为 legacy 兼容路径**。三个问题都有当前代码位置与纯内存复现，尚待解冻后补真实 worker/路由回归；本次没有执行这些集成回归。

自主编排的准确描述应为：**在冻结能力集合内选择至多八个不重复工具，串行执行 read/suggest，其他风险级别转审批，并在限定条件下最多追加一次只读重规划**。它不是已获效果证据的任意工具闭环代理；PlanDraft 的 `expected_result` 是展示元数据，不是执行后验收判定器。现有 fixture 能证明调度分支和持久化合同，测试数量、`provider_called=True` 或一次 TCP Artifact 成功均不充分证明规划选择正确、跨步骤效果达标或自然语言目标完成。

发布与最终全量状态完全沿用本次读取的当前状态表：**active / NO-GO；最终冻结后端全量执行中**。本文未读取或改写其自然终态，也不改变主代理门禁判定。小说正文质量、评分、长度、叙事、改写效果等硬缺口不属于本报告范围。

## 2. 需求来源与当前证据索引

所有位置为读取时文件行号。下文使用 E 编号引用本表的绝对路径，避免把相同文件重复列成长串。

| 编号 | 当前文件与位置 | 本次用途 |
|---|---|---|
| E01 | `D:\小说写作\xuanqiong-wenshu\TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md:4067-4068,4205-4268,4435-4453,4945-4965` | UI-005 字段、执行顺序、最小矩阵；后续以漂移阻断收口的历史口径 |
| E02 | `D:\小说写作\xuanqiong-wenshu\docs\reports\CURRENT_EXECUTION_STATUS_20260906.md:1-35,56-64,140-150` | 当前冻结门禁、accept actor 合同修复、真实模型效果证据边界 |
| E03 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\schemas.py:33-118,158-191,236-260` | 风险/访问/角色/审批/幂等/流式组合约束；PlanDraft 步骤字段 |
| E04 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\registry.py:69-118,129-267,274-473,572-614` | schema 校验；角色复核；RunBound 闸门；写工具绑定及启动期 Provider 策略 |
| E05 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\catalog_release.py:121-151,266-317` | 冻结 manifest/provider/schema；排序、唯一性、release digest |
| E06 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\capability_resolver.py:193-294,296-374` | 能力过滤及独立 release schema validator |
| E07 | `D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_runtime.py:737-826,2338-2447` | 新 Run 快照与身份；生成/改写预留 accept；审批生命周期 |
| E08 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\orchestrator.py:39-266` | 实际 planner 位于此文件：提示、PlanDraft 解析、参数限制、回退 |
| E09 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py:125-144,216-305,355-455,547-622,668-806,812-1025,1042-1089` | worker 编排入口、上下文载入、参数投影、依赖、审批、重规划、回复交接 |
| E10 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\context_refs.py:38-132` | ContextRef 解析结果、绑定字段及工具独立参数对象 |
| E11 | `D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py:63-76,116-130,1210-1215,1374-1380` | 稳定 HTTP 合同错误及实际审批入口 |
| E12 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\write_executor.py:126-195,285-312` | actor/owner 分离；写能力事实；完成候选后暂停，未自动续跑依赖计划 |
| E13 | `D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_execution_service.py:35-138` | 关系化能力执行事实、审批幂等及 handler identity 二次校验 |
| E14 | `D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_context_service.py:94-143,169-195`；`D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_plan_service.py:45-96,162-175` | ContextSnapshot / PlanRevision 创建与摘要核验 |
| E15 | `D:\小说写作\xuanqiong-wenshu\backend\app\repositories\agent_catalog_repository.py:140-188,203-239` | Run/session/project 关联、selected capabilities、release 引用和执行溯源 |
| E16 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\provider_runtime.py:37-175`；`D:\小说写作\xuanqiong-wenshu\backend\app\agent\worker.py:70-94` | 分阶段 Provider 装载；失败事件投影 |
| E17 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\runner.py:661-710`；`D:\小说写作\xuanqiong-wenshu\backend\app\agent\tool_result_digest.py` | 历史恢复执行路径及结果摘要；不是通用动态结果参数引用系统 |

测试证据索引是**当前测试源码的断言范围**，不声称本次重跑通过：

| 编号 | 当前测试绝对路径 | 已核对的覆盖点 |
|---|---|---|
| T01 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_registry_ui005_contract.py:27-216` | permission/confirmation/idempotency/stream 组合、字符串范围、accept actor 字段；其中名含 timeout_and_cancel 的用例本身主要触发 timeout，取消另见 T09 |
| T02 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_execution_capability_fence.py:18-201` | 允许名称、handler/manifest/provider/generation 漂移、成员降权、projectless 创建者私有；漂移多通过直接调用 bound/assert 检查 |
| T03 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_catalog_release.py:62-142`；`D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_capability_resolver.py:26-217` | 深冻结、确定性摘要、重复/无效输入、角色/可用性过滤、release schema |
| T04 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_orchestrator.py:27-131` | Provider 替身的允许工具、作用域、回退、用户显式工具零调用、步骤元数据、绑定参数限制及 attempt ledger |
| T05 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_worker.py:361-650` | 参数投影、失败前置阻断、FakePlanner+工具替身的一次重规划与持久化 job/step/event |
| T06 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_context_refs.py:44-228,540-599` | 严格引用、跨项目/版本冲突、独立参数、成员读取 |
| T07 | `D:\小说写作\xuanqiong-wenshu\backend\app\services\test_agent_context_plan.py:35-218` | 关系化上下文/计划、作用域、数据库约束；168 行起直接验证摘要篡改和 ORM 不可变约束 |
| T08 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_write_executor.py:216-245`；`D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_write_executor_member_access.py:246-370` | 写 handler 身份漂移；Editor 接受 Owner 候选、Viewer 和非成员边界 |
| T09 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_tool_adapters.py:601-660` | timeout、协作取消、预取消、审批身份 |
| T10 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_provider_runtime.py:22-166`；`D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_catalog_contract.py:17-29` | 配置批次原子性、重复 Provider/工具、不启用时不导入、catalog 基线 |
| T11 | `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_agent_artifact_lifecycle_smoke.py`；`D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_catalog_relational.py:37-171` | Artifact 生命周期与关系化快照/迁移合同；不等于 planner 自主效果测评 |

## 3. 逐项要求 → 实现 → 测试覆盖 / 证据不足

“已有实现”表示当前代码接线存在；“部分满足”表示明确边界或证据尚未闭合；“需求口径待确认”不是额外凑出的修复项。

| 要求 | 当前实现位置 | 测试覆盖 / 证据不足 | 判定 |
|---|---|---|---|
| 工具注册包含 schema、权限、风险、审批、幂等、取消、超时、context bindings | E03、E04 `register/build_tool_manifest`；绑定参数须在 input properties 声明 | T01、T10 验证元数据和 catalog 基线，T06 检查声明不一致 | 已有实现 |
| schema 参与实际输入/输出执行校验，而非仅供展示 | E04:69-118,173-180,235,267；E09:410-417 在投影后验参 | T01 字符范围及 T03 release 参数校验有断言；E04 与 E06 是两套有限关键字实现，不应表述为完整 JSON Schema 标准引擎，也未见两套语义全量一致性证明 | 当前声明的基础约束已接线；完整标准/统一性证据不足 |
| 冻结 generation、manifest/provider 版本、handler、权限、流式、幂等与 binding | E05 ToolRelease / CatalogRelease；E07:745-778；E04:274-291 | T02、T03 校验快照和漂移；这些字段并非只有文档描述 | 已有实现 |
| 单独冻结 input_schema_digest / output_schema_digest | E05 存完整 schema 并纳入整体 release SHA256；E04 逐字段规范 JSON 对比完整 schema | 未发现这两个独立字段；整体摘要+完整比较提供内容约束，但与 E01 字段字面要求不完全相同 | 等价内容约束已实现；是否要求独立展示字段属需求口径，不据此单列 bug |
| snapshot 绑定 project/session/run/user 与上下文摘要 | E07:779-826；E15 关系化 run/session/project；E14 上下文 digest | T07、T11 验证事实关联；执行期发现损坏的处理存在 F03，不得用持久化成功替代执行期完整性 | 部分满足，F03 |
| 旧 Run 用旧 snapshot、新 Run 用新 catalog；provider/handler/manifest 漂移有确定结果 | E04:379-428，default registry generation 不同即阻断；E04:606-614 禁止运行中热切配置 | T02:115 `test_run_bound_registry_rejects_active_generation_drift` 明确期待阻断。E01:4262 的“旧 Run 继续使用旧 snapshot”若含继续执行旧 handler，则与后续 E01:4450-4452 及代码冲突 | 当前是“不漂移，旧 Run 阻断”，不是多版本 handler 并存；需求口径待确认 |
| resolver 对少/多/重复/未知工具、顺序有确定行为 | E05:276-292 排序/去重约束；E06 解析过滤；E09:204-213,284-294 按关系化选择集约束最终计划 | T02、T03 覆盖多个维度；未见逐项经真实执行入口验证“损坏 resolution JSON”完整矩阵。legacy 无 resolver 明确保持兼容 | 创建/过滤证据较强，执行入口畸形快照全矩阵不足 |
| Viewer 只读、Editor/Owner/Admin 对应写、非成员隔离；projectless 私有 | E03:65-80；E04:182-236,452-464；E12:140-142；E07 创建时按 live role 解析 | T02 live 降权与 projectless；T08 合法成员接受和拒绝边界。写路径区分实际 actor 与事实 owner，后续修复须保留 | 已有实现；完整写入口漂移闸门另见 F01 |
| ContextRef/ContextSnapshot 绑定来自 Run，而非 UI 当前选择 | E09:228-239,296-305；E10:85-132；E09:410-417 | T06 验证冲突、跨项目和参数独立。绑定确来自持久化 JSON；新关系化 snapshot 核验失败仍继续 JSON 路径，见 F03 | 部分满足 |
| 所有实际工具执行统一核验 frozen handler/provider/schema/版本 | 读规划 E09:229 使用 bound；E17 历史读恢复也绑定；审批 E11:116-126 直接调用 default；E13 仅二次核验能力与 handler 身份 | T02 直接验证 bound；T08 检出 handler 替换，但未覆盖审批入口同 handler 的 generation/provider/schema/binding 漂移；探针 P01/P02 | 部分满足，F01 |
| Planner 根据工具能力生成可验证计划；显式用户工具不触发 Provider | E08:46-73,93-202,215-233：至多八步、不重复、依赖仅向前；项目作用域/参数冲突检查 | T04 fixture 验证。提示仅给属性名称，未给完整类型/required/enum/binding 元数据；尚缺不同自然语言目标下选对工具、参数准确率和失败归因效果证据 | 有界规划已实现；自主选择效果证据不足 |
| 独立工具参数、用户值优先、前置依赖得到正确调度 | E09:390-429,551-622；E10 独立投影，planner 绑定字段猜测被 E08 阻断 | T05 参数与“前置已失败”阻断有覆盖；“前置等待审批”与失败被同一分支处理，探针 P03 | 部分满足，F02 |
| 支持工具结果驱动的自主调整，不伪装完整成功 | E09:812-1025：仅自动计划、首次失败、无审批、无 legacy 参数、未重规划时调用一次；新计划仅新增 read/suggest 工具；接收摘要而非原始输出 | T05:505-647 明确断言三个工具调用序列、原失败保留、revision/job/event，属有效行为证据；FakePlanner 预设选择不证明真实模型改善结果。成功步骤之后并不持续自动重规划，也无通用结果→下步参数引用 | 有界失败重规划已实现；不是通用自主闭环 |
| 审批、幂等、cancel/timeout、stream 延续既有合同 | E04:214-267；E09 checkpoint key、审批分支；E12、E13 审批/步骤 lease 与事实幂等；E03 流式需协作取消 | T01、T08、T09、T11 有针对性断言；未见“审批后继续依赖链+取消恢复”完整矩阵，F02；manifest 的 supports_stream 不等于 registry 返回异步迭代器，实际写流由 writer 发布事件 | 基础合同已有；复合编排证据不足 |
| 任一不匹配稳定错误并落审计；不静默改用当前同名工具 | E11:63-76 为 409 / AGENT_TOOL_CONTRACT_CONFLICT；E16 worker 记录 run_failed/error_type；E13 记录 handler mismatch 失败事实 | 错误映射已存在，但 F01 未进入全合同闸门、F03 吞完整性异常；各漂移类型的路由+审计矩阵不完整 | 部分满足，F01/F03 |
| actor/owner、snapshot generation、tool、correlation/transaction 可溯源 | E12:141-142,184-195；E15 执行事实引用 Run 与 snapshot；E07:779 correlation/transaction | 身份和 snapshot 关系可联查；不是每条事件均直接重复全部字段。T08 与 T11 支持部分链路，不凭日志条数推断全链路覆盖 | 已有事实链；统一审计投影完整矩阵不足 |
| fresh/upgrade 后 UI-005 创建与读取可用，且效果结论独立于测试总数 | E07 新 Run 关系化创建；E02 当前迁移/隔离 acceptance 状态；T11 关系化迁移用例 | 本次没有执行迁移或新 smoke；当前总门禁待主代理收取。真实 Provider smoke 脚本存在不等于已执行或已证明效果 | 本次仅核对源码与既有状态，不新增验收通过结论 |

## 4. 最多三项下一修复：Evidence → Finding → Path

以下恰为三项。优先级是下一轮工程排序，不是已发生数据损坏、权限泄漏或模型效果下降的断言。**当前冻结期不执行修复，不启动回归；待主代理确认全量自然终态和解冻后依序处理。**

### F01 / P1：审批执行缺少与读路径一致的完整 Run 契约闸门

- **Evidence**：E11:116-126 读取 approval 后直接 `DEFAULT_TOOL_REGISTRY.execute`，未载入该 approval 的 Run release 并调用完整 bound 校验；E13:107-128 的二次闸门只检查 capability 可选及 handler identity。E04:379-401 才实现 generation/provider 比对，E04:404-421 实现 manifest/schema/binding 比对。
- **Finding**：旧 Run 的待执行审批在部署换代后，若保留同一个 handler identity 而 generation/provider 版本或兼容性未破坏当前参数的 schema/binding 发生变化，审批路径仍可能按当前 manifest 进入处理器。不能把 T08 的“handler 换名被检出”等同于所有契约漂移均被检出。
- **纯内存实测 P01/P02**：旧 generation=3、当前=4 时，实际 `RunBoundToolRegistry.assert_compatible` 报 generation 冲突；抽取的实际审批路由 helper 仍调用 default registry 替身并拿到 artifact；实际 `begin_write_execution` 在相同 handler identity 下仍返回执行事实。此实测证明控制入口差异，不证明真实写入已发生；handler/数据库/Provider 在探针中均为内存替身。
- **Path / 复现入口**：E11 `_execute_registered_approval` → E04 `AgentToolRegistry.execute` → E12 写处理器 → E13 `begin_write_execution`。用 T08 的同 handler fixture，在建 Run 后仅改变 generation，再走实际审批路由；保持请求参数满足新旧 schema。当前预期缺少契约冲突；修复后必须在 handler/Provider/Artifact 副作用前得到稳定冲突。
- **修复动作**：让审批执行按 approval.run_id 载入并验证 frozen release/resolution，复用完整契约验证而非只比较 handler；**合同一致性验证与 actor/owner 校验分开**。E04 当前 bound 会要求 execution user 等于 snapshot user，直接照搬可能破坏 T08 合法 Editor 处理 Owner 候选的场景，应保留项目成员实时权限及独立 actor/owner 语义。
- **新增回归与反向验证**：实际审批入口参数化覆盖 generation、provider/version、manifest/input/output schema、context binding 漂移和未知 capability；断言处理器零调用、无新增 Artifact/版本、冲突可审计；保留无漂移成功、合法成员及旧 Run 明确兼容样例。独立进程中撤掉新合同闸门，上述漂移回归应失败。当前没有执行这些新增用例。

### F02 / P1：前置等待审批时，下游依赖被错误标成失败且无自动审批续跑闭环

- **Evidence**：E09:550 初始化仅含已完成步骤的集合；571-586 把任何未完成依赖写成 `DependencyNotCompleted`；602-622 只为写步骤创建 approval 后继续遍历。E12:299-312 写成功后暂停至 candidate_ready/quality_blocked 并返回，没有为原计划后续依赖创建续跑 job。
- **Finding**：合法 PlanDraft“chapter.generate → statistics.project，第二步 depends_on=[1]”中，第一步等待审批而非失败，第二步已被记为失败。T05:444 的前置真实失败场景应继续保持阻断，但不覆盖审批等待语义。该问题属于步骤调度，不评价生成正文质量。
- **纯内存实测 P03**：抽取 E09 的完整现有步骤 for 循环，给定第一步 write、第二步 read/depends_on=[1]，运行结果为第一步 awaiting_approval、第二步 failed/DependencyNotCompleted，approval_count=1。未执行任何真实工具。
- **Path / 复现入口**：以已有项目和选中章节 ContextRef 建 Run，FakePlanner 返回上述两步；实际 worker 首轮应停在审批边界，下游应保持待执行。现有循环会立即产生 `plan_step_failed`。审批通过后的完整 worker 续跑验证留待解冻，不能用本次循环探针冒充。
- **修复动作**：明确区分 failed/cancelled 的依赖和 awaiting_approval/running/pending 的依赖；后者保持阻塞待执行而非终态失败。审批的成功/拒绝/失败分别触发持久化 continuation 或确定性终止；续跑复用原步骤、参数、PlanRevision 和幂等键。此方案不引入自动接受候选，也不改变单独接受审批。
- **新增回归与反向验证**：写→读等待审批不失败；批准后只续跑一次；拒绝后下游不执行；前置实际失败仍保留失败证据；双 worker/重启不重复写。独立进程撤回等待态区分或 continuation 入队，分别让等待与续跑用例失败。若产品明确只支持“先读后写且写为末步”，则应在 planner 验证时明确拒绝该依赖形态；现状允许计划却在等待时记失败，不是已声明的能力边界。

### F03 / P1：新 Run 的关系化 ContextSnapshot 完整性失败被静默降级

- **Evidence**：E09:132-143 无 snapshot key 返回 None；有 key 但找不到记录/身份不符也返回 None；`verify_snapshot` 抛 `AgentContextIntegrityError` 同样返回 None。调用方 E09:279-283 未区分这些结果，随后 E09:296-305 使用 Run JSON 的 ContextRef 继续解析和规划。T07:168-205 证明底层摘要校验会报错，但没有证明执行入口保留该错误。
- **Finding**：明确携带新关系化 snapshot key 的 Run，在发现摘要损坏时获得与真实旧 Run 无 snapshot 的相同控制结果。这违反 E01:4234,4240 的新 Run 完整性核验和失败关闭要求。不是宣称 ORM 支持任意正常写坏事实；T07 的 ORM 不可变保护真实存在，缺口是已发现损坏/恢复异常时的执行处理。
- **纯内存实测 P04**：抽取原函数，让内存 ContextService 返回同 user/session 的 snapshot 并在核验时抛摘要不匹配；返回值为 None，与 legacy_no_key 完全相同。异常未传播。
- **Path / 复现入口**：E09 `_relational_context_snapshot` → 新 Run worker。用 T07 的已有新 Run fixture，替换 service.verify_snapshot 为抛同类完整性错误；监测 planner、工具 handler 和后续作业均未启动。当前 wrapper 吞异常；修复后应明确失败并落稳定错误事实。
- **修复动作**：仅对确属旧版本、无关系化快照声明的 Run 保留 legacy 分支；对新 Run 的缺记录、错误 user/session/run 绑定及摘要不符显式报错，维持 context 失败类型到 worker/audit 的投影。不要通过删除 snapshot key 或跳过验证让运行恢复成功。
- **新增回归与反向验证**：legacy 无 key 兼容、新 snapshot 正常、bad digest、missing row、跨 session/user/run 分别验证；断言新 Run 错误时 planner/工具/Provider 零调用。独立进程恢复 `except AgentContextIntegrityError: return None`，新 Run 完整性回归应失败。此处不审查小说内容选择或质量评分。

## 5. 自主编排效果：已有证据具体证明什么

1. **不是空壳**：T04 验证结构化计划进入执行模型；T05 的重规划用例断言原失败步骤保留、补充工具确被调用、revision/job/event 持久化，因此“存在受控失败重规划”有行为证据。
2. **不是效果验收**：T05 使用 FakePlanner 和工具替身，预设“失败后选 statistics.project”，不检验真实模型是否在不同任务下做正确选择；`expected_result` 未驱动结果符合性判断。
3. **覆盖不等于闭环**：Planner 按工具名禁止重复，参数按工具名聚合；一轮投影发生在执行前。当前没有通用成功输出引用、动态发现 Artifact 后自动补参数、按目标达成情况继续规划的合同。不能从生成与接受分开成功推导自主“生成→判断→接受”已经完成；接受保留人工确认是当前明确行为。
4. **真实请求保持禁止**：`D:\小说写作\xuanqiong-wenshu\backend\scripts\real_asgi_agent_planner_provider_smoke.py` 是可读取的现有脚本，本次没有导入或运行。脚本存在不构成本次效果证据；E02 也明确本地 fixture 不能代替真实内容质量评估。
5. **完成口径**：UI-005 的声明/快照/基础读执行可分别确认存在；自主编排应保留“有界、部分闭环、真实目标效果证据不足”的限定。后续效果评估应围绕预期工具、参数、依赖、失败保留及目标结果逐项判断，而不是总测试数；本文不另外开出第四项修复。

## 6. 可复现内存探针与实测输出

### 6.1 执行方式和限制

以下为本次探针的等价合并版，仅使用 Python 标准库。以标准输入运行，解释器路径为 `D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe`，参数 `-B -`；不需要落盘脚本。AST 仅抽取指名的原函数/类和现有步骤循环，替换的只有外部依赖；不导入 app，不启动测试运行器，不访问文件数据库或网络。行号/结构变化时应重新核对源码，本次基线循环为 E09:551。

```python
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
from collections.abc import Mapping

ROOT = Path(r'D:\小说写作\xuanqiong-wenshu')

def tree(relative):
    return ast.parse((ROOT / relative).read_text(encoding='utf-8-sig'))

def load(nodes, env):
    future = ast.ImportFrom(module='__future__',
                            names=[ast.alias(name='annotations')], level=0)
    module = ast.Module(body=[future, *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<UI005-AST>', 'exec'), env)

class Violation(ValueError):
    pass

class LiveRegistry:
    def __init__(self):
        self.calls = []
    async def execute(self, name, **kwargs):
        self.calls.append(name)
        return {'artifact': 'in-memory-artifact'}

live = LiveRegistry()
env = {'Mapping': Mapping, 'json': json, 'ToolContractViolation': Violation,
       'DEFAULT_TOOL_REGISTRY': live,
       'get_default_tool_registry_snapshot': lambda: {'generation': 4, 'tools': []}}
constants = {'_RUN_BOUND_MANIFEST_FIELDS', '_RUN_BOUND_PROVIDER_FIELDS'}
load([n for n in tree('backend/app/agent/registry.py').body
      if getattr(n, 'name', '') in {'RunBoundToolRegistry', '_contract_equal'}
      or (isinstance(n, ast.Assign) and any(
          isinstance(t, ast.Name) and t.id in constants for t in n.targets))], env)
context = {
    'capability_resolution': {'tools': [{'name': 'chapter.generate'}],
                             'request': {'user_id': 1, 'project_id': 'p'}},
    'catalog_release': {'generation': 3, 'tools': [
        {'name': 'chapter.generate', 'handler_identity': 'fixture:writer'}]}}
try:
    env['RunBoundToolRegistry'].from_context(live, context).assert_compatible()
    bound = 'accepted'
except Violation as exc:
    bound = str(exc)

class RouteRuntime:
    async def get_approval(self, **kwargs):
        return NS(id='a', tool_name='chapter.generate', project_id='p',
                  request_json={'chapter_number': 1}, run_id='r')

env.update(AgentRuntimeService=lambda session: RouteRuntime(), AgentConflict=Violation)
load([n for n in tree('backend/app/api/routers/agent.py').body
      if getattr(n, 'name', '') == '_execute_registered_approval'], env)
result = asyncio.run(env['_execute_registered_approval'](
    approval_id='a', session=None, user_id=1))
print(json.dumps({'probe': 'P01', 'bound_check': bound,
                  'route_result': result, 'live_calls': live.calls}))

service = next(n for n in tree('backend/app/services/agent_execution_service.py').body
               if getattr(n, 'name', '') == 'AgentExecutionService')
load([n for n in service.body
      if getattr(n, 'name', '') == 'begin_write_execution'], env)
class Repo:
    async def get_capability_for_snapshot(self, **kwargs):
        return NS(handler_identity='fixture:writer',
                  provider_version='old', manifest_version='old')
class Facts:
    repository = Repo()
    async def get_run_snapshot(self, run_id):
        return NS(catalog_generation=3)
    async def begin_read_execution(self, **kwargs):
        return 'in-memory-execution-fact'
result = asyncio.run(env['begin_write_execution'](
    Facts(), run=NS(id='r'), approval=NS(id='a', tool_name='chapter.generate'),
    step=None, arguments={}, lease_generation=0,
    actual_handler_identity='fixture:writer'))
print(json.dumps({'probe': 'P02', 'result': result}))

execution = tree('backend/app/agent/execution.py')
function = next(n for n in execution.body
                if getattr(n, 'name', '') == 'execute_agent_execution_job')
loop = next(n for n in ast.walk(function)
            if isinstance(n, ast.For) and n.lineno == 551)
wrapper = ast.parse('async def dependency_probe():\n    pass\n').body[0]
wrapper.body = [loop]
load([wrapper], env)
class Runtime:
    def __init__(self):
        self.steps = {}
    async def is_cancel_requested(self, **kwargs):
        return False
    async def ensure_step(self, **kwargs):
        step = NS(id=str(kwargs['step_order']), status='pending',
                  input_json=kwargs['input_payload'])
        self.steps[step.id] = step
        return step
    async def request_approval(self, **kwargs):
        return NS(id='a', tool_name=kwargs['tool_name'])
    async def append_event(self, **kwargs):
        pass
    async def fail_step(self, **kwargs):
        step = self.steps[kwargs['step_id']]
        step.status, step.error_type = 'failed', kwargs['error_type']
class Session:
    async def commit(self):
        pass
runtime = Runtime()
steps = [NS(tool_name='chapter.generate', depends_on=[], risk_level=NS(value='write')),
         NS(tool_name='statistics.project', depends_on=[1], risk_level=NS(value='read'))]
env.update(runtime=runtime, session=Session(), run=NS(id='r', user_id=1, project_id='p'),
           plan=NS(steps=steps), replan_offset=0, cancel_event=NS(is_set=lambda: False),
           projected_tool_arguments={'chapter.generate': {'chapter_number': 1},
                                     'statistics.project': {}},
           goal='generate then inspect statistics',
           resolved_context=NS(canonical_refs=lambda: []), completed_step_orders=set(),
           failed_steps=[], approvals=[], results=[],
           _dict=lambda value: value if isinstance(value, dict) else {})
asyncio.run(env['dependency_probe']())
print(json.dumps({'probe': 'P03', 'steps': [
    {'id': s.id, 'status': s.status, 'error_type': getattr(s, 'error_type', None)}
    for s in runtime.steps.values()], 'approval_count': len(env['approvals'])}))

class IntegrityError(ValueError):
    pass
class Context:
    async def get_run_snapshot(self, **kwargs):
        return NS(session_id='s', user_id=1)
    async def verify_snapshot(self, snapshot):
        raise IntegrityError('context snapshot digest mismatch')
env['AgentContextIntegrityError'] = IntegrityError
load([n for n in execution.body
      if getattr(n, 'name', '') == '_relational_context_snapshot'], env)
async def context_probe():
    values = {}
    for name, ctx in [('legacy_no_key', {}),
                      ('new_run_bad_digest', {'relational_context_snapshot_key': 'ctx-new'})]:
        values[name] = await env['_relational_context_snapshot'](
            context_service=Context(), run=NS(id='r', session_id='s', user_id=1),
            context=ctx)
    return values
print(json.dumps({'probe': 'P04', 'results': asyncio.run(context_probe())}))
```

### 6.2 本次实际输出（探针标签归一化）

```json
{"probe":"P01","bound_check":"tool registry generation differs from the Run capability snapshot","route_result":"in-memory-artifact","live_calls":["chapter.generate"]}
{"probe":"P02","result":"in-memory-execution-fact"}
{"probe":"P03","steps":[{"id":"1","status":"awaiting_approval","error_type":null},{"id":"2","status":"failed","error_type":"DependencyNotCompleted"}],"approval_count":1}
{"probe":"P04","results":{"legacy_no_key":null,"new_run_bad_digest":null}}
```

探针进程均正常退出。P01 路由和 P02 关系化二次闸门分别隔离验证，不冒充真实全栈事务；P03 只证明现有步骤循环的等待态误分类；P04 只证明现有 wrapper 吞异常。完整副作用、HTTP 错误映射、审批 continuation 和 worker 零调用断言均明确留待新增回归。

## 7. 读取基线指纹与交付约束

以下 SHA256 为本次读取文件内容计算，记录的是工作树而非仅 HEAD。它们便于解冻后确认复现对象；本次没有写入主代理的 fingerprint/gates/status 文件。

| 证据文件 | SHA256 |
|---|---|
| E04 registry | `23FF2BA28A4CC1158E2BE002066A8F41D09D7F99F6E6E3FA38F720B4E2548016` |
| E08 orchestrator | `1F0E27101438A913931106BDA105F95A3F22B4B16C15D4DF0A3DC1FD4D8B7A3B` |
| E09 execution | `FBFE3F3772A0D43C8A6A0FC6B05E343D0791339A92744B4FBF93A12D03004298` |
| E10 context_refs | `31896DA95243739CBAC72724FA488A86C72A15E9CD6F111533EDE796DECC5CDB` |
| E07 agent_runtime | `7F7513F48E5CCAB894B7B5BD425DBA913C89DE038EE3259ADDD221101133509D` |
| E13 agent_execution_service | `D825EF1D8790C8273DD2432837CD54292567ED0B39D65D6CB2BD45776B833EA3` |
| E11 agent router | `E240CD9CAB5B46811CA8657CAC96A4B5E25D8FE7E424BD1AC8DE057A750911A8` |
| E12 write_executor | `025EB6858FB566E02C5F07DCF87C8EF5F87BFDE680664E7E2EE3E35F18750867` |
| T02 capability fence | `B33B823E4355085F31550A3724048C04784DDDC23DC5CDE0D1EBB38F6BAC3EF0` |
| T05 worker | `DE22472A1AC73C5F3B228C4833B0E3C283EEB9D8C0DEB13B5B7AB408C04C42B2` |
| T07 context plan | `AEF3EEBD48AC04180D928F1541D289A5A1A7D88AA3040777C953998A7EB5CBF0` |

交付检查：需求逐项对应当前实现及测试证据；恰列三个经内存探针支撑的下一修复；没有按测试数宣称自主编排效果；没有修改任何源码/测试、运行产物或其他报告；没有创建新 task；没有启动 pytest、服务、浏览器或外部 Provider 请求。源码修复、真实回归和反向验证均未执行，继续遵守当前全量冻结。