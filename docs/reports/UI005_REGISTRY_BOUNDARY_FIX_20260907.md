# UI005 Run-bound审批执行边界修复 — 本地2026-09-07

## 结论

审批入口原来只运行关系validator后直接调用DEFAULT registry，漏掉已有RunBoundToolRegistry的完整运行合同。已在审批执行前绑定Run registry，并在绑定对象execute入口重验live release。正常路径保留真实registry的scope、角色、输入/输出schema验证；负例在叶子handler之前终止。

本批7个新增真实registry用例与既有validator/fence/UI005组合共55项通过（14.32s），两个进程内反向验证分别检出5个、1个预期`DID NOT RAISE`。不将此写成整个UI005闭环：真实context_refs与摘要内容重算仍待下一批。

## Evidence → Finding → Path

| 证据 | 发现 | 修复 |
|---|---|---|
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-registry-boundary-before-r3-20260907.log` | 1正常用例通过；generation、context_bindings、output_schema、allowed_project_roles、真实provider版本漂移及绑定后generation漂移6个负例全部因没有抛异常失败 | 审批调用bind_run_tool_registry；RunBound.execute再次assert_compatible |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-registry-boundary-after-r3-20260907.log` | 55通过 | 既有原阈值、无跳过 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-registry-route-mutation-20260907.log` | 只取消路由绑定，5个负例全部DID NOT RAISE | 证明真实路由接线受回归保护，不只是validator单测 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui005-registry-dispatch-mutation-20260907.log` | 只取消绑定对象execute重验，1个负例DID NOT RAISE | 证明跨绑定/执行时点的live generation检查 |

早期测试构造曾替换叶子函数而未保留module/qualname，触发handler identity不一致；该轮不是有效业务反向证据。已用functools.wraps保留叶子身份，正常对照通过，再取before-r3作为有效先红证据。第一次PowerShell换行替换未命中CRLF，随后断言唯一替换点并实际修正；中间日志保留。

## 文件与范围

- `D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py`：审批validator之后以run.context_json绑定registry，再调用其execute。
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\registry.py`：RunBoundToolRegistry.execute开始时assert_compatible，保留单工具membership和execution owner/project检查。
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_registry_boundary.py`：新增7项，真实ORM/Runtime/DEFAULT/RunBound registry，仅替换昂贵叶子handler。
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_approval_run_contract.py`：factory支持requested_tools，删除人工catalog回填；正常route test用真实registry叶子替换，不再以SimpleNamespace manifest规避完整合同。

provider漂移使用真实provider-backed `project.context`，通过真实Run创建时requested_tools同时纳入它和chapter.generate；没有把provider-less chapter.generate假称为默认Provider能力。

## 反向验证机制

脚本：`D:\小说写作\xuanqiong-wenshu\logs\ui005-registry-memory-mutation-20260907.py`。

- route模式临时替换API模块的bind函数为identity；真实DEFAULT registry仍保留，因此只有缺失的Run绑定产生差异。
- dispatch模式从真实execute源码生成内存函数，仅去掉assert_compatible调用；没有修改磁盘源码。
- finally恢复原函数；核验API与registry文件SHA256不变；要求精确5/1个call阶段预期失败、无collect/setup/teardown错误，且失败必须包含DID NOT RAISE。
- 驱动exit0表示变异被正确检出；变异pytest本身为exit1。JSON同目录保存逐条失败与指纹。

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu'
$env:PYTHONUTF8 = '1'
& 'D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe' -B 'D:\小说写作\xuanqiong-wenshu\logs\ui005-registry-memory-mutation-20260907.py' route
```

## 剩余边界

1. 新增测试叶子返回fixture artifact；它证明执行边界与阻断位置，不证明LLM生成或完整write-execution生命周期。负例handler=0且本Run capability execution事实无新增。
2. F1现代Run缺snapshot与F4 provider FK修复由独立子智能体负责，需合并后再定向和全量。
3. F3真实context_refs与关系context snapshot严格验证、F5 canonical digest重算仍未实现。RunBound接线不替代它们。
4. 后端源码已变化，阶段三2131通过只是历史基线；当前后端全量待本批冻结后运行。
5. 当前主目标active、发布NO-GO，未动用户数据库、上传与历史成果。
