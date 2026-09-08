# 阶段十三真实工作台、部署契约与门禁报告

更新：2026-09-07 18:20 +08:00。整体active/NO-GO。

<!-- STAGE13_CURRENT_BEGIN -->
## 阶段十三当前状态（2026-09-07 18:20 +08:00）

原任务“全面优化重构玄穹文枢”在本任务接续，使用子智能体，不创建新任务。总目标 **active / 发布 NO-GO**。此块覆盖下方全部历史“当前/最终”措辞；历史证据保留。

- **后端完整全量3039 passed / 1885.49s / exit0 / valid_gate=true**，18:08结束；638 backend代码/配置输入与2754既有资产无漂移。证据`logs/backend-stage12-frozen-20260907T173645289117+0800.result.json`。文件名前缀沿用stage12，实际覆盖阶段十三部署34项新增测试；部署文件另有历史完成hash与当前采样对照，不声称runner冻结了deploy。
- **前端83文件/643 passed，type-check/build-only exit0**。进度语义修复33项定向、6项真实红测失败、5/5有效ESM变异检出；初次.ts loader错误未计检出。证据`logs/stage13-progress-fix-20260907-174805/closeout.json`。
- **R4真实产品链浏览器1 passed / 24.4s**，独立API/auth/Alembic/DB/worker/审批/候选/continuation；候选1、正文版本0、revision1。当前进度截图和断言已确认candidate_ready，无旧审批60%，无虚设100%。证据`logs/stage13-real-workspace-20260907T181723-71478590/workflow-evidence.json`。
- R3首次加载在5秒默认可见性断言处失败，auth/current-user为200、pageerrors为空、尚未创建Run；日志/trace/视频保留。R4新库原样5秒断言通过，没有提高超时或删除断言。冷启动时序只是当前假设，未宣称根因已确定。
- 上述生成端是受控Planner/writer，**不代表商业Provider或文学收益通过**。截图另见候选预览/浅色正文可读性疑点，Hubble调查真实DOM/CSS，不把toContainText通过当视觉合格。
- 部署F04/F07定向129通过、8反向；命令历史3通过、恢复UUID错误排序反向1失败且源码不变。F06已确认原生dump缺sidecar及自包含数据库SQL格式，Hume开始独立红绿修复。**F06新增实现后3039仅是之前源码版本门禁，必须新全量。**
- Copernicus正在新增MySQL事务提交边界强杀验收，仅新logs/新库，不修改生产源码。Docker运行、七项文学hard gap仍待；completion_eligible=false。

完整计划：`docs/reports/STAGE13_EXECUTION_PLAN_20260907.md`；本轮实测报告：`docs/reports/STAGE13_RUNTIME_AND_GATE_20260907.md`。
<!-- STAGE13_CURRENT_END -->

## 证据→发现→执行

| 证据 | 发现 | 已实施/下一步 |
|---|---|---|
| command-history-red.log与frontend/audit/stage13-command-order/result.json | 同秒UUID排序覆盖服务端durable顺序 | 保留tie稳定顺序；3绿与反向真实检出 |
| R2截图和progress-fix真实23事件replay | 旧progress_update压过候选语义 | 独立语义sequence，原子替换message/phase/action/progress，跨Run保护 |
| R4 workflow-evidence与current-progress-verified.png | 候选已生成、worker续跑成功、进度更新 | 继续可读性验收及真实Provider链；不编造文学收益 |
| stage13-f06-contract-audit/report.md | 原生dump与rollback输入契约不兼容 | 新独立回归+最小producer修复；停写编排仍独立未完成 |

## 失败记录与覆盖限制

R1验收选错折叠面板；R2产品链通过但遗漏当前进度断言；R3尚未进入工作台就初始加载超时；R4保留原工作台5秒可见性断言与新增进度断言，在新库通过。各轮不是同一库重跑，既有结果未覆盖。

前端门禁是开发测试与生产build，Playwright本轮使用Vite dev服务；不能将其写为Docker生产部署验收。R4截图有文字可读性疑点，因此业务通过不等于视觉全通过。数据库预览文本断言不等同于屏幕可读性。

后端runner只记录backend输入；deploy/.env.example、docker-compose.yml的历史完成hash与18:20采样一致，仅证明两个观测点一致，不声称全程监控。F06正在修改另一个部署脚本与新test，须按新源码再跑门禁。


## 18:45进一步实测（覆盖18:20待办状态）

### S13-06原生备份契约

Hume已完成新61项测试（含10种隔离副本变异），57项原始红测失败/4通过，新实现61通过。源码/tests在18:41:12冻结，默认收集3100项（收集数字非通过数字）。三清单、唯一文件、私密umask、完整dump参数、失败阻止迁移、原生生产者到未修改rollback消费契约均覆盖；Docker客户端依赖为替身，不计实际Docker运行。

