# 优化轮次 US-010-R24：schema baseline canonical hash 修复

- 日期：2026-09-19
- 分支：`codex/server-us010-r1`
- 目标：修复 baseline 文件内部 hash 与 verifier 重算口径不一致的问题。

## 发现

旧 baseline 的 `database_schema_sha256` 字段为 `b332...`，但 verifier 对 baseline 内 `actual_tables` 使用 canonical JSON 重算为 `fda1...`；旧 verifier 只比较“重算 baseline vs 当前数据库”，没有校验 baseline 自身存储 hash，因此会漏报 baseline 元数据损坏。

## 修复

- 统一 canonical hash：`sha256(json.dumps({tables: actual_tables}, sort_keys=True, separators=(',', ':')))`.
- 更新 baseline 的存储 hash和当前生成 commit。
- 更新 migration manifest 的 baseline hash和生成 commit。
- `verify_sqlite_baseline.py` 现在同时要求：
  - stored baseline hash == 重算 baseline hash
  - 重算 baseline hash == 当前数据库 hash

## 验收标准

- [x] baseline stored/recomputed/current 三个 hash 一致。
- [x] 生产数据库只读校验通过。
- [x] migration manifest baseline hash同步。
- [ ] R24 提交推送 GitHub。
