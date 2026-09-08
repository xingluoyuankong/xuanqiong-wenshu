# Docker / MySQL 发布门禁独立审查报告

- 审查日期：2026-09-05
- 工作区：`D:\小说写作\xuanqiong-wenshu`
- 当前 HEAD：`dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb`
- 审查范围：Docker Compose、Docker 启动/迁移/回滚脚本、Windows 本地 MySQL 启动脚本、当前 Docker/MySQL 服务可用性
- 操作原则：只读和可逆探测；本轮未执行容器启动/停止、`down`、迁移、数据库初始化、备份恢复、卷删除、数据清理或业务代码修改
- 结论：**NO-GO（静态配置通过，运行时门禁未通过）**

## 1. 工作区保护与变更边界

审查开始时工作区已有未提交改动和大量运行/上传产物。本轮未修改业务代码、数据库、`.mysql/data`、`backend/storage`、上传文件或既有任务/发布文档；仅新增本独立报告文件。

复测时应先保存当前工作区状态，避免把既有产物误判为本轮生成：

```powershell
git status --short --branch
git rev-parse HEAD
```

## 2. 静态 Compose 门禁

### 2.1 配置解析

命令：

```powershell
docker compose --env-file deploy/.env.example `
  -f deploy/docker-compose.yml config --quiet
```

结果：

```text
exit=0
```

Compose 文件 SHA-256：

```text
69FDE2E574D13E7FF20EB1B2CD1611284BAA2E199105AB3DFC716DCC417D4CDB
```

说明：该检查只证明 YAML、变量插值和 Compose 结构可解析；`.env.example` 中仍是示例/占位配置，不代表可直接发布。

### 2.2 Profile 服务矩阵

默认 profile：

```text
agent-command-worker
agent-worker
app
```

命令：

```powershell
docker compose --env-file deploy/.env.example `
  -f deploy/docker-compose.yml config --services
```

MySQL profile：

```text
db
agent-command-worker
agent-worker
app
```

命令：

```powershell
docker compose --env-file deploy/.env.example `
  -f deploy/docker-compose.yml --profile mysql config --services
```

Maintenance profile：

```text
agent-command-worker
agent-worker
app
migrate
```

命令：

```powershell
docker compose --env-file deploy/.env.example `
  -f deploy/docker-compose.yml --profile maintenance config --services
```

结论：

1. `db` 只在 `mysql` profile 中启用。
2. `migrate` 只在 `maintenance` profile 中启用。
3. MySQL 迁移容器路径需要同时显式启用两个 profile：`--profile mysql --profile maintenance`。
4. `docker compose up -d` 默认不会启动内置 MySQL，也不会启动迁移服务。
5. `agent-worker` 和 `agent-command-worker` 对 `db` 使用 `required: false`；当目标配置为 MySQL 时，发布流程必须先验证 `db` 健康，再判定应用可用。

## 3. Docker 运行时门禁

### 3.1 客户端版本

```text
Docker version 29.4.3, build 055a478
Docker Compose version v5.1.3
Context: desktop-linux
```

### 3.2 Server / Engine 探测

`docker version` 和 `docker info` 的共同错误：

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

Windows 服务状态：

```text
Name:      com.docker.service
Status:    Stopped
StartType: Manual
```

Docker named pipe 探测：未发现 `dockerDesktopLinuxEngine` 相关管道。

Compose 状态探测：

```powershell
docker compose --env-file deploy/.env.example `
  -f deploy/docker-compose.yml ps
```

结果：

```text
exit=1
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

MySQL profile 状态探测同样失败，原始错误一致：

```powershell
docker compose --env-file deploy/.env.example `
  -f deploy/docker-compose.yml --profile mysql ps
