# UI006 窄屏抽屉焦点跟进 — 2026-09-07

> **最终交付更新：** Rails 390px 越界修复已完成并冻结；Shell + Rail 定向 **28 passed**，主代理保存的真实浏览器 fixture 在 **390/650/651/960/1440** 五视口及 **651→650** 焦点恢复检查通过。适用范围为 **Shell + 真实 Rail + 简单 slots**，不是完整 API 工作台。最终源码指纹与证据见第 6—8 节；第 1—5 节包含此前焦点修复的阶段记录。

## 交付状态与共享源码恢复确认

**共享 Shell 已恢复正常；2026-09-07 02:14:21（Asia/Shanghai）开始的最终定向复测为 26 passed，退出码 0。已明确通知主代理恢复 5177 真实浏览器验收。** 测试前后 Shell SHA-256 均为 `d417fce7b0ad81ccd1451382a94d03d947c9734a43dad624b4e0926e035d02a6`，没有遗留 `void trigger // reverse verification: omit resize return focus` 或其他临时变异语句。

本次曾在共享 Shell 文件上做临时磁盘变异，影响了主代理正在运行的 Vite HMR 和浏览器验收。这是验证方式不当，不应将短暂回滚视为对并行浏览器无影响。各变异由 finally 恢复原始字节；收到纠正后立即核验源码并定向复测，停止共享树磁盘变异。已读取 `D:\小说写作\xuanqiong-wenshu\logs\ui006-memory-mutation-20260907.mjs`；后续反向只使用独立测试进程内 `enforce: 'pre'` 的 Vite transform 插件，不写共享业务文件、不操作 5177 服务。本报告不将既有磁盘变异谎称为内存变异。

## 1. 写集与实现

本任务仅编辑以下三个前端文件并新增本报告。F1/F4 后端文件只读检查后已停止介入；没有编辑推理 Card、状态 composable、后端、其他文档，也没有启动浏览器或全量测试。

| 文件（绝对路径） | 本轮变更 |
|---|---|
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.vue` | Shell 内局部 DOM ref、打开/关闭/resize 焦点交接、Escape 优先处理焦点所在面板 |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.spec.ts` | 原 7 条用例保留；新增 12 条真实 document DOM 焦点用例，启用自动 unmount 清理监听 |
| `D:\小说写作\xuanqiong-wenshu\frontend\e2e\agent-workspace.spec.ts` | 仅 CARD-071 段落增加 650px 单抽屉、焦点交接断言 |
| `D:\小说写作\xuanqiong-wenshu\docs\reports\UI006_FOCUS_FOLLOWUP_20260907.md` | 本报告 |

### 焦点策略

- 现有 650px 互斥规则仍由原 `useAgentPanelState` 负责，没有修改 composable。651px 仍支持双开；960px 是现有 CSS 固定 drawer 边界，二者用途不同。
- 用户在 <=960px 打开或切换 drawer，等待 Vue DOM 更新后聚焦对应关闭按钮；同侧切换及跨侧互斥都跟随新面板。>960px 保留原桌面打开时的焦点行为。
- 显式关闭、重复触发按钮关闭、Escape 关闭后，回到被关闭面板对应的轨道按钮。查找限制在当前 Shell，且适用于持久化恢复出来的面板，不依赖全局任意按钮。
- Escape 优先关闭实际拥有焦点的面板；没有面板内焦点时保留既有右优先回退。尊重已被子控件 `preventDefault` 的 Escape。
- resize 前记录焦点及所属面板，归一化后只有该面板被关闭才转移到对应轨道；主栏、轨道和仍打开面板的焦点保持原样。兼容隐藏时浏览器将焦点退回 body 的情形。
- 非模态 drawer：不加 `aria-modal`，不让主栏或轨道 inert，不拦截 Tab/Shift+Tab，不装 focus trap。
- 持久化状态初次挂载不抢焦点。异步焦点处理使用 revision 防止较旧交接覆盖后续面板操作，卸载时使待执行交接失效。

