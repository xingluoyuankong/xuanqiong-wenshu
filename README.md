# 玄穹文枢

玄穹文枢是一个面向长篇小说与系列化叙事生产场景的本地优先智能写作系统，围绕“灵感整理—蓝图建模—章节生成—质量评审—知识沉淀”构建闭环创作链路，提供项目蓝图、章节写作台、LLM 多配置编排、写作技能调度、线索追踪、知识图谱与一致性分析等核心能力。

> 本 README 已合并原 `READ.md` 的导航与验证说明。原仓库宣传内容、二维码、外部截图、在线体验链接和历史仓库口径已移除。

## 项目简介

你构建的是一个**面向网络小说、长篇连载与复杂世界观创作的智能写作工程平台**。它不是单点式的“AI 续写工具”，而是一个将创作流程结构化、数据化、可追踪化的创作基础设施：

- 它能将灵感采集、蓝图确认、章节生成、版本比对、线索回收、角色关系维护和质量评审串联为一条完整生产链路。
- 它基于 LLM 配置编排、项目知识沉淀、结构化写作技能和多维度评审机制，提升长文本生成的一致性、可控性与复用效率。
- 目前系统已经具备项目级写作台、知识图谱、情绪曲线、伏笔/线索追踪、写作技能中心、配置治理与验证脚本等一整套可落地能力。
- 它的价值在于把“灵感驱动的写作”升级为“可运营、可迭代、可审计的叙事生产流程”，适合个人作者、工作室化创作和需要稳定产出长篇内容的场景。

## 项目总结

玄穹文枢本质上是一个**以长篇叙事一致性控制为核心的 AI 协同创作平台**。根据当前仓库能力与验证链路，它已经形成了从前端工作台、后端编排服务、模型配置治理到本地验证闭环的完整系统骨架。当前阶段，它不仅能够承担章节级内容生成，还能够通过知识索引、状态追踪与多层评审机制，对创作过程进行过程化管理与结果校准，从而显著降低长篇创作中常见的设定漂移、线索断裂、节奏失衡与上下文遗忘问题。

## 主要能力

- 项目、蓝图、角色、地点、派系管理
- 写作台：章节生成、版本对比、补丁差异、记忆管理
- LLM 设置：多配置组、健康检查、来源追踪、自动切换
- 写作技能：技能目录、安装 / 卸载、执行建议
- 辅助分析：线索追踪、情绪曲线、知识图谱、Token Budget

## 本地正式启动

最稳妥的方式是直接使用仓库根目录的一键脚本：

```powershell
./start.ps1
```

这个脚本会按固定顺序启动整套本地正式栈：

1. 清理旧的 `5174 / 8013` 端口进程
2. 启动项目本地 MySQL（`3309`）
3. 启动后端（`8013`）
4. 启动前端（`5174`）
5. 等待前后端健康检查通过

### 固定端口（不要随便改）

| 服务 | 固定端口 | 作用 | 说明 |
| --- | --- | --- | --- |
| Frontend | `5174` | 浏览器入口 | 正式本地前端入口 |
| Backend | `8013` | API 服务 | 前端 `/api` 请求默认代理到这里 |
| Local MySQL | `3309` | 项目本地数据库 | `backend/.env` 默认连这个端口，不是系统 MySQL `3306` |

访问地址：

- Frontend: `http://127.0.0.1:5174`
- Backend: `http://127.0.0.1:8013`
- Backend health: `http://127.0.0.1:8013/api/health`

重要说明：

- **`5174` 能打开页面，不代表后端正常。** 前端页面打开后，真实数据、章节生成、状态同步仍依赖 `8013`。
- **系统 MySQL `3306` 不能代替项目本地 MySQL `3309`。** 如果 `3309` 没起来，后端通常会直接启动失败。
- **除非用户明确要求，不要改 README、脚本、Vite 代理和启动命令里的默认端口。**

停止服务：

```powershell
./stop.ps1
```

仅在需要手动排障时，再分别启动各服务：

```powershell
# 1) 先启动项目本地 MySQL（3309）
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_local_mysql.ps1

# 2) 再启动后端（必须先进入 backend 目录）
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --log-level warning --no-access-log

# 3) 最后启动前端
cd ..\frontend
npm run dev -- --host 127.0.0.1 --port 5174
```

如果使用 `./start.ps1` 启动，运行日志会写到 `logs/run-时间戳/`，最近一次目录会记录在 `logs/latest-run.txt`。

## 回归验证

```powershell
./verify.ps1 quick
./verify.ps1 smoke
./verify.ps1 full
```

说明：

- `quick`：前端 build + 后端关键 pytest + 配置占位值前置检查；不自动启动整套服务
- `smoke`：正式端口运行态检查 + OpenAPI/LLM 设置冒烟；必要时自动拉起本地正式栈
- `full`：在 quick + smoke 基础上继续执行后端关键 E2E，用于主链路回归定位

