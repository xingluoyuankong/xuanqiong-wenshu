# 优化轮次 US-010-R1：预算门前后端闭环

- 执行日期：2026-09-18（Asia/Shanghai）
- 服务器：qwenpaw-mingzhu
- 工作树：`master`，基线 `af0ad0a1720181455859500493fcf32646743159`
- 本轮分支：`codex/server-us010-r1`
- 目标：让预算门从后端阻断变成前端可见、可解释、可验收的完整状态，并修复当前服务器验收环境阻塞。

## 现状审查结论

1. 服务器真实部署目录为 `/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu`。
2. 当前服务：8013 公网后端、8099 回环后端、5174 静态前端、18093 E2E stub；本轮验收前均健康。
3. 服务器工作树基线已有 US-001 至 US-010 历史提交，但此前没有 Git remote；本轮已恢复 `origin=https://github.com/xingluoyuankong/xuanqiong-wenshu.git`。
4. 基线工作树包含预算门未提交改动、预算门测试和 SQLite `-wal/-shm` 运行时文件；本轮不提交 `storage/e2e_us006.db-wal` 与 `storage/e2e_us006.db-shm`。
5. 运行 `.venv` 与 `/app/venv` 均不是完整测试环境；本轮使用隔离 `/tmp/xuanqiong-test-venv`，按 `backend/requirements-dev.txt` 安装依赖。

## 本轮发现与修复

### 1. 后端预算门语义补全

文件：`backend/app/api/routers/writer.py`、`backend/app/services/token_budget_service.py`

- `total_budget <= 0` 明确解释为 `budget_not_allocated`，阻断新的物理生成调用。
- 普通超预算返回 `budget_exceeded`。
- 返回 `budget_gate_reason`、`budget_unallocated`、预算上限、累计成本、使用率。
- 保留预算检查异常时 fail-open 的既有策略，并记录 warning。
- 预算门仍在章节 claim 之前执行，暂停请求不会占用章节生成状态。

### 2. 写作台预算暂停 UI 闭环

文件：`frontend/src/components/writing-desk/layout/WDWorkspace.vue`、`frontend/src/components/writing-desk/workspace/states/ChapterFailed.vue`

- `budget_exceeded` / `budget_not_allocated` 不再落入 `ChapterEmpty`。
- 前端展示“预算门暂停”、预算上限、已记录成本、使用率和恢复指引。
- 保持章节正文零写入语义，用户调整 Token Budget 后通过顶部命令栏重试。

### 3. 回归与测试基座修复

文件：`backend/tests/test_us010_budget_gate.py`、`backend/requirements-dev.txt`、`frontend/vite.config.ts`、`frontend/src/test/setup.ts`

- 增加未分配预算的预算门回归。
- 声明 `pytest-asyncio==1.1.0`，避免 async 测试被当作不支持。
- 为 Vitest 固定 jsdom URL，并提供缺失/不完整 storage API 的测试 polyfill。
- 修复 `ClueTrackerView.vue` 中两个 `string | number` 模板表达式的类型边界。

## 当前验收证据

### 后端

```text
56 passed in 17.86s
```

覆盖：US-007 Provider 异常、US-009 run_id fencing、US-010 budget closure、预算门超限/未分配/故障放行。

### 前端

```text
23 test files passed
117 tests passed
npm run type-check -> exit 0
npm run build-only -> exit 0
```

构建中的 dynamic import 和大 chunk 提示属于既有性能告警，不影响本轮构建退出码。测试中仍有 Node `--localstorage-file` warning 和若干测试主动输出的错误日志，但没有失败用例。

### 线上健康

本轮代码提交前复核：

```text
127.0.0.1:8013/api/health -> 200
127.0.0.1:8099/api/health -> 200
127.0.0.1:5174/ -> 200
```

这些 200 是旧进程代码的健康证据；本轮代码必须在提交后重启 8013/5174，再做一次同样的健康与预算阻断 smoke。

## 推送与部署验收标准

- [x] 工作树代码 diff 通过 `git diff --check`。
- [x] 后端定向回归 56/56 通过。
- [x] 前端测试、type-check、build 通过。
- [ ] 当前优化分支已提交并推送到 GitHub。
- [ ] 8013 后端重启后仍健康。
- [ ] 5174 静态前端重启/刷新后仍健康。
- [ ] 使用测试项目验证预算阻断响应包含 `budget_gate_reason`、`allowed_actions=["pause"]`，且章节不会进入 generating。
- [ ] 生产工作树清洁，SQLite `-wal/-shm` 不纳入提交。

## 下一轮优先级

1. 用真实项目/认证会话跑预算未分配、超预算、预算检查异常三路 HTTP → worker → status/SSE。
2. 将 `run_id`、attempt、stage、prompt/completion/estimated usage 与 `token_usages` 逐次对账，完成 US-010 真正 closure。
3. 将测试依赖和生产运行依赖拆成明确的构建/部署层，避免线上 `.venv` 与仓库测试环境漂移。
4. 收口双后端 8013/8099 的角色、入口和停止策略，避免同一工作树同时存在两套不可见部署。
5. 补生命周期 manifest/epoch 的强制停止恢复 smoke。
