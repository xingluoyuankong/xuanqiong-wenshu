# 优化轮次 R35：取消请求保持生成任务 busy 直到后台退出（2026-09-19）

## 根因

R34 的 live 验收证明了立即删除活动项目会被 HTTP 409 拦截，但也发现取消接口原先会在后台协程退出前立即把章节写成 `failed`。这样删除保护可能在后台任务仍运行时失效，后台协程继续访问已删除项目会再次触发 ORM refresh/外键错误。

## 本轮变更

修改 `backend/app/api/routers/writer.py::cancel_chapter_generation`：

- 取消接口只登记 `cancel_requested=true`、取消原因和 `cancel_requested` 控制事件；
- 章节状态保持 `generating/evaluating/selecting` 等 busy 状态；
- `allowed_actions` 收敛为 `refresh_status`；
- 流水线已有 `_assert_generation_active`，会在下一阶段检测取消请求并统一生成失败 terminal；
- 删除保护在后台任务真正退出前持续返回 `PROJECT_HAS_ACTIVE_GENERATION`。

新增 `backend/app/services/test_writer_cancel_guard.py`，验证取消请求不会提前把章节改成非 busy 状态。

R34 的 `NovelService.delete_projects` 预检继续生效：批量删除先检查所有项目归属和活动章节，失败时零删除、零提交。

## 验收

### 自动化

- 取消/删除/Writer 路由专项：`10 passed, 1 warning`；
- 后端全量：`276 passed, 1 warning`；
- 唯一警告仍为 passlib 使用 Python `crypt` 的弃用提示。

### Live 必须满足

1. 生成中的项目立即删除返回 409，错误码 `PROJECT_HAS_ACTIVE_GENERATION`；
2. 取消请求返回 200，章节在后台退出前仍保持 busy；
3. 后台任务进入失败/取消 terminal 后，删除返回 200；
4. 删除后 SQLite integrity、孤儿审计和拓扑审计通过；
5. 测试项目及预算记录清理完成。

## 当前真实 Provider 结论

R33 的当前证据仍是 Provider 在 `generate_mission` 等待 30 秒后返回 `PROVIDER_TIMEOUT`，不是内容成功；R35 只修复取消/删除一致性，不把 Provider 超时改写为成功。

## 回滚锚点

回滚本轮提交会恢复原取消接口行为；不执行数据库迁移，不删除生产数据。