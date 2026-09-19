# 优化轮次 R46：短章节导演脚本超时尾部收敛（2026-09-20）

## 触发证据

R45 从服务器真实日志提取 25 条完整 pipeline 记录：

```text
generate_mission p95=30005.88 ms
pipeline total p95=260925.81 ms
```

短章节的导演脚本阶段在 Provider 超时后使用确定性 fallback；对短章节继续等待完整 30 秒会增加尾部延迟，但不会提升最终正文可靠性。

## 本轮变更

仅针对 `target_word_count < 1200` 的导演脚本阶段：

- mission timeout：`30s -> 20s`；
- `retry_same_model_once`：`True -> False`；
- 保留 JSON schema 修复循环和确定性 fallback；
- 长章节 timeout 档位不变；
- 正文生成、质量门、取消 drain、usage attribution 不变。

设计原则：短章节的 mission 是可选规划阶段，已有确定性兜底；减少失败尾部等待，不把短章节改成无质量门的直接生成。

## 验收

```text
后端全量：283 passed, 1 warning
```

唯一警告为 passlib 使用 Python `crypt` 的弃用提示。

专项回归覆盖：

- mission timeout 分档；
- Provider 异常和重试策略；
- 章节质量门；
- 取消/删除生命周期；
- RAG 降级 metadata。

## R46 Live 证据

在提交 `ecfb94f` 部署后的公网 `8013` 上执行一次受控 500 字真实 Provider smoke，临时项目完成后删除。

日志证据：

```text
generate_mission duration_ms=20002.29
PROVIDER_TIMEOUT timeout_seconds=20.0
prepare_context duration_ms=20773.60
```

结果接口与账本：

```text
最终阶段：waiting_for_confirm
候选版本：1
非空正文：505 字符
total_tokens：16568
total_cost：0.0215
usage records：2
```

清理：

```text
项目删除：HTTP 200
novel_projects=0
chapters=0
token_budgets=0
orphan_project_rows={}
```

这证明短章 mission 超时上限已从历史约 30 秒收敛到约 20 秒，同时确定性 fallback 仍允许正文链完成候选稿落库；没有把 Provider timeout 误报为正文失败。

## 预期观测

下一次真实日志报告中，短章节 `generate_mission` 的超时长尾应从约 30 秒上限收敛到约 20 秒；成功快速返回的请求不强制等待。用 R45 同一报告入口重新采样后再判断实际 p50/p95 是否改善。

## 未完成项

- 尚未用新提交触发计费型真实 Provider 章节，只完成代码回归；
- 需要下一轮收集新日志与 R45 报告做前后对比；
- embedding 专用 key、MySQL migration runner、Python 依赖真正可重建安装仍在队列。

## 回滚

回滚本轮提交即可恢复短章节 30 秒 mission timeout 和同模型重试策略，不涉及数据库迁移。