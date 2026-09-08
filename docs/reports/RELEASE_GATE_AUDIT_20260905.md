> **阶段七最新工程门禁**：后端2358通过（1020.08s），481源码/测试文件结束指纹一致；worker现代快照不再降级，等待审批依赖保留pending，267项组合及13/2/2/2反向检出。前端本批未改，沿用601/type-check/build16.89s。F02持久化审批续跑的事务生产者、专用job、原计划复用、ACK屏障和并发恢复仍未完成；完整API工作台E2E、7项文学质量缺口、Docker/MySQL实机仍待完成。发布NO-GO、目标active，当前状态文件顶部为权威入口。

> **当前接续入口（2026-09-07）**：请先阅读 `D:\小说写作\xuanqiong-wenshu\docs\reports\CURRENT_EXECUTION_STATUS_20260906.md`。本文件下方所有“最新/权威”字样均属于历史时点；当前门禁、原超时阈值恢复、未完成项及执行计划以该滚动状态表为准。旧证据保留，不代表当前全量通过。

# 玄穹文枢发布门禁审计（2026-09-05）

> **状态标记：本文原始审计快照及中间复核附录均已被文末 2026-09-06 当前 task 权威探针附录覆盖。**
> 原始章节和中间附录中的旧 HEAD、旧测试失败、旧文件统计和旧 smoke 数字只保留作历史证据；当前权威状态见文末“2026-09-06 当前 task 接续探针附录”，并与 `TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md` 文末权威复核保持一致。
> 历史附录曾记录 `62d4d8c`、`beec949`、`08531cc`、`23f7b0b`、`dbab070`；历史快照曾记录 `d8dcfcd`；`04f2a6e` 仅为历史快照；`f31cd8f` 仅为历史快照；当前最新 HEAD 为 `cc83270`（完整值见文末当前提交后复核附录）。当前发布结论：`active / NO-GO`。



> 审计类型：发布前只读核验与门禁清单
>
> 审计范围：当前分支未提交变更、迁移链、依赖可复现性、服务启动、基础 smoke、fresh/upgrade/downgrade 发布路径
>
> 写入范围：本独立报告；未编辑业务代码、迁移脚本、依赖清单、启动脚本或既有接续文档。

## 1. 发布结论

**当前结论：NO-GO。**

当前分支具备部分可复现证据，但还不满足发布准入条件：

1. 工作区存在 10 个 tracked 变更、95 个未跟踪项，其中 91 个为 `backend/storage` 下的二进制运行工件，另有未提交的 UI-005、UI-006、Agent runtime 相关源码与测试。
2. UI-005 后端定向门禁为 `18 passed, 1 failed`；失败测试为 `test_registry_enforces_declared_schema_string_bounds`，当前注册表没有兑现 manifest 中声明的 `minLength/maxLength` 校验合同。
3. `git diff --check` 报告 `backend/app/services/agent_runtime.py:2424: new blank line at EOF`。
4. 当前生产启动日志包含 `DEBUG 必须在生产环境关闭` 与 `ADMIN_DEFAULT_PASSWORD 仍是默认值` 警告。
5. `verify.ps1 smoke` 已通过基础探针和 OpenAPI/LLM smoke，但 259 项中有 204 项跳过，不等同于真实资源、完整回归和发布后验收。
6. fresh/upgrade/downgrade 的 SQLite 往返断言通过；独立临时数据库进程退出时出现一次 Windows `WinError 32` 文件锁清理告警，需纳入发布前复核。

## 2. 审计快照

### 2.1 Git 状态

| 项目 | 实测值 |
|---|---|
| 分支 | `codex/bohrium-integration-20260831` |
| HEAD | `599da4a9381cb2da8c2d9312340d57b7067ae49a` |
| 相对远端 | `ahead 50` |
| tracked 变更 | 10 个文件 |
| 未跟踪项 | 95 个 |
| 未跟踪二进制 | 91 个，约 68,289 bytes 汇总统计值来自当前 PowerShell 计数 |
| tracked diff | 1,026 行新增，29 行删除 |
| 新增非二进制项 | `.vite/vitest/results.json`、`backend/app/agent/test_registry_ui005_contract.py`、`backend/app/api/routers/test_agent_history_pagination.py`、`frontend/src/features/agent/AgentConversation.performance.spec.ts` |

当前 tracked 变更文件：

```text
TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
backend/app/agent/catalog_contract_v1.json
backend/app/agent/catalog_release.py
backend/app/agent/policy.py
backend/app/agent/registry.py
backend/app/agent/schemas.py
backend/app/api/routers/agent.py
backend/app/services/agent_runtime.py
frontend/src/features/agent/AgentConversation.spec.ts
frontend/src/features/agent/AgentConversation.vue
```

运行工件位于：

```text
backend/storage/novel_imports/9/*.bin
backend/storage/style_uploads/project-1/*.bin
```

这些工件需在发布打包前独立排除，保留在本地运行环境中，避免误入发布提交。

### 2.2 Evidence → Finding → Path

| Evidence | Finding | Path |
|---|---|---|
| `git status --short --branch`、`git diff --stat` | 工作区不是可直接打包的干净发布树；当前变更混合了 UI-005、UI-006、Agent runtime、接续文档和运行工件 | Git 工作区、当前分支 |
| `git diff --check` | 存在 `agent_runtime.py` 文件末尾新增空行提示；发布前需清理或明确纳入提交 | `backend/app/services/agent_runtime.py:2424` |
| `pytest ...test_registry_ui005_contract.py ...` | UI-005 schema bounds 回归失败 1 项；注册表合同尚未完全收口 | `backend/app/agent/registry.py`、`backend/app/agent/test_registry_ui005_contract.py` |
| `pytest ...test_alembic_migrations.py ...test_project_member_migration.py ...test_deployment_contract.py` | 迁移、项目成员迁移和部署契约专项通过 `16 passed` | `backend/app/services/test_alembic_migrations.py`、`backend/app/services/test_project_member_migration.py`、`backend/app/services/test_deployment_contract.py` |
| 临时 SQLite `head → head → base → head` | 版本往返断言到 `029_project_members`；进程退出阶段出现 Windows 文件锁清理告警 | `backend/alembic/versions/000_initial_schema.py` 至 `029_project_members.py` |
| `pip check` | 当前后端虚拟环境依赖无破损项 | `backend/requirements.txt`、`backend/requirements-dev.txt` |
| `npm ci --dry-run --ignore-scripts --no-audit --no-fund` | `frontend/package-lock.json` 可解析，npm 报 `up to date` | `frontend/package.json`、`frontend/package-lock.json` |
| `AgentConversation.spec.ts` | 10 项通过 | `frontend/src/features/agent/AgentConversation.spec.ts` |
| `npm run type-check`、`npm run build-only` | 类型检查通过；生产构建转换 4,918 个模块并成功完成 | `frontend/package.json`、`frontend/src/` |
| `verify.ps1 smoke` | 259 检查：55 通过、204 跳过、0 失败；三条健康探针为 200；OpenAPI 与 LLM settings smoke 通过 | `verify.ps1`、`tools/smoke_api_routes.py`、`tools/smoke_llm_settings_health.py` |
| `logs/run-20260905-082026/*` | 服务已启动并产生 backend/frontend 日志，但启动初期有代理连接拒绝和生产配置警告 | `logs/run-20260905-082026/backend.log`、`backend-error.log`、`frontend-error.log` |

## 3. 依赖与构建门禁

### 3.1 已核验

- Python：`3.11.9`。
- Node：`v24.14.0`，满足 `frontend/package.json` 的 `^20.19.0 || >=22.12.0`。
- npm：`11.9.0`。
- 后端依赖：`pip check` 返回 `No broken requirements found.`。
- 前端锁文件：`lockfileVersion: 3`，根包名为 `xuanqiong-wenshu-studio`，锁定包条目 551 个。
- npm dry-run：`up to date in 1s`。
- 前端 AgentConversation 专项：`1 file / 10 tests passed`。
- 前端生产构建：`4,918 modules transformed`，构建成功。

### 3.2 发布前阻断/观察项

| 等级 | 项目 | 门禁动作 |
|---|---|---|
| P0 | UI-005 `minLength/maxLength` 合同测试失败 | 修复实现与回归后，重新执行 UI-005 定向门禁及完整后端回归 |
| P0 | 当前工作区混合未提交源码与运行工件 | 形成明确 release commit，发布包只来自该 commit；运行工件单独归档 |
| P0 | 生产日志提示 DEBUG 与默认管理员密码 | 发布环境注入显式配置并复跑启动 smoke，日志中不得再出现这两条警告 |
| P1 | `baseline-browser-mapping` 与 `caniuse-lite` 数据过旧提示 | 依赖升级或在发布记录中接受并跟踪；升级后重跑 lockfile、类型、测试、构建 |
| P1 | tracked 文件存在换行/EOF 差异提示 | 发布前执行 `git diff --check`，输出为空才算通过 |

