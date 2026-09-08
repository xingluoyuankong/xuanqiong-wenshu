# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 创作工作台浏览器冒烟 >> 深链历史 Run 并切换运行时，浏览器始终投影所选 Run 的状态和事件
- Location: e2e\agent-workspace.spec.ts:423:3

# Error details

```
Error: expect(locator).toHaveValue(expected) failed

Locator: getByTestId('agent-run-selector')
Expected: "run-old"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toHaveValue" with timeout 5000ms
  - waiting for getByTestId('agent-run-selector')

```

```yaml
- complementary "主导航":
  - button "返回工作台": 玄
  - navigation "工作区导航":
    - button "返回上一页"
    - button "项目"
    - button "灵感与蓝图"
    - button "文风中心"
    - button "模型配置"
    - button "运行监控"
  - button "切换到英文"
  - button "设置"
- main:
  - paragraph: 玄穹文枢 · PROJECT AGENT
  - heading "小说创作 Agent 工作台" [level=1]
  - paragraph: 用自然语言统一规划、查看和调用当前小说项目的能力；读取与分析自动执行，写入与高风险操作先展示计划。
  - strong: E2E 星河旧梦
  - text: 正在准备项目会话
  - complementary:
    - toolbar "项目资源面板":
      - button "项目"
      - button "内容"
      - button "人物"
      - button "世界观": 世界
      - button "资料"
      - button "工具"
  - heading "创作对话" [level=2]
  - paragraph: 展示目标、公开轨迹、Provider reasoning、Assistant 正文、工具调用和结果摘要。
  - text: "准备会话… Agent 请求失败: HTTP 500"
  - paragraph: 请选择项目并发送目标，Agent 的历史消息会显示在这里。
  - region "当前 Agent 上下文": 当前上下文 项目：E2E 星河旧梦
  - text: 给小说 Agent 的指令
  - textbox "给小说 Agent 的指令":
    - /placeholder: 例如：检查当前项目第三章的质量风险，并给出不改正文的计划
  - text: 消息会写入当前会话，并接收真实运行事件。
  - button "发送给 Agent" [disabled]
  - complementary:
    - strong: 运行日志
    - text: 运行轨迹与诊断信息
    - button "关闭运行信息面板": ×
    - heading "运行日志" [level=2]
    - paragraph: 实时事件摘要；独立滚动，不占用聊天阅读区。
    - article:
      - strong: 已就绪
      - paragraph: 请选择项目并发送目标，Agent 的历史消息会显示在这里。
    - article:
      - strong: 会话恢复失败
      - paragraph: "Agent 请求失败: HTTP 500"
    - group: ▸ 当前运行 暂无运行
    - group: ▸ 运行详情 计划、审批、候选
    - group: ▸ 运行规则 边界与质量来源
  - complementary:
    - toolbar "运行信息面板":
      - button "运行日志" [pressed]: 日志
      - button "运行详情": 运行
      - button "进度"
      - button "结果产物": 产物
      - button "质量"
- region "通知"
```

# Test source

