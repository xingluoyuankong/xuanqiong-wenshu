# 玄穹文枢全面优化总审查（2026-09-19）

## 当前发布锚点

- 服务器：`qwenpaw-sbs-prod-szckq`
- 仓库分支：`codex/server-us010-r1`
- GitHub：`https://github.com/xingluoyuankong/xuanqiong-wenshu.git`
- 当前 HEAD：`26225c8`，本地服务器分支与 `origin/codex/server-us010-r1` 同步
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

## R45–R46 最新进展：生成延迟基线与短章 mission 尾部优化

### R45：生成阶段 p50/p95 报告

提交：`cf4a7fd`。

新增只读报告入口：

```text
scripts/report_generation_latency.py
scripts/report_generation_latency.sh
```

基于 25 条真实 pipeline 记录的当前历史基线：

```text
pipeline total p50=16078.90ms p95=260925.81ms
 generate_mission p50=29.31ms p95=30005.88ms
 prepare_context p50=1554.10ms p95=32524.98ms
 generate_variants p50=280.62ms p95=69194.65ms
```

报告不发起 Provider 请求、不修改数据库。R45 建立的是基线，不宣称已经改善性能。

### R46：短章节导演脚本尾部收敛

提交：`ecfb94f`。

对于 `target_word_count < 1200` 的可选导演脚本阶段：

- timeout 从 30 秒降至 20 秒；
- 关闭同模型重复网络重试；
- 保留 JSON schema 修复和确定性 fallback；
- 长章节 timeout 档位、正文生成、质量门和取消 drain 不变。

验证：

```text
后端全量：283 passed, 1 warning
AUDIT_RESULT=PASS
```

由于 R46 尚未触发新的计费型真实章节生成，R45 的历史 p50/p95 仍作为基线；下一次真实 smoke 后再用同一报告入口做前后对比。

## R46 Live 结果更新

R46 提交：`ecfb94f`；live 证据文档提交：`7aaaa9e`。

短章节真实 Provider smoke 已完成：

```text
generate_mission duration_ms=20002.29
PROVIDER_TIMEOUT timeout_seconds=20.0
prepare_context duration_ms=20773.60
候选版本：1
正文长度：505 字符
total_tokens：16568
usage records：2
最终阶段：waiting_for_confirm
临时项目删除：HTTP 200
```

数据库清理后：

```text
novel_projects=0
chapters=0
token_budgets=0
orphan_project_rows={}
```

这证明 R46 的短章 mission 超时收敛已经在真实线上入口生效，同时确定性 fallback、正文生成、usage attribution 和项目清理保持正常。R45 历史延迟基线仍保留用于前后对比，后续继续采集新样本。

## R47–R49 最新进展

### R47：Prepare Context 子阶段计时

提交：`3f1f130`；live 证据提交：`1000207`。

真实 500 字 smoke 证明：

```text
pre_mission_context=94.58ms
post_mission_context=650.80ms
prepare_context=654.88ms
generate_mission=20004.85ms
generate_variants=59412.75ms
```

此前 `prepare_context` 的 20–56 秒长尾包含 mission 等待，R47 已消除统计双计数。当前真实瓶颈是 Provider mission 和正文候选生成，不是上下文装配。

### R48：短章节正文 Token Ceiling

提交：`fc80cc4`；live 证据提交：`f160e11`。

短章节 `target_word_count < 1200` 的正文 `max_tokens` 改为 `max(1800, target * 2.5)`。真实 500 字 smoke：

```text
候选版本=1
正文长度=597
generate_variants=55661.75ms
total_tokens=16011
usage_records=2
```

项目清理和 SQLite integrity 通过。

### R49：延迟报告覆盖受管服务日志

提交：`4cab24d`。

报告默认同时扫描：

```text
backend/logs/**/*.log
logs/**/*.log
```

当前真实报告：

```text
source_files=24
pipeline_samples=28
parse_errors=[]
status=PASS
```

这样 R47/R48 的 `logs/public-backend-8013` 真实运行日志不会漏出统计基线。

## R50–R52 最新进展：候选长尾与护栏回炉

### R50：候选级耗时观测

提交：`43022ba`。

runtime 新增扁平 `candidate_timings`，记录每个候选的：

```text
generation_ms
guardrail_check_ms
guardrail_rewrite_ms
total_ms
```

R50 真实证据：

```text
generation_ms=61358.25
guardrail_check_ms=0.22
guardrail_rewrite_ms=19637.22
total_ms=80182.08
```

