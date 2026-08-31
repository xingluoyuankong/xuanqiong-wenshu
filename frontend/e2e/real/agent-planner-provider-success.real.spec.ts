import { expect, request, test } from '@playwright/test'

const backendBaseUrl = 'http://127.0.0.1:' + (process.env.XQ_AGENT_E2E_BACKEND_PORT || '18023')
const username = 'agent-provider-e2e-admin'
const password = 'AgentProviderE2E-Only-2026!'
const tokenStorageKey = 'xuanqiong.auth.access_token'

type ProvisionedProject = {
  token: string
  projectId: string
  projectTitle: string
}

const containsHiddenReasoning = (value: unknown): boolean => {
  if (Array.isArray(value)) return value.some(containsHiddenReasoning)
  if (!value || typeof value !== 'object') return false
  return Object.entries(value as Record<string, unknown>).some(([key, item]) => {
    const normalized = key.toLowerCase()
    return normalized.includes('reasoning') || normalized.includes('thought') || normalized === 'cot' || normalized === 'chain_of_thought' || containsHiddenReasoning(item)
  })
}

async function provisionIsolatedProject(): Promise<ProvisionedProject> {
  const api = await request.newContext({ baseURL: backendBaseUrl })
  try {
    const login = await api.post('/api/auth/login', { form: { username, password } })
    expect(login.status()).toBe(200)
    const token = String((await login.json()).access_token || '')
    expect(token).not.toBe('')
    const projectTitle = '隔离 Planner Provider 浏览器 E2E ' + Date.now()
    const project = await api.post('/api/novels', {
      headers: { Authorization: 'Bearer ' + token },
      data: {
        title: projectTitle,
        initial_prompt: '隔离项目：只验证真实 Provider Planner 的动态只读能力选择和公开事件。',
      },
    })
    expect(project.status()).toBe(201)
    const payload = await project.json()
    return { token, projectId: String(payload.id), projectTitle }
  } finally {
    await api.dispose()
  }
}

test.describe('真实 Provider Planner 浏览器闭环', () => {
  test('浏览器不传 tools，Provider Planner 动态选择项目能力并持久化公开事实', async ({ page }) => {
    const fixture = await provisionIsolatedProject()
    const api = await request.newContext({ baseURL: backendBaseUrl })
    try {
      const headers = { Authorization: 'Bearer ' + fixture.token }
      await page.addInitScript(([key, token]) => window.localStorage.setItem(key, token), [tokenStorageKey, fixture.token])
      await page.goto('/agent')
      await expect(page.getByTestId('agent-workspace')).toBeVisible()
      await expect(page.getByTestId('agent-project-select')).toContainText(fixture.projectTitle)
      await expect(page.getByTestId('agent-session-status')).toContainText('会话：')

      await page.getByTestId('agent-message-input').fill('请动态选择项目内只读能力，确认当前项目上下文可用并给出一句简短可见摘要；不得生成、改写或接受任何小说正文。')
      await page.getByTestId('agent-plan-submit').click()

      await expect(page.getByTestId('agent-public-work-summary')).toBeVisible({ timeout: 120_000 })
      await expect.poll(async () => page.getByTestId('agent-plan-panel').locator('li').count(), { timeout: 120_000 }).toBeGreaterThan(0)
      await expect(page.getByTestId('agent-run-status')).toHaveText('completed', { timeout: 120_000 })
      await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 回复已完成', { timeout: 120_000 })

      let sessionId = ''
      let runId = ''
      await expect.poll(async () => {
        const sessions = await api.get('/api/agent/sessions?project_id=' + encodeURIComponent(fixture.projectId), { headers })
        if (sessions.status() !== 200) return ''
        const items = await sessions.json()
        sessionId = String(items[0]?.id || '')
        if (!sessionId) return ''
        const detail = await api.get('/api/agent/sessions/' + sessionId, { headers })
        if (detail.status() !== 200) return ''
        const payload = await detail.json()
        const run = (payload.runs || []).at(-1)
        runId = String(run?.id || '')
        return run?.status === 'completed' ? runId : ''
      }, { timeout: 120_000 }).not.toBe('')

      const [planResponse, revisionResponse, provenanceResponse, summaryResponse, eventsResponse] = await Promise.all([
        api.get('/api/agent/runs/' + runId + '/plan', { headers }),
        api.get('/api/agent/runs/' + runId + '/plan-revision', { headers }),
        api.get('/api/agent/runs/' + runId + '/provider-provenance', { headers }),
        api.get('/api/agent/runs/' + runId + '/conversation-summaries', { headers }),
        api.get('/api/agent/sessions/' + sessionId + '/runs/' + runId + '/events', { headers }),
      ])
      expect(planResponse.status()).toBe(200)
      expect(revisionResponse.status()).toBe(200)
      expect(provenanceResponse.status()).toBe(200)
      expect(summaryResponse.status()).toBe(200)
      expect(eventsResponse.status()).toBe(200)

      const plan = await planResponse.json()
      const revision = await revisionResponse.json()
      const provenance = await provenanceResponse.json()
      const summaries = await summaryResponse.json()
      const events = await eventsResponse.json()
      expect(plan.provider_called).toBe(true)
      expect(plan.planner_fallback_reason).toBeFalsy()
      expect(plan.steps.length).toBeGreaterThan(0)
      expect(revision.plan_json.provider_called).toBe(true)
      expect(provenance.planner_provider_called).toBe(true)
      expect(provenance.planner_provider_fallback_reason).toBeFalsy()
      expect(provenance.response_provider_called).toBe(true)
      expect(provenance.response_provider_fallback_reason).toBeFalsy()
      expect(provenance.candidate_writer_provider_called).toBeNull()
      expect(summaries.length).toBeGreaterThan(0)
      expect(events.some((item: { event_type: string }) => item.event_type === 'plan_created')).toBe(true)
      expect(events.some((item: { event_type: string }) => item.event_type === 'public_work_summary')).toBe(true)
      expect(events.some((item: { event_type: string }) => item.event_type === 'assistant_delta')).toBe(true)
      expect(events.every((item: { data_json?: unknown }) => !containsHiddenReasoning(item.data_json || {}))).toBe(true)

      const firstSequence = Number(events[0]?.sequence || 0)
      expect(firstSequence).toBeGreaterThan(0)
      const replay = await api.get('/api/agent/sessions/' + sessionId + '/runs/' + runId + '/events?after_sequence=' + firstSequence, { headers })
      expect(replay.status()).toBe(200)
      const replayEvents = await replay.json()
      expect(replayEvents.length).toBeGreaterThan(0)
      expect(replayEvents.every((item: { sequence: number }) => item.sequence > firstSequence)).toBe(true)
    } finally {
      await api.dispose()
    }
  })
})
