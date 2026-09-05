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


## 2026-09-04 接续回写：当前分支完整质量门禁基线

### A. 完整验证结果

当前分支已完成完整后端、前端与静态差异门禁：

```text
Backend pytest：1586 passed, 6 warnings in 450.90s
Frontend type-check：通过
Frontend Vitest：80 files / 496 tests passed in 113.71s
Frontend build-only：成功，4918 modules，14.83s
git diff --check：通过
```

该基线覆盖当前 Writer H-2、项目成员访问、Agent workspace 与前端构建组合；结果以当前工作树与实际命令输出为准。

### B. 已知非阻断告警

后端测试通过时保留 6 条既有 warnings；前端构建链同时报告 `baseline-browser-mapping` 与 `caniuse-lite` 旧数据提示。它们属于 P2 依赖数据维护告警，不构成当前代码质量门禁失败，也未被通过跳过测试、降低断言或修改验证范围掩盖。

### C. 剩余验收边界

当前剩余工作只包括真实服务层验证：

1. 重启后真实服务 smoke：重新启动 backend / frontend，执行 health、代理链与启动冒烟，确认最新 H-2 代码在真实进程中生效。
2. 真实多用户 HTTP/SSE 验收：以 Owner、Editor、Viewer、Admin、非成员会话覆盖 Writer 写入、运行控制、状态读取、SSE cursor/replay、断线续传、终态围栏与跨项目隔离。

本地模块回归、组合回归和完整质量门禁均不替代上述真实 HTTP/SSE 验收或重启后真实服务 smoke；完成条件必须取得对应真实请求链的独立证据并回写本接续文档。


## 2026-09-04 接续回写：重启后真实服务 smoke 基线

### A. 实际服务与代理链

重启后已对当前分支的真实服务进程完成 smoke：

```text
Backend：http://127.0.0.1:8013
Frontend：http://127.0.0.1:5174
Frontend proxy health：正常
Backend health：正常
```

`verify.ps1 smoke` 已通过；OpenAPI smoke 的实际检查结果为：

```text
259 检查 = 55 通过 / 204 合理跳过 / 0 失败
```

LLM settings smoke 同样通过，确认服务启动、前端代理、OpenAPI 端点枚举与 LLM 配置读取链在重启后的真实进程中正常工作。

### B. 日志日期与接续日期

本次实际 run log 目录为：

```text
logs/run-20260905-044317
```

该目录名反映运行日志生成时间；本权威接续文档的任务接续日期继续保持 **2026-09-04**，不以日志目录日期改写本轮接续记录日期。

### C. 尚未完成的真实验收

当前仍未完成的唯一验收项，是使用真实且彼此不同的 Owner、Editor、Viewer、Admin、非成员会话执行 Writer HTTP/SSE 端到端矩阵。该矩阵必须覆盖项目写入、generation/cancel/resume/finalize、outline/rewrite-outline 控制、状态读取、SSE cursor/replay、断线续传、终态围栏和跨项目隔离，并保留真实请求链证据；现有单用户 smoke、OpenAPI smoke 与本地回归均不替代该验收。


## 2026-09-04 接续回写：真实网络 HTTP/SSE 验收与 Writer H-2 末尾缺口修复

### A. 真实 JWT + 文件 SQLite 多用户验收

本轮已使用真实监听服务、真实 JWT 认证和文件 SQLite fixture 完成独立网络验收：

```text
fixture：live-http-1788555354
认证：POST /api/auth/login → Bearer JWT
存储：文件 SQLite
服务：http://127.0.0.1:8013
会话：Owner / Editor / Viewer / Admin / 非成员，共 5 个独立登录身份
```

验收覆盖的真实请求链包括：

```text
GET /api/projects/{project_id}/members
GET /api/writer/novels/{project_id}/chapters/{chapter_number}/status
GET /api/writer/novels/{project_id}/chapters/outline/status
GET /api/writer/novels/{project_id}/chapters/rewrite-outline/status
GET /api/writer/novels/{project_id}/chapters/{chapter_number}/stream
```

成员读取与管理矩阵在真实 JWT 链路中符合项目访问模型：

```text
Owner：成员管理、项目读取、Writer 状态与 SSE 可用
Editor：项目读取、Writer 状态与 SSE 可用；成员管理不可用
Viewer：项目读取、Writer 状态与 SSE 可用；写入与成员管理不可用
Admin：项目读取、成员管理、Writer 状态与 SSE 可用
非成员：项目成员、状态、outline/rewrite status 与 SSE 均为 403
```

Writer 状态、outline status 和 rewrite-outline status 已分别以 Owner、Editor、Viewer、Admin 验证可读；非成员路径均在资源投影或流创建前被拦截。该结果确认项目成员 read 边界已通过真实 JWT 解析、文件数据库查询、`ProjectAccessService` 与实际网络路由链，而不只依赖内存 SQLite 或依赖覆盖。

### B. 真实章节 SSE cursor / replay 验收

真实 SSE fixture 包含持久化章节 Runtime、`content_delta` 和终态事件。使用真实 `text/event-stream` 请求完成以下验证：

```text
首次请求：after_event_id=0，回放 content_delta 与 task_completed
断线续传：Last-Event-ID / after_event_id 取最大 cursor，仅返回 cursor 之后事件
终态围栏：收到 task_completed 后连接结束
成员读取：Owner / Editor / Viewer / Admin 可回放同项目事件
隔离：非成员、错误 project_id、错误 chapter_number 均不泄漏事件
```

因此 Writer 章节流已在真实网络条件下确认：项目 read gate、项目/章节/Run 精确绑定、durable event replay、cursor 续传与终态闭合同时成立。

### C. 本轮末尾缺口修复

#### 1. 静态 outline status 路由注册顺序

提交：

```text
59032aa
```

已修复静态 outline status 路由与动态 `{chapter_number}/status` 的注册顺序，避免 FastAPI 将 `outline` 或 `rewrite-outline` 误解析为章节编号。真实 HTTP 验收已覆盖：

```text
/chapters/outline/status
/chapters/rewrite-outline/status
```

并确认两条静态路由按预期命中。

#### 2. 后台 generation Pipeline 的 legacy Owner-only 截断

提交：

```text
df55473
```

已移除章节生成后台 Pipeline 在项目实体读取阶段对 legacy `NovelProject.user_id` 的二次 Owner-only 截断。现在的边界明确为：

```text
HTTP 写权限：actor_user_id 的 project write
TaskRuntime / claim / lease / worker / 终态事件：execution_owner_id
Pipeline 项目实体读取：project_id 绑定读取，不以旧项目创建者字段否决协作成员 Run
```

这闭合了 Editor 或 Admin 已通过 Writer 写入口、已创建 Runtime 后，却在 `PipelineOrchestrator.generate_chapter()` 内部被旧 Owner 校验中止的执行链缺口。

专项验证：

```text
Pipeline 相关回归：211 passed
```

该组覆盖项目协作生成进入后台 Pipeline 的路径，避免仅验证路由入队而遗漏 worker 内部项目读取截断。

#### 3. evaluate、async finalize stale selection 与 outline task type

提交：

```text
5e7fdc1
```

本批完成三项 H-2 收口修复：

```text
章节 evaluate：入口改用 project write；Owner / Editor / Admin 可评审，Viewer / 非成员为 403
async finalize stale selection：旧 finalize worker 在写回 selected_version 前先验证当前选择；较新的版本选择不会被旧任务覆盖
outline cancel task type：持久化 Run 恢复和取消同时校验 project_id + run_id + outline task_type；错绑定的非 outline Runtime 返回未找到，且不写入取消事件
```

Writer 成员写入、finalize 与 outline 组合专项结果：

```text
40 passed
```

该组合验证覆盖 Writer 项目 write 矩阵、finalize 选择版本并发不变量，以及 outline/rewrite-outline 运行类型隔离；未通过删除断言、跳过 worker 语义或放宽跨项目绑定获得通过。

### D. 当前验证边界

本节末尾修复后的完整后端、前端与静态差异质量门禁已经按最新工作树重跑完成；最新权威实测基线见本文末尾“最新最终质量门禁回写”。此前“必须重跑”的前置条件已解除，不再以旧基线作为当前分支验证依据。

### E. 后续执行计划

1. 最新工作树的完整后端、前端与静态差异质量门禁已重跑并已回写；后续改动进入前必须重新执行对应完整门禁，再替换权威基线。
2. 重启 backend / frontend 真实服务，复验 health、前端代理、OpenAPI 与当前代码已加载，排除旧进程承载旧路由或旧 worker 的可能。
3. 继续以 `live-http-1788555354` 或等价隔离文件 SQLite fixture 运行真实 HTTP 写执行链：Editor / Admin 的 `generate`、对既有 Run 的 `cancel`、`resume`、状态转移、worker claim、终态事件、SSE cursor 与跨项目隔离；Provider 调用使用确定性测试替身，避免将权限与外部模型稳定性混淆。
4. 继续审查和收口 P1/P2 不变量：
   - `actor_user_id` 与 `execution_owner_id` 在所有后台入口、retry、lease、计量、审计和终态事件中的命名与传递一致性；
   - outline/rewrite-outline 后台 Admin 身份完整恢复，不因重建用户对象遗失 `is_admin`；
   - `edit-fast` 不再经语义含混的 admin-only serializer 返回项目成员数据；
   - legacy outline DB fallback 明确区分 active、terminal 与 idle，不把任意历史记录投影为 active；
   - 所有 Run 恢复、取消、读取和 SSE 均持续保持 `project_id + chapter_id/chapter_number + run_id + task_type` 的精确绑定。

只有完成最新完整质量门禁、真实服务重启验收和真实 generation/cancel/resume 执行链验证后，Writer H-2 才能从“路由与读取/控制链闭合”升级为“当前分支端到端执行基线已确认”。

## 2026-09-04 接续回写：最新最终质量门禁回写

### A. 最新工作树完整质量门禁

在本节所列 Writer H-2 末尾修复、Pipeline 协作生成修复、evaluate/finalize/outline 类型绑定修复全部纳入当前工作树后，已重新执行完整后端、前端与静态差异门禁。权威实测结果如下：

```text
Backend pytest：1592 passed, 6 warnings in 458.76s
Frontend type-check：通过
Frontend Vitest：80 files / 496 tests passed in 84.28s
Frontend build-only：成功，4918 modules in 26.62s
git diff --check：通过
```

本次结果替换此前发生在末尾修复之前的完整质量基线；“完整质量门禁必须重跑”的事项现已完成。

### B. P2 依赖数据告警

后端完整测试仍保留 6 条既有 warnings；前端依赖链的浏览器映射与兼容性数据提示继续保留并列入 P2 依赖数据维护。该告警不改变本轮测试、类型检查、Vitest、构建和静态差异门禁均通过的事实，也没有通过删减测试、放宽断言或缩小验证范围获得通过。

### C. 仍需保持的真实执行验收与不变量

最新完整质量门禁不替代真实进程和真实多用户写执行链验收。后续只保留以下边界：

1. 重启 backend / frontend 真实服务，复验 health、前端代理、OpenAPI、最新路由与 worker 代码已由新进程加载。
2. 在隔离文件 SQLite fixture 的真实 JWT/HTTP 链路中完成 Editor / Admin 的 `generate`、对既有 Run 的 `cancel`、`resume`、worker claim、状态转移、终态事件与 SSE cursor/replay 验证；继续验证 Viewer / 非成员拒绝和跨项目隔离。Provider 调用使用确定性测试替身，避免将执行权限与外部模型稳定性混淆。
3. 持续收口 P1/P2 不变量：
   - `actor_user_id` 与 `execution_owner_id` 在后台入口、retry、lease、计量、审计和终态事件中的命名与传递一致；
   - outline/rewrite-outline 后台 Admin 身份完整恢复，不因重建用户对象遗漏 `is_admin`；
   - `edit-fast` 使用语义明确的项目成员读取序列化路径；
   - legacy outline DB fallback 明确区分 active、terminal 与 idle；
   - 所有 Run 的恢复、取消、读取和 SSE 持续保持 `project_id + chapter_id/chapter_number + run_id + task_type` 精确绑定。

只有在上述真实服务重启与真实 HTTP `generate` / `cancel` / `resume` 执行链验收也形成独立证据后，当前 Writer H-2 才能确认完整端到端执行基线。

## 2026-09-04 当前会话接续复审：历史会话恢复与下一批执行基线

### A. 历史会话定位

已从 Codex 会话记录确认目标历史任务：

```text
标题：全面优化重构玄穹文枢
历史会话 ID：01a02410-94af-7002-9585-3532293aa587
工作区：D:\小说写作\xuanqiong-wenshu
状态：历史会话未加载/卡住
```

当前任务不回到历史会话执行；本文件作为当前任务的唯一接续入口，所有后续代码、测试、审查和计划回写均在当前工作区完成。

### B. 当前工作树与已有证据复核

```text
分支：codex/bohrium-integration-20260831
最近质量提交：af9b5eb docs: refresh final quality gate baseline
已有 Writer 成员专项：78 passed
```

本次重新执行的定向回归集合为：

```text
app/api/routers/test_writer_member_read_access.py
app/api/routers/test_writer_member_stream_access.py
app/api/routers/test_writer_member_write_access.py
app/api/routers/test_writer_member_generation_control_access.py
app/api/routers/test_writer_member_finalize_access.py
app/api/routers/test_writer_member_outline_control_access.py
app/agent/test_write_executor_member_access.py
app/services/test_generation_run_rebind.py
```

实际结果：

```text
78 passed in 39.67s
```

`git diff --check` 当前通过。工作区中仍有导入/风格上传产生的未跟踪 `.bin` 运行工件；这些工件保留原状，不加入提交，不做批量清理。

### C. 本次全面审查的确认项

1. Writer 读写入口已普遍使用 `ProjectAccessService`；生成 Pipeline 已移除后台恢复路径上的旧 Owner-only 项目过滤。
2. H-1 SSE 已覆盖成员读取、持久化终态、`after_event_id`、`Last-Event-ID`、项目/章节/Run/task type 绑定和非成员 403。
3. H-2 已覆盖成员写入、generation cancel/resume、outline/rewrite-outline 控制、finalize 选择版本并发保护以及旧 outline task type 隔离。
4. Agent Artifact、候选接受、成员管理 API/前端面板已有专项回归与组件/API 测试。
5. 当前尚需用真实进程和隔离文件 SQLite 补齐可重复的多用户 HTTP/JWT Writer 执行链；静态检查和本地路由单测不替代该证据。
6. 仍需收口后台身份字段：`actor_user_id` 表示当前 HTTP 操作者，`execution_owner_id` 表示 Run/lease/retry/终态事件原始执行归属；后台重建用户对象必须保留 `is_admin`。
7. `edit-fast` 返回路径仍需使用语义明确的项目成员 serializer；legacy outline DB fallback 仍需明确 active/terminal/idle，避免历史记录被误投影为 active。

### D. 当前执行计划（按优先级）

| 优先级 | 批次 | 交付 | 验证 |
|---|---|---|---|
| P0 | 真实执行链 | 隔离 SQLite + 真实 JWT/HTTP + 确定性 provider 的 Owner/Editor/Viewer/Admin/Outsider 验收脚本与回归 | 登录、成员权限、generate/cancel/resume/finalize、outline、SSE cursor/replay、终态和跨项目隔离 |
| P1 | 后台身份 | 修正 outline/generation worker 的身份重建与 execution owner 传递 | 管理员身份、Owner Run 被成员控制、lease/terminal owner 不漂移 |
| P1 | 状态语义 | 收口 legacy outline fallback 与 active 状态筛选 | active/terminal/idle 反向测试 |
| P2 | 成员 serializer | 使用 `get_chapter_schema_for_member` 等明确命名路径替换 admin-named helper | Editor 可读、Viewer 只读、非成员 403 |
| P2 | 完整门禁 | 所有代码批次合并后重跑后端/前端/构建/重启 smoke | 全量结果写回本文 |

### E. 本批状态

```text
总任务：active
当前批次：复审已完成，P0/P1 子任务并行执行中
已启动子智能体：3 个（HTTP 验收、后台身份、权限全面扫描）
当前接续原则：不创建新 Codex task；子智能体只在当前代码任务的分工范围内工作；任何阻塞由主任务重新分派并继续推进。
```

## 2026-09-04 接续回写：Writer 后台身份一致性专项完成

### A. 已落地改动

本批围绕 Writer 后台恢复与执行身份一致性完成收口，生产代码文件：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\writer.py
```

新增/调整的核心规则：

1. `TaskRuntime.owner_user_id` 在持久化任务存在时作为唯一 `execution_owner_id` 来源；调用层传入的临时用户 ID 仅作为兼容回退。
2. outline / rewrite-outline worker 在跨 `AsyncSession` 恢复时重新加载完整 `UserInDB`，保留：
   - `id`
   - `username`
   - `email`
   - `hashed_password`
   - `is_admin`
   - `is_active`
3. outline recovery 调度、claim、heartbeat、停止检查、终态事件统一使用 `execution_owner_id`。
4. chapter generation worker 的 TaskRuntime lease、Pipeline `user_id`、TaskRuntime 进度/终态事件统一使用持久化 `execution_owner_id`。
5. 项目成员的读取/写入授权与后台任务的执行归属保持分离：
   - `actor_user_id`：当前请求操作者；
   - `execution_owner_id`：Run/lease/retry/终态事件的持久化执行归属。

### B. 新增专项测试

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writer_worker_identity_invariants.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writer_outline_worker_identity.py
```

