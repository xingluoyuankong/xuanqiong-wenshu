# 玄穹文枢质量优化任务接续计划

> 文件：`TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md`  
> 审查时点：2026-09-04  
> 工作区：`D:\小说写作\xuanqiong-wenshu`  
> 编写角色：执行子智能体 E  
> 本次范围：全面审查、证据盘点、分支差异核对、接续计划更新；本次仅新增本文件，未编辑业务代码。
> **最新执行状态（2026-09-04）**：本文件早期第 1—9 节记录的是 `main` 质量主线审查证据；当前实际接续分支已切换为 `codex/bohrium-integration-20260831`，最新 UI-004 实施、测试、真实服务冒烟和下一步均以文末追加记录为准。质量主线的独立证据附录位于 `docs/reports/quality-continuity-evidence-20260904.md`。

---

## 1. 文档定位与接续规则

本文件是当前 `main` 工作区的可执行接续入口。历史会话对应的原始文档为旧分支中的 `TASK_HANDOFF_NOVEL_QUALITY.md`；该文件在当前 `main` 相对旧分支的差异中已被删除，因此后续工作以本文件为入口，并以 JSON 审计产物和可复跑测试输出为证据源。

接续规则：

1. 先保留当前工作区全部未提交内容，再做审计或测试。
2. 质量结论只接受可定位的测试输出、审计 JSON、快照摘要和 Git 差异；历史报告中的“全绿”数字先视为历史信息。
3. 任何质量门优化都先建立失败样本，再实现修复，再跑定向测试，最后跑完整后端门禁。
4. “实现完成”“观测存在”“证据闭环”“达到完成资格”分开记录，不把其中一项替代另一项。
5. 业务代码后续每次变更都要配套：变更说明、测试命令、结果摘要、证据文件、回滚点。

---

## 2. 基线

### 2.1 Git 基线与分支定位

| 项目 | 实测值 |
|---|---|
| 当前分支 | `main` |
| 当前 HEAD | `089aba445fc67dc1d4e0553c4767a66fe7493040` |
| 当前 HEAD 提交 | `refactor: centralize generation quality scoring` |
| 旧接续分支 | `origin/codex/final-continuity-20260520` |
| 旧分支 HEAD | `8fcf4d35ca473560b38fca54bff619fa02671c42` |
| main 相对旧分支新增提交 | 50 |
| 当前工作区状态 | dirty；`git status --porcelain=v1` 返回 15 个顶层条目 |
| 旧接续文档状态 | 仅在旧分支历史中存在；当前 `main` 中删除 |

当前 `main` 的质量评分架构已经完成一次关键收口：

- `backend/app/services/pipeline_orchestrator.py` 引入并继承 `StoryQualityScoringMixin`。
- `backend/app/services/story_quality_scoring.py` 现为生产路径接线后的评分/清理实现，当前约 1557 行。
- `backend/app/services/pipeline_orchestrator.py` 当前约 6171 行，生产质量评分调用点直接通过 mixin 提供。
- `backend/app/services/test_generation_quality_guards.py` 当前约 1746 行。
- 提交 `089aba4` 的核心差异：3 个质量相关文件合计 `96 insertions(+), 681 deletions(-)`；其中编排器删除原地重复实现，评分逻辑集中到 mixin。

### 2.2 与旧分支的整体差异

`git diff origin/codex/final-continuity-20260520..main` 实测：

- `1582 files changed`
- `13858 insertions(+), 64109 deletions(-)`
- backend：1389 个文件，`1680` 行新增、`37076` 行删除
- frontend：156 个文件，`9681` 行新增、`18532` 行删除
- docs：14 个文件，`2496` 行新增、`564` 行删除
- 旧接续文档及旧生产计划类文档在本次差异中被删除或迁移；不能用旧分支文件存在性推断当前代码缺失。

整体差异包含大量存储、生成产物、历史计划和前端整理，后续审查应优先看下列质量主线文件，而非一次性阅读整个差异：

- `backend/app/services/story_quality_scoring.py`
- `backend/app/services/pipeline_orchestrator.py`
- `backend/app/services/test_generation_quality_guards.py`
- `backend/app/scripts/audit_novel_quality_completion.py`（若路径存在则以当前路径为准）
- `backend/output/novel-quality-completion-audit-current-20260823.json`
- `backend/output/novel-quality-task-matrix-current-20260823.json`
- `backend/output/novel-quality-gap-register-20260823.json`
- `audit/production-readiness/evidence/`

### 2.3 当前工作区保护状态

当前工作区存在未跟踪审计产物、运行数据库、前端测试产物和生成文件，包含：

- `audit/`
- `backend/storage/`
- `storage/`
- `backend/backend/`
- `frontend/test-results/`
- `backend/smoke-validation.db-shm`
- `backend/smoke-validation.db-wal`
- `FINAL_22_AUDIT.md`
- `FINAL_DELIVERY_REPORT.md`
- `OPTIMIZATION_ROUND5_REPORT.md`
- `backend/app/services/test_llm_service.py`
- `backend/app/services/test_research_service.py`

这些内容视为现有工作成果或运行证据。后续操作以只读检查和增量写入为主；不得用重置、清理或批量覆盖方式处理工作区。

---

## 3. 权威证据盘点

### 3.1 完成资格审计

权威文件：`backend/output/novel-quality-completion-audit-current-20260823.json`

实测字段：

- `audit_date`: `2026-08-23`
- `goal_status`: `active`
- `completion_eligible`: `false`
- `hard_gap_count`: `7`
- 审计策略：存在任何 hard gap 时，保持 active，不把自动化绿灯当完成。

当前 7 个 hard gap：

1. `E-01.2_prompt_gain`
2. `E-11_T-22_real_repair_gain`
3. `T-06_degrade_rate`
4. `T-16_real_before_after`
5. `T-18_exemption_quality_truth`
6. `T-26_dialogue_marker_calibration`
7. `human_quality_labels`

### 3.2 任务矩阵

权威文件：`backend/output/novel-quality-task-matrix-current-20260823.json`

- T 类任务：26
- E 类任务：12
- 外部人工标签缺口：1
- 索引总条目：39
- hard gap：7
- 矩阵用途：证据索引和任务状态追踪，不替代真实质量真值。

矩阵已经明确指出：

- 自动化测试通过、受控 A/B、selector simulation、重复批次、AI 预标注、空标签都不等于完成。
- E-02 已有分布观测，但还缺人工质量区分真值。
- T-25 只有单次真实成功与单次真实失败，不代表多任务泛化。

### 3.3 十万字长篇证据

项目证据目录：`audit/production-readiness/evidence/`

#### 正文基线

文件：

`audit/production-readiness/evidence/novel-100k-baseline-20260831-732b1b5a-30cf-4382-bb86-d9f7f7a9d182.md`

实测摘要：

- 项目：`732b1b5a-30cf-4382-bb86-d9f7f7a9d182`
- 标题：`优化后测试·雾港回声续篇`
- 生成时间：`2026-08-31T10:50:48.767294+00:00`
- 统计策略：`zh-visible-v1`
- 正式正文 `text_units`：`121295`
- 章节：`33/51`
- 覆盖率：`64.71%`
- 缺少 selected version：`18`
- 空 selected version：`0`
- 内容 digest：`075e2bfdb694b06d29a5aa25206cc108f84a1c9ddb032369df61cca038f11024`

这份证据说明长篇正文样本已超过十万单位，但项目仍处在部分章节完成状态；正文规模达标与全章节完成是两个独立指标。

#### 计划层候选

文件：

`audit/production-readiness/evidence/novel-100k-plan-candidate-20260831-732b1b5a-30cf-4382-bb86-d9f7f7a9d182.md`

实测诊断：

- 方案：`NOVEL_100K_OPT_V1`
- 目标正文单位：`100000`
- 卷候选：4 卷
- 计划层从 `chapter_outline.metadata` 推导 `volume_plan`
- metadata 覆盖 48 章，outline 覆盖 12 章
- 章节总数：55
- 缺少卷元数据：7 章，章节号 49–55
- `novel_outline_ranges_do_not_cover_all_chapters`：outline 覆盖 12，章节总数 55

因此，长篇上下文和正文已有实证，但计划层的章节覆盖仍需修正或明确其“候选计划”属性。

#### 上下文快照

文件：

- `audit/production-readiness/evidence/novel-100k-context-snapshot-20260831-732b1b5a-30cf-4382-bb86-d9f7f7a9d182-ch20.md`
- `audit/production-readiness/evidence/novel-100k-context-snapshot-20260831-732b1b5a-30cf-4382-bb86-d9f7f7a9d182-ch50.md`

章节 50 快照实测：

- 预算：`20000`
- 已选估算单位：`19772`
- selected：`57`
- excluded：`0`
- compressed：`22`
- stale：`0`
- conflicts：`0`
- digest：`15edacd226c237201796ffb9d659ff2f2593ec386cd3efefef9ae7b05e300270`

这支持“项目范围隔离、近期连续性上下文选择、压缩预算和冲突统计”已经有证据；它不等于章节正文质量和人工可读性已经闭环。

---

## 4. 已完成与已接线能力

### 4.1 质量评分生产接线

`089aba4` 之前，评分逻辑分散在 `pipeline_orchestrator.py`，同时存在孤立的 `story_quality_scoring.py`。当前提交已经完成 mixin 接线：

- `PipelineOrchestrator(StoryQualityScoringMixin)` 已落地。
- `_score_story_quality_candidate`、`_fallback_select_best_version`、`_evaluate_event_density`、`_evaluate_ending_pressure`、`_evaluate_dialogue_changes_state` 等生产调用统一走集中实现。
- 生产路径现在包含原孤立模块中已实现的能力：
  - 任务锚点命中；
  - 焦点角色命中；
  - 重复段落风险；
  - 章节标记/提纲残留检测；
  - 确定性清理和重复段落处理；
  - 字数上下限诊断；
  - 质量问题摘要和修复提示。

### 4.2 质量门和修复闭环

已有代码和测试覆盖：

