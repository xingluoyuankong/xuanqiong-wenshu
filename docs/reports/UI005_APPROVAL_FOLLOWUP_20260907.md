# UI005 审批链路只读深审跟进报告

审计日期：2026-09-07（本任务指定的本地日期）。项目：D:\小说写作\xuanqiong-wenshu。

## 结论与范围

**审批契约尚未闭环。最优先修复：现代 Run 缺 snapshot 降级、审批漏接 RunBound registry、审批未校验真实 context_refs。** 同时确认 provider 空关系与内容 digest 重算缺口。

只新增本文件，未修改源码、测试、配置及业务数据；保留原有未提交改动。未运行全量、前端、迁移或外部服务。PowerShell 使用 login:false；Python 使用 PYTHONUTF8=1、-B。用户要求尽快进入实现阶段，本次审查至此结束。

以下代号对应完整路径，行号基于本次读取的未提交工作区：

|代号|完整路径|
|---|---|
|EX|D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py|
|API|D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py|
|REG|D:\小说写作\xuanqiong-wenshu\backend\app\agent\registry.py|
|TEST|D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_run_contract.py|
|FENCE|D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_execution_capability_fence.py|
|UIREG|D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_registry_ui005_contract.py|
|REPO|D:\小说写作\xuanqiong-wenshu\backend\app\repositories\agent_catalog_repository.py|
|FACT|D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_execution_service.py|
|RUNTIME|D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_runtime.py|
|REF|D:\小说写作\xuanqiong-wenshu\backend\app\agent\context_refs.py|
|CTX|D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_context_service.py|
|RELEASE|D:\小说写作\xuanqiong-wenshu\backend\app\agent\catalog_release.py|
|RESOLVER|D:\小说写作\xuanqiong-wenshu\backend\app\agent\capability_resolver.py|
|WRITE|D:\小说写作\xuanqiong-wenshu\backend\app\agent\write_executor.py|

## F1 / P1：snapshot=None 对现代 Run 无条件放行

**位置：EX:62-63；API:129-147、158-176；FACT:107-109。**

判断：validator 尚未读取 context、尚未校验 approval/run/step，就因 snapshot=None 返回。审批入口随后照常调用默认 registry。begin_write_execution 也对缺 snapshot 返回 None，未在下游恢复现代关系要求。

复现条件：保留 Run 的 relational_capability_snapshot_id/key/digest、relational_catalog_release_id、capability_resolution，仅让关系快照缺失。函数 AST 探针返回 ACCEPT None；真实内存 ORM 删除该 Run 的 snapshot 后，原审批入口与真实默认 registry 进入 sentinel handler 一次。此为数据缺失后的完整性问题，未证明普通用户能通过 API 删除 snapshot。

最小修复：早退前显式区分真 legacy 与现代 Run。任一现代关系标识或可靠契约版本存在而 snapshot 缺失，抛 ApprovalRunContractError(field="snapshot")；仅确认为旧 Run 的无现代关系状态保留兼容。FACT 同步采用同一判定，避免旁路调用再次降级。现代创建标识见 RUNTIME:773-789、822-827。

新增测试：test_modern_run_missing_snapshot_rejected_before_registry，参数化各现代标识单独保留、snapshot 查询为空；断言结构化错误、handler=0、execution/artifact 无新增。保留 TEST:197-202 真 legacy 正例。反向变异：恢复无条件 return None 后新负例必须失败。

## F2 / P1：审批入口没有接入 RunBoundToolRegistry.assert_compatible

**位置：API:158-176；EX:168-173；REG:379-428、441-473。**

判断：审批 validator 只对比运行时 handler identity、input schema；入口直接 DEFAULT_TOOL_REGISTRY.execute。活动 generation/provider 与完整冻结 manifest 校验位于 assert_compatible，但该路径未调用。

真实 ORM + 真实默认 registry 实测：

1. 冻结 Run 保持不变，仅让 get_default_tool_registry_snapshot 返回 generation+1，仍进入 handler 一次。
2. 仅将 chapter.generate 的 live manifest 用 model_copy(update={"context_bindings": ()}) 替换，仍进入 handler 一次。
3. 相同数据前置 RunBoundToolRegistry.from_context(DEFAULT_TOOL_REGISTRY, run.context_json).assert_compatible()，两项分别因 generation differs、context_bindings 漂移失败，handler 均为零；正常对照仍通过。