## 2. 定向测试与先红后绿

所有命令的工具执行使用 `login:false`、`PYTHONUTF8=1`，工作目录为 `D:\小说写作\xuanqiong-wenshu\frontend`。没有提权请求。

### 可复核命令

Shell 定向：

```powershell
$env:PYTHONUTF8='1'
& 'D:\download\node\node.exe' 'D:\小说写作\xuanqiong-wenshu\frontend\node_modules\vitest\vitest.mjs' run 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.spec.ts' --reporter=verbose --no-cache
```

Shell 与只读状态 composable 组合定向：

```powershell
$env:PYTHONUTF8='1'
& 'D:\download\node\node.exe' 'D:\小说写作\xuanqiong-wenshu\frontend\node_modules\vitest\vitest.mjs' run 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.spec.ts' 'D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\composables\useAgentPanelState.spec.ts' --reporter=verbose --no-cache
```

| 阶段 | 本地开始时间 | 结果 | 退出码 |
|---|---|---|---:|
| 新增 DOM 用例、尚未实现焦点修复 | 02:08:58 | 8 failed、11 passed，共 19；旧 7 条全部通过 | 1 |
| 焦点实现后 Shell 定向 | 02:10:02 | 19 passed | 0 |
| Shell + 状态定向 | 02:11:26 | 26 passed，2 files | 0 |
| 共享源码恢复确认后的最终定向 | 02:14:21 | 26 passed，2 files；耗时 6.30s | 0 |

新增用例用 `attachTo` 将宿主插入 `document.body`，调用真实元素 `.focus()` 并核验 `document.activeElement`；没有 stub focus 或以属性存在代替焦点。测试覆盖左右打开与显式关闭、左右输入框 Escape、同侧切换/跨侧互斥、651→650 自动关闭、resize 保持主栏和左面板焦点、持久化恢复、非模态 Tab 与轨道可达、重复点击以及宽屏双开 Escape。

红阶段失败为实际焦点对象或面板状态断言：打开后仍在轨道、关闭后仍在输入框、resize 后焦点仍在隐藏右面板、宽屏 Escape 关闭了错误一侧。没有 fixture、导入或 TypeError 故障冒充焦点回归。

### 已执行的反向证据与限制

下面为收到禁止磁盘变异指令前已经完成的操作记录，不是后续建议流程。驱动将源字节暂存在内存，逐项替换磁盘中的一个焦点动作，以 finally 恢复；该方式虽恢复了文件，仍触发 HMR 干扰，因此停止使用。

| 变异 | 定向模式 | 实际结果 |
|---|---|---|
| 取消打开后的 focus | `650px.*打开` | 2 个 AssertionError、17 pending |
| 取消关闭回到触发按钮的 focus | `输入框内 Escape\|显式关闭` | 4 个 AssertionError、15 pending |
| 取消 resize 自动关闭后的 focus | `resize 651` | 1 个 AssertionError、18 pending |

三个变异的 Vitest 退出码均为 1。最终以 `--reporter=json` 解析逐用例 `failureMessages`，确认每项均为 AssertionError 而非 TypeError；三个恢复点 SHA-256 均与交付 Shell 一致。pending 是定向名称过滤，没有删测或全文件绿灯时跳过。

首个 verbose 输出解析尝试曾因 Vitest 将相同异常合并展示而误判“异常文本数不足”，驱动报错后已恢复文件；随后改用 JSON 逐用例校验，并完整跑完三个变异。此解析错误不计作额外有效反向证据。

本轮遵守四文件写集，没有另建日志文件；运行原始输出保留在任务工具记录，本报告汇总命令和实测结果。后续若需要可落盘的内存变异驱动及 JSON 工件，应由主代理确定日志写集。

## 3. CARD071 五视口及浏览器交接

