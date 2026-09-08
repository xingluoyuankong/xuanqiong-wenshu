# 评分反向验证证据修复 — 2026-09-07

## 1. 结论与范围

本次只新增评分反向验证脚本、原始日志、结构化 JSON 日志及本报告，未编辑业务源码、现有测试或其他文档。旧证据保留原样，但其“四条失败”由 classmethod 绑定错误造成，撤销其作为 marker 回归有效性证明的资格。

新的同一 Python 进程验证链为：**baseline 54 passed → 快照 marker 字段删除 4 failed → marker 判罚归零 4 failed → 原描述符恢复后 54 passed**。第二个变异的四条失败全部是原测试第 124 行的业务断言 `AssertionError`，实际分差为 0、预期为 480；第一个变异补齐旧脚本原计划验证的快照字段缺失证据。两者均无 `TypeError`，采集、setup、teardown 均正常。驱动退出码为 0，表示预期的反向失败和恢复检查全部成立，不表示变异测试通过。

- 执行时间：2026-09-07 01:29:11 至 01:29:26（Asia/Shanghai，UTC+08:00）。
- Python：3.11.9，Windows AMD64；PID：40076。
- 工作目录：`D:\小说写作\xuanqiong-wenshu`。
- 解释器：`D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe`。
- 目标测试：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_scoring_artifact_parity.py`。
- `PYTHONUTF8=1`，Python 使用 `-B`，pytest 禁用 cacheprovider；使用当前配置的解释器与权限，没有提权或新建 Codex 任务。

## 2. 文件与证据索引

| ID | 角色 | 绝对路径 |
|---|---|---|
| E-01 | 旧脚本，只读保留 | `D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260906.py` |
| E-02 | 旧失败日志，只读保留 | `D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260906.log` |
| E-03 | 新增进程内 mutation 驱动 | `D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260907.py` |
| E-04 | 新增完整命令、pytest 输出、失败校验日志 | `D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260907-20260907T012911556549+0800.log` |
| E-05 | 新增结构化日志，含每阶段记录、逐用例异常及文件哈希 | `D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260907-20260907T012911556549+0800.json` |
| E-06 | 当前测试，只读 | `D:\小说写作\xuanqiong-wenshu\backend\app\services\test_scoring_artifact_parity.py` |
| E-07 | 当前评分实现，只读 | `D:\小说写作\xuanqiong-wenshu\backend\app\services\pipeline_orchestrator.py` |
| R-01 | 本次唯一新增报告 | `D:\小说写作\xuanqiong-wenshu\docs\reports\SCORING_REVERSE_VERIFICATION_20260907.md` |

E-04/E-05 是本次执行的不可覆盖工件。重跑驱动会以新的微秒时间戳创建新日志，使用排他创建模式保留此前证据。`logs` 被当前 Git ignore 规则忽略，打包交接应显式包含 E-03/E-04/E-05。

## 3. 旧证据为何无效

E-01 先通过类属性取到已经绑定的 `_score_story_quality_candidate`，再将包装函数装成 `classmethod`。包装函数把新绑定传来的 `cls` 继续转发给已绑定方法，导致同一个类被传入两次。

E-02 四条失败均为：

```text
TypeError: PipelineOrchestrator._score_story_quality_candidate() takes 1 positional argument but 2 positional arguments (and 5 keyword-only arguments) were given
```

因此执行在调用原评分器时已经中断，根本尚未运行删除快照字段的语句。旧驱动只验证 pytest 退出码为 1，错误地将调用协议错误也视为 mutation 被测试捕获。

**Finding F-01（E-01、E-02）：旧日志只证明变异脚本绑定错误，不证明评分测试具备 marker 回归检测能力。** 本报告补充证据，不追改旧报告或旧日志。

## 4. 正确的进程内 mutation

### 4.1 描述符绑定和还原

E-03 使用 `inspect.getattr_static(PipelineOrchestrator, METHOD)` 获取原始 `classmethod` 描述符，通过 `.__func__` 获取未绑定函数。快照变异包装函数显式声明 `cls`，调用未绑定函数时只传一次 `cls`，随后删除返回快照中的 `chapter_artifact_marker_count`。这保留了原评分流程、顶层 marker 和 480 分判罚。

每个变异都在 `finally` 中恢复原始描述符对象，而非将先前已绑定的方法重新挂回类上。脚本校验恢复后描述符的对象身份，E-05 的 `descriptor_restored_by_identity` 为 `true`。恢复后在同一进程再执行原文件全部 54 条用例。

### 4.2 两个独立变异

1. **mutation_snapshot_marker_removed**：只移除返回快照的 marker count 字段。此变异精确修复旧脚本的验证意图。四条用例先完整通过 480 分判罚等断言，再在第 133 行访问被移除字段时报 `KeyError: 'chapter_artifact_marker_count'`。该异常属于被测契约缺字段，而非方法调用错误。包装器记录了 8 次成功完成原评分器调用，即每条用例 detected、neutral 各一次。
2. **mutation_marker_penalty_zero**：读取原函数源码到内存，解析 AST，确认唯一的 `artifact_penalty` 赋值及其条件与当前实现一致，只把其右值替换成整数 0。内存编译时移除 AST 的装饰器列表，将产出的未绑定函数仅包装一次 `classmethod`，函数签名保持一致。没有保存或覆盖任何源码文件。保留原 detector 和快照字段，从而让四条用例到达实际判罚断言。

第二个变异的有效语义差异如下；完整内存 AST diff 见 E-04 和 E-05：

```diff
- artifact_penalty = 480 if artifact_markers.get('chapter_artifact_markers') else 0
+ artifact_penalty = 0
```

### 4.3 证据判定标准

新驱动除退出码外，逐项强制校验：

- baseline 实际收集结果中必须恰有四条目标参数化用例，且整个文件全部通过。
- 每个变异选中的 nodeid 与 baseline 的四个目标完全一致；恰好 4 failed、0 passed、0 skipped。
- 每条用例的 setup/call/teardown 记录完整；采集无错误，setup/teardown 全部通过。
- 任一阶段出现 `TypeError` 都使驱动验证失败。
- 失败源必须是未改动测试文件的 `_assert_penalty_contract`，异常类型及具体语句与各变异预期完全一致。
- 快照变异只接受指定 marker key 的 `KeyError`，且真实分差仍为 480；判罚变异只接受分差断言的 `AssertionError`，实际分差必须为 0。
- 两种变异中，detected 的 marker 为 true、neutral 为 false，顶层 count 分别为正数和 0；判罚变异仍有快照字段，快照变异仍有正确判罚。
- 描述符按对象身份恢复，恢复后的全文件测试选择及通过数量与 baseline 相同。
- 前后受保护文件哈希出现差异时，驱动也返回非零。

**Finding F-02（E-03、E-04、E-05、E-06）：四条测试对缺失 marker 快照与移除 marker 判罚均有真实检测能力；有效性依据包含业务值和失败位置，而非仅有失败数量。**

## 5. 命令及实测结果

### 5.1 实际入口命令

以下为 PowerShell 命令；工具执行采用 `login:false`，所有文件参数为绝对路径。

```powershell
$env:PYTHONUTF8="1"
& "D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe" -B "D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260907.py"
```

脚本通过同一 PID 内的四次 `pytest.main` 完成验证，不使用 pytest 子进程。第一次先由 pytest 正常加载现有 conftest，再获取类对象，避免提前导入改变 baseline 的配置顺序。每阶段基础参数如下；变异阶段另加 `-k test_artifact_penalty_is_exactly_480_once_and_auditable`：

```text
-q -p no:cacheprovider --tb=short --color=no
-c D:\小说写作\xuanqiong-wenshu\backend\pytest.ini
--rootdir D:\小说写作\xuanqiong-wenshu\backend
D:\小说写作\xuanqiong-wenshu\backend\app\services\test_scoring_artifact_parity.py
```

E-04 以 `PYTEST_MAIN` JSON 数组记录准确参数边界；E-05 在每个 phase 的 `pytest_args` 保留同样数据。

### 5.2 阶段结果

| 阶段 | 实测结果 | pytest 退出码 | 驱动计时（秒） | 失败原因 |
|---|---|---:|---:|---|
| baseline | 54 passed | 0 | 4.313 | 无 |
| mutation_snapshot_marker_removed | 4 failed, 50 deselected | 1 | 0.734 | 指定 marker 快照字段的 KeyError，第 133 行 |
| mutation_marker_penalty_zero | 4 failed, 50 deselected | 1 | 0.437 | 480 分差业务断言的 AssertionError，第 124 行 |
| restored | 54 passed | 0 | 0.485 | 无 |

驱动计时包含 `pytest.main` 调用开销，和 pytest 自报测试耗时口径不同。最终原始日志摘要：

```text
PROTECTED_FILES 3795 CHANGES []
SCORING_REVERSE_VERIFIED True
DRIVER_EXIT 0
```

### 5.3 四条目标用例的业务值

目标为 E-06 中 `test_artifact_penalty_is_exactly_480_once_and_auditable` 的四个 residue 参数。为便于阅读，下表参数解码为中文；原始 pytest nodeid 完整保存在 E-05 的 `target_nodeids`。

| residue | detected 顶层 marker count | 快照变异 detected/neutral 分数 | 判罚变异 detected/neutral 分数 | 判罚变异实际分差 |
|---|---:|---|---|---:|
| `{"chapter_purpose":"调查失踪"}` | 1 | 234 / 714 | 714 / 714 | 0 |
| `[蓝图](memo)` | 1 | 234 / 714 | 714 / 714 | 0 |
| `约350字` | 1 | 234 / 714 | 714 / 714 | 0 |
| JSON 与蓝图链接以换行组合 | 2 | 234 / 714 | 714 / 714 | 0 |

快照变异中，每条 detected 的 `chapter_artifact_penalty=480`、`quality_penalty=980`；neutral 分别为 0、500。判罚变异中，每条 detected/neutral 的 artifact penalty 均为 0、quality penalty 均为 500。两组中 eligibility 均为 0、quality positive 均为 1214。

第二变异四条均在以下原测试断言失败，原日志报 `assert (714 - 714) == 480`：

```python
assert neutral["score"] - detected["score"] == 480
```

这组证据证明是 marker 判罚被移除所致，而非 `TypeError`、收集失败或 fixture 故障。

## 6. 文件保全和指纹

执行前后对 `git ls-files --cached --others --exclude-standard` 枚举的现存普通文件及旧 scoring 日志/脚本做 SHA-256 比较，共 3,795 个文件，差异列表为空。E-05 保存完整 `protected_before`、`protected_after` 和 `protected_changes`。新 scoring 工件及本次指定报告排除在保全比较之外。

| 证据 | SHA-256 |
|---|---|
| E-01 | `c04ab77aa687e200996b053a62ac4b2013ecefba0ac38012f5fee88d619ad67f` |
| E-02 | `83e27a1f0844f51d181faf22b10b91952cbdd5fb250012fe126cce4dcd871fed` |
| E-03 | `640390a393e9ad00f9e98b7ec98f9472914c3402ac3ae84c936b33f22841eaf2` |
| E-04 | `22f84f839ca8baa6df16216fde7a65858934783132deae8e8f5c65b942912d8b` |
| E-05 | `c813109bc3eed7313dee2122058d0151076c98423e3f2a975cea8d349ce9773c` |
| E-06 | `0d2d4b9788945efd50b368ef01cb0f81b2ee834f8c5abd4bd6a0663f8a933328` |
| E-07 | `af61d955ce602516571e1fb7f6acff7a55766d91ed39ad310916a69c5f3b068f` |

**Finding F-03（E-05）：本次测试区间内，枚举范围内的业务源码、测试、现有文档及旧证据内容保持一致。** 没有执行 reset、清理既有成果、提交或迁移。

## 7. 证据限制和复核路径

1. 本次只执行评分 parity 文件，不运行后端全量、前端 type-check/test/build、API、数据库、LLM 或生产链路验收。这是独立证据修复，不是全项目发布结论。
2. 快照删除产生的 `KeyError` 精确证明快照契约缺字段，单独不证明判罚逻辑失效；第二个判罚归零变异以真正的数值断言失败补齐这一点。两个结论分开记账。
3. marker detector 保持原样；本次没有覆盖 detector 的所有可能变异，也未计算完整 mutation score。没有修改测试断言以适配变异。
4. 四阶段共用同一解释器与模块缓存，恢复后通过说明本进程恢复成功，不等同于全新解释器的冷启动验收。使用现有 conftest 及其本地轻量导入设置。
5. 哈希比较不覆盖全部 ignored 文件、文件元数据或仓库外环境，也不是对其他并行任务的隔离快照。关闭字节码和 pytest 缓存写入用于收窄副作用，不将文件哈希结论扩大为全磁盘审计。
6. 文档技能引用的 `C:\Users\XZXyuan\.codex\skills\reverse-skill\tool-index.md` 读取时报路径不存在，已即时告知。项目测试、解释器、执行器均可用，证据来自实际运行而非该索引。未安装或修改技能资源。
7. 旧日志保留历史状态，旧报告未被回写；下游引用评分反向验证时应使用本报告和 E-04/E-05。

**复核路径 P-01：** 根据第 5.1 节运行 E-03 → 在新 E-04/E-05 确认四阶段数量、异常源与数值 → 检查 `descriptor_restored_by_identity=true`、`protected_changes=[]`、`success=true` 和 `driver_exit=0` → 按第 6 节核验本次工件指纹。F-01 由旧日志定位无效证据，F-02 由新的两个独立 mutation 支撑，F-03 由前后文件指纹支撑。

## 8. 交付前复核补记

复核时间：2026-09-07T01:33:37.688926+08:00。E-03/E-04/E-05 的 SHA-256、报告中四阶段计数、逐条分数及 marker count 均再次核验一致。

新增复核日志：`D:\小说写作\xuanqiong-wenshu\logs\reverse-scoring-artifact-20260907-final-review-20260907T013337688926+0800.json`。

测试结束后的再次逐文件检查发现以下路径相对 E-05 的测试结束快照发生变化。本任务未对这些路径发出写入，哈希比较本身不确定其他活动的具体来源；没有回滚或覆盖。

- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentConversation.vue`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.spec.ts`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\features\agent\AgentReasoningCard.vue`
- `D:\小说写作\xuanqiong-wenshu\frontend\src\views\AgentWorkspace.vue`

第 6 节的 3,795 文件一致结论严格限定于 01:29:11—01:29:26 的测试执行区间；不延伸为最终交付时全仓未变。第一次交付前核验以非零 Python 退出码报告这项差异，随后单独复核评分证据通过，并把差异原样记录于本节和新增日志。外部文件变化不影响已保存的评分执行证据，但反映本工作区不是冻结快照。
