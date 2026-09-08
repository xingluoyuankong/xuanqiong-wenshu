# SSE 前端归属隔离与真实浏览器续接 — 2026-09-07

## 状态与边界

本批仅写 frontend，未修改 backend，没有创建新 task，也没有终止 5174 服务。工作区原有未提交改动保留。
本报告只证明本批前端 SSE 场景，不代表完整产品、文学质量或真实后端部署门禁通过。

## 修复

- `src/features/agent/composables/useAgentRunStream.ts`：history/live 归属一致性校验，旧 generation（包括同 Run ID）隔离。
- 兼容规则：**仅当对象省略 run_id 字段时**，将合法 durable envelope 绑定到当前 run-scoped URL 的 Run；显式 null、空字符串、错误类型及错 Run 拒绝。非对象、缺有效正整数 sequence、缺 event_type 也拒绝。无 run_id 的 stream_error 保持旧协议兼容，不推进 durable cursor。
- SSE event type、SSE id 与 payload event_type/sequence 必须一致；错 Run、重复或错 envelope 在 transport 确认游标之前丢弃，防止错 Run 的高序列号污染 Last-Event-ID 或触发终态。
- durable 去重覆盖历史、实时、重连，以当前 Run 的 sequence 而非可变化的 event.id 为身份；用连续前缀及乱序集合保留 gap 修复，顺序 5000 条后重放旧 identity 仍去重。
- `src/utils/sseStream.ts`：新增可选 acceptEvent 前置校验，不改变未配置者默认协议；终态后丢弃同一个网络 chunk 的后续事件，取消仍打开的 reader；关闭后的迟到 fetch/read 不再分发。
- duplicate-only 重连不重置有效事件重试预算，3 次重试后 disconnected。

## 先红后绿与内存反向

1. 首轮真实 transport 缺陷复现：10 failed / 1 passed，保留 `red-business.log`。随后明确“字段省略”与“显式坏值”的兼容边界，最终回归采用更完整的两个测试文件。
2. 同一最终回归套件、Vite 内存加载修复前源码：**16 failed / 2 passed**，见 `mutation-baseline.json`。这些是业务断言失败，不是启动异常。
3. 最终定向：**33/33 passed**（4 文件）。新增 isolation 7、真实 transport integration 11、公共 SSE 新增 1，共新增 19 项。
4. 内存变异：**6/6 检出**；移除归属检查 6 失败、去重 2 失败、generation 1 失败、transport 前置确认 2 失败、reader 终态取消 1 失败、control 归属 1 失败。变异使用 Vite transform，不写共享业务源文件；前后 SHA256 一致。
5. 保留失败尝试说明：初版 Python 变异驱动因路径/进程启动错误未执行测试并恢复源文件；最终替换为 `run-mutations.mjs` 内存驱动。一次 terminalSeen 单点变异被其他防线覆盖而存活，记录于 `mutation-attempt-terminal-survived.json`，不将其计为检出；最终 terminal 变异针对实际 reader 释放。

## 前端门禁

| 命令 | 结果 |
|---|---|
| npm run type-check | exit 0 |
| npm run test:run | **83 文件 / 634 passed / 95.81s / exit 0** |
| npm run build-only | **14.38s / exit 0** |
| 最后补充定向 | **33 passed** |

源码在上述完整门禁后未再改动；`final-source-recheck.json` 校验本批两份业务实现与已测指纹一致。后续只调整独立 E2E runner/config 和展示样式，不修改业务实现。

## 真实浏览器证据

独立 Chromium + Vite HTTP middleware，使用生产 `useAgentRunStream`、`connectSSE`、真实 reducer 和 Vue DOM。服务端用 res.write 持续发送事件，不使用 route.fulfill 模拟长连接、不使用 fake timer、不调用真实 Provider。

