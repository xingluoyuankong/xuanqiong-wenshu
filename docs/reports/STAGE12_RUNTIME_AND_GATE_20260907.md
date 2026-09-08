# 阶段十二增量实现、验证范围与接续

## 当前状态

阶段十二数据库UTC策略与SQLite强杀恢复已有实测证据；**包含数据库回归的默认后端门禁已3005通过**。总目标active，发布NO-GO；七项文学质量缺口保持未完成。

最终门禁：`logs/backend-stage12-frozen-20260907T160529164332+0800.result.json`，3005 passed / 2283.95s / exit0 / valid_gate=true，session57700已结束。冻结637代码/配置、2749既有资产且前后无漂移。新增`app/db`默认收集目录，保留原agent/services/routers全部范围。

### 门禁证据更正

`logs/backend-stage11-frozen-20260907T153311499845+0800.result.json`确为2993通过/exit0/无漂移；但当时pytest.ini不包含app/db，故没有收集新增UTC回归和既有数据库初始化回归。它是原默认范围通过，不是数据库新增回归已纳入默认全量的证明。

已扩展testpaths，新增`backend/app/services/test_database_gate_collection.py`防止未来再次遗漏；定向12通过。进程内删除app/db配置后该回归真实失败。旧结果与`logs/stage12-final-delivery-manifest.json`保留为历史，后者的“final”命名不代表最终范围完整；本报告及随后新完整门禁覆盖其宽泛表述。

## S12-03：连接级 UTC

新增`backend/app/db/mysql_timezone.py`，在连接创建及每次连接池借出时执行`SET SESSION time_zone = '+00:00'`，仅MySQL启用，重复注册幂等，游标finally关闭，初始化失败向调用者传播。

接入三个engine：

- `backend/app/db/session.py`应用连接池。
- `backend/alembic/env.py`真实迁移engine。
- `backend/app/db/init_db.py`首次建库admin engine。

数据库全局时区不变。新实例1914/PID28424维持global+08，旧40344/PID27272维持UTC。第二实例新建datadir，无复制/删除旧目录。

### 单测与反向

- `backend/app/db/test_mysql_timezone_policy.py`：6项，包含生产session语句、迁移接线、首次建库接线、SQLite跳过、注册幂等、失败拒借出及游标清理。
- app/db现有初始化5项及收集目录守护1项一并定向运行：`logs/stage12-db-gate-collection-green3.log`，12 passed。
- 负向`logs/stage12-negative-policy_removed.json`：取消策略，4个AssertionError及1个未抛期望异常检出；没有collection error。
- 负向`logs/stage12-negative-db_tests_excluded.json`：删去默认db收集目录，回归失败；全程进程内变异，源文件不改。

### 真实非UTC实例验收

权威R4：`logs/stage12-timezone-app-verify-r4/run-20260907T160248-6906b2d3/result.json`，4/4通过，源码无漂移。

1. 生产app.db.session首连UTC，同一个connection_id污染为-05归还后恢复UTC；8并发、新连接、invalidate、dispose后重建均UTC。
2. 移除listeners负控制：物理新连接继承+08，污染复用保持-05；重新安装策略后恢复UTC。
3. 实际Alembic子进程PID3804、连接76：首条DDL执行前观测session+00/global+08/端口1914。共记录335个DDL事件，真实upgrade head成功。不是迁移后用另一个app连接读回代替迁移连接观测。
4. TIMESTAMP在原生+08连接读取与UTC应用相差28800秒；DATETIME开始/结束归一化后两端相等，started<=finished，严格断言通过。

首轮R1有跨event-loop清理告警与datetime/string错误比较字段，R2/R3有验收脚本失败；均保留，不只用报告解释代替测试修正。R4单event loop管理engine，干净退出且数值断言为真。

## S12-04：执行前与执行中强杀

权威：`logs/stage12-crash-recovery-live-20260907T152245-5752a26b/result.json`，cases中的两个场景passed，源码和既有资产无漂移。

- 在真实continuation_worker调用read之前，父进程TerminateProcess实际Python进程；工具未执行，重启后执行一次read。
- 在真实statistics.project已完成章节SELECT后、结果返回前强杀；重启再次执行read，明确至少一次语义，不声称exactly-once。
- 两场景job/step代次1→2，候选文件/冻结plan/context/capability不变，原writer不重跑，不新增正文版本；重复worker无新增工具执行。
- 只在新隔离SQLite中修改lease_expires_at模拟租约时间流逝，未改status/generation/attempt/结果；不能据此声称已经实等完整租约周期。
- 负向是对验收器输入的未恢复快照、重复候选注入检查，不是生产源码变异；与UTC源代码负控制分开记录。

原阶段九原子提交脚本本轮重新执行，parent自动写logs/stage9-*、不使用--work参数。最早本轮结果为`logs/stage9-atomic-process-before_commit-20260907T140834-7eb60523/result.json`10检查通过及`logs/stage9-atomic-process-after_commit-20260907T140852-5687f15c/result.json`11检查通过；后一次before_commit结果`logs/stage9-atomic-process-before_commit-20260907T151125-de46e8d8/result.json`10检查通过。外层两个stage12日志目录没有result并非执行失败，而是parent输出目录固定策略；不再重复执行制造同一证据。

MySQL真实迁移库执行中强杀、网络分区/故障切换仍待完成。

## 种子字节一致性

本轮app/db定向发现`backend/prompts/writing_v2.md`为70个CRLF/130个LF，种子为130个CRLF/130个LF；文字归一化后完全相同，但精确字节断言失败。将种子与当前源逐字节同步后两者SHA256均为`d0dc175c322738f394bed0142c5b2bb9b6b829f7c606754a6b0a94fa3154ffda`，测试恢复通过。没有覆盖数据库中管理员自定义prompt，也未调整测试断言。Git换行转换可能影响后续checkout，当前修改不宣称彻底解决所有平台换行策略。

