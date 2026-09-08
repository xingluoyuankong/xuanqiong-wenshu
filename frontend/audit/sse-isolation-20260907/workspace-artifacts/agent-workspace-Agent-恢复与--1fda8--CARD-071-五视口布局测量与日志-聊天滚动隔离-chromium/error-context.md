# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: agent-workspace.spec.ts >> Agent 恢复与 DLQ 浏览器交互 >> CARD-071 五视口布局测量与日志/聊天滚动隔离
- Location: e2e\agent-workspace.spec.ts:1037:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('agent-message-list')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByTestId('agent-message-list')

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
  1025 |     await expect(page.getByTestId('agent-dead-letter-panel')).toContainText(
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
> 1064 |       await expect(page.getByTestId('agent-message-list')).toBeVisible()
       |                                                            ^ Error: expect(locator).toBeVisible() failed
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
  1126 |           if (logList) {
  1127 |             logList.innerHTML = Array.from({ length: 80 }, (_, index) => `<p>布局验收日志 ${index}</p>`).join('')
  1128 |           }
  1129 |         }
  1130 |         const chatScrollTopBefore = chatMessages?.scrollTop || 0
  1131 |         const logScrollHeight = logViewport?.scrollHeight || 0
  1132 |         const logClientHeight = logViewport?.clientHeight || 0
  1133 |         if (logViewport) logViewport.scrollTop = Math.max(0, logScrollHeight - logClientHeight)
  1134 |         const logScrollTopAfter = logViewport?.scrollTop || 0
  1135 |         const chatScrollTopAfterLog = chatMessages?.scrollTop || 0
  1136 |         const logScrollTopBeforeChat = logViewport?.scrollTop || 0
  1137 |         const chatScrollHeight = chatMessages?.scrollHeight || 0
  1138 |         const chatClientHeight = chatMessages?.clientHeight || 0
  1139 |         if (chatMessages) chatMessages.scrollTop = Math.max(0, chatScrollHeight - chatClientHeight)
  1140 |         const chatScrollTopAfter = chatMessages?.scrollTop || 0
  1141 |         const logScrollTopAfterChat = logViewport?.scrollTop || 0
  1142 |         return {
  1143 |           layout: rect('.agent-layout'),
  1144 |           sidebar: rect('.agent-sidebar'),
  1145 |           main: rect('.agent-main'),
  1146 |           activity: rect('.agent-activity'),
  1147 |           chat: rect('[data-testid="agent-chat-column"]'),
  1148 |           logViewport: rect('[data-testid="agent-runtime-log-viewport"]'),
  1149 |           layoutStyle: style('.agent-layout'),
  1150 |           logStyle: style('[data-testid="agent-runtime-log-viewport"]'),
  1151 |           logScrollHeight,
  1152 |           logClientHeight,
  1153 |           logScrollTopAfter,
  1154 |           chatScrollTopBefore,
  1155 |           chatScrollTopAfterLog,
  1156 |           chatScrollHeight,
  1157 |           chatClientHeight,
  1158 |           chatScrollTopAfter,
  1159 |           logScrollTopBeforeChat,
  1160 |           logScrollTopAfterChat,
  1161 |           horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
  1162 |         }
  1163 |       })
  1164 | 
```