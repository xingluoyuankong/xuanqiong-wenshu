# 玄穹文枢：领域 D 业务功能生产级审查与验收计划

> 范围：研究资料/文献收集、文风提取、灵感/蓝图、人物/势力/线索/知识图谱、项目管理、导入导出、版本/评审、模型提示词配置、管理台权限，以及这些能力与小说生成之间的数据闭环。
>
> 本轮只审查、登记风险、制定重构与验收方案，不修改业务代码；当前工作区的已有未提交改动全部保留。

## 1. 审查基线与证据等级

### 1.1 已确认的工程事实

- 后端为 FastAPI + SQLAlchemy AsyncSession，前端为 Vue + TypeScript，数据库兼容 SQLite/MySQL。
- 领域 D 主要后端入口：`backend/app/api/routers/novels.py`、`research.py`、`style.py`、`projects.py`、`clue_tracker.py`、`knowledge_graph.py`、`review.py`、`llm_config.py`、`admin.py`、`writing_skills.py`、`foreshadowing.py`。
- 主要前端入口：`frontend/src/api/novel-client.ts`、`llm.ts`、`admin.ts`、`views/InspirationMode.vue`、`views/StyleCenterView.vue`、`components/novel-detail/ResearchCenterSection.vue`、`clue-tracker/ClueTrackerView.vue`、`knowledge-graph/KnowledgeGraphView.vue` 和 `components/admin/*`。
- `TaskRuntime`、SSE、租约、心跳、取消和部分重启恢复已经存在，但业务模块仍保留各自的内存任务映射、旧状态字段和兼容入口，尚不能默认视为单一真相源。
- Alembic 当前存在 `000_initial_schema` 至 `003_schema_compatibility`；同时存在历史 SQL 脚本，必须以隔离库实跑迁移结果为准。
- TXT 导出包含机读头和回程元数据；DOCX 当前主要是阅读版正文，不能默认等价于完整工程备份。

### 1.2 证据等级

| 等级 | 证据定义 |
|---|---|
| E0 | 发现了代码、类型或路由，未证明可用 |
| E1 | 有单元/路由测试，但未证明重启、权限、并发或真实 Provider |
| E2 | 隔离 ASGI + SQLite 真实 HTTP 入口通过 |
| E3 | 真实 Provider、重启、断线、双项目隔离、往返和审计证据完整通过 |

本轮不把任何功能直接标为 E3。测试绿色只代表局部证据，不代表生产就绪。

## 2. 领域 D 功能树与统一逻辑链

```text
领域 D：业务资料与生产工作台
├─ A 项目管理与创作资产
│  ├─ 项目创建/列表/详情/删除
│  ├─ 灵感对话与蓝图
│  ├─ 总纲/章节纲/分卷规划
│  ├─ 人物、关系、势力
│  └─ 记忆、时间线、情绪、伏笔
├─ B 研究资料/文献收集
│  ├─ 研究配置
│  ├─ 搜索来源与引用
│  ├─ 研究任务、取消、恢复
│  ├─ 摘要、归档与上下文注入
│  └─ 可信度、来源和审计
├─ C 文风提取与应用
│  ├─ 素材源与上传
│  ├─ 文风画像提取
│  ├─ 全局/项目激活
│  └─ 生成约束与版本
├─ D 线索、伏笔、人物状态与知识图谱
│  ├─ 线索/线程/红鲱鱼
│  ├─ 伏笔/回收/提醒
│  ├─ 节点/边/角色时间线
│  └─ 因果链/记忆同步
├─ E 版本、评审与 Patch/Diff
│  ├─ 版本选择/删除
│  ├─ 六维/一致性评审
│  ├─ Patch、Diff、回退
│  └─ 定稿、质量报告、审计
├─ F LLM、提示词与配置同步
│  ├─ 用户 Provider/模型配置
│  ├─ DeepSeek 健康检查/切换
│  ├─ 管理台提示词 CRUD
│  └─ 配置版本、任务快照
├─ G 导入/导出
│  ├─ TXT 导入与分章分析
│  ├─ TXT 导出与预检
│  ├─ DOCX 阅读导出
│  └─ 工程资产 manifest/sidecar
└─ H 管理台、权限、日志和技能
   ├─ JWT 登录与用户边界
   ├─ 管理员项目查看
   ├─ 运行日志/更新日志
   ├─ 系统配置/限额
   └─ 技能安装/执行
```