- 一致性、自检、事件密度、静态描写、对白攻防、对白改变局势、章末压力、场景兑现、场景结构等质量维度。
- 质量门失败后按 blocker 生成定向修复提示。
- 修复轮次、严格子集采纳、修复诊断和运行时元数据已经接入。
- 候选版本选择已经从单纯长度偏好转向故事推进与结构质量评分。
- 非对白章节的对白维度已经使用三态语义：适用时为 `true/false`，不适用时为 `None`。
- 当前质量问题代码包含 `mission_anchor_missing`、`focus_character_missing`、`repetition_risk`、`chapter_artifact_markers` 等生产诊断项。

### 4.3 长篇和运行稳定性能力

从历史提交和现有证据可确认的已完成方向：

- 长篇上下文包和近期章节连续性选择。
- 角色状态、时间线、因果链、伏笔/线索和知识图谱的写后闭环。
- 生成调用的超时、取消、重试和心跳路径增强。
- 运行日志、SSE 进度和质量门事件可观测性增强。
- LLM 配置解析并发串行化、生成心跳串行化、取消任务回收和时区时间戳修正。
- 前端生成质量状态、日志和章节工作台的既有链路保留。

上述项目是“代码或运行证据已存在”的结论；是否在所有环境、所有 provider、所有长篇任务上稳定泛化，继续由第 5 节 hard gap 约束。

### 4.4 当前测试证据

1. 现有运行日志：
   - `backend/_card078_full_pytest_20260903-121234.log`：`1463 passed in 348.29s`
   - `backend/_card079_full_pytest_20260903-123209.log`：`1464 passed in 456.69s`
2. 当前质量守卫定向测试，使用当前环境可用插件组合实测：
   - 命令：
     ```powershell
     .venv\Scripts\python.exe -m pytest -q app/services/test_generation_quality_guards.py -p no:randomly -p no:seleniumbase -p no:sb_manager -rf
     ```
   - 结果：`67 passed in 11.40s`
3. 当前环境执行附加 `--timeout=120 --timeout-method=thread` 时，pytest 报 `unrecognized arguments`；说明当前环境的 pytest-timeout 参数未注册。后续门禁命令应以实际插件状态为准，不能直接复制旧命令的 timeout 参数。
4. 当前环境执行 `-p no:anyio` 后，质量文件中的 4 个异步测试因缺少异步插件而被收集为失败；这组结果用于说明插件依赖，不用于否定上面的 67 测试结果。

---

## 5. 未完成项与阻塞项

### 5.1 `E-01.2_prompt_gain`：提示词正文优化没有形成正向增益

证据：

- `backend/output/e012-prompt-ab-audit-reproducible-20260823.json`
- `backend/output/e012-prompt-ab-audit-20260823.json`
- `backend/output/t16-e012-contract-contradiction-audit-20260823.json`

当前事实：

- controlled prompt A/B 可以复跑。
- 同任务、provider、model、scorer 的约束已建立。
- candidate 平均分相对 baseline：`-79.5`
- candidate 平均字数相对 baseline：`-304.9`
- 结果没有资格进入生产默认策略。

接续出口：重复受控采样，固定任务和评分器，引入人工真值；以“平均质量提升且成本/长度变化可解释”为通过条件。

### 5.2 `E-11_T-22_real_repair_gain`：真实定向修复没有观察到严格子集增益

证据：`backend/output/e11-t22-real-repair-triggered-audit-20260823.json`

当前事实：

- `repair_attempted=true` 已观察 2 次。
- 合计 4 轮修复。
- 两次 `repair_outcome=unchanged`。
- blocker issue code 严格子集改善：`0`。
- 修复后的 passed/improved 增益：`0`。

已有的是可观测性增强，不是质量增益闭环。接续出口是获取一个同时包含“可修复 warning + blocker”的真实 provider 任务，记录 revise 注入、前后 issue code 集合和最终质量门状态。

### 5.3 `T-06_degrade_rate`：长期标准化降级率不足

证据：

- `backend/output/t06-full-gpt56-inventory-audit-20260823.json`
- `backend/output/t06-multi-batch-retry-distribution-audit-20260823.json`

当前事实：

- 19 批 inventory。
- 122 条成功记录。
- 16 条最终失败。
- 51 次调用缺少 `retry_events`。
- 批次契约、重复任务和 provider 失败混杂。
- 当前数据不支持宣布长期标准化 degrade rate。

接续出口：建立同一模型、同一任务契约、同一 retry/degrade schema 的连续批次，分离 provider failure、业务质量失败和代码异常。

### 5.4 `T-16_real_before_after`：严格生成前后对照尚未闭环

已有 selector simulation 证据：

- 纠正输入 manifest 遗漏后，当前 scorer 在 10 组池中选择 baseline/candidate 为 `5/5`。
- 选择结果相对旧 scorer 发生 `2/10` 变化。

该结果证明选择器行为发生变化，仍不等同于同一生成请求下 production scorer 的严格 before/after 质量提升。接续出口：固定输入 manifest、生成请求、provider/model、独立 frozen evaluator、内容 fingerprint，再做同一任务的前后生成对照。

### 5.5 `T-18_exemption_quality_truth`：豁免路径缺人工真值

证据：`backend/output/quality-annotation-bundle-t18-exemption-20260823/`

当前事实：

- 6 条脱敏样本。
- 1 条 `triggered_rejected`。
- 5 条 `not_triggered_success`。
- `content_emitted=false`。
- manifest 一致性已修复并通过。
- reviewer-a/reviewer-b 模板已生成、独立校验通过，但标签仍空白。

接续出口：两名独立审阅人分别填写，再 merge/adjudicate；把人工结果回写完成审计。

### 5.6 `T-26_dialogue_marker_calibration`：对白状态变化词表缺真实语义校准

历史实测已经发现：对于“具体揭示、做出选择、外部压力”等语义，当前计数器存在漏识别，实测标记数为 0，而测试要求至少 2 个。三态数据结构已经落地，词表质量仍需真实语料校准。

接续出口：构造带人工标签的对白样本集，按“信息变化、主动权变化、关系变化、风险变化、下一步选择”分层测量 precision/recall，再更新词表和回归测试。

### 5.7 `human_quality_labels`：通用人工双审未完成

证据：

- `backend/output/quality-annotation-bundle-20260821/labels.csv`
- `backend/output/quality-annotation-bundle-t18-exemption-20260823/labels.csv`
- `backend/output/quality-annotation-bundle-t18-exemption-20260823/manifest.json`

当前事实：

- 通用 19 条仍为 `0/19 labeled`。
- T-18 专项 6 条仍待填写。
- 模板格式校验可通过。
- `--require-complete` 最终校验仍不通过，完成行数为 0。

接续出口：两名独立审阅人完成通用 19 条和 T-18 6 条，执行 merge/adjudicate，并保留 reviewer 版本、最终标签和一致性摘要。

---

## 6. 分阶段全面优化方案

### Phase 0：工作区与证据冻结

目标：让后续每一轮结果可复现、可回滚、可区分。

动作：

1. 记录 `git status --short --branch`、HEAD、旧分支 tip 和工作区未跟踪清单。
2. 继续保留现有 `audit/rollback-snapshots/20260901/` 快照。
3. 为每轮测试保存：命令、返回码、pytest 收集数、passed、failed、失败集合和耗时。
4. 把 pytest 插件清单单独记录，建立“带 anyio”和“禁用 anyio”的两条命令，不混写结果。
5. 当前阶段只更新计划和证据索引，不碰业务代码。

完成条件：同一命令连续两次得到相同收集数和失败集合；任何插件差异都在日志中显式标注。

### Phase 1：测试运行器收口

目标：解决测试门禁口径漂移，恢复可信全量基线。

动作：

1. 读取 `backend/pytest.ini` 和环境已安装插件。
2. 运行完整 `app` 门禁，记录不带 timeout 参数的当前可用命令。
3. 单独验证异步测试插件；质量文件的 4 个异步测试需在正确插件下执行。
4. 输出一份新的全量基线 JSON/Markdown，包含收集数、通过数、失败数、失败摘要、插件版本和 Python 版本。
5. 将旧的 `727 passed, 36 failed` 保留为历史基线，不覆盖为当前值。

完成条件：全量门禁能够稳定返回并输出失败集合；后续每轮以失败集合增量作为回归判断。

### Phase 2：人工质量真值与对白校准

目标：先补齐所有依赖人工标签的 hard gap，再调整词表和提示词。

动作：

1. 完成通用 19 条双审标签。
2. 完成 T-18 6 条双审标签。
3. 执行 `--require-complete` 验证、merge、adjudicate，生成最终标签摘要。
4. 按对白状态变化五类语义重新标注 T-26 样本。
5. 计算 marker 词表的误报、漏报和分层召回；只把有标签支撑的词加入强信号集合。
6. 增加“非对白章节不适用”和“对白存在但状态未变化”的双向回归样本。

完成条件：人工标签完整、审阅者独立性和仲裁记录齐全；T-26 的指标和回归集可复跑。

### Phase 3：受控质量增益实验

目标：完成 E-01.2、T-16、T-06、E-11 的真实证据闭环。

动作：

1. 固定 10 个以上同契约任务池，保持 provider/model、输入 manifest、目标字数和独立 evaluator 不变。
2. 对 prompt A/B 做多批采样，不把单批负增益结果隐藏；保留每个候选的内容 fingerprint、质量分、人工标签和成本。
3. 对 scorer 做严格 generation before/after，而非只做 selector simulation。
4. 统一 retry/degrade 事件 schema，补齐缺失 `retry_events` 的任务后再估计 T-06。
5. 构造含 blocker 与可修复 warning 的真实任务，验证 repair 前后 issue code 严格子集、最终 passed 和内容变更。
6. 对 provider block、业务质量失败、代码异常分别计数。

完成条件：每个 hard gap 都有明确 acceptance test；实验结果支持“通过、未通过、样本不足”三态，不用样本不足冒充通过。

### Phase 4：长篇计划与连续性收口

目标：把十万字规模证据从“部分章节样本”推进到“计划覆盖、上下文隔离、连续性质量”三层闭环。

动作：