最小修复：关系与内容验证后绑定 Run registry，显式 assert_compatible，再通过绑定对象 execute。REG:451 的 execute 只执行 _manifest，若 wrapper 跨 await/长期复用，应在实际执行边界再次检查活动目录。wrapper 没有 get_handler_identity 代理，勿未经适配直接替换 validator 参数；可以先用底层 registry 验关系，再绑定执行。

新增测试：审批 helper + 真实 DEFAULT/RunBound registry + 只替换叶子 handler，分别覆盖 live generation、provider version、context_bindings、输出 schema/权限字段漂移。provider 用实际带 provider 的能力。断言异常发生于 handler 和 execution fact 之前。反向变异：恢复 API 直接 DEFAULT execute 后组合负例必须失败。

## F3 / P1：审批校验人工 context_bindings，而非真实 context_refs

**位置：EX:174-195；API:158-167；REF:67-102、238-299；CTX:183-197。**

判断：validator 的 session 参数未使用，API 也未传 session。它从 run.context_json["context_bindings"] 读取来源值，来源不存在就 continue；未解析 context_refs，未验证关系化 context snapshot。真实创建的 Run 实测不含顶层 context_bindings，而 TEST:39 人工添加该字段。生产引用解析存在于 Planner（EX:463-472），不是本审批入口。

复现：真实 Run 的批准参数 chapter_number=1；将 context_refs 设置为同项目 selected chapter 99，context_bindings={}。审批 helper 经真实 registry 进入 handler 一次。对同一 project/章节99调用真实 resolve_agent_context_refs，则抛 ContextRefValidationError，消息为 chapter context reference is unavailable for this project。

最小修复：API 传 session，严格校验该 Run 冻结的关系化 context snapshot（身份、scope、snapshot/ref digest），以真实 refs 调用 resolve_agent_context_refs；按冻结 tool manifest 使用 ResolvedAgentContext.project_arguments 验证已批准参数，不静默重写。EX:292-310 的 context snapshot 校验失败返回 None 是宽松 fallback，不适合作为现代审批严格验证器。

语义校准：REF:90-96 允许无上下文值但有显式参数，即便 binding.required=True。缺陷不是“所有缺 source 都必须拒绝”，而是没有从真实 refs 求值。必须保留无选中 refs + 合法显式参数正例，并区分来源不存在与来源值 None。

新增测试：refs 章节12/批准章节99冲突；版本归属错误；artifact 跨项目；引用资源删除；context/ref digest 改动；无选中 refs 但显式参数合法；None 值兼容。负例 handler=0、事实无新增。反向变异：改回仅检查 context_bindings 后 refs 负例应失败。

## F4 / P2：provider-less 分支漏检非空 provider_release_id

**位置：EX:140-167；API:148-157；REPO:88-94。**

判断：provider_release=None 时只看冻结 tool 的 provider_id/version 是否为空，未同时要求 capability.provider_release_id 为空。API 查询带 catalog_release_id 过滤，悬空或跨目录关系可能被折叠成 None。

实测：chapter.generate 在真实目录中 provider_id=None，是合法 provider-less 正例，不能统一要求其必须有 provider。将该 capability.provider_release_id 设为 missing-provider，查询返回 None，真实审批入口仍进入 handler 一次。函数探针也接受相同非空 FK/空关系组合。

边界：测试内存 SQLite 默认未开启 FK，真正悬空 ID 在启用 FK 的环境可能由数据库挡住；生产应用仍应验证 FK 合法但指向异 catalog 的组合，不能将本结果夸大为外部可达写入。

最小修复：provider-less 必须同时满足冻结 provider_id/version 空、capability FK 空、provider_release 空；只要 FK 非空而行缺失就报错。有 provider 时继续检查三方身份，并补 provider row 版本与 provider manifest 自身版本对照；当前版本比较针对 tool 版本。

新增测试：真实 provider-less 正例；provider-required 缺行；provider-less+非空失效 FK；FK 指向实际存在的另一 catalog provider（开启 FK）；provider manifest/tool/row 版本不一致。反向变异：移除非空 FK 检查后新负例失败。

## F5 / P1：digest 只验证副本相等，未重算内容

**位置：EX:106-124；RELEASE:277-307；RESOLVER:154-180；REPO:145-167、176-188。**

判断：catalog row.digest、Run release.digest、snapshot.release_digest、snapshot.digest 与 context digest 是相等检查，manifest_json 也只是与 Run 副本相等。resolver request/tools/exclusions 及关系快照相关内容与 digest 没有重新绑定。

真实入口实测：

