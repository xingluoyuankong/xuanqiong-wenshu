import { nextTick } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { AGENT_PANEL_STORAGE_KEY, useAgentPanelState } from './useAgentPanelState'

describe('useAgentPanelState', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('starts closed on both sides and exposes independent side state', () => {
    const state = useAgentPanelState({ storageKey: 'agent-panel-test' })

    expect(state.activePanels.value).toEqual({ left: null, right: null })
    expect(state.activeLeftPanel.value).toBeNull()
    expect(state.activeRightPanel.value).toBeNull()
    expect(state.isOpen('left')).toBe(false)
    expect(state.isOpen('right')).toBe(false)
  })

  it('opens, toggles, and closes a panel without affecting the other side', async () => {
    const state = useAgentPanelState({ storageKey: 'agent-panel-test' })

    state.open('left', 'content')
    state.open('right', 'log')
    expect(state.activePanels.value).toEqual({ left: 'content', right: 'log' })
    expect(state.isOpen('left', 'content')).toBe(true)
    expect(state.isOpen('right', 'content')).toBe(false)

    state.toggle('left', 'content')
    expect(state.activeLeftPanel.value).toBeNull()
    expect(state.activeRightPanel.value).toBe('log')

    state.close('right')
    expect(state.activePanels.value).toEqual({ left: null, right: null })
    await nextTick()
    expect(window.localStorage.getItem('agent-panel-test')).toBe(JSON.stringify({ left: null, right: null }))
  })

  it('restores valid persisted panels and falls back for malformed entries', () => {
    window.localStorage.setItem('agent-panel-test', JSON.stringify({ left: 'project', right: 'runtime' }))
    const restored = useAgentPanelState({ storageKey: 'agent-panel-test' })
    expect(restored.activePanels.value).toEqual({ left: 'project', right: 'runtime' })

    window.localStorage.setItem('agent-panel-test-bad', '{not-json')
    const fallback = useAgentPanelState({ storageKey: 'agent-panel-test-bad', initial: { left: 'project' } })
    expect(fallback.activePanels.value).toEqual({ left: 'project', right: null })
  })

  it('ignores invalid persisted panel values and can clear both sides', () => {
    window.localStorage.setItem('agent-panel-test', JSON.stringify({ left: 42, right: '' }))
    const state = useAgentPanelState({ storageKey: 'agent-panel-test', initial: { left: 'project', right: 'log' } })
    expect(state.activePanels.value).toEqual({ left: null, right: null })

    state.open('left', 'world')
    state.open('right', 'quality')
    state.clear()
    expect(state.activePanels.value).toEqual({ left: null, right: null })
  })

  it('exports a stable default storage key', () => {
    expect(AGENT_PANEL_STORAGE_KEY).toBe('xuanqiong-wenshu:agent-panels')
  })
})
