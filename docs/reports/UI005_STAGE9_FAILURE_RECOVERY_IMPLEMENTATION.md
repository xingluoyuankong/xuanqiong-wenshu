# UI005 阶段九：失败原子提交与历史孤儿恢复

## 结论与门禁

阶段八冻结全量 **2572 passed / 1173.67s**，615个代码/配置及2725个既有数据文件前后一致。阶段九修改后，**100项恢复/原子性组合通过**，真实CLI强退出前后与旧故障库副本恢复已通过；阶段九原始后端全量 **2672 passed / 1198.96s / exit0**；618输入、2728既有数据文件前后一致，发布仍为 **NO-GO**，总目标 **active**。

本报告中的证据路径保留既有批次标签；其中部分文件名带 `20260907`，仅作历史批次标识，不据此把运行日期写成 2026-09-07。精确运行时刻以对应 JSON 的 `recorded_at` / `finished_at` 和时区偏移为准。

## Evidence → Finding → Path

| 证据 | 发现 | 修复/后续路径 |
|---|---|---|
| `logs/continuation-failure-window-20260907-061036-a93930e8/result.json`：20项断言确认旧缺陷 | 失败投影提交后、Job.fail之前进程退出，Run failed而Job running；恢复CLI worked=False | 失败投影与Job失败同事务；对历史已落盘孤儿另做严格恢复 |
| `logs/stage9-failure-atomicity-red.log`：4失败→修复后4通过 | 别的连接可在Job状态提交前看见终态投影 | 新 `jobs.fail(commit=False)`；consumer统一commit，异常/取消先rollback；worker只认耐久失败ACK |
| `logs/stage9-sqlite-raw-lease-green.log`：100通过 | 历史孤儿恢复需要冻结计划、失败read事实、归属和租约证据，不应只按Run终态猜测 | 新 `continuation_failure_recovery.py`，启动接线，缺证据不改动；RuntimeError→failed，耗尽ProviderTimeout→dead_letter |
| `logs/stage9-historical-orphan-cli.log`：旧副本恢复失败 | SQLite整秒文本与ORM绑定的`.000000`字符串不相等，严格CAS误跳过 | 保留SQLite原始租约文本到不可变proof，按原文CAS；不使用毫秒strftime截断 |
| `logs/stage9-historical-orphan-cli-after-fix.log`：27项断言通过 | 两次真实CLI可收敛旧孤儿，重复启动幂等 | 原始复现DB哈希不变；只改变复制库的目标Job，其余表和候选字节不变 |

## 文件与事务边界

- `backend/app/agent/jobs.py`：`fail`新增可选`commit=False`，默认行为兼容旧调用者。
- `backend/app/agent/continuation_worker.py`：异常处理重新获得Run锁；step/fact/Run失败投影与Job失败在同一提交内。提交前异常执行rollback，避免finally的release_run误提交半状态。
- `backend/app/agent/worker.py`：验证`continuation_failed`结果对应的真实queued/failed/dead_letter状态；启动时先回收有完整证据的历史孤儿，再激活正常续跑意图。
- `backend/app/agent/continuation_failure_recovery.py`：独立观察事务构造不可变proof，在Run及相关行锁内复核proof，再用Job+Run+step+fact条件CAS提交。
- `backend/app/agent/test_continuation_failure_atomicity.py`：5项提交可见性、中断回滚及worker接线测试。
- `backend/app/agent/test_continuation_failure_recovery.py`：95项归属、摘要、冻结计划、租约、竞态、精度、重试耗尽及幂等测试。

失败原子化并不回滚已经完成的Provider调用或候选文件；它处理的是数据库终态提交。候选仍未自动接受，不生成额外正文版本。

## 独立进程验收

### 1. 提交前进程退出

`logs/stage9-atomic-process-before_commit-20260907T064839-2feadf91/result.json`：**10/10**。

- 第一个CLI在Job条件更新后、事务commit前`os._exit(73)`。
- 重开连接看到四行仍为`running/running/running/started`，没有半失败投影。
- 过期旧租约后，真实CLI续跑为`paused/succeeded/completed/completed`。
- 原计划、候选字节不变，无重复writer、无正文版本。未提交的read允许恢复，不宣称外部read副作用exactly-once。

### 2. 提交后进程退出

`logs/stage9-atomic-process-after_commit-20260907T064920-29b608c0/result.json`：**11/11**。

- 第一个CLI在整笔事务commit后`os._exit(74)`。
- 四行均为failed；恢复CLI exit0，不改变终态、计划、候选或正文版本。

### 3. 历史孤儿的真实副本

`logs/stage9-historical-orphan-cli-20260907T070816-8243268b/result.json`：**27/27**。

- SQLite backup API复制旧故障库，原始库只读保留。
- 首次CLI收敛目标Job为failed并清空租约；第二次CLI无重复处理。
- Run/step/approval/artifact/fact/Plan/context/capability/正文版本与候选文件保持原样。

## 有效反向验证

所有变异只发生在Python内存中；未改写业务源码。

| 变异 | 结果 | 证据 |
|---|---|---|
| Job失败提前commit | 4个业务断言失败 | `logs/stage9-atomicity-mutation.json` |
| 去掉SQLite原始租约表示保护 | 1个业务断言失败 | `logs/stage9-raw-lease-fence-removed-mutation.json` |
| 去掉恢复归属校验 | 1个业务断言失败 | `logs/stage9-scope-check-removed-mutation.json` |
| worker恢复入口变为空操作 | 1个业务断言失败 | `logs/stage9-worker-recovery-no-op-mutation.json` |

旧变异与当前源码适用范围分开记录；阶段八8类变异不是阶段九全部新增代码的替代验收。

## 失败记录与未完成项

- 阶段九第一轮冻结全量session94166在24%主动结束：新发现SQLite文本精度缺陷，旧快照不作为通过。无删测、无放宽阈值；修复后从头全量。
- 恢复器生命周期chronology按秒粒度比较，以兼容数据库server_default秒精度；同秒微观逆序不作为精确取证结论。租约有效性与原文CAS保留微秒。
- 真实MySQL行锁、跨实例并发、生产部署矩阵仍待实测，SQLite成功不代表MySQL通过。
- 调度扫描上限、证据不足孤儿的可观测性与人工处置、完整API工作台E2E列入下一批。
- 文学质量七硬缺口仍独立保留；没有人工标签就不报告人类偏好或文学收益。

## 可复跑命令

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\backend'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q app/agent/test_continuation_failure_recovery.py app/agent/test_continuation_failure_atomicity.py
```

独立CLI证据脚本位于工作区`logs/`，每次创建新隔离目录，不清理旧数据库或上传文件。
