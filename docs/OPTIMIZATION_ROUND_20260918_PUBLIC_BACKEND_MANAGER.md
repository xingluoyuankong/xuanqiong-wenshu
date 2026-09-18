# 优化轮次 US-010-R12：公网 8013 生命周期管理与双入口漂移收口

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`741fc06`

## 本轮变更

- `scripts/manage_public_backend.sh`：复用统一 manager 管理公网 8013，role=`public_backend`、host=`0.0.0.0`、port=`8013`。
- `scripts/ensure_public_backend.sh`：为公网 backend 提供 health/status/code-drift 自动恢复入口。
- `scripts/manage_internal_backend.sh`：支持可配置 host/port/role/state_dir，manifest 区分 process_commit/current_commit/code_drift。

## 验收

- 8013 manifest：PID `41198`，role=`public_backend`，process_commit=current_commit，code_drift=false。
- 8099 drift recovery：旧 PID `41096` 检测到 drift 后恢复为 PID `41450`，code_drift=false。
- 8013/8099/5174：均 HTTP 200。
- Cloudflare ingress 仍只指向 8013，8099 保持回环绑定。
- 真实 budget smoke、SQLite integrity audit 和 schema drift audit 继续通过。

## 后续

- 把 `ensure_public_backend.sh` 与 `ensure_internal_backend.sh` 接入正式 supervisor/keepalive 配置。
- 当前外部 keepalive 已通过可重放安装脚本注入，但 supervisor 配置本身仍属于 qwenpaw 外部部署资产。
