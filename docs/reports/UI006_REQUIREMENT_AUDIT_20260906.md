# UI-006 长历史列表性能与移动端体验：需求审计

> 审计日期：2026-09-06。工作区：`D:\小说写作\xuanqiong-wenshu`。读取得到 HEAD：`dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb`；结论依据当前工作树，非仅依据提交版本。
> 本轮是只读源码/测试审计，唯一写入为本报告。未修改源码或测试，未执行 pytest、npm、Vitest、Playwright、浏览器或服务启动，未创建新任务；不介入正在运行的最终后端全量。

## 1. 结论与证据边界

**UI-006 的消息初始窗口及部分分页机制已落地；“全部长历史性能与移动端体验通过”仍缺证据。** 消息列表初始 60 条、分页锚点和重复点击保护有实现及回归。reasoning 的 `virtual-list` 名称不代表虚拟化：当前直接渲染全部 `chunks`，折叠使用 `v-show`，历史状态累计合并。移动端有响应式抽屉和 safe-area CSS，也有真实浏览器几何断言的 E2E 源码，但最窄浏览器用例是 650px；375px 单测使用模拟几何。

本报告给出且仅给出 **3 个具体修复候选**：reasoning 渲染窗口、reasoning 过期响应隔离、窄屏双抽屉重叠。它们均有当前源码依据，但本轮未动态复现，不描述为已实测卡顿、已测内存泄漏或已测交互失效。其他需求差距列为未闭合验收点，不扩大本批修复范围。

证据等级：

- **S：当前源码/测试文本**，可确认控制流、数组处理、CSS 和断言内容；不代表测试本轮运行成功。
- **L：已有日志**，仅承认日志对应那次执行。当前前端日志实际记录 81 文件、545 测试、116.92s；其中 Conversation 12 项、Conversation.performance 5 项、ReasoningCard 2 项、ReasoningHistory 1 项。5 个 performance 用例整文件 74ms 不是浏览器首屏耗时（E14）。
- **B：浏览器动态证据**，本轮未生成或复验。E2E 测试源码中的几何/滚动断言与其实际成功产物分别对待。
- **I：静态推导**，如延迟旧响应回写及抽屉同区域重叠；下面说明触发顺序与待验证行为。

当前状态文档仍将最终冻结后端全量列为执行中，发布状态为 active / NO-GO（E02）。该门禁由主代理处理；已有 TCP/JWT 消息 180 条 / 3 页验收验证接口分页与数据合同，不等同于浏览器虚拟化、帧时或移动布局通过。本审计不审核小说内容质量，也不审核 UI-005 工具权限、注册或编排策略。

## 2. 需求来源与实际位置索引

下列 E 编号是本报告内部定位别名；路径均为当前工作区绝对路径，行号是此次读取时的位置。