- 第一条流：正常事件 1、异 Run terminal 999、重复 1、省略 run_id 的合法事件 2；约 1.2 秒后实际结束 HTTP 流。
- 浏览器自动第二次 fetch：query after_sequence=2，Last-Event-ID=2。
- 第二条流：重复 2、每秒一个后续事件与 heartbeat，持续约 60 秒；随后 terminal 63 和同 chunk 尾随 64，服务端保持流打开，以验证客户端终态主动取消。
- DOM 收到准确序列 1..63、正文片段 1..62、仅 run-a、终态一次；等待超过重试间隔后仍只有两次连接。
- 同 ID 重启再切换 Run B：旧两个 A socket 提前关闭，最终只显示 B 的 [1,2] 和单次终态。
- 一次完整执行在独立端口 43355 **2/2 passed**；两条测试耗时 67389ms、6182ms；HTTP 第二次连接存活 60516ms。
- 后续最终展示修正版使用外层 runner 选择单一空闲端口，最终端口 **29999**，**2/2 passed**，耗时 67382ms / 6150ms，见 `final-sse-results.json`。截图、trace、服务端请求/关闭时间附件均保存。

## 启动调整记录

- 首次动态选端口放在 Playwright config 中，worker 重新加载配置导致重复选择，出现 ERR_CONNECTION_REFUSED；完整失败日志保留。
- 修复：外层 runner 只选一次 port，通过 XQ_SSE_PORT 同时注入 config 和 webServer；strictPort=true、reuseExistingServer=false。不复用、不终止 5174。
- 切换场景服务端终态延迟 5 秒，原断言默认 5 秒出现边界超时；明确断言 15 秒，但仍验证旧 socket 必须在 5 秒前关闭。随后全场景通过。

## 未闭环矩阵（如实保留）

- 新增 SSE fixture 是生产前端 transport/composable/reducer 的真实网络验收，**不是完整 FastAPI/MySQL/Provider 生产栈端到端**。
- 60 秒长连接已证明；小时级 soak、代理/LB idle timeout、HTTP/2、多标签页、离线恢复、非 Chromium 均未证明。
- 既有完整 Agent workspace E2E 尝试 7 项：原 fixture **2 passed / 5 failed**（分页 query 路由遗漏及 API mock/当前 UI 行为漂移）。临时 page-envelope 适配实验 **4 passed / 3 failed**（质量详情需手动加载、死信面板期待、布局消息 fixture）。没有删测试、跳过后宣布全量通过。
- 为不混入无关 fixture 改造，已移除本批对既有 agent-workspace.spec.ts 的包装和额外断言，保留该文件先前改动；实验 helper 移到 `routeAgentFixture.experimental.txt`，失败日志与 trace 保留。**完整工作台 E2E 当前仍未通过**。
- 一次补充单测命令误从仓库根运行了 npx Vitest 5，alias 初始化失败，无测试执行；不计业务红/绿。后续使用 frontend 已安装 Vitest 2.1.9 定向复核，33 通过。
- Browserslist/baseline 数据陈旧、既有 Pinia 测试注入警告保留，未升级依赖。

## 本批 write 集

业务实现（仅此两份）：
- D:\小说写作\xuanqiong-wenshu\frontend\src\utils\sseStream.ts
- D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentRunStream.ts

测试：
- D:\小说写作\xuanqiong-wenshu\frontend\src\utils\sseStream.spec.ts
- D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentRunStream.isolation.spec.ts
- D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentRunStream.transport.spec.ts

浏览器支持：
- D:\小说写作\xuanqiong-wenshu\frontend\playwright.sse-audit.config.ts
- D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-sse-isolation.spec.ts
- D:\小说写作\xuanqiong-wenshu\frontend\e2e\scripts\start-sse-audit-server.mjs
- D:\小说写作\xuanqiong-wenshu\frontend\e2e\fixtures\sse-audit.html
- D:\小说写作\xuanqiong-wenshu\frontend\e2e\fixtures\sse-audit.ts

证据全部位于 D:\小说写作\xuanqiong-wenshu\frontend\audit\sse-isolation-20260907，不改主线 backend recovery 分页或根接续文档。

## 复跑（必须在 frontend 目录）

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\frontend'
node audit/sse-isolation-20260907/run-mutations.mjs
node audit/sse-isolation-20260907/run-browser.mjs e2e/agent-sse-isolation.spec.ts
npm run type-check
npm run test:run
npm run build-only
```

默认 runner 使用时间戳证据标签，保留旧 trace。若要审查完整工作台，可显式传 e2e/agent-workspace.spec.ts；其既有失败与本批 SSE 场景分开记录。
