import { expect, request, test } from '@playwright/test'

const backendBaseUrl = 'http://127.0.0.1:' + (process.env.XQ_AGENT_E2E_BACKEND_PORT || '18013')
const username = 'agent-e2e-admin'
const password = 'AgentE2E-Only-2026!'
const tokenStorageKey = 'xuanqiong.auth.access_token'

type ProvisionedProject = {
  token: string
  projectId: string
  projectTitle: string
}

async function provisionIsolatedProject(): Promise<ProvisionedProject> {
  const api = await request.newContext({ baseURL: backendBaseUrl })
  try {
    const login = await api.post('/api/auth/login', {
      form: { username, password },
    })
    expect(login.status()).toBe(200)
    const token = String((await login.json()).access_token || '')
    expect(token).not.toBe('')
    const projectTitle = '隔离 Agent 浏览器 E2E ' + Date.now()
    const project = await api.post('/api/novels', {
      headers: { Authorization: 'Bearer ' + token },
      data: {
        title: projectTitle,
        initial_prompt: '隔离测试项目：只验证 Agent 控制面和可见事件，不调用真实 Provider，不生成用户正文。',
      },
    })
    expect(project.status()).toBe(201)
    const payload = await project.json()
    expect(payload.id).toBeTruthy()
    return { token, projectId: String(payload.id), projectTitle }
  } finally {
    await api.dispose()
  }
}