覆盖：

- 管理员与普通成员的 `UserInDB` 完整身份恢复；
- outline worker 不再信任恢复调用方 ID，而以 TaskRuntime owner 为准；
- chapter worker 的 lease owner、事件 owner 与 Pipeline user_id 不漂移；
- 缺失后台用户时返回明确 404；
- 原始任务执行归属不被协作成员读取身份覆盖。

### C. 定向验证

执行：

```powershell
cd D:\小说写作\xuanqiong-wenshu
.\backend\.venv\Scripts\python.exe -m pytest -q `
  backend/app/api/routers/test_writer_worker_identity_invariants.py `
  backend/app/api/routers/test_writer_outline_worker_identity.py
```

结果：

```text
6 passed in 5.43s
```

同批 Writer 相关回归集合：

```text
24 passed in 12.14s
```

成员写入、生成控制、finalize、outline 控制集合：

```text
51 passed in 21.69s
```

合计本次同步定向验证：

```text
81 passed
```

静态检查：

```text
python -m py_compile backend/app/api/routers/writer.py      → 通过
git diff --check -- backend/app/api/routers/writer.py       → 通过
```

### D. 当前剩余验证

1. 完整后端/前端门禁需在本批 Writer 改动全部稳定后重新执行，不能沿用修改前的历史数字。
2. 需要重启真实 backend/frontend 进程，验证新 worker 代码已加载。
3. 仍需真实隔离 SQLite + JWT/HTTP 链路验证 Editor/Admin 的 generate、cancel、resume、SSE cursor/replay 与跨项目隔离。
4. `legacy outline DB fallback` 的 active/terminal/idle 语义与 `edit-fast` 成员 serializer 仍列为后续 P1/P2 收口项。

### E. 接续计划更新

当前优先级调整为：

```text
P0：真实多用户 HTTP/JWT Writer 执行链与新 worker 重启验收
P1：legacy outline fallback 状态语义收口
P1：真实 generation/cancel/resume/SSE cursor 端到端证据
P2：edit-fast 成员读取 serializer 命名与权限语义清理
P2：全部改动完成后的后端、前端、构建、smoke 全量门禁
```

## 2026-09-04 当前 task 追加验证回写

### Writer 执行身份一致性批次

已完成并保留以下工作树改动：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\writer.py
D:\小说写作\xuanqiong-wenshu\backend\app\services\novel_service.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writer_worker_identity_invariants.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writer_outline_worker_identity.py
```

关键不变量：

- 后台 worker 从持久化用户恢复完整 `UserInDB`，保留 `is_admin`、`is_active`、`username`、`email` 与密码哈希字段。
- outline generation/rewrite recovery 以 `TaskRuntime.owner_user_id` 作为执行归属，不沿用恢复请求方的临时操作者 ID。
- chapter generation 的 claim、lease、终态事件和 Pipeline user context 使用同一持久化 execution owner。
- 项目成员的 HTTP actor 权限与后台 execution owner 分离，协作成员执行链不再被旧 `NovelProject.user_id` 二次截断。

### 最新可复现实测

Writer worker identity 专项：

```text
6 passed in 5.89s
```

全部 `test_writer*.py`：

```text
78 passed in 35.70s
```

项目成员 Writer 专项集合：

```text
69 passed in 24.95s
```

novels.py 成员访问专项：

```text
30 passed in 13.38s
```

静态检查：

```text
git diff --check → 通过
```

### 下一步

1. 保持现有未提交改动和运行工件，不执行批量清理或强制重置。
2. 对 `novels.py`、`optimizer.py`、`writing_skills.py` 继续按成员 read/write 矩阵补齐缺口，并为每个生产修复增加回归测试。
3. 在 Writer 代码稳定后重新执行完整后端、前端、build、smoke 与真实服务重启验收。
4. 继续补 Agent legacy projection、TaskRuntime 通用成员读取与 HTTP accept 路径的缺口。

## 2026-09-04 接续回写：legacy outline fallback 状态语义收口

### A. 已落地改动

生产文件：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\writer.py
```

新增 `_legacy_outline_job_is_active()` 并收紧 `_load_active_outline_job_from_db(project_id)`：

- 仅将 `queued`、`generating`、`running`、`outline_context`、`outline_chapter_skeleton`、`outline_rewrite`、`saving` 视为可恢复中的任务；
- `idle`、`successful`、`succeeded`、`completed`、`failed`、`cancelled` 视为终态/空闲；
- 最新有效 outline 快照为 terminal/idle 时直接结束恢复，不再向后扫描并复活旧 active 快照；
- 状态缺失时仅允许由明确的 active `progress_stage` 推断 active；
- 项目读取边界仍由 `ProjectAccessService.require_project_read()` 负责，历史记录的 `user_id` 只保留审计意义。

### B. 新增专项测试

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writer_legacy_outline_state.py
```

覆盖：

1. 最新 active legacy snapshot 可恢复；
2. 最新 `successful` snapshot 不复活旧 active run；
3. 最新 `idle` snapshot 不投影为 active；
4. 最新 `cancelled` snapshot 保持终态，不返回可恢复任务。

### C. 验证结果

先红灯验证（修复前）：

```text
1 passed, 3 failed
```

失败准确命中旧逻辑把 terminal/idle 记录直接返回的问题。

修复后：

```text
4 passed in 3.88s
```

反向验证：临时移除 active 状态门后：

```text
REVERSE_EXIT=1
1 passed, 3 failed
```

恢复后的再次回归：

```text
4 passed in 3.88s
```

静态验证：

```text
python -m py_compile app/api/routers/writer.py → 通过
git diff --check → 通过
```

### D. 接续状态

```text
Writer 后台身份专项：完成，6 passed
Writer 成员读取/流/写入/控制/终态专项：完成，75 passed
legacy outline fallback：完成，4 passed
当前总任务：active
下一优先：真实重启后的多用户 HTTP/JWT Writer 执行链，随后重跑完整后端/前端质量门禁。
```

## 2026-09-04 接续回写：Writer 隔离 HTTP/JWT 验收完成

### A. 验收工件

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writer_member_http_acceptance.py
```

该测试使用真实 FastAPI 路由、真实 Bearer JWT 登录和隔离 AsyncSession/SQLite fixture，不写入主运行数据库；Writer 的 `AsyncSessionLocal` 在测试边界绑定到隔离会话。

### B. 已验证合同

- Owner / Editor / Viewer / Admin 读取项目成员列表与章节状态；
- Owner 创建的 `TaskRuntime` 通过 `project_id + chapter_id + run_id` 绑定；
- Viewer 与 Editor 读取 Owner 创建的章节状态、大纲状态、rewrite-outline 状态；
- Viewer 通过 chapter stream 接收 durable `content_delta` 与 `task_completed` 事件；
- Editor 使用 `after_event_id` 只接收游标后的终态事件；
- 项目外成员访问项目资源返回 403；
- 其他项目任务不会污染当前项目的 SSE；
- Bearer token 的实际身份优先于客户端传入或伪造的用户上下文。

### C. 实测结果

执行：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q app/api/routers/test_writer_member_http_acceptance.py
```

结果：

```text
2 passed in 12.42s
```

当前本机服务监听状态（仅作环境记录）：

```text
127.0.0.1:8013 → backend
127.0.0.1:5174 → frontend
```

本次测试以隔离 ASGI 栈完成，尚未替代真实重启进程后的外部 HTTP `generate/cancel/resume` worker 执行验收。

### D. 当前计划调整

```text
已完成：Writer 成员读/流/写/控制/终态定向回归
已完成：后台 execution_owner 身份与 lease 不漂移定向回归
已完成：legacy outline active/terminal/idle fallback 语义回归
已完成：隔离真实 JWT/HTTP 状态与 SSE 验收
待完成：真实重启进程下的 generate/cancel/resume worker 链
待完成：完整后端/前端/type-check/build/smoke 全量门禁替换当前基线
```

### Optimizer 成员写权限批次

新增并验证：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_optimizer_member_access.py
```

实现范围：

- `optimizer.optimize` 使用 `ProjectAccessService.require_project_write`，Editor/Owner/Admin 可执行，Viewer/非成员在读取章节前返回 403。
- `optimizer.apply-optimization` 使用项目 write gate，Editor 可对共享项目写入优化版本，Viewer/非成员无法修改。
- apply 响应使用成员可读章节 serializer，避免成功写入后因 legacy Owner-only serializer 产生错误。

专项结果：

```text
4 passed in 5.35s
```

静态检查：

```text
python -m py_compile backend/app/api/routers/optimizer.py → 通过
git diff --check -- optimizer.py / test_optimizer_member_access.py → 通过
```

### Writing Skills 成员写权限批次

新增并验证：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_writing_skills_member_access.py
```

实现范围：

- 项目作用域的 `writing-skills/skills/{skill_id}/execute` 改用 `ProjectAccessService.require_project_write`。
- Editor/Owner/Admin 可执行项目作用域技能。
- Viewer 与非成员在技能服务实例化前返回 403，避免越权访问项目上下文或消耗执行资源。
- 不带 `project_id` 的技能执行保持既有个人作用域语义。

专项结果：

```text
3 passed in 5.15s
```

### 成员访问聚合回归

当前工作树的成员访问与 Writer 执行身份聚合集合已重新运行：

```text
115 passed in 56.49s
```

集合包含：

- novels.py 项目读取、质量趋势、章节详情、导出、概念会话；
- optimizer 项目优化与应用；
- writing-skills 项目技能执行；
- Writer 生成控制、读取、写入、finalize、SSE、HTTP/JWT；
- outline worker 与 chapter worker 执行身份一致性。

`git diff --check` 对本批修改通过；现有运行二进制工件保持未跟踪状态，未执行批量删除或强制重置。


## 2026-09-04 当前会话接续复审：TaskRuntime 成员边界与 Writer 执行身份收口

### A. 本批完成项

1. **Writer outline/worker 执行身份**

   - outline/rewrite-outline worker 从持久化 `TaskRuntime.owner_user_id` 解析不可变 execution owner；
   - 后台用户跨 session 重建使用 `_load_worker_user()`，保留真实 `username`、`email`、`hashed_password`、`is_admin`、`is_active`；
   - Admin 创建的 outline Run 不再因 worker 重建成普通用户而被旧权限门截断；
   - outline recovery 可复用请求 session，隔离数据库与真实进程均保持同一 Runtime 查询边界。

2. **通用 TaskRuntime 项目成员闭环**

   文件：

   ```text
   backend/app/api/routers/task_runtime.py
   backend/app/api/routers/test_task_runtime_member_access.py
   ```

   当前语义：

   ```text
   项目任务创建：ProjectAccessService.require_project_write(actor)
   项目任务详情/列表/事件/SSE：ProjectAccessService.require_project_read(actor)
   项目任务取消/重试：项目 write + 原 TaskRuntime.owner_user_id 执行
   claim/ recover/ heartbeat/ progress/ metrics/ append-event：继续原始 owner/lease 围栏
   projectless 任务：继续创建者私有，越权读取隐藏为 404
   ```

   新增回归覆盖：

   ```text
   Editor 创建共享项目 Runtime；Viewer/Admin/Editor 读取 Owner Runtime；非成员 403；
   projectless Runtime 越权读取 404；项目事件列表可读；Editor 取消 Owner Runtime；
   owner_user_id、lease_owner、lease_generation 保持不变；项目 Runtime SSE 回放终态事件。
   ```

3. **项目发现与 novels 读取边界**

   - `NovelRepository.list_by_user()` 已改为 owner 或 active `ProjectMember` 可发现；
   - `novels.py` 的 quality trend、章节详情、TXT/DOCX 导出与预检改为项目 read；
   - concept 对话、蓝图生成、蓝图保存与 patch 使用项目 write；
   - `NovelService.get_chapter_schema_for_member()` 提供语义明确的成员读取序列化入口。

### B. 本批验证证据

```text
outline/worker/restart 定向回归：30 passed
TaskRuntime 成员路由/服务回归：7 passed
novels + TaskRuntime P1 定向回归：35 passed
Writer HTTP/JWT/SSE 验收：2 passed
前端成员定向测试：24 passed
隔离文件 SQLite 真实 HTTP 验收脚本：SMOKE_PASSED，31 checks

正确工作目录 backend 的一次完整后端门禁：1655 passed，2 个旧 Agent 质量工具测试与并行测试断言更新重叠；
两项失败随后按当前工作树单独复跑：2 passed。

git diff --check：通过（当前已修改文件）
```

### C. 当前剩余边界

1. `task_runtime.py` 的项目成员读取与 cancel/retry 已有路由回归，但真实 HTTP/JWT 的通用 TaskRuntime 路由矩阵仍需在隔离文件库脚本中补齐；
2. `optimizer.py` 的 optimize/apply、`writing_skills.py` 的 execute_skill 仍需按 read/write 产品语义补齐成员矩阵；
3. Agent 旧 projection、provider usage、approval、Artifact accept、通用任务 worker 控制仍需继续检查是否误用创建者过滤；
4. 最新工作树改动完成后，必须重新执行 backend 全量、frontend type-check/Vitest/build、服务重启 smoke 和真实多用户执行链，替换旧质量基线。

### D. 下一批执行顺序

| 优先级 | 批次 | 当前动作 | 证据 |
|---|---|---|---|
| P0 | optimizer | 分离项目 read 与 apply write，补 Editor/Viewer/Admin/非成员回归 | 无 LLM 单测 + HTTP |
| P0 | writing skills | 区分只读技能与写技能，收口成员权限与后台身份 | 无 LLM 单测 |
| P1 | TaskRuntime HTTP | 在隔离文件 SQLite + JWT 中覆盖项目任务读/列/事件/SSE/cancel/retry | 真实请求链 |
| P1 | Agent 旧投影 | 统一 readable Run、provider usage、approval、Artifact accept 边界 | 定向回归 + 反向验证 |
| P2 | 完整门禁 | 重跑后端、前端、构建、重启 smoke 与 acceptance 脚本 | 新最终基线 |

总任务继续保持 `active`；当前工作在本 task 和当前工作树中推进，不返回历史卡住会话，不创建新的 Codex task。

## 2026-09-04 当前会话接续回写：权限残留第二批收口与真实验收基线

### A. 本批新增修复

本批在当前任务工作区完成，不回到历史会话执行，也未创建新的 Codex task。已完成：

- `novels.py`：质量趋势、章节详情、TXT/DOCX 导出与预检、概念会话、蓝图启动/状态/取消/保存/局部更新统一接入项目成员 read/write 策略。
- `novel_service.py`：`get_section_data()`、`get_chapter_schema()` 使用成员读权限；新增 `get_chapter_schema_for_member()`，替代协作写入路径上的 admin-named serializer。
- `writer.py`：后台 generation/outline/rewrite worker 统一区分 actor 与 execution owner；从用户表完整恢复 `is_admin`、`is_active` 等字段；`edit-fast` 使用成员 serializer。
- `task_runtime.py`：创建任务区分 `actor_user_id` 与 `execution_owner_id`，项目任务先过成员写权限；兼容旧 `owner_user_id`。
- `task_runtime` 路由：项目任务列表、详情、事件、SSE 和控制操作按成员项目范围处理；Viewer 只读；projectless task 保留创建者边界。
- `novel_repository.py`：项目列表包含 owner 或 active member，排除已删除成员和非成员。
- Agent 工具：Provider usage、quality retest、rewrite instructions、quality inspect、entity inspect、finding inspect 接入项目读策略并移除错误的创建者截断。
- `optimizer.py`、`writing_skills.py`：项目上下文操作接入成员策略。

### B. 新增/更新验证工件

- `backend/scripts/run_writer_member_acceptance.py`：每次创建独立 SQLite，执行真实 FastAPI ASGI、真实 JWT 登录和确定性本地桩，覆盖 31 项 Writer 成员执行链检查。
- `backend/app/api/routers/test_writer_member_http_acceptance.py`：隔离 JWT/HTTP/SSE 回归。
- `backend/app/api/routers/test_novels_member_access.py`、`test_novels_blueprint_member_access.py`：小说路由与蓝图成员矩阵。
- `backend/app/api/routers/test_task_runtime_member_routes.py`、`backend/app/services/test_task_runtime_member_access.py`：通用任务运行时成员读写、SSE、执行归属和项目发现。
- `backend/app/agent/test_member_tool_access_sweep.py`：Agent 工具共享项目读取和非成员隔离。
- `docs/reports/collaborative-access-sweep-20260905.md`：全仓残余旧 Owner gate 扫描与缺口清单。

### C. 本批实际验证

定向组合：

```text
129 passed in 57.06s
```

其中包含 Writer worker identity、小说路由、Agent 工具、TaskRuntime 成员访问、隔离 JWT/HTTP 回归和既有相关工具测试。

真实隔离验收：

```text
SMOKE_PASSED {"checks": 31, "dispatch_kinds": ["generate", "generate", "finalize", "outline"], "finalize_status": 200, "generate_status": 200, "outline_status": 200, "resume_status": 200}
```

该脚本结束后自动删除临时数据库，主运行数据库未写入。专项 Agent 旧断言已同步到 HTTP 403 契约，`app/agent/test_tool_adapters.py` 当前 26 passed。Python 编译检查已通过。

### D. 当前审计结论与剩余优先级

确定性旧 Owner gate 已显著收口。审计仍提示以下后续面：

1. `agent.py` 中部分历史事件、context snapshot、plan revision、conversation summary、approval、step、artifact 路径需逐一核对成员读语义与创建者边界，不能仅凭名称批量迁移。
2. `task_runtime` 通用路由与 Worker 的项目任务控制已完成首批成员化，但需在完整门禁后进行真实重启进程 TCP 验收。
3. 前端成员面板已有组件/API 测试；仍需补正确 Vitest 参数下的成员 403/404、restore/remove 即时失效和多角色浏览器级证据。
4. `NovelService.ensure_project_owner()` 保留给真实 owner-only 业务与兼容测试；后续继续清点调用点，避免新成员业务误用。
5. 代码批次合并后必须重跑完整后端、前端 type-check/Vitest/build-only、重启 smoke，并更新本文件权威基线。

### E. 当前任务状态

```text
总任务：active
本批状态：成员权限残留第二批已实现，定向测试与隔离 HTTP smoke 通过
下一批：完整后端/前端质量门禁 + 重启后 TCP HTTP/SSE + Agent 历史投影逐项审查
运行工件：未跟踪二进制保留原状，不提交、不批量清理
```

### Agent legacy projection 成员读取批次

新增可读投影接口与专项测试：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_runtime.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_legacy_projection_member_access.py
```

