# MySQL / 跨实例续跑恢复审查摘要

- 审查日期：2026-09-07（Asia/Shanghai）
- 工作区：`D:\小说写作\xuanqiong-wenshu`
- 范围：真实 MySQL / 跨实例 continuation 恢复审查；只读静态检查与隔离探针。
- 变更边界：未修改 `backend` 核心源码、数据库、上传文件、Docker 卷或现有运行数据；未启动/停止 Docker、未执行迁移、未向项目数据库发送 SQL。
- 当前判定：**MySQL / 跨实例运行门禁仍为 NO-GO；SQLite/静态部分证据保留为局部通过。**

## 1. 当前环境实测

| 检查 | 结果 | 证据 |
|---|---|---|
| Docker Client | `29.4.3` | 本轮只读 `docker version` |
| Docker Compose | `v5.1.3` | 本轮只读 `docker compose version` |
| Docker Server | 不可连接，`Server=null`；`dockerDesktopLinuxEngine` named pipe 不存在 | `logs/docker-runtime-readonly-stage6-20260907.json`、`logs/stage8-docker-readonly-probe.json` |
| Docker 容器状态 | 无法查询，原因同上 | 本轮只读 `docker ps -a` |
| `127.0.0.1:3306` | TCP 不可达 | 本轮只读 TCP 探针 |
| 项目已有 MySQL 数据目录 | 仅保持原状，未打开/启动/修复/清理 | `docs/reports/DOCKER_MYSQL_RELEASE_GATE_AUDIT_20260905.md` |

隔离探针脚本在 Windows 临时 SQLite CAS 文件清理阶段遇到文件句柄占用，已停止重试；该失败不涉及项目数据。原始记录：

- `logs/mysql_cross_instance_audit_20260907.py`
- `logs/mysql-cross-instance-audit-20260907.failure.txt`

该脚本的聚合 JSON 没有生成，因此不把未落盘的中间内存结果包装成“通过”。

## 2. 已验证的静态 / 隔离事实

### 2.1 Compose 与部署接线

已有静态 Compose 审查确认：

- `db` 仅在 `mysql` profile 中启用。
- `migrate` 仅在 `maintenance` profile 中启用。
- MySQL 迁移路径需要同时使用 `--profile mysql --profile maintenance`。
- 默认 `DB_PROVIDER` 是 `sqlite`；默认 `docker compose up -d` 不等于 MySQL 运行。
- `agent-worker`、`agent-command-worker` 对 `db` 使用 `required: false`，因此外部 MySQL 或 profile 组合必须由发布脚本先做连通性检查。
- `deploy/scripts/deploy_docker.sh` 对 MySQL 执行 `SELECT 1` 前置探测，并要求 `MYSQL_PASSWORD`；该逻辑在部署契约测试中有模拟覆盖，但没有真实 MySQL 执行证据。
- 内置 MySQL 服务设置了 `TZ: Asia/Shanghai` 和 `--max_connections=1000`，但 Compose 没有设置 `--default-time-zone=+00:00`。

静态来源：

- `deploy/docker-compose.yml`
- `deploy/.env.example`
- `deploy/scripts/deploy_docker.sh`
- `docs/reports/DOCKER_MYSQL_RELEASE_GATE_AUDIT_20260905.md`

### 2.2 驱动、连接池和 Alembic

代码静态事实：

- MySQL URI 形态为 `mysql+asyncmy://...`。
- `backend/requirements.txt` 固定 `asyncmy==0.2.9`。
- MySQL 引擎启用了 `pool_pre_ping`、连接池大小、overflow、timeout、recycle 和 LIFO 配置。
- Alembic 在线迁移从 `settings.sqlalchemy_database_uri` 取运行时连接串，而不是使用 `alembic.ini` 的 SQLite 回退 URL。
- 当前没有发现 MySQL 专用 `isolation_level` 设置，也没有发现连接建立时强制 `SET time_zone='+00:00'`。

这证明了“有 MySQL 接线”，没有证明“当前 MySQL 实例已经按预期运行”。

### 2.3 Continuation CAS / 锁的源代码约束

静态检查确认：

