# UI-006 reasoning 虚拟化：冻结后的下一步实施计划

> 日期：2026-09-06（Asia/Shanghai）。依据当前工作树，HEAD 为 `dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb`。本轮仅做文件读取、静态审查与本报告写入；未启动 pytest、npm、服务、Provider 或浏览器，未修改源码/测试，未创建新任务。既有未提交成果保持原状。
>
> 本报告限定为原审计 C1 的细化，不重做整项 UI-006 验收。下列修复与验证均待主代理收取冻结后端全量终态、明确解除相应禁令后执行。本轮没有测试通过、性能提升或浏览器实测结论。

## 1. 结论

**C1 仍未闭合：reasoning 有接口分页，但没有实际渲染窗口。** `content-visibility`、容器限高及名为 `virtual-list` 的类/选择器均不等于虚拟化；当前组件为所有已合并 chunks 创建 `pre`，折叠后节点仍存在。

**旧审计的 C2 描述已落后于当前源码。** 历史 composable 现有 generation、activeRequest 归属校验、整页/逐条 Run 校验和扩充后的竞态回归。它们是本批必须保护的基线，不应重新列为尚未实现，也不代表本轮已验证通过。无需为 C1 重写历史请求状态机。

本计划只列 **3 项后续修复**：真实可见窗口；前插/流追加阅读位置；折叠节点回收与完整复制。数据缓存保留、DOM 数量和浏览器性能分别验收。

## 2. 当前真实实现与证据

以下编号仅作为本报告内的证据别名，行号对应本次读取。所有结论来自源码/测试文本，而非动态运行。