### 最近的验证与诊断输出优化

本轮已收口以下验证体验问题：

- `verify.ps1`、`tools/smoke_api_routes.py`、`tools/smoke_llm_settings_health.py` 的主要输出已统一为中文提示
- `smoke` 不再使用 `00000000-0000-0000-0000-000000000000` 这类占位 ID 去扫一批必然 404 的资源接口
- 对依赖真实资源 ID 的路由，改为明确输出“跳过原因”，避免误导性噪音掩盖真正错误
- `start.ps1`、`verify.ps1`、`tools/start_local_mysql.ps1` 及相关验证脚本已补齐 UTF-8 输出链路，减少 Windows PowerShell 中文乱码
- `backend/scripts/diagnose_llm_connectivity.py`、`backend/scripts/backfill_relationship_meta_markers.py`、`backend/scripts/migrate_sqlite_to_mysql.py` 等常用独立脚本的控制台提示已同步中文化

当前目标是：

- 真正失败要清楚暴露
- 跳过原因要可解释
- 不让提示噪音淹没主问题
- 不在 Windows 本地验证时出现明显乱码

## 后端开发

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

后端测试建议优先使用项目虚拟环境：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
```

## 前端开发

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

## Docker 部署

Docker 口径与本地正式口径分离：

- 本地正式运行固定使用 `8013 / 5174 / 3309`
- Docker 默认通过 `deploy/.env` + `deploy/docker-compose.yml` 启动，应用对外端口由 `APP_PORT` 控制
- Docker 默认可走 `DB_PROVIDER=sqlite`；只有切到 MySQL 时才需要 `MYSQL_PASSWORD` 与 `--profile mysql`
- 旧的 `deploy/scripts/quick_deploy.sh` 与 `deploy/scripts/server_deploy.sh` 已改为安全提示入口，不再执行硬编码公网主机、root 登录、默认弱口令写入或 `git reset --hard` 之类的高风险动作

```bash
cp deploy/.env.example deploy/.env
bash deploy/scripts/deploy_docker.sh
```

## LLM 配置与诊断

当前运行时优先级：

1. 用户 `llm_configs`
2. 系统 `system_configs`
3. `.env / env fallback`

常用诊断方式：

```bash
python backend/scripts/diagnose_llm_connectivity.py --user-id <用户ID>
```

只读来源追踪接口：

- `GET /api/llm-config/source-trace`

说明：

- 诊断与追踪接口只返回脱敏后的 key 信息
- 不应提交 `.env`、数据库、日志、备份和测试产物
- `docs/code-index/` 当前作为正式导航索引保留在仓库中；`backups/`、`README.ai`、数据库恢复前备份等本地产物不应入库

## 代码导航

优先查看：

- `docs/code-index/README.md`
- `docs/code-index/functional-zones.md`
- `docs/code-index/auto-file-index.md`
- `docs/code-index/auto-file-index.json`

更新索引：

```powershell
python tools/generate_code_index.py
```

## 现有注意事项

### 固定端口与依赖关系（必看）

- `5174` = 前端固定入口。
- `8013` = 后端固定入口。
- `3309` = 项目本地 MySQL 固定端口。
- 前端 `5174` 的 `/api` 默认代理到 `8013`，所以“页面能打开但按钮报错”通常不是前端挂了，而是后端没起来。
- `backend/.env` 当前默认走 `DB_PROVIDER=mysql`，并使用 `MYSQL_PORT=3309`。如果只开了系统 MySQL `3306`，项目后端仍然可能起不来。
- 除非用户明确要求，不要把临时排障端口改成新的正式口径。

### 常见报错与第一检查项

| 现象 | 最常见原因 | 第一检查项 |
| --- | --- | --- |
| 写作台提示“状态同步失败”“服务暂时不可用” | 后端 `8013` 没起来，或前端代理打不到后端 | 先访问 `http://127.0.0.1:8013/api/health` |
| 后端启动直接退出，并出现 `Can't connect to MySQL server on '127.0.0.1'` | 项目本地 MySQL `3309` 没启动 | 先运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_local_mysql.ps1` |
| 前端页面能打开，但项目列表 / 生成 / 状态刷新都失败 | `5174` 正常，`8013` 异常 | 先查 backend health 和 `logs/latest-run.txt` |
| 手动 `uvicorn` 启动时报 `.env` / `secret_key` / 配置缺失 | 没在 `backend/` 目录执行，导致 `backend/.env` 没读到 | 先 `cd backend` 再启动 |
| 手动跑后端测试时报一堆 NumPy / 插件 / asyncmy 相关错误 | 用了系统 Python / Anaconda / 全局 pytest | 改用 `backend/.venv/Scripts/python.exe` |

### 最快自检命令

```powershell
# 检查本地正式端口是否已起来
Invoke-WebRequest http://127.0.0.1:5174/
Invoke-WebRequest http://127.0.0.1:8013/api/health

