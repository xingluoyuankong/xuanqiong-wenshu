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

## Keepalive 接入

新增 `scripts/ensure_internal_backend.sh`，由 qwenpaw 容器的 keepalive 循环调用：

- 先执行 `manage_internal_backend.sh status`，刷新 manifest。
- 8099 正常时只记录健康，不重启。
- 8099 缺失或 status 失败时调用 `start` 自动恢复。
- 只管理回环 8099，不触碰公网 8013。

## Keepalive 恢复演练

- 外部 keepalive 文件：`qwenpaw-mingzhu/bin/keepalive.sh`。
- 发现原权限为 `644`，直接执行会 `Permission denied`；已修复为 `755`。
- 原文件备份：`/run/csi/mount-root/nas/cdbd15b8c05480833b893f85e09ee146/internal-backend/keepalive.sh.before-internal-backend`。
- 演练：停止 8099 PID `39543`，执行 keepalive 后自动恢复为 PID `39998`。
- 恢复后 8099 `/api/health` HTTP 200；8013 公网 `/api/health` 仍 HTTP 200。
- manifest 更新为当前 commit、PID、启动时间和运行时 Python。

## Commit drift 修复

R10 后续审计发现旧 manifest 会用当前 Git HEAD 覆盖进程真实 commit。现已增加：

- `process_commit`：进程启动时的 checkout commit。
- `current_commit`：当前工作树 HEAD。
- `code_drift`：两者不一致时为 true。
- keepalive 检测 `code_drift=true` 后自动调用 manager restart。

这样新提交不会被旧 8099 进程伪装成当前版本。

## Drift 注入最终验收

- 首次 drift 演练发现 `set -u` 下 `current_commit` 未初始化，已修复。
- 注入 `process_commit=DRIFT_TEST_COMMIT` 后执行 keepalive。
- 旧 PID `40446` 被停止，新 PID `40581` 启动。
- manifest 恢复：`process_commit == current_commit`、`code_drift=false`、`status=running`。
- 8099 与 8013 health 均 HTTP 200。

## R11 可重放安装最终验收

- `scripts/install_internal_backend_keepalive.sh` 已写入仓库。
- 外部 keepalive hook 已幂等安装。
- 安装备份：`keepalive.sh.20260918-220412.bak`。
- 外部文件权限：`755`。
- `sh -n` 通过，直接执行通过。
- 8099 ensure/manifest 仍保持 running，8013 公网入口未受影响。

## R11 公网入口对齐验收

- 8013 旧 PID `38940` 已受控停止。
- 8013 新 PID `41198` 以当前 HEAD 启动。
- 8013/8099/5174：均 HTTP 200。
- 真实 budget smoke：通过并自动删除项目。
- SQLite integrity：foreign_keys=1、orphan_project_rows={}。
- 8013 新启动日志未出现 legacy admin email schema fallback warning。

## R12 公网管理器

- `scripts/manage_public_backend.sh`：8013 公网 backend 的同一 manifest 管理器。
- `scripts/ensure_public_backend.sh`：公网入口健康/commit drift 自动恢复。
- 8013 保持 `0.0.0.0`，8099 保持 `127.0.0.1`；两者共享当前 checkout 和 runtime resolver。
