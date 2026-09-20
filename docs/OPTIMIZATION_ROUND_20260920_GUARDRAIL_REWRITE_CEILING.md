# 优化轮次 R52：短章节护栏回炉 Token Ceiling（2026-09-20）

## 触发证据

R51 候选级 runtime 证据显示：

```text
generation_ms=60538.99
guardrail_check_ms=0.35
guardrail_rewrite_ms=19637.22
total_ms=80182.08
```

短章节原文约 500–600 字，但护栏回炉固定使用 `max_tokens=8000`，存在明显的无效输出预算空间。

## 本轮变更

新增 `_resolve_guardrail_rewrite_max_tokens(original_text)`：

```text
原文 <1200 字符：max(1800, length × 2.0)
原文 <2500 字符：max(3200, length × 2.0)
原文 <5000 字符：max(4800, length × 1.8)
更长原文：8000
```

只收敛护栏回炉的输出上限，不改变：

- 护栏触发条件；
- 违规检查；
- 连续性/缩短比例拒绝保护；
- 质量门；
- 正文最低字数；
- 长章节回炉上限。

## 回归

```text
后端全量：286 passed, 1 warning
```

新增边界回归：

```text
500 字符 -> 1800
1100 字符 -> 2200
2000 字符 -> 4000
6000 字符 -> 8000
```

## 真实验收标准

下一次短章节 smoke 需要记录：

1. `guardrail_rewrite_ms` 前后对比；
2. 候选正文仍非空且满足最低字数；
3. 护栏违规修复未丢失 mission 连续性；
4. usage attribution 完整；
5. SQLite 零残留、topology audit PASS。

R51 的候选级证据保留为优化前基线；不以单次新样本直接宣称 p95 改善。

## 回滚

回滚本轮提交即可恢复固定 8000 token 的护栏回炉上限，不涉及数据库和服务拓扑。