test.describe('真实 FastAPI + SQLite + 鉴权 Agent 工作台', () => {
  test('浏览器通过真实 JWT、Vite 代理和 FastAPI 读取隔离项目并恢复会话', async ({ page }) => {
    const fixture = await provisionIsolatedProject()
    await page.addInitScript(([key, token]) => window.localStorage.setItem(key, token), [tokenStorageKey, fixture.token])

    await page.goto('/agent')
    await expect(page.getByTestId('agent-workspace')).toBeVisible()
    await expect(page.getByTestId('agent-project-select')).toContainText(fixture.projectTitle)
    await expect(page.getByTestId('agent-tool-list')).toContainText('project.context')
    await expect(page.getByTestId('agent-session-status')).toContainText('会话：')

    await page.reload()
    await expect(page.getByTestId('agent-session-status')).toContainText('会话：')
  })

  test('真实 Agent API 执行只读工具，浏览器接收真实 SSE 过程和持久化 step', async ({ page }) => {
    const fixture = await provisionIsolatedProject()
    await page.addInitScript(([key, token]) => window.localStorage.setItem(key, token), [tokenStorageKey, fixture.token])

    await page.goto('/agent')
    await expect(page.getByTestId('agent-session-status')).toContainText('会话：')
    await page.getByTestId('agent-message-input').fill('检查当前项目上下文；本次隔离测试不得调用真实 Provider。')
    await page.getByTestId('agent-plan-submit').click()

    await expect(page.getByTestId('agent-plan-panel')).toContainText('project.context', { timeout: 30_000 })
    await expect(page.getByTestId('agent-public-work-summary')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('agent-public-work-summary')).toContainText('Agent 当前工作')
    await expect(page.getByTestId('agent-process-stream')).toContainText('project.context 已完成', { timeout: 30_000 })
    await expect(page.getByTestId('agent-step-panel')).toContainText('已完成', { timeout: 30_000 })
    await expect(page.getByTestId('agent-run-status')).toHaveText('failed', { timeout: 30_000 })
    await expect(page.getByTestId('agent-process-stream')).toContainText('Agent Provider 回复失败')
  })

  test('真实 API 为写入计划创建并决定审批，且不会在未执行时写入正文', async () => {
    const fixture = await provisionIsolatedProject()
    const api = await request.newContext({ baseURL: backendBaseUrl })
    try {
      const headers = { Authorization: 'Bearer ' + fixture.token }
      const sessionResponse = await api.post('/api/agent/sessions', {
        headers,
        data: { project_id: fixture.projectId, title: '隔离写入审批会话' },
      })
      expect(sessionResponse.status()).toBe(201)
      const session = await sessionResponse.json()

      const messageResponse = await api.post('/api/agent/sessions/' + session.id + '/messages', {
        headers,
        data: {
          content: '仅创建第三章候选写入计划，等待人工审批。',
          tools: ['chapter.generate'],
          arguments: { chapter_number: 3 },
        },
      })
      expect(messageResponse.status()).toBe(201)
      const message = await messageResponse.json()
      expect(message.provider_called).toBe(false)
      expect(message.run.status).toBe('planning')
      expect(message.plan.steps).toEqual([])
      expect(message.approvals).toEqual([])
      expect(message.execution_job.kind).toBe('agent_execution')

      let approvals: Array<{ id: string; status: string }> = []
      await expect.poll(async () => {
        const approvalResponse = await api.get('/api/agent/runs/' + message.run.id + '/approvals', { headers })
        if (approvalResponse.status() !== 200) return -1
        approvals = await approvalResponse.json()
        return approvals.length
      }, { timeout: 30_000 }).toBe(1)
      expect(approvals[0].status).toBe('pending')

      const decision = await api.post('/api/agent/approvals/' + approvals[0].id + '/decision', {
        headers,
        data: { approved: true, reason: '隔离 E2E 只验证审批状态，不执行 Provider 写入。' },
      })
      const decisionPayload = await decision.json()
      expect(decision.status(), JSON.stringify(decisionPayload)).toBe(200)
      expect(decisionPayload.status).toBe('approved')

      const artifacts = await api.get('/api/agent/runs/' + message.run.id + '/artifacts', { headers })
      expect(artifacts.status()).toBe(200)
      expect(await artifacts.json()).toEqual([])
    } finally {
      await api.dispose()
    }
  })

  test('浏览器点击暂停、继续与取消当前 selected Run，并读取真实命令状态', async ({ page }) => {
    const fixture = await provisionIsolatedProject()
    const api = await request.newContext({ baseURL: backendBaseUrl })
    try {
      const headers = { Authorization: 'Bearer ' + fixture.token }
      const sessionResponse = await api.post('/api/agent/sessions', {
        headers,
        data: { project_id: fixture.projectId, title: '隔离运行控制会话' },
      })
      expect(sessionResponse.status()).toBe(201)
      const session = await sessionResponse.json()

      const messageResponse = await api.post('/api/agent/sessions/' + session.id + '/messages', {
        headers,
        data: {
          content: '仅创建第三章候选写入计划，保留在审批等待状态。',
          tools: ['chapter.generate'],
          arguments: { chapter_number: 3 },
        },
      })
      expect(messageResponse.status()).toBe(201)
      const message = await messageResponse.json()

      let approvals: Array<{ id: string; status: string }> = []
      await expect.poll(async () => {
        const approvalResponse = await api.get('/api/agent/runs/' + message.run.id + '/approvals', { headers })
        if (approvalResponse.status() !== 200) return -1
        approvals = await approvalResponse.json()
        return approvals.length
      }, { timeout: 30_000 }).toBe(1)
      expect(approvals[0].status).toBe('pending')

      await page.addInitScript(
        ([key, token]) => window.localStorage.setItem(key, token),
        [tokenStorageKey, fixture.token],
      )
      await page.goto(
        '/agent?project_id=' + fixture.projectId + '&session_id=' + session.id + '&run_id=' + message.run.id,
      )
      await expect(page.getByTestId('agent-run-status')).toHaveText(/planning|awaiting_approval|running/, {
        timeout: 30_000,
      })
      await expect(page.getByTestId('agent-pause-run-button')).toBeVisible({ timeout: 30_000 })

      await page.getByTestId('agent-pause-run-button').click()
      await expect(page.getByTestId('agent-run-status')).toHaveText('paused', { timeout: 30_000 })
      await expect(page.getByTestId('agent-resume-run-button')).toBeVisible()

      await page.getByTestId('agent-resume-run-button').click()
      await expect(page.getByTestId('agent-run-status')).toHaveText(/running|awaiting_approval/, { timeout: 30_000 })
      await expect(page.getByTestId('agent-cancel-run-button')).toBeVisible()

      await page.getByTestId('agent-cancel-run-button').click()
      await expect(page.getByTestId('agent-run-status')).toHaveText('cancelled', { timeout: 30_000 })
      await expect(page.getByTestId('agent-run-control-bar')).toHaveCount(0)

      const commandsResponse = await api.get('/api/agent/runs/' + message.run.id + '/commands', { headers })
      expect(commandsResponse.status()).toBe(200)
      const commands = await commandsResponse.json()
      expect(commands.map((item: { command_type: string; status: string }) => [item.command_type, item.status])).toEqual([
        ['pause', 'applied'],
        ['resume', 'applied'],
        ['cancel', 'applied'],
      ])
    } finally {
      await api.dispose()
    }
  })


})

