# 玄穹文枢剩余任务最终收口报告

日期：2026-05-21
分支：`codex/final-continuity-20260520`
基线：`eed7666 feat: close generation runtime ledger loop`

## 本轮结论

剩余收口任务已完成一轮可验证闭环：项目本体后端/前端可运行，章节 8 和章节 9 已完成真实生成、定稿和账本回写；长章压力样例完成；导入、导出、风格中心、管理台日志和核心页面完成验证；发现的真实问题已转成代码修正或记录为明确限制。

本轮没有新建平行小说引擎。继续沿用现有 `PipelineOrchestrator`、`generation_call_service.py`、伏笔/线索/角色/知识图谱和写作台链路。`generation_call_service.py` 仍只作为可靠调用工具箱，不承担中央调度。

## 外部方法参考

只借鉴功能组织方法，不复制外部代码：

- [novelWriter](https://github.com/vkbo/novelWriter)：项目树、章节文档和元数据索引。
- [bibisco](https://github.com/andreafeccomandi/bibisco)：角色、章节、场景、修订、导出工作流。
- [StoryLine](https://storyline.pixero.com/)：setup/payoff 与 Validator 思路。
- [graphify-novel](https://github.com/Anshler/graphify-novel)：Story Bible + 知识图谱双层状态。

## 代码修正

1. Provider 抖动下的候选保留
   - 文件：`backend/app/services/pipeline_orchestrator.py`
   - 问题：稳定重试只请求 1 个候选时，仍按原始 2 个成功候选阈值判断，导致已有合格候选也被判为失败。
   - 修正：新增 `_attempt_required_success_count()`，按本次实际请求候选数夹紧成功阈值；如果后续重试受 Provider 抖动影响失败，保留最佳部分候选进入评审，并写入用户可读 runtime event。

2. 回归测试
   - 文件：`backend/app/services/test_generation_quality_guards.py`
   - 新增：`test_stable_retry_success_threshold_clamps_to_requested_candidate_count`

3. 全局任务横幅收口
   - 文件：`frontend/src/components/GlobalNavBar.vue`
   - 问题：章节已经 finalized/successful 后，非写作页仍显示全局任务横幅，挤占管理台、风格中心和设置页空间。
   - 修正：非写作页只在任务忙碌或需要处理时显示横幅；成功结束的任务不再干扰工具页。

## 真实实跑结果

主测试项目：`35cbd8ec-6fdb-47d1-bf6d-437970143d4e`，标题 `Codex实跑验证-20260520`。

章节 8：
- 生成并定稿成功，选中版本 `335`。
- 正文字数：`4789` 字符，runtime 实际字数指标 `4563`。
- 定稿账本回写：角色状态 6 条，时间线事件 10 条，因果链 6 条。
- 伏笔闭环：回收 2 条，强化 5 条，新增 2 条。
- 线索/图谱：线索新增 2 条，更新 8 条，知识图谱新增关系边 127 条。
- 首次生成暴露 Provider 抖动候选阈值问题，已修代码并复跑通过。

章节 9 长章压力：
- 目标：8000 字，最低 7200 字。
- 生成并定稿成功，选中版本 `336`。
- 正文字符数：`13008`，runtime 实际字数指标 `12362`，处于实验长章 12000-15000 支持范围内。
- 质量指标：场景数 6，场景兑现率 1.0，结构率 1.0，对话改变局势为真，章末压力通过，事件密度和长章密度通过。
- 定稿账本回写：角色状态 8 条，时间线事件 11 条，因果链 6 条，动态角色入池 `灰路送人汉子`。
- 伏笔闭环：回收 1 条，强化 6 条，新增 6 条。
- 线索/图谱：线索新增 6 条，更新 10 条，知识图谱新增角色节点 1 个、关系边 203 条。

优化/重写保护：
- 对章节 8 执行节奏优化，结果从 4789 到 4840 字符。
- 未覆盖原章节，未触发整章推翻；保留结尾锚点和原事件顺序。

导入/导出：
- 旧稿导入项目：`edabbbc0-f70a-4b35-945a-72e758cc339a`
- 导入成功：分出 1 章，角色状态 5 条，时间线事件 1 条，知识图谱节点 5 个、关系边 9 条。
- 导入项目导出预检通过；TXT 导出 200，DOCX 导出 200。
- 主项目导出预检正确阻断：第 5 章 `evaluation_failed`，第 10-12 章缺正文。TXT/DOCX 返回 409 和结构化原因，这是正确行为。

风格中心：
- 小于最低字数的素材正确失败，提示 `参考文本至少需要 500 字`。
- 直接文本素材创建、画像生成、应用、清理均成功。
- 额外用 5848 字 UTF-8 文件验证上传/抽取/删除，服务端能正确保留中文内容；先前 `????` 样本确认为测试脚本编码污染，已删除污染素材。

浏览器/UI 验证：
- 已验证页面：`/workspace`、`/inspiration`、`/novel/:id`、`/detail/:id`、`/novel/:id/read`、`/admin`、`/style-center`、`/settings`、`/llm-settings`。
- 视口：桌面 `1440x900`，移动 `390x844`。
- 结果：无 console error、无失败请求、无横向溢出。
- 横幅修复后复验：`/admin`、`/style-center`、`/settings`、`/llm-settings`、`/novel/:id` 上 finalized 任务横幅不再出现。
- 本地证据文件：`docs/reports/browser-validation-raw-2026-05-21.json`、`docs/reports/browser-validation-global-task-2026-05-21.json`、`docs/reports/final-validation-screenshots-2026-05-21/`。这些原始截图/JSON 按项目 `.gitignore` 规则保留在本地，不纳入提交。

## 多角色评判

作者视角：
- 第 8、9 章能承接已生成的船坞、潮印、黑帆旧坞和角色关系，长章不是片段拼接。
- 需要关注：长章会略超目标，应在后续继续微调“接近目标”而不是只保底达标。

编辑视角：
- 章节 9 的场景组、桌面冲突、外部追压、角色站位和章末压力完整。
- 真实问题已转修正：Provider 抖动导致候选不足时不应直接失败，已保留合格候选并进入评审。

读者视角：
- 开场有明确动作、对话和压力，不再只有空泛设定。
- 运行日志能看到正文片段和账本更新，不必猜后台是否卡住。

连续性审校视角：
- 定稿后角色状态、伏笔、线索、因果链和图谱均有回写事件。
- 动态角色能入池，章节 9 的新增人物没有用完即消失。

系统稳定性视角：
- Provider 慢和候选失败仍会发生，但现在有 retry、稳定模式、部分候选保留和可读事件。
- 导出预检能阻断缺章/失败章，避免生成乱码或半成品文件。

UI 可用性视角：
- 写作页之外的工具页不再被完成任务横幅占位。
- 风格中心、管理台和设置页在桌面/移动视口没有横向溢出。

## 自动化验证

已通过：

```powershell
python -m pytest backend -q
# 259 passed

python -m compileall backend/app
# passed

cd frontend; npm run test:run
# 127 passed

cd frontend; npm run build
# passed
```

前端测试期间出现的 stderr 是用例刻意模拟的失败分支；测试结论为通过。

## 已知限制

- 主测试项目不是完整可导出成书状态，因为第 5 章仍是 `evaluation_failed`，第 10-12 章缺正文；导出阻断是正确结果。导出成功路径已用导入项目验证。
- 章节 9 长章超过 8000 目标较多，但仍在当前实验长章支持范围内；后续可继续优化目标贴合度。
- 部分原始浏览器截图/JSON 证据被 `.gitignore` 忽略，仅保留本地，不推送到远端。
