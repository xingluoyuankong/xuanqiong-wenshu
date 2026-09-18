# 优化轮次 US-010-R21：服务器拓扑只读验收审计

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 目标：把公网/回环服务、Cloudflare 边界、keepalive、manifest、schema 和 Git 同步检查固化为单命令。

## 命令

```text
scripts/audit_server_topology.sh
```

## 验收内容

- 8013 public manifest：running、commit 对齐、working tree clean（忽略运行时 WAL/SHM）。
- 8099 internal manifest：running、commit 对齐、working tree clean。
- 外部 keepalive：存在、755、shell syntax valid，internal/public hook 各一套。
- 8013、8099、5174 health。
- SQLite foreign key/orphan integrity。
- ORM/database schema drift。
- `git diff --check` 与 GitHub branch `0 ahead / 0 behind`。

## 边界

这是只读审计，不会停止进程、不写数据库、不修改 Cloudflare 配置；WAL/SHM 运行时文件不计为代码 dirty。
