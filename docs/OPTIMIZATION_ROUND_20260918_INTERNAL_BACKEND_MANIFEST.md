# 优化轮次 US-010-R10：8099 内部后端生命周期与 manifest

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`2561ccc`

## 目标

把回环内部后端 8099 从孤立手工 PID 纳入可重复的 start/stop/restart/status/manifest 管理，同时保持 Cloudflare 公网 8013 不变。

## 新增

- `scripts/manage_internal_backend.sh`
  - `status` / `manifest`：输出并持久化当前服务状态。
  - `start`：使用 `server_runtime.sh` 解析当前仓库 Python 和 PYTHONPATH。
  - `stop`：TERM -> 等待 -> KILL，并写 stopped manifest。
  - `restart`：受控停止后重新启动。
  - manifest 记录：role、host、port、pid、commit、Python、Python version、PYTHONPATH、stdout/stderr、started_at、updated_at。

## 运行拓扑

- 8013：公网生产入口，Cloudflare ingress 指向这里。
- 8099：`127.0.0.1` 回环内部入口。
- 5174：静态前端。

## 验收证据

### Status manifest

```text
old 8099 PID: 39298
new 8099 PID: 39543
commit: 2561cccf184ef7b2d9905deb545c498997af3fef
python: .../.venv/bin/python
python_version: 3.11.2
port: 8099
status: running
started_at: 2026-09-18T21:36:54Z
```

### Health

```text
8013/api/health -> 200
8099/api/health -> 200
5174/ -> 200
```

### 安全边界

Cloudflare ingress 配置仅把公网 API 指向 8013，没有把 8099 暴露到公网；8099 保持回环绑定。

## 后续

- 将 8099 manifest 接入 supervisor/keepalive，避免服务只依赖人工执行脚本。
- 为 8013 也生成同格式 manifest，统一公网/内部服务观测。
- 补强制停止、孤儿检测、旧 commit 拒绝启动的回归。
