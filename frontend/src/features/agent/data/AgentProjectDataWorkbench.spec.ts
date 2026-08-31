import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentProjectDataWorkbench from './AgentProjectDataWorkbench.vue'

const listProjectEntitySummariesMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/agent', () => ({
  AgentAPI: { listProjectEntitySummaries: listProjectEntitySummariesMock },
}))

describe('AgentProjectDataWorkbench', () => {
  beforeEach(() => {
    listProjectEntitySummariesMock.mockReset()
    listProjectEntitySummariesMock.mockResolvedValue({
      project_id: 'project-a',
      entities: [
        { kind: 'character', entity_id: 7, label: '沈星河', status: '主角', detail: null },
        { kind: 'research_artifact', entity_id: 8, label: '研究 #8 · global', status: 'completed', detail: null },
      ],
    })
  })

  it('loads label-only summaries and emits identifier-only entity refs', async () => {
    const wrapper = mount(AgentProjectDataWorkbench, {
      props: { projectId: 'project-a', selectedEntityRefs: [] },
    })
    await flushPromises()

    expect(listProjectEntitySummariesMock).toHaveBeenCalledWith('project-a')
    expect(wrapper.text()).toContain('沈星河')
    expect(wrapper.text()).not.toContain('provider_metadata')
    await wrapper.get('[data-testid="agent-project-entity-character-7"]').trigger('click')
    expect(wrapper.emitted('toggle-entity')).toEqual([[{ kind: 'character', entityId: 7 }]])
  })

  it('disables new selection at the bounded selection limit while retaining removal', async () => {
    const wrapper = mount(AgentProjectDataWorkbench, {
      props: {
        projectId: 'project-a',
        selectedEntityRefs: Array.from({ length: 16 }, (_, index) => ({ kind: 'character' as const, entityId: index + 1 })),
      },
    })
    await flushPromises()

    expect((wrapper.get('[data-testid="agent-project-entity-research_artifact-8"]').element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('[data-testid="agent-project-entity-character-7"]').element as HTMLButtonElement).disabled).toBe(false)
  })
})
