# UI005 前端只读 Job 公共投影审查

日期：2026-09-07
范围：仅审查并修改前端公共 Job 投影消费；未修改 backend、数据库、Worker 或 API 服务实现。

## 1. 审查对象

- `frontend/src/api/agent.ts`
- `frontend/src/features/agent/data/AgentDataPanel.vue`
- `frontend/src/features/agent/composables/useAgentProjectGovernanceData.ts`
- `frontend/src/views/AgentWorkspace.vue`
- 对应 API、数据面板和工作台 Vitest。

后端公共投影当前提供以下 Job 字段：

- `terminal_status`：终态状态，当前允许 `completed`、`succeeded`、`failed`、`cancelled`、`dead_letter` 或空值。
- `recovery_status`：当前允许 `not_recorded`、`continuation_completed`、`failure_reconciled`。
- `result_json`：只读安全白名单；当前允许自绑定的 `visible_response_job_id`，以及续跑标志 `continuation_completed`、`pending_approval`、`continuation_acknowledged`。

## 2. 审查结论

### 已发现的问题

1. `AgentJob` 原先只把 `result_json` 声明为宽泛的 `Record<string, unknown>`，没有表达公共投影的白名单字段。
2. `AgentJob` 没有声明 `terminal_status` 和 `recovery_status`，前端缺少这两个服务端字段的类型约束与消费提示。
3. `AgentStateProjection.jobs` 使用重复的窄内联类型，遗漏终态、恢复状态和结果字段的类型声明；运行时 GET 没有裁剪响应。
4. `AgentDataPanel` 只显示实时 `status`，没有显示公共终态、续跑完成/失败对账状态或白名单结果标志。
5. 死信面板原先直接渲染 `error_detail`。公共投影会将该字段置空，因此没有可靠的公开摘要，并形成了对私有错误正文的错误依赖。

### 已确认没有问题的链路

- `useAgentProjectGovernanceData.loadJobs()` 直接保存 `AgentAPI.listJobs()` 的公共结果，没有字段裁剪或重建导致的丢失。
- `AgentWorkspace.vue` 将 `jobs` 和 `deadLetters` 原样传给 `AgentDataPanel`，没有覆盖或降级投影字段。
- `cancelJob`、死信重放返回值继续使用同一 `AgentJob` 公共类型。

## 3. 实施内容

### API 类型

在 `frontend/src/api/agent.ts` 新增：

- `AgentJobTerminalStatus`
- `AgentJobRecoveryStatus`
- `AgentJobResult`
- `AgentRunJobProjection`

并将：

- `AgentJob.result_json` 收窄为 `AgentJobResult`；
- `AgentJob` 补充 `terminal_status`、`recovery_status`；
- `AgentStateProjection.jobs` 改用 `AgentRunJobProjection`。

终态和恢复字段保留可选/空值兼容，以覆盖旧响应或历史夹具；这是编译期约束，不是运行时响应净化器；API 请求函数仍原样接收响应，页面明确选择白名单字段展示。

### AgentDataPanel

- Job 条目新增“终态”显示，使用终态字段而不是把实时状态误当成终态。
- Job 条目新增“恢复”显示，仅展示 `continuation_completed` 和 `failure_reconciled` 等公开状态。
- Job 条目新增“结果”摘要，按 Job kind/status 选择白名单，并以固定中文标签显示是/否；保留 false 与缺失字段的区别。
- 未对 `result_json` 做 JSON 整体序列化，因此未知或私有键不会进入页面。
- 死信条目不再渲染 `error_detail`，改为显示公开终态、恢复状态和“无公开结果摘要”。
- 将 `completed` 纳入状态标签和取消按钮终态门禁，避免已结束 Job 仍显示请求取消。
- 可见响应标记必须属于 `visible_response` 且自绑定当前 Job；续跑布尔标记只在 `agent_continuation` 成功结束时展示。
- `pending_approval=true` 仍显示等待后续审批标志，Job 结束不用于改写 Run 状态。

## 4. 测试证据

### 改动前基线