| 证据 | 真实文件与定位 |
|---|---|
| E01 需求 | `D:\小说写作\xuanqiong-wenshu\TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md`：3992–4036 消息窗口；4141–4165 按需加载与请求隔离；4177–4203 渲染、预算及反向验证；4372–4396 会话稳定键与加载保护。5492、5596 的历史完成表述按具体子项理解，不替代上述完整要求。 |
| E02 当前状态 | `D:\小说写作\xuanqiong-wenshu\docs\reports\CURRENT_EXECUTION_STATUS_20260906.md`：16–37 门禁；66–89 持续计划；末尾“当前最终验收与持续工作入口”限定当前只运行冻结后端全量。 |
| E03 消息 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue`：48–68 列表和加载控件，215–318 窗口/请求锚点，350–362 样式；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.spec.ts`：156–325；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.performance.spec.ts`：24–115。 |
| E04 reasoning 组件 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue`：20–32 展开/全文复制，45–51 全量 chunks 渲染，66–71 滚动与 content-visibility；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts`：2 个状态/展示用例。 |
| E05 reasoning 历史状态 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.ts`：5–6 页长，25–70 reset/merge/load/loadPrevious；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.spec.ts`：8–21 两页正常读取。 |
| E06 页面接线 | `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue`：207–213 reasoning 绑定；267–278 日志；308–332、422–435 分页状态及按钮；370 起审批列表；619–643 日志窗口/滚动；656–666 reasoning 合并与 Run watch；1282–1293 详情展开；1338–1375 hydrate；`D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.spec.ts`：299–365 数据区懒加载、608–610 日志 DOM 分区。 |
| E07 详情状态 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentWorkspaceRuntime.ts`：102 页长 50，159–286 页状态/去重/累积，332–369 Run facts，704–750 活动与流恢复；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentWorkspaceRuntime.spec.ts`：147–205 分页合并/去重/切换，499–575 补洞与无推进停止。 |
| E08 会话状态 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentSessionLifecycle.ts`：52–53 generation，99–125 首屏消息及兼容回退，141–201 Run 分页与深链，241–261 更早消息；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentSessionLifecycle.spec.ts`：111–186 初页，188–226 回退，228–274 深链，276–334 异常页，368–455 过期请求/重复点击。 |
| E09 手机布局与面板状态 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.vue`：16–69 双侧面板，89–117 状态接线，145–180 CSS；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentPanelState.ts`：77–109 双侧独立状态/持久化；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.spec.ts`：双侧同时展开、持久化、aria 与 CSS 字符串断言。 |
| E10 流状态上限 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\reducers\agentEventReducer.ts`：78 活动 240，84–85 reasoning 4096 段/文本 200000 字符，263–271 截取；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\stores\agentRunProjection.ts`：96–97 reasoning 投影。 |
| E11 详情渲染 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\run\AgentRunInspector.vue`：steps 的 `v-for`；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentRunCommandHistory.vue`：14–21 排序但无裁窗，55 列表；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\artifacts\AgentArtifactWorkbench.vue`：8 Artifact 列表，69 正文入口，103 diff 列表；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentToolResultPanel.vue`：94–97 数量/文本默认上限，141/179 截断，398–416 结果裁窗。 |
| E12 治理列表/API | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentProjectGovernanceData.ts`：49–84 timeline/audit 最近 100 条及请求代次，152 起筛选 watch；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\data\AgentDataPanel.vue`：timeline/audit 列表；`D:\小说写作\xuanqiong-wenshu\frontend\src\api\agent.ts`：862 消息页，882–886 activity/reasoning，981 commands 页，1015 approvals，1019 steps 页，1041 artifacts 页，1052 正文独立入口。 |
| E13 浏览器测试与配置 | `D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts`：1032–1171 CARD-071；`D:\小说写作\xuanqiong-wenshu\frontend\playwright.config.ts` 与 `D:\小说写作\xuanqiong-wenshu\frontend\playwright.card071.config.ts`：Desktop Chrome、单 worker；前者有 webServer，后者依赖已有 5174 服务。`D:\小说写作\xuanqiong-wenshu\frontend\e2e\real\agent-workspace.real.spec.ts`：JWT/API/SSE/控制链；`D:\小说写作\xuanqiong-wenshu\frontend\e2e\real\agent-planner-provider-success.real.spec.ts`：Provider 接线，非性能验收。 |
| E14 单测环境与已有输出 | `D:\小说写作\xuanqiong-wenshu\frontend\vite.config.ts`：test.environment=jsdom，Vitest 仅包含 src 下 spec/test；`D:\小说写作\xuanqiong-wenshu\frontend\package.json`：test:run/type-check/build-only/e2e 脚本；`D:\小说写作\xuanqiong-wenshu\logs\frontend-full-current-20260906.log`：174、209、237、240、260–263 行。 |

另直接检查以下测试的实际断言，作为详情列表的局部证据：

- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentRunCommandHistory.spec.ts`：当前 Run 控制记录和空态。
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\run\AgentRunInspector.spec.ts`：状态展示、选中步骤定位，不含十页性能预算。
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\artifacts\AgentArtifactWorkbench.spec.ts`：单 Artifact 显式读取、加载/错误状态与归属；仅使用 UI 行为证据，不评价正文质量。
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentToolResultPanel.spec.ts`：88–115 验证 maxResults/maxListItems/maxTextLength 等裁剪。
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentProjectGovernanceData.spec.ts`：72–137 验证项目切换与筛选旧响应隔离。

## 3. 需求 → 实际实现 → 证据范围 → 未证实点

| 需求 | 实际实现位置与当前行为 | 证据范围 | 未证实点 / 差距 |
|---|---|---|---|
| 消息初始 60 条；长/空消息、追加、prepend、会话切换 | E03 `visibleMessages` 对尾部 slice；按 session_id 重置；外部页前插按首 sequence 判断并补偿高度；本地每次 +60。E08 首次消息页 limit=60、更早使用 beforeSequence。 | S+L：常规 12 项及 performance 5 项；包括错误后实时追加不误判、重复点击、刷新和会话切换。 | 窗口会随已加载页扩大：E03:277/304。加载后 120 条是测试明确预期，不是固定可见范围回收的虚拟列表。十页后内存/耗时与任意高度内容的浏览器锚点未验证。 |
| 2000 条 fixture 初始 DOM 不按历史总数增长 | E03 performance:72–88 注入 2000 条，其中最后一条 250000 字符，断言 60 个 `.message`，挂载 <2000ms。 | S+L：真实存在且已有运行日志的 jsdom 边界测试，比“元素存在”更强。 | 统计是消息 article 数，非所有子孙 DOM；计时包括 jsdom mount，不是浏览器布局/绘制/交互耗时。没有十页浏览器基准或 reasoning 2000 段等价断言。 |
| reasoning 使用 sequence 页并实际窗口化，不仅 content-visibility | E05 初页/旧页各 100、sequence 去重排序；E04:45–51 v-show + 全量 chunks 的 v-for；E06:657–662 合并全部历史与流数据并 join 全文。 | S：分页存在，渲染窗口缺失；E04 测试只验证展开/折叠与状态，E05 仅两条数据正常分页。 | 静态上不满足独立 reasoning 可见窗口要求。E10 流上限是 4096 段，不是“100 段渲染上限”；历史 merge 本身也无总量上限。初始历史页 100 不限制持续流/多页后的 DOM。见 C1。 |
| Run/项目切换立即丢弃旧响应；同页去重 | E08 消息有 generation 与 session 校验；E07 页请求键 runId:kind:offset、loading/loaded 闸门；E12 项目/筛选代次保护。E05 的 await 后无 Run/generation 校验。 | S+L：多个状态模块已有切换/去重回归；reasoning 只有正常两页测试。 | 不可把 Artifact/消息隔离测试外推到 reasoning。A/B 响应乱序时 reasoning 共享 chunks/cursor/error/loading 存在旧响应回写路径，见 C2。完整资源/filter/snapshot 键覆盖也未全域证实。 |
| 隐藏面板不拉详情；首屏读取数量建议 ≤4 | E06 数据区 toggle 懒加载；E07 Artifact 列表不自动遍历读取每项 facts。另一方面 E07:735–737 恢复流前调用 steps/facts/state；facts 内含 provenance/context/plan/conversation summaries；E06:1351–1356 hydrate 读取 approvals/Artifact 首页；详情任一展开会调用三类 summaries。 | S+L：E06 单测 299–365 的“不请求”仅限 Provider usage、治理、实体、成员等指定资源；E07 单测证实 Artifact 摘要不触发逐项质量/谱系请求。 | 不是“所有隐藏详情无请求”；首屏事实读取路径仍存在。真实网络请求峰值、调用是否重叠、预算 ≤4 均未实测。完整懒加载验收尚未闭合。 |
| steps/commands/artifacts 分页；审批与 timeline/audit 可读完整历史 | E07 页长 50、offset 与 next_offset 严格推进、ID 合并；E06 显示总数/加载/错误/更多按钮。E11 组件渲染所有已加载项。E12 timeline/audit 取最近 100，当前 composable 未消费下一页；approvals 在 E12 为普通列表入口，E06 全量循环。 | S+L：E07:147–205 测试分页顺序、请求去重、跨 Run 状态；详情组件测试覆盖局部展示。 | 这三类是追加式分页而非回收式虚拟化；审批未见前端页控件、timeline/audit 更早历史入口未闭合。主需求优先 keyset，当前详情仍 offset，二者应区分；本轮不推断后端查询成本。 |
| 活动/日志窗口，SSE 补洞停止条件 | E06:619–643 日志 DOM 尾部 120，E10 活动投影 240；E07:704–715 恢复活动调用 limit=500；补洞有连续 cursor 检查。 | S+L：E07 单测有 500+501 补洞及无连续推进错误；E13 有日志/聊天各自滚动断言。 | 日志有有界渲染，但不是任意更早日志浏览器分页完成证据。500 是恢复活动请求页长，不等同首批展示 ≤100；网络大小及实时高频更新帧时未测。 |
| 大字段独立加载、超长正文处理、单列表 payload ≤256KB | E12 正文独立 endpoint；E11 Artifact 按钮触发正文/diff；ToolResult 默认最多 16 个结果、500 字符值、20 个列表项。E03 消息正文与 Artifact 预览仍按传入全文显示。 | S+L：tool result 裁剪/空态断言、Artifact 显式加载测试。 | 没有列表响应字节数断言或当前 HAR；`getArtifactContent` 存在不证明每个列表 DTO 都无正文。250000 字符消息 fixture 测试保留全文，未验证截断/复制/下载策略。 |
| 稳定 key、加载/空/错误/重试、键盘和触摸 | E03 message.id；E04 chunk.id 或 runId:sequence；E11 对象 id；多处显示 loading/error，消息错误后仍可重新点击。Shell 有 aria-hidden、关闭按钮 label，轨道有状态属性。 | S+L：按钮事件/aria/空态有局部断言。 | 不存在“所有长列表”统一覆盖证据：reasoning 首屏失败和错误重试、十页边界、焦点顺序/恢复、触摸目标、软键盘遮挡等尚待专项。E03 的重复 ID 测试故意验证输入顺序，不是上游唯一键合同证明。 |
| 手机窄屏、抽屉、滚动隔离与无横溢出 | E09 960/650 断点、fixed 抽屉、safe-area；E13 在 1920/1440/1280/960/650 五视口读取 getBoundingClientRect、computedStyle、scrollHeight，并断言横溢出为 false 和日志/聊天滚动隔离。 | S：真实几何断言代码存在，非仅 DOM exists；本轮未跑 E2E。E03 375px 用例只修改 innerWidth 并人工指定 clientWidth/clientHeight/scrollHeight。 | 最窄真实浏览器用例 650px；配置是 Desktop Chrome、未启用移动触摸模拟；日志通过 innerHTML 注入 80 行，非真实流负载。没有 320/375/390px、键盘/触摸、抽屉遮挡命中验证。静态双侧重叠见 C3。 |

E01 的性能预算先要求固定环境基线，再作为默认门槛；当前缺基线的项目保持“待测”，不编造耗时、掉帧、内存或 payload 数字。分页加载带来的数组增长是源码事实，是否产生用户可感知迟滞应由浏览器测量回答。

## 4. 最多三个修复候选：Evidence → Finding → Path

### C1 — reasoning 的真实渲染窗口（优先级 P1，需求明确差距）

- **Evidence：** E04:45–51/70，E05:34–37，E06:657–662，E10:84/263–271。
- **Finding：** 全部历史 chunks 及最多数千段流数据都进入 `v-for`；折叠只隐藏，不销毁节点。history 的 sequence merge 与全文 join 随数据量处理累计内容。组件名/测试选择器含 virtual 并未实现可见索引、占位高度或节点回收。
- **Path（冻结解除后）：** 在 reasoning 组件引入实际可见窗口或等价有界分页渲染；保留历史缓存与可访问历史导航，区分“数据保留”和“DOM 保留”。新页前插保持阅读锚点，流追加按用户是否在尾部决定跟随；折叠策略保持复制能力及正文完整性。不要用丢历史/删除测试换取节点数变小。
- **正向验证：** 2000 段短长交错 fixture；初始节点与可见窗口量级一致；加载一页仅推进一页，连续十页后渲染节点仍受设计上限约束；检查长段、空段、旧页重叠、流追加、展开/折叠。浏览器记录所有子孙节点数、布局/交互耗时、锚点像素差与内存，不只数 pre。
- **反向验证：** 在主代理批准的独立临时副本或内存变异中，把窗口源恢复为全量 chunks；节点上限专项必须失败。耗时是否红灯按真实测量，不把节点失败冒称为帧时失败。当前未执行此变异。

### C2 — reasoning 历史请求缺少代次隔离（优先级 P1，静态可达竞态）

- **Evidence：** E05:40–54 与 57–70；E06:663–666 在 activeRun 改变时直接调用 load，E06:659 合并时只按 sequence，没有过滤 Run。
- **Finding：** `load(A)` 挂起后 `load(B)` reset 并读入 B，随后 A resolve 会把 A 合并进共享 chunks，并覆盖 B cursor/hasPrevious；相同 sequence 还可能替换另一 Run 的段。旧请求 reject/finally 同样会改当前 error/loading。A 的 loadPrevious 与切换/重复加载也走相同回写路径。这是源码推导，不是本轮实测数据串 Run。
- **Path（冻结解除后）：** reasoning 模块每次 load/reset 推进 request generation；请求开始保存 generation/runId/cursor；成功、失败及 finally 都验证代次与 Run，只有当前请求可回写。分页复用当前上下文、同页去重；必要时在页面合并处校验 runId 作第二层约束。不要只比较 Run ID，A→B→A 仍需要代次。
- **正向验证：** deferred promises 控制 A/B/A 完成顺序；覆盖旧成功、旧失败、旧 finally、load(null)、旧页请求与切换交叉、同 Run 重复 load 和双击分页。断言当前 chunks 的 runId、内容、cursor、hasPrevious、loading、error 全部一致；重复 sequence 不串值。
- **反向验证：** 独立内存/副本撤掉 await 后的代次校验，以上乱序用例必须失败；恢复后重新通过。本轮仅登记，未改源码或测试。

### C3 — ≤650px 双抽屉同时开启占用相同区域（优先级 P2，静态布局冲突）

- **Evidence：** E09 panelState:98–109 只改被选中的 side；Shell:16–60 同时挂载左右面板，116–117 直接转发；Shell:167 两者 z-index=4，179–180 在 ≤650px 下同 top/bottom/width/left/right。Shell 单测明确允许两侧同时 open。E13:1060–1061 同时打开两侧，但 1149–1151 仅检查两侧 width>0。
- **Finding：** 窄屏同开状态按当前 CSS 落入同一个固定矩形；后置右侧面板有遮住左侧内容的路径，两者 aria-hidden 仍为 false。width>0、DOM 存在、横向无溢出和程序赋值 scrollTop 都未验证被遮挡控件能否被点击。未在浏览器测量重叠面积或验证焦点。
- **Path（冻结解除后）：** 为窄屏定义单一活动抽屉，打开一侧时关闭另一侧；桌面继续允许双侧打开。对从桌面缩窄及持久化“双开”恢复做确定性归一化；补齐关闭/切换后焦点返回入口，若采用模态抽屉则同时处理背景交互与 Escape。只改面板呈现状态，不改工具编排。
- **正向验证：** 保留原五视口，追加 320/375/390px；先左后右、先右后左、持久化双开重载、桌面缩窄四条路径。检查当前抽屉控件真实点击命中（含 elementFromPoint 或 Playwright actionability）、Tab 到达/焦点返回、Escape、触摸点击、聊天输入及软键盘场景；保留无横溢出与滚动隔离断言。
- **反向验证：** 独立副本撤掉窄屏互斥及持久化归一化，双开/命中专项必须失败；桌面双开回归应保持通过。当前未执行。

## 5. 冻结结束后的可执行验证队列（本轮零执行）

**前置条件：最终后端全量自然结束，主代理收取终态并明确解除源码/测试/浏览器禁令后，再串行执行。** 下列命令只写在报告中；默认 Playwright 配置会启动前端服务，因此即使是已有 E2E 也须等待上述条件。先保存当前文件指纹和失败输出，再做任何候选修复，不覆盖已有未提交成果。

### 5.1 先复跑现存断言，确认基线

以下使用现有文件，PowerShell 进程以 `login:false` 执行，保持串行；每条 exit 非零时停下定位，不继续包装成通过。

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run test:run -- 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.performance.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.spec.ts'
if ($LASTEXITCODE -ne 0) { throw 'UI006 message/reasoning baseline failed' }
npm run test:run -- 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentSessionLifecycle.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentWorkspaceRuntime.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentPanelState.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.spec.ts'
if ($LASTEXITCODE -ne 0) { throw 'UI006 state/layout baseline failed' }
npm run e2e -- --config 'D:\小说写作\xuanqiong-wenshu\frontend\playwright.config.ts' --grep 'CARD-071' --workers=1
if ($LASTEXITCODE -ne 0) { throw 'UI006 browser layout baseline failed' }
```

