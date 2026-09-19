# 优化轮次 R31：统一服务器测试运行时与全栈验收（2026-09-19）

## 目标

把后端测试入口和生产服务入口统一到同一套 Python 依赖解析链，避免“服务能启动、默认 pytest 因外置依赖路径缺失而收集失败”的验收分叉；同时记录当前全栈验证结果和明确的后续优化项。

## 当前发现

- 服务器仓库提交：`a03bf2d`。
- `.venv/bin/python` 自身不包含 FastAPI、SQLAlchemy、httpx、pydantic 等包。
- 生产运行脚本会按顺序加入仓库路径、仓库 `.venv`、`/app/user-packages/python` 和 `/app/venv/lib/python3.11/site-packages`；直接在 `backend` 目录执行 `.venv/bin/python -m pytest -q` 未继承这条路径，因此收集阶段出现 20 个 `ModuleNotFoundError`。
- 这属于验收入口漂移，不是业务测试失败。

## 本轮变更

新增 `scripts/test_backend.sh`：

1. 复用 `scripts/server_runtime.sh` 的 `xq_prepare_runtime`；
2. 打印实际测试解释器和 `PYTHONPATH`；
3. 在 `backend` 目录调用同一解释器执行 pytest；
4. 支持把额外 pytest 参数透传给测试进程。

本轮没有修改生产数据库、迁移文件或业务逻辑。

## 验收标准与结果

### 后端

命令：

```bash
bash scripts/test_backend.sh
```

结果：

```text
274 passed, 1 warning in 17.98s
```

警告为 `/app/user-packages/python/passlib` 使用 Python `crypt` 的弃用提示，不影响本轮测试结果。

### 前端

命令：

```bash
cd frontend
npm run type-check
npm run test:run
npm run build-only
```

结果：

- TypeScript 类型检查：通过。
- Vitest：`23 files passed`、`117 tests passed`。
- Vite 生产构建：通过，`4714 modules transformed`。

构建保留以下待优化警告：

- 多个对话框同时被静态和动态导入，动态导入未形成独立 chunk；
- 若干产物超过 500 kB，需要后续拆分 vendor/chunk。

### 服务与拓扑

重启后：

- 公网后端 `0.0.0.0:8013`：健康检查 200，进程提交为 `a03bf2d`；
- 内部后端 `127.0.0.1:8099`：健康检查 200，进程提交为 `a03bf2d`；
- 前端 `127.0.0.1:5174`：健康检查 200；
- `bash scripts/audit_server_topology.sh`：`AUDIT_RESULT=PASS`。

拓扑审计同时通过 manifest 对齐、keepalive、SQLite integrity、schema drift、baseline、migration provenance、Git diff 和 remote sync 检查。

## 后续优化队列

1. **前端 chunk 性能**：清理重复静态/动态导入，拆分 `naive-ui`、`export-vendor`、`chart-vendor` 等大块，并以首屏体积和路由加载时间复测。
2. **测试依赖固化**：评估将运行时依赖声明为可重建的服务器环境配置，避免只依赖 `/app/user-packages/python`；当前 R31 先统一入口，不把外置包复制进仓库。
3. **真实 Provider 端到端**：继续区分 stub、健康检查和真实非空章节产物，保留余额、认证和模型不可用证据。
4. **迁移 runner**：R30 计划仍保持 `execute=false`，先补 dialect-specific dry-run、备份和回滚证据，再评估执行路径。

## 回滚锚点

本轮仅新增测试入口和记录文档；回滚可删除新增脚本和文档，不触碰运行数据库及服务配置。