| 证据 | 当前文件与定位 | 静态事实 |
|---|---|---|
| E1 | `D:\小说写作\xuanqiong-wenshu\docs\reports\UI006_REQUIREMENT_AUDIT_20260906.md`：69–75 | C1 要求独立渲染窗口、历史可导航、前插锚点、条件跟尾及正反向验证；2000 段、十页是测试场景，不是已有测量。 |
| E2 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue`：20–32、37–53、66–71 | `isExpanded = streaming || manuallyExpanded`；`displayText = text || chunks.map(...).join('')`；复制调用 clipboard；body 使用 `v-show`；`v-for="chunk in chunks"` 全量渲染；26rem 限高、overflow 与 content-visibility 没有切片/回收逻辑。 |
| E3 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.ts`：5–6、33–90 | 初页游标 2147483647，每页 100；每次 load 先 reset 并推进 generation；成功/失败/finally 校验当前请求；回写前核验页和所有条目的 Run；sequence 去重排序，旧页重叠保留已缓存内容；累计历史没有 DOM 窗口或总量裁剪。 |
| E4 | `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue`：207–213、656–667；`D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue`：70–78 | 历史后接流投影，以 sequence 合并并升序排序，重叠时流数据优先；父层对全部合并内容 join，再把 chunks/text/status/分页状态传到 Card；activeRun 改变触发 history.load。Card 当前没有显式 Run/context 标识。 |
| E5 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\reducers\agentEventReducer.ts`：84–85、253–271 | 流投影保留最近 4096 段；其 reasoningText 截取最后 200000 字符，但 chunks.content 本身未按该字符上限截断。页面 E4 重新 join 合并 chunks，故这两个数都不是 Card 的 DOM/完整历史字符上限。生成的流 chunk 未填 id/runId，不能假设所有条目自带 Run 身份。 |
| E6 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts`：7–24 | 仅两个基础用例：流式展开/完成折叠/手动展开、失败状态。后者标题提到换行，实际断言只有隐藏 style 和失败文字，未验证正文换行、复制、分页、节点上限或真实滚动。text-only 输入当前参与显示条件与复制，正文仍仅遍历 chunks。 |
| E7 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.spec.ts`：11–24、64–341 | 已有初页/旧页、旧成功/失败/finally、A→B→A、同 Run 重载、load(null)、分页与切 Run 交叉、双击去重、终页停止、失败保留游标并重试、页/条目异 Run 整页拒绝的测试文本。不是旧审计所述的仅一个正常分页测试。 |
| E8 | `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\reducers\agentEventReducer.spec.ts`：239–248 | 已断言 reasoning 与 assistant 正文隔离、投影 chunk_index 顺序和 completed 状态；该用例不是 DOM 窗口测试。 |
| E9 | `D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts`：1032 起；`D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.spec.ts`：958–960 附近 | 现有 CARD-071 为五视口布局及日志/聊天滚动隔离，最窄 650px；该 E2E 文件未见 reasoning 专项。Workspace 单测的 HIDDEN_REASONING fixture 不构成长 reasoning 的窗口、复制或锚点覆盖。 |

### 当前成本边界

- 历史 merge、页面合并排序及全文 join 都处理累计内容。真实窗口能约束挂载节点，**不自动消除累计数组、排序或文本拼接成本**。
- 当前没有可见索引、上下占位高度、滚动窗口计算、动态行高测量、前插补偿或条件跟尾实现（E2）。这说明实现缺口，不等于本轮已经复现卡顿、内存泄漏或具体掉帧。
- “全文复制”目前意味着传入 text，或当前已加载 chunks 的全文；它不等于服务端尚未加载的所有历史，更不代表流缓存已裁掉的内容自动恢复。后续 UI/验收应明确此范围。

## 3. 必须保护的不变量

1. **数据与视图分离。** 缩小渲染数组，不裁掉 history.chunks，不把窗口数据回写父层、不降低 reducer 上限、不截断长段来凑节点预算。所有已加载段可通过滚动或明确导航重新访问；远端旧页按钮继续存在。
2. **请求归属不退化。** generation、activeRequest 对象归属与 runId 三重条件继续约束成功/失败/finally；load(null)、同 Run 重载、A→B→A 都使旧请求失效。虚拟列表观察器、延迟布局回调也需要自身的 context 代次隔离。
3. **分页合同不变。** 初页与旧页各 limit=100；一次显式加载只推进一次请求，loading 时重复点击不多发；失败保留上一成功页和游标；终页停发；完整校验后原子合并，不写入异 Run 的部分条目。
4. **去重与优先级不变。** 历史按 sequence 去重升序；旧页重叠保留已有值；页面历史/流重叠仍以流数据为准。不要把 Card 展示顺序悄悄改成 reducer 的 chunkIndex 排序。
5. **身份稳定。** 新窗口的缓存键/锚点采用明确的 active Run/context + sequence，而非数组下标或依赖可选 id。历史 id 与流 chunk 的身份形态不同；同 sequence 的内容更新应保留逻辑位置并重测高度。
6. **reasoning 独立于正文。** 保留 Provider 原始内容、换行、空段语义、状态标签、分页错误与复制入口；不进入 assistant 正文或 public summary。text-only 支持若补齐，须单独断言，勿声称现有测试已覆盖。
7. **展开语义准确保留。** streaming 强制展开；未手动展开时 completed 后折叠，手动展开标志为真时仍展开；现有实现并非“所有 completed 都强制折叠”。保留 aria-expanded 与键盘按钮可用性。
8. **现有成果和门禁受保护。** 本轮不触碰源码/测试；后续保留全部既有竞态及状态断言。若折叠策略变化，优先保留 body 的 v-show，仅对内部窗口子树按需挂载，以继续满足现有 display:none 断言。

## 4. 最多三项直接落地修复

### R1 / P1：可变高度的真实渲染窗口

**Evidence → Finding：** E1/E2/E3/E4 显示全量 DOM 与无限累计数据的耦合。

**Path：** 冻结解除后在 `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue` 引入独立的可见区间；必要时新增 `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningWindow.ts`，只负责展示，不接管历史 API。

- 以 body 实际视口和 scrollTop 计算区间；仅挂载可见段及有限 overscan，前后用占位高度维持整个滚动空间。保留全量缓存供窗口重访与复制，禁止在隐藏副本中再渲染全文。
- 按稳定键记录测量高度，记录 gap；用累计高度定位起止索引。长段/换行/窄屏宽度变化通过 ResizeObserver 重测；空段设一行最小布局高度，避免大量零高度节点穿透窗口预算。不要把所有 chunk 当成固定行高。
- 拟定初始设计为两侧各 6 段 overscan、最多 80 个 chunk 根节点；这是**待实现的工程预算，不是实测性能数据**。在支持视口中要同时证明完整覆盖可见区；若覆盖不足先修正区间算法/最小高度合同，不通过砍可见内容达标。
- 保留既有 testid 便于回归，但以真实 DOM 回收及可访问数据证明窗口成立。content-visibility 即使保留也只算辅助样式；测量节点避免依赖其估算占位高度。

**回归：** 扩充 `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts`，如提取 composable 则新增同目录配套 spec。使用 2000 段短长交错/空段 fixture，滚动至头/中/尾均能找到目标段；再逐次装入十页，已加载总量增加而 chunk 根节点仍 ≤80。统计窗口内所有后代元素，并用 TreeWalker 包含文本节点检查隐藏副本，预算由提交后的固定模板节点数加有界行节点数确定；禁止只数 pre 后漏掉全量辅助结构。单测模拟尺寸只验证区间逻辑，真实换行高度交给 R2 浏览器场景。

**反向：** 独立临时副本或内存变异把窗口输入恢复为全量 chunks；2000 段节点预算断言必须失败；恢复后再绿。该结果只证明节点约束回归，不证明耗时或内存达标。

### R2 / P1：前插锚点、条件跟尾及 Run 上下文隔离

**Evidence → Finding：** E2 没有滚动位置逻辑；E3 前插历史，E4 流追加/重叠更新会改变列表位置；R1 引入的高度估计还会增加布局变化。

**Path：** 在上述 Card/window 内保存阅读状态；通过 `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue` → `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue` 传递显式 Run/context 标识，避免从首段可选 runId 推断。上下文失效时清理高度缓存、锚点和待执行回调，不改 E3 请求状态机。

- 在历史合并前保存首个可见段的稳定键及其相对视口偏移；nextTick/测量完成后按同一键恢复。测量补偿包含按钮/错误区域及 gap 变化，不仅用 scrollHeight 总差估计。需要文字行级稳定时记录可见文本偏移，尤其覆盖长段内阅读和宽度重排。
- 追加前采样是否接近尾部：在尾部才跟到新尾；用户上滚阅读时保持锚点，并给出“回到最新”入口。显式加载旧页优先保留阅读位置，不因同时流追加被强制带走。
- 高度回调、requestAnimationFrame 与上下文代次绑定，卸载/切 Run 时清理；避免旧 A 的测量或滚动回调影响 B，A→B→A 也需要独立代次。观察器和浏览器滚动锚定应避免双重补偿。

**回归：** Card 单测覆盖前插重叠页、长段更新、尾部追加、上滚追加、失败重试、快速切 Run。扩充 `D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts`，新增名称含 `UI006 reasoning virtualization` 的 mock API 用例：真实滚动读取首可见段/文本偏移，记录更新前后几何差；包含 375px 窄屏换行及桌面、短长交错段、十次单页加载、旧页与流追加交错、切 Run。mock API/SSE 全程覆盖，未命中请求直接失败，避免真实 Provider。该标签是计划新增，当前不存在。

**反向：** 分别移除前插补偿、强制所有追加跟尾、移除 context 回调隔离；对应锚点/上滚保持/切 Run 用例应各自失败，再逐项恢复。锚点容差需在执行前以布局合同明确登记；本报告未测得像素差，也不预填达标值。

### R3 / P2：折叠子树回收，复制继续读取完整数据

**Evidence → Finding：** E2 的 v-show 留下全部子节点；E6 未验证复制。直接把 displayText 改成窗口拼接会丢失不可见内容；直接把整个 body 改成 v-if 又会破坏既有隐藏 style 回归。

**Path：** 主要改 `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue`：保留外层 body 的 v-show 与现有状态语义，对内部窗口挂载使用 isExpanded 条件；折叠卸载行节点/暂停测量，保留数据、阅读锚点及头部复制按钮；重开后恢复位置并重新测量。

- 复制始终基于传入的完整 text 或全部已加载 chunks，绝不读取可见 DOM/窗口切片。验证已加载而不可见的头、中、尾内容、换行、空内容、重叠去重后的顺序，以及折叠状态复制。
- text-only 输入应作为正文单独可展示的数据路径；不要制造空列表但显示“已完成”的假覆盖。空 text/chunks 时的状态与按钮合同继续明确。
- 本项不把“减少节点”宣称为“消除全文 join”。父层全文 computed 和累计排序成本仍在；本批不借机扩大为数据层重构。若后续决定按复制动作惰性构造全文，应另以性能证据和 text prop 兼容回归评估。

**回归：** 保留原两个 Card 测试，补 clipboard mock 的完整字符串断言、折叠时 chunk 节点为零、重开后目标段可见、streaming/completed/手动展开组合、text-only 展示。observer 释放与复制反馈定时器清理须有生命周期断言。

**反向：** 分别让复制改读可见切片、撤销内部卸载、破坏手动展开状态；完整复制/折叠节点/状态回归应分别失败，恢复后再绿。不删旧断言或只改报告来制造通过。

## 5. 冻结解除后的验证命令（本轮零执行）

仅在主代理明确放行后按以下顺序串行执行；每个退出码非零立即停下。第一组在修复前确认当前基线，修复后重复执行。新增 composable 若存在，其配套 spec 在第二组前端全量中一并执行。

### 5.1 当前基线与修复后定向回归

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run test:run -- 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\reducers\agentEventReducer.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.spec.ts'
if ($LASTEXITCODE -ne 0) { throw 'UI006 reasoning targeted regression failed' }
```

