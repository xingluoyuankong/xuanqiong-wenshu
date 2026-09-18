# 优化轮次 US-010-R5：管理员 legacy 邮箱 schema 边界

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`d8a7833`

## 发现

8013 重启日志和每次认证请求均出现：`admin@qwenpaw-mingzhu.local` 被 `EmailStr` 判为特殊保留域，`UserInDB.model_validate` 失败后进入兼容回退。数据库内部读取不应重新执行用户输入校验，否则 legacy 数据会造成持续 warning。

## 修复

- `UserInDB.email` 改为内部读取用 `Optional[str]`，保留数据库原值。
- `UserCreate` / `UserUpdate` 继续使用 `EmailStr`，注册与修改邮箱仍严格校验。
- 新增两个 schema 回归：legacy DB 邮箱读取成功、用户注册仍拒绝特殊内部域。

## 验收标准

- [x] 代码与回归已覆盖；R5 重启后日志 grep 未发现 schema fallback/special-use warning。
- [x] 用户输入 schema 仍拒绝 `.local` 特殊域。
- [x] 后端全量：`267 passed in 15.59s`。
- [x] 8013 重启后健康且真实 HTTP budget smoke 继续通过。
- [x] 本轮提交 `5cc5e67` 已推送 GitHub。

## 当前测试

- R5 定向：`11 passed`。
- 后端全量：`267 passed in 15.59s`。

## 最终线上验收

- R5 重启后 8013 PID：`38242`。
- 8013/8099/5174：均 HTTP 200。
- 日志无 `用户数据校验失败`、`schema fallback`、`special-use` 或 `.local` 邮箱警告。
- 真实预算 smoke 和 SQLite integrity audit 均通过。
