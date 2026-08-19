# 玄穹文枢：领域 C 前端生产级重构审查与验收计划

> 范围：前端工作台、左侧导航、右上角进度卡、SSE 正文/日志分流、配置体验、响应式、可访问性、主要视图和组件。
> 性质：**只审查，不修改业务代码**。以下结论以当前源码和本轮实测为准，不采信旧报告。
> 审查日期：2026-08-14
> 工作区：`D:\小说写作\xuanqiong-wenshu`

---

## 1. 当前基线

### 1.1 覆盖范围

本轮覆盖路由、App 壳、鉴权、全局导航、首页、项目列表、创建、TXT 导入、删除、灵感对话、蓝图、小说详情、左侧 section 导航、总纲、章节纲、世界观、角色、关系、章节、研究、线索、伏笔、知识图谱、情绪分析、写作台、章节生成、正文流、日志、取消、恢复、评审、候选、定稿、编辑、差异、补丁、阅读器、文风中心、LLM 设置、系统配置、管理台、API、Pinia、TaskRuntime、SSE、共享 UI、样式、响应式、可访问性和测试。

### 1.2 规模与门禁实测

- Vue 文件：101 个；TypeScript 文件：79 个；`*.spec.ts`：40 个。
- 当前前端未提交改动全部保留；本轮没有回滚、覆盖或删除业务代码。
- `npm run type-check`：**通过**。
- `npm run build-only`：**通过**，Vite 生产构建约 1 分 13 秒。
- `npm run test:run`：本次 120 秒窗口内未稳定收敛，出现 EPIPE；**不能视为全绿**。
- 浏览器真实流程、Lighthouse、axe、窄屏和长文性能：本轮**未验收**。

`frontend/vite.config.ts` 已把 Vitest worker 固定为单 worker，说明 Windows 转换缓存/资源竞争曾造成假超时风险；该配置不能替代全量测试稳定通过。后续须分批、单进程、可重复执行，禁止仅延长 timeout、删测试或降低标准。

---

## 2. 当前信息架构树

```text
玄穹文枢 App
├─ App.vue
│  ├─ GlobalNavBar.vue                 顶部全局导航、最近项目、旧式任务条
│  ├─ RouterView
│  ├─ CustomAlert.vue                  全局确认/警告
│  └─ GlobalNotification.vue           Toast
├─ /                                    WorkspaceEntry.vue
│  ├─ 最近项目、灵感、项目、文风、管理、系统设置、LLM 设置
├─ /workspace                           NovelWorkspace.vue
│  ├─ 搜索/排序/筛选、新建、TXT 导入/轮询/取消、删除、进入项目
├─ /inspiration                         InspirationMode.vue
│  ├─ 多轮对话、动态 UIControl、会话恢复、蓝图任务确认
├─ /detail/:id                          NovelDetail.vue -> NovelDetailShell.vue
│  ├─ 左侧 section 导航
│  ├─ overview / world_setting / novel_outline / characters
│  ├─ relationships / chapter_outline / chapters
│  ├─ emotion_curve / story_trajectory / creative_guidance
│  ├─ comprehensive_analysis / research / clue_tracker
│  ├─ foreshadowing / knowledge_graph / memory_management / token_budget
│  └─ 编辑弹窗、章节新增、演化大纲
├─ /novel/:id                           WritingDesk.vue
│  ├─ WDHeader.vue、WDSidebar.vue、WDWorkspace.vue
│  ├─ FloatingProgressCard.vue
│  ├─ ChapterContent / ChapterGenerating / ChapterFailed
│  ├─ VersionSelector
│  └─ 生成、评审、定稿、差异、补丁、记忆、Token、技能、文风、阅读器弹窗
├─ /novel/:id/read                      NovelFullReaderView.vue
├─ /style-center                        StyleCenterView.vue
├─ /llm-settings                        SettingsView.vue -> LLMSettings.vue
├─ /settings                            SystemSettingsView.vue -> SettingsManagement.vue
├─ /admin                               AdminView.vue
│  ├─ statistics / diagnostics / prompts / novels
│  ├─ runtime-logs / logs / settings / llm-settings
└─ /admin/novel/:id                     AdminNovelDetail.vue
```

目标架构：

```text
应用壳
├─ 左侧主导航：创作、项目、资料、风格、设置、监控
├─ 右上角任务中心：当前任务、多任务切换、取消、恢复、日志
├─ 项目上下文条：项目名、章节、配置版本、同步状态
├─ 主工作区：只展示当前任务需要的信息
└─ 项目/管理二级导航：URL 可恢复、键盘可用、权限清晰
```

当前差距：详情和管理台已有左侧导航，但首页、项目列表、系统设置、LLM 设置、文风中心仍有各自顶部工具带；`GlobalNavBar` 的 `global-task-mini` 与写作台 `FloatingProgressCard` 形成双进度入口。

