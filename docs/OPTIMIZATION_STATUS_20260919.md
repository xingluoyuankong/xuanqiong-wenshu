# 玄穹文枢全面优化总审查（2026-09-19）

## 当前发布锚点

- 服务器：`qwenpaw-sbs-prod-szckq`
- 仓库分支：`codex/server-us010-r1`
- GitHub：`https://github.com/xingluoyuankong/xuanqiong-wenshu.git`
- 当前 HEAD：`a65d3c7`，本地服务器分支与 `origin/codex/server-us010-r1` 同步
- 受管公网后端：`0.0.0.0:8013`
- 受管内网后端：`127.0.0.1:8099`
- 前端：`127.0.0.1:5174`
- 生产 SQLite 未执行迁移，R30 计划仍是只生成、不执行

## 已完成并有当前证据的能力

| 区域 | 状态 | 当前证据 |
|---|---|---|
| 预算门前后端闭环 | PASS | live HTTP smoke：登录、创建项目、预算更新、蓝图保存、生成请求、门禁状态和删除均符合契约 |
| 服务器运行时 | PASS | 8013/8099 使用 `scripts/server_runtime.sh` 解析同一依赖路径，manifest 与 HEAD 对齐 |
| 后端回归 | PASS | `bash scripts/test_backend.sh`：`274 passed, 1 warning` |
| 前端类型 | PASS | `npm run type-check` |
| 前端单元回归 | PASS | `23 files passed, 117 tests passed` |
| 前端生产构建 | PASS | `4710 modules transformed`，构建成功 |
| 前端 WritingDesk 懒加载边界 | PASS | `INEFFECTIVE_DYNAMIC_IMPORT` 已消失；WritingDesk JS 约 145.86 kB 降至 88.66 kB |
| 服务拓扑与 keepalive | PASS | `bash scripts/audit_server_topology.sh` 输出 `AUDIT_RESULT=PASS` |
| SQLite 完整性/漂移/baseline | PASS | topology audit 中 integrity、schema drift、baseline 均通过 |
| migration provenance | PASS | fragment hash 和 manifest provenance 通过 |
| 真实 Provider 文学产物 | PARTIAL | 旧轮次有真实非空产物证据；本轮未重新触发计费型真实生成，不把旧证据升级为当前完成 |

## 最近已推送轮次

### R30：迁移计划与 provenance

提交：`a03bf2d`

- 新增 `scripts/plan_migration.py`；
- 新增 `docs/OPTIMIZATION_ROUND_20260919_MIGRATION_PLAN.md`；
- SQLite/MySQL 计划都保持 `execute=false`；
- 当前状态为 `blocked_by_missing_runner`，未修改生产数据库。

### R31：统一后端测试运行时

提交：`d58d965`

- 新增 `scripts/test_backend.sh`；
- 测试复用生产运行时的 `PYTHONPATH` 和依赖选择；
- 解决默认 `.venv` 不含外置 FastAPI/SQLAlchemy 等包导致的收集失败；
- 新增 `docs/OPTIMIZATION_ROUND_20260919_TEST_RUNTIME.md`。

### R32：前端 WritingDesk 懒加载边界

提交：`7e54456`

- `WritingDesk.vue` 从 barrel 导入改为直接导入实际使用组件；
- 保留 barrel 对外导出兼容性；
- 去除重复静态/动态弹窗依赖；
- 新增 `docs/OPTIMIZATION_ROUND_20260919_FRONTEND_CHUNKS.md`。

## R38–R41 最新进展

### R38：RAG embedding 降级可观测性

提交：`f82351f`，证据文档更新提交：`3636420`。

- `ChapterRAGContext` 增加 `degraded`、`degradation_reason`、`embedding_status`；
- `retrieval_stats` 写入持久化 runtime metadata；
- 真实章节 smoke：`waiting_for_confirm`、1 个候选、521 字符、23093 tokens、3 条 usage；
- live metadata 明确记录 `degraded=true`、`EMBEDDING_UNAVAILABLE`；
- 测试项目已删除，SQLite 零孤儿。