实现范围：

- 项目成员可读取 Owner 创建 Run 的事件、步骤、审批和 Artifact 列表。
- 读取路径统一先经过 `get_readable_run` / `get_session_readable`，再按 Run 绑定读取完整共享记录。
- 非成员在投影查询前返回 403。
- projectless Run 保持创建者私有；非创建者按历史隐藏语义返回 404。
- 保留原有 Owner-only 写入、审批决定、执行和 Artifact 创建方法，不扩大成员写权限。

专项结果：

```text
9 passed in 6.98s
```

Agent/TaskRuntime 成员相关组合结果：

```text
40 passed in 16.71s
```

### 当前成员访问聚合门禁

本批受影响的 Agent、TaskRuntime、novels、optimizer、writing-skills 与 Writer 成员测试全部通过：

```text
159 passed in 66.06s
```

`git diff --check` 通过；未执行强制重置、批量删除或清理现有运行工件。

### 当前待办调整

1. 对真实服务重启后的 Agent/Writer 成员 HTTP 链路执行 health、OpenAPI、JWT 与 SSE 验收。
2. 继续补齐 `novels.py` 蓝图成员矩阵、optimizer/writing-skills HTTP 级验证与跨请求成员移除即时失效测试。
3. 评估 Agent audit、context snapshot、plan revision、conversation summary 和 provider usage 的统一 readable projection，保持写入方法的 owner/actor 边界不变。
4. 所有生产修复稳定后重跑完整后端、前端、构建和 smoke 门禁。

## 2026-09-04 当前会话接续回写：完整质量门禁与重启服务冒烟

### A. 稳定工作树门禁

在协作权限第二批代码收口、TaskRuntime 路由最终恢复语义落定后，重新执行完整后端门禁：

```text
Backend pytest：1694 passed in 727.86s
```

前端门禁：

```text
Frontend type-check：通过
Frontend Vitest：80 files / 496 tests passed in 86.63s
Frontend build-only：成功，4918 modules，15.61s
```

构建仍保留既有 `baseline-browser-mapping` 与 `caniuse-lite` 数据陈旧提示；没有因此跳过测试或缩小验证范围。

### B. 重启后真实服务冒烟

当前本地服务链验证：

```text
Backend：http://127.0.0.1:8013 → health 200
Frontend：http://127.0.0.1:5174 → 首页可达
Frontend proxy：http://127.0.0.1:5174/api/health → 可达
OpenAPI：259 检查 = 55 通过 / 204 合理跳过 / 0 失败
LLM settings smoke：通过
```

`verify.ps1 smoke` 已完成，未发现 500 级错误。资源 ID 依赖端点按既有 smoke 规则合理跳过，真实 JWT/HTTP Writer 资源链由隔离验收脚本单独覆盖。

### C. 真实隔离 Writer 执行链

```text
SMOKE_PASSED {"checks": 31, "dispatch_kinds": ["generate", "generate", "finalize", "outline"], "finalize_status": 200, "generate_status": 200, "outline_status": 200, "resume_status": 200}
```

脚本使用临时 SQLite，结束后自动清理；主运行数据库未被写入。该验收覆盖五类登录身份、成员读取、Writer 状态、SSE 首次回放/cursor、跨项目隔离、Editor generate/cancel/resume/finalize/outline 控制和 Viewer/非成员拒绝。

### D. 版本记录

```text
d1b29af feat: close collaborative project access gaps
```

本版本包含成员访问第二批修复、后台身份字段收口、TaskRuntime 路由、隔离验收脚本、专项测试和审计报告。未跟踪导入/上传二进制运行工件继续保留原状，不加入 Git。

### E. 当前状态与下一计划

```text
总任务：active
当前批次：权限残留第二批 + 完整后端/前端/构建/smoke 门禁已通过
下一优先：逐项审查 agent.py 历史投影链与前端成员管理浏览器级缺口；确认后再进入性能/分页与发布门禁
```
## 2026-09-04 接续回写：当前工作树完整质量门禁更新

### A. 后端全量回归

在修复 `agent_runtime.py` readable 投影方法结构、对齐 Agent 成员权限旧断言、修复 Writer 后台身份与 legacy outline fallback 后，当前后端全量回归重新执行完成：

```text
Backend pytest：1694 passed in 730.05s
```

相关收口专项：

```text
Agent Runtime / project-member：51 passed
Agent tool adapters：26 passed
Writer 成员读/流/写入/控制/HTTP：71 passed
Writer worker identity：6 passed
legacy outline fallback：4 passed
TaskRuntime member routes：2 passed
TaskRuntime route contract：4 passed
```

### B. 前端全量门禁

```text
npm run type-check：通过
npm run test:run：80 files / 496 tests passed in 85.19s
npm run build-only：成功，4918 modules transformed，16.93s
```

仅保留既有 P2 依赖数据提示：

```text
baseline-browser-mapping data over two months old
caniuse-lite data 11 months old
```

### C. 运行时 smoke

当前运行服务：

```text
backend 127.0.0.1:8013
frontend 127.0.0.1:5174
```

执行：

```powershell
.\verify.ps1 -Suite smoke
```

结果：

```text
后端健康检查：PASS
前端首页：PASS
前端代理健康检查：PASS
OpenAPI 路由检查：259 项，55 通过、204 跳过、0 失败
LLM 设置检查：PASS
验证套件 smoke：PASS
```

本次 smoke 使用当前已运行进程，尚未重新启动进程验证最新代码装载；该项仍保留为下一步运行时验收。

### D. 当前权威状态

```text
后端全量：通过
前端类型/单测/构建：通过
静态 diff：通过
隔离 JWT/HTTP Writer：通过
Smoke：通过
待完成：停止并重启 backend/frontend 后再次 health、OpenAPI、Writer HTTP/SSE 验收
```

## 2026-09-04 最新回归回写：全量门禁复核

### 实测结果

当前 HEAD `d1b29af` 加上工作树已有的 `task_runtime.py` 兼容语义补丁，完整后端回归结果：

```text
1694 passed in 667.39s (0:11:07)
```

前端门禁：

```text
npm run type-check → 通过
npm run test:run → 80 files / 496 tests passed in 93.62s
npm run build-only → 成功，4918 modules transformed，19.10s
```

后端关键模块 `py_compile` 与 `git diff --check` 均通过。

成员聚合专项此前结果保持：

```text
159 passed in 66.06s
Agent/TaskRuntime 组合：40 passed in 16.71s
```

### 工作树边界

当前未提交业务差异仅为：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\task_runtime.py
```

该差异保留项目任务无关系用户的历史 404 资源隐藏语义，同时让可见只读成员继续得到明确写权限拒绝；完整 1694 项回归已在该状态下通过。未跟踪的导入/上传二进制运行工件继续保留，未执行批量清理。

### 下一执行队列

1. 先审查 `agent.py` 剩余历史投影链：audit、context snapshot、plan revision、conversation summary、provider usage。
2. 补真实 JWT/HTTP 的 Agent 只读矩阵与跨项目隔离；保持 projectless 资源创建者私有。
3. 对 `task_runtime.py` 现有未提交补丁建立独立提交边界与回滚说明，不混入后续无关修改。
4. 完成上述链路后，再做分页性能、移动端长历史和发布前 smoke 复核。

## 2026-09-04 接续回写：重启进程运行时验收完成

### A. 正式重启

执行：

```powershell
.\start.ps1
```

启动脚本完成旧仓库进程清理、SQLite 模式识别、backend/frontend 重启与等待检查：

```text
backend 127.0.0.1:8013 → READY
frontend 127.0.0.1:5174 → READY
frontend proxy /api/health → READY
```

### B. 重启后 smoke

执行：

```powershell
.\verify.ps1 -Suite smoke
```

结果：

```text
后端健康检查：PASS
前端首页：PASS
前端代理健康检查：PASS
OpenAPI 路由检查：259 项，55 通过、204 跳过、0 失败
LLM 设置检查：PASS
验证套件 smoke：PASS
```

### C. 重启后隔离 HTTP/JWT 回归

执行：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q `
  app/api/routers/test_writer_member_http_acceptance.py `
  app/api/routers/test_task_runtime_member_routes.py
```

结果：

```text
4 passed in 16.14s
```

该集合再次确认：

- Owner / Editor / Viewer / Admin 项目读取权限；
- Owner 创建的 Writer Runtime 状态与 SSE；
- `project_id + chapter_id + run_id` 绑定；
- after-event cursor 回放；
- 非成员 403；
- TaskRuntime 成员列表、详情、事件、stream、创建与控制；
- projectless 任务创建者隔离；
- Bearer 身份与项目成员策略一致。

### D. 当前最新质量基线

```text
Backend pytest：1694 passed
Frontend type-check：通过
Frontend Vitest：80 files / 496 tests passed
Frontend build-only：4918 modules transformed，成功
Smoke：5/5 阶段通过
重启后 HTTP/JWT Writer + TaskRuntime：4 passed
Writer/Agent 定向回归：全部通过
```

仍保留的非阻断项：

```text
baseline-browser-mapping / caniuse-lite 数据陈旧告警
```

### E. 剩余工作

1. 当前分支仍需持续保留未提交业务修改与审计工件；不执行批量清理或历史重写。
2. 真实 Provider 参与的长耗时 `generate/cancel/resume` 外部 HTTP 链仍需确定性 Provider 环境下单独验收；当前隔离 HTTP 测试已覆盖路由、JWT、成员、状态、SSE 与控制合同。
3. UI-005 工具注册/策略统一和 UI-006 长历史虚拟化仍为后续功能批次。
4. 完成所有后续批次后再次替换本文全量质量基线。

当前总任务保持：

```text
active
```

## 2026-09-04 Agent 历史投影第三批回写

### A. 生产收口

已将 Agent 只读历史投影与项目成员权限对齐：

```text
backend/app/api/routers/agent.py
backend/app/services/agent_runtime.py
backend/app/services/agent_plan_service.py
```

当前已覆盖：

- Run 事件、Activity、步骤、审批、Artifact 列表使用 readable Run；
- Run commands 使用 readable Run 投影；
- Plan、Provider provenance、Context snapshot、Plan revision、Conversation summaries 先验证 readable Run，再按 Run 原始 owner 读取不可变事实；
- projectless Run/Session 仍保持创建者私有，其他用户返回 404 隐藏语义；
- 原有写入、审批决定、执行、claim、lease 和 Artifact 创建仍保留 owner/actor 写边界。

### B. 回归证据

Agent 历史投影与既有上下文/会话测试：

```text
53 passed in 32.01s
```

成员聚合门禁此前结果：

```text
159 passed in 66.06s
```

后端完整门禁基线：

```text
1694 passed in 667.39s (0:11:07)
```

前端完整门禁基线：

```text
80 files / 496 tests passed
npm run type-check → 通过
npm run build-only → 成功，4918 modules transformed
```

### C. 工作树与下一步

本批 Agent 投影和前端成员面板测试当前仍处于工作树未提交状态；不覆盖既有改动，不清理运行二进制工件。下一步：

1. 重新运行受影响 Agent/前端定向门禁，确认并发自动化写入后状态稳定；
2. 运行真实 JWT/HTTP Agent readable projection 验收；
3. 继续审查 audit/provider usage/context/plan/conversation 的跨项目过滤和分页边界；
4. 稳定后再替换完整后端、前端、构建与 smoke 权威基线。

### 最后一次增量复核

Agent 历史投影与上下文/会话服务：

```text
53 passed in 32.01s
```

前端成员面板与 Agent Workspace 增量回归：

```text
2 files / 36 tests passed in 6.96s
```

真实服务 smoke：

```text
后端 health 200；前端首页 200；前端 proxy health 200；OpenAPI 259 项检查 0 失败；LLM settings smoke 通过。
```

完整后端基线仍为：

```text
1694 passed in 667.39s (0:11:07)
```


## 2026-09-04 接续回写：Agent readable 历史投影与前端成员矩阵收口

### A. 本批实现

- `agent.py` 的 plan、Provider provenance、ContextSnapshot、PlanRevision、ConversationSummary 与 Run commands 读取先通过 `get_readable_run()`；
- 读取事实继续按 Run 原始 `user_id`、`session_id` 与 `run_id` 查询，成员身份只参与项目可见性裁决，不写入创建者归属；
- `AgentRuntimeService.list_run_commands_readable()` 与 `AgentPlanService.get_latest_revision_for_run_readable()` 提供明确的 readable 查询入口；
- 项目成员仍可读 Owner Run 的公开计划、快照、修订、摘要、命令历史；projectless Run 仍只允许创建者读取；
- 前端 `ProjectMemberPanel` 与 `AgentWorkspace` 测试补齐 owner/editor/admin/viewer 的 `can_manage` 矩阵、403/404/通用错误态、刷新恢复、新增/改角色/移除流程。

### B. 验证

```text
Agent readable projection + TaskRuntime member route：32 passed
Agent legacy / execution facts / runtime 相邻回归：59 passed
前端 type-check：通过
前端 Vitest：80 files / 496 tests passed
前端 build-only：4918 modules transformed，成功
git diff --check：通过
```

### C. 当前边界

- 本批 Agent 读取链不扩大审批决定、执行批准、Run pause/resume/cancel 或 worker lease 的成员写权限；
- 真实隔离 HTTP/JWT Writer/TaskRuntime 脚本仍为 31 checks 通过；Agent 历史投影已有内存数据库合同，真实 TCP HTTP 只读矩阵列入下一验收；
- 修改后的 Agent 读取代码需要在当前提交上重新跑 backend 全量，替换先前 `1694 passed` 基线；
- 未跟踪 `.bin` 运行工件继续保留，不加入提交，不做批量删除。

### D. 下一执行队列

1. 在本批提交上重跑 backend 全量门禁，确认 Agent readable 查询没有破坏旧 owner-only 写/控制合同；
2. 重启 backend/frontend，执行 health、OpenAPI、smoke，并运行隔离 JWT Agent/Writer/TaskRuntime 只读与 SSE 验收；
3. 继续清点 Agent command/control、Artifact accept、approval decision 与 task worker 控制的 actor/execution-owner 分离；
4. 进入 UI-005 工具注册策略统一、UI-006 长历史虚拟列表与跨页缓存性能批次。

总任务保持 `active`。

## 2026-09-04 当前会话接续回写：Agent 历史投影与前端成员管理收口

### A. Agent 历史投影

`agent.py` 的项目上下文读取链已逐项接入成员读策略，覆盖：

```text
events / activity / provider provenance / plan / context snapshot /
plan revision / conversation summaries / approvals / steps / artifacts
```

Owner、Editor、Viewer、Admin 均可读取共享项目投影；非成员隔离；projectless 资源仍按创建者边界返回 404。写入、审批、执行和运行控制没有批量放宽。相关服务投影辅助字段已补齐项目成员可读语义。

验证：

```text
Agent 历史投影专项：17 passed in 12.11s
Agent 相关既有组合：86 passed in 43.05s
本地复核：21 passed in 15.58s
```

### B. 前端成员管理

