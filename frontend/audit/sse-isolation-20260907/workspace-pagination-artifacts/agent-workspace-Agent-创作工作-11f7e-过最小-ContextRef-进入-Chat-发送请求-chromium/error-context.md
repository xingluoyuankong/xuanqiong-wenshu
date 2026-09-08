# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 创作工作台浏览器冒烟 >> Artifact 质量发现通过最小 ContextRef 进入 Chat 发送请求
- Location: e2e\agent-workspace.spec.ts:541:3

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
  - text: 会话已恢复 · active
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
  - text: 会话：E2E Agent 会话 实时运行流已断开，可手动重连
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
    - heading "本会话运行" [level=2]
    - text: 查看运行
    - combobox "查看运行":
      - option "quality- · 已完成 · 100%" [selected]
    - paragraph: 当前：quality-
    - text: 已载入 1 / 1 次运行
    - heading "运行日志" [level=2]
    - paragraph: 实时事件摘要；独立滚动，不占用聊天阅读区。
    - article:
      - strong: 运行流暂时中断
      - paragraph: "Agent 请求失败: HTTP 500"
    - article:
      - strong: 会话已恢复
      - paragraph: 0 条历史消息，1 次运行记录。
    - group:
      - text: ▸ 当前运行 已完成 · 100%
      - region "Agent运行检查器":
        - heading "当前运行" [level=2]
        - paragraph: "Agent 请求失败: HTTP 500"
        - paragraph: 尚未定位动作或结果
        - term: 状态
        - definition: completed
        - term: 关联
        - definition: e2e-corr
        - term: 阶段
        - definition: quality
        - term: 进度
        - definition: 100%
        - term: 步骤
        - definition: "1"
        - term: 规划 Provider
        - definition: 未调用 Provider 本次未调用
        - term: 回复 Provider
        - definition: 尚无运行事实 本次状态未知
        - term: 候选正文 Provider
        - definition: 尚无运行事实 本次状态未知
        - button "重新连接"
        - heading "当前运行工具结果" [level=2]
        - paragraph: 由当前 Run 响应或持久化步骤投影；正文、提示词与密钥不会回显。
        - paragraph: 当前运行没有可展示的工具结果。
        - heading "执行检查点" [level=2]
        - paragraph: 持久化步骤状态与恢复依据。
        - list:
          - listitem: 1. project.context 已完成 · 第 1 次 已复用/保存结果
      - text: "已载入 1 / 1 个步骤命令摘要读取失败：Agent 请求失败: HTTP 500"
      - button "加载更多命令"
    - group:
      - text: ▸ 运行详情 计划、审批、候选
      - region "当前运行冻结事实":
        - strong: 运行冻结事实
        - text: 可恢复、可校验、按当前 Run 隔离
        - term: 上下文快照
        - definition:
          - text: run_initial · 0 条引用 ·
          - code: aaaaaaaaaaaa…
        - term: 计划修订
        - definition:
          - text: r1 · completed
          - code: bbbbbbbbbbbb…
      - heading "候选结果" [level=2]
      - paragraph: 接受后才会保存为新的章节版本。
      - article:
        - text: chapter_candidate candidate 质量：未检查 · 阻断项 0 尚未取得权威质量门禁，暂不能接受候选。
        - button "读取质量与谱系"
        - text: 谱系事实尚未载入。 artifact://quality-context
        - button "查看候选正文"
        - button "定位质量阻断"
        - button "读取修复指令"
        - button "在写作台打开对应章节"
        - button "接受并保存版本" [disabled]
      - text: 已载入 1 / 1 个候选
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
  529 |     await expect(page.getByTestId('agent-process-stream')).toContainText('历史 Run 已载入')
  530 | 
  531 |     await page.getByTestId('agent-run-selector').selectOption(newestRun.id)
  532 |     await expect(page.getByTestId('agent-selected-run-id')).toContainText('run-new')
  533 |     await expect(page.getByTestId('agent-run-progress')).toHaveText('88%')
  534 |     await expect(page.getByTestId('agent-step-panel')).toContainText('quality.inspect')
  535 |     await expect(page.getByTestId('agent-public-work-summary')).toContainText('最新 Run 正在汇总质量。')
  536 |     await expect(page.getByTestId('agent-public-work-summary')).not.toContainText('历史 Run 正在整理章节版本。')
  537 |     await expect(page.getByTestId('agent-process-stream')).toContainText('最新 Run 已载入')
  538 |     await expect(page.getByTestId('agent-process-stream')).not.toContainText('历史 Run 已载入')
  539 |   })
  540 | 
  541 |   test('Artifact 质量发现通过最小 ContextRef 进入 Chat 发送请求', async ({ page }) => {
  542 |     const state = await mockAgentApi(page)
  543 |     const run = {
  544 |       id: 'quality-context-run',
  545 |       session_id: session.id,
  546 |       user_id: 1,
  547 |       project_id: project.id,
  548 |       status: 'completed',
  549 |       current_phase: 'quality',
  550 |       current_step: 1,
  551 |       progress: 100,
  552 |       created_at: session.created_at,
  553 |       started_at: session.created_at,
  554 |       finished_at: session.created_at,
  555 |     }
  556 |     const artifact = {
  557 |       id: 'quality-context-artifact',
  558 |       run_id: run.id,
  559 |       user_id: 1,
  560 |       project_id: project.id,
  561 |       kind: 'chapter_candidate',
  562 |       uri: 'artifact://quality-context',
  563 |       metadata_json: { status: 'candidate' },
  564 |       created_at: session.created_at,
  565 |     }
  566 |     state.run = run
  567 |     let messagePayload: Record<string, unknown> | undefined
  568 | 
  569 |     await unrouteAgentFixture(page, '**/api/agent/sessions?project_id=*')
  570 |     await routeAgentFixture(page, '**/api/agent/sessions?project_id=*', async (route) =>
  571 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
  572 |     )
  573 |     await unrouteAgentFixture(page, '**/api/agent/runs/*/artifacts')
  574 |     await routeAgentFixture(page, '**/api/agent/runs/*/artifacts', async (route) =>
  575 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([artifact]) }),
  576 |     )
  577 |     await unrouteAgentFixture(page, '**/api/agent/artifacts/*/quality')
  578 |     await routeAgentFixture(page, '**/api/agent/artifacts/*/quality', async (route) =>
  579 |       route.fulfill({
  580 |         status: 200,
  581 |         contentType: 'application/json',
  582 |         body: JSON.stringify({
  583 |           artifact_id: artifact.id,
  584 |           quality_result: null,
  585 |           gate: null,
  586 |           findings: [{
  587 |             id: 'quality-finding-row',
  588 |             finding_id: 'quality-finding-e2e',
  589 |             code: 'ending_pressure_missing',
  590 |             category: 'ending',
  591 |             severity: 'blocker',
  592 |             status: 'open',
  593 |             message: 'DO_NOT_SEND_MESSAGE',
  594 |             fingerprint: 'a'.repeat(64),
  595 |             location_json: { hidden: 'DO_NOT_SEND_LOCATION' },
  596 |             evidence_json: { hidden: 'DO_NOT_SEND_EVIDENCE' },
  597 |             remediation_json: { hidden: 'DO_NOT_SEND_REMEDIATION' },
  598 |             created_at: session.created_at,
  599 |           }],
  600 |         }),
  601 |       }),
  602 |     )
  603 |     await routeAgentFixture(page, `**/api/agent/sessions/${session.id}/messages`, async (route) => {
  604 |       messagePayload = route.request().postDataJSON() as Record<string, unknown>
  605 |       await route.fulfill({
  606 |         status: 201,
  607 |         contentType: 'application/json',
  608 |         body: JSON.stringify({
  609 |           message: {
  610 |             id: 'quality-context-user-message',
  611 |             session_id: session.id,
  612 |             user_id: 1,
  613 |             role: 'user',
  614 |             content: '根据质量发现修订候选稿',
  615 |             sequence: 1,
  616 |             created_at: session.created_at,
  617 |           },
  618 |           assistant_message: null,
  619 |           run: null,
  620 |           plan: null,
  621 |           tool_results: [],
  622 |           approvals: [],
  623 |         }),
  624 |       })
  625 |     })
  626 | 
  627 |     await page.goto(`/agent?project_id=${project.id}&session_id=${session.id}&run_id=${run.id}`)
  628 |     await expandWorkspaceSection(page, 'agent-run-details-section')