1. 修正或明确 49–55 章的 volume metadata 和 chapter outline 覆盖关系。
2. 对章节 20、50 等上下文快照做同一 schema 的预算、压缩、stale、conflicts 对比。
3. 为选定章节生成正文质量摘要，关联任务计划、上下文 digest、版本 fingerprint。
4. 对长章执行事件密度、场景结构、章末压力、角色状态、因果承接的组合审计。
5. 把长篇失败样例和局部修复结果写入同一 evidence bundle。

完成条件：计划覆盖和正文覆盖分开可见；任一章节都能从计划 → 上下文 → 候选 → 质量门 → 定稿/阻断追溯。

### Phase 5：架构与持续优化收口

目标：在证据闭环后再推进持续优化，不再依赖孤立模块或历史报告。

动作：

1. 以 `StoryQualityScoringMixin` 为唯一生产评分实现，持续检查是否出现第二份同名逻辑。
2. 将质量规则、阈值、词表和版本号结构化输出到 runtime metadata。
3. 把质量门 blocker、修复轮次、最终决策和回滚引用统一到一份事件 schema。
4. 建立每轮质量趋势报表：总体分、各维度分、人工一致性、provider 状态、耗时、成本和回归集合。
5. 将所有“完成”字段绑定到完成资格审计脚本，禁止手工改成完成。

完成条件：代码、证据、审计、报告四者互相引用；新会话只读本文件即可继续工作。

---

## 7. 验证命令

以下命令按当前 Windows PowerShell 工作区编写。命令输出要写入本轮证据文件，避免只在终端展示。

### 7.1 工作区与分支

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu'
git status --short --branch
git log --oneline --decorate -20
git show -s --format=fuller HEAD
git show -s --format=fuller origin/codex/final-continuity-20260520
git rev-list --count origin/codex/final-continuity-20260520..main
git diff --stat origin/codex/final-continuity-20260520..main
```

### 7.2 质量评分架构核对

```powershell
rg -n "StoryQualityScoringMixin|class PipelineOrchestrator|def _score_story_quality_candidate|def _evaluate_event_density|def _evaluate_ending_pressure|def _apply_deterministic_cleanup|repetition_risk" backend/app/services/pipeline_orchestrator.py backend/app/services/story_quality_scoring.py backend/app/services/test_generation_quality_guards.py
```

### 7.3 当前环境可用的质量守卫定向门禁

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\backend'
.venv\Scripts\python.exe -m pytest -q app/services/test_generation_quality_guards.py -p no:randomly -p no:seleniumbase -p no:sb_manager -rf
```

本轮实测：`67 passed in 11.40s`。

### 7.4 全量后端门禁

先执行环境探测：

```powershell
.venv\Scripts\python.exe -m pytest --help | Select-String 'timeout|anyio|randomly|seleniumbase|sb_manager'
.venv\Scripts\python.exe -m pip list | Select-String 'pytest|anyio|asyncio|timeout|selenium'
```

在插件状态确认后运行：

```powershell
.venv\Scripts\python.exe -m pytest -q app -p no:randomly -p no:seleniumbase -p no:sb_manager -rf
```

旧接续文档中的 `--timeout=120 --timeout-method=thread` 属于历史命令形态；当前环境实测对该参数报 `unrecognized arguments`，先以插件探测结果为准。

### 7.5 编译与前端门禁

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu\backend'
.venv\Scripts\python.exe -m compileall app

Set-Location 'D:\小说写作\xuanqiong-wenshu\frontend'
npx vitest run
npm run build
```

### 7.6 审计产物结构校验

```powershell
Set-Location 'D:\小说写作\xuanqiong-wenshu'
Get-Content 'backend/output/novel-quality-completion-audit-current-20260823.json' -Raw | ConvertFrom-Json | Out-Null
Get-Content 'backend/output/novel-quality-task-matrix-current-20260823.json' -Raw | ConvertFrom-Json | Out-Null
Get-Content 'backend/output/novel-quality-gap-register-20260823.json' -Raw | ConvertFrom-Json | Out-Null
Get-Content 'audit/production-readiness/evidence/novel-100k-baseline-20260831-732b1b5a-30cf-4382-bb86-d9f7f7a9d182.json' -Raw | ConvertFrom-Json | Out-Null
```

最后一条命令对应的 JSON 文件若被移动或改名，以同目录实际存在的 baseline JSON 为准；Markdown 摘要仍保留供人工审阅。

### 7.7 当前审计结论抽取

```powershell
$j = Get-Content 'backend/output/novel-quality-completion-audit-current-20260823.json' -Raw | ConvertFrom-Json
$j | Select-Object audit_date, goal_status, completion_eligible, hard_gap_count, blockers | ConvertTo-Json -Depth 8
```

预期结论仍为 `completion_eligible=false`、7 个 hard gap，直至第 5 节全部完成并重新生成审计产物。

---

## 8. 回滚点

### 8.1 文档层回滚点

- 当前文件：`TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md`
- 回滚方式：保留本文件上一版副本或从 Git 新增文件的提交中恢复；本轮未改业务代码。
- 若本文件尚未提交，回滚只涉及删除本文件，不触碰其他未跟踪成果。

### 8.2 质量评分架构回滚点

- 当前接线提交：`089aba445fc67dc1d4e0553c4767a66fe7493040`
- 关键父提交：`d646eaf` 及其前序质量评分实现。
- 旧分支质量接续基线：`origin/codex/final-continuity-20260520` / `8fcf4d35ca473560b38fca54bff619fa02671c42`
- 只把这些提交作为比较和恢复参考；恢复前先保存工作区 patch，并保留未跟踪证据目录。

### 8.3 数据和证据回滚点

`audit/rollback-snapshots/20260901/` 已存在以下恢复材料：

- `baseline-head.bundle`
- `tracked-working-tree.patch`
- `untracked-source-manifest.json`
- `layout.diff`
- `remote-doc-sync.mbox`
- `pre-bohrium-data/`

这些材料用于恢复提交指针、追踪文件差异、未跟踪文件清单和运行数据快照。任何恢复动作都必须先复制当前证据目录和当前状态输出。

### 8.4 测试回滚判定

出现以下任一情况时暂停下一轮业务优化并回到上一证据点：

- 全量测试收集数突然下降。
- 失败集合出现新成员。
- 异步测试因插件变化而从可执行变成 skipped/collection error。
- 质量守卫 67 项定向基线出现新失败。
- `completion_eligible` 在没有新人工真值或新真实 provider 证据时意外变为 true。
- 内容 digest、上下文 digest 或任务 manifest 在同一输入下发生未解释变化。

---

## 9. 下一次接续的第一组动作

按顺序执行：

1. 读取本文件第 2、3、5 节。
2. 保存当前 `git status --short --branch` 和插件探测输出。
3. 运行第 7.3 的 67 项质量守卫基线。
4. 运行全量后端门禁，生成当前失败集合。
5. 对照 7 个 hard gap，先处理人工标签和 T-26 校准所需的证据准备，不先改阈值。
6. 完成一轮证据闭环后，重新生成 completion audit、task matrix 和 gap register。
7. 只有审计 guard 允许时，才把对应条目标记为 completed；否则继续保持 active。

当前总判定：**质量评分生产接线已完成，长篇和运行稳定性有较完整实现与证据；质量优化总目标仍为 active，7 个 hard gap 尚未闭环。**

---

## 2026-09-04 续接更新：UI-004 成员管理 HTTP 与 Owner 不可变约束

### A. 本批目标

把 `project_members` 从服务层/Agent 读取权限推进到可操作的成员管理 HTTP 闭环，并锁定项目 Owner 不可被误转授、降级或移除。

### B. 实际修改文件

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\project_members.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\__init__.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_project_members_route.py
D:\小说写作\xuanqiong-wenshu\backend\app\services\project_access_service.py
D:\小说写作\xuanqiong-wenshu\backend\app\services\test_project_access_service.py
```

### C. 已落地能力

- `GET /api/projects/{project_id}/members`：列出活动成员；
- `POST /api/projects/{project_id}/members`：添加成员或恢复软删除成员；
- `PATCH /api/projects/{project_id}/members/{user_id}`：更新活动成员角色；
- `DELETE /api/projects/{project_id}/members/{user_id}`：软删除成员；
- 角色矩阵沿用 `owner/editor/viewer`，管理员可管理；
- 非成员、Viewer、停用用户、无效用户和无效角色均有明确错误路径；
- PATCH 不再直接改 ORM 字段，统一经过 `ProjectAccessService.update_member_role()`；
- Owner 角色以 `NovelProject.user_id` 为锚点；尚无所有权转移工作流前：
  - 不允许把 Owner 角色转授给其他用户；
  - 不允许 Owner 降级为 Editor/Viewer；
  - 不允许软删除 Owner；
- 既有旧项目 owner-scoped 兼容路径保留。

### D. 实测结果

定向回归：

```text
backend\.venv\Scripts\python.exe -m pytest -q app/services/test_project_access_service.py app/api/routers/test_project_members_route.py
8 passed in 20.51s
```

UI-003-D/E 与 UI-004 原有专项回归：

```text
41 passed
```

### E. 反向验证

本批新增测试会在以下保护被移除时失败：

- 恢复路由直接写入 `member.role`，绕过 Owner 不可变策略；
- 移除 Owner 转授检查；
- 移除 Owner 降级检查；
- 移除 Owner 删除检查。

当前没有保留破坏版本。

### F. 当前未完成边界

- 其他小说业务路由仍有 `ensure_project_owner` 或直接 `NovelProject.user_id` 过滤，成员权限尚未全域贯穿；
- Agent 工具执行、Artifact 读写、时间线/审计/Provider usage 的成员访问还需逐端点核验；
- 尚未完成真实启动后的多用户 HTTP/SSE/UI 验收；
- 尚未完成前端成员管理界面；
- UI-005 工具注册权限策略与 UI-006 长历史虚拟列表仍排队；
- 质量总目标继续为 `active`，不因本批专项全绿而提前收口。

### G. 当前 Git 状态与下一目标

当前分支：

```text
codex/bohrium-integration-20260831
```

