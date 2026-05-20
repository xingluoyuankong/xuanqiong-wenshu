# 生成/重写质量重构实跑报告（2026-05-20）

## 范围

本轮优先处理大纲/蓝图/章节大纲/正文生成与重写链路中的质量和字数问题，重点不在 UI 重排。

外部参考只取方法，不照搬架构：

- OpenAI Structured Outputs：结构化输出应有 schema 约束和失败修复。
- OpenAI rate limit/backoff：429/瞬时失败需要退避、重试和 token 上限控制。
- Chapter.pub 章节长度参考：常见章节约 1500-5000 词，幻想类可更长，关键是篇幅服务节奏。
- Story Planner scene/sequel：场景应有 goal/conflict/disaster，后续反应应有 reaction/dilemma/decision。

## 真实实跑

- 服务：`http://127.0.0.1:8014/`
- Provider：CPA `http://localhost:8317/v1`
- 项目：`b1fc5ac3-c12b-4315-bd42-6dc881199516`
- 章节：第 1 章
- 目标字数：2200
- 最低字数：1900
- 最终候选：version `328`
- 实际字数：3803
- 状态：`waiting_for_confirm`

## 失败转修复

1. 首次实跑失败：质量门误判章末压力不足，未识别“见了地，才真会死人”等中文钩子。
   - 修复：扩展章末递压中文标记。
   - 回归测试：`test_ending_pressure_recognizes_specific_chinese_cliffhanger_markers`

2. 第二次实跑失败：scene 关键词匹配过死，AI 评审、对话改局、章末压力、一致性都支持可用，但 `scene_fulfillment_rate` 误杀。
   - 修复：质量门增加 AI 评审交叉证据，只在无 critical、一致性通过、对话改局、章末递压、字数充足时抵消 scene 关键词漏判。
   - 回归测试：`test_structural_quality_gate_uses_positive_ai_review_as_cross_check_for_scene_keyword_miss`

3. 优化阶段验证：节奏优化返回稿没有可靠保留“旧南渠/药渣味/死人风险”等关键锚点风险。
   - 修复：优化接口增加关键连续性 motif 守门，丢失原文关键地点/线索/风险词时拒收并回退原文。
   - 回归测试：`test_continuity_guard_rejects_optimizer_when_critical_motifs_disappear`

## 多视角评判

- 作者视角：首稿字数超过目标，场景密度和对话推进明显高于旧流程；仍需后续继续减少解释性总结句。
- 编辑视角：质量门不再只看机械关键词；会结合 AI 评审和硬性连续性指标，降低误杀。
- 读者视角：章末危险能递给下一章，水楼查账到旧南渠的悬念链条更清楚。
- 连续性审校：长篇连续性门通过，角色、伏笔、线索、场景任务均写入运行指标。
- 稳定性视角：CPA 曾出现 stream INTERNAL_ERROR，可靠调用工具箱的重试/退避路径继续有效；优化阶段新增丢锚回退保护。

## 后续建议

- 下轮继续把 scene 兑现从关键词命中升级为结构化抽取，减少对字符串命中的依赖。
- 长章 7000-10000 字压力样例仍应继续跑，但本轮已先修复短/标准章同样需要的质量门误杀和优化丢锚问题。
