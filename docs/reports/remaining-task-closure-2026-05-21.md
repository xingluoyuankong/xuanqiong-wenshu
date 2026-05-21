# 玄穹文枢剩余任务收口报告 2026-05-21

## 本轮真实实跑

- 项目本体：`D:\小说写作\xuanqiong-wenshu`
- 前端：`http://127.0.0.1:5174/`
- 后端：`http://127.0.0.1:8013/`
- Provider：CPA `/v1`，只作为模型供应方。
- 实跑项目：`35cbd8ec-6fdb-47d1-bf6d-437970143d4e`，`Codex实跑验证-20260520`
- 实跑章节：第 7 章，目标 2600，最低 2200，候选版本 `333`，定稿正文约 5260 字。

## 实跑发现的问题与代码修正

1. 写前伏笔提醒 Provider 504 重试只出现在程序日志里，用户详细生成日志看不到。
   - 修复：`foreshadowing_tracker_service.py` 接收 `progress_callback`，通过 `generation_call_service.py` 的重试事件把 Provider 抖动写回章节运行态。
   - 接线：`enhanced_writing_flow.py` 与 `pipeline_orchestrator.py` 把写前增强上下文、伏笔章节任务接入运行态事件。

2. 第 7 章定稿同步请求超过客户端 180 秒超时，但后台最终继续完成。
   - 修复：`/chapters/{chapter_number}/finalize` 默认后台执行账本同步，立即返回 queued 结果；显式 `async_finalize: false` 保留同步调试路径。
   - 运行态新增“定稿后台同步排队”，后续后台继续写入记忆层、伏笔、线索/图谱、最终完成事件。

3. 因果链抽取结构化输出被 Provider 拒绝一次，原因是 schema 对象缺少 `additionalProperties: false`。
   - 修复：`CAUSAL_CHAIN_EXTRACTION_SCHEMA` 根对象与数组 item 都改为 strict schema，减少结构化输出被拒后再降级 JSON mode 的浪费。

4. 质量门误报 `mission_hit_count=0`，因为章节导演脚本中的场景角色、outcome、payoff、bridge 没纳入任务锚点。
   - 修复：fallback mission keywords 纳入 `pov / focus_characters / scene.characters / outcome / payoff / bridge / foreshadowing_task`。

5. 移动端浏览器验证发现 `/style-center` 与 `/settings` 横向溢出，设置页有 Naive UI provider 警告。
   - 修复：风格中心响应式网格媒体查询恢复为 1/2 列布局；系统配置表放入局部横向滚动容器；App 根节点补 `NConfigProvider`。

6. 两处乱码文案影响运行日志可读性。
   - 修复：`[版本风格提示]`、Provider 网络错误提示、因果链抽取失败日志均恢复为可读中文。

## 第 7 章定稿账本结果

- 角色状态：写入 7 条。
- 时间线事件：写入 10 条。
- 因果链：写入 6 条。
- 伏笔闭环：回收 1 条，强化 6 条，新增 1 条。
- 线索/图谱：线索新增 1 条、更新 7 条，图谱新增关系边 166 条。
- 最终运行态：`finalized`，详细日志可看到“定稿闭环完成”。

## 多视角评判

- 作者视角：第 7 章从第 6 章证据拆分压力继续推进，没有平铺成静态说明；结尾“回来”的多重呼唤能自然递交下一章。
- 编辑视角：事件密度和行动目标较前面版本更明确，章节中有角色分工、路线转移和目标重心变化。
- 读者视角：黑帆旧坞、半毁航图、外环裂口形成清晰悬念链，章末压力有效。
- 连续性审校视角：角色、伏笔、因果、图谱账本在定稿后有可见闭环，不再只停留在程序日志。
- 系统稳定性视角：Provider 抖动、结构化 schema 拒绝、长定稿请求超时都被转成可解释运行态或默认后台任务。
- UI 可用性视角：写作台、详情、管理台、风格中心、设置页桌面/移动端无横向溢出，运行日志可显示章节定稿闭环。

## 验证结果

- `python -m pytest backend -q`：258 passed。
- `python -m compileall backend/app`：通过。
- `cd frontend; npm run test:run`：127 passed。
- `cd frontend; npm run build`：通过。
- 浏览器验证：`/workspace`、`/novel/:id`、`/detail/:id`、`/admin`、`/style-center`、`/settings` 在桌面 1440x900 和移动 390x844 下均无 console error、无 500、无横向溢出。
