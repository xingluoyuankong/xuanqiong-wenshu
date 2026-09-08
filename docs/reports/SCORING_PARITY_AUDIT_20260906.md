# 评分能力对等性只读审查 — 2026-09-06

> 结论：当前分支已内联实现主要评分能力，并存在多项超出 local main 的工程增强；未抽 mixin 不等于功能未移植。两边仍有真实的匹配、残留识别/计分和输出契约差异。此报告是静态源码/测试审查，不是运行验收或真实质量收益证明。

## 1. 基线、边界与证据口径

- 工作区：`D:\小说写作\xuanqiong-wenshu`。
- 当前分支：`codex/bohrium-integration-20260831`；HEAD：`dc3788e812d02fdd5112ed9b74dc1da2ac7da7eb`。
- 对比基线仅为本机 `main`：`089aba445fc67dc1d4e0553c4767a66fe7493040`；未 fetch，不代表远端最新状态。
- 当前评分文件与所审13个测试/源码文件均逐一核对与 HEAD 一致（文本按 UTF-8 / LF 归一化比较）；其他代理的改动与全量运行产物不纳入本审查结论。
- 仅使用 git show/grep/ls-tree、文本读取、Python 标准库 AST 与哈希。Python 设置 PYTHONIOENCODING=utf-8、stdout UTF-8，并使用 -B；所有 exec 均 login:false。未导入应用模块，未调用任何评分函数，未启动 pytest、provider、应用服务或测试收集。
- 唯一写入文件为本报告；未编辑源码/测试，未执行合并、cherry-pick、切分支或改写索引。没有开展主代理负责的7项真实质量收益/人工标签缺口，也没有开展 UI005/006。
- “AST一致”忽略行号与注释，但默认保留 docstring、装饰器、签名；它只证明方法文本结构一致，不证明被调方法、常量与完整行为一致。下文“可达/未接线”是静态常规调用证据，不外推反射或仓库外调用。

### 证据定位缩写

- **C**：当前 `D:\小说写作\xuanqiong-wenshu\backend\app\services\pipeline_orchestrator.py`；行号属于当前工作区/HEAD。
- **M**：仅存在于 git 对象 `089aba445fc67dc1d4e0553c4767a66fe7493040:backend/app/services/story_quality_scoring.py` 的 mixin；对应工作区路径 `D:\小说写作\xuanqiong-wenshu\backend\app\services\story_quality_scoring.py` 当前不存在，切勿作为当前源码引用。
- **MP**：git 对象 `089aba445fc67dc1d4e0553c4767a66fe7493040:backend/app/services/pipeline_orchestrator.py`；main 的实际编排类，行号属于 main。
- **TG**：当前 `D:\小说写作\xuanqiong-wenshu/backend/app/services/test_generation_quality_guards.py`；**MTG** 为同一路径在上述 main 对象中的测试。

## 2. 先纠正接线与同名误判

1. M 共 **28个方法**，C 有 **22个同名方法**，缺6个名字；22个中4个 AST 完全一致：对白预期、场景兑现、故事单元切分、字数统计。重复检测仅增加 docstring，去掉 docstring 后也是一致实现。
2. MP:50 导入 mixin，MP:109 继承；但 MP:473–563、566–608、6092–6093 分别覆盖 `_build_quality_issue_summary`、`_attach_quality_gate_status_to_guard`、`_count_words`。mixin 的同名实现不等于 main 实际行为；QUALITY_ISSUE_LABELS / HINTS 也在 main 类中覆盖。
3. M:207–251 的显式 passed is True / 非 dict 防护是被覆盖实现。MP:572 与 C:604 的实际附加函数仍使用 `bool(structural_quality_gate.get("passed", True))`。这是共有容错边界，不应写成 main 已修复、当前漏移植。M 中处理零场景比率和 0.35/0.25 阈值的摘要实现同样被覆盖。
4. git grep 整个 main backend：`_apply_deterministic_cleanup` 与 `_sanitize_markdown_presentation` 仅见定义（后一项另有注释）；重复清理两个 helper 在 cleanup 子图内调用，没有生成入口接入。`_score_fallback_candidate` 只有定义与 MTG:1679/1694 两次测试调用。`_coerce_float` 只供被覆盖摘要使用，QUALITY_THRESHOLD_CONFIGS 只见定义。
5. 真正在两边使用的是 `_score_story_quality_candidate` → `_fallback_select_best_version`：MP:5439–5444 与 C:8363–8368 都传 target/min。当前没有旧简化评分器，不影响这条 canonical 链。
6. 当前 cleanup 反而有生产接线：C:4154–4165（initial）、4524–4559（final、门禁重算、最终评分与 snapshot）。main 的同名重复段清理与当前 Markdown 清理不是可直接交换的实现。