- `AgentJobService.claim_job` 使用条件 `UPDATE`，并检查 `rowcount == 1`；条件包含 Job 状态、lease 过期、`lease_generation`、owner、Run 可运行状态和取消标记。
- `claim_next_job` 允许多个 worker 看到同一候选，但最终以条件更新作为唯一 claim fence。
- `continuation.py` 使用 Run 的 no-op `UPDATE` 获取 SQLite 写锁，并把 `state_version` 作为写入边界；注释明确说明 SQLite 不执行 `FOR UPDATE` 的实际行锁语义。
- `continuation_failure_recovery.py` 使用 `with_for_update()` 读取恢复证明涉及的 Run、Job、Step，并在最终更新后检查 `rowcount`；同时校验 lease、generation、状态和失败事实摘要。
- `agent_runtime.py` 的命令/Run 读取路径存在 `with_for_update()`。
- 关键续跑、失败恢复和 source ACK 代码含 generation/lease CAS 约束。

可以确认：**SQLAlchemy 表达式和源代码意图具备跨实例 CAS/行锁的实现基础。**

尚未确认：

- 两个独立 MySQL 连接同时 claim 时是否严格只产生一个 winner。
- MySQL InnoDB 的 `FOR UPDATE` 等待、提交后可见性和锁释放时序。
- 两个进程在不同连接池、不同主机/容器上运行时的事务行为。

### 2.4 时间字段风险边界

当前实现同时存在三类时间来源：

1. 应用层 `datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)`，即写入去时区的 UTC 墙上时间。
2. ORM 模型大量使用 `DateTime(timezone=True)`；MySQL 通常将其落为不保存时区的 `DATETIME` 语义。
3. 迁移和模型中大量 `server_default=func.now()` / `onupdate=func.now()`，其值取决于 MySQL session/system 时区。

因此：

- SQLite 测试中对 naive/aware 时间的兼容修复不能直接证明 MySQL server default 与应用 UTC 时间比较一致。
- 内置服务的 `TZ: Asia/Shanghai` 不能替代 MySQL `default-time-zone` 或连接级时区设置。
- 当前没有真实 MySQL 的 `@@session.time_zone`、`@@system_time_zone`、`NOW(6)` 与应用写入值对照证据。
- `microsecond=0` 还会把 lease/expiry 的精度降到秒；MySQL 运行时需要实测边界时间恰好相等时的 `<=` 语义。

这属于本批最重要的未闭环项。

## 3. 覆盖矩阵

| 维度 | 当前证据 | 结论 |
|---|---|---|
| Compose YAML / 变量插值 | 2026-09-05 静态 `docker compose config` 通过 | 已验证静态结构 |
| MySQL / maintenance profile 组合 | 已验证服务矩阵与 profile 关系 | 已验证静态接线 |
| MySQL driver / URI | `asyncmy` 依赖、`mysql+asyncmy` URL、Alembic runtime URI | 已验证源码接线 |
| 连接池健康 | `pool_pre_ping` 与 MySQL pool 参数 | 已验证配置存在 |
| MySQL 真实 TCP | 3306 不可达 | 未验证 |
| MySQL 真实登录 / `SELECT 1` | 没有实例可执行 | 未验证 |
| Alembic `upgrade head` on MySQL | 只有 SQLite 新库/并发迁移测试与模拟部署测试 | 未验证 |
| Schema/index/FK 在 MySQL | 没有 `SHOW CREATE TABLE` / information_schema 证据 | 未验证 |
| 单实例 CAS | SQLite/源码级条件更新证据 | 部分验证，非 MySQL 证明 |
| 双独立连接 claim winner | 没有真实 MySQL 双进程测试 | 未验证 |
| 过期 lease + generation reclaim | SQLite 定向续跑测试、源码 CAS | 部分验证 |
| stale worker late write | SQLite/独立 CLI 过程证据 | 部分验证 |
| `FOR UPDATE` 行锁等待 | SQL 表达式/源码存在；无 MySQL 时序测试 | 未验证运行语义 |
| 事务隔离级别 | 未配置显式级别，未查询实例值 | 未验证；存在部署差异风险 |
| server/app 时间一致性 | 源码可见 UTC-naive + server `NOW()` 双来源 | 未验证；当前为风险项 |
| 失败投影与 Job 状态原子性 | SQLite 定向/进程级证据 | 部分验证 |
| 跨实例 recovery CAS | 源码约束存在，实际实例缺失 | 未验证 |
| TCP/HTTP smoke | 现有 smoke 主要是本机 HTTP + SQLite 临时库 | 不能替代 MySQL/TCP DB 证据 |
| Docker 容器健康、重启、卷持久化 | Docker Server 不可用 | 未验证 |

