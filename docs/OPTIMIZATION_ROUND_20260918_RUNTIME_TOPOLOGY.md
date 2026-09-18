# 优化轮次 US-010-R9：双后端运行角色收口

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`602fde7`

## 审查发现

服务器同时运行两个玄穹文书后端：

- `8013`：`0.0.0.0`，Cloudflare ingress `wenshu-api-qwenpaw-mingzhu.xzxyuan.ccwu.cc` 指向这里，是公网生产入口。
- `8099`：`127.0.0.1` 回环，仅本机可达，没有 Cloudflare ingress，是内部回环/兼容入口。

此前 8099 使用 `/app/venv/bin/python` 的旧进程，8013 使用仓库 `.venv` + `/app/user-packages/python` 的新运行时，同一 checkout 存在版本漂移。

## 本轮动作

- 停止旧 8099 PID `30221`。
- 使用 `scripts/server_runtime.sh` 解析当前仓库运行时。
- 以当前提交启动 8099 新 PID `39298`。
- 保留端口和回环绑定，不改公网 ingress，不影响 8013。

## 验收

```text
8013/api/health -> 200
8099/api/health -> 200
5174/ -> 200
```

两个后端都使用当前 checkout 的代码；启动日志没有 `UserInDB` legacy email schema fallback warning。

## 运行角色结论

- 生产公网入口：8013。
- 内部回环兼容入口：8099。
- 前端静态入口：5174。
- E2E stub 端口：按测试需要临时启动，不属于生产入口。

## 后续治理

- 需要把 8099 的调用者和停止责任纳入正式 supervisor/manifest，而不是依赖孤立 PID。
- 需要为 8013 和 8099 都记录启动 commit、运行时 Python、PYTHONPATH 与日志目录。
- Cloudflare ingress 继续只指向 8013，避免内部 8099 被意外暴露。
