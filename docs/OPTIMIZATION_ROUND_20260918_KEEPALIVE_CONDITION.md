# 优化轮次 US-010-R16：keepalive 健康条件显式化

- 日期：2026-09-18
- 分支：`codex/server-us010-r1`
- 基线：`6f16f58`

## 发现

`ensure_public_backend.sh` 与 `ensure_internal_backend.sh` 的健康判断使用了混合 `&&/||` 表达式，虽然当前 shell 短路结果多数场景正确，但缺少括号，容易在后续字段扩展时产生错误判定。

## 修复

健康条件现在明确要求同时满足：

```text
status == running
code_drift != true
working_tree_dirty != true
```

否则进入 start/restart 分支。

## 验收

- [x] 两个脚本 `bash -n` 通过。
- [x] 8013/8099 manifest 均记录 `status=running`、`code_drift=false`。
- [x] runtime 文件不触发 dirty 误判。
- [x] 8013/8099/5174 health 保持 200。
- [ ] R16 提交推送 GitHub。
