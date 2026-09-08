# 小说质量原目标复核与下一批修复

> 核验日期：2026-09-06。工作在当前Agent接续分支，不把main分支、旧批次、结构审计或自动化通过替代真实质量收益。
> 当前后端冻结全量在运行；本轮仅读取源码、既有脱敏批次及标签文件，执行纯元数据审计和临时fixture探针。未改生产源码、真实标签、数据库或调用外部Provider。

## 1. 原目标与当前结论

质量任务矩阵包含26项T任务、12项E任务和1项外部标签要求，共39项。当前完成资格重算仍为`completion_eligible=false`，七项硬缺口保留。

**重要纠偏：**历史接续文档声称当前`PipelineOrchestrator(StoryQualityScoringMixin)`已接线，但该叙述属于local `main` 的`089aba445fc67dc1d4e0553c4767a66fe7493040`。当前Agent分支没有`story_quality_scoring.py`，评分方法位于`pipeline_orchestrator.py`内。部分功能显然已在内联实现中，因此“文件未拆分”不等同“功能未移植”；独立方法级审查另见本轮SCORING_PARITY报告，禁止直接覆盖或合并两条分支。

## 2. 七项硬缺口：新复算结果与所缺证据

| 原要求 | 本轮实际证据 | 仍需完成 |
|---|---|---|
| E-01.2 prompt gain | 重算既有10对controlled A/B；scorer平均分差+144.4，平均字数差-695.1 | 重复受控生成、独立/人工质量评价、预注册成本与质量准入；不把scorer得分变化当用户偏好 |
| E-11 / T-22 real repair gain | 当前审计exit2、status=insufficient；2次尝试/4轮均unchanged，完整diagnostics缺失 | 实际质量门进入→定向修复→完整前后诊断→严格子集改善→最终通过的真实Provider链 |
| T-06 standardized degrade rate | 当前审计exit2、status=insufficient；输入契约不统一，rate=null | 同Provider/model/mission/request/scorer/comparison契约和完整retry_events的连续批次，满足既定样本门槛 |
| T-16 real before/after | 有corrected结构接口和selector simulation；未找到可以直接认作真实质量增益的成对证据 | 固定输入manifest及生成契约、不同production scorer、同一独立冻结evaluator；真实输出与内容指纹绑定 |
| T-18 exemption truth | 6条专项样本；reviewer A/B及labels均0条填写 | 实际独立双审、争议裁决及分层接受率/误杀率，保留来源身份 |
| T-26 dialogue marker calibration | 存在标记计数与测试，但人工语义真值尚缺 | 按信息/主动权/关系/风险/选择分层标注并计算precision/recall；不要为通过样本而调词表 |
| human quality labels | 本轮逐CSV读取：通用19条0填写；专项6条0填写 | 完整审阅与来源核验，不以AI预标注、空CSV、全填true或测试fixture冒充人工真值 |

E-01.2旧附录的-79.5属于更早批次，不能覆盖随后保存的+144.4 controlled A/B；**两组数字都不证明生产文学质量收益**。本轮+144.4仅重算既有批次，没有新增外部生成。

## 3. 新发现：完成资格保护器的两项误放行

位置：`D:\小说写作\xuanqiong-wenshu\backend\scripts\audit_novel_quality_completion.py`。

### QG-01：未将审阅样本集合/身份绑定manifest

当前`_annotation_errors`与`_validate_merged_result`只核对两份CSV及合并文件互相一致，未读取manifest进行完整集合比对。临时fixture放入真实manifest的六个T18样本ID，却提供另一条`Q001`的两份完整CSV和合并文件；保护器返回`completion_eligible=true`且errors为空。

**修复验收：**缺manifest、manifest格式错误、selected_count不符、重复ID、样本缺失/多余、内容sha/章节/版本不符均拒绝；两份CSV完整对应manifest、身份一致时保留正常通过路径。不要硬编码样本数6，使用经过验证的manifest集合。

### QG-02：合并结果可反转两位审阅人的一致标签

同一个临时fixture中，两位审阅人八个维度全部`false`，`merged-annotations.json`全部`true`；当前保护器仍返回合格。检查合法枚举不等于验证合并结论的来源。

**修复验收：**普通merge对一致标签必须原样保留；分歧保留未解决状态，或由已有明确裁决格式提供可验证的裁决人、结论及说明后接受。先核对现有export/merge/adjudication合同，再接线；不将所有分歧强行取true或偷偷改变人工结论。

