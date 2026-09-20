# 优化轮次 R68：前端 SPA fallback 接管、管理与拓扑门禁（2026-09-21）

## 触发证据

R66 真实 Chromium 基线确认旧 5174 进程为：

```text
python3 -m http.server 5174 --directory frontend/dist --bind 0.0.0.0
```

旧入口导致：

```text
/             -> 200
/workspace    -> 404
/admin        -> 404
/settings     -> 404
```

因此根路径健康不再能代表前端发布健康。

## 本轮变更

```text
scripts/manage_frontend.sh
scripts/ensure_frontend.sh
scripts/test_manage_frontend.sh
scripts/audit_server_topology.sh
docs/OPTIMIZATION_ROUND_20260921_FRONTEND_MANAGEMENT.md
```

- `manage_frontend.sh` 提供 `status/start/stop/restart`，只管理由 `frontend_spa_server.py` 启动的进程；端口被未知进程占用时拒绝替换；
- 写入 `logs/frontend-5174/manifest.json`，记录 process/current commit、dirty、server、dist、PID、日志；
- `ensure_frontend.sh` 为容器 keepalive 的最小 hook；
- topology audit 新增前端 manifest 对齐、`/`、`/workspace`、`/admin`、`/settings` HTML `#app` 检查，并锁定缺失静态资源和 `/api` 不被 fallback 吞掉；
- 添加隔离端口 lifecycle 回归，不触碰生产 5174。

## 自动化验收

```text
bash scripts/test_manage_frontend.sh  PASS
python3 scripts/test_frontend_spa_server.py  7 tests PASS
bash -n manage/ensure/test/topology scripts  PASS
```

`test_manage_frontend.sh` 在临时 `18174` 端口验证 start/status/stop、深链接 fallback、真实静态资源、缺失资源 404 和 API 隔离。

## 当前部署证据

旧 `http.server` PID 已停止；当前 5174：

```text
python3 scripts/frontend_spa_server.py --root frontend/dist --host 0.0.0.0 --port 5174
```

HTTP：

```text
/                     200
/workspace            200
/admin                200
/settings             200
/inspiration          200
/novel/fixture-id     200
/assets/index-*.js    200
/missing.js           404
/api/health           404
```

Chromium/CDP 直接导航：

```text
/, /workspace, /admin, /settings, /inspiration, /novel/fixture-id
readyState=complete
appRoot=true
```

`/admin` 的静态入口通过只证明 SPA 能启动；真实授权态仍由 Vue guard 和后台 API 分别验收，不能因 `index.html` 返回 200 而误报管理权限功能完整。

## 运行时自愈

服务器外部 keepalive 配置新增一个受标记保护的前端 hook，只执行仓库内 `scripts/ensure_frontend.sh`。这项外部运行时配置不纳入 Git；仓库中的 hook 脚本、管理脚本、测试和本轮证据会随提交推送。

## 回滚

```text
bash scripts/manage_frontend.sh stop
python3 -m http.server 5174 --directory frontend/dist --bind 0.0.0.0
```

回滚后深链接会重新 404，因此回滚只用于新入口不可用时的临时恢复；恢复前必须保留失败日志并重新验证 8013、8099、5174。