# MySQL 隔离运行门禁与跨实例 CAS 验收

- 日期：2026-09-07（Asia/Shanghai）
- 状态：**READY_FOR_MAINLINE_MIGRATION**
- 范围：本机已存在的 MySQL Community Server 8.4.9；全新隔离 datadir；仅回环地址；真实 TCP / InnoDB / 独立客户端与 asyncmy 探针。
- 源码边界：未修改 `backend`、`deploy` 核心源码；未启动系统服务；未启动 Docker Desktop；未接触项目既有 MySQL 数据目录、Docker 卷或数据库。

## 1. 运行实例

| 项目 | 值 |
|---|---|
| `mysqld` | `C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe` |
| 版本 | `8.4.9` |
| 当前 PID | `27272` |
| 监听 | `127.0.0.1:40344` |
| datadir | `D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\datadir` |
| 运行根目录 | `D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa` |
| 证据目录 | `D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\evidence` |
| 私有凭据文件 | `D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\private\credentials.json` |
| 密码输出 | `false` |
| 系统服务 | 未安装、未启动 |
| Docker | 未启动 |

凭据文件已设置为当前用户和 SYSTEM 可读；报告、终端和公开 JSON 均没有密码内容。主线读取该文件时保持私密，不要把内容写入聊天或普通日志。

## 2. 真实门禁结果

### 2.1 asyncmy 应用驱动路径

`asyncmy` 默认非 TLS TCP 连接建立了 3 个独立连接，均返回：

```text
SELECT 1 = 1
VERSION() = 8.4.9
@@session.time_zone = +00:00
@@session.transaction_isolation = REPEATABLE-READ
@@default_storage_engine = InnoDB
```

证据：`D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\evidence\asyncmy-default-probe.json`

强制 TLS 的早期探针曾在 Windows asyncmy 握手阶段失败；该失败单独保留，不代表应用默认连接路径失败。

### 2.2 InnoDB 行锁等待

- 连接 A 持有 `SELECT ... FOR UPDATE`。
- 连接 B 对同一行执行 UPDATE。
- 第三连接在 `performance_schema.data_lock_waits` 观察到真实等待。
- 提交 A 后，B 完成更新，`ROW_COUNT()=1`，最终 marker 为 `1`。

证据：

- `D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\evidence\native-client-probes-final.json`
- `D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\evidence\barrier-cas-evidence.json`

### 2.3 双连接 CAS winner / loser

对同一 InnoDB 行执行带状态、owner、generation 条件的 UPDATE：

| 隔离级别 | 独立连接结果 | 最终状态 | stale generation |
|---|---|---|---|
| `REPEATABLE READ` | `1 / 0` | `running / generation=1 / owner=a` | `ROW_COUNT()=0` |
| `READ COMMITTED` | `1 / 0` | `running / generation=1 / owner=a` | `ROW_COUNT()=0` |

屏障型测试额外确认：两个 contender 在锁释放前都曾出现在 `data_lock_waits` 中，随后只有一个赢家。

证据：`D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\evidence\barrier-cas-evidence.json`

## 3. 主线复用

主线可以使用以下交接清单执行真实 Alembic 迁移：

```text
D:\小说写作\xuanqiong-wenshu\logs\mysql-isolated-runtime-handoff-20260907.json
```

该 JSON 只包含 PID、端口、目录、证据路径和私有凭据文件位置，不包含密码。

建议迁移进程读取私有凭据文件并在自身环境中设置 `DB_PROVIDER=mysql` / `DATABASE_URL`，执行迁移后立即保存 `alembic current`、表结构、索引、外键和迁移日志。不要让迁移进程接管或停止 PID `27272`。

## 4. 受控进程边界

本轮控制器只接受交接清单中的 PID、可执行文件、datadir 和端口同时匹配时的 status/stop 操作。当前可控存活进程只有：

```text
PID 27272 -> C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe -> D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\datadir -> 127.0.0.1:40344
```

所有 probe 客户端已退出；没有注册服务或 Docker 容器。控制脚本：

```text
logs/mysql_isolated_control.py
```

## 5. 源码漂移记录

探针前后发现并行工作区变化：

```text
["backend\\app\\agent\\continuation.py", "backend\\app\\agent\\continuation_failure_recovery.py", "backend\\app\\agent\\test_continuation_scan_fairness.py"]
```

本轮未回滚、覆盖或修复这些文件；这不影响 MySQL 隔离实例和本批证据，但不能把本轮工作区整体描述为源码零漂移。

## 6. 文件清单

- `logs/mysql-isolated-runtime-handoff-20260907.json`
- `logs/mysql-isolated-active.json`
- `logs/mysql-live-20260907T092945-a3cfb7aa/evidence/native-client-probes-final.json`
- `logs/mysql-live-20260907T092945-a3cfb7aa/evidence/asyncmy-default-probe.json`
- `logs/mysql-live-20260907T092945-a3cfb7aa/evidence/barrier-cas-evidence.json`
- `logs/mysql-live-20260907T092945-a3cfb7aa/evidence/runtime.json`
- `logs/mysql_isolated_live_probe.py`
- `logs/mysql_native_client_probes_final.py`
- `logs/mysql_barrier_cas_probe.py`
- `logs/mysql_isolated_control.py`

结论：**真实本机 MySQL 连接、UTC 会话、InnoDB 隔离级别、行锁等待、双连接 CAS winner/loser 和 stale-generation 保护均已形成落盘证据；实例保持运行，等待主线执行真实迁移。**

## 7. 必须保留的异常与验收范围

- 首次 Windows monitor 子进程重传参数时，datadir 被截为 `D:\`。现场发现 `D:\auto.cnf`（56 字节）和 `D:\binlog.index`（空文件）；这超出预期 logs 写入范围，已记录 SHA-256 并保留，未自动删除或移动。前次进程已退出，现实例启用 `--no-monitor`，通过命令行和 SQL 返回的 datadir 双重核对。详见同目录 `first-attempt-path-side-effects.json`。
- 当前运行命令仍含一次性 `--init-file` 路径，该文件在设置随机密码、确认登录成功后已删除。不要直接原样重放该启动命令；后续重启须移除 init-file 参数，且不重复初始化。当前主线应直接复用正在运行的实例。
- asyncmy 已通过的是探针内 Selector 事件循环、默认非 TLS 路径；不是默认 Proactor+TLS 通过证明，也不是 Alembic 或应用 continuation 通过证明。
- CAS 使用新建的 InnoDB 探针表，不是应用的 AgentJob 表。证据证明数据库原语与跨连接竞争行为；业务 SQL、迁移、应用恢复仍待主线执行。
- 不同进程和不同连接连接到同一个本机 MySQL 实例；未声称验证多 MySQL 节点、跨主机时钟偏移、集群故障切换。
- `logs/mysql_isolated_control.py` 是本批交付的 status/stop 控制入口；此前失败的启动草稿仅作为历史诊断保留，不建议执行。

## 8. 最终应用驱动探针

在未切换事件循环的 Windows 默认 `WindowsProactorEventLoopPolicy` 下，`asyncmy` 通过同一隔离实例建立 TCP 连接并返回：

```text
SELECT 1 = 1
VERSION() = 8.4.9
@@session.time_zone = +00:00
@@session.transaction_isolation = REPEATABLE-READ
@@default_storage_engine = InnoDB
```

证据：`D:\小说写作\xuanqiong-wenshu\logs\mysql-live-20260907T092945-a3cfb7aa\evidence\asyncmy-default-event-loop-probe.json`。本项通过后，主线不需要为数据库迁移额外切换 Windows 事件循环。
