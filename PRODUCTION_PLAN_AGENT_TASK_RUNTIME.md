# 玄穹文枢：领域 A——统一任务中心、TaskRuntime、SSE、取消/恢复/并发/权限

> 审查性质：只审查、不修改业务代码。  
> 审查基线：以当前工作区代码、当前测试和当前静态检索结果为准，不引用旧报告的“已完成”结论。  
> 审查日期：2026-08-14（Asia/Shanghai）。  
> 本次代理新增文件：本文件；未修改任何业务代码。

## 0. 执行摘要

当前后端已经存在一个可持久化的 `TaskRuntime`/`TaskRuntimeEvent` 基础设施，并且通用任务路由具备创建、查询、事件回放、SSE、租约领取、恢复、心跳、进度、取消、重试和 stale 巡检入口。当前实测通过了：

- `backend/app/services/test_task_runtime.py`、`test_task_reconciliation.py`、`test_persistent_generation_log_service.py`：**32 passed**。
- `backend/app/api/routers/test_task_runtime_route.py`、`test_research_job.py`、`test_outline_job_restart_recovery.py`：**20 passed**。
- `backend\.venv\Scripts\python.exe -m compileall -q backend/app`：**通过**。

这些结果只能证明定向单元/路由替身测试覆盖的行为，不等同于全功能生产级验收。静态检索仍确认以下问题：

1. 研究、文风、蓝图、旧稿导入、章节大纲等领域仍保留模块级 `_JOBS`、`_RUNS`、`_SCHEDULED_RUNS` 和进程内 `asyncio.Task`；部分路径把它们称为兼容回退，但尚未完成“所有新任务只以 TaskRuntime 为状态真相源”的收口。
2. `generation_log_service.py` 仍有纯内存缓冲、订阅队列、owner 字典和闲置清理；持久化日志服务另行桥接到 TaskRuntime，存在双轨 API 和调用方误用风险。
3. 状态转移的部分方法是“读取 ORM 对象后再提交”的逻辑，虽然终态/取消保护已有测试，但跨进程并发下仍需要以数据库条件更新或版本号保证所有竞争窗口可证明。
4. `task_runtime` SSE 和 `updates` SSE 都是轮询数据库的生成器，能按事件游标回放，但正文 `content_delta`、日志 `log`、诊断和普通进度的统一事件契约尚未在所有业务入口完成证明。
5. TaskRuntime API 对 project 的创建入口做了 owner 校验，但 `list_tasks`、`reconcile_stale_tasks` 等依赖任务 owner 过滤；项目/章节归属的一致性、跨资源 ID 组合校验和管理员审计语义仍需补齐契约测试。
6. 当前测试是定向测试；尚未用真实 HTTP/SSE、多进程/双 worker、真实 Provider、进程重启和双项目压力对本领域做正式全链路验收。

结论：**TaskRuntime 核心已具备可继续工程化的骨架，但领域 A 当前不能判定为生产级全绿，P0 仍是“统一所有后台任务的状态源”和“真实入口并发/断线/重启验收”。**

---

## 1. 现状文件与职责清单

### 1.1 任务中心核心文件

| 文件 | 当前职责 | 当前证据 | 风险/待核验 |
|---|---|---|---|
| `backend/app/models/task_runtime.py` | `task_runtime_tasks`、`task_runtime_events` ORM 模型；任务字段、事件游标、租约、心跳、指标、产物引用 | 任务主键、owner/project/chapter 索引；事件外键；任务和事件幂等唯一约束 | 缺少显式状态版本/乐观锁字段；事件表没有专门的 `(task_id,event_id)` 复合读取索引；`payload` 仍是自由 JSON |
| `backend/app/schemas/task_runtime.py` | 状态枚举、事件枚举、创建/进度/心跳/租约/指标/重试/事件 DTO | 状态含 `queued/running/cancelling/cancelled/succeeded/failed/stale`；事件含日志、正文增量、诊断、质量更新 | DTO 未明确动作列表、结构化错误对象、产物引用集合、事件通道/分片序号/内容哈希等生产字段 |
| `backend/app/services/task_runtime.py` | 创建、查询、列表、payload 合并、事件写入、claim/recover、心跳、进度、取消、retry、stale、指标 | 32 项定向服务测试通过 | 需要做跨会话竞争测试、状态转移矩阵测试、任务类型/作用域幂等约束测试；`append_event` 的状态转换需要数据库级 CAS 证据 |
| `backend/app/services/task_reconciliation.py` | 启动/巡检时将心跳超时任务标记 stale，释放孤儿忙章节并保留恢复信息 | 6 项重启巡检测试通过 | 当前重点偏章节生成；研究/文风/蓝图/导入的业务产物修复和 worker 重启恢复仍由各路由自处理 |
| `backend/app/services/persistent_generation_log_service.py` | 将旧生成日志 API 桥接到 TaskRuntime `LOG`/终态事件 | 3 项定向测试覆盖 | 尚未证明所有日志调用方都已迁移；与内存 `GenerationLogService` 并存 |
| `backend/app/services/generation_log_service.py` | 旧的内存日志缓冲、订阅队列、owner 校验、闲置清理 | 静态确认 `_buffers/_subscribers/_last_activity/_owners` | 进程重启丢失、跨 worker 不共享、与持久化日志双轨；不可作为生产状态源 |
| `backend/app/main.py` | lifespan 启动巡检和周期 sweeper | 静态确认 `asyncio.create_task(_periodic_sweeper())`；compileall 通过 | 单进程 sweeper；多实例部署会重复巡检，虽部分更新有竞态保护，但尚无多实例实测；sweeper 失败告警与自愈指标需验收 |
| `backend/app/db/session.py` | SQLite WAL/连接参数、MySQL 连接池、异步会话 | 静态确认 SQLite 与 MySQL 分支 | SQLite 写竞争、MySQL 隔离级别、长 SSE 会话与连接生命周期需要压力测试 |
| `backend/app/db/init_db.py`、`backend/alembic/versions/001_task_runtime.py` | 跨进程迁移锁、TaskRuntime 表迁移/兼容修复 | 静态确认外部 lock 文件与 migration marker | 需要在隔离数据库上双进程迁移、断电/半迁移和升级回滚验收 |