命令：

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run type-check
npx vitest run src/api/agent.spec.ts src/features/agent/data/AgentDataPanel.spec.ts src/features/agent/composables/useAgentProjectGovernanceData.spec.ts
```

结果：

- `npm run type-check`：通过，退出码 0。
- 3 个 Vitest 文件：30/30 passed。
- 测试文件：3 passed。
- Vitest 总耗时：25.16s。

### 改动后定向验证

命令：

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run type-check
npx vitest run src/api/agent.spec.ts src/features/agent/data/AgentDataPanel.spec.ts src/features/agent/composables/useAgentProjectGovernanceData.spec.ts src/views/AgentWorkspace.spec.ts
```

结果：

- `npm run type-check`：通过，退出码 0。
- 4 个 Vitest 文件：4 passed。
- 75/75 tests passed。
- Agent API：23 项通过。
- AgentDataPanel：17 项通过。
- `useAgentProjectGovernanceData`：4 项通过。
- AgentWorkspace：31 项通过。
- Vitest 总耗时：9.40s。
- `git diff --check`：通过；仅出现既有仓库的换行符提示，没有空白错误。

新增覆盖：

1. API 公共 Job 投影保留 `terminal_status`、`recovery_status` 和白名单 `result_json`。
2. AgentDataPanel 展示续跑终态、恢复状态和固定结果标签。
3. AgentDataPanel 不渲染结果中的私有未知键。
4. 死信面板展示失败对账状态，不渲染 `error_detail`。
5. AgentWorkspace 真实挂载数据面板后仍能看到续跑状态和结果标签，证明工作台传递链路没有丢字段。

### 补充边界覆盖与反向验证

- 白名单 false、空结果、字段缺省、非布尔值、错误 kind/status、自绑定与不匹配 ID。
- `completed/succeeded/failed/cancelled/dead_letter` 五类终态取消按钮门禁。
- GET 死信读取和 Run state 嵌套 Job 字段保留、只发起读取请求、等待审批 Run 不被成功 Job 改写。
- 未模拟提交候选、执行审批、Run 恢复等写动作；组件只读挂载时没有 emit。

反向验证采用**临时修改组件文件 → 独立 Vitest → finally 恢复原字节**，并非纯内存 patch。每次变异期间没有并行启动正常门禁；源码检查未发现竞争修改。

| 变异 | 真实业务断言失败 | 同批其余通过 | 退出码 |
|---|---:|---:|---:|
| 隐藏普通 Job 终态显示 | 2 | 15 | 1 |
| 移除续跑结果摘要 | 2 | 15 | 1 |
| 从取消按钮终态门禁移除 completed | 1 | 16 | 1 |
| 死信恢复显示 error_detail | 1 | 16 | 1 |

四类变异均产生 `AssertionError`，不是导入或编译错误。`4/4` 检出，组件原字节恢复一致；SHA-256：`71a5c7c8a258917fe724c3364956eb8528ce142f416c2b14672763a44ac8bd1e`。

早期驱动曾遇到 npx 启动路径、控制台编码和脚本语法错误；这些轮次不计为有效变异证据。上述结果来自最后完整运行，执行器改用已定位 Node 和本地 Vitest 入口。

### 变异恢复后的门禁

- `npm run type-check`：退出码 0。
- `npm run build-only`：退出码 0，4918 modules，23.19s。
- `npm run test:run`：退出码 0；81 个测试文件通过，615/615 项通过，95.32s。
- 非阻断提示：Browserslist/baseline-browser-mapping 数据陈旧；部分既有工作台夹具有 Pinia injection 提示。本批未更新依赖或隐藏警告。

## 5. 文件变更

本批实际修改/新增：

- `frontend/src/api/agent.ts`
- `frontend/src/api/agent.spec.ts`
- `frontend/src/features/agent/data/AgentDataPanel.vue`
- `frontend/src/features/agent/data/AgentDataPanel.spec.ts`
- `frontend/src/views/AgentWorkspace.spec.ts`
- `docs/reports/UI005_FRONTEND_JOB_PROJECTION_READONLY_AUDIT_20260907.md`

未修改：

- `frontend/src/views/AgentWorkspace.vue`
- `frontend/src/features/agent/composables/useAgentProjectGovernanceData.ts`
- 所有 `backend` 文件。

## 6. 验收判断

本批定向门禁通过，覆盖类型、API 字段保留、数据面板展示、工作台挂载和私有字段不误显示。这里的工作台挂载是 Vitest/jsdom；本批未执行真实浏览器验收。

这只证明前端公共 Job 投影消费闭环，不等同于 backend continuation 全量门禁、整体发布门禁或文学质量收益已经通过。