当前基线提交：

```text
fdc8da5 Allow project members to read agent data
```

本批代码与文档尚未提交，先保留工作树，下一步继续执行：

```text
UI-004-B：按端点矩阵把 Agent Artifact、timeline、audit、provider usage、工具执行统一接入 ProjectAccessService，补成员 HTTP 回归。
```

随后：

```text
UI-004-C：真实多用户 FastAPI + SQLite + SSE 验收；
UI-004-D：前端成员管理 UI；
UI-005：工具注册 schema/策略；
UI-006：长历史分页、虚拟列表和移动端性能。
```

## 2026-09-04 追加：Agent 接续线全量门禁复核与两项基线纠偏

### A. 全量复核结果

在 `codex/bohrium-integration-20260831` 分支执行：

```text
backend\.venv\Scripts\python.exe -m pytest -q
```

首轮结果：

```text
1474 passed, 2 failed
```

两个失败均为已有测试契约与 UI-004 现状不一致，并非成员管理新路由运行错误：

1. 数据库失败映射测试没有把 Agent session lookup 设为数据库异常，实际按正确语义返回 session missing；
2. 项目 Provider usage 的非成员访问在成员权限模型下统一返回 403，旧测试仍断言 owner-scoped 时代的 404。

### B. 纠偏与复测

修正文件：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_database_errors.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_runtime_route.py
```

修正内容：

- 数据库失败测试在消息路由 session lookup 边界显式注入 SQLAlchemyError；
- 非成员 Provider usage 测试改为断言统一 403，避免泄露项目存在性。

定向复测：

```text
2 passed in 10.53s
```

成员/Reasoning/迁移/Agent stream 定向复测：

```text
45 passed in 42.29s
```

前端：

```text
npm run type-check       通过
npm run build-only       通过，4914 modules transformed
npm run test:run         77/78 文件通过，489/490 通过
```

前端唯一失败为并行高负载下 `src/views/AdminView.spec.ts` 20 秒超时；隔离重跑：

```text
npx vitest run src/views/AdminView.spec.ts --reporter=verbose
1 passed in 9.37s
```

因此该项判定为测试运行资源竞争/超时敏感，不把全量并行结果伪装成全绿；后续需降低并行负载或提高该测试的稳定超时配置后再做一次完整前端门禁。

生产构建警告：

```text
baseline-browser-mapping 数据超过两个月；
caniuse-lite 数据约 11 个月未更新。
```

该警告未阻断构建，列入 P2 依赖刷新任务。

### C. 新增提交

```text
1f2e265 feat: close project member management access loop
ab3c1d3 test: align access and database failure contracts
```

### D. 当前状态

- UI-004 成员管理 HTTP 已具备；
- Owner 不可转授/降级/移除策略已加固；
- Agent 分支工作树仍有未跟踪的 `TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260905.md`，该文件来自用户提供的次日环境上下文，当前权威接续文档仍为本文件（2026-09-04）；
- 全量后端需在两项测试契约纠偏后再跑一轮确认；
- 全部相关业务路由权限贯穿和真实 API/SSE 联调仍未完成。

### E. 下一批执行目标

```text
1. 重跑 backend 全量 pytest，确认 1476 项基线收口；
2. 修复或隔离 AdminView 并行超时，再跑前端全量；
3. 枚举 Agent router 的所有读取端点并补成员访问测试；
4. 启动真实后端，执行 health、成员管理、Agent reasoning、SSE 断线恢复 smoke；
5. 追加 UI-004 状态和证据后，再进入 UI-005/UI-006。
```

## 2026-09-04 最终回写：当前分支完整静态/单元门禁已收口

在修正 Agent 数据库异常测试注入边界、对齐项目成员拒绝语义、并把 `AdminView` 动态导入测试超时从 20 秒提升到 30 秒后，重新执行完整门禁：

```text
后端：backend\.venv\Scripts\python.exe -m pytest -q
结果：1476 passed in 644.36s

前端：npm run type-check
结果：通过

前端：npm run test:run
结果：78 files passed, 490 tests passed, 113.65s

前端：npm run build-only
结果：通过，4914 modules transformed，1m51s

git diff --check
结果：通过
```

前端构建仍提示 `baseline-browser-mapping` 和 `caniuse-lite` 兼容性数据较旧，未阻断本轮测试/构建；保留为 P2 依赖数据刷新任务。

本分支当前已包含本批提交：

```text
1f2e265 feat: close project member management access loop
ab3c1d3 test: align access and database failure contracts
d5972aa test: stabilize admin view import regression
```

本批结论：UI-004 成员管理 HTTP 与 Agent 读取权限基线的单元/静态门禁已经收口；真实服务启动、多用户 HTTP/SSE、全业务路由成员策略贯穿、成员管理 UI、UI-005、UI-006 和 main 质量主线逐批对齐仍是后续工作，任务总状态保持 `active`。

## 2026-09-04 追加：SQLite 启动路径修复与真实服务冒烟

### A. 发现与修复

首次运行根目录 `start.ps1` 时，尽管 `backend/.env` 配置为 `DB_PROVIDER=sqlite`，脚本仍在载入 `.env` 前把 provider 默认成 `mysql`，导致错误调用本地 MySQL 启动脚本并因缺少 `mysqld.exe` 退出。

修复文件：

```text
D:\小说写作\xuanqiong-wenshu\start.ps1
```

修复方式：

- 优先使用显式环境变量 `DB_PROVIDER`；
- 环境变量不存在时读取 `backend/.env` 的 `DB_PROVIDER`；
- 两者都缺失时才保留历史默认 `mysql`；
- 统一小写化后再决定是否启动本地 MySQL。

### B. 真实运行验证

修复后重新执行：

```text
.\start.ps1
```

结果：

```text
DB_PROVIDER=sqlite
skip local MySQL
BACKEND_READY=True
FRONTEND_READY=True
FRONTEND_PROXY_READY=True
backend=http://127.0.0.1:8013
frontend=http://127.0.0.1:5174
```

随后执行：

```text
Invoke-WebRequest http://127.0.0.1:8013/api/health
Invoke-WebRequest http://127.0.0.1:5174/api/health
.\verify.ps1 smoke
```

结果：

```text
后端 health：200
前端代理 health：200
OpenAPI 冒烟：259 项检查，55 通过、204 因缺少真实资源 ID 合理跳过、0 失败
LLM 设置冒烟：通过
verify.ps1 smoke：通过
```

### C. 当前边界

- 本轮证明 SQLite 配置下的正式本地启动、前端代理、健康检查和 OpenAPI 冒烟可用；
- 冒烟不替代带真实多用户项目、成员管理、Agent reasoning、SSE 断线恢复的端到端验收；
- MySQL 部署路径仍要求由部署环境提供正确 `mysqld.exe` 或 `XUANQIONG_WENSHU_MYSQLD_PATH`；
- 服务保持运行，后续可直接基于 8013/5174 继续多用户 UI/API 验收。

### D. 真实成员管理 API 验收补充

在已启动的本地 SQLite 服务上创建隔离项目后，实际调用：

```text
POST /api/novels
GET /api/projects/{project_id}/members
PATCH /api/projects/{project_id}/members/{owner_user_id}
DELETE /api/projects/{project_id}/members/{owner_user_id}
```

实际结果：

```text
member_count=1
owner_role=owner
owner_demote_status=422
owner_delete_status=422
```

该验收确认创建项目会同步生成 Owner 成员行，且 HTTP 层同样拒绝 Owner 降级与删除。该本地 API 验收使用的隔离项目 ID 为 `5e7bbd69-5509-45c8-ac09-255b3a13626d`；没有调用 Provider。

### E. 远端同步状态

本批本地提交已形成完整可回滚链，但推送到现有 `origin` 时返回 GitHub 403（当前本机认证身份没有该仓库写入权限）。代码、测试和接续文档全部保留在本地分支；不通过改 remote、不覆盖凭据、不改写历史来规避该问题。待本机切换到具有仓库写权限的 GitHub 身份后，执行：

```powershell
git push origin codex/bohrium-integration-20260831
```


## 2026-09-04 追加：UI-004-B 项目资源成员权限与成员面板接线

### A. 项目资源 API 权限贯穿

`backend/app/api/routers/projects.py` 的 13 个项目资源端点已经从旧 `NovelService.ensure_project_owner()` 收敛到统一 `ProjectAccessService`：

```text
读取（Viewer / Editor / Owner / Admin）：
- constitution
- persona
- memory
- memory snapshots
- character states
- factions

改写（Editor / Owner / Admin）：
- constitution
- persona
- memory
- incremental memory
- compress memory
- rollback memory
- factions
```

新增回归：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_projects_member_access.py
```

锁定 Viewer 读取、Viewer 写入拒绝、Editor 写入、非成员读写拒绝。

### B. 成员列表的访问投影

成员列表属于项目共享元数据，现改为所有活动项目成员可读取；写入管理仍限定 Owner/Admin。

`GET /api/projects/{project_id}/members` 新增：

```text
access_role
can_manage
```

前端不再根据本地猜测所有权决定操作权限，而是以服务端 `can_manage` 投影决定是否启用管理操作。

### C. 前端成员管理接线

新增：

```text
D:\小说写作\xuanqiong-wenshu\frontend\src\api\projectMembers.ts
D:\小说写作\xuanqiong-wenshu\frontend\src\api\projectMembers.spec.ts
D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\ProjectMemberPanel.vue
D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\ProjectMemberPanel.spec.ts
```

并在：

```text
D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue
```

的数据与候选区域新增“项目成员”折叠面板。面板支持列表、刷新、添加、角色变更、移除、Owner 控件锁定、服务端错误展示、只读成员态和移动端布局。

### D. 本批实测

```text
后端成员专项：11 passed in 60.05s
前端 AgentWorkspace + 成员 API + 成员面板专项：3 files / 24 tests passed in 36.25s
前端 type-check：通过
git diff --check：通过
```

### E. 下一项