---

## 3. 页面→store→API→TaskRuntime 逻辑链

### 3.1 当前链路

```text
用户操作
  ↓
Vue View / Component
  ↓
局部 ref / Pinia novel store / auth store
  ↓
API client(fetch + buildAuthHeaders)
  ↓
后端路由
  ├─ 立即 JSON
  ├─ 旧式 run_id + status 轮询
  └─ TaskRuntime task_id + events + stream
  ↓
currentProject / 局部状态投影
  ↓
进度、正文、日志、错误、产物展示
```

### 3.2 生产目标链路

```text
用户操作 -> domain component/store -> 统一 taskClient
  -> create/get/list/cancel/retry/resume/replay/stream
  -> TaskRuntime 持久化真相源
  -> 按 task_id + event_id 幂等 reducer
  -> status/progress/log/content_delta 四个投影
  -> 任务卡、正文流、日志流、终态动作
```

### 3.3 当前评分

| 功能 | 评分 | 当前证据 |
|---|---:|---|
| 类型边界 | 78 | `api/types/novel.ts` 已集中类型，但 `novel.ts`、`novel-client.ts`、`admin.ts` 仍有历史模型 |
| Pinia 集中度 | 62 | 章节主状态在 `novel` store，研究/文风/导入/任务大量留在视图 ref |
| TaskRuntime 覆盖 | 48 | 写作台已接入，蓝图/研究/文风/导入主要仍用独立 run_id |
| 事件幂等 | 68 | 写作台按 task_event_id 合并，尚无跨任务共享 reducer |
| 正文/日志分流 | 72 | `extractContentDelta` 已限制 `content_delta`，管理日志未接同一实时流 |
| 配置追溯 | 55 | 有配置版本 API 类型，任务详情未完整展示闭环 |
| 响应式 | 67 | 写作台/管理台已有移动布局，详情和密集区未实测 |
| 可访问性 | 54 | 有部分 aria/role，焦点、状态播报、模态框语义未系统化 |

---

## 4. 功能域审查总表

| 域 | 当前页面/组件 | 当前链路 | 关键风险 | 优先级 |
|---|---|---|---|---|
| C01 应用壳/鉴权 | `App.vue`、router、`auth.ts` | route → guard → view → auth/API | 401、错误边界、全局入口不统一 | P0 |
| C02 项目管理 | `WorkspaceEntry.vue`、`NovelWorkspace.vue` | store → NovelAPI → project cache | 导入未进 TaskRuntime；格式口径不一致 | P0 |
| C03 灵感/蓝图 | `InspirationMode.vue`、`BlueprintConfirmation.vue` | conversation/blueprint API → 局部轮询 | 时间型假进度、刷新恢复不足 | P0 |
| C04 详情/左导航 | `NovelDetailShell.vue` | section → API → local section state | 请求竞态、字段映射弱、容器过大 | P1 |
| C05 总纲/章节纲 | outline sections、生成 modal | outline API/job → project blueprint | UI 字段与实际上下文接线未证实 | P0 |
| C06 写作台布局 | `WritingDesk.vue`、`WD*` | store → child emit → API/runtime | 父组件高耦合、四套状态投影 | P0 |
| C07 正文/SSE/日志 | `ChapterGenerating.vue`、`sseStream.ts` | TaskRuntime → replay/SSE → reducer | 管理端未共用；长文性能未测 | P0 |
| C08 右上角进度卡 | `FloatingProgressCard.vue`、GlobalNav | runtime → UI model → card | 顶部旧任务条并存；多任务不足 | P0 |
| C09 评审/定稿/编辑 | VersionSelector、各 modal | chapter APIs → project merge | 原子一致性、长文差异性能未测 | P0 |
| C10 阅读/导出 | reader、`docx` 依赖 | project/chapter → reader/export | 主流程导出入口和任务闭环不清 | P1 |
| C11 文风中心 | `StyleCenterView.vue` | OptimizerAPI → run_id 轮询 | 未进 TaskRuntime；profile 版本不可见 | P1 |
| C12 LLM/系统配置 | `LLMSettings.vue`、settings | config API → local form → next task | 保存版本与任务快照未闭环 | P0 |
| C13 研究资料 | `ResearchCenterSection.vue` | research API → run_id 轮询 | 刷新丢任务、prompt 输入、成本控制 | P0 |
| C14 连续性工具 | 伏笔/线索/图谱/情绪/分析 | feature API → local data | 是否回灌正文不透明；疑似未接按钮 | P1 |
| C15 管理台/运行日志 | `AdminView.vue`、RuntimeLog | AdminAPI → polling | 非统一实时流、权限/脱敏需验收 | P0 |
| C16 UI/样式/无障碍 | shared ui、tokens、main.css | 组件 → CSS/Naive/Tailwind | 多套设计系统、卡片臃肿、焦点不统一 | P1 |