- 将 run.context_json.capability_resolution.tools 改为 []，保留原 digest/ID 和关系 selected 集合，仍进入 handler。
- 深拷贝 catalog.manifest_json，修改一个 tool.description，同步修改 Run release 副本但保留旧 digest/release_id，仍进入 handler。

函数层还接受 snapshot.request_json 变化与 selected 集合清空。但后者在真实 API 的 REPO:179-180 已有 selected membership 拦截，故它不是已证明的 route 绕过；route 结论以以上两项为准。

最小修复：复用 canonical payload，勿 hash 包含自身 digest 的完整 JSON。catalog 材料为 schema_version/catalog_id/generation/providers/tools，重算 hash 及内容 ID；resolver 材料为 resolver_schema_version/release_id/release_digest/generation/request/tools/exclusions，重算 digest 与 resolver ID。再验证关系 snapshot 的 request、selected、exclusions、scope 与已验证 resolver 内容一致。持久化 snapshot_id 带 :run:{run.id} 后缀（REPO:141-165），不同于 resolver 原始 ID，需分别验证。复用现有排序及序列化规则，避免 tuple/list 往返误报。

新增测试：真实 builder 构造合法初值，分别修改 request/tools/exclusions、catalog tool/provider 内容但保留 digest；加入合法 canonical 往返正例。现有 fixture 的 release-digest/snapshot-digest 任意字符串应替换为真实计算值。反向变异：去掉重算后负例失败。摘要是完整性证据，不是防止全库写入者同步重算全部摘要的信任锚。

## F6 / P2：route 与 registry 测试存在组合覆盖空白

- TEST:283-332 使用真实 ORM，但 301-312 把整个 DEFAULT_TOOL_REGISTRY 换成 RegistryStub。它证明辅助入口调用 stub，不证明真实 registry 的权限、schema、输出验证或 RunBound 接线。
- TEST:337-380 的漂移负例同样使用 stub，只验证部分身份/digest 字符串不同。它们未覆盖内容重算、真实 refs、活动目录漂移。
- TEST:314-331 的 execution 数量前后都是0在该测试内成立，但 stub 从未调用真实 write executor；这不是完整写执行事实的单次/幂等证据。
- TEST:268-278 人工将 catalog.manifest_json 回填 Run。额外内存 AST 对照删除回填语句后，两者在当前代码下已经相等，validator 也通过；本次未证实回填掩盖当前必现问题。建议移除这种“测试先修状态”的动作，以直接 assert 创建结果替代。
- TEST:143-153 名称称 rejects_missing_binding，实际删 source 后 assert 成功；154-163 的失败是参数绑定缺失，不是真实 schema 类型约束。fixture schema 只有 type:object。
- FENCE:99-126 用真实默认 registry 和 assert_compatible 测 provider/generation，确实有针对性；88-96 也真实检验 manifest 漂移。不是假测试，但没有组合进审批入口。
- UIREG:142-164 名称含 timeout_and_cancel，实际只测 timeout，未传 cancel_event；sleep(1) 与 timeout=1 同边界也脆弱。应拆开取消测试，采用可控阻塞 Event 与 finally 清理。
- API:1259-1265 的 HTTP wrapper 未被 TEST 私有 helper 测试经过，不等价于 HTTP 认证、状态映射、响应校验完成。

最小补测：真实 helper+真实 registry，mock 降至叶子 handler；新增 HTTP 结构化409映射；真实 write executor 的 execution/artifact 单次与重试幂等（仅 mock 业务 LLM）；真实 input_schema 的类型/required/additionalProperties。先添加原实现会失败的 F1-F5 用例，再实施修复。

## 实测记录与可信边界