## 4. 迁移审计

### 4.1 迁移图

- Alembic 版本：`000_initial_schema` 至 `029_project_members`，共 30 个 revision 文件。
- 当前头：`029_project_members`。
- 当前数据库：在 `backend` 目录使用 `alembic.ini` 查询到 `029_project_members (head)`。
- revision 图为单线性链，无分叉头。
- `backend/alembic/env.py` 以 `settings.sqlalchemy_database_uri` 为运行时数据库 URL；`alembic.ini` 中的 SQLite URL属于回退/可读配置，执行时需确认环境变量和配置来源。

### 4.2 已实测往返

迁移专项和部署契约测试：

```text
backend/app/services/test_alembic_migrations.py
backend/app/services/test_project_member_migration.py
backend/app/services/test_deployment_contract.py

16 passed in 69.43s
```

独立临时 SQLite 往返：

```text
fresh upgrade:       029_project_members
repeat upgrade:      029_project_members
 downgrade base:     completed
 re-upgrade head:    029_project_members
```

阶段断言输出：

```text
{'fresh_head': '029_project_members',
 'repeat_head': '029_project_members',
 'base_version_table_count': 1,
 'reupgrade_head': '029_project_members'}
MIGRATION_ROUNDTRIP_PASSED
```

补充现象：Windows 进程退出时临时 SQLite 文件出现一次 `WinError 32` 清理告警。迁移阶段断言已完成，但发布前需确认实际服务、Alembic engine、SQLite 连接池在正常停止后都能释放文件句柄。

### 4.3 当前迁移风险

- `deploy/scripts/run_migrations.sh` 面向 MySQL，具备连接检查、`mysqldump --single-transaction`、Alembic `upgrade head` 和 `current`。
- `deploy/scripts/verify_migration.sh` 的非 strict 模式可以在存在检查失败时返回成功；发布门禁必须使用 `--strict`，并将 `failures=0` 作为硬条件。
- `deploy/docker-compose.yml` 有独立 `migrate` maintenance profile，命令为 `python -m alembic upgrade head`；生产发布需先执行迁移容器，再启动 app/worker。
- 当前 `deploy/scripts/rollback.sh` 是交互式 MySQL 备份恢复脚本，不是经过当前分支实测的 Alembic downgrade 自动化流程；默认 SQLite 部署不应直接套用该脚本。
- 生产 downgrade 尚缺少本分支、目标数据库引擎和真实备份恢复验证，发布前只能把“备份恢复演练通过”作为 downgrade 通过条件。

## 5. 服务启动与 smoke 证据

### 5.1 启动入口

Windows 本地入口：

```powershell
./start.ps1
./verify.ps1 smoke
./stop.ps1
```

`start.ps1` 当前启动 backend `127.0.0.1:8013` 与 frontend `127.0.0.1:5174`，每次写入时间目录 `logs/run-YYYYMMDD-HHMMSS`，并更新 `logs/latest-run.txt`。

Docker 入口：

```text
deploy/docker-entrypoint.sh
deploy/supervisord.conf
deploy/docker-compose.yml
```

Compose 关键服务：

- `app`：API 与 nginx 组合镜像。
- `agent-worker`：独立 Agent Job worker。
- `agent-command-worker`：独立 pause/resume/cancel worker。
- `migrate`：maintenance profile 迁移容器。
- `db`：MySQL profile 数据库服务。

原生 Linux/Bohrium 入口：

```bash
bash deploy/scripts/bohrium_native_release.sh
```

该脚本执行备份、远端 fast-forward、后端依赖安装、前端 `npm ci/build-only`、Supervisor 重启和 `/api/health` 验证；执行前需要确认 Unix 路径、虚拟环境、`runtime.env`、Supervisor 配置和 SQLite 数据文件均存在。

### 5.2 当前 smoke 实测

执行：

```powershell
./verify.ps1 smoke
```

结果：

```text
后端健康检查：200
前端首页：200
前端代理 health：200
OpenAPI 检查：259 总数，55 通过，204 跳过，0 失败
LLM settings smoke：通过
```

需要保留的解释：204 个跳过项主要依赖真实 project/chapter/resource ID；该结果证明路由无 500 级错误和基础服务可达，不等同于完整业务资源验收。

### 5.3 启动日志风险

`logs/run-20260905-082026/backend.log` 记录：

```text
启动安全警告：DEBUG 必须在生产环境关闭
启动安全警告：ADMIN_DEFAULT_PASSWORD 仍是默认值
```

`frontend-error.log` 记录后端尚未就绪阶段的两次：

```text
vite proxy error: /api/health
ECONNREFUSED 127.0.0.1:8013
```

最终三条 health probe 返回 200，说明服务随后就绪；发布前仍应让启动流程等待后端 readiness，再启动或放行前端代理 smoke，减少启动窗口中的误报。

## 6. Fresh 发布清单

适用场景：新环境、新 SQLite volume 或新 MySQL schema。

### 6.1 代码与依赖

- [ ] 取得唯一 release commit，工作树只包含该 release 内容。
- [ ] 确认 `git diff --check` 无输出。
- [ ] 排除 `backend/storage/**/*.bin`、日志、`.vite/`、`dist/`、本地数据库和临时锁文件。
- [ ] 使用 `backend/requirements.txt` 安装后端依赖。
- [ ] 在 `frontend` 执行 `npm ci`，禁止以 `npm install` 生成未审查的 lockfile 漂移。
- [ ] 运行 `pip check`、前端 type-check、Vitest、production build。

### 6.2 数据库

