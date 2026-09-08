# 文学质量缺口证据推进报告

> 实际整理时间：2026-09-07T05:50:28+08:00（文件名为批次标识）。范围仅覆盖日志与新报告；没有修改 continuation、生产业务代码、数据库、上传文件或人工标签。
> 本报告把自动评分变化、夹具回归和人工真值严格分开，不把任何自动指标写成文学收益。

## 结论

本批最可落地的两项推进已经落地：

1. **T26 对话状态标记校准夹具**：新增 10 条边界夹具，覆盖信息、主动权、关系、风险、选择五类语义 strata；当前实现 10/10 通过。夹具参考值明确标为 `fixture_reference_not_human_label`，不能替代真实章节人工 precision/recall。
2. **E01.2 Prompt A/B 证据重算**：新增严格的逐条契约/记录集合/内容文件/摘要指纹审计。历史批次形成 10 条配对观测：均值分差 `+144.4`，中位数分差 `-6.0`，候选分数上升 4 条、下降 5 条、持平 1 条；均值字数差 `-695.1`。这批结果只记作受控 A/B 观测，不构成生产文学收益或 T16 严格 before/after。

**当前发布/完成结论：仍不满足。** 本轮没有新增人工标签、没有新 Provider 生成，也没有宣称收益。

## 新增文件