UI-004 继续推进：对 `analytics`、`clue_tracker`、`foreshadowing`、`knowledge_graph`、`research`、`style`、`outline`、`writer` 和 Agent 工具执行入口按 read/write 分类逐批接入统一成员策略，并补真实多用户 SSE 验收。

## 2026-09-04 追加：UI-004-C Agent State Projection 成员读取修复

### A. 发现

真实 HTTP 成员回归先覆盖 reasoning、activity 与 state。Viewer 对 reasoning/activity 已可读，但 `GET /api/agent/runs/{run_id}/state` 仍按 `AgentRun.user_id == requester_id` 查询，导致项目 Viewer 返回 404。这与已定义的成员读取模型不一致。

### B. 修复

修改：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\agent\state_projection.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_project_member_http.py
```

State projection 现在：

- 先通过 `AgentRuntimeService.get_readable_run()` 统一解析 project member 可读性；
- 后续步骤、审批、Artifact、Job、Command、TaskRuntime 查询使用 Run 所属用户，而不是查看成员的用户 ID；
- Viewer 可获得安全状态投影，但 `allowed_commands=[]`；
- Editor/Owner/Admin 的可控制性仍由 `ProjectAccessService.require_project_read()` 返回的 write 能力决定；
- projectless Run 保持原有创建者隔离。

### C. 定向门禁

```text
app/api/routers/test_agent_project_member_http.py
app/agent/test_state_projection.py

11 passed in 19.45s
```

此批补齐 UI-004 所要求的 reasoning、activity、Run state 成员读取闭环。下一步仍是 SSE stream、Artifact/command 端点、其余业务路由与真实多用户 SSE 验收。

### D. 真实成员 Reasoning / Activity / State 验收

重启本地服务加载本批代码后，使用 Owner 创建项目关联 Agent Run，并以 Viewer Bearer 身份实际调用：

```text
GET /api/agent/runs/{run_id}/reasoning
GET /api/agent/runs/{run_id}/activity
GET /api/agent/runs/{run_id}/state
```

实际结果：

```text
reasoning_count=1
activity_count=2
state_owner_user_id=1
viewer_allowed_commands=[]
```

该结果验证了 Viewer 能读取 provider reasoning、公开活动和安全 Run state，且不会获得运行控制命令。

## 2026-09-04 追加：UI-004-D 项目协作权限第二批路由收口

### A. 已接入统一成员策略的模块

```text
clue_tracker.py
foreshadowing.py
knowledge_graph.py
analytics.py
analytics_enhanced.py
```

按端点语义划分为：

```text
Viewer/Editor/Owner/Admin 可读：
- 线索列表、概览、线程、红鲱鱼、未解决线索、线索时间线
- 伏笔列表、提醒、分析
- 知识图谱节点、边、概览、角色时间线、关联节点、线程、导出
- 情感曲线、伏笔分析、增强情感曲线、故事轨迹、创意指导、综合分析

Editor/Owner/Admin 可改：
- 线索创建、更新、删除、章节关联
- 伏笔创建、解决、提醒关闭
- 知识图谱节点/边创建、更新、删除
- 分析缓存失效
```

所有迁移端点均使用 `ProjectAccessService.require_project_read()` 或 `require_project_write()`；旧 `ensure_project_owner` 和 `NovelProject.user_id == current_user.id` 限制已从上述模块的目标项目路径移除。

### B. 新增回归

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_clue_foreshadowing_member_access.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_knowledge_analytics_member_access.py
```

覆盖：Viewer 可读、Viewer 写入拒绝、Editor 写入、非成员读写拒绝。第二个测试同时修正增强分析真实路由前缀为：

```text
/api/analytics/projects/{project_id}/...
```

### C. 实测

```text
成员权限路由专项：12 passed in 7.65s
Python compile：通过
git diff --check：通过
```

### D. 后续范围

下一批继续处理：

```text
research.py
style.py（含后台 worker 的 write 权限）
outline.py
review.py
patch_diff.py
token_budget.py
writer.py
Agent tool adapters / execution facts
```

每批继续保持 read/write 分类、失败测试先行、专项回归、真实 HTTP/SSE 验收和接续文档回写。

## 2026-09-04 追加：UI-004-E Research / Outline 成员权限闭环

### A. Research 路由

`research.py` 将旧 `_ensure_owner()` 拆分为：

```text
_ensure_read()
_ensure_write()
```

并接入 `ProjectAccessService`：

```text
read：config、artifacts、run status
write：config 更新、run、run/start、run cancel
```

### B. Outline 路由

`outline.py` 的权限按语义迁移：

```text
write：evolve、next、generate-long
read：alternatives、structure、history
```

`generate-long` 不再在通过成员写权限后再次调用旧 owner-scoped `get_project_schema()`；改为使用 `require_project_write()` 已解析的项目实体，避免 Editor 在第二层旧校验被截断。

### C. 测试与兼容调整

新增：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_research_outline_member_access.py
```

已有研究任务回归从旧 `NovelService` mock 调整为 `ProjectAccessService` mock，保持后台任务、取消、重启恢复的原测试意图。

实测：

```text
Research/Outline 成员权限 + 既有研究任务/大纲回归：33 passed in 17.95s
Python compile：通过
git diff --check：通过
```

### D. 后续

`style.py` 的 HTTP 与后台 worker 写权限、`review.py`、`patch_diff.py`、`token_budget.py`、`writer.py` 仍在后续队列。`test_style_member_access.py` 已存在红灯基线，待对应 style 实现同批收口。

## 2026-09-04 追加：UI-004-F Style HTTP 与后台任务成员写权限闭环

### A. Style 路由

`style.py` 已把 21 个 HTTP 项目校验从旧 owner-only 逻辑迁移到 `ProjectAccessService`：

```text
read：sources、library、upload status、profiles、profile status、active、style summary
write：sources 上传/删除、profile 创建/取消/更新、apply、active 删除、extract、style 删除、generate
```

### B. 后台 worker

以下后台链路也改为统一写权限校验：

```text
_run_style_source_upload_job()
_run_style_profile_job()
```

这样 Editor 发起的风格素材上传/画像任务不会在 worker 阶段被旧 owner-only 检查截断。

### C. 兼容回归

已有 `test_style_profile_job.py` 的权限 seam 从旧 `NovelService` mock 更新为 `ProjectAccessService` mock，保留任务启动、心跳、取消、恢复、跨项目阻断等原测试意图。

实测：

```text
Style 成员路由 + Style profile/source job 回归：21 passed in 16.53s
Python compile：通过
git diff --check：通过
```

### D. 队列更新

下一批优先：`review.py`、`patch_diff.py`、`token_budget.py`、`writer.py` 和 Agent 工具执行层；其中 `writer.py` 范围大，先做端点/服务调用图与测试矩阵，再按功能域分批迁移。

## 2026-09-04 追加：UI-004-G Review / Patch Diff / Token Budget 成员权限闭环

本批迁移：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\review.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\patch_diff.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\token_budget.py
```

权限分类：

```text
write：six-dimension review、consistency review、Patch apply/revert、预算配置/记录/告警处理/分配
read：文本 Diff、版本 Diff、Patch history、预算/使用量/模块使用量/告警
```

新回归：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_review_patch_budget_member_access.py
```

覆盖 Editor 写入、Viewer 读取、Viewer 写入拒绝和非成员拒绝；测试替身隔离 LLM、Patch 和预算持久化副作用。

实测：

```text
Review/Patch/Token 成员专项 + TokenBudget 服务回归：11 passed in 4.44s
Python compile：通过
git diff --check：通过
```

下一批进入 Writer H-1 读路径/运行态可见性和 Agent ContextRef P0 迁移。

## 2026-09-04 追加：UI-004 Agent ContextRef P0 成员协作修复

`backend/app/agent/context_refs.py` 已从旧 Owner-only `NovelService.ensure_project_owner()` 切换到 `ProjectAccessService.require_project_read()`。

共享项目 ContextRef 的可见性现在按项目成员权限判断，不再按创建者 `user_id` 截断：

```text
chapter / chapter_version
Agent Artifact
Quality Finding
Research Artifact
character / faction / foreshadowing / knowledge node
```

项目无关资源仍维持创建者隔离；跨项目 ContextRef 继续拒绝。

新增回归覆盖：Viewer 选择 Owner 创建的 chapter version 与 Agent Artifact 成功；非成员得到 403。

```text
backend/app/agent/test_context_refs.py
11 passed in 3.96s
```

下一 Agent P0：`tool_adapters.py`，将 `project.context`、章节/大纲/质量/统计/知识图谱/文风/研究/伏笔等只读工具改为项目成员可读；之后处理 `write_executor.py` 与单 Run execution facts。

## 2026-09-04 追加：UI-004 Agent 只读工具 P0 与全量回归合同对齐

### A. 十个项目只读工具成员化

`backend/app/agent/tool_adapters.py` 新增统一项目读取门和兼容序列化适配，以下工具现在支持 Owner / Editor / Viewer / Admin 的项目成员读取：

```text
project.context
chapter.inspect
chapter.version.list
chapter.version.diff
outline.inspect
statistics.project
knowledge.inspect
style.inspect
research.inspect
foreshadowing.inspect
```

非成员统一返回 403。项目无关资源继续维持私有隔离。

### B. 专项与反向验证

新增：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\agent\test_tool_adapters_member_access.py
```

专项：

```text
22 passed
```

反向移除统一成员读取门后：

```text
12 failed
```

恢复实现后专项重新通过。

### C. 既有回归合同修正

旧 adapter 测试把非成员项目读取表述为“空结果”或 `ValueError`。UI-004 统一合同为非成员 `403`，故更新：

```text
backend/app/agent/test_tool_adapters.py
```

并同步更新 clue / knowledge graph 路由既有测试的权限 mock：

```text
backend/app/api/routers/test_clue_tracker_route.py
backend/app/api/routers/test_knowledge_graph_route.py
```

定向复测：

```text
Agent tool adapters：48 passed in 14.30s
Clue / KnowledgeGraph 路由：2 passed in 3.35s
```

全量后端首轮发现的 6 个旧合同失败均已定位并修复；下一步重新执行完整后端门禁取得最终结果。

### D. 后续 P0