---

## 5. 各功能域详细审查与验收标准

### C01 应用壳、路由、鉴权和全局反馈

**现状与链路：** `App.vue` 挂载 `GlobalNavBar`、RouterView、CustomAlert、GlobalNotification；`router/index.ts` 有懒加载、管理员 guard 和 chunk reload guard；`stores/auth.ts` 用 localStorage token，登录后请求当前用户。

```text
route -> guard -> view mount -> auth bootstrap -> fetch + Authorization
     -> 局部错误或全局通知
```

**风险与计划：** fatal error 只进入 ref，模板没有完整可恢复错误页；401 失效、重新登录、跨标签注销不统一；全局入口重复。建立 auth bootstrap 单例、401 invalidation、错误边界（重试/返回/诊断）和全局 task store。

**验收：** 首次启动、刷新、token 失效、普通用户访问管理路由、懒加载失败均有可见结果；不产生无限请求；错误可重试/返回；任务仍可恢复查询。

### C02 首页、项目列表、创建、导入和删除

**现状与链路：** `WorkspaceEntry.vue` 显示最近 5 个项目；`NovelWorkspace.vue` 提供搜索、排序、筛选、新建、TXT 导入、取消、删除；`novel` store 管理项目列表；`novel-client.ts` 提供导入 start/status/cancel，另有旧式 `importNovel`。

```text
WorkspaceEntry/NovelWorkspace -> novel store -> NovelAPI -> project cache
TXT input -> startNovelImport -> local run_id + setTimeout 轮询 -> status -> 跳转/错误
```

**风险与计划：** 导入未进 TaskRuntime，刷新丢本地 run_id；工作台 input 主要限制 `.txt`，其他文案宣称更多格式；多处项目缓存无统一失效；删除回滚需真实验证。改为 TaskRuntime 导入任务、事件回放、产物 ref 和统一项目缓存失效。

**验收：** 创建后首页/列表/详情/写作台一致；导入刷新可恢复、取消不可转成功；格式支持矩阵与 input/API 一致；删除失败不静默丢项目。

### C03 灵感对话、UIControl 和蓝图

**现状与链路：** `InspirationMode.vue` 使用 `novelStore.sendConversation/createProject/loadProject`，局部保存消息/UIControl；`BlueprintConfirmation.vue` 启动 job 后 2 秒轮询，同时有后端进度、时间型 `progressTimer` 和 timeout。

```text
对话 -> store -> converseConcept -> conversation_state/UIControl -> local messages
蓝图 -> startBlueprint -> project status polling -> local progress -> save/跳转
```

**风险与计划：** 本地时间进度可能超过真实阶段；蓝图刷新恢复不足；会话状态在 view/store 之间回退；长篇参数是否全部送达未证明。统一成 blueprint TaskRuntime、事件 reducer、artifact ref、原子保存。

**验收：** 刷新恢复会话/控件；进度只来自持久化任务；取消、失败、重复点击可收敛；总字数、卷数、章节数、目标字数、分段策略在请求和任务详情可核验。

### C04 小说详情壳和左侧导航

**现状与链路：** `NovelDetailShell.vue` 维护 section registry、异步组件、`sectionData/loading/error`，用 `route.query.section` 恢复；普通用户/管理员分别使用 `NovelAPI/AdminAPI`；移动端有遮罩抽屉。

```text
/detail/:id?section=x -> activeSection -> loadSection/fetchAnalysisSection
 -> API -> sectionData -> section component -> edit/add/evolve -> mutation -> reload
```

**风险与计划：** 快速切换/项目切换请求竞态；通用 `updateBlueprint` 字段映射弱；单一大卡片承载大量内容。建立 section registry（权限、缓存、loader）、可取消请求和 mutation rollback。

**验收：** 键盘可操作，选中语义明确，query 可恢复；快速切换不被旧请求覆盖；编辑覆盖成功/非法/拒绝/异常回滚；移动抽屉焦点、Escape、遮罩、滚动锁定正确。

### C05 长篇总纲、章节纲和蓝图展示

**现状与链路：** `NovelOutlineSection.vue` 展示阶段、故事弧、卷、伏笔、世界/角色/势力/资源/情绪/事件/转折；`ChapterOutlineSection.vue`、`ChapterOutlineEditor.vue` 编辑章节纲；`WDGenerateOutlineModal.vue` 提供章节范围、数量、总字数、目标字数、额外要求。

```text
蓝图/总纲 -> section API -> display
章节纲 modal/editor -> store/chapterWorkflow -> job/JSON -> project.blueprint
```

