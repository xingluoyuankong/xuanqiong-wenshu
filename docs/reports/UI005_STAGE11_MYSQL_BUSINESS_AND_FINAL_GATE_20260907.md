# 阶段十一：MySQL业务链、扫描反向与最终集成

## 阶段十二最终门禁（2026-09-07 15:59 +08:00）

阶段十二新增连接时区策略、时区回归、`writing_v2` seed 字节修复后的原始后端全量已通过：**2993 passed / 1547.77s / exit0 / valid_gate=true**；冻结636代码/配置、2746既有资产，测试前后无漂移。权威证据：`logs/backend-stage11-frozen-20260907T153311499845+0800.result.json`。

阶段十二已形成的证据：

- S12-03真实非UTC MySQL连接策略四项全通过，专属18 passed：`logs/stage12-timezone-app-verify/run-20260907T152917-b42134e0/result.json`。
- S12-04真实SQLite执行前/执行中强杀与worker重启恢复通过，执行中read按至少一次记录：`logs/stage12-crash-recovery-live-20260907T152245-5752a26b/result.json`。
- S12-07文学质量只读复核完成但七项hard gap保留：`logs/stage12-literary-S12-07/completion-audit.json`。

仍未完成：Docker实际部署矩阵、MySQL执行中强杀/故障切换、真实后端+浏览器综合闭环、Provider真实文学质量批次和七项文学真值。目标保持active、发布NO-GO。

## 最终状态（2026-09-07 13:41 +08:00）

**第三轮原始后端全量2993 passed / 1694.68s / exit0 / valid_gate=true；634个代码/配置、2743个既有资产无漂移。** 最终证据：`logs/backend-stage11-frozen-20260907T131232785321+0800.result.json`。本结果包含同秒命令顺序和MySQL NULL排序修复，不由旧门禁与定向拼接。

前端本轮634/type-check/build通过，SSE真实浏览器2项通过；MySQL业务7项、命令/投影/NULL9项及跨OS进程claim/recovery/CLI空闲重启通过。反向证据、第二轮1失败、所有旧数据库/日志均保留。第一轮到最终的11个源/测试变更见`logs/stage11-first-to-final-source-manifest.json`。

阶段十一工程修复与本轮验收已收口，但整体目标仍active、发布NO-GO：Docker部署、非UTC默认会话、执行中强杀、真实Provider综合链路与七项文学质量缺口仍须继续。下一阶段：`docs/reports/STAGE12_EXECUTION_PLAN_20260907.md`。

下方“运行中/准备第三轮”是执行过程历史记录，均由本顶部最终证据覆盖。

## 当前结论

2026-09-07在现有任务与工作区接续，保留原始数据库、上传文件、日志及所有未提交改动。阶段十一第一轮冻结全量2943通过；随后真实MySQL业务验收暴露两类SQLite全量没有发现的缺陷，已修复并完成7/7真实业务验收。补丁后第二轮原始后端全量已完成：2973 passed、1 failed，exit1；同秒命令排序回归已定位并修复，正在真实MySQL复验后准备第三轮全量，不据第一轮数字替新源码背书。

原任务：**全面优化重构玄穹文枢**（`01a02410-94af-7002-9585-3532293aa587`）。执行仍在当前任务（`01a06d1c-19e0-75e0-a30e-9c3d0bae9867`）。没有新建Codex任务；使用现有及新增子智能体分离MySQL、前端门禁、扫描反向写集。

## 修复与证据链

| Evidence | Finding | Path |
|---|---|---|
| 首轮真实MySQL业务result：claim单赢家但generation0，stale completion成功 | UPDATE先写owner/expiry，再执行读取它们的generation CASE，MySQL结果与SQLite不同 | `backend/app/agent/jobs.py::claim_job`、`backend/app/services/agent_runtime.py::claim_run`采用ordered_values |
| R2 chronology：step.started_at=04:23:17，之后创建的fact.started_at=04:23:16 | 应用微秒时间写DATETIME(0)进位，而fact起点依赖数据库整秒时钟，导致跨行时间顺序倒置 | Runtime生命周期写入UTC整秒；fact开始/重试/完成/失败显式统一UTC整秒 |
| lifecycle red：5 failed / 1 passed | 固定.750000秒复现落库时序合同，保留真正跨秒倒序拒绝 | `backend/app/agent/test_mysql_lifecycle_clock.py` |
| claim/clock组合141 passed，真实业务R4 7/7 passed | Job/Run代次与恢复时序修复通过 | `logs/stage11-mysql-claim-clock-directed.log`及R4result |
| 初始10个内存变异7检出/3存活 | activation测试未直接验证扫描上限和异常游标恢复；返回预算在正整数路径为冗余，但非正预算真实可达 | 追加9项扫描回归并重跑3个存活变异 |

