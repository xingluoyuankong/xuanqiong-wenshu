# 预算 Closure 语义（US-010）

> 目的：给出"逻辑调用 vs 物理尝试"在计费上的统一口径。
>
> **本文档的结论以代码实测为准，未实现的项明确标注为"未实现"，不做美化。**
> 最后更新：2026-09-18 ｜ 代码基线：commit `65b49c1`

---

## 0. 一句话结论

**当前不存在"预算闭包"（budget closure）。**

`TokenBudgetService` 是一个**被动账本**（passive ledger）：

- 记账必须由**外部调用方**显式发起（只有手工 API 端点会调）；
- 生成链路（章节正文、自评、增强、审阅）**从不自动记账**；
- 超预算**不会阻断任何调用**，只写一条 alert 记录；
- 系统内**没有价格表**，`cost` 完全由调用方传入。

因此 US-010 的大多数验收项描述的是**目标态而非现状**。逐条对照见 §5。

---

## 1. 计数口径：哪些调用计入？

### 1.1 实际计入的（唯一的写入口）

| 项 | 位置 |
| --- | --- |
| 唯一写入口 | `backend/app/api/routers/token_budget.py:131` `POST /{project_id}/token-budget/usage` |
| 落库实现 | `backend/app/services/token_budget_service.py:79` `record_usage()` |
| 数据表 | `token_usages`（`backend/app/models/token_budget.py` `TokenUsage`） |

该端点的请求体（`RecordUsageRequest`，`token_budget.py:45`）：

```python
module: str          # world | character | outline | content | other
tokens_used: int     # 调用方自报
cost: float          # 调用方自报 —— 系统不做任何换算
model_name: Optional[str]
chapter_id: Optional[int]
operation_type: Optional[str]
description: Optional[str]
```

**关键事实：`tokens_used` 和 `cost` 都是调用方自报的原始值，服务端不校验、不推导、不与 Provider 返回的 usage 对账。**

### 1.2 未计入的

生成链路对 `TokenBudgetService` 的引用数 = **0**（实测）：

```bash
grep -rn "TokenBudgetService\|record_usage" \
  backend/app/services/pipeline_orchestrator.py \
  backend/app/services/generation_call_service.py
# → 无输出
```

即：写一章小说所消耗的 token，**不会被自动记入预算**。除非有外部系统手工 PATCH 该端点。

### 1.3 prompt / completion 是否分开？

**没有分开。** `TokenUsage` 只有单个 `tokens_used` 字段，无 `prompt_tokens` / `completion_tokens` 之分。

---

## 2. 结算时机

**无自动结算。** 唯一路径是外部显式 POST `.../usage`，事务内 `add` + `commit`（`token_budget_service.py:79-104`）。

由此导致的语义空洞：

| 场景 | 当前行为 |
| --- | --- |
| 请求前预留额度 | **不存在** |
| 完成后结算 | 仅当外部显式调用时发生 |
| 流式中断 | **无处理**（没有流式结算逻辑） |
| 失败/重试 | **无处理**（重试不会被记账，也不会被去重） |

### 2.1 与 `run_id` fence 的关系

生成任务的 fence token `run_id`（见 `docs/workers_epoch_fencing_verification.md` 及其修正）**不参与计费**，`token_usages` 表无 run_id 字段。因此无法把成本归因到某一次具体尝试。

---

## 3. 超限行为（实测）

`get_or_create_budget()`（`token_budget_service.py:21`）在项目首次访问时创建默认预算：

```python
total_budget=100.0      # 元
chapter_budget=5.0      # 元
module_allocation={"world":20,"character":15,"outline":10,"content":55}
warning_threshold=80.0  # %
```

`check_and_create_alert()`（`token_budget_service.py:205`）按用量百分比分档：

| usage_percent | alert_type |
| --- | --- |
| ≥ 100 | `exceeded` |
| ≥ 90 | `critical` |
| ≥ warning_threshold(80) | `warning` |
| 其他 | `None`（不建 alert） |

### 3.1 超限后会发生什么？

**什么都不会发生，除了数据库多一条 alert 行。**

- 没有 402/403 拒绝；
- 没有降级；
- 没有截断；
- 没有 `allowed_actions = pause`（见 §5 第 6 条）；
- 生成链路甚至不知道预算的存在。

