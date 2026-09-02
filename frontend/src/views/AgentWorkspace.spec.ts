import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentWorkspace from './AgentWorkspace.vue'
import workspaceSource from './AgentWorkspace.vue?raw'

const {
  pushMock,
  replaceMock,
  routeQuery,
  listToolsMock,
  listProjectEntitySummariesMock,
  createPlanMock,
  listSessionsMock,
  getSessionMock,
  listEventsMock,
  listRunActivityMock,
  listApprovalsMock,
  listArtifactsMock,
  listRunStepsMock,
  listExecutionFactsMock,
  getProviderUsageSummaryMock,
  getRunPlanMock,
  getRunStateMock,
  getArtifactContentMock,
  getArtifactQualityMock,
  createSessionMock,
  sendMessageMock,
  submitRunCommandMock,
  getSectionMock,
  getChapterMock,
  store,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  routeQuery: {} as Record<string, string>,
  listToolsMock: vi.fn(),
  listProjectEntitySummariesMock: vi.fn(),
  createPlanMock: vi.fn(),
  listSessionsMock: vi.fn(),
  getSessionMock: vi.fn(),
  listEventsMock: vi.fn(),
  listRunActivityMock: vi.fn(),
  listApprovalsMock: vi.fn(),
  listArtifactsMock: vi.fn(),
  listRunStepsMock: vi.fn(),
  listExecutionFactsMock: vi.fn(),
  getProviderUsageSummaryMock: vi.fn(),
  getRunPlanMock: vi.fn(),
  getRunStateMock: vi.fn(),
  getArtifactContentMock: vi.fn(),
  getArtifactQualityMock: vi.fn(),
  createSessionMock: vi.fn(),
  sendMessageMock: vi.fn(),
  submitRunCommandMock: vi.fn(),
  getSectionMock: vi.fn(),
  getChapterMock: vi.fn(),
  store: {
    projects: [{ id: 'p1', title: '星河旧梦', completed_chapters: 2, total_chapters: 8 }],
    loadProjects: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}))
vi.mock('@/stores/novel', () => ({ useNovelStore: () => store }))
vi.mock('@/api/novel', () => ({
  NovelAPI: { getSection: getSectionMock, getChapter: getChapterMock },
}))
vi.mock('@/api/agent', () => ({
  buildAgentRunCommandIdempotencyKey: (runId: string, command: string, version: number) =>
    `agent-run-command:${runId}:${command}:state-${version}`,
  AgentAPI: {
    listTools: listToolsMock,
    listProjectEntitySummaries: listProjectEntitySummariesMock,
    createPlan: createPlanMock,
    listSessions: listSessionsMock,
    getSession: getSessionMock,
    listEvents: listEventsMock,
    listRunActivity: listRunActivityMock,
    listApprovals: listApprovalsMock,
    listArtifacts: listArtifactsMock,
    listRunSteps: listRunStepsMock,
    listExecutionFacts: listExecutionFactsMock,
    getProviderUsageSummary: getProviderUsageSummaryMock,
    getRunPlan: getRunPlanMock,
    getRunState: getRunStateMock,
    getArtifactContent: getArtifactContentMock,
    getArtifactQuality: getArtifactQualityMock,
    createSession: createSessionMock,
    sendMessage: sendMessageMock,
    submitRunCommand: submitRunCommandMock,
    sessionStreamUrl: vi.fn(),
  },
}))