**风险与计划：** 显示字段丰富但不等于生成上下文接线完整；蓝图/章节纲任务协议分叉；长篇展示嵌套卡片过重；修改后连续性快照失效不可见。建立 BlueprintVersion → Volume/Arc/Chapter 依赖 → outline task → artifact/config_version → context invalidation。

**验收：** 可按卷/弧/章节折叠定位；修改后下一任务显示纲要版本/快照；取消/失败不污染旧纲；层级控件键盘可用。

### C06 写作台布局、章节侧栏和主区

**现状与链路：** `WritingDesk.vue` 集中项目加载、章节选择、状态同步、SSE、TaskRuntime hydration、快捷键、弹窗和事件；`WDHeader`、`WDSidebar`、`WDWorkspace` 已有外壳。

```text
/novel/:id -> loadProject -> currentProject -> task context
 -> Header/Sidebar/Workspace -> emit -> parent handler
 -> chapter API/TaskRuntime -> project reload + chapter projection
```

**风险与计划：** currentProject、chapter runtime、TaskRuntime snapshot、local stream 四套投影；父组件高耦合；Header/Workspace 动作重复；窄屏长列表未验收。拆出 project context、chapter selection、task subscription、generation controller、modal controller、workspace projection。

**验收：** 390/768/1024/1280 宽度均可选章和生成；切章不串任务；刷新可恢复；每个主操作唯一，禁用原因清晰。

### C07 章节生成、正文流、日志、取消和恢复

**现状与链路：** `api/task-runtime.ts` 有 get/list/cancel/retry/events/stream；`sseStream.ts` 支持 token、游标、Last-Event-ID、重连和关闭；`WritingDesk.vue` hydrate；`ChapterGenerating.vue` 展示正文和日志；`chapterGeneration.ts` 负责阶段与 `extractContentDelta`。

```text
task_id -> getTask + listEvents(cursor) -> applySnapshot -> chapter runtime
stream -> connectSSE -> cursor/id 去重 -> reducer
content_delta -> streamed body
其他事件 -> logs/progress/review/error
```

**正向证据：** SSE 使用 fetch 可带 Bearer；断线带游标；正文只认 `event_type === content_delta`；刷新后可 hydrate；组件有正文预览、阶段日志、质量、连续性、Token 提示。

**风险与计划：** 默认最大重试 3 次，失败后没有统一手动续接；非法 JSON 直接忽略；旧章节轮询兼容分支仍在；长章逐 token 的 DOM/内存未量化；管理日志未共用流。抽出事件 envelope 校验、task/event reducer、content/log/progress projection，使用分块缓冲和窗口渲染。

**验收：** 断线续接无漏片/重片/乱序；日志不进正文；旧 task、跨项目、迟到终态拒绝写入；取消不可复活；20k 字流不卡顿；刷新/后端重启后可恢复或结构化失败。

### C08 右上角进度卡和等待体验

**现状与链路：** `FloatingProgressCard.vue` 有阶段、百分比、字数、状态、runner、等待文案、取消和关闭；`chapterGeneration.ts` 有 ETA/stall；`GlobalNavBar.vue` 仍有 `global-task-mini` 和 60 秒 `loadProject` 轮询。

```text
runtime -> resolveProjectTaskContext -> buildChapterTaskUiModel -> card
非写作台 -> GlobalNavBar -> interval loadProject -> mini task bar
```

**风险与计划：** 顶部旧条与右上角卡冲突；runner 只能是 UI 动画；多项目只围绕 currentProject；关闭后恢复入口不明确。以 `TaskRuntime.listTasks` 驱动全局 task store、多任务 selector 和统一动作。

**验收：** 顶部不再占整行；卡片不遮正文；百分比来自持久化任务；无心跳显示未更新时长和动作；多项目可切换；reduced-motion 下静态化。

### C09 评审、定稿、编辑、差异和补丁

**现状与链路：** `VersionSelector`、评审/版本/差异/补丁 modal、`ChapterContent` 覆盖主要操作；store 有评审、选择、删除、编辑和局部乐观回滚。

**风险与计划：** 定稿与记忆/时间线/质量结论的原子一致性不可见；`content.length` 字数口径需与后端对齐；弹窗切换旧内容残留；长文差异未基准。统一 version identity、原子终态、弹窗 abort 和长文虚拟化。

**验收：** 失败时版本/选择回滚；定稿后正文、质量、记忆可追溯；切换弹窗不串数据；200k 字阅读/差异不阻塞交互超过 200ms。

### C10 阅读器和导出

**现状与链路：** 有 `/novel/:id/read`、`WDTextReaderModal` 和 `docx` 依赖；源码中尚未发现清晰统一、从主流程进入的 TXT/DOCX/EPUB 导出任务闭环。