主代理真实native验收`logs/stage13-native-live/run-20260907T183743-139f8bbc/result.json`通过：真实mysql/mysqldump/Alembic，先备份一表再升级88表，恢复仅新库后只余原sentinel；中文/二进制精确保持、全部后增表移除。另在新库继续验证“已经完整迁移的88表包”恢复，当前运行中，不能预报通过。

### S13-07 MySQL读完成事务边界

`logs/stage13-mysql-transaction-crash/run-20260907T182635-3fb73d85/delivery-summary.json`：真实强杀提交前/后两正向通过、遗漏fact完成操作的进程内变异检出。前：未提交行对独立连接不可见，恢复Job/step代次1→2，read重跑一次；后：commit返回但JobACK之前强杀，恢复Job代次1→2但step保持1，read零重跑。各repeat两次全快照保持。真实迁移三新库均87表、2trigger、head030；旧库未改、秘密匹配0、140原始证据hash一致。lease expiry是时间模拟，不是等待租约自然到期，不外推所有事务/网络故障。

### S13-10可读性

R4候选PRE实际上含完整正文。trace DOM/CSS部分静态重建确认：全局浅色背景!important覆盖ink背景而保留白色前景，PRE/DD白字；消息grid配页面52vh最小高度将短气泡拉高374px。不是字体或动画；Hubble获准只改Conversation/Workspace与其spec四文件，正在红绿修复。新真实浏览器会增加颜色、容器及气泡高度断言，再查截图，不仅检查textContent。

### 新门禁

`logs/backend-stage13-frozen-20260907T184118001760+0800.log`正在完整运行，648 backend/部署代码输入和2755既有资产；此前3039不覆盖新增61项。本次runner新增部署输入指纹但仍不包含私有.env。runner独立3项harness通过、正确模块绑定的反向R2 2失败/1通过；初始R1绑定错误模块的证据保留且不作为有效核验。


## 19:04 R5/R6与新初始化竞态

UI修复源码后的三门禁649通过，type/build exit0；这不是新的实际浏览器全链路通过。R5初始工作台可见性5秒失败，R6初始页面通过但在会话建立前点击发送：POST/api/agent/plan后才GET/create sessions，未发POST messages。submitMessage原来将runtimeSupported且session=null误当compat，且先清空goal。Hubble正在以延迟初始化红测修复，不通过改验收等待session绕过产品缺陷。旧R4只是进度修复版本通过；前端改动后未外推其结论。

F06完整已迁移88表包已实际恢复通过，详见`logs/stage13-native-live/run-20260907T184417-e9677d71/REPORT.md`；默认3100收集不等于新的全量完成。后端新全量仍运行中。


## 20:03 preview验收

R8使用已构建frontend/dist的Vite preview，而非dev服务器；真实backend、JWT、数据库、HTTP、独立worker、SSE/UI仍执行。source/frontend dist hash前后未漂移。R8 `runner-result.json` valid_acceptance=true；preaccept versions=0/artifacts=1/revision=1，postaccept versions=1且正文一致，重复accept同version，DOM PRE/DD颜色均rgb(68,64,60)，消息列表和气泡约71.86px，pageerrors空，`/api/agent/plan` POST计数为0。该生成端仍是controlled fixture，不是商业Provider。

最终后端阶段十三冻结runner仍未结束；其当前目标是覆盖新增native fixture路径回归并核对backend/deploy输入和既有资产无漂移。结束前不宣称发布门禁通过。


## 20:26最终工程门禁

最终后端冻结runner自然结束：3103 passed，exit0，648输入与2760既有资产前后hash一致。最终前端type/test/build已是会话就绪修复后的654测试。R8使用dist preview而非dev，source/dist验收过程无漂移。工程链通过不等于生产发布：Docker无实际daemon/矩阵，Provider为controlled fixture，文学completion_eligible仍false。


## 20:47最终收口

阶段十三工程门禁现已闭环：后端3103无漂移、前端654/type/build、R8构建preview工作台、真实native MySQL完整备份恢复、MySQL两个提交边界。Docker预检不是运行通过：daemon命名管道与真实deploy/.env缺失。文学审查不是质量通过：7 hard gap和completion_eligible=false保持。当前总目标active、发布NO-GO。


## 20:56文学输入契约

阶段十三文学支线没有调用Provider、生成新样本、改标签、改正文或改数据库。25项冻结双盲审阅包验证通过，所有human列、reviewer身份和仲裁行为空；4种隔离变异全部检出且原包恢复。它是后续人工审阅的输入工件，不是质量结果。