### 2.1 统一业务逻辑链

```text
前端操作
 → API 类型与请求校验
 → JWT 身份 + 项目 owner/admin 权限
 → 幂等键、项目锁/租约
 → TaskRuntime（任务）或事务服务（即时 CRUD）
 → 领域模型、产物、事件持久化
 → 配置/提示词/上下文快照
 → 研究、文风、人物、线索、图谱、评审进入生成上下文
 → SSE/轮询返回阶段、日志、正文或产物
 → 前端合并状态并提供终态动作
 → TXT/DOCX 导出或再次导入
 → 隔离库、审计、hash、耗时和质量证据
```

### 2.2 统一任务状态链

```text
queued → running → cancelling → cancelled
                     ├────────→ succeeded
                     ├────────→ failed
重启扫描：queued/running + 无有效租约 → stale → resume/retry/fail
```

旧模块的 `successful`、`generating`、`interrupted` 等只能做兼容展示。终态不可复活，迟到回调必须被 `lease_owner + attempt + event_cursor` 拒绝。

## 3. 所有功能共同验收门禁

每个功能必须同时满足：

1. 成功、空值、越界、错误枚举、重复提交、跨项目 ID、Provider 失败均有结构化响应。
2. 未登录返回 401；非所有者返回 403/404；管理员行为可审计；路径参数替换不能跨项目读写。
3. 运行中杀进程后能查询到明确状态；可恢复任务从 checkpoint 继续，不可恢复任务转 `stale/failed` 并提供重试。
4. 相同幂等键不创建重复任务；项目 A/B 并发时事件、缓存、文件、产物、配置和正文完全隔离。
5. 任务冻结 `config_version`、model、prompt revision、参数摘要和上下文快照；运行中配置变更不影响旧任务。
6. TXT/DOCX 明确覆盖范围；不支持项进入 `warnings[]`，不得静默丢失。
7. 每项新增修复有回归测试，并做反向验证：故意去掉 owner guard/checkpoint/游标后测试必须失败。

### 3.1 统一隔离入口验收资产

使用独立数据库 `backend/storage/acceptance-d-<run>.db`，创建用户 1/2、项目 A/B 和互异资产；真实调用前端实际使用的 HTTP 路由。记录脱敏的 request、response、run_id/task_id、event_cursor、数据库行数、产物 hash、耗时和错误码。

固定动作：

```text
登录 → 创建 A/B → 写入资产 → 启动任务 → SSE/轮询 → 取消/断线 → 杀进程 → 重启 → 恢复/失败
→ 导出 TXT/DOCX → 隔离库导入 → 对比 manifest/hash/顺序/外键 → 权限负测
```

## 4. A：项目管理、灵感与蓝图

### 4.1 当前现状与前后端链路

- 路由：`/api/novels` 创建、列表、详情、删除；`/{project_id}/concept/converse`；`blueprint/generate/start|status|cancel|save`；旧同步 `/blueprint/generate` 仍存在。
- 前端：`NovelAPI`、`InspirationMode.vue`、`BlueprintConfirmation.vue`、`BlueprintDisplay.vue`、`NovelOutlineSection.vue`、`ChapterOutlineSection.vue`。
- 链路：`Inspiration/Blueprint UI → novels.py → NovelService/blueprint generator → NovelProject/N​​ovelBlueprint/BlueprintCharacter/BlueprintRelationship/ChapterOutline → BlueprintGenerationJob + TaskRuntimeEvent → save/patch → 生成上下文`。

### 4.2 数据模型、恢复与权限

- 核心模型：`NovelProject`、`NovelBlueprint`、`BlueprintCharacter`、`BlueprintRelationship`、`ChapterOutline`、`BlueprintGenerationJob`。
- 分卷、故事弧、伏笔系统部分仍放在 `world_setting`/蓝图 JSON，查询、版本比较、局部更新和导出易漂移。
- 蓝图已有持久化 job、事件、checkpoint 和恢复逻辑，但同时存在内存活跃任务与旧 job payload；需证明重启不会重复生成或迟到覆盖。
- 项目 owner guard 主要存在；管理员读取单独走 admin 路由。必须补齐 save、patch、旧同步入口的权限矩阵。