```text
writing desk/reader -> project/chapter API -> local reader
```

**风险与计划：** 导出入口/格式覆盖/失败恢复不完整可见；前端生成超长 DOCX 可能阻塞；目录、搜索、位置保存和语义未形成证据。先列格式支持矩阵，再决定后端异步产物或前端小文件导出。

**验收：** 主流程可进入/返回；大文件导出走任务产物；TXT/DOCX 往返检查章节顺序、正文、版本和元数据；阅读器支持键盘和窄屏。

### C11 文风中心、素材、画像和学习批次

**现状与链路：** `StyleCenterView.vue` 处理素材、文件、批次、画像、激活和历史；`OptimizerAPI` 提供 source/profile 操作；页面用局部 run_id 和 setTimeout 轮询。

```text
StyleCenter -> OptimizerAPI -> run_id/status polling -> sources/profile -> active style
```

**风险与计划：** 未进 TaskRuntime；格式文案/input/API 可能不一致；激活 profile 与写作台缺少版本；多项目切换可能回写旧项目。统一任务、产物、profile version 和 project key。

**验收：** 上传/生成/取消/刷新/失败/重试可恢复；激活后写作台显示 profile version；大文件有上传/处理进度；键盘可用。

### C12 LLM、系统配置和即时生效

**现状与链路：** `SettingsView -> LLMSettings` 提供 Provider、Key、模型、拉取、健康检查、自动切换；`api/llm.ts` 有配置版本、模型和健康接口；管理台也有并列入口；生成 modal 主要局部组装 options。

```text
config form -> get/save config -> config version -> next generation request
```

**风险与计划：** 保存值与下一任务实际版本缺少证据；双入口并发保存语义不明；Key masking、错误、空模型和默认值来源需验收；生成配置缺少项目级快照。统一 schema、version、task snapshot 和任务详情投影。

**验收：** 修改 DeepSeek 等模型后下一任务使用新版本且可核验；保存失败不覆盖；Key 不回显/不泄漏；非法 URL、空模型、重复 profile、禁用 provider、冲突保存均有解释。

### C13 研究资料、文献和内容收集

**现状与链路：** `ResearchCenterSection.vue` 有配置、全局/强化/章节研究、取消、artifact；API 有 start/status/cancel/list；页面 1 秒轮询；章节号通过 `window.prompt` 输入。

```text
ResearchCenter -> research API -> run_id/status polling -> artifact/source display
```

**风险与计划：** 刷新丢 run_id；`force: true` 重复成本；研究配置对正文生效版本不可见；原生 prompt 不生产级。接 TaskRuntime，建立去重/成本提示/可访问章节表单。

**验收：** 刷新可恢复；来源有 URL、片段、可信度、层级、交叉来源；配置、运行、结果可追溯；不使用原生 prompt 作为主流程输入。

### C14 记忆、连续性、伏笔、线索、图谱和情绪

**现状与链路：** 记忆/Token 通过写作台 modal；伏笔、线索、图谱、情绪和分析各自请求 API、局部缓存；`KnowledgeGraphView.vue` 的“刷新图谱”和“分析剧情线”源码均绑定 `reload`，疑似未接 `analyzePlotThreads`。

```text
detail section/modal -> feature API -> local data -> analysis display -> manual next action
```

**风险与计划：** 分析是否回灌下一章不透明；任务协议和缓存失效不统一；按钮文案与动作可能不一致；图表文本替代不足。统一 feature task/result/invalidated 状态和“已回灌”标记。

**验收：** 每项显示来源章节、时间、快照、是否回灌；分析按钮命中专用 API；定稿后缓存失效或标记待分析；100+ 章节仍可用，图表可访问。

### C15 管理台、运行日志、诊断、提示词和系统管理

**现状与链路：** `AdminView.vue` 有左侧菜单和 query tab；`RuntimeLogManagement.vue` 主要 `AdminAPI.listRuntimeLogs` + 自动刷新，源码有 SSE ready 注释但当前未见统一实时订阅；诊断也有 interval；提示词、小说、配置、更新日志分组件。

```text
AdminView query.tab -> admin component -> AdminAPI -> local table/card
```

**风险与计划：** 管理日志不是同一 TaskRuntime 实时流；自动刷新与写作台 SSE 重复；正文预览/开发者详情权限、脱敏和项目隔离需证据；admin 类型与普通类型重复。管理端复用 task event reducer 和权限过滤。

**验收：** 管理员看到同一任务实时事件且正文/日志不串；URL 过滤可恢复；event_id 去重；非管理员拒绝且不泄漏详情。

### C16 共享 UI、样式、视觉密度和维护性

**现状与链路：** 有 `shared/ui` 和 `tokens.css`，但页面混用 Tailwind、Material 类、局部 CSS、Naive UI；`main.css` 约 2090 行；构建产物有约 446.90 kB Naive UI、343.54 kB export vendor、200.12 kB chart vendor 块。

