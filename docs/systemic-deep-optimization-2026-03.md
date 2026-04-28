# 玄穹文枢系统性深度优化报告（2026-03-26）

## 1. 任务目标

本轮工作不是继续堆叠“看起来更强”的 AI 模块，而是围绕以下四个目标做真正能落地的系统性优化：

- 完整扫描本地仓库，重新确认目录结构、源码规模、主链路和风险点。
- 对照外部成熟 AI 小说写作产品与研究，校准 玄穹文枢 的产品逻辑和工程优先级。
- 直接修复影响商业化质量的关键问题：默认安全策略、首屏性能、数据模型收口、验证链路。
- 更新 README 和报告文档，让后续接手者能够快速理解这轮改动的“为什么”和“怎么验证”。

工作目录：`<repo-root>`

## 2. 仓库扫描结论

### 2.1 目录与技术栈

- `backend/`：FastAPI + SQLAlchemy Async + 多阶段写作流水线 + LLM 服务封装 + 向量检索/RAG。
- `frontend/`：Vue 3 + Pinia + Vite + Naive UI，写作台是核心交互入口。
- `deploy/`：Dockerfile、Compose、Nginx 与部署脚本。
- `docs/`：已有架构融合、工作流、RAG、优化报告等多轮文档沉淀。

### 2.2 核心源码规模

按源码目录粗略统计：

- `backend/app/api/routers`：13 个文件，约 3975 行。
- `backend/app/services`：50 个文件，约 17360 行。
- `backend/app\models`：17 个文件，约 1456 行。
- `frontend/src/components`：61 个文件，约 11258 行。
- `frontend/src/views`：12 个文件，约 2263 行。

这说明 玄穹文枢 已经不是“功能太少”，而是进入了“能力很多，但复杂度开始失控”的阶段。

### 2.3 扫描中发现的显性问题

- 工作树已经存在大量未提交改动，说明项目处于持续迭代中，且不少能力已在半重构状态。
- 后端默认跨域与安全默认值仍偏松，不适合直接进入商业化部署。
- 前端写作台仍在页面层做字符串化章节版本 JSON 解析，说明接口契约没有收口。
- 前端构建虽然能通过，但首屏负载和包体结构仍有明显可优化空间。

## 3. 外部调研与基线判断

本轮调研重点不是“抄竞品”，而是提炼成熟产品和研究里最稳定的能力模型。

### 3.1 产品侧基线

来自 Sudowrite、Novelcrafter 等成熟产品的共同信号：

- 长篇写作一定有稳定的“故事圣经 / Codex / Story Bible”。
- AI 上下文不是把所有设定一股脑塞进去，而是做与当前任务相关的可见性筛选。
- 角色、地点、剧情线、支线、时间线都需要成为正式的一等对象，而不是附属文本字段。
- 用户真正感知的是“我能否沿着清晰流程持续写下去”，不是系统有多少隐藏模块。

### 3.2 研究侧基线

近期长文本故事生成研究反复指向同样的结论：

- 需要动态分层大纲，而不是一次性僵硬大纲。
- 需要长期记忆层或时间知识图谱，避免章节级上下文断裂。
- 需要自动冲突分析和反馈闭环，而不是单次生成后就结束。

这些结论与 玄穹文枢 现有方向是对齐的，问题主要不在“方向错了”，而在“默认路径和工程实现还不够稳”。

## 4. 本轮落地的核心优化

### 4.1 后端默认安全与部署配置收紧

修改文件：

- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/env.example`

本轮做了这些调整：

- 将 `debug` 默认值改为更安全的关闭状态。
- 将 `allow_registration` 默认值改为关闭，避免意外开放注册。
- 在应用启动阶段加入生产环境安全校验：
  - `DEBUG=true` 时拒绝生产启动。
  - 默认管理员密码未更换时拒绝生产启动。
  - `SECRET_KEY` 仍像占位值或长度过短时拒绝生产启动。
- 在开发环境保留启动，但会给出明确安全警告，避免“悄悄带病运行”。
- 显式使用 `CORS_ALLOW_ORIGINS` 和 `cors_allow_credentials_effective`，避免 `* + credentials` 这种既不安全又容易引起浏览器兼容问题的组合。
- 将 `env.example` 同步调整为更符合生产现实的示例值，包括关闭 `DEBUG`、关闭默认注册、压回章节版本数配置。

解决的问题：

- 避免商业部署时因为默认值过松导致的安全事故。
- 避免跨域配置在浏览器与服务端之间出现不一致行为。
- 避免部署文档和实际默认配置继续漂移。

### 4.2 前端首屏性能优化

修改文件：

- `frontend/src/assets/main.css`
- `frontend/src/router/index.ts`
- `frontend/vite.config.ts`

本轮做了这些调整：

- 保持本地字体栈，避免依赖远程字体服务。
- 核心页面全部切为路由级懒加载，写作台不再拖慢入口页和登录页。
- 在 Vite 中增加更细粒度的 vendor 拆包，让 `vue`、`naive-ui`、`chart.js` 等资源不再全挤进同一主包。

这类改动的价值不只是“构建警告更少”，而是：

- 首屏加载更轻。
- 网络慢、跨境网络或私有部署时更稳。
- 写作台不再拖累不相关页面的打开速度。

### 4.3 章节版本数据模型收口

修改文件：

- `frontend/src/api/novel.ts`
- `frontend/src/stores/novel.ts`
- `frontend/src/views/WritingDesk.vue`
- `frontend/src/utils/chapterContent.ts`
- `frontend/src/components/writing-desk/WDVersionDetailModal.vue`
- `frontend/src/components/writing-desk/WDWorkspace.vue`
- `frontend/src/components/writing-desk/workspace/ChapterContent.vue`
- `frontend/src/components/writing-desk/workspace/VersionSelector.vue`

问题本质：

- 后端返回的章节版本历史在前端仍可能是字符串数组。
- 写作台页面里长期混杂着“如果它其实是字符串 JSON 就现场解析”的兼容逻辑。
- 这导致 UI 层承担了数据清洗职责，也带来一堆脆弱判断和历史调试残留。

本轮处理方式：

- 在 `frontend/src/api/novel.ts` 新增统一归一化逻辑：
  - 自动提取字符串化 JSON 中的正文内容。
  - 将 `chapter.content` 与 `chapter.versions[*].content` 统一清洗为可直接渲染文本。
  - 将章节版本统一转为 `ChapterVersion[]`。
  - 所有返回 `NovelProject` / `Chapter` 的接口都在 API 层做标准化。
- 新增 `frontend/src/utils/chapterContent.ts` 作为共享归一化工具，避免“每个组件各写一套 JSON 解析+转义还原”。
- 更新 `Chapter.versions` 的类型定义，让它回到真正的结构化对象数组。
- 更新 store 中的章节编辑乐观更新逻辑，确保版本历史按对象而不是字符串维护。
- 清理写作台页面、版本详情、版本列表、章节正文组件中的重复解析逻辑，让组件只消费规范数据。

效果：

- 页面逻辑更干净。
- 章节版本选择和详情展示更稳。
- 写作台渲染路径减少重复 JSON 解析，交互一致性更好。
- 后续如果继续演进版本元数据，不必再在多个组件里复制兼容代码。

### 4.4 验证链路补齐

修改文件：

- `backend/app/services/test_phase4_integration.py`
- `backend/requirements-dev.txt`

本轮做了这些调整：

- 为现有 Phase 4 smoke tests 增加可直接执行的 `__main__` 入口。
- 新增 `backend/requirements-dev.txt`，把 `pytest` 放入开发依赖而不是运行依赖。

解决的问题：

- 即便在“测试工具尚未安装”的机器上，也可以用 `python backend/app/services/test_phase4_integration.py` 做最小 smoke 验证。
- 需要跑 pytest 时，安装路径也更清楚，不再靠口头约定。

## 5. 验证结果

### 5.1 实际执行命令（2026-03-26）

本轮已实际执行以下命令：

- `.\backend\.venv\Scripts\python.exe -m compileall app`
- `.\backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); import app.main; print('import-ok')"`
- `.\backend\.venv\Scripts\python.exe app\services\test_phase4_integration.py`
- `npm run build`

### 5.2 实际结果

- 后端编译检查通过（`compileall` 成功）。
- 后端应用入口可正常导入（输出 `import-ok`）。
- Phase 4 最小 smoke 套件通过（输出 `Phase 4 smoke suite passed.`）。
- 前端构建与类型检查通过，关键产物为：
  - `dist/assets/index-*.css`：`114.95 kB`（gzip `18.16 kB`）。
  - `dist/assets/WritingDesk-*.js`：`99.38 kB`（gzip `25.12 kB`）。
  - `dist/assets/naive-ui-*.js`：`467.70 kB`（gzip `123.25 kB`）。
- 仍存在环境提示但不阻塞构建：
  - 本机 npm 用户配置存在 `//github.com/.insteadOf` 的兼容性 warning。
  - `baseline-browser-mapping` 依赖提示可升级。

结论：本轮改动在“可构建、可导入、可最小回归验证”层面已经闭环。

## 6. 仍然存在的后续空间

这轮已经解决了“高收益、低副作用”的关键问题，但仍有后续空间：

- `backend/app/core/config.py` 仍可继续向更完整的 Pydantic V2 风格演进。
- 后端 LLM 调用韧性仍有深化空间，例如把限流、空响应、结构化解析失败分层处理得更细。
- 章节 / 剧情线 / 伏笔 / 时间线的可视化产品层还可以继续增强。
- 若未来继续做极致性能优化，可继续按页面拆出更细粒度的写作台组件 chunk。

## 7. 结论

玄穹文枢 当前最需要的不是再加十个新模块，而是让已有能力以更可靠、更清晰、更商业化的方式落地。

本轮优化真正完成的是三件事：

- 把生产环境安全边界补上了。
- 把前端首屏和主路由负担降下来了。
- 把写作台最核心的数据契约收口了。

这三件事不会像“又多了一个 AI 模式”那样显眼，但它们才是决定这个项目能不能走向商业级质量的基础设施。

## 8. 外部参考来源

- Sudowrite 用户反馈与功能更新页：[https://feedback.sudowrite.com/](https://feedback.sudowrite.com/)
- Novelcrafter Help Center（Codex / 自动提取角色）：[https://docs.novelcrafter.com/en/articles/9184520-how-to-automatically-add-characters-to-the-codex](https://docs.novelcrafter.com/en/articles/9184520-how-to-automatically-add-characters-to-the-codex)
- ACL 2025，DOME 长篇故事生成论文：[https://aclanthology.org/2025.naacl-long.63/](https://aclanthology.org/2025.naacl-long.63/)