1. AST 读取原始 validator、_validate_schema 与既有 _fixture，在内存执行；不导入应用初始化。基线 ACCEPT；现代缺 snapshot ACCEPT；provider 空关系/FK非空 ACCEPT；resolution.tools=[] ACCEPT；snapshot.request_json 变化 ACCEPT；真实 refs 不一致 ACCEPT。对照：单改 snapshot.digest → REJECT snapshot.digest；provider-required 缺行 → REJECT provider_release；人工 bound=12/参数99 → REJECT context_binding.chapter_number。
2. 三个现有测试文件 TEST/FENCE/UIREG：**48 passed, 1 warning in 9.19s，pytest exit=0**。未跑全量。运行器禁用 conftest 自动加载、插件自动发现、cacheprovider、logging 与文件捕获，显式 pytest_asyncio、等价内存 task_session；所有引擎转为 sqlite+aiosqlite:///:memory:，保留现有 conftest 的依赖轻量 stub。这是隔离基建下定向结果，不是原生产环境完整测试结果。
3. ORM 集成探针使用现有 _route_fixture；原始 helper、默认 registry.execute、输入 schema 与项目权限仍真实运行。仅以 functools.wraps(original_handler) 的 sentinel 替换叶子 handler，保持 module:qualname identity，返回 artifact=SimpleNamespace(id="sentinel")。正常、缺 snapshot、provider坏FK、resolver内容、catalog内容、refs漂移、generation漂移、live bindings漂移各自都进入 handler 一次。每项使用新内存 DB，结束恢复 registry 变更。
4. 对照前置真实 assert_compatible：正常仍进入，generation/live bindings 两项拒绝，handler=0。真实 ContextRef resolver 对不可用章节99拒绝。未经人工回填的 Run：catalog 副本相等、validator ACCEPT、无顶层 context_bindings、chapter.generate provider_id=None。
5. Python audit hook 拦截文件写、目录变更、外部进程及网络；只允许 asyncio 内部 socketpair。初次 AST 因缺 lineno 失败，经 fix_missing_locations 修正；初次基建分别因 platform 子进程、pytest 捕获临时文件、socketpair 被拦截，调整运行器后48项完成。这些不记为产品失败。
6. 一次额外去回填探针工具超时，未形成有效证据；随后检查未见 python.exe -B - 遗留进程。改为只调用 validator 的有时限探针后获得第4条有效结果。首次报告写入命令因嵌套 here-string 解析错误失败，未创建文件；本次最终写入使用单层 here-string。
7. 不宣称业务 LLM、实际 Artifact 落库、HTTP E2E、并发审批、全量测试完成。WRITE:134 有审批状态检查、153 有 step claim、184-189 创建执行事实；本次未把前置完整性问题夸大为所有下游防线都不存在。

## 精确复现步骤（供实现轮复用）

- 函数层：AST 提取 EX 的 ApprovalRunContractError/_approval_contract_mismatch/validate_approval_run_contract、REG 的 ToolContractViolation/_validate_schema、TEST 的 _fixture；保留原函数体，使用 ast.fix_missing_locations。registry 仅返回 identity=handler:v1 与 input_schema={type:object}。每例新建 fixture，单独执行上述变异并 await validator，记录具体 field。
- 路由层：在内存 SQLite 初始化真实 Base metadata；调用 TEST:205-279 _route_fixture；真实 DEFAULT 的叶子 handler 替换为 wraps sentinel；单次变异并 commit，调用 API:119 _execute_registered_approval，记录 handler 调用数。不要用 RegistryStub 替换真实 execute。
- generation：只变活动快照获取函数返回的 generation+1。bindings：仅替换 _tools[name] 中的 manifest.context_bindings=()。对照：在 helper 前调用真实 bound.assert_compatible，原应接受的基线继续接受，漂移应拒绝。
- 缺 snapshot：仅删除本内存 Run 的 snapshot，保留现代 context。provider：provider-less 能力的 FK 非空，provider 查询为空。resolver：context.resolution.tools=[]而关系 selected 保留。catalog：深拷贝 manifest，修改 description并同步Run副本，旧digest保持不动。
- refs：同项目 selected chapter99与批准chapter1不一致、顶层bindings空；比较 helper 与真实 resolve_agent_context_refs 结果。不要把缺source且合法显式参数当作必然负例。

## 源码基线及实施验收

读取时记录的 SHA-256（未提交工作区）：

|文件|SHA-256|
|---|---|
|EX|3e2bfc6749e0c1e1842b53bbf1cf3796dc04746baec5acba356f02c03e72e8ef|
|API|186815e58406209739724e0a19c9be0c2d31e08ad2b3d0c35d1dba811eaea335|
|REG|23ff2ba28a4cc1158e2be002066a8f41d09d7f99f6e6e3fa38f720b4e2548016|
|TEST|38bb023016750d202f618ec0ddb196d7e433d0faca11a82ff26a571456b25f63|
|UIREG|ad31ae4053f09104ed09b967b705bb1ad2bd3994d9faa1e5f125d468ec6021cc|

下一轮优先 F1/F2/F3，再补 F4/F5 与 F6 组合测试。每项修复必须有原实现失败、修复通过、撤掉修复后再次失败的证据。本轮没有实施源码修复，因此不把这些新增测试及修复反向变异说成已完成；已完成的是原实现异常输入探针与真实 assert 的对照。

**交接状态：只读审查结束；报告已形成，主代理接续实现。**