describe('AgentWorkspace', () => {
  beforeEach(() => {
    pushMock.mockReset()
    replaceMock.mockReset()
    Object.keys(routeQuery).forEach((key) => delete routeQuery[key])
    store.loadProjects.mockReset()
    store.loadProjects.mockResolvedValue(undefined)
    listProjectEntitySummariesMock.mockReset()
    listProjectEntitySummariesMock.mockResolvedValue({ project_id: 'p1', entities: [] })
    listSessionsMock.mockReset()
    getSessionMock.mockReset()
    listEventsMock.mockReset()
    listRunActivityMock.mockReset()
    listRunActivityMock.mockResolvedValue([])
    listApprovalsMock.mockReset()
    listArtifactsMock.mockReset()
    listRunStepsMock.mockReset()
    listExecutionFactsMock.mockReset()
    listExecutionFactsMock.mockResolvedValue([])
    getProviderUsageSummaryMock.mockReset()
    getProviderUsageSummaryMock.mockImplementation(async (runId: string) => ({
      run_id: runId,
      total_attempts: 0,
      succeeded_attempts: 0,
      failed_attempts: 0,
      fallback_attempts: 0,
      first_token_attempts: 0,
      digest_attempts: 0,
      selected_attempts: 0,
      last_error_category: null,
      latest_first_token_at: null,
    }))
    getRunPlanMock.mockReset()
    getRunStateMock.mockReset()
    getArtifactContentMock.mockReset()
    getArtifactQualityMock.mockReset()
    createSessionMock.mockReset()
    sendMessageMock.mockReset()
    submitRunCommandMock.mockReset()
    getSectionMock.mockReset()
    getChapterMock.mockReset()
    replaceMock.mockResolvedValue(undefined)
    listToolsMock.mockResolvedValue({
      count: 1,
      generation: 4,
      tools: [
        {
          name: 'project.context',
          description: '读取项目',
          risk_level: 'read',
          requires_confirmation: false,
          supports_stream: false,
          provider_id: 'project-read',
          provider_version: '1.0.0',
          source: 'builtin',
        },
      ],
    })
    getSectionMock.mockImplementation(async (_projectId: string, section: string) =>
      section === 'chapters'
        ? {
            section,
            data: {
              chapters: [
                {
                  chapter_number: 1,
                  title: '树章节',
                  summary: '轻量摘要',
                  generation_status: 'successful',
                  word_count: 120,
                },
              ],
            },
          }
        : {
            section,
            data: {
              chapter_outline: [
                {
                  chapter_number: 1,
                  title: '树章节',
                  summary: '大纲摘要',
                  metadata: { volume_number: 1, volume_title: '第一卷' },
                },
              ],
            },
          },
    )
    getChapterMock.mockResolvedValue({
      chapter_number: 1,
      title: '树章节',
      summary: '轻量摘要',
      content: 'TREE_PREVIEW',
      selected_version_id: 11,
      versions: [{ id: 11, content: 'TREE_PREVIEW' }],
      evaluation: null,
      generation_status: 'successful',
    })
    getRunPlanMock.mockResolvedValue({
      goal: '运行计划',
      mode: 'explore',
      provider_called: false,
      steps: [],
      events: [],
    })
    createPlanMock.mockResolvedValue({
      goal: '检查质量',
      mode: 'explore',
      provider_called: false,
      steps: [
        {
          order: 1,
          tool_name: 'quality.inspect',
          description: '分析质量',
          risk_level: 'suggest',
          requires_confirmation: false,
        },
      ],
      events: [],
    })
  })
  it('按当前 Run 请求 Provider 统计并把失败留在数据面板', async () => {
    Object.assign(routeQuery, { project_id: 'p1', session_id: 's-usage', run_id: 'run-usage' })
    const session = { id: 's-usage', user_id: 1, project_id: 'p1', status: 'active', created_at: 'now', updated_at: 'now' }
    const run = { id: 'run-usage', session_id: session.id, user_id: 1, project_id: 'p1', status: 'completed', current_phase: 'completed', current_step: 1, progress: 100, created_at: '2026-09-02T09:00:00Z' }
    listSessionsMock.mockResolvedValue([session])
    getSessionMock.mockResolvedValue({ ...session, messages: [], runs: [run] })
    listEventsMock.mockResolvedValue([])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    listRunStepsMock.mockResolvedValue([])
    getRunStateMock.mockResolvedValue({
      correlation_id: 'c-usage',
      progress: 100,
      phase: 'completed',
      current_step: 1,
      terminal_status: 'completed',
      capability_snapshot: { generation: 1, providers: [], tools: [] },
    })
    getProviderUsageSummaryMock.mockResolvedValue({
      run_id: run.id,
      total_attempts: 2,
      succeeded_attempts: 1,
      failed_attempts: 1,
      fallback_attempts: 1,
      first_token_attempts: 1,
      digest_attempts: 1,
      selected_attempts: 1,
      last_error_category: 'TIMEOUT',
      latest_first_token_at: '2026-09-02T09:00:01Z',
    })

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()

    expect(getProviderUsageSummaryMock).toHaveBeenCalledWith(run.id)
    expect(wrapper.get('[data-testid="agent-provider-usage-panel"]').text()).toContain('TIMEOUT')
  })

  it('右侧日志显示动作对应的结果引用，而不把结果正文混入日志', () => {
    expect(workspaceSource).toContain('v-if="event.actionId || event.phase || event.resultRef"')
    expect(workspaceSource).toContain('结果：{{ event.resultRef }}')
    expect(workspaceSource).toContain('scrollIntoView')
  })

  it('点击日志动作或结果引用后定位当前 Run，并在切换 Run 时清理定位', async () => {
    const scrollIntoViewMock = vi.fn()
    Object.defineProperty(window.HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoViewMock })
    Object.assign(routeQuery, { project_id: 'p1', session_id: 's-locate', run_id: 'run-locate-old' })
    const session = { id: 's-locate', user_id: 1, project_id: 'p1', status: 'active', created_at: 'now', updated_at: 'now' }
    const oldRun = { id: 'run-locate-old', session_id: session.id, user_id: 1, project_id: 'p1', status: 'completed', current_phase: 'completed', current_step: 1, progress: 100, created_at: '2026-08-27T09:00:00Z' }
    const newRun = { id: 'run-locate-new', session_id: session.id, user_id: 1, project_id: 'p1', status: 'completed', current_phase: 'completed', current_step: 1, progress: 100, created_at: '2026-08-27T09:01:00Z' }
    listSessionsMock.mockResolvedValue([session])
    getSessionMock.mockResolvedValue({ ...session, messages: [], runs: [oldRun, newRun] })
    listEventsMock.mockImplementation(async (_sessionId: string, runId: string) => [{
      id: `${runId}-event`, run_id: runId, sequence: 1, event_type: 'tool_call_completed', summary: '工具已完成',
      data: { action_id: `step:${runId}`, result_ref: `execution:${runId}`, phase: 'tool_execution', progress: 100 },
    }])
    listRunStepsMock.mockImplementation(async (runId: string) => [{
      id: runId, run_id: runId, user_id: 1, step_order: 1, tool_name: 'quality.inspect',
      idempotency_key: `idem-${runId}`, status: 'completed', attempt_count: 1, output_json: { execution_id: runId, summary: '安全摘要' },
    }])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    getRunStateMock.mockImplementation(async (runId: string) => ({
      correlation_id: `c-${runId}`, run_id: runId, user_id: 1, progress: 100, phase: 'completed', current_step: 1,
      terminal_status: 'completed', recoverable: false, cancellation_requested: false, last_event_sequence: 1,
      steps: [], approvals: [], artifacts: [], accepted_version_ids: [], jobs: [], task_runtime_refs: [],
    }))

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()

    await wrapper.get('[data-testid="agent-log-action-ref"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-testid="agent-inspector-section"]').element as HTMLDetailsElement).open).toBe(true)
    expect(wrapper.get('[data-testid="agent-selected-location"]').text()).toContain('step:run-locate-old')
    expect(wrapper.get('[data-testid="agent-step-run-locate-old"]').classes()).toContain('step-list__item--selected')
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: 'nearest' })

    await wrapper.get('[data-testid="agent-log-result-ref"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-selected-location"]').text()).toContain('execution:run-locate-old')
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: 'nearest' })

    await wrapper.get('[data-testid="agent-run-selector"]').setValue('run-locate-new')
    await flushPromises()
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-selected-location"]').text()).toContain('尚未定位')
    expect(wrapper.find('.step-list__item--selected').exists()).toBe(false)
  })

  it('将导航、聊天和运行日志分隔为可折叠的独立区域', async () => {
    const wrapper = mount(AgentWorkspace)
    await flushPromises()

    expect(wrapper.find('[data-testid="agent-sidebar-stack"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-chat-column"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-activity-stack"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-log-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-activity-stack"] [data-testid="agent-process-stream"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-runtime-log-viewport"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-chat-column"] [data-testid="agent-process-stream"]').exists()).toBe(false)

    const projectSection = wrapper.get('[data-testid="agent-project-section"]').element as HTMLDetailsElement
    const sessionSection = wrapper.get('[data-testid="agent-session-section"]').element as HTMLDetailsElement
    const toolsSection = wrapper.get('[data-testid="agent-tools-section"]').element as HTMLDetailsElement
    const dataSection = wrapper.get('[data-testid="agent-data-section"]').element as HTMLDetailsElement
    expect(projectSection.open).toBe(true)
    expect(sessionSection.open).toBe(false)
    expect(toolsSection.open).toBe(false)
    expect(dataSection.open).toBe(false)
    const runDetailsSection = wrapper.get('[data-testid="agent-run-details-section"]').element as HTMLDetailsElement
    expect(runDetailsSection.open).toBe(false)
  })

  it('显示项目和后端工具注册表', async () => {
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-project-select"]').text()).toContain('星河旧梦')
    expect(wrapper.get('[data-testid="agent-tool-list"]').text()).toContain('project.context')
    expect(wrapper.get('[data-testid="agent-tool-catalog-generation"]').text()).toContain('第 4 代')
    expect(wrapper.get('[data-testid="agent-tool-list"]').text()).toContain(
      '内置 Provider · project-read v1.0.0',
    )
  })
  it('只用轻量 section 构建内容树，并在点击章节后懒加载预览', async () => {
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()
    expect(getSectionMock).toHaveBeenCalledWith('p1', 'chapters')
    expect(getSectionMock).toHaveBeenCalledWith('p1', 'chapter_outline')
    expect(wrapper.get('[data-testid="agent-content-chapter-1"]').text()).toContain('树章节')
    expect(getChapterMock).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="agent-content-chapter-1"]').trigger('click')
    await flushPromises()
    expect(getChapterMock).toHaveBeenCalledWith('p1', 1)
    expect(wrapper.get('[data-testid="agent-content-preview-text"]').text()).toContain(
      'TREE_PREVIEW',
    )
    expect(replaceMock).toHaveBeenCalledWith({
      path: '/agent',
      query: { project_id: 'p1', chapter: '1', version_id: '11', focus: 'version' },
    })
  })
  it('提交目标后展示 provider-free 计划', async () => {
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await wrapper.get('[data-testid="agent-message-input"]').setValue('检查质量')
    await wrapper.get('[data-testid="agent-plan-submit"]').trigger('submit')
    await flushPromises()
    expect(createPlanMock).toHaveBeenCalledWith({ goal: '检查质量', project_id: 'p1' })
    expect(wrapper.get('[data-testid="agent-plan-panel"]').text()).toContain('quality.inspect')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain(
      '未调用 Provider（受控本地计划）。',
    )
  })
  it('展示 Provider 参与规划，而不把它误报为本地计划', async () => {
    createPlanMock.mockResolvedValueOnce({
      goal: '检查质量',
      mode: 'explore',
      provider_called: true,
      steps: [
        {
          order: 1,
          tool_name: 'quality.inspect',
          description: '分析质量',
          risk_level: 'suggest',
          requires_confirmation: false,
        },
      ],
      events: [],
    })
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await wrapper.get('[data-testid="agent-message-input"]').setValue('检查质量')
    await wrapper.get('[data-testid="agent-plan-submit"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain(
      'Provider 已参与受控工具规划。',
    )
  })
  it('从受控深链恢复当前项目、会话、运行与 Artifact，并把实际上下文写回地址栏', async () => {
    Object.assign(routeQuery, {
      project_id: 'p1',
      session_id: 's1',
      run_id: 'r1',
      artifact_id: 'a1',
    })
    const session = {
      id: 's1',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    const run = {
      id: 'r1',
      session_id: 's1',
      user_id: 1,
      project_id: 'p1',
      status: 'completed',
      current_step: 1,
      progress: 100,
      created_at: 'now',
    }
    listSessionsMock.mockResolvedValue([session])
    getSessionMock.mockResolvedValue({ ...session, messages: [], runs: [run] })
    listEventsMock.mockResolvedValue([])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([
      {
        id: 'a1',
        run_id: 'r1',
        user_id: 1,
        project_id: 'p1',
        kind: 'chapter_candidate',
        uri: 'artifact://a1',
        metadata_json: {},
        created_at: 'now',
      },
    ])
    listRunStepsMock.mockResolvedValue([])
    getRunStateMock.mockResolvedValue({
      correlation_id: 'c1',
      progress: 100,
      phase: 'completed',
      current_step: 1,
      terminal_status: 'completed',
      capability_snapshot: {
        generation: 3,
        providers: [],
        tools: [{ name: 'project.context', risk_level: 'read' }],
      },
    })
    getArtifactContentMock.mockResolvedValue('安全候选内容')
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()
    expect(listSessionsMock).toHaveBeenCalledWith('p1')
    expect(getSessionMock).toHaveBeenCalledWith('s1')
    expect(listArtifactsMock).toHaveBeenCalledWith('r1')
    expect(getArtifactContentMock).toHaveBeenCalledWith('a1')
    expect(wrapper.get('[data-testid="agent-capability-generation"]').text()).toContain('第 3 代')
    expect(replaceMock).toHaveBeenCalledWith({
      path: '/agent',
      query: { project_id: 'p1', session_id: 's1', run_id: 'r1', artifact_id: 'a1' },
    })
  })

  it('深链历史 Run 后保持显式选择，并按 Run 隔离步骤、事件和候选', async () => {
    Object.assign(routeQuery, { project_id: 'p1', session_id: 's-multi', run_id: 'run-old' })
    const session = {
      id: 's-multi',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    const oldRun = {
      id: 'run-old',
      session_id: session.id,
      user_id: 1,
      project_id: 'p1',
      status: 'completed',
      current_phase: 'completed',
      current_step: 1,
      progress: 21,
      created_at: '2026-08-27T09:00:00Z',
    }
    const newestRun = {
      id: 'run-new',
      session_id: session.id,
      user_id: 1,
      project_id: 'p1',
      status: 'completed',
      current_phase: 'completed',
      current_step: 2,
      progress: 88,
      created_at: '2026-08-27T09:01:00Z',
    }
    listSessionsMock.mockResolvedValue([session])
    getSessionMock.mockResolvedValue({ ...session, messages: [], runs: [oldRun, newestRun] })
    listEventsMock.mockImplementation(async (_sessionId: string, runId: string) => [
      {
        id: `${runId}-event`,
        run_id: runId,
        sequence: 1,
        event_type: 'progress_update',
        summary: runId === oldRun.id ? '历史运行正在校验版本' : '最新运行正在汇总质量',
        data: {
          progress: runId === oldRun.id ? 21 : 88,
          progress_message: runId === oldRun.id ? '历史步骤' : '最新步骤',
          phase: runId === oldRun.id ? 'quality_check' : 'summary',
          action_id: runId === oldRun.id ? 'quality:history' : 'summary:latest',
        },
      },
    ])
    listApprovalsMock.mockImplementation(async (runId: string) => [
      { id: `approval-${runId}`, run_id: runId, user_id: 1, tool_name: 'chapter.rewrite', status: 'pending' },
    ])
    listArtifactsMock.mockImplementation(async (runId: string) => [
      {
        id: `artifact-${runId}`,
        run_id: runId,
        user_id: 1,
        project_id: 'p1',
        kind: 'chapter_candidate',
        uri: `artifact://${runId}`,
        metadata_json: {},
        created_at: 'now',
      },
    ])
    listRunStepsMock.mockImplementation(async (runId: string) => [
      {
        id: `step-${runId}`,
        run_id: runId,
        user_id: 1,
        step_order: 1,
        tool_name: runId === oldRun.id ? 'chapter.version.list' : 'quality.inspect',
        idempotency_key: `idempotency-${runId}`,
        status: 'completed',
        attempt_count: 1,
        output_json: {},
      },
    ])
    listExecutionFactsMock.mockImplementation(async (runId: string) => runId === oldRun.id ? [{
      execution_id: 'execution-facts-history', run_id: runId, step_id: `step-${runId}`,
      action_id: 'quality:history', result_ref: 'execution:execution-facts-history',
      tool_name: 'chapter.version.list', status: 'completed', attempt: 1, has_output: true,
    }] : [])
    getRunStateMock.mockImplementation(async (runId: string) => ({
      correlation_id: `correlation-${runId}`,
      run_id: runId,
      user_id: 1,
      progress: runId === oldRun.id ? 21 : 88,
      phase: 'completed',
      current_step: runId === oldRun.id ? 1 : 2,
      terminal_status: 'completed',
      recoverable: false,
      cancellation_requested: false,
      last_event_sequence: 1,
      latest_public_summary: {
        action_id: `summary-${runId}`,
        phase: 'tool_execution',
        current_action: runId === oldRun.id ? '历史运行正在整理章节版本。' : '最新运行正在汇总质量。',
        input_scope: [{ kind: 'chapter', chapter_number: runId === oldRun.id ? 3 : 8 }],
        selected_capability: runId === oldRun.id ? 'chapter.version.list' : 'quality.inspect',
        revision: 0,
      },
      latest_public_summary_sequence: 1,
      latest_public_summary_at: 'now',
      steps: [],
      approvals: [],
      artifacts: [],
      accepted_version_ids: [],
      jobs: [],
      task_runtime_refs: [],
    }))

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-run-selector"]').element).toHaveProperty('value', 'run-old')
    expect(wrapper.get('[data-testid="agent-selected-run-id"]').text()).toContain('run-old')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain('动作：quality:history')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain('结果：execution:execution-facts-history')
    expect(listExecutionFactsMock).toHaveBeenCalledWith('run-old')
    expect(wrapper.get('[data-testid="agent-run-progress"]').text()).toContain('21%')
    expect(wrapper.get('[data-testid="agent-step-panel"]').text()).toContain('chapter.version.list')
    expect(wrapper.get('[data-testid="agent-public-work-summary"]').text()).toContain('历史运行正在整理章节版本。')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain('历史运行正在校验版本')
    expect(listArtifactsMock).toHaveBeenCalledWith('run-old')
    expect(listArtifactsMock).not.toHaveBeenCalledWith('run-new')

    await wrapper.get('[data-testid="agent-run-selector"]').setValue('run-new')
    await flushPromises()
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-selected-run-id"]').text()).toContain('run-new')
    expect(wrapper.get('[data-testid="agent-run-progress"]').text()).toContain('88%')
    expect(wrapper.get('[data-testid="agent-step-panel"]').text()).toContain('quality.inspect')
    expect(wrapper.get('[data-testid="agent-public-work-summary"]').text()).toContain('最新运行正在汇总质量。')
    expect(wrapper.get('[data-testid="agent-public-work-summary"]').text()).not.toContain('历史运行正在整理章节版本。')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain('最新运行正在汇总质量')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).not.toContain('历史运行正在校验版本')
    expect(listArtifactsMock).toHaveBeenCalledWith('run-new')
    expect(replaceMock).toHaveBeenLastCalledWith({
      path: '/agent',
      query: { project_id: 'p1', session_id: 's-multi', run_id: 'run-new' },
    })
  })


  it('收到 public_work_summary 后回读 selected Run checkpoint，且不显示事件中的隐藏字段', async () => {
    Object.assign(routeQuery, { project_id: 'p1', session_id: 's-summary', run_id: 'run-summary' })
    const summarySession = {
      id: 's-summary',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    const summaryRun = {
      id: 'run-summary',
      session_id: summarySession.id,
      user_id: 1,
      project_id: 'p1',
      status: 'completed',
      current_step: 1,
      progress: 100,
      created_at: 'now',
    }
    const baseState = {
      correlation_id: 'summary-correlation',
      run_id: summaryRun.id,
      user_id: 1,
      progress: 100,
      phase: 'assistant_response',
      current_step: 1,
      terminal_status: 'completed',
      recoverable: false,
      cancellation_requested: false,
      last_event_sequence: 1,
      steps: [],
      approvals: [],
      artifacts: [],
      accepted_version_ids: [],
      jobs: [],
      task_runtime_refs: [],
    }
    listSessionsMock.mockResolvedValue([summarySession])
    getSessionMock.mockResolvedValue({ ...summarySession, messages: [], runs: [summaryRun] })
    listRunStepsMock.mockResolvedValue([])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    listEventsMock.mockResolvedValue([])
    listRunActivityMock.mockResolvedValue([
      {
        id: 'summary-event',
        run_id: summaryRun.id,
        sequence: 1,
        event_type: 'public_work_summary',
        summary: '正在读取项目上下文。',
        data: {
          action_id: 'context:started',
          phase: 'context',
          current_action: '正在读取项目上下文。',
          reasoning: 'HIDDEN_REASONING',
        },
      },
    ])
    getRunStateMock
      .mockResolvedValueOnce({ ...baseState, latest_public_summary: null })
      .mockResolvedValueOnce({
        ...baseState,
        latest_public_summary: {
          action_id: 'context:started',
          phase: 'context',
          current_action: '已从 durable checkpoint 恢复当前工作。',
          input_scope: [{ kind: 'project', project_id: 'p1' }],
          selected_capability: 'project.context',
          next_action: '建立执行计划。',
          revision: 0,
        },
        latest_public_summary_sequence: 1,
        latest_public_summary_at: 'now',
      })

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()
    await flushPromises()
    await flushPromises()

    expect(listRunActivityMock).toHaveBeenCalledWith(summaryRun.id, 0, 500)
    expect(getRunStateMock).toHaveBeenCalledTimes(2)
    const summary = wrapper.get('[data-testid="agent-public-work-summary"]').text()
    expect(summary).toContain('已从 durable checkpoint 恢复当前工作。')
    expect(summary).toContain('project.context')
    expect(wrapper.text()).not.toContain('HIDDEN_REASONING')
  })

  it('展示当前 Run 的安全工具结果摘要，不回显敏感正文', async () => {
    Object.assign(routeQuery, { project_id: 'p1', session_id: 's-tool', run_id: 'r-tool' })
    const session = {
      id: 's-tool',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    const run = {
      id: 'r-tool',
      session_id: 's-tool',
      user_id: 1,
      project_id: 'p1',
      status: 'completed',
      current_step: 1,
      progress: 100,
      created_at: 'now',
    }
    listSessionsMock.mockResolvedValue([session])
    getSessionMock.mockResolvedValue({ ...session, messages: [], runs: [run] })
    listEventsMock.mockResolvedValue([])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    getRunStateMock.mockResolvedValue({
      correlation_id: 'c-tool',
      run_id: 'r-tool',
      user_id: 1,
      progress: 100,
      phase: 'completed',
      current_step: 1,
      terminal_status: 'completed',
      recoverable: false,
      cancellation_requested: false,
      last_event_sequence: 0,
      steps: [],
      approvals: [],
      artifacts: [],
      accepted_version_ids: [],
      jobs: [],
      task_runtime_refs: [],
    })
    listRunStepsMock.mockResolvedValue([
      {
        id: 'step-tool',
        run_id: 'r-tool',
        user_id: 1,
        step_order: 1,
        tool_name: 'chapter.version.list',
        idempotency_key: 'r-tool:1',
        status: 'completed',
        attempt_count: 1,
        output_json: {
          count: 1,
          versions: [
            {
              chapter_number: 3,
              version_id: 12,
              status: 'candidate',
              word_count: 920,
              content: 'SECRET_CHAPTER_PROSE',
            },
          ],
        },
      },
    ])

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()
    const panel = wrapper.get('[data-testid="agent-tool-result-panel"]')
    expect(panel.text()).toContain('chapter.version.list')
    expect(panel.text()).toContain('第3章 v12')
    expect(panel.text()).not.toContain('SECRET_CHAPTER_PROSE')
  })

  it('可以打开既有 WritingDesk', async () => {
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await wrapper.get('.agent-sidebar .xq-button').trigger('click')
    expect(pushMock).toHaveBeenCalledWith({ path: '/novel/p1', query: { focus: 'version' } })
  })

  it('将内容树选中的章节版本作为最小 ContextRef 快照发送给 Agent', async () => {
    const currentSession = {
      id: 'context-session',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    listProjectEntitySummariesMock.mockResolvedValue({
      project_id: 'p1',
      entities: [{ kind: 'character', entity_id: 17, label: '沈星河', status: '主角', detail: null }],
    })
    listSessionsMock.mockResolvedValue([currentSession])
    getSessionMock.mockResolvedValue({ ...currentSession, messages: [], runs: [] })
    listEventsMock.mockResolvedValue([])
    listRunStepsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    getRunStateMock.mockResolvedValue({
      correlation_id: 'context-correlation',
      progress: 100,
      phase: 'completed',
      current_step: 1,
      terminal_status: 'completed',
      steps: [],
      approvals: [],
      artifacts: [],
      jobs: [],
      task_runtime_refs: [],
    })
    sendMessageMock.mockResolvedValue({
      message: {
        id: 'user-context',
        session_id: currentSession.id,
        user_id: 1,
        role: 'user',
        content: '检查当前版本',
        sequence: 1,
        created_at: 'now',
      },
      assistant_message: null,
      run: {
        id: 'run-context',
        session_id: currentSession.id,
        user_id: 1,
        project_id: 'p1',
        status: 'completed',
        current_step: 1,
        progress: 100,
        created_at: 'now',
      },
      plan: {
        goal: '检查当前版本',
        mode: 'explore',
        provider_called: false,
        steps: [
          {
            order: 1,
            tool_name: 'chapter.inspect',
            description: '读取章节',
            risk_level: 'read',
            requires_confirmation: false,
          },
        ],
        events: [],
      },
      tool_results: [],
      approvals: [],
    })

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()
    await wrapper.get('[data-testid="agent-content-chapter-1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="agent-project-entity-character-17"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-context-chips"]').text()).toContain('人物 #17')
    expect(wrapper.get('[data-testid="agent-context-chips"]').text()).toContain('第 1 章 · 版本 11')

    await wrapper.get('[data-testid="agent-message-input"]').setValue('检查当前版本')
    await wrapper.get('[data-testid="agent-plan-submit"]').trigger('submit')
    await flushPromises()

    expect(sendMessageMock).toHaveBeenCalledWith('context-session', {
      content: '检查当前版本',
      context_refs: [
        { kind: 'project', project_id: 'p1' },
        {
          kind: 'chapter_version',
          project_id: 'p1',
          chapter_number: 1,
          version_id: 11,
          role: 'selected',
        },
        { kind: 'character', project_id: 'p1', entity_id: 17 },
      ],
    })
  })

  it('将 Artifact 关系化质量发现以最小 ContextRef 加入 Chat 并发送', async () => {
    const currentSession = {
      id: 'quality-context-session',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    const run = {
      id: 'quality-context-run',
      session_id: currentSession.id,
      user_id: 1,
      project_id: 'p1',
      status: 'completed',
      current_step: 1,
      progress: 100,
      created_at: 'now',
    }
    const artifact = {
      id: 'quality-context-artifact',
      run_id: run.id,
      user_id: 1,
      project_id: 'p1',
      kind: 'chapter_candidate',
      uri: 'artifact://quality-context',
      metadata_json: { status: 'candidate' },
      created_at: 'now',
    }
    listSessionsMock.mockResolvedValue([currentSession])
    getSessionMock.mockResolvedValue({ ...currentSession, messages: [], runs: [run] })
    listEventsMock.mockResolvedValue([])
    listRunStepsMock.mockResolvedValue([])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([artifact])
    getArtifactQualityMock.mockResolvedValue({
      artifact_id: artifact.id,
      quality_result: null,
      gate: null,
      findings: [{
        id: 'quality-finding-row',
        finding_id: 'quality-finding-17',
        code: 'ending_pressure_missing',
        category: 'ending',
        severity: 'blocker',
        status: 'open',
        message: 'DO_NOT_SEND_MESSAGE',
        fingerprint: 'a'.repeat(64),
        location_json: { hidden: 'DO_NOT_SEND_LOCATION' },
        evidence_json: { hidden: 'DO_NOT_SEND_EVIDENCE' },
        remediation_json: { hidden: 'DO_NOT_SEND_REMEDIATION' },
        created_at: 'now',
      }],
    })
    getRunStateMock.mockResolvedValue({
      correlation_id: 'quality-context-correlation',
      progress: 100,
      phase: 'completed',
      current_step: 1,
      terminal_status: 'completed',
      steps: [],
      approvals: [],
      artifacts: [],
      jobs: [],
      task_runtime_refs: [],
    })
    sendMessageMock.mockResolvedValue({
      message: {
        id: 'quality-context-message',
        session_id: currentSession.id,
        user_id: 1,
        role: 'user',
        content: '根据质量发现修订候选稿',
        sequence: 1,
        created_at: 'now',
      },
      assistant_message: null,
      run: null,
      plan: null,
      tool_results: [],
      approvals: [],
    })

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()
    await wrapper.get('[data-testid="agent-quality-finding-quality-finding-17"]').trigger('click')

    expect(wrapper.get('[data-testid="agent-context-chips"]').text()).toContain('质量发现：quality-')
    expect(wrapper.get('[data-testid="agent-quality-finding-quality-finding-17"]').text()).toContain('移除上下文')

    await wrapper.get('[data-testid="agent-message-input"]').setValue('根据质量发现修订候选稿')
    await wrapper.get('[data-testid="agent-plan-submit"]').trigger('submit')
    await flushPromises()

    const payload = sendMessageMock.mock.calls.at(-1)?.[1]
    expect(payload).toEqual({
      content: '根据质量发现修订候选稿',
      context_refs: [
        { kind: 'project', project_id: 'p1' },
        { kind: 'quality_finding', project_id: 'p1', finding_id: 'quality-finding-17' },
      ],
    })
    const serialized = JSON.stringify(payload)
    expect(serialized).not.toContain('DO_NOT_SEND_MESSAGE')
    expect(serialized).not.toContain('DO_NOT_SEND_LOCATION')
    expect(serialized).not.toContain('DO_NOT_SEND_EVIDENCE')
    expect(serialized).not.toContain('DO_NOT_SEND_REMEDIATION')
  })

  it('收到 durable execution 排队响应时展示等待真实规划状态', async () => {
    const queuedSession = {
      id: 'queued-session',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    listSessionsMock.mockResolvedValue([queuedSession])
    getSessionMock.mockResolvedValue({ ...queuedSession, messages: [], runs: [] })
    listEventsMock.mockResolvedValue([])
    listRunStepsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    getRunStateMock.mockResolvedValue({
      correlation_id: 'queued-correlation',
      progress: 10,
      phase: 'queued',
      current_step: 0,
      steps: [],
      approvals: [],
      artifacts: [],
      jobs: [],
      task_runtime_refs: [],
    })
    sendMessageMock.mockResolvedValue({
      message: {
        id: 'queued-user-message',
        session_id: queuedSession.id,
        user_id: 1,
        role: 'user',
        content: '整理当前项目',
        sequence: 1,
        created_at: 'now',
      },
      assistant_message: null,
      run: {
        id: 'queued-run',
        session_id: queuedSession.id,
        user_id: 1,
        project_id: 'p1',
        status: 'completed',
        current_step: 0,
        progress: 10,
        created_at: 'now',
      },
      plan: {
        goal: '整理当前项目',
        mode: 'explore',
        provider_called: false,
        steps: [],
        events: [],
      },
      tool_results: [],
      approvals: [],
    })

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await wrapper.get('[data-testid="agent-message-input"]').setValue('整理当前项目')
    await wrapper.get('[data-testid="agent-plan-submit"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-plan-queued"]').text()).toContain('正在由执行器生成真实计划')
    expect(wrapper.get('[data-testid="agent-process-stream"]').text()).toContain('Agent 已排队')
  })

  it('通过 Chat Durable Command API 暂停并取消当前 selected Run，且控制权限来自服务端状态投影', async () => {
    Object.assign(routeQuery, { project_id: 'p1', session_id: 's-control', run_id: 'run-control' })
    const currentSession = {
      id: 's-control',
      user_id: 1,
      project_id: 'p1',
      status: 'active',
      created_at: 'now',
      updated_at: 'now',
    }
    const runningRun = {
      id: 'run-control',
      correlation_id: 'control-correlation',
      session_id: currentSession.id,
      user_id: 1,
      project_id: 'p1',
      status: 'running',
      current_phase: 'tool_execution',
      current_step: 2,
      progress: 44,
      state_version: 4,
      allowed_commands: ['pause', 'cancel'] as const,
      created_at: 'now',
    }
    let commandHistory: Array<{
      id: string
      run_id: string
      command_type: 'pause' | 'resume' | 'cancel'
      status: 'requested' | 'applied' | 'rejected' | 'failed'
      reason?: string | null
      idempotency_key?: string | null
      expected_state_version?: number | null
      error_type?: string | null
      requested_at: string
      applied_at?: string | null
    }> = []
    let runStatus = 'running'
    let runPhase = 'tool_execution'
    let stateVersion = 4
    let allowedCommands: Array<'pause' | 'resume' | 'cancel'> = ['pause', 'cancel']
    const baseState = {
      correlation_id: 'control-correlation',
      run_id: runningRun.id,
      user_id: 1,
      progress: 44,
      phase: runPhase,
      status: runStatus,
      state_version: stateVersion,
      allowed_commands: allowedCommands,
      terminal_status: null as string | null,
      recoverable: false,
      cancellation_requested: false,
      last_event_sequence: 0,
      steps: [],
      approvals: [],
      artifacts: [],
      accepted_version_ids: [],
      jobs: [],
      commands: commandHistory,
      task_runtime_refs: [],
    }
    listSessionsMock.mockResolvedValue([currentSession])
    getSessionMock.mockResolvedValue({ ...currentSession, messages: [], runs: [runningRun] })
    listEventsMock.mockResolvedValue([])
    listRunActivityMock.mockResolvedValue([])
    listRunStepsMock.mockResolvedValue([])
    listApprovalsMock.mockResolvedValue([])
    listArtifactsMock.mockResolvedValue([])
    getRunStateMock.mockImplementation(async () => ({
      ...baseState,
      status: runStatus,
      phase: runPhase,
      state_version: stateVersion,
      allowed_commands: allowedCommands,
      terminal_status: runStatus === 'cancelled' ? 'cancelled' : null,
      commands: commandHistory,
    }))
    submitRunCommandMock.mockImplementation(async (_runId: string, input: {
      command_type: 'pause' | 'resume' | 'cancel'
      idempotency_key: string
      expected_state_version: number
      reason?: string
    }) => {
      const command = {
        id: `command-${input.command_type}`,
        run_id: runningRun.id,
        command_type: input.command_type,
        status: 'applied' as const,
        reason: input.reason,
        idempotency_key: input.idempotency_key,
        expected_state_version: input.expected_state_version,
        requested_at: 'now',
        applied_at: 'now',
      }
      commandHistory = [...commandHistory, command]
      if (input.command_type === 'pause') {
        runStatus = 'paused'
        runPhase = 'paused'
        stateVersion = 5
        allowedCommands = ['resume', 'cancel']
      }
      if (input.command_type === 'cancel') {
        runStatus = 'cancelled'
        runPhase = 'cancelled'
        stateVersion = 6
        allowedCommands = []
      }
      return command
    })

    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    await flushPromises()

    await wrapper.get('[data-testid="agent-pause-run-button"]').trigger('click')
    await flushPromises()
    expect(submitRunCommandMock).toHaveBeenCalledWith(runningRun.id, expect.objectContaining({
      command_type: 'pause',
      expected_state_version: 4,
      idempotency_key: 'agent-run-command:run-control:pause:state-4',
    }))
    expect(wrapper.get('[data-testid="agent-run-status"]').text()).toBe('paused')
    expect(wrapper.find('[data-testid="agent-resume-run-button"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="agent-run-command-history"]').text()).toContain('暂停')

    await wrapper.get('[data-testid="agent-cancel-run-button"]').trigger('click')
    await flushPromises()
    expect(submitRunCommandMock).toHaveBeenLastCalledWith(runningRun.id, expect.objectContaining({
      command_type: 'cancel',
      expected_state_version: 5,
      idempotency_key: 'agent-run-command:run-control:cancel:state-5',
    }))
    expect(wrapper.get('[data-testid="agent-run-status"]').text()).toBe('cancelled')
    expect(wrapper.find('[data-testid="agent-run-control-bar"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="agent-run-command-history"]').text()).toContain('取消')

  })
  it('运行详情默认收纳但可通过摘要展开', async () => {
    const wrapper = mount(AgentWorkspace)
    await flushPromises()
    const section = wrapper.get('[data-testid="agent-run-details-section"]')
    expect((section.element as HTMLDetailsElement).open).toBe(false)

    await section.get('summary').trigger('click')
    expect((section.element as HTMLDetailsElement).open).toBe(true)
    expect(section.text()).toContain('运行详情')
  })
})