仍保留全部五视口：1920×1080、1440×900、1280×800、960×800、650×844。原日志/聊天独立滚动、横向溢出、截图、测量 JSON 及大屏五列宽度断言全部保留。

- 650px：先关闭从持久化恢复的左抽屉，确保接下来测试实际用户打开行为；打开左抽屉后检查焦点，允许聚焦右轨道，再打开右抽屉并验证左侧隐藏；验证 Escape 和显式关闭回到日志触发按钮，最后打开右侧日志进行既有滚动测量。断言只存在一个打开面板，隐藏左侧宽度为 0。
- 960px：仍是原双面板可见断言。
- >960px：仍保留五列、左右 >=240px、主栏 >300px 原范围。

仅运行下列**收集命令**，没有启动浏览器或 Vite webServer：

```powershell
$env:PYTHONUTF8='1'
& 'D:\download\node\node.exe' 'D:\小说写作\xuanqiong-wenshu\frontend\node_modules\@playwright\test\cli.js' test --config 'D:\小说写作\xuanqiong-wenshu\frontend\playwright.config.ts' --list --grep 'CARD-071'
```

结果：`Total: 1 test in 1 file`，退出码 0。这是一个内部循环五视口的 Playwright 用例，不是五次浏览器验收通过。

该阶段浏览器交接已由主代理完成后续验证；最终证据见第 7 节。最终验证使用 Shell + 真实 Rail + 简单 slots，不是本节 CARD071 完整 API 页面验收。先前 HMR 干扰记录保留，不用后续通过掩盖该事实。

## 4. 焦点修复阶段文件指纹（历史；最终 Rails 指纹见第 8 节）

| 文件 | SHA-256 |
|---|---|
| Shell.vue | `d417fce7b0ad81ccd1451382a94d03d947c9734a43dad624b4e0926e035d02a6` |
| Shell.spec.ts | `5d43a61462f538ca8c32a5f84507d6c01e07e2d51cd69375a36f5af1bd2883bd` |
| E2E agent-workspace.spec.ts | `1ab6c10c000c3cd138f1ee657d575656ab1210d070186cbefdb1d6d2f1a58120` |

## 5. 证据边界

- jsdom 中真实挂载和 focus 可验证 `activeElement` 及事件路由，但不模拟完整浏览器布局、CSS 可见性或原生 Tab 顺序；Tab 测试只证明未被拦截以及其他区域可显式聚焦，原生顺序由浏览器核验。
- 没有运行前端全量、完整 type-check/build、后端全量或实际 E2E。Playwright list 仅证明用例可收集。
- 测试出现 baseline-browser-mapping/Browserslist 数据过期提示，不影响本轮定向通过，未升级依赖。
- 本报告不宣称整个并行工作区未变；保留现有改动，不回滚其他代理成果。

## 6. Rails 390px 追加修复与冻结定向

### 缺陷与正常实现

主代理真实浏览器发现 390px 左 tools（x≈204.82、w≈32.52）越界后被右 log（x≈196.80、w≈32.52）遮挡，点击工具实际打开日志；650px 当时未复现。该现象来自半屏容器内按钮最小内容宽度与 `flex: 1 1 0` 挤压叠加，轨道又缺少滚动/裁剪约束。

本轮仅对 Shell/AgentRail 的 <=650px CSS 做正常修改，新增 AgentRail spec 回归：

- Shell 左右半屏分区增加 border-box、overflow hidden 和圆角裁剪；原中央间隙、安全区和左右宽度规则保留。
- Rail 保持 width/max-width 100%、min-width 0，单行 flex-start；overflow-x auto、overflow-y hidden，独立横向滚动及 overscroll-behavior-x contain，保留滚动条。
- 按钮使用 `flex: 0 0 2.75rem`，宽度 2.75rem，min-width/min-height 均为 44px；按钮不再压缩挤入半屏，末尾按钮通过横向滚动触达。
- 原 650px 抽屉互斥、非模态焦点、关闭/Escape/resize 路径均保持。Shell script 校验逐字未变；AgentRail 脚本与模板也未变。