SQLite：

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c alembic.ini current
```

MySQL：

```bash
bash deploy/scripts/run_migrations.sh --dry-run
bash deploy/scripts/run_migrations.sh
bash deploy/scripts/verify_migration.sh --strict
```

Fresh 通过条件：

- schema 版本为 `029_project_members`；
- `alembic_version` 存在且只有一个 head；
- Agent、TaskRuntime、ProjectMember 关键表存在；
- 初始化管理员配置已注入，默认管理员密码告警消失；
- 迁移日志和备份路径已归档。

### 6.3 服务与 smoke

- [ ] 启动 API、Agent worker、command worker、frontend/nginx。
- [ ] 等待 `/api/health`、前端首页和前端代理 health 连续两次返回 200。
- [ ] 运行 `verify.ps1 smoke`。
- [ ] 使用真实 fresh fixture 完成登录、创建项目、创建 Agent session/run、生成/取消/恢复、SSE 或 durable event replay。
- [ ] 保存运行 ID、数据库版本、服务日志目录、commit SHA 和 smoke 摘要。

## 7. Upgrade 发布清单

适用场景：已有 `000` 至 `028` 或历史兼容 schema 的数据库升级到 `029_project_members`。

### 7.1 发布前

- [ ] 固化发布 commit 和上一版本 commit。
- [ ] 记录数据库引擎、版本、schema 当前 revision、数据库大小和关键表行数。
- [ ] SQLite 使用逻辑备份；MySQL 使用 `mysqldump --single-transaction --routines --events` 或等价一致性备份。
- [ ] 对 uploads、novel imports、style uploads 单独归档。
- [ ] 在复制库执行当前 revision 到 `029_project_members` 的升级。
- [ ] 对 `NovelProject.user_id` 旧 owner 验证 `project_members` owner 回填只发生一次。

### 7.2 执行顺序

```text
1. 进入维护窗口，停止会写数据库的 worker 或切换为 drain。
2. 生成数据库与上传工件备份，并记录 SHA-256/路径。
3. 运行 migration preflight 和当前 revision 记录。
4. 执行 Alembic upgrade head。
5. 使用 --strict 做 migration verification。
6. 部署后端依赖和前端静态资源。
7. 启动 app、agent-worker、agent-command-worker。
8. 等待 readiness，再执行基础 health、OpenAPI、LLM settings smoke。
9. 使用真实成员 fixture 验证 owner/editor/viewer/admin/outside 隔离。
10. 记录发布结果、日志目录、数据库 revision 和回滚点。
```

### 7.3 Upgrade 通过条件

- [ ] 升级前备份存在、大小非零、可读。
- [ ] 升级后 `current == 029_project_members`。
- [ ] 应用启动不再执行隐式 startup schema alteration。
- [ ] 新旧数据可读，旧项目 owner 已物化为 `project_members.role=owner`。
- [ ] 重复执行 `upgrade head` 幂等。
- [ ] 真实服务 smoke、完整后端回归和前端三门禁均通过。

## 8. Downgrade / rollback 发布清单

当前分支对 downgrade 的证据分为两类：

1. **迁移结构 downgrade**：临时 SQLite 已验证 `head → base → head`，项目成员专项已验证 `029 → 028` 后 `project_members` 移除且旧项目保留。
2. **生产 rollback**：当前脚本以 MySQL SQL 备份恢复为主，尚未在目标生产引擎和真实备份上完成本分支演练。

### 8.1 Downgrade 演练

- [ ] 复制生产数据库到隔离实例，不在在线库直接演练。
- [ ] 记录 `029_project_members` 迁移前后的 owner/member 行数。
- [ ] 在隔离实例执行目标 downgrade，并验证旧应用所需表、列、索引和数据可读。
- [ ] 验证 project member 回填数据在 downgrade 后的预期处理方式；若旧应用不识别该表，回滚必须采用数据库备份恢复而非仅降级 revision。
- [ ] 重新启动上一版本 API/worker，运行上一版本 health、登录、项目读取、章节读取和任务状态 smoke。
- [ ] 对 SQLite 验证文件句柄释放、锁文件释放和服务正常停止。
- [ ] 对 MySQL 验证备份恢复耗时、字符集、存储过程/事件和权限。

### 8.2 生产回滚顺序

```text
1. 触发发布回滚决定并冻结写入。
2. 保存当前版本日志、release.json、commit SHA、schema revision 和数据库摘要。
3. 先恢复应用版本；数据库按兼容矩阵决定“备份恢复”或“可逆 downgrade”。
4. 若使用备份恢复，先生成当前数据库 safety backup。
5. 恢复目标备份并执行数据完整性核验。
6. 启动上一版本 app/worker，确认 readiness。
7. 运行上一版本基础 smoke 与关键业务 smoke。
8. 观察错误日志、任务队列、迁移锁和数据库连接。
9. 归档回滚证据，保留当前版本备份以便二次恢复。
```

### 8.3 Downgrade 阻断条件

- [ ] 没有可读且已验证的备份。
- [ ] 上一版本不兼容 `029_project_members` schema。
- [ ] 只验证了 Alembic revision，没有验证上一版本真实业务读写。
- [ ] SQLite 文件仍被服务进程持有，或迁移锁未释放。
- [ ] 回滚后没有重新执行 health、登录、项目和任务状态 smoke。

## 9. 发布前总门禁

### P0 硬门禁

- [ ] 当前 release commit 唯一且可追溯。
- [ ] 工作区没有未审查源码变更。
- [ ] UI-005 当前失败测试已修复并通过。
- [ ] 后端完整 pytest 通过。
- [ ] 前端 `npm run type-check`、`npm run test:run`、`npm run build-only` 全部通过。
- [ ] `git diff --check` 无输出。
- [ ] fresh migration 通过。
- [ ] upgrade migration 通过且幂等。
- [ ] 目标数据库备份、上传工件备份和恢复抽样通过。
- [ ] 生产配置已替换默认管理员密码，DEBUG 警告消失。
- [ ] API、frontend、agent-worker、agent-command-worker readiness 全部通过。
- [ ] 真实资源 smoke 不依赖大量跳过项作为唯一证据。

### P1 强门禁

- [ ] migration verifier 使用 `--strict`。
- [ ] 运行一次真实成员协作验收：owner/editor/viewer/admin/outside。
- [ ] 运行一次 Agent durable event/SSE replay 验收。
- [ ] 运行一次 worker cancel/resume/recovery 验收。
- [ ] 运行一次质量闸门和章节版本接受验收。
- [ ] 记录启动冷启动时间、readiness 时间、迁移耗时、smoke 耗时。
- [ ] 记录日志目录、数据库 revision、commit SHA、备份路径和摘要哈希。
- [ ] 对 SQLite 确认迁移锁和连接句柄释放；对 MySQL 确认连接、字符集和权限。

### P2 观察项

- [ ] 更新或接受 `baseline-browser-mapping`、`caniuse-lite` 数据提示。
- [ ] 评估将完整 smoke 中依赖真实资源 ID 的项目改为隔离 fixture。
- [ ] 增加可自动执行的 production downgrade/restore 演练证据。
- [ ] 为发布结果建立固定格式的 machine-readable summary。

## 10. 本次审计执行记录

```text
分支：codex/bohrium-integration-20260831
HEAD：599da4a9381cb2da8c2d9312340d57b7067ae49a
日期：2026-09-05

迁移/部署专项：16 passed in 69.43s
后端 UI-005 定向：18 passed, 1 failed
前端 AgentConversation：10 passed
前端 type-check：通过
前端 build-only：成功，4918 modules transformed
pip check：No broken requirements found
npm ci dry-run：up to date
verify.ps1 smoke：259 checks = 55 passed / 204 skipped / 0 failed
基础 health：backend 200 / frontend 200 / proxy 200
```

### 复核命令

```powershell
# Git 与静态门禁
 git status --short --branch
 git diff --check

# 后端依赖与迁移
 .\backend\.venv\Scripts\python.exe -m pip check
 Push-Location backend
 .\.venv\Scripts\python.exe -m alembic -c alembic.ini current
 .\.venv\Scripts\python.exe -m alembic -c alembic.ini heads
 Pop-Location

# 迁移与部署专项
 .\backend\.venv\Scripts\python.exe -m pytest -q `
   backend/app/services/test_alembic_migrations.py `
   backend/app/services/test_project_member_migration.py `
   backend/app/services/test_deployment_contract.py

# 前端门禁
 npm --prefix frontend run type-check
 Push-Location frontend
 npm exec vitest run src/features/agent/AgentConversation.spec.ts
 npm run build-only
 Pop-Location

# 服务 smoke
 .\verify.ps1 smoke
```

## 11. 结论与下一动作

当前报告只完成发布门禁审查与清单固化，不对现有业务实现作收口性修改。

发布前最短闭环：

1. 收口当前未提交源码与测试变更，保留运行工件在发布包之外。
2. 修复 UI-005 schema bounds 失败，并补齐反向回归。
3. 清理 `agent_runtime.py` EOF diff，直到 `git diff --check` 无输出。
4. 在非默认生产配置下重启服务，复跑完整 smoke。
5. 执行完整后端 pytest、完整前端三门禁和真实 fixture 验收。
6. 在隔离数据库完成 upgrade、restore/downgrade 演练并归档证据。
7. 重新生成 release summary 后再进行发布决策。

在上述 P0 项全部满足前，保持 **NO-GO**。

## 当前复核附录（2026-09-05，覆盖原始快照结论）

```text
HEAD: 62d4d8c docs: record latest release environment facts
Backend full pytest: 1761 passed
Frontend full Vitest: 81 files / 536 tests passed
Frontend type-check: PASS
Frontend build-only: 4918 modules transformed, PASS
TCP/JWT projectless pagination: 180 messages / 3 pages / no duplicates
TCP/JWT member matrix: 125 messages / viewer=200 / shared outsider=403 / private outsider=404
SQLite backup/restore matrix: PASS / exit=0
Production smoke: 261 checks / 51 passed / 210 skipped / 0 failed
Agent worker --once: exit=0
Agent command worker --once: exit=0
Docker daemon: unavailable on current host
MySQL TCP resource: unavailable on current host

Current NO-GO reasons:
1. Docker Compose runtime health cannot be evidenced while the Docker daemon is unavailable.
2. Formal MySQL migration/backup/restore/rollback cannot be evidenced without a MySQL resource.
3. Smoke still has 210 real-resource-dependent skips.
```



## 当前 HEAD 复核附录（2026-09-05，覆盖前述所有旧快照）

### 1. 当前提交与工作树

```text
分支：codex/bohrium-integration-20260831
当前 HEAD：beec949 docs: supersede stale release audit snapshot
当前 HEAD 已包含的关键提交链：
  92a03cc perf: paginate agent run history in workspace
  3cf7bdb test: lock session detail payload compatibility contract
  508d53f test: add isolated migration backup restore matrix
  d560d4f test: add tcp jwt member pagination acceptance
  ce2b664 fix: accept authenticated production llm smoke
跟踪文件未提交：无
未跟踪内容：.vite、日志、backend/storage/**/*.bin 等运行工件，均保留在发布包边界之外
```

### 2. 当前代码与回归证据

```text
后端全量 pytest：1761 passed in 961.27s (0:16:01)
前端全量 Vitest：81 files / 536 tests passed
前端 npm run type-check：通过
前端 npm run build-only：通过，4918 modules transformed
git diff --check：通过
前端 Run/Session/Workspace/API 定向：4 files / 69 tests passed
迁移/项目成员/部署合同：16 passed
```

