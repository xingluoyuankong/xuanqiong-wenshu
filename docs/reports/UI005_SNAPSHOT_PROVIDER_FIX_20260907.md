# UI005 F1/F4 有界修复交付

日期：2026-09-07（任务本地日期）。状态：**实现完成，定向绿灯与有效内存反向验证完成，可交接后端全量冻结。**

## 1. 写集与排除项

本代理只写以下三个文件：

- D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py：仅 validate_approval_run_contract 函数。
- D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_snapshot_provider_integrity.py：独立新增测试。
- D:\小说写作\xuanqiong-wenshu\docs\reports\UI005_SNAPSHOT_PROVIDER_FIX_20260907.md：本报告。

未修改 registry.py、api/routers/agent.py、既有 test_approval_run_contract.py。实施期间主代理已经更新 F2 与旧 factory，本批在这些当前修改上完成定向组合验证；这些文件相对开工时有变化，不归因于本代理。已有未提交成果与业务数据保留，未 reset、迁移、运行全量或新建任务。

不处理 F3 真实引用、不处理 F5 内容完整性重算；不修改 FACT 的 begin_write_execution 旁路，当前修复边界严格是指定 validator。F2 由主代理独立交付。

## 2. 精确实现

源码绝对路径：D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py。

|位置|改动|错误 field|
|---|---|---|
|62-75|先读取 Run context；snapshot 缺失时，只要存在实际 Runtime 发出的现代标识就拒绝，键值为 None 也算现代痕迹|snapshot|
|160-163|provider-less 且查不到 provider row 时，要求 capability.provider_release_id 严格为 None；非空、空字符串均拒绝|capability.provider_release_id|
|178|现有 row 对冻结 tool 的版本检查之外，补 row.provider_version 对 provider manifest.provider_version 的一致性|provider.manifest_provider_version|

现代标识来自当前 AgentRuntimeService.create_run 的实际输出，不引入新的协议版本字段：catalog_release、capability_resolution、catalog_release_id、capability_resolution_id、relational_catalog_release_id、relational_capability_snapshot_id/key/digest、relational_context_snapshot_id/key。

没有现代标识的真实 legacy Run 继续兼容；只有旧 capability_snapshot 不被当成新增现代判据。本实现不是“键值 truthy”判断，避免损坏的 None 值再次引发降级。没有声称能仅凭完全删除全部现代标识后的 JSON 区分历史来源。

provider-less 的正常 None FK 仍通过。有 provider 的原 FK、catalog、tool/provider identity、row/tool version 检查仍保留。此次不是全盘要求内置工具都有 provider。

## 3. 新测试的真实性与覆盖

测试文件：D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_snapshot_provider_integrity.py，共 **32 项**。

|测试组|数量|真实执行边界|
|---|---:|---|
|现代 Run 删除 snapshot，context 全保留|1|真实 ORM 删除、原审批 helper、真实默认/RunBound registry|
|10 个 Runtime 标识分别只保留该键，值为原值或 None|20|每例先真实 create_run，断言 Runtime 确有此键，再注入损坏状态|
|legacy / provider-less / provider-backed 正例|3|真实批准记录、权限/schema/registry，叶子 handler 调用一次|
|provider-less dangling / 空字符串 / other-catalog FK|3|真实查询 provider 与真实 helper|
|provider-less 错连同目录存在的 provider|1|保留现有 provider identity 拦截|
|provider-required FK 清空|1|保留现有 provider_release 拒绝|
|row 版本与 frozen tool 不同|1|保留现有 provider.provider_version 拒绝|
|row/tool 一致但 provider manifest 版本不同或 None|2|新增 provider.manifest_provider_version 拒绝|

所有负例检查结构化 code/field、叶子调用为零，以及 AgentCapabilityExecution/AgentArtifactRef 前后计数为零。这里的“零事实”是配合真实 registry 边界验证，不宣称已运行真实业务生成。

独立 factory 使用真实 User/NovelProject/AgentRuntimeService 创建 session、Run、step、approval 并批准；不调用依赖旧签名的 _route_fixture，也不人工回填 catalog JSON。创建后直接 assert Runtime catalog 与持久化 manifest 一致、snapshot digest 与 Runtime 标识一致。

legacy 正例直接持久化旧形态 AgentRun 后使用真实 Runtime 创建审批，不把现代 Run 清空字段后冒充创建来源。叶子 handler 用 wraps 保留原 identity，registry.execute、绑定校验、输入 schema、项目访问检查不替换。

Provider-backed 用例仅在内存调整真实 built-in project-read provider 的工具归属，让真实 Runtime/builders 生成 chapter.generate 的 provider release 及 resolver。版本关系用例在原始 snapshot.providers 中注入版本差异后交由真实 builder/Runtime 生成全套 catalog/resolver/hash；随后只改变实际 provider row 版本以重现 row/tool 一致、row/provider manifest 不一致。没有伪造 digest、release_id 或 manually repaired Run context。

