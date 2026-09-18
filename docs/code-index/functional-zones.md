# 功能分区总览

目标：把项目按“业务功能 + 维护边界”做可执行分区，后续优化按分区推进，不再全仓库盲搜。

## A. 后端接口层（Backend API Layer）

- 目录：`backend/app/api/routers/`
- 职责：HTTP 路由、参数接收、鉴权后调用服务层、返回响应模型。
- 关键文件：
  - `backend/app/api/routers/writer.py`
  - `backend/app/api/routers/novels.py`
  - `backend/app/api/routers/llm_config.py`
  - `backend/app/api/routers/auth.py`

## B. 后端服务编排层（Backend Service Pipeline）

- 目录：`backend/app/services/`、`backend/app/tasks/`
- 职责：核心业务逻辑、写作流程编排、LLM 调用、记忆系统与一致性策略。
- 关键文件：
  - `backend/app/services/pipeline_orchestrator.py`
  - `backend/app/services/llm_service.py`
  - `backend/app/services/memory_layer_service.py`
  - `backend/app/services/enhanced_writing_flow.py`
  - `backend/app/services/llm_config_service.py`

## C. 后端领域层（Domain Models / Schemas / Repositories）

- 目录：`backend/app/models/`、`backend/app/schemas/`、`backend/app/repositories/`
- 职责：数据模型、响应/请求结构、数据库访问封装。
- 关键文件：
  - `backend/app/models/novel.py`
  - `backend/app/models/llm_config.py`
  - `backend/app/schemas/novel.py`
  - `backend/app/schemas/llm_config.py`
  - `backend/app/repositories/novel_repository.py`

## D. 后端基础设施层（Core / DB / Config）

- 目录：`backend/app/core/`、`backend/app/db/`、`backend/app/config/`
- 职责：配置、依赖注入、安全、数据库会话与初始化。
- 关键文件：
  - `backend/app/main.py`
  - `backend/app/core/config.py`
  - `backend/app/core/dependencies.py`
  - `backend/app/db/session.py`
  - `backend/app/db/init_db.py`

## E. 前端应用壳层（Frontend App Shell）

- 目录：`frontend/src/main.ts`、`frontend/src/router/`、`frontend/src/stores/`
- 职责：应用启动、路由、全局状态和鉴权态。
- 关键文件：
  - `frontend/src/main.ts`
  - `frontend/src/router/index.ts`
  - `frontend/src/stores/auth.ts`
  - `frontend/src/stores/novel.ts`

## F. 前端页面与组件层（Frontend UI Layer）

- 目录：`frontend/src/views/`、`frontend/src/components/`
- 职责：可视化交互、写作工作台、设置页、管理页。
- 关键文件：
  - `frontend/src/views/NovelWorkspace.vue`
  - `frontend/src/views/SettingsView.vue`
  - `frontend/src/components/LLMSettings.vue`
  - `frontend/src/components/ChapterWorkspaceEnhanced.vue`

## G. 前端数据层（Frontend API & Composables）

- 目录：`frontend/src/api/`、`frontend/src/composables/`、`frontend/src/utils/`
- 职责：前端 API 客户端、通用逻辑组合、格式化工具。
- 关键文件：
  - `frontend/src/api/novel.ts`
  - `frontend/src/api/llm.ts`
  - `frontend/src/composables/useAlert.ts`
  - `frontend/src/utils/chapterContent.ts`

## H. 部署与运行层（Deploy & Runtime）

- 目录：`deploy/`、`start_xuanqiong_wenshu.cmd`、`backend/scripts/`
- 职责：容器部署、Nginx、启动脚本、诊断脚本。
- 关键文件：
  - `start_xuanqiong_wenshu.cmd`
  - `deploy/docker-compose.yml`
  - `deploy/Dockerfile`
  - `backend/scripts/diagnose_llm_connectivity.py`

## I. 文档与审计层（Docs & Reports）

- 目录：`docs/`、根目录各类 `*.md`
- 职责：设计说明、优化记录、部署指南、审计报告。
- 关键文件：
  - `README.md`
  - `READ.md`
  - `DEEP_OPTIMIZATION_REPORT.md`
  - `CODE_AUDIT_REPORT.md`

## 建议执行方式

1. 每个优化任务先归属到一个主分区（A-I）。
2. 主分区之外最多扩展一个相邻分区，控制变更半径。
3. 每次结构变化后执行 `python tools/generate_code_index.py` 更新索引。
