# UI005 阶段七：严格worker上下文与依赖等待语义

> 状态：实现和定向/内存反向已完成；正确backend目录全量2358通过/1020.08s，481文件结束hash无漂移。原F03的worker宽松读取已替换；原F02只关闭等待误判，持久化continuation生产者/消费者与事务交接仍待完成。文件名沿用当前证据批次编号，不以历史文档日期代替执行记录。

## 实现范围

| 文件 | 改动 |
|---|---|
| `D:\小说写作\xuanqiong-wenshu\backend\app\agent\run_context_integrity.py` | 从审批helper抽出中性严格读取器，返回(snapshot, user refs)；现代缺失/损坏不再返回legacy结果 |
| `D:\小说写作\xuanqiong-wenshu\backend\app\agent\approval_context_contract.py` | 调用共享读取器，继续负责真实资源解析、批准参数不变及稳定错误转换 |
| `D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py` | worker先检查原始context类型，读取关系capability事实后强制现代snapshot，原_relational_context_snapshot不再吞完整性错误；依赖从持久化step状态判定 |
| `D:\小说写作\xuanqiong-wenshu\backend\app\agent\dependency_state.py` | 纯依赖分类，只有completed满足；等待/失败/取消有不同结果，未知值按失败 |
| `D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_runtime.py` | 为plan_step_blocked/cancelled显式保留有限reason/dependencies等事件字段，不放开任意payload |

审批helper语义仍是“当前Run绑定快照”，没有新增Approval创建时snapshot版本字段。共享读取器不将自动novel refs当用户选择；只核验用户前缀、关系元数据与摘要，之后由各入口解析真实引用资源。

## Evidence → Finding → Path

| 证据 | 观察 | 修复结果 |
|---|---|---|
| `D:\小说写作\xuanqiong-wenshu\logs\worker-context-before-20260907.log` | 14失败/3通过；13类现代缺失/身份/digest/refs损坏仍到达Planner，invalid-json虽停止但变成普通ValueError | 17条真实worker测试覆盖缺row、digest/ref digest、ID/key、user/session/project/correlation/transaction、双删定位、null、refs漂移和原context类型；initial/replan-context/真实legacy正例保持 |
| `D:\小说写作\xuanqiong-wenshu\logs\worker-context-after-shared-20260907.log` | 62通过/125.76s | 新worker17 + 审批29 + 原worker16，无静默fallback |
| `D:\小说写作\xuanqiong-wenshu\logs\worker-dependency-before-20260907.log` | 两个真实write→read/链式依赖用例：下游被错误写为failed | 依赖等待保留pending，原checkpoint参数/PlanRevision依赖不改，首轮job可ACK，Run仍awaiting_approval |
| `D:\小说写作\xuanqiong-wenshu\logs\worker-dependency-after-20260907.log` | 中间2失败/80通过，事件reason字段被服务白名单丢弃 | 补两个事件的有限字段白名单；不删事件断言 |
| `D:\小说写作\xuanqiong-wenshu\logs\worker-dependency-after-events-20260907.log` | 两条真实worker等待用例通过 | 无下游read、无额外Planner/replan、无错误终态 |
| `D:\小说写作\xuanqiong-wenshu\logs\stage7-worker-approval-targeted-20260907.log` | **267通过/153.64s** | 新worker17、等待与事件4、纯helper64、原worker16、审批166组合；正常仓库pytest |

新增测试：

- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_worker_context_integrity.py`
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_worker_dependency_waiting.py`
- `D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_dependency_state.py`

真实worker测试使用临时SQLite与实际AgentWorker/Runtime/Job/Step/PlanRevision服务，仅Planner和昂贵read叶子替换。负例不仅检查异常，而是检查Planner/read零调用、Run/job明确失败、无step/Artifact/capability execution/PlanRevision或visible job新增。正例包括真实旧形态Run，未把现代Run清空标识后冒充legacy。

## 反向验证

主代理驱动：`D:\小说写作\xuanqiong-wenshu\logs\stage7-worker-memory-mutation-20260907.py`。原conftest、进程内替换、finally恢复、源码hash一致：

| 模式 | 故意破坏 | 业务断言失败数 |
|---|---|---:|
| worker-context | worker context loader返回None恢复宽松路径 | 13 |
| dependency-wait | waiting被分类成failed | 2 |
| dependency-event | 删除两类事件白名单 | 2 |
| shared-refs-prefix | 内存函数省略共享reader的refs关系前缀/元数据检查 | 2 |

日志与逐项JSON：`D:\小说写作\xuanqiong-wenshu\logs\stage7-{mode}-mutation-20260907.log`及.json。各驱动exit0表示预期红灯被正确检出，不表示变异版本测试通过。无磁盘变异/HMR干扰、无TypeError或SyntaxError充数。

纯helper子智能体证据：`D:\小说写作\xuanqiong-wenshu\logs\ui005_dependency_state_20260907\mutation_summary.json`，64用例、1,728组三依赖组合、9类进程内变异均检出。最初缺模块收集失败不作为行为回归证据；该helper行为证明来自正常绿灯与9类有效变异。

## F02明确未完成的部分

本批保留完整write→read依赖，不限制写操作必须末步，但目前只做到“批准前等待不失败”。尚未实现：

1. approval executed/rejected/execution_failed与续跑意图的同事务提交。
2. 专用continuation job、原PlanRevision/参数/checkpoint复用、独立CLI handler注册。
3. 初始worker ACK与提前批准之间的持久化交接屏障。
4. 用户pause/cancel优先、候选仍未接受、quality_blocked返回态及消费ACK原子化。
5. 重启/双worker/重复审批/重试的幂等及有界对账。

取消/失败状态纯helper已区分；主循环接入取消分支不等于完成审批拒绝的终态事务链。后续W03—W14仍应按UI005_WORKER_CONTINUATION_PLAN_20260907.md逐项实现和验证，不能由本批267通过外推完成。

## 当前门禁与下一步

正确工作目录在启动前以Python assert验证为 `D:\小说写作\xuanqiong-wenshu\backend`。

- 冻结指纹：`D:\小说写作\xuanqiong-wenshu\logs\backend-stage7-frozen-fingerprint-20260907.json`，481个backend/app Python文件。
- 全量日志：`D:\小说写作\xuanqiong-wenshu\logs\backend-full-stage7-20260907.log`，自然终态2358 passed in1020.08s，exit0；结束hash在 `logs/backend-stage7-verified-fingerprint-20260907.json`。
- 前端本批未修改，沿用601通过/type-check/build16.89s，未无意义重复跑前端。
- 正文质量七项硬缺口、真实人工标签、完整API页面E2E、Docker/MySQL运行时仍未闭合；主目标active，发布NO-GO。