### 4.3 优化步骤与验收

1. 固化 `BlueprintDocument v1`：书级目标、卷、篇章弧、章节依赖、角色弧、伏笔、世界规则均有 schema。
2. 概念对话产物与正式蓝图分离，状态为 `draft → validated → saved → superseded`。
3. 所有后台状态统一 `TaskRuntime`；旧同步入口只做 202/run_id 适配。
4. 按世界观、角色、弧线、分卷、章节批次写 checkpoint；保存用 `blueprint_version + base_version` 防覆盖。
5. 结构门检查章节覆盖、角色弧、冲突升级、伏笔窗口、前后章约束和长篇分卷主线。
6. 短篇 10 章和长篇 100 章均需真实生成结构；A/B 并发事件 project_id 必须 100% 匹配。
7. TXT roundtrip 比较标题、蓝图、角色、关系、卷、章节纲、伏笔计划的数量、顺序和 hash；DOCX 仅阅读版，缺失资产必须告警。

### 4.4 风险

P0：旧同步接口绕过任务协议、手工保存覆盖后台结果、JSON 蓝图不可审计。P1：长篇结构字段不足、版本冲突无提示。

## 5. B：研究资料、文献与内容收集

### 5.1 当前现状与前后端链路

- 路由：`/api/projects/{project_id}/research/config`、`/artifacts`、`/run`（兼容同步）、`/run/start`、status、cancel。
- 前端：`ResearchCenterSection.vue`、`NovelAPI`。
- 链路：`Research UI → research.py → ProjectResearchService → ResearchSearchClient → ResearchArtifact → build_prompt_context → 大纲/章节生成`。

### 5.2 数据模型、恢复与权限

- `ProjectResearchConfig` 保存 Provider、模型、域名规则、并发数和开关。
- `ResearchArtifact` 保存 run_id、project_id、user_id、scope、chapter、query_plan、sources、summary、file_manifest、provider_metadata、error。
- 已接入 TaskRuntime/heartbeat/取消/恢复，但 status 仍在内存 job、artifact、runtime 间择优，存在多真相源。
- 配置、运行、查询、取消主要有 owner guard；必须验证 run_id、artifact、文件路径不能跨项目/跨用户。

### 5.3 优化步骤与验收

1. 来源标准化为 URL、标题、发布者、发布日期、抓取时间、snippet、claim、confidence、license。
2. 查询计划、抓取结果、综合结论、引用关系拆成不可变 artifact attempt；失败不覆盖成功结果。
3. 以 query 为 checkpoint，重启只重做未完成 query；同 fingerprint 幂等，force 建立父子 attempt。
4. 任务冻结研究配置、模型、域名规则、prompt revision；事实、推断、创作建议分区。
5. URL 做 SSRF、重定向、私网、大小、超时和密钥脱敏控制；研究引用写入生成任务快照。
6. TXT 工程导出需保存 query/source/引用/版本 sidecar；DOCX 只能附研究引用附录，缺失时警告。
7. 真实验收：Provider 成功、来源失败、综合失败、取消、断线、杀进程恢复、A/B 隔离全部通过；重复调用不重复 artifact。

### 5.4 风险

P0：多真相源、来源不可追溯、恢复后重复搜索。P1：配置回读和日志泄密、研究结果版本未绑定。

## 6. C：文风提取、素材库与应用

### 6.1 当前现状与链路

- 路由：`/style/sources`、上传 start/status/cancel、`/profiles/start`/status/cancel、profile patch、`/active`、apply、extract、summary、generate；旧同步上传/画像入口仍有。
- 前端：`StyleCenterView.vue`、`WDStyleExtractModal.vue`、`OptimizerAPI`。
- 链路：`Style UI → style.py → StyleRAGService → UserStyleLibrary(JSON Text) + 临时文件 → profile → global/project active → generation context`。