最后一条选择既有 CARD-071，不代表自动获得新手机/性能覆盖。5174 端口如被其他任务占用，由主代理安排独立配置，不抢占、不回收其他任务服务；card071 专用配置本身也不负责启动服务。

### 5.2 补缺失回归，再逐个候选红→绿→反向红→恢复绿

1. 先补 C2 deferred 竞态和 C3 双抽屉命中回归，分别记录修复前红灯；C1 同步补 2000 段和十页有界渲染基准。新增测试位于主代理批准的后续改动中，本轮未创建。
2. 固定环境/浏览器版本、fixture seed、视口和字体状态；记录消息/reasoning 各 2000 条，10 页，短文本、长中文、长无空格字符串、空段及 SSE 交错追加。比较冷首屏、展开、prepend、追加、切 Run 和第 1/5/10 页。
3. 记录请求路径/参数/次数、最大同时在途数、响应未压缩正文与传输字节数，分别判断 ≤100 首批、≤256KB 列表、≤4 首屏读取建议预算；正常首屏与兼容回退/深链补页分开统计。确认隐藏面板详情请求，避免仅测数据治理面板。
4. DOM 同时记录消息/段节点和总子孙数；采集浏览器渲染/交互耗时、长任务、内存和 cursor 往返延迟。内存若当前浏览器不支持采样则标记缺证，保留可复跑命令与原因。阈值记录基线与回归百分比，不凭空填成功值，也不降低已有 2000 条 fixture 或 2000ms jsdom 断言。
5. 移动场景保留原五视口并增加 320/375/390px，使用触摸上下文；软键盘/实际安全区另用支持该能力的设备验证，不把 setViewportSize 当作软键盘证据。回归内容应包含消息和 reasoning 的真实高度 prepend、持续追加、抽屉切换、焦点与滚动。
6. 反向性能验证必须恢复全量渲染并检出；分页重复/跳序/忽略 cursor、详情移回首屏/移除去重、SSE 错 cursor 的相关专项也需按 E01:4198–4203 保留红灯证据。仅本报告 C1–C3 列为修复候选，其余是原需求验收，不扩展到 UI-005 或小说质量实现。

