# UI005 F5 内容摘要修复交付报告

日期：2026-09-07。状态：**F5 helper、独立测试、正常 conftest 定向绿灯及进程内反向验证完成。**

## 1. 写集

本批新增：

- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\approval_snapshot_integrity.py`
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_snapshot_integrity.py`
- `D:\小说写作\xuanqiong-wenshu\docs\reports\UI005_CONTENT_DIGEST_FIX_20260907.md`
- `D:\小说写作\xuanqiong-wenshu\logs\` 下 F5 原始输出、反向脚本及清单。

未修改 `execution.py`、`api/routers/agent.py`、`test_approval_run_contract.py`、registry 或测试阈值。F3 与 F5 集成仍由主代理负责。本批未运行全量，也未修改业务数据。

实施依据：`D:\小说写作\xuanqiong-wenshu\docs\reports\UI005_CONTEXT_DIGEST_IMPLEMENTATION_PLAN_20260907.md`。

## 2. 接口与行为

实现接口：

```python
def validate_approval_snapshot_integrity(*, run, snapshot, catalog_release) -> None:
    ...
```

异常：`ApprovalSnapshotIntegrityError(field)`。`field` 通过异常属性返回；message 固定为 `approval snapshot integrity mismatch`，不包含 payload、摘要、用户输入或资源内容。成功返回 `None`。

实现是同步纯 helper：不访问数据库，不读取 live registry，不重建历史 Catalog，不修改输入对象。调用方负责现代 Run/legacy 判定，并将该异常转换为既有 `ApprovalRunContractError`。

## 3. 校验内容

### Catalog

对 `schema_version`、`catalog_id`、`generation`、`providers`、`tools` 五个 canonical 字段计算 SHA-256。canonical 规则为 `ensure_ascii=False`、`sort_keys=True`、`separators=(",", ":")`、`allow_nan=False`；不把 `digest` 或 `release_id` 自身纳入摘要材料。

校验内容包括：摘要为 64 位小写 hex，`release_id == catalog_id + ":" + digest[:16]`，providers/tools 的容器、字段类型、排序和唯一性，完整持久化 Catalog row 字段，以及 row `manifest_json` 与 Run JSON 副本的 canonical 等价性。list/tuple JSON 往返被视为同一内容。

### Resolver

对 `resolver_schema_version`、`release_id`、`release_digest`、`generation`、`request`、`tools`、`exclusions` 七个字段重算摘要；ID 规则为 `resolver-v{schema}:{digest[:16]}`。

校验 resolver 对 Catalog 的 release_id/release_digest/generation 引用，request 的用户/项目/角色及数组类型，resolver tools 与 Catalog 同名 tool 的逐项 canonical 相等，tools 与 exclusions 的顺序和唯一性，NaN/Infinity/set/任意对象等不可 canonical 值。

request.user_id 与 request.project_id 必须等于 Run 的 user_id/project_id，防止仅同步修改 request 和 digest 后改变执行主体。

### 关系 snapshot 与 Run projection

校验关系快照：

- `run_id/user_id/project_id/transaction_id` 与 Run 一致；
- `catalog_release_id` 与 Catalog row ID 一致；
- generation、resolver schema、resolved_version、digest、release_digest 一致；
- `snapshot_id == resolver_snapshot_id + ":run:" + run.id`；
- request、selected capability IDs、exclusions 与 resolver 一致；
- `resolved_scope_json.resolver_snapshot_id/release_id/tool_names` 与 resolver 一致；
- Run context 中 Catalog/Resolver ID、关系 row ID/key/digest 与验证后的内容一致。

缺少 payload/关系字段、类型错误、旧 digest、旧 ID、关系漂移均抛结构化 field。helper 不做 F3 的 ContextRef 资源存在性和权限检查。

## 4. 正向证据

正常仓库 runner 命令：

```powershell
$env:PYTHONUTF8='1'
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -X utf8 -B -m pytest -q --tb=short app/agent/test_approval_snapshot_integrity.py
```

该命令保留项目 `backend/conftest.py`，未使用 `--noconftest`。结果：

- 实现前：`60 failed, 6 passed in 5.98s`，失败来自应拒绝的 digest/ID/关系变异；
- 实现后：`66 passed in 4.21s`；最终反向后正常 runner 复验：`66 passed in 3.51s`，exit=0；
- 未运行后端全量；该结果仅是 F5 独立文件的正常 conftest 定向门禁。

测试使用真实 `build_catalog_release`、`resolve_capabilities` 和真实 Runtime/ORM roundtrip。测试还将 live registry snapshot/builder 临时替换为抛错，确认 helper 不读取 live registry。另有 project-scoped 与 projectless Runtime 正例、tuple/list 及 key-order 正例。

## 5. 进程内反向证据

反向驱动：

`D:\小说写作\xuanqiong-wenshu\logs\ui005-f5-reverse-v2-20260907.py`

最终 v2 驱动由 pytest collection hook 在原 conftest 完成加载后操作，只对选定函数进行 AST 变异和编译，保留原 ApprovalSnapshotIntegrityError 类身份；不重新执行整个模块，不写回 helper/test。运行时保留正常项目 conftest、原配置与插件，仅使用 `-B` 避免 pyc。每次变异结束校验磁盘 helper SHA-256 未改变。

最终三组反向结果：

|内存变异|预期失败结果|证明|
|---|---:|---|
|让 `_digest` 保留格式检查但信任 stored，不重算内容|5 failed, 61 deselected|Catalog tools/providers 与 resolver request/tools/exclusions 的旧摘要会被回归测试捕获|
|移除 `snapshot.selected_capability_ids_json` 关系比较|1 failed, 65 deselected|关系 selected 列表漂移会被捕获|
|将 resolver request user/project 与 Run 的比较改为自比|2 failed, 64 deselected|同步改 request 与 digest 仍不能改变执行主体|

三组退出码均为1。digest组：1项 `DID NOT RAISE`，4项结构化 field 不再是期望 digest 字段的断言失败（下游关系检查仍有拦截）；selected组1项与actor组2项均为 `DID NOT RAISE`。这些是保留异常类身份后的真实契约断言失败，不是导入、fixture、异常类不一致或 anchor 错误。最终日志显示 `exception_identity_preserved=True` 和 `SOURCE_SHA256_UNCHANGED`。磁盘源码始终保持正常实现。

首版驱动重新执行整个模块，导致异常类身份重建；相关旧日志只保留为历史记录，**不作为有效反向交付依据**。最终以v2的5/1/2项红灯和最终正常66项绿灯为准。

## 6. 证据文件

已写入 `D:\小说写作\xuanqiong-wenshu\logs\`：

- `ui005-f5-red-normal-20260907.stdout.log` / `.stderr.log`
- `ui005-f5-green-normal-20260907.stdout.log` / `.stderr.log`
- `ui005-f5-final-normal-20260907.stdout.log` / `.stderr.log`
- `ui005-f5-reverse-v2-20260907.py`
- `ui005-f5-reverse-v2-digest-20260907.stdout.log` / `.stderr.log`
- `ui005-f5-reverse-v2-selected-20260907.stdout.log` / `.stderr.log`
- `ui005-f5-reverse-v2-actor-20260907.stdout.log` / `.stderr.log`
- `ui005-f5-evidence-manifest-20260907.json`

最终清单记录命令、退出码、原始日志文件名、源码 SHA-256 与证据文件 SHA-256；旧v1反向显式标为不可用于最终验收。原始红灯/绿灯 stdout 由实际运行结果直接归档；没有根据报告数字重建日志。

## 7. 边界与后续交接

摘要重算用于发现冻结内容被修改后未同步的 digest/ID/关系副本；它不是防止拥有全部持久化写权限的一方同步修改内容并重算摘要的独立信任根。

F3 真实 session 快照定位/verify、current-vs-frozen refs、`resolve_agent_context_refs` 和 approved argument projection 由主代理负责。F5 helper 已将所需三对象校验集中到一个同步边界，主代理接线时不应从 live registry 重建冻结内容，也不应把含自身 digest/ID 的完整 JSON 再次 hash。

**交接状态：F5 有界实现完成，helper/test 源码可冻结；主代理继续 F3/F5 集成及正常后端全量。**

## 8. 直接复跑与集成注意事项

```powershell
$env:PYTHONUTF8='1'
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu\backend'
& '.\.venv\Scripts\python.exe' -X utf8 -B -m pytest -q --tb=short app/agent/test_approval_snapshot_integrity.py
& '.\.venv\Scripts\python.exe' -X utf8 -B '..\logs\ui005-f5-reverse-v2-20260907.py' digest
& '.\.venv\Scripts\python.exe' -X utf8 -B '..\logs\ui005-f5-reverse-v2-20260907.py' selected
& '.\.venv\Scripts\python.exe' -X utf8 -B '..\logs\ui005-f5-reverse-v2-20260907.py' actor
```

正向预期exit=0；反向分别5/1/2项回归断言失败，各自exit=1。集成方捕获 ApprovalSnapshotIntegrityError 并用 .field 转为 ApprovalRunContractError；legacy 分流保留在调用方。本批未接入路由，不把66项正向当作F3/F5最终组合或全量完成。旧关系单测中的假摘要应由集成方换成真实builder材料，或明确只测内容校验之前的关系层，不降低helper标准。

## 9. 冻结后只读复核：schema 支持版本闸门

按主代理本轮要求，只读复核并记录，**本项暂保留，不修改 helper/test，不重复组合或全量**。

已核对事实（下列文件均位于 D:\小说写作\xuanqiong-wenshu\backend\app\agent）：

- catalog_release.py:19 的 CATALOG_RELEASE_SCHEMA_VERSION=1，build_catalog_release 在415行写入该版本；CatalogRelease 构造在277-278行仅要求版本正数。
- capability_resolver.py:19 的 RESOLVER_SCHEMA_VERSION=1，resolve_capabilities 在242行写入该版本；快照构造在155-156行同样仅要求正数。
- approval_snapshot_integrity.py:228、243 对两类 schema 只做正整数类型检查；22-24行的摘要材料字段与后续结构校验是固定合同，没有按版本分派。版本数参与 digest/ID 及 row 一致性校验，但不存在 supported-version allowlist。

判断：**内容一致性校验并不等于支持该 schema 的语义。** 一个携带未知正整数版本、仍采用现有字段结构且摘要/ID/关系副本全部一致的对象，有可能通过当前 helper；此为静态控制流判断，本次未运行新探针。普通 Runtime 当前只产生版本1，所以未证实正常版本1路径存在新增故障；也未证明系统支持未来版本语义。

若未来版本增加新的摘要材料或改变字段含义，固定字段抽取会继续按当前规则解释；尤其未知版本新增的顶层语义字段未必进入当前材料集合。因此建议在引入新 schema 或接受外部导入/跨版本快照前，明确 supported catalog/resolver version 集合，并在读取材料之前按版本拒绝或分派到对应解析器。不要把“版本是正整数”作为未来兼容承诺，也不要自动回退到版本1解释未知版本。

下一批若采用版本闸门，最小回归应包括：版本1真实 Runtime 正例；未知正整数版本且重新计算正确摘要/ID/关系的负例（排除仅因旧digest失败）；bool/0/负数负例；若正式支持多版本则逐版本冻结材料正例。当前无明确多版本兼容需求，主代理要求本批先保留并记录；这是显式待决合同，不冒充已修复。

主代理回传：F5已接入真实API structural validator之后、bind registry之前，8条真实route负例已取得红灯；F3独立helper27项通过，6文件组合正在运行。本代理未代验该运行状态，不将回传进度标为本次实测门禁。

冻结核对：helper SHA-256 = 26c668822a4490965cfc176dc0865a36955df508f045654e528f5d047f378755；独立测试 SHA-256 = 7078306a911645e8cacf2c7f68b702d87233ee70335cda724cfd6b6b0c0bfb47，与F5最终证据一致。源码/测试冻结交付，本次仅追加此说明。
## 10. 最终 F5 集成与正常门禁交接

主代理已将 F5 helper 接入真实审批 API：位于既有 structural validator 之后、`bind_run_tool_registry` 之前；`ApprovalSnapshotIntegrityError.field` 转换为既有 `ApprovalRunContractError`。本代理未修改 helper/test 源码，仅记录接线结果。

最终正常定向组合日志：`D:\小说写作\xuanqiong-wenshu\logs\ui005-stage6-final-targeted.log`。

- **190 passed**：87 项既有审批/registry 组合 + 29 项 F3 + 8 项真实 route 负例 + 66 项 F5。
- 该结果由主代理的正常仓库 runner 取得；不使用本代理早期隔离内存 runner 数字替代正常门禁。
- F5 组合已覆盖真实 API 接线后的错误转换和 handler 前置拒绝边界。

真实 API 反向日志：`D:\小说写作\xuanqiong-wenshu\logs\ui005-stage6-digest-route-mutation-20260907.log`。

- 在实际 API 接线中取消 F5 helper 调用；5 项回归均以 `DID NOT RAISE` 失败。
- 该结果证明 route 级测试能够识别 helper 接线缺失，不是仅验证纯函数自身。
- 本代理没有重跑该日志，仅按主代理回传记录并纳入交接证据。

**阶段状态：F5 纯 helper、独立测试、正常 API 集成、route 反向和最终 190 项正常组合均已交接；后端源码与测试冻结，主代理进入后端全量。**