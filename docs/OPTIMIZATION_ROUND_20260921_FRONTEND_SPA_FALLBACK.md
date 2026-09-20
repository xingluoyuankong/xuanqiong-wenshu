# 优化轮次 R67：前端 SPA history fallback 实现（2026-09-21）

## 目标

修复 R66 发现的生产前端深链接缺陷：当前 5174 使用 Python 标准静态服务器，首页 `/` 能返回 `index.html`，但 `/workspace`、`/admin`、`/settings` 等 Vue Router history 路由直接访问返回 404。

## 本轮变更

```text
scripts/frontend_spa_server.py
scripts/test_frontend_spa_server.py
```

实现边界：

- 已存在的静态文件直接返回；
- `/` 返回 `index.html`；
- 无扩展名且不存在的前端路径回退 `index.html`；
- 缺失 `.js`、`.css`、`.json` 等带扩展名资源保持 404；
- `/api` 和 `/api/...` 不由前端服务器接管；
- 拒绝普通和 URL 编码路径遍历；
- 拒绝反斜杠路径和越出文档根的符号链接；
- 禁止目录列表；
- 支持 GET/HEAD；
- 返回 `Content-Length` 和 `X-Content-Type-Options: nosniff`。

## 专项验收

```text
python3 -m py_compile scripts/frontend_spa_server.py scripts/test_frontend_spa_server.py
python3 scripts/test_frontend_spa_server.py
```

实际结果：

```text
Ran 7 tests in 3.585s
OK
git diff --check: PASS
```

覆盖：

1. 根路径与真实静态文件；
2. 无扩展名 SPA 路由回退；
3. 缺失静态资源 404；
4. `/api` 路径隔离；
5. URL 编码路径遍历；
6. 目录访问和目录列表防护；
7. 越界符号链接防护。

## 部署状态

本轮只新增实现和专项测试，**尚未替换当前受管 5174 进程**。当前线上进程仍是：

```text
python3 -m http.server 5174 --directory frontend/dist --bind 0.0.0.0
```

因此当前直接访问深链接仍可能返回 404；必须在确认前端进程托管入口和 keepalive 关系后，再执行切换、重启和浏览器复验。

## 下一轮部署验收

```text
GET /              -> 200
GET /workspace     -> 200 + index.html
GET /admin         -> 200 + index.html，再由 Vue 鉴权守卫处理
GET /settings      -> 200 + index.html
GET /assets/exist  -> 200
GET /missing.js    -> 404
GET /api/health    -> 由后端处理，不被前端 fallback 吞掉
```

浏览器层还必须确认：`readyState=complete`、`#app=true`、无入口脚本/CSS/chunk 404、无页面级 JavaScript exception，并在刷新场景复验。

## 回滚

保留旧的 `python3 -m http.server` 启动命令；如果新入口切换后健康检查或浏览器深链接失败，停止新进程、恢复旧进程、复跑 8013/8099/5174 health 和 topology audit。