**风险与计划：** 多套视觉体系导致按钮/卡片/弹窗/间距不一致；嵌套卡片和大容器仍影响密度；焦点和动效无全局规范。收敛 shared UI/Token、主操作层级、空/错/加载状态和 reduced-motion。

**验收：** 主要页面统一组件；单屏最多两层卡片嵌套；正文优先；reduced-motion、高对比、焦点环、200% 缩放、中文长文本通过。

---

## 6. 未接线按钮与疑似未接线功能清单

以下是基于当前源码的“需要真实浏览器点击确认”的清单，不把疑似问题冒充为已修复：

| 位置 | 按钮/功能 | 当前代码迹象 | 风险/验收动作 |
|---|---|---|---|
| `frontend/src/components/knowledge-graph/KnowledgeGraphView.vue` | “分析剧情线” | 与“刷新图谱”都绑定 `reload` | 点击后必须命中 `KnowledgeGraphAPI.analyzePlotThreads`，并显示任务/结果变化 |
| `frontend/src/components/admin/RuntimeLogManagement.vue` | 实时 SSE | 有 `SSE ready` 注释，但实际主要自动刷新 | 生成任务时检查是否实时到达、是否按 event_id 去重 |
| `frontend/src/components/GlobalNavBar.vue` | 右上角/全局任务恢复 | `global-task-mini` 只有回到写作页语义 | 非写作台验证多任务、取消、恢复、日志入口是否真实存在 |
| `frontend/src/views/NovelWorkspace.vue` | 导入格式 | input 实际主要 `accept=.txt` | docx/epub 等文案是否可用必须按格式逐项点击验收 |
| `frontend/src/views/StyleCenterView.vue` | 素材/画像后台任务 | 依赖局部 run_id 和轮询 | 刷新页面验证任务是否还在、是否能取消/恢复 |
| `frontend/src/components/novel-detail/ResearchCenterSection.vue` | 研究后台任务 | 依赖局部 run_id 和轮询 | 刷新、断线、重复点击、取消竞态验收 |
| `frontend/src/components/BlueprintConfirmation.vue` | 蓝图真实进度 | 同时有后端状态和本地时间 progressTimer | 人为延迟后端响应，确认百分比不超越真实阶段 |
| `frontend/src/views/SettingsView.vue` / `LLMSettings.vue` | 配置即时生效 | 有保存/version API，但任务详情闭环未见 | 修改 DeepSeek 后启动任务并核对 provider/model/version |
| `frontend/src/views/WritingDesk.vue` | 快捷键自定义 | 表单保存显示配置，但需确认是否改变监听逻辑 | 修改快捷键后实际触发并刷新验证 |
| `frontend/src/components/shared/NovelDetailShell.vue` | 记忆/Token/文风入口 | 异步 modal 和 section 入口并存 | 每个按钮点击后核对真实 API、项目 ID 和回写状态 |
| `frontend/src/views/NovelWorkspace.vue` / reader | 导出入口 | 发现依赖和阅读器，未形成清晰统一导出链 | 从主流程实际寻找并执行 TXT/DOCX 导出 |

---

## 7. 分块优化计划

### Block C0：统一任务协议与投影（P0）

定义 `TaskEnvelope/TaskEvent/TaskProjection`；按 `task_id + event_id` 幂等；统一 queued/running/cancelling/cancelled/succeeded/failed/stale；建立按用户/项目/章节索引的 task store；将旧 run_id 适配为兼容层。

**完成条件：** 蓝图、研究、文风、导入、正文、日志都消费统一 projection；刷新、回放、终态不可复活测试通过。

### Block C1：SSE 与正文/日志分流（P0）

增强 `sseStream.ts` 的 heartbeat、HTTP 分类、手动续接、缺口回放、运行时 schema 校验和解析诊断；正文只允许 `content_delta`；日志消费非正文事件；长文用分块缓冲/窗口渲染；写作台和管理台共用订阅器。

**完成条件：** 断线、乱序、重片、跨 task、迟到终态测试通过。

### Block C2：右上角任务中心（P0）

移除顶部常驻任务条语义；`TaskRuntime.listTasks` 驱动全局 task store；右上角展示真实阶段、百分比、心跳、耗时、ETA、等待原因、预算、诊断和动作；支持多任务切换、取消、恢复、重试、日志；适配窄屏/reduced-motion。

**完成条件：** 卡片不遮正文，多项目可切换，进度只来自持久化任务。

### Block C3：写作台拆分与连续生成（P0/P1）

拆出项目上下文、章节选择、任务订阅、生成控制、弹窗、快捷键、状态同步；收敛 Header/Sidebar/Workspace 接口；明确切章、刷新、返回、后台运行；统一质量门/评审/定稿；长章按段展示。