## S12-07：文学质量审计而非达标

`docs/reports/STAGE12_LITERARY_S12-07_20260907.md`和补充验证说明：29项通过、7/7内存变异检出；completion_eligible=false，7项hard gap不变。未调用Provider、未填写human字段。4份CSV37行含重复模板，唯一原始样本基础19+T18六项；没有把37行当37个独立真值。

## 后续顺序

1. 当前包含app/db的新默认全量完成后校验完整结果、hash与节点范围。
2. 实际迁移库026触发器合法/非法INSERT/UPDATE及迁移重入、备份恢复验收（独立子智能体仅新库/logs）。
3. MySQL进程强杀恢复和真实后端+浏览器审批工作台闭环。
4. Docker daemon可用后另行执行compose发布/回滚矩阵，不改旧卷。
5. 七项文学质量缺口按`docs/reports/STAGE12_EXECUTION_PLAN_20260907.md`继续，AI评分不替代人工真值。

## S12-04追加：MySQL迁移库真实强杀（2026-09-07 16:16 +08:00）

`logs/stage12-crash-mysql-20260907T161300-487d80f9/result.json`：两个新随机库均真实Alembic升级至030，87表/2触发器，生产app.db.session、UTC和REPEATABLE-READ。工具执行前及执行中父进程强杀实际worker，重启后Job succeeded/Step completed/Fact completed，generation 1→2，Run paused候选待用户处理。原writer与候选未重复，正文版本未新增，repeat零工具调用。

工具执行前实际worker PID35220、恢复40596；工具执行中26172、恢复45292；强杀退出91，恢复与repeat退出0。read分别0+1与1+1；仍为至少一次语义。仅调整新库lease_expires_at模拟时间流逝，不改状态和代次。637代码/配置、2749既有资产无漂移。

MySQL提交中/提交后失败事务强退出、自然租约完整等待、网络/服务器故障切换仍未由这两个场景证明，不以覆盖两个工具点代替所有崩溃窗口。

## S12-05追加：迁移约束与全库备份恢复

1. `logs/stage12-quality-constraints-20260907T161112-06eb895d/result.json`：真实升级、同Run合法INSERT/UPDATE、NULL artifact合法路径、crossRun INSERT/改artifact/改run均触发MySQL1644；重复upgrade零DDL，schema/data hash不变。初次恢复触发器重名1359，失败原样保留。
2. `logs/stage12-quality-constraints-20260907T161439-d15c85a8/result.json`：六表data+trigger恢复通过，只是局部成功，不作为全库结果。
3. **全库权威**：`logs/stage12-quality-full-restore-20260907T162536-3b787790/final-summary.json`及`result.json`。原生mysqldump全部87表、2trigger、revision，恢复到经过不存在/空库验证的全新目标，未先跑Alembic，未覆盖任何旧库。dump/restore均exit0。
4. 1086列定义、全部87表行数/逐行hash多重集、trigger正文/SQL mode/DEFINER等一致；42条数据、15张有数据表，空表未排除。121个FK含复合键完整NOT EXISTS检查，孤儿0。
5. 导入仅在新目标会话临时关闭FK，结束重新开启并验证；独立连接FK=1。合法与非法触发器探针均在恢复后运行并rollback，源/目标业务快照保持不变。
6. 首次schema文本比较因SHOW CREATE多显式CHARACTER SET子句失败，未改成盲目忽略：先严格比较1086列实际字符集/collation元数据，再去除冗余文本。原始失败与新规范化结果各自保留。

这证明隔离完整小库备份恢复，不证明生产规模、跨版本、跨主机DEFINER迁移或Docker脚本全链路；后续仍按完整产品要求继续。

## 最终默认后端门禁（2026-09-07 16:43 +08:00）

3005 passed / 2283.95s，exit0；原始pytest-q完整执行，默认收集范围agent/services/routers/db均保留。新增12项（6时区+5既有db初始化+1收集守护）已计入默认全量，不再以定向代替。637源码/配置与2749既有资产无漂移。

证据：`logs/backend-stage12-frozen-20260907T160529164332+0800.result.json`。此前2993记录继续保留为旧收集范围，不拼接数字。前端三门禁正在当前源码重新运行。

## 当前前端与部署最终复核（2026-09-07 17:00 +08:00）

- 当前前端重新执行type-check、test:run、build-only均exit0；83测试文件/634项通过，114个构建产物，业务源码前后hash一致。证据`logs/stage12-frontend-final-gates-summary-20260907-164721.json`，不是复用旧门禁冒充本轮。
- Docker只读报告`logs/stage12-docker-deploy-readonly-20260907-165353/result.json`：client/Compose可用，desktop-linux daemon命名管道缺失；真实deploy/.env缺失、原始config失败。哨兵SQLite/maintenance/internal/external MySQL等五分支解析通过，仅是配置层证据。
- 静态新增待办：deploy/.env.example直启命令未走显式备份/migrate编排；内置MySQL默认口令、app MYSQL_PASSWORD与healthcheck插值不一致；原生迁移脚本与Docker rollback备份manifest契约不同。均未改源码、未启动容器，后续需先红测再修复而非仅修改报告。
- 容器实际时区、镜像、健康、卷、deploy/rollback运行链仍未验。原生MySQL完整备份恢复不代替Docker。

总体：后端3005+前端634完整当前门禁通过；UTC、SQLite/MySQL工具点强杀、原生迁移约束/全库恢复已有证据。目标继续active/NO-GO，剩余是其他故障窗口、实际后端+浏览器、部署配置与Docker运行、真实文学证据。