已验证的成员权限与执行身份主线继续保持通过：Owner/Editor/Viewer/非成员 project 读取边界、Writer 执行身份、Agent capability snapshot、Viewer 写入阻断、projectless 私有执行身份均有当前仓库专项证据。

### 3. 当前分页与真实 HTTP 证据

```text
TCP_MESSAGE_PAGINATION_PASSED
180 messages / limit=60 / 3 pages / duplicate_count=0

TCP_MEMBER_PAGINATION_PASSED
125 messages / 3 pages / viewer=200 / shared outsider=403 / projectless outsider=404

TCP_JWT_RUN_PAGINATION_PASSED
125 runs / limit=50 / 3 pages / duplicate_count=0
```

前端首屏已经使用：

```text
GET /sessions/{id}?include_messages=false&include_runs=false
GET /sessions/{id}/messages?limit=60
GET /sessions/{id}/runs?limit=50
```

旧详情无参数的 `include_messages=true`、`include_runs=true` 兼容合同由测试锁定，尚未翻转默认值。

### 4. 当前迁移、生产配置和 Worker 证据

```text
MIGRATION_BACKUP_RESTORE_MATRIX_PASSED
fresh/repeat/downgrade/restore/re-upgrade：通过
backup_sha256 == restored_sha256：True

显式 production API 临时配置：health=200，security_warnings=0
Agent worker --once：exit=0
Agent command worker --once：exit=0
Docker Compose config：default/maintenance/mysql profiles 解析通过
```

### 5. 当前未闭合门禁与 NO-GO 原因

```text
发布结论：active / NO-GO
```

剩余原因仅按证据边界记录，不将缺失资源推断为通过：

1. 当前主机 Docker Engine 不可用，只能完成 Compose 静态解析，尚无真实容器 app、migrate、agent-worker、agent-command-worker 健康矩阵。
2. 当前主机没有 MySQL 客户端，3306 无监听，正式 MySQL TCP migration、backup/restore、rollback 尚未实测。
3. `verify.ps1 smoke` 仍有约 210 项依赖真实项目/章节/Artifact 资源的跳过项，不能单独代表完整业务验收。
4. Compose 静态解析时可选 Linux.do/SMTP 配置为空值提示仍需在正式部署配置中按功能开关注入。
5. 发布审计只在正式 Docker/MySQL/真实资源节点完成后重判 GO/NO-GO。

前述报告正文和旧附录中的 `599da4a`、`62d4d8c`、204 skipped、旧 UI-005 失败等内容均为历史快照；当前结论以本附录和接续文档最新章节为准。

## 当前 HEAD 最新复核附录（2026-09-05，08531cc）

```text
HEAD: 08531cc test: harden run pagination and refresh audit
Frontend lifecycle targeted: 14 passed
Frontend full baseline: 81 files / 536 passed
Backend full baseline: 1761 passed
TCP message pagination: 180 messages / 3 pages / no duplicates
TCP member pagination: 125 messages / viewer=200 / shared outsider=403 / private outsider=404
TCP Run pagination: 125 runs / limit=50 / 3 pages / no duplicates
SQLite backup/restore matrix: PASS / exit=0
Production smoke: 261 checks / 51 passed / 210 skipped / 0 failed
Agent worker --once: exit=0
Agent command worker --once: exit=0
Docker daemon: unavailable
MySQL TCP resource: unavailable

Current conclusion: active / NO-GO
Remaining gates: real Compose orchestration, formal MySQL migration and restore, real-resource smoke coverage.
```

## 最新当前 HEAD 附录（23f7b0b，2026-09-05）

```text
HEAD: 23f7b0b test: add authenticated smoke fixture coverage
Authenticated smoke: credentials mode
Writer live create/generate/cancel path: exercised; cleanup status checked
Smoke: 261 total / 55 passed / 206 skipped / 0 failed
Skip categories: expensive=2, mutating=6, resource-identity=198
Frontend full baseline: 81 files / 536 passed
Backend full baseline: 1761 passed
TCP message: 180 messages / 3 pages / no duplicates
TCP member: 125 messages / viewer=200 / shared outsider=403 / private outsider=404
TCP Run: 125 runs / 3 pages / no duplicates
SQLite backup/restore: PASS
Docker daemon: unavailable
MySQL TCP: unavailable
Conclusion: active / NO-GO
```

## 2026-09-05 Smoke lifecycle 最新附录

```text
HEAD before report commit: 1adea10
Authenticated smoke: credentials
Total: 261
Passed: 53
Skipped: 208
Failed: 0
Skipped by reason: mutating=6, expensive=2, resource-identity=198, live-prerequisite=2
Fixture DELETE status: checked and passed
Live generate/cancel: executed
Live evaluate/select: gated until a completed candidate exists
Conclusion: active / NO-GO
```

## 当前 HEAD 复核附录（2026-09-05，OpenAPI smoke 认证门禁修复）

```text
修复前现象：verify.ps1 smoke 在 configure_auth() 的匿名分支触发 NameError: AUTH_MODE 未定义
修复文件：tools/smoke_api_routes.py
回归文件：backend/app/services/test_smoke_api_routes.py
匿名认证回归：1 passed
成员/Writer/Agent/TaskRuntime/迁移/部署组合：187 passed + 17 passed
OpenAPI smoke：261 checks / 53 passed / 208 skipped / 0 failed
LLM 设置 smoke：通过
py_compile：通过
git diff --check：通过
```

本轮修复只涉及 smoke 认证状态初始化和对应回归测试，没有修改成员权限、Writer/Agent 业务授权逻辑。当前发布结论仍为 `active / NO-GO`；真实 Docker Compose、正式 MySQL 迁移恢复回滚和真实资源 smoke 覆盖仍需部署资源证据。

## 当前 HEAD 复核附录（2026-09-05，smoke 门禁提交后）

```text
HEAD: dbab070 test: lock anonymous smoke auth initialization
OpenAPI/LLM smoke: 261 checks / 53 passed / 208 skipped / 0 failed
Smoke auth regression: 1 passed
Member/Writer/Agent/TaskRuntime/migration/deployment targeted: 187 + 17 passed
Default SQLite smoke fixture audit: 21 historical fixtures; 20 legacy OpenAPI Smoke 0 with stale TaskRuntime, 1 UUID fixture
py_compile: PASS
git diff --check: PASS
```

本轮已关闭 smoke 匿名认证初始化阻断；历史 fixture 仅盘点未删除。发布结论继续为 `active / NO-GO`，剩余原因是 Docker Compose、正式 MySQL 和完整真实资源 smoke 证据。


## 当前 HEAD 复核附录（2026-09-05，d8dcfcd，覆盖前述所有旧快照）

> 本附录是本报告唯一的当前权威口径。第 1—11 节及其后 `62d4d8c`、`beec949`、`08531cc`、`23f7b0b`、`dbab070` 等附录中的不同 HEAD、`1761 passed`、旧前端测试数和旧 smoke 数字均为历史快照。

### Git 与全量门禁

```text
分支：codex/bohrium-integration-20260831
HEAD：d8dcfcdd1ff521131d8721cf256b54fa21f3ae7c
HEAD 提交：docs: record smoke gate closure and fixture audit
验证采集时 tracked 源码/测试未提交文件：无
本次文档同步产生的 tracked 修改：TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md、docs/reports/RELEASE_GATE_AUDIT_20260905.md
未跟踪内容：.vite、logs、backend/storage/**/*.bin、两份 smoke fixture dry-run 工件，保留在发布包边界之外

后端全量 pytest：1763 passed in 899.01s (0:14:59)
前端全量 Vitest：81 files / 536 tests passed in 84.59s
前端 type-check：PASS
前端 build-only：4918 modules transformed，PASS，built in 35.65s
git diff --check：PASS
```

### Run 分页权威证据

```text
后端 Run/消息/Runtime 专项：36 passed in 39.11s
前端 Agent API/Session Lifecycle/Conversation/Workspace：4 files / 69 tests passed in 8.20s
TCP_JWT_RUN_PAGINATION_PASSED
125 runs / limit=50 / 3 pages / duplicate_count=0
游标：before_created_at + before_id；页内 created_at + id 升序；fixture 已回收
```