`ProjectMemberPanel` 与 `AgentWorkspace` 现有测试补齐了 Owner/Editor/Viewer/Admin 的 `can_manage`、只读状态、成员新增/角色更新/移除、403/404/通用错误、重试恢复和即时列表更新。

验证：

```text
定向 Vitest：2 files / 36 tests passed
完整 Vitest：80 files / 510 tests passed in 79.20s
```

既有 Pinia 注入提示、浏览器映射数据提示和 caniuse-lite 提示继续记录为非阻断告警。

### C. 服务层调用点审查

`NovelService.ensure_project_owner()` 的生产调用点已分类：当前保留在 `delete_projects()` 的真实 owner-only 删除语义；项目摘要、区段、章节详情、项目列表和成员业务不再依赖隐式 Owner-only 读取。反向验证把成员读取临时替换回旧门后准确失败，随后已恢复并完成字节校验。

### D. 本批门禁状态

```text
完整后端：1694 passed in 727.86s
前端 type-check：通过
前端 Vitest：80 files / 496 tests passed in 86.63s（随后成员管理扩展专项完成 510 tests）
前端 build-only：4918 modules，15.61s，成功
verify.ps1 smoke：259 检查 = 55 通过 / 204 合理跳过 / 0 失败
隔离 Writer HTTP/JWT：31 checks，SMOKE_PASSED
```

由于 Agent 历史投影和前端测试在上述完整门禁之后又新增了代码/测试，本节之后必须再替换一次完整后端与前端权威数字；当前总任务保持 active，不提前宣告最终完成。

### E. 下一执行批次

1. 立即以当前提交后的工作树重跑完整后端、前端 type-check、Vitest、build-only 和 smoke，替换旧基线。
2. 复核 `agent.py` 变更后的真实重启 TCP HTTP/SSE，重点共享项目历史投影和 projectless 隔离。
3. 继续处理报告中剩余“需人工确认”的产品语义，不做无证据的批量权限放宽。
4. 完成后再进入分页/长历史性能、前端浏览器级真实服务验收和发布门禁。
### 2026-09-04 最新最终后端全量基线

Agent 历史投影补丁落盘后，重新执行完整后端门禁：

```text
1706 passed in 587.61s (0:09:47)
```

该数字替换此前 1694 项的旧基线，后续以后续工作树变更为准继续递增验证。

### Agent 成员控制链最终回归

新增专项：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_member_controls.py
```

覆盖：

- Editor/Admin 暂停并恢复 Owner 创建的 Run；
- Viewer/非成员控制 Owner Run 被 403 拒绝；
- 成员提交 Run command 时使用 Owner 作为 execution owner，同时在 payload 保留 actor_user_id；
- Run 状态、Owner ID 与控制命令归属不漂移。

最新结果：

```text
5 passed in 5.25s
```

当前 HEAD 已包含 Agent readable projection 与成员 UI 覆盖提交：

```text
1808ecd test: close agent projections and member UI coverage
```

工作树仅保留 Agent 路由的增量调整、接续文档回写、成员控制专项测试和既有二进制运行工件；不执行批量清理。

### 基线说明修正

`1706 passed in 587.61s` 是 Agent readable projection 增量落盘后的最近一次完整后端基线；其后新增的 Agent 成员控制专项已单独验证：

```text
5 passed in 5.25s
```

因此当前证据采用：

```text
完整后端基线：1706 passed
其后增量专项：Agent 成员控制 5 passed；Agent 历史投影/上下文/会话 53 passed
```

后续若再修改后端生产代码，先重跑受影响专项，再重新替换完整后端基线。


## 2026-09-04 接续回写：Agent Run 控制与候选 Artifact 协作闭环

### A. 控制边界

- 共享项目 Run 的 pause/resume/cancel 与 command 提交先通过项目 write；
- 实际状态变更、取消副作用、命令记录和终态事件继续使用原始 Run `user_id` 作为 execution owner；
- command payload 自动记录 `actor_user_id`，不修改 Run/Command 的原始归属；
- 共享项目 `chapter_candidate` Artifact 的 accept 先通过项目 write，随后以 Artifact/Run 原始 owner 完成 approval、执行与版本落库；
- Viewer 和非成员继续拒绝；projectless Run/Artifact 继续创建者私有；
- `claim/release/recover` 保留后台 lease/恢复器的 owner-scoped 语义，不把成员读取或项目写权限直接升级成 worker 租约控制。

### B. 验证

```text
Agent Run controls + Artifact accept：9 passed
Agent readable projection + TaskRuntime member routes：26 passed
backend 全量（控制补丁前最近稳定提交）：1706 passed，6 warnings
前端 type-check：通过
前端 Vitest：80 files / 510 tests passed
前端 build-only：4918 modules transformed，成功
git diff --check：通过
```

### C. 下一步

1. 提交当前 Agent 控制补丁后重新执行 backend 全量，替换 1706 项基线；
2. 重启 backend/frontend，执行 smoke、OpenAPI、隔离 JWT Writer/TaskRuntime 验收；
3. 补真实 JWT Agent 只读与控制矩阵，重点 command history、plan/context/summaries、Artifact accept；
4. 之后进入 UI-005 工具注册策略统一和 UI-006 长历史性能批次。

总任务保持 `active`。

### Agent readable projection 真实 JWT/HTTP 验收

新增测试：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_readable_projection_http.py
```

覆盖真实 FastAPI ASGITransport、真实 `/api/auth/login` JWT 与隔离 SQLite：

- Owner/Editor/Viewer/Admin 读取 Owner Run 的 Plan、Provider provenance、Context snapshot、Plan revision、Conversation summaries；
- 成员读取 commands、approvals、steps、Artifacts；
- 非成员访问上述历史投影全部返回 403；
- projectless Run 的历史仍保持创建者私有，其他用户返回 404；
- 读取返回保留原始 Owner attribution，不把 Viewer/Editor 身份写回历史事实。

专项结果：

```text
14 passed in 66.05s
```


## 2026-09-04 接续回写：重启服务与 Agent 真实 HTTP 验收

### A. 重启与 smoke

已执行项目启动脚本完成 backend/frontend 重启：

```text
backend 127.0.0.1:8013 READY
frontend 127.0.0.1:5174 READY
frontend proxy /api/health 200
```

随后执行 `verify.ps1 -Suite smoke`：

```text
后端健康检查：PASS
前端首页：PASS
前端代理健康检查：PASS
OpenAPI：259 检查 = 55 通过 / 204 合理跳过 / 0 失败
LLM settings smoke：PASS
```

隔离 Writer HTTP/JWT 验收再次通过：

```text
SMOKE_PASSED
checks=31
generate_status=200
finalize_status=200
outline_status=200
resume_status=200
```

### B. Agent 真实 HTTP/JWT 回归

当前 Agent 路由真实 ASGI/JWT 专项已通过：

```text
readable projection / P1 facts：19 passed
quality lineage / stream / approval：15 passed
member controls / Artifact accept / legacy projection：28 passed
合计：62 passed
```

覆盖共享项目成员读取、plan/provider/context/summary/commands、事件与 SSE、Editor/Admin Run 控制、候选 Artifact 接受、Viewer/非成员拒绝、projectless 404 隔离和跨项目绑定。

### C. UI-006 初审

当前 Agent Workspace 已具备：

```text
运行日志最多渲染 120 条，独立滚动和尾部跟随；
Provider reasoning 首页 100 条游标分页，可加载更早内容；
事件 reducer 有数量上限，避免活动流无限增长；
成员面板与长历史相关前端测试已纳入完整 Vitest。
```

真正需要继续优化的方向是大型 artifact/steps/commands 详情的分页接口与虚拟列表，而不是重复增加日志上限。

### D. 当前验证状态

```text
最近稳定 backend 全量：1706 passed，6 warnings（Agent 控制补丁专项之后需再替换）
前端 type-check：通过
前端 Vitest：80 files / 510 tests passed
前端 build-only：4918 modules transformed，成功
重启 smoke：通过
隔离 Writer：31 checks 通过
真实 Agent HTTP/JWT：62 passed
```

### E. 下一批

1. 在 `a8cc091` 上重跑 backend 全量，替换 1706 项旧基线；
2. 清点 Agent command/control、Artifact accept 的 actor/execution owner 审计字段是否在所有写入事件中完整保留；
3. 为 Artifact/steps/commands 增加按 Run 游标分页或虚拟列表前置设计，保持当前日志/reasoning 已有上限；
4. 完成后再执行一次 frontend 全量、重启 smoke、Writer/Agent 隔离 HTTP 验收。

总任务保持 `active`。

### Agent 全域聚合回归

在 Agent Artifact accept、成员控制、readable projection 真实 HTTP 变更之后，全部 Agent 相关后端测试聚合通过：

```text
493 passed in 430.42s (0:07:10)
```

覆盖目录/文件族：

- `backend/app/agent/test_*.py`
- `backend/app/api/routers/test_agent*.py`
- `backend/app/services/test_agent*.py`

当前 Agent 生产边界：

- 项目成员可读共享 Run 历史与安全投影；
- Editor/Admin 控制共享 Run 时以 Owner execution identity 执行；
- Artifact accept 使用项目 write gate，并保留 Artifact 原始 execution owner；
- Viewer/非成员控制或接受写入被拒绝；
- projectless Run/Session/Artifact 继续创建者私有。

## 2026-09-04 接续回写：Agent 成员控制与 Artifact 接受闭环

### A. Agent Run 控制成员化

生产文件：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py
```

新增统一 `_resolve_writable_run()`：

- 先通过 `AgentRuntimeService.get_readable_run()` 确认 Run 可见；
- 项目 Run 再通过 `ProjectAccessService.require_project_write()` 判定 Editor/Owner/Admin 写权限；
- Viewer 和非成员返回一致的 403；
- Runtime 状态机、lease、事件、计量继续使用持久化 `run.user_id` 作为 `execution_owner_id`；
- 命令 payload 保留 `actor_user_id`，区分当前操作者和执行归属。

覆盖端点：

```text
POST /api/agent/runs/{run_id}/commands
POST /api/agent/runs/{run_id}/pause
POST /api/agent/runs/{run_id}/resume
POST /api/agent/runs/{run_id}/cancel
```

### B. Agent Artifact 接受成员化

同一生产文件新增 `_resolve_writable_artifact()`：

- 项目 Artifact 先执行项目成员写权限；
- projectless Artifact 继续保持创建者私有隔离；
- Editor/Admin 可接受 Owner 创建的候选；
- 审批、质量门、版本写入和终态事件继续使用 Artifact 原始 `user_id`；
- 接受请求的成员身份记录到审批参数 `actor_user_id`。

### C. Agent Runtime 成员可读投影

生产文件：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_runtime.py
```

保留 creator-scoped 的原方法，同时提供独立 readable 投影：

```text
list_steps_readable()
list_approvals_readable()
list_artifacts_readable()
```

三者都先使用 `get_readable_run()`，项目成员可以读取共享 Run 的步骤、审批历史和 Artifact 元数据；lease/claim/执行协调方法没有被扩成成员可接管。

### D. 新增/对齐测试

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_member_controls.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_artifact_member_accept.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_task_runtime_member_routes.py
```

既有旧测试已将非成员项目访问合同统一为：

```text
HTTP 403 + “无权访问该项目”
```

### E. 验证结果

Agent Run 控制定向：

```text
5 passed
```

Artifact 接受定向：

```text
4 passed
```

全部 Agent API 路由：

```text
112 passed in 44.38s
```

TaskRuntime 成员路由：

```text
2 passed in 10.51s
```

Agent Runtime 核心集合：

```text
51 passed in 19.77s
```

后端当前最新全量回归：

```text
1729 passed in 717.96s
```

静态检查：

```text
python -m py_compile agent.py / agent_runtime.py / writer.py / optimizer.py → 通过
git diff --check → 通过
```

反向验证：

```text
Run 控制执行归属临时改为当前成员 → 3 failed，确认 owner 绑定断言有效
Artifact 接受执行归属临时改为当前成员 → 2 failed，确认原始 Artifact owner 绑定断言有效
```

### F. 当前运行时验证状态

之前服务重启后的 smoke 已通过，但本批 `agent.py` 与 `agent_runtime.py` 修改是在该次重启之后落盘；因此必须再次重启服务并重跑 smoke，确认 8013/5174 实际加载当前代码。

### G. 接续计划

```text
P0：重启服务并重跑 smoke + Agent/TaskRuntime HTTP 验收
P1：继续审查 Agent 写审批决策、recover/claim/release 与成员策略边界
P1：真实 Provider 条件下的 generate/cancel/resume 执行链
P2：前端 Agent 长历史分页/虚拟列表性能
P2：最终完整后端/前端/构建/静态基线替换
```


## 2026-09-04 最新最终门禁回写：Agent 控制补丁纳入后的完整验证

### A. 完整 backend 门禁

在 `a8cc091 feat: enable shared agent run controls` 及其测试/文档提交后，于正确目录 `D:\小说写作\xuanqiong-wenshu\backend` 执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
1729 passed in 704.80s (0:11:44)
6 warnings
```

6 条 warning 均为既有 FastAPI 状态码弃用提示，未影响测试结果。

### B. 前端与运行时证据

当前仍有效的完整前端门禁：

```text
npm run type-check：通过
npm run test:run：80 files / 510 tests passed
npm run build-only：4918 modules transformed，成功
```

Agent 控制补丁落盘后已执行真实服务重启：

```text
backend 127.0.0.1:8013 READY
frontend 127.0.0.1:5174 READY
verify.ps1 -Suite smoke：5/5 阶段通过
OpenAPI：259 检查 = 55 通过 / 204 合理跳过 / 0 失败
隔离 Writer HTTP/JWT：SMOKE_PASSED，31 checks
Agent HTTP/JWT 相关专项：62 passed
```

### C. 当前完成范围

```text
项目成员模型与成员管理 API/前端面板
Writer H-1 状态/SSE 与 H-2 写入、生成、取消、恢复、定稿、大纲控制
Agent readable Run 投影、reasoning、activity、plan、context、summary、approval、step、artifact
Agent Editor/Admin Run pause/resume/cancel/command 与候选 Artifact accept
TaskRuntime 项目成员读/列/事件/SSE/cancel/retry 与 actor/execution-owner 分离
optimizer、writing-skills、novels 主要项目访问边界
``

### D. 仍需继续的队列

1. 真实 TCP HTTP 下补 Agent 成员只读/控制矩阵（当前已有 ASGI/JWT 与内存回归，服务重启 smoke 已完成）；
2. 对 Agent command/control、Artifact accept、审批决定的审计字段做跨请求持久化检查；
3. UI-006：Artifact/steps/commands 详情的分页或虚拟列表，保留日志 120 条和 reasoning 100 条窗口；
4. 处理审计报告列出的 `novels` 低优先级导出/蓝图、项目列表、成员移除即时失效和前端浏览器级证据；
5. 所有后续代码批次完成后重新替换 backend/frontend/smoke/HTTP 最终基线。

总任务继续保持 `active`，不返回历史卡住会话。

## 2026-09-04 接续回写：Agent Run 控制与 Artifact 接受审计补强

### A. 生产改动

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\agent.py
```

成员控制与候选接受均完成 actor/execution owner 分离：

- 项目 Run 的 pause/resume/cancel/commands 先验证项目成员写权限；
- Editor/Admin 可以控制 Owner 创建的项目 Run；Viewer/非成员返回 403；
- Runtime 状态机、lease、事件和后台执行仍使用持久化 `run.user_id`；
- 命令 payload 固化 `actor_user_id`；
- Artifact 接受的 `approval_required` 事件同时固化 `actor_user_id` 与 `execution_owner_id`；
- projectless Run/Artifact 仍保持创建者私有隔离。

### B. Agent Runtime readable 投影

```text
D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_runtime.py
```

新增的成员可读投影保持独立：

```text
list_steps_readable()
list_approvals_readable()
list_artifacts_readable()
```

未扩大 Worker claim、lease、approval execution 的 creator-scoped 控制权。

