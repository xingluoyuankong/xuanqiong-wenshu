# 优化轮次 R66：真实 Chromium 首屏与路由资源基线（2026-09-20）

## 目标

补齐 R59 静态入口预算之外的真实浏览器证据，测量首页、写作工作区和管理入口在当前服务器 Chromium 下的 DOM ready、load event、API 请求、modulepreload 和路由 chunk 加载情况。

## 审计入口

```text
scripts/audit_frontend_browser.mjs
scripts/audit_frontend_browser.sh
```

运行：

```bash
bash scripts/audit_frontend_browser.sh
```

脚本使用一次性 headless Chromium 和 CDP，结束时清理浏览器 profile 与进程。当前脚本输出资源 timing；深链接是否通过由 HTTP/浏览器结果单独判定，不能只看脚本退出码。

## 当前真实基线

服务器前端进程：

```text
python3 -m http.server 5174 --directory frontend/dist --bind 0.0.0.0
```

首页 `/` 的真实 Chromium 采样：

```text
title=玄穹文枢
readyState=complete
appRoot=true
responseEnd≈233.4ms
domContentLoaded≈742.7ms
loadEventEnd≈749.8ms
```

同一服务器上的直接 HTTP/Chromium 深链接结果：

```text
GET /             -> 200, HTML, #app=true
GET /workspace    -> 404, Error response, #app=false
GET /admin        -> 404, Error response, #app=false
GET /settings     -> 404, Error response, #app=false
```

这不是 Vue Router 权限判断，而是静态服务器在 Vue 应用启动前已经返回 404；当前生产入口缺少 SPA history fallback。

## 首屏资源分项

当前 `frontend/dist/index.html` 的入口资源：

```text
modulepreload_count=4
modulepreload_bytes=198345 bytes
entry_script=9586 bytes
stylesheet=142931 bytes
listed_static_assets_total=350862 bytes
```

四个 modulepreload：

```text
headlessui=97099 bytes
naive-alert=70338 bytes
pinia-vendor=6156 bytes
vue-router=24752 bytes
```

`198345` 只代表四个 modulepreload；加上入口脚本和 CSS 后，列出的静态文件大小为 `350862` bytes。浏览器实际传输量应使用 `transferSize`/`encodedBodySize`，不能把静态文件大小约写成单一“208KB”结论。

首页随后继续加载：

```text
/api/novels/current-user
/api/novels
GlobalNavBar / WorkspaceEntry / novel / markdown-vendor 等路由资源
```

Chromium 的 DBus/GCM 报错来自无桌面总线/浏览器后台注册；首页 HTTP、DOM 和 API 请求仍成功，该环境噪声不能作为应用失败。

## 根因与下一轮修复

新增但尚未接管生产 5174 的实现：

```text
scripts/frontend_spa_server.py
scripts/test_frontend_spa_server.py
```

实现和专项测试已经完成，但当前受管进程仍是 Python 标准静态服务器，因此线上深链接仍保持 404。接管前必须更新实际启动/keepalive 入口，并重新运行整套拓扑与浏览器验收。

## 验收标准

### HTTP 层

```text
GET /             -> 200, text/html, index.html
GET /workspace    -> 200, text/html, index.html
GET /admin        -> 200, text/html, index.html，然后由 Vue 权限守卫处理
GET /settings     -> 200, text/html, index.html
GET /assets/existing-file.js -> 真实文件 200
GET /missing.js   -> 404
GET /api/...      -> 不由前端服务器吞掉
```

### 浏览器层

每个目标路由必须记录最终 URL、导航状态、`readyState`、`#app`、DOM/load timing、API 状态、脚本/CSS/chunk 404、console error 和异常。最低通过条件是 `readyState=complete`、`appRoot=true`、无入口脚本/CSS/chunk 404、无页面级 JavaScript exception。

### 服务层

```text
HEAD 已提交
origin 与 HEAD 一致
working_tree_dirty=false
process_commit==current_commit
8013/8099 health=200
5174 root/deep-links healthy
```

## 当前结论

R59 的静态 `modulepreload_count=4` 已被真实浏览器确认；首页基线已取得。工作区、管理入口和设置页的直接访问被当前 SPA fallback 缺陷阻断，R66 不能被标记为完整通过。下一轮应先接管 SPA fallback，再重采集所有 history 路由，不能把当前 `/` 通过扩大解释为前端发布通过。