### QG-03：原始merge遮住合法裁决文件

现有完整链已经有`merge_quality_annotations.py`及`adjudicate_quality_annotations.py`，后者输出裁决人、说明、逐项原值与结论、source_merged_sha256。临时fixture调用这两个真实函数产生合法裁决，并同时保留原始merge与adjudicated文件；当前`_find_merged_result`优先选择原始merge，仍报未解决`adjudicate`，从而误阻断合法流程。

**修复验收：**优先验证裁决产物，但必须校验其原merge哈希、CSV身份与原始标签、实际分歧集合、决议来源及每项结论。无效裁决不静默退回另一个文件获得通过；原始merge保留用于溯源，不要求人工删除证据。合法无分歧merge和完整裁决两条正向流程均通过。

独立证据：`D:\小说写作\xuanqiong-wenshu\logs\quality-adjudication-shadow-probe-20260906.json`，valid_adjudication=true，both_merge_and_adjudication_present=true，但completion_eligible=false且错误指向原merge未解决值。真实标签未改动。

### 探针证据

`D:\小说写作\xuanqiong-wenshu\logs\quality-completion-guard-negative-probe-20260906.json`：

- fixture_only=true；real_annotations_modified=false；provider_calls=false。
- manifest_sample_count=6；reviewer_sample_ids=[Q001]。
- manifest_mismatch_wrongly_eligible=true。
- unanimous_false_but_merged_true_wrongly_eligible=true。

探针使用当前测试辅助函数构造临时目录，实际调用当前audit函数；生产源码、真实标签未改动，临时fixture已清理。

## 4. 下一批执行顺序

1. 先读取当前冻结后端全量自然终态，不在运行中改源码。
2. 全量结束后，以QG-01/QG-02/QG-03先补失败回归，再修复保护器及合法fixture；保留原测试意图，新增manifest及merge来源检查不是删减通过路径。
3. 做反向验证：撤掉manifest绑定、撤掉一致标签校验时，新回归应失败；真实空标签仍应保持不合格。
4. 与UI-005/UI-006/评分方法级审查发现按影响排序，先处理真实会误判完成或破坏用户流程的问题，再做纯结构抽取。
5. 后续真实生成实验按既定固定契约采样，明确资源成本与调用来源；人工真值由真实审阅人形成，代理只做辅助检查。

## 5. 本轮可定位证据

所有新证据位于`D:\小说写作\xuanqiong-wenshu\logs`：

- `novel-quality-completion-recheck-20260906.json`：完成资格false、七个blocker；脚本自身audit_date是历史固定元数据，不表示本轮未重跑。
- `quality-label-inventory-20260906.json`：逐CSV实际行数、填写数、完整数。
- `e11-repair-gain-recheck-20260906.json`：insufficient，不宣称repair收益。
- `t06-standardized-recheck-20260906.json`：insufficient，rate保留null。
- `e012-prompt-ab-recheck-20260906.json`：controlled A/B，不是strict T16。
- `quality-evidence-recheck-exits-20260906.json`：上述CLI实际退出码分别2/2/0。
- `quality-completion-guard-negative-probe-20260906.json`：两项临时样本误放行复现。

当前总体目标仍为active；工程门禁和质量完成资格分开记录。即使冻结全量全绿，七项真实质量缺口及本轮误放行问题也不会自动消失。

## 6. 审计后的修复证据（阶段二）

QG-01/02/03已由主代理修复，源码改动在阶段一2017项全量自然结束、指纹核验之后进行。

- manifest必须完整、去重、selected_count一致、身份及SHA256合法，并与两份CSV全量一一对应。
- merge必须保留一致的true/false/na；分歧只能通过有来源的裁决解决。
- 裁决文件不再被原merge遮挡；通过现有apply_adjudication合同回放，核对CSV、source merge、决议、结论及来源hash；无效裁决不退回其他文件获得通过。
- 原有合法无分歧及完整裁决两条路径通过；未降低标准或删除原用例。
- 定向四文件55项通过；保存的旧实现与新回归组合32项失败，证明原问题被检出。
- 真实数据重算仍七项硬缺口，人工标签仍空白，未制造质量完成或收益证明。

这仅闭合证据验证器的三个缺陷，不闭合第2节的真实质量收益/人工真值要求。下一代码批仍需综合与冻结全量复核。
