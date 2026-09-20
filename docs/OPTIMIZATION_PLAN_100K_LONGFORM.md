# 玄穹文枢 10 万字级长篇处理链路优化方案

> 版本：v2.0（方向纠正版）
> 日期：2026-09-20
> 目标：优化玄穹文枢对约 10 万字长篇项目的规划、生成、记忆、检索、连续性、修订、性能和可靠性
> 非目标：本方案不要求、也不把“实际生成一部 10 万字小说”作为本轮交付物

## 0. 先把目标说清楚

本方案优化的是**系统处理 10 万字级长篇项目的能力**，不是让系统一次性生成 10 万字小说。

“10 万字”在本文中表示系统需要稳定承载的内容规模，用来设计：

- 上下文裁剪与分层记忆；
- 章节摘要和事实账本；
- RAG 检索与隔离；
- 角色、世界观、时间线、伏笔的连续性检查；
- 章节版本与修订影响传播；
- 任务恢复、取消、重试和并发写入；
- token、延迟、成本和数据库容量；
- 前端长列表、长正文阅读和导出；
- 可复现测试、部署和回滚。

本方案的完成标准是：**系统面对 10 万字级项目时不因上下文膨胀、状态漂移、检索混乱、任务长尾、数据库写入或前端长内容而失稳。**

## 1. 当前真实基线

### 1.1 已经通过的工程项

| 项目 | 当前证据 |
|---|---|
| 后端回归 | `291 passed, 1 warning` |
| 前端类型检查 | `npm run type-check` PASS |
| 前端测试 | `24 files, 118 tests passed` |
| 前端构建 | `npm run build-only` PASS |
| runtime dependency audit | PASS |
| runtime 隔离重建 | 94/94 snapshot，PASS |
| 8013/8099/5174 拓扑 | `AUDIT_RESULT=PASS` |
| 5174 history fallback | 已接管，浏览器深链接 PASS |

### 1.2 当前真实阻断

Embedding 当前仍为：

```text
provider=openai
model=text-embedding-3-large
code=EMBEDDING_CONFIG_MISSING
vector_nonempty=false
vector_dimension=0
```

MySQL 当前仍为：

```text
db_provider=sqlite
mysql_password_set=false
execute=false
connected=false
writes_performed=false
status=BLOCKED
```

FK planner 当前识别：

```text
chapters <-> chapter_versions
timeline_events -> timeline_events
status=BLOCKED_BY_FK_CYCLES
```

这些状态是系统优化的输入条件，不能被计划文字改写成已完成。

## 2. 优化范围和非目标

### 2.1 本方案要优化的内容

1. 长篇项目的输入、输出和版本数据流；
2. 10 万字级内容的分层记忆和上下文组装；
3. 章节摘要、事实、角色状态、世界规则、时间线和伏笔索引；
4. RAG 的索引、检索、项目隔离和降级可观测性；
5. 长任务的超时、重试、取消、SSE terminal 和恢复；
6. 章节修订对后续上下文的影响传播；
7. token、成本、延迟、缓存和数据库压力；
8. 前端长正文、章节列表、版本对比和导出体验；
9. SQLite 当前运行与未来 MySQL 迁移的可审计性；
10. 真实 Provider、fixture、mock、health 和队列响应的证据分层。

### 2.2 本方案明确不做的事

- 不在本轮自动创作一部 10 万字小说；
- 不用脚本批量灌入小说正文来制造“完成”；
- 不把章节数量、字符数或 mock 输出当系统优化完成证据；
- 不在没有 embedding 凭据时伪造向量和 RAG 命中；
- 不在 MySQL readiness 和 FK cycle 未解决前执行迁移 apply；
- 不为了通过测试删除长篇相关测试或提高构建阈值；
- 不把一次成功的短章节请求外推成 10 万字级稳定性证明。

## 3. 10 万字级系统容量模型

### 3.1 内容分层

系统不能把 10 万字全文每次都塞入 Provider prompt。推荐固定为五层：

