# 优化轮次 R61：护栏回炉动态 Ceiling 接线回归（2026-09-20）

## 目标

R52 已增加按原文长度计算护栏回炉 `max_tokens`，但此前只有纯函数边界测试。本轮补充真实异步调用级回归，捕获 `_rewrite_with_guardrails` 传给 shared generation policy 的实际上限，防止未来业务接线回退为固定 8000。

## 新增回归

覆盖原文长度：

```text
500 -> 1800
1100 -> 2200
2000 -> 4000
```

测试同时验证：

- rewrite prompt 被调用；
- Provider policy 的 `max_tokens` 使用动态值；
- 返回内容经过 guardrail continuity 检查；
- 不改变原有异常/拒绝回退逻辑。

## 验收

```text
护栏质量回归：68 passed, 1 warning
后端全量：290 passed, 1 warning
```

唯一警告仍为 passlib 使用 Python `crypt` 的弃用提示。

本轮没有改变 token ceiling 算法，只把 R52 逻辑接线变成可回归契约；下一次真实违规样本仍需比较 `guardrail_rewrite_ms` 前后收益。

## 回滚

回滚本轮提交只会移除新增接线回归，不改变生产行为。