### 方法级差异全表

| 方法 | M 行号 | C 行号 | 静态结论 |
|---|---:|---:|---|
| `_build_quality_issue_summary` | 94–204 | 503–595 | mixin 实现被 main 类覆盖（MP:473–563）；实际比较应以覆盖方法为准。当前 repetition 码为 repeated_paragraph_flood，增加 continuity 警告并采用三态失败判断；main 实际摘要额外收录 artifact 与字数问题。mixin 中 0.35/0.25 场景阈值及零值转换修补不是 main 生产摘要事实。 |
| `_attach_quality_gate_status_to_guard` | 207–251 | 598–657 | mixin 实现被 MP:566–608 覆盖。mixin 的 passed is True / 非 dict 处理在 main 常规实例上不生效；main 实际与当前都默认缺失 passed 为 True。当前强制物化 snapshot，增加 exemptions 与自检来源/分数/问题数。 |
| `_collect_fallback_mission_keywords` | 254–322 | 6838–6904 | 同用途、双向分歧。main 优先人物/POV，纳入 character_focus、must_happen、pressure_shift，上限24；当前上限48并补过滤泛词/助词的中文二字锚点，缺少这些键的直接收集及独立人物优先桶。后两场景字段已有其他接线，详见 §3。 |
| `_chapter_mission_expects_dialogue` | 325–334 | 6907–6916 | AST 完全一致；对白任务预期识别已存在。 |
| `_expand_synonyms` | 419–435 | 无同名方法 | 当前无同名方法及同义词表；main 经 _score_text_hits 实际可达。当前中文短锚点不是同义词替代。 |
| `_extract_quality_tokens` | 438–480 | 6919–6961 | 分词/候选片段算法保留；main classmethod + cls 递归，当前 staticmethod + PipelineOrchestrator 硬绑定递归。当前也有中文3/4/5字子串，非仅整句匹配。 |
| `_fuzzy_match_token` | 483–496 | 无同名方法 | 当前无同名方法；main 经 _score_text_hits 可达，采用三字滑窗命中数 >= max(1,len(token)//3)，不要求顺序或完整语义一致。 |
| `_score_text_hits` | 499–526 | 6964–6967 | main 依次精确、同义词、fuzzy，输出 ~同义词 / ~fuzzy 证据；当前对提取后的 token 只做子串命中。此差异向场景兑现和末尾任务钩子传播。 |
| `_evaluate_scene_fulfillment` | 529–615 | 6970–7056 | 方法 AST 完全一致，含10个字段、4组结构、最多8场；但所调用 _score_text_hits 不同，所以整条行为链并非等价。两边均支持 must_happen / pressure_shift。 |
| `_story_units` | 627–638 | 7100–7111 | AST 完全一致，故事单元切分已存在。 |
| `_unit_has_progression` | 641–646 | 7114–7121 | main 引号本身即算推进；当前带引号仍需推进词或对白状态词，并剔除弱转折词独立充当推进证据。 |
| `_evaluate_event_density` | 649–716 | 7192–7291 | 当前增加 <800 未评估三态、<7000 长章维度不适用、双命中/比例窗口与尾窗合并、最长无推进占比；分档阈值也不同。main 短样本与非长章直接给 True；详见 §4。 |
| `_count_dialogue_state_change_markers` | 719–743 | 7294–7311 | 两边均按唯一词表去重计数。main 有较多自然动作/口语压力词（如摊牌、松口、话锋一转）；当前另有拿到/名单/医院/消息等词。不可描述为当前独有去重或每项都更严格。 |
| `_evaluate_dialogue_changes_state` | 746–768 | 7321–7358 | 两边均支持无要求且无对白为 None。main 可在引号>=8、状态词>=1时通过；当前声明要求固定引号>=2且状态词>=2，未声明但有对白按1状态词判断，并增加 applicable/expectation 字段。 |
| `_evaluate_ending_pressure` | 771–892 | 7375–7451 | main 420字窗口、题材词根、自然期限模式、加权压力分；当前260字窗口+原文末段、通用语义/弱信号分离、完整收束词、末段泄气判定及新观测字段。实际有召回能力差异，但不是无条件回退 main。 |
| `_estimate_static_description_runs` | 895–909 | 7533–7567 | main 只凭通用动作字词判静态；当前通过 _paragraph_has_character_action 要求人物主体，并向检测传入任务书焦点人名。由 staticmethod 变 classmethod，多 character_names 关键字参数。 |
| `_collect_focus_character_names` | 912–949 | 7481–7530 | 四来源合并、过滤占位名、2–12字、前8名骨架已移植。当前 classmethod 引用扩展占位符常量，并将解析结果用于动作/配比检测。 |
| `_evaluate_repetition_risk` | 952–982 | 7589–7634 | 删除方法 docstring 后 AST 完全一致；>=30字段、>=800字启用、次数/占比判据保留。当前同时接分数 -420 与硬 blocker，非缺少重复检测。 |
| `_remove_exact_repeated_paragraphs` | 985–1005 | 无同名方法 | 当前无此删除 helper；main 仅由未接生产的重复段 cleanup 调用，属于实现储备而非主线在用能力。 |
| `_remove_exact_repeated_paragraphs_with_floor` | 1008–1068 | 无同名方法 | 当前无此 helper；main cleanup 子图内使用，保最低字数边界。preferred_floor 只计算/返回，实际删除停止线是 hard_floor。 |
| `_apply_deterministic_cleanup` | 1071–1156 | 1754–1779 | 同名不同义：main 清除重复段、返回 dict 或 None，生产未见调用；当前清 Markdown 外壳、返回 dict，在生成链 initial/final 两处实际调用并保 diff/最低字数/重算。直接替换会破坏当前契约。 |
| `_score_fallback_candidate` | 1159–1220 | 无同名方法 | 当前无此旧简化评分器；main 仅2个测试直接调用，生产 fallback 用 canonical scorer。缺少该名字不是候选评分未移植；其1.25超长线也不是 canonical 的2.0/1.6。 |
| `_sanitize_markdown_presentation` | 1223–1267 | 1733–1751 | main 返回 str、仅剥表现标题与强调、保留结构指令行，且未见生产调用；当前返回 (str,list)、去所有 Markdown 标题/本章完/**，由已接线 cleanup 调用。保结构残留证据的差异见 §3。 |
| `_detect_chapter_artifact_markers` | 1270–1324 | 7637–7671 | 两边均存在且接 canonical scorer。main 覆盖 JSON任务字段、蓝图链接及多种行内指令；当前更泛化约N字和结构粗体，但漏掉一批 main 模式。 |
| `_score_story_quality_candidate` | 1327–1504 | 7826–8181 | canonical 综合评分已接线。字数0.92、2.0/1.6、三类扣分、焦点缺席-240、重复-420均存在；当前增加三态、配比、承接、末段压力与拆分观测，但缺 main 的 artifact -480、mission_keyword_count 和 preferred_floor 输出别名。 |
| `_fallback_select_best_version` | 1507–1541 | 8186–8227 | 两边生产调用均传 target/min。当前删除固定>=1000字的同分优先项，增加 heuristic_rank；默认0与main None在无配置时均中性，排序仍由 canonical 分数主导。 |
| `_coerce_float` | 1545–1551 | 无同名方法 | 当前无此 helper；main 只被已覆盖的 mixin 摘要调用。属于潜在容错储备，不是当前评分失去数值转换的直接证据。 |
| `_count_words` | 1555–1556 | 9037–9038 | AST 完全一致；main 类也保留同名覆盖。按去空白字符数计数，不是英文分词数。 |

## 3. 主线真实独有项、局部缺口与未接线储备

### 3.1 已接线的差异：确有缺口，但逐项限定影响

**E1 → F1：残留识别覆盖与候选分数缺口。** M:1270–1324 检测任务 JSON（chapter_purpose/scene_list/continuity_anchor 等）、任务/蓝图 Markdown 链接、若干行内指令短语；C:7637–7671 无这些分支。例如独立行 `{"chapter_purpose":"调查失踪"}` 或 `[蓝图](memo)`，静态模式检查显示 main 有对应规则，当前规则列表无匹配分支。此处是源码推导样例，未执行评分或测试。
- M:1403 对识别出的 artifact 扣480；C:7932–8000 的总分与 quality_penalty 都没有 artifact 对应项，虽然 C:8075 / 8180 仍输出检测结果。因此“存在检测字段”不等于“候选排序已接扣分”。
- 当前 C:833–838 仍将已识别残留设为 blocker，故不是残留门禁整体缺失。实际缺口是漏识别类别，以及识别后未直接进入这项候选扣分。候选被抬高是局部评分方向推论，非已观测线上排序事件。
- 当前 C:1733–1751 无条件删 Markdown 标题行；如 `## 场景1：调查` 可在 initial cleanup 中被去掉，随后门禁看到的是清理后文本。main sanitizer 会保留 structural_line 证据，但该 sanitizer 在 main 没有生成接线。应区分“当前清洗会移除证据”与“main 生产已经做了更好的清洗”。
- 当前也有 main 未同等泛化的 `约\s*\d+\s*字` 与结构粗体检测。补齐时应合并覆盖，而非整段回退检测器。

**E2 → F2：场景/尾部任务命中的语义扩展差异。** M:499–526 经同义词与fuzzy识别进入场景兑现（M:574）和末尾任务命中；当前 C:6964–6967 只有提取 token 后的精确子串匹配。词条 `质问` 对正文 `逼问`：main 表与路径存在直接同义词桥接，当前没有等价同义词步骤。
- 当前 C:6919–6961 也提取3/4/5字片段，且 C:6823–6904 的任务候选支路另外补二字锚点；因此“当前全是整句硬匹配”是错误描述。两个 token 体系用途不同，二字任务命中未自动流入 `_score_text_hits`。
- main 的fuzzy只看三字窗出现数；它不是经过语义验证的相似度，容易让不完整片段与泛化表达加分。这里只认定能力/行为缺口，不认定打开fuzzy必然提升真实质量。
- main 的自然动作/口语词与期限模式也真实进入对白/尾部判定，例如 M:719–743、771–892；当前有不同词表、通用压力及末段约束。这是双向召回/误报取舍，不宜把题材专词和宽松条件直接搬回。

**E3 → F3：任务字段是局部遗漏，而非整条能力缺失。** M:254–322 的通用任务候选词收集直接读 character_focus / must_happen / pressure_shift，并让人物桶先占24项配额；C:6838–6904 未直读这些键，候选按原短语顺序排到48项。
- 但 C:6986–6997 的场景兑现已读 must_happen / pressure_shift；C:7411 的末尾 hook 也读 pressure_shift；C:7525 的焦点人名解析已读 character_focus。
- 更重要的是 C:1665/1668 的任务归一化分别将缺失 goal/outcome 回填为 must_happen/pressure_shift，C:5530 的生成任务路径调用这项归一化。因此遗漏主要影响直接输入原始任务、已有 goal/outcome 且另有补充信息的任务，以及人物优先配额；不应报告为生产完全不支持这三字段。

**E4 → F4：输出可观测性确有小缺口。** M:1422/1472 的 snapshot/顶层含 `mission_keyword_count`；C:8002–8181 的两层输出均未保留这一分母，只有命中数/命中例子。main 也输出 `preferred_floor` 别名，当前保留 `preferred_word_floor` 而未保留该别名；已审当前消费没有据此确认故障。main 的 ending_pressure_score / narrative_pressure_hits / deadline_pattern_hits 也被当前另一套末段观测字段替代，不应当作纯漏字段机械回填。

### 3.2 存在于 main 代码但未形成生产增量的部分

- 精确重复段自动删除/保底删除：M:985–1156；当前仅检测、扣分、拦截，并进行另一类 Markdown 清洗。自动去重实现确实未移植，但 main 生成链也没有调用它，故不属于 main 已上线而当前倒退。
- 该删除 helper 的 preferred_floor 只是返回的观测值；真正停止条件是 candidate_words < hard_floor（M:1052）。禁止把它描述为同时强制92%目标下限。
- main sanitizer 的保留结构指令行/剥斜体实现、被覆盖的摘要容错与 gate 显式通过、旧简化 scorer / QUALITY_THRESHOLD_CONFIGS，均按未接线/覆盖/测试接口分类，而非生产欠账。

## 4. 当前分支更完整的实现与应保留的取舍

以下“更完整/更强”限定于可辨别坏样本、接口一致性和可观测性；源码注释中的历史语料数量、分位数和误杀率本次未复核，不作为实测收益。

| 当前能力 | 源码证据 | 与 main 的实质区别 / 限定 |
|---|---|---|
| 推进防刷分 | C:7059–7184 | 引号或弱转折词不再独立算推进；窗口同时要求至少2个推进单元和5%比例，短尾窗<40%合并。main 用窗口内任意推进即命中。 |
| 密度三态与长度公平性 | C:7192–7291、7951–7960 | <800未评估，<7000不评价长章密度；None既不加分也不扣分；最长静态单元按全章占比而非固定句数。分档阈值同时变化，不宣称每个维度都更严。 |
| 白对话形式的约束及适用性 | C:7321–7358、7941–7945 | 声明对白预期仍需>=2状态词，不采用main的密集引号+1词放宽；未声明且无对白两边均None，当前增加applicable/declared字段。 |
| 末段压力识别 | C:7375–7451 | 通用语义与弱标点分离、最后非空段单独检测、移除“一切都”中性前缀作硬否决。压力在尾窗却末段泄气有单独观测与判据；main 无末段层。 |
| 静态动作主体与焦点名传播 | C:7481–7586、7880–7907 | 任务书人名可证明动作主体，环境里的“风吹/景物移动”等不因泛化动作字自动算行动；保持重复检测原判据。静态分支第二条采用>=3连段，main为>=2。 |
| 中文任务短锚点 | C:6811–6904、7796–7823 | 过滤助词与泛词后的二字内容锚点，任务词上限48；承接匹配允许同一锚点至少两个内容词命中。不是完整语义模型。 |
| 新增观测与弱排序维度 | C:7674–7823、7977–8026 | 新增反转、对白/动作/描写配比、说话人分布、场景切换、任务书诊断、开头承接。配比及承接缺失进入扣分，其他若干项只观测；不把每个新增字段都说成排序能力。 |
| 总分拆分与末尾权重 | C:7946、7977–8006 | 平结尾扣460（main120）；拆分 eligibility<=280、quality_positive_score、quality_penalty并持久化总分。eligibility是从现有总分反算的分解，不是新增独立封顶重构；mission_hits等原正分仍在。 |
| fallback排序/名次 | C:8186–8227、8363–8368 | active target/min已经传入；删除固定1000字同分项并输出heuristic_rank。main也传target/min，并非当前独有接线。 |
| 清洗与终态一致性 | C:4154–4165、4524–4559 | 初次/最终清洗diff、最低字数回退；最终清洗后重算门禁和评分。main同名cleanup无生成调用。 |
| 观测快照与门禁说明 | C:598–657、8002–8100 | 总分和配比/反转/说话人/场景切换顶层字段，legacy guard也物化snapshot，保留exemptions及自检证据。保留警告与blocker区分；不改变原门禁默认语义。 |

额外限定：当前 `_evaluate_mission_quality` 支持首章不要求继承，但 canonical scorer 在 C:7867 固定传 chapter_number=2；本审查只确认新增诊断实现存在，不据此宣称已经章号精确接线。此项仅记录边界，不扩展为主代理的质量收益工作。

## 5. 测试源码对比与证据强度

- 对同一个 test_generation_quality_guards.py 做 AST 静态计数：main **67个**测试方法，当前 **202个**；类名+方法名相同 **55个**，其中 **50个AST完全一致**。计数不是pytest收集数，参数化展开未计入，也不是整个仓库测试规模或通过数。
- main 中少数无同名测试：旧 `_score_fallback_candidate` 两例属于旧接口；active字数传递、未要求对白None等在当前由更细的测试类覆盖对应契约（下表）。未发现同名，不代表行为无回归。其余并发/provider等无同名测试不在本评分任务范围内。
- 当前测试包含合成正反样本、monkeypatch破坏和源码接线断言；三种证据强度不同。源码字符串断言只能保护对应接线文字，不等同实际行为或真实小说质量验收。

| 保护域 | 已有测试定位 | 从断言确认的契约 |
|---|---|---|
| 推进/尾窗 | TG:2749–2894、3110–3268；T2 | 防纯寒暄、弱标点、全句推进、全窗口通过；尾片合并及2命中下限。 |
| 静态与重复 | TG:3271–3457；T3、T4 | 四条静态风险分支、重复次数/比例、-420与硬门；环境动作反例、自定义焦点人名传播破坏。 |
| 末段压力 | TG:3460–3557；T2 | 末段非固定尾窗、泄气诊断字段、中性收束前缀与语义/弱信号边界。 |
| 焦点与字数 | TG:3588–4013 | 人名过滤/警告、三类字数判罚、阈值边界、active配置向门/重试/fallback传递、无配置中性。 |
| 白对话三态 | TG:4062–4416 | None既不奖也不罚，真实失败仍判，重复词表不二次计数，门/修复/重试对齐。 |
| 密度三态 | TG:4424–4684 | 800/7000边界、空比率与计数区分，None不扣分，skip reason进入snapshot，门/修复/重试对齐。 |
| 中文词命中 | T5:16–71 | 保留账簿/照片/脚步等锚点，过滤泛词；关闭二字抽取会降低命中与分数。 |
| 清洗与终态 | T6:4–99、T7:30–87；TG:2563–2570 | 清洗diff与最低字数、initial/final摘要、final cleanup后门禁重算；包含源码顺序/删除反向断言。 |
| 分数与字段 | T8、T9、T10 | eligibility<=280，合成好坏样本差>=600，多维度扣分、承接/长章项入账，snapshot总分及新观测顶层镜像。 |
| 门禁等级 | T11:16–154 | 场景/对白等不确定维度warning，高置信重复blocker，自检豁免及修复说明；不将观测字段全变硬门。 |

### 测试文件证据索引（全部为当前文件）

- **T2**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_quality_early_batches_sabotage.py`。
- **T3**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_static_repetition_sabotage.py`。
- **T4**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_static_action_focus_name_regression.py`。
- **T5**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_chinese_mission_keyword_matching.py`。
- **T6**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_deterministic_cleanup.py`。
- **T7**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_deterministic_cleanup_integration.py`。
- **T8**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_quality_score_eligibility.py`。
- **T9**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_quality_score_sabotage.py`。
- **T10**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_quality_enhancements.py`。
- **T11**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_quality_gate_severity.py`。
- **T12**：`D:\小说写作\xuanqiong-wenshu\backend\app\services\test_quality_observability.py`。

在本次限定的评分测试源码检索中，未见专门直接验证 `_score_text_hits` 同义词/fuzzy层、上述 JSON/蓝图链接残留类型或 artifact -480 的当前测试。已有“修复引入新artifact应拒收”的门禁测试与清洗测试，并未自动覆盖这些分支。未执行任何既有测试或反向测试。

## 6. 下一优化点（仅3项，均待全量结束后另行实施）

### O1：补齐残留“识别 → 候选分数 → 门禁/摘要”的一致性

- 依据：E1/F1；main detector覆盖与-480确在canonical链，当前只完整保有已识别类别的blocker。
- 做法边界：保留当前约N字/结构粗体覆盖，补入经确认的JSON/任务链接/指令类别；先明确装饰标题与结构指令行的清洗边界。识别结果、分数与quality_penalty镜像、问题码应一致，而非仅补字段或仅改报告。
- 待新增回归：同正文插入任务JSON/蓝图链接/结构标题后应出现预期识别、排序差与门禁结果；装饰标题、正常强调和普通叙述作反例。破坏检测分支或扣分后，相应断言应失败。纯抽取阶段不要混入这项行为变化。

### O2：按证据补任务文本匹配，避免整表导入fuzzy

- 依据：E2/F2、E3/F3；同义词路径真实缺失，原始任务字段与人物配额只在通用候选收集支路局部遗漏，现有归一化/场景/末尾路径已经覆盖部分信息。
- 做法边界：保留当前中文锚点过滤及48项上限；优先验证短明确动词同义替换与人物优先配额，区分 exact/synonym 证据。原始任务与归一化任务成对覆盖；不要把宽泛三字窗相交等同有效场景兑现。
- 待新增回归：质问/逼问的正例、泛化词堆砌和局部相同片段反例、只有character_focus的原始任务、同时含goal/must_happen或outcome/pressure_shift的补充信息、词池饱和的人物保留。去掉真实同义桥接或错误放宽fuzzy时，对应正/反断言应失败。

### O3：补任务命中分母的稳定观测契约

- 依据：E4/F4；main两层输出含mission_keyword_count，当前只见命中数，重建候选评分原因少了分母。
- 做法边界：优先在guard与snapshot同源写入mission_keyword_count，保持现有得分/门禁不变；preferred_floor别名只有确认消费者需要时才保留，不把名称差异虚构成故障。不复活已经换算法的旧ending_pressure_score等字段。
- 待新增回归：空任务、去重、48项截断后分母、顶层/snapshot相等，补观测前后score与gate完全一致；删除任一镜像字段后回归应失败。该项是诊断完整性，不宣称真实质量提升。

自动重复段删除、被覆盖的main容错、主代理负责的质量收益/人工标签工作均不追加为第四优化点。

## 7. 安全抽取边界：只搬当前行为，暂不实施

### 7.1 建议的最小依赖闭包

- 从**当前内联实现**抽取，不直接使用main mixin覆盖当前类。评分纯逻辑可搬；数据库、provider、状态机、服务调用、门禁阻断/修复/持久化留在编排层。抽取不是一次顺带调阈值、补匹配或换清洗算法的机会。
- AST依赖闭包：22个同名方法之外，还要考虑当前11个被调helper；否则类抽出后会丢新增维度。如下：

| 当前新增依赖 | C 行号 |
|---|---:|
| `_extract_chinese_mission_terms` | 6823–6835 |
| `_window_has_state_change` | 7136–7146 |
| `_split_progression_windows` | 7149–7156 |
| `_event_density_floors` | 7159–7184 |
| `_paragraph_has_character_action` | 7570–7586 |
| `_evaluate_reversal_quality` | 7674–7683 |
| `_evaluate_content_balance` | 7686–7732 |
| `_evaluate_mission_quality` | 7735–7770 |
| `_evaluate_dialogue_speaker_distribution` | 7773–7780 |
| `_evaluate_scene_transition_clarity` | 7783–7793 |
| `_evaluate_continuity_inherit` | 7796–7823 |

- 若选择不把 `_attach_quality_gate_status_to_guard` / cleanup 一起抽出，可留编排包装；但明确唯一实现来源，避免再次出现main的“继承但本类覆盖”的事实歧义。`_build_structural_quality_gate`、`_evaluate_structural_quality_gate_for_content`、首稿重试、结构修复与generate_chapter不纳入纯评分mixin。
- 必须随迁或显式注入的常量：QUALITY_ISSUE_LABELS/HINTS、MISSION_KEYWORD_GENERIC_TERMS/PARTICLES、STORY_PROGRESSION_MARKERS、DIALOGUE_QUOTE_MARKS、ENDING_SEMANTIC_HOOK_MARKERS/WEAK_HOOK_MARKERS/CLOSURE_MARKERS、ENDING_CORE_FLAT_CHARS/WEAK_ONLY_LIMIT、EVENT_DENSITY_MIN_SAMPLE_CHARS、UNDECLARED_DIALOGUE_STATE_MARKER_FLOOR、WINDOW_PROGRESSION_MIN_HITS/RATIO_FLOOR/TAIL_MERGE_RATIO、FOCUS_CHARACTER_PLACEHOLDERS、STATIC_ACTION_MARKERS。
- 当前4个方法硬绑定 PipelineOrchestrator：`_collect_fallback_mission_keywords`、`_extract_quality_tokens`、`_extract_chinese_mission_terms`、`_evaluate_continuity_inherit`。抽取时处理为明确的cls/helper依赖，避免新文件反向导入编排类形成循环；装饰器变化与monkeypatch分派语义要单独校核。
- 纯评分闭包所需标准库/类型包括math、re、deepcopy、Any/Dict/List/Optional/Sequence/Tuple；以抽取后的AST自由名集合核验，勿携带LLM/ORM/asyncio运行副作用。

### 7.2 回归需保护项（此处只列清单，不执行）

1. **调用契约**：PipelineOrchestrator原方法调用入口、classmethod/staticmethod绑定、可选raw_text/character_names、fallback默认0、字数参数一路传递；保留monkeypatch对子方法与常量的可拦截性。
2. **分数契约**：去空白字符计数，0.92 preferred、target<=2500时2.0否则1.6的上限及2500/2501边界；-620/-520/-180、重复-420、焦点-240、当前章末-460、承接-280、配比扣分、总分分解和eligibility<=280保持当前值。当前artifact尚无-480，纯抽取阶段也保持现状；O1另行变更。
3. **三态契约**：None/False/True逐层不被bool压平；<800短样本和<7000长章适用性，skip reason与比率None保留；门/重试/修复按当前语义消费，未要求对白且无对白既不奖也不罚。
4. **防刷分及文本契约**：引号、弱转折、弱标点单独不充当强证据；末段raw_text必须继续传入，窗口双命中与短尾合并、人名动作主体、精确重复阈值及静态四分支不回退。
5. **快照与排序契约**：guard总分=snapshot总分；新观测字段、quality_rule_warnings、exemptions、自检来源/问题数、heuristic_rank、稳定同分顺序与空候选返回继续保留。T8/T9/T10与TG相关断言是保护材料而非通过证明。
6. **清洗与副作用边界**：保持 `(cleaned, metadata)` 与 sanitizer `(str,list)`，最低字数回退、initial/final摘要、最终正文重算gate/score后再持久化；主线返回str或None的版本不混入。保留T6/T7的真实函数断言与接线顺序断言。
7. **反向验证安排**：全量结束并由主代理安排修改后，以现有monkeypatch/源码接线反向测试为基础，逐一验证破坏末段参数传递、三态、目标字数传参、人名传递、窗口门、重复检测、快照字段会被检测。当前禁写/禁测窗口内未实施破坏、运行或测试编辑。

## 8. 可复核命令与审查指纹

以下仅列读取/解析方法，报告生成时已使用同类只读命令；没有执行checkout、merge、cherry-pick或测试。

```powershell
git -C "D:\小说写作\xuanqiong-wenshu" rev-parse HEAD main
git -C "D:\小说写作\xuanqiong-wenshu" show 089aba445fc67dc1d4e0553c4767a66fe7493040:backend/app/services/story_quality_scoring.py
git -C "D:\小说写作\xuanqiong-wenshu" show 089aba445fc67dc1d4e0553c4767a66fe7493040:backend/app/services/pipeline_orchestrator.py
git -C "D:\小说写作\xuanqiong-wenshu" grep -n -e _apply_deterministic_cleanup -e _sanitize_markdown_presentation -e _score_fallback_candidate -e _coerce_float 089aba445fc67dc1d4e0553c4767a66fe7493040 -- backend
$env:PYTHONIOENCODING = "utf-8"
# Python解析入口：& "D:\小说写作\xuanqiong-wenshu/backend/.venv/Scripts/python.exe" -B -
# ast.parse 仅解析 git show / read_text 得到的字符串；不 import app、不 exec/compile 应用节点。
```

### 已审文件 SHA-256（当前磁盘字节；不作为全仓冻结证明）

| 文件（见证据索引） | SHA-256 |
|---|---|
| C | `ddaa2ef4a8a5be4985ad8f64e607c128924c0eb882799bfd68612d17037ef39a` |
| TG | `37db11d165a909592b51eae1c0f80e462ac96aa8b17f1fce0870688d3d751988` |
| T2 | `ac8af2c44229a8c1519fe60ef009d8bf4ba2bae9504edc961e6aff1b8c9689a7` |
| T3 | `a60c48b07608760e9397b9a2c199011e5573ae2ddb8f03216504bf866f7fc763` |
| T4 | `742c91c3de6cdaa260b340137518cd2331fa6a3cdaab316bee6189d431052d2e` |
| T5 | `a9f953aa75aaca0954a2cd14812b409dcac9cc9306809b611e04e6523f1c1114` |
| T6 | `e61bd1acf67af6cf9ec150ec9879f95cae21c749524b408a3d24511e9acb6f41` |
| T7 | `959a7561678d1f9cfe7793b13fa5195a619ae543cb9e5ce5a3c8725ca264e63f` |
| T8 | `4feb247d8094f7eb5c3a803cbf87d5f85f849971b640171c1f3bf9f770d1434b` |
| T9 | `60c5f98dc803041327c2a3b1a41f489f452be093451c4413d65fea2a4cd7566d` |
| T10 | `e985a9965c2c0df5ddb65aa77e372d7627698112536bffae7555e1fe54439811` |
| T11 | `6a911634a685553fa318027c4b153074e8808952a288fec2c2025b72f3311733` |
| T12 | `989247ce2769da213b23029e18982a8dd3dc3f2bf4a1842c2ed64c497130406b` |

本报告将实现存在、生产静态接线、测试断言、运行验收和真实质量收益分开记账；后两项没有在本次审查中发生。
