# UI005 阶段六：真实上下文与摘要接线验证

本地执行日期：2026-09-07（Asia/Shanghai；使用本机日志时间）。

## 当前结论

F3真实上下文helper、F5内容摘要helper已经接入审批API。正常仓库指定测试组合 **190 passed in36.59s**；进程内组合反向3/5/2个预期业务失败全部检出。正确backend工作目录全量已 **2273 passed in956.63s / exit0**，476文件结束指纹一致。阶段五2170不再作为新源码背书。

## 修复位置

- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\approval_context_contract.py`：严格context边界。
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\approval_snapshot_integrity.py`：纯内容摘要/关系投影边界，详细报告见UI005_CONTENT_DIGEST_FIX_20260907.md。
- `D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py`：结构关系→F5摘要→RunBound→F3上下文→RunBound.execute，所有失败在业务叶子之前转换为结构化ApprovalRunContractError。
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py`：保留结构校验；错误消息不再拼接expected/actual完整payload；docstring明确不是单函数代表全部合同。

F3单独helper无session时明确报错；现代Run即使两个context定位均被移除仍拒绝。legacy不带关系snapshot时不强制现代locator，但存在的引用仍经真实解析器验证。API无条件调用此helper，结构validator的隔离单测没有数据库并不意味着实际API可跳过F3。

## F3校验边界

1. context为Mapping、refs为数组、AgentContextRef按strict解析，禁止将数字字符串/布尔值暗中变为章节整数。
2. 当前Run关联snapshot的ID/key、run/session/user/project/correlation/transaction精确匹配；当前支持schema_version严格整数1。
3. 调用AgentContextService.verify_snapshot验证总摘要和逐ref摘要；缺行/错误定位/损坏摘要均拒绝。
4. 比较当前Run用户refs与冻结context JSON用户refs；再比较关系snapshot.refs的用户前缀、ref_order连续性及ref_type/ref_key/ref_version/role派生字段。
5. initial snapshot可追加自动novel_refs，不能把这些自动知识条目全部当作用户选中章节；replan用户refs前缀仍精确验证。
6. 重新调用真实resolve_agent_context_refs检验资源存在、版本所属章节、artifact项目归属；project_arguments只允许得到已经批准的参数，不静默填充/覆盖已批准请求。
7. 异常message/detail只含固定字段名与简短说明，敏感哨兵测试确认不回显引用标识。

**不夸大版本绑定**：当前模型没有在Approval行保存“批准创建时context snapshot版本”。本批验证当前Run绑定的不可变快照，不声称新增了未落库的Approval级旧版本绑定。后续如需求要求固定审批创建版本，需另行持久化设计/迁移和重规划用例。

## Evidence → Finding → Path

| 证据 | 观察 | 对应闭环 |
|---|---|---|
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-context-before-20260907.log` | F3新增18项，15个负例全部DID NOT RAISE，3正例通过 | 真实API缺上下文读取/验证 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-context-strict-before-20260907.log` | 自洽关系补测后，未知schema、字符串章节仍被接受 | 严格schema/ref类型补强 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-context-final-20260907.log` | 29项通过，14.41s | 有效initial/replan/无refs显式参数/同项目artifact、缺资源/错版本/真正跨项目artifact、定位/digest/自洽refs冲突/错误脱敏 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-content-route-before-20260907.log` | 8个内容/关系route负例在接线前失败 | 单独helper通过不代表真实入口受保护 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-f3-f5-integrated-20260907.log` | 中间164项通过 | 后续新增2项真实artifact后再组合 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-stage6-final-targeted.log` | 最终190通过，36.59s | 87既有+29F3+8route+66F5，正常conftest |

初版内联草稿因换行拼接产生SyntaxError，已删除该草稿；后续内联F3还存在无session分支与只看两份JSON的不足，已拆为必经helper并补关系前缀与metadata。中间失败保留，不记作有效反向证据，不降低测试门槛。

## 组合反向验证

驱动：`D:\小说写作\xuanqiong-wenshu\logs\ui005-stage6-composition-mutation-20260907.py`。

| 模式 | 变异 | 结果 |
|---|---|---:|
| context-route | 取消API实际F3调用 | 3个DID NOT RAISE |
| digest-route | 取消API实际F5调用 | 5个DID NOT RAISE |
| context-refs-prefix | 内存编译F3函数，移除关系refs前缀/metadata核验 | 2个DID NOT RAISE |

每轮使用原pytest conftest，collection hook后变异，finally还原函数；异常类身份保持；API/F3/F5三个文件SHA256不变；无collect/setup/teardown故障；要求精确失败数量及DID NOT RAISE。该三组不是“3类F3”：其中digest-route明确是F5组合验证。

对应日志/逐条JSON：`D:\小说写作\xuanqiong-wenshu\logs\ui005-stage6-{mode}-mutation-20260907.log`及同名.json。

## 当前门禁运行说明

阶段六第一次未指定backend工作目录而从仓库根运行pytest，命中了根pytest.ini的backend/app/services测试范围及不同async配置，出现失败。该运行日志`D:\小说写作\xuanqiong-wenshu\logs\backend-full-stage6-20260907.log`必须保留；它不是工程要求的backend目录全量，也不能将其失败全部解释为业务修复回归。自然终态后应读取失败原因，再在明确backend工作目录运行原命令并单独保存日志。

当前源码冻结指纹：`D:\小说写作\xuanqiong-wenshu\logs\backend-stage6-frozen-fingerprint-20260907.json`，476个backend/app Python文件。

## 剩余事项

- 正确backend目录全量2273通过，见 `logs/backend-full-stage6-correct-cwd-20260906.log`；结束指纹 `logs/backend-stage6-verified-fingerprint-20260907.json`（476文件无漂移）。前端本批未改，沿用601门禁。
- 原UI005编排F02等待审批依赖与F03 worker快照降级仍在；下一批按UI005_WORKER_CONTINUATION_PLAN_20260907.md实施。
- 完整API工作台CARD071执行仍待验收；Shell/Rail独立页面不替代。
- 七项文学质量证据、真实双审标签、Docker/MySQL实机仍未闭合，发布NO-GO、目标active。

### 根目录误跑终态纠偏

错误目录运行自然结束为193失败/1191通过/345 warnings，446.16s；读取确认存在async_generator fixture未await与project_ledger_sync_leases缺表错误。`logs/stage6-root-run-failure-classification.json`只统计诊断行，不假称193个独立失败全部归类。该日志保留，不删失败测试；正确backend配置的全量2273随后正常通过。正确全量日志后缀20260906是命名沿用，实际运行时间与本机2026-09-07/verified_at对应。