```text
write_executor.py：Editor 创建/接收候选，Viewer Artifact 可读
execution_facts.py：单 Run facts / provider summary 成员可读
writer.py H-1：状态、SSE、运行态项目成员读取
```

## 2026-09-04 全量门禁回写：UI-004 当前阶段稳定基线

在完成项目成员 HTTP、项目资源路由、Agent state/reasoning/activity、ContextRef、十个只读工具、Research/Outline/Style、Review/Patch/Token Budget 权限迁移后，完整回归结果：

```text
后端：1514 passed in 410.08s
前端 type-check：通过
前端 Vitest：80 files / 496 tests passed in 96.82s
前端 build-only：通过，4918 modules transformed，43.74s
git diff --check：通过
```

前端构建继续报告 `baseline-browser-mapping` 与 `caniuse-lite` 数据较旧，列为 P2 依赖数据更新，不影响本轮构建产物。

当前 UI-004 仍为 active：下一 P0 是 Agent `write_executor.py` 与 `execution_facts.py` 的成员可读/可写投影，随后进入 Writer H-1 运行态和 SSE 成员读取；其余旧 Owner-only 业务域继续按小批次迁移，不把本轮全绿当作总任务完成。

## 2026-09-04 追加：重启后的真实服务冒烟

本批代码已重新启动到本地 SQLite 服务：

```text
backend: 127.0.0.1:8013
frontend: 127.0.0.1:5174
```

验证：

```text
backend health：200
frontend proxy health：200
verify.ps1 smoke：通过
OpenAPI smoke：259 检查，55 通过、204 因缺真实资源合理跳过、0 失败
```

该结果验证当前已提交分支可以启动并完成基础 API/代理冒烟；项目成员的完整多用户 SSE、Writer H-1、Agent write executor 与 execution facts 仍是后续验收范围。


## 2026-09-04 接续回写：UI-004 Agent Execution Facts 单 Run 成员读取

### A. 本轮合并与范围审计

已对比根目录接续文档与误放置副本：

```text
根文档：D:/小说写作/xuanqiong-wenshu/TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
误放置副本：D:/小说写作/xuanqiong-wenshu/backend/TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
```

根文档此前仅将 `execution_facts.py` 标记为 Agent P0 待办；误放置副本包含本批完成记录。现已将该记录归并到本权威根文档，并删除误放置副本，避免后续接续读取到重复且位置错误的任务状态。

本轮文档维护只涉及上述两份接续文档：未编辑源码、测试文件、运行数据库、导入二进制或其他工作区工件。

### B. 已完成：项目单 Run execution facts 成员读取

当前提交：

```text
ddfce68 feat: expose execution facts to project members
```

实现文件：

```text
backend/app/agent/execution_facts.py
```

`AgentExecutionFactService` 新增项目 Run 的统一可读解析，并由以下两个单 Run 只读投影复用：

```text
list_for_run()
provider_usage_summary()
```

项目关联 Run 的读取合同：

```text
Owner / Editor / Viewer / Admin：通过 ProjectAccessService.require_project_read() 读取
非成员：HTTP 403
```

该规则适用于 Owner 创建的同项目 Run；Viewer 与 Editor 读取执行事实、调用状态、摘要统计时不再被 `AgentRun.user_id` 的创建者过滤截断。返回仍保持安全投影：execution facts 不返回 input/output JSON，Provider summary 不返回原始 provider attempts 载荷。

无项目关联的 Run 保持创建者私有：

```text
projectless Run：仅创建者读取
其他用户：AgentExecutionFactNotFound
```

本批没有扩大 worker 控制范围；以下执行协调写路径继续按原有创建者/worker 语义隔离：

```text
Run claim
lease
step claim
execution facts 写入
事件追加
状态机终态写入
```

### C. 回归与反向验证

新增专项：

```text
backend/app/agent/test_execution_facts_member_access.py
```

覆盖：

```text
Viewer：读取项目 Run execution facts 与 provider usage summary 成功
Editor：读取项目 Run execution facts 与 provider usage summary 成功
非成员：两类项目 Run 读取均返回 403
projectless Run：继续仅允许创建者读取
安全投影：正文与原始 provider attempts 载荷不出现在读模型中
```

实测基线：

```text
专项实现前：3 failed, 1 passed
专项实现后：4 passed in 2.68s
execution facts 既有 + 成员专项：8 passed in 4.03s
Python compile：通过
git diff --check：通过
```

反向验证已执行：临时移除项目 Run 的成员读取门后，专项立即变为：

```text
3 failed, 1 passed
```

失败覆盖 Viewer、Editor 与非成员的读取合同；随后按原始字节恢复实现，组合回归重新达到 `8 passed`。

### D. 当前全面审查结论

UI-004 的成员权限主线已经从项目成员管理、项目资源读写、Agent state/reasoning/activity、ContextRef、十个只读工具，推进到单 Run execution facts 和 Provider summary 的读取投影。当前确认：

```text
项目成员可读：Run、Reasoning、Activity、单 Run execution facts、单 Run Provider summary、项目级 Provider 汇总、十个 Agent 只读工具
Owner / Editor 可写：项目 Session / Run 创建及已迁移的项目业务写入口
Viewer：保持项目只读，未获得 Agent worker 控制权或候选接受权
非成员：项目资源与 Agent 读模型统一以 403 拒绝
projectless Agent 资源：继续按创建者隔离
```

仍未完成的 P0 缺口：

```text
write_executor.py：项目 Artifact / rewrite instruction 的成员可读投影；Editor 对候选创建、版本差异、候选接受的项目写权限；Creator/worker 控制权与协作成员权限分离
writer.py H-1：章节生成状态、大纲状态、SSE 进度、TaskRuntime 查询按项目成员读取；不再把 TaskRuntime.owner_user_id 作为项目资源读边界
Agent runtime readable projections：Artifact 列表、Approval 历史、事件分页的成员可读 API/HTTP 验收统一
```

当前工作树 HEAD 已包含 execution facts 修复；此前记录的完整后端/前端门禁是该批之前的稳定参考，不代替本提交后的全量门禁。执行 facts 本批已经取得专项与既有模块组合回归；后续完成下一 P0 闭环后，统一重跑完整后端、前端 type-check、Vitest、build-only 与真实多成员 HTTP/SSE 验收。

### E. 下一阶段 P0 执行计划

1. `write_executor.py`：先写成员矩阵测试，覆盖 Viewer 读取 Owner/Editor 生成的项目 Artifact、Editor 生成 rewrite 候选/版本 Diff/接受候选、非成员 403；保持 projectless Artifact 创建者隔离与 worker claim 隔离。
2. 将 `context_refs.py`、`tool_adapters.py`、`write_executor.py` 共同使用的项目 Artifact 读取/写入判定收敛为一致的 `ProjectAccessService` 语义，避免重新引入 `AgentArtifactRef.user_id == user_id` 或 `NovelProject.user_id == user_id` 的创建者过滤。
3. `writer.py H-1`：先完成状态与 SSE 的 read-only 路径，再迁移写入、运行恢复与后台定稿；TaskRuntime 保留发起者审计字段，但项目成员可读性仅以项目访问权限裁决。
4. 补真实多用户 HTTP/SSE 验收：Owner 创建项目 Run / 章节任务后，Viewer 可读取状态与安全投影，Editor 可执行项目写操作，非成员持续得到 403；并验证断线重连、终态围栏与跨项目隔离。
5. 在上述 P0 批次收口后，执行当前分支的完整质量门禁并回写新的权威实测数字，不使用历史报告替代当前结果。


## 2026-09-04 接续回写：UI-004 Agent write_executor 项目成员读写闭环

### A. 已完成范围

本批完成 `backend/app/agent/write_executor.py` 的项目成员访问闭环。项目关联的候选 Artifact、rewrite instruction、章节版本差异与候选接受不再仅按资源创建者 `user_id` 判定；读取与写入统一按项目成员角色裁决。

成员读写矩阵：

```text
项目 Owner / Editor：可读取项目 Artifact、rewrite instruction、候选质量结果、版本差异；可创建/执行候选写入并接受候选 Artifact
项目 Viewer：可读取项目 Artifact、rewrite instruction、候选质量 Gate 与版本差异；不可创建候选、不可接受候选、不可改变正式章节版本
项目非成员：项目 Artifact、质量、差异、候选接受及写入路径统一 403
项目无关 Artifact / instruction：继续仅对创建者可见与可操作
```

### B. actor_user_id 与 execution_owner_id 分离

项目协作写入不再把“当前操作成员”与“原运行创建者/执行协调者”混为一个身份：

```text
actor_user_id：当前发起读取、创建候选、接受候选或版本操作的项目成员；由 ProjectAccessService 进行 read/write 权限裁决
execution_owner_id：原 Run / candidate / worker 的创建者与执行协调归属；保留用于审计、运行恢复、lease 与 worker 控制
```

由此保证：Editor 对项目资源的协作写入不被 Owner 创建的 Run、Artifact 或版本记录截断；同时 Viewer 和其他协作成员未获得 worker claim、lease、终态控制或跨创建者执行接管权限。

### C. projectless 隔离、质量 Gate 与运行事件归属

```text
projectless Artifact / rewrite instruction：维持创建者私有隔离
项目 Artifact / instruction：成员读取投影按项目 read 权限开放
候选接受、正式版本写入：仅 Owner / Editor 的项目 write 权限允许
质量 Gate：成员读取同项目候选的安全质量投影；Gate 结果、finding、质量 lineage 保留原 Run / candidate 归属
运行事件：保留 execution_owner_id 作为事件与 worker 执行归属；成员读取不会改变事件写入者、序列、lease 或终态围栏
```

### D. 专项、既有与相邻回归

新增/更新的 write executor 成员访问专项覆盖：

```text
Viewer：读取 Owner / Editor 创建的项目候选 Artifact、instruction、质量 Gate 与版本差异
Editor：创建 rewrite 候选、读取版本差异、接受项目候选 Artifact
Viewer：候选创建与接受均被拒绝
非成员：项目读写路径均返回 403
projectless：非创建者仍隔离
```

