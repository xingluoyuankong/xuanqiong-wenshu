# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 创作工作台浏览器冒烟 >> Artifact 质量发现通过最小 ContextRef 进入 Chat 发送请求
- Location: e2e\agent-workspace.spec.ts:540:3

# Error details

```
Error: expect(locator).toHaveText(expected) failed

Locator: getByTestId('agent-quality-finding-quality-finding-e2e')
Expected: "加入上下文"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toHaveText" with timeout 5000ms
  - waiting for getByTestId('agent-quality-finding-quality-finding-e2e')

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
  624 |     })
  625 | 
  626 |     await page.goto(`/agent?project_id=${project.id}&session_id=${session.id}&run_id=${run.id}`)
  627 |     await expandWorkspaceSection(page, 'agent-run-details-section')
> 628 |     await expect(page.getByTestId('agent-quality-finding-quality-finding-e2e')).toHaveText('加入上下文')
      |                                                                                 ^ Error: expect(locator).toHaveText(expected) failed
  629 |     await page.getByTestId('agent-quality-finding-quality-finding-e2e').click()
  630 |     await expect(page.getByTestId('agent-quality-finding-quality-finding-e2e')).toHaveText('移除上下文')
  631 |     await expect(page.getByTestId('agent-context-chip-quality-finding')).toContainText('质量发现：quality-')
  632 | 
  633 |     await page.getByTestId('agent-message-input').fill('根据质量发现修订候选稿')
  634 |     await page.getByTestId('agent-plan-submit').click()
  635 | 
  636 |     expect(messagePayload).toEqual({
  637 |       content: '根据质量发现修订候选稿',
  638 |       context_refs: [
  639 |         { kind: 'project', project_id: project.id },
  640 |         { kind: 'quality_finding', project_id: project.id, finding_id: 'quality-finding-e2e' },
  641 |       ],
  642 |     })
  643 |     const serialized = JSON.stringify(messagePayload)
  644 |     expect(serialized).not.toContain('DO_NOT_SEND_MESSAGE')
  645 |     expect(serialized).not.toContain('DO_NOT_SEND_LOCATION')
  646 |     expect(serialized).not.toContain('DO_NOT_SEND_EVIDENCE')
  647 |     expect(serialized).not.toContain('DO_NOT_SEND_REMEDIATION')
  648 |   })
  649 | 
  650 |   test('消息发送后展示真实运行摘要和助手消息', async ({ page }) => {
  651 |     const state = await mockAgentApi(page)
  652 |     let messagePayload: Record<string, unknown> | undefined
  653 |     await page.route(`**/api/agent/sessions/${session.id}/messages`, async (route) => {
  654 |       messagePayload = route.request().postDataJSON() as Record<string, unknown>
  655 |       await route.fulfill({
  656 |         status: 201,
  657 |         contentType: 'application/json',
  658 |         body: JSON.stringify({
  659 |           message: {
  660 |             id: 'm-user',
  661 |             session_id: session.id,
  662 |             user_id: 1,
  663 |             role: 'user',
  664 |             content: '检查当前项目',
  665 |             sequence: 1,
  666 |             created_at: session.created_at,
  667 |           },
  668 |           assistant_message: null,
  669 |           run: (state.run = {
  670 |             id: 'run-1',
  671 |             session_id: session.id,
  672 |             user_id: 1,
  673 |             project_id: project.id,
  674 |             status: 'running',
  675 |             current_phase: 'assistant_response',
  676 |             current_step: 1,
  677 |             progress: 80,
  678 |             created_at: session.created_at,
  679 |             started_at: session.created_at,
  680 |             finished_at: null,
  681 |           }),
  682 |           plan: {
  683 |             goal: '检查当前项目',
  684 |             project_id: project.id,
  685 |             mode: 'explore',
  686 |             steps: [
  687 |               {
  688 |                 order: 1,
  689 |                 tool_name: 'project.context',
  690 |                 description: '读取项目',
  691 |                 risk_level: 'read',
  692 |                 requires_confirmation: false,
  693 |               },
  694 |             ],
  695 |             events: [],
  696 |             provider_called: false,
  697 |           },
  698 |           tool_results: [{ tool_name: 'project.context', result: { project: project } }],
  699 |         }),
  700 |       })
  701 |     })
  702 |     await page.route(`**/api/agent/sessions/${session.id}/runs/run-1/events**`, async (route) =>
  703 |       route.fulfill({
  704 |         status: 200,
  705 |         contentType: 'application/json',
  706 |         body: JSON.stringify([
  707 |           {
  708 |             id: 'event-1',
  709 |             run_id: 'run-1',
  710 |             user_id: 1,
  711 |             sequence: 1,
  712 |             event_type: 'plan_created',
  713 |             summary: '计划已创建',
  714 |             data: { phase: 'planning' },
  715 |             created_at: session.created_at,
  716 |           },
  717 |           {
  718 |             id: 'event-2',
  719 |             run_id: 'run-1',
  720 |             user_id: 1,
  721 |             sequence: 2,
  722 |             event_type: 'step_reused',
  723 |             summary: '已复用项目上下文结果',
  724 |             data: { tool_name: 'project.context', step: 1, phase: 'checkpoint_replay' },
  725 |             created_at: session.created_at,
  726 |           },
  727 |         ]),
  728 |       }),
```