### 5.2 新增浏览器专项后的真实布局验证

前提：R2 的 E2E 用例已提交到允许修改的工作树；只运行 mock 专项，不运行 real-provider 套件。已读取的 `D:\小说写作\xuanqiong-wenshu\frontend\playwright.config.ts` 会启动 Vite，使用 5174 且 reuseExistingServer=false，**本轮禁止执行**。放行后仍需主代理确认端口与服务安排，避免抢占其他工作。

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu\frontend'
$spec = 'D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts'
if (-not (Select-String -LiteralPath $spec -SimpleMatch 'UI006 reasoning virtualization' -Quiet)) {
  throw 'New reasoning browser cases are not present yet'
}
npm run e2e -- --config 'D:\小说写作\xuanqiong-wenshu\frontend\playwright.config.ts' --grep 'UI006 reasoning virtualization' --workers=1
if ($LASTEXITCODE -ne 0) { throw 'UI006 reasoning browser regression failed' }
```

确认实际发现并执行了目标用例；不要用 pass-with-no-tests 或只跑旧 CARD-071 替代。本条不会自动生成尚未实现的断言。

### 5.3 修复、反向红灯及恢复后的前端门禁

反向变异只在主代理批准的独立副本或内存中进行，分别重复对应定向命令，确认预期断言红灯而不是配置/依赖错误；恢复后回到主工作树执行以下命令。不得在共享工作树为演示红灯临时破坏源码。

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu\frontend'
npm run type-check
if ($LASTEXITCODE -ne 0) { throw 'Frontend type-check failed' }
npm run test:run
if ($LASTEXITCODE -ne 0) { throw 'Frontend full regression failed' }
npm run build-only
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
```