### 6.2 模型、恢复与权限

- `UserStyleLibrary` 以 `style_sources_json/style_profiles_json/global_active_profile_id` 存储；缺少独立 source/profile/version 表和强外键。
- 上传/profile 已有 TaskRuntime claim、heartbeat、cancel、重建；仍有 `_STYLE_*_PROJECT_RUNS` 内存映射。
- 路由先 owner guard，但素材库以 user_id 为主，项目私有与 global 的可见性必须用真实入口证明。
- 风险：JSON 整体更新并发覆盖、文件路径和临时文件、原文隐私、激活值与任务快照不一致。

### 6.3 优化步骤与验收

1. 拆分 `StyleSource/StyleProfile/StyleApplication/StyleExtractionRun`，保存 hash、格式、字符数、授权、解析版本、owner、project scope。
2. 按文件/章节 checkpoint；画像版本原子提交；重复素材按 hash 幂等。
3. 明确优先级：任务显式 > 项目 active > 用户 global > 默认；任务保存 profile_version。
4. 文风提取只输出可迁移写作特征，不直接复制参考原文；删除画像不影响已定稿文本。
5. TXT 用 sidecar 导出画像，DOCX 只附报告；重新导入 DOCX 必须提示需要重新提取。
6. 真实流程：上传→解析→提取→预览→激活→生成→清除→刷新；断点、取消、A/B、用户 2 权限全部通过。

### 6.4 风险

P1：JSON 整体覆盖、global/project 边界、版权/隐私提示和旧同步接口阻塞。

## 7. D：人物、势力、关系、记忆与世界资产

### 7.1 当前现状与链路

- 前端：`CharactersEditorEnhanced.vue`、`RelationshipsEditor.vue`、项目详情 sections、分析工作台。
- 路由：蓝图保存/patch；`projects.py` 的 `/constitution`、`/persona`、`/memory`、`/characters/state`、`/factions`；服务包括 `NovelService`、`FactionService`、`MemoryLayerService`。
- 链路：`编辑器 → projects/novels → BlueprintCharacter/Relationship 或 Faction* → CharacterState/TimelineEvent/CausalChain → context builder → 大纲/正文/评审`。

### 7.2 数据模型、恢复与权限

- 人物和关系有独立表，但长篇属性仍大量放在 `extra`/蓝图 JSON；势力有关系、成员和历史表。
- 记忆、角色状态、时间线、因果链为独立模型；定稿自动同步属于任务链，需要 lease/outbox。
- CRUD 本身是事务操作；自动同步必须可恢复、幂等、不能回写历史章节。owner guard 需覆盖所有 ID 引用。
- 风险：同名实体、字符串引用、蓝图保存覆盖自动丰富、并发编辑丢失、实体 revision 缺失。

### 7.3 优化步骤与验收

1. 建立统一 StoryEntity/alias/stable ID；作者确认、正文抽取、AI 推断、派生数据分层。
2. 所有变更写 revision；手工编辑与自动同步冲突返回冲突，不静默覆盖。
3. 故事时间、势力变化、角色状态用结构化 event；上下文只取当前章节有效 revision。
4. TXT sidecar 往返检查实体、关系、成员、历史、状态事件、时间线和因果链；DOCX 只能附可读表格，缺失项告警。
5. A/B 真实入口验证外键 remap；项目 A ID 在 B 必须 404/409；第 N 章同步不能污染第 N-1 章。

### 7.4 风险

P1：字符串/JSON 过多、自动同步与手工编辑竞态；长篇连续生成前必须关闭。

## 8. E：线索、伏笔、线程与知识图谱

### 8.1 当前现状与链路

- 线索：`/api/projects/{project_id}/clues` CRUD、overview、threads、red-herring、unresolved、timeline、link-chapter；前端 `ClueTrackerView.vue`。
- 伏笔：`/api/projects/{project_id}/foreshadowings`、resolve、reminders、dismiss、analysis；服务 `ForeshadowingService`。
- 图谱：`/api/projects/{project_id}/knowledge-graph/*` 节点、边、overview、timeline、connected、threads、export；前端 `KnowledgeGraphView.vue`。
- 链路：`UI → route owner guard → ClueTracker/Foreshadowing/KnowledgeGraphService → facts/links/resolution/nodes/edges → ledger lease/sync → generation/review/export`。

