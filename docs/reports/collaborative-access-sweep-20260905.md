# Collaborative access sweep — 2026-09-05

## 1. 审计结论

本报告基于当前工作区 `D:\小说写作\xuanqiong-wenshu`、分支 `codex/bohrium-integration-20260831`、HEAD `af9b5eb docs: refresh final quality gate baseline` 的源码、路由、前端实现和定向测试结果生成。范围是 `ProjectMember`/`ProjectAccessService` 迁移后仍可能把项目访问错误收窄为 `NovelProject.user_id` 所有者访问的路径。

结论分三类：

- **已安全**：入口已经调用 `ProjectAccessService`，或旧 `user_id` 只是执行归属/兼容字段，不是访问判断；当前测试有证据支撑。
- **需修复**：成员访问已经是项目级契约，但代码仍使用旧 Owner-only gate，或已完成项目授权后又用所有者字段二次过滤，Editor/Viewer/Admin 会被错误截断或资源被错误隐藏。
- **需人工确认**：该路径确实是项目资源，但是否应向 Editor/Admin/Viewer 开放取决于产品语义，尤其是删除、通用任务控制、审批控制等不可仅靠静态搜索决定。

总体判断：**Agent 只读投影、Writer H-1/H-2、Artifact 读取辅助链、analytics/outline/项目子资源的大多数入口已经迁移；仍有一组可复现的旧 Owner-only 残留，集中在 `novels.py` 老业务路由、`optimizer.py`、`writing_skills.py`、Agent 旧读方法、质量工具、Artifact 接受兼容端点以及通用 TaskRuntime。**

## 2. 证据与命令结果

### 2.1 已执行搜索

```powershell
rg -n --glob '*.py' "ensure_project_owner\(" backend/app --glob '!**/test_*.py'
rg -n --glob '*.py' "project\.user_id|NovelProject\.user_id" backend/app --glob '!**/test_*.py'
rg -n --glob '*.py' "select\(NovelProject\)" backend/app/services backend/app/agent --glob '!**/test_*.py'
rg -n --glob '*.{ts,vue}' "ProjectMemberPanel|projectMembers|/members|can_manage|access_role" frontend/src
```

扫描命中确认：

- `ensure_project_owner` 生产调用点仍位于 `novels.py`、`optimizer.py`、`writing_skills.py`，并由 `core/dependencies.py:get_project_owner_guard` 间接提供。
- 直接 `NovelProject.user_id` 过滤仍位于 `agent/execution_facts.py`、`agent/tool_adapters.py`、`api/routers/task_runtime.py`、`repositories/novel_repository.py`；其中一部分是执行归属或旧列表语义，另一部分是访问 gate。
- Agent 运行服务同时存在 `_run()`（创建者限定）与 `get_readable_run()`/`list_events_readable()`（项目成员可读）两套入口，路由调用混用，是主要残留风险源。

### 2.2 定向后端测试

执行：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q `
  app/services/test_project_access_service.py `
  app/agent/test_execution_facts_member_access.py `
  app/agent/test_tool_adapters_member_access.py `
  app/agent/test_write_executor_member_access.py `
  app/api/routers/test_agent_project_member_http.py `
  app/api/routers/test_project_members_route.py `
  app/api/routers/test_projects_member_access.py `
  app/api/routers/test_knowledge_analytics_member_access.py `
  app/api/routers/test_writer_member_read_access.py `
  app/api/routers/test_writer_member_write_access.py `
  app/api/routers/test_writer_member_generation_control_access.py `
  app/api/routers/test_writer_member_outline_control_access.py `
  app/api/routers/test_writer_member_finalize_access.py `
  app/api/routers/test_writer_member_stream_access.py