| 层 | 内容 | 用途 | 更新频率 |
|---|---|---|---|
| L0 项目契约 | 题材、风格、硬约束、禁止事项 | 每次请求都需要的稳定约束 | 低 |
| L1 全书摘要 | 主线、终局方向、全局冲突 | 跨卷导航 | 低/人工确认 |
| L2 卷级摘要 | 当前卷目标、已发生事件、未决线索 | 当前卷规划 | 每卷/重大修订 |
| L3 章节摘要 | 最近章节结果、角色变化、章末压力 | 下一章生成 | 每章 |
| L4 事实检索 | 人物、地点、道具、时间线、伏笔的结构化事实 | 按查询召回 | 事件变化时 |

原始正文是证据源，摘要和向量是派生索引，任何派生层都不能无记录覆盖原文和确认版本。

### 3.2 Context budget

每次 Provider 调用都必须有显式预算，不允许按全文长度无限增长：

```text
system_contract_budget
project_contract_budget
retrieved_facts_budget
recent_chapters_budget
current_chapter_plan_budget
output_budget
reserved_safety_margin
```

上下文组装器必须输出 `context_manifest`：

```json
{
  "project_id": "...",
  "chapter_id": "...",
  "base_version_id": "...",
  "snapshot_id": "...",
  "selected_layers": ["L0", "L1", "L2", "L3", "L4"],
  "source_ids": [],
  "token_estimate": 0,
  "max_tokens": 0,
  "truncated_layers": [],
  "omitted_sources": [],
  "context_digest": "..."
}
```

通过条件：

- 每次调用都能解释上下文由哪些来源组成；
- 超预算时按优先级裁剪，不静默截断关键硬约束；
- 同一 snapshot、同一参数的组装结果可复现；
- 旧版本内容不会混入新版本 context；
- context 预算和 output 预算分别统计。

### 3.3 10 万字不是单一容量指标

必须同时观察：

```text
全文字符数
章节数
场景数
结构化事实数
摘要层数
向量条目数
单次 prompt tokens
单章累计 tokens
全项目累计 tokens
数据库行数
版本数量
修订传播范围
```

## 4. 核心优化路线

### Phase 1：长篇数据流审计

目标：先确认现有代码已经如何保存和读取长篇状态，避免重复造表或破坏已跑通链路。

审计范围：

- `PipelineOrchestrator` 的输入输出；
- `ChapterVersion` 和章节状态；
- `longform_context_service`；
- `memory_layer_service`；
- `knowledge_retrieval_service`；
- `style_rag_service`；
- `timeline`、`foreshadowing`、`character` 相关服务；
- SSE、retry、cancel、superseded-run 和 persist 阶段；
- token usage、cost、attempt 和 project/user 归属。

交付物：

```text
当前长篇数据流图
模块输入输出表
上下文来源清单
写入点清单
状态机和终态清单
```

验收：没有只读审计遗漏的持久化写入点；每个摘要、向量、事实和版本都能定位来源。

### Phase 2：分层上下文和裁剪优化

目标：让 10 万字级项目不会因全文拼接导致 token 爆炸、延迟长尾和成本失控。

实施顺序：

1. 把 L0/L1/L2/L3/L4 作为显式 context sections；
2. 每层设置独立 token ceiling；
3. 先保留硬约束、当前章计划和最近连续性事实；
4. 再按相关性加入历史事实和摘要；
5. 最后才加入低优先级背景正文片段；
6. 超限时记录裁剪原因和被省略 source；
7. 生成、评审、改写分别使用各自 context policy；
8. 对相同 digest 的不可变 context 做版本化缓存。

验收指标：

- 10 万字规模模拟项目下，单次 prompt 不随全文线性增长；
- context assembly p50/p95 有记录；
- 裁剪不会删除项目硬约束和当前章必要事实；
- 缓存命中与未命中产生相同的事实集合；
- 故意降低 ceiling 时测试失败，而不是静默生成错误 context。

### Phase 3：连续性账本和事实冲突门

目标：避免长篇项目在章节增长后出现角色、地点、道具、时间线和伏笔漂移。

结构化对象：