真实验收命令：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe scripts\agent_tcp_run_pagination_acceptance.py --count 125 --limit 50
```

### 当前发布结论与剩余门禁

```text
发布结论：active / NO-GO
最新已记录 smoke：261 checks / 53 passed / 208 skipped / 0 failed
已闭合：Run 分页服务—客户端链路、真实 125 Run TCP/JWT 复合游标验收、后端/前端全量回归、前端 type-check/build
未闭合：Docker Engine 实际 Compose app/migrate/agent-worker/agent-command-worker 健康矩阵；正式 MySQL migration/backup/restore/rollback；完整真实资源 smoke 覆盖
```

后续任何提交后，必须以新 HEAD 重新执行并更新本附录；旧附录不得继续充当当前发布证据。

## 当前 HEAD 复核附录（2026-09-05，acceptance 套件实测）

```text
验收入口：verify.ps1 acceptance
结果：exit=0
TCP message pagination：PASS / 180 messages / 3 pages / duplicate_count=0
TCP member pagination：PASS / 125 messages / viewer=200 / shared outsider=403 / private outsider=404
TCP Run pagination：PASS / 125 runs / 3 pages / duplicate_count=0
SQLite migration backup/restore：PASS / fresh-repeat-downgrade-restore-reupgrade
Agent worker --once：PASS
Agent command worker --once：PASS
```

该套件已把当前主机可执行的成员权限、消息/Run 长历史、迁移恢复和 Worker 入口验收固化为单一命令。Docker Compose 实际容器编排和正式 MySQL TCP 仍需对应资源节点。

## 当前 HEAD 复核附录（2026-09-05，全量门禁与 acceptance 接线后）

```text
HEAD: 9d21c64 test: add unified acceptance verification suite
Backend full pytest: 1764 passed
Frontend full Vitest: 81 files / 544 tests passed
Frontend type-check: PASS
Frontend build-only: 4918 modules transformed, PASS
OpenAPI/LLM smoke: 261 checks / 53 passed / 208 skipped / 0 failed
verify.ps1 acceptance: PASS / exit=0
Writer/Agent/member/TaskRuntime targeted: 187 passed
Migration/deployment/member targeted: 17 passed
Smoke auth regression: 1 passed
git diff --check: PASS
```

当前仍为 `active / NO-GO`：Docker Compose 实际编排、正式 MySQL migration/backup/restore/rollback 和完整真实资源 smoke 覆盖尚未获得对应资源节点证据。

## 2026-09-05 Acceptance suite 最新复核

```text
verify.ps1 -Suite acceptance：PASS
6/6 steps passed
TCP message/member/Run pagination：PASS
SQLite migration backup/restore：PASS
Agent worker --once：PASS
Agent command worker --once：PASS
Docker daemon：仍无 Server 响应
MySQL TCP：无监听
Current conclusion：active / NO-GO
```


## 当前 HEAD 复核附录（2026-09-05，441fedf）

```text
HEAD: 441fedf test: add acceptance suite orchestration
Tracked working tree: clean
Backend full pytest: 1764 passed
Frontend full Vitest: 81 files / 544 tests passed
Frontend type-check: PASS
Frontend build-only: 4918 modules transformed, PASS
OpenAPI/LLM smoke: 261 total / 53 passed / 208 skipped / 0 failed
verify.ps1 acceptance: 6/6 PASS
Writer/Agent/member/TaskRuntime targeted: 187 passed
Migration/deployment/member targeted: 17 passed
```

Current conclusion remains `active / NO-GO`; the remaining gates require Docker Compose runtime, formal MySQL resources, broader real-resource smoke, and final release adjudication.

## 2026-09-06 当前 task 接续探针附录

```text
历史会话：全面优化重构玄穹文枢 / 01a02410-94af-7002-9585-3532293aa587
当前 task：01a06d1c-19e0-75e0-a30e-9c3d0bae9867
分支：codex/bohrium-integration-20260831
HEAD：04f2a6eb8d7bfaecb4ec8e76d141c4e6e7a77317
Docker Compose CLI：v5.1.3
Compose config：PASS（注入 SECRET_KEY、ADMIN_DEFAULT_PASSWORD、MYSQL_ROOT_PASSWORD、MYSQL_PASSWORD）
Compose service parse：app / agent-worker / agent-command-worker
Docker server：未响应，dockerDesktopLinuxEngine named pipe 不存在
com.docker.service：Stopped / Manual
MySQL TCP：127.0.0.1:3306=false；127.0.0.1:3309=false
本地 MySQL 脚本：默认 D:/download/MySQL/bin/mysqld.exe 不存在
发布结论：active / NO-GO
```

本附录新增了静态 Compose 配置通过的证据，但未把缺失 Docker Engine、MySQL 实例和完整真实资源 smoke 误判为通过。`.audit-openapi-smoke-fixtures-20260905.jsonl` 为历史未跟踪只读盘点工件，包含 18 条记录；当前 SQLite 直读结果为 21 条，最新结果保存于 `.audit-openapi-smoke-fixtures-current-20260906.json`；两者均留在工作区且不进入发布提交。

### 2026-09-06 历史 fixture 只读 dry-run 补充

```text
命令：backend\.venv\Scripts\python.exe backend/scripts/audit_smoke_fixtures.py --db backend/storage/xuanqiong_wenshu.db
结果：SMOKE_FIXTURE_AUDIT_PASSED
fixture_count：21
标题：20 条 OpenAPI Smoke 0，1 条带 UUID 后缀
runtime：21/21 关联 task 状态 stale
资源关系：每条 1 chapter、1 outline、1 blueprint、1 runtime task、1 member、1 token budget
回收动作：0；仅生成 .audit-openapi-smoke-fixtures-current-20260906.json dry-run 工件
```

回收前仍需基于 owner、marker、年龄、终态、关联事件和可恢复备份做二次确认；本次没有删除历史数据。
## 2026-09-06 当前 HEAD 最终权威复核（d26466f）

```text
HEAD：d26466f7bddf71a48512aa17a7ead283676df749
HEAD 提交：audit: make smoke fixture dry-run deterministic
分支：codex/bohrium-integration-20260831
定向回归：2 passed（fixture dry-run 决策、smoke API 认证）
fixture dry-run：SMOKE_FIXTURE_AUDIT_PASSED / 21 条 / candidate=21
固定时间：2026-09-06T00:00:00+08:00
git diff --check：PASS
当前发布结论：active / NO-GO
```

本次提交把 fixture 审计扩展为确定性只读 dry-run：输出 owner、runtime 明细、marker、年龄和决策统计，并对空任务集及活动任务采用 hold 规则；本次回收动作仍为 0。Docker Compose runtime、正式 MySQL 迁移恢复回滚和完整真实资源 smoke 仍待对应资源节点。
## 2026-09-06 当前 HEAD 最终同步（2781212）

```text
HEAD：2781212a49fda0d484943641154d19fc033cf68e
HEAD 提交：docs: sync current handoff audit head
分支：codex/bohrium-integration-20260831
本次新增：将当前 task 的最终 HEAD、fixture dry-run 和 Docker/MySQL 探针同步到接续文档与发布审计
定向回归：2 passed
fixture dry-run：SMOKE_FIXTURE_AUDIT_PASSED / 21 条 / candidate=21
Docker Compose 静态 config：PASS；Docker Server：未响应
MySQL TCP 3306/3309：均未监听
git diff --check：PASS
当前发布结论：active / NO-GO
```

本附录覆盖此前 `d26466f`、`04f2a6e`、`441fedf` 等旧快照；旧数字和旧工作树描述仅作历史证据。当前运行工件继续保留在工作区外发布边界，未执行 fixture 回收。
## 2026-09-06 当前 HEAD 最终复核（f31cd8f）

```text
HEAD：f31cd8f566d9b76c10df014b2f889cf18c8c5fe2
HEAD 提交：audit: honor smoke fixture markers and age gate
分支：codex/bohrium-integration-20260831
新增定向回归：2 passed
fixture dry-run：SMOKE_FIXTURE_AUDIT_PASSED / 21 条
决策统计：candidate=20；hold-marked-fixture=1
固定复核时间：2026-09-06T00:00:00+08:00
年龄门槛：3600 秒
Docker Compose 静态 config：PASS；Docker Server：未响应
MySQL TCP 127.0.0.1:3306/3309：均未监听
当前发布结论：active / NO-GO
```

本轮 dry-run 改为读取 `initial_prompt` 与标题中的真实 `xq-smoke-fixture:<id>` marker，并对带 marker 的 fixture 默认 hold；终态、无 marker 且达到年龄门槛的 legacy fixture 才列为 candidate。本轮仍未执行回收或删除。
## 当前工作树状态（2026-09-06 复核后）

```text
HEAD：f31cd8f566d9b76c10df014b2f889cf18c8c5fe2
tracked 未提交修改：本接续文档、本文档（仅同步当前审计口径）
未跟踪运行工件：.vite、logs、backend/storage/**/*.bin、smoke fixture JSON/JSONL，以及既有盘点工件；全部保留，不纳入发布提交
git diff --check：PASS
```
## 2026-09-06 当前 HEAD smoke 分组复核（7aefff1）

```text
HEAD：7aefff1b7af20d62cd5957119ffb3df0f4d03454
HEAD 提交：test: group resource identity smoke skips
OpenAPI smoke：261 / 53 passed / 208 skipped / 0 failed
resource-identity：198 项，已按参数族分组输出
定向回归：3 passed
开发栈：backend/frontend/proxy 均通过健康检查
当前发布结论：active / NO-GO
```

资源身份跳过分组已输出到 `logs/smoke-current-20260906.log`，首要族为 `project_id=135`、`run_id=26`、`task_id=14`、`artifact_id=8`。本轮只增强观测和回归，没有伪造资源 ID，也没有改变跳过项为通过。
## 当前提交后 smoke 复核（cc83270）

```text
HEAD：cc83270a4cffaff81ea7792b3d7f9ce6cbf28b4f
HEAD 提交：fix: close smoke-discovered clue and stream gaps
OpenAPI smoke：261 checks / 114 passed / 147 skipped / 0 failed
跳过分类：resource-identity=136；mutating=6；expensive=2；live-resource-prerequisite=2；streaming=1
定向回归：4 passed
clues/overview：200
Docker Compose 静态 config：PASS；Docker Server：未响应
MySQL TCP 3306/3309：均未监听
当前发布结论：active / NO-GO
```

本轮关闭了 smoke 放开项目级 GET 后发现的 `clues/overview` 500，并将长连接 SSE 路由纳入独立流式验收分类。旧附录中的 `53/208` smoke 数字降级为历史快照；当前权威 smoke 数字为 `114/147/0`。
## 当前提交后全量门禁复核（HEAD cc83270）

```text
HEAD：cc83270a4cffaff81ea7792b3d7f9ce6cbf28b4f
Backend full pytest：1766 passed in 639.84s
Frontend full Vitest：81 files / 544 tests passed in 279.44s
Frontend type-check：PASS
Frontend build-only：PASS / 4918 modules transformed
OpenAPI smoke：261 total / 114 passed / 147 skipped / 0 failed
定向回归：4 passed
git diff --check：PASS
当前发布结论：active / NO-GO
```

本次门禁是在提交后重新执行，确认 clue overview 修复和 smoke 项目级 GET 覆盖没有引入回归。跳过项主要仍集中于未知资源 ID、写入型接口、高开销接口和长连接 SSE；这些分类均已显式记录。
## 当前提交后 clue fixture 覆盖复核（cdd2907）

```text
HEAD：cdd29070372171bef0df29fe17f9e9abef4a8f6e
HEAD 提交：test: cover clue resources in smoke fixture
OpenAPI smoke：261 / 116 passed / 145 skipped / 0 failed
clue detail：200
clue timeline：200
resource-identity：134
定向回归：3 passed
当前发布结论：active / NO-GO
```

本轮增加了可回收 clue fixture，并让 clue detail/timeline 两个 GET 路由使用真实 `clue_id`；临时项目清理后不保留该 fixture。后续继续按资源族补齐 artifact、run、task 等真实数据。
## 当前提交后 runtime 清理复核（e0b242a）

```text
HEAD：e0b242abd109a916df8f454343fe72cf72116283
HEAD 提交：fix: clean project runtime tasks during smoke
定向回归：8 passed
OpenAPI smoke：261 / 115 passed / 146 skipped / 0 failed
项目数前后：21 -> 21
TaskRuntime 总数前后：83 -> 83
generation_log 全局任务前后：38 -> 38
Docker Compose 静态 config：PASS；Docker Server：未响应
MySQL TCP 3306/3309：均未监听
当前发布结论：active / NO-GO
```

本轮确认项目删除与 smoke 清理不会继续增加 TaskRuntime 孤儿记录；历史孤儿记录保持只读留存，后续另行按 owner、marker、年龄和运行状态制定回收动作。
## 当前提交后 acceptance 全量复核（HEAD e0b242a）

```text
HEAD：e0b242abd109a916df8f454343fe72cf72116283
verify.ps1 -Suite acceptance：PASS / 6 of 6
消息分页：180 / 3 pages / duplicate_count=0
成员分页：125 / shared outsider=403 / private outsider=404
Run 分页：125 / 3 pages / duplicate_count=0
SQLite migration backup/restore：PASS
source/restored SHA256：bdb7b58ab2f21f4e7f44606ad28bf02f29a4d4689cc7fdc344911f1fc89d9cb3
sentinel_count：1
Agent worker --once：PASS
Agent command worker --once：PASS
OpenAPI smoke：261 / 115 passed / 146 skipped / 0 failed
当前发布结论：active / NO-GO
```

Acceptance 在 runtime 清理修复后重新通过，说明项目删除时清理 TaskRuntime/TaskRuntimeEvent 不影响分页、权限、迁移恢复和 worker 生命周期。
## 当前提交后 task fixture 覆盖复核（74ae303）

```text
HEAD：74ae303e5be70a95c27ffb1f4482fc75811bfaef
HEAD 提交：test: cover generated task runtime routes
OpenAPI smoke：261 / 117 passed / 144 skipped / 0 failed
resource-identity：129
streaming-route：4
定向回归：3 passed
TaskRuntime 前后：83 -> 83
generation_log 前后：38 -> 38
当前发布结论：active / NO-GO
```

本轮真实生成响应中的 TaskRuntime ID 已接入 smoke context，task detail/events 路由完成真实请求；没有新增孤儿任务。长连接流式路由继续由独立 SSE 验收覆盖。
## 当前提交后 Agent session fixture 覆盖复核（7322537）

```text
HEAD：7322537fa80c427e59622fe7c6c64362a3a3e3aa
HEAD 提交：test: cover agent sessions in smoke fixture
OpenAPI smoke：261 / 119 passed / 142 skipped / 0 failed
resource-identity：126
streaming-route：4
定向回归：7 passed
项目数：21 -> 21
TaskRuntime：83 -> 83
AgentSession：44 -> 44
generation_log：38 -> 38
当前发布结论：active / NO-GO
```

Agent session 详情、消息列表和 Run 列表已使用真实 session fixture 验收；项目清理前后 session/task/global-log 计数一致。Provider、AgentRun、Artifact 深层资源仍留待独立运行验收。
## 当前 HEAD Agent session 后 acceptance 复核（7322537）

```text
HEAD：7322537fa80c427e59622fe7c6c64362a3a3e3aa
verify.ps1 -Suite acceptance：PASS / 6 of 6
OpenAPI smoke：261 / 119 passed / 142 skipped / 0 failed
source/restored SHA256：ab250b5a71df04915fa994da3545ee2e9a5d86c9ec97eb7b98c8d3c56f3f68a7
sentinel_count：1
项目数：21 -> 21
TaskRuntime：83 -> 83
AgentSession：44 -> 44
generation_log：38 -> 38
当前发布结论：active / NO-GO
```

Agent session detail/messages/runs 的真实 GET 覆盖已加入 smoke；项目删除显式清理 AgentSession，前后数据库计数一致。
## 当前 HEAD 全量后端门禁复核（4e01c67）

```text
HEAD：4e01c67a75d3d2319fb57b3f6274b334e84b9e06
Backend full pytest：1767 passed in 675.48s
Frontend full Vitest：81 files / 544 tests passed
Frontend type-check：PASS
Frontend build-only：PASS / 4918 modules transformed
OpenAPI smoke：261 / 119 passed / 142 skipped / 0 failed
verify.ps1 acceptance：6/6 PASS
git diff --check：PASS
当前发布结论：active / NO-GO
```

后端全量测试已覆盖 AgentSession 项目删除级联清理；剩余发布缺口仍是 Docker runtime、正式 MySQL 矩阵和 AgentRun/Artifact 深层真实资源覆盖。
## AgentRun/Artifact 深层 fixture 探针复核

```text
探针：临时 project + AgentSession + message + run/events + cancel + project delete
message submit：503
error_code：AGENT_EVENT_LEDGER_UNAVAILABLE
AgentRun/Artifact 有效证据：未形成
探针清理：完成
AgentRun 前后：1 -> 1
Artifact 前后：0 -> 0
AgentSession 前后：44 -> 44
TaskRuntime 前后：83 -> 83
```

当前发布结论继续为 `active / NO-GO`。该 503 被记录为真实环境缺口，不降级为通过；下一步需在事件账本可写后重跑 AgentRun、Provider 和 Artifact 质量/内容/lineage GET 验收。
## 当前 HEAD AgentRun fixture 覆盖复核（c328788）

```text
HEAD：c3287885a4259e84e5d09f375bd2b5e5588faf8f
HEAD 提交：fix: advance agent catalog generation for run smoke
Catalog generation：2
Catalog/runtime targeted：45 passed
Smoke targeted：3 passed
OpenAPI smoke：261 / 135 passed / 126 skipped / 0 failed
resource-identity：109
streaming-route：4
AgentRun：message=201；detail=200；events=200
Artifact：0，仍待 Provider/Artifact 生成链路
当前发布结论：active / NO-GO
```

本轮解决 `agent_catalog_releases(catalog_id,generation)` 与旧 digest 冲突造成的 AgentRun 503；新 generation=2 后事件账本写入正常。探针清理后没有新增项目、Run、Artifact、Session 或 TaskRuntime 残留。
## 本轮权威发布审计快照（追加记录，保留全部历史证据）

> 本节针对当前接续批次重新整理证据状态。此前报告中的历史结论、历史 HEAD、历史测试数字和历史探针结果均保留；本节只新增当前判定依据，不回写旧记录。

### 1. 当前版本与证据状态

```text
审计对象分支：codex/bohrium-integration-20260831
当前 HEAD：dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb
HEAD 提交：docs: record agent run smoke coverage
AgentRun 修复提交：c3287885a4259e84e5d09f375bd2b5e5588faf8f
编辑前 tracked 工作树：clean；当前 tracked 改动仅为本轮两份指定文档
既有未跟踪运行工件：138 项，保留原状
本轮文档范围：仅本接续文档与本发布审计文档
```

### 2. 通过、历史基线与阻塞矩阵

| 检查项 | 结果 | 证据状态 | 发布含义 |
|---|---:|---|---|
| Catalog generation 冲突修复 | PASS | 当前 `c328788` | AgentRun 创建阻塞已解除 |
| AgentRun message/detail/events | 201/200/200 | 当前 | 基础 Run 读写链已形成证据 |
| AgentRun 定向回归 | 45 passed | 当前 | Catalog/runtime 修复有回归覆盖 |
| OpenAPI smoke | 261 / 135 / 126 / 0 | 当前 | 无失败，但 109 项资源身份和 4 项流式路由仍未覆盖 |
| fixture 审计 | PASSED | 当前 | 21 个 fixture 的 dry-run 通过；未执行回收动作 |
| 后端全量 pytest | 1767 passed | 历史 | 结果早于 `c328788`，当前发布批次仍需重跑 |
| 前端门禁 | 544 tests、type-check、build 通过 | 历史 | 当前发布批次仍需复核 |
| acceptance | 6/6 PASS | 历史 | 当前发布批次仍需重跑 |
| AgentRun cancel | 503 记录仍未闭合 | 当前缺口 | 运行生命周期无法判定为完整通过 |
| Provider/Artifact | 未形成真实完整链路；Artifact=0 | 当前缺口 | Artifact 资源族无法判定为通过 |
| Docker Server | 未响应 | 当前缺口 | Compose 运行矩阵缺失 |
| MySQL 3306/3309 | 均未监听 | 当前缺口 | 正式数据库矩阵缺失 |

### 3. 当前 NO-GO 判定

```text
任务状态：active
发布状态：NO-GO
判定依据：P0 门禁尚未全部闭合
```

本次 `c328788` 已实质关闭一个 AgentRun 创建阻塞，但它只证明事件账本写入恢复，不代表 cancel、Provider、worker、terminal Run、Artifact、Docker Compose 和正式 MySQL 全部通过。当前保持 `active / NO-GO`，不把跳过项、历史基线或静态配置结果折算为发布通过。

### 4. 剩余门禁与执行优先级

1. **P0-1：AgentRun cancel**。独立复现 503，捕获服务层底层异常，修复取消副作用，补充 HTTP 与服务层回归，并验证状态、事件、幂等和项目清理。
2. **P0-2：Provider/Worker/terminal Run**。取得真实 provider response、worker 消费和终态 Run 证据，保存请求、事件、状态转换与清理前后计数。
3. **P0-3：Artifact 资源族**。从真实 Run 生成 Artifact，接入 smoke context，覆盖 content、quality、lineage、quality-blockers、rewrite-instructions 及相关 diff 路由。
4. **P0-4：Docker Compose runtime**。Docker Server 可用后，执行 migrate、app、agent-worker、agent-command-worker 的启动、健康、日志、停止和重启矩阵。
5. **P0-5：正式 MySQL**。实例可用后执行 migration、backup、restore、rollback、re-upgrade，并记录 SHA256/sentinel/版本和失败回滚结果。
6. **P1：最终回归与裁决**。在当前 HEAD 或最新修复 HEAD 上重跑后端全量、前端三项门禁、acceptance、smoke、fixture 审计，再形成最终 GO/NO-GO。

### 5. 本轮验证记录

```text
Git branch：codex/bohrium-integration-20260831
Git HEAD：dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb
git diff --check：PASS
本轮文档之外的 tracked 文件改动：0；当前 diff 仅含本接续文档与本发布审计文档
既有未跟踪工件：138 项，未清理