### 8.2 数据模型、恢复与权限

- 线索：`StoryClue/ClueChapterLink/ClueThread`；伏笔：`Foreshadowing/Resolution/Reminder`；图谱：`CharacterNode/EventEdge/Metadata`。
- overview/graph 读取可能触发同步，不能把带副作用的 GET 当普通查询；并发同步必须走项目租约或后台任务。
- 路由有 owner guard 和跨项目节点/边校验；导出、timeline、link-chapter、批量 sync 需专项负测。
- 风险：多个账本重复表达、派生数据被删除后复活、analysis cache 过期不明、批量部分失败无报告、JSON export 不足。

### 8.3 优化步骤与验收

1. 建立 StoryFact/StoryEvent 与 source revision；派生图谱不能成为作者事实唯一真相。
2. sync 使用 `(project_id, source_type, source_id, source_revision)` 幂等 upsert；analysis 保存输入 revision、算法/模型版本。
3. 线索线程提供回收窗口、红鲱鱼解释、未解决原因和下章约束。
4. 图谱完整 JSON 导出，其他格式明确支持性；导入做节点 remap、边完整性、版本警告。
5. TXT sidecar 保存线索/伏笔/线程/节点/边/分析；DOCX 仅附录，缺失时显式 warning。
6. 真实流程：创建线索→链接章节→生成/同步→回收→timeline/graph→导出；重复 overview 不改变事实数量。

### 8.4 风险

P0/P1：多个账本和同步副作用、缓存不可追踪、图谱不可完整往返。

## 9. F：导入、导出与工程资产往返

### 9.1 当前现状与链路

- 导入：`POST /api/novels/import/start`、status、cancel；旧 `/import` deprecated；服务 `ImportService`。
- 导入流程：读取编码→机读头→分章→采样→角色提取→蓝图分析→项目/章节/账本/图谱写入→TaskRuntime。
- 导出：`/export/preflight`、`/export/txt`、`/export/docx`；服务 `ExportService`；TXT 使用 `novel_text_format.py`。
- TXT 包含 project、blueprint、chapter_outlines、formal_ledgers、chapter_versions 等元数据；DOCX 目前只有书名、章节标题和正文段落。

### 9.2 模型、恢复、权限与风险

- 导入临时文件按 project/run 路径校验，有恢复/取消逻辑，但内存 job 与 runtime/数据库状态共存，需防止重启重复创建。
- 导出需要 owner guard；管理员导出权限、审计和下载留存策略需明确。
- 主要风险：DOCX 无完整工程回程；TXT schema 版本仍早期；研究/文风/prompt/config/patch/评审/记忆快照可能遗漏；AI 分析失败的空蓝图降级可能被误判成功；文件大小、恶意 XML、临时文件清理不足。

### 9.3 优化步骤与验收

1. 定义 `XQ-NOVEL-EXPORT` manifest：正文、blueprint、ledgers、research、style、reviews、config provenance、checksums。
2. TXT 保持可读，完整资产放 sidecar/zip；单 TXT 明示可恢复范围。
3. DOCX 作为阅读版或附带 manifest；前端不能把 DOCX 当完整备份。
4. 导入采用解析预检→事务/outbox 写入；子资产失败生成逐项报告，不能静默返回空项目。
5. 所有源 ID 做 new ID remap；校验章节唯一键、版本选择、外键和 owner。
6. 加入 MIME/大小/编码/压缩炸弹/路径穿越/恶意 XML 防护；导入支持 dry-run、预览、新建/合并/冲突策略。

### 9.4 TXT/DOCX 往返验收标准

- TXT：导出→隔离库导入→再次导出，章节顺序/正文/标题/selected version/蓝图/角色关系/章节纲/伏笔/线索/时间线/快照/记忆/研究引用按 manifest 比对。
- DOCX：至少恢复书名、章节顺序、章节标题、正文；所有未支持资产进入 `warnings[]`。
- 负测：空章节、未定稿版本、损坏文件、UTF-8/GBK、重复章节号、外键缺失必须结构化失败。
- A 文件导入 B 后所有 ID 重新生成；用户 2 无法读取 A 的文件、任务、项目或导出。