### 1.2 任务路由与业务入口

| 路由文件 | 入口/任务域 | 当前状态处理方式 |
|---|---|---|
| `backend/app/api/routers/task_runtime.py` | `/api/task-runtime/tasks` 全套通用任务 API | 主要以 TaskRuntime 为源；鉴权通过 `get_current_user` |
| `backend/app/api/routers/updates.py` | `/api/updates/stream/*` 旧生成日志 API、活跃任务列表 | 读取持久化 TaskRuntime，但只筛选 `LOG` 和终态事件 |
| `backend/app/api/routers/writer.py` | 正文生成、章节取消/恢复、章节大纲/重写大纲、章节流 | 正文章节已有 TaskRuntime 注册/claim/事件桥接；章节大纲仍有 `_OUTLINE_JOBS/_OUTLINE_PROJECT_RUNS/_OUTLINE_SCHEDULED_RUNS` |
| `backend/app/api/routers/novels.py` | 蓝图生成、旧稿导入、导出和项目入口 | 蓝图/导入均有 TaskRuntime 适配，但仍保留内存 job 快照和调度集合 |
| `backend/app/api/routers/research.py` | 研究配置、运行、查询、取消 | 新任务创建 TaskRuntime；运行句柄、job snapshot 和 scheduled set 仍在内存 |
| `backend/app/api/routers/style.py` | 文风素材上传、文风画像生成、取消/恢复查询 | 新任务创建 TaskRuntime；两类 job 字典、项目 run 映射和 scheduled set 仍存在 |
| `backend/app/api/routers/outline.py` | 长篇总纲、结构、历史、演化 | 当前路由本身偏同步/业务服务调用；需确认是否与长篇异步任务中心完全对齐 |
| `backend/app/services/generation_call_service.py` | Provider 调用、超时和生成任务内部 provider task | 静态确认 `asyncio.create_task`；应明确该句柄只负责取消当前 Provider 调用，不得被当作任务状态源 |
| `backend/app/services/project_ledger_lease_service.py` | 项目账本租约 | 静态确认另有 heartbeat task；需要和 TaskRuntime lease 边界区分，避免双租约死锁/误判 |

### 1.3 已确认的内存字典/句柄残留

| 文件 | 符号 | 用途 | 生产级处置 |
|---|---|---|---|
| `routers/research.py` | `_RESEARCH_TASKS` | run_id → 当前进程协程句柄 | 保留为临时句柄注册表，但只能用于发取消信号/清理；状态、权限、恢复、终态必须来自 TaskRuntime |
| `routers/research.py` | `_RESEARCH_JOBS` | job 快照/兼容读取 | 新任务禁止依赖；迁移完成后仅保留短期诊断缓存或删除 |
| `routers/research.py` | `_RESEARCH_SCHEDULED_RUNS` | 防止同进程重复调度 | 改为 TaskRuntime claim + 幂等键 + worker 调度表；集合不能跨进程去重 |
| `routers/style.py` | `_STYLE_PROFILE_JOBS`、`_STYLE_SOURCE_UPLOAD_JOBS` | 两类文风任务快照 | 由统一任务 DTO/事件 payload 恢复；内存只保存 asyncio 句柄 |
| `routers/style.py` | `_STYLE_*_PROJECT_RUNS` | project → 最新 run 映射 | 改为数据库查询同项目同类型 active task；加入 owner/project/type 复合约束 |
| `routers/style.py` | `_STYLE_SCHEDULED_RUNS` | 同进程调度去重 | 改为 claim/lease；重启后由 queued/stale 任务扫描恢复 |
| `routers/novels.py` | `_BLUEPRINT_JOBS`、`_BLUEPRINT_PROJECT_RUNS`、`_BLUEPRINT_SCHEDULED_RUNS` | 蓝图任务快照、项目映射、调度集合 | TaskRuntime payload 保存执行 spec 和阶段；状态接口不读内存覆盖 DB |
| `routers/novels.py` | `_IMPORT_JOBS`、`_IMPORT_USER_RUNS`、`_IMPORT_SCHEDULED_RUNS` | 旧稿导入快照、用户映射、调度集合 | 上传文件引用/断点进入 TaskRuntime payload；按 owner + task_type + scope 查询 active task |
| `routers/writer.py` | `_OUTLINE_JOBS`、`_OUTLINE_PROJECT_RUNS`、`_OUTLINE_SCHEDULED_RUNS` | 章节大纲任务快照、项目映射、调度集合 | 统一为 `outline_generation`/`outline_rewrite` 任务；取消/恢复/重复提交走同一 runtime API |
| `services/generation_log_service.py` | `_buffers`、`_subscribers`、`_last_activity`、`_owners` | 旧内存日志 | 删除生产调用路径，统一从 `TaskRuntimeEvent` 回放；实时广播可使用进程内订阅优化，但不能丢失持久化事件 |
| `main.py` | `sweeper = asyncio.create_task(...)` | 单实例巡检句柄 | 句柄可保留；巡检本身必须幂等、可观测，并在多实例部署中采用数据库/分布式租约 |

---

## 2. 当前路由清单与契约审查

### 2.1 通用 TaskRuntime 路由

前缀：`/api/task-runtime`，文件：`backend/app/api/routers/task_runtime.py`。