这证明单候选正文 Provider 请求和护栏回炉共同构成 `generate_variants` 长尾。

### R51：候选耗时 runtime 序列化修复

提交：`358f054`。

R50 初版嵌套 timing 在 runtime compact 后变成 `[object:5]`。R51 将其改成扁平列表，保留完整数值。后端全量：`285 passed`。

### R52：短章节护栏回炉 ceiling

代码提交：`a1a851c`；live 证据提交：`af03b3c`。

短原文的护栏回炉 `max_tokens` 根据原文长度动态上限，避免 500 字短章固定使用 8000 token。

R52 真实 smoke：

```text
候选版本：1
正文长度：491 字符
generation_ms=54869.49
guardrail_check_ms=0.24
guardrail_rewrite_ms=0.0
total_ms=54874.86
项目删除：HTTP 200
SQLite 零残留
```

该样本未触发回炉，因此只证明动态 ceiling 不影响正常路径；R51 的回炉长尾仍保留为对比基线，后续需要可控违规 fixture 或更多真实样本验证回炉收益。

## R50–R53 最新进展

### R50–R51：候选级耗时与 runtime 序列化

提交：`43022ba`、`358f054`。

真实候选级数据：

```text
generation_ms=61358.25
guardrail_check_ms=0.22
guardrail_rewrite_ms=19637.22
total_ms=80182.08
```

R51 修复嵌套 runtime compact 丢失问题，将候选 timing 改成扁平记录。

### R52：短章护栏回炉 ceiling

提交：`a1a851c`；live 证据：`af03b3c`。

500 字短章回炉 ceiling 按原文长度动态计算。正常路径真实 smoke：

```text
generation_ms=54869.49
guardrail_check_ms=0.24
guardrail_rewrite_ms=0.0
正文长度=491
```

该样本未触发回炉，不能单独证明回炉长尾已改善；R51 的回炉长尾仍保留作基线。

### R53：MySQL migration 只读 readiness audit

提交：`7f0a587`。

新增：

```text
scripts/audit_mysql_migration_readiness.py
scripts/audit_mysql_migration_readiness.sh
docs/OPTIMIZATION_ROUND_20260920_MYSQL_MIGRATION_READINESS.md
```

真实审计结果：

```text
execute=false
connected=false
writes_performed=false
db_provider=sqlite
mysql_password_set=false
provenance_failures=[]
status=BLOCKED
```

R53 明确证明当前 MySQL migration runner 不应执行；SQLite copy dry-run 已完成，MySQL 仍等待独立目标配置、备份、copy dry-run、rollback 和人工 review。

## R54 最新进展：候选级延迟聚合

提交：`6a756be`。

延迟报告现在解析 `Pipeline candidate timings`，并单独输出候选级 p50/p95：

```text
candidate_sample_count=3
generation_ms p50=60538.99 p95=61276.32
guardrail_check_ms p50=0.24 p95=0.34
guardrail_rewrite_ms p50=0.0 p95=17673.5
total_ms p50=61363.72 p95=78300.24
```

结论：

- Provider generation 是主要耗时来源；
- 护栏回炉只在部分样本触发，但触发时约 17–20 秒；
- 本轮只增强报告聚合，不改变生成行为；
- 后续优化需要分别针对 Provider 请求长尾和可控违规回炉，不把二者混成一个“generate_variants”数字。

## R50–R54 最新进展

### R50/R51：候选级耗时和 runtime 序列化

提交：`43022ba`、`358f054`。

真实候选数据：

```text
generation_ms=61358.25
guardrail_check_ms=0.22
guardrail_rewrite_ms=19637.22
total_ms=80182.08
```

R51 将候选 timing 改为扁平 runtime 结构，修复 `[object:5]` 丢失数值的问题。

### R52：短章护栏回炉 token ceiling

提交：`a1a851c`；live 证据：`af03b3c`。

短章回炉上限按原文长度动态计算。正常路径真实 smoke 的 `guardrail_rewrite_ms=0`；R51 的回炉长尾继续保留为基线，后续需要可控违规 fixture 或更多样本验证收益。

### R53：MySQL readiness

提交：`7f0a587`。

只读 readiness 当前明确为：

```text
execute=false
connected=false
writes_performed=false
db_provider=sqlite
mysql_password_set=false
provenance_failures=[]
status=BLOCKED
```

SQLite copy dry-run/rollback 已通过；MySQL runner 未执行。

### R54：候选级 p50/p95 聚合

提交：`6a756be`，当前 HEAD 为综合状态更新后的 `b60c4ec`。

当前候选样本：3 条。