> 629 |     await expect(page.getByTestId('agent-quality-finding-quality-finding-e2e')).toHaveText('加入上下文')
      |                                                                                 ^ Error: expect(locator).toHaveText(expected) failed
  630 |     await page.getByTestId('agent-quality-finding-quality-finding-e2e').click()
  631 |     await expect(page.getByTestId('agent-quality-finding-quality-finding-e2e')).toHaveText('移除上下文')
  632 |     await expect(page.getByTestId('agent-context-chip-quality-finding')).toContainText('质量发现：quality-')
  633 | 
  634 |     await page.getByTestId('agent-message-input').fill('根据质量发现修订候选稿')
  635 |     await page.getByTestId('agent-plan-submit').click()
  636 | 
  637 |     expect(messagePayload).toEqual({
  638 |       content: '根据质量发现修订候选稿',
  639 |       context_refs: [
  640 |         { kind: 'project', project_id: project.id },
  641 |         { kind: 'quality_finding', project_id: project.id, finding_id: 'quality-finding-e2e' },
  642 |       ],
  643 |     })
  644 |     const serialized = JSON.stringify(messagePayload)
  645 |     expect(serialized).not.toContain('DO_NOT_SEND_MESSAGE')
  646 |     expect(serialized).not.toContain('DO_NOT_SEND_LOCATION')
  647 |     expect(serialized).not.toContain('DO_NOT_SEND_EVIDENCE')
  648 |     expect(serialized).not.toContain('DO_NOT_SEND_REMEDIATION')
  649 |   })
  650 | 
  651 |   test('消息发送后展示真实运行摘要和助手消息', async ({ page }) => {
  652 |     const state = await mockAgentApi(page)
  653 |     let messagePayload: Record<string, unknown> | undefined
  654 |     await routeAgentFixture(page, `**/api/agent/sessions/${session.id}/messages`, async (route) => {
  655 |       messagePayload = route.request().postDataJSON() as Record<string, unknown>
  656 |       await route.fulfill({
  657 |         status: 201,
  658 |         contentType: 'application/json',
  659 |         body: JSON.stringify({
  660 |           message: {
  661 |             id: 'm-user',
  662 |             session_id: session.id,
  663 |             user_id: 1,
  664 |             role: 'user',
  665 |             content: '检查当前项目',
  666 |             sequence: 1,
  667 |             created_at: session.created_at,
  668 |           },
  669 |           assistant_message: null,
  670 |           run: (state.run = {
  671 |             id: 'run-1',
  672 |             session_id: session.id,
  673 |             user_id: 1,
  674 |             project_id: project.id,
  675 |             status: 'running',
  676 |             current_phase: 'assistant_response',
  677 |             current_step: 1,
  678 |             progress: 80,
  679 |             created_at: session.created_at,
  680 |             started_at: session.created_at,
  681 |             finished_at: null,
  682 |           }),
  683 |           plan: {
  684 |             goal: '检查当前项目',
  685 |             project_id: project.id,
  686 |             mode: 'explore',
  687 |             steps: [
  688 |               {
  689 |                 order: 1,
  690 |                 tool_name: 'project.context',
  691 |                 description: '读取项目',
  692 |                 risk_level: 'read',
  693 |                 requires_confirmation: false,
  694 |               },
  695 |             ],
  696 |             events: [],
  697 |             provider_called: false,
  698 |           },
  699 |           tool_results: [{ tool_name: 'project.context', result: { project: project } }],
  700 |         }),
  701 |       })
  702 |     })
  703 |     await routeAgentFixture(page, `**/api/agent/sessions/${session.id}/runs/run-1/events**`, async (route) =>
  704 |       route.fulfill({
  705 |         status: 200,
  706 |         contentType: 'application/json',
  707 |         body: JSON.stringify([
  708 |           {
  709 |             id: 'event-1',
  710 |             run_id: 'run-1',
  711 |             user_id: 1,
  712 |             sequence: 1,
  713 |             event_type: 'plan_created',
  714 |             summary: '计划已创建',
  715 |             data: { phase: 'planning' },
  716 |             created_at: session.created_at,
  717 |           },
  718 |           {
  719 |             id: 'event-2',
  720 |             run_id: 'run-1',
  721 |             user_id: 1,
  722 |             sequence: 2,
  723 |             event_type: 'step_reused',
  724 |             summary: '已复用项目上下文结果',
  725 |             data: { tool_name: 'project.context', step: 1, phase: 'checkpoint_replay' },
  726 |             created_at: session.created_at,
  727 |           },
  728 |         ]),
  729 |       }),
```