### C. 测试

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_member_controls.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_artifact_member_accept.py
```

覆盖：

- Editor/Admin 控制 Owner Run；
- Viewer/非成员写控制拒绝；
- 命令保留原始 execution owner 与当前 actor；
- Editor/Admin 接受 Owner 候选；
- Artifact 接受事件记录 actor/execution owner；
- Viewer/非成员候选接受拒绝。

### D. 实测结果

关键集合：

```text
Agent controls + Artifact accept + project HTTP：11 passed in 8.57s
全部 Agent API 路由：126 passed in 123.25s
```

反向验证：

```text
Run 控制错误使用当前成员 ID：3 failed
Artifact 接受错误使用当前成员 ID：2 failed
```

两次反向红灯均准确命中持久化 Runtime owner 约束，随后已恢复生产代码并复跑通过。

### E. 当前门禁状态

```text
此前后端全量：1729 passed
本批新增 Artifact 审计字段后：需再次重跑全量
重启后 smoke：已通过
重启后 Writer/TaskRuntime HTTP：已通过
前端 type-check/Vitest/build：已通过
```

下一步为包含本批最新 `agent.py` 审计字段的后端全量回归。

### Actor / Execution Owner 审计字段收口

已补齐 Agent 事件公开字段与成员写入审计：

```text
backend/app/services/agent_runtime.py
backend/app/api/routers/agent.py
backend/app/api/routers/test_agent_member_controls.py
backend/app/api/routers/test_agent_artifact_member_accept.py
```

当前不变量：

- Run command requested/applied/rejected 事件保留 `actor_user_id` 与 `execution_owner_id`；
- Artifact accept 的 `approval_required` 事件保留 `actor_user_id` 与 `execution_owner_id`；
- 审批 `request_json` 与事件审计字段一致；
- 公开事件仍受 `_VISIBLE_EVENT_KEYS` 白名单约束，不放开任意 Provider 或隐藏字段；
- 控制执行、审批执行和运行状态变更继续使用原始 execution owner。

本批定向验证：

```text
9 passed in 6.91s
```

全部 Agent 相关回归：

```text
493 passed in 431.80s (0:07:11)
```

## 2026-09-04 接续回写：Agent 批次最终后端基线

### A. 最新后端全量

在完成 Agent Run 控制成员化、Artifact 接受审计字段、Agent Runtime readable 投影以及既有测试合同对齐后，重新执行：

```powershell
cd D:\小说写作\xuanqiong-wenshu\backend
.\.venv\Scripts\python.exe -m pytest -q
```

最终结果：

```text
1729 passed in 724.56s
```

### B. 最新 Agent 路由证据

```text
全部 Agent API 路由：126 passed in 123.25s
Agent controls + Artifact accept + project HTTP：11 passed
TaskRuntime 成员路由：2 passed
Agent Runtime 核心集合：51 passed
Writer 成员读/流/写入/控制/HTTP：71 passed
Writer worker identity：6 passed
legacy outline fallback：4 passed
```

### C. 重启后运行时证据

最新进程通过：

```text
start.ps1：backend/frontend/proxy READY
verify.ps1 -Suite smoke：5 个阶段 PASS
OpenAPI：259 项，55 通过、204 跳过、0 失败
Writer/TaskRuntime 隔离 HTTP/JWT：4 passed
```

### D. 当前完整质量门禁基线

```text
Backend pytest：1729 passed
Frontend type-check：通过
Frontend Vitest：80 files / 496 tests passed
Frontend build-only：4918 modules transformed，成功
Smoke：通过
```

前端仍有非阻断依赖数据告警：

```text
baseline-browser-mapping data over two months old
caniuse-lite data 11 months old
```

### E. 接续状态

```text
当前总任务：active
当前主线：Agent/Writer 项目成员权限、运行恢复、审计和质量门闭环已形成稳定基线
下一 P0/P1：真实 Provider 条件下 generate/cancel/resume 端到端链
下一 P2：UI-006 长历史 cursor 分页、虚拟列表和移动端性能
```

### 2026-09-04 最新最终后端基线：Agent 审计字段补丁后

在 `_VISIBLE_EVENT_KEYS`、Run command 事件和 Artifact accept 事件补齐 `actor_user_id` / `execution_owner_id` 后，重新执行完整后端门禁：

```text
1729 passed in 798.57s (0:13:18)
```

该结果替换此前 1706 项旧基线；Agent 全域聚合 493 项、真实 Agent HTTP/JWT 14 项和成员控制/Artifact accept 9 项均已先行通过。

## 2026-09-04 最终回写：Agent 控制审计字段与当前质量门禁

### A. Agent 控制与候选接受

当前提交链已补齐：

```text
Agent Run pause/resume/cancel/command：项目成员写权限 + 原始 execution owner
Agent Artifact accept：项目成员写权限 + 原始 execution owner
approval_required / run_command_* 公开事件：actor_user_id + execution_owner_id
projectless Run/Artifact：仍按创建者私有边界
```

真实隔离 HTTP/ASGI 与专项测试确认 Editor/Admin 可操作 Owner Run，Viewer/非成员被拒绝，且控制命令、审批请求、终态事件不发生执行归属漂移。

### B. 当前最终实测门禁

本批所有 Agent 控制审计字段变更纳入后重新执行：

```text
Backend pytest：1729 passed in 768.38s (0:12:48)
Frontend type-check：通过
Frontend Vitest：80 files / 510 tests passed in 79.20s
Frontend build-only：4918 modules，13.19s，成功
隔离 Writer HTTP/JWT：31 checks，SMOKE_PASSED
Agent projection/control/artifact 专项：26 passed
```

此前完整后端失败的 2 条 Artifact 事件断言已由事件审计字段补齐修复；最终全量结果为 0 failures。前端保留既有 `baseline-browser-mapping`、`caniuse-lite` 和 Pinia 注入提示，均未影响门禁结果。

### C. 当前提交与工作区

```text
93dcf15 test: verify shared agent controls and artifact attribution
```

接续文档、Agent readable projection、共享 Run 控制、Artifact 接受审计和成员测试均已纳入提交链。未跟踪的导入/上传二进制运行工件保留原状，不提交、不批量清理。

### D. 下一阶段

```text
总任务：active
当前阶段：项目成员权限闭环与 Agent 历史投影已完成，完整后端/前端门禁已通过
下一阶段：真实重启后 TCP HTTP/SSE 对 Agent 历史投影与共享 Run 控制复验；随后进入 UI-005 工具注册策略统一、UI-006 长历史分页/窗口化性能和发布门禁
```
## 2026-09-05 当前任务续接回写：Agent 控制审计最终收口

### A. 最新修复

提交：

```text
c14d8c6 fix: expose actor attribution on approval events
```

`approval_granted` / `approval_rejected` 事件的公开字段白名单已与 `approval_required`、`run_command_*` 对齐，持续保留：

```text
actor_user_id
execution_owner_id
```

该字段用于审计操作者与持久化执行归属，不改变 projectless 私有边界，也不放宽审批执行权限。

### B. 最新验证

```text
Agent Artifact accept：4 passed
Agent controls + readable projection HTTP：23 passed
Backend 全量（含最新 Agent 控制链）：1729 passed in 768.38s
Frontend type-check：通过
Frontend Vitest：80 files / 510 tests passed
Frontend build-only：4918 modules，成功
verify.ps1 smoke：259 检查 = 55 通过 / 204 合理跳过 / 0 失败
```

此前全量测试中由审计字段补齐前产生的 2 条红灯已消除；随后定向和全量均通过。

### C. 当前工作区与未跟踪工件

```text
分支：codex/bohrium-integration-20260831
HEAD：c14d8c6
业务代码与测试变更：已提交
```

`backend/storage/novel_imports/9/*.bin`、`backend/storage/style_uploads/project-1/*.bin` 等运行产生的未跟踪二进制继续保留原状，不加入提交，不执行批量清理。

### D. 下一批执行计划

```text
P0：重启当前 HEAD 对应的 backend/frontend，执行 Agent 历史投影与共享 Run 控制 TCP HTTP/SSE 复验
P1：完成 UI-005 工具注册中心 schema/权限/编排策略统一审查
P1：完善 UI-006 长历史 cursor、窗口化渲染、性能基准与移动端视口回归
P2：发布前 fresh/upgrade/downgrade 迁移、依赖告警治理和正式质量报告
```

总任务继续保持 `active`，当前不返回历史卡死会话，也不创建新的 Codex task。
### 审批决定审计链收口

继续补齐 Artifact accept 的审批生命周期：

- `approval_required`、`approval_granted`、`approval_rejected` 事件允许并记录 `actor_user_id` 与 `execution_owner_id`；
- 审批决定从 `AgentApproval.request_json` 继承原始操作者，不因后续使用 Owner execution identity 而丢失 actor；
- Run command 请求/应用/拒绝事件保持同一审计字段合同。

专项结果：

```text
Artifact accept + Agent member control：9 passed in 8.07s
全部 Agent 相关测试：493 passed in 338.65s (0:05:38)
```

下一步重新执行真实服务 smoke，并在稳定后替换完整后端基线。

## 2026-09-05 UI-006 消息历史窗口化收口

### A. 本批实现

文件：

```text
D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue
D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.spec.ts
```

实现：

- 长会话默认只渲染尾部 60 条消息，减少初始 DOM 和布局成本；
- 通过“加载更早消息”按 60 条扩展窗口；
- 扩展窗口后按新增内容高度恢复滚动锚点，避免用户阅读位置跳动；
- 切换会话时按首条消息 ID 复位窗口，避免沿用上一会话已展开的窗口大小；
- 同一会话追加新消息不触发窗口复位，保留尾部消息体验。

### B. 验证

```text
AgentConversation 专项：8 passed
Frontend type-check：通过
Frontend Vitest：80 files / 512 tests passed in 79.23s
Frontend build-only：4918 modules transformed，成功，9.52s
```

已有后端最新基线：

```text
1729 passed
```

真实 smoke：

```text
后端 health 200；前端首页 200；前端代理 health 200；OpenAPI 259 检查 0 失败；LLM settings smoke 通过。
```

### C. 下一批

1. 继续为 Agent steps/commands/Artifacts 设计后端分页合同，保持旧列表响应兼容；
2. 评估 Agent Workspace 详情区域是否需要按需加载和分页，而不是扩大消息窗口；
3. 重新执行变更后的完整前端/后端基线，随后更新发布前 smoke 证据。

## 2026-09-05 规划审查：分页、按需加载、性能、UI-005 运行时绑定与迁移门禁

### A. 审查输入与当前结论

本次仅审查并更新本接续文档，未编辑业务代码、测试代码或运行工件。审查输入：

```text
工作区：D:\小说写作\xuanqiong-wenshu
分支：codex/bohrium-integration-20260831
HEAD：599da4a docs: update continuation checkpoint
```

当前 `git status --short` 的业务相关状态：

```text
M  TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
M  backend/app/agent/catalog_contract_v1.json
M  backend/app/agent/registry.py
M  backend/app/agent/schemas.py
M  frontend/src/features/agent/AgentConversation.spec.ts
M  frontend/src/features/agent/AgentConversation.vue
?? backend/app/agent/test_registry_ui005_contract.py
```

另有 `backend/storage/novel_imports/9/*.bin`、`backend/storage/style_uploads/project-1/*.bin` 等运行产生的未跟踪工件，继续保留原状，不纳入本阶段规划性提交，也不执行批量清理。

规划审查结论：

1. **UI-006 已完成消息会话尾部窗口化的第一步**：`AgentConversation` 默认渲染尾部 60 条，并支持按 60 条加载更早消息及滚动锚点恢复；这解决了会话消息的初始 DOM 膨胀，但没有覆盖 reasoning、activity/timeline、steps、approvals、artifacts、tool result 等长列表。
2. **UI-005 已有静态权限与契约基础**：manifest 已表达 `access_level`、`allowed_project_roles`、`idempotency_policy`、`context_bindings`，并已有 `backend/app/agent/test_registry_ui005_contract.py` 的模型级测试；当前工作树中该测试仍为未跟踪文件，尚未形成提交边界。
3. **UI-005 运行时绑定仍需形成完整证据链**：当前 `RunBoundToolRegistry` 已按 Run capability snapshot 限制工具名并校验 handler identity，但快照中的 generation、provider/version、manifest 版本、schema/上下文绑定一致性、执行时项目角色复核，仍应通过明确字段和运行时专项逐项验收，不能仅凭静态 manifest 测试视为完成。
4. **分页能力是分散存在而非统一合同**：activity/reasoning/events 使用 sequence cursor，timeline/audit 仍使用 offset，approvals/artifacts/steps 仍主要返回完整列表；前端 Workspace 仍会并行拉取多个完整详情集合。下一阶段应优先建立统一页面合同，再改 UI 消费方式。
5. **迁移门禁尚未成为发布阻断条件**：当前已有 `020_agent_catalog_relational.py` 至 `029_project_members.py` 等迁移链，但还需要 fresh、upgrade、重复执行、数据回填、降级策略和应用启动兼容矩阵的可重复证据。

### B. 下一阶段目标与不变约束

阶段目标：把 Agent Workspace 从“打开 Run 即拉取多个完整集合”收敛为“摘要首屏 + 详情按需 + 稳定游标分页 + 固定 Run 能力快照”，并让数据库迁移和性能预算成为发布前硬门禁。

不变约束：

- Owner/Editor/Viewer/Admin 的项目成员读取合同继续保持；Viewer 只读，写入/审批/运行控制权限不因分页或缓存扩大。
- projectless session、Run、Artifact、事件和工具调用继续保持创建者隔离，不因为共享项目分页查询而混入项目数据。
- `project_id + session_id + run_id + chapter_id` 等已有绑定继续严格校验；分页游标不得成为跨项目或跨 Run 的可复用令牌。
- 旧客户端列表响应和既有 SSE/事件游标语义保持兼容；新页面合同通过明确版本或显式 page 模式接入，避免静默改变旧响应类型。
- 所有生产修复遵循“先红灯样本—最小实现—专项—相邻回归—全量门禁—反向验证”的顺序。

### C. 分页与游标统一方案

#### C.1 统一页面 DTO

新增页面能力时优先复用统一 envelope；字段命名保持稳定：

```json
{
  "items": [],
  "next_cursor": "opaque-cursor-or-null",
  "previous_cursor": "opaque-cursor-or-null",
  "has_more": true,
  "page_size": 50,
  "snapshot": "stable-read-boundary"
}
```

合同要求：

- `items` 按服务端声明的唯一稳定顺序返回；游标只编码排序键、过滤条件摘要和资源边界，不接受客户端伪造任意主键跳转。
- 动态事件流使用单调 `sequence`：`after_sequence` 只返回严格大于游标的事件；SSE 的 `Last-Event-ID` 与该语义保持一致。
- steps、approvals、artifacts、execution facts、reasoning 等 Run 资源使用 keyset cursor；优先采用 `(created_at, id)` 或已有单调序列，禁止新功能继续扩大 offset 分页在高增长表上的使用。
- timeline/audit 现有 offset 保留给旧客户端；新 Workspace 页面使用 cursor 版本，并在同一 `snapshot` 内翻页，避免插入新记录造成重复或跳过。
- 默认 `page_size` 使用 50；上限按资源设为 100 或 200，事件/推理等高频资源沿用 500 的明确上限。服务端拒绝 0、负数、过大值和跨资源复用游标。
- 不返回昂贵的 `total` 作为默认字段；如确有 UI 需求，单独提供异步统计或明确成本标记。

#### C.2 兼容接入顺序

1. 先在 service 层补 `Page` 返回对象和 cursor 编解码/边界校验，不立即改变现有 router 的旧列表 response model。
2. 为 steps、approvals、artifacts 增加显式 page 路由或显式 `response=page` 合同；旧调用继续得到数组，新调用得到 envelope。
3. 将 timeline/audit 从 offset 迁移到 cursor 查询，同时保留 offset 兼容分支并设置迁移观测日志；确认旧前端没有依赖任意 offset 跳页后再收紧。
4. 对 reasoning/events/activity 统一 `after_sequence`、`before_sequence`、`limit` 的边界和排序，明确 `before_sequence` 的历史加载方向以及空页时的 cursor 行为。
5. 每个 page response 必须带资源边界标识（至少 `run_id`，项目资源同时带 `project_id`）；游标解码后的边界不匹配时返回稳定错误码，不返回另一资源的数据。

#### C.3 分页专项测试建议

建议新增或扩展：

```text
backend/app/services/test_agent_runtime_pagination.py
backend/app/api/routers/test_agent_projection_pagination.py
backend/app/api/routers/test_agent_stream_pagination.py
backend/app/api/routers/test_agent_member_access_pagination.py
```

最小用例：

- 首页、末页、空页、单条页、超过上限 page size；
- 同一 Run 连续翻页无重复、无遗漏，顺序稳定；
- 新插入记录不破坏同一 snapshot 的翻页结果；
- 游标损坏、过期、改写过滤条件、跨项目、跨 Run、projectless 互换均拒绝；
- Viewer/Editor/Owner/Admin 读取同项目资源，非成员 403，读取不改变 lease/owner/execution identity；
- 旧数组响应回归；新 envelope 与 OpenAPI/schema 序列化回归；
- SSE 首次流、`Last-Event-ID`、`after_sequence` 和断线重连只消费后续事件。

### D. 按需加载与 Workspace 数据流

#### D.1 首屏只保留摘要

Agent Workspace 首次打开只请求：

- session/run 摘要、状态、错误摘要、能力快照摘要；
- 最近一页 activity/event（默认 50，必要时 100）；
- 最近一页 reasoning 或当前活跃流所需的增量；
- 当前用户可执行动作的权限投影。

以下数据改为选中面板或显式展开时请求：

- steps：选择“步骤”面板后按页加载；
- approvals：存在 approval_required 或用户打开审批面板时加载；
- artifacts：首屏只加载元数据/状态/大小/版本，展开单个 Artifact 后再加载正文或 diff；
- execution facts、tool result、上下文快照、计划修订：先显示摘要，详情按单项加载；
- timeline/audit：默认最近页，筛选条件变化时重置 cursor，不复用旧筛选的游标。

#### D.2 前端加载控制

- 每个资源缓存键必须包含 `projectId/sessionId/runId/resource/filter/snapshot`，切换 Run 或项目立即丢弃旧请求结果。
- 同一资源的相同页请求去重；新选择覆盖旧选择时取消或忽略过期请求，禁止旧响应回写当前 Run。
- 面板展开采用懒加载，Artifact 正文、diff、tool result 等大字段不得随列表接口返回。
- 滚动接近底部才预取下一页；“加载更早”只在用户主动点击或接近顶部时触发，避免首屏预取完整历史。
- 断线 SSE 与历史补洞共用同一 cursor 投影；补洞没有连续推进时立即停止并展示可恢复错误，不进入无界重试。
- 继续保留 projectless/写入路径的现有 UI 行为，按需加载只改变读取时机和数据量，不改变授权与写入动作。

建议专项文件：

```text
frontend/src/views/AgentWorkspace.pagination.spec.ts
frontend/src/features/agent/composables/useAgentWorkspaceRuntime.pagination.spec.ts
frontend/src/features/agent/AgentReasoningCard.pagination.spec.ts
frontend/src/features/agent/AgentRunCommandHistory.pagination.spec.ts
frontend/src/features/agent/AgentRunInspector.pagination.spec.ts
```

### E. 性能优化与可量化预算

#### E.1 渲染策略

1. `AgentConversation` 的尾部 60 条窗口化作为基线，补齐长消息、空消息、切换 Run、连续追加和历史 prepend 的基准。
2. `AgentReasoningCard` 使用 sequence cursor 加“加载更早”，并采用可见窗口或等价虚拟化；不能只依赖 `content-visibility` 后仍创建全量 DOM。
3. activity/timeline、steps、commands、approvals、artifacts 使用分页列表；单项正文、diff、tool result 使用折叠详情和按需渲染。
4. 对超长正文使用文本截断、复制全文单独请求或 Blob/下载通道；列表 DTO 禁止重复携带完整正文。
5. 所有长列表组件增加稳定 `key`、加载占位、空态、错误重试、分页边界和键盘/移动端触摸回归。

#### E.2 建议发布预算

在现有机器和固定 fixture 上建立基线后，将以下作为默认阻断阈值；若真实测量需要调整，必须在文档中记录前后值和原因：

- 首屏 Agent Workspace 不因隐藏面板发起详情请求；默认每个列表首批不超过 100 项。
- 2000 条 reasoning/message fixture 下，初始实际 DOM 节点保持在可见窗口量级，不随总历史线性增长；点击加载历史只增加一个窗口页。
- 单个列表请求默认 payload 不超过 256 KB；正文/diff/tool result 等大字段独立加载。
- 同一 Run 首屏并行读取请求数量有上限，建议不超过 4 个；重复打开同一面板不得重复请求同一页。
- 分页连续读取 10 页后，内存、渲染耗时和游标延迟不得随页数线性恶化；具体阈值以基线测量值的回归百分比记录。
- 前端 type-check、Vitest、build-only 与后端专项/全量门禁保持全绿；性能回归测试不得通过减少断言或降低 fixture 规模制造通过。

#### E.3 反向性能验证

- 将窗口大小临时扩大为全量，性能专项应能明确暴露 DOM/耗时回归；恢复实现后重新通过。
- 将分页服务临时改为重复/跳序/忽略 cursor，连续翻页专项必须红灯。
- 将详情请求移回首屏或移除请求去重，Workspace 加载专项必须检测到额外请求。
- 将 SSE cursor 错位或返回旧事件，流回放专项必须失败。

### F. UI-005 运行时绑定收口方案

#### F.1 Run 能力快照必须冻结的字段

Run 创建时冻结一份可序列化、可审计的 capability snapshot，至少包括：

```text
catalog_generation
manifest_version
name
provider_id
provider_version
handler_identity
access_level
allowed_project_roles
risk_level
idempotency_policy
supports_stream
context_bindings
input_schema_digest
output_schema_digest
```

snapshot 同时记录 `project_id`、`session_id`、`run_id`、创建用户和创建时的 resolved context 摘要。快照是执行事实，不随注册中心热更新而漂移；新 Run 才使用新 catalog。

#### F.2 运行时顺序

固定执行顺序：

1. 载入 Run snapshot，并验证 snapshot 完整、版本可识别、边界与当前 Run 一致；
2. 校验当前用户对项目资源的角色，以及工具 manifest 的 `access_level/allowed_project_roles`；projectless 仍走创建者私有路径；
3. 用 Run 创建时的 ContextRef/ContextSnapshot 解析并应用 `context_bindings`，禁止从当前 UI 选中状态静默替换 Run 绑定；
4. 校验 handler identity、provider/version、manifest/schema digest 与 snapshot 一致；
5. 校验输入 schema、幂等键、审批/确认要求和 cancellation/stream 合同；
6. 执行并记录 `actor_user_id`、`execution_owner_id`、snapshot generation、tool name、correlation/transaction id；
7. 任一项不匹配即 fail closed，返回稳定错误码并写入审计事件，不降级到当前 registry 的同名工具。

当前代码审查重点：`RunBoundToolRegistry.from_context()` 已读取 capability resolution/release tools 并限制 allowed names，也校验 handler identity；下一批必须验证并补齐 generation、provider/version、manifest/schema digest 和上下文边界是否真正参与执行时校验，避免只在数据快照中携带而未形成约束。

#### F.3 UI-005 专项与验收矩阵

现有静态测试继续保留：

```text
backend/app/agent/test_registry_ui005_contract.py
```

建议补充：

```text
backend/app/agent/test_registry_ui005_runtime_binding.py
backend/app/api/routers/test_agent_runtime_capability_snapshot.py
backend/app/services/test_agent_tool_execution_contract.py
```

最小矩阵：

- 创建 Run 后修改全局 catalog：旧 Run 继续使用旧 snapshot，新 Run 使用新 generation；
- 同名工具 handler identity/provider/version 变化时，旧 Run 明确拒绝；
- manifest/schema/context binding 变化时拒绝漂移；
- capability resolution 少工具、多工具、重复工具、未知工具、工具顺序变化均有确定结果；
- Viewer 只能读取，Editor/Owner/Admin 才能执行对应写工具，非成员 403；
- projectless Run 不能借用项目工具快照或项目成员权限；
- cancellation、timeout、idempotency、approval_required 和 stream 工具保持既有合同；
- 公开 catalog 与 Python registry、provider health、handler identity 的一致性可序列化并可审计。

### G. 迁移与发布门禁

#### G.1 数据库迁移门禁

针对现有 `020_agent_catalog_relational.py` 至 `029_project_members.py` 及后续迁移，建立固定矩阵：

1. **静态链检查**：单一 head、revision/down_revision 连续、无重复 revision、模型与迁移 schema 差异可解释。
2. **Fresh**：空数据库从头升级到当前 head，启动应用、生成一个 projectless Run 和一个项目 Run，验证核心表、索引、唯一约束和成员权限。
3. **Upgrade**：至少从 `019`、`024`、`029` 三个代表快照升级到当前 head；每个快照记录表计数、关键列 nullability、索引和数据回填前后计数。
4. **重复执行**：同一迁移命令重复运行应保持幂等，不重复插入 catalog/provider、成员 owner 或默认数据。
5. **运行兼容**：迁移中间状态不应让应用启动静默降级为错误权限；滚动发布期间旧代码/新 schema 与新代码/旧 schema 的兼容矩阵必须有明确结果。
6. **Downgrade/回滚**：支持的降级逐个实测并验证数据损失边界；不支持安全降级的迁移必须显式标注 forward-only，发布包提供数据库备份、恢复演练和应用回滚顺序，不能把“down_revision 存在”当作可回滚证明。
7. **失败注入**：在每个关键 DDL/backfill 步骤前后模拟中断，确认重跑结果、事务边界和错误恢复行为。

建议证据与测试位置：

```text
backend/app/migrations/test_migration_gate.py
backend/app/migrations/test_catalog_migration_compatibility.py
backend/output/migration-gate-<date>.json
```

若项目当前没有独立 migration test package，则将测试放到现有 `backend/app/services` 或迁移工具目录，并在本文件记录实际路径，禁止只生成人工报告。

#### G.2 Catalog/Schema/客户端门禁

- `catalog_contract_v1.json`、Pydantic manifest、Python registry、provider health 和前端 `AgentToolCatalog` 类型必须通过同一 drift test；工具名、风险级别、权限角色、schema、stream、幂等策略任何不一致都阻断发布。
- OpenAPI 快照检查新增 page envelope、错误码、SSE 参数和旧响应兼容；不接受只在单元测试中存在而 HTTP schema 未更新。
- fresh/upgrade 数据库上各执行一次 UI-005 capability snapshot 创建与工具读取，证明迁移后运行时绑定可用。
- 前端旧 fixture、旧数组响应、新分页 envelope、空页和错误码都要有兼容测试。

#### G.3 发布阻断顺序

```text
Gate 0：git 状态、未提交成果、运行工件和回滚点登记
Gate 1：UI-005 catalog/registry/schema drift + runtime binding 专项
Gate 2：分页 service/router/member-access/SSE 专项
Gate 3：前端按需加载、窗口化、移动端和请求去重专项
Gate 4：迁移静态链 + fresh + upgrade + 重复执行 + 回滚/备份证据
Gate 5：后端全量 pytest
Gate 6：frontend type-check + test:run + build-only
Gate 7：真实服务 health、OpenAPI、HTTP/JWT、SSE、projectless/项目隔离 smoke
Gate 8：审计产物、性能预算、迁移证据和正式报告归档
```

任一 Gate 失败时，状态标为 `blocked` 或 `active-with-gap`，不得用跳过测试、删 fixture、放宽权限、改变旧响应断言或只更新报告来制造通过。

### H. 分阶段执行顺序与退出条件

#### P0：冻结合同与建立红灯

- 归档当前 UI-005 工作树差异和未跟踪专项测试的边界；
- 为 page envelope、cursor 边界、snapshot 字段和错误码先写失败测试；
- 记录现有 Workspace 首屏请求数、响应大小、DOM 数量和 2000 条历史 fixture 基线。

退出条件：合同测试在旧实现上按预期红灯，且基线数据有命令、时间、环境和结果记录。

#### P1：UI-005 运行时绑定

- 实现快照冻结、generation/provider/version/identity/schema/context 校验；
- 接入 actor/execution owner 审计字段；
- 完成 projectless、成员角色、审批、幂等、取消、超时、流式工具回归。

退出条件：UI-005 runtime 专项全绿，旧 Run/新 Run 漂移测试和反向破坏测试均完成。

#### P1：后端分页与按需 API

- 先 service 后 router，steps/approvals/artifacts 优先；
- 再收敛 activity/reasoning/timeline/audit 的 cursor 合同；
- 保持旧列表响应，新增 page 版本并更新 OpenAPI；
- 建立跨项目、跨 Run、projectless 和成员角色分页隔离测试。

退出条件：连续 10 页无重复/遗漏，游标边界稳定，旧客户端回归全绿。

#### P1：前端消费与性能

- Agent Workspace 首屏摘要化；
- 详情面板懒加载、请求去重、过期响应丢弃、Artifact 正文/diff 单项加载；
- Reasoning、timeline/activity、steps/commands/approvals/artifacts 完成窗口化或分页渲染；
- 加入移动端窄视口和键盘可用性回归。

退出条件：请求数、payload、DOM 和加载耗时满足预算；故意恢复全量渲染时性能专项红灯。

#### P2：迁移门禁与发布验收

- 完成迁移链静态检查、fresh/upgrade/重复执行、备份恢复和 forward-only 标记；
- 在迁移前后执行 UI-005 snapshot 与分页读取 smoke；
- 更新正式质量报告、审计 JSON、回滚点和证据索引。

退出条件：Gate 0—8 全部有可复跑命令和原始输出；未跟踪运行工件与业务提交边界清晰；总任务才可从 `active` 进入完成评估。

### I. 本次规划审查回报

本次实际修改文件仅为：

```text
D:\小说写作\xuanqiong-wenshu\TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
```

建议下一次执行严格从 **P0 合同红灯与性能基线** 开始，优先处理 UI-005 运行时快照校验和 steps/approvals/artifacts page envelope；在这两项完成前，不继续扩大 UI-006 的全量视觉层改造，也不把当前静态注册契约测试或已有消息窗口化结果标记为整批完成。

## 2026-09-05 UI-006 审查与 Agent 历史集合分页契约

### A. UI-006 独立审查收口

文件：

```text
D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue
D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.spec.ts
```

修复并验证：

- 用稳定的 `session_id` 识别会话，避免同一会话刷新或前置补历史消息时错误收缩已展开窗口；
- 加载更早消息增加并发闸门、禁用态、加载态和 `aria-busy`，快速重复点击只扩展一个窗口；
- 长历史默认渲染尾部 60 条，按 60 条扩展并保持滚动锚点；
- 实际会话切换按不同 `session_id` 复位窗口。

验证结果：

```text
AgentConversation 专项：10 passed
Frontend type-check：通过
Frontend Vitest：80 files / 514 tests passed
Frontend build-only：4918 modules transformed，成功
```

### B. Agent steps/commands/artifacts 可选分页

当前工作树补齐三类历史集合的兼容分页合同：

- 不带 `offset` 继续返回原有数组响应；
- 显式 `offset` 返回 `run_id/items/total/limit/offset/has_more/next_offset` 页对象；
- 读取分页继续复用 `get_readable_run` 项目成员访问边界；
- 通过 `created_at + id` 对 Artifact 做稳定排序，避免同一时间戳下顺序漂移。

新增/涉及测试：

```text
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_history_pagination.py
D:\小说写作\xuanqiong-wenshu\backend\app\api\routers\test_agent_readable_projection_http.py
```

真实验证：

```text
分页/可读投影/时间线回归：35 passed
注册契约、catalog release、relational、UI-005、capability：68 passed
Agent runtime、tool adapter、成员访问：20 passed
真实 JWT 分页成员/非成员隔离：1 passed
```

### C. 当前未完成队列

```text
P0：重启当前 HEAD 对应 backend/frontend，执行真实 TCP HTTP/SSE Agent 历史投影与共享 Run 控制复验
P1：将跨会话 Agent timeline 从 offset 迁移为稳定游标或补齐等价的可消费分页合同
P1：评估前端 Agent Workspace 详情区域按需消费 steps/commands/artifacts 页对象
P2：重新执行后端全量门禁并更新发布前 smoke 证据
```

本批未创建 Codex task；现有未提交业务改动与运行工件继续保留。

## 2026-09-05 当前批次最终收口：分页、懒加载与运行时能力闸门

### A. 本批提交

当前分支：`codex/bohrium-integration-20260831`

```text
43b1f3f feat: add agent history pagination contracts
a) steps/commands/artifacts 可选 offset 分页 envelope，保留旧数组响应
b) AgentConversation 60 条尾部窗口化与性能边界测试

4508103 perf: lazy load agent workspace details
a) Agent Workspace 数据详情区首开懒加载
b) Provider/治理/实体/成员详情请求延后到首次展开

 e770a96 feat: enforce run capability contract fences
 a) RunBoundToolRegistry 冻结 manifest/provider/generation 合同
 b) 执行期拒绝 live registry 漂移
```

### B. 已验证门禁

```text
后端全量：1744 passed in 661.95s
前端全量：81 files / 520 tests passed
前端 type-check：通过
前端 build-only：4918 modules transformed，成功
UI-005 定向组合：37 passed
分页/时间线/可读投影：稳定相关回归通过（实验性 timeline cursor 已撤销）
AgentWorkspace + AgentConversation 定向：45 passed
```

固定提示仍为浏览器数据包过期告警和测试环境 Pinia 注入提示，不影响门禁结果。

### C. 当前能力边界

1. steps/commands/artifacts 只有显式 `offset` 才返回页对象，旧调用保持裸数组兼容；前端已补充 page client，但 Workspace 详情消费仍待独立接入。
2. AgentConversation 已控制 DOM 窗口，但 `getSession()` 仍一次返回完整消息数组；后续继续做消息 API cursor 分页，不能把本地窗口化当作 payload 优化完成。
3. Agent Workspace 数据与候选区已改为首次展开加载，运行时错误可以重试；Artifact 质量/血缘的逐项懒加载仍是下一批优化点。
4. RunBoundToolRegistry 已在默认 registry 上校验 generation、provider 元数据、handler identity 和 manifest 合同；旧 Run 缺失完整 release 上下文时保持兼容路径。成员角色最终执行闸门仍需在 Capability Resolver/执行入口做统一绑定验证。
5. 跨会话 timeline 仍保持成熟的 `offset + limit` 稳定旧实现；此前试验的 keyset cursor 因直接路由函数调用中的 FastAPI Query 默认对象兼容问题及测试推进问题已撤销，不计入完成项。

### D. 当前工作区与发布状态

业务代码工作区当前已清洁；剩余未跟踪内容主要是运行产生的 `.bin` 导入/上传工件和 `.vite/` 缓存，不提交、不批量清理。

最新完整门禁已通过，但发布报告仍保留 `NO-GO` 历史审查结论，原因包括生产默认配置告警、真实服务 smoke 证据需要用当前 HEAD 替换，以及迁移/恢复矩阵需继续归档。因此当前总任务状态保持 `active`。

### E. 下一执行顺序

```text
P0：用当前 HEAD 重启 backend/frontend，重跑真实 HTTP/JWT/SSE、成员隔离和共享 Run 控制验收
P1：把 Agent Workspace steps/commands/artifacts 接入 page client，完成详情区分页消费与空页/错误/切换 Run 回归
P1：在 Capability Resolver/执行入口统一接入当前成员角色与 allowed_project_roles，补 projectless/Viewer/Editor/Owner/Admin 矩阵
P1：Artifact 列表摘要与质量/血缘事实拆成两阶段加载，保留深链和接受候选流程
P2：完成 fresh/upgrade/downgrade/备份恢复矩阵，替换当前 HEAD 的 release gate 证据
P2：最终后端/前端全量门禁、smoke 证据归档，重新评估 GO/NO-GO
```

当前接续策略继续有效：只在本任务和当前工作区推进，不回历史卡死会话，不创建新的 Codex task；子智能体按独立范围并行审查，结果由主任务统一集成。

## 2026-09-05 成员角色执行闸门与当前 HEAD 全量门禁复核

### A. 成员角色闸门收口

提交：

```text
5de763f feat: enforce member roles at agent execution
```

已完成：

- `CapabilityResolutionRequest` 增加 `project_role`，并由 `AgentRuntimeService` 在 Run 能力解析前从项目访问投影读取当前角色；
- `resolve_capabilities()` 保持函数式包装与对象式 Resolver 语义一致；
- `RunBoundToolRegistry` 在执行期复核 Run 快照中的用户/项目边界；
- 项目工具执行前统一读取当前成员角色，并按 manifest 的 `allowed_project_roles` 阻断角色降级后的执行；
- projectless 工具继续绑定原始执行用户，其他用户复用同一 Run 时被阻断；
- 非成员项目访问保留原有 HTTP 403/404 错误语义，输入 schema/审批身份错误仍保留 `ToolContractViolation` 语义；
- `build_tool_manifest()` 支持自定义 `output_schema` 与 `idempotency_key`，不影响既有调用方。

### B. 当前 HEAD 验证

```text
成员角色/Resolver/执行期/Tool Adapter：51 passed
UI-005/Catalog/Resolver/Provider 组合：72 passed
后端全量：1754 passed in 771.34s
Frontend 全量（当前已提交前端基线）：81 files / 523 tests passed
Frontend type-check：通过
Frontend build-only：4918 modules transformed，成功
```

全量后端结果以当前 HEAD `5de763f` 及其父提交链为准；固定的浏览器数据包过期告警与测试环境 Pinia 注入提示仍存在，但没有失败。

### C. 当前 Git 与发布状态

```text
当前 HEAD：5de763f
当前分支：codex/bohrium-integration-20260831
```

业务代码和接续文档提交已形成可回滚链；工作区剩余未跟踪内容为运行产生的 `.bin` 导入/上传工件、`.vite/` 缓存和发布审计草稿，不纳入业务提交，不批量清理。

此前 `docs/reports/RELEASE_GATE_AUDIT_20260905.md` 是基于更早 `599da4a` 工作区的审计快照，仍保留其 NO-GO 历史结论；待当前 HEAD 的真实服务、生产配置和迁移恢复证据替换后再重新评估。

### D. 下一执行批次

```text
P0：重启当前 HEAD 的 backend/frontend，执行真实 health、OpenAPI、HTTP/JWT、SSE、成员隔离和共享 Run 控制验收
P1：将 Workspace 详情区接入分页 page client；当前仅保留 page API 客户端与后端合同，未把未通过的半成品消费代码带入提交
P1：Artifact 列表摘要与质量/血缘事实两阶段加载，保持深链和候选接受流程
P2：fresh/upgrade/downgrade/备份恢复矩阵与默认生产配置审查
P2：更新 release gate 报告为当前 HEAD，完成最终发布评估
```

当前总任务继续保持 `active`，按接续文档逐批推进。

## 2026-09-05 当前 HEAD 真实服务复验

### A. 服务重启

```text
启动脚本：D:\小说写作\xuanqiong-wenshu\start.ps1
日志目录：D:\小说写作\xuanqiong-wenshu\logs\run-20260905-104230
Backend：http://127.0.0.1:8013
Frontend：http://127.0.0.1:5174
Frontend proxy：http://127.0.0.1:5174/api/health
```

启动结果：

```text
BACKEND_READY=True
FRONTEND_READY=True
FRONTEND_PROXY_READY=True
```

### B. 当前 HEAD smoke

```text
verify.ps1 smoke：259 检查
通过：55
合理跳过：204
失败：0
```

通过范围包括：backend health、frontend 首页、frontend proxy health、OpenAPI 路由冒烟和 LLM settings health-check。需要真实资源 ID 的项目/章节接口按脚本约定跳过，不能把跳过项等同于完整业务验收。

### C. 隔离 Writer HTTP/JWT 验收

```text
脚本：D:\小说写作\xuanqiong-wenshu\backend\scripts\run_writer_member_acceptance.py
结果：SMOKE_PASSED
checks=31
generate_status=200
finalize_status=200
outline_status=200
resume_status=200
dispatch_kinds=[generate, generate, finalize, outline]
```

脚本使用临时 SQLite，迁移从初始 schema 到 `029_project_members`，结束后清理隔离目录，不污染主数据库。

### D. 发布状态复核

当前业务门禁与真实服务基本探针均通过；发布状态仍保持 `NO-GO`，原因没有改变：

- 生产配置仍需明确替换默认管理员密码并关闭 DEBUG；
- 真实资源型 smoke 仍有大量合理跳过，需要隔离 fixture 或真实资源矩阵补齐；
- fresh/upgrade/downgrade/备份恢复证据仍需以当前 HEAD 重新归档；
- `.vite/` 与导入/上传 `.bin` 是运行工件，必须排除在发布提交之外。

下一步优先级保持：

```text
P0：生产配置门禁与当前 HEAD 的 fresh/upgrade/restore 证据
P1：Workspace 分页 page client 的正式消费（不带入未通过的半成品）
P1：Artifact 摘要与质量/血缘事实两阶段加载
P2：更新 release gate 报告并完成 GO/NO-GO 重评
```

## 2026-09-05 Artifact 两阶段加载收口

### A. 实现与提交

提交：

```text
13c701d perf: defer artifact quality facts
```

已完成：

- Artifact 列表先读取分页元数据摘要，不再在 Run 切换/普通历史恢复时为全部候选并行拉取质量与谱系事实；
- 每个 Artifact 增加显式“读取质量与谱系”动作，事实请求按单项触发；
- 深链指定 Artifact 时只对指定项加载事实并恢复预览；
- 质量阻断、diff、预览、接受候选等既有操作仍保留单项加载链；
- 分页摘要载入后恢复当前 Run 已记忆的 Artifact 投影，避免切换/刷新后阻断与差异定位丢失；
- 详情区分页支持加载更多候选，旧数组接口仍作为兼容 fallback。

### B. 验证

```text
Artifact/Runtime/Workspace 定向：65 passed
前端全量：81 files / 526 tests passed
Frontend type-check：通过
Frontend build-only：4918 modules transformed，成功
```

新增覆盖包括：

- 普通摘要列表不触发每个 Artifact 的质量/谱系请求；
- 单项显式读取质量与谱系事实；
- 深链 Artifact 单项事实加载；
- 相同时间戳候选的稳定排序；
- 分页加载期间切换 Run 的过期响应隔离；
- 已选阻断/diff/预览投影在摘要刷新后恢复。

### C. 当前剩余重点

```text
P0：当前 HEAD 生产配置审查（DEBUG/default admin）与迁移恢复证据
P1：完整会话 messages/runs API cursor 分页，解决 getSession 全量 payload
P1：Artifact 页面错误重试、分页筛选状态和深链体验继续回归
P1：成员角色在实际 Agent HTTP 执行入口的 owner/editor/viewer/admin 矩阵验收
P2：更新 RELEASE_GATE_AUDIT_20260905.md 为当前 HEAD，重新评估 GO/NO-GO
```

当前总任务保持 `active`，继续按 P0/P1/P2 逐批推进。

## 2026-09-05 P0 迁移与配置门禁复核

### A. 当前 HEAD 结果

```text
HEAD：1ff1912
分支：codex/bohrium-integration-20260831
```

专项：

```text
Alembic migration + project member migration + deployment contract + config security：19 passed in 53.97s
backend pip check：No broken requirements found
```

迁移链当前已覆盖 fresh、重复升级、代表性版本路径、项目成员回填和部署契约；后续仍需补齐以当前 HEAD 归档的 restore/downgrade 原始证据。

### B. P0 配置结论

当前 `backend/.env` 仍为本地开发配置：

```text
ENVIRONMENT=development
DEBUG=true
ADMIN_DEFAULT_PASSWORD=ChangeMe123!
DB_PROVIDER=sqlite
```

启动日志因此保留开发配置提示。该配置不在本批自动替换，避免覆盖本地凭据或改变运行环境；发布门禁继续要求正式部署注入独立的管理员密码、关闭 DEBUG，并重新生成当前 HEAD 的启动证据。

### C. 下一批消息历史分页

已登记独立审查任务，目标是新增向后兼容的 messages/runs page API：

```text
旧 GET /agent/sessions/{session_id} 默认保持 AgentSessionDetail 数组字段
新增显式分页路径或参数，使用稳定 sequence/created_at + id 游标
成员/projectless 边界复用现有 readable session
前端在长会话场景按页取历史，避免仅做本地 DOM 窗口化
```

在消息 API 合同和 HTTP 回归通过前，不把 `getSession()` 全量 payload 标记为性能问题已解决。


## 2026-09-05 当前 HEAD 复验与 Agent 详情分页消费

### A. 当前提交与工作树

```text
分支：codex/bohrium-integration-20260831
HEAD：以本次记录生成时的 git log -1 为准
源码工作树：前端详情分页消费改动待审查/提交；运行产生的 .vite/ 与 storage 工件保留原状
```

### B. 本批实现

1. 能力解析请求新增 `project_role`，并将角色写入 resolver snapshot；`AgentRuntimeService.create_run` 对项目 Run 从 `ProjectAccessService` 解析并冻结 owner/editor/viewer/admin（管理员归一为 admin）。
2. `AgentToolRegistry.execute` 在单一执行边界重新读取项目成员角色，写工具拒绝 viewer；projectless Run 通过 capability snapshot 保持创建用户私有执行身份。
3. `RunBoundToolRegistry` 校验 snapshot 中的 execution user/project 与实际执行参数一致。
4. Agent Workspace 详情区接入 `/runs/{run_id}/steps|commands|artifacts` page envelope：首屏 50 条、显式加载更多、按 ID 合并、同秒 Artifact 以 `created_at + id` 稳定排序、请求去重、过期请求 loading 清理。
5. Artifact 列表摘要与质量/谱系事实分两阶段；列表首屏不批量读取事实，用户可按单个 Artifact 显式读取质量与谱系。
6. 日志动作定位会先确保步骤摘要已载入；深链 Artifact 只对目标 Artifact 读取事实。

### C. 当前真实验证

```text
后端全量 pytest：1754 passed in 779.99s (0:12:59)
后端能力/成员/运行时定向：105 passed in 59.79s
前端 type-check：通过
前端全量 Vitest：81 files / 527 tests passed
前端 Agent 分页、Artifact、Workspace、UI-006 定向：81 tests passed
前端 build-only：4918 modules transformed，成功
verify.ps1 smoke：259 checks = 55 passed / 204 skipped / 0 failed
真实 Writer 成员验收：SMOKE_PASSED checks=31，generate/finalize/outline/resume 均为 200
差异检查：git diff --check 通过
```

固定非阻塞提示：浏览器数据包过期提示、Vitest AgentWorkspace 测试环境 Pinia 注入提示。

### D. 仍未完成的发布门禁

```text
1. 迁移 fresh/upgrade/repeat/downgrade/备份恢复矩阵尚未完整归档。
2. verify smoke 仍有 204 项因缺少真实资源 ID 跳过，不能作为真实资源验收唯一证据。
3. 真实生产配置默认 DEBUG/管理员配置告警仍需在显式发布配置下复验。
4. 前端详情分页的真实 TCP/JWT 长历史页面验收仍需补充，当前 page envelope 已有单测和 API 合同验证。
5. 需要对本批前端改动执行最终审查后提交，并再次运行发布前全量门禁。

因此总任务继续保持 active / NO-GO，下一顺序为：提交前端详情分页改动 → 真实 TCP/JWT 分页长历史验收 → 迁移/恢复矩阵 → 最终全量门禁与发布报告。
```

## 2026-09-05 Agent 消息历史分页合同

### A. 新增提交

```text
9e92cee feat: add paged agent message history
```

新增：

```text
GET /api/agent/sessions/{session_id}/messages?limit=60
GET /api/agent/sessions/{session_id}/messages?limit=60&before_sequence=61
```

合同：

- 默认返回最新消息页；
- `before_sequence` 排除游标本身并向更早消息翻页；
- 数据库按 `sequence DESC` 取 `limit + 1`，响应恢复为 `sequence ASC`；
- 页对象包含 `session_id/items/next_cursor/has_more`；
- `limit` 由路由限制在 `1..200`；
- 复用 `_session_readable`，项目成员共享读取和 projectless 创建者私有边界保持不变；
- 既有 `GET /api/agent/sessions/{session_id}` 不变，仍返回兼容的 `messages/runs` 数组。

涉及文件：

```text
backend/app/agent/schemas.py
backend/app/services/agent_runtime.py
backend/app/api/routers/agent.py
backend/app/api/routers/test_agent_message_pagination.py
```

### B. 验证

```text
消息分页 + 既有 Agent runtime route：30 passed
py_compile：通过
git diff --check：通过（提交前除已知运行文档空行外）
```

隔离测试覆盖：最新页、游标排除、空尾页、limit 边界、项目成员读取、项目越权 403、旧详情数组形状。

### C. 当前边界

本提交只交付后端分页合同；前端当前仍通过 `getSession()` 读取完整消息数组，下一批将改造 `useAgentSessionLifecycle`：首屏读取消息页，加载更早消息时调用 page endpoint，并与 `AgentConversation` 的本地窗口/锚点合并。当前不能把后端 endpoint 单独视为首屏 payload 已降低。

## 2026-09-05 消息分页路由当前 HEAD 服务复验

### A. 当前服务

```text
日志目录：D:\小说写作\xuanqiong-wenshu\logs\run-20260905-111959
Backend ready：True
Frontend ready：True
Frontend proxy ready：True
```

### B. smoke 结果

```text
verify.ps1 smoke：261 检查
通过：55
合理跳过：206
失败：0
```

新增 `GET /api/agent/sessions/{session_id}/messages` 已进入 OpenAPI 路由检查集合，没有引入 500 级错误。需要真实资源 ID 的检查仍按既有脚本规则跳过。

### C. 下一动作

```text
P1：补前端 AgentAPI.listSessionMessagesPage 客户端和独立 API 回归
P1：将 useAgentSessionLifecycle 改为可选分页历史消费，保留旧 getSession fallback
P1：补前端 prepend、锚点、会话切换和 projectless/member HTTP 验收
```

## 2026-09-05 当前全面审查权威状态（最终）

> 本节是当前任务唯一可执行的状态入口。此前各节中的“下一步”“下一批”“下一动作”均保留为历史记录；若与本节冲突，以本节和当前工作区实测结果为准。

### A. 当前 HEAD 与分支

```text
工作区：D:\小说写作\xuanqiong-wenshu
分支：codex/bohrium-integration-20260831
HEAD：9ca512f4aa633941f21c8ac6eab59cd5c0830ec9
HEAD 提交：test: cover session run pagination compatibility
相对 origin/codex/bohrium-integration-20260831：ahead 65
审查日期：2026-09-05
```

当前 HEAD 已包含以下已落地能力：

- Agent steps/commands/artifacts page envelope 与前端 Workspace 分页消费；
- Agent Workspace 详情区首屏懒加载、按页读取、重复请求抑制、Run 切换隔离、空页收口和错误状态；
- Run capability snapshot / provider / manifest 合同闸门；
- 项目成员角色在 Agent 执行入口的读取和写入边界；
- Artifact 质量/谱系事实两阶段加载；
- Agent 消息历史分页后端合同与前端 `listSessionMessagesPage` 消费；
- AgentConversation 尾部窗口化、加载更早消息和滚动锚点保持。

### B. 当前未提交文件与运行工件

当前 `git status --short --branch` 实测：

```text
已跟踪未提交文件：7 个
未跟踪条目：108 个
其中：.bin 运行工件 106 个，.vite 缓存 1 项，发布审查报告 1 项
```

已跟踪未提交文件：

```text
frontend/src/api/agent.spec.ts
frontend/src/api/agent.ts
frontend/src/features/agent/AgentConversation.spec.ts
frontend/src/features/agent/AgentConversation.vue
frontend/src/features/agent/composables/useAgentSessionLifecycle.spec.ts
frontend/src/features/agent/composables/useAgentSessionLifecycle.ts
frontend/src/views/AgentWorkspace.vue
```

未跟踪非二进制内容：

```text
.vite/vitest/results.json
docs/reports/RELEASE_GATE_AUDIT_20260905.md
```

运行产生的二进制工件继续保留原状，不纳入本次文档审查改动：

```text
backend/storage/novel_imports/9/*.bin
backend/storage/style_uploads/project-1/*.bin
```

本次只修改本接续文档；未修改代码、测试、数据库、配置、启动脚本或运行工件。

### C. 当前前端未提交批次

当前未提交前端批次是 Agent 消息历史分页链路，不是 steps/commands/artifacts 详情分页批次。具体包括：

1. `AgentAPI.getSession(sessionId, { includeMessages: false })` 的兼容调用；
2. `AgentAPI.listSessionMessagesPage` 客户端；
3. `useAgentSessionLifecycle` 的最新消息页加载、向前翻页、旧 `getSession()` 回退、会话切换隔离；
4. `AgentConversation` 的外部分页事件、尾部窗口化、prepend 后滚动锚点保持；
5. `AgentWorkspace` 对加载更早消息事件和分页状态的消费。

旧数组接口仍保留，兼容路径未移除。当前 steps/commands/artifacts 分页消费已经属于 HEAD，不应再写入“待接入”队列。

### D. 当前实测验证

本次在当前 HEAD/工作区执行的最小相关门禁：

```text
AgentWorkspace + useAgentWorkspaceRuntime：2 个测试文件 / 56 tests passed
AgentAPI + useAgentSessionLifecycle + AgentConversation：3 个测试文件 / 34 tests passed
npm run type-check：通过
git diff --check：通过
```

两组测试均为当前命令实测结果：

```text
2 files passed
Tests 56 passed

3 files passed
Tests 34 passed
```

固定非阻塞提示：

- `baseline-browser-mapping` 数据包过旧；
- `caniuse-lite` 数据包过旧；
- AgentWorkspace 测试环境存在 Pinia injection warning。

这些提示未造成本次相关门禁失败。`.vite/vitest/results.json` 中的旧失败结果属于缓存内容，不作为当前验证依据。

### E. 当前完成度判断

| 工作项 | 当前状态 | 依据 |
|---|---|---|
| 项目成员权限闭环 | 已完成 | 当前 HEAD 历史提交与既有后端/HTTP 回归记录 |
| Agent Run 控制审计 | 已完成 | 当前 HEAD 历史提交与既有 Agent 控制回归记录 |
| UI-005 注册中心与运行时能力快照 | 已完成 | 当前 HEAD 已包含相关提交，既有定向回归记录有效 |
| UI-006 AgentConversation DOM 窗口化 | 已完成 | 当前前端测试 11 项通过，相关类型检查通过 |
| steps/commands/artifacts page client | 已完成并进入 HEAD | `HEAD` 中存在 `loadRunDetailPage`、三个 page client 和“加载更多”入口；相关运行时/Workspace 测试 56 项通过 |
| Agent 消息历史分页前端消费 | 已实现，未提交 | 7 个前端文件未提交；相关测试 34 项通过，仍需形成独立提交批次 |
| 真实 TCP/JWT 长历史消息分页验收 | 未完成 | 当前只有单测和已有服务路由 smoke 证据 |
| fresh/upgrade/repeat/downgrade/备份恢复矩阵 | 未完整归档 | 历史专项有通过记录，当前 HEAD 的完整发布证据仍需集中归档 |
| 正式生产配置复验 | 未完成 | 仍需以显式发布配置复跑并确认 DEBUG/默认管理员配置告警消失 |

### F. 当前 NO-GO 条件

当前总任务保持 `active / NO-GO`，阻断条件如下：

1. 工作区存在未提交前端源码与测试，当前不是可直接打包的干净发布树；
2. Agent 消息分页前端批次尚未形成提交、审查和发布前完整门禁闭环；
3. 真实 TCP/JWT 长历史消息分页页面验收尚未完成；
4. fresh/upgrade/repeat/downgrade/备份恢复矩阵尚未以当前 HEAD 的统一证据包完整归档；
5. 正式生产配置下的 DEBUG 与默认管理员配置门禁尚未完成复验；
6. `verify.ps1 smoke` 仍存在大量因缺少真实资源 ID 的合理跳过项，不能单独代表完整资源验收；
7. 未跟踪 `.vite` 与 storage 二进制工件仍需在发布打包边界之外单独处理。

历史发布审查报告 `docs/reports/RELEASE_GATE_AUDIT_20260905.md` 基于更早的 `599da4a` 快照，仍作为历史证据保存；其中关于 UI-005 失败、旧 HEAD 和旧文件清单的内容不得当作当前状态。

### G. 唯一后续执行计划

按以下顺序执行，完成一项再进入下一项：

```text
P0：提交前端消息分页批次前的最终 diff 审查，确认只包含 7 个预期前端文件；
P0：重新执行前端全量 type-check、Vitest、build-only，并记录当前 HEAD/提交后的数字；
P1：启动当前 HEAD 对应服务，补真实 TCP/JWT 消息分页、成员共享读取和 projectless 隔离验收；
P1：核对消息分页与 AgentConversation 窗口化的长历史 payload、prepend、会话切换和重复请求指标；
P1：以当前 HEAD 重新归档 fresh/upgrade/repeat/downgrade/备份恢复证据；
P1：使用显式生产配置重启并复验 DEBUG、默认管理员配置和基础 smoke；
P2：排除运行工件后形成发布提交，执行最终后端/前端全量门禁；
P2：更新发布门禁审计，重新评估 GO/NO-GO。
```

### H. 当前接续规则

- 继续在当前任务和当前工作区推进；
- 保留全部现有未提交源码、测试、文档和运行工件；
- 后续代码变更必须配套回归测试、反向验证、差异检查和可定位证据；
- 不把历史数字、缓存结果或旧发布报告数字冒充当前 HEAD 实测结果；
- 当前唯一待推进主线是“消息历史分页前端批次 → 真实 HTTP/JWT 验收 → 发布门禁闭环”。

## 2026-09-05 前端分页批次提交后续审查（当前任务继续）

### 当前已完成

- 已修复分页首屏失败、响应格式异常时的旧 `getSession()` 回退；旧 mock/兼容路径不会再因空分页响应丢失当前会话。
- 已通过前端相关定向回归：3 个测试文件、34 tests passed；生命周期测试现为 5 tests passed。
- 已通过前端全量回归：81 个测试文件、533 tests passed。
- 已通过 `npm run type-check`。
- 已通过 `npm run build-only`：4918 modules transformed。
- 已通过 `git diff --check`。
- 已形成提交：`5bc1612 feat: wire paged agent message history into workspace`。
- 后端消息/会话分页与 runtime 组合回归由子智能体完成：合计 183 passed；另有消息/会话专项 33 passed；静态编译通过。

### 当前验证后的真实状态

```text
HEAD：5bc1612
前端消息分页批次：已提交
工作区剩余 tracked 未提交：仅 TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
运行工件：.vite 与 backend/storage/**/*.bin 继续保留，不纳入发布提交
发布结论：仍为 NO-GO
```

### 新增审查发现

1. 会话详情接口默认仍可能读取完整消息数组与 Run 数组；新分页端点尚未成为所有大历史访问的唯一入口，长历史响应体仍有增长风险。
2. 真实 TCP/JWT 会话分页检查已验证登录、路由和现有会话分页返回 200，但现有 20 个会话消息总数均为 0，尚未形成数百条消息的长历史实证。
3. 真实成员验收脚本仍使用 ASGITransport；需要独立 TCP 客户端连接 127.0.0.1:8013 完成成员共享读取、projectless 隔离、连续游标翻页和无重复/无遗漏证明。
4. fresh/upgrade/repeat/downgrade 已有专项记录，但“备份 → 恢复 → hash/计数 → current → 服务健康 → 恢复后再次升级”证据包仍不完整。
5. 当前 `backend/.env` 仍是开发配置，启动日志的 DEBUG 与默认管理员配置警告尚未通过显式发布配置复验。

### 下一执行顺序（覆盖旧计划中的已完成项）

```text
P1：补真实 TCP/JWT 长历史消息分页验收脚本并运行，优先覆盖 180+ 消息、limit=60、before_sequence 连续翻页、无重复无遗漏；
P1：补真实 TCP 成员共享读取与 projectless 创建者边界验收；
P1：以当前 HEAD 重新归档迁移 fresh/upgrade/repeat/downgrade/备份恢复矩阵；
P1：显式注入发布配置重启服务，确认 DEBUG/默认管理员配置告警消失，再跑 smoke；
P2：补会话详情默认 payload 策略审查，决定保留兼容默认值还是改为元数据优先，并配套 HTTP/前端回归；
P2：最终后端全量、前端全量、构建、smoke、证据包检查，更新发布审计并重判 GO/NO-GO。
```

### 当前继续规则

- 本任务继续在当前 Codex task 和当前工作区执行，不回历史卡住会话，不创建新的 Codex task。
- 子智能体只承担分支明确、可验收的并行子任务；主任务负责审查、整合、测试、提交和发布结论。
- 子智能体若卡住，主任务立即催收、缩小任务、接手或关闭；不把未完成状态当作完成证据。
- 运行工件只保留，不批量清理；提交时按明确路径选择，不使用全量暂存。

## 2026-09-05 真实 TCP/JWT 长历史验收结果

### 验收脚本

新增：`backend/scripts/agent_tcp_message_pagination_acceptance.py`。脚本通过真实 TCP 连接 `http://127.0.0.1:8013` 完成 JWT 登录；通过当前服务配置数据库写入隔离 projectless fixture，再通过 TCP API 验证读取，结束后回收 fixture。密码只从环境变量读取，不写入输出。