## 4. 最短实现路径

以下是下一次具备 MySQL 实例后的最短闭环，不需要扩大业务改动面：

1. 准备全新的、与 `.mysql/data` 和现有 Docker volume 无关的 MySQL 8.0 临时实例；只注入测试数据库和测试账号。
2. 用 `DB_PROVIDER=mysql` 和该实例连接串执行 `alembic upgrade head`，立即采集：
   - `SELECT VERSION(), @@transaction_isolation, @@session.transaction_isolation, @@session.time_zone, @@system_time_zone;`
   - `SHOW CREATE TABLE agent_jobs;`
   - `SHOW CREATE TABLE agent_runs;`
   - `SHOW CREATE TABLE agent_run_steps;`
   - `SHOW CREATE TABLE agent_capability_executions;`
3. 增加一个非业务测试/脚本，启动两个独立 Python 进程、两个独立 SQLAlchemy 连接，对同一 queued Job 做 claim：预期一个 `rowcount=1`、另一个 `rowcount=0`，最终 generation 只增加一次。
4. 增加锁等待场景：连接 A `SELECT ... FOR UPDATE` 后暂停；连接 B 对同一 Run/Job 执行 recovery/claim；记录等待、A 提交后 B 的可见结果和 B 的 `rowcount`。
5. 增加 stale-worker 场景：A lease 过期，B 以新 generation 接管，A 迟到完成/失败必须 `rowcount=0`，且不能覆盖 B 的 owner、generation、terminal state。
6. 增加 failure-recovery 场景：两个独立 worker 同时尝试收敛同一个 orphan continuation，预期只有一个恢复提交；另一个读取到精确 proof 但 CAS 失败，不得重复工具调用。
7. 固定时间策略并实测：应用写入 UTC 值、server default 值、lease expiry 边界值分别读取；在实例配置或连接事件中统一为 UTC 后再复跑全部时间断言。当前代码还没有本批实现这一配置，因此这里是“最短修复路径”，不是已完成事项。
8. 将上述测试接入 CI 的 MySQL service，至少覆盖 MySQL 8.0；SQLite 回归继续保留，不能用 SQLite 绿灯替换 MySQL 门禁。

## 5. 本批结论

- **通过**：Compose/profile 静态结构、MySQL 驱动/URI/连接池接线、Alembic 使用 runtime URI、续跑 CAS/generation/rowcount/部分 `FOR UPDATE` 源代码约束、既有 SQLite 与独立 CLI 的局部恢复证据。
- **未通过或缺失**：Docker Server、MySQL TCP/登录、真实 MySQL migration、真实 InnoDB 行锁、真实事务隔离、时间字段一致性、双进程跨实例恢复、容器重启和卷持久化。
- **整体发布判定**：继续保持 `active / NO-GO`；这不是 continuation 核心源码失败，而是本批所要求的真实 MySQL/跨实例运行证据尚未具备。

## 6. 文件清单

本批新增：

- `logs/mysql_cross_instance_audit_20260907.py`：只读静态/隔离探针脚本；本轮在临时 SQLite 文件清理阶段失败，未写入聚合 JSON。
- `logs/mysql-cross-instance-audit-20260907.failure.txt`：失败原因与环境证据。
- `docs/reports/MYSQL_CROSS_INSTANCE_RECOVERY_AUDIT_20260907.md`：本报告。

已有相关证据：

- `docs/reports/DOCKER_MYSQL_RELEASE_GATE_AUDIT_20260905.md`
- `logs/docker-runtime-readonly-stage6-20260907.json`
- `logs/stage8-docker-readonly-probe.json`
- `backend/app/services/test_deployment_contract.py`
- `backend/app/services/test_alembic_migrations.py`
- `backend/app/agent/test_continuation_boundaries.py`
- `backend/app/agent/test_continuation_failure_atomicity.py`
- `backend/app/agent/test_continuation_failure_recovery.py`
- `backend/app/agent/test_continuation_worker.py`

本报告不把探针中未落盘的内存中间值作为证据，不把 SQLite/模拟部署结果表述为真实 MySQL 通过。