Smoke fixture audit：SMOKE_FIXTURE_AUDIT_PASSED
fixture_count：21
decision_counts：candidate=20；hold-marked-fixture=1
min_age_seconds：3600

OpenAPI smoke：261 checks / 135 passed / 126 skipped / 0 failed
resource-identity：109
streaming-route：4
AgentRun：message=201；detail=200；events=200
Agent catalog generation：2
Artifact：0

Docker client：29.4.3
Docker server：连接失败，dockerDesktopLinuxEngine named pipe 不存在
com.docker.service：Stopped / Manual
MySQL TCP：127.0.0.1:3306=False；127.0.0.1:3309=False
```

### 6. 审计结论与下一次更新要求

本轮审计没有改变历史证据，只把 `dc3788e`、`c328788`、当前 smoke fixture 审计和 Docker/MySQL 探针提升为当前接续批次的权威状态。下一次更新必须至少包含：cancel 的底层异常与修复回归、Provider/terminal Run 结果、真实 Artifact 数量与资源族结果、当前 HEAD 全量测试、Docker runtime 矩阵、正式 MySQL 矩阵，以及基于全部 P0 证据的最终 GO/NO-GO 重判。在这些结果出现前，发布状态保持 `active / NO-GO`。
## 当前 task 验证增量（2026-09-05）

### 已闭合的本轮门禁

1. **AgentRun 取消服务与 ASGI 合同**
   - `test_agent_cancellation_convergence.py`：`2 passed`。
   - 新增 `test_cancel_agent_run_http_contract_returns_terminal_run`：`1 passed in 108.16s`。
   - 返回 `200`，Run 最终状态 `cancelled`，阶段 `cancelled`。
   - 历史 503 的 Catalog generation 冲突已由 `c328788` 修复；取消副作用未发现新的底层异常。

2. **Provider/Artifact 生命周期 fixture**
   - 新增 `backend/app/agent/test_agent_artifact_lifecycle_smoke.py`。
   - 最终回归：`1 passed in 75.98s`。
   - 已验证 fixture Provider、候选正文文件、Artifact 引用、SHA256、质量结果与门、content/quality/blockers/rewrite/lineage 查询、候选接受、章节版本 Artifact、accepted lineage 和 `completed/accepted` Run。
   - 该 fixture 使用隔离数据库与临时文件根目录，Artifact ID 由 service 生成，不污染现有运行数据库。

3. **组合定向与前端快速门禁**
   - Catalog/runtime/jobs/cancel 组合定向回归：`12 passed`。
   - 前端 type-check 进程退出码：`0`。
   - `git diff --check`：PASS。

### 仍未闭合的发布证据

- 独立 TCP 服务进程上的 AgentRun message/detail/events/cancel 端到端响应。
- 真实 Agent Worker/Command Worker 消费、Provider response、terminal Run 和生产服务 Artifact HTTP 资源。
- Artifact fixture 接入 `tools/smoke_api_routes.py` 后的外部 HTTP 资源身份覆盖。
- Docker Server/Compose runtime；现状与静态配置见 `docs/reports/DOCKER_MYSQL_RELEASE_GATE_AUDIT_20260905.md`。
- 正式 MySQL migration/backup/restore/rollback/re-upgrade。
- 当前 HEAD 后端全量、前端 Vitest/type-check/build-only、acceptance 的最终批次复核。

### 当前发布判定

取消服务层与 Artifact 隔离生命周期回归已通过，但运行时、容器、MySQL 及最终批次证据尚未全部齐备，当前结论保持：`active / NO-GO`。

### 后续执行顺序

1. 复测独立 TCP AgentRun cancel；
2. 闭合 Worker/Provider/terminal Run；
3. 接入生产服务 Artifact HTTP fixture；
4. 重跑当前 HEAD 全量门禁；
5. 执行 Docker/MySQL 矩阵；
6. 重新生成发布审计并重判 GO/NO-GO。

## 当前 task 权威复核（2026-09-06）

### 本轮已完成

- AgentRun cancel 服务层与 ASGI HTTP 合同：`3 passed`，HTTP 返回 `200/cancelled/cancelled`。
- Artifact provider/quality/lineage/acceptance 隔离生命周期：`1 passed`。
- Command Worker 孤儿 Run 恢复：`1 passed`，孤儿命令收敛为 `failed/OrphanedRun`，worker 保持可运行。
- 两个 CLI worker once 回归与两个独立 ASGI worker replay 回归：逐项 `4 passed`。
- `verify.ps1 -Suite acceptance`：`6/6 PASS`。
- 前端 `type-check`：PASS；`build-only`：PASS，4918 modules transformed。
- AgentWorkspace focused：30 tests passed；六个视图存在性 focused：全部通过，AdminView 使用 120 秒冷启动窗口。
- `git diff --check`：PASS。

### 全量门禁的真实分层

```text
后端全量修复前：1765 passed / 4 failures
四个失败项修复后逐项：4 passed
前端全量修复前：535 passed / 9 timeout failures
AgentWorkspace 修复后 focused：30 passed
前端视图存在性 focused：6 passed
```

这组数字不折算成“当前全量已通过”；当前修复后完整批次仍需在资源空闲窗口执行。

### 当前阻塞

- Docker Server：named pipe 不存在，`com.docker.service` 未运行；Compose runtime 无真实证据。
- MySQL：3306/3309 无监听；正式迁移恢复回滚矩阵无实例证据。
- 生产 HTTP Artifact fixture 尚未接入 OpenAPI smoke，隔离 service fixture 已通过。
- 当前修复后后端/前端完整批次仍待重跑。

### 发布判定

当前继续为 `active / NO-GO`：关键业务回归和 acceptance 已推进，但容器、正式 MySQL、生产 HTTP Artifact 资源族及修复后完整批次尚未全部闭合。

## 当前 task 最新验证结果（2026-09-06）

- `verify.ps1 -Suite acceptance`：`6/6 PASS`。
- TCP message/member/Run pagination、SQLite migration backup/restore、Agent worker once、Agent command worker once 全部通过。
- acceptance 首次复测暴露历史孤儿 `AgentRunCommand` 崩溃；`command_recovery.py` 已加入 `OrphanedRun` 终态收敛，修复回归通过，Command Worker 二次 acceptance 正常退出。
- 修复前后端全量快照：`1765 passed / 4 failures`；四个失败项逐项复测 `4 passed`。
- 关键后端组合回归 `5 passed`；Artifact lifecycle `1 passed`；Cancel service/HTTP `3 passed`。
- 前端 type-check PASS；build-only PASS，4918 modules transformed；AgentWorkspace focused `30 passed`；视图存在性 focused `6 passed`。
- `git diff --check` PASS。

### 当前剩余门禁

1. 修复后后端完整 pytest 批次；
2. 修复后前端完整 Vitest 批次；
3. 生产 HTTP Artifact 生成链接入 OpenAPI smoke；
4. Docker Server/Compose runtime；
5. 正式 MySQL migration/backup/restore/rollback/re-upgrade；
6. 全部证据完成后的最终 GO/NO-GO 重判。

发布结论继续为 `active / NO-GO`；不把逐项回归、历史全量快照或静态配置结果折算成当前全量发布通过。

## OpenAPI smoke 稳定复测（2026-09-06）

正式栈启动高峰期间首次 smoke 的 `/api/novels/import/status` 出现单次 15 秒超时；热身后重新执行已通过：

```text
OpenAPI smoke：261 checks / 135 passed / 126 skipped / 0 failed
resource-identity：109
streaming-route：4
```

当前结论：接口稳定复测通过；资源身份、流式和昂贵路由仍按真实前置条件分层，不把跳过项折算为通过。

## Deployment 脚本顺序修复（2026-09-06）

- `deploy/scripts/deploy_docker.sh` 已调整为 Compose 内迁移顺序：MySQL 健康 → migrate 容器 → app/两个 Worker。
- `RUN_MIGRATIONS` 提供显式开关。
- `deploy/scripts/rollback.sh` 已统一到 `docker compose`，并固定读取项目根目录下的 `deploy/.env`。
- Bash 语法检查：两个脚本均 PASS。
- Compose maintenance/mysql profiles 静态 config：PASS。
- `test_deployment_contract.py`：`8 passed`。

真实 Docker runtime 仍待 Docker Server 恢复，当前发布结论继续为 `active / NO-GO`。

## 独立测试门禁审查（2026-09-06，当前 task）

### 审查范围

本轮只审查测试门禁、失败分层和进程冷启动稳定性；未修改业务逻辑，保留全部未跟踪数据库、日志、上传文件、运行工件及既有工作树改动。

### 当前权威证据

- 后端收集：`1770 tests collected in 167.60s`，收集成功。
- 修复后的 worker/ASGI 定向批次：`8 passed in 838.13s`。
- 定向批次慢测：
  - `test_worker_cli_once_mode_exits_cleanly`：`110.82s`；
  - `test_command_worker_cli_once_exits_cleanly_on_empty_database`：`96.79s`；
  - `test_worker_b_replays_events_written_via_worker_a_http_to_shared_sqlite`：`269.40s`；
  - `test_independent_worker_once_completes_execution_then_visible_response_via_http`：`295.87s`。
- 历史修复前后端全量：`1765 passed / 4 failed`；四个失败均为 CLI 子进程超时或 ASGI worker 健康启动窗口超时，失败发生在进程/启动层，没有形成业务断言失败。
- 当前定向批次在本机高资源争用状态下仍为 `8/8 PASS`，因此四个修复项的行为回归证据成立；完整全量仍需单独串行执行。

### 超时判断

1. **CLI 子进程：由 120 秒提升到 180 秒。** 现有实测最大值为 `110.82s`，120 秒只剩约 9 秒余量，属于脆弱门槛。180 秒约为当前最大实测的 1.6 倍，仍保留明确的失败上限，不改变被测程序行为。
2. **AdminView 动态导入：由 120000ms 提升到 180000ms。** 既有冷启动观测约 119 秒，120 秒余量约 1 秒；180 秒用于覆盖首次 Vite transform 和 Windows 文件句柄争用。该调整只位于独立 spec 的测试等待窗口。
3. **ASGI worker 启动：保留 180 秒。** 本轮 ASGI 测试完整调用耗时 `269.40s/295.87s`，其中含双进程启动、HTTP 写入、SSE 回放和清理，不应直接等同于健康启动耗时；当前 180 秒健康检查门槛已在 `8/8` 批次中通过，暂无扩大该启动门槛的直接证据。
4. **资源争用记录：** 当前机器存在长时间运行的外部 Python 扫描进程（PID `21672`，启动于 `2026-09-05 14:52:59`），以及正在运行的应用/前端进程。它是本轮耗时解释变量，未被本轮测试修改或终止；最终全量门禁应在机器资源空闲窗口执行，并避免后端/前端全量并行。

### 本轮实际改动

仅测试稳定性改动：

```text
backend/app/agent/test_worker_cli.py
  subprocess.run(timeout=120) -> timeout=180