### 实测结果

```text
TCP_MESSAGE_PAGINATION_PASSED
message_count=180
page_limit=60
pages=3
first_sequence=1
last_sequence=180
duplicate_count=0
compact_session_detail=200
JWT profile=200
```

覆盖：

- `/api/auth/login` JWT 登录；
- `/api/novels/current-user` 身份确认；
- `/api/agent/sessions` projectless 会话创建；
- `/api/agent/sessions/{id}?include_messages=false&include_runs=false` 紧凑详情；
- `/api/agent/sessions/{id}/messages?limit=60` 最新页；
- 连续 `before_sequence` 翻页；
- 180 条序列无重复、无遗漏；
- fixture 成功回收。

### 追加后端回归

- `app/api/routers/test_agent_session_pagination.py`：4 passed；新增真实 JWT 语义的 ASGI 成员长历史回归也通过。
- 迁移专项：`test_alembic_migrations.py`、`test_project_member_migration.py`、`test_deployment_contract.py`：16 passed。
- 当前服务 smoke：261 checks，55 passed，206 skipped，0 failed。

### 状态更新

真实 TCP/JWT 长历史消息分页主缺口已关闭。成员共享读取与 projectless 隔离已有 HTTP/ASGI 合同回归，但仍可继续增加真实 TCP 多用户 token 验收；迁移备份恢复、显式发布配置复验、会话详情默认 payload 策略仍是发布门禁剩余项。

