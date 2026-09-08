# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 恢复与 DLQ 浏览器交互 >> 管理员可查看死信 Job 并重放，普通面板不泄露 Provider 私有字段
- Location: e2e\agent-workspace.spec.ts:954:3

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: getByTestId('agent-dead-letter-panel')
Expected substring: "ProviderTimeout"
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toContainText" with timeout 5000ms
  - waiting for getByTestId('agent-dead-letter-panel')

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
      - button "项目" [pressed]
      - button "内容"
      - button "人物"
      - button "世界观": 世界
      - button "资料"
      - button "工具"
  - complementary:
    - strong: 项目
    - text: 项目资源与上下文
    - button "关闭项目资源面板": ×
    - group:
      - text: ▸ 项目与内容 2/8 章
      - heading "项目上下文" [level=2]
      - paragraph: Agent 只能操作当前项目。
      - text: 小说项目
      - combobox "小说项目":
        - option "请选择项目"
        - option "E2E 星河旧梦" [selected]
      - paragraph: 2/8 章已完成
      - button "打开写作台"
      - heading "项目内容树" [level=2]
      - paragraph: 仅加载章节元数据；点击章节后再按需读取版本预览。
      - list:
        - listitem:
          - strong: 第1卷 · 星河卷
          - list:
            - listitem:
              - button "第 1 章 · E2E 第一章 successful · 1280 字 E2E 轻量章节摘要"
    - group: ▸ 会话 1 个
    - group: ▸ 项目工具 1 项
    - group:
      - text: ▸ 数据与候选 按需展开
      - heading "Provider 健康状态" [level=2]
      - paragraph: 管理员可见的脱敏注册状态。
      - paragraph: 注册表：healthy · 1 个 Provider
      - list:
        - listitem:
          - strong: project-read
          - text: loaded 1 个工具 · builtin · v1.0.0
      - heading "当前 Run Provider 调用" [level=2]
      - paragraph: 只显示本次运行的脱敏计数，不展示请求或输出正文。
      - paragraph: 暂无选中的 Run。
      - heading "项目 Provider 累计" [level=2]
      - paragraph: 跨 Run 的脱敏调用摘要；不展示请求或输出正文。
      - paragraph: "Agent 请求失败: HTTP 500"
      - heading "持久化 Agent Job" [level=2]
      - paragraph: 已接入独立 Worker；未启动时 Job 会保留在队列，重启后可继续领取。
      - list:
        - listitem: 暂无持久化 Job。
      - heading "项目实体上下文" [level=2]
      - paragraph: 选择最小实体引用；Agent 再通过受控能力读取摘要。
      - paragraph: "Agent 请求失败: HTTP 500"
      - group: ▸ 项目成员 共享与权限
  - heading "创作对话" [level=2]
  - paragraph: 展示目标、公开轨迹、Provider reasoning、Assistant 正文、工具调用和结果摘要。
  - text: 会话：E2E Agent 会话
  - paragraph: 请选择项目并发送目标，Agent 的历史消息会显示在这里。
  - region "当前 Agent 上下文": 当前上下文 项目：E2E 星河旧梦
  - text: 给小说 Agent 的指令
  - textbox "给小说 Agent 的指令":
    - /placeholder: 例如：检查当前项目第三章的质量风险，并给出不改正文的计划
  - text: 消息会写入当前会话，并接收真实运行事件。
  - button "发送给 Agent" [disabled]
  - complementary:
    - toolbar "运行信息面板":
      - button "运行日志": 日志
      - button "运行详情": 运行
      - button "进度"
      - button "结果产物": 产物
      - button "质量"