```text
CharacterState
WorldRule
LocationState
ItemOwnership
TimelineEvent
ForeshadowingLedger
ChapterDeliveryPacket
ContinuitySnapshot
```

每个事实必须带：

```text
entity_id
source_chapter_id
source_version_id
valid_from
valid_to
confidence
status
supersedes
```

冲突分级：

| 等级 | 例子 | 处理 |
|---|---|---|
| BLOCKING | 已死亡角色重新正常行动、核心道具同时属于两人 | 阻断确认 |
| REVIEW | 角色语气变化、非核心地点描述差异 | 人工审查 |
| INFO | 有来源的新事实或合理成长 | 记录并继续 |

验收：注入一个已知矛盾时，测试必须指出实体、来源章节、冲突字段和阻断等级。

### Phase 4：RAG 和 Embedding 优化

目标：把“配置存在、请求成功、向量非空、检索有效”拆成独立状态。

实施：

1. embedding key/base URL/model 独立于 chat key；
2. 对输入文本规范化、分块、去重并记录 chunk source；
3. 向量索引按 project/novel 隔离；
4. 更新章节时使用版本化 upsert，不删除确认版本证据；
5. 查询返回 source chapter/version/digest；
6. 记录 top-k、score、latency 和命中事实；
7. embedding 失败时返回结构化 degraded 状态；
8. 无向量模式与真实 RAG 模式分开统计。

真实验收分层：

```text
config_present
request_success
vector_nonempty
vector_dimension_stable
index_write_success
retrieval_relevant
cross_project_isolation
```

当前没有独立凭据时，正确结果仍是 `EMBEDDING_CONFIG_MISSING`。

### Phase 5：章节版本、修订传播和并发写入

目标：长篇修订不能无记录地污染后续章节和账本。

每次生成/修订必须绑定：

```text
project_id
chapter_id
generation_run_id
base_version_id
context_digest
snapshot_id
optimistic_lock_version
```

规则：

- 接受版本必须幂等；
- 同一 chapter 不能产生两个同时生效的 confirmed version；
- 修订旧章后生成 `RevisionImpact`；
- 受影响的后续章节进入 stale/review 队列；
- superseded run 不得落库新确认版本；
- 旧任务晚到不得覆盖新版本；
- Story Bible 更新采用版本冲突检测。

验收：并发提交、旧任务晚到、取消后回写、修订后读取旧 snapshot 四类测试必须分别覆盖。

### Phase 6：长任务可靠性和可恢复性

目标：10 万字级项目由大量长任务组成，必须把长尾和中断作为正常状态处理。

必须观测：

```text
queued
claimed
running
retrying
cancelling
cancelled
waiting_for_confirm
completed
failed
superseded
stale
```

每个任务必须有唯一 terminal event。超时、Provider 断流、进程重启、网络中断和用户取消都必须能恢复或明确失败。

验收：

- cancel 后不再新增正文/确认版本/usage；
- retry 不重复计费或重复接受；
- SSE 断开不把任务误报成功；
- worker 重启后可从持久化状态恢复；
- stale run 不得覆盖新结果；
- 数据库中不存在悬挂 generating 状态。

### Phase 7：性能、成本和缓存

目标：降低 10 万字级项目的累计成本和长尾，不通过降低质量门制造假优化。

分阶段统计：

```text
context_assembly_ms
retrieval_ms
mission_ms
provider_ms
review_ms
persist_ms
retry_count
tokens_in
tokens_out
cost
cache_hit
```

缓存原则：

- 只缓存不可变输入和带 digest 的派生结果；
- 不缓存实时任务状态；
- prompt、context、model、policy 变化必须失效；
- 缓存命中不能改变事实集合；
- 统计命中/未命中两套 p50/p95。

预算分为单章、单项目、全局三层，状态必须明确为 `budget_blocked`、`awaiting_approval`、`degraded_mode`、`completed` 或 `failed`。

### Phase 8：前端长内容和导出

目标：让长篇项目在浏览器中可用，而不是只让后端能处理。

优化范围：