| 方法 | 路径 | 当前用途 | 验收重点 |
|---|---|---|---|
| POST | `/tasks` | 创建 queued 任务，项目存在且属于当前用户时允许绑定 | 重复 idempotency、不同用户冲突、项目/章节归属 |
| GET | `/tasks` | 按 owner/project/chapter/status 列表 | 不能读到他人任务；status 非法值处理；分页/排序稳定 |
| GET | `/tasks/{id}` | 查询快照 | 404/权限拒绝必须不泄露任务存在性 |
| GET | `/tasks/{id}/events` | 游标后的事件列表 | 顺序、上限、无漏/无重、权限隔离 |
| GET | `/tasks/{id}/stream` | TaskRuntime 全事件 SSE | `Last-Event-ID`、终态关闭、心跳、断线、事件分片 |
| POST | `/tasks/{id}/claim` | worker 领取/更新租约 | 双 worker 只有一个成功；stale 可抢占；cancelling 不应被复活 |
| POST | `/tasks/{id}/recover` | stale/running 恢复入口 | 只允许明确可恢复状态；不应把 queued 误当恢复 |
| POST | `/tasks/{id}/metrics` | 指标持久化 | 终态后指标语义；重复写入；token 不可为负 |
| POST | `/stale/reconcile` | 当前用户范围 stale 巡检 | 是否允许普通用户触发；项目过滤权限；并发巡检幂等 |
| POST | `/tasks/{id}/progress` | 进度/阶段/消息 | 终态拒绝；cancelling 不回 running；进度单调性策略 |
| POST | `/tasks/{id}/heartbeat` | 心跳/租约 | 非 owner/非 lease owner 不能刷新；终态不应重新活跃 |
| POST | `/tasks/{id}/cancel` | 请求取消；未领取 queued 可立即 cancelled | running 必须先 cancelling，再由 worker 收敛；迟到成功拒绝 |
| POST | `/tasks/{id}/retry` | failed/cancelled/stale 重试 | 重试预算、幂等、旧 worker 隔离、payload checkpoint 复用 |
| POST | `/tasks/{id}/events` | 通用事件写入 | 不应开放给普通前端任意伪造终态；生产应限制为内部/受控事件类型 |

### 2.2 SSE 与日志路由差异

当前有两套面向前端的 SSE：

1. `GET /api/task-runtime/tasks/{task_id}/stream`：回放全部 TaskRuntime 事件，包括 `content_delta`、`log`、`progress`、诊断和终态。
2. `GET /api/updates/stream/{task_id}`：只查询 `LOG`、`TASK_COMPLETED`、`TASK_FAILED`、`TASK_CANCELLED` 四类事件，用于旧日志 UI。

这意味着同一任务有两个事件视图。若正文流使用第一条、运行日志使用第二条，前端必须明确订阅关系；否则会出现“正文进入日志区”或“日志区看不到阶段/诊断”的体验和验收歧义。后续统一事件 DTO 时应保留 `channel = content | log | progress | diagnostic | terminal`，并在 API 层提供显式过滤，而不是靠不同路由隐式过滤。

### 2.3 业务路由的当前状态真相风险

- 研究 status 路由先读取内存 job，再查询 artifact 和 TaskRuntime；代码注释声明 TaskRuntime 优先，但必须用真实重启 HTTP 流程证明所有分支都不会由旧内存快照覆盖持久状态。
- 文风 status/cancel 同时恢复内存 job 和 TaskRuntime；任务存在时 TaskRuntime 是主要依据，但没有全域统一的公共状态序列化器。
- 蓝图和章节大纲有大量“从历史记录/DB 复原 legacy payload，再写入内存字典”的逻辑，容易把业务 legacy status 与 TaskRuntime status 之间的映射分散在多处。
- 旧稿导入的上传文件引用已进入 TaskRuntime payload 的设计路径，但必须实测进程重启后路径校验、文件缺失、取消和重试。

---

## 3. 当前状态机与目标状态机

### 3.1 当前声明状态

`backend/app/schemas/task_runtime.py` 声明：

```text
queued → running → cancelling → cancelled
queued/running/cancelling → failed
running/cancelling → stale
failed/cancelled/stale → queued（retry）
queued/running/stale → running（claim/recover 的部分路径）
```

核心代码已明确以下保护：

- `TERMINAL_STATUSES = cancelled/succeeded/failed/stale`。
- 终态任务不能被写成不同状态。
- `cancelling` 任务不能被迟到 Provider 回调改成 `running/succeeded/failed`。
- queued 且无 lease 的取消可由 API 直接收口为 cancelled。
- stale 任务可被新 worker 通过 claim/recover 重新领取。

### 3.2 当前未完全证明的状态问题

1. `append_event()` 在 Python ORM 对象上做状态检查/赋值并 commit；需要跨 session、双 worker、取消与完成同时提交的数据库级测试。
2. `claim()` 对 queued/stale/running 使用条件 update，属于较强的竞争保护；但 claim 后追加 `TASK_STARTED` 事件是后续步骤，若事件提交失败，任务可能已 running 但缺少 started 事件，需要明确 outbox/补偿策略。
3. `request_cancel()` 的 cancelling 事件和 queued 立即 cancelled 是两次提交；中途进程崩溃时可能留下 cancelling，需要巡检或 worker 继续收口。
4. `retry()` 直接复用同一个 task_id 并增加 retry_count；需要明确“重试是同一逻辑任务的新 attempt”还是“新 task”，并给每次 attempt 独立 lease、事件序列和产物引用。
5. `stale` 同时表示“worker 心跳超时”和“可恢复中间态”，业务 UI 需要区分 stale reason、最后心跳、是否已有部分产物。

### 3.3 生产目标状态机