本批预期仅前端改动，不另启动后端 pytest。若主代理后续要求后端全量，由主代理在原冻结流程结束后另行调度，避免重复占用资源。

## 6. 验收记录与结论边界

| 项目 | 后续必须记录 | 本轮状态 |
|---|---|---|
| 数据保留/可达 | 载入总段数、去重结果、头中尾导航、十页 cursor 与调用次数、复制完整字符串 | 仅读取实现与已有测试 |
| 实际虚拟化 | 展开/折叠及头中尾位置的 chunk 根节点数、全部后代元素/文本节点数、设计预算与实测比较 | 未测量；没有窗口实现 |
| 阅读位置 | 前插、追加、长段增高、宽度重排前后的稳定键、文本偏移、像素差；上滚不跟尾 | 未测量 |
| 浏览器性能 | 固定 fixture/浏览器版本/视口/缩放/构建模式/硬件；渲染布局与交互耗时、长任务及内存测量方法、重复次数和原始样本 | 未测量；没有毫秒、FPS、MB 或百分比结论 |
| 回归有效性 | 修复前红→修复后绿→各变异预期红→恢复绿，保留命令、退出码及准确失败断言 | 未执行 |

2000 段、十页、80 节点、6 段 overscan 都是上述计划的输入/拟定预算；4096、200000、100、26rem 是读取到的当前常量/CSS。两类均不应包装为性能测量。单测耗时、样式存在、DOM 上限分别与浏览器帧时/内存结论区分。完成 R1–R3 后也不自动宣称整个 UI-006（含移动抽屉及其他列表）已通过。

