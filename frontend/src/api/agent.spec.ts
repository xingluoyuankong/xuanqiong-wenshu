import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AgentAPI, buildAgentRunCommandIdempotencyKey } from './agent'

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
        response_provider_called: false,
        response_provider_fallback_reason: 'ProviderTimeout',
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
      response_provider_called: false,
      response_provider_fallback_reason: 'ProviderTimeout',
      candidate_writer_provider_called: null,
      candidate_writer_provider_fallback_reason: null,
      candidate_writer_model_ref: null,
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

})