```

结论：Docker CLI/Compose 客户端已安装，Docker Server 当前不可连接；因此本机没有形成 app、worker、command-worker、db、migrate 的容器级健康证据。

## 4. MySQL 运行时门禁

### 4.1 TCP 只读探测

使用 1 秒连接超时的 TCP 探针，未发送 SQL、未写入数据：

```text
127.0.0.1:3306=False
127.0.0.1:3309=False
127.0.0.1:80=False
127.0.0.1:8088=False
```

### 4.2 进程/服务探测

未发现正在运行的 `mysqld` / `mariadbd` 进程；未发现运行中的 MySQL/MariaDB Windows 服务。

### 4.3 本地数据目录保护性观察

项目下 `.mysql/data` 存在历史 MySQL 数据文件和库目录，包括 `mysql`、`performance_schema`、`sys`、`xuanqiong_wenshu` 以及 InnoDB/binlog 文件。本轮仅列目录和时间戳，未打开数据库、未启动实例、未初始化、未修复、未删除、未移动。

`.mysql/logs/stderr.log` 最后一段历史日志记录了 **2026-05-20** 的一次 MySQL 8.4.7 启动成功，包含 `ready for connections` 和端口 `3309`；这属于历史证据，不等于 2026-09-05 当前实例可用。

### 4.4 Windows 本地 MySQL 启动脚本路径

`tools/start_local_mysql.ps1` 的默认路径：

```text
mysqld.exe:    D:/download/MySQL/bin/mysqld.exe
mysqladmin.exe: D:/download/MySQL/bin/mysqladmin.exe
```

当前探测结果：

```text
D:/download/MySQL/bin/mysqld.exe=False
D:/download/MySQL/bin/mysqladmin.exe=False
X:/\.mysql/my.ini=True
X:/\.mysql/client.cnf=True
```

脚本的默认数据目录为 `X:\.mysql\data`、默认端口为 `3309`，并允许使用 `XUANQIONG_WENSHU_MYSQLD_PATH` 和 `XUANQIONG_WENSHU_MYSQLADMIN_PATH` 覆盖可执行文件路径。脚本 PowerShell 语法解析通过，但默认二进制路径失效，故当前本地 MySQL 启动门禁仍为 NO-GO。

当前 `backend/.env` 配置为 `DB_PROVIDER=sqlite`、`MYSQL_PORT=3309`；因此普通本地启动路径会优先走 SQLite，不能据此证明 MySQL 路径已经验收。

## 5. 启动、迁移、回滚脚本审查

### 5.1 `deploy/scripts/deploy_docker.sh`

已确认行为：

- 从 `deploy/.env` 加载变量。
- 要求 `SECRET_KEY`、`ADMIN_DEFAULT_PASSWORD`、`OPENAI_API_KEY` 非空；示例占位值会通过“非空”检查，缺少强度/占位符拒绝校验。
- `DB_PROVIDER=mysql` 时仅设置 `--profile mysql`，没有自动加入 `maintenance` profile。
- MySQL 分支在容器启动前询问是否执行 `bash deploy/scripts/run_migrations.sh`。
- 后续执行 `docker compose ... down`、无缓存构建、`up -d`、等待 10 秒、检查容器状态和应用健康。

关键发布缺口：

1. **迁移时序缺口**：内置 `db` 容器尚未被 `up`，脚本就从宿主机执行 `run_migrations.sh`。当 `.env` 使用 `MYSQL_HOST=db` 时，宿主机通常不能解析 Compose 内部服务名 `db`；即使改成 `localhost:3306`，内置数据库容器也尚未监听。该路径没有先启动并等待 `db` 健康。
2. **破坏性默认动作**：发布脚本默认在构建前执行 `docker compose down`。本轮没有执行此命令。正式发布前应把停止旧栈、备份证明和回滚点作为显式门槛，而不是在探测阶段触发。
3. **健康检查等待固定为 10 秒后再轮询**，没有把 `db` 健康状态作为应用启动的独立门禁证据。
4. `exec app curl http://127.0.0.1:8000/api/health` 依赖容器内部后端端口和 supervisor 进程布局；应同时保存 `docker compose ps`、`docker compose logs --tail` 和容器 health 状态，避免单一 HTTP 检查掩盖 worker/db 未就绪。

### 5.2 `deploy/scripts/run_migrations.sh`

已确认行为：

- 默认 `MYSQL_HOST=localhost`、`MYSQL_PORT=3306`。
- 要求 `MYSQL_PASSWORD`、`mysql`、`mysqldump`。
- 先执行 `SELECT 1` 连通性检查。
- 非 dry-run 路径先做 `mysqldump --single-transaction --routines --events`，并拒绝空备份，再执行 legacy SQL/Alembic。
- 备份文件默认写入 `$REPO_ROOT/backups`。

结论：脚本的“先备份后迁移”顺序是可保留的，但它是宿主机 MySQL 客户端脚本，不是 Compose 内部迁移容器命令；对内置 `db` 服务不能在 `db` 健康前直接调用。

### 5.3 `deploy/scripts/rollback.sh`

已确认行为：

- 回滚前先创建安全备份。
- 使用 `docker-compose` 老命令名，而当前部署入口和环境验证使用 `docker compose`。
- 恢复流程中包含 `docker-compose down`，随后执行 SQL 恢复并重新启动服务。
- 本轮未执行任何回滚动作。

结论：回滚脚本需单独复测命令兼容性、Compose 文件定位、项目名/卷绑定、备份文件路径和恢复后健康状态；在这些项目未被实测前，不纳入 GO 证据。

### 5.4 `start.ps1` / `tools/start_local_mysql.ps1`

- `start.ps1` 若未从环境变量或 `backend/.env` 读到 `DB_PROVIDER`，默认值为 `mysql`。
- 当前仓库 `backend/.env` 明确为 `sqlite`，所以本次常规本地启动会跳过本地 MySQL。
- `tools/start_local_mysql.ps1` 会在数据目录缺少系统库时执行初始化；本轮没有调用该脚本，以保护现有 `.mysql/data`。
- 默认 MySQL 二进制路径不存在，是当前 Windows 本地 MySQL 门禁的直接阻断点。

## 6. 门禁判定

