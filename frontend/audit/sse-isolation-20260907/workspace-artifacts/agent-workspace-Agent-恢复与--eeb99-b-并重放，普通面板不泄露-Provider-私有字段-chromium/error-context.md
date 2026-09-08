# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 恢复与 DLQ 浏览器交互 >> 管理员可查看死信 Job 并重放，普通面板不泄露 Provider 私有字段
- Location: e2e\agent-workspace.spec.ts:953:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: getByTestId('agent-dead-letter-panel')
Expected substring: "temporary provider failure"
Received string:    "死信 Job（管理员）只允许管理员重新排队；原失败次数和审计事件保留。visible_response · ProviderTimeoutattempt 1/1 · dlq-1无公开结果摘要重新排队"
Timeout: 5000ms

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for getByTestId('agent-dead-letter-panel')
    14 × locator resolved to <section data-v-3045fdb9="" data-v-318697e4="" data-testid="agent-dead-letter-panel" class="xq-panel xq-paper-grain xq-panel--paper">…</section>
       - unexpected value "死信 Job（管理员）只允许管理员重新排队；原失败次数和审计事件保留。visible_response · ProviderTimeoutattempt 1/1 · dlq-1无公开结果摘要重新排队"

```

```yaml
- heading "死信 Job（管理员）" [level=2]
- paragraph: 只允许管理员重新排队；原失败次数和审计事件保留。
- list:
  - listitem:
    - strong: visible_response · ProviderTimeout
    - text: attempt 1/1 · dlq-1 无公开结果摘要
    - button "重新排队"
