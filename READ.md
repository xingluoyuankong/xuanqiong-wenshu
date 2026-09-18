# 玄穹文枢项目总导航（先看这个）

这个文件是项目的统一入口，目标是让后续优化不再每次全仓库重检索。

## 1) 先看这里

- 功能分区说明：`docs/code-index/README.md`
- 人工维护的功能分区总览：`docs/code-index/functional-zones.md`
- 自动生成的文件索引（按分区）：`docs/code-index/auto-file-index.md`
- 机器可读索引 JSON：`docs/code-index/auto-file-index.json`

## 2) 如何更新索引

在仓库根目录运行：

```powershell
python tools/generate_code_index.py
```

## 2.1 功能冒烟测试（改完必跑）

这次"设置页健康检查 + 自动切换 provider"功能对应冒烟脚本：

```powershell
python tools/smoke_llm_settings_health.py
```

通过标准：

- `http://127.0.0.1:8013/docs` 与 `http://127.0.0.1:5174` 返回 `200`
- OpenAPI 包含 `/api/llm-config/health-check` 与 `/api/llm-config/auto-switch`
- 当前 `system_user_fallback` 基线下，`/api/llm-config/health-check` 返回 `200` 且响应结构包含 `has_usable_profile`

本轮已同步优化：

- `verify.ps1`、`tools/smoke_api_routes.py`、`tools/smoke_llm_settings_health.py` 的控制台输出已改为更清晰的中文提示
- 通用 OpenAPI 冒烟检查不再伪造 `00000000-0000-0000-0000-000000000000` 这类占位 ID 去触发资源依赖型接口
- 对依赖真实资源 ID 的接口，统一输出“跳过原因”，减少误导性 404 噪音
- `start.ps1`、`verify.ps1`、`tools/start_local_mysql.ps1` 以及相关诊断脚本已补 UTF-8 输出链路，降低 PowerShell 中文乱码概率
- `backend/scripts/diagnose_llm_connectivity.py`、`backend/scripts/backfill_relationship_meta_markers.py`、`backend/scripts/migrate_sqlite_to_mysql.py` 等独立脚本也已同步中文化

更新后会覆盖：

- `docs/code-index/auto-file-index.md`
- `docs/code-index/auto-file-index.json`

## 2.2 当前主线注意事项（必看，避免一个问题反复折腾）

### 后端验证环境

- **后端命令必须优先在 `backend/` 目录执行**，否则 `backend/.env` 可能不会被正确加载。
- **后端测试必须优先使用项目自己的虚拟环境**：`backend/.venv/Scripts/python.exe`。
- 不要直接用系统全局 `pytest` / Anaconda Python 跑后端测试；之前已实际踩坑：全局插件链会引入额外的 NumPy / SciPy 二进制兼容问题，浪费排查时间。

推荐命令：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
```

### 完成标准

- **前端 build 通过 ≠ 功能完成**。
- **代码写了 ≠ 前后端已对齐**。
- 至少同时满足以下几项，才能说这一块真的修完：
  1. 后端导入 / 启动通过
  2. `Base.metadata.create_all()` 能覆盖新增模型
  3. 前后端接口路径一致
  4. smoke test 通过
  5. 前端构建通过
- 如果还没做真实联调或登录后页面操作验证，只能说“代码与静态验证已通过”，不能笼统说“功能全部完成”。

### 玄穹文枢当前这条主线的几个高频坑

- **新增 ORM 模型后，必须同步更新** `backend/app/models/__init__.py`，否则模型不会进入建表链路。
- **项目级接口统一走** `/api/projects/{project_id}/...`，不要再写成 `/api/{project_id}/...`。
- `clue_tracker` 的静态路由：
  - `/clues/threads`
  - `/clues/red-herring`
  - `/clues/unresolved`
  必须定义在 `/{clue_id}` 之前，否则会被动态路由吞掉。
- `NovelDetailShell.vue` 这类壳组件里，弹窗 `@updated` 回调必须指向**当前组件里真实存在的方法**，不要挂不存在的 `loadData`。

### 当前已验证通过的命令

```powershell
# 快速回归（build + pytest）
./verify.ps1 quick