- 章节列表虚拟滚动或分页；
- 长正文按章加载，不一次性挂载 10 万字 DOM；
- 版本对比按差异片段加载；
- 生成进度和 SSE 状态不阻塞阅读；
- 修订影响以列表展示；
- 导出使用后台任务并显示真实状态；
- 深链接刷新必须保留；
- 管理路由和 API 错误分开显示。

验收：

- 10 万字模拟项目打开章节列表不出现明显卡死；
- 单章阅读、切换和返回保持可用；
- 导出失败不会清空当前编辑状态；
- `/workspace`、`/admin`、`/settings` 直接刷新可启动 SPA。

### Phase 9：SQLite 当前运行与 MySQL 迁移准备

目标：先保证 SQLite 继续稳定，再为未来 MySQL 做可审计准备。

当前保持：

```text
SQLite production
MySQL preview-only
```

迁移前必须完成：

1. backup manifest；
2. source schema fingerprint；
3. fragment hash；
4. FK dependency plan；
5. `chapters <-> chapter_versions` 两阶段约束演练；
6. `timeline_events` 自引用约束演练；
7. 行数、约束、索引和 fingerprint 对比；
8. 副本 rollback rehearsal；
9. 人工 review；
10. 最后才允许显式 apply。

## 5. 推荐实施轮次

| 轮次 | 主题 | 主要交付 | 验收 |
|---|---|---|---|
| R69 | context manifest | 分层上下文、预算、裁剪原因 | fixture 长上下文回归 |
| R70 | continuity snapshot | 事实来源、冲突分级、snapshot | 注入冲突必须阻断 |
| R71 | revision impact | 修订传播、stale 后续章节 | 旧章修订影响可追踪 |
| R72 | embedding probe | 独立配置、向量和检索分层 | 非空向量和固定事实集 |
| R73 | long-task recovery | cancel/retry/SSE/restart | terminal 唯一、无脏写 |
| R74 | cost/cache | digest cache、token/cost 分层 | p50/p95 和账本一致 |
| R75 | long-content UI | 虚拟列表、按章加载、导出 | 10 万字 fixture 浏览器门禁 |
| R76 | MySQL rehearsal | 副本迁移、FK cycle、rollback | 无生产写入、fingerprint 可比 |

每轮只改一个主题，必须更新对应 `docs/OPTIMIZATION_ROUND_*.md`，跑专项测试、反向测试、部署审计并推送 GitHub。

## 6. 统一验收标准

### 6.1 长上下文

```text
context_manifest 可重现
预算超限有结构化裁剪原因
硬约束不会被静默裁掉
摘要/事实/原文来源可追踪
同输入 digest 结果稳定
```

### 6.2 连续性

```text
人物、地点、道具、时间线、伏笔均有来源
BLOCKING 冲突阻断确认
REVIEW 冲突进入人工队列
修订能生成 RevisionImpact
旧 run 不覆盖新 version
```

### 6.3 可靠性

```text
每个任务唯一 terminal
cancel/retry/restart 可验证
无悬挂 generating
usage 与 project/user/attempt 关联
失败状态不伪装成功
```

### 6.4 性能成本

```text
context/retrieval/provider/review/persist 分段计时
输入/输出 token 分开
retry 和失败成本单独记录
cache hit/miss 可比较
不通过降低质量门制造性能绿灯
```

### 6.5 部署

```text
process_commit == current_commit
working_tree_dirty == false
8013/8099/5174 health PASS
所有核心深链接 appRoot=true
API/静态资源边界正确
GitHub branch 同步
```

## 7. 当前下一步

1. R69 先审计现有 context assembler，输出来源、优先级和 token budget，不立即重写主链；
2. 在隔离 fixture 中模拟 10 万字级项目，验证上下文不按全文线性膨胀；
3. 再实现 `context_manifest` 和可观察裁剪；
4. 之后推进 continuity snapshot、revision impact、embedding、长任务恢复和长内容 UI；
5. MySQL 继续保持 preview-only，直到 readiness、FK cycle 和 rollback rehearsal 全部有证据。

本方案的完成不是“生成十万字小说”，而是让玄穹文枢能够稳定、可审计、可回滚地处理十万字级长篇项目。