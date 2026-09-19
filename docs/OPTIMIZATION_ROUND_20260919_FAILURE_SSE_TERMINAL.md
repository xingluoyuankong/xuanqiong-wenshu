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
