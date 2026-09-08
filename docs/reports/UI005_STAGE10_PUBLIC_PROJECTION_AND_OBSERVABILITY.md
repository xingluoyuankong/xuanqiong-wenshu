# UI005 阶段十：公共 Job 投影、恢复器可观测性与前端消费

## 当前结论

截至 **2026年9月7日**，阶段十后端冻结门禁已有效通过：**2720 passed / 1209.75s / exit0**，621个代码/配置输入与2734个既有数据文件前后一致。阶段十定向 API、日志与新增 transaction-scope 回归通过；前端公共 Job 投影消费同步完成，定向75项、前端全量615项、type-check和build通过。整体仍为 **active / NO-GO**，Docker/MySQL实机及文学质量硬缺口仍未收口。

## Evidence → Finding → Path

| Evidence | Finding | Path |
|---|---|---|
| `logs/stage10-api-visible-correlation-green.log`：43 passed | 公共 Job 状态、终态、分页、成员读取、SSE终止与自绑定可见响应标识具备回归覆盖 | `backend/app/api/routers/agent.py` + `agent_job_projection.py` |
| `logs/stage10-api-additional-green1.log`：5 passed | Job投影必须同时绑定 user/run/correlation/transaction/project；伪造 transaction 不进入列表或Run状态 | `scoped_job_query` transaction `IS NOT DISTINCT FROM` 条件 |
| `logs/stage10-logger-disabled-green1.log`：组合48 passed | Alembic `fileConfig` 造成已导入子logger disabled 时，恢复器事件仍需可观察；测试捕获器恢复原logger状态 | `continuation_failure_recovery.py` 日志路径与观测测试 |
| `logs/backend-stage10-frozen-20260907T084230072041+0800.result.json`：`2720 passed`、`valid_gate=true` | 阶段十后端全量无代码/既有资产漂移 | `run_backend_stage10_frozen_gate.py` |
| `logs/stage10-frontend-job-projection-summary.json` | 前端类型、公共字段白名单和数据面板消费已完成 | `frontend/src/api/agent.ts`、`AgentDataPanel.vue`及其测试 |

## 实现摘要

- 后端新增只读 `PublicAgentJobRead`，隐藏 payload、私密 result、error_detail、lease_owner 和原始幂等键；只公开有限终态、恢复状态和自绑定 visible-response 标记。
- Run state 的 Job 列表复用同一 scoped query，绑定 user、run、correlation、transaction、project；读取项目成员可见状态，Job列表保持 owner scope。
- 恢复器记录 `continuation_failure_recovered` / `continuation_recovery_skipped` 结构化事件，不记录错误正文、Provider响应或凭据；对被迁移配置禁用的 logger 先恢复可观察性。
- 前端把 `terminal_status`、`recovery_status` 和安全 `result_json` 收窄为类型白名单；DataPanel显示固定中文摘要，不序列化未知字段或错误正文。
- `visible_response_job_id` 仅当它等于当前 Job ID 时进入公共结果，防止任意关联ID泄漏。

## 反向验证

阶段十已保存以下内存变异证据：

- 去掉公共 Job 投影：业务断言失败；
- 去掉 scoped query：跨用户/跨Run/跨项目断言失败；
- 去掉恢复入口：历史孤儿worker接线断言失败；
- 去掉恢复日志事件：两项可观测性断言失败；
- 前端四类 DataPanel 变异全部检出（见前端审查报告）。

变异只在进程内替换函数，源码哈希保持一致；旧变异日志若引用修复前测试捕获器，保留为历史失败，不当作当前冻结证据。

## 未完成与下一批

1. 真实 MySQL 行锁/跨实例恢复与 production deployment matrix 仍未实测；SQLite通过不外推为MySQL通过。
2. API层 continuation 查询已覆盖公共Job/Run state，但尚需完整前端端到端浏览器验收与真实长运行SSE重连矩阵。
3. Docker只读探针仍 `Server=null`；未启动或重置Docker卷。
4. 文学质量七项硬缺口继续保留：E01.2、E11/T22、T06、T16、T18、T26、human labels。
5. 阶段十后的任何 backend 修改都必须从头重跑后端全量，不使用2720作为新代码背书。