```text
generation_ms p50=60538.99 p95=61276.32
guardrail_check_ms p50=0.24 p95=0.34
guardrail_rewrite_ms p50=0.0 p95=17673.5
total_ms p50=61363.72 p95=78300.24
```

R54 只读解析 `backend/logs/**/*.log` 与受管服务 `logs/**/*.log`，不触发新的 Provider 请求。

## R55 最新进展：Embedding Health Check API

提交：`bb6c624`。

新增只读接口：

```text
GET /api/llm-config/embedding-health-check
```

真实 HTTP 验收：

```text
login=200
embedding_health=200
code=EMBEDDING_CONFIG_MISSING
vector_nonempty=false
vector_dimension=0
```

接口复用用户鉴权和 LLMService，不启动章节生成，不创建项目/章节/预算，不返回任何密钥或上游响应正文。配置独立 embedding key/base URL 后可直接用该接口验证非空向量和维度。

## R55 最新进展：Embedding Health Check API

提交：`bb6c624`；live 证据与综合状态更新提交：`0030049`。

新增只读接口：

```text
GET /api/llm-config/embedding-health-check
```

真实 HTTP 验收：

```text
login=200
embedding_health=200
vector_nonempty=false
vector_dimension=0
code=EMBEDDING_CONFIG_MISSING
```

接口复用用户鉴权和 `LLMService`，不启动章节生成，不创建项目/章节/预算，不返回 API key 或上游响应正文。配置独立 embedding key/base URL 后可直接用同一接口验证非空向量和维度。

## R56 最新进展：Admin Vendor 首屏预加载边界

提交：`c8ef176`。

R56 移除 Vite 专用 `admin-vendor` manual chunk 归类。构建通过后，`dist/index.html` 已不再预加载管理域 vendor，AdminView 仍保持异步路由和异步面板边界。

```text
前端 type-check：PASS
前端测试：23 files / 117 tests passed
生产构建：PASS
Some chunks are larger than 500 kB：无
INEFFECTIVE_DYNAMIC_IMPORT：无
```

这证明公共入口 preload 依赖减少；真实浏览器 LCP/网络瀑布仍需后续独立采集。

## R55–R56 最新进展

### R55：Embedding Health Check API

提交：`bb6c624`；live 与综合状态提交：`0030049`、`19d2e0d`。

新增只读接口：

```text
GET /api/llm-config/embedding-health-check
```

真实 HTTP 结果：

```text
login=200
embedding_health=200
vector_nonempty=false
vector_dimension=0
code=EMBEDDING_CONFIG_MISSING
```

不启动章节生成、不创建项目/章节/预算，不返回 API key 或上游响应正文。配置独立 embedding key/base URL 后可用同一接口做非空向量和维度验收。

### R56：Admin Vendor 首屏预加载边界

提交：`c8ef176`；综合状态提交：`520de7a`。

- 移除 Vite 专用 `admin-vendor` manual chunk 归类；
- `dist/index.html` 不再 modulepreload 管理域 vendor；
- AdminView 继续保持异步路由和异步面板；
- type-check、23 files/117 tests、build 全部通过；
- `>500 kB` 和 `INEFFECTIVE_DYNAMIC_IMPORT` 警告均无。

R56 证明公共入口 preload 边界改善；真实浏览器 LCP/网络瀑布仍需独立采集。

## R56–R59 最新进展

### R56：Admin Vendor 首屏 preload 边界

提交：`c8ef176`；综合状态提交：`520de7a`。

公共入口已移除 `admin-vendor` modulepreload，AdminView 继续保持异步路由/面板加载。前端 type-check、117 个测试和 build 全部通过。

### R57：runtime/test 依赖 lock 分层

提交：`2243953`。

- runtime snapshot：94 distributions；
- test snapshot：6 distributions；
- runtime/test overlap：空；
- canonical source root、版本和 import：全部 PASS；
- 后端全量：287 passed。

### R58：管理台 Embedding health card

提交：`bb6c624`；状态/live 提交：`0030049`、`19d2e0d`。

系统配置页增加手动 Embedding 能力检查卡片，调用只读 health-check API；当前实际返回 `EMBEDDING_CONFIG_MISSING`，不回显密钥、不启动章节生成。

### R59：前端入口 preload budget gate

提交：`6da689f`。

新增 `scripts/audit_frontend_entry.sh`，当前真实结果：

```text
index_bytes=828
modulepreload_count=4
modulepreload_bytes=198345
admin_vendor_preloads=[]
failures=[]
status=PASS
```