backend/app/agent/test_command_worker_cli.py
  subprocess.run(timeout=120) -> timeout=180

frontend/src/views/AdminView.spec.ts
  test timeout 120000ms -> 180000ms
```

既有 `app.models` 显式注册、Command Worker 孤儿命令回归、ASGI 启动窗口和 AgentWorkspace Promise 归一化改动保持不变；本轮没有触碰生产业务实现。

### 最小最终批次

机器资源不足时先执行以下快速层，形成可重放证据：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m py_compile `
  app/agent/test_worker_cli.py `
  app/agent/test_command_worker_cli.py `
  app/agent/test_asgi_worker_event_replay.py
cd ..
git diff --check
```

资源空闲后按串行顺序执行，不并发：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q `
  app/agent/test_worker_cli.py `
  app/agent/test_command_worker_cli.py `
  app/agent/test_asgi_worker_event_replay.py `
  --durations=20 --tb=short

cd ..\frontend
npm run test:run -- src/views/AdminView.spec.ts src/views/AgentWorkspace.spec.ts
npm run type-check
npm run build-only
```

最后才执行两项完整门禁：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q --durations=20

cd ..\frontend
npm run test:run
```

判定规则：定向层、后端全量、前端全量必须全部在当前修改后的工作树通过；若失败，按 `import/transform`、子进程启动、应用断言、资源争用四类分别记录，单次超时不直接判定为业务回归，也不以扩大阈值替代失败定位。

### 当前结论

```text
测试稳定性审查：PASS（当前定向 8/8）
后端全量最终门禁：待当前工作树重跑
前端全量最终门禁：待当前工作树重跑
发布判定：active / NO-GO
```