### 5.3 候选全部通过后再跑前端门禁

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run type-check
if ($LASTEXITCODE -ne 0) { throw 'Frontend type-check failed' }
npm run test:run
if ($LASTEXITCODE -ne 0) { throw 'Frontend full tests failed' }
npm run build-only
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
```

后端门禁由主代理统一排队，本报告不安排另一轮 pytest。记录每次新执行的原始输出、代码指纹与用例规模；旧 545 项结果仅为当前已读日志证据。

## 6. 交付自检与读取指纹

- [x] 已读接续文档 UI-006 与当前执行状态，直接追到组件、状态、Vitest、E2E 和配置。
- [x] 区分源码、已有日志、静态推导及未生成的浏览器证据。
- [x] 每项需求有实际位置、证据范围与未证实点，三个候选有 Evidence→Finding→Path。
- [x] 未把 content-visibility、DOM 存在、模拟 375px 或单测挂载时间称作真实虚拟化/移动性能通过。
- [x] 未宣称卡顿、未执行被禁止的测试/浏览器/服务、未创建新任务。
- [x] 唯一新写入文件：`D:\小说写作\xuanqiong-wenshu\docs\reports\UI006_REQUIREMENT_AUDIT_20260906.md`。
- [ ] C1–C3 动态复现、修复、正反向回归与新浏览器性能产物：等待冻结解除和主代理选择，未执行。

以下 SHA256 为报告写入前读取的关键文件指纹，用于后续识别工作树漂移；不将 HEAD 相同当作未提交源码相同。

| 文件 | SHA256 |
|---|---|
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue` | `37B3245886DF05EBCB7626754A2059B3599ACB22E33715ABCCFE03660099B931` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.performance.spec.ts` | `EA44683AE0CFBF526C48315C90AAD29551F5E290B72B142B441073DA4F44FEB6` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue` | `3C96A1821FEAD57EAD83CF79A6F745772E6B0C1ED889FEB573C643A3DA92F900` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.ts` | `6750606D4B8FF42CE8EB09016F159084E5C546F2F61A092CC03A2DDA9E04946F` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.spec.ts` | `80992D9FE0C47C4E70A7327ADC134169811130150C429533AD90FA43E44BD5A9` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue` | `00B6B901720C29246ABEADE91DD2E786F98A1DFE9FAF67BE443A3337C3938539` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentWorkspaceRuntime.ts` | `15DB81107E6A892B679499521AC80855AA7AC41FEEAB209CA96D4B195AE7DA74` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.vue` | `24322AA666E517176A191A01A50BE4954665CA01044E2D7BD9147AFCD82F52DC` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentPanelState.ts` | `41BA54757503995D2D9234A234A54F69D5CDD14B3C47644BBE7CB805BD2E269A` |
| `D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts` | `4B64021DEA0735094E8A8CE6F9296FE3ADBC10DB469E66FF577DC0CAECD7C77A` |