该门禁检查 dist 入口引用资源存在，并防止 `admin-vendor` 重新进入公共入口 preload；它不替代真实浏览器 LCP/网络瀑布验收。

## R60 最新进展：MySQL 迁移默认执行闸门

提交：`4345271`。

`backend/scripts/migrate_sqlite_to_mysql.py` 现在默认只输出 preview：

```text
execute=false
connected=false
writes_performed=false
status=preview_only
table_count=57
```

真实 preview 使用带密码的目标 URL 验收时，输出只显示：

```text
mysql+asyncmy://root:***@127.0.0.1:3306/xuanqiong_wenshu
```

默认不会连接、建库、建表或复制数据。真实执行必须显式传入 `--apply --backup-manifest`，且 backup manifest 必须声明 `backup_completed=true`。

预览还暴露了 MySQL 迁移未完成的结构风险：`chapters` 与 `chapter_versions` 存在无法自动排序的互相依赖 FK cycle，后续必须人工设计建表/约束顺序和 rollback 方案，当前不进入 apply。

后端全量已达到 `289 passed`，SQLite integrity、topology、dependency audit 继续通过。

## R60 最新进展：MySQL 迁移默认执行闸门

提交：`4345271`；综合状态提交：`26225c8`。

`backend/scripts/migrate_sqlite_to_mysql.py` 现在默认只输出 preview：

```text
execute=false
connected=false
writes_performed=false
status=preview_only
table_count=57
```

真实 preview 使用带密码目标 URL 验收时，密码输出为 `***`，未连接 MySQL、未建库、未建表、未复制数据。真实执行必须显式 `--apply --backup-manifest`，且 backup manifest 必须声明 `backup_completed=true`。

当前 readiness 仍为：

```text
db_provider=sqlite
mysql_password_set=false
status=BLOCKED
```

preview 还暴露了 `chapters` 与 `chapter_versions` 的互相依赖 FK cycle；后续必须人工设计 MySQL 建表/约束顺序、备份和 rollback，当前不进入 apply。

## 仍需完成的优化任务与验收标准

### P0：真实 Provider 当前入口复验（R37 已取得当前证据，继续做多轮稳定性复验）

**任务**：在当前 `7e54456` 服务上重新做一次最小计费/配额可控的真实章节生成，记录 provider、model、attempt、SSE terminal、非空正文、token usage 和数据库归属。

**通过条件**：

1. 真实 provider 返回非空、可解析正文；
2. SSE 最终事件唯一且为 `complete` 或有结构化 `failed` terminal；
3. `token_usages` 与对应 project/user/attempt 关联；
4. 不把 health、stub、队列入列或 HTTP 200 计为真实成功；
5. 余额/认证/模型不可用时保留原始状态和失败原因。

### P0：迁移 runner 与回滚演练（SQLite copy dry-run 已完成，R53/R60 MySQL readiness、apply guard 与 FK cycle 仍阻断 apply）

**任务**：先为 SQLite 和 MySQL 分别建立可重放的 copy dry-run、备份、升级、回滚和人工 review 证据；当前生产库保持不变。

**通过条件**：

1. fragment hash 与 manifest/baseline 绑定；
2. dry-run 只作用于副本；
3. upgrade 与 rollback 前后 schema fingerprint 可比较；
4. 失败时生产库零写入；
5. 获得人工审查记录后才允许生成可执行计划。

### P0：embedding 专用配置补齐与真实非空向量验收（R55 health-check API 已完成，当前配置仍缺独立 key）

**当前状态**：配置缺少独立 embedding key，探针稳定返回 `EMBEDDING_CONFIG_MISSING`。下一步需要配置专用 key/base URL 后，用 `scripts/probe_embedding.sh` 验证非空向量和维度，再验证 RAG 命中质量。

### P1：服务器 Python 依赖可重建性（R43 审计清单已完成，依赖重建仍未完成）

**任务**：把当前 `/app/user-packages/python` 与 `/app/venv/...` 的运行时依赖来源转成可检查、可重建的部署契约；R31 的测试入口统一只是过渡，不复制未知环境包进仓库。

**通过条件**：

1. 新机器按文档可安装同版本依赖；
2. `scripts/server_runtime.sh` 在干净环境能明确失败并给出缺失包；
3. 后端测试和服务启动使用同一锁定依赖集合；
4. 版本漂移进入 manifest/audit。

### P1：Naive UI 首屏拆分（R44 组件 chunk 与 R56 Admin preload 边界已完成，真实请求瀑布仍待验证）

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