| 文件 | 用途 |
|---|---|
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/audit_literary_quality_gaps.py` | 只读 T26/E01.2 审计器；拒绝重复 mission、缺分数、契约漂移、摘要篡改、路径越界和不完整指纹 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/test_audit_literary_quality_gaps.py` | 29 条定向回归；含输入篡改、路径边界和 T26 必需对白缺失用例 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/run_mutations.py` | 7 个进程内变异验证入口，不写回生产源码 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/recheck_existing_evidence.py` | 重跑 completion、E11/T22、T06、T16 审计并盘点标签文件 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/observations-final.json` | T26/E01.2 机器可读结果 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/gap-recheck.json` | 现有七项缺口复核结果 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/mutation-results.json` | 反向验证结果 |
| `D:/小说写作/xuanqiong-wenshu/logs/literary-quality-evidence-audit/*.log` | 命令 stdout/stderr 原始记录 |

## T26 结果

- 夹具总数：`10`。
- 通过：`10`；失败：`0`。
- 五类 strata 覆盖：`{"agency": 2, "choice": 1, "information": 2, "none": 1, "relationship": 2, "risk": 2}`。
- `human_labels_available=false`。
- `corpus_precision_recall_claim=false`。

这一步的工程价值是把当前阈值语义锁成可回归的边界合同，尤其覆盖：无对白、叙述中出现状态词、只靠标点、一个状态信号、两个状态信号、未声明对白和对白预期却完全缺失。它没有把这些夹具冒充人工标注，也没有调整生产阈值。

## E01.2 结果

审计状态：`controlled_ab_observed_not_strict_t16`。

| 观测项 | 结果 |
|---|---:|
| 配对 mission | `10` |
| 候选分数均值差 | `144.4` |
| 候选分数中位数差 | `-6.0` |
| 候选字数均值差 | `-695.1` |
| 分数上升/下降/持平 | `4/5/1` |
| 新增/移除 issue-code 的配对数 | `1/1` |
| leave-one-mission-out 均值差范围 | `[-15.11, 282.67]` |

审计强制核对：两侧 summary 均为 passed、mission 集合唯一且相同、Provider/model 相同、scorer 与 mission contract 相同、generation request contract 不同、每条 payload 的 prompt variant 正确、prompt digest 完整、内容文件存在且位于运行目录内、摘要聚合可重算、指纹可重算。

解释：均值为正但中位数为负，且下降配对多于上升配对；因此本批不支持“整体质量提升”结论。`production_literary_gain_proven=false`、`strict_t16_before_after_proven=false`、`human_preference_proven=false`。

## 现有缺口复核

- completion：`completion_eligible=False`；硬缺口仍为 `E-01.2_prompt_gain, E-11_T-22_real_repair_gain, T-06_degrade_rate, T-16_real_before_after, T-18_exemption_quality_truth, T-26_dialogue_marker_calibration, human_quality_labels`。
- E11/T22：`status=insufficient`；repair 2 条、diagnostics 0 条、strict-subset improvement 0 条、有效 gain 0 条、unchanged 2 条。
- T06：`status=insufficient`；两个单独满足观测条件的批次共20次调用，但两批契约不同，未形成统一cohort，所以 `degrade_rate=null`；0条重试事件不等于已证明退化率为0。另1个Provider阻断批次被排除。
- T16：全量扫描 49 个 summary，其中 23 个指纹完整；识别12个不同scorer候选配对、2个同scorer/同contract可比配对。后两对仅属既有审计器的结构可比记录，并非不同生产版本加同一独立冻结evaluator的真实before/after收益证据。
- 人工标签：4个CSV共37行（包含同一6条T18样本的三份模板，不是37个独立样本），`any_filled_rows=0`、`complete_label_rows=0`、`reviewer_identity_rows=0`；labels/manifest 指纹前后相同。

## 反向验证

- 定向回归：`29 passed`。
- 变异验证：7/7 校验点被检出，`all_detected=true`。
- 审计脚本、测试脚本和 `D:/小说写作/xuanqiong-wenshu/backend/app/services/pipeline_orchestrator.py` 的指纹前后一致，`source_hashes_unchanged=true`。
- 变异点包括：关闭摘要聚合校验、重复 mission、错误 variant、改变非 Prompt 生成参数、破坏 mission 指纹、内容路径越界、强制 T26 全部通过。

## 可复跑命令

```powershell
& "D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe" -m pytest -q "D:\小说写作\xuanqiong-wenshu\logs\literary-quality-evidence-audit\test_audit_literary_quality_gaps.py"
& "D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe" "D:\小说写作\xuanqiong-wenshu\logs\literary-quality-evidence-audit\audit_literary_quality_gaps.py" --output "D:\小说写作\xuanqiong-wenshu\logs\literary-quality-evidence-audit\observations-final.json"
& "D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe" "D:\小说写作\xuanqiong-wenshu\logs\literary-quality-evidence-audit\run_mutations.py"
& "D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe" "D:\小说写作\xuanqiong-wenshu\logs\literary-quality-evidence-audit\recheck_existing_evidence.py"
```

脚本退出码约定：定向测试与夹具审计成功返回 0；E11/T22、T06 证据不足时保留审计器既有的非 0 退出码，但报告中的 `insufficient` 是证据状态，不是业务代码失败。

## 后续最短路径

1. T26：用真实章节 manifest 选取五类 strata，添加两位独立审阅者的真实标签、身份和仲裁文件；在标签到齐前维持 `precision/recall=null`。
2. E01.2：固定mission、Provider/model和非Prompt生成参数，仅改变Prompt（因此request contract按设计不同）；预注册质量与成本门槛，补足随机重复批次、tokens和延迟字段，用独立冻结evaluator评价。
3. T16：单独固定生成输入与契约，记录真实生产before/after版本及改动；逐条绑定生成时的正文摘要、生产版本和独立冻结evaluator版本。不要把同scorer重复批次或Prompt A/B当作该证据。
4. E11/T22：等待真实质量门进入、保存完整 before/after diagnostics 和 issue-code 严格子集改善；unchanged 保持为无收益。
5. T06：在同一 contract 下生成完整 retry_events 的连续批次，达到原门槛后才计算 degrade rate。

本批交付的是证据基础设施和可复现边界测试，不改变七项硬缺口的完成状态。


## 证据解释和主线隔离

- leave-one-mission-out范围是逐一移除一条mission后的均值敏感性检查，不是置信区间，也不是显著性检验。
- 当前正文SHA256只锁定本轮读取到的字节。历史summary未逐条携带生成时正文摘要，因此没有证明历史分数与当前正文的密码学绑定；本轮也没有重跑历史scorer。
- T26的五类标签只是夹具设计分组，不是人工语义判断；通过只能证明词表阈值分支符合现有合同。对白缺失必失败由独立第29条测试覆盖，不包含在10条夹具统计内。
- 全部新增Python最终位于logs目录。早期曾短暂置于backend的两个新增文件已移回日志目录，没有修改已有业务文件。早期路径/夹具契约错误随后修复，最终结果以final-tests-post-mutation.log为准。
- 用户告知session54497为探索性后端全量；当前工具上下文查询返回Unknown process id，不据此推断运行成败。本文29条是独立定向测试，未宣称后端全量、前端全量或发布冻结门禁通过。
- logs被现有.gitignore忽略。脚本真实存在于工作区，但未进入Git跟踪；后续如需纳入版本控制，应单独评审搬迁或精确添加，不批量解除日志忽略。


## 阶段十一只读重算（2026-09-07 12:24 +08:00）

新证据目录：`logs/stage11-quality-recheck-20260907T122447/`；没有覆盖上述旧审计输出。

- completion：exit0，`goal_status=active`、`completion_eligible=false`、hard_gap_count=7。
- E11/T22 repair：exit2，`status=insufficient`、`gain_claimed=false`。
- T06：exit2，`status=insufficient`、三项rates均null；证据不足的退出码不等于代码故障。
- T16可比性审计：exit0，只代表审计运行结束，未据此宣布改前后收益。
- 基础标签19条、T18标签6条与两份6条reviewer模板均0行已填人工字段；样本身份无错误。模板不是额外独立样本，不累加成37份真值。
- `labels_and_manifests_unchanged=true`；所有人工标签保持原样。

继续按硬缺口而非测试数量决定完成资格。
