# 优化轮次 US-010-R2：统一服务器运行入口与真实 HTTP 验收

- 执行日期：2026-09-18
- 服务器：qwenpaw-mingzhu
- 分支：`codex/server-us010-r1`
- 基线提交：`f9d7997b0bbc04a667151fc9ef8501dcfdc1bc79`

## 本轮审查发现

1. `start.sh`、`restart.sh`、`monitor.sh` 各自硬编码了不同的 Python 和 Uvicorn 入口；服务器仓库 `.venv` 没有运行依赖，实际服务依赖 `/app/user-packages/python` 的隐式 `PYTHONPATH`。
2. 手工启动可以成功，但 `start.sh` 直接使用 `.venv/bin/python -m uvicorn` 会失败，导致启动脚本与真实部署不一致。
3. 当前 SQLite 有完整业务表，但 checkout 没有 `alembic.ini`/Alembic 版本目录，数据库没有 `alembic_version`；本轮不向生产库盲写版本表，迁移体系列为后续独立任务。
4. 后端全量测试结果为 `259 passed / 4 failed`；4 个失败集中在旧 Provider 异常测试的 fake 重试实现、OpenAI SDK 异常构造参数和重复 ledger 记录断言，尚未把它们误判成生产代码全绿。

## 本轮变更

- `scripts/server_runtime.sh`：统一解析仓库 Python、外置用户包和核心导入依赖，导出 `XQ_PYTHON`、`XQ_BACKEND_APP`、`PYTHONPATH`。
- `scripts/test_server_runtime.sh`：可重复验证运行时解析和 `uvicorn/fastapi/sqlalchemy/aiosqlite` 导入。
- `start.sh`：改用统一运行时和 `backend.app.main:app`。
- `restart.sh`、`monitor.sh`：改用同一运行时解析器，不再裸调用 `uvicorn`。
- `scripts/verify_budget_gate_http.py`、`scripts/verify_budget_gate_http.sh`：固化真实 HTTP 预算门 smoke，创建临时项目后自动删除。

## 本轮验收

### 运行时解析

```text
scripts/test_server_runtime.sh -> RUNTIME_IMPORTS=ok
fastapi=0.110.0 sqlalchemy=2.0.44 uvicorn=0.29.0
```

### 真实 HTTP 预算门

```text
login=200
create=201
budget_update=200
blueprint=200
generate=200
status=budget_not_allocated
budget_gate_reason=budget_not_allocated
allowed_actions=["pause"]
queued=false
delete=200
```

测试项目已删除，没有保留业务数据。

### 仍开放

- Provider 异常全量回归仍有 4 个测试契约失败，下一轮修正为真正调用生产重试路径，并适配当前 OpenAI SDK 构造方式。
- SQLite 数据库版本追踪缺失；需要先建立快照、schema 对照和回滚方案，再决定是否导入版本表或迁移工具。
- 当前 8013/8099 双后端仍同时存在，需要明确单一生产入口。