此次实际编辑文件为：

1. `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.vue`（仅 CSS）。
2. `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\layout\AgentRail.vue`（仅 CSS）。
3. `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\layout\AgentRail.spec.ts`（原 5 条保留，新增 4 条）。

### 红绿与冻结证据

| 阶段 | 结果 |
|---|---|
| CSS/组件回归先加、修复前 | AgentRail 3 failed / 6 passed；缺横向滚动、按钮仍可压缩、分区缺裁剪均被捕获 |
| 正常 CSS 实现后 | Shell 19 passed + Rail 9 passed = **28 passed** |
| 新增只读证据脚本冻结复测 | **28 passed、0 failed、退出码 0**，测试前后哈希与冻结预期一致 |

新增测试采用 PostCSS 解析 <=650px 规则验证分区/滚动/44px 契约，另用真实 document 挂载检查左六右五按钮保留及 tools/log 独立事件分派；不把这些组件断言当作真实点击几何证明。`git diff --check` 通过。

冻结证据工件：

- `D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907.py`
- `D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907T022640584119+0800.log`
- `D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907T022640584119+0800.json`

脚本的实际命令及逐用例 Vitest JSON 均保存于上述日志；复现入口：

```powershell
$env:PYTHONUTF8='1'
& 'D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe' -B 'D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907.py'
```

本次 Rails 修复只提交正常代码，没有任何磁盘反向变异；冻结脚本 `disk_mutation=false`、`memory_mutation=false`。尚未新增 Shell/Rail 内存变异证据，不将此前磁盘结果计作内存验证。此后源码冻结；本报告更新没有重跑测试、启动浏览器或修改源码。

## 7. 最终真实浏览器结果（主代理执行，本任务读取核验）

证据：`D:\小说写作\xuanqiong-wenshu\logs\ui006-focus-real-browser-final-20260907.json`。

- `passed=true`、`consoleErrors=[]`。
- fixture：`workspace-focus-fixture.html`。
- 原始 scope：`Real Shell and Rail with simple slots, not full API-backed workspace`。
- 五视口宽度：390、650、651、960、1440px；所有记录中的 opened/closed/escaped 均无页面横向溢出，左右 rail 包围盒无重叠。
- <=960px 打开左抽屉后焦点为关闭按钮；1440px 保留桌面行为，焦点仍在 tools 触发按钮。各视口关闭后回到左 tools，Escape 后回到右 quality。
- 651→650：归一化前左右同时打开，焦点在 activity 按钮；归一化后右抽屉隐藏、宽度为 0，左侧保留，焦点回到右 log 轨道按钮。

| 视口宽度 | 左 rail 右边界 | 右 rail 左边界 | 结论 |
|---:|---:|---:|---|
| 390 | 183.323 | 191.344 | 无重叠 |
| 650 | 313.323 | 321.344 | 无重叠 |
| 651 | 62.396 | 573.604 | 无重叠 |
| 960 | 62.396 | 882.271 | 无重叠 |
| 1440 | 68.000 | 1368.000 | 无重叠 |

390px 的两个 rail clientWidth 均为 173，scrollWidth 分别为 303/254，证实两个分区确实存在独立横向滚动内容。主代理此前另反馈 tools 经滚动后中心 hit 命中自身、宽度 44px，quality 可达；该中心命中结果属于用户反馈，最终 JSON 主要保存焦点、面板状态、rail 几何及滚动宽度，并未包含该次 elementFromPoint 原始字段。

JSON 的 `left`/`right` 字符串是 aria-hidden 状态：`"false"` 代表显示，`"true"` 代表隐藏，不能反向解读。

**范围限制：** 此最终结果证明 Shell + 真实 Rail 的简单 slots fixture 交互及布局；不声称完整 API 工作台、真实消息/审批链、CARD071 原五视口滚动隔离、全部原生 Tab 顺序或全站响应式均已验收。第 3 节 CARD071 仍只完成收集检查，两组五视口集合不同，应分开记账。

