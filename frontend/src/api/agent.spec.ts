import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AgentAPI, buildAgentRunCommandIdempotencyKey, type AgentJob } from './agent'

const fetchMock = vi.fn()

vi.mock('@/stores/auth', () => ({
  buildAuthHeaders: () => new Headers({ Authorization: 'Bearer test' }),
}))

describe('AgentAPI timeline and artifact diff', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('请求管理员 Provider 健康状态', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ registry_status: 'healthy', provider_count: 1, providers: [] }) })
    await AgentAPI.listToolHealth()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/tools/health')
  })

  it('读取能力目录 generation 和工具来源字段', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ generation: 4, count: 1, tools: [{ name: 'project.context', description: '读取项目', risk_level: 'read', requires_confirmation: false, supports_stream: false, provider_id: 'project-read', provider_version: '1.0.0', source: 'builtin' }] }) })
    const result = await AgentAPI.listTools()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/tools')
    expect(result.generation).toBe(4)
    expect(result.tools[0]).toMatchObject({ provider_id: 'project-read', provider_version: '1.0.0', source: 'builtin' })
  })

  it('只读死信 GET 保留失败对账投影，不发起重放', async () => {
    const publicJob = {
      id: 'dead-read', kind: 'agent_continuation', status: 'dead_letter',
      terminal_status: 'dead_letter', recovery_status: 'failure_reconciled', result_json: {},
      error_type: 'RuntimeError', error_detail: null,
    }
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => [publicJob] })
    expect(await AgentAPI.listDeadLetters()).toEqual([publicJob])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/agent/dead-letters?limit=100')
    expect(fetchMock.mock.calls[0][1].method || 'GET').toBe('GET')
  })

  it('Run state 的嵌套 Job 保留 false 与后续审批标记，不覆盖 Run 终态', async () => {
    const publicJob = {
      id: 'nested-continuation', kind: 'agent_continuation', status: 'succeeded',
      attempt_count: 1, max_attempts: 3, terminal_status: 'succeeded', recovery_status: 'not_recorded',
      result_json: { continuation_completed: false, pending_approval: true, continuation_acknowledged: false },
      finished_at: '2026-09-07T00:00:02Z',
    }
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      status: 'awaiting_approval', terminal_status: null, jobs: [publicJob],
    }) })
    const state = await AgentAPI.getRunState('run/nested')
    expect(state.jobs[0]).toEqual(publicJob)
    expect(state.jobs[0].result_json.continuation_completed).toBe(false)
    expect(state.jobs[0].recovery_status).toBe('not_recorded')
    expect(state.terminal_status).toBeNull()
    expect(state.status).toBe('awaiting_approval')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/agent/runs/run%2Fnested/state')
    expect(fetchMock.mock.calls[0][1].method || 'GET').toBe('GET')
  })

  it('读取公共 Job 投影的终态、恢复状态和安全 result_json 白名单', async () => {
    const publicJob: AgentJob = {
      id: 'continuation-1',
      run_id: 'run-1',
      correlation_id: 'correlation-1',
      user_id: 1,
      project_id: 'project-1',
      kind: 'agent_continuation',
      status: 'succeeded',
      idempotency_key: '',
      payload_json: {},
      result_json: {
        continuation_completed: true,
        continuation_acknowledged: true,
      },
      error_type: null,
      error_detail: null,
      attempt_count: 1,
      max_attempts: 3,
      available_at: '2026-09-07T00:00:00Z',
      lease_owner: null,
      lease_expires_at: null,
      lease_generation: 0,
      cancel_requested_at: null,
      cancel_reason: null,
      created_at: '2026-09-07T00:00:00Z',
      started_at: '2026-09-07T00:00:01Z',
      finished_at: '2026-09-07T00:00:02Z',
      terminal_status: 'succeeded',
      recovery_status: 'continuation_completed',
    }
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => [publicJob] })

    const result = await AgentAPI.listJobs('project-1', 'succeeded')

    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/agent/jobs?project_id=project-1&status=succeeded')
    expect(result[0]).toMatchObject({
      terminal_status: 'succeeded',
      recovery_status: 'continuation_completed',
      result_json: {
        continuation_completed: true,
        continuation_acknowledged: true,
      },
    })
  })

  it('请求项目级 Provider 摘要并编码项目、时间窗口和有界 limit', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        project_id: 'project/a',
        run_count: 0,
        attempt_count: 0,
        succeeded_attempts: 0,
        failed_attempts: 0,
        fallback_attempts: 0,
        first_token_attempts: 0,
        digest_attempts: 0,
        selected_attempts: 0,
        last_error_category: null,
        latest_attempt_at: null,
        runs: [],
      }),
    })
    await AgentAPI.getProjectProviderUsageSummary('project/a', {
      since: '2026-09-03T00:00:00Z',
      limit: 999,
    })
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/agent/projects/project%2Fa/provider-usage-summary?')
    expect(String(url)).toContain('since=2026-09-03T00%3A00%3A00Z')
    expect(String(url)).toContain('limit=100')
  })

  it('按项目和事件筛选跨会话时间线并保留分页参数', async () => {
    await AgentAPI.listTimeline({ projectId: 'project-a', eventType: 'tool_call_completed', runStatus: 'completed', toolName: 'project.context', offset: 20, limit: 40 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/agent/timeline?')
    expect(String(url)).toContain('project_id=project-a')
    expect(String(url)).toContain('event_type=tool_call_completed')
    expect(String(url)).toContain('run_status=completed')
    expect(String(url)).toContain('tool_name=project.context')
    expect(String(url)).toContain('offset=20')
    expect(String(url)).toContain('limit=40')
    expect(init.credentials).toBe('include')
  })

  it('请求 artifact 对指定 ChapterVersion 的差异并返回深链字段', async () => {
    await AgentAPI.getArtifactVersionDiff('artifact-a', { projectId: 'project-a', chapterNumber: 7, versionId: 42 })
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/agent/artifacts/artifact-a/chapter-version-diff?')
    expect(String(url)).toContain('project_id=project-a')
    expect(String(url)).toContain('chapter_number=7')
    expect(String(url)).toContain('version_id=42')
  })

  it('请求 artifact 的关系化质量结果和谱系事实', async () => {
    await AgentAPI.getArtifactQuality('artifact-a')
    await AgentAPI.getArtifactLineage('artifact-a')
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/agent/artifacts/artifact-a/quality')
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/agent/artifacts/artifact-a/lineage')
  })

  it('请求 artifact 的规范化 quality blocker 定位数据', async () => {
    await AgentAPI.listArtifactQualityBlockers('artifact-a')
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/artifacts/artifact-a/quality-blockers')
  })


  it('请求统一 Agent 审计账本并保留 artifact/source version 筛选', async () => {
    await AgentAPI.listAudit({ projectId: 'project-a', artifactId: 'artifact-a', sourceVersionId: 11, offset: 10, limit: 25 })
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/agent/audit?')
    expect(String(url)).toContain('project_id=project-a')
    expect(String(url)).toContain('artifact_id=artifact-a')
    expect(String(url)).toContain('source_version_id=11')
    expect(String(url)).toContain('offset=10')
    expect(String(url)).toContain('limit=25')
  })


  it('读取单个 Run 的安全状态投影', async () => {
    await AgentAPI.getRunState('run-state-a')
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/runs/run-state-a/state')
  })

  it('读取三阶段 Provider provenance，保留 null 代表尚未产生该阶段事实', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        planner_provider_called: true,
        planner_provider_fallback_reason: null,
        planner_provider_attempts: { provider_attempts: [{ status: 'succeeded' }], selected_provider_attempt: 1, fallback_used: false },
        response_provider_called: false,
        response_provider_fallback_reason: 'ProviderTimeout',
        response_provider_attempts: { provider_attempts: [{ status: 'failed', error_category: 'TIMEOUT' }], selected_provider_attempt: null, fallback_used: false },
        candidate_writer_provider_called: null,
        candidate_writer_provider_fallback_reason: null,
        candidate_writer_model_ref: null,
      }),
    })

    const result = await AgentAPI.getRunProviderProvenance('run/provenance a')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/runs/run%2Fprovenance%20a/provider-provenance')
    expect(init.credentials).toBe('include')
    expect(result).toEqual({
      planner_provider_called: true,
      planner_provider_fallback_reason: null,
      planner_provider_attempts: { provider_attempts: [{ status: 'succeeded' }], selected_provider_attempt: 1, fallback_used: false },
      response_provider_called: false,
      response_provider_fallback_reason: 'ProviderTimeout',
      response_provider_attempts: { provider_attempts: [{ status: 'failed', error_category: 'TIMEOUT' }], selected_provider_attempt: null, fallback_used: false },
      candidate_writer_provider_called: null,
      candidate_writer_provider_fallback_reason: null,
      candidate_writer_model_ref: null,
      candidate_writer_provider_attempts: null,
    })
  })

  it('将畸形 Provider Attempt snapshot 降级为空态且不透传未知字段', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        planner_provider_called: true,
        planner_provider_fallback_reason: null,
        planner_provider_attempts: { provider_attempts: 'invalid', api_key: 'secret' },
        response_provider_called: false,
        response_provider_fallback_reason: 'TimeoutError',
        response_provider_attempts: {
          provider_attempts: [{ status: 'failed', error_category: 'TIMEOUT', prompt: 'private', injected: true }],
          selected_provider_attempt: 99,
          fallback_used: true,
        },
        candidate_writer_provider_called: null,
        candidate_writer_provider_fallback_reason: null,
        candidate_writer_model_ref: null,
      }),
    })

    const result = await AgentAPI.getRunProviderProvenance('run-malformed-provenance')

    expect(result.planner_provider_attempts).toBeNull()
    expect(result.response_provider_attempts).toEqual({
      provider_attempts: [{ status: 'failed', error_category: 'TIMEOUT' }],
      selected_provider_attempt: null,
      fallback_used: true,
    })
  })


  it('读取 P1-A 的冻结上下文、计划修订和会话摘要事实', async () => {
    await AgentAPI.getRunContextSnapshot('run-fact-a')
    await AgentAPI.getRunPlanRevision('run-fact-a')
    await AgentAPI.listRunConversationSummaries('run-fact-a', 17)
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/agent/runs/run-fact-a/context-snapshot')
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/agent/runs/run-fact-a/plan-revision')
    expect(String(fetchMock.mock.calls[2][0])).toBe('/api/agent/runs/run-fact-a/conversation-summaries?limit=17')
  })

  it('请求 artifact 的结构化 rewrite instruction', async () => {
    await AgentAPI.listArtifactRewriteInstructions('artifact-a')
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/artifacts/artifact-a/rewrite-instructions')
  })


  it('发送最小 ContextRef 请求体而不携带章节正文', async () => {
    await AgentAPI.sendMessage('session-a', {
      content: '检查当前版本',
      context_refs: [
        { kind: 'project', project_id: 'project-a' },
        { kind: 'chapter_version', project_id: 'project-a', chapter_number: 7, version_id: 12, role: 'selected' },
      ],
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/sessions/session-a/messages')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      content: '检查当前版本',
      context_refs: [
        { kind: 'project', project_id: 'project-a' },
        { kind: 'chapter_version', project_id: 'project-a', chapter_number: 7, version_id: 12, role: 'selected' },
      ],
    })
    expect(String(init.body)).not.toContain('content_preview')
  })


  it('按 sequence cursor 和上限读取单个 Run 的 durable Activity', async () => {
    await AgentAPI.listRunActivity('run-a', 12, 200)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/runs/run-a/activity?after_sequence=12&limit=200')
  })


  it('通过 Durable Run Command API 提交幂等暂停命令和状态版本', async () => {
    const idempotencyKey = buildAgentRunCommandIdempotencyKey('run-control', 'pause', 7)
    await AgentAPI.submitRunCommand('run-control', {
      command_type: 'pause',
      idempotency_key: idempotencyKey,
      expected_state_version: 7,
      reason: '作者检查当前计划',
      payload_json: { source: 'chat' },
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/runs/run-control/commands')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      command_type: 'pause',
      idempotency_key: 'agent-run-command:run-control:pause:state-7',
      expected_state_version: 7,
      reason: '作者检查当前计划',
      payload_json: { source: 'chat' },
    })
  })

  it('请求 Agent Run 历史分页 envelope 并规范化 limit/offset', async () => {
    await AgentAPI.listRunCommandsPage('run/page', { limit: 999, offset: -5 })
    await AgentAPI.listRunStepsPage('run/page', { limit: 0, offset: 12 })
    await AgentAPI.listArtifactsPage('run/page', { limit: 2, offset: 7 })

    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/agent/runs/run%2Fpage/commands?limit=200&offset=0')
    expect(String(fetchMock.mock.calls[1][0])).toBe('/api/agent/runs/run%2Fpage/steps?limit=1&offset=12')
    expect(String(fetchMock.mock.calls[2][0])).toBe('/api/agent/runs/run%2Fpage/artifacts?limit=2&offset=7')
  })


  it('请求 session 元数据时可关闭完整消息与运行数组', async () => {
    await AgentAPI.getSession('session/meta', { includeMessages: false, includeRuns: false })
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/sessions/session%2Fmeta?include_messages=false&include_runs=false')
  })

  it('请求会话运行分页并保留 created_at + id 游标', async () => {
    await AgentAPI.listSessionRunsPage('session/runs', { limit: 3, beforeCreatedAt: '2026-09-05T01:00:00Z', beforeId: 'run-2' })
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/sessions/session%2Fruns/runs?limit=3&before_created_at=2026-09-05T01%3A00%3A00Z&before_id=run-2')
  })

  it('请求会话消息分页并规范化 limit 与 before_sequence', async () => {
    await AgentAPI.listSessionMessagesPage('session/page', { limit: 999, beforeSequence: 61 })
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/agent/sessions/session%2Fpage/messages?limit=200&before_sequence=61')
  })

})
