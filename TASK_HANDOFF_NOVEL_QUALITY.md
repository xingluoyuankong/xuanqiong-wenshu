# 任务接续文档：小说生成质量优化（xuanqiong-wenshu）

> 生成时间：2026-08-17（末次更新 2026-08-19，批 8 + 收尾审查）
> 分支：`codex/final-continuity-20260520`（批 2-8 已提交并推送，见 `3e64060`）
> 后端全量门禁基线：**`727 passed, 36 failed in 86.14s`**（2026-08-19 实测，**唯一可信值**）。
> 命令**必须带四个 `-p no:` 开关**，见 §2.3——裸 `pytest app -q` 会假绿（D-26）。
> **历史值 659→661→668→679→688→691→718→742 以及 401/401、648 全部作废**：不是过期，
> 是由一个会静默吞测试的 runner 产出的（D-26）。36 个失败是先存欠账，非本轮引入（D-27）。
> 本文档所有数值、行号、判定结果均为本轮实机执行所得，非推测。推测部分会显式标注「未验证」。

---

## 0. 文档用途与阅读顺序

这份文档的作用是让任何一个新会话（或新的人）**在不读历史对话的情况下**，直接接手「让小说初稿生成质量达标」这件事。

建议阅读顺序：

1. 第 1 节 —— 30 秒了解现状与最重要的那个发现。
2. 第 2 节 —— 硬约束。**动手前必须读完**，尤其是 2.1（未提交成果）与 2.2（修复协议）。
3. 第 4 节 —— 本轮实证结论。这是所有判断的地面真相。
4. 第 5 节 —— 缺陷清单 D-01～D-22。
5. 第 6 / 7 节 —— 优化方案总表与逐条执行说明。**实际干活看这两节。**
6. 第 12 节 —— 立即动作。接手者从这一节的第一条开始做。

其余章节按需查阅。

---

## 1. 一句话现状

小说生成管线已有一套相当完整的「结构质量门」（11 类 blocker + 6 条软放行），但本轮实机探测确证了三件事：

1. **`backend/app/services/story_quality_scoring.py`（1525 行）是零引用的孤儿死代码**，与生产实现已漂移 7 处方法；生产路径用的是 `pipeline_orchestrator.py` 内联的另一份。**在孤儿文件上做的任何优化都不会影响生成的正文。**
2. **孤儿文件里恰好躺着几处已写好、但从未接线生效的质量判定改进**（章末压力的非标点强钩子、倒计时正则、叙事压力词表）。接线即生效，是当前性价比最高的一步。
3. **现有质量门存在可复现的漏判**：纯寒暄对话灌水的坏样本拿到 1039 分（好样本 1302 分）且 `event_density_passed=true`；章末压力门只要末尾有两个标点（`？` 和 `！`）即通过。

> **🔴 2026-08-19 最重要的一条（后于下面所有内容，优先读）**：本文档此前记录的**全部**
> 「全量 N passed / 全绿」结论都是假的——测试 runner 有插件冲突，会静默吞掉测试并返回
> 退出码 0（**D-26**，P0）。**唯一可信基线是 `727 passed, 36 failed`**，其中 36 个失败是
> 先于本轮存在的欠账（**D-27**）。接手第一件事是 **T-23 修 runner**，在那之前任何优化的
> 验收都不成立。详见文档末尾「2026-08-19 本轮的三项结论」。

> **第 1、3 条的状态已变**（2026-08-18，批 2-4 完成后）：第 3 条列的两个漏判**都已修复并被 `class TestBadSampleRegression` 锁住**（批 2 修章末压力、批 3 修事件密度、批 4 固化坏样本）。第 1 条的孤儿文件**还在**（T-19 排在批 10 最后）。**批 4 又暴露出一个同类问题：章末压力的 260 字尾窗会被正文钩子遮蔽（D-24），排进批 6。**

同时纠正一条前序会话的错误结论：**坏样本回归测试并非「完全缺失」**。它们存在于 `test_generation_quality_guards.py`（当时 2151 行，批 8 后 4438 行），且针对的是生产路径。前序把「孤儿文件没有专属测试文件」误读成「坏样本测试没落地」。真正的缺口是**特定坏样本类型未被覆盖**（详见 4.6 与 D-05）。

---

## 2. 硬约束（动手前必读）

### 2.1 保留未提交成果 —— 最高优先级

工作区有 **317 处未提交改动**（`git status --porcelain | wc -l` 实测）。这些是前序多轮优化的全部成果。

**禁止的操作：**

- `git reset --hard`、`git checkout -- <file>`、`git stash`（除非明确要求）
- `git clean -f/-fd`
- 批量覆盖写入（用 `Write` 覆盖一个未读过的已存在文件）
- 任何不可逆迁移（`alembic downgrade`、删表、重建库）
- 强推（`git push --force`）

**如果读取工具返回的内容看起来不对（重复行、行号跳跃、混入无关文件内容、出现「省略：…」这类伪造函数体），立刻停止编辑。** 基于污染内容做 `Edit` 会破坏这 317 处改动。详见 2.5。

### 2.2 修复协议（每一条代码修改都要走完）

1. **先写能证明缺陷的失败测试**，运行并确认它**失败**（红）。
2. 实现修复，确认该测试**通过**（绿）。
3. **临时故意破坏修复的关键条件**（例如把新加的阈值改回旧值），重跑，确认新测试**必然失败**——这一步是为了证明测试真的在守护这个行为，而不是恒真断言。
4. 恢复实现，重跑**定向测试**与**后端全量门禁**。
5. 记录：执行的命令、输出尾部（含 passed 计数）、新增断言、涉及文件。

### 2.3 门禁命令与基线

> **2026-08-19 重大改正：本节此前记录的全部全量数字（659 / 661 / 668 / 679 / 688 / 691 / 718 / 742）
> 都是不可信的。** 不是数字抄错，是**跑测试的命令本身会静默吞掉测试**：`pytest.ini` 的
> `asyncio_mode = auto` 与 `anyio` 插件抢同一批异步测试，进程不走栈展开直接死，输出缓冲区
> 整个丢失，而 `-q` 模式下 shell 拿到的退出码还是 0（假绿）。详见 D-26。
>
> **首个可信基线：`727 passed, 36 failed in 86.14s`（2026-08-19 实测）。**
> 36 个失败不是本轮改坏的，是一直存在、之前从没跑到过（被崩溃掩盖）。构成见 D-26 / D-27。

后端全量（**必须带这四个 `-p no:` 开关，缺一个就回到假绿**）：

```bash
cd "/d/小说写作/xuanqiong-wenshu/backend" && python -m pytest app -p no:randomly -p no:anyio -p no:seleniumbase -p no:sb_manager -q --timeout=120 --timeout-method=thread -rf
```

四个开关各自的理由，**不要因为「看起来冗余」就删**：

| 开关 | 不加会怎样 |
|---|---|
| `-p no:anyio` | 与 `asyncio_mode = auto` 冲突 → 进程猝死、输出丢失、假绿（D-26） |
| `-p no:seleniumbase` | seleniumbase 硬拦 `--timeout`，抛 `Don't use --timeout=s from pytest-timeout!` 直接退出 |
| `-p no:sb_manager` | 同上，seleniumbase 的第二个入口插件 |
| `-p no:randomly` | 随机顺序会让状态污染类失败漂移，无法复现定位 |

`--timeout=120 --timeout-method=thread` 是必需的：有测试会真的挂住（不是慢），没有单测超时
就只能靠外层 `timeout` 砍掉整个进程，拿不到「是哪一个挂的」。

后端定向（质量守卫，最常用）：

```bash
cd "/d/小说写作/xuanqiong-wenshu/backend" && .venv/Scripts/python.exe -m pytest -q app/services/test_generation_quality_guards.py
```

前端三件套：

```bash
cd "/d/小说写作/xuanqiong-wenshu/frontend" && npm run type-check && npm run test:run && npm run build-only
```

**任何修改后，后端全量必须 ≥ 727 passed，且失败数不得超过 36**（2026-08-19 实测基线）。
注意这条门禁的形态和以前不一样：**现阶段允许有失败**，因为那 36 个是先于本轮存在的欠账
（28 个 spec-first 未实现 + 8 个行为分歧，见 D-26 / D-27），不是本轮引入的。判断标准是
**失败集合不能变大、也不能换人**——跑完拿 `-rf` 的列表和 D-26 的清单逐条对，多一条就是回归。

提交信息里的测试数**必须是本次实测输出**，且必须写成 `N passed, M failed` 的完整形态，
不许只写 passed 数。历史提交写的 `— 401/401`、以及本文档此前的 `742 passed`，都是假绿产物
（D-18 / D-26）。

**批 4 之后多了一道更快的护栏**：改任何质量门之前先跑 `-k "BadSampleRegression"`（9 条，约 3-13s），它比全量快一个数量级，且专门守着「坏样本必须被拦、正向对照不能被误杀」两个方向。全绿再跑全量。

**另外**：凡是改动质量门阈值的任务（T-06 已做、T-16 待做），门禁全绿**不等于**改对了。批 3 的第一版阈值定向与全量全绿，但在真实语料上误杀 95%。**阈值类改动必须额外跑一次真实语料校准**（做法见批 3 实际落地记录）。

### 2.4 成本与并发约束

- **禁止再开 Workflow 编排、禁止大批并发子智能体。** 前序一次 97 节点审计消耗 3,879,503 subagent tokens / 12,876 秒，产出为零，且触发多个 `403 pre-consume quota failed`（额度不足）。用户已明确表达不满（并发过高导致机器卡顿）。
- 允许并行的只有**普通工具调用**（多个 `Read`/`Grep`/`Bash` 放在同一条消息里），这不算并发智能体。
- 工作方式：**直接执行 + 小范围定向读写**。需要理解运行时行为时，写临时探针脚本直接跑，比读几千行源码更省更准。

### 2.5 环境已知问题

**问题 1：大段文本读取管道间歇性污染。**

症状（前序实际遇到过）：`Read`/`Grep`/`Bash` 输出大段文本时，可能出现伪造的函数体桩（如「省略：具体标记统计」）、行号重复或跳跃（637 重复出现、677 直接跳到 637）、混入完全无关的旧文件内容、`grep` 结果尾部漏进 XML 标签片段。

诊断结论：**底层 Python / pytest / 文件系统是好的**（pytest 计数、`Glob`、exit code、`wc -l`、小范围结构化输出都可信），抖动只发生在大段文本渲染上。

应对（本轮已验证有效）：

- 单次 `Read` 控制在 **150 行以内**，并检查行号是否连续。
- 用 `grep -n` 拿锚点行号，再定点小范围 `Read`，不要整文件读 8000 行。
- **优先「执行观察」而非「阅读推断」**：写临时 Python 探针直接调用目标函数打印结果（本轮所有关键结论都是这么拿到的）。
- 输出量大时先重定向到文件、`wc -l` 确认规模再读。
- **发现污染迹象就绝不做 Edit。**

**问题 2：Windows 控制台 GBK 乱码。**

`python xxx.py` 打印中文时会变成 `�������`。本轮 `_probe_bypass.py` 就中招了（结论仍可读，因为布尔值和 ASCII 字段名没坏）。

解决：

```bash
cd "/d/小说写作/xuanqiong-wenshu/backend" && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe _probe.py
```

或在脚本里只打印 ASCII 字段名 + `json.dumps(..., ensure_ascii=True)`。

**问题 3：`&&` 链会被中间命令的非零退出码打断。**

例如 `wc -l fileA fileB && grep ...`，若 `fileB` 不存在，`wc` 返回非零，后面的 `grep` 不会执行，容易误判成「grep 没有结果」。

解决：用 `;` 分隔并显式打印退出码：

```bash
cmd1 2>&1; echo "===EXIT $?==="; cmd2 2>&1
```

### 2.6 语言与脱敏

- 全部输出、注释、提交信息、任务标题用**简体中文**。
- 保持原文不译：代码标识符、文件路径、命令、参数、报错原文、API 字段名、配置 key。
- 证据里**不要**记录密钥、JWT、完整 Prompt 正文、用户小说正文、Provider 私密配置。

---

## 3. 架构速查

### 3.1 生成管线（`PipelineOrchestrator.generate_chapter`）

核心流程（简化，按执行顺序）：

1. **多候选初稿生成**（`run_writer_pass` ~6337 闭包，调用 `LLMService.stream_generate`）
   - 首稿若命中坏模式（静态描写 + 字数短 + 对话少）触发**定向重试**（~6456-6531，本轮实证该闭环已存在）
   - 连续三次失败降级到 `stable_model`
   - `stable` 连续失败触发 `partial` 抢救
2. **多轮续写**（字数不足时）
3. **AI review**（语义场景评判，可能覆盖字面规则的 false negative）
4. **self_critique**（结构自检，返回 final_score / critical_count / major_count）
5. **reader_sim / reader_polish**（模拟读者反馈，低 continue_ratio 触发改写）
6. **consistency**（一致性校验 + repair）
7. **结构质量门**（~640-891，`_build_structural_quality_gate_result`）← **这是当前生产路径的质量判定核心**
   - 11 类 blocker：
     - `self_critique`: critical > 1 / score < 42 / major ≥ 12
     - `consistency`: critical 未解决 / major ≥ 5 未解决
     - `story_progression_guard`: static_description_risk / chapter_artifact_markers / insufficient_dialogue_pressure / dialogue_does_not_change_state / ending_pressure_missing / chapter_progression_weak / scene_fulfillment_weak / scene_structure_weak / event_density_weak / state_change_interval_weak / long_chapter_event_density_weak
   - 6 条软放行路径（~698-871，`progression_soft_pass`(727) / `scene_soft_pass`(752) / `semantic_scene_soft_pass`(770) / `dense_scene_soft_pass`(781) / `density_soft_pass`(840) / `rich_progression_evidence`(698)）
8. **blocker persist**（若有 blocker 则不落库，触发下一步修复；否则跳到 12）
9. **结构质量门定向修复**（**批 5 后 2054-2241**，`_attempt_structural_gate_repair`）← 前序 Task#4 建成，**批 5（T-22）已增强**
   - 根据 blocker 类型动态拼接修复 prompt
   - 重跑 consistency + self_critique
   - 再次质量门判定，**最多 2 轮**（`STRUCTURAL_GATE_REPAIR_MAX_ROUNDS`），按严格子集收缩采纳部分改善
   - 无论采纳与否都返回 `repair_summary` 诊断，写进 `runtime_metadata["quality_gate_repairs"]`（3878 / 4104）
10. **enrichment**（~8322-8381，远低于目标字数时追加内容，**仅限行动/对话/后果/短接续决策**，不加空洞描写）
11. **enrichment 后再过一次质量门**（~8375，`_build_structural_quality_gate_result` 第二次调用，分数重算）
12. **最终守卫**（`_should_skip_final_persist` ~924）
13. **连续性门**（多章连贯性）
14. **落库 / 推送 SSE**

### 3.2 质量评分的两份实现（本轮关键发现）

#### 实现 A：孤儿文件 `backend/app/services/story_quality_scoring.py`（1525 行）

- 状态：**零引用死代码**。`git grep "from.*story_quality_scoring\|import.*StoryQualityScoringMixin"` 全库无匹配。
- 特征：独立文件，28 个方法，包含一些**已写好但从未生效的改进**（见 4.3）。
- 没有专属测试文件（`test_story_quality_scoring.py` 不存在）。

#### 实现 B：生产路径 `pipeline_orchestrator.py` 内联实现（8459+ 行）

- 位置：`_evaluate_ending_pressure`(769)、`_count_dialogue_state_change_markers`(719)、`_evaluate_dialogue_changes_state`(746)、`_evaluate_event_density`(649)、`_story_units`(627)、`_unit_has_progression`(641)、以及 `_build_structural_quality_gate_result`(640-891) 调用这些。
- 特征：直接在编排器类里实现，与生成流程紧耦合。
- 测试：`test_generation_quality_guards.py`（**批 8 后 4438 行 / 188 收集（167 passed, 21 failed）**；下文凡出现「2151 行 / 56 个测试」的都是批 1 之前的原始快照，保留以说明当时的判断依据）。

#### 两者漂移矩阵（本轮用 `inspect.getsource` + 去空白 SHA256 实测）

| 方法 | 生产路径 B | 孤儿 A | 判定 |
|-----|-----------|-------|------|
| `_story_units` | 13 行 | 13 行 | 一致 |
| `_unit_has_progression` | 7 行 | 7 行 | 一致 |
| `_evaluate_event_density` | 69 行 | 69 行 | 一致 |
| `_estimate_static_description_runs` | 16 行 | 16 行 | 一致 |
| `_evaluate_scene_fulfillment` | 88 行 | 88 行 | 一致 |
| `_chapter_mission_expects_dialogue` | 11 行 | 11 行 | 一致 |
| `_count_dialogue_state_change_markers` | 15 行 | **26 行** | **漂移** |
| `_evaluate_dialogue_changes_state` | 10 行 | **22 行** | **漂移** |
| `_evaluate_ending_pressure` | 57 行 | **123 行** | **漂移** |
| `_score_fallback_candidate` | 52 行 | 43 行 | **漂移** |
| `_detect_chapter_artifact_markers` | 36 行 | **56 行** | **漂移** |
| `_score_story_quality_candidate` | 124 行 | **173 行** | **漂移** |
| `_build_quality_issue_summary` | 78 行 | **112 行** | **漂移** |
| `_fallback_select_best_version` | 31 行 | 31 行 | **漂移**（同长度不同内容）|
| `_evaluate_repetition_risk` | **不存在** | 32 行 | 生产缺失 |
| `_collect_focus_character_names` | **不存在** | 39 行 | 生产缺失 |
| `_apply_deterministic_cleanup` | **不存在** | 87 行 | 生产缺失 |
| `_sanitize_markdown_presentation` | **不存在** | 46 行 | 生产缺失 |
| `_remove_exact_repeated_paragraphs(_with_floor)` | **不存在** | 23+63 行 | 生产缺失 |

`PipelineOrchestrator.__mro__` 实测为 `['PipelineOrchestrator', 'object']` —— **孤儿 mixin 不在继承链上**。

生产缺失的 5 项经 `grep -rn "def <name>" app/` 复核，**全库唯一定义都在孤儿文件里**，生产路径没有任何等价命名的实现。也就是说主生成路径当前**不具备**：

- 正文重复段落风险判定（`repetition_risk`）
- 「该出场的焦点角色没出场」判罚（`focus_character_hits`）
- 确定性清理与精确重复段落移除
- Markdown 呈现痕迹清理（`**加粗**`、`#` 标题残留在小说正文里）

唯一相关的旁路：`longform_generation_service.py:494` 会 append 一条 `chapter_repetition_risk` **warning**（不是 blocker，且只在长篇分段路径生效）。

**结论：修改孤儿文件 A 不影响生成的正文。所有优化必须落在 `pipeline_orchestrator.py`（B）。**

### 3.3 前端质量展示（已实现）

- **工具模块**：`frontend/src/utils/chapterQuality.ts`（109 行）+ 测试 `chapterQuality.spec.ts`（92 行）
  - `resolveChapterQualityMetrics`：解析后端返回的 quality_summary
  - `buildChapterQualitySummary`：构建前端展示的摘要卡片数据
- **展示位置**（实际使用 `grep` 确认）：
  - `WDSidebar.vue` —— 侧边栏质量摘要面板
  - `WDWorkspace.vue` —— 主工作区顶部质量状态条
  - `VersionSelector.vue` —— 版本选择器里的质量对比卡片
- **数据流**：后端 API 返回的 `chapter.metadata.quality_summary` / `version.quality_summary` → 前端工具函数解析 → Vue 组件渲染

前端展示**已到位**，是前序优化成果之一。新增后端质量指标会自动流向前端（只要后端在 `quality_summary` 里返回）。

### 3.4 模块提取标记（管线内部注释）

`pipeline_orchestrator.py` 里存在 3 处 `# ====== EXTRACTABLE: <name>.py` 边界注释（前序留的重构线索，本轮未执行提取）。**注意注释里写的 L 值与注释自身所在行号不一致**（注释写于文件更早版本，之后文件增长过），以实际行号为准：

| 注释所在行 | 目标模块 | 注释里写的区间 | 实际覆盖 |
|-----------|---------|--------------|---------|
| 397 | `_pipeline_quality_gate.py` | L381-L940 | 397 → 905（END 注释在 905）|
| 7165 | `_pipeline_story_scoring.py` | L5881-L6281 | 7165 → 7572 |
| 7795 | `_pipeline_self_critique.py` | L6506-L6782 | 7795 → 8075 |

这些标记**只是重构意图**，实际代码全在 `pipeline_orchestrator.py` 一个文件（8482 行）里。**提取动作非本任务优先级，暂不执行**——它会大面积改动 317 处未提交改动所在的文件，且不直接改善生成质量。

---

## 4. 本轮实证结论（全部可复现）

### 4.1 全量门禁基线

命令见 2.3（**必须带四个 `-p no:` 开关**）。

**首个可信基线：`727 passed, 36 failed in 86.14s`（2026-08-19 实测，exit code 1）。**

历史数字**全部作废，且作废的理由不是「过期」而是「测量工具坏了」**——它们由一个会静默
吞测试的 runner 产出，既不是当时的真实值，也无法通过重跑复原：

| 来源 | 数字 | 状态 |
|---|---|---|
| 提交信息 `32eafd3` / `57e7e1c` / `f869ec3` 等 | `401/401` | **假绿**（D-26） |
| 前序会话记录 | `648 passed in 51.41s` | **假绿** |
| 本轮（改动前）实测 | `659 passed in 83.58s` | **假绿** |
| 批 1 / 批 2 / 批 3 / 批 4 实测 | `661` / `668` / `679` / `688` | **假绿** |
| 批 5 实测 | `691 passed in 61.34s` | **假绿** |
| 批 6 实测 | `718 passed in 55.80s` | **假绿** |
| 批 7 实测 | `742 passed in 62.50s` | **假绿** |
| **2026-08-19 修正 runner 后实测** | **`727 passed, 36 failed in 86.14s`** | **唯一有效** |

为什么 727 比作废的 742 还少：那 742 里包含了被 anyio 冲突「跳过而计为通过」的测试，
以及崩溃前已计数的部分；727 是在**全部测试真的被执行**的前提下数出来的。两个数字不可比。

**这件事对本文档全部「已修复 ✅」标记的影响**：批 2-8 的定向测试（`test_generation_quality_guards.py`
单文件、`-k BadSampleRegression`）**不受影响**——它们是同步测试，不碰 anyio，实测
`167 passed, 21 failed` 可信。受影响的只有「全量全绿」这一类整体性结论。也就是说：
**各批改对了没有，仍然有定向证据支撑；但「没有破坏别处」这个结论，此前从未被真正验证过。**

`CLAUDE.md` 的 `Latest Progress` **现在也写了基线数字**（原先没写，是批 3 加进去的），所以每批完成后**要同时更新三处**：本文档 6.3 执行状态、本文档第 12 节当前进度、`CLAUDE.md`。详见 D-18。

### 4.2 孤儿死代码确证

```bash
grep -rn "story_quality_scoring\|StoryQualityScoringMixin" --include=*.py app/
```

只有两条匹配，都在孤儿文件自身：第 1 行的 `# AIMETA` 注释、第 15 行的 `class StoryQualityScoringMixin:`。**没有任何 import**。

`PipelineOrchestrator.__mro__` == `['PipelineOrchestrator', 'object']`。

Git 历史侧证：

```bash
git log --oneline -- backend/app/services/story_quality_scoring.py
# a9ccceb feat: research service + story quality scoring + project ledger lease   ← 唯一一次提交
```

而 `pipeline_orchestrator.py` 此后有多次针对质量门的独立提交（`9f26cb4 fix: ending_pressure_missing blocker添加self_critique score>=75豁免`、`1436f0b fix: event_density_weak blocker添加self_critique score>=70豁免` 等）。

**判定：孤儿文件是一次「提取到独立模块」的尝试，提取后从未接线、从未维护，生产侧继续独立演进。**

### 4.3 生产评分模型完整还原（`_score_story_quality_candidate`，7454-7578）

中间量（7464-7490）：

```python
condensed = "".join(text.split())          # 去掉全部空白
word_count = len(condensed)                 # 非空白字符数，中文 1 字 = 1
paragraphs = [s for s in text.splitlines() if s.strip()]
paragraph_count = len(paragraphs)           # 非空行数
dialogue_markers = sum(text.count(m) for m in ("“","”","「","」","『","』",'"'))
```

评分权重（7492-7506，**生产版实际代码**）：

```python
score = 0
score += len(mission_hits) * 180                                    # 任务书关键词命中
score += min(paragraph_count, 12) * 18                              # 上限 +216
score += min(dialogue_markers, 10) * 12                             # 上限 +120
score += int(scene_rate * 280) if scene_count else 80               # 无 scene_list 时白给 +80
score += int(scene_structure_rate * 140) if scene_count else 40     # 无 scene_list 时白给 +40
score += 140 if dialogue_changes_state else -140                    # ±140
score += 140 if ending_hook else -120                               # +140 / -120
score += min(progression_unit_count, 18) * 16                       # 上限 +288
score += 80 if event_density_passed else -180
score += 60 if state_change_interval_passed else -130
score += 90 if long_chapter_density_passed else -180
score += min(word_count, 2400) // 50                                # 上限 +48
score -= len(violations) * 500
score -= 260 if static_description_risk else 0
```

**生产版相比孤儿版缺少的 5 项判罚**（这解释了两版分差）：

| 缺失判罚 | 孤儿版权重 | 后果 |
|---------|-----------|------|
| `repetition_risk` | −420 | **重复段落灌水不扣分** |
| `focus_character` 未出场 | −240 | 该出场的角色缺席不扣分 |
| `word_count_below_min` | −620 | 字数低于下限在评分层不扣分 |
| `word_count_far_above_target` | −520 | 严重超长不扣分 |
| `word_count_far_below_target` | −180 | 严重不足不扣分 |

`static_description_risk` 生产版判定（7483-7487，**只有 3 条分支，且阈值比孤儿版松**）：

```python
static_description_risk = bool(
    (dialogue_markers == 0 and paragraph_count <= 4 and word_count >= 1800)   # 孤儿版: >=1200
    or (word_count >= 1500 and max_static_run >= 3)                            # 孤儿版: >=1200 且 >=2
    or (word_count >= 2500 and event_density_passed is False and max_static_run >= 2)  # 孤儿版: >=2000
)
# 孤儿版独有的第 4 条分支（生产缺失）：
#   word_count >= 1600 and dialogue_markers > 0 and max_static_run >= 2 and static_paragraph_count >= 3
#   —— 即「有对话但夹着多段大段静态描写」在生产路径不判罚
```

### 4.4 四样本判定快照（生产路径 vs 孤儿）

探针脚本：`backend/_probe_quality.py`（临时文件，用完删）。参数统一 `target_word_count=3000, min_word_count=2000, chapter_mission=None, violations=[]`。样本用序数前缀扩写，避免整段精确重复。

| 样本 | 字数 | 段数 | 引号数 | score(生产) | score(孤儿) | static_risk | dialogue_changes_state | ending_pressure | event_density |
|-----|-----|-----|-------|-----------|-----------|------------|----------------------|----------------|--------------|
| `BAD_ALL_DESCRIPTION`（纯静态描写，零对话，单段）| 2313 | 1 | 0 | **−276** | −456 | ✅ true | ❌ **true** | ✅ false | ✅ false |
| `BAD_FLAT_CHATTER`（纯寒暄对话，局势零变化）| 2270 | 100 | 220 | **1039** | 439 | ❌ **false** | ❌ **true** | ✅ false | ❌ **true** |
| `BAD_MUNDANE_SEQUENCE`（流水账日常动作）| 2399 | 110 | 0 | **549** | 369 | ❌ **false** | ❌ **true** | ✅ false | ✅ false |
| `GOOD_DRAMATIC`（动作+对话改变局势+反转+结尾钩）| 2408 | 80 | 112 | **1302** | 702 | ✅ false | ✅ true | ✅ **true** | ✅ true |

（✅ = 判对，❌ = 判错）

生产路径 `quality_issue_codes`：

- `BAD_ALL_DESCRIPTION` → `["static_description_risk", "chapter_progression_weak", "ending_pressure_missing", "event_density_weak"]`
- `BAD_FLAT_CHATTER` → `["chapter_progression_weak", "ending_pressure_missing"]`
- `BAD_MUNDANE_SEQUENCE` → `["chapter_progression_weak", "ending_pressure_missing", "event_density_weak"]`
- `GOOD_DRAMATIC` → `[]`

### 4.5 逐项验算：坏样本为什么能拿高分

手工按 4.3 权重表复算 `BAD_FLAT_CHATTER`（纯寒暄坏样本）与 `GOOD_DRAMATIC`（好样本），**与探针输出完全吻合**（验证了权重表还原正确）：

| 加分项 | BAD_FLAT_CHATTER | GOOD_DRAMATIC | 差 |
|-------|-----------------|---------------|---|
| `paragraph_count` (min 12 × 18) | +216 | +216 | 0 |
| `dialogue_markers` (min 10 × 12) | +120 | +120 | 0 |
| 无 scene_list 白给 | +120 | +120 | 0 |
| `dialogue_changes_state` | +140 | +140 | 0 |
| **`ending_hook`** | **−120** | **+140** | **260** |
| `progression_unit_count` (min 18 × 16) | +288 | +288 | 0 |
| `event_density_passed` | +80 | +80 | 0 |
| `state_change_interval_passed` | +60 | +60 | 0 |
| `long_chapter_density_passed` | +90 | +90 | 0 |
| `word_count // 50` | +45 | +48 | 3 |
| **合计** | **1039** | **1302** | **263** |

**这是整份文档最重要的一张表。** 它证明：

1. 纯寒暄灌水与真正有戏的正文，**分差只有 20%，且全部来自 `ending_pressure` 单一维度**；其余 11 项加分**完全相同**。
2. `paragraph_count` + `dialogue_markers` + `progression_unit_count` 三项共 **624 分**（好样本总分的 48%），**只奖励「分段多、引号多、句子多」，与内容质量无关** —— 机械灌水即可拿满。
3. 在多候选选择场景下，一个「对话灌水但结尾随手加个问号」的候选（1039 + 260 = 1299 分）**与真正好的候选（1302）几乎并列**，完全可能被选中推给用户。

### 4.6 章末压力门三缺陷确证

探针 `backend/_probe_bypass.py`，直接调 `PipelineOrchestrator._evaluate_ending_pressure(condensed, None)`：

| 输入结尾 | 期望 | 实际 | 命中 |
|---------|-----|------|-----|
| 「…觉得这一天过得很舒服。真的很舒服吗？当然很舒服！」| 不通过 | **通过** ❌ | `['？', '！']` |
| 「…觉得这一天过得很舒服，非常舒服，也很安稳。」| 不通过 | 不通过 ✅ | `[]` |
| 「…追兵已经堵住了退路，玻璃在身后炸裂，而幕后是谁，**一切都**还是未知。」| 通过 | **不通过** ❌ | closure=`['一切都']` |
| 「…追兵已经堵住了退路，玻璃在身后炸裂，而幕后是谁，仍旧无人知道。」| 通过 | **不通过** ❌ | `['退路']` 仅 1 个 |
| 「…日子就这样过去了，平平淡淡才是真，明天也会一样。」| 不通过 | 不通过 ✅ | `[]` |

对应生产代码（7313-7338）：

```python
hook_markers = ("却","突然","忽然","门外","脚步","消息","期限","代价","危险",
                "线索","证据","下一刻","来不及","问题","？","?","！","!")   # ← 标点混在钩子里
closure_markers = ("终于结束","告一段落","松了口气","一切都","暂时平静","圆满","尘埃落定")
# ↑ "一切都" 过宽，会误杀 "一切都还是未知" / "一切都失控了" 这类真钩子
passed = bool((deliver_hits or len(hook_hits) >= 2 or mission_hook_pass) and not closure_hits)
# ↑ 两个标点即满足 len(hook_hits) >= 2
```

三个缺陷：

- **E1（漏判）**：`？` `！` `?` `!` 四个标点被当作钩子标记，**任意两个标点即通过章末压力门**，正文内容可以是「这一天过得很舒服」。
- **E2（误杀）**：`closure_markers` 含 `"一切都"`，一旦真钩子里出现「一切都还是未知」「一切都失控了」，`not closure_hits` 直接为假，**无论有多少真压力信号都判不通过**。
- **E3（识别不足）**：`hook_markers` 缺少大量常见强压力词（追兵、堵住、炸裂、逼近、锁死、倒计时…），真钩子往往只命中 1 个词就达不到 `>= 2`。

**孤儿文件里恰好有 E1 与 E3 的修复，但从未接线**（`_evaluate_ending_pressure` 孤儿版 123 行 vs 生产版 57 行）：

```python
# 孤儿版 867-878：把标点排除出「强钩子」计数
strong_non_punct_hooks = [h for h in hook_hits if h not in {"？", "?", "！", "!"}]
narrative_pressure_markers = ("最多","半天","药效","假药",...,"追兵","倒计时","会死","门半开")
deadline_patterns = (r"最多.{0,6}(半天|一天|一晚|一夜|三天|一时|一刻|一炷香)", ...)
pressure_score = (2 if soft_deliver else 0) + (2 if mission_hook_hits else 0) \
    + min(3, len(strong_non_punct_hooks)) + min(3, len(narrative_hits)) + (2 if deadline_hits else 0)
passed = bool(not closure_hits and (soft_deliver or len(strong_non_punct_hooks) >= 2
    or mission_hook_pass or len(narrative_hits) >= 2
    or (deadline_hits and (...)) or pressure_score >= 3))
```

**但孤儿版也没修 E2**（`closure_markers` 里同样有 `"一切都"`），且孤儿版引入了新问题（见 D-06 过拟合）。

### 4.7 事件密度门的三个失效点

生产代码 `_evaluate_event_density`（**批 5 后 7439 起**；原文写的 7192-7260 是批 3 之前的行号，且当时与孤儿版完全一致——批 3 已把生产版改开，两者不再等同）：

```python
if word_count < 800:                      # ← 失效点 1
    return {"event_density_passed": True, "progression_unit_count": 0, ...}   # 无条件放行

def _unit_has_progression(unit):
    if any(mark in unit for mark in ("“","”","「","」","『","』",'"')):
        return True                        # ← 失效点 2：任何带引号的句子都算「有推进」
    return any(marker in unit for marker in STORY_PROGRESSION_MARKERS)

density_floor  = 1.0  if word_count < 2500 else 1.25 if word_count < 7000 else 1.45
unit_rate_floor= 0.16 if word_count < 2500 else 0.2  if word_count < 7000 else 0.22
# ← 失效点 3：实测 density_per_1000 达 83.7，阈值只要 1.0，差 80 倍
```

- **失效点 1**：短于 800 非空白字符的文本无条件放行事件密度门。短章、片段续写完全不受约束。
- **失效点 2**：`_unit_has_progression` 把「任何含引号的句子」判为有推进。于是纯寒暄对话的每一句都算推进 → `BAD_FLAT_CHATTER` 实测 `progression_unit_count=190`、`event_density_per_1000=83.7`。**引号 ≠ 局势推进**，这是本轮最严重的单点漏判。
- **失效点 3**：阈值 `density_floor=1.0~1.45` 与实际量级（几十）差 1～2 个数量级，这个门实际上**永远通过**，除非文本一句对话都没有且不含任何推进词。

### 4.8 `dialogue_changes_state` 在无任务书时形同虚设

生产代码 `_evaluate_dialogue_changes_state`（**批 5 后 7531 起**）：

```python
marker_count = cls._count_dialogue_state_change_markers(text)
if not expected_dialogue:
    passed = True                          # ← 无条件通过
elif dialogue_markers >= 2 and marker_count >= 2:
    passed = True
else:
    passed = False
```

`expected_dialogue` 来自 `_chapter_mission_expects_dialogue(chapter_mission)`。当 `chapter_mission` 为 `None` 或没有对话期望时，**该维度无条件返回 `True`，白给 +140 分**。

实测：4 个样本（包括**零对话标记**的 `BAD_ALL_DESCRIPTION` 和 `BAD_MUNDANE_SEQUENCE`）**全部** `dialogue_changes_state=true`。

一个零对话的纯描写文本被判定为「对话改变了局势」，语义上是荒谬的。而且质量门的 6 条软放行里有 4 条把 `dialogue_changes_state` 当作正向证据（`story_guard.get("dialogue_changes_state", True)`），**这个恒真值会连带激活软放行，绕过其它 blocker**。

### 4.9 静态描写检测的逃逸路径

`_estimate_static_description_runs`（7347-7362）：

```python
action_markers = ("说","问","答","走","退","伸手","抬头","看","盯","推","抓","按","转身","决定","发现","却","但")
is_static = len(plain) >= 100 and not any(marker in plain for marker in action_markers)
```

两个问题：

1. **段落长度门槛 100 字**：流水账式短段（每段 20～40 字）永远不算 static。实测 `BAD_MUNDANE_SEQUENCE`（110 段流水账、零对话、零冲突）`static_description_risk=false`。
2. **`action_markers` 含「看」「却」「但」「说」等超高频字**：任何一段静态景物描写只要出现一次「看」或「但」，就不算静态。中文写景几乎必然出现「看」。

结果：`static_description_risk` 实际只能抓住「零对话 + 段数 ≤4 + 字数 ≥1800」这一种极端形态（实测 `BAD_ALL_DESCRIPTION` 命中的正是这条）。**真实生成中更常见的「多段景物描写 + 偶尔一句对话」完全逃逸。**

### 4.10 质量门的软放行与自评豁免

`_build_structural_quality_gate`（616 起，blocker 主体 640-891）共 11 类 blocker、6 条软放行。软放行的共同核心条件：

```python
progression_soft_pass = (
    story_dialogue_markers >= 8                                  # 引号 ≥ 8（4 组）
    and not static_description_risk
    and dialogue_changes_state                                    # ← 4.8 证明无任务书时恒真
    and ending_pressure_passed                                    # ← 4.6 证明两个标点即可
    and critique_critical <= 1
    and (critique_score is None or critique_score >= 70)
    and len(critical_consistency) == 0 and len(major_consistency) < 2
)
```

`density_soft_pass`、`dense_scene_soft_pass`、`scene_soft_pass`、`semantic_scene_soft_pass`、`rich_progression_evidence` 结构类似，都依赖 `dialogue_markers >= 8` + `dialogue_changes_state` + `ending_pressure_passed`。

**组合起来构成一条完整的绕过链**：

> 堆够 4 组引号（`dialogue_markers >= 8`）→ 无任务书时 `dialogue_changes_state` 恒真 → 结尾随手写「真的吗？太好了！」使 `ending_pressure_passed` 为真 → 同时满足多条软放行 → 绕过 `event_density_weak`、`chapter_progression_weak`、`scene_fulfillment_weak`、`state_change_interval_weak` 等 blocker。

此外，两条 blocker 有**自评豁免**（来自 `git log` 的 `9f26cb4`、`1436f0b` 两次提交）：

```python
# ending_pressure_missing（829-839）
and (critique_score is None or critique_score < 75)     # self_critique 给 ≥75 分即免罚
# event_density_weak（847-857）
and (critique_score is None or critique_score < 70)     # self_critique 给 ≥70 分即免罚
```

`critique_score` 是 LLM 自检给自己打的分。**LLM 给自己打 75 分就能让「章末无压力」免罚** —— 自评闭环漏洞。当初加这两条豁免是为了减少误杀（真实运行中被误判 blocked），但代价是把把关权交给了被检查者本身。

### 4.11 前序结论纠正：坏样本回归测试并非缺失

前序会话的任务定义是「`test_story_quality_scoring.py` 不存在 → 坏样本回归测试尚未落地」。**这个判断是错的。**

实测 `test_generation_quality_guards.py`（当时 2151 行）已有 56 个测试，其中直接覆盖坏样本的至少包括（**下表行号是批 1 之前的快照，现已全部位移；批 8 后该文件 4438 行 / 188 收集，见附录 A.2**）：

| 行号 | 测试名 | 覆盖的坏样本类型 |
|-----|-------|---------------|
| 1387 | `test_story_quality_metrics_reject_all_description_sample` | 全描写 |
| 1464 | `test_story_quality_metrics_reject_keyword_padded_low_event_density` | 关键词灌水 + 低事件密度 |
| 483 | `test_first_draft_retry_triggers_for_static_short_dialogue_light_copy` | 静态 + 短 + 少对话 |
| 689 | `test_structural_quality_gate_blocks_static_description_and_weak_progression` | 静态描写 + 弱推进 |
| 658 | `test_structural_quality_gate_blocks_catastrophic_self_critique_and_consistency_failures` | 自检/一致性灾难 |
| 1511 | `test_first_draft_retry_triggers_for_long_chapter_low_event_density` | 长章低密度 |
| 1408 | `test_story_quality_metrics_reward_scene_dialogue_and_ending_pressure` | 好样本对照（防误杀）|
| 1550 | `test_story_quality_metrics_accept_dense_scene_sequel_progression` | 好样本对照 |
| 1495 | `test_event_density_allows_dense_progression_despite_local_plain_run` | 好样本对照 |
| 1432 | `test_dialogue_state_guard_recognizes_concrete_revelation_choice_and_external_pressure` | 对话状态变化正例 |
| 1455 / 888 / 1671 / 1736 | `test_ending_pressure_*` 四个 | 章末压力正例 |

**真正的缺口是特定坏样本类型没被覆盖**（见 D-05），而不是「没有坏样本测试」。这个纠正很重要：接手者不要再去新建 `test_story_quality_scoring.py`（那会给孤儿死代码写测试，对生成正文零影响）。

> **批 4 后续**（2026-08-18）：D-05 表里已实现能力对应的缺口全部补齐——`class TestBadSampleRegression` 9 条测试进了同一个文件（现 113 passed）。**上表行号已因批 2/3/4 的插入整体下移，别照抄，用 `grep -n "def test_"` 重新定位。** 剩下的 D-05-c/f/g 三项要等 T-13/T-10/T-17 把生产能力做出来才有断言对象。

---

## 5. 缺陷清单

优先级定义：**P0** = 直接导致坏正文被放行给用户，且修复成本低；**P1** = 显著影响判定准确度；**P2** = 能力缺失或稳健性问题；**P3** = 文档/整洁度。

### D-01（P0）孤儿死代码 1525 行，与生产漂移

- **现象**：`story_quality_scoring.py` 零引用，与生产实现漂移 7 处方法、生产缺失 5 处能力。
- **证据**：4.2、3.2 漂移矩阵。`__mro__` 不含 mixin；`grep` 无 import；git 仅 1 次提交。
- **影响**：任何在该文件上做的优化不生效；两份评分逻辑并行维护，后续修改极易改错文件；1525 行死代码干扰阅读与搜索（`grep _evaluate_ending_pressure` 会返回两处，容易改错）。
- **修复方案（三选一，推荐 B）**：
  - A. 让 `PipelineOrchestrator` 继承 `StoryQualityScoringMixin`，删掉内联实现。**风险高**：孤儿版有过拟合词表（D-06）和不同阈值，切换会改变现有 56 个测试的判定结果，可能大面积红。
  - B. **推荐**：把孤儿版里**确实更好**的部分（`strong_non_punct_hooks`、`narrative_pressure_markers`、`deadline_patterns`、`_evaluate_repetition_risk`、`_sanitize_markdown_presentation`）**逐项移植**到生产路径，每项一个独立提交 + 独立测试；移植完成后**删除孤儿文件**。
  - C. 只删孤儿文件，不移植。**不推荐**：会丢掉已写好的改进。
- **验收**：`grep -rn "story_quality_scoring" app/` 无结果（文件已删）；后端全量达到**当批目标值**（T-19 在批 10，目标 709，见 6.3 表；不要拿 659/668 这类起点值当验收线，那会掩盖前 9 批新增测试丢失）。
- **风险**：孤儿文件可能被外部脚本/文档引用。删除前执行 `grep -rn "story_quality_scoring" . --exclude-dir=.git --exclude-dir=.venv` 全库确认。

### D-02（P0）`_unit_has_progression` 把引号当推进 → 对话灌水拿满事件密度 ✅ 已修复（2026-08-18，批 3 / T-04）

> **修复后实测**：纯寒暄样本 `progression_unit_count` 从 190 降到 **0**、`event_density_passed` → `False`；正向对照 `GOOD_DRAMATIC` 仍 `True`（`rate` 0.3158）。引号句现在必须另有推进词或对话状态改变词；`却/但/然而/转而/下一步/活` 已移入 `WEAK_TRANSITION_MARKERS`，不参与判定，并有集合护栏测试防回退。

- **现象**：纯寒暄对话（「今天天气真不错啊」「是啊，阳光很好」）实测 `progression_unit_count=190`、`event_density_per_1000=83.7`、`event_density_passed=true`。
- **证据**：4.4、4.7 失效点 2。
- **位置**：`pipeline_orchestrator.py:7184-7190`（`_unit_has_progression`）；孤儿同 `story_quality_scoring.py:641-647`。
- **根因（本轮补充：有两个，只修引号那个是不够的）**：
  - **根因 1（引号）**：`if any(mark in unit for mark in ("“","”",...)): return True` —— 只要句子里有引号就直接返回 True，不看内容。
  - **根因 2（词表被三个纯连词污染，本轮新发现）**：`STORY_PROGRESSION_MARKERS`(7159-7167) 的最后一行是：
    ```python
    "杀", "死", "活", "必须", "否则", "来不及", "下一步", "转而", "却", "但", "然而",
    ```
    `"却"` / `"但"` / `"然而"` 是**纯转折连词**，`"活"` 是**极高频语素**（会命中「生活」「活着」「干活」「活动」）。中文叙事里几乎任何一句稍长的句子都含「但」或「却」。也就是说**即使把根因 1 修好、即使句子里完全没有引号，`_unit_has_progression` 仍然近似恒真**。
    这解释了 D-16 实测里为什么纯寒暄样本能拿到 `progression_unit_rate=1.0`（190/190 全部算推进）—— 不只是引号，还有连词。
- **影响**：这是 CLAUDE.md 目标「增加自然对话」被反向利用的核心通道：LLM 只要把无意义寒暄拆成很多句带引号的短句，就能同时刷高 `progression_unit_count`（+288）、`dialogue_markers`（+120）、`paragraph_count`（+216），并通过事件密度门。加上连词污染，连「全描写无对话」的文本也能刷高推进率。
- **修复方案（两个根因一起改，缺一个等于没改）**：
  ```python
  # 第一步：把纯连词与高频语素从主词表移出，单独成表（它们只能做辅助信号，不能单独判定推进）
  WEAK_TRANSITION_MARKERS = ("却", "但", "然而", "转而", "下一步", "活")
  STORY_PROGRESSION_MARKERS = (...去掉上面 6 个后的其余词...)

  # 第二步：引号不再无条件算推进
  def _unit_has_progression(cls, unit):
      if not unit:
          return False
      has_quote = any(mark in unit for mark in ("“","”","「","」","『","』",'"'))
      has_marker = any(m in unit for m in cls.STORY_PROGRESSION_MARKERS)
      if has_quote:
          # 引号必须配合局势变化信号，纯寒暄不算推进
          return has_marker or cls._count_dialogue_state_change_markers(unit) > 0
      return has_marker
  ```
  **注意 `"杀"/"死"/"必须"/"否则"/"来不及" 保留在主词表**——它们虽然也是单字/短词，但语义上确实指向危险与迫近，误报率可接受；`"活"` 必须移出，因为它的高频用法（生活/干活）与叙事推进无关。
- **验收**：新增测试 `test_event_density_rejects_pure_small_talk_dialogue`，断言 `BAD_FLAT_CHATTER` 样本 `event_density_passed is False` 且 `progression_unit_count` 显著下降；**另加 `test_progression_marker_table_excludes_bare_conjunctions`**，断言 `"但" not in STORY_PROGRESSION_MARKERS and "却" not in ... and "活" not in ...`（这条是防回退的护栏，成本一行）；`GOOD_DRAMATIC` 仍 `True`（防误杀）。后端全量 ≥ 668+N（批 2 后的基线）。
- **风险中等**：会降低所有对话密集文本的 `progression_unit_count`，可能让原本通过的真实章节被判 `event_density_weak`。**必须同时跑 4.4 的好样本对照，并检查现有 56 个测试**（尤其 1495 `test_event_density_allows_dense_progression_despite_local_plain_run`、1550 `test_story_quality_metrics_accept_dense_scene_sequel_progression`）。若这两个测试变红，说明阈值需要同步调低（`density_floor` 从 1.0 降到 0.6 左右），而不是回退修复。

- **风险中等**：会降低所有对话密集文本的 `progression_unit_count`，可能让原本通过的真实章节被判 `event_density_weak`。**必须同时跑 4.4 的好样本对照，并检查现有 56 个测试**（尤其 1495 `test_event_density_allows_dense_progression_despite_local_plain_run`、1550 `test_story_quality_metrics_accept_dense_scene_sequel_progression`）。若这两个测试变红，说明阈值需要同步调低（`density_floor` 从 1.0 降到 0.6 左右），而不是回退修复。

### D-03（P0）章末压力门可被两个标点通过 ✅ 已修复（2026-08-18，批 2 / T-03）

- **修复实现**（与下方原方案有出入，实际采用的是更彻底的分级词表）：
  - 词表从函数内局部变量提升为三个类属性：`PipelineOrchestrator.ENDING_WEAK_HOOK_MARKERS`（`？ ? ！ ! 却 突然 忽然`，7 个）、`ENDING_SEMANTIC_HOOK_MARKERS`（56 个实质压力词）、`ENDING_CLOSURE_MARKERS`（14 个完整收束短语）。提为类属性是为了让测试能直接断言词表内容（护栏测试靠它守住"不许再塞专有词"）。
  - 判定改为 `generic_pass = bool(semantic_hits) and (len(semantic_hits) + len(weak_hits)) >= 2` —— **语义命中是必要条件**，标点只能凑数量。原方案的 `strong_non_punct_hooks` 过滤只排除了 4 个标点，仍会让 `却` + `突然` 这类纯副词组合通过；分级词表把副词也归入弱信号，更彻底。
  - `mission_hook_pass` 保持原强度不放宽：`bool(mission_hook_hits and (semantic_hits or weak_hits))`，与原 `mission_hook_hits and hook_hits` 等价。
  - 新增两个可观测字段 `ending_semantic_hit_count` / `ending_weak_hit_count`，同时补进 `quality_metric_snapshot`（否则前端读的那份扁平快照拿不到，见下方"字段透出"）。
- **验收结果**：`test_ending_pressure_rejects_punctuation_only_hook` 断言纯标点结尾 `passed is False` + `ending_semantic_hit_count == 0` + `ending_weak_hit_count >= 2`；`test_ending_pressure_still_accepts_semantic_hook_without_punctuation` 守住反方向（无标点的强钩子仍通过）。4 个既有 ending_pressure 正例测试全绿。
- **反向验证**：把标点并回语义词表后，纯标点样本重新 `passed=True`（`sem=2`），确认测试必红。

<details>
<summary>原缺陷记录（供追溯）</summary>

- **现象**：结尾「他喝完了茶…觉得这一天过得很舒服。真的很舒服吗？当然很舒服！」→ `ending_pressure_passed=True`。
- **证据**：4.6 表第 1 行（实机验证）。
- **位置**：`pipeline_orchestrator.py:7313-7316`（`hook_markers` 含 `"？","?","！","!"`）、`7338`（`len(hook_hits) >= 2`）。
- **根因**：标点被放进了钩子标记表，且通过条件只数标记个数不看类型。
- **影响**：`ending_pressure_passed` 是 **6 条软放行中 5 条的必要条件**，还值 260 分（+140 / −120）。一个标点级的绕过会同时：让坏章通过章末压力门、白拿 260 分、激活软放行绕过其它 blocker。**这是当前最廉价的"骗过质量门"路径。**
- **原修复方案**（孤儿文件已有现成实现，移植即可）：
  ```python
  strong_non_punct_hooks = [h for h in hook_hits if h not in {"？", "?", "！", "!"}]
  passed = bool(
      not closure_hits
      and (deliver_hits or len(strong_non_punct_hooks) >= 2 or mission_hook_pass)
  )
  ```
  保留标点用于 `ending_pressure_score`（作为弱信号加分），但**不再单独构成通过条件**。
- **风险中等**：会让部分真实章节从通过变不通过。**必须与 D-04、D-05-b（补强压力词表）一起做**，否则会出现「修了漏判、放大了误杀」的净负面。→ 实际执行时 T-02 / T-03 / T-15 同批完成，三者互相抵消了误杀与漏判。

</details>

### D-04（P0）`closure_markers` 里的 `"一切都"` 误杀真钩子 ✅ 已修复（2026-08-18，批 2 / T-02）

- **修复实现**：`ENDING_CLOSURE_MARKERS` 把中性前缀 `"一切都"` 换成 7 个完整收束短语（`一切都结束` / `一切都过去` / `一切都平静` / `一切都恢复` / `一切都安稳` / `一切都很好` / `一切都没事`），另补 `平平淡淡才是真`。
- **与原方案的偏差（有意，且更严格）**：**没有采用**「强钩子可以压过 closure」（`not (closure_hits and not strong_non_punct_hooks)`），仍保留 `and not closure_hits` 的硬否决。理由：换成完整短语后，`一切都平静下来` 这类命中本身就是明确的平淡收束信号，此时即使前文有语义压力词也应判平淡；按原方案放行会让「追兵撤走了…一切都平静下来」（语义命中 3 个）被判通过，等于放宽平淡结尾门，与 CLAUDE.md「减少平淡结尾」的目标相反。新增 `test_ending_pressure_still_blocks_complete_flat_closure` 专门守住这个方向。
- **验收结果**：`test_ending_pressure_keeps_hook_when_closure_prefix_appears` 断言「…而幕后是谁，一切都还是未知。」`flat_closure_markers == []` 且 `passed is True`。
- **反向验证**：把 `"一切都"` 放回 closure 词表后，该真钩子重新被判 `passed=False`、`closure=['一切都']`，确认测试必红。
- **孤儿版未修**：`story_quality_scoring.py:798` 的 `closure_markers` 仍含裸 `"一切都"`，留待 T-19 统一处理（该文件在生产路径上零引用，见 D-19）。

<details>
<summary>原缺陷记录（供追溯）</summary>

- **现象**：结尾「追兵已经堵住了退路，玻璃在身后炸裂，而幕后是谁，**一切都**还是未知。」→ `ending_pressure_passed=False`，`flat_closure_markers=['一切都']`。
- **证据**：4.6 表第 3 行（实机验证）。
- **位置**：`pipeline_orchestrator.py:7317`；孤儿版 `story_quality_scoring.py:798` 有同样问题。
- **根因**：`"一切都"` 是三字通用前缀，「一切都还是未知」「一切都失控了」「一切都来不及了」全是**悬念钩子**，却被当作「平淡收束」。而 `closure_hits` 是**一票否决**（`and not closure_hits`）。
- **影响**：真正写得好的章末悬念被判「平收」→ 触发不必要的修复重写 → 浪费 LLM 调用、可能把好结尾改坏。这是**误杀方向**的缺陷，用户观感上表现为「明明写得挺好却总被打回重写」。
- **风险低**：这是收窄误杀，不会放行坏样本（因为仍要求真钩子命中）。**这是整份清单里性价比最高的一条：改 1 行常量 + 1 行条件，直接减少无谓重写。**

</details>


### D-05（P0）坏样本回归测试的具体覆盖缺口 ✅ 已实现的形态全部补齐（2026-08-18，批 4 / T-07）

既有 56 个测试已覆盖「全描写」「关键词灌水」「静态+短+少对话」「长章低密度」等（见 4.11）。**未覆盖**的坏样本类型：

| 编号 | 缺口 | 本轮实测的漏判 | 建议测试名 |
|-----|-----|--------------|-----------|
| D-05-a | **纯寒暄对话灌水** | score 1039（好样本 1302）、`event_density_passed=true`、`static_description_risk=false` | `test_flat_chatter_sample_is_blocked` ✅ 批 4 已加（批 3 已先修好判定） |
| D-05-b | **流水账日常动作序列** | `static_description_risk=false`、score 549 | `test_mundane_sequence_sample_is_blocked` ✅ 批 4 已加（**拦它的是章末压力门，不是密度门**，理由见批 4 落地记录偏差 ②） |
| D-05-c | **零对话文本被判「对话改变局势」** | `dialogue_marker_count=0` 却 `dialogue_changes_state=true` | `test_dialogue_state_is_not_claimed_without_any_dialogue` ⏳ 留 T-13（需先把 `dialogue_changes_state` 改三态，见 D-07） |
| D-05-d | **纯标点结尾** | `ending_pressure_passed=true` | `test_ending_pressure_rejects_punctuation_only_hook` ✅ 批 2 已加；批 4 另加整章级 `test_punctuation_only_hook_sample_is_blocked` |
| D-05-e | **真钩子含「一切都」被误杀** | `ending_pressure_passed=false` | `test_ending_pressure_keeps_hook_when_closure_prefix_appears` ✅ 批 2 已加 |
| D-05-f | **重复段落灌水** | ✅ **批 6 已实现**（T-10，`_evaluate_repetition_risk` + 判罚 −420 + 硬 blocker） | ✅ `class TestRepeatedParagraphFlood` 7 条（检出 / 硬 blocker / 判罚 / 短应答不误报 / 其余坏样本不误报 / 快照 / 800 字门槛） |
| D-05-g | **正文残留 Markdown 标记** | 生产路径无清理 | `test_chapter_body_has_no_markdown_presentation_artifacts` ⏳ 留 T-17 |
| D-05-h | **好坏样本分差下限** | 坏样本仅比好样本低 20% | `test_density_class_samples_score_far_below_control`（≥300）+ `test_ending_class_samples_score_below_control`（≥200）✅ 批 4 已加，拆两条的理由见落地记录偏差 ③ |

- **批 4 补齐范围**：a / b / d / h 四项 + 全描写形态 + 平淡收束形态 + 防误杀锚点，共 9 条测试收在 `class TestBadSampleRegression`。**c / f / g 三项不是漏做，是它们依赖的生产能力（D-07 三态、D-10 重复检测、D-11 清理）还没实现**，没有可断言的对象，分别留 T-13 / T-10 / T-17。
- **测试文件**：全部加到 **`backend/app/services/test_generation_quality_guards.py`**（针对生产路径）。**不要**新建 `test_story_quality_scoring.py`。
- **调用方式**（生产入口，classmethod，无需实例化）：
  ```python
  from app.services.pipeline_orchestrator import PipelineOrchestrator

  result = PipelineOrchestrator._score_story_quality_candidate(
      content=SAMPLE_TEXT,
      violations=[],
      chapter_mission=None,          # 或传 dict 以激活 expected_dialogue / scene_list 判定
      target_word_count=3000,
      min_word_count=2000,
  )
  assert result["static_description_risk"] is True
  ```
- **样本设计硬要求**（本轮踩过的坑，务必遵守）：
  1. **字数 ≥ 2200 非空白字符**。`word_count` 是去掉全部空白后的字符数；`word_count < 800` 会让事件密度门无条件放行（4.7 失效点 1），`< min_word_count` 会引入字数噪声。本轮第一版探针用 `× 3` 重复只得到 675～723 字，全部走了短路分支，白跑一轮。
  2. **不要整段精确重复**去凑字数。会触发 `repetition_risk`（孤儿路径）并污染判定。用序数前缀变体（本轮 `_probe_quality.py` 的 `grow()` 做法）：把模板里的 `＃` 替换成「初/次/三/四…」。
  3. **样本里不要混入英文词**。第一版探针误把 `remote` 留在中文样本里，会影响分词与标记命中。
  4. **每个坏样本必须配一个好样本对照断言**，防止「修了漏判、造成误杀」。
  5. 断言用**实测值**，不要用猜的数字。先写探针跑出真实值，再写断言。

### D-06（P1）章末压力词表对单一作品过拟合 ✅ 生产版已修复（2026-08-18，批 2 / T-15）；孤儿版留待 T-19

- **修复实现**：42 个 `\uXXXX` 全部还原成中文字面量，**剔除 10 个专有词**（`涨潮`、`潮水`、`缉印令`、`旧木片`、`旧南渠`、`药渣`、`药味`、`药耗`、`见了地`、`病人`），并按原方案的 5 个语义类别补通用词，最终 `ENDING_SEMANTIC_HOOK_MARKERS` 共 56 个：
  - 信息缺口类：`门外` `脚步` `消息` `线索` `证据` `异常` `不自然` `问题` `警告` `真相`
  - 倒计时/期限类：`期限` `下一` `下一轮` `下一章` `下一刻` `倒计时` `没时间` `最后一次` `来不及`
  - 强制选择类：`必须` `否则` `只能` `不得不` `别无选择` `绝路` `退路`
  - 追捕/威胁类：`封锁` `通缉` `追索` `追杀` `追兵` `追上来` `包围` `逼近` `堵死` `锁死` `陷阱` `盯上` `跟踪` `失踪` `失控` `暴露` `背叛` `威胁`
  - 代价/伤亡类：`代价` `后果` `危险` `危机` `压力` `死人` `会死` `死在` `人命` `生死` `活不过` `重伤`
- **与原方案的偏差**：
  1. **保留 `人命`**（原方案把它列进了应剔除的专有词）。理由：`闹出人命`、`这是人命` 是跨题材通用的压力表达，不是某部作品的道具名或地名，保留不会造成跨题材误判。
  2. **合并了重叠词**：把 `会先死` / `会死人` / `真会死` 三个互为子串的词合并成 `会死`，减少同一表达被拆成多个命中导致的计数虚高（`真会死人` 现在命中 `死人` + `会死` = 2，原先能命中 4 个）。这不是完整修复——彻底做法是按命中区间去重，但会让既有测试 `"下一轮" in hits` 之类的断言随遍历顺序漂移，成本收益不划算，记为遗留项。
- **验收结果**：
  - `grep -no '\\u[0-9a-f]\{4\}' pipeline_orchestrator.py` 剩 13 处，全部无风险：`7046` 是正则中日韩范围 `[^\u4e00-\u9fff...]`；`7381-7385` 是 `\uff5c`（｜）、`\uff1a`（：）、`\u3011`（】）三个**全角标点**，位于 `_detect_chapter_artifact_markers`，同行的中文关键词本来就是字面量，无过拟合风险（可读性遗留项，见新增的 D-23）。
  - 新增 `test_ending_hook_markers_are_genre_neutral_and_greppable`：既断言 10 个专有词不在词表里，又直接读源码断言 `ENDING_SEMANTIC_HOOK_MARKERS` 定义块内不含 `\u` —— **这条护栏是防回归的关键**，以后谁想再塞专有词或转义都会立刻报红。
  - 新增 `test_ending_pressure_uses_genre_neutral_markers_for_urban_story`：都市题材结尾（辞职信 / 陌生号码 / 保安 / `门外` + `必须`）判定通过，证明换题材不再依赖专有词。
  - 原第 891 行过拟合测试已改写为 `test_ending_pressure_recognizes_semantic_cliffhanger_without_punctuation`：样本里的 `见了地` 去掉，`deliver_to_next` 从 `旧南渠` 换成 `账册`，断言从 `any(hit in {"死人","见了地","真会死"})` 改成看 `ending_semantic_hit_count >= 1` + `ending_weak_hit_count == 0`（不再绑定具体词，也不受 `hits[:10]` 截断影响）。
- **反向验证**：把 `追兵` 从词表抽掉后，都市/追捕型钩子掉回 `passed=False`（`sem=1`）；把 `药渣`、`旧南渠` 放回词表后护栏测试报红。
- **孤儿版更严重且尚未处理**：`story_quality_scoring.py:800-811` 的 `zh_hook_markers` 仍是半修状态（800-811 转义、813-816 已是中文字面量），含全部 10 个被剔除的专有词。**危险点**：如果有人走 T-19 的备选方案 A（让 `PipelineOrchestrator` 继承 `StoryQualityScoringMixin`），这批专有词会静默回到生产，而新增的护栏测试只盯 `pipeline_orchestrator.py` 的词表块，抓不到它。T-19 执行时必须先删该文件或先还原它的词表。

<details>
<summary>原缺陷记录（供追溯）</summary>

- **现象**：生产版 `zh_hook_markers`（7318-7331）用 `\uXXXX` 转义写了一批只属于某一部具体小说的专有词：`旧木片`、`旧南渠`、`药渣`、`药味`、`药耗`、`见了地`、`病人`、`人命`。孤儿版更严重，额外含**人物名 `顾棠`、`林舟`**，以及 `血契`、`反噬`、`停棺`、`棺材铺`、`火印`、`令牌`、`假药`，注释直写 `Live ch2 paraphrase-friendly pressure roots`。
- **证据**：本轮 `Read pipeline_orchestrator.py:7318-7331`、`story_quality_scoring.py:799-858`。
- **根因**：为了让某一部小说的第 2 章通过质量门，把该作品的道具名/人名硬编码进了**通用**评分器。
- **影响**：
  1. 换题材（都市/科幻/言情）的小说拿不到这些加成，章末压力更容易被误判 false。
  2. 恰好含这些词的文本白拿通过（例如医疗题材出现「病人」「药味」即可能凑够 2 个 hook）。
  3. `\uXXXX` 转义使词表无法被 `grep` 搜到，维护性极差。
- **原风险评估（已被实测证实）**：
  - `test_generation_quality_guards.py:902` 断言 `any(hit in {"死人", "见了地", "真会死"} ...)`，剔除 `见了地` 后仍可靠 `死人` 命中 → 实际执行时该测试被整条改写为跨题材版本，不再有词表硬依赖。
  - `test_generation_quality_guards.py:896-897` 的 `旧南渠` 通过 `continuity_anchor.deliver_to_next` **动态注入**，不依赖硬编码词表 → 证明动态通道已被测试覆盖。
  - 其余 8 个测试文件共 65 处专有词只是**样本正文用词**，不是对词表的断言 → 未受影响（全量 667 → 668 全绿）。

</details>


### D-07（P1）`dialogue_changes_state` 无任务书时恒真

- **现象**：4 个样本（含**零对话**的两个）全部 `dialogue_changes_state=true`。
- **证据**：4.4、4.8。
- **位置**：`pipeline_orchestrator.py:7531 起`（**批 5 后**）。
- **根因**：`if not expected_dialogue: passed = True` —— 把「本章不要求对话」当成「对话质量合格」。
- **影响**：
  1. 白给 +140 分（占好样本总分 11%）。
  2. 该字段被 4 条软放行当作正向证据（`story_guard.get("dialogue_changes_state", True)`），恒真值会**连带激活软放行**，绕过其它 blocker。这是比分数更严重的后果。
  3. 语义荒谬：零对话文本被标注为「对话改变了局势」，写进 `quality_summary` 后会在前端展示给用户，损害可信度。
- **修复方案**：区分「不适用」与「合格」三态，不要用布尔值承担两种含义：
  ```python
  if dialogue_markers == 0:
      state = "not_applicable"      # 没有对话，该维度不适用
      passed = None                  # 不加分也不减分
  elif not expected_dialogue:
      # 任务书没要求对话，但正文有对话 → 仍然按内容判定，只是不作为 blocker
      passed = (marker_count >= 1)
  elif dialogue_markers >= 2 and marker_count >= 2:
      passed = True
  ...
  ```
  同时评分改为：`score += 140 if passed is True else (0 if passed is None else -140)`；软放行里把 `story_guard.get("dialogue_changes_state", True)` 改为 `story_guard.get("dialogue_changes_state") is not False`（明确区分 None）。
- **验收**：D-05-c 测试；`quality_summary` 里零对话章节不再出现「对话改变局势」正向标签。
- **风险中高**：改动布尔语义会波及 6 条软放行和 11 类 blocker 的判定。**必须逐个跑现有 56 个测试**，并对每个变红的测试判断是「测试固化了错误行为」（应改测试）还是「修复过头」（应调实现）。建议**拆成两步**：先只改评分不加分（低风险），再改软放行判定（高风险）。

### D-08（P1）静态描写检测逃逸 ✅ 已修（批 6，T-08 + T-09）

> **批 6 落地结论（以实测为准，下面的原始分析保留作历史）**：
> - **主根因是高频单字，不是环境动作词**。原分析把「收紧 `action_markers`」和「移植第 4 条」并列，实测顺序相反：一段 130 字纯风景（含 看/却/但/发现）在修前测得 `static_paragraph_count=0`——检测器根本没启动，第 4 条移植过去也无从触发。删掉这 4 个高频单字后，真实语料 `max_static_run` 从全 0 变成 p50=1 / max=2，`static_paragraph_count` p95=4，这才是检测器开始工作的唯一客观证据。
> - **环境动作词单独建表**：`AMBIENT_MOTION_MARKERS`（10 项）不参与判定，只为守卫测试断言「没有回流进 `STATIC_ACTION_MARKERS`」而存在。
> - **第 2 条阈值没有对齐孤儿版**：保留 `max_static_run >= 3`（孤儿版是 `>= 2`）。真实语料触发率：生产原样 0.000 / 孤儿版逐字照搬 0.044 / 孤儿版+第 2 条回到 3 → **0.029（采用）**。按「宁可漏判不要误杀」选了更松的可接受档。
> - **`len(plain) >= 100` 门槛未下调**（原方案 2 建议降到 60 并引入 `static_char_ratio`）：删单字后 100 字门槛已能出量，再降会把抒情段落一起吃掉。原方案 3（名词/动词密度比）未做。
> - **行号已失效**：批 6 的 grep 实测位置是 `STATIC_ACTION_MARKERS` 7658、`AMBIENT_MOTION_MARKERS` 7670、`_estimate_static_description_runs` 7673（已由 staticmethod 改 classmethod）、四条或式 `static_description_risk` 7815。下面正文里的 7586 / 7590 / 7669-7673 是批 5 时的旧值，别再照抄。
> - 覆盖率由 D-25 一并补齐：四条或式各有一个「只命中自己、另外三条为 False」的样本，外加 `STATIC_RUN_AT_LIMIT` 边界哨兵测试守住第 2 条阈值。

- **现象**：`BAD_ALL_DESCRIPTION`（纯风景描写、零对话、2200+ 字）被判 `static_description_risk=false`。
- **证据**：4.3。
- **位置**（**行号已按批 5 校准，批 6 后已失效，见上方结论**）：`pipeline_orchestrator.py:7586 起`（`_estimate_static_description_runs`，`action_markers` 在 7590）+ `7669-7673`（`static_description_risk` 三条或式）。
- **根因（两层，都得改）**：
  1. **单段判定太松**（7590 的 `action_markers`）：
     ```python
     action_markers = ("说","问","答","走","退","伸手","抬头","看","盯","推","抓","按","转身","决定","发现","却","但")
     is_static = len(plain) >= 100 and not any(marker in plain for marker in action_markers)
     ```
     - `看`、`却`、`但`、`发现` 是汉语超高频字。纯风景描写里「远处湖面**看**似平滑」「云影**却**淡」「**但**风铃不动」轻易出现，整段立刻被判为「有动作」。
     - `len(plain) >= 100` 门槛过高：把长风景段落切成 60-90 字的短段就完全不进入统计。
  2. **风险合成条件的三条或式都有硬门槛**（7669-7673）：
     - 第一条要求 `paragraph_count <= 4`：把风景写成 20 个短段即绕过。
     - 第二、三条依赖 `max_static_run >= 3` / `>= 2`，而 `max_static_run` 因上一层逃逸恒为 0。
- **与孤儿版对比（本轮实测，孤儿版在这一项上明确更严）**：

  | 条件 | 生产版（`pipeline_orchestrator.py:7669-7673`） | 孤儿版（`story_quality_scoring.py:1346-1356`） |
  |---|---|---|
  | 第 1 条（零对话+少段落） | `word_count >= 1800` | `word_count >= 1200` |
  | 第 2 条（连续静态段） | `>= 1500` 且 `max_static_run >= 3` | `>= 1200` 且 `max_static_run >= 2` |
  | 第 3 条（密度不足+静态） | `>= 2500` 且 `max_static_run >= 2` | `>= 2000` 且 `max_static_run >= 2` |
  | 第 4 条（有对话但静态段多） | **不存在** | `>= 1600` 且 `dialogue_markers > 0` 且 `max_static_run >= 2` 且 `static_paragraph_count >= 3` |

  孤儿版第 4 条正是堵「插一句对话就绕过」的，生产版完全没有 → **移植第 4 条并把阈值对齐孤儿版，是 D-08 里最低风险、最高收益的一步**，比重写 `action_markers` 更值得先做。
- **修复方案**（按性价比排序，建议 1+2 先做，3 视效果再定）：
  1. **收紧 `action_markers`**：删掉 `看`、`却`、`但`、`发现` 这 4 个高频字，改用**动作短语**而非单字：
     ```python
     action_markers = ("说道","问道","答道","开口","转身","伸手","抬头","扭头","后退",
                       "冲向","抓住","推开","按住","拔出","扣动","决定","撞","喊","扑")
     ```
     单字保留 `走`、`退`、`推`、`抓`、`按`、`盯` 即可（这些在纯风景里罕见）。
  2. **降低段落长度门槛并改用比例判定**：`len(plain) >= 60`；同时新增全文级指标 `static_char_ratio = 静态段落总字数 / 全文字数`，当 `static_char_ratio >= 0.6 and dialogue_markers <= 2` 直接判 `static_description_risk=True`，不再依赖 `max_static_run` 连续段数。这一条能同时堵住「切成短段」和「插一句对话」两种绕过。
  3. **可选增强**：统计「感官/景物名词密度」（`光`、`影`、`雾`、`云`、`风`、`色`、`静`、`寂`）与「动词密度」之比，比值过高判静态。此项主观性强、易误杀抒情段落，**除非 1+2 不够，否则不做**。
- **验收**：D-05-a（纯风景，切成 20 短段）与 `BAD_ALL_DESCRIPTION` 均判 `static_description_risk=True`；`GOOD_DRAMATIC` 仍为 `False`；既有 `test_structural_quality_gate_blocks_static_description_and_weak_progression`(**692**) 与 `test_first_draft_retry_triggers_for_static_short_dialogue_light_copy`(**486**) 保持绿。另外**批 4 的 `TestBadSampleRegression` 9 条必须全绿**（`-k "BadSampleRegression"`，比全量快一个数量级）。
- **风险中等**：收紧 `action_markers` 会让更多文本被判静态 → 质量门更容易 block → 生成重试变多、耗时上升。**T-22 已于批 5 完成**，`_attempt_structural_gate_repair`(2054) 现在能采纳部分改善且最多试 2 轮，救回率比批 4 之前高，但仍建议改完跑一次真实生成端到端验证。

### D-09（P1）评分模型可机械灌水刷分

- **现象**：好坏样本分差仅 263 分（20%），而 `paragraph_count`+`dialogue_markers`+`progression_unit_count` 三项贡献 624 分（好样本总分的 48%），这三项**只奖励「分段多、引号多、句子多」**。
- **证据**：4.6、4.9、4.10。
- **位置**：`pipeline_orchestrator.py:7488-7506`。
- **根因**：这三项是「形式计数」而非「质量判定」：
  | 项 | 公式 | 上限 | 刷分方式 |
  |---|---|---|---|
  | 段落数 | `min(paragraph_count, 12) * 18` | +216 | 任意文本按句子换行即满 |
  | 引号数 | `min(dialogue_markers, 10) * 12` | +120 | 堆 5 组无意义对话即满 |
  | 推进单元 | `min(progression_unit_count, 18) * 16` | +288 | 因 D-02 引号即算推进，与上一项重复计数 |
  | 字数 | `min(word_count, 2400) // 50` | +48 | 灌水即满 |
  | **合计** | | **+672** | 全部可机械满足 |
- **影响**：LLM 生成的「安全但空洞」文本（大量短段+寒暄对话）能拿到接近好样本的分数，`_fallback_select_best_version`(7579) 在多候选里会选中它。**这是「为什么生成的小说全是描写和废话对话」的直接机制解释。**
- **修复方案**（不要简单调权重，要改成「有上限的资格分 + 无上限的质量分」两段式）：
  1. **形式项降权并封顶为资格分**：段落数 `min(paragraph_count, 12) * 18` → `min(paragraph_count, 8) * 10`（上限 +80）；引号数 `min(dialogue_markers, 10) * 12` → `min(dialogue_markers, 6) * 10`（上限 +60）。形式项合计从 336 降到 140。
  2. **推进单元改为「有效推进单元」**：依赖 D-02 修完后的 `_unit_has_progression`，只统计真正含状态变化标记的单元；权重保持 16 但基数会大幅下降，自然拉开差距。
  3. **质量项加权**：`ending_pressure` 由 `+140/-120` 提到 `+200/-260`；`event_density_passed` 由 `+80/-180` 提到 `+120/-260`；新增 `reversal_present`（检测 `却`+`原来`+`竟`+`反而`+`没想到` 在**同一段内**与状态变化标记共现）`+160`。
  4. **加负向判罚**（见 D-10/D-12/D-13）：重复段落 −420、focus_character 未出场 −240、字数偏离 −620/−520/−180。
  5. **验收指标**：好坏样本分差 **≥ 600 分（≥45%）**，且分差来源分布在 ≥3 个维度（不能像现在全靠 ending_pressure 一项）。这是 D-05-h 测试要固化的东西。
- **风险高**：改评分权重会改变**所有**多候选选择结果，可能让既有测试里「期望选中 version X」的断言变红。**先 `grep -rn "_fallback_select_best_version\|_should_override_ai_review_choice" app/services/test_*.py` 列出受影响测试，逐个人工判断期望值是否仍合理。** 建议顺序：先做 4（加判罚，只影响坏样本，不影响好样本相对排序）→ 再做 3（加权质量项）→ 最后做 1（降权形式项，影响面最大）。

### D-10（P1）生产路径完全缺失重复段落检测

- **实测确证**（本轮）：
  ```bash
  grep -n "_evaluate_repetition_risk\|repetition_risk" app/services/pipeline_orchestrator.py
  # → 0 结果
  ```
  生产版 `_score_story_quality_candidate` 的输出字典里**没有任何** `repetition_*` 字段；孤儿版 1344 行调用 `_evaluate_repetition_risk` 并在 1376 行判罚 `-420`，还把 7 个字段 `**repetition` 展开进快照。
- **影响**：LLM 最常见的低质量退化方式之一就是**整段复述前文**（尤其在续写/enrichment 补字数时）。生产路径对此**零检测、零判罚、零可见性**。多候选里「靠复制段落凑字数」的候选与正常候选同分，甚至因段落数/字数项更高而**胜出**。
- **移植代码**（孤儿版 `story_quality_scoring.py:949-980`，可直接照搬，无外部依赖，只用 `re`）：
  ```python
  @staticmethod
  def _evaluate_repetition_risk(paragraphs: List[str], *, word_count: int) -> Dict[str, Any]:
      normalized = [p for p in (re.sub(r"\s+", "", str(x or "")) for x in paragraphs) if len(p) >= 30]
      counts: Dict[str, int] = {}
      for paragraph in normalized:
          counts[paragraph] = counts.get(paragraph, 0) + 1
      repeated = [(t, c) for t, c in counts.items() if c > 1]
      repeated_instances = sum(c - 1 for _t, c in repeated)
      max_repeat = max((c for _t, c in repeated), default=1)
      longest_repeated = max((len(t) for t, _c in repeated), default=0)
      repeated_ratio = round(repeated_instances / max(1, len(normalized)), 4)
      risk = bool(
          word_count >= 800 and repeated
          and ((max_repeat >= 3 and longest_repeated >= 30)
               or (repeated_instances >= 2 and repeated_ratio >= 0.3 and longest_repeated >= 80))
      )
      return {"repetition_risk": risk, "repeated_paragraph_count": len(repeated),
              "repeated_paragraph_instances": repeated_instances,
              "max_repeated_paragraph_count": max_repeat,
              "repeated_paragraph_ratio": repeated_ratio,
              "longest_repeated_paragraph_chars": longest_repeated,
              "repeated_paragraph_examples": [t[:120] for t, _c in repeated[:3]]}
  ```
  接入点三处，缺一不可：
  1. `_score_story_quality_candidate`(7454) 内新增 `repetition = cls._evaluate_repetition_risk(paragraphs, word_count=word_count)`。
  2. 评分加 `score -= 420 if repetition.get("repetition_risk") else 0`。
  3. 返回字典与 `quality_metric_snapshot` 都加 `**repetition`（前端与 `_build_quality_issue_summary` 靠这些字段出诊断文案）。
- **同时要加 blocker**：`_build_structural_quality_gate`(616) 新增第 12 类 blocker `repeated_paragraph_flood`，条件 `story_guard.get("repetition_risk")`。否则只扣分不阻断，仍会产出重复正文。
- **注意**：孤儿版只检测**精确重复**（去空白后完全相同）。LLM 更常见的是「近似复述」（改几个字）。精确检测是低误杀的第一步，**近似重复检测不要在这一轮做**（需要 SimHash/编辑距离，误杀风险高、耗时增加），留作 P3。
- **验收**：D-05-f 测试；`GOOD_DRAMATIC`（用序数前缀扩写、无精确重复）仍 `repetition_risk=False`——这条很重要，它证明「合法的排比/回环结构」不被误杀。
- **风险低**：纯新增字段与判罚，不改任何既有判定。唯一风险是 blocker 上线后 block 率上升，与 D-08 同样需要确认定向修复能救回。

### D-11（P2）生产路径缺失确定性清理与 Markdown 呈现清理

- **实测确证**（本轮）：生产文件里 `_apply_deterministic_cleanup`、`_sanitize_markdown_presentation`、`_remove_exact_repeated_paragraphs`、`_remove_exact_repeated_paragraphs_with_floor` **四个方法全部 0 结果**。孤儿版分别在 1069、1201、983、1006 行。
- **孤儿版能力**：
  - `_apply_deterministic_cleanup`(1069)：不调 LLM 的确定性正文清理（移除精确重复段落等），返回 `(cleaned_content, report)`。
  - `_sanitize_markdown_presentation`(1201)：清除正文里残留的 Markdown 语法（`#` 标题、`**` 加粗、`- ` 列表、代码围栏）——LLM 经常把「章节标题」「小标题」「要点列表」写进小说正文。
  - `_remove_exact_repeated_paragraphs_with_floor`(1006)：带字数下限保护的重复段落移除（避免清理后字数掉到 min 以下）。
- **影响**：正文里的 Markdown 残留和重复段落**只能靠 LLM 二次调用（optimizer/enrichment）去掉**，成本高且不确定。确定性清理是「免费的、必然生效的」质量提升。
- **注意生产路径已有部分能力**：`_detect_chapter_artifact_markers`(7417) 会**检测**章节标题类残留并判罚 −480（7502 附近）+ 触发 `chapter_artifact_markers` blocker，但**只检测不清理**。所以现状是「发现问题 → 整章 block → 重新生成」，而正确做法是「发现 → 确定性清掉 → 不必重生成」。
- **修复方案**：移植 `_sanitize_markdown_presentation` 与 `_apply_deterministic_cleanup`，在 `generate_chapter` 里插到**质量门之前**（即 `_evaluate_structural_quality_gate_for_content` 调用点之前），让清理后的正文去过门。清理动作必须写进 `runtime_metadata`（如 `deterministic_cleanup_report`）以便可见与可回溯。
- **验收**：D-05-g 测试（正文含 `## 第三章`、`**重点**`、`- 列表项` → 清理后消失且 `chapter_artifact_markers=False`）；清理后字数不低于 `min_word_count`（用 `_with_floor` 版本保证）。
- **风险中等**：清理正文是**修改用户作品内容**的操作。必须：① 只清理明确的 Markdown 语法与精确重复，不做任何语义改写；② 清理前后的 diff 记入日志；③ 清理不得使字数跌破 `min_word_count`（这正是 `_with_floor` 变体存在的原因）。

### D-12（P2）焦点人物缺席已被连续性门检测，但不进入候选评分（**本轮修正：不是"完全缺失"**）

- **✅ 已于批 7 修复（2026-08-19）**：`_collect_focus_character_names` 已移植到生产路径（`chapter_mission` 四来源）、判罚 −240、四个快照字段齐全。**仍然保持 warning 不加 blocker**（别名/称谓替代本名会让字符串匹配误判），并单独加了 `test_focus_absence_is_warning_not_blocker` 钉住这一点。落地细节见第 7 节「批 7 实际落地记录」。**本条以下内容保留为「当初怎么想的」备查。**

- **先纠正一条容易写错的结论**：焦点人物缺席**并非完全没有检测**。`longform_context_service.py:734-745`（`evaluate_continuity_quality`）已经在做：
  ```python
  missing_focus = [
      name for name in package.cast_plan.chapter_focus_names
      if name and name not in text and not name.startswith("角色")
  ][:6]
  if missing_focus:
      warnings.append({"code": "chapter_focus_missing",
                       "message": "本章角色焦点在正文中缺席或弱化。", "characters": missing_focus})
  ```
- **真正的缺口有三个**：
  1. 它只是 **warning，不是 blocker**，也**不影响候选评分**（多候选排序时，焦点人物全部缺席的候选与正常候选同分）。
  2. 它的数据源是 `package.cast_plan.chapter_focus_names`（**长篇上下文包**）。当 `package is None` 时（`longform_context_service.py:716-720`）整个连续性门直接 `passed=True` 并只留一条 `longform_context_missing` warning —— 也就是说**短篇/未启用长篇上下文的场景下，焦点人物检查完全不生效**。
  3. `chapter_mission.focus_characters` / `character_focus` / `pov_character` / `scene_list[].characters` 这条数据源**从来没有被用于焦点人物检查**（只有孤儿版 `_collect_focus_character_names`(910) 会读它，而孤儿版零引用）。
- **实测确证**：`grep -n "_collect_focus_character_names\|focus_character_missing" app/services/pipeline_orchestrator.py` → **0 结果**。
- **修复方案（修正后）**：
  - 移植孤儿版 `_collect_focus_character_names`(909-947) 到生产路径，数据源用 `chapter_mission`（**与连续性门的 `cast_plan` 互补，不冲突**：一个来自任务书，一个来自长篇记忆层，两者都缺席才是强信号）。
  - 在 `_score_story_quality_candidate` 里加判罚 `-240`（条件 `focus_character_names and not focus_character_hits and word_count >= 1200`）。
  - 返回字段与快照加 `focus_character_names` / `focus_character_hit_count` / `missing_focus_characters` / `focus_character_missing`。
  - **保持 warning 语义，暂不加 blocker**（理由见下）。
- **移植要点**（孤儿版实现的三个关键设计，照抄不要改）：
  - `placeholders = {"主角","男主","女主","角色","角色A","角色B","protagonist","pov"}` 过滤占位符（否则会拿「主角」去正文里做字符串匹配）。
  - 按 `[，。；、,;\s/|]+` 切分，只保留 2-12 字的名字，去重后取前 8 个。
  - 判罚条件是 `not focus_character_hits`（**一个都没出现**才罚），而不是「有缺失就罚」——配角某章不出场是正常的。
- **为什么暂不加 blocker**：LLM 常用别名/称谓替代本名（「顾家小姐」代替「顾棠」、「那个男人」代替本名），字符串匹配会误判。先只判罚 + 可见，收集真实误报率再决定。这与连续性门把它定为 warning 的判断一致。
- **验收**：任务书 `focus_characters: ["陈默", "苏婉"]`，正文一个都没提且字数 ≥1200 → `focus_character_missing=True` 且分数低 240；任务书 `focus_characters: ["主角"]`（占位符）→ `focus_character_names=[]`，不判罚；`package is None` 的短篇场景下仍能生效（这是相对连续性门的净增益）。
- **风险低**：纯新增判罚，不加 blocker 不会提高拒稿率。

### D-13（P1）字数维度完全不进入候选评分（三层原因，必须一起修）

- **✅ 已于批 7 修复（2026-08-19），实际是四层不是三层**：除本条列的三处，`_evaluate_first_draft_retry` 还有第 4 处——它签名里字数是必填、自己做了规范化，调用评分器时就是不传，导致同一份 `story_guard` 里 `reason_codes` 说字数不足而字数标志说没问题，**自相矛盾且长期没人发现**。三判罚定为 620/520/180，`upper` 系数取孤儿版 2.0/1.6（**死代码里的 1.25 会让误杀率从 0.012 涨到 0.305**）。真实语料 n=99 校准表见 §11.2.1「批 7 表」，落地细节见第 7 节「批 7 实际落地记录」。**本条以下内容保留为「当初怎么想的」备查。**

这一条是本轮**最容易被漏掉、也最容易误判为「已经在做了」**的缺陷。生产路径的字数检查存在，但**位置不对**。

- **第 1 层：生产版评分器函数体完全不使用字数参数**（决定性证据）：
  ```bash
  awk 'NR>=7454 && NR<=7578 && (/target_word_count/ || /min_word_count/ || /target_floor/ || /minimum_floor/)' \
    app/services/pipeline_orchestrator.py
  # 只输出两行，都是签名里的形参声明：
  #     target_word_count: Optional[int] = None,
  #     min_word_count: Optional[int] = None,
  ```
  即：两个参数**声明了但函数体内一次都没用到**。孤儿版 1317-1325 用它们算出 `target_floor` / `minimum_floor` / `preferred_floor`（`target*0.92`）/ `upper_target`（`≤2500` 时 `target*2.0`，否则 `target*1.6`）与 3 个布尔判定，并在 1379-1381 判罚 `-620` / `-520` / `-180`。**生产版全部缺失。**

- **第 2 层：6 个调用点里 5 个根本没传这两个参数**（本轮逐点实测）：

  | 行号 | 调用者 | 传字数参数 | 后果 |
  |---|---|---|---|
  | 442 | `_evaluate_structural_quality_gate_for_content`（质量门） | ✅ | 传了也被忽略（第 1 层） |
  | 3437 | reader_polish 结构诊断 | ❌ | — |
  | 4039 | `final_quality_guard`（**写入元数据、前端展示**） | ❌ | 前端看到的字数字段无意义 |
  | 5732 | `_evaluate_first_draft_retry`（首稿重试判定） | ❌ | 见下，最严重 |
  | 6492 | 首稿重试后的新旧比分 | ❌ | 重试比分不惩罚字数偏离 |
  | 7590 | `_fallback_select_best_version`（**多候选选择**） | ❌ | 多候选排序完全不看字数 |

  `_evaluate_first_draft_retry`(5723) 最能说明问题：它的签名里 `target_word_count: int` / `min_word_count: int` 是**必填参数**，5737-5738 还自己 `max(0, int(...))` 规范化了一遍，**却在 5732-5736 调用评分器时没有传下去**。这是纯粹的漏传，不是设计取舍。

- **第 3 层：管线层确实检查字数，但那是「事后阻断」而非「候选择优」**：`generate_chapter` 在 4086-4124 用 `runtime_metadata["word_requirement_met"] = final_word_count >= active_config.min_word_count` 检查，并在 `active_config.enforce_min_word_count` 为真时（4099）阻断。这解释了为什么这个缺陷一直没被发现——**字数不足确实会被拦下来**，但拦下来的方式是「整章失败」，而不是「在多个候选里选字数达标的那个」。

- **综合影响**：
  1. 多候选生成时，2200 字候选与 3000 字候选在评分上只差 `min(word_count, 2400)//50` 的**几分**（且 2400 以上封顶，3000 字与 2400 字完全同分）。系统会因为「段落多/引号多」而选中字数不足的候选，**然后在管线末端因字数不足整章失败**——本来选另一个候选就能过。
  2. `word_count_far_above_target`（超长）零判罚：LLM 写到 2 倍目标字数（典型的灌水失控）不受任何惩罚，反而因段落数/引号数更多而得分更高。
- **修复方案（必须三层一起改，只改一层无效）**：
  1. 把孤儿版 1317-1325 的字数计算与 1379-1381 的三条判罚移植进生产版 `_score_story_quality_candidate`。**注意 `upper_target` 用孤儿版的 `2.0/1.6` 而不是 `_score_fallback_candidate` 里的 `1.25`**——1.25 对小说过严（长章节正常会超目标）。
  2. 给 5 个漏传的调用点补上参数。3437 / 4039 / 6492 / 7590 需要先确认作用域里能拿到 `config.target_word_count` / `config.min_word_count`（4039 在 `generate_chapter` 内，有 `active_config`；7590 在 classmethod 内，**需要给 `_fallback_select_best_version` 加两个可选参数并从调用处传入**）。
  3. 把 8 个字数字段加进返回字典与 `quality_metric_snapshot`（`word_count_below_min` / `word_requirement_met` / `preferred_word_floor` / `upper_word_ceiling` / `word_count_far_above_target` / `word_count_far_below_target` / `target_word_count` / `min_word_count`），前端才能显示真实的字数达标状态。
- **验收**：同一组候选（2200 字 vs 3000 字，其余维度相同，`min_word_count=2500`）→ 3000 字候选得分高 ≥620；`_fallback_select_best_version` 选中 3000 字那个。这是 D-05 之外要新增的第 9 个测试。
- **风险中高**：第 2 层补参数会**真实改变多候选选择结果**（这正是目的），必然影响既有测试的期望值。**顺序建议**：先做第 1 层+第 3 层（加计算、加字段，但**判罚系数先设为 0**）→ 跑全量确认当批基线全绿、只是多了字段 → 再把判罚系数改成 −620/−520/−180 → 再补第 2 层调用点参数 → 每步跑全量。

### D-14（P2·谨慎）self_critique 自评豁免构成自评闭环

- **位置**：`_build_structural_quality_gate`(616) 内两条豁免（在 640-891 blocker 段中）：
  - `ending_pressure_missing` 在 `critique_score >= 75` 时不作为 blocker
  - `event_density_weak` 在 `critique_score >= 70` 时不作为 blocker
  `critique_score` 来自 `_run_self_critique`(7803) —— 也就是**同一个 LLM 对自己刚写的正文打的分**。
- **问题**：确定性指标（结构诊断）被**非确定性自评**否决。LLM 自评普遍虚高，`>=75` 是很容易达到的分数。等价于「模型说自己写得好，就不用过结构门」。
- **但这条改动风险最高，必须谨慎**：这两条豁免**当初就是为了修误杀而加的**（结构门在真实数据上误杀了合格章节，用自评分兜底放行）。直接删掉会让误杀问题回归，表现为「生成一直失败」，比现在更糟。
- **正确处理顺序（不要跳步）**：
  1. **先修准确率，再收豁免。** D-03（标点绕过）、D-04（`一切都` 误杀）、D-16（密度门量级）修完后，`ending_pressure` 与 `event_density` 的判定准确率会显著提升，误杀本身减少 → 豁免的必要性下降。
  2. 修完上述项后，**先加观测不改行为**：在 `quality_metric_snapshot` 里记录 `critique_exemption_applied: ["ending_pressure_missing", ...]`，跑一批真实生成，统计豁免触发率。
  3. 只有当豁免触发率低（说明确定性指标已经够准）时，才提高阈值（`75 → 88`、`70 → 85`）或改成「豁免需同时满足自评分高**且**该维度的次级证据存在」。
  4. **绝不直接删除豁免。**
- **验收**：豁免触发率有数据；调整阈值后全量在当批基线上仍全绿；真实生成的失败率不上升。
- **风险高**：这是「宁可放过坏的，不可误杀好的」与「质量门必须有牙齿」之间的权衡，**需要真实生成数据支撑，不能只靠单测判断**。这也是为什么它排 P2 而不是 P0——它的收益取决于 P0/P1 是否先做完。

### D-15（P2）`word_count < 800` 无条件放行事件密度门

- **位置**：`pipeline_orchestrator.py:7193-7204`。
- **现象**：字数不足 800 时直接返回全 True 且 `progression_unit_rate: 1.0`：
  ```python
  if word_count < 800:
      return {"event_density_passed": True, "long_chapter_density_passed": True,
              "state_change_interval_passed": True, "progression_unit_count": 0,
              "story_unit_count": 0, "progression_unit_rate": 1.0,
              "event_density_per_1000": 0.0, "state_change_window_pass_rate": 1.0,
              "max_plain_unit_run": 0}
  ```
- **这个短路本身是合理的**（短文本统计不可靠），但有两个具体问题：
  1. **返回值自相矛盾**：`progression_unit_count=0` 与 `progression_unit_rate=1.0` 同时出现（0 个推进单元却说推进率 100%）。这些字段会流入 `quality_metric_snapshot` → 元数据 → 前端，用户看到「推进率 100%，推进事件 0 个」。应改为 `progression_unit_rate: None` 并在快照里标 `event_density_evaluated: False`，让前端能显示「样本过短，未评估」而不是假的满分。
  2. **配置放行风险**：`min_word_count` 默认 500（`pipeline_orchestrator.py:114`）。当用户把目标字数设得很小（短章模式）时，**整个事件密度门对所有章节永久失效**，且没有任何提示。
- **修复方案**：
  1. 把矛盾字段改成 `None` + 新增 `event_density_evaluated: bool`（默认 True，短路时 False）。所有消费方（6 条软放行、blocker、前端 `chapterQuality.ts`）用 `is not False` 而不是 `get(..., True)` 判断。
  2. 当 `min_word_count < 800` 时，在 `runtime_metadata` 里写一条 `quality_gate_notice: "min_word_count 低于 800，事件密度门不生效"`，让配置副作用可见。
  3. **不要降低 800 这个阈值**——句子级统计在 800 字以下确实噪声太大。
- **验收**：600 字样本 → `event_density_evaluated=False`、`progression_unit_rate is None`、不加分不减分；既有 `test_event_density_*` 测试仍绿（它们用的样本都 ≥800 字，本轮第一版探针踩的就是这个坑，见 4.2）。
- **风险低**：只改「不适用」的表达方式，不改判定结果。唯一要小心的是所有 `get("event_density_passed", True)` 的默认值写法——必须逐个确认 None 不会被当成 False。

### D-16（**P0，本轮新发现，优先级高于原 D-02**）事件密度门量级完全失配，且指标方向是反的 ✅ 三项全部已修复（2026-08-18，批 3 / T-04+T-05+T-06）

> **修复后实测**：`BAD_FLAT_CHATTER` `rate` 1.0 → **0.0**、`event_density_passed` → `False`；`GOOD_DRAMATIC` `rate` 0.6923 → 0.3158、仍 `True`；`state_change_window_pass_rate` 在真实语料上从"恒 1.0"变成中位数 1.0 但**有分布**（p10=0.333，纯寒暄 0.0）。
>
> **本节第 1019/1021/1023 条的具体建议全部作废**：`density_floor` 8/10/12、`unit_rate_floor` 0.35、"先设 4.0 观察"——这三个数字都是按合成样本的量级推的，在 147 条真实生成章节上分别误杀 68%、79%、42%。真实定值是 **1.5/1.8/2.0** 与 **0.025/0.028/0.03**，窗口占比 **0.05**（不是 0.15/0.25），连段判据从绝对句数换成占全章句数的比例 **0.75/0.72/0.70**。完整校准数据、5 处偏差与已知局限见第 7 节「批 3 实际落地记录」。
>
> **量级结论的修正**：本节说"实测密度 53-125，门槛 1.0 差两个数量级"——那是**引号无条件算推进**时的数字。收紧判定后真实章节的 `event_density_per_1000` 中位数只有 **4.60**（p05=2.01），所以修复后的正确量级是**个位数**，不是几十。批 3 第一版正是错读了这一点才把门槛定到 6.0/7.0/8.0。

这是本轮最重要的发现。事件密度门不只是"不起作用"，它在多候选比较里**系统性偏好灌水文本**。

- **实测数据**（本轮，直接调 `P._evaluate_event_density`，两个样本都用序数前缀扩写避免精确重复）：

  | 指标 | `BAD_FLAT_CHATTER`（纯寒暄灌水） | `GOOD_DRAMATIC`（有冲突有反转） | 门槛 |
  |---|---|---|---|
  | `word_count` | 1520 | 1344 | — |
  | `story_unit_count` | 190 | 104 | — |
  | `progression_unit_count` | **190** | 72 | — |
  | `progression_unit_rate` | **1.0** | **0.6923** | `>= 0.16` |
  | `event_density_per_1000` | **125.0** | **53.57** | `>= 1.0` |
  | `state_change_window_pass_rate` | 1.0 (2/2) | 1.0 (2/2) | `>= 0.6` |
  | `max_plain_unit_run` | 0 | 2 | `<= 5` |
  | `event_density_passed` | **True** | True | — |

  > **样本规模说明**：这张表用的是 1520/1344 字的精简版样本，4.7 用的是 2270 字扩写版（`density_per_1000=83.7`）。两组数字不同只是因为样本长度不同，**结论完全一致**：实测值比门槛 `1.0` 高出 50-125 倍。做验收测试时用哪一组都可以，但**断言必须写实测值**，不要跨样本抄数字。

- **三个独立缺陷，一起造成门失效**：

  **D-16-a 门槛量级差两个数量级。** `density_floor = 1.0 / 1.25 / 1.45`（7227），实测值 **125.0 / 53.6**，超出门槛 **125 倍 / 54 倍**。这个门槛显然是按"每 1000 字有 1~1.5 个**真实事件**"设计的，但 `event_density_per_1000` 实际算的是"每 1000 字有多少个**句子级单元被判为有推进**"（7225：`progression_count / (word_count/1000)`，而 `_story_units`(7171) 按 `[。！？!?\n]+` 切句）。一个 1500 字文本有 100-190 个句子，密度天然是 60-130。**这个门永远不可能因为 `density_per_1000` 不足而失败。**

  **D-16-b `progression_unit_rate` 指标方向相反。** 灌水样本 **1.0**，好样本 **0.69**——灌水文本在这个指标上**赢了**。根因是 D-02（`_unit_has_progression` 7187 行「含任何引号即算推进」）：寒暄对话 100% 是引号句 → 每个单元都算推进；真正好的正文有大量**叙述与动作句**（「话音未落，她扣动扳机」这类无引号句）→ 只有 69% 命中。门槛 0.16 对两者都是白送（6.2 倍 / 4.3 倍余量）。

  **D-16-c `state_change_window_pass_rate` 恒为 1.0，因为把句子级判定函数用在了 950 字窗口上。** 7220-7222：
  ```python
  window_size = 1200 if word_count >= 7000 else 950
  windows = [condensed[i:i + window_size] for i in range(0, len(condensed), window_size)] or [condensed]
  window_hits = sum(1 for window in windows if cls._unit_has_progression(window))
  ```
  `_unit_has_progression` 的语义是「**这一句**里有没有推进」，用「含任何引号或任一 `STORY_PROGRESSION_MARKERS` 即为真」判定——对一句话合理，对 **950 个字**必然为真（950 字里不可能一个引号和推进词都没有）。所以 `state_change_interval_passed`（7232）**恒真**，`dense_progression_override`（7233）也因此更容易触发。两个样本都是 2/2 = 1.0，印证了这一点。

- **综合影响**：
  1. `event_density_weak` / `state_change_interval_weak` / `long_chapter_event_density_weak` 三类 blocker **实际上只有 `max_plain_unit_run > 5` 一条能触发**（即"连续 6 句以上完全没有引号和推进词"）。纯风景描写会被拦下（本轮实测 1650 字纯描写样本 `max_plain_unit_run=88` → `False`），**但只要每隔几句插一句对话就能完全绕过**。
  2. 这解释了 4.11 观察到的绕过链的核心机制，也解释了「为什么生成的小说全是废话对话」——**灌水对话在事件密度维度上是最优策略**。
  3. `event_density_passed` 恒真还连带让 `density_soft_pass` / `dense_scene_soft_pass` 等软放行更易成立，进一步削弱其它 blocker。

- **修复方案（必须先修 D-02 再调门槛，顺序不能反）**：
  1. **先修 D-02**：`_unit_has_progression` 不能「有引号即为真」。改成：引号句必须**同时**含状态变化标记（`_count_dialogue_state_change_markers` 用的那批词）或动作词才算推进。修完后 `progression_unit_rate` 才有区分度（预期灌水样本降到 0.2-0.4，好样本保持 0.6-0.8）。
  2. **再重定 `density_floor` 量级**。修完 D-02 后重跑探针拿到真实分布，再定门槛。**不要凭猜**。经验起点：按「每 1000 字至少 8-12 个有效推进单元」设 `density_floor = 8.0 / 10.0 / 12.0`，但**必须用真实生成的正文样本校准**，否则会大面积误杀。
  3. **修 D-16-c**：给窗口判定单独写一个 `_window_has_state_change(window)`，要求窗口内**至少 2 个**状态变化标记，而不是复用句子级函数。或者更简单：把窗口判定改为「窗口内的 `_story_units` 中有 ≥15% 判为推进」。
  4. **提高 `unit_rate_floor`**：0.16 → 0.35（修完 D-02 后好样本约 0.6-0.8，留足余量）。
- **验收（D-05 之外新增，属 D-05-h 的量化部分）**：修完后 `BAD_FLAT_CHATTER` 必须 `event_density_passed=False`，`GOOD_DRAMATIC` 必须 `True`；且 `progression_unit_rate(GOOD) > progression_unit_rate(BAD_FLAT_CHATTER)`（方向修正的直接断言，**这条断言现在会失败**，正是它证明了缺陷存在）。
- **风险高但收益最大**：这是整个质量门里唯一"方向错误"的指标，修好它同时解决 D-02、D-09（推进单元刷分）和绕过链的核心环节。**但门槛重定必须靠真实数据校准**，纯靠合成样本定出的门槛上线后会大面积误杀。**建议做法**：改完 D-02 与 D-16-c 后，先把 `density_floor` 设成一个**保守值**（如 4.0）上线观察，再逐步收紧。

### D-17（P3）EXTRACTABLE 边界注释的行号与实际不符

- **实测**（本轮 `grep -n "EXTRACTABLE"`）：

  | 注释所在行 | 注释内容 | 注释声称的范围 | 实际起始行 | 偏差 |
  |---|---|---|---|---|
  | 397 | `_pipeline_quality_gate.py (L381-L940)` | L381-L940 | 397 | 小（-16） |
  | 7165 | `_pipeline_story_scoring.py (L5881-L6281, ~400 lines)` | L5881-L6281 | 7165 | **大（-1284）** |
  | 7795 | `_pipeline_self_critique.py (L6506-L6782, ~276 lines)` | L6506-L6782 | 7795 | **大（-1289）** |

- **根因**：这三条注释是提交 `32eafd3`（`v3.1.2: pipeline_orchestrator 内部标记 3 个可提取模块边界注释`）加的，写的是**当时**的行号。之后文件继续增长约 1290 行，注释里的行号全部失效。
- **本轮新发现的第二个问题（比行号失效严重）：三条注释没有一条落在语句边界上，全部插在语句内部。** 修复时逐条确认，实际位置比第一版记录的更糟：
  - 397 那条插在 `_content_fingerprint` 的 `def` 与函数体第一行**之间**（即函数体内部），缩进还是 4 空格而非 8 空格。
  - 7165 那条插在 `STORY_PROGRESSION_MARKERS` 元组字面量内部，把一张词表劈成两半：
    ```python
    STORY_PROGRESSION_MARKERS = (
        "逼问", "质问", ... "追上", "救下",
    # ====== EXTRACTABLE: _pipeline_story_scoring.py (L5881-L6281, ~400 lines) ======
        "杀", "死", "活", ... "却", "但", "然而",
    )
    ```
  - 7795（修复时实际在 7742）那条插在 `return selected_index, {...}` 的 **dict 字面量内部**，把 `"flaws"` 与 `"suggestions"` 两个键劈开。

  三处语法上都合法（Python 允许字面量内注释），但注释宣告的「模块边界」全部落在数据结构或函数体中间——**按这些边界做模块提取会直接切断词表、切碎 return 语句**。这说明这三条注释是机械插入的，未经人工校验。
- **影响**：低（不影响运行），但会误导后续做模块提取的人（我本轮第一版文档就照抄了错的行号，见 4.x 的更正记录）；7165 / 7742 那两条如果真被当作切割点使用，会造成语法错误或词表丢失。
- **修复方案**：把行号从注释里**删掉**，只保留模块名与职责描述；同时把三条注释各自**移到所属语句/定义之前**（397 → `@staticmethod` 之前；7165 → `STORY_PROGRESSION_MARKERS = (` 之前；7742 → `async def _run_self_critique` 之前），让边界落在语句之间。行号注释注定会腐烂，不该写进代码：
  ```python
  # ====== EXTRACTABLE: _pipeline_story_scoring.py — 故事质量评分与事件密度 ======
  ```
- **✅ 已于批 1 修复**（2026-08-18）：三条注释去行号 + 全部移到语句之前，`STORY_PROGRESSION_MARKERS` 词数改前改后均为 **61**（用 `python -c "print(len(P.STORY_PROGRESSION_MARKERS))"` 改前改后各测一次），新增护栏测试 `test_extractable_comments_have_no_line_numbers`（正则 `EXTRACTABLE.*?L\d+` 断言 0 命中，改前 3 命中）。全量 **661 passed**。
- **不要**在这一轮做实际的模块提取（见第 10 节「明确不做」）。质量逻辑正在改，提取会让 diff 无法审查。
- **风险极低**：纯注释改动。

### D-18（P3）文档与提交信息里的测试基线数字过期

- **实测本轮基线**（**命令已作废，会假绿，D-26**；原文保留备查）：
  ```
  659 passed in 83.58s
  ```
- **过期的数字**：
  - 最近 5 条提交信息里反复写 `401/401`（`32eafd3`、`57e7e1c`、`f869ec3` 等）—— 已过期 258 个测试。
  - `CLAUDE.md` 的 `Latest Progress` 只写"backend quality guards 与 frontend quality display 回归套件通过"，没写数字，**这部分是准确的**（不需要改）。
  - 前序会话记录的 `648 passed in 51.41s` 也已过期（本轮 659）。
- **注意耗时变化**：51.41s → 83.58s。测试数只增加 1.7%，耗时增加 63%。可能是新增测试较重或机器负载差异，**本轮未深究**。若后续做性能相关工作，这是一条待查线索，但不属于质量优化范围。
- **修复方案**：不要在提交信息里写绝对测试数（它必然过期）。改写「全量通过」或「+N 新增测试全绿」。已有的历史提交信息不要改（会重写历史，违反硬约束）。
- **本文档的基线约定**：后续任何一步改动，都以**当批基线**为对照（批 2 完成后是 **668 passed**，见第 6.3 表逐批目标值）；如果新增了测试，基线相应上调，并在提交信息里写本次实测的总数（T-21）。

### D-19（P2，本轮新发现）`_score_fallback_candidate` 是必然抛 NameError 的死代码

- **实测确证**（本轮）：
  ```
  SIG: (*, content: 'str', violations: 'List[Dict[str, Any]]', chapter_mission: 'Optional[dict]') -> 'Dict[str, Any]'
  RAISED: NameError name 'target_word_count' is not defined
  ```
- **位置**：`pipeline_orchestrator.py:7364-7414`。签名（7367-7369）只有 3 个参数，函数体 7374-7382 却引用了 `target_word_count` 与 `min_word_count`：
  ```python
  target_floor = max(0, int(target_word_count or 0))     # NameError
  minimum_floor = max(0, int(min_word_count or 0))       # NameError
  ```
  模块级也没有同名全局变量（`grep -n "^target_word_count\|^min_word_count" → 0 结果`）。
- **为什么没在生产暴露**：`grep -rn "_score_fallback_candidate" app/` 只匹配到两处**定义**（生产 7364、孤儿 1157），**零调用点**。真正的多候选选择走 `_fallback_select_best_version`(7579)，它调用的是 `_score_story_quality_candidate`（7590）。所以这个函数从来没被执行过。
- **它证明了什么（比缺陷本身更重要）**：孤儿版同名函数（`story_quality_scoring.py:1157-1168`）的函数体里**没有**这段字数逻辑，直接从 `text` 走到 `paragraphs`。也就是说生产版这段字数代码是**从 `_score_story_quality_candidate` 复制过来时错位粘贴的**，且**没有任何测试覆盖能发现它**。这是「内联复制评分逻辑」这条技术路径已经造成真实错误的直接物证 —— 支撑 D-01 的结论（不要维护两份实现）。
- **修复方案（二选一，推荐 1）**：
  1. **直接删除** `_score_fallback_candidate`（7364-7414，51 行）。零调用、必崩、功能被 `_score_story_quality_candidate` 完全覆盖。删除后跑全量确认 659 仍绿。
  2. 若担心将来要用：补签名 `target_word_count: Optional[int] = None, min_word_count: Optional[int] = None`，并加一个直接调用它的单测。**但这等于再维护一份第三套评分逻辑，不推荐。**
- **验收**：删除后 `grep -rn "_score_fallback_candidate" app/` 只剩孤儿文件那一处（孤儿文件按 D-01 方案 B 最终整体删除）；全量 659 passed。
- **风险极低**：零调用点的死代码，删除不可能影响运行。这是**整份清单里性价比最高的一条**：改动明确、风险为零、清掉一个必崩函数。
- **✅ 已于批 1 修复**（2026-08-18）：按方案 1 删除生产文件里的 52 行（`@classmethod` 到 return 结束）。删除前重跑前置检查，确认 `grep -rn "_score_fallback_candidate"` 只有两处定义 + 探针脚本 `_cmp_scoring.py` 里的字符串，零调用点。新增护栏测试 `test_pipeline_has_no_dead_fallback_scorer`（`assert not hasattr(PipelineOrchestrator, "_score_fallback_candidate")`，改前红、改后绿；反向验证用 `setattr` 把属性放回去确认断言必红）。孤儿文件 `story_quality_scoring.py:1157` 那份**保留**，留给 T-19 整体删除。全量 **661 passed**。

### D-20（**P1，本轮新发现**）质量门的字数配置断链：4 个调用点全部落到硬编码默认值 3000/2000

- **✅ 已于批 7 修复（2026-08-19）**：`_evaluate_structural_quality_gate_for_content` 的 `target_word_count` / `min_word_count` **默认值已删除改成必填**，任何漏传当场 `TypeError`；8 个接线点全部补上从 `active_config` 取的实际值。**注意 `_fallback_select_best_version` 的默认值故意保留为 0**（中性）而不是同样删掉——它只做候选排序，缺配置时字数维度整体缺席比按错值判罚更安全。这个不对称在源码里写了注释、测试里各钉一条。真实目标字数有 16 个档位、跨度 800~10000，只有 9 条恰好是 3000（见 §11.2.1 批 7 表），这就是删默认值的依据。**本条以下内容保留为「当初怎么想的」备查。**

- **位置**：`_evaluate_structural_quality_gate_for_content`(430) 的签名 438-439 行：
  ```python
  target_word_count: int = 3000,
  min_word_count: int = 2000,
  ```
- **实测确证**（本轮 `grep -A7 "_evaluate_structural_quality_gate_for_content("`）：**全部 4 个调用点都没有传这两个参数**：

  | 行号 | 调用位置 | 传参 |
  |---|---|---|
  | 2098 | `_attempt_structural_gate_repair` 内的修复后重评 | ❌ |
  | 3716 | enrichment 前的质量门（`story_progression_guard_pre_enrichment`） | ❌ |
  | 3725 | enrichment 后的主质量门 | ❌ |
  | 3938 | 最终质量门 | ❌ |

- **后果**：质量门**永远**按 `target=3000, min=2000` 判定，与 `active_config.target_word_count` / `active_config.min_word_count` 完全脱钩。而 `PipelineConfig.min_word_count` 默认值是 **500**（`pipeline_orchestrator.py:114`），用户还能在 flow_config 里改（4403-4414）。所以：
  - 用户配 6000 字长章 → 质量门按 3000 判（长章节的密度/字数标准全部用错档位）。
  - 用户配 1500 字短章 → 质量门按 2000 判最低字数，比用户要求更严。
  - `_evaluate_event_density` 的档位（`<2500` / `<7000` / `>=7000`）用的是**实测 `word_count`** 而非配置值，所以不受这条影响；受影响的是所有以 `target_floor` / `minimum_floor` 为基准的判定。
- **与 D-13 的关系**：D-13 说的是「评分器函数体不用这两个参数」，D-20 说的是「调用链根本没把真实配置传进来」。**两条是串联的两处断点，只修一处等于没修**：
  - 只修 D-13（让函数体使用参数）→ 用的还是 3000/2000 默认值，仍然错。
  - 只修 D-20（把真实配置传进来）→ 函数体不用，仍然无效。
- **修复方案**：
  1. **删掉默认值**，改成必填 keyword-only 参数（`target_word_count: int` / `min_word_count: int`），让漏传变成 `TypeError` 而不是静默用错值。这是防止同类缺陷复发的关键——**默认值把配置断链变成了静默失败**。
  2. 4 个调用点补传：3716 / 3725 / 3938 在 `generate_chapter` 内，有 `active_config`，直接传 `active_config.target_word_count` / `active_config.min_word_count`；2098 在 `_attempt_structural_gate_repair` 内，签名里已有 `active_config`（2044），直接传。
  3. 与 T-12（D-13）在同一批次做，单独做没有意义。
- **验收**：改成必填后跑全量 —— 若有测试直接调 `_evaluate_structural_quality_gate_for_content` 而不传参，会立刻 `TypeError` 暴露出来，逐个补上真实值即可（这正是想要的效果）。新增一个测试：`min_word_count=6000` 的配置下，5000 字正文被判 `word_count_below_min=True`（当前实现会判 False，因为按 2000 比）。
- **风险中**：改成必填参数会让所有漏传点变成运行时错误，**必须一次改完 4 个调用点 + 所有测试调用点**，不能分两次提交。

### D-21（**P1，本轮新发现**）定向修复闭环只试一次且要求"全部 blocker 清零"，是加 blocker 的风险放大器

> **✅ 已于批 5（T-22）修复（2026-08-18）。** 下面 4 条修复方案里的前 3 条已落地：严格子集收缩判据、上限 2 轮、失败也留诊断。第 4 条（`enable_self_critique` 关闭时走确定性清理）依赖 T-17，批 5 只留了 `TODO(T-17/D-11)` 注释与 `repair_skipped_reason = "self_critique_disabled"`，**实际接线在批 10**。落地细节、返回值语义变更与反向验证记录见第 7 节「批 5 实际落地记录」。本条以下内容保留为「当初为什么要改」的备查，**行号是修复前的**。

- **位置**：`_attempt_structural_gate_repair`(2035-2116，**修复后约 2035-2241**)。
- **实测读代码确认的两个限制**：
  1. **只做一次修复**：2074 调用 `revise_chapter` 一次，没有重试循环。
  2. **要求重评完全通过**：
     ```python
     repaired_summaries, repaired_gate = self._evaluate_structural_quality_gate_for_content(...)
     if not repaired_gate.get("passed", False):
         return None      # ← 部分改善也当失败，整章走拒稿
     ```
     从 5 个 blocker 修到只剩 1 个，也返回 `None` → 调用方走「落库拒稿 + 422 拦截」（2053 注释明确说明）。修复成果**被整个丢弃**（`next_content` 不保留）。
  3. 另外它受 `enable_self_critique` 开关控制（2058）—— 关闭自评时**定向修复完全不可用**，质量门失败就是直接拒稿。
- **为什么这条必须先解决**：D-08（收紧静态检测）、D-10（新增重复段落 blocker）都会**提高 blocker 触发率**。在「一次修复 + 全清零才算成功」的机制下，blocker 越多 → 一次修复全清零的概率越低 → **拒稿率上升**。用户看到的不是"质量变好"，而是"生成一直失败"。这正是前序会话里 D-14 那两条自评豁免被加进来的原因（为了压误杀），**如果不先修这里，同样的补丁会被再加一次**。
- **修复方案（按优先级）**：
  1. **保留部分改善**：把 `if not repaired_gate.get("passed")` 改成「blocker 数量严格下降且没有新增 blocker 类型」即视为改善，采纳 `next_content` 并把新的 gate 状态写进元数据；只有当 blocker 完全没减少时才 `return None`。这样即使不能一次过门，正文也在变好，且下一轮修复从更好的起点开始。
  2. **允许最多 2 次修复**：第 2 次只针对第 1 次之后剩下的 blocker 构造 issues。**上限设 2，不要更多**（每次都是一次 LLM 调用，成本与耗时线性增长；见 2.4 成本约束）。
  3. **修复失败时也要保留诊断**：当前 `return None` 后调用方只有原始 gate 的 codes；应把「尝试修复过、修复后剩余哪些 blocker」写进 `runtime_metadata`，让前端能显示"已尝试自动修复，仍有 N 项未达标"，而不是让用户面对一个无解的 422。
  4. `enable_self_critique` 关闭时，至少要走确定性清理（T-17/D-11），不能完全无自愈手段。
- **验收**：构造一个有 3 个 blocker 的正文 + mock 的 `revise_chapter` 返回只修掉 2 个的版本 → 断言修复结果被采纳、`runtime_metadata` 记录剩余 1 个 blocker、不抛 422。
- **风险中**：改「采纳条件」会让原本拒稿的章节变成放行（带未达标标记）。**这是有意的权衡**：拒稿对用户价值为零，带标记的部分改善至少可用且可见。但必须确保前端把"未完全达标"显示清楚（前端展示层已就绪，见 3.3）。
- **不要另起设计——仓库里已有现成范式可照抄**：`longform_context_service.evaluate_continuity_quality`(709-840) 处理的是同类问题（一批检查项，有的致命有的只是瑕疵），它的三个设计恰好就是本条缺陷缺的东西：
  1. **blocker / warning 两级分档**，而非「通过或拒稿」二值。同一个 code 还能按严重度动态升级——`due_foreshadowing_not_visible` 在 `distance >= 12` 或 `importance in {"major","long",5}` 时才升为 blocker，否则留在 warning。
  2. **每条问题自带 `patch_suggestions`**（`strengthen_payoff_patch` / `local_payoff_patch`），把「哪里不对」变成「往这儿加这句」，修复提示词可以直接拼装，不需要让 LLM 自己猜。
  3. **依赖缺失时降级而不是失败**：`package is None` → `passed=True` + 一条 `longform_context_missing` warning。
  结构质量门现在这 11 类 blocker **全部是同一档**，没有 warning 层，也没有 patch 建议。**T-22 的实现应当把结构质量门改造成同构形态**（分档 + patch），这同时也是 E-11 的内容；两者是一条路上的两步，先做 T-22 的「保留部分改善」，再做 E-11 的「完整分档」。

### D-22（P3，本轮新发现）前端本地兜底文案漏了 `event_density_passed`

- **位置**：`frontend/src/utils/chapterQuality.ts:79-87`。
- **实测代码**：
  ```ts
  if (!backendLabels.length) {
    if (Number.isFinite(sceneRate) && sceneRate < 0.75) issues.push(`场景兑现 ${percent}%`)
    if (metrics.dialogue_changes_state === false) issues.push('对白未改局势')
    if (metrics.ending_pressure_passed === false) issues.push('章末未递压')
    if (metrics.static_description_risk === true) issues.push('静态描写偏高')
  }
  ```
  5 个维度里**只兜底了 4 个**，`event_density_passed === false` **没有任何兜底文案**。当后端没下发 `quality_issue_labels` 时（例如老章节的 metadata、或某条路径漏写 labels），事件密度不达标在前端**完全不可见**。
- **影响**：低（正常路径后端会下发 labels）。但事件密度恰好是 D-16 揭示的核心维度，它在前端的可见性不该有缺口。
- **一个顺带的好消息（对 T-13/T-14 很重要）**：前端用的是**严格比较** `=== false` / `=== true`，所以 T-13/T-14 把 `True` 改成 `None`（JSON `null`）之后，**前端天然不会把「未评估」误显示成「未通过」**（`null === false` 为 `false`）。**T-13/T-14 不需要改前端逻辑**，只需要在有余力时补一条「样本过短未评估」的中性提示。
- **修复方案**（**并入 T-14 一起做，不单独占一个任务编号**）：
  ```ts
  if (metrics.event_density_passed === false) issues.push(pick('事件密度不足', 'Event density too low'))
  if (metrics.event_density_evaluated === false) issues.push(pick('篇幅过短未评估密度', 'Too short to evaluate density'))
  ```
  第二条是中性提示，**tone 不应是 danger**（106 行的 tone 计算里要把它排除，否则「样本过短」会被显示成红色风险）。
- **验收**：前端 spec（`chapterQuality.spec.ts` 现 92 行）加两个用例：`event_density_passed: false` 且无 backendLabels → issues 含「事件密度不足」；`event_density_evaluated: false` → issues 含中性提示且 `tone !== 'danger'`。
- **风险零**（纯前端显示层新增分支）。

### D-23（P3，批 2 新发现）`_detect_chapter_artifact_markers` 的全角标点仍写成 `\uXXXX`

- **位置**：`pipeline_orchestrator.py:7381-7385`（`_detect_chapter_artifact_markers` 内的正则字符类）。
- **现象**：同一个字符类里半角与全角混写两种风格——`[|\uff5c:\uff1a\u3011]` 里 `|`、`:` 是字面量，而对应的全角 `｜`(`\uff5c`)、`：`(`\uff1a`)、`】`(`\u3011`) 写成转义；7382/7383 更别扭：开括号 `【` 是字面量、闭括号 `】` 却是 `\u3011`。
- **与 D-06 的区别**：这里**没有过拟合风险**（同行的中文关键词"场景/扩写/修订/完整章节正文/写作指令"本来就是字面量，只有分隔符被转义），所以**不是缺陷，只是可读性与风格一致性问题**。
- **影响**：低。审查时看不出正则到底匹配哪些分隔符，改动容易漏掉一侧括号。
- **修复方案**：把 5 行里的 `\uff5c` / `\uff1a` / `\u3011` 直接写成 `｜` / `：` / `】`。纯字面量替换，无行为变化。
- **验收**：`grep -no '\\u[0-9a-f]\{4\}' app/services/pipeline_orchestrator.py` 只剩 7046 行的正则中日韩范围 `[^\u4e00-\u9fff...]`（那个必须保留，是合法用法）。
- **建议归属**：并入批 10 的 T-17/T-18 清理批一起做，不单独占任务编号。

---

### D-24（**P1，批 4 新发现**）章末压力只看尾 260 字，短的坏结尾会被正文强钩子遮蔽

- **位置**：`pipeline_orchestrator.py:7542-7584`（`_evaluate_ending_pressure`，**行号已按批 5 校准**），第一行 `ending_excerpt = condensed_text[-260:]`（7543）。
- **现象**：尾窗是固定的 260 字**字符窗**，不是「最后一段」也不是「最后 N 句」。如果作者（或模型）在一段有张力的正文后面接一句短的泄气结尾，这句结尾进了窗口，**正文末尾的强钩子也一起进了窗口**，语义命中由正文提供，结尾的泄气被完全抵消。
- **实测证据**（批 4 建样本时撞上的，两组只差尾巴长度）：

| 构造 | 尾巴长度 | `quality_issue_codes` | score |
|---|---|---|---|
| `GOOD_DRAMATIC` + 标点疑问尾巴 | 38 字 | `[]` | 1302（**与正向对照完全相同**） |
| `GOOD_DRAMATIC` + 275 字扁平动作填充 + 同一句标点尾巴 | 275 字 | 含 `ending_pressure_missing` | 1042 |

  也就是说：**同一个坏结尾，只因为前面正文离得近，就从"必拦"变成"零代价通过"。**
- **同类构造里另一个样本没露出来，纯属词表运气**：`GOOD_DRAMATIC` + 短的「一切都平静下来」结尾**能**被拦住，原因只是这句话正好命中 `ENDING_CLOSURE_MARKERS` 的一票否决路径——一票否决不看语义命中，所以不受遮蔽影响。换句话说，两种结尾失败形态里，只有恰好落进收束词表的那一种能被短尾巴检出。这是 **D-04 过拟合问题的另一副面孔**：检出能力依赖词表命中，而不是依赖结构判定。
- **影响**：中。真实生成的章节结尾通常是 1-3 句（远短于 260 字），正文最后一段几乎必然被卷进尾窗，所以**生产环境里这个遮蔽是常态而非边角情况**。它会让 `ending_pressure_missing` 的召回率显著低于批 2 修复后应有的水平——批 2 修的是「标点不能顶替语义」，D-24 说的是「语义命中可能根本不来自结尾」。
- **修复方案**（**必须按 §11.2.1 做真实语料校准，不能凭直觉定**）：
  1. 尾窗改成结构化取样：先按换行切段，取最后 1-2 个非空段落；段落总长不足时再向前补，但**补进来的部分只用于凑最小长度，不参与语义命中计数**。
  2. 或者保留字符窗但**给窗口内的位置加权**：靠后的句子命中才算强信号，靠前的降为弱信号（复用批 2 的 weak/semantic 二分机制，改动面更小）。
  3. 无论走哪条，都要在 `quality_metric_snapshot` 里补一个「语义命中落在尾窗哪个位置」的可观测字段，否则误杀无法诊断（批 2 漏 `flat_closure_markers` 就是这个教训）。
- **验收**：短尾巴版 `BAD_PUNCTUATION_HOOK`（38 字尾巴）必须被拦；`GOOD_DRAMATIC` 正向对照必须仍然 `codes == []`；真实语料里历史通过样本的 `ending_pressure_passed` 通过率不得跌破 §11.2.1 校准出的下限。
- **建议归属**：**批 6**（与 T-08/T-09 静态描写同批，都属于"判定逻辑本身有洞"而非阈值问题）。批 4 只把它记为已知偏差，用 275 字填充绕开，**没有修**。
- **✅ 已于批 6 修复（2026-08-19），但修法与上面的设想相反**：上面建议缩小尾窗，**实测缩窗的 6 个变体全部更差**（真实通过池 0.475~0.782 vs 基线 0.812），那是误杀不是召回。实际做法是**保留 260 字尾窗、另加一道末段否决**：按换行切出最后一段，零语义钩子且（弱信号 >= 2 或长度 >= 150 字）则不通过。落地细节、变体对比表与归因见第 7 节「批 6 实际落地记录」与 §11.2.1 批 6 分位表。**本条以上内容保留为「当初怎么想的」备查。**

---

### D-25（P3，批 4 新发现，**✅ 批 6 已修**）`static_description_risk` 三条 or 里第 2/3 条没有任何坏样本覆盖

> **✅ 已于批 6 修复（2026-08-19），解法比下面的方案更严**：不是「补一个 `max_static_run >= 3` 的样本」，而是给**四条 or 各配一个只命中自己的样本**（`class TestStaticDescriptionRiskBranches`，内含 `_clause_flags` 归因辅助，每条测试都断言「本条 True 且其余三条全 False」）。理由：样本串味（同时命中两条）时改坏任一条都不会红，那正是 D-25 的成因。另加一个卡在门槛边界的哨兵样本 `STATIC_RUN_AT_LIMIT` 钉住第 2 条的阈值本身。见第 7 节「批 6 实际落地记录」。

- **位置**：`pipeline_orchestrator.py:7669-7673`（`static_description_risk` 的三条 or，**行号已按批 5 校准**）。
- **现象**：批 4 反向验证时把 `_estimate_static_description_runs` 改成恒返回 `{"static_paragraph_count": 0, "max_static_run": 0}`，`test_all_description_sample_is_blocked` **仍然绿**。原因：`BAD_ALL_DESCRIPTION` 实测是 **1 个段落 / 2313 字 / `dialogue_marker_count == 0`**，命中的是第一条 or（`dialogue_markers == 0 and paragraph_count <= 4 and word_count >= 1800`），而它的 `max_static_run` **实测本来就是 0**（那唯一一段里含"漫过/洒在/摇曳/透过"等动作词，按 `_estimate_static_description_runs` 的判定不算静态段）。
- **影响**：低，但会掩盖回归。第 2 条（`word_count>=1500 and max_static_run>=3`）和第 3 条（`word_count>=2500 and event_density_passed is False and max_static_run>=2`）目前**没有任何测试守着**，改坏了不会有测试变红。
- **修复方案**：在 T-08/T-09 动静态描写判定时，**顺手补一个多段样本**——若干段每段 ≥100 字、且刻意不含 `action_markers`（连自然现象动词也不能有，见 D-08 后半），使 `max_static_run >= 3`，断言 `max_static_run` 与 `static_description_risk` 一起成立。这样三条 or 才都有覆盖。
- **验收**：把 `_estimate_static_description_runs` 改成恒返回 0 时，新样本的测试必须红。
- **建议归属**：批 6，T-08 的验收项之一（不单独占任务编号）。

---

### D-26（**P0，2026-08-19 新发现，优先级高于本文档所有其它条目**）测试 runner 假绿：`asyncio_mode = auto` 与 `anyio` 插件冲突，进程猝死且退出码为 0

- **位置**：`backend/pytest.ini`（`asyncio_mode = auto`）＋ `backend/conftest.py:23-25`（`anyio_backend` fixture）＋ 各处 `@pytest.mark.anyio`。
- **现象**：跑全量或跑较大目录时，pytest **静默死掉**——不抛异常、不打 traceback、输出缓冲区整个丢失。`-q` 模式下 shell 拿到的退出码是 **0**，看起来像"跑完了、全绿"；只有 `-v` 才能看到真实 `RC=1` 和"走到某个测试就没有下文"。崩溃点**随测试组合漂移**，所以单跑必过、合跑必崩，极易被误判成"环境抖动"。
- **控制变量实证**（同一文件、同一顺序，只差一个开关）：

| 命令 | 结果 |
|---|---|
| `pytest app/api/routers/test_style_profile_job.py` | `RC=1`，输出 0 字节，11 个 PASSED 后无下文 |
| 同上 **`-p no:anyio`** | **`19 passed in 15.28s`，`RC=0`** |

- **根因**：`plugins:` 行显示 `anyio-4.12.1` 与 `asyncio-1.3.0` 同时加载。`asyncio_mode = auto` 让 pytest-asyncio 接管**所有**协程测试，**包括**那些标了 `@pytest.mark.anyio`、本该由 `conftest.py` 的 `anyio_backend` fixture 驱动的。两个插件在不同事件循环上驱动同一个协程，进程不走栈展开就终止，缓冲区来不及 flush。
- **影响（这是本条排 P0 的理由）**：**本文档与所有历史提交里的每一个"全量 N passed / 全绿"结论都是假的**（见 4.1 作废表）。更严重的是它的长期后果——在被修正之前，**任何人改任何代码，都无法知道有没有破坏别处**。批 2-8 的定向测试不受影响（同步测试，不碰 anyio），所以"各批改对了没有"仍有证据；但"没有破坏别处"从未被验证过。
- **修复方案**（三条路，**倾向第 2 条**）：
  1. 门禁命令永久加 `-p no:anyio`：最小改动，已验证有效，但把配置问题藏进了命令行，新人照 `pytest -q` 跑还是假绿。
  2. **统一异步栈**：把 `@pytest.mark.anyio` 全部换成 pytest-asyncio 的标记（或反之），删掉多余的那个插件依赖。改动面大但根治，且让裸 `pytest` 也是可信的。
  3. `pytest.ini` 里 `asyncio_mode = strict` + 显式标记：介于两者之间，需要给现有异步测试逐个补标记。
- **验收**：裸跑 `python -m pytest app -q`（**不带任何 `-p no:`**）必须给出与门禁命令一致的 `passed/failed` 数，且退出码与结果一致（有失败时非 0）。
- **顺带记两个次级环境陷阱**（同一次排查踩到，写在这里省得别人再踩）：
  - **seleniumbase 硬拦 `--timeout`**：抛 `Don't use --timeout=s from pytest-timeout! Use --time-limit=s instead!` 并直接退出。必须 `-p no:seleniumbase -p no:sb_manager`。
  - **后台命令的 `cd` 不跨调用保持**：必须在同一条命令里 `cd backend && python -m pytest ...`，否则报 `file or directory not found: app`。
- **建议归属**：**批 8-F 之前的第 0 步**。在 runner 可信之前做任何优化，都是在没有仪表的情况下开车。

---

### D-27（**P0，2026-08-19 新发现**）36 个先存失败：28 个方法从未被实现（spec-first 欠账）＋ 8 个真实行为分歧

- **来源**：D-26 修正 runner 后首次拿到完整结果 `727 passed, 36 failed`。**这 36 个不是本轮改坏的**——它们一直存在，只是被 anyio 崩溃掩盖着从没跑到过。
- **A 组：9 个方法从未被实现，牵连 28 个失败。**

| 缺失方法 | 失败数 | 涉及文件 |
|---|---|---|
| `_detect_generation_meta_leakage` | 5 | `test_generation_quality_guards.py` |
| `_extract_segment_text` | 5 | `test_longform_segment_streaming.py` |
| `_rebind_generation_run_if_needed` | 4 | `test_generation_run_rebind.py` |
| `_summarize_generation_error` | 2 | `test_generation_quality_guards.py` |
| `_normalize_generated_prose` | 2 | `test_generation_quality_guards.py` |
| `_strip_leading_generation_meta` | 1 | 同上 |
| `_resolve_writer_prompt_budget` | 1 | 同上 |
| `_build_lean_chapter_mission` | 1 | 同上 |
| `_resolve_scene_split_generation_soft_timeout` | 1 | `test_cloud_provider_resilience.py` |

  余下 6 个失败是同批测试里 `orchestrator.guardrails`（测试自身对 `object.__new__` 实例的 setup，**不是**缺失方法）等连带项。

- **"从未被实现"是怎么坐实的**（不是"可能被 checkout 擦了"，这点很重要，别再往恢复方向浪费时间）：
  1. `git show HEAD^:...pipeline_orchestrator.py | grep -c "def <name>"` → 0
  2. 当前工作区 `grep -c` → 0
  3. `git log --all --oneline -S"def <name>"` → 0（全历史、全分支都没出现过）
  4. **决定性一条**：扫描 `~/.claude/projects/D-------xuanqiong-wenshu/` 下**全部 154 个 transcript**（含 `subagents/` 与 `subagents/workflows/` 子目录），统计针对 `pipeline_orchestrator.py` 的 `Edit`/`Write`/`MultiEdit` 记录 → **恰好 97 次，全部来自主会话，且已全部重放**。而同期对**测试文件**的 48 次编辑完好无损。
  → 结论：**测试先写、实现没写**。这是 spec-first 留下的欠账，不是代码丢失。
- **A 组的好消息**：测试把契约钉得很死，照着写不用猜。举证（`test_generation_quality_guards.py:142-215`）：
  - `_summarize_generation_error`：`LongformGenerationContractError` → 以 `"LongformGenerationContractError:"` 开头且 `len <= 360`；`HTTPException(503, detail={"code": "UPSTREAM_TIMEOUT", "message": "Provider 超时"})` → **精确等于** `"UPSTREAM_TIMEOUT: Provider 超时"`（结构化 detail 优先于状态码）。
  - `_detect_generation_meta_leakage`：返回**命中标记列表**（`"the user wants"` / `"let's design"` / `"need at least"` / `"我来设计"` / `"让我写"`）；对 `"The lantern shook. 林七没有回头。"` 必须返回 `[]`；**对 `"林七沿着潮湿的石阶往下走。" * 180 + 泄漏句` 也必须返回 `[]`** —— 即存在**头部窗口上限**，与 D-24 的末段窗口是同一设计思路（只扫开头，不深入正文）。
  - `_strip_leading_generation_meta`：`"They want:\n- Target: 1200 characters\n\nLet me design it.\n---\nDraft:\n顾沉推开门…"` → 精确剩下 `"顾沉推开门，看见火光贴着墙根逼近。"`（以 `---` / `Draft:` 为草稿边界）。
  - `_resolve_writer_prompt_budget`：`(1200) == 1800`（1.5×）、`(5000) == 6000`（1.2×）→ 两段不同倍率。**它是既有三件套的缺失成员**：`_resolve_chapter_generation_max_tokens`（`pipeline_orchestrator.py:1561`）与 `_resolve_chapter_generation_soft_timeout`（同文件 `:1331`）都已存在且被 8 处调用。这说明这批方法是当前架构的既定组成部分，不是凭空发明。
  - `_build_lean_chapter_mission`：`mission["generation_source"] == "local_short_chapter_contract"`；`continuity_anchor["inherit_from_previous"] == [previous_tail]`；`scene_list[0]["word_budget"] == target_word_count` 且 `conflict` / `end_hook` 非空。
- **B 组：8 个真实行为分歧**（实现与测试的约定不一致，**必须先判"哪边对"再动手**）：

| 断言 | 实现实际值 | 测试预期 | 性质 |
|---|---|---|---|
| `_resolve_chapter_mission_timeout(700)` | `30.0` | `20.0` | 阈值约定不一致 |
| `_resolve_chapter_generation_max_tokens(700)` | `3200` | `2200` | 阈值约定不一致 |
| `_build_stable_retry_config(short)` | 返回 `PipelineConfig` | `None` | 短章不该走整章重试 |
| `_build_stable_retry_config(longform)` | 返回 `PipelineConfig` | `None` | 长章同上 |
| `guard["dialogue_state_change_markers"]` | `0` | `>= 2` | **落在批 8 T-13 上，见下** |
| `'mission_progression_weak' not in reasons` | 在里面 | 不该在 | 原因码进出不符 |
| `'word_count_far_below_target' not in reasons` | 在里面 | 不该在 | 原因码进出不符 |
| `'chapter_progression_weak' in blockers` | 不在（实际是 `insufficient_dialogue_pressure` / `static_description_risk`） | 该在 | 原因码进出不符 |

- **B 组第 5 行要单独记一笔（对批 8 的结论有修正作用）**：`test_dialogue_state_guard_recognizes_concrete_revelation_choice_and_external_pressure` 期望该样本的 `dialogue_state_change_markers >= 2`，实测 **0**。这**不是**三态逻辑（T-13）写错了——三态的 21 项定向测试与 24 项文本变异反向验证都通过——而是 **`_count_dialogue_state_change_markers` 的标记识别覆盖不足**：该样本里的"具体揭示 / 做出选择 / 外部压力"三类语义，词表一个都没认出来。
  → **所以 T-13 不能算完全闭环**：判定的三分支结构对了，但喂给它的标记计数偏低，会让本该 `True` 的样本落到"未声明预期 + 计数不足门槛"那条路。修法属于词表扩充（与 D-06 章末压力词表过拟合同类问题），**必须走真实语料校准**（§11.2.1），不能凭直觉加词。
- **建议归属**：A 组 = **批 8-F**（新实现，9 个方法）；B 组 = **批 8-G**（先定性再改，其中 `dialogue_state_change_markers` 词表扩充需真实语料校准）。两批都必须在 D-26 修好之后做。

---

## 6. 优化方案总表

### 6.1 任务编号与执行顺序（**这一节是接手后的行动清单**）

排序原则：**先做零风险的清障与观测，再做有依赖前置的核心指标修复，最后做需要真实数据校准的权重与豁免调整。** 不要按缺陷编号顺序做——D-01/D-02 编号在前但依赖在后。

| # | 任务 | 对应缺陷 | 优先级 | 风险 | 改动量 | 前置 |
|---|---|---|---|---|---|---|
| **T-01** | 删除 `_score_fallback_candidate` 死代码 | D-19 | P0 | 零 | −51 行 | 无 |
| **T-02** | ✅ 已完成（批 2）`ENDING_CLOSURE_MARKERS` 去掉裸 `"一切都"`，换 7 个完整收束短语；**未采用**"强钩子优先"（偏差理由见 D-04） | D-04 | P0 | 低 | ~5 行 | 无 |
| **T-03** | ✅ 已完成（批 2）三张词表提为类属性 + 语义命中作必要条件（比原方案的 `strong_non_punct_hooks` 更彻底，副词也降为弱信号） | D-03 | P0 | 中 | ~20 行 | T-02 |
| **T-04** | ✅ 已完成（批 3）引号句需另有推进词或对话状态改变词 + 词表剔出 `却/但/然而/转而/下一步/活` 到 `WEAK_TRANSITION_MARKERS` | D-02（双根因） | P0 | 中高 | ~15 行 | T-01 |
| **T-05** | ✅ 已完成（批 3）新增 `_window_has_state_change`（占比 **0.05** + 最少 2 句）与尾窗合并；占比不是起点值 0.25，理由见批 3 落地记录 | D-16-c | P0 | 中 | ~30 行 | T-04 |
| **T-06** | ✅ 已完成（批 3）阈值提成 `_event_density_floors` 类方法，由 147 条真实语料两轮校准定值；`plain_run_limit` 换成 `plain_run_ratio_limit` | D-16-a/b | P0 | 高 | ~40 行 | T-04, T-05 |
| **T-07** | ✅ 已完成（批 4）`class TestBadSampleRegression` 9 条测试 / 5 个坏样本 + 1 个正向对照锚点；覆盖 5 种已实现的失败形态（8 个样本里 3 个依赖 D-10/D-12/E-07，顺延到对应批次），顺带修了 `flat_closure_markers` 观测性漏项 | D-05 | P0 | 零 | +约 170 行测试 + 1 行生产 | T-02…T-06 |
| **T-22** | **增强定向修复闭环（保留部分改善 + 最多 2 次 + 失败也留诊断）** | D-21 | **P0** | 中 | ~50 行 | T-07 |
| **T-08** | 移植静态描写第 4 条分支 + 对齐阈值 | D-08（前半） | P1 | 低 | ~8 行 | **T-22** |
| **T-09** | 动作词加主体约束 + 自然现象动词拆出 `AMBIENT_MOTION_MARKERS` | D-08（后半） | P1 | 中 | ~25 行 | T-08 |
| **T-10** | 移植重复段落检测 + 判罚 + 第 12 类 blocker | D-10 | P1 | 低 | ~45 行 | 无 |
| **T-11** | ✅ 已完成（批 7）四来源采集 + 占位符过滤 + 判罚 −240 + 四个快照字段；**保持 warning 不加 blocker，单独一条测试钉住** | D-12 | P2 | 低 | ~45 行 | 无 |
| **T-12** | ✅ 已完成（批 7）四层断链全修；`upper` 系数用 2.0/1.6（1.25 会让误杀率涨 25 倍）；第 3 层删默认值改必填、第 4 层默认值取 0，**两层故意不对称**，理由见批 7 落地记录 | D-13 + **D-20** | P1 | 中高 | ~55 行 | T-01 |
| **T-13** | `dialogue_changes_state` 改三态 | D-07 | P1 | 中高 | ~25 行 | T-07 |
| **T-14** | 事件密度短路返回值改 `None` + `evaluated` 标记 **+ 前端补 event_density 兜底文案（D-22）** | D-15 + **D-22** | P2 | 低 | ~15 行 + 前端 ~4 行 | T-06 |
| **T-15** | ✅ 已完成（批 2）42 个 `\uXXXX` 还原 + 剔 10 个专有词 + 补通用词到 56 个 + 加 grep 护栏测试；**孤儿版 `story_quality_scoring.py` 未动，留 T-19** | D-06 | P1 | 中 | ~35 行 | T-03 |
| **T-16** | 重配评分权重（形式项降权、质量项加权、加反转项） | D-09 | P1 | 高 | ~30 行 | T-04…T-13 |
| **T-17** | 移植确定性清理与 Markdown 呈现清理 | D-11 | P2 | 中 | ~120 行 | T-10 |
| **T-18** | 自评豁免加观测 → 调阈值 | D-14 | P2 | 高 | ~20 行 | T-03, T-06 |
| **T-19** | 删除孤儿文件 `story_quality_scoring.py` | D-01 | P2 | 低 | −1525 行 | T-10…T-17 |
| **T-20** | EXTRACTABLE 注释去掉行号 | D-17 | P3 | 零 | ~3 行 | 无 |
| **T-21** | 提交信息约定改为「全量通过/增量」 | D-18 | P3 | 零 | 0 行 | 无 |
| **T-23** | **修 runner 假绿：统一异步栈（`asyncio_mode` 与 `anyio` 二选一）** | **D-26** | **P0** | 中 | ~30 行配置＋标记 | **无（必须最先做）** |
| **T-24** | 实现 9 个从未落地的方法（契约已由测试钉死） | **D-27 A 组** | P0 | 高 | ~350 行 | T-23 |
| **T-25** | 定性并修 8 个行为分歧（阈值 4 项 / 原因码 3 项 / 词表 1 项） | **D-27 B 组** | P1 | 中 | ~40 行 | T-23 |
| **T-26** | `_count_dialogue_state_change_markers` 词表扩充（**须真实语料校准**） | D-27 B 组第 5 行 | P1 | 中 | ~20 行 | T-25 |

> **T-23 是新的关键路径起点。** 它排在 T-01 之前——在 runner 会静默吞测试的前提下，
> 其余任何任务的"全量全绿"验收都无法成立（D-26）。

### 6.2 依赖图（关键路径）

```
T-01 ──┬─→ T-04 ──→ T-05 ──→ T-06 ──┬─→ T-07 ──→ T-22 ──┬─→ T-08 ──→ T-09 ──┐
       │                             │            │      │                   │
       └─→ T-12 ────────────────────┤            │      └─→ T-10 ──→ T-17 ──┤
                                     │            │                          │
T-02 ──→ T-03 ──→ T-15 ─────────────┤            └─→ T-13 ─────────────────┤
                          ↘ T-18 ←──┘                                        │
T-11 ────────────────────────────────────────────────────────────────────────┤
                                                                             │
                                                        T-14 ────────────────┤
                                                                             ↓
                                                      T-16 ──→ 端到端真实生成验证 ──→ T-19
T-20 / T-21（独立，随时可做；注意 T-21 是"提交信息约定"，别和缺陷编号 D-21 混淆）
```

**关键路径是 `T-01 → T-04 → T-05 → T-06 → T-07 → T-22 → T-13 → T-16`。** 这条链上任何一步跳过，后面的门槛校准都会用错误的数据基线。

**T-22 是整张图的闸门**：它在 T-07（测试固化）之后、T-08/T-09/T-10（三个会提高 blocker 触发率的任务）之前。**先做 T-22 再加 blocker**，否则拒稿率上升会掩盖质量改善，重演 D-14 那种"加自评豁免压误杀"的补丁。

### 6.3 分批提交建议（每批独立可回滚，每批跑全量）

> **执行状态**：
> - 批 1 ✅ 已完成（2026-08-18，实测 `661 passed in 71.45s`，与下表目标值一致）。
> - 批 2 ✅ 已完成（2026-08-18，实测 **`668 passed in 97.11s`**，比下表目标 666 多 2 个——多出来的是两条防误杀/防回归对照：`test_ending_pressure_still_blocks_complete_flat_closure`（改完 D-04 不能反过来放行真平淡）和 `test_quality_metric_snapshot_exposes_ending_pressure_hit_counts`（新增计数字段必须进前端读的那份扁平快照）。符合下方说明第 1 条"多出来是正常的"）。
> - 批 3 ✅ 已完成（2026-08-18，实测 **`679 passed in 94.61s`**，比下表目标 674 多 5 个。多出来的原因：阈值第一版用合成样本定，在真实语料上误杀 95%，重定阈值时补了 3 条真实分布护栏 —— `test_event_density_uses_plain_run_ratio_not_absolute_run`（新字段必须过 snapshot 白名单）、`test_state_change_window_rate_survives_real_corpus_ratio`（真实密度的正文必须过窗口门）、`test_state_change_window_needs_two_hits_when_sentences_are_long`（长句正文里只有句数条件能拦单句推进）；另有 1 条改名 `..._to_sentence_level_units` → `..._to_real_corpus_distribution`。详见第 7 节「批 3 实际落地记录」）。
> - 批 4 ✅ 已完成（2026-08-18，实测 **`688 passed in 118.20s`**，比下表目标 687 多 1 个。多出来的原因：T-07 要求的「与正向对照分差 ≥300」在结尾类样本上做不到（实测两个都正好 260），只能拆成两条测试——密度类 `>=300`、结尾类 `>=200`，于是分差检查从 1 条变成 2 条。三处与 T-07 原方案的偏差见第 7 节「批 4 实际落地记录」）。
> - 批 5 ✅ 已完成（2026-08-18，实测 **`691 passed in 61.34s`**，比下表目标 690 多 1 个。多出来的原因：T-22 原方案只要求 +2（保留部分改善、失败留诊断），实际拆成 4 条新增测试——「部分改善必须采纳」「换了一种毛病必须拒绝」「轮数上限恰好是 2」「自评关闭时也要留 `repair_skipped_reason`」，另有 1 条既有测试改名并反转断言（`..._rejects_revision_that_does_not_pass_gate` → `..._adopts_partial_improvement`），所以净增 3 而不是 2。详见第 7 节「批 5 实际落地记录」）。
> - 批 6 ✅ 已完成（2026-08-19，实测 **`718 passed in 55.80s`**，比下表目标 696 多 22 个。多出来的原因：D-25 从「补 1 个静态连段样本」升级成「四条 or 各配一个只命中自己的互斥样本 + 阈值哨兵」，D-24 又额外带出 7 条末段否决测试。详见第 7 节「批 6 实际落地记录」）。
> - 批 7 ✅ 已完成（2026-08-19，实测 **`742 passed`**，比下表目标 725 多 17 个。多出来的原因：T-11 的「保持 warning 不加 blocker」与 T-12 的「第 3/4 层默认值故意不对称」各需单独测试钉住，另有 upper 系数不单调、三判罚不进 blocker 等 4 条防回退护栏。详见第 7 节「批 7 实际落地记录」）。
> - 批 8-10 待办。**下一批基线按 742 起算**；下表批 8-10 的目标值请在表值上再 +45。

| 批次 | 含任务 | 预期效果 | 新增测试（按第 7 节逐任务标注相加） | 跑完这批的全量应为 |
|---|---|---|---|---|
| **批 1（清障）** | T-01, T-20, T-21 | 无行为变化，清掉必崩死代码 | +2（T-01 +1、T-20 +1、T-21 +0） | **661 passed** ✅ 实测 661 |
| **批 2（章末压力）** | T-02, T-03, T-15 | 章末压力门不再被标点绕过、不再误杀、不再过拟合 | +5（+1 / +2 / +2）→ 实际 +7 | **666 passed** ✅ 实测 **668** |
| **批 3（事件密度，核心）** | T-04, T-05, T-06 | 事件密度门方向修正，灌水对话不再拿满推进 | +6（+3 / +1 / +2）→ 实际 **+11** | **674 passed** ✅ 实测 **679** |
| **批 4（回归测试）** | T-07 | 5 种已实现的失败形态固化 + 1 个防误杀锚点 | +8 → 实际 **+9** | **687 passed** ✅ 实测 **688** |
| **批 5（修复闭环，加 blocker 前必做）** | **T-22** | 部分改善不再被丢弃，拒稿率不随 blocker 增加而爆炸 | +2 → 实际 **+3** | **690 passed** ✅ 实测 **691** |
| **批 6（静态与重复）** ✅ | T-08, T-09, T-10 | 纯描写与复制段落被拦下（**外加 D-24 尾窗遮蔽、D-25 静态连段覆盖缺口**） | 计划 +5，**实际 +27** | ~~718 passed~~ **假绿（D-26）** |
| **批 7（字数与人物）** ✅ | T-11, T-12 | 候选选择考虑字数与焦点人物；质量门用真实配置 | 计划 +7，**实际 +24** | ~~742 passed~~ **假绿（D-26）** |
| **批 8（三态与短路）** ✅ | T-13, T-14 (+D-22) | 「没测过」不再冒充「通过」；前端 `null` 不显示成风险 | 计划 +7，**实际 +21** | 定向 **167 passed, 21 failed**（可信） |
| **T-23（修 runner）** ⏳ | **D-26** | **裸 `pytest` 也能给出可信数字** | 0（改配置） | **首个真正可信的全量值** |
| **T-24 / T-25 / T-26** ⏳ | D-27 | 9 个方法落地 + 8 项分歧定性 + 词表校准 | 0（让现存 36 条转绿） | 目标 **763 passed, 0 failed** |

> **这张表从批 6 起的「全量」列已不可用**（D-26）。批 8 起改为记录**定向测试的完整形态**
> （`N passed, M failed`），因为定向测试是同步的、不受插件冲突影响，是当前唯一可信的证据。
> T-23 完成后，本列恢复记录全量值。
| **批 8（三态与短路）** | T-13, T-14 | 消除「零对话却说对话改变局势」等假阳性 | +5（+3 / +2） | **730 passed**（前端 `chapterQuality.spec.ts` 另 +2，见 D-22） |
| **批 9（权重重配）** | T-16 | 好坏分差从 20% 提到 ≥45% | +2 | **732 passed**，**影响面最大** |
| **批 10（清理与收尾）** | T-17, T-18, T-19 | 确定性清理生效，孤儿文件删除 | +6（+3 / +2 / +1） | **738 passed** |

**合计 +79（批 2 实际 +7、批 3 实际 +11、批 4 实际 +9、批 5 实际 +3、批 6 实际 +27，故终值约 738 passed）**；前端 `vitest` 另 +2。批 7-10 的目标值已按批 6 的实际增量整体上移，估算增量本身未改。

**批次之间必须跑全量**，且**批 3、批 9 之后建议做一次真实生成端到端验证**（见 8.4），因为这两批改的是判定方向与权重，单测无法反映真实文本分布。

关于上面这两列数字，四点必须说清楚：

1. **它是下限估算，不是承诺值。** 每批增量直接来自第 7 节每个任务末尾的「**全量**：+N」标注（例如批 3 的 +6 = T-04 的 +3 + T-05 的 +1 + T-06 的 +2）。实际写测试时为了补防误杀对照，往往会多 1-2 个，**多出来是正常的，少了才要回头查是不是漏写了断言**。
2. **批 3 / 批 7 / 批 8 / 批 9 会让既有测试变红**（第 7 节在 T-04、T-12 步骤 B、T-13 步骤 1、T-16 各自标了）。变红后**不要直接改断言让它变绿**——先判断是「修复误杀了合法样本」（那是修复的问题）还是「原测试固化了错误行为」（那才改测试，并在提交信息里写明改了哪条、为什么）。这个判断错了，整批修复就白做。
   - **批 3 实测更正**：既有 93 条一条都没红，两个必查的防误杀测试（1501 `..._allows_dense_progression_despite_local_plain_run`、1556 `..._accept_dense_scene_sequel_progression`）靠尾窗合并与放宽连段条件保持绿。真正变红的是**本批自己新写的护栏**：第一版阈值全绿，是真实语料校准把它推翻的——这说明**这类判断不能只靠既有测试的红绿，必须另跑真实语料**。
3. **只统计后端 `pytest` 的数**。前端 `vitest` 独立计数（当前 `chapterQuality.spec.ts` 92 行），只有批 8 会动它。不要把两边的数加在一起写进提交信息。
4. **实测与预期不符时，以实测为准并当场更新本表**（本表就是这么被修正的：原先写的 +35/694 是早期估算，与第 7 节逐任务标注相加的 +48/707 矛盾，已按第 7 节校正）。

### 6.4 增强性优化方案（E 系列 · 不是缺陷修复，是能力新增）

**与 D/T 系列的区别**：D 系列是「现有机制坏了或被绕过」，修完只是回到设计意图；E 系列是「设计意图本身不够」，需要新增能力。**执行顺序上 E 系列一律排在 T 系列之后**——在事件密度门方向都反着的情况下（D-16）加新维度，只会加更多噪声。唯一例外是 E-01，它是最上游杠杆，可以与 T 系列并行推进。

**优先级判断依据**：越靠上游越省钱。提示词（E-01）在生成前生效，不合格内容根本不会产生；质量门在生成后生效，只能拒稿或重修，每次重修都是一次 LLM 调用。所以**E-01 的期望收益高于整个 T 系列**，但它的验证成本也最高（必须真实生成对比，没有单元测试能证明提示词更好）。

---

#### E-01（收益最高·验证最难）写作提示词与写作契约：纳入版本控制 + 内容优化

**现状实测**（本轮核实，与前序记录有出入，以本轮为准）：提示词**不是**「全在数据库」，而是**分两层**：

| 层 | 位置 | 是否可版本控制 | 是否可回归测试 |
|---|---|---|---|
| 主写作提示词 `writing_v2` / `writing` | **数据库**（`prompt_service.get_prompt(name)`，`prompt_service.py` 97 行） | ❌ 无 diff、无 review、无回滚 | ❌ |
| 章节写作契约（硬指令） | **代码**：`_resolve_chapter_draft_contract`(1201)、`_format_chapter_draft_contract_for_prompt`(1254)、`_build_prompt_sections`(5593)、场景执行清单(5504-5524)、`_build_prose_only_system_prompt`(6761) | ✅ | ✅ |
| 多候选风格差异提示 | 代码：`_resolve_style_hints`(5702) | ✅ | ✅ |

- 代码层的写作契约**质量已经相当高**，不要重写。摘录 5486-5524 的实际指令：
  ```
  场景衔接规则：下一段必须吃住上一段留下的动作、情绪或风险，不要只靠关键词拼接。
  对话硬要求：只要进入对话场，至少两轮来回，其中一轮必须改变主动权、信息量或风险级别。
  承接上章时必须落地：{inherit_from_previous 前 3 项}
  章末必须递交的新压力：{deliver_to_next 前 3 项}
  N. 场景X | 建议篇幅 NNN 字左右
     - 本场必须完成 / 正面阻碍 / 本场转折 / 情绪变化 / 对话职责 / 收尾钩子
     - 开场要求：尽快把人物拉进动作、试探、威胁或决策，不许只铺环境。
     - 过渡要求：本场结尾必须自然推出下一场，不要用总结句硬切。
     - 章末要求：必须让局势相比章首发生实质变化，再把压力递到下一章。
  ```
  **这套指令与质量门的 5 个维度基本对齐**（场景达成、对话改变状态、章末压力、静态描写、事件密度），说明提示词侧已经在要求正确的东西。**这反过来是一个重要判断：生成质量差不是因为没告诉 LLM 要什么，而是因为质量门没有真正把不合格的挡住**（见 D-16），所以 LLM 没有被迫改进。
- **E-01 要做的两件事，第一件优先**：
  1. **把 DB 提示词落盘为 seed**：新增 `backend/app/db/seeds/prompts/writing_v2.md`（先跑 `SELECT name, LENGTH(content) FROM prompts` 导出现网内容，不要凭空写），在 `init_db.py` 里做「不存在则插入、存在则不覆盖」的幂等 seed。**必须不覆盖**——现网 DB 里的可能是用户手工调优过的版本，覆盖就是破坏用户成果（违反 2.2 硬约束）。落盘后提示词才有 diff、才能 review、才能回滚。
  2. **内容优化**：只有在第 1 件完成、且 T 系列批 3（事件密度）上线后再做。方向是把质量门的判罚项翻译成正向指令（例如 D-10 上线后加「同一段落不得重复出现」）。**每次改动必须留真实生成前后对比**（见 E-08），否则无法证明变好还是变差。

**风险**：E-01.1 零风险（纯新增文件 + 幂等插入）。E-01.2 风险高且不可测——提示词改动会同时影响所有维度，且没有单元测试能捕获退化，只能靠 E-08 的批量评测兜底。**没有 E-08 之前不要动提示词正文。**

#### E-02（P2）新增「转折/反转达成度」维度

- **为什么需要**：CLAUDE.md 明确把「反转」列为目标，但**质量门里没有任何一项在检测反转**。实测 `grep -n "reversal|turn_detected" pipeline_orchestrator.py` → **0 结果**。现在唯一与 `turn` 有关的处理是：
  - 提示词侧要求「本场转折：{scene.turn}」（5513）——只是要求，没有校验；
  - `_collect_fallback_mission_keywords`(6988) 把 `scene.turn` 的文本混进一个 24 项的泛化关键词词袋，用于 fallback 场景达成度的字符串命中——**这不是反转检测**，命中「转折」这两个字或 turn 描述里的任意名词都算。
- **设计**（不要做成纯词表，会重演 D-06 的过拟合）：
  ```python
  REVERSAL_SIGNALS = (
      # 预期落空
      "并不是", "根本不是", "竟然", "居然", "反而", "原来", "却是", "出乎",
      # 立场/主动权翻转
      "翻脸", "倒戈", "反制", "反手", "夺回", "被反", "自己也",
      # 信息颠覆
      "谎", "假的", "伪造", "另有", "真正的", "早就",
  )
  ```
  判定要**双条件**：`REVERSAL_SIGNALS` 命中 ≥1 **且** 命中位置落在正文后 60% 区间（反转出现在开头往往是承接上章，不算本章反转）。命中数与位置写进快照：`reversal_signal_count` / `reversal_in_late_section`。
- **接入方式（关键：先只观测，不判罚不 block）**：
  1. 第一步只把 `reversal_signal_count` / `reversal_in_late_section` 加进 `story_quality_metrics` 快照与日志，**不参与评分**。
  2. 跑真实生成收集 20+ 章的分布，看好章与差章是否真的分得开。
  3. 只有分布可区分时，才加判罚（建议 −160，弱信号弱判罚），并且**永远不要做成 blocker**——反转的表达方式太多，字符串检测的召回率注定不高，做成 blocker 必然大量误杀。
- **验收**：`GOOD_DRAMATIC` 样本（箱子里不是黄金而是妹妹照片）→ `reversal_signal_count >= 1` 且 `reversal_in_late_section is True`；`BAD_FLAT_CHATTER` → `reversal_signal_count == 0`。
- **风险低**（只观测阶段为零风险）。**这是 E 系列里最该先做的一条**，因为它能直接回答「生成的小说有没有反转」这个 CLAUDE.md 一级目标问题，而当前完全没有数据。

---

#### E-03（P3）人物声音区分度（对话是否千人一面）

- **问题**：现在的对话检测只数引号（`dialogue_marker_count`）和状态变化词，**完全不看是谁在说**。LLM 的典型退化是所有角色用同一种腔调说话，读者感觉「像同一个人自言自语」。
- **可行的确定性指标**（不需要 LLM 判断）：
  1. **说话人分布**：用 `「某某说/道/问」`、`"…"某某` 的模式提取说话人，算 `speaker_count` 与最大占比 `dominant_speaker_ratio`。单人占比 >0.85 且 `speaker_count >= 2` 是一个可疑信号（任务书要求多人对话但实际一个人说了绝大多数）。
  2. **句长分布差异**：把每个说话人的台词平均长度算出来，若所有说话人的均值标准差 < 3 字，说明台词长度完全同质（真实人物的语速/句长差异较大）。
  3. **句尾语气词分布**：`吗/呢/吧/啊/罢了/而已` 等在不同说话人间的分布是否有差异。
- **优先级低的理由**：这三个指标都是**弱相关**指标，中文对话提取本身准确率有限（无提示语的连续对话很难归属说话人），投入产出比不如 E-02。**建议只做指标 1（说话人分布），做成纯观测项**，指标 2/3 留待有真实数据后再评估。
- **风险低**（纯观测）。**不要做成判罚**——「一章里主要由一个人说话」在审讯、独白、电话场景里完全正常。

#### E-04（P2）动作 / 对话 / 描写三分配比

- **现状**：只有单向的「静态描写风险」（`_estimate_static_description_runs`，见 D-08）与「引号计数」，**没有配比概念**。所以两种极端都可能通过：全是描写（被 D-08 修好后能挡住一部分）、全是对话（当前完全挡不住，见 D-02/D-16）。
- **设计**：按段落分类，算三个比例，写进快照：
  ```python
  # 段落分类（互斥，按优先级判定）
  # 1. dialogue  : 含引号
  # 2. action    : 含动作动词（推/抓/冲/砸/拔/按/闯/逃/追/救/摔/夺…）且无引号
  # 3. description: 其余（含风景/心理/说明）
  dialogue_ratio / action_ratio / description_ratio  # 三者和为 1
  ```
- **判定（宽区间，只挡极端）**：只在**明显失衡**时给弱判罚，不设 blocker：
  - `description_ratio > 0.70` → −200（几乎全是描写）
  - `dialogue_ratio > 0.80` → −200（几乎全是对话，即「剧本化」，D-02 修好后这条是补充防线）
  - `action_ratio < 0.05 且 word_count >= 1500` → −120（整章没有任何身体动作）
  - **中间区间一律不判罚**。理由：不同题材的合理配比差异巨大（言情对话多、悬疑描写多），任何"理想配比"都是过拟合。
- **依赖**：必须在 D-08（静态检测修复）之后做，否则 `description_ratio` 与静态判罚会重复计分同一个问题。
- **验收**：`BAD_ALL_DESCRIPTION` → `description_ratio > 0.9` 且被判罚；`BAD_FLAT_CHATTER` → `dialogue_ratio > 0.8` 且被判罚；`GOOD_DRAMATIC` → 三个比例都在中间区间，**零判罚**（这条断言是防误杀的核心）。
- **风险低-中**：新增两条判罚会拉低部分正常章节的分数。因为不是 blocker，最坏后果是候选排序变化，不会造成拒稿。

---

#### E-05（P3）场景转换清晰度

- **现状**：提示词已经明确要求「过渡要求：本场结尾必须自然推出下一场，不要用总结句硬切」（5522），但**没有任何检测**。`_evaluate_scene_fulfillment` 只做 `scene_list` 关键词命中，不看场景之间是怎么切的。
- **可检测的坏模式**（这些是确定性的，误报率低）：
  - **硬切**：段落以「第二天」「几天后」「另一边」「与此同时」开头，且**前一段末尾没有任何压力信号**（无 `deliver`/悬念/未完成动作）→ 说明是用时间副词硬跳，不是自然过渡。
  - **总结句收尾**：段落末尾出现「就这样」「一切都」「日子就这样」「从此」+ 句号 → 已被 D-04 的章末检测部分覆盖，但 D-04 只看章末，这里看**每个场景末**。
  - **场景数与任务书不符**：`scene_list` 有 5 个场景，正文只有 2 个明显场景边界。
- **实现难点**：「场景边界」在中文正文里没有可靠标记（不像剧本有 INT./EXT.）。只能用启发式（空行 + 时间/地点副词开头）。**准确率有限，所以定 P3 且只做观测**。
- **建议**：只实现第 2 项（场景末总结句），因为它复用 D-04 已有的 `closure_markers` 词表，成本极低；第 1、3 项留待 E-08 有真实数据后评估。
- **风险低**（观测项）。

---

#### E-06（P3）多候选差异化增强

- **现状（已较好，不要重写）**：`_resolve_style_hints`(5702-5714) 已经给三个候选不同的风格指令：
  ```python
  ["冲突推进优先，描写只服务情绪与动作，避免空转内心戏和静态景物铺陈",
   "冲突更强，节奏更快，多写动作和对话博弈",
   "悬念更重，多埋伏笔，结尾钩子更强，但不要牺牲当前章的动作推进"][:version_count]
  ```
- **可改进点**：这三条都是「同一方向的不同强度」（都在要冲突），差异化不足 → 三个候选会高度相似，多候选的择优价值被削弱。真正的差异化应该是**处理方式不同而非强度不同**：
  - 候选 A：**从冲突最激烈处切入**（in medias res），把铺垫后置。
  - 候选 B：**先给一个错误判断再推翻**（把本章的反转前置到中段）。
  - 候选 C：**以对话博弈为主线**，动作作为对话的后果出现。
- **前置条件（重要）**：**在评分器可靠之前不要做这件事**。当前评分器无法区分好坏（D-09/D-16），差异化候选只会让「随机选一个」变成「随机选一个更不一样的」。必须等 T-16（权重重配）完成、能证明好样本分数显著高于坏样本之后再做。
- **验收**：三个候选的 `story_quality_metrics` 在至少 2 个维度上有可观测差异（不是随机噪声级别）；被选中的候选分数显著高于未选中的（差值 ≥300）。
- **风险低**（只改提示词拼装，不改判定逻辑）。但**验证成本高**，需要真实生成（见 E-08）。

#### E-07（P1·E 系列里价值第二高）`inherit_from_previous` 从未被确定性校验

- **本轮全库实测**（`grep -rn "inherit_from_previous" backend/app`，共 9 处生产代码消费点），逐一核对后结论是：**没有一处在检查正文是否真的承接了上一章**。
  | 位置 | 实际做的事 | 是校验吗 |
  |---|---|---|
  | `pipeline_orchestrator.py:1427-1429` | JSON Schema 声明字段必填 | ❌ 只约束任务书结构 |
  | `pipeline_orchestrator.py:1469-1471` | 清洗/截断字符串 | ❌ |
  | `pipeline_orchestrator.py:5126` | 从上一章锚点生成 `inherit_from_previous` | ❌ 生产方 |
  | `pipeline_orchestrator.py:5498-5499` | 拼进提示词「承接上章时必须落地：…」 | ❌ 只是要求 |
  | `pipeline_orchestrator.py:6974` | 混入 `_collect_fallback_mission_keywords` 的 24 项泛化词袋 | ❌ 泛化关键词命中，非承接校验 |
  | `ai_review_service.py:242-245` | 拼进 review 清单「必须承接：…」 | ❌ 交给 LLM 主观判断 |
  | `pipeline_chapter_mission.py:130/208/382/659` | 任务书生成与合并 | ❌ 生产方 |
- **对比**：`deliver_to_next` 反而**有**确定性校验（章末压力门通过 `continuity_anchor.deliver_to_next` 动态注入词表，见 D-06 的 `test_generation_quality_guards.py:896-897`）。也就是说**「递给下一章」被检查了，「承接上一章」没有** —— 这是章节断裂感最直接的来源，而 CLAUDE.md 把「章节连续性」列为一级目标。
- **设计（与 `deliver_to_next` 的检查对称，代码可复用）**：
  ```python
  # 与章末压力门的 deliver 注入完全对称：把 inherit 项拆成关键词，检查是否出现在正文【前 40%】
  inherit_items = (chapter_mission.get("continuity_anchor") or {}).get("inherit_from_previous") or []
  # 承接必须发生在章节开头段，写到中后段说明是补写而不是承接
  head_section = condensed[: max(1, int(len(condensed) * 0.4))]
  inherit_hits = [item for item in keywords if item in head_section]
  ```
  返回 `inherit_keyword_count` / `inherit_hit_count` / `inherit_hits_in_head` / `continuity_inherit_missing`。
- **判罚与分档（学连续性门，见 D-21 的范式）**：
  - 一个都没命中且 `inherit_items` 非空且 `word_count >= 1200` → 判罚 −280 + **warning** `continuity_inherit_missing`。
  - **不做 blocker**：`inherit_from_previous` 是 LLM 生成的自然语言短句（如「门外传来三声不该出现的敲击」），正文完全可以用不同措辞承接同一件事（「敲门声又响了三下」），字符串匹配必然漏判。
  - 命中但都在后 60% → 弱 warning `continuity_inherit_late`（不判罚，只观测）。
- **附带产出**：这条实现后，`patch_suggestions` 可以直接给出「在开篇 200 字内落地：{未命中的 inherit 项}」，接进 T-22 的定向修复。这是**唯一一条既能诊断又能自动生成修复指令的新增项**。
- **验收**：任务书 `inherit_from_previous: ["门外脚步声逼近"]`，正文全篇不提脚步 → `continuity_inherit_missing=True`、−280、warning 出现在快照；正文开篇就写「脚步声已经到了门外」→ 命中（**注意这个用例会漏判，因为字符串是「门外脚步声逼近」而正文是「脚步声已经到了门外」**——测试要如实断言当前实现的行为，并在测试名里标出 `_exact_match_only`，把局限固化下来而不是假装解决了）。
- **风险低**（warning + 弱判罚，不 block）。

---

#### E-08（P0·所有提示词改动的前置条件）离线批量真实生成质量评测

- **为什么是 P0**：E-01（提示词）、E-06（候选差异化）、T-16（权重重配）这三项**都无法用单元测试证明有效**。单元测试只能证明「给定这段文本，评分器给出预期分数」，不能证明「改完之后 LLM 写得更好」。没有 E-08，这三项就是盲改。
- **设计（离线脚本，不进生产路径）**：新增 `backend/scripts/quality_bench.py`（**不是测试文件，不进 pytest 收集范围**）：
  1. 固定 N 个章节任务书（建议 N=10，覆盖开篇/对话章/动作章/过渡章/收束章），**固化到 `backend/scripts/bench_missions/*.json`** —— 任务书必须固定，否则每次基准都在变。
  2. 对每个任务书跑一次完整 `generate_chapter`，落 `runs/{timestamp}/{mission_id}.json`（含正文、`story_quality_metrics`、gate 结果、耗时、token）。
  3. 汇总成一行一章的 CSV + 一个汇总表：各维度通过率、平均分、blocker 分布、平均字数、平均耗时、token 成本。
  4. 与上一次基准 diff，输出「哪个维度变好、哪个变差」。
- **必须遵守的约束**：
  - **成本可控**：10 章 × 3 候选 = 30 次 LLM 调用，跑一次要真金白银。**默认 N=3 的 smoke 模式，完整 N=10 只在提示词改动前后各跑一次。**
  - **正文脱敏**：汇总 CSV 里**只存指标不存正文**；正文单独落在 `runs/` 并加进 `.gitignore`（遵守 2.6 证据脱敏约束：不提交用户小说正文）。
  - **可离线复算**：所有指标必须能从已落盘的正文重新算一遍（这样改评分器后不用重新生成就能对比），即脚本要支持 `--rescore-only runs/{timestamp}`。
- **验收**：能跑通 `python -m scripts.quality_bench --smoke`，产出 3 章的指标表；`--rescore-only` 能对同一批正文用新评分器重算并 diff。
- **风险低**（离线脚本，不改生产路径）。**但这是唯一能回答「优化到底有没有用」的工具**，建议在 T 系列批 3 之后立刻做，让批 9（权重重配）有据可依。

#### E-09（P2）质量指标的跨章趋势可观测性

- **现状实测**：指标只存在两个地方，**都是单章视角**：
  1. 章节 `metadata["quality_metrics"]`（`pipeline_orchestrator.py:2001`，值取自 `story_guard["quality_metric_snapshot"]`）与 `metadata["quality_gate"]`（1994）。
  2. SSE 事件与 `runtime_metadata["quality_gates"]`（2284 起，含 `prompt_section_count` / `prompt_estimated_tokens` / `stable_retry_reason` / `partial_candidate_salvage_used` 等运行期字段）。
- **缺口**：`grep -n "quality" backend/app/api` 的结果里**没有任何跨章聚合端点**（只有 `foreshadowing.py` 的伏笔分析分数和 `writer.py` 的 `outline_quality`）。所以现在无法回答这几个问题：
  - 这本书 40 章里，哪些章的 `event_density_passed=False`？
  - 加了 D-10 重复检测之后，blocker 触发率是升了还是降了？
  - `ending_pressure_missing` 的自评豁免（D-14）到底触发了多少次？（**这是 D-14 提阈值的前置数据，没有它就只能拍脑袋**）
- **设计（最小实现，不要建新表）**：
  1. 新增只读端点 `GET /api/novels/{novel_id}/quality-trend`，遍历该书所有章节的 `metadata["quality_metrics"]` 与 `metadata["quality_gate"]`，返回逐章的 5 维通过与否、分数、blocker codes、字数。
  2. **不新建数据库表**（避免 Alembic 迁移，遵守 2.2「禁止不可逆迁移」）。指标已经在 metadata JSON 里，聚合在应用层做即可。数据量级是几十到几百章，全表扫可接受。
  3. 前端在写作台加一个折叠面板，展示逐章色块（绿/黄/红）+ blocker 计数条形图。前端质量展示组件已就绪（见 3.3），复用 `chapterQuality.ts` 的字段映射即可。
- **附带价值**：D-14（自评豁免提阈值）、T-16（权重重配）、E-02（反转检测是否可判罚）**都需要这个端点提供的分布数据**。它是所有「调阈值」类决策的依据来源。
- **验收**：造 3 章不同质量的 metadata → 端点返回 3 行，字段与单章一致，`blocker_code_counts` 聚合正确；空 metadata 的老章节不报错（返回 `null` 占位而非 500）。
- **风险低**（纯只读聚合，不改写路径）。

---

#### E-10（P2）`chapter_mission` 自身的质量校验

- **问题**：整条质量链路都建立在「章节任务书是好的」这个假设上。但任务书本身是 LLM 生成的（`pipeline_chapter_mission.py`），如果任务书写得空（`scene_list` 只有 1 个场景、`turn` 写成「让局势发生变化」这种同义反复、`inherit_from_previous` 为空），那么：
  - 场景达成度检查退化成「命中 1 个关键词就算达成」；
  - 章末压力门的动态词表为空 → 只能靠通用词表（正是 D-06 过拟合的场景）；
  - `dialogue_changes_state` 因 `expected_dialogue` 为空而恒真放行（**这正是 D-07 的触发条件**）。
  **即：任务书质量差会让整套质量门集体失效，而现在没有任何检查。**
- **实测线索**：提示词侧的默认值兜底（5511-5516）用的就是同义反复文案：`str(scene.get('turn') or '让局势发生变化')`、`str(scene.get('conflict') or '制造明确阻碍')`。也就是说任务书字段缺失时，喂给 LLM 的是一句无信息量的话，而**系统不知道自己在喂废话**。
- **设计**：在 `generate_chapter` 消费任务书之前加一次确定性体检，结果写进 `runtime_metadata["mission_quality"]`：
  | 检查项 | 条件 | 级别 |
  |---|---|---|
  | `mission_scene_too_few` | `len(scene_list) < 2` 且 `target_word_count >= 2000` | warning |
  | `mission_turn_placeholder` | `scene.turn` 命中兜底文案或长度 < 6 字 | warning |
  | `mission_inherit_empty` | 非首章且 `inherit_from_previous` 为空 | warning |
  | `mission_dialogue_strategy_empty` | `dialogue_strategy` 缺失（→ 会触发 D-07 恒真） | warning |
  | `mission_focus_placeholder` | `focus_characters` 全是占位符（「主角」「男主」） | warning |
- **关键设计取舍**：**全部是 warning，不 block、不重新生成任务书**。重新生成任务书成本高（一次 LLM 调用）且可能陷入循环。第一步只要「知道任务书是空的」，就能在评分时对相应维度做**降权而不是白给通过**（例如 `dialogue_strategy` 为空时，`dialogue_changes_state` 返回 `not_applicable` 而非 `True`——这与 D-07 的三态方案正好合流）。
- **依赖**：与 D-07（三态）同批做最省事，两者共用「任务书是否声明了对话预期」这个判断。
- **验收**：空任务书 `{}` → 5 条 warning 全出；完整任务书 → 0 条。
- **风险低**（纯观测 + 与 D-07 合流）。

#### E-11（P1）结构质量门改造成「blocker / warning 分级 + patch_suggestions」

- **这是 T-22 的延伸终点，也是整个质量体系的目标形态**。T-22 解决「部分改善不要丢」，E-11 解决「一开始就不该把所有问题当同一档」。
- **现状**：结构质量门的 11 类问题**全在同一档**——任何一条命中就是 blocker，就走「落库拒稿 + 422」。没有 warning 层，没有严重度动态判定，没有修复建议。所以只有两个出口：完美通过，或者用户看到一个失败的章节。
- **现成范式（不要另起设计，仓库里已有）**：`longform_context_service.evaluate_continuity_quality`(709-840) 处理同类问题的三个做法：
  1. `blockers` 与 `warnings` 两个列表分开返回，`passed` 只看 `blockers`。
  2. 同一 code 按严重度动态升档：`due_foreshadowing_not_visible` 在 `distance >= 12` 或 `importance in {"major","long",5}` 时进 `blockers`，否则进 `warnings`。
  3. 每条问题带 `patch_suggestions`（`strengthen_payoff_patch` / `local_payoff_patch`），把「哪里不对」变成「在这里加这句」。
- **11 类问题的建议分档**（以修完 T 系列后的可靠度为依据）：
  | 类别 | 建议档位 | 理由 |
  |---|---|---|
  | 字数不足 / 远超上限 | **blocker** | 判定 100% 可靠（数字比较） |
  | 章节污染标记（`chapter_artifact_markers`） | **blocker**，但**先走确定性清理**（T-17）再判 | 可清理的问题不该拒稿 |
  | 重复段落洪水（D-10 新增） | **blocker**（精确重复）| 判定可靠（字符串完全相同） |
  | 事件密度不足 | blocker（**T 系列修完门槛校准后**） | 修好前不可靠，见 D-16 |
  | 章末压力缺失 | blocker | 修好 D-03/D-04 后较可靠 |
  | 场景达成度不足 | **warning**（现为 blocker） | 依赖关键词命中，措辞变体会漏判 |
  | 静态描写风险 | blocker（D-08 修完后） | 段落级统计，较可靠 |
  | 对话未改变状态 | **warning**（现为 blocker） | D-07 三态后仍依赖词表 |
  | 焦点人物缺席（E-01 系列新增） | **warning** | 别名/称谓会误判，见 D-12 |
  | 跨章承接缺失（E-07 新增） | **warning** | 措辞变体必然漏判 |
  | 反转缺失（E-02 新增） | **永久 warning** | 表达方式过多，永远不该 block |
- **patch_suggestions 的最小可用形态**：不需要 LLM 生成，可以按 code 模板化拼装：
  ```python
  PATCH_TEMPLATES = {
      "ending_pressure_missing": "把结尾改成未解决状态：{deliver_to_next 首项}，不要用总结句收束。",
      "continuity_inherit_missing": "在开篇 200 字内落地上一章遗留：{未命中的 inherit 项}。",
      "dialogue_state_change_missing": "至少一轮对话要改变主动权、信息量或风险级别：{dialogue_strategy.purpose}。",
      "static_description_heavy": "把第 {段号} 段起的连续描写改成人物动作或对话，保留不超过 2 句环境。",
      "repeated_paragraph_flood": "删除重复段落，只保留首次出现（重复片段：{片段前 20 字}…）。",
  }
  ```
  这些 patch 直接喂给 T-22 的 `revise_chapter`，比现在只给 code 列表的定向修复准确得多。
- **验收**：一个只有 `scene_fulfillment` 与 `dialogue_state_change` 两项不达标的正文 → `passed=True`（因为两项都是 warning）、`warnings` 有 2 条、每条带 patch 文案；一个字数不足的正文 → `passed=False`。
- **风险中-高**：把 4 项从 blocker 降为 warning 会**显著提高放行率**。**这是有意的**——当前的高拒稿率来自不可靠的判定，降档后靠判罚分数在多候选排序里起作用（比 block 更温和）。**但必须在 T-16（权重重配）之后做**，否则判罚不起作用又不 block，等于什么都不做。
- **顺序结论**：`T-22（保留部分改善）→ T-16（权重重配）→ E-11（分档 + patch）`，不能跳步。

---

### 6.5 E 系列汇总与执行顺序

| 编号 | 内容 | 优先级 | 风险 | 前置 | 能否用单测验证 |
|---|---|---|---|---|---|
| E-08 | 离线批量真实生成评测脚本 | **P0** | 低 | 无 | 部分（脚本自身可测） |
| E-01.1 | DB 提示词落盘为 seed | P1 | 零 | 无 | ✅ |
| E-07 | `inherit_from_previous` 确定性校验 | P1 | 低 | 无 | ✅ |
| E-11 | 质量门分级 + patch | P1 | 中-高 | T-22, T-16 | ✅ |
| E-02 | 反转/转折检测（先只观测） | P2 | 低 | 无 | ✅ |
| E-04 | 动作/对话/描写配比 | P2 | 低-中 | D-08 | ✅ |
| E-09 | 跨章质量趋势端点 | P2 | 低 | 无 | ✅ |
| E-10 | 任务书自身体检 | P2 | 低 | 与 D-07 合流 | ✅ |
| E-01.2 | 提示词正文优化 | P2 | **高** | E-08, T 系列批 3 | ❌ 只能靠 E-08 |
| E-03 | 人物声音区分度（只做说话人分布） | P3 | 低 | 无 | ✅ |
| E-05 | 场景转换清晰度（只做场景末总结句） | P3 | 低 | D-04 | ✅ |
| E-06 | 多候选差异化增强 | P3 | 低 | T-16 | ❌ 只能靠 E-08 |

**执行顺序（在 T 系列 10 批之后，或按标注并行）**：

```
E-08（评测脚本，可与 T 系列并行，越早越好）
  └→ E-01.2 / E-06（提示词类，必须有 E-08 才能验证）

E-01.1（seed 落盘，零风险，随时可做）

E-07 → E-02 → E-09 → E-10 →（此时 T-22/T-16 已完成）→ E-11
                              └→ E-04（需 D-08）
                              └→ E-03 / E-05（P3，有余力再做）
```

**一句话结论**：如果只能做三件 E 系列的事，做 **E-08（否则无法验证任何提示词改动）、E-07（唯一既能诊断又能自动修复的新增项）、E-11（把「拒稿」变成「带标记放行 + 修复建议」）**。

---

## 7. 每个任务的详细执行说明（T-01～T-22）

**通用执行协议（每一条任务都要走完，来自 2.3 硬约束，不可省略）**：

1. **先写失败测试**：新增能证明缺陷存在的测试，运行确认**红**（如果新测试一开始就绿，说明缺陷判断错了，停下来重新分析，不要改实现）。
2. **实现修复**，跑定向测试确认**绿**。
3. **反向验证**：临时把修复里的关键条件故意改坏（例如把新加的阈值改回原值），确认新增测试**必然变红**；恢复实现。这一步是防止「测试其实没测到修复」。
4. **跑全量门禁**：用 §2.3 的**四开关命令**（不是裸 `pytest app -q`，那会假绿，D-26），与基线 `727 passed, 36 failed` 对比；**并拿 `-rf` 清单和 D-27 的表逐条核对失败集合有没有变大或换人**。
5. **记录证据**：命令、输出尾部（含 passed 数与耗时）、受影响测试清单。**不记录密钥、Prompt 正文、用户小说正文**（2.6）。

**通用验证命令**（cwd 必须是 `backend`，`PYTHONIOENCODING=utf-8` 防 GBK 乱码）：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -p no:randomly -p no:anyio -q
```

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && python -m pytest app -p no:randomly -p no:anyio -p no:seleniumbase -p no:sb_manager -q --timeout=120 --timeout-method=thread -rf
```

> **Windows/bash 环境注意**：`cd` **不跨 Bash 调用持久**（本轮已因此踩坑一次，见 4.x）。每条命令都要自带 `cd`，或全部用绝对路径。不要用 `&&` 串接长命令链（前序会话中多次因此被截断），改用 `;` 分隔并在末尾加 `echo "===EXIT $?==="` 确认退出码。

---

### 批 1：清障（T-01 / T-20 / T-21）—— 零风险，先做完让后面干净

#### T-01 删除死代码 `_score_fallback_candidate`（对应 D-19）

- **位置**：`backend/app/services/pipeline_orchestrator.py:7364-7414`（约 51 行，起止以 `def _score_fallback_candidate` 到下一个 `def` 之前为准，**动手前先重新 grep 行号**，文件在变）。
- **前置检查（必须做，证明真的零调用）**：
  ```bash
  cd /d/小说写作/xuanqiong-wenshu/backend && grep -rn "_score_fallback_candidate" app | grep -v "def _score_fallback_candidate"
  ```
  期望输出：**只有 `story_quality_scoring.py`（孤儿文件）里的定义，没有任何调用**。如果出现调用点，**停止**，改为修 `NameError`（补两个参数）而不是删除。
- **改动**：删掉 `pipeline_orchestrator.py` 里的整个 `_score_fallback_candidate`。**只删生产文件里的**，孤儿文件留给 T-19 整体删除。
- **测试**：新增 `test_pipeline_has_no_dead_fallback_scorer`：
  ```python
  def test_pipeline_has_no_dead_fallback_scorer():
      assert not hasattr(PipelineOrchestrator, "_score_fallback_candidate")
  ```
  **反向验证**：删除前先加这条测试 → 必须红；删除后 → 绿。
- **全量**：`659 passed` → `660 passed`（+1）。
- **回滚**：`git diff` 单文件恢复即可（不要用 `git checkout --`，用编辑器撤销或从 `git show HEAD:` 取原内容手工贴回）。

#### T-20 EXTRACTABLE 注释去行号 + 移出元组内部（对应 D-17）

- **位置**：`pipeline_orchestrator.py` 三处：397、7165（**在 `STORY_PROGRESSION_MARKERS` 元组内部**）、7795。
- **改动**：
  1. 三条注释全部删掉 `(L____-L____, ~N lines)` 部分，只留 `# ====== EXTRACTABLE: <模块名> — <职责> ======`。
  2. **把 7165 那条移到 `STORY_PROGRESSION_MARKERS = (` 这一行之前**，让模块边界落在语句之间而不是元组字面量中间。
- **测试**：新增 `test_extractable_comments_have_no_line_numbers`，读源文件、正则 `EXTRACTABLE.*L\d+` 断言 0 命中。**反向验证**：改前跑 → 红（3 命中）。
- **全量**：+1（`661 passed`）。
- **风险零**（纯注释）。注意别手滑删掉元组里的词，改完立刻跑 `python -c "from app.services.pipeline_orchestrator import PipelineOrchestrator as P; print(len(P.STORY_PROGRESSION_MARKERS))"` 确认词数不变（改前先记下这个数）。

#### T-21 提交信息里的测试数约定（对应 D-18）

- **问题**：`32eafd3` 等提交信息写「401/401」，实际基线已是 659。历史提交信息不能改（会重写历史，违反 2.2），要改的是**往后的约定**。
- **改动**：不是代码改动，是流程约定，写进 `CLAUDE.md` 的 Latest Progress 段（**只加一行，不要重写整个文件**）：
  ```
  - 提交信息里的测试数必须是本次实测输出，写成 `N passed, M failed` 完整形态（不许只写 passed 数）。
    全量命令必须带 `-p no:anyio -p no:seleniumbase -p no:sb_manager -p no:randomly`，裸跑会假绿（D-26）。
  ```
- **另外**：`CLAUDE.md` 现有内容**不需要改**——它没有写具体测试数字，那部分是准确的（这一点前序文档写错过，见 4.1）。
- **测试**：无（流程约定）。
- **全量**：不变（`661 passed`）。

---

### 批 2：章末压力门（T-02 / T-03 / T-15）—— 判定最不可靠的一环

#### T-02 从 `closure_markers` 移除 `"一切都"`（对应 D-04）✅ 已完成（2026-08-18，批 2）

> **实际落地**：采用方案 A（完整收束搭配），词表最终为 `ENDING_CLOSURE_MARKERS`（类属性，14 项）。**未采用** D-04 里"强钩子压过 closure"的第二半——偏差理由与新增的防回归测试见 D-04。测试名按本节约定落为 `test_ending_pressure_keeps_hook_when_closure_prefix_appears`（不是下面写的 `..._allows_unknown_hook_with_yiqiedou`，改名是为了和 D-04 验收行一致）。`grep -n "一切都" app/services/test_*.py` 已复核：改动前测试里对该词零依赖。

- **位置**：`pipeline_orchestrator.py` 的 `_evaluate_ending_pressure` 内 `flat_closure_markers` / `closure_markers` 词表（动手前 grep `closure_markers` 定位）。
- **证据**（探针 `_probe_bypass.py` 已验证，见 4.x）：真钩子句「而幕后是谁，**一切都**还是未知」被判 `flat_closure_markers` 命中 → 章末压力**误判为平淡收束**。而不含该词的同义句「仍旧无人知道」正常通过。
- **根因**：`"一切都"` 是**中性前缀**，后面接什么决定语义：
  - 平淡收束：「一切都过去了」「一切都很好」「一切都恢复了平静」
  - 强钩子：「一切都还是未知」「一切都不对劲」「一切都才刚刚开始」
- **改动（二选一，推荐方案 A）**：
  - **方案 A（简单可靠）**：直接把 `"一切都"` 从词表删除，改为收录**完整的收束搭配**：`"一切都过去了"`、`"一切都恢复"`、`"一切都很好"`、`"一切都结束了"`、`"一切都平静"`。
  - 方案 B：保留 `"一切都"` 但加否定后缀白名单（`未知/不对/没有结束/才开始/变了`）。**不推荐**——白名单永远列不完，是 D-06 同类的过拟合。
- **测试**：新增 `test_ending_pressure_allows_unknown_hook_with_yiqiedou`，断言探针里那句真钩子 `ending_pressure_passed is True` 且 `flat_closure_markers` 为空。**反向验证**：改前跑 → 红。
- **全量**：+1。**同时检查**现有测试里是否有依赖「`一切都` 会被判平淡」的断言（`grep -n "一切都" app/services/test_*.py`），有则一并调整样本。

#### T-03 章末压力不能只靠标点（对应 D-03）✅ 已完成（2026-08-18，批 2）

> **实际落地**：下面的伪码就是最终实现（`generic_pass = bool(semantic_hits) and (len(semantic_hits) + len(weak_hits)) >= 2`），但**弱信号集合比原计划大**：除 `？ ? ！ !` 四个标点，还把 `却` / `突然` / `忽然` 三个纯副词降为弱信号（它们在任何句子里都可能出现，原先算实质钩子）。三张词表同时提为类属性以便测试直接断言。另新增 `ending_semantic_hit_count` / `ending_weak_hit_count` 两个可观测字段并补进 `quality_metric_snapshot`。6 个既有 ending_pressure 测试逐条推演后全绿，无需改样本。

- **位置**：同 `_evaluate_ending_pressure`。
- **证据**（探针已验证）：「觉得这一天过得很舒服。真的很舒服吗？当然很舒服！」—— 零实质压力，**仅靠 `？` 和 `！` 两个标点**就通过了章末压力门。
- **根因**：问号/叹号被当作独立的压力信号计入 `ending_pressure_hits`。
- **改动**：标点降级为**辅助信号**——问号/叹号本身不再计入 hits，只有在**同时命中语义压力词**（`zh_hook_markers` 或动态注入的 `deliver_to_next` 关键词）时才作为加分；`ending_pressure_passed` 必须至少有 1 个语义命中。
  ```python
  # 伪码：语义命中是必要条件，标点只能加强不能替代
  semantic_hits = [...]           # 词表 + deliver_to_next 动态注入
  punctuation_hits = [...]        # ？！
  passed = bool(semantic_hits) and (len(semantic_hits) + len(punctuation_hits)) >= threshold
  ```
- **测试**：新增 `test_ending_pressure_rejects_punctuation_only_hook`（断言那句「很舒服吗？当然很舒服！」`passed is False`）+ `test_ending_pressure_still_accepts_semantic_hook_without_punctuation`（防误杀：纯陈述的强钩子「追兵已经堵住了退路」应通过）。
- **全量**：+2。
- **风险中**：会让部分原本通过的章节变红。**必须检查 `test_generation_quality_guards.py` 里所有 `ending_pressure` 相关测试**（约 6-8 个），确认它们的样本都有语义压力词而不是只靠标点。

#### T-15 章末压力词表去过拟合（对应 D-06）✅ 生产版已完成（2026-08-18，批 2）

> **实际落地**：42 个 `\uXXXX` 全部还原，剔除 10 个专有词，补通用词后 `ENDING_SEMANTIC_HOOK_MARKERS` 共 56 项（分类与下面的 5 类基本一致，但用的是**词根**而不是下面这种整句短语——`"已经堵住"` 这类长搭配命中率太低，实际用 `堵死` / `退路` / `追兵` 这样的 2-3 字词根）。**保留了 `人命`**（原计划要剔，理由见 D-06 偏差说明）。下面第 1655 行提到的"唯一硬依赖"已整条改写为跨题材版本。孤儿文件 `story_quality_scoring.py` 的同名词表**未动**，留 T-19。

- **位置**：`pipeline_orchestrator.py` 的 `zh_hook_markers`（`_evaluate_ending_pressure` 内，以 `\uXXXX` 转义形式硬编码）。
- **问题**：词表里混着**具体作品的专有名词**：`旧木片` / `旧南渠` / `药渣` / `药味` / `药耗` / `见了地` / `病人` / `人命`（孤儿版还有人名 `顾棠` / `林舟`）。这些词只对某一本书有效，对其他题材完全无用——等于章末压力门在别的书上只剩通用词那一小半在起作用。
- **替代方案（5 类通用压力语义，覆盖题材无关的钩子形态）**：
  ```python
  # 1 时限压迫
  "来不及", "只剩", "最后一次", "天亮之前", "倒计时", "期限", "还有几天"
  # 2 未解信息
  "还是未知", "无人知道", "不知道是谁", "另有其人", "真相是", "为什么会"
  # 3 迫近威胁
  "已经堵住", "正在逼近", "追上来", "包围", "盯上", "找上门", "冲进来"
  # 4 代价既成
  "已经死了", "再也回不去", "付出了", "换来的是", "血", "尸体"
  # 5 决断待执行
  "必须在", "只能选", "别无选择", "已经决定", "赌一次", "如果失败"
  ```
- **唯一的硬依赖，动手前必须处理**：`app/services/test_generation_quality_guards.py:902`
  ```python
  assert any(hit in {"死人", "见了地", "真会死"} for hit in ...)
  ```
  这条断言**直接依赖专有词 `见了地`**。改词表会让它变红。处理办法：把该测试的样本正文改成通用压力表达（例如把「见了地」改成「已经死了」），并把断言集合同步改为新词表里的词。**不要为了让测试过而在新词表里保留 `见了地`。**
- **不受影响的**：`896-897` 用的是 `continuity_anchor.deliver_to_next: ["旧南渠"]` —— 这是**动态注入**，走任务书数据而非硬编码词表，改词表不影响它。这个机制本身是对的，应该保留并加强（见 E-07）。
- **其余 8 个测试文件里的 65 处专有词只是样本用词**（正文内容），不构成断言依赖，无需修改。
- **测试**：新增 `test_ending_pressure_marker_table_has_no_work_specific_terms`，断言 `"药渣" not in markers and "旧南渠" not in markers and "见了地" not in markers`（防回退护栏）+ `test_ending_pressure_detects_generic_time_pressure_hook`（新词表能命中通用钩子）。
- **全量**：+2，且 `test_generation_quality_guards.py:902` 那条被改写（数量不变）。
- **风险中**：换词表会改变所有章末判定。**必须跑完整的 `test_generation_quality_guards.py`（56 个测试）逐个看红的**，逐个判断是「样本用词过时」还是「新词表召回不足」。

---

### 批 3：事件密度核心（T-04 / T-05 / T-06）—— **本轮最重要的一批**

> **这批改完，「灌水对话拿满分」这个根本问题才算解决。** 批 3 之前的所有工作都不触及 D-16 揭示的核心失效。

#### T-04 修 `_unit_has_progression`：引号 + 连词双根因（对应 D-02）

- **位置**：`pipeline_orchestrator.py:7169-7189`（`_story_units` 与 `_unit_has_progression`）+ `STORY_PROGRESSION_MARKERS`(7159-7167)。
- **两个根因必须一起改**（只改一个等于没改，见 D-02 的实证）：
  1. 引号无条件返回 `True`；
  2. 词表末尾含纯连词 `"却" "但" "然而" "转而" "下一步"` 与高频语素 `"活"` → 即使没引号也近似恒真。
- **改动**：
  ```python
  WEAK_TRANSITION_MARKERS = ("却", "但", "然而", "转而", "下一步", "活")   # 新增，只做辅助不做判定
  STORY_PROGRESSION_MARKERS = (...移除上述 6 个后的其余词...)

  @classmethod
  def _unit_has_progression(cls, unit: str) -> bool:
      if not unit:
          return False
      has_quote = any(mark in unit for mark in ("“", "”", "「", "」", "『", "』", '"'))
      has_marker = any(m in unit for m in cls.STORY_PROGRESSION_MARKERS)
      if has_quote:
          return has_marker or cls._count_dialogue_state_change_markers(unit) > 0
      return has_marker
  ```
  **保留 `"杀" "死" "必须" "否则" "来不及"` 在主词表**（语义确实指向危险）；`"活"` 必须移出（生活/干活/活动）。
- **测试**：
  - `test_progression_marker_table_excludes_bare_conjunctions`：断言 `"但"/"却"/"然而"/"活"` 不在主词表（一行护栏，防回退）。
  - `test_event_density_rejects_pure_small_talk_dialogue`：`BAD_FLAT_CHATTER` 样本 → `progression_unit_count` 相比修复前**显著下降**、`event_density_passed is False`。
  - `test_event_density_still_accepts_dramatic_scene`：`GOOD_DRAMATIC` → 仍 `True`（防误杀，**这条比上面两条更重要**）。
- **样本来源**：直接用探针 `backend/_probe_quality.py` 里的 `BAD_FLAT_CHATTER` / `GOOD_DRAMATIC`（1520 / 1344 字版本），**搬进测试文件时保留 `grow()` 的序数前缀写法**，否则整段重复会触发 D-10 加的重复检测，污染断言。
- **全量**：+3，但**预期有既有测试变红**（见下）。
- **必查的既有测试**（改前先单独跑一遍记下结果）：
  - `test_generation_quality_guards.py:1495` `test_event_density_allows_dense_progression_despite_local_plain_run`
  - `test_generation_quality_guards.py:1550` `test_story_quality_metrics_accept_dense_scene_sequel_progression`
  这两个是**防误杀测试**，如果变红，正确处理是**同步下调 `density_floor`**（在 T-06 里做），而不是回退 T-04。

#### T-05 修窗口判定：不要把句子级函数用在千字窗口上（对应 D-16-c）

- **位置**：`pipeline_orchestrator.py:7220-7222`
  ```python
  window_size = 1200 if word_count >= 7000 else 950
  windows = [condensed[i:i + window_size] for i in range(0, len(condensed), window_size)] or [condensed]
  window_hits = sum(1 for window in windows if cls._unit_has_progression(window))
  ```
- **根因**：`_unit_has_progression` 是**按句子设计**的判定（「这一句里有没有推进信号」）。把它用在 950 字的窗口上，只要整段 950 字里出现**一次**引号或一个推进词，整个窗口就算合格 → `state_change_window_pass_rate` 实测**恒为 1.0**（好坏样本都是 2/2），门槛 0.6 永远达标。**这个指标目前完全没有鉴别力。**
- **改动**：窗口合格的判定改成「窗口内**按句子统计**的推进句占比达标」，而不是「窗口里有没有」：
  ```python
  def _window_has_state_change(cls, window: str) -> bool:
      units = cls._story_units(window)
      if not units:
          return False
      hits = sum(1 for unit in units if cls._unit_has_progression(unit))
      # 千字窗口内至少要有一定比例的推进句，不是「有一句就算」
      return (hits / len(units)) >= 0.25 and hits >= 2
  ```
  阈值 `0.25 / 2` 是**起点，必须用真实正文校准**（见 T-06 的校准流程，两者共用同一批样本）。
- **依赖**：**必须在 T-04 之后**。T-04 之前 `_unit_has_progression` 近似恒真，比例算出来也是 1.0，改了看不出效果。
- **测试**：`test_state_change_window_rate_discriminates_flat_chatter`，断言 `BAD_FLAT_CHATTER` 的 `state_change_window_pass_rate < 1.0` 且 **严格小于** `GOOD_DRAMATIC` 的值。**这条断言在修复前必定失败（两者都是 1.0），正是缺陷证据。**
- **全量**：+1。
- **风险中**：新增了一个真正会失败的门。与 T-06 一起调阈值。

#### T-06 重定事件密度门槛（对应 D-16-a / D-16-b）

- **位置**：`pipeline_orchestrator.py:7225-7230`
  ```python
  density_per_1000 = round(progression_count / max(1.0, word_count / 1000), 4)
  density_floor   = 1.0  if word_count < 2500 else 1.25 if word_count < 7000 else 1.45
  unit_rate_floor = 0.16 if word_count < 2500 else 0.2  if word_count < 7000 else 0.22
  window_floor    = 0.6  if word_count < 2500 else 0.68 if word_count < 7000 else 0.74
  plain_run_limit = 5    if word_count < 7000 else 4
  ```
- **问题（D-16-a：量级差 54-125 倍）**：`_story_units` 是**句子级**切分，1500 字的中文正文能切出 150-190 个单元。所以 `density_per_1000` 的实际量级是 **50-125**，而门槛是 **1.0**。这个门**在数学上不可能失败**。

  | 样本 | word_count | progression_count | density_per_1000 | 门槛 | 结果 |
  |---|---|---|---|---|---|
  | BAD_FLAT_CHATTER（纯寒暄） | 1520 | 190 | **125.0** | 1.0 | ✅ 通过 |
  | GOOD_DRAMATIC（真冲突） | 1344 | 72 | **53.57** | 1.0 | ✅ 通过 |

- **问题（D-16-b：方向相反）**：`progression_unit_rate` 灌水样本 **1.0** > 好样本 **0.6923**。**指标越高反而越差**。根因是 D-02（引号+连词恒真），所以 **T-04 必须先做**。
- **改动与校准流程（不要拍脑袋定数字）**：
  1. T-04/T-05 完成后，先跑探针拿到新的量级：`BAD_FLAT_CHATTER` / `BAD_ALL_DESCRIPTION` / `BAD_MUNDANE_SEQUENCE` / `GOOD_DRAMATIC` 四个样本的新 `density_per_1000` 与 `progression_unit_rate`。
  2. **门槛取「好样本最低值」与「坏样本最高值」之间**，偏向宽松（宁可漏判不可误杀）。参考起点：`density_floor` **8.0 / 10.0 / 12.0**（对应三档字数），`unit_rate_floor` **0.16 → 0.35**。
  3. **上线时先保守设 `density_floor = 4.0` 观察一段真实生成**，确认误杀率可接受后再提到 8.0。**不要一次到位**——这个门一旦过严，所有章节都会拒稿。
  4. `window_floor` 与 `plain_run_limit` 在 T-05 改了语义后**必须重新校准**（旧值是针对恒真指标定的，无意义）。
- **测试（核心验收断言，修复前必失败）**：
  ```python
  def test_progression_rate_ranks_dramatic_above_flat_chatter():
      good = score(GOOD_DRAMATIC)["progression_unit_rate"]
      bad  = score(BAD_FLAT_CHATTER)["progression_unit_rate"]
      assert good > bad          # 当前：0.6923 > 1.0 → False，这就是缺陷证据
  ```
  再加 `test_event_density_floor_is_calibrated_to_sentence_level_units`（断言 `density_floor` 在合理量级，防有人把它改回 1.0）。
- **全量**：+2，**外加 T-04 里那两个既有防误杀测试可能需要在这里同步调阈值才转绿**。
- **风险高**：这是整份文档里对生产行为影响第二大的改动（最大是 T-16）。**必须在批 3 完成后做一次真实生成端到端验证**（见第 8.4 节），确认真实章节不会被大面积拒稿。

#### 批 3 实际落地记录（2026-08-18 完成，基线 668 → 679）

> **最重要的一条教训**：**不要用合成样本定生产阈值。** 第一版严格按本节建议做（`density_floor` 6/7/8、`unit_rate_floor` 0.14/0.16/0.18、`plain_run_limit` 12/12/10），定向与全量门禁全绿；随后灌 147 条真实生成章节进去，**通过率只有 3.7%，历史合格章节被误杀 95%**。合成样本 `GOOD_DRAMATIC` 每句都是冲突（`rate` 0.32、最长无推进连段 7 句），真实章节的推进句占比中位数只有 **0.079**、最长无推进连段中位数 **36 句**——两者差一个量级。阈值必须、且只能由真实语料定。

**真实语料校准（探针 `backend/_probe_real_corpus.py` + `_probe_threshold_grid.py`，用完即删）**

- 语料：`backend/storage/xuanqiong_wenshu.db` → `chapter_versions.content`，≥800 汉字、按 content 去重后 **147 条**；按 20 字 shingle 去重率 <0.90 剔除 **13 条**退化循环文本；`metadata.review_summaries.story_progression_guard.event_density_passed` 提供历史标签（True 120 / False 6 / 无 21）。**正向池 = 旧 True 且非退化 = 107 条。**
- 正向池实测分位（新判定逻辑下）：

  | 指标 | p05 | p10 | p25 | p50 | p75 | p95 | max |
  |---|---|---|---|---|---|---|---|
  | `event_density_per_1000` | 2.01 | 2.23 | 2.88 | **4.60** | 7.13 | 9.48 | 13.65 |
  | `progression_unit_rate` | 0.026 | 0.035 | 0.047 | **0.079** | 0.128 | 0.204 | 0.253 |
  | `max_plain_unit_run`（绝对句数） | 14 | 16 | 20 | **36** | 63 | 104 | 167 |
  | `max_plain_unit_run_ratio`（占全章句数） | 0.127 | 0.134 | 0.158 | **0.218** | 0.301 | 0.448 | 0.681 |
  | `story_unit_count` | 55 | 76 | 112 | **159** | 244 | 422 | 1269 |

- 单条件误杀率（正向池 n=107）：`density_floor` 1.5→3.7% / 2.0→4.7% / 2.5→18.7% / 6.0→**68.2%**；`unit_rate_floor` 0.025→2.8% / 0.03→7.5% / 0.04→18.7% / 0.14→**78.5%**；`plain_run_limit`（绝对）12→**95.3%** / 60→26.2% / 120→3.7%；`plain_run_ratio` 0.7→**0.0%** / 0.5→3.7% / 0.3→26.2%。
- 校准后实测：正向池通过 **95.0%**（拒 6 条，全部是 `density` 0.67-2.16、`rate` 0.015-0.027 的超低密度长文本，正是这道门该拦的形态）；分档通过率 <2500 字 **100%**（n=46）、2500-6999 **91.9%**（n=86）、≥7000 **50%**（n=2，样本太少无意义）。`state_change_window_pass_rate` 中位数从 **0.0 修到 1.0**。

**与本节建议的 5 处偏差（都有实测依据）**

1. `density_floor` **1.5 / 1.8 / 2.0**，不是建议的 8/10/12，也没走"先设 4.0 观察"——4.0 在真实语料上就误杀 42%。
2. `unit_rate_floor` **0.025 / 0.028 / 0.03**，不是 0.16→0.35。
3. `plain_run_limit`（绝对句数）**整个删掉**，换成 `plain_run_ratio_limit` **0.75 / 0.72 / 0.70**。绝对句数随章节长度线性膨胀（真实 p95=104），用绝对阈值等于按长度歧视长章；比例形态才有鉴别力（真实 max 0.681，纯寒暄样本 1.0）。
4. T-05 的窗口占比 **0.05**，不是起点值 0.25。0.25 时 107 条真实合格正文只有 **6.5%** 能让窗口率达到 0.5，指标等于恒假。"推进不能只集中在开头"这个诉求改由 `WINDOW_PROGRESSION_MIN_HITS = 2` 承担。
5. 额外做了**尾窗合并**（`WINDOW_TAIL_MERGE_RATIO = 0.4`，`_split_progression_windows`）：950 字切完剩十几个字单独成窗、再要求它有 2 句推进必然不达标，是纯切分噪声。

**代码改动（`pipeline_orchestrator.py`）**

- `STORY_PROGRESSION_MARKERS` 拆出 `WEAK_TRANSITION_MARKERS = ("却", "但", "然而", "转而", "下一步", "活")`（只做辅助不参与判定）与 `DIALOGUE_QUOTE_MARKS`。
- `_unit_has_progression`：引号不再无条件返回 `True`，对话句必须另有推进词或对话状态改变词。
- 新增 `_window_has_state_change`（按窗口内推进句占比 + 最少 2 句判定）、`_split_progression_windows`（尾窗合并）、`_event_density_floors`（分档阈值提成类方法，docstring 里写明真实分位）。
- `_evaluate_event_density`：判定改用 `plain_run_ratio`，新增返回字段 **`max_plain_unit_run_ratio`**，并同步加进 `quality_metric_snapshot` 的显式白名单（**唯一会让新字段静默丢失的地方**）。短路分支（`word_count < 800`）也补了该字段。

**已知局限（下一个人不要重复踩）**

- **旧 False 那 6 条在新实现下全部通过**（拦截率 0%）。不是回退：旧标签是用旧判定（引号全算推进）配 0.16 高门槛算出来的，两套指标不可比；这 6 条在新指标下 `density` 中位数 3.13、`rate` 0.051，落在正常范围内。n=6 也没有统计意义。**真实语料里缺少足够的"真坏样本"，这道门的鉴别力目前只能由合成样本 + `plain_run_ratio` 保证。**
- `plain_run_ratio` 在真实语料上**一条都没拦**（拒稿主因是 `rate` 6/6 与 `density` 4/6）。它的作用是拦 `ratio` 接近 1.0 的纯寒暄/纯描写堆砌，属于兜底而非主判据。
- **这道门已被重定位为「底线门」**：只拦纯描写堆砌、纯寒暄这类灾难样本，不承担质量优选（那是评分与 prompt 的职责）。任何想靠它提升平均质量的改动都会立刻撞上误杀墙。
- 真实章节的 `rate` 只有 0.079，意味着 **93% 的句子不含任何推进词**——推进词表对真实文本的召回率很低。这是词表覆盖问题，不是阈值问题，留给后续批次（与 E 系列的词表扩充一起做）。

**反向验证（`backend/_reverse_verify_batch3b.py`，8 条有效项全部必红成立）**

① 窗口占比退回 0.25 → 真实密度样本红；② `WINDOW_PROGRESSION_MIN_HITS` 退回 1 → 长句样本红（短句样本证不了，会被占比先拦住，脚本里标为对照项）；③ 阈值量级抬回 6.0/0.14 → 护栏红；③b 压到 1.0/0.01 → 护栏红；④ `floors` 里加回 `plain_run_limit` 键 → 护栏红；⑤ 比例上限压到 0.1 → 护栏红；⑥ 密度结果不含比例字段 → 红；⑦ 新字段漏出 snapshot 白名单 → 红。类属性/类方法全部 `setattr` 复原确认通过。

**8.4 真实生成端到端验证：⏳ 待做。** 本轮无 LLM 额度（前序已出现 `403 pre-consume quota failed`），无法真实调用生成管线。已做的是**离线灌真实历史正文**（147 条）做校准，覆盖了"真实章节会不会被大面积拒稿"这个核心风险，但**没有覆盖**"新阈值下重试/降级链路的实际行为"。恢复额度后必须补。

**顺带确认的两件事（不是缺陷，避免重查）**

- `_score_story_quality_candidate` 的**顶层返回**没有 `event_density_per_1000` / `state_change_window_pass_rate` / `max_plain_unit_run*`，只有 `quality_metric_snapshot` 里有。已核实无外部消费方，故意不补。
- 批 1 遗留已补：`# ====== END _pipeline_story_scoring.py ======` 原先卡在 `_score_story_quality_candidate` 的 return 字典字面量中间（把 `quality_issue_labels` 与 `quality_metric_snapshot` 两个键劈开），本批已挪到 return 语句之后（现 7614），相对位置不变——仍在 `_score_story_quality_candidate` 与 `_fallback_select_best_version` 之间，模块边界含义没改。

---

### 批 4：坏样本回归测试套件（T-07）

#### T-07 建立 8 个坏样本的回归测试（对应 D-05）

- **为什么单独成一批**：CLAUDE.md 明确要求「为坏样本（全描写、无逻辑、无反转、平淡结尾）建可复现回归测试」，而现有 56 个测试**几乎全是「好样本应通过」方向**，缺的是「坏样本必须被拦住」方向。批 3 改完门槛后，正是把坏样本固化下来的时机——**否则下一次有人为了压误杀调松阈值，没有任何测试会红**。
- **文件**：在 `app/services/test_generation_quality_guards.py` 末尾新增一个 `class TestBadSampleRegression`（**不要新建文件**，见第 10 节「明确不做」——新建 `test_story_quality_scoring.py` 会给孤儿模块续命）。
- **样本常量集中定义**（复用探针里已验证过的写法）：
  ```python
  # 用序数前缀扩写，避免整段精确重复触发 D-10 的重复段落检测
  _ORD = ("初", "次", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")
  def _grow(block: str, times: int) -> str:
      return "".join(block.replace("＃", _ORD[i % len(_ORD)]) for i in range(times))
  ```
- **8 个坏样本与各自必须触发的 code**：

  | # | 样本名 | 特征 | 必须触发 | 对应缺陷 |
  |---|---|---|---|---|
  | 1 | `BAD_ALL_DESCRIPTION` | 全景物描写，无对话无动作 | `static_description_risk`（**不是 `static_description_heavy`**，见下方落地记录偏差 ①） | D-08 |
  | 2 | `BAD_FLAT_CHATTER` | 纯寒暄对话灌水 | `event_density_weak` | D-02/D-16 |
  | 3 | `BAD_MUNDANE_SEQUENCE` | 起床刷牙上班流水账 | `ending_pressure_missing`（**不是 `event_density_weak`**，见偏差 ②） | D-16 |
  | 4 | `BAD_PUNCTUATION_HOOK` | 结尾只有「舒服吗？舒服！」 | `ending_pressure_missing` | D-03 |
  | 5 | `BAD_FLAT_CLOSURE` | 结尾「日子就这样过去了」 | `ending_pressure_missing` | D-04 |
  | 6 | `BAD_REPEATED_PARAGRAPH` | 同一段落重复 4 次凑字数 | `repeated_paragraph_flood` | D-10 |
  | 7 | `BAD_MISSING_FOCUS` | 任务书指定 2 人，正文一个没出现 | `focus_character_missing`（warning） | D-12 |
  | 8 | `BAD_NO_INHERIT` | 任务书有 inherit，正文全不承接 | `continuity_inherit_missing`（warning） | E-07 |

  **外加 1 个正向对照 `GOOD_DRAMATIC`**：断言它**不触发上面任何一条**。这条是整个套件的防误杀锚点，**每次调阈值都必须保证它是绿的**。
- **每个样本 2 条断言**：① 触发预期 code；② `score` 显著低于 `GOOD_DRAMATIC`（差值 ≥300，与 T-16 的验收标准对齐）。
- **注意**：样本 6/7/8 依赖 D-10/D-12/E-07 的实现。**批 4 先只写 1-5（5 个样本，+8 测试含对照与分数断言），6-8 在对应批次里补**。文档里一次列全是为了让接手人知道最终形态。
- **全量**：+8（按 6.3 表，跑完批 4 应为 `680 passed` 左右，取决于前面各批实际增量）。
- **风险零**（纯新增测试）。**但如果新写的测试一开始就绿，说明批 3 的修复没生效，回去查。**

#### 批 4 实际落地记录（2026-08-18 完成，基线 679 → 688）

**门禁**：定向 `test_generation_quality_guards.py` **113 passed in 13.40s**（104 → 113，`--collect-only -q` 核对新增正好 9 条）；全量 ~~688 passed in 118.20s~~ **（假绿，D-26；`exit 0` 本身就是 D-26 的症状）**。

**改了两个文件**：
1. `test_generation_quality_guards.py`：新增 `class TestBadSampleRegression`（9 个方法）+ 3 个样本常量（`BAD_ALL_DESCRIPTION` / `BAD_MUNDANE_SEQUENCE` / 两个结尾类样本）+ 1 个公用填充常量 `_FLAT_ENDING_FILLER` + 2 个分组元组（`BAD_SAMPLES_DENSITY_CLASS` / `BAD_SAMPLES_ENDING_CLASS`）。`BAD_FLAT_CHATTER` 与 `GOOD_DRAMATIC` 复用批 3 已固化的常量，评分入口复用既有 `_score_density_sample` 辅助函数。
2. `pipeline_orchestrator.py`：**一行生产改动**——`quality_metric_snapshot` 白名单补 `flat_closure_markers`（见下方偏差 ④）。

**9 条测试及其锁住的东西**：

| 测试 | 锁住的行为 |
|---|---|
| `test_all_description_sample_is_blocked` | codes 含 `static_description_risk` + `event_density_weak`；`progression_unit_count == 0`；`max_plain_unit_run_ratio == 1.0` |
| `test_flat_chatter_sample_is_blocked` | codes 含 `event_density_weak`；`state_change_interval_passed is False`；`progression_unit_rate == 0.0` |
| `test_mundane_sequence_sample_is_blocked` | codes 含 `ending_pressure_missing`；**并有意断言 `event_density_passed is True`** |
| `test_punctuation_only_hook_sample_is_blocked` | `ending_semantic_hit_count == 0`、`ending_weak_hit_count >= 2`，且 `event_density_passed is True`、`static_description_risk is False`（**失败维度唯一**，证明拦它的确实是章末压力门） |
| `test_flat_closure_sample_is_blocked` | `flat_closure_markers != []` 且带 `ending_pressure_missing` |
| `test_flat_closure_markers_reach_quality_metric_snapshot` | 新字段必须穿过快照白名单；正向对照必须是**空 list 而不是缺键** |
| `test_positive_control_triggers_no_blocker` | `quality_issue_codes == []`、`tone == "success"` —— **整套的防误杀锚点** |
| `test_density_class_samples_score_far_below_control` | 3 个密度类样本与对照分差 `>= 300`（实测 **1578 / 1001 / 493**） |
| `test_ending_class_samples_score_below_control` | 2 个结尾类样本分差 `>= 200`（实测两个都正好 **260**，见偏差 ③） |

**与 T-07 原方案的 4 处偏差（都是实测逼出来的，不是简化）**：

- **① code 名写错**：上表原写 `static_description_heavy`，生产实际 code 是 **`static_description_risk`**（`_build_quality_issue_summary` 里 `add("static_description_risk")`）。已就地改正。
- **② 样本 3 的预期 code 换了**：流水账 `BAD_MUNDANE_SEQUENCE` 实测 **`event_density_passed is True`** —— 它动作词密集，密度门本来就不该拦它（密度门是**底线门**，拦的是"连动作都没有"，不是"动作没有意义"）。真正拦住它的是章末压力门（`ending_pressure_missing`）。测试因此把 `event_density_passed is True` 写成**正式断言并附注"改这里前先看 T-06"**——如果哪天有人为了抓流水账去抬密度阈值，这条会红，提醒他那是 T-16 权重问题而不是密度门问题。
- **③ 结尾类分差达不到 ≥300**：实测两个结尾类样本与对照的分差都正好 **260**。这不是缺陷，是「一处结尾」在总分里本来就只值这么多分——结尾类样本与对照只差最后一段，密度、场景、静态描写维度全部相同。处理：把原方案的 1 条分差测试**拆成两条**（密度类 `>=300`、结尾类 `>=200`），并在 docstring 写明实测值与理由：**结尾维度真正的防线是 `ending_pressure_missing` 这个 blocker，不是分差。** 这也是全量比目标 687 多 1 条的原因。
- **④ 顺带修了一个批 2 的观测性漏项**：写第 5 条测试时 `KeyError: 'flat_closure_markers'` —— 用 `python -c` 打印顶层键与快照键确认该字段**两处都没有**。批 2 把 `ending_semantic_hit_count` / `ending_weak_hit_count` 补进了白名单却漏了这个 list，后果是用户只看到「章末未递出压力」，不知道是哪句话触发的一票否决，也无从判断误杀。已加进 `quality_metric_snapshot` 白名单并用第 6 条测试锁住。**教训与批 3 同源：新增字段必须显式过白名单，白名单是唯一的静默丢弃点。**

**建样本时撞出的新缺陷 D-24（尾窗遮蔽）**：按方案直接写「正文 + 短标点尾巴」会让测试**一开始就绿**（`codes=[]`、score 与对照完全相同 1302）。根因不是批 3 修复失效，而是 `_evaluate_ending_pressure` 的 260 字尾窗把正文强钩子一起卷了进来。填充到 275 字才正确拦住（score 1042）。第一版填充 159 字**仍然不够**。构造这段填充时逐条排查了 56 个语义钩子词、14 个收束词、以及倒计时正则 `[一二三四五六七八九十]\s*[、，,]\s*[一二三四五六七八九十]`，确认零命中。详见 D-24，**修复排进批 6**。

**反向验证**（`_reverse_verify_batch4.py`，运行时 `setattr` 改坏 6 处生产条件，用完即删，末尾复原确认 6 个属性全部 `is` 原对象）：**11/11 必红**。逐条改坏点 → 必红测试：① `_unit_has_progression` 退回"有引号即算推进" → 寒暄样本；② `_event_density_floors` 压成恒真（全 0 / ratio 1.0）→ 全描写 + 寒暄样本；③ 让 weak 命中可顶替语义压力 → 标点钩子样本；④ 取消 `not closure_hits` 一票否决 → 平淡收束样本 + 快照测试 + 结尾分差测试；⑤ 从快照 `pop("flat_closure_markers")` → 快照测试；⑥ 抹掉 `story_guard["static_description_risk"]` → 全描写样本；⑦ 阈值抬到 99.0/0.9/0.99 → **正向对照必红**（证明防误杀锚点真的会拦住"为抓坏样本而过度收紧"）；⑧ 把 score 抹平成常数 → 密度类分差测试。**唯一一条"改坏了却仍绿"的是把 `_estimate_static_description_runs` 恒返回 0**，已记为 D-25（静态描写三条 or 里第 2/3 条无覆盖，留 T-08 补样本）。

**清理**：`_probe_badsamples.py` / `_reverse_verify_batch4.py` 已删；11.1 里挂着的 `_probe_quality.py` / `_cmp_scoring.py` / `_probe_out.json`（原定"留到批 4 之后"）也已删除，删前用 `git ls-files --error-unmatch` + `git status --short -uall` 确认 5 个文件全部 untracked。

---

### 批 5：修复闭环（T-22）—— ✅ **已完成（2026-08-18，691 passed）**

#### T-22 定向修复闭环：保留部分改善 + 最多 2 次 + 失败也留诊断（对应 D-21）

> **✅ 已完成（批 5，2026-08-18）。** 下面的方案描述保留为设计依据，**代码位置与返回值语义已变**——实际落地形态、2 处与方案的偏差、反向验证记录见本节末尾「批 5 实际落地记录」。

- **位置**：`pipeline_orchestrator.py:2035-2116`（**修复前**；修复后为 **2054-2241**）。
- **为什么排在加 blocker 之前**：批 6（T-08/T-09/T-10）会**提高 blocker 触发率**。在当前「一次修复 + 全清零才算成功」机制下，blocker 越多 → 一次修复全清零的概率越低 → **拒稿率上升**，用户看到的是「生成一直失败」而不是「质量变好」。**这是前序会话里 D-14 那两条自评豁免被加进来的根本原因；不先修这里，同样的补丁会被再加一次。**
- **改动 1（核心）：保留部分改善**。当前：
  ```python
  if not repaired_gate.get("passed", False):
      return None            # ← 5 个 blocker 修到剩 1 个，也整个丢弃
  ```
  改为：
  ```python
  before = set(structural_quality_gate.get("quality_issue_codes") or [])
  after  = set(repaired_gate.get("quality_issue_codes") or [])
  improved = len(after) < len(before) and not (after - before)   # 严格减少且无新增类型
  if not repaired_gate.get("passed", False) and not improved:
      return None
  # improved 为真时采纳 next_content，并把「未完全达标」写进元数据
  ```
  **`not (after - before)` 这个条件很重要**：防止「修掉 3 个、引入 2 个新问题」被当成改善。
- **改动 2：最多 2 次修复**。第 2 次只针对剩余 blocker 构造 issues。**上限硬编码 2，不要做成配置项**（配置项会被调大，每次都是一次 LLM 调用，成本与耗时线性增长，见 2.4）。
- **改动 3：失败也留诊断**。当前 `return None` 后调用方只有原始 gate 的 codes。应写进 `runtime_metadata`：`repair_attempted`、`repair_rounds`、`issue_codes_before`、`issue_codes_after`、`repair_outcome ∈ {passed, improved, unchanged}`。前端就能显示「已尝试自动修复，仍有 N 项未达标」，而不是让用户面对一个无解的 422。（2110/2114 已有 `structural_quality_gate` / `issue_codes_before` 的写入位置，顺着补即可。）
- **改动 4**：`enable_self_critique` 关闭时（2058 的开关），至少要走确定性清理（T-17），不能完全无自愈手段。**这条依赖 T-17，可以留到批 10 再接上**，批 5 先只加一条 TODO 注释和 `runtime_metadata["repair_skipped_reason"]`。
- **测试**：
  - `test_structural_repair_accepts_partial_improvement`：mock `revise_chapter` 返回「3 个 blocker 修到剩 1 个」的版本 → 断言结果被采纳、`repair_outcome == "improved"`、不抛 422。
  - `test_structural_repair_rejects_swapped_issues`：mock 返回「修掉 2 个但新增 2 个」→ 断言 `return None`（`after - before` 非空）。
- **全量**：+2。
- **风险中**：原本拒稿的章节会变成「带未达标标记放行」。**这是有意的权衡**：拒稿对用户价值为零。前端展示层已就绪（见 3.3），确保「未完全达标」显示清楚即可。

#### 批 5 实际落地记录（2026-08-18 完成，基线 688 → 691）

**门禁**：定向 `test_generation_quality_guards.py` **116 passed in 4.84s**（113 → 116，净增 3）；全量 ~~691 passed in 61.34s~~ **（假绿，D-26）**。

**改了两个文件**：

1. `pipeline_orchestrator.py`（4 处编辑，**下列行号为落地后 `grep -n` 实测**）：
   - `typing` 导入加 `Sequence`。
   - 新增类属性 `STRUCTURAL_GATE_REPAIR_MAX_ROUNDS = 2`（**2037**）与 `staticmethod _is_structural_repair_improvement(before_codes, after_codes)`（**2040**）。判据即改动 1 的严格子集收缩：`len(after) < len(before) and not (after - before)`。
   - 重写 `_attempt_structural_gate_repair`（**2054-2241**，原 2035-2116）；轮数循环在 **2148**（`for _round in range(self.STRUCTURAL_GATE_REPAIR_MAX_ROUNDS)`）。
   - 两处调用点（**3857** 与 **4083**）改成同一形态：先无条件把 `repair_summary` 追加进 `runtime_metadata["quality_gate_repairs"]`（**3878** / **4104**），再看 `adopted` 决定是否替换正文。
2. `test_generation_quality_guards.py`：4 条新增测试 + 1 条既有测试改名并反转断言。

**返回值语义变更（比原方案更进一步，调用方必须知道）**：`_attempt_structural_gate_repair` **不再返回 `None`**，一律返回字典，采纳与否由 `adopted` 布尔表达。原来「`None` = 失败、非 `None` = 已采纳」的约定被彻底取消——因为改动 3 要求「失败也留诊断」，而 `None` 里放不下诊断。四种跳过原因写进 `repair_skipped_reason`：`self_critique_disabled` / `story_guard_missing` / `no_structural_issue` / `revise_failed`。这样前端能区分「试过但没修好」和「这个 preset 压根没试」，后者原先和前者长得一模一样。

**诊断字典字段**（`repair_summary`，两处调用点都追加进 `runtime_metadata["quality_gate_repairs"]`）：`status`（`applied` / `rejected`）、`repair_attempted`、`repair_rounds`、`repair_outcome ∈ {passed, improved, unchanged, skipped}`、`repair_skipped_reason`、`issue_count`、`issue_codes_before`、`issue_codes_after`、`new_issue_codes`、`remaining_issue_count`。**未采纳时也写**——否则用户面对的是一个无从解释的 422，这正是改动 3 的目的。

**5 条测试及其锁住的东西**（行号为落地后实测；同族另有 2 条既有测试 `..._adopts_revision_that_fixes_progression` 1000、`..._is_wired_into_generate_chapter` 1368 保持绿）：

| 测试 | 行号 | 锁住的行为 |
|---|---|---|
| `test_structural_gate_repair_adopts_partial_improvement` | 1132 | **既有测试改名 + 断言反转**（原 `..._rejects_revision_that_does_not_pass_gate` 断言「没过门就整章丢弃」，正是 D-21 的错误行为）。现断言部分改善被采纳、`repair_outcome == "improved"` |
| `test_structural_gate_repair_rejects_traded_issue_types` | 1195 | 「修掉几个、引入新 code 类型」必须拒绝，且 `new_issue_codes` 记下引入了什么 |
| `test_structural_gate_repair_stops_at_two_rounds` | 1252 | `STRUCTURAL_GATE_REPAIR_MAX_ROUNDS` 恰好是 2（**上下都卡**：退回 1 红、放宽到 3 也红），且 `repair_rounds` 如实记录 |
| `test_structural_gate_repair_keeps_diagnostics_when_no_improvement` | 1065 | 无改善时不能返回 `None`，`issue_codes_after` 必须有内容 |
| `test_structural_gate_repair_skipped_when_self_critique_disabled` | 1319 | 自评关闭时也要返回诊断并填 `repair_skipped_reason` |

**与 T-22 原方案的 2 处偏差**：

- **① 增量 +2 → 实际 +3**。原方案只列了两条测试（保留部分改善、拒绝换毛病）。实际拆成 4 条新增：轮数上限需要单独一条（而且必须上下都卡，否则「放宽到 3」这种退化改不红），诊断保留也需要单独一条（无改善路径与跳过路径是两条不同分支）。加上 1 条改名反转，收集数净增 3。
- **② 改动 4 的 TODO 落点**：原方案说「加一条 TODO 注释和 `runtime_metadata["repair_skipped_reason"]`」。实际把 `repair_skipped_reason` 放进了 `repair_summary` 而不是 `runtime_metadata` 顶层——因为诊断字典本身就要进 `runtime_metadata["quality_gate_repairs"]`，放顶层会造成同一信息两个来源。TODO 注释按方案写在 `self_critique_disabled` 分支上，标注 `TODO(T-17/D-11)`。

**这一批的核心教训：blocker 数量下降不等于改善。** 实测反例——`"## 场景 1｜开场\n\n" + GOOD_DRAMATIC` 的 blocker 数从起点 7 条掉到 1 条，数量上是大幅"改善"，但那 1 条是 `chapter_artifact_markers`，一种起点根本不存在的失败形态。若只按数量判定就会采纳它，修复循环随后朝「继续消灭 artifact 标记」的方向收敛，而原本的结构问题一个都没解决。所以 `not (after - before)` 这半个条件不是防御性冗余，是判据的主体部分。**任何后续的「是否变好了」判据都要带这半条**（E-11 的分档尤其要注意，分档会让「换一档毛病」更容易发生）。

**反向验证**（`_reverse_verify_batch5.py`，运行时 `setattr` 改坏 4 处生产条件共 12 种方式，用完即删，末尾 5 项 `is` 比较确认全部复原）：**12/12 必红**。逐条改坏点 → 必红测试：① 退回「必须一次过门才采纳」→ 部分改善测试；② 改善判据只看数量、不看新增类型 → 换毛病测试；③ 轮数上限退回 1、④ 放宽到 3 → 轮数测试（双向）；⑤ 失败时退回 `return None` → 无改善诊断测试 + 跳过诊断测试；⑥ `repair_rounds` 记成 1 → 轮数测试；⑦ `issue_codes_after` 丢空、⑧ `repair_skipped_reason` 不填、⑨ `new_issue_codes` 丢空 → 各自对应的诊断测试；⑩ 采纳信号退回 `is not None`、⑪ 未采纳时不记 `runtime_metadata` → 接线测试。

**反向验证的一个方法论坑（值得抄走）**：接线测试 `test_structural_gate_repair_is_wired_into_generate_chapter` 断言的是 `inspect.getsource(PipelineOrchestrator.generate_chapter)` 的**文本内容**（数 `quality_gate_repairs` 出现次数、检查采纳条件写法）。所以改坏它必须替换 `inspect.getsource` 本身，让它对 `generate_chapter` 返回改坏后的源码字符串；替换 `P.generate_chapter` 对象只会让测试抛 `TypeError`，那是**假必红**——测试变红的原因和要证明的缺陷无关。凡是基于源码文本断言的测试，反向验证都要走这条路。

**清理**：`_probe_batch5.py` / `_probe_batch5b.py` / `_reverse_verify_batch5.py` 已删。两个探针全程只打印 code 名、布尔值、字数与 issues 条数，不打印任何正文，符合 2.2 的证据脱敏要求。

---

### 批 6：静态描写与重复检测（T-08 / T-09 / T-10 **+ D-24 / D-25**）

> **批 4 追加进本批的两项**（不单独占任务编号，但**必须在本批做完**）：
> - **D-24 章末压力尾窗遮蔽**（`pipeline_orchestrator.py:7392`，`ending_excerpt = condensed_text[-260:]`）。改动方案与验收见 D-24 条目。**属于「判定逻辑有洞」而不是「阈值不对」，和 T-08/T-09 同类**，所以放一批。注意：修完之后 8.3 的第 6 条铁律（结尾类样本必须自带 ≥260 字尾巴）可以放宽，届时应把 `BAD_PUNCTUATION_HOOK` / `BAD_FLAT_CLOSURE` 的 `_FLAT_ENDING_FILLER` 缩短，**并确认它们仍然被拦** —— 那是 D-24 真正修好的证据。
> - **D-25 静态描写三条 or 里第 2/3 条无覆盖**：做 T-08 时顺手补一个 `max_static_run >= 3` 的多段样本。验收方式：把 `_estimate_static_description_runs` 改成恒返回 0，新样本必须红（现有的 `BAD_ALL_DESCRIPTION` 在这种改坏下**仍然绿**，因为它走第 1 条 or）。

#### T-08 移植静态描写检测的第 4 条判定 + 对齐阈值（对应 D-08 前半）

- **位置**：`pipeline_orchestrator.py:7669-7673`（生产版判定，**行号已按批 5 校准**）vs `story_quality_scoring.py:1346-1356`（孤儿版）。
- **实测差异表**（这是全文档里差异最清晰的一处，直接移植即可）：

  | 条件 | 生产版(7669-7673) | 孤儿版(1346-1356) |
  |---|---|---|
  | 第 1 条 | `word_count >= 1800` | `>= 1200` |
  | 第 2 条 | `>= 1500` 且 `max_static_run >= 3` | `>= 1200` 且 `>= 2` |
  | 第 3 条 | `>= 2500` 且 `>= 2` | `>= 2000` 且 `>= 2` |
  | 第 4 条 | **不存在** | `>= 1600` 且 `dialogue_markers > 0` 且 `max_static_run >= 2` 且 `static_paragraph_count >= 3` |

- **第 4 条为什么关键**：它是**唯一能抓住「插几句对话掩护大段描写」**的判定（前 3 条都只看静态段落本身，一有对话就放过）。实测 `BAD_ALL_DESCRIPTION` 纯描写会被抓，但「描写+零星对话」的混合体在生产版能逃逸。
- **改动**：把第 4 条整条移植过来，并把前 3 条阈值对齐孤儿版（1800→1200、1500→1200、2500→2000，`max_static_run` 3→2）。
- **依赖**：**T-22 已于批 5 完成**，闸门已就位，可以放心提高 blocker 率。
- **测试**：`test_static_description_detects_description_with_token_dialogue`——构造「1800 字描写 + 3 句寒暄对话」样本，断言 **`static_description_risk`**（注意：不是 `static_description_heavy`，批 4 已核实生产 code 名是前者）触发。**反向验证**：移植前跑 → 红。
- **全量**：+2（含一条阈值护栏测试）。
- **风险中**：阈值下调会提高触发率。**这是本文档里性价比最高的单条改动**（工作量小、判定可靠、直击 CLAUDE.md 第一条目标「减少静态描写」）。

#### T-09 收紧 `action_markers`（对应 D-08 后半）

- **位置**：`_estimate_static_description_runs` 内判断「这一段是不是静态」时用的动作词表。
- **问题**：词表过宽会把描写段误判为动作段（例如「风吹过」「光洒在」这类**无主体动作**也算动作），导致静态段落数被低估。
- **改动**：动作词判定加**主体约束**——只有当段落里同时存在「人称/人名 + 动作动词」才算动作段；纯自然现象动词（吹/洒/飘/流/垂/映）不计。实现上最简单的做法是把这些自然现象动词单独列成 `AMBIENT_MOTION_MARKERS` 并从动作词表移出。
- **测试**：`test_ambient_motion_does_not_count_as_action`——「晨雾漫过山谷，阳光洒在石阶上，芦苇轻轻摇曳」断言被判为静态段落。
- **全量**：+1。
- **风险低-中**：与 T-08 叠加会进一步提高静态判罚率，**两条必须同批做同批验证**，否则分不清是哪条造成的误杀。

#### T-10 移植重复段落检测 + 新增第 12 类 blocker（对应 D-10）

- **位置**：生产**完全缺失**；孤儿版 `story_quality_scoring.py:949-980`（`_evaluate_repetition_risk`）可直接照搬。
- **孤儿版算法（阈值照抄，不要改）**：
  - 段落归一化后 `len(plain) >= 30` 才计入（短段落重复是正常的，如对话应答）；
  - `word_count >= 800` 才启用；
  - 判定：`(max_repeat >= 3 and longest >= 30) or (instances >= 2 and ratio >= 0.3 and longest >= 80)`
    —— 即「同一段出现 ≥3 次且长度 ≥30 字」**或**「重复段落占正文比例 ≥30% 且最长重复段 ≥80 字」。
- **接入点三处**（缺一处就不生效）：
  1. `_score_story_quality_candidate` 里调用并判罚 **−420**；
  2. 返回字典与 `quality_metric_snapshot` 加 `repetition_risk` / `repeated_paragraph_count` / `longest_repeated_length` / `repetition_ratio`；
  3. 结构质量门新增**第 12 类 blocker** `repeated_paragraph_flood`（判定 100% 可靠——字符串完全相同，可以放心做 blocker）。
- **为什么重要**：重复段落是 LLM 凑字数最典型的退化形式，而且**当前会被评分器当成正分**（重复段落同样贡献 `paragraph_count` +216 与 `progression_unit_count` +288）。也就是说现在**复制粘贴同一段能刷高分**。
- **明确不做**：近似重复检测（编辑距离 / 向量相似度）留 **P3**（见第 10 节）。精确重复已能抓住绝大多数灌水，近似重复的误判风险和实现成本都高得多。
- **依赖**：T-22（新增 blocker）。
- **测试**：`test_repeated_paragraph_flood_blocks_candidate`（同一 120 字段落重复 4 次 → blocker 触发、判罚 −420）+ `test_short_repeated_dialogue_is_not_flagged`（「「好。」」重复 5 次不触发，因 `len < 30`）。
- **全量**：+2。
- **风险中**：新增 blocker 会提高拒稿率，但因为判定可靠，误杀风险主要来自**正常的排比/复沓修辞**（例如刻意重复的抒情段）。`len >= 30` 与 `ratio >= 0.3` 两个阈值已经过滤掉大部分修辞用法。

#### 批 6 实际落地记录（2026-08-19 完成，基线 691 → 718）

**门禁**：定向 `test_generation_quality_guards.py` **143 passed in 3.68s**（116 → 143，净增 27）；全量 ~~718 passed in 55.80s~~ **（假绿，D-26）**（目标 696，实际 +27 而非 +5，原因见下面「与原方案的 4 处偏差」）。

**改了两个文件。`pipeline_orchestrator.py` 的落地行号（`grep -n` 实测）**：

| 符号 | 行号 | 归属 |
|---|---|---|
| `"repeated_paragraph_flood": "整段重复灌水"`（label） | 456 | T-10 |
| `add("repeated_paragraph_flood")`（code 派发） | 534 | T-10 |
| `blockers.append(... "repeated_paragraph_flood")`（第 12 类 blocker） | 730 | T-10 |
| `ENDING_CORE_WEAK_ONLY_LIMIT = 2` / `ENDING_CORE_FLAT_CHARS = 150` | 7569 / 7570 | D-24 |
| `_evaluate_ending_pressure`（加 `raw_text` 形参） | 7573 | D-24 |
| `"ending_core_chars"` 等 4 个返回字段 | 7645-7648 | D-24 |
| `STATIC_ACTION_MARKERS`（类属性，34 项） | 7658 | T-09 |
| `AMBIENT_MOTION_MARKERS`（类属性，10 项） | 7670 | T-09 |
| `_estimate_static_description_runs`（`staticmethod` → `classmethod`） | 7673 | T-09 |
| `_evaluate_repetition_risk`（照搬孤儿版 949-980） | 7690 | T-10 |
| `static_description_risk = bool(...)` 四条 or | 7815 | T-08 |
| `score -= 420 if repetition...` | 7846 | T-10 |
| `"ending_core_chars"` 等 4 项进快照白名单 | 7866-7869 | D-24 |
| `"repetition_risk"` 等 5 项进快照白名单 | 7888 起 | T-10 |

**T-09 的实测根因（比 D-08 原描述更狠）**：原词表里的 `看 / 却 / 但 / 发现` 是汉语超高频**单字**，纯风景描写随手就有——「湖面看似平滑」「云影却淡」「但风铃不动」。实测一段 130 字纯景物含这四个字，`static_paragraph_count` 就是 0。也就是说 D-08 的后半不只是"自然现象动词算成了动作"，**主要漏洞是高频单字**。修法是重建词表（不放任何高频单字），并把自然现象动词单列成 `AMBIENT_MOTION_MARKERS`——它**不参与判定**，只为让护栏测试能断言它没混进动作表。词表收紧后真实语料（n=136）`max_static_run` 分位从全 0 右移到 p50=1 / max=2，`static_paragraph_count` p95 从 2 到 4：**检测器这才真的开始工作**。

**T-08 的阈值决定（没有照抄孤儿版）**：前 3 条阈值按方案对齐孤儿版，但**第 2 条的 `max_static_run` 保持 `>= 3`，没有放松到孤儿版的 `>= 2`**。依据是 §11.2.1 真实语料触发率：生产原状 0.000、孤儿版原样 0.044、孤儿版+第 2 条保持 3 → **0.029（采纳）**、再把第 4 条的 `static_paragraph_count` 抬到 4 → 0.022、抬到 5 → 0.015。0.044 与 0.029 都在底线门可接受范围内，取宽的那个符合「宁可漏判不要误杀」。**这个阈值单独有一条测试钉住**（见下表 `test_clause_2_threshold_stays_at_three_static_paragraphs`），理由在反向验证一节。

**T-10 照搬，一个阈值都没动。** 真实语料实测 `repetition_risk` 触发率 **0.000**（`repeated_instances` p95=0、max=1），所以这道门不会碰到正常文本，可以直接做 blocker 而不需要 soft_pass 兜底。判罚 −420 的定标依据写在函数注释里：必须大于重复段落自身能刷到的正分（`paragraph_count` +216 与 `progression_unit_count` +288），否则复制粘贴仍然划算。实测灌水样本总分 **−260**，短应答样本 **+273**。

**D-24 的修法与 6 个失败方向（这条最值得抄走）**：直觉做法是把 260 字尾窗改小，**全部更差**。变体 A/B（按字符或按段落把语义窗口缩到 60~200）在真实通过池上的通过率是 0.475~0.782，而基线是 **0.812**——那是误杀，不是召回。真正有效的是**保留尾窗、另加一道末段否决**（变体 G）：按换行切出最后一段，若该段零语义钩子命中，且满足「弱信号 >= 2」或「长度 >= 150 字」，则整章章末压力不通过。标定：`ENDING_CORE_WEAK_ONLY_LIMIT` w_min=1 → 0.762、**w_min=2 → 0.802（采纳）**、w_min=3 → 0.812 但放过坏样本；`ENDING_CORE_FLAT_CHARS` 取 120/150/200 都是 0.802（**零额外代价**，因真实末段 p95=151）。净代价 = 真实语料多拦 1 个样本（末段 76 字、弱信号 `却 / 忽然`）；False 池 0/13 前后不变。

**D-24 的一个接线陷阱**：`_evaluate_ending_pressure` 原来只收 `condensed_text`，而 `condensed` 已经把换行去掉了，**切不出末段**。所以调用点必须显式传原文 `raw_text=text`。这一处漏了不会报错，只会让末段判定静默退化成"整段就是尾窗"——反向验证里专门有一条覆盖它。

**D-24 修好带来的连带效果**：8.3 第 6 条铁律（结尾类样本必须自带 >= 260 字尾巴）**已可放宽**。证明是新增的 `SHORT_TAIL_PUNCTUATION_HOOK` / `SHORT_TAIL_FLAT_CLOSURE`：尾巴只有 31 / 24 字，没有任何填充，同样被拦（`ending_pressure_missing`，分差 260）。同一个坏结尾在修复前是 score=1302 / `codes=[]`。`BAD_PUNCTUATION_HOOK` / `BAD_FLAT_CLOSURE` 的 275 字填充**故意保留**，作为「长填充 + 泄气结尾」的历史对照，`_FLAT_ENDING_FILLER` 的注释已改写说明这一点。

**D-25 的解法不是"补一个样本"，是给四条 or 各配一个只命中自己的样本**。D-25 原方案只要求补 `max_static_run >= 3` 的多段样本。实际做法更严：新增 `class TestStaticDescriptionRiskBranches`，里面有一个 `_clause_flags` 把四条判定各算一遍，每条判定的测试都断言**「本条 True 且其余三条全 False」**。样本串味（同时命中两条）会让测试自己红——因为串味的样本改坏任一条都不会红，那正是 D-25 的成因。四个专用样本：

| 判定 | 样本 | 实测归因 |
|---|---|---|
| 第 1 条（无对话 + 段数 <= 4） | `BAD_ALL_DESCRIPTION`（既有） | wc=2331 / para=1 / dlg=0 / run=0 |
| 第 2 条（静态连段 >= 3） | `STATIC_RUN_FLOOD` | wc=1708 / run=16 / sp=16 / dlg=0，密度过关 |
| 第 3 条（低密度 + 连段 >= 2） | `STATIC_LOW_DENSITY` | wc=2227 / run=2 / sp=15 / `event_density_passed=False` |
| 第 4 条（对话掩护，T-08 新增） | `STATIC_TOKEN_DIALOGUE` | wc=1934 / run=2 / sp=16 / **dlg=4**，密度过关 |
| （阈值哨兵，不命中任何条） | `STATIC_RUN_AT_LIMIT` | wc=1908 / run=**2** / dlg=0，密度过关 → 四条全 False |

**27 条新增测试分四个类**：

| 类 | 条数 | 锁住的东西 |
|---|---|---|
| `TestStaticActionMarkerTable` | 5 | T-09 词表本身：高频单字不得入表、`AMBIENT_MOTION_MARKERS` 不得漏进动作表、逃逸样本必判静态、真动作段必判非静态、100 字门槛下边界 |
| `TestStaticDescriptionRiskBranches` | 8 | T-08 + D-25：四条 or 逐条只命中自己、第 2 条阈值哨兵、两个指标进快照、正向对照四条全不命中 |
| `TestRepeatedParagraphFlood` | 7 | T-10：检出、硬 blocker、判罚大于可刷正分、短应答不误报、其余坏样本不误报、5 个快照字段、800 字启用门槛 |
| `TestEndingCoreWindow` | 7 | D-24：短标点尾巴不再被掩护、短收束尾巴走 closure 路径、末段长度就是末段而非定长窗、两个阈值常量、正向对照仍过、4 个快照字段、分差 |

**与原方案的 4 处偏差**：

- **① 增量 +5 → 实际 +27。** 主因是 D-25 的解法从「补 1 个样本」升级成「四条判定各配互斥样本 + 归因辅助」，本身就是 8 条；其次 D-24 的 4 个新字段、T-10 的 5 个新字段都各需一条快照测试（那是新字段唯一的静默丢弃点）；词表类的 5 条则是因为**词表坏掉不会报错**，只测下游抓不到。
- **② T-08 第 2 条阈值没对齐孤儿版**（`>= 3` 而非 `>= 2`），依据是真实语料触发率，见上文。
- **③ T-10 的快照字段名与方案不同**：方案写 `longest_repeated_length` / `repetition_ratio`，实际照搬孤儿版用 `longest_repeated_paragraph_chars` / `repeated_paragraph_ratio`，并多带 `repeated_paragraph_instances`。**照搬源的字段名优先**——留着不一致等于给 T-19（删孤儿文件）埋一次改名。
- **④ D-24 修法与 D-24 条目里的设想相反**：条目建议缩小尾窗，实测缩小一律更差，改成"保留尾窗 + 末段否决"。D-24 条目正文保留原设想作为"当初怎么想的"备查。

**顺手修掉的一个潜伏缺陷（不在本批范围，但不修就没法做 T-10）**：批 3 的测试辅助函数 `_grow` 只替换首行的 `＃` 占位符，其余各行逐字复制。T-10 一落地就暴露：`GOOD_DRAMATIC` 实测有 6 个段落各重复 8 次（最长 46 字），`BAD_FLAT_CHATTER` 有 2 个各重复 10 次，于是**正向对照自己带上了 `repeated_paragraph_flood`**。修法是给「归一化后 >= 30 字」的行加逐轮不同的序数前缀（短行不动，否则引号离开行首会影响对话痕迹判定）。同一根因还打中一条既有测试 `test_structural_gate_accepts_dense_scene_evidence_when_structure_keywords_are_rephrased`，它用 `(...) * 5` 拼正文，同样已改成逐轮前缀。**教训：任何"复制样本凑字数"的测试辅助，都要保证进入统计的单位是唯一的**，否则新增一道退化检测就会先打中自己的样本。

**反向验证**（`_probe_b6_reverse.py`，改**源码文本**共 16 处后逐条跑 pytest，跑完写回原文并 diff 校验，用完即删）：**16/16 必红**，恢复校验 True。逐条改坏点 → 必红测试：① 把「看/却/但/发现」放回动作表 → 词表测试 + 逃逸样本测试；② `AMBIENT_MOTION_MARKERS` 加一个动作词 → 泄漏测试；③ 去掉动作词判断（全判静态）→ 真动作段测试；④ 删第 4 条判定 → 对话掩护测试；⑤ 第 2 条门槛松到 `>= 2` → **阈值哨兵测试**；⑥ 删第 3 条判定 → 低密度测试；⑦ 重复检测恒 False → 4 条重复测试；⑧ 30 字门槛降到 3 → 短应答误报测试；⑨ 判罚清零 → 判罚测试；⑩ blocker 降级 → 硬 blocker 测试；⑪ 丢一个重复快照字段 → 快照测试；⑫ 末段否决恒 False → 4 条 D-24 测试；⑬ `ENDING_CORE_WEAK_ONLY_LIMIT` 抬到 3 → 阈值测试 + 短标点尾巴测试；⑭ `ENDING_CORE_FLAT_CHARS` 抬到 400 → 长平结尾测试；⑮ 调用点不传 `raw_text` → 末段长度测试 + 短标点尾巴测试；⑯ 丢一个 `ending_core_*` 快照字段 → 快照测试。

**反向验证暴露的一个覆盖缺口（当场补掉）**：第一轮里 ⑤「第 2 条门槛松到 `>= 2`」**全绿**。原因是归因用的 `_clause_flags` 在测试里重算判定逻辑，检测不到生产端阈值漂移，而其余测试都只断言「该命中的命中了」——放松门槛不会让它们漏掉。补 `STATIC_RUN_AT_LIMIT`（`max_static_run` 恰好 2）+ `test_clause_2_threshold_stays_at_three_static_paragraphs` 后，该改坏点单独必红。**方法论：凡是"测试里重算了一遍生产逻辑"的归因辅助，都必须另配一个卡在阈值边界上的哨兵样本**，否则阈值漂移是测不出来的。

**清理**：`_probe_batch6.py` / `_probe_batch6_corpus.py` / `_probe_b6_tests.py` / `_probe_b6_reverse.py` / `_probe_c3.py` / `_probe_good.py` / `_probe_good2.py` / `_probe_gate.py` 与 `_probe_b6_orchestrator.bak` 已全部删除，`backend` 下无遗留。所有探针全程只打印指标、布尔与分位数，不打印任何正文，符合 2.2 的证据脱敏要求。

---

### 批 7：字数与焦点人物（T-11 / T-12）

#### T-11 焦点人物缺席进入候选评分（对应 D-12，**注意 D-12 已修正过表述**）

- **先记住修正后的事实**：焦点人物缺席**不是完全没检测**——`longform_context_service.py:734-745` 的连续性门已有 `chapter_focus_missing`（warning，数据源 `package.cast_plan.chapter_focus_names`）。T-11 补的是另外三个缺口：① 不进入候选评分；② `package is None` 时（短篇/未启用长篇上下文）完全不生效；③ `chapter_mission` 这条数据源从未被用。
- **改动**：
  1. 移植 `story_quality_scoring.py:909-947` 的 `_collect_focus_character_names` 到生产路径，数据源用 `chapter_mission`（`focus_characters` / `character_focus` / `pov_character` / `scene_list[].characters` 四个来源）。
  2. `_score_story_quality_candidate` 加判罚 **−240**，条件 `focus_character_names and not focus_character_hits and word_count >= 1200`。
  3. 快照加 `focus_character_names` / `focus_character_hit_count` / `missing_focus_characters` / `focus_character_missing`。
- **三个必须照抄的设计**（孤儿版这三点是对的）：
  - `placeholders = {"主角","男主","女主","角色","角色A","角色B","protagonist","pov"}` 过滤占位符；
  - 按 `[，。；、,;\s/|]+` 切分，只留 2-12 字，去重取前 8；
  - 判罚条件是 `not focus_character_hits`（**一个都没出现**才罚）——配角某章不出场是正常的。
- **保持 warning，不加 blocker**：LLM 常用别名/称谓替代本名（「顾家小姐」代替「顾棠」），字符串匹配会误判。与连续性门的判断保持一致。
- **测试**：`test_focus_character_missing_penalizes_candidate`（2 个名字全缺席且 ≥1200 字 → 判罚 −240）+ `test_focus_character_placeholder_is_ignored`（`["主角"]` → `focus_character_names == []`，不判罚）。
- **全量**：+2。**风险低**（不加 blocker 不会提高拒稿率）。

#### T-12 字数维度四层断链全修（对应 D-13 + D-20，**四处断点，只修一处等于没修**）

- **这是全文档结构最复杂的一条**。四层断点，从内到外：

  **第 1 层：评分函数内部根本不用字数参数**
  - 证据：`pipeline_orchestrator.py:7454-7578` 范围内，`target_word_count` / `min_word_count` **只出现在函数签名的两行里**，函数体内零引用。
  - 改动：移植孤儿版 `story_quality_scoring.py:1317-1325` 的计算 + `1361-1381` 的三条判罚：
    ```python
    preferred_floor = max(minimum_floor, int(target_floor * 0.92)) if target_floor else minimum_floor
    word_count_below_min        = bool(minimum_floor and word_count < minimum_floor)
    word_count_far_below_target = bool(preferred_floor and word_count < preferred_floor)
    upper_target = int(target_floor * 2.0) if target_floor and target_floor <= 2500 else (int(target_floor * 1.6) if target_floor else 0)
    word_count_far_above_target = bool(upper_target and word_count > upper_target)
    # 判罚
    score -= 620 if word_count_below_min else 0
    score -= 520 if word_count_far_above_target else 0
    score -= 180 if word_count_far_below_target and not word_count_below_min else 0
    ```
    **`upper_target` 用孤儿版的 2.0 / 1.6，不要用死代码 `_score_fallback_candidate` 里的 1.25**（1.25 太严，正常章节容易超）。

  **第 2 层：5 个调用点不传字数**
  | 行号 | 调用者 | 现状 |
  |---|---|---|
  | 442 | `_evaluate_structural_quality_gate_for_content` | ✅ 传了（但传的是硬编码默认值，见第 3 层） |
  | 3437 | 候选评分主路径 | ❌ 不传 |
  | 4039 | 续写后重评 | ❌ 不传 |
  | 5732 | `_evaluate_first_draft_retry` | ❌ 不传（**且它自己签名里是必填**，见第 4 层） |
  | 6492 | enrichment 后重评 | ❌ 不传 |
  | 7590 | `_fallback_select_best_version` | ❌ 不传 |

  **第 3 层：质量门签名的硬编码默认值（D-20）**
  - `_evaluate_structural_quality_gate_for_content`(430) 签名 438-439：
    ```python
    target_word_count: int = 3000,
    min_word_count: int = 2000,
    ```
    **4 个调用点（2098 / 3716 / 3725 / 3938）全部不传** → 质量门**永远按 3000/2000 判**，与 `active_config` 完全脱钩。用户配 6000 字长章按 3000 判、配 1500 字短章按 2000 判最低（比目标还高）。
  - 改动：**删掉默认值改成必填**，让任何漏传变成 `TypeError`（在测试阶段暴露，而不是静默用错值）。4 个调用点补上从 `config` 取的实际值。

  **第 4 层：`_evaluate_first_draft_retry` 自己规范化了却不传下去**
  - `5723-5738`：签名里 `target_word_count: int, min_word_count: int` 是**必填**，`5737-5738` 还自己做了 `max(0, int(...))` 规范化，但 `5732` 调用评分器时**就是不传**。这是最明显的一处「参数拿到手又扔掉」。
- **分步实施（不要一次全改，否则出问题无法定位）**：
  1. **步骤 A**：第 1 层加字段但**判罚系数全设 0**（只让字段出现在快照里，行为零变化），跑全量确认 `659+N passed` 不变。
  2. **步骤 B**：把系数改成 620/520/180，跑全量。**此时预期有测试变红**——因为很多测试样本字数远低于默认 3000。逐个判断是「样本该加长」还是「该显式传小一点的 target」。
  3. **步骤 C**：修第 2/3/4 层的调用点（含删默认值）。这一步会让**实际生效的字数从 3000/2000 变成用户配置值**，是行为变化最大的一步。
- **测试**：`test_word_count_below_min_penalizes_heavily`（1000 字 vs `min=2000` → −620）+ `test_word_count_far_above_target_penalizes`（`target=2000` 实际 5000 → −520）+ `test_quality_gate_requires_explicit_word_count_config`（不传字数参数 → `TypeError`，这条是防回退护栏）。
- **全量**：+5，**步骤 B 会有既有测试变红需要逐个处理**（预估 3-8 个）。
- **风险高**：这条改完，质量门第一次真正按用户配置的字数判定。**必须做真实生成验证**（第 8.4 节），尤其验证短章（1500 字）与长章（6000 字）两个极端。

#### 批 7 实际落地记录（2026-08-19 完成，基线 718 → 742）

**全量实测**：~~742 passed in 62.50s, 0 failed~~ **（假绿，D-26。「0 failed」是插件冲突吞掉测试后的假象，真实值为 727 passed / 36 failed）**。

**跑测试时踩到的一个环境坑（不是代码问题，但会浪费半小时）**：本批多次出现 `pytest app` 或 `pytest app/services` **跑到中途被 SIGTERM 杀掉（exit 143）**，而**把 62 个测试文件显式列在命令行上、或加 `-v`、或分片跑**，同样的集合就能全绿。两种方式收集数都是 646，逐片跑也全过——**不是某个测试挂起**。根因未查清（疑似本机 Windows 下长时间静默输出被外层判超时）。处理办法：遇到 143 先 `tasklist | grep python` 清掉残留进程再重跑，或改用显式文件列表 / `-v`。**exit 143 既不等于失败也不能当通过**——必须拿到 `N passed` 那一行才算。

**T-11 落地（+9，方案说 +2）**：判罚 −240、四来源采集、占位符过滤、2-12 字切分、前 8 去重、`not focus_character_hits` 才罚、四个快照字段，全部按方案照抄孤儿版。**保持 warning 不加 blocker**，并**单独加一条测试钉住这件事**（`test_focus_absence_is_warning_not_blocker`）——别名误判的风险在于「升级成 blocker」这一步无声发生，光测判罚测不出来。多出的 7 条来自：占位符表大小写可比性、判罚不叠加、`word_count >= 1200` 门槛边界、四个来源各一条。

**T-12 落地（+15，方案说 +5）**：四层断点全修，按方案的步骤 A/B/C 顺序做。

- **第 1 层**（评分器内部）：三判罚 620/520/180 + 七个快照字段，`upper_target` 用孤儿版 2.0/1.6。**没有采纳死代码里的 1.25**——真实语料实测（n=82 历史通过池）1.25 会让 `far_above` 触发率从 0.012 涨到 0.305，是 25 倍误杀差距，见 §11.2.1 批 7 表。
- **第 2 层**（`_evaluate_first_draft_retry`）：这层的断链最刺眼——函数签名收了 target/min、自己还做了 `max(0, int(...))` 规范化，调用评分器时就是不传。后果不只是漏判：同一份 `story_guard` 里 `reason_codes` 说字数不足、字数标志却说没问题，**自相矛盾且长期没人发现**。
- **第 3 层**（`_evaluate_structural_quality_gate_for_content`）：默认值 3000/2000 **删掉改成必填**（keyword-only 无默认）。这一步让 11 处测试调用点当场 `TypeError`——**这正是设计意图**，静默用错值判定通过与否才是危险的。11 处统一补 `_SAMPLE_TARGET_WORDS=2500 / _SAMPLE_MIN_WORDS=2250`（常量提到文件头，因为前半段的 gate 类测试也要用）。
- **第 4 层**（`_fallback_select_best_version`）：**默认值取 0 而不是删掉**，与第 3 层相反。取舍依据是失败模式不同：第 3 层判「通过与否」，缺配置按错值判会误杀章节；第 4 层只做**候选排序**，所有候选共享同一份配置，缺配置时字数维度整体缺席、排序退化成 T-12 之前的行为，不会把某个候选单独判死。这个不对称**在源码里写了注释、在测试里各钉一条**（`test_gate_helper_refuses_to_default_word_config` / `test_fallback_defaults_stay_neutral_not_hardcoded`），否则后人"统一风格"时必然改错一边。
- **接线点共 8 处**：质量门 3 处（含 enrichment 前后两次重评）、`reader_simulator` 后重评 1 处、`final_quality_guard` 1 处、首稿重试 1 处、retry 候选 1 处、fallback 排序 1 处（并给 `_run_ai_review` 加了字数参数透传）。

**与方案的四处偏差**：

- **① 步骤 B 预期的"既有测试变红"没有发生**（方案预估 3-8 个）。原因是步骤 C 把默认值从 3000/2000 改成必填/中性 0，而既有测试样本都在 2310-2810 字——按 3000/2000 判会大面积红，按显式传的 2500/2250 判则字数维度中性。**顺序救了这一批**：先改判罚系数、再改默认值，中间那一刻的红是被步骤 C 一起消掉的。
- **② `word_requirement_met` 用三态而非 bool**：没配 `min_word_count` 时是 `None`（不适用），不是 `False`。写成 bool 会让所有未配 min 的章节在前端显示成"字数未达标"。
- **③ 发现并保留一处已知不单调**：`target=2500` 时 upper=5000，`target=2501` 时 upper=4001——目标涨 1 字上限反降 999。**没有修**，因为 2500 是短章/长章分界，两侧"超长"的含义本就不同；改之前必须按 §11.2.1 灌真实语料。加了 `test_upper_ceiling_is_known_non_monotonic_at_2500` 把这个反直觉行为钉住，避免后人顺手"修单调性"时无声改掉短章上限。
- **④ 三判罚一律不进 `quality_issue_codes`、不进 gate blockers**：字数是评分维度不是底线门。真实语料里 22% 的历史正文低于 min（p50 只有目标的 0.608），升级成 blocker 会当场拒掉五分之一的稿子。单独一条测试钉住（`test_word_penalties_do_not_become_gate_blockers`）。

**反向验证**（`_probe_b7c_reverse.py`，沿用批 6 的"改源码文本→跑 pytest→写回→SHA256 校验"，用完即删）：**14/14 必红**，写回校验一致。改坏点 → 必红：① 撤 below_min 判罚；② 撤 far_above；③ 撤 far_below；④ 让 far_below 叠加到 below_min；⑤ upper 系数换 1.25；⑥ 去掉 min>target 钳制；⑦ `word_requirement_met` 退化成 bool；⑧ 第 1 层参数恢复成死参数；⑨ 第 2 层漏传；⑩ 第 3 层恢复 3000/2000 默认值；⑪ 第 4 层漏传；⑫ 第 4 层默认值改硬编码；⑬ 删七字段白名单；⑭ 把字数判罚升级成 gate blocker。

**反向验证第一轮暴露的 6 个假绿（值得记）**：⑦⑨⑩⑪⑫⑭ 首轮全绿，**都不是覆盖缺口，是探针自己写错了**：
- ⑦：`word_requirement_met` 在源码里有**两处**（snapshot 与顶层返回），`str.replace(..., 1)` 只改了一处，另一处仍是三态 → 测试当然绿。改成替换 2 处后必红。
- ⑨⑩⑪⑫：改坏点在 `TestWordCountWiringAcrossLayers`，但 `-k` 选择器写的是 `WordCountPenalties`，**把该红的类整个 deselect 掉了**。选择器放宽成 `WordCount` 后全部必红。
- ⑭：原设计往评分器局部的 `violations` 列表追加一项，而 gate blockers 是在 `_build_structural_quality_gate` 里另算的，**改动根本到不了判定路径**。锚点换成 `blockers: List[...] = []` 之后必红。

**方法论**：反向验证"没红"有三种成因——真覆盖缺口、**改坏点没落在判定路径上**、**选择器把该红的测试排除了**。后两种是探针 bug，会伪装成"测试不够严"。判别方法：先确认改坏后**至少有一条测试被 selected**（看 `N passed, M deselected` 里 N 是否包含目标类），再确认改动点确实在被测函数的调用链上。批 6 的 16/16 之所以一次过，是因为那批的改坏点都在同一个函数体内。

---

### 批 8：三态语义与短路返回值（T-13 / T-14）

#### T-13 `dialogue_changes_state` 改三态（对应 D-07）

- **问题**：`if not expected_dialogue: passed = True` —— 任务书没声明对话预期时，**这一维直接白给通过**。而它同时被 4 条软放行当作**正向证据**使用：
  ```python
  and story_guard.get("dialogue_changes_state", True)      # 5743-5760 附近
  ```
  即：任务书没写 `dialogue_strategy` → 这维恒真 → 软放行更容易成立 → 白给 +140 分。
- **改动（拆两步，不要一次改完）**：
  - **步骤 1（改评分）**：`dialogue_changes_state` 返回三态——`True`（检查过且通过）/ `False`（检查过且不通过）/ `None`（未检查，因为任务书没声明预期）。同时加显式字段 `dialogue_expectation_declared: bool`。**此时消费方还是 `get(..., True)`，`None` 会被当假值** → 所以步骤 1 单独提交时要确认全量结果，预期会有测试红。
  - **步骤 2（改消费）**：所有消费点从 `get("dialogue_changes_state", True)` 改成 `is not False`：
    ```python
    and story_guard.get("dialogue_changes_state") is not False
    ```
    语义变成「只要不是明确失败就不算反对证据」，`None` 不再被当成正向证据也不被当成失败。
- **消费点清查（改前必做）**：
  ```bash
  cd /d/小说写作/xuanqiong-wenshu/backend && grep -n "dialogue_changes_state" app/services/*.py app/api/routers/*.py
  ```
  **前端也要查**（`chapterQuality.ts` 的字段映射会把 `null` 显示成什么？需要显示成「不适用」而不是「未通过」）。
- **与 E-10 合流**：E-10 的 `mission_dialogue_strategy_empty` warning 用的是同一个判断，两者同批做省一半工作。
- **测试**：`test_dialogue_state_returns_none_without_expectation`（任务书无 `dialogue_strategy` → `None` 而非 `True`）+ `test_soft_pass_does_not_count_unknown_dialogue_as_evidence`（`None` 时软放行不成立）。
- **全量**：+3。**风险中**：软放行变严会提高 blocker 率（所以排在 T-22 之后）。

#### T-14 事件密度短路返回值改 `None` + 新增 `event_density_evaluated`（对应 D-15）

- **位置**：`pipeline_orchestrator.py:7192-7204`
  ```python
  if word_count < 800:
      return {"event_density_passed": True, ..., "progression_unit_count": 0,
              "progression_unit_rate": 1.0, "event_density_per_1000": 0.0,
              "state_change_window_pass_rate": 1.0, "max_plain_unit_run": 0}
  ```
- **问题不是短路本身**（800 字以下统计不可靠，短路是对的），**而是返回值自相矛盾**：`progression_unit_count=0` 同时 `progression_unit_rate=1.0`、`density_per_1000=0.0` 同时 `passed=True`。这些值会流进快照、日志、API、前端，显示成「推进单元 0 个，推进率 100%」。
- **另一个隐患**：`PipelineConfig.min_word_count` 默认 **500**（114 行）。如果有配置走到 500 字目标，整章都在 800 以下 → **整个密度门永久失效且无人知晓**。
- **改动**：
  ```python
  if word_count < 800:
      return {"event_density_evaluated": False,     # 新增显式标记
              "event_density_passed": None,          # 未评估，不是通过
              "progression_unit_count": 0,
              "progression_unit_rate": None,         # 不再谎报 1.0
              "event_density_per_1000": None,
              "state_change_window_pass_rate": None,
              "max_plain_unit_run": 0,
              "event_density_skip_reason": "word_count_below_800"}
  ```
  所有消费方改成 `is not False`（与 T-13 同一套模式）。**前端要把 `null` 显示成「样本过短未评估」**。
- **明确不要做的**：不要降低 800 这个阈值。800 字以下的中文正文切出来的句子太少，`rate` 类指标方差极大，降阈值只会引入噪声。
- **测试**：`test_short_content_marks_density_as_not_evaluated`（600 字 → `event_density_evaluated is False`、`event_density_passed is None`）+ `test_short_content_does_not_report_fake_full_rate`（断言 `progression_unit_rate is None`，**修复前这条必红**，因为现在返回 1.0）。
- **全量**：+2。**风险低-中**：改的是短样本路径，主要风险在前端对 `null` 的处理。

---

### 批 8 实际落地记录（2026-08-18 ~ 2026-08-19）

**结果**：`test_generation_quality_guards.py` 实测 **`167 passed, 21 failed`**（21 个失败全是 D-27 A 组的先存欠账，与本批无关）。三态改造本身全绿。

**T-13 落地**：三态 + `dialogue_expectation_declared` + `dialogue_state_applicable` 按方案做完，**四层消费点全部改成 `is False` 显式判定**（gate blocker / 定向修复清单 / 重试原因码 / AI 复核覆盖）。定标实测分差：`True-None = 140`、`None-False = 140`——即 `None` 落在正中间，既不加分也不倒扣，这正是三态想要的语义。

**T-14 落地**：短路分支三个 `passed` 全改 `None`，比率类改 `None` 而非 `0`（避免前端画出一根 0 的进度条），加 `event_density_evaluated` / `event_density_skip_reason` 双标记。计分从两分支改三分支，实测旧写法把 `None` 当失败合计倒扣 **490** 分。

**反向验证（`_probe_b8e_tests.py`，24 个文本变异全部被捕获）**：与批 6 / 批 7-C 同法——**改源码字符串而非 `setattr`**，因为这两个缺陷的判据全写在函数体里（`is False` / `is not False` / 三分支 if），换类属性碰不到。脚本在 `finally` 里还原并比对 sha256，且**按当前文件行尾编码锚点**（CRLF 文件里用 LF 锚点一个都匹配不到；`read_text`/`write_text` 会把行尾整体归一，导致"内容还原了但整个文件被重写"）。

**D-22 前端落地**：`chapterQuality.ts` 补 3 条 event_density 兜底文案，并加一条测试钉住**三态 `null` 不得显示成风险**（`treats null tri-state metrics as not-applicable rather than failures` → `issues == []`、`tone == 'success'`）。这条是本轮核心谎报的前端侧闭环。

**⚠️ T-13 的遗留缺口（不能算完全闭环）**：见 D-27 B 组第 5 行——`_count_dialogue_state_change_markers` 对"具体揭示 / 做出选择 / 外部压力"三类语义**一个都认不出来**（该样本实测 0 个标记，测试要求 ≥2）。三分支结构是对的，但喂进去的计数偏低，会让本该 `True` 的样本落到"未声明预期 + 计数不足门槛"那条路。**修法归 T-26，须走真实语料校准。**

**本批的一次事故（教训比成果重要）**：期间执行 `git checkout` 覆盖了 `pipeline_orchestrator.py`，抹掉了当时未提交的生产改动。**恢复办法已验证可行**：扫 `~/.claude/projects/<项目>/` 下全部 transcript（`rglob("*.jsonl")`，**必须含 `subagents/` 与 `subagents/workflows/` 子目录**），提取针对目标文件的 `Edit`/`Write` 记录按时间戳排序重放（脚本见 `_recover_scan.py` / `_recover_replay.py`）。本次重放 97 次编辑全部成功。**但这不是安全网**——它只能救回"曾经通过工具写入过"的内容，且 D-27 证明了**扫不到的东西就是从来没写过**，别指望恢复。**动 `git checkout` / `git restore` 前先 `git stash` 或 `git diff > backup.patch`。**

---

### 批 9：权重重配（T-16）—— **对生产行为影响最大的一批**

#### T-16 两段式评分：有上限的资格分 + 无上限的质量分（对应 D-09）

- **问题（实测拆解）**：形式项合计 **672 分全部可机械满足**，与内容质量无关：
  | 项 | 分值 | 怎么机械满足 |
  |---|---|---|
  | 段落数 | +216 | 多敲回车 |
  | 引号数 | +120 | 多加对话 |
  | 推进单元数 | +288 | 多写短句（D-02 修好后会难一些，但仍可刷） |
  | 字数达标 | +48 | 凑字数 |
- **后果**：一篇「格式完美内容空洞」的稿子能拿到与「格式一般但冲突扎实」的稿子相近甚至更高的分数 → 多候选择优形同随机。
- **改动（两段式）**：
  ```
  资格分（Eligibility，有上限，占比 ≤35%）：段落/引号/字数/推进单元数等形式项，
      每项**封顶**，达到基本要求即满分，超出不再加分。
  质量分（Quality，无上限的负向为主）：场景达成、对话改变状态、章末压力、静态描写、
      事件密度、重复、焦点人物、承接 —— 以判罚为主，判罚不设下限。
  最终分 = 资格分（封顶） + 基准分 − 质量判罚总和
  ```
  **关键设计**：形式项**封顶**是核心。封顶之后「多敲回车」的收益归零，刷分通道被堵住。
- **验收标准（硬性，来自 D-09）**：
  - 好坏样本分差 **≥600 分（≥45%）**；
  - 分差必须**分布在 ≥3 个维度**上（不能靠单一维度撑起全部差距，否则是过拟合到某一条规则）。
- **前置**：**必须在 T-04/T-05/T-06（事件密度可靠）与 T-10/T-11/T-12（判罚项补齐）之后**。在指标方向都反着的时候重配权重，只会把错误放大。
- **测试**：`test_quality_score_gap_between_good_and_bad_samples`（用 T-07 的 8 个坏样本 + `GOOD_DRAMATIC`，断言分差 ≥600）+ `test_form_only_content_cannot_reach_high_score`（构造「格式完美但全是寒暄」的样本，断言分数 < `GOOD_DRAMATIC` − 600）。
- **全量**：+2，**但预期有较多既有测试的分数断言需要更新**（凡是断言具体分数值的测试都会变）。改之前先跑 `grep -n "score.*>=\|score.*==" app/services/test_generation_quality_guards.py` 清点。
- **风险最高**：这条改完，候选排序结果会整体变化。**必须做真实生成端到端验证 + E-08 批量评测对比**，这也是为什么 E-08 建议在批 3 之后就做完。

---

### 批 10：清理收尾（T-17 / T-18 / T-19）

#### T-17 移植确定性清理与 Markdown 呈现清理（对应 D-11）

- **现状**：四个清理方法在生产路径**全部缺失**（`grep` 结果全 0），孤儿版有实现：
  | 方法 | 孤儿版行号 | 职责 |
  |---|---|---|
  | `_apply_deterministic_cleanup` | 1069 | 确定性清理主入口 |
  | `_sanitize_markdown_presentation` | 1201 | 去掉正文里的 Markdown 标记 |
  | `_detect_chapter_artifact_markers` | 983 | 检测章节污染标记（生产版有，见下） |
  | `_fallback_select_best_version` | 1006 | 兜底选版 |
- **生产现状的问题**：`_detect_chapter_artifact_markers`(7417) **只检测、判罚 −480 并 block，但不清理**。也就是说正文里出现「## 第三章」「**冲突升级**」「（本章完）」这类污染标记时，系统的反应是**拒稿**，而正确反应是**确定性地清掉它们再继续**——这类问题不需要 LLM 参与，纯字符串处理就能解决，拒稿是纯粹的浪费。
- **改动**：移植 `_apply_deterministic_cleanup` + `_sanitize_markdown_presentation`，在质量门**之前**执行；`_detect_chapter_artifact_markers` 保留（清理后仍残留的才判罚）。
- **三条硬性约束（清理是改用户正文，必须谨慎）**：
  1. **只清 Markdown 标记与精确重复，绝不做语义改写**。删除 `#`/`**`/`- ` 前缀、`（本章完）`、`第 N 章` 标题行；不改任何一句正文措辞。
  2. **diff 必须记日志**：清理前后的字符数变化与被删片段（截断到前 40 字）写进 `runtime_metadata["deterministic_cleanup"]`。用户要能知道系统动了什么。
  3. **不得跌破 `min_word_count`**：清理后如果字数低于最低要求，**放弃清理并保留原文**（返回原始内容 + 一条 warning）。宁可留着污染标记也不要因为清理把章节变成不合格长度。
- **测试**：`test_deterministic_cleanup_removes_markdown_headings`（正文含 `## 第三章` → 被清掉、diff 记录）+ `test_cleanup_aborts_when_result_below_min_word_count`（清理会让字数跌破 min → 保留原文）。
- **全量**：+3。**风险中**：改的是正文内容。**第 3 条约束是安全阀，必须先实现它再实现清理逻辑。**
- **附带**：T-22 的改动 4（`enable_self_critique` 关闭时至少走确定性清理）在这里接上。

#### T-18 自评豁免提阈值（对应 D-14，**顺序敏感，不要提前做**）

- **现状**：`ending_pressure_missing` 在 `critique_score >= 75` 时、`event_density_weak` 在 `>= 70` 时**不作为 blocker**。这构成自评闭环——模型自己给自己打 75 分就能豁免结构门。
- **绝对不要直接删除这两条豁免**。它们当初就是为了压误杀而加的：在 D-03/D-04/D-16 都没修的情况下，这两个门的误判率极高，删掉豁免会造成大面积拒稿。
- **正确顺序（三步，缺一步都不要动阈值）**：
  1. 先完成 T-02/T-03/T-15（章末压力准确率）与 T-04/T-05/T-06（事件密度准确率）；
  2. 通过 E-09 的趋势端点**统计豁免实际触发率**（真实数据里这两条豁免被用了多少次、用了之后的章节质量如何）；
  3. **只有触发率数据显示豁免已很少必要时**，才把阈值提到 `75 → 88`、`70 → 85`。
- **测试**：`test_ending_pressure_exemption_requires_high_critique_score`（`critique_score=80` 时**不再**豁免，`=90` 时豁免）。
- **全量**：+2。**风险中-高**：会提高拒稿率。**如果第 2 步的数据不支持，就不要做这条任务**——保留原阈值是完全可以接受的结果，写进文档也算完成。

#### T-19 删除孤儿模块 `story_quality_scoring.py`（对应 D-01，−1525 行）

- **前提**：**必须在 T-08/T-10/T-11/T-12/T-17 全部移植完成之后**。这个文件是所有移植的源，删早了就没参照了。
- **前置检查（必须全部为空）**：
  ```bash
  cd /d/小说写作/xuanqiong-wenshu/backend && grep -rn "story_quality_scoring\|StoryQualityScoringMixin" app | grep -v "^app/services/story_quality_scoring.py"
  ```
  期望：**0 结果**。（前序已用 `_cmp_scoring.py` 验证 `StoryQualityScoringMixin not in PipelineOrchestrator.__mro__`，即它确实未被继承。）
- **改动**：删除 `backend/app/services/story_quality_scoring.py` 整个文件。
- **为什么必须删而不是保留**：D-19 已经证明「维护两份实现」造成了真实错误——`_score_fallback_candidate` 在生产文件里被粘贴成必然抛 `NameError` 的死代码，而孤儿版是好的，且**没有任何测试能发现**。保留孤儿文件的每一天都在积累这种漂移。
- **删除前的最后一步**：把移植清单核对一遍，确认孤儿版里**这 6 项能力都已在生产路径落地**：字数判罚（T-12）、重复检测（T-10）、焦点人物（T-11）、静态第 4 条（T-08）、确定性清理（T-17）、Markdown 清理（T-17）。**逐条 grep 确认，不要凭记忆。**
- **测试**：`test_orphan_scoring_module_is_removed`：
  ```python
  def test_orphan_scoring_module_is_removed():
      with pytest.raises(ImportError):
          import app.services.story_quality_scoring   # noqa
  ```
- **全量**：+1，**且总耗时应下降**（少 1525 行的导入与收集）。
- **风险低**（已验证零引用），**但不可逆**（虽然 git 可恢复）。删除前把移植清单核对完。

---

## 8. 回归测试设计规范

### 8.1 测试放在哪里（不要新建文件）

- **全部加进 `backend/app/services/test_generation_quality_guards.py`**（**批 8 后 4438 行 / 188 收集（167 passed, 21 failed）**；本行原写「2151 行 / 56 个测试」，是批 1 之前的数字）。新增内容按批次分组成 class：`TestBadSampleRegression`（批 4 已建）、`TestEventDensityCalibration`、`TestWordCountDimension` 等。
- **明确不要新建 `test_story_quality_scoring.py`**——给孤儿模块写测试等于给它续命，与 T-19（删除孤儿）直接冲突。这条已写进第 10 节「明确不做」。
- 测试文件与被测模块同目录（`app/services/test_*.py`），这是本项目既有约定，不要改成 `tests/` 目录结构。

### 8.2 评分器怎么直接调（不需要起 FastAPI，也不需要 DB）

所有评分方法都是 `classmethod`，可以直接调用，这是本轮所有实证结论的取证方式：

```python
from app.services.pipeline_orchestrator import PipelineOrchestrator as P

result = P._score_story_quality_candidate(
    content=SAMPLE_TEXT,
    violations=[],
    chapter_mission=None,          # 或传 dict 模拟任务书
    target_word_count=3000,
    min_word_count=2000,
)
```

单独测某一维时直接调对应方法（`_evaluate_ending_pressure` 的第一个位置参数吃的是**去空白后的正文**，但**批 6 之后必须另传 `raw_text=` 原文**，否则切不出末段，末段否决会静默失效）：

```python
condensed = "".join(SAMPLE_TEXT.split())
P._evaluate_ending_pressure(condensed, None, raw_text=SAMPLE_TEXT)   # raw_text 必传，见批 6/D-24
P._evaluate_event_density(condensed, ...)
P._estimate_static_description_runs(SAMPLE_TEXT.splitlines())        # 吃段落 list，不是整篇字符串
P._evaluate_repetition_risk(SAMPLE_TEXT.splitlines(), word_count=len(condensed))  # 批 6/T-10
```

**T-12 步骤 C 之后**，`_evaluate_structural_quality_gate_for_content` 的字数参数变成必填，测试里必须显式传，否则 `TypeError`（这是有意设计的护栏）。

### 8.3 样本编写的七条铁律（本轮踩过的坑，逐条都有代价）

1. **字数必须 ≥800**，否则走 `_evaluate_event_density` 短路（T-14 之后是 `None`，之前是假的 `passed=True`），拿到的数据无效。**本轮第一版探针就栽在这里**：GOOD 样本只有 688 字，整组数据白跑。建议样本统一做到 1300-1600 字。
2. **扩写必须加序数前缀，不能整段复制**：
   ```python
   _ORD = ("初", "次", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")
   def _grow(block: str, times: int) -> str:
       return "".join(block.replace("＃", _ORD[i % len(_ORD)]) for i in range(times))
   ```
   否则 T-10 的重复段落检测会命中，判罚 −420 污染所有断言。
3. **每个坏样本只坏一个维度**。想测静态描写就不要在里面顺手写一个平淡结尾，否则测试失败时分不清是哪条规则起作用。
4. **必须配一个正向对照**（`GOOD_DRAMATIC`），断言它**不触发**任何被测 code。**所有调阈值的任务都必须让这条保持绿**——它是防误杀的唯一自动化防线。
5. **样本正文不要用专有名词**（人名/地名/物品名）。用「她」「他」「照片」「钥匙」这类通用词。理由见 D-06：专有词进了测试断言就会变成词表的硬依赖，词表想改都改不动。
6. ~~**测结尾的样本，坏尾巴本身必须 ≥260 字**~~ **（批 4 新增，✅ 批 6 已随 D-24 解除）**。原文如下，保留为历史：`_evaluate_ending_pressure` 只看 `condensed_text[-260:]` 这个**字符窗**，尾巴短了，正文里的强钩子会一起进窗口把坏结尾盖过去——**测试会一开始就绿，而且是假绿**（实测 38 字尾巴的样本 `codes=[]`、score 与正向对照完全相同）。
   **批 6 之后的新规矩**：尾窗仍在，但另有一道**末段否决**（按换行切出最后一段单独判泄气），所以**短尾巴样本可以直接写**——`SHORT_TAIL_PUNCTUATION_HOOK` / `SHORT_TAIL_FLAT_CLOSURE` 的尾巴只有 31 / 24 字，无任何填充，同样被拦。**新的注意点变成两条**：① 末段必须是**独立一行**（否决靠换行切段，把坏结尾接在正文同一行里等于没写）；② 想让末段否决走「零语义 + 弱信号 >= 2」这条路，尾巴里就不能有语义钩子——`ENDING_SEMANTIC_HOOK_MARKERS`（56 个）仍要逐条排掉，`ENDING_CLOSURE_MARKERS`（14 个）则是另一条独立路径，命中它走的是 `flat_closure_markers` 而不是 `ending_core_deflating`。
7. **断言用实测值，不要用文档里的数字**。文档会过期，探针不会。写断言前先跑一次探针把 `quality_issue_codes` 与关键指标打出来，按实际值写；如果实测与本文档冲突，**以实测为准并回来改文档**（批 4 就这样改掉了 D-05 表里两处错的预期 code）。

### 8.4 真实生成端到端验证流程（批 3、批 7、批 9 之后各做一次）

单元测试只能证明「给这段文本，评分器给出预期结果」，**不能证明真实生成不会被大面积拒稿**。以下三批改完必须做真实验证：**批 3（事件密度门槛）、批 7（字数四层）、批 9（权重重配）**。

**流程（成本可控版，一次约 3-5 章）**：

1. 选一个已有章节的项目，用**已有蓝图与任务书**（不要新建项目，避免蓝图生成的额外成本与变量）。
2. 生成 3 章：一个短章（目标 1500 字）、一个常规章（3000）、一个长章（6000）。**三个字数档都要覆盖**，因为几乎所有阈值都是按 `word_count` 分档的（`< 2500` / `< 7000` / `>= 7000`）。
3. 每章记录：是否通过质量门、blocker codes、5 维指标值、实际字数、候选数、耗时、重试次数、是否触发定向修复。
4. **判定标准**：
   - **通过率不得低于改动前**（若 3 章里有 2 章以上拒稿 → 阈值过严，回退到更宽松的值，**不要靠加豁免来救**，那是 D-14 的老路）。
   - 5 维指标要能区分——如果三章的指标值几乎一样，说明门还是没有鉴别力。
   - 若触发定向修复，检查 T-22 的 `repair_outcome` 是否记录正确。
5. **证据留存**：命令、指标表、blocker 列表存到 `docs/quality-runs/{date}.md`。**只存指标不存正文**（2.6 脱敏约束）。
6. 有 E-08 之后，这一步用 `python -m scripts.quality_bench --smoke` 代替手工操作。

**批 7 的专属验证点（做这次验证时一定要看的三件事，其余批次没有）**：

- **字数配置真的到位了吗**：在 3 章的 `quality_metric_snapshot` 里核对 `target_word_count` / `min_word_count` **等于任务书里配的值**，不是 3000/2000。这是 D-20 的直接回归检查——单测只能证明"传了就用"，证明不了生产链路上取的是 `active_config`。
- **短章 1500 的 `below_min` 会不会误杀**：`min` 生产上恒为 `target * 0.9` = 1350。真实语料里 22% 的历史正文低于 min（比值 p50 仅 0.608），所以**短章是最可能触发 −620 的档位**。若短章因字数被拒，先看实际字数——如果确实低于 1350，那是生成端的问题不是门的问题，**不要调松阈值**。
- **长章 6000 的 `far_above` 上限是 9600**（`target > 2500` 走 1.6 系数）。顺便实测一下 `target=2500`（上限 5000）与 `target=2600`（上限 4160）这个已知不单调点在真实生成里会不会咬人——如果咬了，那才是修单调性的时机，届时按 §11.2.1 灌语料重定系数。

**如果没有可用的 LLM 额度或环境**：这一步**可以推迟但不能跳过**——把「待真实验证」明确写进提交信息和本文档的进度表，不要让下一个人以为验证过了。前序会话已经出现过 `403 pre-consume quota failed`，额度不足是真实可能的。

---

## 9. 已完成的工作（**不要重做**）

这一节的目的是防止接手人重复劳动。以下都是已经落地并有测试覆盖的能力，**改动它们之前先读现有实现**。

### 9.1 后端质量门主体（已建成，问题在准确率不在有无）

- **5 维评分**：场景达成度（`scene_fulfillment_rate` / `fulfilled_scene_count`）、对话改变状态（`dialogue_changes_state`）、章末压力（`ending_pressure_passed`）、静态描写风险（`static_description_risk`）、事件密度（`event_density_passed` 及 5 个子指标）。
- **11 类 blocker + 6 条软放行**：软放行是 `progression_soft_pass` / `scene_soft_pass` / `semantic_scene_soft_pass` / `dense_scene_soft_pass` / `density_soft_pass` / `rich_progression_evidence`。软放行机制本身是合理设计（避免单一硬阈值误杀），问题在于它消费的是不可靠的指标（见 D-07/D-16）。
- **质量指标快照**：`quality_metric_snapshot` 落进章节 `metadata["quality_metrics"]`（`pipeline_orchestrator.py:2001`）、`metadata["quality_gate"]`（1994）、SSE 事件、`runtime_metadata["quality_gates"]`（**批 5 后 2409 起**）。
- **测试**：原始 56 个测试在 `test_generation_quality_guards.py`（当时 2151 行，现 4438 行），**当时绝大多数是「好样本应通过」方向**，缺坏样本方向。**批 4（T-07）已补上 `TestBadSampleRegression` 9 条双向测试；批 8 后全文件 4438 行 / 188 收集（167 passed, 21 failed），各 class 行号见附录 A.2。**

### 9.2 前端质量展示（**已全部就绪，本轮实测确认文件都在**）

| 文件 | 职责 |
|---|---|
| `frontend/src/utils/chapterQuality.ts`（109 行） | 指标解析与文案生成（`resolveChapterQualityMetrics` / `buildChapterQualitySummary`） |
| `frontend/src/utils/chapterQuality.spec.ts`（92 行） | 上述逻辑的回归测试 |
| `components/writing-desk/layout/WDSidebar.vue` + spec | 侧栏质量摘要 |
| `components/writing-desk/layout/WDWorkspace.vue` + spec | 章节头部质量条、失败态诊断 |
| `components/writing-desk/workspace/review/VersionSelector.vue` + spec | 候选卡片上的质量标签 |
| `components/writing-desk/dialogs/WDVersionDetailModal.vue` + spec | 版本详情弹窗里的完整指标 |

- **指标读取的优先级链**（`chapterQuality.ts:38-61`，改后端字段位置时必须对齐）：
  `runtime.quality_metrics` → 选中版本 `metadata.quality_metrics` → `metadata.review_summaries.final_quality_metrics` → `metadata.story_progression_guard.quality_metric_snapshot` → 最后一个版本同上。
- **文案策略**：后端下发的 `quality_issue_labels` 是**成文中文文案，前端不二次翻译**（76 行注释明确写了）；只有本地兜底文案走 `pick()` 双语。**所以新增 blocker 时，后端必须同时给出中文 label**，否则前端只能显示 code。
- **唯一缺口**：本地兜底漏了 `event_density_passed`（见 D-22，随 T-14 一起补）。

### 9.3 前序会话已完成的两项任务（Task #4 / Task #5）

- **Task #4：结构质量门的定向修复闭环**（`_attempt_structural_gate_repair`，**批 5 后 2054-2241**）。原有 D-21 的三个限制（只试一次、要求全清零、受 `enable_self_critique` 开关控制）**已在批 5（T-22）全部解除**：改为最多 2 轮、按严格子集收缩采纳部分改善、跳过与失败都返回诊断。第 4 条（自评关闭时走确定性清理）仍待 T-17，批 10 接线。
- **Task #5：首稿重试带结构诊断做定向重试**（`_evaluate_first_draft_retry`）。已建成；**D-13 第 4 层的漏传字数参数已于批 7 修好**（它签名收了字数、自己做了规范化、调用评分器时就是不传），现在字数标志与 `reason_codes` 同源，不会再自相矛盾。

### 9.4 提示词侧的写作契约（**质量已高，不要重写**）

- `_resolve_chapter_draft_contract`(1201) / `_format_chapter_draft_contract_for_prompt`(1254) / `_build_prompt_sections`(5593) / 场景执行清单(5504-5524) / `_build_prose_only_system_prompt`(6761) / `_resolve_style_hints`(5702)。
- 实际指令内容见 E-01 的摘录。**它与质量门的 5 个维度基本对齐**（场景/对话/钩子/描写/密度都有明确要求），说明提示词侧已经在要求正确的东西。
- **这条推导很重要**：生成质量差**不是因为没告诉 LLM 要什么**，而是因为质量门没能真正挡住不合格的（D-16），所以 LLM 没有被迫改进。**优化重点应放在判定准确率（T 系列），而不是继续加提示词。**

### 9.5 enrichment（扩写）提示词约束

- 已被约束为「动作、对话、后果、简短的 sequel 决策」，**明确禁止空洞描写填充**。这条已落地，不要再改成通用扩写。

### 9.6 连续性门（`longform_context_service.evaluate_continuity_quality`，709-840）

**这是全仓库设计最完善的质量检查，结构质量门应该向它学习（见 E-11）**：

| code | 级别 | 说明 |
|---|---|---|
| `longform_context_missing` | warning | 上下文包缺失时**放行**而非失败 |
| `longform_context_chapter_mismatch` | blocker | 包与当前章号不符 |
| `chapter_focus_missing` | warning | 焦点人物缺席（源 `cast_plan.chapter_focus_names`，过滤 `startswith("角色")`） |
| `dead_character_active_without_explanation` | blocker | 已死人物仍在行动（`dead_action_words = ("说","问","笑","走","抬","看","冲","握","坐")`） |
| `due_foreshadowing_payoff_weak` | warning | 附 `strengthen_payoff_patch` |
| `due_foreshadowing_not_visible` | **动态升档** | `distance >= 12` 或 `importance in {major,long,5}` → blocker，否则 warning，附 `local_payoff_patch` |
| `long_gap_foreshadowing_memory_risk` | warning | `distance >= 8` |
| 因果链承接（835+） | — | 检查 `causal_chains` 里 status 非 `resolved`/`abandoned` 的链条 |

- `payoff_signal_words = ("揭开","真相","原来","证据","兑现","回收","解释","指向","导致","因此","代价","暴露","确认","证实")`。
- **三个可复用的设计**：blocker/warning 分级、同 code 按严重度动态升档、每条问题带 `patch_suggestions`。

---

## 10. 明确不做（**每条都有理由，不要好心重开**）

| 不做什么 | 理由 |
|---|---|
| **不再开 Workflow 编排、不开大批并发子智能体** | 前序会话的 97 节点审计消耗 **3,879,503 subagent tokens / 12,876 秒，产出为零**，并触发多个 `403 pre-consume quota failed`。用户明确表达过不满（「你TMD并发开的太多了，电脑都卡了」「审了7个小时」）。**本任务全程单线程手工执行。** |
| **不重跑 `wf_67ec591a-c92`** | 就是上面那个零产出的审计运行。 |
| **不做 EXTRACTABLE 模块提取** | 3 个模块提取（`_pipeline_quality_gate` / `_pipeline_story_scoring` / `_pipeline_self_critique`）是纯重构，与质量目标无关，且会让所有行号引用失效、review 困难。T-20 只删注释里的行号，**不做提取**。 |
| **不新建 `test_story_quality_scoring.py`** | 给孤儿模块写测试等于给它续命，与 T-19（删除孤儿）冲突。所有测试进 `test_generation_quality_guards.py`。 |
| **不做近似重复检测**（编辑距离 / 向量相似度） | T-10 的精确重复检测已能抓住绝大多数灌水，近似重复的误判风险（正常的复沓修辞）与实现成本都高得多。留 P3。 |
| **不删除 D-14 的两条自评豁免** | 它们是为压误杀而加的。在 T-02/T-03/T-15/T-04/T-05/T-06 完成并有 E-09 的触发率数据之前，删掉会造成大面积拒稿。见 T-18 的三步顺序。 |
| **不降低事件密度的 800 字短路阈值** | 800 字以下切出的句子太少，`rate` 类指标方差极大，降阈值只会引入噪声。见 T-14。 |
| **不把 `_score_fallback_candidate` 修好** | 它是零调用点的死代码（D-19），修它等于给死代码续命。直接删（T-01）。 |
| **不改历史提交信息里的测试数** | 会重写 git 历史，违反 2.2。只约定往后（T-21）。 |
| **不覆盖数据库里现有的提示词** | 现网 DB 里的 `writing_v2` 可能是用户手工调优过的。E-01.1 的 seed 必须是「不存在则插入、存在则不覆盖」。 |
| **不重写 9.4 的写作契约** | 它已与质量门 5 维对齐，质量高。见 9.4 的推导：问题在判定端不在提示端。 |
| **不做 `reversal`（反转）的 blocker** | 反转的表达方式太多，字符串检测召回率注定不高，做成 blocker 必然大量误杀。E-02 永久停留在 warning。 |
| **不新建数据库表来存质量指标** | 指标已在 metadata JSON 里，E-09 在应用层聚合即可。新建表要 Alembic 迁移，违反 2.2「禁止不可逆迁移」。 |
| **不在没有 E-08 的情况下改提示词正文** | 提示词改动会同时影响所有维度且无单测能捕获退化，没有批量评测就是盲改。见 E-01.2。 |

---

## 11. 临时文件与清理

### 11.1 本轮产生的临时探针（**任务结束前必须删除**）

| 文件 | 用途 | 保留价值 |
|---|---|---|
| `backend/_probe_quality.py` | 对比生产版与孤儿版评分器在 4 个样本上的输出 | 样本已搬进 T-07 测试，**已删** |
| `backend/_probe_bypass.py` | 验证章末压力门的两个逃逸（纯标点通过、`"一切都"` 误杀） | 5 个 CASES 已搬进 T-02/T-03 测试，**已删** |
| `backend/_cmp_scoring.py` | 用 `inspect.getsource` + SHA256 检测两份实现的漂移 | T-19 删孤儿后彻底无用，**已删** |
| `backend/_probe_out.json` | 探针输出 | **已删** |
| `backend/_probe_hookwords.py`（批 2） | 逐个跑钩子词表，定位 `"一切都"` 这类过宽词条 | 结论已进 D-04 与批 2 测试，已删 |
| `backend/_probe_density.py`（批 3 轮 1） | 观察 `_story_units` 切分粒度与 `progression_unit_rate` 的真实量级 | 结论已进 T-04 落地记录，已删 |
| `backend/_reverse_verify_batch3.py`（批 3 轮 1） | 运行时 `setattr` 改坏词表/窗口逻辑，确认新测试必红 | 结论已进批 3 落地记录，已删 |
| `backend/_probe_real_corpus.py`（批 3 轮 2） | **灌 147 条真实历史章节**测阈值分布与误杀率 | **方法必须传下去**（见下方「要不要重建」），数据已进第 7 节分位表，脚本已删 |
| `backend/_probe_threshold_grid.py`（批 3 轮 2） | 阈值网格 + 窗口 `ratio×hits` 敏感度扫描 | 选定组合已写入源码与文档，已删 |
| `backend/_reverse_verify_batch3b.py`（批 3 轮 2） | 9 项改坏（阈值量级、键名、比例上限、新字段、白名单），8 项必红 | 结论已进批 3 落地记录，已删 |
| `backend/_probe_badsamples.py`（批 4） | 打印 5 个坏样本 + 正向对照 + 2 个短尾巴对照的 codes / 12 个指标 / 与对照的分差；开头打印填充长度提醒 260 尾窗约束 | **发现了 D-24 尾窗遮蔽**；断言值已按实测写进 T-07 测试，已删 |
| `backend/_reverse_verify_batch4.py`（批 4） | 运行时 `setattr` 改坏 6 处生产条件共 11 项，逐条确认新测试必红 | 11/11 必红 + 1 条覆盖缺口（D-25）已进批 4 落地记录，已删 |
| `backend/_probe_b7_cfg.py` / `_probe_b7_keys.py`（批 7-A） | 摸清真实字数配置存在哪个 metadata 路径（`chapter_mission.chapter_draft_contract`，不是 `guardrail`） | 路径已写进 §11.2.1 批 7 表的取样说明，已删 |
| `backend/_probe_b7_corpus.py` / `_probe_b7_corpus2.py`（批 7-A） | 灌 99 条带字数契约的真实正文，测三判罚触发率与 `upper` 系数敏感性 | **数据已进 §11.2.1「批 7 表」**，脚本已删 |
| `backend/_probe_b7_score.py` / `_probe_b7_t11.py`（批 7-B） | 实测 T-11 判罚分差与四来源采集结果 | 断言值已进 `TestFocusCharacterAbsence`，已删 |
| `backend/_probe_b7c_tests.py`（批 7-C） | 写测试前先实测每条断言的真实数值（620/520/180、floor/upper、三态、排序分差 23→643） | 全部照抄进 `TestWordCountPenalties`，已删 |
| `backend/_probe_b7_verify.py`（批 7-C） | T-12 接通后在真实语料上复核触发率，并断言 snapshot 与顶层字段同源 | 结论已进批 7 落地记录，已删 |
| `backend/_probe_b7c_reverse.py`（批 7-C） | 改源码文本 14 处，逐条确认必红；**首轮 6 项假绿全是探针自己的 bug** | 14/14 必红 + 假绿三类成因已进批 7 落地记录，已删 |

**清理命令**（批 1-4 的探针**已全部清完**，命令留档备查，重建同名脚本后可直接复用）：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && rm -f _probe_quality.py _cmp_scoring.py _probe_out.json _probe_badsamples.py _reverse_verify_batch4.py
```

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && rm -f _probe_bypass.py _probe_hookwords.py _probe_density.py _reverse_verify_batch3.py _probe_real_corpus.py _probe_threshold_grid.py _reverse_verify_batch3b.py
```

```bash
rm -f _probe_b7_cfg.py _probe_b7_keys.py _probe_b7_corpus.py _probe_b7_corpus2.py _probe_b7_score.py _probe_b7_t11.py _probe_b7c_tests.py _probe_b7_verify.py _probe_b7c_reverse.py
```

**批 8 的探针（2026-08-19 实测仍在盘上，⏳ 待删）**：

| 文件 | 用途 | 处置 |
|---|---|---|
| `_probe_b8_corpus.py` / `_probe_b8_keys.py` / `_probe_b8_order.py` / `_probe_b8_x.py`（批 8-A） | 真实语料量化 T-13/T-14 影响面、摸 metadata 键路径与判定顺序 | 数据已进批 8 落地记录，⏳ 待删 |
| `_probe_b8e_calib.py`（批 8-E） | 定标：三态在真实评分器上的分差（`True-None=140` / `None-False=140`；密度旧写法倒扣 490） | 数值已进批 8 落地记录，⏳ 待删 |
| `_probe_b8e_tests.py`（批 8-E） | **24 个文本变异反向验证**，含 sha256 还原校验与行尾编码对齐 | 24/24 必红已进落地记录，⏳ 待删 |

**批 8 事故遗留的恢复工具（⏳ 待删，但方法必须留在文档里）**：`_recover_scan.py`（扫 transcript 提取编辑记录，**`rglob` 必须含 `subagents/`**）、`_recover_replay.py`（按时间戳重放）、`_recover_show.py`、`_recover_edits.json`（97 条编辑记录）、`_rec_*_old.txt` / `_rec_*_new.txt`（14 个逐条比对样本）。

**其它遗留物（⏳ 待删）**：`_head_po.py.tmp` / `_head_test.py.tmp` / `_po_head_backup.py.tmp`、`app/services/task_runtime.py.orig`、`app/api/routers/.research.patch`、`storage/.real-asgi-*.db.migration.lock`（**51 个**，测试跑出来的迁移锁残留）。

**批 8 清理命令**：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && rm -f _probe_b8_corpus.py _probe_b8_keys.py _probe_b8_order.py _probe_b8_x.py _probe_b8e_calib.py _probe_b8e_tests.py _recover_scan.py _recover_replay.py _recover_show.py _recover_edits.json _rec_*_old.txt _rec_*_new.txt _head_po.py.tmp _head_test.py.tmp _po_head_backup.py.tmp app/services/task_runtime.py.orig app/api/routers/.research.patch
```

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && rm -f storage/.real-asgi-*.db.migration.lock
```

> **进度**（2026-08-19，批 8 完成后）：批 1-7 的探针**已全部清完**；**批 8 的 6 个探针 + 4 个恢复脚本 + 14 个比对样本 + 3 个 `.tmp` + 51 个迁移锁尚在盘上**（命令见上）。批 2/3/4/6/7/8 的样本与断言值都已固化进 `test_generation_quality_guards.py`（188 条收集，167 passed）；阈值校准结论、反向验证结果、D-24/D-25 的关闭记录已分别写进第 7 节各批落地记录、§11.2.1 批 6/批 7 分位表与第 5 节缺陷清单。
>
> **批 6 探针的一个做法差异（值得抄）**：前几批的反向验证用运行时 `setattr` 改坏类属性，批 6 改成**直接改源码文本再跑 pytest**，跑完写回原文并 `diff` 校验。原因是本批有 5 处改坏点在函数体内部（`or` 分支、判罚表达式、blocker 分支、调用点传参），`setattr` 碰不到；而"改文本"顺带能验证锚点是否还在——第一轮就有 3 条因锚点缩进不对而报「锚点失配」，那本身就是有效信号（说明我记的代码形态和实际不符）。**代价是必须保证异常路径也写回原文**（用 `try/finally` + 末尾 diff 校验）。

>
> **真实语料校准探针要不要重建**：T-16（批 9）改评分权重时**必须重建一次**。可复用的做法（约 60 行，写完即删）：连 `backend/storage/xuanqiong_wenshu.db`，`select content, metadata from chapter_versions`，过滤 ≥800 汉字 + 按 content 去重 + 20 字 shingle 去重率 ≥0.90，用 `metadata.review_summaries.story_progression_guard.*` 做历史标签，逐条调目标 classmethod，**只打印分位数/通过率/误杀条数，绝不打印正文**（2.6 脱敏约束）。注意这批语料被 `.gitignore` 忽略、不在 git 里，**换机即失**——所以结论必须写进文档，不能只留在脚本里。

> **删除前确认**：`git status` 里这几个文件应该是 untracked（`??`）。如果显示为已跟踪，说明被误提交过，此时先确认没有其它人依赖再删。

### 11.2 探针方法本身要留下来（写进本文档而不是留脚本）

本轮所有可靠结论都来自**执行观察（execute-to-observe）而非阅读推断**。这个方法要传下去：

```python
# 最小可用探针模板：不起服务、不连 DB，直接调 classmethod
from app.services.pipeline_orchestrator import PipelineOrchestrator as P
r = P._score_story_quality_candidate(content=SAMPLE, violations=[], chapter_mission=None,
                                     target_word_count=3000, min_word_count=2000)
print({k: r.get(k) for k in ("score", "word_count", "progression_unit_count",
                             "progression_unit_rate", "event_density_per_1000",
                             "event_density_passed", "quality_issue_codes")})
```

**为什么必须执行而不能只读源码**：本轮有 3 个结论只有执行才能得到——① `_score_fallback_candidate` 抛 `NameError`（读源码看不出，因为参数名看起来是对的）；② `progression_unit_rate` 方向相反（读源码只能看出「引号算推进」，看不出量级差 125 倍）；③ `"一切都"` 误杀真钩子（读词表不会觉得有问题）。其中 ① 已在批 1 修复、③ 已在批 2 修复（D-04）、② 已在批 3 修复（T-04/T-05/T-06，见第 7 节落地记录）。

#### 11.2.1 第二层探针：灌真实历史正文做阈值校准（批 3 新增的方法，**改阈值必用**）

上面的模板只解决「代码行为是什么」，解决不了「阈值定在哪」。批 3 用合成样本定出的第一版阈值**定向 101 passed、全量 676 passed 全绿，却在真实语料上误杀 96%**——单元测试的样本是自己写的，写样本的人和定阈值的人是同一个，必然自我一致。

```python
# 第二层探针模板：灌真实历史正文，只输出统计量
import json, sqlite3
from app.services.pipeline_orchestrator import PipelineOrchestrator as P

rows = sqlite3.connect("storage/xuanqiong_wenshu.db").execute(
    "select content, metadata from chapter_versions").fetchall()

seen, samples = set(), []
for content, meta in rows:
    if not content or len("".join(content.split())) < 800 or content in seen:
        continue
    seen.add(content)
    # 20 字 shingle 去重率 <0.90 的是退化循环文本，必须剔除，否则拉低整池密度
    sh = {content[i:i + 20] for i in range(0, max(1, len(content) - 19))}
    if len(sh) / max(1, len(content) - 19) < 0.90:
        continue
    label = (json.loads(meta or "{}").get("review_summaries", {})
             .get("story_progression_guard", {}).get("event_density_passed"))
    samples.append((content, label))          # label = 历史判定，用来算误杀

vals = sorted(P._evaluate_event_density(c, word_count=len("".join(c.split())))
              ["progression_unit_rate"] for c, lb in samples if lb is True)
pct = lambda q: vals[min(len(vals) - 1, int(len(vals) * q))]
print(f"n={len(vals)} p05={pct(.05)} p50={pct(.50)} p95={pct(.95)}")   # 只打印数字
```

**四条硬规矩**：

1. **只打印统计量，绝不打印正文片段**——这是用户小说正文，落进日志就违反 2.6 脱敏约束。
2. **必须剔退化文本**：`chapter_versions` 里混着重试产生的循环复读正文，20 字 shingle 去重率能一刀切掉，不剔就会把整池密度拉低、导致阈值定得过松。
3. **必须分「历史 True 池」与「历史 False 池」分别看**：前者算误杀率（这是主要风险），后者算漏判率——但后者往往只有个位数条且指标定义已变，**不可比，要在结论里明说 n 太小**。
4. **阈值取真实分布的低分位（p03-p08）**，不取中位数。这类门是**底线门**，只拦灾难样本；质量优选归评分与 prompt。宁可漏判不要误杀。

**语料不在 git 里**（`storage/*.db` 被 `.gitignore` 忽略），换机即失。所以**分位表必须抄进本文档**（第 7 节批 3 落地记录已抄了 6 指标 × 7 分位），脚本本身写完即删。

**批 6 复用同一套取样逻辑跑出来的数字（2026-08-19，n=136）**，静态描写与重复检测两组指标都在这里，改这两道门前先看它：

| 指标 | p03 | p05 | p10 | p25 | p50 | p75 | p95 | max | 何时用 |
|---|---|---|---|---|---|---|---|---|---|
| `word_count` | — | — | — | — | 2827 | — | — | — | 四条 or 的字数门槛都以它为基准 |
| `max_static_run`（T-09 收紧后） | 0 | 0 | 0 | 0 | **1** | 1 | 1 | **2** | 第 2 条门槛定 3 的依据：真实文本到不了 3 |
| `static_paragraph_count`（T-09 收紧后） | 0 | 0 | 0 | 0 | **1** | 2 | **4** | 8 | 第 4 条的 `>= 3` 落在 p75~p95 之间 |
| `repeated_paragraph_instances` | 0 | 0 | 0 | 0 | 0 | 0 | **0** | **1** | 重复检测触发率 0.000 的直接证据 |
| 末段字数（按换行切） | — | — | — | — | **24** | 73 | **151** | 275 | `ENDING_CORE_FLAT_CHARS = 150` 取在 p95 |
| 末两段字数 | — | — | — | — | 67 | — | 300 | — | 说明 260 字定长尾窗覆盖的是"末两段"，不是"末段" |

**T-09 收紧前的对照**：`max_static_run` 与 `static_paragraph_count` 在真实语料上**全是 0**（因为高频单字让每段都算"有动作"）。这两行数字从全 0 变成有分布，是 T-09 生效的唯一客观证据——**光看测试变绿看不出这件事**。

**批 7 表：字数三判罚的真实触发率（2026-08-19，n=99）**

批 7 的取样比前几批多一道过滤：字数判罚需要**每条样本自己的字数配置**，取自
`metadata.chapter_mission.chapter_draft_contract.{target_word_count,min_word_count}`。
136 条里只有 99 条带这个契约，其余是契约字段引入之前的历史数据。**取样口径变了就要重报 n**，
不能拿 136 的分位表套 99 的触发率。

| 判罚 | 全样本触发 | 历史通过池触发率（n=82） | 判罚值 | 结论 |
|---|---|---|---|---|
| `word_count_below_min` | 23 / 99 | **0.220** | −620 | 触发率高但**这是真实不足**，不是误杀，见下 |
| `word_count_far_below_target`（不含 below_min） | 3 / 99 | **0.024** | −180 | 窄带，符合"够最低但偏薄"的设计意图 |
| `word_count_far_above_target` | 1 / 99 | **0.012** | −520 | 2.0/1.6 系数下几乎不触发 |

**0.220 为什么不是误杀**：这 23 条的「实际字数 / 目标字数」比值分位是
p0=0.304、p25=0.474、**p50=0.608**、p75=0.833、max=0.872——**没有一条超过 0.9**，
也就是全部真的没写够（生产里 `min` 恒为 `target * 0.9`）。样例：目标 4000 写了 1890、
目标 1200 写了 802。这不是阈值定松定紧的问题，是历史生成本身字数不达标，
**正是 T-12 要暴露的东西**。所以这一项**不按"低分位"原则调松**——底线门宁可漏判的原则
适用于"指标定义模糊"的门（静态描写、事件密度），不适用于"用户明确配了 min 却没达到"。

**`upper_target` 系数敏感性（同一池 n=82，只改系数）**：

| 系数 | `far_above` 触发率 | 取舍 |
|---|---|---|
| **2.0 / 1.6**（孤儿版，采纳） | **0.012** | 只拦真正写散的极端样本 |
| 1.6 / 1.4 | 0.134 | 已开始打到正常长章 |
| 1.25 / 1.25（死代码 `_score_fallback_candidate`） | **0.305** | **三成正常章节被判超长**，25 倍误杀差距 |

**目标字数的真实档位分布**（说明为什么硬编码 3000/2000 是灾难）：
`5000×26, 2500×21, 3000×9, 1600×5, 1200×5, 2000×5, 2400×4, 1400×4, 4000×4, 3500×4, 1800×3, 3200×2, 1500×2, 800×2, 1000×2, 10000×1`
——**16 个不同档位，跨度 800 到 10000**，其中只有 9 条恰好是 3000。第 3 层删默认值改必填的依据就是这行数字。

**触发率栅格（T-08 四条 or 的候选阈值组合）**：

| 方案 | 真实语料触发率 | 取舍 |
|---|---|---|
| 生产原状（3 条，高阈值） | 0.000 | 等于这道门不存在 |
| 孤儿版原样（4 条，第 2 条 `>= 2`） | 0.044 | 可接受，但比下一档更容易误杀"零星长段" |
| **孤儿版 + 第 2 条保持 `>= 3`** | **0.029** | **采纳** |
| 再把第 4 条 `static_paragraph_count` 抬到 4 | 0.022 | 过紧，第 4 条几乎抓不到混合体 |
| 抬到 5 | 0.015 | 同上，更紧 |

**D-24 变体对比（历史 `ending_pressure_passed: true` 池，n=101，基线通过率 0.812）**：

| 变体 | 做法 | 通过率 | 结论 |
|---|---|---|---|
| 基线 | 尾窗 260 字符 | **0.812** | 参照 |
| A / B | 把语义窗口缩到 60~200 字符或末 1~2 段 | 0.475~0.782 | **全部更差**，是误杀不是召回 |
| G，w_min=1 | 末段否决，弱信号 >= 1 | 0.762 | 代价过大 |
| **G，w_min=2** | 末段否决，弱信号 >= 2 | **0.802** | **采纳**，净代价 1 个样本 |
| G，w_min=3 | 末段否决，弱信号 >= 3 | 0.812 | 零代价但**放过坏样本**，等于没修 |
| G + `long_n` 120/150/200 | 追加"末段 >= n 字且零语义"否决 | 0.802 | 三个取值都零额外代价，取 150 |

**归因（解释为什么末段否决是对的落点）**：True 池里 **79.2%** 的语义钩子就在末段之内、**12.9%** 压根没有语义钩子（靠 `deliver_to_next` 或任务钩子过门）、只有 **7.9%** 的钩子只落在末段之外。也就是说"末段自己带钩子"是真实的常态，把没钩子的末段判泄气不会牵连大多数正常文本；而 False 池（n=13）在修改前后都是 0/13 通过，没有引入新的漏判。

### 11.3 关于 317 处未提交改动

- **全部保留，不做任何清理**（2.2 硬约束）。
- 禁止 `git reset --hard`、`git checkout -- <file>`、`git stash`、`git clean -f/-fd`、`git push --force`。
- 分批提交时**只 `git add` 本批涉及的文件**，不要 `git add .`（会把 317 处无关改动混进来）。
- 本文档自身（`TASK_HANDOFF_NOVEL_QUALITY.md`）也是未提交文件之一，建议**在批 1 时单独提交一次**，避免它在后续批次里被反复卷入 diff。

---

## 12. 下一步立即动作（接手后的前 30 分钟）

**不要先读代码，先跑这四条命令确认环境与基线**：

```bash
cd /d/小说写作/xuanqiong-wenshu && git status --short | head -20 ; git branch --show-current
```

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && python -m pytest app -p no:randomly -p no:anyio -p no:seleniumbase -p no:sb_manager -q --timeout=120 --timeout-method=thread -rf 2>&1 | tail -45
```

> **⚠️ 四个 `-p no:` 一个都不能少。** 曾经写在这里的裸 `pytest app -q` 会触发 D-26 的假绿：
> 进程猝死、输出丢失、退出码 0，看起来像"全绿跑完"。本文档历史上所有"全量全绿"结论都是
> 这么来的。各开关的必要性见 §2.3 的表。

期望看到 **`727 passed, 36 failed`**（2026-08-19 实测，唯一可信基线）。**看到失败不要慌**——
那 36 个是先存欠账（D-27），不是有人改坏了。拿 `-rf` 的清单和 D-27 的表逐条对：**条目一致
就是正常起点；多出任何一条才是回归。** 如果你看到的是"742 passed 全绿"，说明你用的是裸命令
（假绿），回上面重跑。

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && grep -rn "plain_run_limit\|_score_fallback_candidate" app | grep -v "def _score_fallback_candidate"
```

期望：**零命中**（批 1 删掉了死代码 `_score_fallback_candidate` 的生产版调用、批 3 把绝对连段阈值 `plain_run_limit` 整个换成了比例 `plain_run_ratio_limit`）。如果 `plain_run_limit` 又出现，说明有人把绝对句数阈值改回去了 → 先看第 7 节批 3 落地记录再动。

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -q -k "BadSampleRegression" 2>&1 | tail -5
```

期望：**9 passed**（2026-08-19 实测 3.82s）。批 4 之后，「确认前面各批成果仍在」不再需要临时探针（`_probe_quality.py` 已删）——`class TestBadSampleRegression` 就是常驻版本：5 个坏样本必须被拦、`GOOD_DRAMATIC` 必须零 blocker、分差必须够大。**这 9 条里任何一条红，都不要改断言，先回第 7 节批 3/批 4 落地记录查是哪个门被改松或改紧了。** 需要看具体指标数值时用 11.2 的模板临时重建探针；改阈值前还要按 11.2.1 灌真实语料。

**批 6 之后，快速护栏扩到 4 个类**（静态描写 / 整段重复 / 章末核心段都进了常驻测试）：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -q -k "BadSampleRegression or StaticActionMarkerTable or StaticDescriptionRiskBranches or RepeatedParagraphFlood or EndingCoreWindow" 2>&1 | tail -3
```

期望：**36 passed**（2026-08-19 实测 3.39s；9 + 5 + 8 + 7 + 7）。改质量门先跑这一条，全绿再跑全量。`TestStaticDescriptionRiskBranches` 里的 `STATIC_RUN_AT_LIMIT` 是**阈值哨兵**——它断言四条或式全部为 False，是唯一能在「有人把第 2 条从 `>= 3` 放松到 `>= 2`」时变红的测试（D-25 的教训：只断言「该命中的命中了」，阈值放松是全绿的）。

**然后按这个顺序动手**：

1. **批 1（T-01 / T-20 / T-21）** —— ✅ 已完成（实测 661 passed）。零风险清障，先拿到「改动 + 测试 + 全量通过」的完整节奏。**同时把本文档单独提交一次。**
2. **批 2（T-02 / T-03 / T-15）** —— ✅ 已完成（实测 **668 passed in 97.11s**）。章末压力门：语义命中成必要条件、`一切都` 误杀已解、42 个转义词还原并剔 10 个专有词、加 grep 护栏。原样本探针 `_probe_bypass.py` / `_probe_hookwords.py` 的样本已固化进测试并删除探针。
3. **批 3（T-04 / T-05 / T-06）** —— ✅ 已完成（实测 **679 passed in 94.61s**）。事件密度门三项全修 + **用 147 条真实历史章节重定全部阈值**（第一版靠合成样本定的阈值误杀 96%）。**8.4 的真实生成端到端验证仍 ⏳ 待做**（无 LLM 额度，`403 pre-consume quota failed`），恢复额度后必须补。
4. **批 4（T-07）** —— ✅ 已完成（实测 **688 passed in 118.20s**）。`class TestBadSampleRegression` 9 条测试固化 5 种失败形态 + 1 个防误杀锚点，锁死批 2/批 3 的成果；顺带修 `flat_closure_markers` 观测性漏项；新发现 D-24（尾窗遮蔽）与 D-25（静态连段无覆盖），都排进批 6。
5. **批 5（T-22）** —— ✅ 已完成（实测 **691 passed in 61.34s**）。修复闭环三项全落地：严格子集收缩判据 `_is_structural_repair_improvement`、`STRUCTURAL_GATE_REPAIR_MAX_ROUNDS = 2`、失败与跳过都返回 `repair_summary` 诊断。**返回值语义变了：`_attempt_structural_gate_repair` 不再返回 `None`，采纳与否看 `adopted`**——加 blocker 的闸门已就位，批 6 可以放心提高触发率。
6. **批 6（T-08 / T-09 / T-10 + D-24 / D-25）** —— ✅ 已完成（实测 **718 passed in 55.80s**）。T-09 重建动作词表（**根因是高频单字**而不只是自然现象动词）、T-08 补第 4 条判定（第 2 条门槛按真实语料保持 `>= 3`）、T-10 照搬重复检测并做第 12 类硬 blocker、D-24 改成「保留 260 尾窗 + 末段否决」（缩窗的 6 个变体全部更差）、D-25 改成四条 or 各配互斥样本。新增 27 条测试分 4 个类，反向验证 16/16 必红。**D-24 与 D-25 两条缺陷至此关闭。**

7. **批 7（T-11 / T-12）** —— ✅ 已完成（实测 **742 passed**）。焦点人物缺席进候选评分（判罚 −240，不加 blocker）；字数四层断链全修（三判罚 620/520/180、`upper` 系数 2.0/1.6、第 3 层必填 / 第 4 层默认 0 故意不对称）。真实语料 n=99 校准表见 §11.2.1「批 7 表」。反向验证 14/14 必红，**其中 6 项首轮假绿全是探针 bug**（选择器 deselect、改坏点不在判定路径、只替换了 2 处中的 1 处），方法论已写进批 7 落地记录。
8. **批 8（T-13 / T-14 + D-22）** —— ✅ 已完成（`test_generation_quality_guards.py` 实测 **167 passed, 21 failed**，21 个失败全是 D-27 先存欠账）。三态改造 + 短路返回 `None` + 前端兜底文案，反向验证 24/24 必红。定标分差：`True-None = 140`、`None-False = 140`（三态语义正确）；旧两分支写法把密度 `None` 当失败合计倒扣 **490**。**T-13 留一个缺口未闭环**（标记词表认不出三类语义，见 D-27 B 组第 5 行 → T-26）。本批还发生了一次 `git checkout` 覆盖未提交代码的事故，恢复方法与教训见第 7 节「批 8 实际落地记录」。

9. **T-23（D-26）—— 下一步必须先做这个，优先级高于批 9**。修 runner 假绿：`asyncio_mode = auto` 与 `anyio` 插件冲突，导致本文档此前**所有**"全量全绿"结论作废。**在这一条修好之前，任何优化任务的验收都不成立**——你无法知道改动有没有破坏别处。三条修法见 D-26，倾向"统一异步栈"（根治，让裸 `pytest` 也可信）。
10. **T-24（D-27 A 组）**。实现 9 个从未落地的方法。契约已由 28 条现存测试钉死（精确返回值、长度上限、头部窗口边界都有），照着写不用猜；`_resolve_writer_prompt_budget` 是既有三件套的缺失成员（另两个在 `pipeline_orchestrator.py:1331` / `:1561`，已被 8 处调用）。
11. **T-25 / T-26（D-27 B 组）**。8 个真实行为分歧，**先定性"哪边对"再改**：4 项阈值约定不一致、3 项原因码进出不符、1 项词表覆盖不足。其中 T-26（`_count_dialogue_state_change_markers` 扩词）**必须走 §11.2.1 的真实语料校准**——它与 D-06 章末压力词表过拟合是同类问题，凭直觉加词会重演批 3「合成样本定阈值、真实语料误杀 96%」的错误。
12. 之后才按 6.3 的批 9-10 顺序执行（T-16 权重重配 / T-17-T-19 清理收尾）。
9. **E-08（离线评测脚本）建议尽早插入**（原计划排在批 3 与批 4 之间，已错过窗口，**批 6 已完成，现在就是补它的窗口**），这样批 9（权重重配）才有数据依据。批 3 的 11.2.1 真实语料探针已经把「怎么读 DB、怎么剔退化文本、怎么脱敏」跑通了，E-08 可以直接照搬那套取样逻辑。

**如果只有很少时间，做这三件事**（按性价比排序，**三项均已完成**）：

1. ~~**T-01**（删死代码，5 分钟，零风险，−51 行）~~ ✅ 批 1
2. ~~**T-08**（静态描写第 4 条 + 阈值对齐，直击 CLAUDE.md 第一目标，判定可靠）~~ ✅ 批 6
3. ~~**T-04 + T-06**（事件密度双根因 + 门槛，**唯一能解决「灌水对话拿满分」的改动**）~~ ✅ 批 3

**T-12 已于批 7 完成**，CLAUDE.md 第一目标「字数足够」现已全链路接通（评分器内部 + 首稿重试 + 质量门 + fallback 排序共 8 个接线点）。

**接下来性价比最高的是 T-13**（`dialogue_changes_state` 三态，D-07）：任务书没声明对话预期时这一维恒真，还被 4 条软放行当作正向证据白给 +140 分——改动小，但要注意消费点从 `get(..., True)` 改成 `is not False` 必须同批做完，否则 `None` 会被当假值。

**每批完成后必须做的三件事**：① 跑全量并记下 passed 数；② 提交信息里写**本次实测**的数字（T-21）；③ 更新本文档第 12 节顶部的「当前进度」一行（下面这行）。

> **当前进度**（2026-08-18 更新）：文档已完成（第 0-12 节 + 附录）。
> - **批 1 ✅**：T-01 删死代码 `_score_fallback_candidate`（−52 行）、T-20 三条 EXTRACTABLE 注释去行号并移出字面量内部、T-21 约定写进 `CLAUDE.md`。全量 **661 passed in 71.45s**。
> - **批 2 ✅**：T-02 `一切都` → 7 个完整收束短语；T-03 三张词表提为类属性 `ENDING_WEAK_HOOK_MARKERS` / `ENDING_SEMANTIC_HOOK_MARKERS` / `ENDING_CLOSURE_MARKERS`，判定改为「语义命中是必要条件」，新增 `ending_semantic_hit_count` / `ending_weak_hit_count` 并补进 `quality_metric_snapshot`；T-15 42 个 `\uXXXX` 还原 + 剔 10 个专有词 + 补通用词至 56 个 + 加 grep 护栏测试。定向 93 passed，全量 **668 passed in 97.11s**（比目标 666 多 2 条防误杀对照）。4 条反向验证全部必红成立。
> - **批 3 ✅**：T-04 `_unit_has_progression` 不再把引号当推进 + `STORY_PROGRESSION_MARKERS` 剔纯连词与 `"活"`；T-05 窗口判定改用 `_window_has_state_change` + 尾窗合并 `WINDOW_TAIL_MERGE_RATIO`；T-06 四档阈值**全部按真实语料重定**（`density_floor` 1.5/1.8/2.0、`unit_rate_floor` 0.025/0.028/0.03、`WINDOW_PROGRESSION_RATIO_FLOOR` 0.25→0.05 + `MIN_HITS=2`），绝对 `plain_run_limit` **整个删掉**换成比例 `plain_run_ratio_limit` 0.75/0.72/0.70 并新增 `max_plain_unit_run_ratio` 字段（已补进 `quality_metric_snapshot` 白名单）。定向 103 passed in 9.34s，全量 **679 passed in 94.61s**。反向验证 8 项必红成立、5 项复原确认全 True。真实语料复验：历史合格池通过率 **95.0%**（n=107，第一版阈值只有 3.7%）。
> - **教训（写在这里免得再犯）**：**不要用合成样本定生产阈值。** 批 3 第一版阈值定向与全量全绿，却在真实语料上误杀 96%——改阈值必须按 11.2.1 灌真实历史正文校准。
> - **批 4 ✅**：T-07 新增 `class TestBadSampleRegression` 9 条测试（5 个坏样本 + 1 个正向对照锚点 + 2 条分差测试 + 1 条快照测试）。生产改动只有 1 行：`flat_closure_markers` 补进 `quality_metric_snapshot` 白名单（批 2 漏的观测项）。定向 113 passed in 13.40s，全量 **688 passed in 118.20s**（比目标 687 多 1 条，原因是结尾类分差达不到 300，拆成两条测试）。反向验证 **11/11 必红**、6 个属性复原确认全 True。
> - **批 4 的两个新发现**：**D-24 尾窗遮蔽**——`_evaluate_ending_pressure` 只看 `condensed_text[-260:]`，短的坏结尾会被正文强钩子盖过去（同一坏结尾 38 字尾巴 → `codes=[]`/score 1302，275 字尾巴 → 含 `ending_pressure_missing`/score 1042）；**D-25** 静态描写三条 or 里第 2/3 条无任何样本覆盖。两条都排进批 6。
> - **教训 2（与批 3 同源）**：新增快照字段必须显式过 `quality_metric_snapshot` 白名单，那是唯一的静默丢弃点——批 2 补了两个计数却漏了 `flat_closure_markers`，直到批 4 写测试才暴露。
> - **批 5 ✅**：T-22 修复闭环。新增类属性 `STRUCTURAL_GATE_REPAIR_MAX_ROUNDS = 2`（硬编码，成本闸门不是调参空间）与 `staticmethod _is_structural_repair_improvement`（严格子集收缩 `len(after) < len(before) and not (after - before)`）；`_attempt_structural_gate_repair` 重写为「总是返回诊断字典，采纳与否看 `adopted`」，四种跳过原因写进 `repair_skipped_reason`；两处调用点未采纳也把 `repair_summary` 追加进 `runtime_metadata["quality_gate_repairs"]`。定向 116 passed in 4.84s，全量 **691 passed in 61.34s**（比目标 690 多 1 条，原因是轮数上限要上下都卡、诊断保留分两条分支，净增 3 而非 2）。反向验证 **12/12 必红**、5 项复原确认全 True。
> - **教训 3（判据类的通用陷阱）**：**blocker 数量下降不等于改善。** 实测反例 `"## 场景 1｜开场\n\n" + GOOD_DRAMATIC` 从 7 条掉到 1 条，但那 1 条是全新形态 `chapter_artifact_markers`，采纳它会让修复循环朝错误方向收敛。`not (after - before)` 是判据主体，不是防御性冗余。E-11 做分档时尤其要带上这半条。
> - **教训 4（反向验证方法论）**：基于 `inspect.getsource` 文本断言的测试，改坏点必须落在 `inspect.getsource` 本身；替换被测函数对象只会抛 `TypeError`，那是**假必红**——变红原因与要证明的缺陷无关。
> - **批 6 ✅**：T-08 静态描写第 4 条判定 + 第 2 条门槛按真实语料保持 `>= 3`（触发率 0.029 而非孤儿版 0.044）；T-09 重建 `STATIC_ACTION_MARKERS`（**根因是「看/却/但/发现」这类高频单字**，不只是自然现象动词）并把自然现象动词单列成 `AMBIENT_MOTION_MARKERS`（不参与判定，仅供护栏断言）；T-10 照搬 `_evaluate_repetition_risk`（阈值一个未动，真实触发率 0.000）+ 判罚 −420 + 第 12 类硬 blocker；D-24 改成**保留 260 尾窗 + 末段否决**（`ENDING_CORE_WEAK_ONLY_LIMIT = 2` / `ENDING_CORE_FLAT_CHARS = 150`），缩窗的 6 个变体在真实通过池上全部更差（0.475~0.782 vs 基线 0.812）；D-25 改成四条 or 各配一个**只命中自己**的样本。定向 143 passed in 3.68s，全量 ~~718 passed~~ **（假绿，D-26）**（计划 +5，实际 +27）。反向验证 **16/16 必红**、恢复校验 True。
> - **批 6 的两条方法论**：① **凡是"测试里重算了一遍生产逻辑"的归因辅助，都必须另配一个卡在阈值边界上的哨兵样本**——第一轮反向验证里「第 2 条门槛松到 `>= 2`」全绿，就是因为归因函数在测试里重算，检测不到生产端阈值漂移。② **任何"复制样本凑字数"的测试辅助都要保证进入统计的单位唯一**——批 3 的 `_grow` 只替换首行占位符，导致 T-10 一落地就把正向对照自己判成重复灌水。
> - **批 7 ✅**：T-11 焦点人物缺席进候选评分（判罚 −240，保持 warning 不加 blocker）；T-12 字数维度四层断链全修（三判罚 620/520/180、`upper` 系数 2.0/1.6、第 3 层删默认值改必填、第 4 层默认值取 0）。真实语料校准 n=99：`below_min` 触发 0.220（**实为真实字数不足，比值 p50 仅 0.608**，不调松）、`far_below` 0.024、`far_above` 0.012；1.25 系数会让 `far_above` 涨到 0.305。定向 167 passed in 3.73s，全量 **742 passed in 62.50s**（计划 +7，实际 +24）。反向验证 **14/14 必红**、写回校验一致。
>
> - **下一步：批 8（T-13 `dialogue_changes_state` 三态 / T-14 事件密度短路返回值），基线 742。** 剩余 7 个 T 任务与 12 个 E 任务待办，另有 8.4 真实生成端到端验证待额度恢复后补。

---

## 附录 A：关键代码位置速查

> **行号会漂移**（本轮已因此踩坑，见 D-17）。动手前用 `grep -n "<符号名>"` 重新定位。这张表按**符号名**索引，行号只作参考。

### A.1 `backend/app/services/pipeline_orchestrator.py`

| 符号 / 内容 | 参考行号 | 相关缺陷 |
|---|---|---|
| `PipelineConfig.min_word_count: int = 500` | 114 | D-15 |
| `PipelineConfig.enforce_min_word_count: bool = True` | 117 | D-13 |
| `_resolve_chapter_draft_contract` | **1235** | 9.4 / E-01 |
| **⚠️ 本表行号已于 2026-08-19（批 8 收尾）全表重新校准**，方式是逐个符号 `grep -n` 实测，**不是**按插入量估算偏移。文件当前 **8077 行**（批 5 版本约 8267 行，**变短了**——所以旧表里「批 6 新增」那几行标的 7569-7846 全部偏大 1000+，已作废）。| — | — |
| `_evaluate_structural_quality_gate_for_content` 定义 | **415** | D-20 |
| ↳ ~~硬编码默认值 `target=3000, min=2000`~~ → **已改必填**（keyword-only 无默认） | **424** | **D-20 ✅ 批 7 已修** |
| `_build_quality_issue_summary` | **486** | 9.1 |
| ↳ `tone` 升级判据（`len(items) >= 2` 或含 danger 类 code） | **562** | 9.1 |
| ↳ 第 12 类 blocker `repeated_paragraph_flood`（label / 说明 / 派发 / 消费） | **446 / 469 / 531 / 733** | ✅ T-10 |
| `_build_structural_reader_polish_issues`（第 2 层定向修复清单） | **975** | T-22 / D-27 B |
| `STRUCTURAL_GATE_REPAIR_MAX_ROUNDS = 2` | **1888** | **T-22 ✅**（硬编码成本闸门，不要改成配置项） |
| `_is_structural_repair_improvement`（严格子集收缩判据） | **1891** | **T-22 ✅** |
| `_attempt_structural_gate_repair` | **1905** | **D-21 ✅ / T-22 ✅** |
| `runtime_metadata["quality_gate_repairs"]` 两处写入点 | **3582 / 3810** | **T-22 ✅**（未采纳也写） |
| `quality_metric_snapshot` 消费点（落库 / gate / 快照组装） | **595 / 618 / 1852 / 3907** | 9.2 |
| `generate_chapter` 主流程入口 | **2164** | 3.x |
| `_resolve_config`（flow_config 覆盖） | **4255** | — |
| `_build_stable_retry_config` | **4434** | **D-27 B 组**（短章/长章都该返回 `None`，实际都返回了配置） |
| `_build_prompt_sections` | **5290** | 9.4 |
| `_resolve_style_hints`（3 条候选风格） | **5399** | E-06 |
| `_evaluate_first_draft_retry` 定义（第 3 层，✅ 批 7 已接字数） | **5420** | D-13 ✅ / D-07 ✅ |
| `_chapter_mission_expects_dialogue` | **6160** | D-07 / E-10 |
| `_collect_fallback_mission_keywords` | **6097** | E-07 |
| `STORY_PROGRESSION_MARKERS`（✅ 批 3 已剔纯连词与 `"活"`） | **6312** | **D-02 已修** |
| `ENDING_WEAK_HOOK_MARKERS`（批 2 提为类属性，7 个） | **6330** | D-03 已修 |
| `ENDING_SEMANTIC_HOOK_MARKERS`（批 2 去过拟合，56 个） | **6335** | D-06 已修 |
| `ENDING_CLOSURE_MARKERS`（批 2 换完整短语，14 个） | **6346** | D-04 已修 |
| `_story_units`（句子级切分，未改） | **6353** | D-16-a |
| `_unit_has_progression`（✅ 批 3：引号必须同时带状态变化词） | **6367** | **D-02 已修** |
| `_window_has_state_change`（批 3 新增，窗口级判定） | **6389** | **D-16-c 已修** |
| `_split_progression_windows`（批 3 新增） | **6402** | T-05 |
| `_event_density_floors`（✅ 批 3 按真实语料重定四档） | **6412** | **D-16-a 已修** |
| `EVENT_DENSITY_MIN_SAMPLE_CHARS = 800`（**不要下调，见批 8**） | **6442** | ✅ T-14 |
| `_evaluate_event_density` | **6445** | **D-15 ✅ 批 8 已修** |
| ↳ 短路分支三个 `passed` 返回 `None` + `event_density_evaluated: False` | **6461** | ✅ T-14 |
| ↳ 正常路径 `event_density_evaluated: True` | **6528** | ✅ T-14 |
| `_count_dialogue_state_change_markers` | **6544** | **D-27 B 组**（三类语义一个都认不出，归 T-26） |
| `UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR = 1` | **6562** | ✅ T-13 |
| `_evaluate_dialogue_changes_state`（✅ 批 8 改三态） | **6565** | **D-07 ✅ 已修** |
| ↳ `dialogue_state_applicable` 产出点 | **6598** | ✅ T-13 |
| `ENDING_CORE_WEAK_ONLY_LIMIT` / `ENDING_CORE_FLAT_CHARS` | **6607 / 6615** | ✅ D-24 |
| `_evaluate_ending_pressure`（含 `raw_text` 形参与末段否决） | **6619** | ✅ D-03 / D-04 / D-24 |
| `STATIC_ACTION_MARKERS`（34 项）/ `AMBIENT_MOTION_MARKERS`（10 项） | **6704 / 6716** | ✅ T-09 |
| `_estimate_static_description_runs`（`staticmethod` → `classmethod`） | **6777** | ✅ T-09 |
| `_evaluate_repetition_risk`（照搬孤儿版 949-980） | **6794** | ✅ T-10 |
| `_detect_chapter_artifact_markers`（只检测不清理） | **6842** | D-11 |
| `_score_story_quality_candidate` 主体 | **6879** | D-09 / D-13 |
| ↳ `static_description_risk` 四条 or（**第 2 条门槛 `>= 3` 不要放松，D-25 哨兵守着**） | **6952-6960** | ✅ T-08 |
| ↳ 静态判罚 `score -= 260` / 重复判罚 `score -= 420` | **6998 / 7000** | ✅ T-08 / T-10 |
| ↳ 密度三判定三分支计分（`is True` / `is False`，**不要改回真假判断**） | **7057** | ✅ T-14 |
| ↳ `dialogue_changes_state` 三分支计分（±140） | **7037** | ✅ T-13 |
| `quality_metric_snapshot` 白名单（**新增字段必须加进来，唯一静默丢弃点**） | **7115-7122** | 9.2 |
| `_fallback_select_best_version`（第 4 层，默认值取 0 而非删除） | **7155** | D-13 ✅ |
| `_should_override_ai_review_choice`（第 4 层 AI 复核覆盖） | **7207** | ✅ T-13 |
| `_resolve_chapter_generation_soft_timeout` | **1331** | — |
| `_resolve_chapter_mission_timeout` | **1345** | **D-27 B 组**（`(700)` 实际 30.0 / 测试要 20.0） |
| `_resolve_chapter_generation_max_tokens` | **1561** | **D-27 B 组**（`(700)` 实际 3200 / 测试要 2200） |
| **`_resolve_writer_prompt_budget`（不存在，待实现）** | — | **D-27 A 组 / T-24**（上面两个的缺失第三成员） |
| ~~`_score_fallback_candidate`（必崩死代码）~~ | 已删 | ✅ D-19 / T-01 |
| EXTRACTABLE 注释三处（✅ 均在语句外） | **380 / 6311 / 7397** | D-17 已修 |
| `PipelineConfig.min_word_count` / `enforce_min_word_count` | **102 / 105** | D-15 / D-13 |

### A.2 其它后端文件

| 文件 | 符号 / 内容 | 参考行号 | 相关 |
|---|---|---|---|
| `story_quality_scoring.py`（**1525 行孤儿，零引用**） | `StoryQualityScoringMixin` | 全文件 | D-01 / T-19 |
| ↳ | `_collect_focus_character_names` | 909-947 | D-12 / T-11 |
| ↳ | `_evaluate_repetition_risk`（**可直接照搬**） | 949-980 | D-10 / T-10 |
| ↳ | `_detect_chapter_artifact_markers` | 983 | D-11 |
| ↳ | `_fallback_select_best_version` | 1006 | D-11 |
| ↳ | `_apply_deterministic_cleanup` | 1069 | D-11 / T-17 |
| ↳ | `_score_fallback_candidate`（函数体**无**字数逻辑，证明生产版是错位粘贴） | 1157-1168 | **D-19** |
| ↳ | `_sanitize_markdown_presentation` | 1201 | D-11 / T-17 |
| ↳ | 字数计算（`preferred_floor` / `upper_target` 2.0/1.6） | 1317-1325 | **D-13 / T-12** |
| ↳ | 静态描写判定（**含生产缺失的第 4 条**） | 1346-1356 | **D-08 / T-08** |
| ↳ | 完整评分（后 6 行判罚生产全缺） | 1361-1381 | D-13 / T-12 |
| ↳ | `inherit_from_previous` 也进了关键词候选 | 293 | E-07 |
| `longform_context_service.py` | `evaluate_continuity_quality`（**范式参照**） | 709-840 | 9.6 / E-11 |
| ↳ | `package is None` 时降级放行 | 716-720 | 9.6 |
| ↳ | `chapter_focus_missing`（warning） | 734-745 | **D-12 修正依据** |
| ↳ | 因果链承接检查 | 835+ | 9.6 |
| `prompt_service.py`（**仅 97 行**） | `get_prompt(name)` 走 DB | — | **E-01** |
| `ai_review_service.py` | `_format_mission_checklist`（把 inherit 喂给 review） | 230-247 | E-07 |
| `pipeline_chapter_mission.py` | 任务书生成 / Schema / 合并 | 130 / 208 / 382 / 659 | E-10 |
| `test_generation_quality_guards.py`（**批 8 后 4438 行 / 188 收集 / 167 passed, 21 failed**） | `_SAMPLE_TARGET_WORDS` / `_SAMPLE_MIN_WORDS`（批 7 提到文件头，gate 类测试共用） | **23** | ✅ T-12 |
| ↳ | `class TestBadSampleRegression`（批 4，9 条） | **3016** | ✅ T-07 |
| ↳ | `class TestStaticActionMarkerTable`（批 6，5 条） | **3127** | ✅ T-09 |
| ↳ | `class TestStaticDescriptionRiskBranches`（批 6，8 条） | **3177** | ✅ T-08 / D-25 |
| ↳ | `class TestRepeatedParagraphFlood`（批 6，7 条） | **3279** | ✅ T-10 |
| ↳ | `class TestEndingCoreWindow`（批 6，7 条） | **3366** | ✅ D-24 |
| ↳ | `class TestFocusCharacterAbsence`（批 7） | **3494** | ✅ T-11 |
| ↳ | `class TestWordCountPenalties`（批 7） | **3662** | ✅ T-12 |
| ↳ | `class TestDialogueStateTriState`（批 8） | **3968** | ✅ T-13 |
| ↳ | `class TestDialogueStateTriStateWiringAcrossLayers`（批 8，四层接线） | **4093** | ✅ T-13 |
| ↳ | `class TestEventDensityNotEvaluated`（批 8） | **4222** | ✅ T-14 |
| ↳ | `class TestEventDensityNotEvaluatedWiringAcrossLayers`（批 8，四层接线） | **4353** | ✅ T-14 |
| ↳ | **21 个失败测试**（引用 9 个从未实现的方法） | 见 **D-27 A 组**表 | **T-24** |
| `api/routers/writer.py`（5899 行） | `_resolve_quality_candidate_version_count` | 1137 | 成本 |
| ↳ | `high_quality_longform = requested_target >= 4500` | 1318 | 成本 |
| ↳ | 质量门失败 → `decision="quality_gate_failed"` | 3359 | D-21 |

### A.3 前端文件

| 文件 | 内容 | 参考行号 | 相关 |
|---|---|---|---|
| `frontend/src/utils/chapterQuality.ts`（**批 8 后 129 行**） | 三态字段的 `=== false` 判据（**`null` 不得算失败**） | **21 / 23** | ✅ **D-22 / T-13 / T-14** |
| ↳ | 本地兜底文案（✅ 批 8 补齐 3 条 event_density） | **104 / 106** | ✅ **D-22 已修** |
| `frontend/src/utils/chapterQuality.spec.ts`（**批 8 后 160 行 / 5 测试全绿**） | `treats null tri-state metrics as not-applicable rather than failures`（**三态前端闭环**） | **127** | ✅ D-22 |
| `WDSidebar.vue` / `WDWorkspace.vue` / `VersionSelector.vue` / `WDVersionDetailModal.vue` | 均有配套 `.spec.ts` | — | 9.2 |

---

## 附录 B：命令速查

> **环境注意**（本轮全部踩过）：① `cd` **不跨 Bash 调用持久**，每条命令自带 `cd`；**后台命令尤其如此**，否则报 `file or directory not found: app`；② 加 `PYTHONIOENCODING=utf-8` 防 GBK 乱码；③ 不要用长 `&&` 链，用 `;` 分隔并在末尾 `echo "===EXIT $?==="`；④ **不要在仓库根跑 `grep -r`**（`node_modules` 会让它超过 120s 被转后台），用 ripgrep 或限定 `backend/app` 范围；⑤ **全量测试必须带四个 `-p no:` 开关**，见下方第一条 —— 少一个就是假绿（D-26）。

**① 后端全量（唯一正确的写法）**：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && python -m pytest app -p no:randomly -p no:anyio -p no:seleniumbase -p no:sb_manager -q --timeout=120 --timeout-method=thread -rf 2>&1 | tail -45
```

期望 `727 passed, 36 failed`（2026-08-19）。**`-rf` 是必需的**：36 个先存失败要逐条和 D-27 的表对，光看数字对不出「是不是换人了」。

> ⚠️ **绝对不要用** `python -m pytest app -q`（裸跑）。它会因 anyio/asyncio 插件冲突静默吞测试、丢输出、并返回退出码 0 —— 本文档历史上所有「全量全绿」都是这么来的（D-26）。

**② 后端定向（质量守卫，最常用；同步测试不受 D-26 影响）**：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -p no:randomly -p no:anyio -q 2>&1 | tail -5
```

期望 `167 passed, 21 failed`（21 个全是 D-27 A 组欠账）。

**③ 快速护栏（改质量门前先跑这条，约 3.4s）**：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -p no:anyio -q -k "BadSampleRegression or StaticActionMarkerTable or StaticDescriptionRiskBranches or RepeatedParagraphFlood or EndingCoreWindow" 2>&1 | tail -3
```

**④ 批 8 三态专项（T-13 / T-14 四层接线）**：

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -p no:anyio -q -k "TriState or NotEvaluated" 2>&1 | tail -3
```

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -m pytest app/services/test_generation_quality_guards.py -q -k "event_density" 2>&1 | tail -20
```

**⑤ 前端定向（`npm run test:unit` 在本机不可用，用 `npx vitest run`）**：

```bash
cd /d/小说写作/xuanqiong-wenshu/frontend && npx vitest run src/utils/chapterQuality.spec.ts 2>&1 | tail -8
```

期望 `5 passed`（2026-08-19 实测 29.29s；`environment 18.04s` 是 jsdom 启动，正常）。

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && grep -n "STORY_PROGRESSION_MARKERS\|_unit_has_progression\|density_floor" app/services/pipeline_orchestrator.py
```

```bash
cd /d/小说写作/xuanqiong-wenshu/backend && PYTHONIOENCODING=utf-8 python -c "from app.services.pipeline_orchestrator import PipelineOrchestrator as P; print(len(P.STORY_PROGRESSION_MARKERS))"
```

```bash
cd /d/小说写作/xuanqiong-wenshu && git status --short | wc -l ; git branch --show-current
```

```bash
cd /d/小说写作/xuanqiong-wenshu && git diff --stat backend/app/services/pipeline_orchestrator.py
```

---

## 附录 C：字段与术语字典

### C.1 质量指标字段（`quality_metric_snapshot` / `metadata["quality_metrics"]`）

| 字段 | 类型 | 含义 | 当前状态 |
|---|---|---|---|
| `score` | int | 候选综合分 | 形式项 672 分可机械刷（D-09） |
| `word_count` | int | 去空白后的字符数 | 正常 |
| `paragraph_count` | int | 段落数 | +216 可刷 |
| `dialogue_marker_count` | int | 引号数量 | +120 可刷 |
| `scene_fulfillment_rate` | float | 已兑现场景 / 总场景 | 依赖关键词命中，措辞变体会漏判 |
| `fulfilled_scene_count` / `scene_count` | int | 场景兑现计数 | 正常 |
| `dialogue_changes_state` | bool | 对话是否改变局势 | **无任务书时恒 True**（D-07），T-13 改三态 |
| `ending_pressure_passed` | bool | 章末是否递出压力 | ✅ 批 2 已修：语义命中成必要条件（D-03）、`"一切都"` 误杀已解（D-04）。✅ **批 6 已修 D-24**：保留 260 字符尾窗做语义判定，另加末段否决（`ending_core_deflating`），短结尾不再被正文钩子遮蔽 |
| `ending_core_chars` / `ending_core_semantic_hit_count` / `ending_core_weak_hit_count` / `ending_core_deflating` | int/int/int/bool | 末段（按换行切出的最后一段）的长度、语义钩子命中数、弱信号命中数、是否判为泄气 | ✅ 批 6 新增（D-24）。**末段否决与 `flat_closure_markers` 是两条独立路径**：前者管「没钩子」，后者管「完整收束」 |
| `repetition_risk` / `repeated_paragraph_count` / `repeated_paragraph_instances` / `max_repeated_paragraph_count` / `repeated_paragraph_ratio` / `longest_repeated_paragraph_chars` | bool/int/int/int/float/int | 精确重复段落检测（>= 30 字的段落才计入，正文 >= 800 字才启用） | ✅ 批 6 新增（T-10），阈值照搬孤儿版未改。真实语料触发率 **0.000**，所以做硬 blocker `repeated_paragraph_flood` 而非 soft_pass |
| `ending_pressure_hits` | list | 命中的压力词（顺序：deliver → mission → 语义 → 弱信号，截前 10） | ✅ 批 2 已去过拟合（D-06）。**断言时别绑具体词**，用下面两个计数字段 |
| `ending_semantic_hit_count` | int | 语义压力词命中数 | **批 2 新增**。`>= 1` 是通过的必要条件；快照里也有 |
| `ending_weak_hit_count` | int | 弱信号命中数（`？ ? ！ ! 却 突然 忽然`） | **批 2 新增**。只能凑数量，单独存在不构成通过 |
| `flat_closure_markers` | list | 命中的平淡收束词 | ✅ 批 2 已改完整短语（D-04）；仍是一票否决（有意保留，理由见 D-04）。✅ **批 4 已补进快照白名单**——批 2 漏了它，用户只看到「章末未递出压力」却看不到是哪句触发的否决 |
| `static_description_risk` | bool | 静态描写是否过多 | 缺第 4 条判定，阈值偏松（D-08）。三条 or 里**只有第 1 条有测试覆盖**（D-25） |
| `static_paragraph_count` / `max_static_run` | int | 静态段落数 / 最长连续静态段 | 正常 |
| `event_density_passed` | bool | 事件密度是否达标 | ✅ 批 3 已按 147 条真实语料重定阈值（D-16-a）。定位是**底线门**：只拦纯描写/纯寒暄，不做质量优选。前端兜底仍漏它（D-22） |
| `progression_unit_count` | int | 有推进的句子数 | ✅ 批 3 已修：引号不再恒真、纯连词与 `"活"` 已剔（D-02） |
| `progression_unit_rate` | float | 推进句 / 总句数 | ✅ 批 3 方向已修正。**真实语料 p50 仅 0.079**（p05 0.026 / p95 0.204），门槛 0.025-0.03；≥0.3 基本只出现在合成样本里 |
| `event_density_per_1000` | float | 每千字推进句数 | ✅ 批 3 门槛 1.5/1.8/2.0（真实语料 p05 2.01 / p50 4.60 / p95 9.48） |
| `state_change_window_pass_rate` | float | 合格窗口占比 | ✅ 批 3 已修：改用 `_window_has_state_change` + 尾窗合并（D-16-c）。窗口内需 `占比 ≥ 0.05` **且** `推进句 ≥ 2` 条件同时满足 |
| `max_plain_unit_run` | int | 最长无推进连续句（绝对句数） | ⚠️ **不再作阈值**：绝对值随章节长度线性膨胀（真实 p50=36 / p95=104 / max=167），用它必然歧视长章。只保留作展示 |
| `max_plain_unit_run_ratio` | float | 最长无推进连段 / 全章句数 | **批 3 新增，替代绝对句数做判定**。真实语料 p50=0.218 / p95=0.448 / max=0.681，纯寒暄灌水样本 1.0；上限 0.75/0.72/0.70 |
| `quality_issue_codes` / `quality_issue_labels` | list | 问题 code / 中文文案 | **新增 blocker 必须同时给中文 label**（9.2） |
| `quality_issue_summary` | dict | `{tone, labels, codes, count}` | 前端 tone 直接用它 |
| `repetition_risk` 等 | — | 重复段落 | **生产完全缺失**（D-10） |
| `focus_character_missing` 等 | — | 焦点人物缺席 | 生产缺失，连续性门有 warning（D-12） |
| `event_density_evaluated` | bool | 密度是否真的评估过 | **待新增**（T-14） |
| `word_count_below_min` 等 | — | 字数判罚标志 | **生产缺失**（D-13 / T-12） |
| `reversal_signal_count` | int | 反转信号数 | **待新增**（E-02） |
| `inherit_hit_count` 等 | — | 跨章承接命中 | **待新增**（E-07） |

### C.2 任务书（`chapter_mission`）字段

| 字段 | 用途 | 备注 |
|---|---|---|
| `chapter_purpose` | 本章目的 | 进关键词词袋 |
| `scene_list[]` | 场景清单 | 每项含 `goal` / `conflict` / `turn` / `outcome` / `payoff` / `bridge` / `emotion_shift` / `dialogue_value` / `end_hook` / `foreshadowing_task` / `characters` |
| `continuity_anchor.inherit_from_previous` | 必须承接上章的事 | **从未被确定性校验**（E-07） |
| `continuity_anchor.deliver_to_next` | 必须递给下章的压力 | **有**动态注入章末词表（机制正确） |
| `dialogue_strategy.purpose` / `.subtext` | 对话职责 | 缺失 → `dialogue_changes_state` 恒真（D-07） |
| `focus_characters` / `character_focus` / `pov_character` | 焦点人物 | 生产路径未用于检查（D-12） |
| `character_arc_task` | 人物弧任务 | 进关键词词袋 |

### C.3 术语

| 术语 | 含义 |
|---|---|
| **结构质量门**（structural quality gate） | `_evaluate_structural_quality_gate_for_content`，11 类 blocker，失败 → 落库拒稿 + 422 |
| **连续性门** | `longform_context_service.evaluate_continuity_quality`，有 blocker/warning 分级 + patch（9.6，范式参照） |
| **软放行**（soft pass） | 6 条：`progression_soft_pass` / `scene_soft_pass` / `semantic_scene_soft_pass` / `dense_scene_soft_pass` / `density_soft_pass` / `rich_progression_evidence`。用其它维度的正向证据豁免某一维不达标 |
| **自评豁免** | `critique_score >= 75/70` 时两类 blocker 降级（D-14），构成自评闭环 |
| **定向修复**（structural gate repair） | `_attempt_structural_gate_repair`，质量门失败后针对 blocker 调 `revise_chapter` 重写（D-21 / T-22） |
| **孤儿模块** | `story_quality_scoring.py`，1525 行，`StoryQualityScoringMixin` 未被任何类继承（已用 `__mro__` 验证），但保留着 6 项生产缺失的能力 |
| **探针法**（execute-to-observe） | 写临时脚本直接调 classmethod 观察真实输出，而非阅读源码推断。本轮 3 个核心结论只有执行才能得到（11.2） |
| **资格分 / 质量分** | T-16 的两段式评分：形式项封顶（资格），内容项以判罚为主且不设下限（质量） |
| **坏样本回归** | T-07 的 8 个样本，每个只坏一个维度，配 1 个正向对照防误杀 |

---

## 文档完成状态

- **第 0-12 节 + 附录 A/B/C 全部完成。**
- 缺陷清单：**D-01 ～ D-27**（27 条。本轮新增实证 5 条：D-19 死代码、D-20 字数配置断链、D-21 修复闭环、D-22 前端兜底缺口，以及 D-02 的第二根因「纯连词污染词表」；批 2 新增 D-23；批 4 新增 D-24 尾窗遮蔽、D-25 静态连段无覆盖；**2026-08-19 新增 D-26 runner 假绿（P0）、D-27 36 个先存失败（P0）**）。**已修：D-02 / D-03 / D-04 / D-06 / D-07 / D-08 / D-10 / D-15 / D-16-a / D-16-c / D-17 / D-19 / D-21 / D-22 / D-24 / D-25。**
- 修复任务：**T-01 ～ T-26**（26 条）。**已完成 T-01～T-15 与 T-20、T-21、T-22（批 1-8）**；D-24/D-25 已随批 6 关闭，D-22 随批 8 关闭，均不单独占编号。**新增 T-23（修 runner，P0）/ T-24（实现 9 个方法）/ T-25 / T-26。**
- 增强任务：**E-01 ～ E-11**（12 项，含 E-01.1 / E-01.2 拆分）。**全部待办。**
- **代码改动进度：批 1-8 已完成。** 但**全量基线的历史序列（659 → 742）全部作废**——它们由一个会静默吞测试的 runner 产出（D-26）。**唯一可信基线：`727 passed, 36 failed`（2026-08-19）。** 下一步是 **T-23 修 runner**，不是批 9，见第 12 节。

---

## 2026-08-19 本轮（批 8 + 收尾审查）的三项结论

这三条改变了文档的可信度基础，单独列出来，接手人**先看这里再看别处**：

**① 测量工具是坏的（D-26，P0）。** `pytest.ini` 的 `asyncio_mode = auto` 与 `anyio` 插件抢同一批异步测试，进程猝死、输出缓冲区丢失、`-q` 下退出码还是 0。控制变量实证：同一文件裸跑 `RC=1` 且输出 0 字节，加 `-p no:anyio` 则 `19 passed in 15.28s`。**后果是本文档与所有历史提交里的每一个"全量全绿"都是假的**，包括 §2.3 的 742、§4.1 的整张历史表、以及提交 `32eafd3` / `57e7e1c` 的 `401/401`。定向测试（同步、不碰 anyio）不受影响，所以"各批改对了没有"仍有证据；**但"没有破坏别处"这个结论从未被真正验证过。**

**② 修好 runner 后首次拿到完整结果：`727 passed, 36 failed`（D-27，P0）。** 36 个失败**不是本轮改坏的**，是一直存在、被崩溃掩盖着从没跑到过。构成是 28 个 spec-first 欠账（9 个方法从未被实现）＋ 8 个真实行为分歧。"从未被实现"经四重排除坐实：HEAD^ / 工作区 / `git log --all -S` 全为 0，且**扫描全部 154 个 transcript（含 `subagents/` 与 workflows 子目录）确认针对该文件的写入恰好 97 次、已全部重放**，而同期对测试文件的 48 次编辑完好无损。**别再往"恢复"方向浪费时间——扫不到的东西就是从来没写过。**

**③ 批 8 本体完成，但 T-13 留一个缺口。** 三态改造 + 短路返回 `None` + 前端兜底文案落地，反向验证 24/24 必红，定标分差 `True-None=140` / `None-False=140`。**缺口**：`_count_dialogue_state_change_markers` 对"具体揭示 / 做出选择 / 外部压力"三类语义一个都认不出来（实测 0 个标记，测试要求 ≥2）。三分支结构是对的，喂进去的计数偏低——归 T-26，**须走真实语料校准**。

**一条方法论教训（比上面三条更通用）**：本轮花了大量时间在"全量跑不出数字"上反复试超时、试分片、试插件组合，中途一度把原因归结为"网络/DB 依赖测试"和"Windows 长时间静默输出被判超时"——**两个归因都是错的**。真正定位靠的是**控制变量**：同一文件、同一顺序，只改一个开关。**下次遇到"时快时慢、时红时绿、单跑必过合跑必崩"，先怀疑工具链冲突，别怀疑被测代码；并且第一件事是让失败可复现，而不是让它消失。**

**本轮收尾时做的一致性修正**（记在这里是为了让接手人知道哪些数字被动过、别再拿旧版数字对照）：

1. 全文的后端门禁基线从 `648 passed in 51.41s` 统一为 **`659 passed in 83.58s`**（648 是前序会话的过期值，本轮实测 659；D-18 记录了这个数字反复过期的原因）。原先第 2.3 节与 D-01/D-12/D-14 的验收行还在用 648，会让接手人在跑完前几批后误判「测试变多了是不是有问题」。
2. 2.3 节的门禁要求改为「达到当批目标值」，绝对数只在 6.3 表里维护一处，避免同一个数字散落在七八处各自过期。
3. 6.3 分批表的「全量基线变化」列（原先混用 `659 → 659`、`659+3`、`+4` 三种写法，且各批增量是早期估算的 +35 / 终值 694）改为 **「新增测试 +N」+「跑完这批的全量应为 X passed」两列**，数字全部按第 7 节每个任务末尾的「**全量**：+N」标注重新相加：各批 +2 / +5 / +6 / +8 / +2 / +5 / +7 / +5 / +2 / +6，**合计 +48、终值约 707 passed**。同时把 T-07 里写的「+8（674 passed）」改为 680（它用的是旧序列）。**这是本次收尾发现的唯一算术性矛盾**，如果不修，接手人跑完批 4 会看到 680 而文档说 674，从而误以为多出了 6 个不该有的测试。
4. 6.1 总表 T-14 行补注「含 D-22 前端兜底」——D-22 不单独占任务编号，如果只看 6.1 表会漏掉这 4 行前端改动。
5. 2.3 节与 6.3 说明第 3 条曾一度写成「提交信息不要写绝对测试数」，与 T-21 的约定（**写本次实测的数字**）冲突，已统一到 T-21 的口径。
6. **上面第 1、3 条里的数字已被实测覆盖**（写它们时代码还没动）：基线不再是 659 而是 **742**（659 → 661 → 668 → 679 → 688 → 691 → 718 → 742）；合计增量不再是 +48 而是 **+103**、终值约 **762**（批 2 实际 +7、批 3 实际 +11、批 4 实际 +9、批 5 实际 +3、批 6 实际 +27、批 7 实际 +24，都比估算多）。**以 6.3 表的「执行状态」引用块和第 12 节「当前进度」为准，这两处每批都会更新；第 1、3 条只作为"当初为什么改过这些数字"的备查。**
7. **附录 A.1 的行号在批 5 全表校准过一次**（批 5 在 2035 前后插入约 130 行，2035 之后的旧行号全部失效）。校准方式是 `grep -n` 逐个符号实测，不是按插入量估算偏移。**下一批改完 `pipeline_orchestrator.py` 后要再校准一次**——这张表的价值全在行号准，错了比没有更糟。