```ts
  423 |   test('深链历史 Run 并切换运行时，浏览器始终投影所选 Run 的状态和事件', async ({ page }) => {
  424 |     await mockAgentApi(page)
  425 |     const oldRun = {
  426 |       id: 'run-old',
  427 |       session_id: session.id,
  428 |       user_id: 1,
  429 |       project_id: project.id,
  430 |       status: 'completed',
  431 |       current_phase: 'completed',
  432 |       current_step: 1,
  433 |       progress: 21,
  434 |       created_at: '2026-08-24T00:00:00Z',
  435 |       started_at: '2026-08-24T00:00:00Z',
  436 |       finished_at: '2026-08-24T00:00:01Z',
  437 |     }
  438 |     const newestRun = {
  439 |       id: 'run-new',
  440 |       session_id: session.id,
  441 |       user_id: 1,
  442 |       project_id: project.id,
  443 |       status: 'completed',
  444 |       current_phase: 'completed',
  445 |       current_step: 2,
  446 |       progress: 88,
  447 |       created_at: '2026-08-24T00:01:00Z',
  448 |       started_at: '2026-08-24T00:01:00Z',
  449 |       finished_at: '2026-08-24T00:01:01Z',
  450 |     }
  451 | 
  452 |     await page.unroute('**/api/agent/sessions?project_id=*')
  453 |     await page.route('**/api/agent/sessions?project_id=*', async (route) =>
  454 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
  455 |     )
  456 |     await page.unroute(`**/api/agent/sessions/${session.id}`)
  457 |     await page.route(`**/api/agent/sessions/${session.id}`, async (route) =>
  458 |       route.fulfill({
  459 |         status: 200,
  460 |         contentType: 'application/json',
  461 |         body: JSON.stringify({ ...session, messages: [], runs: [oldRun, newestRun] }),
  462 |       }),
  463 |     )
  464 |     await page.unroute('**/api/agent/runs/*/approvals')
  465 |     await page.route('**/api/agent/runs/*/approvals', async (route) => {
  466 |       const runId = route.request().url().includes('run-old') ? oldRun.id : newestRun.id
  467 |       await route.fulfill({
  468 |         status: 200,
  469 |         contentType: 'application/json',
  470 |         body: JSON.stringify([{ id: `approval-${runId}`, run_id: runId, user_id: 1, tool_name: 'chapter.rewrite', status: 'pending' }]),
  471 |       })
  472 |     })
  473 |     await page.unroute('**/api/agent/runs/*/artifacts')
  474 |     await page.route('**/api/agent/runs/*/artifacts', async (route) => {
  475 |       const runId = route.request().url().includes('run-old') ? oldRun.id : newestRun.id
  476 |       await route.fulfill({
  477 |         status: 200,
  478 |         contentType: 'application/json',
  479 |         body: JSON.stringify([{ id: `artifact-${runId}`, run_id: runId, user_id: 1, project_id: project.id, kind: 'chapter_candidate', uri: `artifact://${runId}`, metadata_json: {}, created_at: session.created_at }]),
  480 |       })
  481 |     })
  482 |     await page.unroute('**/api/agent/runs/*/steps')
  483 |     await page.route('**/api/agent/runs/*/steps', async (route) => {
  484 |       const isOld = route.request().url().includes('run-old')
  485 |       const runId = isOld ? oldRun.id : newestRun.id
  486 |       await route.fulfill({
  487 |         status: 200,
  488 |         contentType: 'application/json',
  489 |         body: JSON.stringify([{ id: `step-${runId}`, run_id: runId, user_id: 1, step_order: 1, tool_name: isOld ? 'chapter.version.list' : 'quality.inspect', idempotency_key: `step-${runId}`, status: 'completed', attempt_count: 1, output_json: {} }]),
  490 |       })
  491 |     })
  492 |     await page.unroute('**/api/agent/runs/*/state')
  493 |     await page.route('**/api/agent/runs/*/state', async (route) => {
  494 |       const isOld = route.request().url().includes('run-old')
  495 |       const run = isOld ? oldRun : newestRun
  496 |       const latestPublicSummary = {
  497 |         action_id: `summary-${run.id}`,
  498 |         phase: 'tool_execution',
  499 |         current_action: isOld ? '历史 Run 正在整理章节版本。' : '最新 Run 正在汇总质量。',
  500 |         input_scope: [{ kind: 'chapter', chapter_number: isOld ? 3 : 8 }],
  501 |         selected_capability: isOld ? 'chapter.version.list' : 'quality.inspect',
  502 |         revision: 0,
  503 |       }
  504 |       await route.fulfill({
  505 |         status: 200,
  506 |         contentType: 'application/json',
  507 |         body: JSON.stringify({ correlation_id: `correlation-${run.id}`, run_id: run.id, user_id: 1, progress: run.progress, phase: run.current_phase, current_step: run.current_step, terminal_status: run.status, recoverable: false, cancellation_requested: false, last_event_sequence: 1, latest_public_summary: latestPublicSummary, latest_public_summary_sequence: 1, latest_public_summary_at: session.created_at, steps: [], approvals: [], artifacts: [], accepted_version_ids: [], jobs: [], task_runtime_refs: [] }),
  508 |       })
  509 |     })
  510 |     await page.unroute(`**/api/agent/sessions/${session.id}/runs/*/events**`)
  511 |     await page.route(`**/api/agent/sessions/${session.id}/runs/*/events**`, async (route) => {
  512 |       const isOld = route.request().url().includes('run-old')
  513 |       const run = isOld ? oldRun : newestRun
  514 |       await route.fulfill({
  515 |         status: 200,
  516 |         contentType: 'application/json',
  517 |         body: JSON.stringify([{ id: `event-${run.id}`, run_id: run.id, user_id: 1, sequence: 1, event_type: 'progress_update', summary: isOld ? '历史 Run 已载入' : '最新 Run 已载入', data: { progress: run.progress, progress_message: isOld ? '历史进度' : '最新进度' }, created_at: session.created_at }]),
  518 |       })
  519 |     })
  520 | 
  521 |     await page.goto(`/agent?project_id=${project.id}&session_id=${session.id}&run_id=${oldRun.id}`)
  522 |     await openAgentPanel(page, 'right', 'log')