# 查看 3309 / 8013 / 5174 的监听情况
Get-NetTCPConnection -LocalPort 3309,8013,5174 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, State, OwningProcess

# 如果 3309 没起来，先补起项目本地 MySQL
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_local_mysql.ps1
```

### 后端验证环境

- 后端命令优先在 `backend/` 目录执行，否则 `backend/.env` 可能不会被正确加载。
- 后端测试优先使用项目虚拟环境：`backend/.venv/Scripts/python.exe`。
- 不要直接用系统全局 `pytest` 或 Anaconda Python 跑后端测试，容易引入额外插件和二进制兼容问题。

推荐命令：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
```

### 完成标准

- 前端 build 通过，不等于功能完成。
- 代码改完，不等于前后端已对齐。
- 至少应同时满足：
  1. 后端导入 / 启动通过
  2. `Base.metadata.create_all()` 能覆盖新增模型
  3. 前后端接口路径一致
  4. smoke test 通过
  5. 前端构建通过
- 如果还没做真实联调或页面操作验证，只能说“代码与静态验证已通过”，不能直接说“功能已完成”。

### 高频坑

- 新增 ORM 模型后，必须同步更新 `backend/app/models/__init__.py`。
- 项目级接口统一走 `/api/projects/{project_id}/...`，不要写成 `/api/{project_id}/...`。
- `clue_tracker` 静态路由 `/clues/threads`、`/clues/red-herring`、`/clues/unresolved` 必须定义在 `/{clue_id}` 之前。
- `NovelDetailShell.vue` 这类壳组件里的弹窗 `@updated` 回调，必须指向当前组件真实存在的方法。

### 当前建议验证命令

```powershell
./verify.ps1 quick
./start.ps1
./verify.ps1 smoke
./verify.ps1 full

# 或手动执行
npm --prefix frontend run build
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
cd ..
backend\.venv\Scripts\python.exe tools/smoke_api_routes.py
backend\.venv\Scripts\python.exe tools/smoke_llm_settings_health.py
```

### 正式使用前推荐顺序

1. `./start.ps1`
2. `./verify.ps1 smoke`
3. 如涉及后端或关键链路改动，再跑 `./verify.ps1 full`
4. 使用完成后运行 `./stop.ps1`

### 协作与更新红线（每次更新都要遵守）

- 正式端口默认固定：Frontend `5174`、Backend `8013`。除非用户明确要求，否则不要修改 README、脚本、前端配置、启动命令里的默认端口，更不要把临时排查端口变成新的对外口径。
- 不要污染用户已保存配置。任何 smoke / e2e / 诊断脚本如果临时写入 LLM 配置，结束后必须恢复原配置，不能删除用户原有配置。
- 不要把 build 通过当成功能完成。涉及设置页、写作台、章节生成、章节评审等主链路改动时，至少运行对应 `verify.ps1` 套件，必要时补真实接口链路验证。
- 不要让通用 smoke 做破坏性写操作。通用验证脚本应以可达性、契约和非破坏性检查为主；会覆盖配置、删除数据或代价高的检查要单独控制。
- 不要在收口阶段继续扩散修改范围。优先只修主链路和本轮新增验证点，临时产物与测试脚本分开处理。
- 不要提交 `.env`、数据库、备份、日志、临时输出、测试产物等文件。

### 推荐优化工作流

1. 先在 `functional-zones.md` 确定要动的功能区。
2. 再在 `auto-file-index.md` 锁定候选文件。
3. 只读取该分区的入口文件与关联服务，不跨区扩散。
4. 变更完成后运行 `python tools/generate_code_index.py`，保持索引与代码同步。
5. CI 最小门槛以 `.github/workflows/xuanqiong-wenshu-quick-smoke.yml` 为准，先跑 quick + smoke。

## 关键入口

- 后端入口：`backend/app/main.py`
- 前端入口：`frontend/src/main.ts`
- 写作主链路：`backend/app/services/pipeline_orchestrator.py`
- LLM 网关：`backend/app/services/llm_service.py`
- 写作技能：`backend/app/services/writing_skills_service.py`
- 设置页：`frontend/src/components/LLMSettings.vue`
- 写作台：`frontend/src/components/writing-desk/`

## 仓库说明

当前 GitHub 项目建议使用：

- `https://github.com/xingluoyuankong/xuanqiong-wenshu`

提交时应排除：

- `.env`
- 数据库文件
- 备份文件
- 日志
- 临时输出
- 测试产物
- 本地 IDE / 代理配置（如 `.serena/`）
- 任何包含个人账号、邮箱、密钥、数据库口令或机器路径的私有配置

## License

MIT
