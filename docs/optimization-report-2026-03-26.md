# 玄穹文枢系统级优化报告（2026-03-26）

## 1. 结论先行

本次“越优化越失败”的核心原因不是单点，而是**稳定性链路断裂**：

1. 上游 LLM 流式连接不稳定（`httpx.ReadError` / `APIConnectionError`）在关键路径未完整兜底。
2. 章节多版本并发生成时，任一子任务失败会拖垮整次生成。
3. 前端对 500/503 的错误反馈不友好，用户只能看到“请求失败，状态码: xxx”。
4. 历史 SQLite 结构与 ORM 自增策略存在兼容性风险（`story_time_trackers.id`）。

本轮已完成热修，目标是先把“经常直接炸 500”压下去，再进入结构性优化。

## 2. 已完成热修（本轮已落地）

### 2.1 后端流式网络异常兜底

- 文件：`backend/app/services/llm_service.py`
- 修复点：
  - 补充捕获 `httpx.ReadError`、`httpx.ConnectError`（此前会穿透为 500）。
  - 对瞬时网络错误增加同模型一次短退避重试（0.8s）。
  - 统一映射为可回退处理的 `HTTPException(503)`，不再“裸异常打爆”。

### 2.2 多版本并发生成容错

- 文件：`backend/app/services/pipeline_orchestrator.py`
- 修复点：
  - `asyncio.gather(..., return_exceptions=True)` 收集子任务异常。
  - 保留成功版本，不因单个版本失败导致整章失败。
  - 若全部失败，明确写入 `chapter.status = "generation_failed"` 并抛出可读错误。

### 2.3 评审链路回归修复与异常透传

- 文件：`backend/app/api/routers/writer.py`
- 修复点：
  - 修复误插代码导致的生成链路回归。
  - 评审失败分支使用预缓存 `version_id`，避免回滚后 ORM 访问触发二次异常。
  - 不再把下游 `HTTPException` 一律包装成 500（保留 503 等真实状态）。

### 2.4 SQLite 兼容修复（时间追踪表）

- 文件：
  - `backend/app/models/memory_layer.py`
  - `backend/app/services/memory_layer_service.py`
- 修复点：
  - 兼容 SQLite 自增行为差异。
  - 为历史表结构增加手动分配 `id` 兜底，避免 `NOT NULL constraint failed: story_time_trackers.id`。

### 2.5 前端错误可读性增强

- 文件：
  - `frontend/src/api/novel.ts`
  - `frontend/src/api/admin.ts`
- 修复点：
  - 网络失败提示改为可理解文案（非状态码噪音）。
  - 500/503/429 错误映射为可行动提示（稍后重试、限流、服务不可用）。
  - 从响应体中解析 `detail/message/error.message`，减少“无效报错”。

## 3. 当前状态评估

### 3.1 P0（已缓解）

- `POST /api/writer/.../chapters/generate` 因 `httpx.ReadError` 直接 500 的问题已修复路径。
- 并发生成“一个失败全失败”的问题已改为“部分成功可继续”。

### 3.2 P0/P1（仍需推进）

1. 上游模型服务本身不稳定（尤其代理网关/兼容层），仍会返回 503，但现在应是可读失败而非系统崩溃。
2. 前端认证链路对临时失败过于激进（`/users/me` 非 401 也可能触发登出，需要专项修正）。
3. API 客户端仍未完全统一（存在多处裸 `fetch` 与不一致错误处理）。
4. 章节“生成中/评审中”状态可观测性不足，缺少后端真实阶段回传。

## 4. 系统级深度优化计划（建议 7 天）

## Day 1-2：稳定性优先（必须先做）

1. 统一 LLM 调用策略：
   - 明确错误分层（网络、鉴权、限流、模型不可用、超时）。
   - 统一重试策略（指数退避 + 抖动 + 最大重试次数）。
2. 统一异常到状态码映射：
   - 业务失败（4xx）与平台失败（503）严格分离。
3. 生成任务状态收口：
   - `generating -> success/failed` 必须闭环，禁止“卡住中间态”。

## Day 3-4：速度优化（用户体感）

1. 并发策略细化：
   - 多版本生成改为“最快成功优先返回 + 其余异步补全（可配置）”。
2. 长链路阶段可视化：
   - 返回阶段枚举：`summarizing / planning / drafting / reviewing / finalizing`。
3. 向量化、记忆层、伏笔抽取默认异步化：
   - 主链路优先保证可编辑稿件先可用。

## Day 5-6：体验与可维护性

1. 前端统一 `apiClient`：
   - 统一 token 注入、错误映射、重试、可观测埋点。
2. 认证策略修复：
   - 仅 `401` 登出，`500/503` 保留会话并可重试。
3. 创作工作台交互改造：
   - 去除原生 `alert/confirm`，统一非阻塞提示与重试入口。

## Day 7：回归与验收

1. 增加 E2E 冒烟：
   - 项目创建 -> 章节生成 -> 评审 -> 定稿。
2. 压测与故障注入：
   - 模拟上游超时/断流/限流，验证降级行为。
3. 发布清单与回滚预案：
   - 按功能开关灰度，逐步放量。

## 5. 质量与速度验收指标（建议）

1. 章节生成主链路成功率（5分钟窗口）>= 98%
2. 同类错误重复弹出率下降 60%+
3. 500 占比下降到 < 0.5%，503 可解释率 100%
4. 用户可见“卡死中间态”减少 90%
5. 前端 API 错误文案可读率（人工评审）>= 95%

## 6. 对标外部项目得到的产品要求（用于功能标尺）

1. 统一 Story Bible / Codex 作为事实源与上下文控制。
2. 章节版本分叉管理（不是简单覆盖）。
3. 可视化阶段反馈（写作过程可见，不是黑盒等待）。
4. 系列级角色/世界观共享（跨书一致性）。
5. 失败可恢复、可重试、不中断创作流。

> 这些能力与当前项目方向一致，但需要把“已有功能”从堆叠状态收敛成稳定主链路。

## 7. 外部参考（已核对）

- Sudowrite Story Bible（2026-01 更新）：  
  <https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/what-is-story-bible/jmWepHcQdJetNrE991fjJC>
- Sudowrite Chat（可读取 Story Bible 上下文）：  
  <https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/chat/5vbuELXf6LZQnGfVzsEXCV>
- Sudowrite Series Support（跨项目共享角色/世界观/大纲）：  
  <https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/series-support/3vfbZPCB1ANLm75FXmJf28>
- Novelcrafter Codex（可追踪角色弧线、上下文注入、关系层级）：  
  <https://www.novelcrafter.com/courses/codex-cookbook>
- LangChain Story Writing（章节图谱、版本分叉、阶段流式状态）：  
  <https://raw.githubusercontent.com/langchain-ai/story-writing/main/README.md>
- OpenAI 官方速率限制与退避策略建议：  
  <https://developers.openai.com/api/docs/guides/rate-limits>

## 8. 说明

“解决所有问题”在工程上不可能一次提交完成，但本轮已经把**最影响可用性的崩溃链路**修复并形成可执行路线图。下一步建议按 P0 -> P1 -> P2 连续推进，每次发布可回归、可度量、可回滚。