> 523 |     await expect(page.getByTestId('agent-run-selector')).toHaveValue(oldRun.id)
      |                                                          ^ Error: expect(locator).toHaveValue(expected) failed
  524 |     await expect(page.getByTestId('agent-selected-run-id')).toContainText('run-old')
  525 |     await expect(page.getByTestId('agent-run-progress')).toHaveText('21%')
  526 |     await expect(page.getByTestId('agent-step-panel')).toContainText('chapter.version.list')
  527 |     await expect(page.getByTestId('agent-public-work-summary')).toContainText('历史 Run 正在整理章节版本。')
  528 |     await expect(page.getByTestId('agent-process-stream')).toContainText('历史 Run 已载入')
  529 | 
  530 |     await page.getByTestId('agent-run-selector').selectOption(newestRun.id)
  531 |     await expect(page.getByTestId('agent-selected-run-id')).toContainText('run-new')
  532 |     await expect(page.getByTestId('agent-run-progress')).toHaveText('88%')
  533 |     await expect(page.getByTestId('agent-step-panel')).toContainText('quality.inspect')
  534 |     await expect(page.getByTestId('agent-public-work-summary')).toContainText('最新 Run 正在汇总质量。')
  535 |     await expect(page.getByTestId('agent-public-work-summary')).not.toContainText('历史 Run 正在整理章节版本。')
  536 |     await expect(page.getByTestId('agent-process-stream')).toContainText('最新 Run 已载入')
  537 |     await expect(page.getByTestId('agent-process-stream')).not.toContainText('历史 Run 已载入')
  538 |   })
  539 | 
  540 |   test('Artifact 质量发现通过最小 ContextRef 进入 Chat 发送请求', async ({ page }) => {
  541 |     const state = await mockAgentApi(page)
  542 |     const run = {
  543 |       id: 'quality-context-run',
  544 |       session_id: session.id,
  545 |       user_id: 1,
  546 |       project_id: project.id,
  547 |       status: 'completed',
  548 |       current_phase: 'quality',
  549 |       current_step: 1,
  550 |       progress: 100,
  551 |       created_at: session.created_at,
  552 |       started_at: session.created_at,
  553 |       finished_at: session.created_at,
  554 |     }
  555 |     const artifact = {
  556 |       id: 'quality-context-artifact',
  557 |       run_id: run.id,
  558 |       user_id: 1,
  559 |       project_id: project.id,
  560 |       kind: 'chapter_candidate',
  561 |       uri: 'artifact://quality-context',
  562 |       metadata_json: { status: 'candidate' },
  563 |       created_at: session.created_at,
  564 |     }
  565 |     state.run = run
  566 |     let messagePayload: Record<string, unknown> | undefined
  567 | 
  568 |     await page.unroute('**/api/agent/sessions?project_id=*')
  569 |     await page.route('**/api/agent/sessions?project_id=*', async (route) =>
  570 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
  571 |     )
  572 |     await page.unroute('**/api/agent/runs/*/artifacts')
  573 |     await page.route('**/api/agent/runs/*/artifacts', async (route) =>
  574 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([artifact]) }),
  575 |     )
  576 |     await page.unroute('**/api/agent/artifacts/*/quality')
  577 |     await page.route('**/api/agent/artifacts/*/quality', async (route) =>
  578 |       route.fulfill({
  579 |         status: 200,
  580 |         contentType: 'application/json',
  581 |         body: JSON.stringify({
  582 |           artifact_id: artifact.id,
  583 |           quality_result: null,
  584 |           gate: null,
  585 |           findings: [{
  586 |             id: 'quality-finding-row',
  587 |             finding_id: 'quality-finding-e2e',
  588 |             code: 'ending_pressure_missing',
  589 |             category: 'ending',
  590 |             severity: 'blocker',
  591 |             status: 'open',
  592 |             message: 'DO_NOT_SEND_MESSAGE',
  593 |             fingerprint: 'a'.repeat(64),
  594 |             location_json: { hidden: 'DO_NOT_SEND_LOCATION' },
  595 |             evidence_json: { hidden: 'DO_NOT_SEND_EVIDENCE' },
  596 |             remediation_json: { hidden: 'DO_NOT_SEND_REMEDIATION' },
  597 |             created_at: session.created_at,
  598 |           }],
  599 |         }),
  600 |       }),
  601 |     )
  602 |     await page.route(`**/api/agent/sessions/${session.id}/messages`, async (route) => {
  603 |       messagePayload = route.request().postDataJSON() as Record<string, unknown>
  604 |       await route.fulfill({
  605 |         status: 201,
  606 |         contentType: 'application/json',
  607 |         body: JSON.stringify({
  608 |           message: {
  609 |             id: 'quality-context-user-message',
  610 |             session_id: session.id,
  611 |             user_id: 1,
  612 |             role: 'user',
  613 |             content: '根据质量发现修订候选稿',
  614 |             sequence: 1,
  615 |             created_at: session.created_at,
  616 |           },
  617 |           assistant_message: null,
  618 |           run: null,
  619 |           plan: null,
  620 |           tool_results: [],
  621 |           approvals: [],
  622 |         }),
  623 |       })
```