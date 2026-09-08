# 阶段十三执行计划与接续验收

更新：2026-09-07 18:42 +08:00。目标active，发布NO-GO。保留历史未提交改动和全部运行资产。

## 当前任务表（2026-09-07 18:42 +08:00）

| ID | 工作 | 当前状态 | 下一验收 |
|---|---|---|---|
| S13-01 | 部署F04/F07入口/口令/healthcheck | 129定向、8反向、3039旧基线完整通过 | Docker实际运行待条件 |
| S13-02 | 同秒命令历史稳定排序 | 3绿/1红与反向通过，643全量覆盖 | 和UI修复统一复验 |
| S13-03 | 真实工作台批准/执行/worker续跑 | R4实际浏览器通过，进度candidate_ready | 新R5增加DOM颜色/短消息布局断言 |
| S13-04 | 当前进度旧审批残留 | 修复完成，33定向、5反向、643/type/build及R4通过 | 保持回归 |
| S13-05 | 后端原始全量 | F06前3039通过；18:41新全量运行 | 648代码/部署输入、2755既有资产；读取实际结果 |
| S13-06 | 原生备份manifest/SQL格式 | 61回归绿；真实MySQL生产脚本迁移/恢复通过 | 收组合与反向详细结果、新全量；原生停写编排独立待 |
| S13-07 | MySQL read完成提交前后强杀 | 2正向+1实际变异检出，三库真实迁移87表/2trigger | 其他事务/JobACK/网络边界独立待 |
| S13-08 | Docker真实部署 | daemon/env条件未补齐 | 条件变化再跑，不把native验收充作Docker |
| S13-09 | Provider/文学收益 | 七项hard gap保留 | 实际来源/cohort/人工真值采集 |
| S13-10 | 白字浅色背景/短消息巨大空白 | 51定向/7有效反向、649/type/build通过 | R5初始加载失败，R6发现独立会话竞态，视觉业务链待重验 |
| S13-11 | 初始化前发送误走compat plan并丢失草稿 | R6真实复现，Hubble正在红绿修复 | 保留runtimeUnsupported兼容；runtimeSupported必须会话就绪，保留草稿 |

## 并行边界

主代理：门禁、真实浏览器、命令排序反向、文档与证据整合。Hubble：event reducer及相关spec、必要Conversation文件。Hume：F06只读证据，仅logs目录；后端全量冻结期间不改backend/deploy。子智能体可在明确不重叠写集内继续委派，不创建用户新任务。

## 证据→发现→执行路径

1. R2 workflow-evidence表明产品持久化正确，但截图当前进度仍为awaiting_approval/60%。路径：以事件语义序列更新完整状态元组，添加实际浏览器断言，不直接删掉进度显示掩盖问题。
2. 同秒命令逆序UUID红测真实失败。路径：保留后端tie顺序，内存恢复旧比较器再次失败，磁盘源码不变。
3. 部署入口34新增+95既有定向通过。路径：扩大原始全量，独立验证Compose部署文件指纹，Docker运行与静态/模拟shell测试分开报告。
4. 文学hard gap为证据不足而非通过率不足。路径：采集真实来源和对照，不重复统计空标签、不同cohort或受控短文为质量提升。

## 继续动作

先收回Hubble修复证据并复核diff；新建隔离SQLite/随机端口运行R3（不复用R2库），同时等待后端冻结全量自然结束；前端三门禁收口。随后更新本表与四个接续入口，进入F06实现和MySQL下一故障窗口。任何失败保留原日志、fixture和快照；修复后用新目录重跑。


## 18:20执行更新（覆盖上表旧状态）

S13-01/S13-05：原始后端3039全量通过；S13-02/S13-04：前端643/type/build完成，进度5反向检出。S13-03：R4实际浏览器1通过且当前进度candidate_ready；R3初始加载失败保留。新增S13-10：真实截图文字可读性调查，由Hubble负责，先测DOM/CSS再修。

S13-06：Hume进入run_migrations.sh+新test_native_backup_manifest_contract.py独立修复；不要触碰rollback/deploy_docker旧成果。S13-07：Copernicus仅新增logs验收脚本与新MySQL库，推进事务提交边界。主代理继续报告、真实验收和集成，源码稳定后重新门禁。后续Provider/文学证据与Docker条件仍维持独立阻塞项，不停止其他可执行工作。


## 18:42执行与接续句柄

新完整后端门禁：`logs/backend-stage13-frozen-20260907T184118001760+0800.log`，session98322，未出终态前保持backend/deploy冻结。runner现纳入非秘密部署输入；独立harness 3绿、2红，进程内恢复遗漏deploy导致2失败。首轮反向绑定了错误模块，保留R1，R2正确绑定fixture模块后仍真实检出，以negative-r2为准。

