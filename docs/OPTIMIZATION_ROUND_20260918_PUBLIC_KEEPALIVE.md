# 优化轮次 US-010-R19：公网 keepalive 自动恢复

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`f97342c`

## 变更

新增 `scripts/install_public_backend_keepalive.sh`，将 `ensure_public_backend.sh` 幂等注入 qwenpaw 外部 keepalive。

- 每次安装前备份外部 keepalive。
- 注入 begin/end 标记，重复执行不会重复添加。
- 自动恢复 755 权限并执行 `sh -n`。
- 只管理公网 8013，不改变 8099 回环入口。

## 真实故障恢复验收

- 旧 8013 PID：`45975`。
- 受控停止 8013。
- 直接执行 qwenpaw keepalive。
- 新 8013 PID：`46821`。
- 8013 health：HTTP 200。
- 8099 health：HTTP 200。
- 外部 keepalive 备份已生成到 qwenpaw-backups。

## 当前要求

- [x] 公网 8013 keepalive hook 可重放安装。
- [x] 8013 故障后自动恢复。
- [x] Cloudflare ingress 仍只指向 8013。
- [x] R19 提交推送 GitHub。

## R20 duplicate hook cleanup

- 重新审查发现外部 keepalive 曾同时存在旧手工 internal hook 和标记 hook。
- 已移除旧手工 internal hook，仅保留一个 begin/end 标记块。
- 当前 keepalive 中 internal/public 各保留一套调用，`sh -n` 通过，直接执行后 8013/8099 health 均 HTTP 200。
- `install_internal_backend_keepalive.sh` 后续安装会先移除已知 legacy 块，保持幂等。