### 修改范围

- `backend/app/agent/jobs.py`：明确generation CASE先于owner/expiry赋值；显式generation=0不当作缺省。
- `backend/app/services/agent_runtime.py`：Run同类赋值顺序；读取刷新避免ORM身份映射保留旧代次；生命周期时钟写入前取UTC整秒。
- `backend/app/services/agent_execution_service.py`：新建/重试fact显式记录本次开始时间，完成/失败时间统一秒精度；duration_ms计算保留原时间精度。
- `backend/app/agent/test_lease_mysql_dialect.py`：编译真实服务语句验证MySQL/SQLite SET顺序，显式代次与重领/续租/旧完成回归。
- `backend/app/agent/test_mysql_lifecycle_clock.py`：生命周期时间精度与真实跨秒倒序拒绝。
- `backend/app/agent/test_continuation_scan_fairness.py`：真实SQL扫描上下界、异常回滚/重试、非正预算保留blocked。

现有恢复proof未降低时间证明要求；没有把generation0补写成1；没有改全量测试收集范围。

## 真实MySQL验收

实例：独立native MySQL8.4.9、127.0.0.1:40344、UTC、REPEATABLE-READ、FK检查开启。新建随机隔离数据库，未覆盖已有库。Planner/writer采用既有受控夹具，Job、Run、审批、continuation及恢复运行真实服务/SQL。不是实际Provider文学质量测试。

权威业务结果：`logs/stage11-mysql-continuation-business-20260907T122916-e70a7d19/result.json`。

| 场景 | 实测 |
|---|---|
| 双连接同Job领取 | 两连接都观测到锁等待；SQL更新rowcount为1和0；仅一个winner；generation1 |
| Job过期重领 | 旧generation1，新generation2；旧完成被拒，Job仍running且result未污染 |
| Run续租/重领 | 首次1、同owner未过期仍1、过期后2；新连接读回2 |
| 审批后continuation生产 | 真实审批/冻结计划数据产生blocked intent |
| 历史失败孤儿构造 | 真实失败Run/step/fact与过期running Job，保留独立证据 |
| 失败恢复CAS | 分别改Run state_version、step error_type、fact error_type、Job lease_owner，过时proof均拒绝；双恢复者单赢家，重复恢复为空 |
| UTC/expiry | NOW(6)=UTC_TIMESTAMP(6)，未来available_at拒绝领取；DATETIME精度0，读取时按UTC约定处理 |

源文件前后指纹一致。R1/R2/R3失败证据保留；R2/R3还包含验收脚本本身的REPEATABLE-READ快照读取顺序与证据字段错误，已在新脚本修正，不冒充业务源码修复。

真实MySQL负控制：`logs/stage11-mysql-continuation-business-20260907T123255-1fb16483/result.json`。只在进程内把generation表达式移回owner/expiry之后，generation/旧完成/Run续租再次失败；磁盘实现不改。

### 迁移证据独立归属

- fresh迁移：`logs/stage11-mysql-alembic-upgrade-fresh.json`，exit0。
- fresh库只读复核：`logs/stage11-mysql-fresh-readonly-verify.json`；库`xq_stage11_mig_854e1a38`，head `030_research_schema_repair`，87表。
- 旧`stage11-mysql-head-verify.json`指向`xq_migration_fixture`，86表；它不属于fresh库，保留但不串写。
- 独立ORM建表：`logs/stage11-mysql-create-all.json`，83表。
- JSON默认值括号表达式、Alembic版本列128、002 marker重入和018 CONCAT兼容已落盘。迁移表数不同不直接证明schema等价，仍需专门差异/部署矩阵。
- Docker Server旧探针仍缺失；native实例结果不替代Docker部署、备份和恢复验收。