### 9.5 风险

P0：DOCX 完整回程未实现、partial-success 语义不清、重启可能重复导入、临时文件治理不足。

## 10. G：版本、评审、Patch/Diff 与正式应用

### 10.1 当前现状与链路

- 版本/定稿/章节纲入口在 `writer.py`；评审入口为 `/api/review/six-dimension`、`/consistency`；Patch/Diff 在 `patch_diff.py`。
- 前端：`VersionSelector.vue`、`WDVersionDetailModal.vue`、`WDEvaluationDetailModal.vue`、`WDPatchDiffModal.vue`。
- 链路：`UI → writer/review/patch_diff → ChapterVersion/ChapterEvaluation/PatchEdit/DiffLine → selected_version_id/status → finalize → memory/ledger/graph/foreshadow → export`。

### 10.2 数据模型、恢复与权限

- 版本模型有正文、provider、metadata；评审有 decision/feedback/score；Patch 有原文、目标、操作、diff 行和累计 patch。
- 需要统一 revision、父版本、content hash、评审输入 hash、配置快照和定稿批次；当前信息可能分散在多个 metadata/runtime 字段。
- 评审/定稿/异步账本同步必须与 TaskRuntime、项目 lease、outbox 绑定；version_id、patch_id、chapter_number 替换攻击需全覆盖。
- 风险：选中与定稿非原子、旧评审不自动 stale、回退不重建下游账本、删版本断链、失败状态语义漂移。

### 10.3 优化步骤与验收

1. 版本保存 `revision_id/parent/content_hash/config_snapshot/prompt_snapshot/context_snapshot`。
2. 评审绑定 version_id + content_hash；正文改变即 stale。
3. 选择、质量门、定稿、账本同步走同一 finalize transaction/outbox，可重放。
4. Patch 校验 base_version、操作范围、幂等 key、目标 hash；回退创建新版本，不覆盖历史。
5. 删除改为软删除/审计；保护 selected/exported 版本。
6. TXT manifest 保存候选版本、selected、评审、patch；DOCX 只导出选中版本并标明范围。
7. 真实验收：评审旧版→改写→stale；patch→diff→revert→重评审；并发定稿一个成功、另一个结构化冲突；重启不重复同步。

### 10.4 风险

P0/P1：原子定稿、版本 provenance、跨表回退和评审 stale。

## 11. H：LLM、提示词、DeepSeek 与配置同步

### 11.1 当前现状与链路

- 用户路由：`/api/llm-config` GET/PUT/DELETE、models、source-trace、health-check、auto-switch、bump。
- 前端：`frontend/src/api/llm.ts`、`LLMSettings.vue`、管理员 `LLMSettingsPanel.vue`。
- 模型：`LLMConfig`，多 Provider profile 以 JSON Text 保存；服务 `LLMConfigService`；`ConfigSyncManager` 管理用户配置版本。
- 管理提示词：`/api/admin/prompts` CRUD，`PromptService` 使用进程级 cache；系统配置和管理日志另有 admin 路由。
- 默认运行配置已切换 DeepSeek，但下一任务是否读取新版本、真实探针和产物 provenance 必须用真实入口验收。

### 11.2 权限、恢复与风险

- 配置 CRUD 是即时事务；任务运行中必须冻结旧快照，重试才可显式使用新版本。
- LLM 配置用户级；提示词、系统配置和管理台是管理员级；任何 key 不得进入日志、SSE、错误或导出。
- `ConfigSyncManager` 有进程内缓存/订阅，跨进程需数据库版本为真相；Prompt cache 可能读旧值；profile 与 legacy primary 字段可能漂移；自动切换 provenance 可能缺失。

### 11.3 优化步骤与验收

