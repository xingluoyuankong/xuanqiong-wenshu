---
contract_id: chapter_writing_contract
version: 1.0.0
kind: code-layer-writing-contract
source: pipeline_orchestrator.py
source_scope: _resolve_chapter_draft_contract + _build_scene_execution_ledger + prompt hard rules
database_write_policy: read-only
---
# CHAPTER_DRAFT_CONTRACT

这是代码层章节写作契约的 v1.0.0 版本化快照。它是审计、diff 和回归测试的只读
基准，不是 `writing` 或 `writing_v2` 数据库主提示词，也不应覆盖数据库中的用户版本。

## 字数与场景预算

- target_chars: {target_word_count}; minimum_chars: {min_word_count}; preferred_floor: {preferred_floor}.
- supported_range_chars: {supported_min}-{experimental_max}.
- generation_strategy: {generation_strategy}; tier: {tier}.
- recommended_scene_count: {scene_count_min}-{scene_count_max} real scenes or scene groups.
- Do not pad with static scenery, repeated thoughts, or synopsis.
- Every 900-1500 chars should contain a concrete state change: action pressure, dialogue leverage, discovery, cost, relationship shift, or payoff.
- For long chapters, keep one continuous chapter voice: grouped scenes are planning units, not separate disconnected fragments.

## 场景执行规则

- 场景衔接规则：下一段必须吃住上一段留下的动作、情绪或风险，不要只靠关键词拼接。
- 每个场景都必须落地本场目标、正面阻碍、本场转折、情绪变化、对话职责和收尾钩子（以导演脚本实际字段为准）。
- 场景结尾必须自然推出下一场，不要用总结句硬切。
- 章末必须让局势相比章首发生实质变化，再把压力递到下一章。

## 对话与推进规则

- 对话硬要求：只要进入对话场，至少两轮来回，其中一轮必须改变主动权、信息量或风险级别。
- 开篇前预算内必须让读者看见本章动作目标与第一层阻碍，禁止把开场耗在纯氛围、纯回忆或纯解释上。
- 每 2-3 段至少发生一次可感知变化（动作推进、对话攻防、信息释放、关系变化或风险升级）。
- 直接输出章节正文，不输出分析、JSON、小标题、开场白或结束语。