## 8. 最终冻结指纹与证据完整性

以下指纹于报告最终更新前只读核验，与冻结定向 JSON 的 `after_hashes` 完全一致；Shell 的旧 `d417…` 指纹属于 Rails CSS 修复前的历史状态，由本节最终指纹取代。

| 文件绝对路径 | SHA-256 |
|---|---|
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.vue` | `15a08dc1ed220e7d98a090d4349136caed11cd06c6647c1398bc9f6e823830c3` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentWorkspaceShell.spec.ts` | `5d43a61462f538ca8c32a5f84507d6c01e07e2d51cd69375a36f5af1bd2883bd` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\layout\AgentRail.vue` | `f8937fe304fe2e1687eef12c82bc61e244c3df3b6bf832a1f1603d21d7510985` |
| `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\layout\AgentRail.spec.ts` | `5c18de1dd0331e78c50691253db5d3c5a7ba67875236de76fe24c6c8ac852a95` |

最终证据文件指纹：

| 文件绝对路径 | SHA-256 |
|---|---|
| `D:\小说写作\xuanqiong-wenshu\logs\ui006-focus-real-browser-final-20260907.json` | `899d1f97cea1871a7ad8c4364d0a0996de28165721229bce4e9d06a8be096f0f` |
| `D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907T022640584119+0800.json` | `c11abc219d083b0c122f1d93b866beee97a30150b839a3bf08ea13aab0423125` |
| `D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907T022640584119+0800.log` | `c8587ced1948b9309970143b9e4c8417f8bd41e0463dd1a4622ea230f2b44911` |
| `D:\小说写作\xuanqiong-wenshu\logs\shell-rail-freeze-evidence-20260907.py` | `ddfdd212ad452fd99d8f2ee7b16e0b45a0e5c442ca61433bc2fcd85952406f7e` |

交付状态：正常源码保持冻结，报告更新完成，本任务结束。没有前端全量、后端测试或新的源码变异。

## 9. 主代理最终内存反向与原生Tab证据

主代理在后端全量自然结束后补跑5类**加载期内存变异**，没有改写共享Shell/Rail文件，也不触发Vite HMR。驱动与逐条失败JSON均持久化：

- `D:\小说写作\xuanqiong-wenshu\logs\ui006-shell-rail-memory-mutation-20260907.mjs`
- `D:\小说写作\xuanqiong-wenshu\logs\ui006-shell-rail-memory-{case}-20260907.log`
- `D:\小说写作\xuanqiong-wenshu\logs\ui006-shell-rail-memory-{case}-summary-20260907.json`

| 变异 | 实际预期断言失败 |
|---|---:|
| openFocus：去掉打开聚焦 | 3 |
| closeFocus：去掉关闭返回 | 7 |
| resizeFocus：去掉断点归一化返回 | 1 |
| railScroll：去掉横向滚动裁剪合同 | 1 |
| railShrink：允许flex压缩按钮 | 1 |

每轮要求替换点唯一且实际命中、无运行/收集错误、无TypeError/ReferenceError/SyntaxError，Shell与Rail源码hash前后一致。raw CSS导入在同一Vite pre-load插件内变异，所以CSS合同回归确实检查损坏内容；没有在磁盘注入替代源码。CSS合同变异不等同真实几何变异，390px几何故障/修复另有真实浏览器证据。

原生键盘行为实测：390px左抽屉关闭按钮→Tab→侧栏输入→Tab→主栏输入→Shift+Tab→侧栏输入。断言通过，证明当前独立Shell页面没有安装焦点陷阱：

`D:\小说写作\xuanqiong-wenshu\logs\ui006-native-tab-browser-20260907.json`

此前共享磁盘变异记录继续保留为历史，不再作为后续推荐方式。新内存驱动可复跑，最终前端全量/type/build由主代理串行执行并在当前状态入口更新。
