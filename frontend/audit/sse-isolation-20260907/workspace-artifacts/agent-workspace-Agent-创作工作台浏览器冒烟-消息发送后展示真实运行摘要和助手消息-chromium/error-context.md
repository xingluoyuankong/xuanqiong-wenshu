# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 创作工作台浏览器冒烟 >> 消息发送后展示真实运行摘要和助手消息
- Location: e2e\agent-workspace.spec.ts:650:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: getByTestId('agent-message-list')
Expected substring: "已完成项目上下文检查。"
Received string:    "你检查当前项目"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for getByTestId('agent-message-list')
    14 × locator resolved to <div class="messages" data-v-d4bbed65="" data-testid="agent-message-list">…</div>
       - unexpected value "你检查当前项目"

```

```yaml
- article:
  - text: 你
  - paragraph: 检查当前项目
```

# Test source

```ts
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
  729 |     )
  730 |     await page.route(`**/api/agent/sessions/${session.id}/runs/run-1/stream**`, async (route) => {
  731 |       state.run = {
  732 |         ...state.run,
  733 |         status: 'completed',
  734 |         current_phase: 'summary',
  735 |         progress: 100,
  736 |         finished_at: session.created_at,
  737 |       }
  738 |       state.messages = [
  739 |         {
  740 |           id: 'm-user',
  741 |           session_id: session.id,
  742 |           user_id: 1,
  743 |           role: 'user',
  744 |           content: '检查当前项目',
  745 |           sequence: 1,
  746 |           created_at: session.created_at,
  747 |         },
  748 |         {
  749 |           id: 'm-assistant',
  750 |           session_id: session.id,
  751 |           user_id: 1,
  752 |           role: 'assistant',
  753 |           content: '已完成项目上下文检查。',
  754 |           sequence: 2,
  755 |           created_at: session.created_at,
  756 |         },
  757 |       ]
  758 |       const event = (
  759 |         sequence: number,
  760 |         eventType: string,
  761 |         summary: string,
  762 |         data: Record<string, unknown>,
  763 |       ) =>
  764 |         `id: ${sequence}\nevent: ${eventType}\ndata: ${JSON.stringify({ id: `event-${sequence}`, run_id: 'run-1', user_id: 1, sequence, event_type: eventType, summary, data, created_at: session.created_at })}\n\n`
  765 |       await route.fulfill({
  766 |         status: 200,
  767 |         contentType: 'text/event-stream',
  768 |         body:
  769 |           event(3, 'progress_update', '正在生成可见回复', {
  770 |             phase: 'assistant_response',
  771 |             progress: 90,
  772 |             step: 1,
  773 |             tool_name: 'project.context',
  774 |             progress_message: '工具已完成，正在生成可见回复。',
  775 |           }) +
  776 |           event(90, 'assistant_delta', '错误 Run 的输出', { content: '不应出现的跨 Run 事件', run_id: 'run-foreign' })
  777 |             .replace('run_id\":\"run-1', 'run_id\":\"run-foreign') +
  778 |           event(4, 'assistant_delta', 'Agent 输出第一段', { content: '已完成' }) +
  779 |           event(4, 'assistant_delta', 'Agent 输出第一段（重复重放）', { content: '已完成' }) +
  780 |           event(5, 'assistant_delta', 'Agent 输出第二段', { content: '项目上下文检查。' }) +
  781 |           event(6, 'run_completed', 'Agent 运行已完成', { phase: 'summary', progress: 100 }),
  782 |       })
  783 |     })
  784 |     await page.goto('/agent')
  785 |     await openAgentPanel(page, 'left', 'project')
  786 |     await page.getByTestId('agent-content-chapter-1').click()
  787 |     await expect(page.getByTestId('agent-context-chip-chapter-version')).toContainText(
  788 |       '第 1 章 · 版本 11',
  789 |     )
  790 |     await page.getByTestId('agent-message-input').fill('检查当前项目')
  791 |     await page.getByTestId('agent-plan-submit').click()