## 2026-09-05 当前任务继续审查（提交与 smoke 后）

### 已推进到的最新节点

- 前端消息分页批次已提交：`5bc1612 feat: wire paged agent message history into workspace`。
- 消息 prepend 锚点、实时追加与分页失败重试边界已补强并提交：`c1ba52c fix: stabilize paged message prepend anchor`。
- 前端定向分页/会话/对话回归：17 tests passed。
- 前端全量回归：81 files / 533 tests passed。
- `npm run type-check`：通过。
- `npm run build-only`：通过，4918 modules transformed。
- 后端消息/会话分页与 runtime 组合回归：183 passed；消息/会话专项：33 passed；静态检查通过。
- 当前服务 smoke：261 checks，55 passed，206 skipped，0 failed；Backend、Frontend、Proxy health 均通过。

### 当前工作区与发布状态

```text
HEAD：c1ba52c
tracked 未提交：TASK_HANDOFF_NOVEL_QUALITY_CONTINUATION_20260904.md
未跟踪：.vite、backend/storage 下运行二进制、历史发布审计报告
git diff --check：通过
发布结论：NO-GO
```

### 当前审查结论

消息历史分页前端主线已完成实现、回归、构建和提交；下一阶段不再重复开发同一批次，转入真实 TCP/JWT 长历史数据验收与发布证据闭环。后端审查另发现：会话详情默认仍会读取完整消息与 Run，长历史场景仍保留 payload 增长风险；该项列为 P2 设计审查，不阻塞当前分页批次提交，但阻塞最终发布结论。