```text
created
  ↓ durable create + task_created
queued
  ├─ cancel(unclaimed) ───────────────→ cancelled
  ├─ claim(CAS + lease) ──────────────→ running
  └─ process restart ─────────────────→ queued（仅无 lease 且未执行）

running
  ├─ progress/heartbeat ──────────────→ running
  ├─ cancel request ──────────────────→ cancelling
  ├─ heartbeat timeout ───────────────→ stale
  ├─ atomic finalize success ─────────→ succeeded
  └─ atomic finalize failure ─────────→ failed

cancelling
  ├─ worker observes cancellation ────→ cancelled
  ├─ heartbeat timeout ───────────────→ stale（带 cancel_requested=true）
  └─ late success/failure/progress ───→ reject state resurrection; audit only

stale
  ├─ recover(CAS + new lease) ─────────→ running
  ├─ retry budget path ─────────────────→ queued（new attempt）
  └─ user discard/expiry policy ───────→ failed or cancelled（必须显式原因）

terminal
  ├─ query/events/export ──────────────→ read-only
  └─ retry with idempotency ───────────→ new attempt; never mutate old terminal history
```

生产实现要求：状态转移、attempt 编号、lease token、事件写入和关键产物 outbox 在同一事务边界或具备可重放补偿；任何迟到回调必须携带 attempt/lease token，不能只携带 task_id。

---

## 4. 领域逻辑链

### 4.1 通用任务执行逻辑链

```text
前端提交
  ↓
鉴权 get_current_user
  ↓
项目/章节 owner 校验
  ↓
构造 task_type + scope + idempotency_key + execution_spec
  ↓
TaskRuntime.create_task（durable queued + task_created）
  ↓
worker 调度（只能传 task_id，不以内存 job 作为状态）
  ↓
claim（CAS + lease_owner + heartbeat）
  ↓
stage/progress/log/content_delta 事件
  ↓
周期 heartbeat 与取消检查
  ├─ cancel：cancelling → worker 收敛 → cancelled
  ├─ timeout/崩溃：sweeper → stale → recover/重试
  ├─ 失败：结构化 error + failed
  └─ 成功：产物事务 + succeeded
  ↓
SSE/查询按 event_cursor 回放
  ↓
前端显示动作：取消/恢复/重试/查看产物/查看诊断
```

### 4.2 取消竞态逻辑链

```text
用户点击取消
  ↓
鉴权 + owner 过滤
  ↓
TaskRuntime.request_cancel
  ├─ terminal：幂等返回，不产生复活
  ├─ queued 无 lease：cancel_requested + cancelled
  └─ running：cancel_requested + cancelling
       ↓
      进程内句柄若存在则发送 cancel signal（仅控制句柄）
       ↓
      worker/provider 在安全点观察 TaskRuntime
       ↓
      释放业务锁/章节占用/临时资源
       ↓
      事务写 TASK_CANCELLED + 产物/工件 cancelled
       ↓
      SSE 发送终态并关闭
```

### 4.3 重启恢复逻辑链

```text
进程启动
  ↓
数据库迁移/锁
  ↓
TaskReconciliationService.reconcile
  ├─ running/cancelling 心跳超时 → stale + task_stale
  ├─ live lease → 保留，不误杀
  └─ 章节 busy 且无活跃任务 → 释放为可重试并保留 run_id
  ↓
请求 status/list 或专用恢复扫描
  ↓
queued/stale 任务进入调度候选
  ↓
worker claim CAS
  ↓
从 payload/checkpoint 恢复，不从内存字典猜测
```

---

## 5. 树状依赖图

```text
FastAPI app
├─ lifespan
│  ├─ init_db / Alembic
│  ├─ TaskReconciliationService
│  └─ periodic sweeper
├─ auth/dependencies
│  ├─ get_current_user
│  └─ get_project_owner_guard
├─ API routers
│  ├─ task_runtime.py
│  │  ├─ TaskRuntimeService
│  │  ├─ TaskRuntimeRead/EventRead
│  │  └─ AsyncSessionLocal polling SSE
│  ├─ updates.py
│  │  └─ PersistentGenerationLogService → TaskRuntimeEvent
│  ├─ writer.py
│  │  ├─ chapter generation
│  │  ├─ outline jobs (内存残留)
│  │  ├─ PipelineOrchestrator
│  │  └─ longform checkpoint
│  ├─ novels.py
│  │  ├─ blueprint jobs (内存残留)
│  │  └─ import jobs (内存残留)
│  ├─ research.py
│  │  ├─ research artifact service
│  │  └─ research jobs (内存残留)
│  └─ style.py
│     ├─ style upload
│     ├─ style profile
│     └─ style jobs (内存残留)
├─ persistence
│  ├─ TaskRuntime
│  ├─ TaskRuntimeEvent
│  ├─ business artifacts/chapters/versions
│  └─ migration locks
└─ external execution
   ├─ asyncio task handle（进程本地控制，不是真相源）
   ├─ LLM/provider task
   ├─ Celery tasks（部分非生成分析功能）
   └─ file artifacts/upload storage
```

### 5.1 统一改造后的目标依赖

```text
业务路由
  ↓ 只创建 TaskSpec，不维护业务状态机
TaskCoordinator
  ├─ TaskRuntimeRepository（唯一状态源）
  ├─ TaskAttempt/LeaseRepository
  ├─ EventRepository（事件游标/幂等）
  ├─ TaskDispatcher（跨进程可恢复）
  ├─ CancellationRegistry（仅句柄）
  ├─ ArtifactOutbox
  └─ TaskSerializer（所有业务域统一 DTO）
        ↓
Worker adapter
  ├─ research
  ├─ style
  ├─ blueprint
  ├─ outline
  ├─ import
  └─ chapter generation
```

---

## 6. 分块执行计划

### P0-A1：统一任务注册与状态真相源

**目标**：所有六类后台任务（正文、长篇总纲/章节纲、蓝图、研究、文风、导入）使用同一 TaskSpec/TaskRuntime/事件协议。

**步骤**：