### Other-catalog 与 SQLite FK

该用例位于测试文件 187-215 行：

1. 在创建业务 fixture 前执行 PRAGMA foreign_keys=ON，并断言值为1。
2. deepcopy 原始 get_default_tool_registry_snapshot，修改 generation，再调用 build_catalog_release；**不对构造完毕的哈希对象调用 replace**。
3. 断言第二份 release 的 digest/release_id 与第一份不同，通过真实 repository 持久化。
4. 查询并确认目标 AgentProviderRelease 存在，且 catalog_id 不同，再将 capability FK 指向该真实行。
5. commit 后再次断言 foreign_keys=1、PRAGMA foreign_key_check 返回空；数据库合法 FK 仍被应用 catalog predicate 排除，validator 正确拒绝。

另两个 dangling/空字符串用例明确模拟关闭 FK 或历史损坏数据，未冒充 FK 开启时的合法写入。other-catalog 是本批实际完成的 FK 集成范围。

## 4. 红—绿—反向—恢复证据

|阶段|结果|含义|
|---|---|---|
|修改实现前独立测试|26 failed, 6 passed；26.27s；exit=1|26个失败均是应抛 ApprovalRunContractError 而未抛，不是夹具/导入错误|
|只改指定函数后|32 passed；23.77s；exit=0|三处实现修复生效|
|最终 canonical/FK 夹具后|32 passed；23.91s；exit=0|用户指出的 fixture 要求已落地|
|撤掉 snapshot guard|1 failed, 31 deselected；4.02s；exit=1|test_modern_missing_snapshot_rejected_at_real_route 识别降级回退|
|撤掉非空 provider FK guard|3 failed, 29 deselected；6.79s；exit=1|包含真正 FK 开启的 other-catalog 负例|
|撤掉 row/provider manifest 版本比较|2 failed, 30 deselected；2.06s；exit=1|字符串差异与 None 差异均识别|
|恢复原磁盘实现，五文件组合|**87 passed, 1 warning；42.23s；exit=0**|F1/F4 + F2 + 既有审批/registry 同时通过|

反向方法：从磁盘解析 validator AST，每次只删除一处 guard 或版本比较 tuple，assert 命中计数恰为1；编译到独立进程内 namespace，替换 execution_module 与 router_module 指向的校验函数，再运行原测试。失败原因均为 DID NOT RAISE，而非把函数替换成总抛错、删测试或修改期望。

**磁盘上从未写入变异版本**。每次测试新进程结束即还原；最后组合运行使用磁盘正常实现，所以不存在“测试后忘记恢复”的状态。最终夹具修改后，三组反向均已重跑，不引用旧夹具反向结果充数。

初次红灯夹具在实现前已成功形成26个行为失败；之后按主代理要求将 other-catalog 改为原始 snapshot→builder，并启用 FK。最终版本又以相同实现检查点做有效反向，补足最终夹具的回退证据。

## 5. 定向组合清单及运行方式

最终仅运行以下五个文件，未运行全量：

- D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_snapshot_provider_integrity.py
- D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_registry_boundary.py
- D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_run_contract.py
- D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_execution_capability_fence.py
- D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_registry_ui005_contract.py

为不影响数据，复用先前内存运行器：Python -B、PYTHONUTF8=1、PYTHONDONTWRITEBYTECODE=1；用真实 metadata 创建 SQLite :memory: 数据库；pytest 禁用 conftest 自动加载、自动插件发现、cacheprovider、logging 与文件捕获，显式启用 pytest_asyncio 及等价 task_session。仅应用原 conftest 的轻量 dependency stub，应用默认 engine 也转为内存，避免导入触碰磁盘 DB。

审计 hook 拦截文件写、目录改动、外部进程及外连，允许 asyncio 内部 socketpair；测试脚本和输出留在内存，不新增脚本/缓存文件。唯一 warning 为 pytest_asyncio 预导入导致的 assertion rewrite 提示，不是测试失败。以上是隔离基建下的真实模块定向结果，非生产全栈运行证明。

全量由主代理冻结后执行；本批没有代跑全量，也未为测试绕开真实 registry 与 ORM。后续 F3/F5 仍未关闭。

## 6. 交付检查

- 对比开工时 execution.py，在移除 validator 文本后，其余文件内容完全一致，确认实现改动仅发生在指定函数。
- 保留主代理的 F2 及旧 factory 更新；独立 factory 不受 requested_tools 可选参数变化影响。
- 不动其他代理前端写集；不新增会话、审批或提权操作。
- 最终测试、三个 mutation 及实现均已交付；本报告落盘后即可结束本批并冻结后端验证。
