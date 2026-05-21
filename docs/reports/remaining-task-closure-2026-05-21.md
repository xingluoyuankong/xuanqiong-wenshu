# 玄穹文枢剩余任务收口记录 2026-05-21

## 本轮目标

本轮聚焦“账本闭环和生成状态可观测性”这条剩余主线：让知识图谱、章节大纲后台任务、定稿后的线索/图谱同步在代码和界面上能说明白“数据来自哪里、发生在哪章、置信度多少、当前状态是什么”。

外部参考只借方法，不复制代码：
- novelWriter：项目树、标签、引用索引的组织方式。
- bibisco / Manuskript：角色、章节、场景工作流对写作项目管理的启发。
- graphify-novel：Story Bible 与知识图谱双层状态的思路。
- autonovel：draft/review 循环中让产物与评审结果可追踪的思路。

## 已完成改动

1. 知识图谱事实元数据
   - `KnowledgeGraphService.get_project_graph()` 现在会为节点输出 `fact_source / fact_source_label / first_chapter / latest_chapter / confidence / lifecycle / relationship_count`。
   - 图谱边输出 `fact_source / fact_source_label / source_chapter / latest_chapter / confidence`。
   - 时间线事件同步成边时写入 `extra.source=timeline_event`、来源章节、最新章节和事件 ID。

2. API 兼容扩展
   - `CharacterNodeResponse` 和 `EventEdgeResponse` 只新增可选字段，不破坏旧前端。
   - 节点列表、边列表和完整图谱接口统一复用增强后的图谱 payload。

3. 章节大纲任务事件
   - `OutlineGenerationJobResponse` 新增 `events`。
   - 章节大纲生成/重写的后台任务现在会记录排队、上下文审计、章节骨架、局部重写、保存、成功、失败、取消等事件。

4. 定稿账本日志
   - 定稿后的 `ledger_graph` runtime event 不再只写“同步完成”，会展示线索新增/更新、图谱节点/边新增、过期节点/关系清理数量。
   - `finalized` 总结会明确指出记忆层、伏笔闭环、线索/图谱同步是否降级。

5. 前端知识图谱页
   - 角色列表和焦点角色详情展示生命周期、首见章节、最新章节、事实来源、关系数和置信度。
   - 关系边展示来源类型、来源章节、最新章节和置信度。
   - 页面文案明确说明：知识图谱用于关系查询，当前事实仍以记忆层/故事账本为准。

## 验证结果

- `python -m pytest backend/app/services/test_knowledge_graph_causal_chain.py backend/app/api/routers/test_outline_generation_job.py backend/app/services/test_blueprint_observability.py -q`：113 passed。
- `python -m compileall backend/app`：通过。
- `python -m pytest backend -q`：252 passed。
- `cd frontend; npm run test:run`：127 passed。
- `cd frontend; npm run build`：通过。

## 浏览器验证

项目本体运行地址：
- backend: `http://127.0.0.1:8013`
- frontend: `http://127.0.0.1:5174`

已验证页面：
- `/` 桌面视口：无 console error、无 request failed、无横向溢出。
- `/workspace` 移动视口：无 console error、无 request failed、无横向溢出。
- `/detail/35cbd8ec-6fdb-47d1-bf6d-437970143d4e` 知识图谱桌面视口：新事实字段可见，无 console error、无 request failed、无横向溢出。
- 同一详情页知识图谱移动视口：先打开侧栏后进入知识图谱，新事实字段可见，无 console error、无 request failed、无横向溢出。
- `/llm-settings` 桌面视口：无 console error、无 request failed、无横向溢出。

API 实跑确认：
- `/api/projects/{project_id}/knowledge-graph` 已返回节点事实来源、首见/最新章节、置信度、生命周期、关系数。
- 同一接口已返回关系边事实来源、来源章节、最新章节和置信度。

## 后续仍建议继续做

- 用 CPA 仅作为 Provider，继续跑 2-3 轮完整生成链：灵感/蓝图/章节大纲/正文/重写/优化/定稿/导出。
- 把本轮新增的图谱事实字段也接入故事账本侧栏，使写作台不必跳到详情页才能看角色生命周期。
- 对旧稿导入和长章 7000-10000 字压力样例继续做真实产物评判，并把问题转为代码修正。