### R39：embedding provider 失败分类

提交：`85f7a66`，live 证据提交：`d574718`。

- 401/403/timeout/connection/empty response 具有稳定分类码；
- 当前真实探针分类为 `EMBEDDING_AUTHENTICATION_FAILED`；
- 专项 `71 passed`，后端全量 `279 passed`。

### R40：embedding 专用凭据隔离

提交：`a9aa6fe`，live 证据提交：`662946d`。

- 缺少独立 `embedding.api_key` 时不再回退复用 chat key；
- 本地直接返回 `EMBEDDING_CONFIG_MISSING`；
- 不向错误 embedding endpoint 发送 chat 凭据；
- 专项 `75 passed`，后端全量 `283 passed`。

### R41：只读 embedding 能力探针

提交：`d10bfcc`。

新增：

```text
scripts/probe_embedding.py
scripts/probe_embedding.sh
docs/OPTIMIZATION_ROUND_20260919_EMBEDDING_PROBE.md
```

当前探针实测：

```text
vector_nonempty=false
vector_dimension=0
code=EMBEDDING_CONFIG_MISSING
novel_projects=0
chapters=0
token_budgets=0
```

不会创建项目、章节、预算或正文生成任务。

## R42 最新进展：SQLite migration copy dry-run

提交：`a65d3c7`。

新增：

```text
scripts/migration_copy_dry_run.py
scripts/migration_copy_dry_run.sh
docs/OPTIMIZATION_ROUND_20260919_MIGRATION_COPY_DRY_RUN.md
```

当前真实演练结果：

```text
status=PASS
source_unchanged=true
rollback_verified=true
provenance_failures=[]
```

`add_chapter_outline_metadata.sql` 在当前库中已存在，因此标记为 `already_applied_on_copy`；其余三个含 MySQL 方言的 fragment 均保持 skipped，没有执行生产迁移。生产 SQLite integrity、schema baseline 和 topology audit 均通过。

## R43 最新进展：服务器依赖运行时可审计

提交：`90a6b57`。

新增：

```text
deploy/runtime_dependencies.json
scripts/audit_runtime_dependencies.py
scripts/audit_runtime_dependencies.sh
docs/OPTIMIZATION_ROUND_20260919_RUNTIME_DEPENDENCY_MANIFEST.md
```

审计内容：

- runtime/test 依赖版本；
- 实际 distribution source root；
- 关键模块 import；
- 外置容器挂载路径的 canonical resolve；
- 版本漂移和来源漂移的失败返回。

真实服务器结果：

```text
status=PASS
failures=[]
fastapi=0.110.0
sqlalchemy=2.0.44
uvicorn=0.29.0
openai=2.3.0
pytest=8.4.1
pytest-asyncio=1.1.0
```

生产依赖实际由容器 canonical path 提供，manifest 保留 `/app/user-packages/python` 别名并通过 realpath 校验，避免容器挂载 ID 变化造成误报。后端全量仍为 `283 passed`，拓扑审计通过。

## R44 最新进展：Naive UI 按组件拆分 chunk

提交：`19ac1d2`。

- 修改前端 Vite `manualChunks`，按 `naive-ui/es/<component>` 拆分；
- 共享内部模块归入 `naive-ui-runtime`；
- `type-check` 通过；
- 前端 `23 files / 117 tests` 通过；
- 生产构建通过；
- 原约 `557.33 kB` 的单一 Naive UI chunk 消除；
- 最大组件 chunk 为 `naive-data-table`，约 `301.06 kB`；
- 构建不再出现 `Some chunks are larger than 500 kB` 或 `INEFFECTIVE_DYNAMIC_IMPORT`。

真实浏览器请求瀑布和 `naive-data-table` 内部继续拆分仍列入后续 P1，不把静态构建体积替代真实首屏性能证据。