```

# Test source

```ts
  925  |           status: 'completed',
  926  |           current_phase: 'summary',
  927  |           progress: 100,
  928  |           finished_at: session.created_at,
  929  |         }
  930  |         await route.fulfill({
  931  |           status: 200,
  932  |           contentType: 'text/event-stream',
  933  |           body:
  934  |             event(2, 'run_resumed', '运行已恢复', { phase: 'recovered' }) +
  935  |             event(3, 'assistant_delta', 'Agent 输出', { content: '恢复完成' }) +
  936  |             event(4, 'run_completed', '运行已完成', { phase: 'summary', progress: 100 }),
  937  |         })
  938  |       },
  939  |     )
  940  |     await page.goto('/agent')
  941  |     await openAgentPanel(page, 'right', 'log')
  942  |     await page.getByTestId('agent-message-input').fill('恢复运行')
  943  |     await page.getByTestId('agent-plan-submit').click()
  944  |     await expect(page.getByTestId('agent-recover-run-button')).toBeVisible()
  945  |     await page.getByTestId('agent-recover-run-button').click()
  946  |     await expect(page.getByTestId('agent-process-stream')).toContainText('运行已恢复', {
  947  |       timeout: 10_000,
  948  |     })
  949  |     await expect(page.getByTestId('agent-run-status')).toHaveText('completed', { timeout: 10_000 })
  950  |     expect(streamCalls).toBeGreaterThan(0)
  951  |   })
  952  | 
  953  |   test('管理员可查看死信 Job 并重放，普通面板不泄露 Provider 私有字段', async ({ page }) => {
  954  |     const state = await mockAgentApi(page)
  955  |     let replayed = false
  956  |     await page.unroute('**/api/agent/dead-letters*')
  957  |     await page.route('**/api/agent/dead-letters/dlq-1/replay**', async (route) => {
  958  |       replayed = true
  959  |       await route.fulfill({
  960  |         status: 200,
  961  |         contentType: 'application/json',
  962  |         body: JSON.stringify({
  963  |           id: 'dlq-1',
  964  |           run_id: 'run-dlq',
  965  |           user_id: 1,
  966  |           project_id: project.id,
  967  |           kind: 'visible_response',
  968  |           status: 'queued',
  969  |           idempotency_key: 'dlq-key',
  970  |           payload_json: {},
  971  |           result_json: {},
  972  |           error_type: 'ProviderTimeout',
  973  |           error_detail: 'replayed_by=1; reason=Agent 工作台管理员重放',
  974  |           attempt_count: 1,
  975  |           max_attempts: 1,
  976  |           available_at: session.created_at,
  977  |           lease_owner: null,
  978  |           lease_expires_at: null,
  979  |           cancel_requested_at: null,
  980  |           cancel_reason: null,
  981  |           created_at: session.created_at,
  982  |           started_at: session.created_at,
  983  |           finished_at: null,
  984  |         }),
  985  |       })
  986  |     })
  987  |     await page.route('**/api/agent/dead-letters?limit=*', async (route) => {
  988  |       await route.fulfill({
  989  |         status: 200,
  990  |         contentType: 'application/json',
  991  |         body: JSON.stringify(
  992  |           replayed
  993  |             ? []
  994  |             : [
  995  |                 {
  996  |                   id: 'dlq-1',
  997  |                   run_id: 'run-dlq',
  998  |                   user_id: 1,
  999  |                   project_id: project.id,
  1000 |                   kind: 'visible_response',
  1001 |                   status: 'dead_letter',
  1002 |                   idempotency_key: 'dlq-key',
  1003 |                   payload_json: {},
  1004 |                   result_json: {},
  1005 |                   error_type: 'ProviderTimeout',
  1006 |                   error_detail: 'temporary provider failure',
  1007 |                   attempt_count: 1,
  1008 |                   max_attempts: 1,
  1009 |                   available_at: session.created_at,
  1010 |                   lease_owner: null,
  1011 |                   lease_expires_at: null,
  1012 |                   cancel_requested_at: null,
  1013 |                   cancel_reason: null,
  1014 |                   created_at: session.created_at,
  1015 |                   started_at: session.created_at,
  1016 |                   finished_at: session.created_at,
  1017 |                 },
  1018 |               ],
  1019 |         ),
  1020 |       })
  1021 |     })
  1022 |     await page.goto('/agent')
  1023 |     await expandWorkspaceSection(page, 'agent-data-section')
  1024 |     await expect(page.getByTestId('agent-dead-letter-panel')).toContainText('ProviderTimeout')
> 1025 |     await expect(page.getByTestId('agent-dead-letter-panel')).toContainText(
       |                                                               ^ Error: expect(locator).toContainText(expected) failed
  1026 |       'temporary provider failure',
  1027 |     )
  1028 |     await page
  1029 |       .getByTestId('agent-dead-letter-panel')
  1030 |       .getByRole('button', { name: '重新排队' })
  1031 |       .click()
  1032 |     await expect(page.getByTestId('agent-process-stream')).toContainText('死信 Job 已重新排队')
  1033 |     expect(replayed).toBe(true)
  1034 |     expect(state).toBeTruthy()
  1035 |   })
  1036 | 
  1037 |   test('CARD-071 五视口布局测量与日志/聊天滚动隔离', async ({ page }, testInfo) => {
  1038 |     const state = await mockAgentApi(page)
  1039 |     state.messages = Array.from({ length: 80 }, (_, index) => ({
  1040 |       id: `layout-message-${index}`,
  1041 |       session_id: session.id,
  1042 |       role: index % 2 ? 'assistant' : 'user',
  1043 |       content: `布局验收历史消息 ${index}`,
  1044 |       created_at: session.created_at,
  1045 |     }))
  1046 |     await page.unroute('**/api/agent/sessions?project_id=*')
  1047 |     await page.route('**/api/agent/sessions?project_id=*', async (route) =>
  1048 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
  1049 |     )
  1050 |     const viewports = [
  1051 |       { width: 1920, height: 1080 },
  1052 |       { width: 1440, height: 900 },
  1053 |       { width: 1280, height: 800 },
  1054 |       { width: 960, height: 800 },
  1055 |       { width: 650, height: 844 },
  1056 |     ]
  1057 |     const measurements: Array<Record<string, unknown>> = []
  1058 | 
  1059 |     for (const viewport of viewports) {
  1060 |       await page.setViewportSize(viewport)
  1061 |       await page.goto('/agent')
  1062 |       await expect(page.getByTestId('agent-workspace')).toBeVisible()
  1063 |       await expect(page.getByTestId('agent-project-select')).toContainText('E2E 星河旧梦')
  1064 |       await expect(page.getByTestId('agent-message-list')).toBeVisible()
  1065 |       if (viewport.width <= 650) {
  1066 |         // Persisted desktop dual-open state normalizes to a single left drawer.
  1067 |         // Close it first so this branch tests an actual user-triggered opening.
  1068 |         if (await page.getByTestId('agent-left-panel').getAttribute('data-panel-open') === 'true') {
  1069 |           await page.getByTestId('agent-side-panel-close-left').click()
  1070 |         }
  1071 |       }
  1072 |       await openAgentPanel(page, 'left', 'project')
  1073 |       if (viewport.width <= 650) {
  1074 |         await expect(page.getByTestId('agent-side-panel-close-left')).toBeFocused()
  1075 |         await expect(page.getByTestId('agent-right-panel')).toBeHidden()
  1076 |         // A non-modal drawer leaves the opposite rail reachable without a trap.
  1077 |         await page.getByTestId('agent-rail-panel-right-log').focus()
  1078 |         await expect(page.getByTestId('agent-rail-panel-right-log')).toBeFocused()
  1079 |       }
  1080 |       await openAgentPanel(page, 'right', 'log')
  1081 |       await expect(page.getByTestId('agent-runtime-log-viewport')).toBeVisible()
  1082 |       if (viewport.width <= 650) {
  1083 |         await expect(page.getByTestId('agent-left-panel')).toBeHidden()
  1084 |         await expect(page.getByTestId('agent-side-panel-close-right')).toBeFocused()
  1085 |         await page.keyboard.press('Escape')
  1086 |         await expect(page.getByTestId('agent-right-panel')).toBeHidden()
  1087 |         await expect(page.getByTestId('agent-rail-panel-right-log')).toBeFocused()
  1088 |         await openAgentPanel(page, 'right', 'log')
  1089 |         await page.getByTestId('agent-side-panel-close-right').click()
  1090 |         await expect(page.getByTestId('agent-rail-panel-right-log')).toBeFocused()
  1091 |         await openAgentPanel(page, 'right', 'log')
  1092 |         await expect(page.locator('.agent-side-panel.agent-panel-open')).toHaveCount(1)
  1093 |         await expect(page.getByTestId('agent-runtime-log-viewport')).toBeVisible()
  1094 |       }
  1095 | 
  1096 |       const measurement = await page.evaluate(() => {
  1097 |         const query = (selector: string) => document.querySelector(selector)
  1098 |         const rect = (selector: string) => {
  1099 |           const element = query(selector)
  1100 |           if (!element) return null
  1101 |           const value = element.getBoundingClientRect()
  1102 |           return {
  1103 |             x: Math.round(value.x),
  1104 |             y: Math.round(value.y),
  1105 |             width: Math.round(value.width),
  1106 |             height: Math.round(value.height),
  1107 |           }
  1108 |         }
  1109 |         const style = (selector: string) => {
  1110 |           const element = query(selector)
  1111 |           if (!element) return null
  1112 |           const value = getComputedStyle(element)
  1113 |           return {
  1114 |             display: value.display,
  1115 |             overflowY: value.overflowY,
  1116 |             minWidth: value.minWidth,
  1117 |             minHeight: value.minHeight,
  1118 |             maxHeight: value.maxHeight,
  1119 |             gridTemplateColumns: value.gridTemplateColumns,
  1120 |           }
  1121 |         }
  1122 |         const logViewport = query('[data-testid="agent-runtime-log-viewport"]') as HTMLElement | null
  1123 |         const chatMessages = query('[data-testid="agent-message-list"]') as HTMLElement | null
  1124 |         if (logViewport) {
  1125 |           const logList = logViewport.querySelector('[data-testid="agent-process-stream"]') as HTMLElement | null
```