1. 版本化 provider profile、model capability、secret reference、health snapshot；主字段仅兼容读取。
2. 保存配置时写 config_version 和审计事件；任务 payload 写非敏感摘要。
3. Prompt 使用 `name + revision + content_hash`，cache key 包含版本；运行任务不受更新影响。
4. DeepSeek 探针验证 models、最小 chat、SSE、超时、错误码、token usage 和取消；错误结构化。
5. 自动切换记录候选、原因、预算、实际 Provider、回退结果。
6. TXT/DOCX 只导出非敏感 provenance；导入不覆盖当前用户配置，只恢复历史引用。
7. 真实验收：用户 1 改 DeepSeek 后下一任务读取新版本；运行中旧任务保持旧版本；用户 2 不受影响；重启/多进程 Prompt 不读旧 cache；密钥扫描为零。

### 11.4 风险

P0：跨进程配置/Prompt cache、真实 DeepSeek 兼容性、自动切换可追溯性和秘密泄露。

## 12. I：管理台权限、运行日志、系统配置与写作技能

### 12.1 当前现状与链路

- 管理台路由：`/api/admin/stats`、diagnostics、novel-projects、runtime-logs、prompts、update-logs、daily-request-limit、system-configs。
- 认证：`/api/auth/login`，`get_current_user` 支持 Bearer JWT；开发环境无 token 有默认系统用户兼容回退，生产环境要求 token；`get_current_admin` 做管理员门禁。
- 运行日志：`/api/updates/stream/tasks`、`stream/{task_id}`、log、complete、create；另有 `PersistentGenerationLogService`/`TaskRuntime`。
- 写作技能：`/api/writing-skills/skills`、catalog、detail、install、uninstall、execute；记录 `SkillExecution`。

### 12.2 数据模型、恢复与风险

- 用户模型 `User` 有 `is_admin/is_active`；管理配置包括 `AdminSetting/SystemConfig/Prompt/UpdateLog`；技能有 `WritingSkill/SkillExecution`。
- 管理员路由多数使用 `get_current_admin`；业务项目 owner 采用 `NovelService.ensure_project_owner`；必须检查管理员是否只读、是否可导出、是否能执行影响用户数据的操作。
- 日志与 TaskRuntime 可能存在两套事件；日志查询必须按 owner/project/task 做过滤；技能执行不能任意读取其他项目或执行未授权文件/网络操作。
- 风险：开发回退身份不可进入生产；管理员操作缺少 audit actor/action/before/after；系统配置改动范围不清；技能目录和执行权限缺少沙箱。

### 12.3 优化步骤与验收

1. 建立 RBAC/ABAC 矩阵：owner、collaborator（若未来支持）、admin、system；所有路由生成机器可读权限清单。
2. 统一审计：actor、resource、action、before/after hash、reason、request_id、ip、timestamp；秘密字段只记录 masked。
3. 日志统一读取 TaskRuntime 事件，旧 generation log 作为兼容投影；SSE 支持游标、心跳、权限和终态关闭。
4. 系统配置增加 schema、变更前检查、回滚、版本和影响范围；管理员保存后下一任务可验证版本。
5. 技能安装校验来源、版本、hash、权限声明和依赖；执行使用允许目录/网络列表、超时和资源上限。
6. TXT/DOCX 导入导出不得泄漏用户、管理员、token、API key、内部路径或日志正文；管理台导出必须单独授权和审计。
7. 真实验收：用户 2、非管理员、管理员、停用用户、过期 JWT、伪造 task/project/skill ID 全部负测；管理员操作可回放。

### 12.4 风险

P0：日志双源、技能执行边界、管理员副作用和开发身份回退。P1：审计字段不足、系统配置无回滚。

## 13. 分阶段执行计划与评分

### 阶段 D0：契约盘点与门禁（先做）

- 输出路由—schema—model—service—前端调用矩阵。
- 清理 deprecated/同步入口清单，标明适配期限。
- 建立领域 D 隔离 ASGI harness、两个用户/两个项目 fixture、导入导出 manifest 比对器。
- 验收：所有入口都有成功/401/403/422/异常用例；未完成项不得标 E2。

### 阶段 D1：数据与权限安全

- 统一 owner/admin guard、ID remap、敏感字段脱敏、项目 lease、审计事件。
- 先处理 P0：跨项目读取、任务多真相源、日志/密钥泄露、导入重复创建。
- 验收：权限负测 100% 通过，A/B 并发无串数据，秘密扫描零命中。

