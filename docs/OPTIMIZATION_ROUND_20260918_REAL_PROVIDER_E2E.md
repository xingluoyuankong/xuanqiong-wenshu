# 优化轮次 US-010-R7：真实 Provider 章节生成与 usage 对账

- 执行日期：2026-09-18
- 服务器：qwenpaw-mingzhu
- 分支：`codex/server-us010-r1`
- 基线提交：`6b0f6d4`

## 本轮目标

验证真实 Provider 链路：HTTP POST generate -> worker/pipeline -> 真实 Provider -> ChapterVersion -> status -> SSE terminal -> TokenUsage。使用隔离数据库 `storage/e2e_us006.db` 和隔离端口 `18299`，不触碰生产 8013、生产 SQLite 或生产项目。

## 实际结果

```text
server_ready: true
login: 200
save_blueprint: 200
generate_http: 200
status_http: 200
status_stage: waiting_for_confirm
sse_http: 200
sse_content_type: text/event-stream; charset=utf-8
sse_frame_count: 19
sse_terminal_event: type=complete
db_chapter_status: waiting_for_confirm
db_version_count: 1
db_version_lens: [490]
```

### 真实 usage 对账

```text
db_token_usage_rows: 2
db_token_usage_total: 16237
db_token_usage_prompt: 11675
db_token_usage_completion: 4562
db_token_usage_estimated_rows: 0
db_token_usage_run_ids: [bd0fd71b-8836-481b-8168-d9710a064ae3]
db_token_usage_stages: [chapter_generation]
db_token_usage_models: [GLM-5.3-Flash]
```

真实 Provider 返回的 usage 已进入预算账本，没有退化为估算值；归因包含 run_id、stage 和模型。

## 与 stub E2E 的区别

- stub E2E：验证确定性 HTTP/worker/SSE/落库工程链路，Provider 被替换，usage rows 可以为 0。
- 本轮 real E2E：使用真实 Provider，验证真实正文、真实 SSE 终态和实际 prompt/completion usage。
- 两者不能互相替代；本轮首次补齐真实 Provider 证据。

## 验收结论

- [x] 真实 Provider 请求成功。
- [x] 正文非空并落库。
- [x] 章节版本落库。
- [x] SSE terminal event 收到。
- [x] `TokenUsage` 非空。
- [x] prompt/completion tokens 分离。
- [x] `is_estimated=0`。
- [x] run_id、stage、model_name 均可追踪。
- [x] 隔离数据库和测试项目在 E2E 脚本结束后清理。

## 仍开放

1. 多次物理 retry 的真实 Provider usage 去重/逐 attempt 对账。
2. 真实 Provider 超预算后的 402/429/5xx 组合故障矩阵。
3. SQLite schema 版本追踪正式化；当前只读 drift audit 已通过，但仍没有正式迁移版本表。
4. 8013 与 8099 双入口的最终角色收口。