真实native证据：`logs/stage13-native-live/run-20260907T183743-139f8bbc/result.json`，参阅REPORT.md。MySQL提交边界证据：`logs/stage13-mysql-transaction-crash/run-20260907T182635-3fb73d85/delivery-summary.json`，仅read completion两个窗口，lease expiry为时间模拟。Copernicus已完成并关闭。

Hubble独占Conversation.vue/spec与Workspace.vue/spec；完成后主代理运行`logs/run_stage13_workspace_acceptance.py`，每轮新库新目录，捕获真实退出码与frontend/src/验收脚本前后hash；不复用旧库覆盖证据。Hume仅做收口证据与测试，不再改当前全量输入。


## 19:04新发现与当前真实边界

- F06已迁移完整88表包也完成真实恢复：`logs/stage13-native-live/run-20260907T184417-e9677d71/result.json`，155141字节、2trigger、revision030、sentinel与二进制保持、后增marker消失；不代表全业务行数据/121FK复验。
- UI可读性修复三门禁649/type/build通过，build18:56:36完成。7有效反向中3项初次CRLF锚点失败不计，normalized重跑实际注入并检出。源码四文件冻结曾覆盖R5/R6。
- R5在初始工作台5秒限时失败，未进业务；R6初始页面通过、真正点击发送，但走了/api/agent/plan，随后才初始化session，120秒等待messages超时。这是新的产品竞态，不归为冷加载，也不通过在验收里等session掩盖。`logs/stage13-bootstrap-race-observed.json`是紧凑请求证据。
- Hubble正在修S13-11，仍使用四文件/必要session lifecycle受控写集；修复后新的前端三门禁及dev真实浏览器再跑。主代理已准备独立preview模式和可选--accept分支，仍保留preaccept versions0及所有业务断言，未执行preview/accept前不宣称通过。
- 新后端全量session98322继续运行，backend/deploy冻结；主代理不暂停/重启正常门禁，不覆盖原日志。内存约剩1GB时不再增开重型并行工作或新子代理。


## 20:03阶段门禁更新

- R7开发服务真实验收与R8构建产物preview真实验收均通过：两轮均覆盖消息会话、候选生成、进度语义、非白字DOM、短消息布局、质量读取、接受版本、重复接受幂等和刷新后的100%终态；R8目录为`logs/stage13-real-workspace-20260907T195925-c6d74764`，source hash无漂移。
- 19:57启动的最终阶段十三后端冻结门禁仍运行中；本轮初始快照648输入/2760既有资产，已修复测试夹具进入该门禁，必须等完整终态。之前失败的旧门禁结果保留，不能用R7/R8替代后端全量。
- F06真实完整88表备份恢复、S13-07两个MySQL提交边界已闭环；Docker实机、原生停写编排、全部MySQL故障矩阵和文学七项hard gap仍是独立未完成。
- 用户要求持续优化：门禁结束后只修当前失败，先红后绿与反向，再重新冻结；每轮更新本计划及四个接续入口，保留所有失败目录。


## 20:26阶段十三工程门禁收口

S13-05最终3103项全量通过，648输入/2760资产无漂移；S13-04前端654/类型/构建通过，R7 dev与R8 preview完整工作台通过。F06真实88表包恢复、S13-07两个MySQL提交边界已证实。阶段十三工程门禁闭环，但发布继续NO-GO。

下一轮并行只处理未闭合证据：Docker只读前置、文学hard gap证据契约；生产源码保持稳定。任何后续实现都需新写集、红绿/反向、再跑相应全量，不得把当前3103/654外推到未来源码。


## 20:47最终阶段十三状态

S13-05、S13-06、S13-07、S13-10、S13-11和R7/R8已闭环，工程门禁为3103/654/type/build通过。S13-08 Docker只读预检已收口：P0 Engine不可达、P1真实deploy/.env缺失，等待外部环境条件变化，不重复扫描。S13-09文学只读审查已收口：7 hard gap保留，下一批按25个既有去重样本双人盲审优先，不调用Provider、不填标签。

当前继续动作：保留所有工程证据与失败证据；有Docker条件变化时重新从preflight→基线→单一矩阵执行；有人类审阅输入后按冻结manifest/hash/双审/仲裁契约采集文学真值。未满足前保持active/NO-GO，不将工程绿灯写成产品发布。


## 20:56文学审阅包已冻结

已生成`logs/stage13-literary-review-packet-20260907/`：25个既有去重样本（general19/T18 6）、A/B各25行空白表、空仲裁表、README和验证器。主代理验证`valid=true`，packet hash `a3b10ef55d91448c703a583b1baf516f26daf8b06d9e1c69d6620837ef884b94`；R2反向审计删除行、改绑定hash、预填human列、改manifest数量均检出且原包恢复。此包只准备人工输入，不含任何人工真值，completion_eligible仍false。
