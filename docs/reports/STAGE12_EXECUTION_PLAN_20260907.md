# 阶段十二执行方案：部署一致性、规模门禁与质量证据

## 接续边界

当前工作区`D:/小说写作/xuanqiong-wenshu`，分支`codex/bohrium-integration-20260831`。目标保持active，当前整体NO-GO。阶段十一三轮门禁分别保存，第三轮已2993通过、exit0、源与资产无漂移；本方案只排期下一阶段，未实施项不得写成完成。

本任务继续由主代理协调子智能体，不新建Codex任务。现有danger-full-access/never运行环境由工具继承；不以口头承诺改变工具实际权限。不重置数据库、不改旧上传/正文、不清理失败证据，不把CLI空闲重启外推为执行中崩溃恢复。

## 1. 当前可接受的工程基线

- UI005审批后持久化continuation、冻结计划/上下文/能力、第二次审批、来源ACK与generation防线已实现；不重新Planner、不自动接受候选、不自动创建正文版本。
- SQLite后端第二轮2973通过/1失败已经发现同秒命令排序问题，现已修复并完成定向；第三轮已2993通过并涵盖该修复。
- MySQL真实业务7项通过、跨OS进程claim/recovery和CLI空闲重启通过；命令/投影/NULL次序真实9项通过。
- 前端type-check、83文件634测试、build通过，SSE真实HTTP/Chromium2项通过；后端之后的变化不等于浏览器全后端链已重跑。
- MySQL fresh迁移87表与ORM83业务表的4表差为迁移marker；两条冗余唯一索引已识别，026触发器在迁移路径存在，未据create_all测试样本省略trigger断言生产缺陷。
- 文学质量仍7项hard gap；人工标签0行填写。本轮所有绿灯是工程证据，不等于文学收益。

## 2. 执行顺序及完成条件

| 编号 | 任务 | 实现/检查位置 | 完成条件 | 触发退回条件 |
|---|---|---|---|---|
| S12-01 | 已完成：阶段十一第三轮2993通过 | `logs/run_backend_stage11_frozen_gate.py` | 原始pytest-q exit0，完整汇总，输入/资产指纹无漂移 | 任一失败、collection错误、源码或既有资产漂移 |
| S12-02 | 命令排序规模评估（有界单Run矩阵已通过） | `backend/app/agent/command_ordering.py`、`command_recovery.py`、`state_projection.py` | 新隔离库100/1000/5000事件及10/100命令，列表/claim SELECT耗时与EXPLAIN；给p50/max和样本边界 | 单查询>5秒停止扩容并记录，不用小样本宣称SLA |
| S12-03 | UTC策略与真实R4通过，默认门禁扩展后运行中 | `backend/app/db/session.py`、`backend/alembic/env.py`、`deploy/docker-compose.yml` | 非UTC服务端下应用连接初始化、连接池新建/回收、迁移连接、TIMESTAMP默认值/生命周期字段采用一致UTC；配真实反向 | 探针偷偷覆盖时区而生产连接没有；只测UTC实例 |
| S12-04 | SQLite/MySQL工具前/中强杀通过，其他崩溃窗口待补 | `backend/scripts/agent_worker.py`、`continuation_worker.py`、`continuation_failure_recovery.py` | 新迁移库中执行前/事务中/提交后强退出，独立worker重启；单工具事实、无重复候选、CAS与终态对账 | 只测空闲--once；把fixture强制改终态称自动恢复 |
| S12-05 | 原生MySQL迁移约束/87表恢复通过，Docker部署待补 | `backend/app/db/init_db.py`、`backend/alembic/versions`、`deploy/scripts/deploy_docker.sh`、`rollback.sh` | 真迁移库trigger合法/非法写入边界、升级重入、备份恢复；Docker daemon恢复后走实际compose矩阵 | create_all代替迁移，重置卷，删旧证据，忽略恢复失败 |
| S12-06 | 前后端综合工作台闭环 | `frontend/e2e/agent-workspace.spec.ts`、`backend/app/api/routers/agent.py` | 真实后端+独立worker+浏览器，聊天/项目切换/审批/恢复/终态/候选查看链 | 仅route.fulfill或受控HTTP流，却声称实际后端全链路 |
| S12-07 | 已完成只读复核，七项仍缺真值 | `backend/scripts/audit_*`、`backend/output` | 每项按下表真实证据达标并重算completion资格 | 自动分数/AI评审伪装人工标签，换cohort、删失败样本 |

## 3. 数据库优化实施原则

### 命令顺序规模化

当前排序以requested_at、run_id、匹配请求事件最小sequence、command_id组成稳定顺序；sequence仅在同Run时间平局内比较。相关子查询按run_id缩小事件范围，JSON匹配仍需要过滤；EXPLAIN filesort是观察，不等于错误，也不等于磁盘溢出。