1. 盘点每个任务的 task_type、scope、owner、业务产物、执行输入、恢复 checkpoint、取消安全点。
2. 建立统一 `TaskSpec`：`task_id/task_type/owner_user_id/project_id/chapter_id/idempotency_key/attempt/execution_spec/result_ref`。
3. 将各路由的 `_JOBS` 快照字段映射到 `TaskRuntime.payload` 的版本化命名空间，例如 `payload.task_spec_v1`、`payload.checkpoint_v1`、`payload.legacy_projection`。
4. 状态查询统一走 `TaskRuntimeService`；内存 job 只能作为句柄索引，禁止作为 API 状态来源。
5. 为每个任务域添加 `TaskWorkerAdapter`，由统一协调器调用 claim/heartbeat/progress/finalize。
6. 加入“无 TaskRuntime 时明确失败/迁移告警”的策略，逐步删除静默兼容回退。

**完成定义**：六类任务均可在清空模块级 job 字典后查询、取消、恢复和重试；状态 DTO 字段一致；旧字段仅作为 projection。

### P0-A2：状态机与原子终态

**目标**：取消、成功、失败、stale、重试在跨协程/跨进程下不可复活、不可重复收口。

**步骤**：

1. 建立显式状态转移表和 attempt/lease token。
2. 对 claim、cancel request、finalize success/failure/cancelled、mark stale、recover 使用数据库条件更新（CAS）。
3. 为终态 finalize 增加 attempt/lease 校验；迟到 worker 只能写 rejected-late 诊断事件。
4. 解决“状态已切换但终态事件/业务产物提交失败”的 outbox 或补偿事务。
5. 重试改为独立 attempt，旧 attempt 事件不可覆盖新 attempt 状态。
6. 对 cancelling 超时制定明确 policy：继续 stale + 可恢复，或在安全边界自动 cancelled，不允许永久卡住。

### P0-A3：SSE 统一、回放和通道隔离

**目标**：断线重连无漏片、无重片、无串任务；正文和日志严格分离。

**步骤**：

1. 统一事件 DTO：`event_id/task_id/attempt/event_type/channel/status/stage/progress/message/payload/created_at`。
2. 为 `content_delta` 增加 `stream_id/segment_index/sequence/content_hash/is_final`，客户端按 sequence 幂等拼接。
3. `Last-Event-ID` 与 query cursor 统一语义，明确以较大游标还是客户端确认游标为准，并记录重连诊断。
4. 通用 SSE 支持心跳、Retry/结束原因、终态关闭、客户端断开清理；事件量大时分页回放不能超出内存。
5. `updates` 旧日志流改为 TaskRuntime 通道过滤，不再另立状态体系；保留兼容路径但输出统一 envelope。
6. 真实验证浏览器/HTTP 客户端断开后携带游标重连，检查 event_id 严格递增且正文/日志无交叉。

### P0-A4：跨项目并发与幂等隔离

**目标**：同项目同类任务去重，不同项目可并发；双 worker 不重复执行。

**步骤**：

1. 定义 scope key：`owner + project + chapter + task_type + logical_input_hash`。
2. 将重复提交幂等键写入数据库唯一约束，明确同键同任务返回 200/201 的 API 语义。
3. 对“相同 project/type 不允许并发”的业务锁使用 DB lease/唯一 active constraint，不能只用 `_PROJECT_RUNS` 字典。
4. 对不同项目设置独立 semaphore/配额，避免一个项目的大任务阻塞全部项目。
5. 双 worker 对同一 queued/stale task 做 claim race；必须只有一个成功进入 running。
6. 真实双项目并发检查所有 TaskRuntime、事件、正文版本、日志和产物引用。

### P0-A5：重启、stale 和恢复

**目标**：进程重启不重复入队，不丢 checkpoint；活任务不误杀，死任务可操作收敛。

**步骤**：

1. 启动巡检只改变心跳已超时任务；保留 live lease。
2. 将 queued/stale 扫描交给统一 dispatcher；由 claim 抢占，不由 status API 隐式重复启动。
3. 恢复必须从 TaskRuntime payload/checkpoint 装载业务输入；缺 checkpoint 结构化失败。
4. 章节、研究 artifact、文风文件、蓝图记录、导入文件分别定义产物修复动作。
5. 进程重启前后记录任务状态、事件 cursor、lease、heartbeat、attempt、产物计数。
6. 双进程启动/迁移/sweeper 只允许一个逻辑收口事件。

### P0-A6：权限与跨资源校验

**目标**：任何查询、事件、SSE、取消、恢复、重试、claim、日志操作均不泄漏他人数据。

**步骤**：

1. 所有 task_id 查询都以 owner_user_id 条件过滤；404 与 403 的选择形成统一安全策略。
2. 创建/更新任务时校验 project_id 属于 owner，chapter_id 必须属于 project_id 且不可跨项目。
3. 对管理员是否可跨用户运维建立显式 admin endpoint，不让普通 endpoint 通过空 owner 绕过隔离。
4. SSE 初始握手和每次轮询都保持同一 owner 过滤；不能只在首次握手校验。
5. 事件 payload 禁止输出密钥、Prompt 私密字段、上传原文和他人项目内容。
6. 加入不同用户同 task_id、同 project_id、同 idempotency_key 的权限测试。

### P1-A7：统一业务适配器与删除双轨

1. 先迁移 research，再迁移 style upload/profile，再迁移 blueprint/import，最后迁移 outline。
2. 每迁移一个域，新增“清空内存字典仍可运行”的回归测试。
3. 将内存 `GenerationLogService` 标记为 deprecated，仅保留迁移适配，不再接受生产写入。
4. 删除旧 status 字段映射中能覆盖 TaskRuntime 的分支；保留用户可见的 legacy projection。
5. 文档记录各域的 task_type、事件、产物、恢复点和取消安全点。

### P1-A8：可观测性与运维

