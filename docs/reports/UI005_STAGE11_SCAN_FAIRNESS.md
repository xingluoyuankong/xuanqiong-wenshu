# 阶段十一：Continuation 维护扫描活性修复

<!-- STAGE11_EVIDENCE_REFRESH_BEGIN -->
## 阶段十一最新复核：2026-09-07

**最终收口：后端2993 passed / exit0，634输入和2743既有资产无漂移。** `logs/backend-stage11-frozen-20260907T131232785321+0800.result.json`；扫描15项、新增3类反向检出、MySQL业务7项与命令9项通过。以下旧基线仍保留；完整报告见`docs/reports/UI005_STAGE11_MYSQL_BUSINESS_AND_FINAL_GATE_20260907.md`。

- 原始后端冻结全量 **2943 passed / 1369.76s / exit0**，629代码/配置与2737既有资产无漂移：`logs/backend-stage11-frozen-20260907T111845482296+0800.result.json`。这是Job/Run MySQL代次补丁之前的基线，补丁之后须再全量。
- 当前扫描6项基线已通过，恢复组合 **112 passed**：`logs/stage11-mutation-audit/run-20260907-114116/baseline-1/result.json`、`logs/stage11-recovery-final-targeted.log`。
- 内存反向10项：7检出、3存活；activation上限/异常回滚需补断言，返回预算需辨别冗余防线：`logs/stage11-mutation-audit/run-20260907-114116/summary.json`。
- MySQL已非“客户端/实例缺失”：隔离MySQL8.4.9正在40344端口运行；JSON默认值表达式、Alembic版本列128、002 marker重入、018 CONCAT方言均有修复。fresh迁移exit0、ORM新库83表。
- MySQL真实业务首轮红测发现generation恒0与stale completion被接受，Job/Run claim赋值顺序正在修复；故MySQL业务仍NO-GO，不按迁移通过推断业务通过。
- SSE后续真实Chromium2/2通过、前端原始三门禁634通过，详见`frontend/audit/sse-isolation-20260907/REPORT.md`与`frontend/audit/frontend-final-gates-20260907-112159/summary.verified.json`。

下方验证数字与“未完成”清单为原始阶段十一扫描修复时点；当前排期以`docs/reports/CURRENT_EXECUTION_STATUS_20260906.md`顶部为准。
<!-- STAGE11_EVIDENCE_REFRESH_END -->


## 结论

发现并修复了一个调度活性问题：恢复器和 blocked continuation 激活器固定按最旧记录取有限前缀；当前缀长期处于用户暂停、证据不足或损坏状态时，后续可处理记录会被永久遮挡。

修复后，worker 对两类维护扫描分别维护轮转游标；每轮仍使用有界查询，下一轮从上次扫描锚点继续，尾部后自动回绕。普通 Job claim 的排序和业务状态不变，跳过的记录不会被错误修改。

## Evidence → Finding → Path

| Evidence | Finding | Path |
|---|---|---|
| `logs/stage11-scan-fairness-red.log`：2 failed | 105个暂停前缀和205个未证明失败前缀可使健康 continuation 在旧固定窗口内永远不可达 | 修复前 `activate_ready`/`recover_failed_continuations` 固定前缀 |
| `logs/stage11-scan-cursor-green1.log`：103 passed | 轮转游标越过暂停/未证明前缀，健康 continuation 最终可激活或恢复；前缀仍保持原状态 | `backend/app/agent/continuation_scan.py`、`worker.py`、`continuation.py`、`continuation_failure_recovery.py` |
| `backend/app/agent/test_continuation_scan_fairness.py` | 覆盖用户暂停 blocked 前缀和未证明 failed orphan 前缀 | 两个真实 durable worker 场景 |

## 实现边界

- 新增 `ContinuationScanCursor`，仅保留内存中的当前 worker 游标，不写业务数据库。
- 维护扫描用 Job ID 做稳定轮转锚点，避免 SQLite/MySQL 时间精度差异影响分页。
- 每轮仍有上限；超过上限的记录不会被一次性加载。
- 游标扫描到尾部后自动回绕。
- Job claim 仍使用原有 available_at/created_at/id 顺序，不改变执行优先级。
- 用户暂停、取消、证据不完整和损坏 continuation 不会因为轮转而被自动改状态。

## 验证

```text
103 passed in 36.47s
```

阶段十一变更后必须重新执行后端原始全量；阶段十 `2720 passed` 仅作为历史基线。

## 未完成

- 真实 MySQL/InnoDB 双实例 CAS、锁等待和时间时区矩阵仍未通过。
- Docker daemon 当前不可用，继续保留只读探针结果。
- SSE fresh 浏览器长运行/中途断线重连和页面级 payload.run_id 错配仍需收口。
- 文学质量七项硬缺口继续独立推进。