实测：

```text
write_executor 成员专项：5 passed
既有 write_executor / Agent 相邻回归：15 passed
Agent Runtime、质量 Gate、Artifact / ContextRef 相邻回归：63 passed
```

这些回归确认本批没有通过放宽 worker 控制、删除 Gate 或降低事件归属约束制造通过；成员协作仅扩展项目资源的 read/write 投影。

### E. 当前未完成：Writer H-1 审查发现

Writer 路由仍是 UI-004 的最大剩余 P0 域。审查确认以下 Owner/创建者绑定尚需按依赖顺序迁移：

```text
1. 章节生成状态读取：get_chapter_generation_status() 仍经 NovelService.get_chapter_status_schema() 触发旧 Owner 校验
2. 大纲运行状态：get_chapters_outline_generation_status() 及 rewrite 状态仍是 Owner-only
3. SSE 章节进度：stream_chapter_progress() 顶层和 _find_chapter_runtime_task() 仍把 TaskRuntime.owner_user_id 作为资源读取过滤
4. 大纲恢复：_load_active_outline_job_from_runtime() 按 TaskRuntime.owner_user_id 过滤，协作成员无法读取 Owner 启动的活动运行
5. 章节生成/回包：_load_project_schema() 与 NovelService.get_project_schema() 存在二次 Owner 校验，Editor 即使通过入口也可能在回包阶段被截断
6. 后台定稿：_run_finalize_pipeline() 仍以 NovelProject.user_id 查询，Editor 发起后可能跳过记忆刷新或项目上下文处理
```

### F. 精确下一步：Writer H-1

1. 先新增 Writer H-1 成员 HTTP/服务回归：Viewer 读取章节状态、大纲状态、SSE 安全进度；Editor 发起/取消/恢复项目运行；非成员统一 403。
2. 将状态与 SSE read-only 路径迁移到 `ProjectAccessService.require_project_read()`；按 `project_id` 查询 TaskRuntime，再由项目成员权限裁决可见性，`owner_user_id` 仅保留审计与执行归属。
3. 改造 `_load_project_schema()`、章节状态序列化与大纲状态序列化，使其接收已验证的项目访问结果或项目实体，清除回包阶段的第二层 Owner 校验。
4. 再迁移章节生成、取消、恢复、版本选择、正文编辑等 write 路径到 `require_project_write()`，并保持 Viewer 403。
5. 最后处理大纲任务恢复、SSE 终态围栏、后台定稿和 TaskRuntime 关联查询，验证 Editor 发起的后台流程不被 `NovelProject.user_id` 过滤截断。
6. Writer H-1 收口后执行真实多用户 HTTP/SSE 验收，再重跑当前分支完整后端、前端 type-check、Vitest、build-only 与启动冒烟，回写新的权威实测数字。


### G. write_executor 成果归档与接续游标

`write_executor.py` 的 UI-004 P0 成员读写闭环状态为已完成；本批交付的边界与回归证据固定如下：

```text
项目成员读取：Owner / Editor / Viewer 读取项目 Artifact、instruction、质量 Gate 与版本差异
项目成员写入：Owner / Editor 创建候选、执行候选写入、接受候选 Artifact
只读边界：Viewer 不可创建、接受或改变正式版本
隔离边界：非成员 403；projectless 保持创建者私有；worker claim / lease / 终态控制保持 execution_owner_id 归属
验证基线：专项 5 passed；既有/相邻回归 15 + 63 passed
```

接续游标已前移至 `Writer H-1`：先建立成员读取状态、SSE 和 TaskRuntime 的回归矩阵，再逐层清除状态序列化、运行恢复、项目 schema 回包和后台定稿中的 Owner-only 二次过滤。


## 2026-09-04 接续回写：UI-004 Writer H-1 成员读取与运行态绑定闭环

### A. 已完成：Writer H-1 项目成员 read 路径

本批完成 Writer H-1 的项目成员读取闭环，以下 read-only 路径已按 `ProjectAccessService.require_project_read()` 进行项目成员可见性裁决：

```text
章节生成状态：get_chapter_generation_status()
大纲生成状态：get_chapters_outline_generation_status()
章节大纲改写状态：get_chapter_outline_rewrite_status()
章节进度 SSE：stream_chapter_progress()
```

Owner / Editor / Viewer / Admin 可读取同项目的安全运行状态与进度；非成员按项目访问合同返回 403。Viewer 获得的是状态、进度和安全事件投影，不获得章节生成、取消、恢复、版本选择或 worker 控制能力。

### B. TaskRuntime 项目 + 章节绑定

章节运行态查询不再仅把 `TaskRuntime.owner_user_id` 当作项目资源读取边界。H-1 已将运行态定位收敛到项目与章节绑定：

```text
project_id + chapter_number：定位章节运行任务
项目成员 read 权限：裁决 Owner / Editor / Viewer 的运行态可见性
owner_user_id：保留为发起者/审计/执行归属字段
lease / worker ownership：保持原有执行协调语义
```

因此，Owner 发起的章节运行和大纲运行可被同项目 Editor、Viewer 读取状态与 SSE 进度，同时未改变任务创建者、lease、终态围栏或 worker 处理权。

### C. 边界保持

本批只迁移 Writer 的成员读取路径：

```text
读操作：项目成员 read 权限；Owner / lease 归属不变
写入路由：继续 creator-scoped，尚未扩大到项目成员协作写入
worker claim / cancel ownership / terminal transition：保持既有执行控制边界
```

这确保 H-1 不会通过放宽运行控制来实现状态可见性；Writer 写入协作将在 H-2 按独立的成员 write 矩阵和运行归属规则处理。

### D. 实际验证

```text
Writer H-1 成员读取专项：12 passed
Writer H-1 合并验证：34 passed（28 + 6）
```

覆盖章节状态、大纲状态、rewrite-outline 状态、章节 SSE、Owner/Editor/Viewer 读取、非成员 403、TaskRuntime 项目+章节定位、重启恢复相邻合同与既有 Owner/lease 执行边界。

### E. 已完成：H-1 SSE durable replay route-integration 覆盖

新增路由集成回归：

```text
backend/app/api/routers/test_writer_member_stream_access.py
```

覆盖 Writer H-1 的持久运行事件回放合同：

```text
Viewer / Editor：读取 Owner 创建的 TaskRuntime 章节 SSE 事件回放
after_event_id：按事件游标仅补发后续事件
Last-Event-ID：HTTP SSE 重连游标与 after_event_id 合同一致
非成员：读取章节流统一 403
跨项目隔离：不返回其他项目 TaskRuntime 事件
跨章节隔离：不返回同项目其他章节的 TaskRuntime 事件
```

专项实测：

```text
Writer H-1 SSE durable replay route-integration：6 passed
Writer H-1 合并验证：34 passed（28 + 6）
```

该批仅补齐成员读取与 durable replay 的路由合同；Owner/lease、worker claim、事件写入者和终态控制继续维持既有执行归属。

### F. 下一 P0

1. 真实 HTTP 多用户 SSE 验收：使用 Owner、Editor、Viewer 与非成员会话验证连接、断线重连、after_event_id / Last-Event-ID 补发、终态围栏、跨项目/跨章节隔离及 403 合同。
2. Writer H-2 写路径：在独立成员 write 矩阵下迁移章节生成、取消、恢复、版本选择、正文编辑与大纲写入；Viewer 持续 403。
3. H-2 处理 `_load_project_schema()`、章节/大纲回包序列化与后台定稿，消除 Editor 在通过入口校验后遭遇 Owner-only 二次过滤的路径。
4. H-2 收口后，执行真实多用户 Writer HTTP/SSE 验收，并回写完整后端、前端与启动冒烟的新基线。


## 2026-09-04 接续回写：UI-004 Writer H-2 首批成员写路径闭环

### A. 提交与完成范围

当前完成提交：

```text
dbef259
```

Writer H-2 首批已将项目成员写权限接入项目 schema 回包与以下章节操作。通过写权限后，回包不再因遗留 Owner-only schema 加载而把 Editor 截断：

```text
项目成员 schema 可读回包
章节版本选择
正文编辑
快速正文编辑
章节大纲更新
章节删除
候选版本删除
```

### B. 成员写入矩阵

```text
Owner / Editor / Admin：可执行版本选择、正文编辑、快速编辑、章节大纲更新、章节删除、候选版本删除，并取得项目 schema 可读回包
Viewer：上述写路径统一 403
非成员：项目 schema、章节资源与上述写路径统一 403
```

读模型继续使用项目成员权限，写入模型仅赋予 Owner / Editor / Admin 项目 write 权限；本批未将 Viewer 提升为可写成员。

### C. TaskRuntime 与协作 actor 边界

H-2 首批不改写既有运行控制归属：

```text
协作 actor：用于 ProjectAccessService 的项目 write 权限裁决
TaskRuntime owner_user_id：保留任务发起者、审计与运行归属
lease / worker ownership：保持既有控制边界
终态、claim、恢复协调：不因协作成员执行章节写操作而迁移给该 actor
```

因此，Editor 可对项目章节资源完成已纳入本批的协作写入，但不会重写 Owner 创建任务的 owner、lease 或 worker 执行控制。

### D. 验证与反向验证

```text
Writer H-2 首批成员写路径专项：15 passed
Writer H-1 / H-2 / 相邻组合回归：41 passed
```

旧 Owner gate 已执行反向验证：临时保留旧 Owner-only 校验时，Editor 章节写操作明确返回：

```text
Editor = 403
```

恢复成员 write 实现后专项与组合回归重新通过。该证据确认 H-2 的 Editor 可写合同来自项目成员权限迁移，而非测试替身或放宽 Viewer / worker 控制边界。

### E. 下一批：H-2 运行控制 actor / execution owner 分离

下一批按以下范围继续，保持“项目写权限”与“运行控制归属”分层：