# 启动正式本地栈
./start.ps1

# 运行态 smoke
./verify.ps1 smoke

# 完整业务回归
./verify.ps1 full

# 或手动执行
npm --prefix frontend run build
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
cd ..
backend\.venv\Scripts\python.exe tools/smoke_api_routes.py
backend\.venv\Scripts\python.exe tools/smoke_llm_settings_health.py
```

### 2026-04-08 已修复并验证的点

- `token_budget` / `clue_tracker` / `faction` 模型已补进 `backend/app/models/__init__.py`
- `token_budget` 后端路由已对齐到 `/api/projects/{project_id}/token-budget...`
- `clue_tracker` 后端路由已对齐到 `/api/projects/{project_id}/clues...`
- `clue_tracker` 静态路由顺序已修正
- `frontend/src/components/shared/NovelDetailShell.vue` 中 Token Budget 弹窗未定义回调已修复
- `world_setting.factions` 已接到真实 `PUT/GET /api/projects/{project_id}/factions`，并验证会回流到 `/api/novels/{project_id}/sections/world_setting`
- `backend/app/services/writing_skills_service.py` 的技能执行已从占位返回升级为真实 LLM 调用，并补上 `user_id` 透传；否则会错误走全局默认 LLM 配置，导致 401/错误 provider 回退
- 已验证：前端 build 通过、后端集成测试 13/13 通过、API route smoke 160/160 通过、LLM settings smoke 通过（正式本地口径为 `frontend 5174 -> backend 8013`；`/docs`、前端首页、`/api/updates/latest`、`/api/llm-config` 可达，OpenAPI 包含 `/api/llm-config/health-check`、`/api/llm-config/auto-switch`、`/api/llm-config/models`，且 health-check 返回结构包含 `has_usable_profile`）
- 已做进程内真实鉴权联调：登录 -> 建项目 -> 保存 factions -> 读取 world_setting -> 安装 skill -> 执行 skill -> 卸载 skill -> 删除项目，全链路通过；写作技能返回 `result.mode = "llm"`
- 已做进程内真实鉴权联调：`token budget` 已验证 `GET/PUT budget`、`record usage`、`usage stats`、`usage-by-module`、`alerts`、`resolve alert`、`allocate` 全链路通过，且非 owner 访问 `/api/projects/{project_id}/token-budget...` 返回 `403`
- 已做进程内真实鉴权联调：`clue tracker` 已验证 `create/list/detail/update/link-chapter/timeline/red-herring/unresolved/delete` 全链路通过，且非 owner 访问 `/api/projects/{project_id}/clues...` 返回 `403`
- 已做进程内真实鉴权联调：`foreshadowing + knowledge graph` 已验证通过；knowledge graph 前端契约 `/api/{project_id}/knowledge-graph/*` 已补齐，旧根路径 `/{project_id}/knowledge-graph/*` 仍保留兼容；foreign access 返回真实 `403`
- 已做进程内真实鉴权联调：`style + memory management` 已验证 `style extract/get/generate/clear` 与 `memory snapshots/incremental/compress/rollback` 全链路通过；owner 用户级 `llm_config` 健康检查通过，foreign access 返回真实 `403`
- 已做进程内真实鉴权联调：`outline` 已验证 `evolve -> alternatives -> next -> history` 全链路通过；前端契约 `/api/novels/{project_id}/outline/*` 可命中；owner 用户级单 profile LLM 配置健康检查通过，foreign access 返回真实 `403`
- 本轮新增修复：`WDStyleExtractModal.vue` 已兼容 `number/chapter_number`；`memory_layer_service.py` 已修复角色状态 SQL、snapshot/rollback 排序与 rollback 中的 `ProjectMemory` 引用；`foreshadowing_service.py` 已修复 analysis 误按主键查 `project_id` 的唯一约束风险；`outline` 路径已对齐 `/api/novels/{project_id}/outline/*`，且 `outline.py` / `outline_evolution_service.py` 已从 async/sync 混用收敛为 AsyncSession 主链路；`auth_service.py` 已补注册唯一约束竞态兜底；`novel_service.py` 已补 `chapter/outline` 创建竞态兜底；`app/services/test_phase4_integration.py` 当前 13/13 通过；新增 `backend/scripts/e2e_outline_validation.py` 用于 outline 真链路回归；`backend/scripts/e2e_foreshadowing_graph_validation.py` 已补 owner 用户级单 profile LLM 配置，避免验证时误落入全局 fallback 链造成噪音告警
- 本轮最终关键验收：`backend/scripts/e2e_token_clue_validation.py`、`backend/scripts/e2e_style_memory_validation.py`、`backend/scripts/e2e_foreshadowing_graph_validation.py`、`backend/scripts/e2e_outline_validation.py` 均已重新通过；foreign access 分别返回真实 `403`；当前主线与关键功能验收已收口。

### 正式使用前推荐顺序

1. `./start.ps1`
2. `./verify.ps1 smoke`
3. 如涉及后端或关键链路改动，再跑 `./verify.ps1 full`
4. 使用完成后运行 `./stop.ps1`

## 3) 推荐优化工作流（避免重复检索）

1. 先在 `functional-zones.md` 确定要动的功能区。
2. 再在 `auto-file-index.md` 锁定候选文件。
3. 只读取该分区的入口文件与关联服务，不跨区扩散。
4. 变更完成后运行 `python tools/generate_code_index.py`，保持索引与代码同步。
5. CI 最小门槛以 `.github/workflows/xuanqiong-wenshu-quick-smoke.yml` 为准，先跑 quick + smoke，不把重型 full 回归直接绑定到每次提交。

## 4) 关键入口

- 后端入口：`backend/app/main.py`
- 前端入口：`frontend/src/main.ts`
- 章节生成主链路：`backend/app/services/pipeline_orchestrator.py`
- LLM 网关与容错：`backend/app/services/llm_service.py`
- LLM 配置与设置页：`backend/app/api/routers/llm_config.py` / `frontend/src/components/LLMSettings.vue`
- 启动器：`start_xuanqiong_wenshu.cmd`
- CI：`.github/workflows/xuanqiong-wenshu-quick-smoke.yml`
- canonical 子启动器：`backend/start_backend.cmd` / `frontend/start_frontend_dev.cmd`

---

## 5) 2026-03-29 优化记录

### 文件清理

- 删除了 85 个日志文件
- 删除了 490 个 `__pycache__` 目录
- 删除了 `.pytest_cache` 和 `.benchmarks` 目录
- 删除了 37 个 `README.ai` 文件（AI 生成的说明文件）
- 移动了根目录的报告文件到 `docs/reports/` 目录
- 删除了未使用的组件：
  - `HelloWorld.vue`
  - `ChapterWorkspace.vue`
  - `ChapterWorkspaceEnhanced.vue`

### 代码修复

1. **后端导入语句位置修复** (`backend/app/services/novel_service.py`)
   - 将导入语句从文件末尾移动到文件开头
   - 修复了 `inspect` 函数在使用后才导入的问题

2. **前端 API 错误处理增强** (`frontend/src/api/llm.ts`)
   - 添加了 401 状态码处理，在未授权时自动登出并重定向到登录页

### 配置优化

- LLM 配置已更新为使用 OpenRouter API（可用）
- 管理员密码已重置

### 测试结果

- 后端健康检查：通过
- 前端服务：通过
- 登录 API：通过
- 小说列表 API：通过
- LLM 健康检查：通过（345 个模型可用）
- 章节生成 API：通过