| 门禁项 | 状态 | 证据 |
|---|---|---|
| Compose YAML/变量静态展开 | PASS | `config --quiet` exit 0 |
| 默认服务矩阵可解析 | PASS | app + 两个 worker |
| MySQL profile 可解析 | PASS | `--profile mysql config --quiet` exit 0，含 db |
| Maintenance profile 可解析 | PASS | 含 migrate |
| Docker CLI/Compose 客户端 | PASS | Docker 29.4.3 / Compose 5.1.3 |
| Docker Server/Engine | **BLOCKED** | desktop-linux named pipe 不存在；服务 Stopped |
| Compose 容器状态/健康 | **BLOCKED** | `compose ps` exit 1 |
| 本地 MySQL 3306/3309 | **BLOCKED** | TCP 探测均为 False |
| 本地 MySQL 进程/服务 | **BLOCKED** | 未发现 mysqld/mariadbd 或服务 |
| MySQL 数据目录存在性 | OBSERVED | `.mysql/data` 存在历史库文件；未修改 |
| Windows MySQL 启动脚本语法 | PASS | PowerShell parser 0 errors |
| Windows MySQL 默认二进制路径 | **FAIL** | 两个默认路径均不存在 |
| Docker MySQL 真实迁移/恢复 | **NOT RUN** | Docker Server 不可用；未触碰数据 |
| 发布综合结论 | **NO-GO** | 运行时证据链未闭合 |

## 7. 服务恢复后的无破坏性复测顺序

以下命令只用于建立运行时证据；执行前应确认使用正确的 `deploy/.env`，并保留现有数据卷。不要用 `down -v`，不要删除 `mysql-data` 或 SQLite 存储卷。

### 7.1 Docker Server 复测

```powershell
docker info
docker compose version
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml config --quiet
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml ps
```

### 7.2 内置 MySQL 栈复测

先以真实值配置 `DB_PROVIDER=mysql`、`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`，然后按健康状态推进：

```powershell
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql up -d db
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql ps db
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql logs --tail=100 db
```

数据库健康后，再运行 Compose 内的迁移服务，避免宿主机解析 `db`：

```powershell
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql --profile maintenance `
  run --rm migrate
```

迁移成功后启动应用和两个 worker：

```powershell
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql up -d app agent-worker agent-command-worker
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql ps
docker compose --env-file deploy/.env `
  -f deploy/docker-compose.yml --profile mysql exec -T app `
  curl -f http://127.0.0.1:8000/api/health
```

复测证据应至少包含：容器 ID、镜像 ID、`db` health=healthy、migration exit 0、app/worker/command-worker 状态、应用健康响应、最近 100 行日志和停止前后的数据卷名称。停止验证时只使用不带 `-v` 的显式命令，并保存日志。

### 7.3 Windows 本地 MySQL 复测

先只检查可执行文件路径，不触碰数据目录：

```powershell
Test-Path $env:XUANQIONG_WENSHU_MYSQLD_PATH
Test-Path $env:XUANQIONG_WENSHU_MYSQLADMIN_PATH
Test-NetConnection 127.0.0.1 -Port 3309
```

确认二进制来自实际安装位置后，再通过环境变量覆盖脚本默认路径；不要在现有 `.mysql/data` 上执行初始化参数。启动成功后保存 `mysqladmin ping`、PID、端口、日志尾部和 `SELECT VERSION()` 输出，再运行项目迁移/验收。

## 8. 文档与后续修复建议

本轮只记录建议，不修改部署代码：

1. 将 Docker MySQL 迁移改成“先启动 `db` 并等待 health，再在 Compose 网络内执行 migrate”，或明确区分外部 MySQL 与内置 MySQL 两条路径。
2. 发布脚本将 `--profile mysql` 与 `--profile maintenance` 的关系写成明确命令；不要让宿主机 `run_migrations.sh` 隐式承担容器内迁移职责。
3. 把 `docker compose down` 从默认发布步骤改为显式、可确认的动作，并在动作前输出数据卷/容器清单和备份校验值。
4. 统一所有脚本使用 `docker compose`，显式传入 `--env-file deploy/.env -f deploy/docker-compose.yml`，固定 Compose project name，避免旧 `docker-compose` 命令和当前上下文不一致。
5. 对 `SECRET_KEY`、管理员密码、MySQL 密码和 API key 增加占位符拒绝、最小长度和生产环境校验；`.env.example` 只能用于静态 config 检查，不能直接作为发布配置。
6. Windows 本地 MySQL 脚本的默认路径应改为可配置且在启动前给出明确 preflight 结果；路径失效时直接停止，不进入初始化分支。
7. 正式 GO 判定前补齐 Docker runtime、MySQL health、migration、app、两个 worker、停止/重启后数据保留和回滚演练证据。

## 9. 可复现证据摘要

```text
HEAD=dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb
Docker=29.4.3
Compose=5.1.3
Compose config=PASS
Default services=app, agent-worker, agent-command-worker
MySQL profile config=PASS; services include db
Maintenance profile config=PASS; services include migrate
Docker server=UNAVAILABLE; desktop-linux named pipe missing
com.docker.service=Stopped / Manual
TCP 3306=False
TCP 3309=False
mysqld process/service=not found
local MySQL default mysqld path=False
local MySQL default mysqladmin path=False
Existing .mysql/data=present; untouched
Existing .mysql/logs/stderr.log=historical ready log from 2026-05-20; not current proof
Release gate=NO-GO
```