1. 章节生成：Editor 可发起项目生成，但创建者、TaskRuntime owner、worker lease 与 execution owner 的字段语义显式分离。
2. 章节取消与恢复：定义协作成员操作项目运行时的 actor、原 execution owner、lease holder 与 terminal fence 合同，避免静默接管或错误拒绝。
3. finalize：清理项目 schema、记忆刷新和后台定稿中的遗留 `NovelProject.user_id` 二次过滤，使 Editor 发起的闭环不在后台阶段截断。
4. outline start / cancel：将大纲运行启动与取消迁移到同一 actor/execution owner 模型，Viewer 持续 403，非成员持续 403。
5. 上述写路径收口后，补真实多用户 HTTP/SSE 验收与完整质量门禁回写。


## 2026-09-04 接续回写：UI-004 Writer H-2 运行控制与协作恢复闭环

### A. 新 generation 的 execution owner 合同

本批将 Writer 新建章节生成的项目 write 权限与 TaskRuntime 执行归属显式分层：

```text
generate / advanced generate：必须通过项目 write gate
可发起身份：Owner / Editor / Admin
new generation TaskRuntime execution owner：实际发起生成的 Owner / Editor / Admin
Viewer / 非成员：403
```

因此，Editor 或 Admin 发起的新章节生成会以该发起者作为 TaskRuntime 的 execution owner；项目协作权限不再依赖项目创建者身份，且运行审计、worker 调度和后续恢复具有明确的创建者归属。

### B. 既有 Run 的取消与恢复

Owner、Editor、Admin 均可对同项目既有章节 Run 发起取消或恢复请求；协作 actor 的权限仅用于项目 write 裁决，不重写原 Run 的执行控制身份：

```text
Editor 取消 / 恢复 Owner 既有 Run：允许
TaskRuntime cancel / retry：继续使用原 execution owner
worker 调度：继续使用原 execution owner
lease / owner_user_id：不因协作 actor 的取消或恢复改变
Viewer / 非成员：403
```

该合同既允许项目成员协作处理卡住或需要恢复的生成，又避免取消、重试、worker 调度和终态事件被操作成员静默接管。

### C. 已迁移 Writer 路径

```text
POST generate
POST advanced generate
POST cancel chapter generation
POST resume chapter generation
```

所有上述入口使用项目 write gate。对于既有运行，读写请求先按项目成员身份授权，再在 TaskRuntime 层保留原 execution owner 的调度和 lease 语义。

### D. 专项与组合回归

新增专项：

```text
backend/app/api/routers/test_writer_member_generation_control_access.py
```

验证：

```text
Writer H-2 generation-control 成员专项：11 passed
Writer route regressions + stream + H-1 / H-2 合并回归：87 passed
```

专项覆盖 Owner / Editor / Admin 发起新 generation、Viewer/非成员 403、Editor 取消/恢复 Owner 既有 Run、原 execution owner 保持、lease 不改写及 worker 调度继续使用原运行归属。

### E. H-2 剩余范围与下一步

H-2 尚待处理的写路径：

```text
finalize
outline / rewrite-outline start
outline / rewrite-outline cancel
deprecated outline generation 路径
```

收口顺序：

1. 迁移 finalize，确保 Editor 发起的项目定稿在项目 schema、记忆刷新和后台处理阶段不被遗留 Owner-only 过滤截断。
2. 迁移 outline / rewrite-outline start 与 cancel，建立与章节生成一致的 actor / execution owner / lease 合同。
3. 审计并迁移 deprecated outline generation 路径，防止旧入口绕开项目成员 write gate 或复活 Owner-only 二次过滤。
4. 完成真实多用户 HTTP 验收，覆盖 Owner、Editor、Viewer、Admin、非成员的生成、取消、恢复、状态和 SSE 流合同。
5. H-2 全部收口后回写完整后端、前端、启动冒烟与跨项目隔离的权威实测基线。


## 2026-09-04 接续回写：UI-004 Writer H-2 finalize 成员定稿闭环

### A. finalize 项目写入合同

`finalize` 入口已迁移到项目 write gate：

```text
Owner / Editor / Admin：可对同项目章节执行同步 finalize
Viewer：403
非成员：403
```

当前发起同步 finalize 的成员同时成为本次新 finalize 执行的 `execution owner`；项目成员权限用于入口 write 裁决，新的后台或同步定稿运行归属明确记录为当前 actor，不再依赖项目创建者身份。

### B. 后台与记忆刷新二次过滤清理

finalize 处理链中的项目 schema、后台定稿与记忆刷新已完成 Owner-only 二次过滤审计。角色/记忆层的 project character 查询不再通过 `NovelProject.user_id` 截断，因此 Editor 发起的同项目定稿可以完整命中项目角色与记忆数据，不会在入口校验通过后因旧项目创建者过滤而降级或中断。

```text
project character query：仅按 project 绑定查询
finalize execution owner：当前发起 finalize 的 Owner / Editor / Admin
Viewer / 非成员：持续禁止进入 finalize 写路径
```

### C. 验证

本批已完成 finalize 专项和现有 finalize / regression / generation 组合验证：

```text
57 passed
```

验证覆盖同步 finalize 的 Owner / Editor / Admin 成员写入合同、Viewer/非成员 403、项目角色与记忆查询不受 `NovelProject.user_id` 旧过滤影响，以及 generation 运行控制回归不退化。

### D. 下一步

1. 迁移 `outline / rewrite-outline` 的 start / cancel 运行归属：项目 write actor 仅负责准入；既有 Runtime 的 execution owner、lease、重试、worker 与终态事件继续使用原运行归属；新 Run 使用实际发起成员作为 execution owner。
2. 审计 deprecated outline generation 路径，统一项目 write gate、共享 active-run 去重与 project/task/run 绑定。
3. 执行真实 HTTP 多用户验收，覆盖 Owner、Editor、Viewer、Admin、非成员的 generation、cancel、resume、finalize、outline/rewrite-outline、状态读取与 SSE cursor/replay，并验证跨项目隔离。


## 2026-09-04 接续回写：UI-004 Writer H-2 outline / rewrite-outline 控制闭环

### A. start / cancel 项目写入合同

`outline` 与 `rewrite-outline` 的 start / cancel 入口已统一迁移至项目 write gate：

```text
Owner / Editor / Admin：可启动和取消同项目 outline / rewrite-outline 运行
Viewer：403
非成员：403
```

新启动的 outline 或 rewrite-outline Run 以实际发起成员作为 `execution owner`。项目成员身份仅用于入口 project write 裁决；新运行的 TaskRuntime、worker、计量与审计归属明确记录为当前 actor。

### B. 共享项目 active Run 与既有运行控制

共享项目中的 active outline / rewrite-outline Run 按项目与任务类型去重：

```text
active-run dedup key：project_id + task_type
```

同项目成员重复 start 不会因 actor 身份不同而创建并行重复运行。对于持久化既有 Run，Editor 可以取消 Owner 创建的同项目 Run；取消请求与终态事件继续使用原始运行 owner：

```text
TaskRuntime request_cancel：原 execution owner
terminal event：原 execution owner
lease / lease owner / lease generation：保持不变
```

这使协作成员能够处理 Owner 创建但卡住的 outline 运行，同时不静默篡改原始 TaskRuntime 的执行归属或 lease 控制边界。

### C. 专项与组合验证

新增专项：

```text
backend/app/api/routers/test_writer_member_outline_control_access.py
```

验证结果：

```text
Writer H-2 outline/rewrite-outline 控制专项：14 passed
当前综合组合回归：129 passed（115 + 14）
```

专项覆盖 Owner / Editor / Admin 的 start 权限、新 Run execution owner=actor、按 `project_id + task_type` 的共享去重、Editor 取消 Owner 持久化 Run 时原 owner 的 request_cancel / terminal event 语义与 lease 不变，以及 Viewer / 非成员 403。

### D. 下一步

1. 迁移 deprecated outline generation path，统一 project write gate、TaskRuntime execution owner、共享项目 active-run 去重与项目/任务/run 绑定，清理遗留 Owner-only 二次过滤。
2. 完成真实多用户 HTTP 验收，覆盖 Owner、Editor、Viewer、Admin、非成员的 generation、cancel、resume、finalize、outline/rewrite-outline start/cancel、状态读取、SSE cursor/replay 与跨项目隔离。
3. deprecated path 与真实 HTTP 验收收口后，重新执行完整后端、前端、启动冒烟和跨项目隔离质量门禁，并回写权威实测基线。


## 2026-09-04 接续回写：UI-004 Writer H-2 deprecated outline / rewrite-outline 同步入口迁移

### A. 同步入口项目成员写入合同

deprecated `outline` 与 `rewrite-outline` 同步入口已完成项目成员写权限迁移：

```text
入口权限：project write
可发起身份：Owner / Editor / Admin
Viewer / 非成员：403
```

同步 LLM 调用继续以当前实际发起成员作为本次执行的 `execution owner`，使额度计量、审计和同步写入归属与 actor 一致。

### B. 项目实体恢复与 Owner-only 截断清理

两个同步入口中的项目实体恢复已改为通过 repository 按项目绑定读取，不再以 `NovelProject.user_id` 作为恢复查询条件。Editor 或 Admin 在通过项目 write 后可完整取得同项目实体，旧项目创建者过滤不再在同步生成/改写链路中造成二次截断。

```text
project entity restore：repository project-bound lookup
legacy NovelProject.user_id filter：已移出同步入口恢复路径
sync execution owner：current actor
```

### C. 验证

现有 outline/member 组合验证：

```text
40 passed
```

该组合覆盖 deprecated outline / rewrite-outline 同步入口的 project write 合同、项目实体恢复不受 Owner-only 过滤影响、当前 actor 的同步 execution owner 归属，以及 Viewer / 非成员拒绝路径。

### D. 剩余阶段

Writer H-2 的代码迁移范围已收口；下一阶段仅保留：

1. 真实多用户 HTTP/SSE 验收：覆盖 Owner、Editor、Viewer、Admin、非成员的 Writer 写入、运行控制、状态读取、SSE cursor/replay、断线续传、终态围栏与跨项目隔离。
2. 当前分支完整质量门禁：重新执行后端全量测试、前端 type-check、Vitest、build-only、服务启动/冒烟与跨项目隔离验证，并将权威实测基线回写本接续文档。