1. 记录任务创建、claim、释放、stale、recover、cancel、retry、finalize 的结构化审计。
2. 指标：queued age、running age、heartbeat lag、stale count、cancel latency、retry count、SSE reconnect、event lag、duplicate claim rejection。
3. 每个失败都包含稳定 error_code、用户提示、retryable、root_cause、attempt、last_stage、result_ref。
4. 增加任务积压、sweeper 异常、事件写入失败、outbox 未收敛告警。

### P2-A9：数据库/部署强化

1. 为 MySQL/SQLite 分别执行事务隔离、锁等待、写冲突和连接泄漏压力测试。
2. 评估事件表分区/归档策略；正文增量不可无限写入主表而不清理。
3. 多实例部署下用分布式 lease 或数据库 advisory lock 约束 sweeper/dispatcher。
4. 明确 schema migration 的在线升级、回滚和旧客户端兼容窗口。

---

## 7. 逐功能优化步骤与验收标准

### 7.1 任务创建/成功

**优化逻辑**：请求校验 → 生成稳定 scope/idempotency → durable create → task_created → worker claim → 阶段事件 → 原子产物提交 → succeeded。

**验收**：

- 合法请求返回任务标识和 `queued`，数据库恰有一条任务和一条创建事件。
- worker 只能通过 claim 进入 running；重复 claim 被拒绝或幂等返回同一 lease。
- 成功后任务、终态事件、业务产物、`result_ref`、指标一致；刷新和新进程查询相同。
- 终态事件只出现一次；任务成功后再写 running/progress 被拒绝。
- 任务结束时间、耗时、token 指标非负且可追溯。

### 7.2 失败与结构化错误

**优化逻辑**：异常分类 → 释放业务资源 → 写 error_code/detail/root_cause → failed 终态 → 暴露 retryable/action。

**验收**：

- Provider 超时、格式错误、权限错误、产物提交失败分别有稳定错误码。
- 失败不会静默保持 running；不会写假成功产物。
- 可重试失败保留 checkpoint 和诊断；不可重试失败不给出误导性 retry action。
- 迟到成功回调不能覆盖 failed；只留审计事件。
- 失败任务查询、SSE、日志和业务 UI 的状态一致。

### 7.3 取消

**优化逻辑**：请求取消 → queued 无 lease 直接 cancelled；running 进入 cancelling → worker/provider 安全点停止 → 释放资源 → cancelled。

**验收**：

- queued 未领取任务取消在 2 秒内进入 cancelled，不永久停在 cancelling。
- running 任务取消先观察到 cancelling，不提前伪造业务终态；worker 收敛后才 cancelled。
- 取消后迟到 progress 不复活；迟到 success/failure 被拒绝。
- 重复取消幂等；终态取消不增加错误或新任务。
- 取消时保留已确认分段/中间产物，但不得把未确认内容伪装为正式版本。

### 7.4 重启与恢复

**优化逻辑**：进程重启 → reconcile → live lease 保留、超时任务 stale → dispatcher 扫描 queued/stale → claim → 从 checkpoint 恢复。

**验收**：

- 清空所有模块级内存字典后，任务仍能查询到正确状态、阶段、游标、checkpoint 和动作。
- 正常 live lease 不被启动巡检重置或重复启动。
- 心跳超时任务变为 stale，有 `STALE_TASK` 和最后心跳证据。
- recover 只启动一个新 worker；不从头重复已确认段。
- 进程重启后不产生重复 `task_started`/重复业务产物/重复入队。
- 缺失或损坏 checkpoint 给出明确不可恢复错误，而不是无限等待。

### 7.5 权限隔离

**优化逻辑**：JWT/开发模式策略 → owner/project/chapter 级校验 → TaskRuntime 查询条件过滤 → 事件和 SSE 二次过滤。

**验收**：

- 用户 A 不能查询、列举、读取事件、订阅 SSE、取消、恢复、重试用户 B 的任务。
- 用户 A 不能把自己的任务绑定到用户 B 的项目或章节。
- 跨 project 的 chapter_id、result_ref、payload 不可被写入或读取。
- 生产环境无 token 必须 401；无效/过期 token 不泄露任务存在性。
- 管理员运维权限必须走显式授权路径并产生审计。

### 7.6 重复提交与幂等

**优化逻辑**：客户端幂等键 → DB 唯一约束 → 同键返回原任务 → 不同 scope/用户冲突 → retry 使用独立 attempt key。

**验收**：

- 同一用户、同一 scope、同一幂等键并发提交 20 次只产生一条任务。
- 同幂等键但不同 task_type/owner/scope 必须 409，不能返回他人任务。
- 网络超时后客户端重放请求不会重复生成正文或研究产物。
- retry 请求重复提交只产生一次新的 attempt 事件链。

### 7.7 SSE 断线、回放与通道分离

**优化逻辑**：首次握手权限校验 → 从游标读取持久化事件 → 按 event_id/sequence 发送 → 心跳 → 断线 → Last-Event-ID 续接 → 终态关闭。

**验收**：

- 初始连接收到游标之后的所有事件，按 event_id 严格递增。
- 人工断开后带 `Last-Event-ID` 重连：无漏片、无重片；重复片段按客户端幂等键可安全丢弃。
- 心跳不改变任务 `updated_at`/业务进度，不污染正文。
- `content_delta` 只进入正文通道；`log`/diagnostic 只进入日志通道。
- 任务终态且无剩余事件时 SSE 关闭；连接不会永久轮询。
- 500+ 事件分页回放不会只返回前 500 后静默终止，必须可继续游标读取。

### 7.8 跨项目并发

**验收**：

- 项目 A、B 各提交至少两类任务，能并发运行且各自完成。
- A 的事件、正文、日志、artifact、result_ref 不在 B 的查询或 SSE 中出现。
- 同一项目同类 active 任务按明确策略去重或排队，不依赖单进程字典。
- 双 worker 抢同一任务只有一个获得 lease；另一个得到可解释冲突。
- 一个项目取消不影响另一项目的任务和连接。

---