```

结果：**115 passed in 47.56s**。

该结果证明当前已迁移的成员访问链路回归通过，但不覆盖本报告列出的全部旧路由。

### 2.3 定向前端测试命令

实际执行：

```powershell
cd D:\小说写作\xuanqiong-wenshu\frontend
npm run test:run -- --runInBand src/api/projectMembers.spec.ts src/features/agent/ProjectMemberPanel.spec.ts src/views/AgentWorkspace.spec.ts
```

结果：Vitest 在收集测试前报 `Unknown option --runInBand`，因此该次命令没有产生前端测试通过证据，也不是源码断言失败。已有质量基线记录 `npm run test:run` 为 80 files / 496 tests passed；本报告把它作为历史基线，不把错误参数命令冒充本次定向通过。

## 3. 旧 Owner-only gate 清单

### 3.1 需修复：明确违反项目成员访问契约

| 优先级 | 文件 / 函数 | 路径或调用语义 | 现状证据 | 影响与建议 |
|---|---|---|---|---|
| P0 | `backend/app/api/routers/novels.py` / `get_quality_trend` | `GET /api/novels/{project_id}/quality-trend` | 约第 3374 行调用 `get_project_owner_guard` | 这是跨章节质量趋势只读接口；Viewer/Editor/Admin 应按项目读权限访问，却仍被旧所有者 gate 截断。改为 `ProjectAccessService.require_project_read`，并保留当前脱敏输出。补 Viewer/Editor/Admin/非成员 HTTP 回归。 |
| P0 | `backend/app/api/routers/novels.py` / `export_novel_as_txt`、`preflight_export_novel`、`export_novel_as_docx` | `GET /api/novels/{project_id}/export/txt`、`/export/preflight`、`/export/docx` | 约第 3596、3621、3636 行调用 `get_project_owner_guard` | 导出和导出预检是项目读操作；当前成员迁移后仍只允许旧 Owner。建议统一 `require_project_read`，并确认导出是否对 Viewer 开放；若产品决定 Viewer 不得导出，应转入“人工确认”而不是继续使用名称含义模糊的 Owner guard。 |
| P0 | `backend/app/services/novel_service.py` / `get_section_data`、`get_chapter_schema` | 被 `novels.py` 的项目章节/内容读取路由调用 | 约第 1814、1825 行直接调用 `ensure_project_owner` | 这是服务层二次 gate；即使路由先完成成员读授权，Editor/Viewer 仍会在序列化时被拒绝。新增 `get_section_data_readable`/`get_chapter_schema_readable` 或把现有方法切换到显式 ProjectAccessService，并保留 admin 专用方法的边界。 |
| P0 | `backend/app/api/routers/novels.py` / `get_chapter` | 项目章节详情读取 | 路由调用 `NovelService.get_chapter_schema`，后者回到 `ensure_project_owner` | 成员章节读取会被服务层旧 gate 截断；与已通过的 Writer status/member read 语义不一致。补 Viewer/Editor 读取章节详情的 HTTP 测试。 |
| P0 | `backend/app/api/routers/novels.py` / `_generate_blueprint_impl` 及其 start/legacy forwarding 入口 | 蓝图生成后台任务与旧同步兼容路径 | 约第 4673 行 `_generate_blueprint_impl` 调用 `ensure_project_owner`；相关 start/legacy route 仍进入该实现 | Editor 发起蓝图生成后，后台实现再次按旧 Owner 校验；与 Writer generation 已修复的 execution owner/actor 分离不一致。入口应做 `require_project_write`，后台只按 `project_id` 读取，并显式保留执行归属。 |
| P0 | `backend/app/api/routers/novels.py` / `cancel_blueprint_generation` | `POST /api/novels/{project_id}/blueprint/generate/cancel` | 约第 4610 行调用 `get_project_owner_guard` | Editor/Admin 取消共享项目蓝图任务会被拒绝；同时蓝图 runtime 查询仍需核对原始 execution owner。迁移到 project write + run ownership 分离，并补 Editor 取消 Owner Run 的测试。 |
| P0 | `backend/app/api/routers/novels.py` / `save_blueprint`、`patch_blueprint` | `POST /api/novels/{project_id}/blueprint/save`、`PATCH /api/novels/{project_id}/blueprint` | 约第 4996、5021 行调用 `ensure_project_owner` | 明确项目写入路径，Editor/Admin 应按既有项目 write 规则工作；Viewer/非成员应 403。改为 `require_project_write`，返回序列化时使用已授权的成员读 helper。 |
| P0 | `backend/app/api/routers/novels.py` / `converse_with_concept` | `POST /api/novels/{project_id}/concept/converse` | AST/搜索命中约第 3667 行调用 `ensure_project_owner` | 会话/概念内容属于项目协作写入链；Editor 被旧 Owner gate 阻断。若产品规定概念会话仅 Owner 可写，需在权限矩阵中明确；当前项目写契约下应迁移到 `require_project_write`。 |
| P0 | `backend/app/api/routers/optimizer.py` / `optimize_chapter` | `POST /api/optimizer/optimize` | 约第 281 行调用 `ensure_project_owner` | 读取项目章节并运行优化；至少应使用项目读权限，若优化任务消耗并产生共享候选则应使用项目 write。当前旧 Owner gate 会阻止协作者使用功能。 |
| P0 | `backend/app/api/routers/optimizer.py` / `apply_optimization` | `POST /api/optimizer/apply-optimization` | 约第 493 行调用 `ensure_project_owner`，随后新增版本并更新 selected version | 明确写入项目资源；应迁移到 `require_project_write`，并单独验证 Viewer/非成员 403、Editor/Admin 成功及异步/选择版本一致性。 |
| P0 | `backend/app/api/routers/writing_skills.py` / `execute_skill` | `POST /api/writing-skills/skills/{skill_id}/execute`，带 `request.project_id` | 约第 190 行调用 `ensure_project_owner` | 带项目上下文的技能执行仍只允许 Owner；调用后还把当前操作者传入 `WritingSkillsService.execute_skill`，存在 actor 已是成员但前置 gate 仍是 Owner 的不一致。按技能能力区分 read/write，至少替换前置 gate 并补 Editor/Viewer 矩阵。 |
| P0 | `backend/app/agent/execution_facts.py` / `project_provider_usage_summary` | Agent 项目 Provider usage 旧聚合方法 | 约第 263 行 `select(NovelProject).where(NovelProject.id == project_id, NovelProject.user_id == user_id)`，并在 AgentRun 上继续限定 `user_id` | 同文件的 `project_provider_usage_summary_readable` 已先 `require_project_read`，说明项目成员读契约已存在；旧方法仍是所有者专用版本。确认所有路由改用 readable 版本，或将旧方法明确标为内部兼容方法，避免 `/runs/{run_id}/provider-usage-summary` 等路由继续走旧分支。 |
| P0 | `backend/app/agent/tool_adapters.py` / `execute_quality_retest` | Agent `quality.retest` | 约第 324 行把 `NovelProject.user_id == user_id` 放进版本查询 | 工具是只读质量复测，项目成员应能读取并复测共享版本；当前 Editor/Admin/Viewer 会被旧 Owner 过滤。改为先 `require_project_read`，查询按 `project_id/chapter/version`，不要按操作者替代项目权限。 |
| P0 | `backend/app/agent/tool_adapters.py` / `execute_quality_rewrite_instructions` | Agent 质量重写指令工具 | 约第 379 行同时按 `AgentArtifactRef.user_id == user_id`、`NovelProject.user_id == user_id` 过滤 | 质量结果/Artifact 已有项目成员读取测试，但该工具仍把创建者字段当访问边界。按 Artifact 所属 run/project 做 project read 校验，保留 projectless Artifact 创建者私有规则。 |
| P0 | `backend/app/api/routers/agent.py` / `accept_agent_artifact` | `POST /api/agent/artifacts/{artifact_id}/accept` | 约第 1163—1167 行要求 `AgentArtifactRef.user_id == current_user.id` 且 `AgentRun.user_id == current_user.id` | 这是已迁移的 Artifact 协作链中最明显的兼容端点残留；Editor 接受 Owner 生成的候选版本会在创建 approval 前被拒绝。应复用 `read_artifact`/`write_executor` 的 project access 与 execution owner 分离逻辑。补 Editor 接受 Owner candidate 的 HTTP 回归。 |
| P0 | `backend/app/services/agent_runtime.py` / `_run` 及其旧读调用 | Agent run 的通用创建者限定读取 | `_run` 查询 `AgentRun.id == run_id, AgentRun.user_id == user_id`；Agent router 的 `list_agent_events`、context snapshot、plan revision、conversation summaries、approvals、steps、artifacts 等仍有直接调用旧方法 | 同服务已提供 `get_readable_run`、`list_events_readable`，但路由混用。项目 Run 的读取必须统一 readable；projectless Run 继续 creator-only。逐路由替换并保留 claim/release/recover 等控制方法的独立 write/lease 规则。 |

### 3.2 需修复：直接 owner 字段过滤，需保留执行归属但解除访问误绑定

| 优先级 | 文件 / 函数 | 路径或语义 | 证据与判断 |
|---|---|---|---|
| P1 | `backend/app/api/routers/task_runtime.py` / `create_task` | `POST /api/task-runtime/tasks`，带 `project_id` | 约第 51—53 行直接查询 `NovelProject.id == request.project_id` 且 `NovelProject.user_id == current_user.id`。项目任务创建应先 `ProjectAccessService.require_project_write`，再把当前用户写入 `owner_user_id`；否则 Editor/Admin 无法创建共享项目任务。 |
| P1 | `backend/app/repositories/novel_repository.py` / `list_by_user`、`NovelService.list_projects_for_user` | 项目列表读取 | 约第 37 行仅 `NovelProject.user_id == user_id`。这不是单个资源 gate，而是成员项目发现缺口：被添加为 Editor/Viewer 的项目不会出现在正常项目列表。应增加“本人拥有或有 active ProjectMember”的列表查询；保留 projectless/legacy 兼容。 |
| P1 | `backend/app/api/routers/agent.py` / `list_agent_events` | `GET /api/agent/sessions/{session_id}/runs/{run_id}/events` | 约第 475、478 行调用 `get_run`/`list_events`，而同路由的 SSE 已调用 readable 版本。成员首次事件读取与 SSE 语义不一致，需统一 project-bound Run 的 read helper。 |
| P1 | `backend/app/api/routers/agent.py` / context snapshot、plan revision、conversation summaries | `/runs/{run_id}/context-snapshot`、`plan-revision`、`conversation-summaries` | 约第 835、862、879 行仍先调用 `get_run`。这些是只读投影，应使用 `get_readable_run`；projectless Run 仍 creator-only。 |
| P1 | `backend/app/api/routers/agent.py` / `get_agent_provider_usage_summary` | `GET /api/agent/runs/{run_id}/provider-usage-summary` | 约第 987—994 行调用旧 `AgentExecutionFactService.provider_usage_summary` 的风险链；旧方法要求项目 Owner。改为以 readable Run + project read 为前置，并仅返回脱敏聚合。 |
| P1 | `backend/app/api/routers/agent.py` / `list_agent_approvals`、`list_agent_run_steps`、`list_agent_artifacts` | `/runs/{run_id}/approvals`、`/steps`、`/artifacts` | 约第 1026、1034、1205 行调用 `list_approvals`、`list_steps`、`list_artifacts`；服务实现以 `_run` 和行级 `user_id` 过滤。若项目 Run 的运行轨迹、步骤、Artifact 属于共享读模型，应迁移为 project-readable 查询；若 approvals/steps 只对创建者可见，应写入明确产品矩阵并补测试。 |
| P1 | `backend/app/agent/tool_adapters.py` / `_readable_project_schema`、`_readable_project_section` | Agent `project.context`、项目 section 工具 | 当前先 `require_project_read`，再把 `access.project.user_id` 传给旧 Owner-scoped `NovelService` serializer | 现有做法在数据访问上可工作，且成员工具测试通过；但参数语义容易被误用。建议提供显式 `get_project_schema_for_member`/`get_section_data_for_member`，避免未来调用者把访问者 ID 误传给旧方法。当前列为“已安全（技术债）”，不是立即缺陷。 |

### 3.3 需人工确认：所有者限制可能是产品设计，不应直接扩大

| 优先级 | 文件 / 函数 | 路径或语义 | 当前证据 | 需要确认的问题 |
|---|---|---|---|---|
| P1 | `backend/app/services/novel_service.py` / `delete_projects`，`novels.py` / `delete_novels` | `DELETE /api/novels` 批量删除项目 | 约第 1895 行调用 `ensure_project_owner` | 删除是破坏性项目级动作。当前 Writer 项目 write 规则允许 Editor/Admin 写，但是否允许删除整个项目尚未在成员矩阵中定义。建议默认 Owner/Admin，若产品要让 Editor 删除，再改为 project write 并增加二次确认/审计。 |
| P1 | `backend/app/api/routers/task_runtime.py` / `list_tasks`、`stream_task_events`，`TaskRuntimeService` owner 参数 | 通用任务列表、任务 SSE、任务取消/重试等 | `list_tasks` 以 `owner_user_id` 查询；stream 先以 owner 取 task；服务 API普遍保留 owner 参数 | Writer/blueprint 的专用 runtime 已有 execution owner 语义，但通用 TaskRuntime 是否属于共享项目状态尚未完全定义。确认：项目成员能否读共享任务、Editor 能否取消/重试、Viewer 是否只读；确认后拆分 `project_read` 与 `execution_control`。 |
| P1 | `backend/app/services/agent_runtime.py` / `request_approval`、`decide_approval`、`claim_approval_execution`、`claim_step` | Agent 审批与执行控制 | 当前 approval/run/step 多按创建者 `user_id` 过滤；接受候选的兼容 route 也被同一约束影响 | “项目写权限”不必然等于“代替原执行者作审批/执行控制”。需要确定 Editor 是否可批准/拒绝 Owner 创建的 Agent 写入；若允许，使用 actor + execution owner 分离；若不允许，保持 creator-only 并把 403/404 语义写入矩阵。 |
| P1 | `backend/app/api/routers/novels.py` / 蓝图导出、蓝图兼容旧路由 | blueprint job 的 owner 字段与后台恢复 | 旧 job payload 在 `_upsert_blueprint_job_record` 中缺省时从 `NovelProject.user_id` 回填；这更像 execution owner 兼容逻辑，不是单纯访问 gate | 确认缺省 user_id 的历史任务是否始终应归属项目 Owner；新 Editor 启动的任务不得被回填逻辑覆盖。 |
| P2 | `backend/app/services/export_service.py` / `_get_project`、`novel_benchmark_service.py` / `build_baseline`、`outline_evolution_service.py` 内部 project 查询 | 服务内部直接 `select(NovelProject).where(NovelProject.id == project_id)` | 这些函数本身未展示当前用户参数；路由层部分已先做 ProjectAccessService，但服务也可能被后台任务或其他调用者直接使用 | 逐调用者确认：HTTP 入口必须先授权；后台 worker 使用 execution owner/runtime contract；纯内部 benchmark 是否不属于用户请求。不要仅凭“直接查项目”将其全部判为漏洞。 |

## 4. 已安全项与当前证据

| 范围 | 文件 / 证据 | 结论 |
|---|---|---|
| 统一访问策略 | `backend/app/services/project_access_service.py` | `ProjectAccess` 已区分 owner/editor/viewer/admin；legacy owner fallback、软删除成员、owner 不可转授/移除均有单元测试。 |
| Analytics | `backend/app/api/routers/analytics.py`、`analytics_enhanced.py` | 已使用 `require_project_read`/`require_project_write`；当前命中搜索未发现旧 Owner gate。 |
| Outline | `backend/app/api/routers/outline.py` | 生成/选择使用 write，读取/历史使用 read；当前路由层已迁移。后台内部查询仍需按调用者确认，但入口已有策略层。 |
| Projects 子资源 | `backend/app/api/routers/projects.py` | constitution/persona/memory/character state 等读写入口使用 ProjectAccessService；对应成员测试通过。 |
| Clue/Foreshadowing、Knowledge、Research、Style、Review、Patch-diff、Token budget | 各对应 router 与 `test_*_member_access.py` | 当前迁移链路有成员读写测试；定向集合整体通过。 |
| Agent readable projections | `agent/execution_facts.py:project_provider_usage_summary_readable`、`agent/state_projection.py`、`agent/context_refs.py`、`agent/write_executor.py` | 已建立正确模式：先 project read/write，再按 run/artifact 的 execution owner 做后台归属；相关成员测试通过。 |
| Writer H-1/H-2 | `writer.py`、`novel_service.py` 与 5 个 writer member 测试文件 | 章节状态、outline status、SSE replay、取消/恢复、finalize selection、Editor 写入等当前定向回归通过；本报告把它作为迁移后的正向参考实现。 |
| 前端成员面板 | `frontend/src/features/agent/ProjectMemberPanel.vue`、`frontend/src/api/projectMembers.ts`、`frontend/src/views/AgentWorkspace.vue` | 已有真实组件/API 调用和挂载证据；详见第 5 节。 |

## 5. 前端成员管理 UI/API 证据

### 5.1 已存在的实现

- `frontend/src/api/projectMembers.ts`
  - `ProjectMembersAPI.list(projectId)`：读取 `/projects/{encodedProjectId}/members`。
  - `ProjectMembersAPI.add(projectId, payload)`：POST 添加或恢复成员。
  - `ProjectMembersAPI.updateRole(projectId, userId, payload)`：PATCH 角色。
  - `ProjectMembersAPI.remove(projectId, userId)`：DELETE 软删除成员。
  - 请求带 `credentials: include`，JSON mutation 带认证 header。
- `frontend/src/features/agent/ProjectMemberPanel.vue`
  - 加载并按 owner-first 排序；展示 `access_role`、`can_manage`。
  - owner 角色下拉与移除按钮禁用，避免降级/移除 owner。
  - viewer/read-only 状态禁用添加、角色修改和删除。
  - owner/editor/admin 可在 `canManage` 条件满足时提交添加、修改角色、删除。
  - 通过 `loaded`/`changed` 事件向父视图回传成员投影。
- `frontend/src/views/AgentWorkspace.vue`
  - 在 Agent 项目工作区挂载成员管理 section，并按当前项目加载成员。
  - UI 组件当前主要落在 Agent 工作区，不是全局项目详情页。

### 5.2 已有前端测试证据

- `frontend/src/api/projectMembers.spec.ts`
  - project ID 编码；list/add 请求路径；认证 header；JSON body。
  - 服务器 422 detail 能向 UI/API 调用者透传。
- `frontend/src/features/agent/ProjectMemberPanel.spec.ts`
  - owner-first 排序；owner 控件禁用。
  - viewer 只读状态；添加按钮、角色控件禁用。
  - owner 添加 viewer 后成员列表和 changed projection 更新。
- `frontend/src/views/AgentWorkspace.spec.ts`
  - AgentWorkspace 显示项目成员 section，并能渲染 owner 成员。

### 5.3 前端证据缺口

1. 没有看到 `updateRole` 成功后的 UI 状态更新断言；只有 API 端错误透传覆盖。
2. 没有看到 remove 成功、删除后列表更新、网络失败重试/错误态测试。
3. 没有 owner/editor/admin 三种 `can_manage` 的完整 UI 矩阵；当前 viewer 和 owner 有证据，editor/admin 多为后端测试或实现推断。
4. 没有恢复已软删除成员的前端用例；后端 `add_or_restore_member` 的恢复语义需要 UI 证据。
5. 没有非成员 403、项目不存在 404、成员被即时移除后刷新失效的浏览器级测试。
6. 成员面板只在 `AgentWorkspace` 被发现；项目主页面、Writer 页面、项目设置页是否需要同一入口没有证据。
7. 本轮前端定向命令因传入 Vitest 不支持的 `--runInBand` 参数而在收集前退出；应以正确参数重新执行并保留输出。

## 6. 后端测试矩阵与缺口

### 6.1 当前已有矩阵

| 领域 | Owner | Editor | Viewer | Admin | 非成员 | 证据 |
|---|---:|---:|---:|---:|---:|---|
| ProjectAccessService 基础读写 | ✓ | ✓ | ✓ | ✓ | ✓ | `test_project_access_service.py` |
| Agent project HTTP/read projection | ✓ | ✓ | ✓ | ✓ | ✓ | `test_agent_project_member_http.py`、`test_execution_facts_member_access.py` |
| Agent tool adapters | 部分 | 部分 | 部分 | 部分 | ✓ | `test_tool_adapters_member_access.py`；未覆盖本报告两处旧 owner filter |
| Artifact read/write executor | ✓ | ✓ | viewer 拒绝 | ✓ | ✓ | `test_write_executor_member_access.py`；兼容 accept route 仍缺 HTTP 覆盖 |
| Analytics/knowledge/graph | ✓ | ✓ | 读 ✓/写拒绝 | ✓ | ✓ | `test_knowledge_analytics_member_access.py` |
| Projects 子资源 | ✓ | ✓ | 读 ✓/写拒绝 | ✓ | ✓ | `test_projects_member_access.py` 等 |
| Writer status/SSE/write/control/finalize | ✓ | ✓ | 读 ✓/写拒绝 | ✓ | ✓ | 5 个 writer member 测试文件 |
| 成员 API | owner manage、成员读 | 部分 | 读 | admin | 非成员拒绝 | `test_project_members_route.py`、`test_project_access_service.py` |

### 6.2 关键缺口

- `novels.py` quality trend、章节详情、导出、概念会话、蓝图 start/cancel/save/patch 没有完整的成员 HTTP 矩阵。
- `optimizer.py` optimize/apply 没有 Editor/Viewer/Admin/非成员专项矩阵。
- `writing_skills.py:execute_skill` 没有项目成员矩阵，也没有区分 read-only skill 与 write-capable skill。
- Agent `list_agent_events`、context snapshot、plan revision、conversation summaries、provider usage、approvals、steps、artifacts 缺少 Editor/Viewer/Admin/非成员的统一矩阵；当前只覆盖了已迁移 readable 分支的一部分。
- `accept_agent_artifact` 缺少 Editor 接受 Owner candidate 的 HTTP 回归。
- `task-runtime` 缺少 project member 读、任务 SSE、Editor 控制和 Viewer 只读测试。
- 项目列表缺少“成员项目可发现”测试；现有 owner-only `list_by_user` 会把协作项目排除。
- 缺少移除成员后已有 token/已有页面即时失效的跨请求测试。
- 缺少“故意恢复旧 `NovelProject.user_id` 过滤后测试失败”的反向验证；下一修复批次必须为每个 P0 领域增加至少一个破坏实现验证。

## 7. 推荐执行顺序

### P0 — 先消除确定性错误 gate

1. `novel_service.get_section_data/get_chapter_schema` 增加显式 member-readable 语义，先修章节详情与 Agent 旧 serializer 依赖。
2. `novels.py` quality trend、导出/预检/文档导出改为 read gate。
3. `novels.py` 蓝图生成/取消/保存/patch、概念会话改为 write gate，并完整检查后台 execution owner。
4. `optimizer.py`、`writing_skills.py` 接入 read/write 策略。
5. Agent `get_run` 混用路由全部改为 readable；provider usage、quality tools、Artifact accept 解除错误的创建者过滤。

### P1 — 补共享发现和通用运行时

1. `NovelRepository.list_by_user` 改为“owner 或 active member”项目列表，或新增明确的 `list_accessible_projects`。
2. `task_runtime.create_task` 先 project write，再保存 actor/execution owner；通用 list/stream/control 依据人工确认结果拆分权限。
3. 为上述每类路由补 Owner/Editor/Viewer/Admin/非成员测试，并添加跨项目/跨 Run/跨章节隔离。
4. 重新执行正确的前端成员专项测试命令，补 update/remove/restore/403/404/error-state 用例。

### P2 — 语义收口和技术债

1. 用 `get_project_schema_for_member` 等显式服务名替代“先授权再传 canonical owner ID”的隐式适配。
2. 将 `get_project_owner_guard` 重命名为明确的 `require_legacy_owner` 或限制其只用于真正的 owner-only 产品操作，避免新代码误用。
3. 对 export、approval、delete、benchmark、后台恢复等路径建立一张产品权限表，避免静态迁移扩大过度。

## 8. 交付边界

- 本批只新增本报告：`D:\小说写作\xuanqiong-wenshu\docs\reports\collaborative-access-sweep-20260905.md`。
- 未修改业务代码、测试、前端文件或接续计划文档。
- 未创建 Codex task，未提交 Git。
- 当前工作区原有未跟踪二进制运行工件保持原状。
- 本报告不把历史全量测试数字替代为本次扫描证据；本次最强实测结果是后端成员定向集合 **115 passed in 47.56s**。

## 9. 下一步验收命令

```powershell
cd D:\小说写作\xuanqiong-wenshu\frontend
npm run test:run -- src/api/projectMembers.spec.ts src/features/agent/ProjectMemberPanel.spec.ts src/views/AgentWorkspace.spec.ts

cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q `
  app/api/routers/test_novels_member_access.py `
  app/api/routers/test_optimizer_member_access.py `
  app/api/routers/test_writing_skills_member_access.py `
  app/api/routers/test_agent_legacy_projection_member_access.py `
  app/api/routers/test_task_runtime_member_access.py
```

上面的后端文件名是建议新增的专项测试分组，不代表当前已经存在；不得把它们写成当前已通过证据。
