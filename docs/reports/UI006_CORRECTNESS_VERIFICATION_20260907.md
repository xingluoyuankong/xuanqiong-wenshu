# UI006 推理卡片正确性验证 — 2026-09-07

## 结论

阶段四初版的有界窗口有实际缺陷，并非补文档即可验收。修正版已通过卡片13项测试、前端全量585项、type-check和构建；6类加载期内存变异全部检出；真实Vue页面10阶段几何断言通过。此结论只覆盖推理卡片与Run身份传递，不覆盖完整工作台窄屏焦点、全部性能指标或文学质量。

## Evidence → Finding → Path

| 证据 | 实际发现 | 修复与验收路径 |
|---|---|---|
| `D:\小说写作\xuanqiong-wenshu\logs\ui006-correctness-before-20260907.log` | 新增4项全部失败：7000超界渲染120项、text-only无pre、折叠保留20项、前插scrollTop仍1000而非3050 | 二分窗口/超界钳制、正文fallback、折叠卸载、稳定段内锚点；原4条保留 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui006-correctness-final-20260907.log` | 13项通过，含observer重测/释放、流式同段增长、Run切换、复制失败与计时器清理、Ctrl+Home/End | 主组件与真实父组件传递回归 |
| `D:\小说写作\xuanqiong-wenshu\logs\frontend-full-after-ui006-c2-20260907.log` | 中间全量584通过/1失败：jsdom无scrollHeight被当作到尾 | onScroll采用实际高度或虚拟高度回退；保留失败与阈值 |
| `D:\小说写作\xuanqiong-wenshu\logs\frontend-full-after-ui006-c2-r2-20260907.log` | 81文件585通过，110.04秒 | 修复后全量，不跳过失败项 |
| `D:\小说写作\xuanqiong-wenshu\logs\ui006-typecheck-final-r2-20260907.log` | type-check通过 | Vue模板ref与父props真实编译 |
| `D:\小说写作\xuanqiong-wenshu\logs\frontend-build-after-ui006-c2-r2-20260907.log` | 构建16.60秒，exit0 | 正式构建，不替换为dev编译 |

## 实现边界

主要文件：

- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.spec.ts`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue`

绝对定位代替spacer/grid gap混算，累计高度与实际行间距统一9px。宽度变化清理旧测量，行内容变化使旧高度失效；ResizeObserver主动更新测量。窗口外DOM卸载后unobserve，折叠回收窗口；完整数据仍用于复制。显示区域使用可聚焦容器，Ctrl/Meta+Home/End与条件尾随保持窗口状态同步。

`contextKey`由activeRun.id经AgentConversation传入；row key同时包含Run、id或sequence+chunkIndex。显式Run切换清理展开、锚点和高度。没有修改历史请求generation、游标、去重与C2隔离实现。

不宣称整算法成为常数时间：累计layout仍为O(n)，displayText仍可能全文join；未测堆内存峰值、帧率或超大单段开销。

## 内存反向验证

驱动：`D:\小说写作\xuanqiong-wenshu\logs\ui006-memory-mutation-20260907.mjs`。

Vite `enforce: pre` 在加载`.vue`时替换目标字符串，磁盘源码保持不变。最终六轮源码SHA256均为：

`8d9887572aa4f16255d5c553181a8adbc34a8cc1e93a580674ea8c8be1e00acc`

| 变异 | 最终预期失败数 | 断言语义 |
|---|---:|---|
| allRows | 6 | 全量DOM违反窗口边界/首末段语义 |
| noAnchor | 1 | 前插阅读位置不补偿 |
| noResize | 1 | observer触发后第二行top不随高度改变 |
| noTextFallback | 1 | 展开后正文pre缺失 |
| noRecycle | 3 | 折叠或Run切换仍保留正文节点 |
| windowCopy | 2 | 窗口或折叠数据不等于完整复制内容 |

每轮要求变异锚点确实命中、存在断言失败、无运行/收集错误、无TypeError/ReferenceError/SyntaxError，且源码hash一致。缺pre属于预期UI契约失败，不是编译或导入错误。驱动exit0表示反向检查成立，不表示变异实现测试通过。

最终日志命名：`D:\小说写作\xuanqiong-wenshu\logs\ui006-mutation-{case}-final-20260907.log`，对应JSON和summary JSON同目录。

复跑：

```powershell
Set-Location -LiteralPath 'D:\小说写作\xuanqiong-wenshu'
$env:UI006_EVIDENCE_TAG = 'review-20260907'
node 'D:\小说写作\xuanqiong-wenshu\logs\ui006-memory-mutation-20260907.mjs' noAnchor
```

## 真实浏览器验收

- 页面：本次创建的独立Vue fixture；不访问API、Provider或数据库。
- `D:\小说写作\xuanqiong-wenshu\frontend\e2e\reasoning-virtualization-fixture.html`
- `D:\小说写作\xuanqiong-wenshu\frontend\e2e\reasoning-virtualization-fixture.ts`
- 实测JSON：`D:\小说写作\xuanqiong-wenshu\logs\ui006-real-browser-final-20260907.json`
- 可复用E2E用例：`D:\小说写作\xuanqiong-wenshu\frontend\e2e\reasoning-virtualization.spec.ts`。本批实际执行为Codex内置浏览器的UI操作与只读DOM断言，**未把未执行的Playwright CLI用例记为通过**。

正式浏览器断言前登记：锚点/尾部容差2px，行距误差小于1px，DOM行数小于40。

| 阶段 | 观察 |
|---|---|
| collapsed | 0行DOM |
| head | row-100可达，9行DOM |
| middle | row-104，段首相对容器-60.2083px，12行DOM |
| prepend | 前插100段后仍row-104，-60.4063px，差约0.198px |
| narrow | 内容宽度750→330px，仍row-104，-60.2083px；行距约9px |
| tail | row-2099可达，4行DOM，距底0.672px |
| tail-growth | 同一尾段追加30行，1行DOM，距底1.328px |
| no-hijack | Ctrl+Home后继续追加尾部，scrollTop仍0，row-0仍首段 |
| reclaimed | 完成后手动折叠，0行DOM |
| reopened | 重开row-0，7行DOM |

十阶段断言均通过，最终console error为空。早期手工检查还发现原生Ctrl+End落在估算尾部后随着测量产生偏移，现已补显式首尾导航与尾部测量跟随；对应单元回归保留。

## 未闭环事项与下一步

1. 完整工作台650px互斥/焦点/Escape仍需真实多视口验收，独立卡片宽度测试不替代它。
2. 旧CARD071在650px仍要求左右面板同时有宽度，与当前互斥需求冲突；应修改为互斥正反断言并保留五视口，而非删除测试。
3. 未测试巨型单段、堆峰值和长期追加吞吐；有界DOM不等于全部性能目标完成。
4. 全部改动未提交；源码指纹在`D:\小说写作\xuanqiong-wenshu\logs\ui006-corrected-code-fingerprint-20260907.json`。
5. 主目标active、发布NO-GO；继续UI005合同闭环，不重复运行未修改后端的2131项全量。
