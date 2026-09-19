# 优化轮次 R36：生成任务句柄取消、drain 与重启恢复（2026-09-19）

## R35 live 发现

R35 的真实闭环证明立即删除和取消请求都返回了预期的 409/200，但 Provider 长等待期间章节持续处于 `generating`，即使取消请求已经写入，后台 `BackgroundTasks` 协程仍未退出，临时项目无法在终态前清理。

这说明只写数据库里的 `cancel_requested` 不足以终止当前进程内的 provider await，也不能把取消终态和协程生命周期绑定。

## 本轮变更

修改 `backend/app/api/routers/writer.py`：

1. 增加 `_ACTIVE_GENERATION_TASKS`，按 `run_id` 注册实际后台 asyncio task；
2. 增加 `_PENDING_GENERATION_RUNS`，覆盖请求已 claim、后台任务尚未开始的窗口；
3. `_generate_chapter_async` 改为 wrapper，注册/注销 task 句柄并保证 finally 清理；
4. 取消接口先写 `cancel_requested`，再尝试 cancel + drain 当前 task，等待最多 10 秒；
5. 只有确认 task 已退出，才写章节 failed 状态和 `GENERATION_CANCELLED` terminal；
6. 排队窗口无 active task 时继续保持 busy；
7. 进程重启后没有 active/pending 句柄时，已持久化的取消请求可安全收口为失败 terminal，避免永久占用项目；
8. 保持 R34 的项目删除预检：后台未退出前删除仍返回 `PROJECT_HAS_ACTIVE_GENERATION`。

新增回归覆盖：

- 未 drain：章节仍保持 busy；
- 已 drain：才调用失败收口和 terminal SSE；
- 活动生成项目删除零写入；
- Writer 路由与后端全量回归。

## 验收结果

```text
专项取消/删除/Writer 回归：通过
后端全量：277 passed, 1 warning
```

唯一警告仍为 passlib 的 Python `crypt` 弃用提示。

## Live 验收标准

1. 生成后立即删除返回 409，错误码 `PROJECT_HAS_ACTIVE_GENERATION`；
2. 取消请求期间章节仍 busy，删除继续返回 409；
3. 当前进程内任务被 drain 后，章节进入 failed，terminal code 为 `GENERATION_CANCELLED`；
4. 终态后删除返回 200；
5. 进程重启后对已取消 run 再调用取消，可收口并删除；
6. SQLite integrity、schema baseline、拓扑和 remote sync 全部通过；
7. 临时项目最终无残留。

## 当前 Provider 结论

R33/R35 的真实 Provider 仍在导演脚本/上下文阶段出现 `PROVIDER_TIMEOUT` 或长等待；本轮只修复取消生命周期和删除一致性，未将 Provider 超时冒充为内容生成成功。

## 回滚锚点

回滚本轮提交会恢复仅数据库标记取消的旧行为；不执行生产迁移。