## 8. 真实入口脚本建议

现有相关脚本：

- `backend/scripts/real_asgi_generation_smoke.py`
- `backend/scripts/real_asgi_longform_generation_smoke.py`
- `backend/scripts/real_asgi_concurrent_generation_smoke.py`

建议新增领域 A 专用脚本（建议放在 `backend/scripts/real_asgi_task_runtime_acceptance.py`，仅作为后续执行计划，不在本次审查中创建）：

### 8.1 单任务完整生命周期

```powershell
backend\.venv\Scripts\python.exe backend\scripts\real_asgi_task_runtime_acceptance.py --case lifecycle --db isolated-task-runtime.db
```

步骤：登录/获取测试用户 → 创建 project → POST `/api/task-runtime/tasks` → 记录 task_id → claim → progress/log/content_delta → heartbeat → finalize → GET task/events → SSE 终态关闭。

### 8.2 取消竞态

```powershell
backend\.venv\Scripts\python.exe backend\scripts\real_asgi_task_runtime_acceptance.py --case cancel-race --db isolated-cancel.db
```

并发发起 cancel 与迟到 progress/success，验证最终状态只可能是 cancelling/cancelled，不能 running/succeeded 复活。

### 8.3 重启恢复

```powershell
backend\.venv\Scripts\python.exe backend\scripts\real_asgi_task_runtime_acceptance.py --case restart-recovery --db isolated-restart.db
```

第一进程创建并 claim 后停止；第二进程清空所有模块缓存，执行 reconcile/status/recover；验证 checkpoint、事件 cursor、attempt 和业务产物。

### 8.4 SSE 断线续接

```powershell
backend\.venv\Scripts\python.exe backend\scripts\real_asgi_task_runtime_acceptance.py --case sse-reconnect --db isolated-sse.db
```

连接读取 N 个事件后主动断开，携带最后一个 `id` 重连；比较服务端事件集合与客户端最终拼接结果，要求集合等价、顺序正确。

### 8.5 双项目/双 worker 并发

```powershell
backend\.venv\Scripts\python.exe backend\scripts\real_asgi_task_runtime_acceptance.py --case isolation --db isolated-concurrency.db
```

以两个项目、两个用户、两个 worker 进程执行正文/研究/文风等任务，验证数据库 claim、owner、事件、正文和 artifact 隔离。

### 8.6 执行纪律

- 真实脚本必须串行执行；并发只在脚本内部按测试场景控制，避免多个 smoke 脚本共享 Provider/数据库造成误判。
- 每次输出脱敏 JSON：`case/task_id/owner/project/status/stages/event_count/content_event_count/log_event_count/reconnect_count/retry_count/elapsed_ms/db_evidence`。
- 每次验收使用隔离 SQLite 或专用测试库；不得读取或输出真实密钥、token、用户正文。
- 失败不得改写为通过；保留失败数据库和事件快照供复盘。

---

## 9. 量化评分表

总分 100；P0 核心项任一低于 90 不得进入下一阶段。评分必须基于实测证据，不能以单元测试数量替代真实链路。

| 维度 | 权重 | 90 分达标线 | 评分证据 |
|---|---:|---|---|
| 状态机正确性 | 20 | 所有合法/非法转移矩阵通过；无终态复活 | DB 最终状态、事件序列、竞态测试 |
| 取消与资源收敛 | 12 | queued/running/cancelling 三种路径均可收口；无永久 cancelling | cancel latency、worker/资源释放日志 |
| 重启/stale/恢复 | 15 | 清空内存、多进程重启后可查询/恢复；不重复入队 | 前后 DB 快照、attempt、checkpoint、产物 |
| SSE 回放可靠性 | 15 | 断线续接无漏片/重片；终态自动关闭 | event_id 集合对比、连接记录 |
| 正文/日志通道隔离 | 8 | content 与 log 完全分离，分片可幂等拼接 | 通道事件计数、前端接收快照 |
| 幂等与重复提交 | 10 | 20 次并发重复只产生一条逻辑任务/一次 retry | 唯一键、task 数、attempt 事件 |
| 权限与数据隔离 | 10 | 跨用户/跨项目所有读写/SSE 均拒绝且不泄露 | 401/403/404 记录、payload 检查 |
| 跨项目并发与租约 | 5 | 双 worker 单 claim；双项目互不阻塞/串数据 | lease_owner、耗时、任务矩阵 |
| 可观测性与错误可操作性 | 3 | 错误码、阶段、retryable、诊断和审计齐全 | 结构化日志/任务 DTO |
| **合计** | **100** | **≥90 且无 P0** | 发布审计记录 |

### 9.1 单功能评分模板

```text
功能：
范围：
测试入口：
状态机正确性：__/20
取消/恢复：__/20
SSE/事件：__/15
权限/隔离：__/15
幂等/并发：__/15
错误/观测：__/10
性能：__/5
总分：__/100
证据：
阻塞问题：
下一轮动作：
```

---

## 10. 测试矩阵与反向验证要求

### 10.1 必测矩阵

| 场景 | 成功 | 失败 | 取消 | 重启 | 权限 | 重复提交 |
|---|---|---|---|---|---|---|
| 正文生成 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 长篇总纲/章节纲 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 蓝图 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 研究 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 文风上传/画像 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 旧稿导入 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 通用日志/SSE | ✓ | ✓ | N/A | ✓ | ✓ | ✓ |

### 10.2 每个修复必须做的反向验证

1. 先用失败用例证明现有缺陷或未覆盖边界。
2. 添加回归测试。
3. 故意删除/绕过修复逻辑，确认测试确实失败。
4. 恢复修复后运行定向测试。
5. 再运行后端正式命令：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

6. 运行 `compileall`、`git diff --check`，再执行真实入口脚本。

---

## 11. 子代理/并行执行分工建议