### 阶段 D2：任务与资料链

- 研究、文风、蓝图、导入统一 TaskRuntime；checkpoint、恢复、取消、SSE 游标统一。
- 验收：每类任务杀进程恢复或明确 stale；取消不可复活；断线无漏片/重片。

### 阶段 D3：实体账本与版本闭环

- 统一实体 ID/revision、线索/伏笔/图谱事实源、版本 provenance、评审 stale、finalize outbox。
- 验收：正文生成读取的每个资料 revision 可追踪；回退不污染历史；重复 sync 不增量重复。

### 阶段 D4：导入导出与真实 Provider

- 完成 TXT 工程 manifest、DOCX 覆盖声明/sidecar、DeepSeek 探针、配置版本。
- 验收：TXT 清单 100% 往返；DOCX 声明范围 100% 往返；DeepSeek 短任务真实通过；失败有结构化收敛。

### 阶段 D5：前端业务体验与发布审计

- 收敛左侧入口、任务进度/日志、错误动作、版本/研究/文风/图谱空状态和可访问性。
- 验收：浏览器真实流程“创建项目→蓝图→研究→文风→实体→生成→评审→定稿→导出”完整可走；任何不可用项有可见提示和重试。

### 13.1 功能评分表

每个功能 100 分：

| 维度 | 分值 | 说明 |
|---|---:|---|
| 前后端契约 | 15 | 字段、默认值、错误、旧入口一致 |
| 数据完整性 | 15 | 外键、版本、hash、事务、manifest |
| 任务恢复 | 15 | 重启、取消、重试、断线、幂等 |
| 权限隔离 | 15 | 用户、项目、管理员、ID 替换 |
| 真实入口 | 15 | 隔离 ASGI/SQLite/Provider |
| TXT/DOCX 往返 | 10 | 声明范围内可恢复且有告警 |
| 可观测与审计 | 10 | 事件、日志、provenance、脱敏 |
| 前端可用性 | 5 | 入口、状态、错误、键盘/窄屏 |

核心功能低于 90/100 不得进入下一阶段；出现跨项目泄漏、取消复活、永久卡死、重复导入、秘密泄露任一项直接阻断发布。

## 14. 最终发布准入

1. 后端全量 pytest、compileall；前端 type-check、test:run、build-only 连续两轮通过，不能跳过核心测试。
2. 领域 D 的研究、文风、蓝图、导入、导出、实体、图谱、版本、LLM、管理台均完成 E2；核心生产路径达到 E3。
3. 真实验收必须包含：短章所需资料链、10 章连续资料读取、长篇蓝图、双项目并发、配置即时生效、TXT/DOCX 往返、杀进程恢复。
4. 所有剩余限制有用户可见提示、可重试路径、审计记录和责任人；不能用“单测绿色”替代真实证据。

## 15. 当前待关闭风险清单

| 优先级 | 风险 | 关闭证据 |
|---|---|---|
| P0 | 各业务模块任务状态多真相源 | 统一 TaskRuntime + 重启/取消/重复提交实跑 |
| P0 | 导入可能重复创建或部分成功静默降级 | 两阶段导入、manifest、杀进程和损坏文件验收 |
| P0 | TXT/DOCX 工程资产覆盖不完整 | 清单化 roundtrip 与 warnings 证据 |
| P0 | LLM/Prompt 配置跨进程旧缓存 | 版本化快照、多进程/重启实跑 |
| P0 | 管理日志/技能执行越权 | RBAC、资源沙箱、审计和负测 |
| P1 | 研究来源、引用和可信度不可追溯 | source schema、引用审计和失败分类 |
| P1 | 文风 JSON 整体覆盖与 global/project 混用 | 独立版本模型、并发编辑冲突测试 |
| P1 | 人物/线索/图谱/伏笔多账本重复 | 统一实体/事件/revision 与幂等 sync |
| P1 | 版本评审与定稿非原子 | content hash、stale、outbox、回退重放 |

本文件是领域 D 的审查计划和验收基线，不是“已完成”报告；任何功能只有在对应真实证据写入审计台账后才能提升证据等级。