`chapter_budget` 字段**在整个代码库中没有任何消费者**（grep 无命中），是个纯声明字段。

---

## 4. 重试与失败的计费语义

| 问题 | 答案 |
| --- | --- |
| 重试是否重复计费？ | **未定义**——因为根本不自动计费 |
| 失败的物理尝试是否计入？ | **未定义** |
| 逻辑调用与物理尝试如何区分？ | **系统中无此概念** |

`generation_call_service` 会记录 `attempts`（`GenerationCallPolicy` / 结果对象），但该 `attempts` **不外传至计费层**，只用于日志与重试控制。

> 注：`backend/app/services/test_provider_exception_handling*.py` 里存在名为
> `test_budget_ledger_tracks_only_successful_attempts` 的测试，但它操作的是
> 一个测试内自建的 mock ledger，**并非** `TokenBudgetService`，不能作为
> "生产已按成功尝试计费"的证据。

---

## 5. 验收标准逐条对照

| # | 验收标准 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | 文档说明 estimated vs actual tokens | **PARTIAL** | 本文档即为该文档；但**代码中不存在 estimated/actual 的区分**——只有调用方自报的单一 `tokens_used` |
| 2 | 在 context variable 中展示 retry counter | **NOT IMPLEMENTED** | `attempts` 仅存在于 `generation_call_service` 的返回值/日志，未进入任何 contextvar，也未暴露给前端 |
| 3 | 自评成本与生成成本分开记录 | **NOT IMPLEMENTED** | `module` 枚举仅有 world/character/outline/content/other；虽有 `enable_self_critique`（`writer.py:871`）与 `SelfCritiqueService`，但其成本不单独记账 |
| 4 | 增强审阅成本按阶段追踪 | **NOT IMPLEMENTED** | `pipeline_orchestrator.py` 中无任何按 phase 记账的代码；`token_usages` 无 phase 字段（仅有 `operation_type`，且无生产写入方） |
| 5 | 前端准确展示预算分解 | **NOT IMPLEMENTED** | `frontend/src` 中 grep `token-budget` / `budget_remaining` **零命中**；后端有 `GET .../token-budget/usage` 端点但无前端消费 |
| 6 | 超预算时 `allowed_actions = pause` | **NOT IMPLEMENTED** | 全代码库 grep `allowed_actions` 与 `pause` 无交集；`allowed_actions` 只用于章节生成的 `refresh_status` / `cancel_generation` |

**6 条中 1 条 PARTIAL、5 条未实现。**

---

## 6. 与"文档化"有关的真实风险

1. **静默失效的账本**：预算 UI 会展示 `usage_percent`，但该数字只反映"外部手工上报"的量，与真实消耗无关。若据此做成本决策，会严重低估。
2. **`cost` 无来源**：没有任何定价表，也没有从 token 推导 cost 的函数（grep `pricing` / `cost_per` / `per_token` 均无命中）。所谓"花费 ¥x"完全取决于调用方填入的数字。
3. **`chapter_budget` 是死字段**：无消费者。
4. **alert 去重按 alert_type**：同一类型未处理告警会抑制后续告警（`token_budget_service.py:225`），因此用量继续攀升时不会重复提醒。

---

## 7. 若要真正实现 closure 语义，需要补的最小集

按依赖顺序：

1. **在 LLM 出口自动记账**：`llm_service.get_llm_response` / `_stream_single_model` 拿到 Provider 返回的 `usage`，写入 `token_usages`，并携带 `run_id` 与 `attempt_index`。
2. **区分逻辑调用 / 物理尝试**：`token_usages` 增加 `logical_call_id`（一次逻辑生成）与 `attempt_index`（第几次物理尝试），才能回答"重试是否重复计费"。
3. **定义结算时机**：建议"完成后结算 + 失败不扣"，并在流式中断时按已产出 token 结算。
4. **超限行为落地**：在生成入口处读预算，超限返回 `allowed_actions=["pause"]` 并阻断后续物理调用（而非仅写 alert）。
5. **定价表**：以 `model_name` → 单价表把 token 换算成 cost，取代调用方自报。

以上均**未实现**，本文档仅记录需求与现状差距。

---

*本文档中的每个结论均可在标注的 `file:line` 处验证。凡标注"未实现/零命中"的，均为实测 grep 结果。*