> 792 |     await expect(page.getByTestId('agent-message-list')).toContainText('已完成项目上下文检查。')
      |                                                          ^ Error: expect(locator).toContainText(expected) failed
  793 |     await expect(page.getByTestId('agent-run-status')).toContainText('completed')
  794 |     await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 已返回计划')
  795 |     await expect(page.getByTestId('agent-process-stream')).toContainText('已复用已完成步骤')
  796 |     await expect(page.getByTestId('agent-process-stream')).toContainText('运行进度')
  797 |     await expect(page.getByTestId('agent-run-progress-message')).toContainText(
  798 |       '工具已完成，正在生成可见回复。',
  799 |     )
  800 |     await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 输出第一段')
  801 |     await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 输出第二段')
  802 |     await expect(page.getByTestId('agent-process-stream')).not.toContainText('不应出现的跨 Run 事件')
  803 |     await expect(page.getByTestId('agent-process-stream')).not.toContainText('Agent 输出第一段（重复重放）')
  804 |     await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 运行已完成')
  805 |     await expect(page.getByTestId('agent-step-panel')).toContainText('project.context')
  806 |     await expect(page.getByTestId('agent-step-panel')).toContainText('第 1 次')
  807 |     await expect(page.getByTestId('agent-step-panel')).toContainText('已完成')
  808 |     await expect(page.getByTestId('agent-step-panel')).toContainText('已复用/保存结果')
  809 |     expect(messagePayload).toEqual({
  810 |       content: '检查当前项目',
  811 |       context_refs: [
  812 |         { kind: 'project', project_id: project.id },
  813 |         {
  814 |           kind: 'chapter_version',
  815 |           project_id: project.id,
  816 |           chapter_number: 1,
  817 |           version_id: 11,
  818 |           role: 'selected',
  819 |         },
  820 |       ],
  821 |     })
  822 |     expect(JSON.stringify(messagePayload)).not.toContain('E2E 章节正文预览')
  823 |   })
  824 | })
  825 | 
  826 | test.describe('Agent 恢复与 DLQ 浏览器交互', () => {
  827 |   test('恢复就绪运行显示恢复按钮并接收恢复后的可见事件', async ({ page }) => {
  828 |     const state = await mockAgentApi(page)
  829 |     let streamCalls = 0
  830 |     await page.route(`**/api/agent/sessions/${session.id}/messages`, async (route) =>
  831 |       route.fulfill({
  832 |         status: 201,
  833 |         contentType: 'application/json',
  834 |         body: JSON.stringify({
  835 |           message: {
  836 |             id: 'm-recover-user',
  837 |             session_id: session.id,
  838 |             user_id: 1,
  839 |             role: 'user',
  840 |             content: '恢复运行',
  841 |             sequence: 1,
  842 |             created_at: session.created_at,
  843 |           },
  844 |           assistant_message: null,
  845 |           run: (state.run = {
  846 |             id: 'run-recover',
  847 |             session_id: session.id,
  848 |             user_id: 1,
  849 |             project_id: project.id,
  850 |             status: 'paused',
  851 |             current_phase: 'recovery_ready',
  852 |             current_step: 1,
  853 |             progress: 80,
  854 |             created_at: session.created_at,
  855 |             started_at: session.created_at,
  856 |             finished_at: null,
  857 |           }),
  858 |           plan: {
  859 |             goal: '恢复运行',
  860 |             project_id: project.id,
  861 |             mode: 'explore',
  862 |             steps: [
  863 |               {
  864 |                 order: 1,
  865 |                 tool_name: 'project.context',
  866 |                 description: '读取项目',
  867 |                 risk_level: 'read',
  868 |                 requires_confirmation: false,
  869 |               },
  870 |             ],
  871 |             events: [],
  872 |             provider_called: false,
  873 |           },
  874 |           tool_results: [{ tool_name: 'project.context', result: { project } }],
  875 |         }),
  876 |       }),
  877 |     )
  878 |     await page.route(
  879 |       `**/api/agent/sessions/${session.id}/runs/run-recover/events**`,
  880 |       async (route) =>
  881 |         route.fulfill({
  882 |           status: 200,
  883 |           contentType: 'application/json',
  884 |           body: JSON.stringify([
  885 |             {
  886 |               id: 'recover-event-1',
  887 |               run_id: 'run-recover',
  888 |               user_id: 1,
  889 |               sequence: 1,
  890 |               event_type: 'run_recovery_ready',
  891 |               summary: '运行已进入可恢复状态',
  892 |               data: { phase: 'recovery_ready' },
```