### 下一批唯一执行计划

```text
P1：完成独立 TCP/JWT 长历史验收脚本，验证 180+ 消息、limit=60 连续 before_sequence、无重复无遗漏、紧凑详情与成员边界；
P1：运行并保存当前服务 TCP 验收证据，若现有真实服务没有可用长历史数据，则通过隔离数据入口生成可回收 fixture；
P1：重新执行当前 HEAD 的迁移 fresh/upgrade/repeat/downgrade 与备份恢复矩阵，记录 Alembic current、计数/hash、恢复后健康检查；
P1：使用显式发布配置重启，复验 DEBUG、默认管理员配置告警消失，并再次跑 smoke；
P2：评估会话详情默认 payload 策略，必要时将默认读取改为元数据优先，配套后端/前端合同测试；
P2：最终全量门禁、发布审计更新、GO/NO-GO 重判。
```

### 证据边界

- `.vite/vitest/results.json` 旧缓存结果不作当前证据；
- 未跟踪 storage 二进制和日志保留，不批量清理，不加入代码提交；
- 历史发布报告中的旧 HEAD、旧失败项和旧文件统计不覆盖本节当前状态；
- 当前任务继续在本会话与当前工作区推进，不回历史卡住任务，不创建新的 Codex task。

## 2026-09-05 会话刷新 payload 优化

- 修复 `AgentWorkspace.refreshSessionMessages` 在终态刷新时重新读取完整消息数组的问题。
- 分页客户端存在时，刷新路径现在使用 `getSession(..., { includeMessages: false })` 加 `listSessionMessagesPage(limit=60)`；兼容旧 mock/旧客户端时继续走旧完整详情接口。
- 相关验证：`AgentWorkspace.spec.ts` 与 `useAgentSessionLifecycle.spec.ts` 共 35 tests passed；`npm run type-check` 通过；`git diff --check` 通过。
- 已提交：`f92885c perf: use paged messages during session refresh`。
- 当前最新代码头：`f92885c`。

### 当前待办重新排序

```text
P1：补真实 TCP 多用户 JWT 成员共享读取与 projectless 隔离验收；
P1：以当前头重新归档备份 → 恢复 → hash/计数 → Alembic current → 服务健康 → 再升级证据；
P1：显式发布配置重启并复验启动警告与 smoke；
P2：审查会话详情默认 include_messages/include_runs 策略，兼容性与长历史 payload 二选一后配套合同测试；
P2：最终全量门禁与发布审计更新，保持 GO/NO-GO 可追溯。
```

## 2026-09-05 显式生产配置复验结果

### 服务启动

通过进程级环境变量启动当前头服务，未修改 `backend/.env`：

```text
ENVIRONMENT=production
DEBUG=false
ADMIN_DEFAULT_PASSWORD=<独立临时发布夹具值>
```

启动结果：

```text
Backend ready=True
Frontend ready=True
Frontend proxy ready=True
```

当前运行日志目录：`logs/run-20260905-121940`。启动日志未出现 DEBUG 或默认管理员密码警告。

### 认证 TCP 分页复验

在生产认证语义下重新运行 `backend/scripts/agent_tcp_message_pagination_acceptance.py`：

```text
TCP_MESSAGE_PAGINATION_PASSED
message_count=180
page_limit=60
pages=3
first_sequence=1
last_sequence=180
duplicate_count=0
```

### smoke 结果与门禁发现

`verify.ps1 smoke` 的基础 health、前端、代理和 OpenAPI 路由检查通过（261 checks，51 passed，210 skipped，0 failed）；LLM settings 子检查因生产环境强制认证，而现有 smoke 请求未附带 Bearer token，出现 `401`，导致整个 smoke 套件退出码为 1。

该结果说明：生产认证语义已生效，但 `verify.ps1` 的 LLM settings smoke 尚未适配生产 Bearer 认证。下一步应给 smoke 检查增加可选的测试 JWT/登录凭据注入，或将“生产环境未认证请求返回 401”作为明确通过分支，同时保留 health 与 OpenAPI 合同检查。

当前发布结论仍为 `NO-GO`，原因从“启动配置警告”收敛为“发布 smoke 认证适配、备份恢复证据、详情 payload 策略与完整门禁尚未闭环”。
