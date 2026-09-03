import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'

export type AgentPanelSide = 'left' | 'right'
export type AgentPanelId = string

export interface AgentPanelState {
  left: AgentPanelId | null
  right: AgentPanelId | null
}

export interface UseAgentPanelStateOptions {
  /** Storage key used to restore the last open panel on the current device. */
  storageKey?: string
  /** Initial panels used when no valid persisted state exists. */
  initial?: Partial<AgentPanelState>
}

export interface AgentPanelStateApi {
  activePanels: Ref<AgentPanelState>
  activeLeftPanel: ComputedRef<AgentPanelId | null>
  activeRightPanel: ComputedRef<AgentPanelId | null>
  activePanel: (side: AgentPanelSide) => ComputedRef<AgentPanelId | null>
  isOpen: (side: AgentPanelSide, panelId?: AgentPanelId | null) => boolean
  open: (side: AgentPanelSide, panelId: AgentPanelId) => void
  close: (side: AgentPanelSide) => void
  toggle: (side: AgentPanelSide, panelId: AgentPanelId) => void
  clear: () => void
}

const DEFAULT_STORAGE_KEY = 'xuanqiong-wenshu:agent-panels'
const SIDES: AgentPanelSide[] = ['left', 'right']

const emptyState = (): AgentPanelState => ({ left: null, right: null })

const isPanelId = (value: unknown): value is AgentPanelId =>
  typeof value === 'string' && value.trim().length > 0

const normalizePanel = (value: unknown): AgentPanelId | null =>
  (isPanelId(value) ? value : null)

const normalizeState = (
  value: unknown,
  initial: Partial<AgentPanelState> = {},
): AgentPanelState => {
  const candidate = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  return {
    left: normalizePanel(candidate.left ?? initial.left),
    right: normalizePanel(candidate.right ?? initial.right),
  }
}

const readState = (
  storageKey: string,
  initial: Partial<AgentPanelState>,
): AgentPanelState => {
  if (typeof window === 'undefined') return normalizeState(null, initial)

  try {
    const persisted = window.localStorage.getItem(storageKey)
    return persisted ? normalizeState(JSON.parse(persisted), initial) : normalizeState(null, initial)
  } catch {
    // A blocked or malformed localStorage entry must not prevent the workspace from opening.
    return normalizeState(null, initial)
  }
}

const persistState = (storageKey: string, state: AgentPanelState): void => {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(storageKey, JSON.stringify(state))
  } catch {
    // Storage is a convenience; panel interaction remains usable when it is unavailable.
  }
}

export function useAgentPanelState(options: UseAgentPanelStateOptions = {}): AgentPanelStateApi {
  const storageKey = options.storageKey || DEFAULT_STORAGE_KEY
  const activePanels = ref<AgentPanelState>(readState(storageKey, options.initial || {}))

  watch(
    activePanels,
    (state) => persistState(storageKey, state),
    { deep: true },
  )

  const activeLeftPanel = computed(() => activePanels.value.left)
  const activeRightPanel = computed(() => activePanels.value.right)

  const activePanel = (side: AgentPanelSide): ComputedRef<AgentPanelId | null> =>
    computed(() => activePanels.value[side])

  const isOpen = (side: AgentPanelSide, panelId?: AgentPanelId | null): boolean => {
    const active = activePanels.value[side]
    return panelId === undefined || panelId === null ? active !== null : active === panelId
  }

  const open = (side: AgentPanelSide, panelId: AgentPanelId): void => {
    if (!isPanelId(panelId)) return
    activePanels.value[side] = panelId
  }

  const close = (side: AgentPanelSide): void => {
    activePanels.value[side] = null
  }

  const toggle = (side: AgentPanelSide, panelId: AgentPanelId): void => {
    if (activePanels.value[side] === panelId) close(side)
    else open(side, panelId)
  }

  const clear = (): void => {
    const next = emptyState()
    for (const side of SIDES) activePanels.value[side] = next[side]
  }

  return {
    activePanels,
    activeLeftPanel,
    activeRightPanel,
    activePanel,
    isOpen,
    open,
    close,
    toggle,
    clear,
  }
}

export { DEFAULT_STORAGE_KEY as AGENT_PANEL_STORAGE_KEY }