本领域后续可以并行安排以下独立代理，但所有代理必须只提交自己负责的代码和测试，最终由一个集成代理执行全量门禁与真实入口验收：

```text
领域 A-1 TaskRuntime 状态机代理
  ├─ 状态转移/CAS/attempt/lease
  └─ 状态矩阵与竞态测试

领域 A-2 SSE 代理
  ├─ 统一 envelope/channel/sequence
  ├─ Last-Event-ID/心跳/终态
  └─ 断线重连实测

领域 A-3 研究/文风任务迁移代理
  ├─ 删除状态读取对内存 job 的依赖
  └─ 重启/取消/权限回归

领域 A-4 蓝图/导入/章节纲迁移代理
  ├─ TaskSpec/payload/checkpoint
  └─ 重复提交/进程重启/产物一致性

领域 A-5 权限与并发代理
  ├─ owner/project/chapter 组合校验
  ├─ 双用户/双项目/双 worker
  └─ 数据泄漏审计

集成验收代理
  ├─ 串行定向测试
  ├─ 全量 pytest
  ├─ 真实 ASGI/SSE 脚本
  └─ 评分与未决风险台账
```

代理边界：A-1/A-2 先定义公共契约；A-3/A-4 依赖契约后迁移；A-5 可与 A-3/A-4 并行写权限测试；集成代理不得以测试替身代替真实入口。

---

## 12. 未决风险台账

| 编号 | 风险 | 级别 | 当前证据 | 解除条件 |
|---|---|---|---|---|
| R-A-001 | 多业务域仍保留内存 job 状态/调度集合 | P0 | 静态检索确认 research/style/novels/writer 多组符号 | 六类任务清空内存后真实恢复通过 |
| R-A-002 | TaskRuntime 状态转移跨进程 CAS 覆盖不完整 | P0 | 现有测试偏服务级，未覆盖真实双 session 所有终态竞态 | 双 worker + cancel/finalize/stale 竞态通过 |
| R-A-003 | `updates` SSE 与 TaskRuntime SSE 事件视图不一致 | P0 | 两路由筛选集合不同 | 统一 channel/envelope 并完成前端通道验收 |
| R-A-004 | 正文 `content_delta` 的分片顺序/幂等字段尚未在通用 DTO 固化 | P0 | schema 有事件类型但无 sequence/segment contract | 2 万字分段断线续接通过 |
| R-A-005 | 取消请求两阶段提交中断可能留下 cancelling | P0 | `request_cancel` 先写 cancelling，再按条件写 cancelled | 重启巡检/worker 对 cancelling 有确定收敛策略 |
| R-A-006 | claim 成功后 started 事件写入失败可能造成状态/事件不一致 | P1 | `claim` 状态更新与事件追加分步 | outbox/补偿或原子事务实测通过 |
| R-A-007 | retry 复用 task_id，attempt 语义未独立固化 | P1 | `retry()` 增加 retry_count 并回 queued | attempt 级事件/lease/产物隔离通过 |
| R-A-008 | 普通任务 API 暴露 `POST /events`，内部事件写入边界不清 | P1 | 路由允许当前用户提交任意枚举事件 | 限制内部事件或加入签名/worker 权限 |
| R-A-009 | `stale` 同时表达超时和可恢复态，用户动作语义可能混淆 | P1 | schema 只有单一 stale 状态 | 增加 reason/recovery_action 并完成 UI/脚本验收 |
| R-A-010 | 内存 GenerationLogService 与持久化日志双轨并存 | P1 | 静态确认四组内存结构 | 生产调用路径全部切换并删除/隔离旧服务 |
| R-A-011 | 多实例 sweeper/迁移/SQLite 写竞争尚无压力证据 | P1 | 仅静态配置和定向测试 | 双进程/多实例 DB 压测及故障注入通过 |
| R-A-012 | 真实 Provider、真实浏览器 SSE、真实进程重启尚未纳入本领域正式门禁 | P0 | 本次仅执行定向 pytest/compileall | 真实脚本输出脱敏证据且连续两轮通过 |
| R-A-013 | 开发环境无 Bearer 时保留 system user 回退，生产配置误用会扩大风险 | P1 | `get_current_user` 明确按 environment 分支 | 生产启动强制配置检查并完成未授权 HTTP 验收 |
| R-A-014 | 任务 payload 自由 JSON 可能保存过大正文/敏感信息 | P2 | ORM payload 为 JSON，无大小/字段策略 | schema 版本、大小上限、敏感字段过滤和外置 artifact |

---

## 13. 当前审查结论与下一阶段门禁

### 当前可确认

- TaskRuntime 表、事件表、状态枚举、租约、心跳、重试和 stale 基础实现存在。
- 定向 TaskRuntime/巡检/持久化日志测试 32 项通过。
- 定向 TaskRuntime 路由/研究/章节大纲重启恢复测试 20 项通过。
- Python `compileall` 通过。
- owner 过滤、项目创建校验、取消迟到进度保护、stale 重复巡检幂等已有回归证据。

### 当前不可确认

- 所有后台任务都以 TaskRuntime 为唯一状态真相源。
- 多进程/多 worker 下全部状态转移和终态提交无竞态漏洞。
- 所有 SSE 断线续接无漏片/重片，尤其是正文长文本分片。
- 真实 Provider、真实浏览器、真实进程重启和双项目并发全链路通过。
- 全量后端 pytest、前端门禁和发布级验收连续两轮通过。

### 领域 A 下一阶段准入条件

1. 先完成 R-A-001、R-A-002、R-A-003、R-A-004、R-A-005、R-A-012 六项 P0。
2. 六类任务全部通过 success/failure/cancel/restart/permission/duplicate 六维矩阵。
3. 真实入口评分达到 90/100，且无永久卡死、静默失败、取消复活、跨项目泄漏、重复入队。
4. 集成代理执行正式后端命令和真实 ASGI 脚本；不得只提交计划或测试报告。