## 反向验证

1. 扫描/迁移初始10项：`logs/stage11-mutation-audit/run-20260907-114116/summary.json`，7检出/3存活，collection_errors=0。
2. 新增9项后，扫描基线15 passed；3个存活变异均由call阶段断言检出：`logs/stage11-mutation-audit/activation-scoped-20260907-122908/summary.json`。
3. M10准确边界：默认worker正整数预算下早退为等价冗余；检测来自服务方法真实可达的limit=0/-1，并用limit=1实际成功激活作阳性对照。没有伪造超长候选页。
4. 代次/时钟新增3个进程内负控制：`logs/stage11-mysql-negative-job.json`、`stage11-mysql-negative-run.json`、`stage11-mysql-negative-clock.json`；均exit1、检出且源未改。
5. 不把不同测试修订的7+3写成同一次10/10运行；完整历史批次与前后SHA256分别保留。

## 门禁

| 门禁 | 状态与证据 |
|---|---|
| 阶段十一第一轮后端 | 2943 passed / 1369.76s / exit0；629输入、2737既有资产无漂移；`logs/backend-stage11-frozen-20260907T111845482296+0800.result.json` |
| MySQL补丁后第二轮后端全量 | **1 failed, 2973 passed / 1542.57s / exit1 / valid_gate=false**；631输入、2740既有资产无漂移；`logs/backend-stage11-frozen-20260907T123239703488+0800.result.json` |
| 当前前端 | type-check/test:run/build-only均exit0，83文件634 passed；`frontend/audit/frontend-final-gates-20260907-112159/summary.verified.json` |
| SSE真实浏览器 | 2/2，真实HTTP60秒续接/去重/取消/Run切换；`frontend/audit/sse-isolation-20260907/final-sse-results.json` |

## 下一步

1. 收回补丁后后端全量真实退出码、测试数与指纹；失败就保留红测定位修复，不使用旧通过数替代。
2. 增补真实MySQL独立进程worker重启与迁移前后schema/备份恢复证据；双连接验收不外推为双进程已通过。
3. 单独完成Docker部署矩阵，保护既有卷；daemon缺失时推进其他独立任务。
4. 七项文学质量缺口继续按接续计划推进。本轮只读重算`logs/stage11-quality-recheck-20260907T122447/gap-recheck.json`仍7项、completion_eligible=false；未填写或伪造人工标签。

总目标保持active，发布NO-GO。

## 部署只读复核补充（2026-09-07 12:38 +08:00）

`logs/stage11-deployment-readonly-20260907T123803.json`：docker info退出1，dockerDesktopLinuxEngine named pipe不存在；未启动/重启Docker，未修改卷。

源码审查另发现部署时区验收边界：`deploy/docker-compose.yml` 的db环境为TZ=Asia/Shanghai，而`backend/app/db/session.py`的MySQL连接参数未显式初始化会话UTC。当前真实业务探针显式init_command设置UTC，因此7/7结果只证明UTC会话路径，不证明部署默认时区路径。下一阶段需要新实例/连接池初始化与回收复用的真实时区矩阵，检查服务端默认时间、ORM读回和生命周期排序，不修改现有实例全局时区。

## 第三轮集成前的命令排序与NULL兼容修复

### 同秒命令回归

第二轮全量唯一失败为`test_pause_resume_cancel_have_auditable_state_transitions`：暂停/继续/取消同秒请求的requested_at相同，随机UUID排序不等于请求顺序。独立重跑同样失败：`logs/stage11-command-timestamp-red.log`。

- 新增`backend/app/agent/command_ordering.py`，使用同一Run/user/correlation/transaction、同command_id/type的持久化run_command_requested事件sequence打破同秒平局；NULL transaction以空值安全比较处理。
- requested_at仍作为第一排序键；Run-local sequence不被当作全局时钟；没有匹配事件的历史命令保留稳定ID后备顺序。
- 接入runtime三类命令列表、state projection、command_recovery领取与过期恢复；不新增数据库字段、不重写历史记录。
- 初始新增测试红7/绿1；修复后与旧runtime组合47通过；扩展14项专属回归后相关组合86通过。
- 反向：恢复仅timestamp/UUID排序13断言失败；去掉scope4维校验6断言失败；控制组14通过。证据`logs/stage11-command-chronology-mutation-summary.json`。