若实测规模成本不可接受，先设计有迁移支持的request_sequence持久化字段及正确回填/空值后备，再比较索引方案；不把sequence抄到可变payload后无完整性约束当作权威事实。新的字段必须在command和requested event同事务写入；旧记录仅由匹配Run/user/correlation/transaction、command_id/type的事件证明回填。

### UTC连接契约

已发现compose db使用Asia/Shanghai，应用MySQL engine未显式设置session UTC，现有业务验收则显式设置UTC。因此需要真实非UTC对照而非单纯改报告。优先连接级修复，不改变现有服务器GLOBAL time_zone；测试新连接、池复用/失效重建、迁移engine。不得输出连接密码。

### 历史异常处理

旧generation0与跨行时间倒序记录保留取证；当前补丁保护新执行，严格恢复器不会自动为旧坏数据编造generation或时间。针对历史修复另建带筛选证明、dry-run差异、事务CAS和可回滚副本的工具；未经逐项证明不批量修数。

## 4. 文学质量七项的证据要求

| 缺口 | 下一份有效证据 | 明确排除 |
|---|---|---|
| E01.2 Prompt gain | 同Provider/model/scorer/mission contract、保留prompt差异指纹的配对批次，报告全分布与失败 | 均值被单项拉高即宣布提升；混用不同cohort |
| E11/T22 repair gain | 同一真实失败文本触发repair，保存before/after、实际修复差异和诊断 | unchanged两条当有效收益；只测修复函数可调用 |
| T06 degrade rate | 统一cohort完整retry_events与eligible分母，Provider最终阻断单列 | 0条已记录重试等于退化率0；旧批次补造retry原因 |
| T16 before/after | 同scorer/契约、有效内容摘要与版本身份的严格配对 | 不同scorer候选、控制模板、单侧summary |
| T18 exemption truth | 真实豁免触发记录与独立质量审阅 | 人造触发等于生产有效；AI填human字段 |
| T26 dialogue calibration | 真实语料分层抽样、标注准则与独立标签后计算precision/recall | 10个边界fixture等于语料校准 |
| human quality labels | 人工实际审阅、reviewer身份、内容指纹与样本对应 | AI预标注、空模板、重复reviewer模板计为独立样本 |

现有样本先整理出“待审正文+判定维度+来源指纹”的低负担审阅包，AI辅助评审使用单独字段与显式来源；若用户不做人工标注，项目可继续工程优化，但human_preference_proven保持false，不虚构完成。

## 5. 子智能体协调与门禁纪律

- 主代理负责立即阻断项、集成、最终门禁与接续文档；不把当前必须解决的问题丢给子智能体后空等。
- 子智能体按文件写集分工：数据/时区、命令规模、前端综合E2E、文学证据分别隔离。源码冻结期只允许logs证据或只读分析。
- 子智能体遇实际错误时先读错误、检查进程和测试日志、给出可复现事实并继续可独立工作；不得反复请求已具备的工具权限。
- 完成子智能体及时关闭；需要原上下文时恢复同一子智能体，不创建新任务。
- 新修复必须先红后绿和内存/隔离副本反向；记录真实call断言，不把导入失败算检出。
- 每个阶段末尾执行后端原始全量、必要的前端三门禁、源/既有资产指纹；旧数字仅作历史基线。

## 6. 权威状态入口

当前数字以`docs/reports/CURRENT_EXECUTION_STATUS_20260906.md`顶部滚动表为准，实施细节见`docs/reports/UI005_STAGE11_MYSQL_BUSINESS_AND_FINAL_GATE_20260907.md`。日期以证据recorded_at/finished_at为准，文件批次名不替代实际时间。

## S12-02 提前完成的有界证据（2026-09-07 13:20 +08:00）

`logs/stage11-command-order-scale/run-20260907T131919-949cc349/summary.json`及`report.md`：6个新隔离库，100/1000/5000事件×10/100命令；5种SELECT各3次，共90次，匹配和顺序均通过，最慢52.734ms，未触发5秒中止阈值。源码未修改，命令仍requested、attempt_count=0、generation=0。

最大档5000事件/100命令：列表median47.717ms、第一页median49.557ms、claim candidate SELECT median47.990ms。此处包含execute+fetch，不含连接创建/API序列化；数据校验会预热缓存，机器与主全量共享负载。EXPLAIN多为event_type索引过滤+相关子查询、外层filesort；不是所有规模都走run_id索引，也不证明发生磁盘溢写。

该单Run上限内无需为了filesort添加索引。多Run、高并发、冷缓存及大规模命令队列仍保留为后续性能覆盖，不宣称生产SLA。完整批次输出均保留，不将有界样本外推为无限规模通过。

## 阶段十二已完成证据（2026-09-07 15:31 +08:00）

### S12-03 MySQL连接级UTC