**完成条件：** 浏览器完成 1—10 章连续生成、刷新、取消、恢复、定稿。

### Block C4：蓝图/章节纲/研究/文风/导入统一（P0/P1）

每类任务具备 create/status/events/result/ref；移除时间型假进度；持久化 project/user/config version/artifact ref；统一任务卡/日志；重复提交使用幂等键或动作锁。

**完成条件：** 刷新、断线、取消、恢复、重复提交、跨项目隔离自动化通过。

### Block C5：左侧导航和信息架构（P1）

形成全局左侧导航：创作、项目、资料、风格、设置、监控；详情/写作台保留项目级二级导航；query/params 恢复状态；移动抽屉统一焦点、Escape、遮罩和滚动锁定。

**完成条件：** 主要流程任一步刷新都能恢复同一页面上下文。

### Block C6：配置体验和任务追溯（P1）

统一 LLM/系统/项目/章节配置 schema、默认值、校验、保存和版本；任务显示 provider/model/prompt/params/style/research/context snapshot；处理并发冲突、脱敏和回滚。

**完成条件：** 修改 DeepSeek 后下一任务实测使用新版本，任务详情可核验。

### Block C7：响应式、可访问性、视觉密度（P1）

收敛 shared UI/Token；统一按钮、面板、加载/错误/空状态；实测 390/768/1024/1280/1440；补 aria-current、aria-live、aria-busy、dialog focus trap、label/description、图表文本替代；支持键盘、200% 缩放、高对比、reduced-motion。

**完成条件：** axe 无严重/高危问题；键盘完成核心流程；无主要溢出和遮挡。

### Block C8：发布门禁和真实验收（贯穿）

Vitest 分批单进程记录耗时；补路由/任务/SSE/权限交互测试；使用隔离后端和真实 DeepSeek；记录 task ID、event 数、正文长度、配置版本、恢复结果、截图/trace。

**完成条件：** 前端三门禁连续两轮通过，核心浏览器流程无 P0。

---

## 7. 真实浏览器验收流程

### F1：创建项目到短章定稿

首页 → 灵感模式 → 创建项目 → 完成一轮对话 → 生成蓝图 → 进入详情核对总纲/章节纲 → 进入写作台 → 选择 DeepSeek 和章节参数 → 生成短章 → 同屏核对正文流与日志分区 → 评审/候选/定稿 → 刷新。

**通过标准：** 不依赖开发者工具补状态；每个主动作有 loading、成功或结构化失败；正文没有日志、JSON、模型元文本；刷新后章节、任务和定稿状态一致。

### F2：SSE 断线、刷新、取消、恢复

启动生成 → 断开网络或 SSE → 观察右上角任务卡 → 恢复网络 → 游标续接 → 刷新页面 → `TaskRuntime` 查询和事件回放 → 取消 → `cancelling/cancelled` → 对可恢复失败任务执行 retry/resume。

**通过标准：** 正文无漏片、重片和乱序；日志不进正文；取消后不回到 running/succeeded；刷新后能恢复或显示明确失败，不整章回退重写。

### F3：双项目并发隔离

项目 A 和项目 B 分别启动章节生成 → 切换项目 → 切换右上角任务卡 → 分别查看正文、日志、进度、错误和产物 → 分别取消或完成。

**通过标准：** project_id、chapter_id、task_id、正文、日志、配置、产物完全隔离；一个项目失败不会改变另一个项目的 UI 终态。

### F4：长篇连续生成

长篇总纲 → 分卷/章节纲 → 第 1 章定稿 → 第 2—10 章连续生成 → 每章查看前序摘要、人物、伏笔、时间线和最近快照 → 中途刷新、切章、回读和继续。

**通过标准：** 章节顺序不乱；下一章任务显示实际读取的上下文快照/纲要版本；不存在只在当前 Vue 页面内存中保留的关键连续性状态。

### F5：配置即时生效

LLM 设置 → 选择 `deepseek-v4-flash-free` → 保存 → 记录配置版本 → 写作台修改字数、分段、候选、文风、提示词和账本开关 → 启动任务 → 查看任务详情。

**通过标准：** 任务详情可核对 provider、model、config version、prompt/profile/context snapshot 和生成参数；旧任务不被新配置改写；保存失败不覆盖已生效配置。

### F6：研究、文风、旧稿导入和管理日志

启动研究/文风素材上传/画像生成/TXT 导入 → 离开页面或刷新 → 右上角任务卡恢复 → 查看来源/画像/导入产物 → 管理员打开运行日志 → 对照写作台同一任务事件。

**通过标准：** 四类后台任务均可查询、取消、恢复、重试；任务不因离开页面卡死；管理台与写作台事件按 event_id 一致且不重复。