## 7. 文件指纹与只读复核

以下 SHA256 为报告写入前读取的文件快照。复核可使用 `Get-FileHash -Algorithm SHA256 -LiteralPath '绝对路径'`；路径取下表具体文件。记录用于区分主代理/其他任务后续变化，不据整个工作区 git status 的变化推断本轮修改范围。本轮唯一写入为本报告。

| 绝对路径 | SHA256 |
|---|---|
| `D:\小说写作\xuanqiong-wenshu\docs\reports\UI006_REQUIREMENT_AUDIT_20260906.md` | `907F673283A8947032CAEE0A16D6C453CCDEA3A5375C3A935EAE79DC3DAE3F9E` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue` | `3C96A1821FEAD57EAD83CF79A6F745772E6B0C1ED889FEB573C643A3DA92F900` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.ts` | `675E5DD2FED83134C831EC13E3E3F0D1B63B8D87DAA26BD217FBE5C82B891AC2` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts` | `13E9C6624FCF44D5D7A8F5AB9DBD265B2C589107AD80D6B1726064CF2AC6D9DE` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentReasoningHistory.spec.ts` | `BCD418E220E927C8C586AE04B88611B08EB5D74E1F1CB57D463636803B86DE2E` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue` | `00B6B901720C29246ABEADE91DD2E786F98A1DFE9FAF67BE443A3337C3938539` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue` | `37B3245886DF05EBCB7626754A2059B3599ACB22E33715ABCCFE03660099B931` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\reducers\agentEventReducer.ts` | `36A511649CE8FDCF67BDD7DD2C49CD1FD0B22CEF6FA4B91C71D9565EBB68E038` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\reducers\agentEventReducer.spec.ts` | `01B3CBE900621A88F159E6DF63F88E482254F1109DA8D36B358788F32AD0E0FA` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.spec.ts` | `01CEC2ADC43D31D8A940EFE20E3E0ABCAE039C013A762634992CE41D2F2445D1` |
| `D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts` | `4B64021DEA0735094E8A8CE6F9296FE3ADBC10DB469E66FF577DC0CAECD7C77A` |
| `D:\小说写作\xuanqiong-wenshu\frontend\package.json` | `91D74770D1537A93E75818EA3BF334B6C614E2A3A5C27A0AA94B49A7AAD2FBC1` |
| `D:\小说写作\xuanqiong-wenshu\frontend\playwright.config.ts` | `7C4AE1ED32D5858BA5B429716F10B1EBD916EC7C4A06A354CA3041A6FE0199AA` |