- region "通知"
```

# Test source

```ts
  925  |           ...state.run,
  926  |           status: 'completed',
  927  |           current_phase: 'summary',
  928  |           progress: 100,
  929  |           finished_at: session.created_at,
  930  |         }
  931  |         await route.fulfill({
  932  |           status: 200,
  933  |           contentType: 'text/event-stream',
  934  |           body:
  935  |             event(2, 'run_resumed', '运行已恢复', { phase: 'recovered' }) +
  936  |             event(3, 'assistant_delta', 'Agent 输出', { content: '恢复完成' }) +
  937  |             event(4, 'run_completed', '运行已完成', { phase: 'summary', progress: 100 }),
  938  |         })
  939  |       },
  940  |     )
  941  |     await page.goto('/agent')
  942  |     await openAgentPanel(page, 'right', 'log')
  943  |     await page.getByTestId('agent-message-input').fill('恢复运行')
  944  |     await page.getByTestId('agent-plan-submit').click()
  945  |     await expect(page.getByTestId('agent-recover-run-button')).toBeVisible()
  946  |     await page.getByTestId('agent-recover-run-button').click()
  947  |     await expect(page.getByTestId('agent-process-stream')).toContainText('运行已恢复', {
  948  |       timeout: 10_000,
  949  |     })
  950  |     await expect(page.getByTestId('agent-run-status')).toHaveText('completed', { timeout: 10_000 })
  951  |     expect(streamCalls).toBeGreaterThan(0)
  952  |   })
  953  | 
  954  |   test('管理员可查看死信 Job 并重放，普通面板不泄露 Provider 私有字段', async ({ page }) => {
  955  |     const state = await mockAgentApi(page)
  956  |     let replayed = false
  957  |     await unrouteAgentFixture(page, '**/api/agent/dead-letters*')
  958  |     await routeAgentFixture(page, '**/api/agent/dead-letters/dlq-1/replay**', async (route) => {
  959  |       replayed = true
  960  |       await route.fulfill({
  961  |         status: 200,
  962  |         contentType: 'application/json',
  963  |         body: JSON.stringify({
  964  |           id: 'dlq-1',
  965  |           run_id: 'run-dlq',
  966  |           user_id: 1,
  967  |           project_id: project.id,
  968  |           kind: 'visible_response',
  969  |           status: 'queued',
  970  |           idempotency_key: 'dlq-key',
  971  |           payload_json: {},
  972  |           result_json: {},
  973  |           error_type: 'ProviderTimeout',
  974  |           error_detail: 'replayed_by=1; reason=Agent 工作台管理员重放',
  975  |           attempt_count: 1,
  976  |           max_attempts: 1,
  977  |           available_at: session.created_at,
  978  |           lease_owner: null,
  979  |           lease_expires_at: null,
  980  |           cancel_requested_at: null,
  981  |           cancel_reason: null,
  982  |           created_at: session.created_at,
  983  |           started_at: session.created_at,
  984  |           finished_at: null,
  985  |         }),
  986  |       })
  987  |     })
  988  |     await routeAgentFixture(page, '**/api/agent/dead-letters?limit=*', async (route) => {
  989  |       await route.fulfill({
  990  |         status: 200,
  991  |         contentType: 'application/json',
  992  |         body: JSON.stringify(
  993  |           replayed
  994  |             ? []
  995  |             : [
  996  |                 {
  997  |                   id: 'dlq-1',
  998  |                   run_id: 'run-dlq',
  999  |                   user_id: 1,
  1000 |                   project_id: project.id,
  1001 |                   kind: 'visible_response',
  1002 |                   status: 'dead_letter',
  1003 |                   idempotency_key: 'dlq-key',
  1004 |                   payload_json: {},
  1005 |                   result_json: {},
  1006 |                   error_type: 'ProviderTimeout',
  1007 |                   error_detail: 'temporary provider failure',
  1008 |                   attempt_count: 1,
  1009 |                   max_attempts: 1,
  1010 |                   available_at: session.created_at,
  1011 |                   lease_owner: null,
  1012 |                   lease_expires_at: null,
  1013 |                   cancel_requested_at: null,
  1014 |                   cancel_reason: null,
  1015 |                   created_at: session.created_at,
  1016 |                   started_at: session.created_at,
  1017 |                   finished_at: session.created_at,
  1018 |                 },
  1019 |               ],
  1020 |         ),
  1021 |       })
  1022 |     })
  1023 |     await page.goto('/agent')
  1024 |     await expandWorkspaceSection(page, 'agent-data-section')
> 1025 |     await expect(page.getByTestId('agent-dead-letter-panel')).toContainText('ProviderTimeout')
       |                                                               ^ Error: expect(locator).toContainText(expected) failed
  1026 |     await expect(page.getByTestId('agent-dead-letter-panel')).toContainText(
  1027 |       'temporary provider failure',
  1028 |     )
  1029 |     await page
  1030 |       .getByTestId('agent-dead-letter-panel')
  1031 |       .getByRole('button', { name: '重新排队' })
  1032 |       .click()
  1033 |     await expect(page.getByTestId('agent-process-stream')).toContainText('死信 Job 已重新排队')
  1034 |     expect(replayed).toBe(true)
  1035 |     expect(state).toBeTruthy()
  1036 |   })
  1037 | 
  1038 |   test('CARD-071 五视口布局测量与日志/聊天滚动隔离', async ({ page }, testInfo) => {
  1039 |     const state = await mockAgentApi(page)
  1040 |     state.messages = Array.from({ length: 80 }, (_, index) => ({
  1041 |       id: `layout-message-${index}`,
  1042 |       session_id: session.id,
  1043 |       role: index % 2 ? 'assistant' : 'user',
  1044 |       content: `布局验收历史消息 ${index}`,
  1045 |       created_at: session.created_at,
  1046 |     }))
  1047 |     await unrouteAgentFixture(page, '**/api/agent/sessions?project_id=*')
  1048 |     await routeAgentFixture(page, '**/api/agent/sessions?project_id=*', async (route) =>
  1049 |       route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
  1050 |     )
  1051 |     const viewports = [
  1052 |       { width: 1920, height: 1080 },
  1053 |       { width: 1440, height: 900 },
  1054 |       { width: 1280, height: 800 },
  1055 |       { width: 960, height: 800 },
  1056 |       { width: 650, height: 844 },
  1057 |     ]
  1058 |     const measurements: Array<Record<string, unknown>> = []
  1059 | 
  1060 |     for (const viewport of viewports) {
  1061 |       await page.setViewportSize(viewport)
  1062 |       await page.goto('/agent')
  1063 |       await expect(page.getByTestId('agent-workspace')).toBeVisible()
  1064 |       await expect(page.getByTestId('agent-project-select')).toContainText('E2E 星河旧梦')
  1065 |       await expect(page.getByTestId('agent-message-list')).toBeVisible()
  1066 |       if (viewport.width <= 650) {
  1067 |         // Persisted desktop dual-open state normalizes to a single left drawer.
  1068 |         // Close it first so this branch tests an actual user-triggered opening.
  1069 |         if (await page.getByTestId('agent-left-panel').getAttribute('data-panel-open') === 'true') {
  1070 |           await page.getByTestId('agent-side-panel-close-left').click()
  1071 |         }
  1072 |       }
  1073 |       await openAgentPanel(page, 'left', 'project')
  1074 |       if (viewport.width <= 650) {
  1075 |         await expect(page.getByTestId('agent-side-panel-close-left')).toBeFocused()
  1076 |         await expect(page.getByTestId('agent-right-panel')).toBeHidden()
  1077 |         // A non-modal drawer leaves the opposite rail reachable without a trap.
  1078 |         await page.getByTestId('agent-rail-panel-right-log').focus()
  1079 |         await expect(page.getByTestId('agent-rail-panel-right-log')).toBeFocused()
  1080 |       }
  1081 |       await openAgentPanel(page, 'right', 'log')
  1082 |       await expect(page.getByTestId('agent-runtime-log-viewport')).toBeVisible()
  1083 |       if (viewport.width <= 650) {
  1084 |         await expect(page.getByTestId('agent-left-panel')).toBeHidden()
  1085 |         await expect(page.getByTestId('agent-side-panel-close-right')).toBeFocused()
  1086 |         await page.keyboard.press('Escape')
  1087 |         await expect(page.getByTestId('agent-right-panel')).toBeHidden()
  1088 |         await expect(page.getByTestId('agent-rail-panel-right-log')).toBeFocused()
  1089 |         await openAgentPanel(page, 'right', 'log')
  1090 |         await page.getByTestId('agent-side-panel-close-right').click()
  1091 |         await expect(page.getByTestId('agent-rail-panel-right-log')).toBeFocused()
  1092 |         await openAgentPanel(page, 'right', 'log')
  1093 |         await expect(page.locator('.agent-side-panel.agent-panel-open')).toHaveCount(1)
  1094 |         await expect(page.getByTestId('agent-runtime-log-viewport')).toBeVisible()
  1095 |       }
  1096 | 
  1097 |       const measurement = await page.evaluate(() => {
  1098 |         const query = (selector: string) => document.querySelector(selector)
  1099 |         const rect = (selector: string) => {
  1100 |           const element = query(selector)
  1101 |           if (!element) return null
  1102 |           const value = element.getBoundingClientRect()
  1103 |           return {
  1104 |             x: Math.round(value.x),
  1105 |             y: Math.round(value.y),
  1106 |             width: Math.round(value.width),
  1107 |             height: Math.round(value.height),
  1108 |           }
  1109 |         }
  1110 |         const style = (selector: string) => {
  1111 |           const element = query(selector)
  1112 |           if (!element) return null
  1113 |           const value = getComputedStyle(element)
  1114 |           return {
  1115 |             display: value.display,
  1116 |             overflowY: value.overflowY,
  1117 |             minWidth: value.minWidth,
  1118 |             minHeight: value.minHeight,
  1119 |             maxHeight: value.maxHeight,
  1120 |             gridTemplateColumns: value.gridTemplateColumns,
  1121 |           }
  1122 |         }
  1123 |         const logViewport = query('[data-testid="agent-runtime-log-viewport"]') as HTMLElement | null
  1124 |         const chatMessages = query('[data-testid="agent-message-list"]') as HTMLElement | null
  1125 |         if (logViewport) {
```