- 实现：`backend/app/db/mysql_timezone.py`；应用engine、Alembic迁移engine、首次建库admin engine均安装connect+checkout策略，只执行`SET SESSION time_zone = '+00:00'`，不改GLOBAL。
- 专属回归：`backend/app/db/test_mysql_timezone_policy.py` **18 passed**；移除策略负向控制真实失败。
- 真实非UTC实例：PID 28424、端口1914、MySQL8.4.9、global/session `+08:00`；旧40344 UTC实例未修改。
- 真实生产连接验收：首次连接、池污染后归还、8并发借用、invalidate重连、dispose重建、Alembic upgrade head、TIMESTAMP/DATETIME持久化均通过；迁移head=030、87表。结果：`logs/stage12-timezone-app-verify/run-20260907T152917-b42134e0/result.json`。
- 负向：移除connect/checkout listeners后，物理新连接继承`+08:00`、污染连接保持`-05:00`；恢复策略后回到UTC。未声称生产SLA；日志中的跨event-loop清理警告已记录，不影响断言/退出码。

### S12-04 live强杀恢复

`logs/stage12-crash-recovery-live-20260907T152245-5752a26b/result.json`：两个真实worker进程场景通过。

- 工具执行前强杀：工具未执行，重启后一次read，冻结计划/上下文/能力快照及候选唯一性保持，无正文版本。
- 工具执行中强杀：真实`statistics.project`已完成章节查询后被强杀；重启后read重试并完成，明确按至少一次语义记录，不宣称exactly-once。
- 两场景均有父进程真实TerminateProcess、重启worker、repeat worker幂等、CAS和负向检查；source/既有资产无漂移。
- MySQL强杀矩阵、网络分区和物理主机故障切换仍未完成。

### S12-07文学质量只读复核

`docs/reports/STAGE12_LITERARY_S12-07_20260907.md`及`logs/stage12-literary-S12-07/`：29 passed、7/7内存反向检出，但七项hard gap均保留，`completion_eligible=false`。本轮未调用Provider、未填写人工标签、未改正文/数据库；该支线严格写集存在首次运行核验限制，已在补充报告中披露。

### 其他

- `backend/app/db/seeds/prompts/writing_v2.md` 已与 `backend/prompts/writing_v2.md` 字节一致；原差异为中段LF/CRLF漂移，精确种子回归恢复通过。
- S12-03源码新增后必须执行新的后端原始全量；旧2993只覆盖此前源码。

## 16:28 当前范围纠正及推进

- 默认pytest原先未收集app/db，先前2993不覆盖新增db回归；已将app/db纳入且添加收集守护，12项定向/负控制通过。新默认全量运行于`logs/backend-stage12-frozen-20260907T160529164332+0800.log`。
- UTC严格R4证据为`logs/stage12-timezone-app-verify-r4/run-20260907T160248-6906b2d3/result.json`；实际迁移首DDL同连接UTC和归一化DATETIME相等已验证，早期R1读回间接证据由此补齐。
- MySQL迁移库before_tool/during_tool真实强杀通过：`logs/stage12-crash-mysql-20260907T161300-487d80f9/result.json`；没有覆盖其他故障窗口。
- S12-05原生全87表mysqldump恢复、121 FK anti-join、trigger拒绝语义验证通过：`logs/stage12-quality-full-restore-20260907T162536-3b787790/final-summary.json`。Docker daemon及实际deploy/rollback仍独立待验。
- 当前详情以`docs/reports/STAGE12_RUNTIME_AND_GATE_20260907.md`为准；旧完成表述不替代新覆盖范围。

## 默认完整门禁收口（2026-09-07 16:43 +08:00）

已纳入app/db并完成默认原始后端全量：3005通过，637代码/配置与2749既有资产无漂移，`logs/backend-stage12-frozen-20260907T160529164332+0800.result.json`。S12-03完整门禁完成；S12-04已验SQLite/MySQL工具前/中强杀；S12-05原生87表全库恢复完成，但Docker发布和其他崩溃窗口仍待。S12-06真实后端浏览器与七项文学收益仍未完成。整体保持active/NO-GO。

## 下一轮优先事项（本轮收口后）

1. 修复部署示例入口与备份/迁移编排不一致；默认口令/healthcheck插值不一致；原生备份与rollback manifest契约。按只读报告F04/F06/F07建立回归及反向后实施，保留旧产物。
2. S12-06搭建真实后端+独立worker+浏览器工作台流程；既有SSE受控HTTP2项不代表该链通过。
3. 继续MySQL失败事务提交前/后强杀和历史孤儿恢复；两工具点强杀已有证据，不重复盘点。
4. Docker daemon/env实际条件补齐后独立跑部署矩阵；不要反复仅轮询缺失daemon而不推进其他工作。
5. 文学质量从证据采集推进而非反复重算旧空标签；AI评审字段来源独立，严禁冒充human真值。

当前门禁：后端3005、前端634/type-check/build均通过。详见`docs/reports/STAGE12_RUNTIME_AND_GATE_20260907.md`。