### MySQL NULL次序语法

真实MySQL命令验收7项中6通过，但projection触发审批查询`NULLS FIRST`语法错误：`logs/stage11-mysql-command-order-20260907T130448-09c052f9/result.json`。全库核对共4处，涉及runtime两类审批列表、state projection和Job dead-letter列表。

- 使用`IS NULL`布尔键后接原值排序，保留审批NULL优先/死信NULL最后语义。
- 新增`backend/app/agent/test_mysql_null_ordering.py`，编译实际服务语句为MySQL方言再执行SQLite行为验证。
- 先红4失败/1通过，进程内回退同样4个call断言检出、collection_errors=0、source_unchanged=true：`logs/stage11-null-order-negative.json`。
- 真实MySQL新库复验与最终全量仍以随后新结果为准。

### 跨进程及schema补充

- `logs/stage11-mysql-cross-process-20260907T125031-69e4e31d/result.json`：两个实际Python进程Job claim单赢家rowcount1/0；另两个进程failure recovery单赢家，恢复入口与worker CLI新进程重复执行幂等。未覆盖执行中强杀、网络分区或MySQL故障切换。
- `logs/stage11-mysql-schema-audit/schema-diff.json`：83个共享业务表列定义一致，4表差为迁移版本/marker；两条冗余唯一索引能力等价；026 trigger仅在迁移库存在符合create_all与迁移的预期边界。当前startup/deploy走Alembic，未据ORM样本缺trigger指称生产缺陷。
- schema初稿mysql_version误记collation和触发器优先级误判已更正，错误初稿逐字节保留并有离线反向校验。

## 第三轮冻结门禁启动（2026-09-07 13:12 +08:00）

- 命令/投影/NULL最后组合：`logs/stage11-command-null-projection-combined.log`，78 passed / 134.37s。
- 真实MySQL新库：`logs/stage11-mysql-command-order-20260907T131017-9950da8c/result.json`，9/9通过，源码无漂移。包括列表分页、projection、JSON/null-safe相关子查询、历史后备、claim/recovery顺序、approval NULL first、dead-letter NULL last及EXPLAIN。
- 第三轮原始全量：`logs/backend-stage11-frozen-20260907T131232785321+0800.log`，session15806；634个代码/配置输入、2743个既有资产。状态运行中，不提前写通过。
- 第二轮1失败/2973通过与原始错误栈完整保留；不是重跑单个失败测试后把旧全量拼成通过。

## 有界命令排序性能

第三轮冻结期间执行只写logs与新隔离库的性能支线：`logs/stage11-command-order-scale/run-20260907T131919-949cc349/summary.json`。6档、90次SELECT均通过，最慢52.734ms，最大每库5000事件/100命令。未执行命令业务、未增加索引，源指纹无漂移。仅证明单Run/已预热/共享负载的有界矩阵；跨Run、并发与生产SLA未证明。详见`docs/reports/STAGE12_EXECUTION_PLAN_20260907.md`的S12-02追加说明。

## 阶段十二接续结果（2026-09-07 15:31 +08:00）

- S12-03：生产MySQL连接级UTC策略已实现并真实通过；证据`logs/stage12-timezone-app-verify/run-20260907T152917-b42134e0/result.json`，专属18项通过。
- S12-04：真实SQLite live强杀两场景通过；工具执行前恢复一次read，工具执行中恢复按至少一次语义；证据`logs/stage12-crash-recovery-live-20260907T152245-5752a26b/result.json`。
- S12-07：文学质量只读复核29项通过、7/7变异检出，但completion资格仍为false，七项hard gap保留。
- `writing_v2` seed行尾漂移已矫正并通过精确种子回归；这属于现有初始化资产一致性修复，未改变提示正文语义。
- 新增源码变更后，最终后端全量需要从头重跑；2993是历史阶段十一基线，不覆盖本批。
