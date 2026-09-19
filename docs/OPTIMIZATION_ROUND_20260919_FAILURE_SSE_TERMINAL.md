# 优化轮次 US-010-R28：失败生成 SSE terminal 收口

- 日期：2026-09-19
- 分支：`codex/server-us010-r1`
- 目标：让失败/超时/质量门失败的章节生成也向 SSE 订阅者发送明确 terminal error event。

## 发现

隔离真实 Provider 无效模型 E2E 结果：

- 章节 status 正确为 `failed`。
- 版本数为 0，正文为空。
- 但 SSE `terminal_event=null`，长连接只能依赖 idle timeout 收口。

## 修复

- `GenerationLogService.fail_task()` 写入：
  - `level=error`
  - `metadata.type=failed`
  - `metadata.event_kind=terminal`
  - stage/code/retryable
- 后台生成 timeout、普通异常、质量门失败路径调用 failure terminal。
- `complete_task()` 也显式写 `event_kind=terminal`。

## 当前回归

- `test_generation_log_service.py`：失败 terminal event 4 项定向回归与模型不可用测试通过。
- 后端全量：`274 passed in 18.24s`。
- 下一步：运行隔离 invalid-model E2E，确认 `sse_terminal_event.metadata.type=failed`。

## R29 correction

Invalid-model terminal event initially carried `retryable=true` because the generic failure helper used a fixed value. It now derives retryability from error code; `PROVIDER_MODEL_UNAVAILABLE` and authentication failures are terminal non-retryable states.

## R29 非重试失败终端语义

- 初次 invalid-model E2E 已收到 failed terminal，但 generic helper 写了 `retryable=true`。
- `GenerationLogService.fail_task()` 现在对 `PROVIDER_MODEL_UNAVAILABLE` 和 `AUTHENTICATION_FAILED` 默认写 `retryable=false`。
- writer failure helper 也按错误码传递 retryability。
- 定向 4 passed；后端全量 `274 passed in 20.76s`。
- 下一步重启两个入口并重跑隔离 invalid-model E2E。

## R29 最终线上 E2E

- 8013/8099 已对齐提交 `1d69ec7`。
- invalid-model 隔离 E2E：HTTP generate=200，章节最终 status=`failed`，版本数=0。
- SSE terminal event：收到 `level=error`、`type=failed`、`event_kind=terminal`。
- code=`PROVIDER_MODEL_UNAVAILABLE`。
- retryable=`false`。
- E2E exit=0。