## 仍需完成的优化任务与验收标准

### P0：真实 Provider 当前入口复验（R37 已取得当前证据，继续做多轮稳定性复验）

**任务**：在当前 `7e54456` 服务上重新做一次最小计费/配额可控的真实章节生成，记录 provider、model、attempt、SSE terminal、非空正文、token usage 和数据库归属。

**通过条件**：

1. 真实 provider 返回非空、可解析正文；
2. SSE 最终事件唯一且为 `complete` 或有结构化 `failed` terminal；
3. `token_usages` 与对应 project/user/attempt 关联；
4. 不把 health、stub、队列入列或 HTTP 200 计为真实成功；
5. 余额/认证/模型不可用时保留原始状态和失败原因。

### P0：迁移 runner 与回滚演练（SQLite copy dry-run 已完成，MySQL runner 仍未建立）

**任务**：先为 SQLite 和 MySQL 分别建立可重放的 copy dry-run、备份、升级、回滚和人工 review 证据；当前生产库保持不变。

**通过条件**：

1. fragment hash 与 manifest/baseline 绑定；
2. dry-run 只作用于副本；
3. upgrade 与 rollback 前后 schema fingerprint 可比较；
4. 失败时生产库零写入；
5. 获得人工审查记录后才允许生成可执行计划。

### P0：embedding 专用配置补齐与真实非空向量验收

**当前状态**：配置缺少独立 embedding key，探针稳定返回 `EMBEDDING_CONFIG_MISSING`。下一步需要配置专用 key/base URL 后，用 `scripts/probe_embedding.sh` 验证非空向量和维度，再验证 RAG 命中质量。

### P1：服务器 Python 依赖可重建性（R43 审计清单已完成，依赖重建仍未完成）

**任务**：把当前 `/app/user-packages/python` 与 `/app/venv/...` 的运行时依赖来源转成可检查、可重建的部署契约；R31 的测试入口统一只是过渡，不复制未知环境包进仓库。

**通过条件**：

1. 新机器按文档可安装同版本依赖；
2. `scripts/server_runtime.sh` 在干净环境能明确失败并给出缺失包；
3. 后端测试和服务启动使用同一锁定依赖集合；
4. 版本漂移进入 manifest/audit。

### P1：Naive UI 首屏拆分（R44 组件 chunk 已完成，真实请求瀑布仍待验证）

**任务**：分析 `naive-ui` 约 `557.33 kB`（gzip 约 `156.37 kB`）的实际首屏请求，不调高 warning 阈值掩盖问题；仅在确认路由加载收益后拆分。

**通过条件**：

1. 首屏/写作台/管理页请求瀑布分别有基线；
2. 按功能域拆分后首屏传输量下降；
3. `type-check`、117 前端测试和 build 全通过；
4. 交互页首次打开没有组件加载错误。

### P2：构建与测试噪声收敛

- 处理 Vitest `--localstorage-file` 无有效路径警告；
- 评估 passlib `crypt` 弃用警告的依赖升级窗口；
- 记录构建 plugin timing，但不以调高阈值代替优化。

## 受保护不变量

1. 8013 是公网入口，8099 只监听回环地址，5174 是前端入口，角色不混用；
2. 每次提交后，受管进程的 `process_commit == current_commit`；
3. 生产数据库迁移前必须有备份、copy dry-run、rollback 和人工 review；
4. 不提交 `storage/*.db-wal`、`storage/*.db-shm`；当前这两个文件仍只存在服务器本地；
5. 不用历史绿灯、stub、健康 200 或队列响应替代当前真实 Provider 章节成功；
6. 每个优化轮次都要有对应 `docs/OPTIMIZATION_ROUND_*.md` 或本总审查更新，并推送 GitHub。

## 当前未提交资产

```text
storage/e2e_us006.db-shm
storage/e2e_us006.db-wal
```

这是测试运行时 SQLite 临时文件，已明确排除出 Git 提交；清理前需要确认没有活动连接和写入者。