---

## 8. 性能验收指标

| 指标 | 目标 | 证据 |
|---|---:|---|
| 首页 LCP | 冷缓存/热缓存分别 ≤ 2.5s | Lighthouse 生产预览报告 |
| 路由点击反馈 | ≤ 100ms 显示 loading | 浏览器 Performance trace |
| 主页面可交互 | ≤ 3s | Lighthouse/trace |
| SSE 事件到 UI | P95 ≤ 200ms | 事件时间戳与浏览器 trace |
| 1000 事件回放 | 主线程单次阻塞 ≤ 200ms | Performance long task 记录 |
| 20,000 字正文流 | 无明显输入/滚动卡顿 | 真实长章 trace、内存快照 |
| 200,000 字项目 | 阅读/章节列表不崩溃 | 浏览器长文流程 |
| 5 个并发任务 | 任务切换 ≤ 100ms | 多项目 trace |
| SSE 断线检测 | ≤ 5s，并提供手动续接 | 断网流程记录 |

构建基线中已见较大 vendor chunk：Naive UI 约 446.90 kB、export vendor 约 343.54 kB、chart vendor 约 200.12 kB（Vite 输出的未压缩值）。后续必须记录 gzip、首屏加载和路由实际使用情况，不能只看 build 成功。

---

## 9. 可访问性与响应式验收

1. 仅用键盘可以完成导航、项目进入、生成、取消、恢复、定稿、section 切换和弹窗关闭。
2. Tab 顺序符合视觉顺序；弹窗打开后焦点进入，关闭后返回触发按钮；移动抽屉支持 Escape、遮罩关闭和滚动锁定。
3. 导航使用 `aria-current` 或等价选中语义；生成进度使用 `aria-live`/`aria-busy`，正文 token 不逐个造成屏幕阅读器噪声。
4. 所有输入有 label/description；错误、空状态、禁用原因和重试动作可被读出。
5. 图表、知识图谱和长篇结构提供文本摘要或等价列表，不以颜色作为唯一信息。
6. 通过 390、768、1024、1280、1440px 宽度；无横向溢出、主按钮遮挡正文或任务卡遮挡编辑区。
7. 支持 200% 浏览器缩放、高对比度、中文长文本和 `prefers-reduced-motion`。
8. axe 无严重/高危问题；核心流程有键盘录制或可复现步骤。

---

## 10. 发布门禁与领域 C 结论

每个功能域按 100 分评分：功能可用性 25、任务一致性 20、数据/连续性 20、错误恢复 15、性能 10、可访问性 5、测试证据 5。C03、C05、C06、C07、C08、C12 任一低于 90 分不得进入发布阶段。

发布前必须满足：

1. `npm run type-check`、`npm run test:run`、`npm run build-only` 连续两轮通过。
2. 无永久卡死、静默失败、取消复活、跨项目数据泄漏、刷新后任务丢失。
3. 真实 Provider 完成短章、10 章连续、长章分段、双项目并发、配置即时生效和任务刷新恢复。
4. 正文与日志严格分流；管理日志与写作台使用同一事件语义。
5. 所有核心功能 ≥90/100；剩余限制有用户可见提示、重试路径和审计记录。

**领域 C 当前结论：** 前端已有完整页面骨架，写作台已出现 TaskRuntime、SSE 游标续接、正文/日志分流和右上角进度卡实现；但不能宣称生产级。当前 P0 是任务协议分叉、全局任务中心、管理日志实时流、配置版本追溯、多项目真实隔离和全量 Vitest 稳定性。

## 11. C 领域证据路径

- `frontend/src/App.vue`
- `frontend/src/router/index.ts`
- `frontend/src/stores/novel.ts`
- `frontend/src/stores/auth.ts`
- `frontend/src/api/novel-client.ts`
- `frontend/src/api/novel.ts`
- `frontend/src/api/task-runtime.ts`
- `frontend/src/utils/sseStream.ts`
- `frontend/src/utils/chapterGeneration.ts`
- `frontend/src/views/WritingDesk.vue`
- `frontend/src/components/writing-desk/layout/WDWorkspace.vue`
- `frontend/src/components/writing-desk/widgets/FloatingProgressCard.vue`
- `frontend/src/components/writing-desk/workspace/states/ChapterGenerating.vue`
- `frontend/src/components/shared/NovelDetailShell.vue`
- `frontend/src/views/NovelWorkspace.vue`
- `frontend/src/views/InspirationMode.vue`
- `frontend/src/views/StyleCenterView.vue`
- `frontend/src/components/novel-detail/ResearchCenterSection.vue`
- `frontend/src/components/admin/RuntimeLogManagement.vue`
- `frontend/vite.config.ts`
