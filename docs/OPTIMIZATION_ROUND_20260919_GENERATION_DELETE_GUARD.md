# 优化轮次 R34：生成中的项目删除保护（2026-09-19）

## 触发证据

R33 当前提交上的真实 Provider 复验使用临时项目 `e09bc93e-2aa7-4b76-a806-8b00105e9433`，生成任务在 `prepare_context` 阶段停留，Provider 30 秒超时后继续执行。测试脚本在轮询超时后删除项目，服务日志出现：

```text
Could not refresh instance '<Chapter ...>'
(sqlite3.IntegrityError) FOREIGN KEY constraint failed
```

根因是删除路由立即删除项目，而 `BackgroundTasks` 中的章节生成协程仍持有旧 `Chapter` 对象并继续写入。数据库完整性审计最终仍为零孤儿，但运行日志和失败终态不完整。

## 本轮变更

修改 `NovelService.delete_projects`：

1. 先验证整个删除批次的项目归属；
2. 查询这些项目下处于 `generating`、`evaluating`、`selecting` 的章节；
3. 发现任一活动章节时返回 HTTP 409；
4. 返回结构化错误：

```json
{
  "code": "PROJECT_HAS_ACTIVE_GENERATION",
  "message": "请先取消进行中的章节生成，再删除项目。",
  "chapters": [{"project_id": "...", "chapter_number": 1, "status": "generating"}]
}
```

5. 预检失败时不执行任何项目删除、不提交事务，避免批量删除部分成功。

新增回归：`backend/app/services/test_novel_delete_guard.py`，覆盖活动生成拒删、零删除、零提交和结构化错误。

## 验收标准与结果

### 自动化回归

- 新增删除保护 + writer 路由回归：`9 passed, 1 warning`；
- 后端全量：`275 passed, 1 warning`；
- 警告仍为 passlib 使用 Python `crypt` 的弃用提示。

### Live 验收

提交服务后需执行以下闭环并记录：

1. 创建临时项目并保存单章蓝图；
2. 设置有限预算并发起生成；
3. 立即删除必须得到 HTTP 409 和 `PROJECT_HAS_ACTIVE_GENERATION`；
4. 调用取消生成并等待终态；
5. 终态后删除必须得到 200；
6. SQLite integrity、孤儿检查和拓扑审计必须通过；
7. 测试项目、版本和预算记录最终清理。

## 未完成/后续

- Provider 当前在最小请求上出现 `PROVIDER_TIMEOUT`，需要单独优化 provider timeout/上下文阶段，不把本轮删除保护误报成 Provider 成功；
- 需要补充真实取消后的 terminal SSE 证据；
- R30 migration runner、Python 依赖可重建性和 Naive UI 首屏拆分继续保留在总审查队列。

## 回滚锚点

回滚本轮提交可恢复原删除语义；数据库不执行迁移，测试临时项目不作为持久资产。