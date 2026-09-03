<script setup lang="ts">
import { computed } from 'vue'
import type { AgentPanelId, AgentPanelSide } from '../composables/useAgentPanelState'

export type AgentRailIconName =
  | 'project'
  | 'content'
  | 'characters'
  | 'world'
  | 'materials'
  | 'tools'
  | 'log'
  | 'run'
  | 'progress'
  | 'artifact'
  | 'quality'
  | 'menu'
  | (string & {})

export interface AgentRailPanelDefinition {
  id: AgentPanelId
  label: string
  shortLabel?: string
  description?: string
  icon?: AgentRailIconName
  badge?: string | number
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    side: AgentPanelSide
    activePanel?: AgentPanelId | null
    panels?: AgentRailPanelDefinition[]
    panelDefinitions?: AgentRailPanelDefinition[]
    ariaLabel?: string
  }>(),
  {
    activePanel: null,
    panels: () => [],
    panelDefinitions: undefined,
    ariaLabel: undefined,
  },
)

const emit = defineEmits<{
  (event: 'toggle', panelId: AgentPanelId): void
  (event: 'open', panelId: AgentPanelId): void
  (event: 'close'): void
  (event: 'select', panelId: AgentPanelId): void
  (event: 'update:activePanel', panelId: AgentPanelId | null): void
}>()

const resolvedPanels = computed(() => props.panelDefinitions ?? props.panels)
const railLabel = computed(() =>
  props.ariaLabel || (props.side === 'left' ? '项目资源面板' : '运行信息面板'),
)

const iconAliases: Record<string, AgentRailIconName> = {
  project: 'project',
  projects: 'project',
  content: 'content',
  chapter: 'content',
  chapters: 'content',
  characters: 'characters',
  character: 'characters',
  world: 'world',
  materials: 'materials',
  material: 'materials',
  tools: 'tools',
  log: 'log',
  runtime: 'log',
  run: 'run',
  progress: 'progress',
  artifact: 'artifact',
  artifacts: 'artifact',
  quality: 'quality',
}

const fallbackIconByPanel: Record<string, AgentRailIconName> = {
  project: 'project',
  content: 'content',
  chapters: 'content',
  characters: 'characters',
  world: 'world',
  materials: 'materials',
  tools: 'tools',
  log: 'log',
  runtime: 'log',
  run: 'run',
  progress: 'progress',
  artifacts: 'artifact',
  quality: 'quality',
}

const iconKind = (panel: AgentRailPanelDefinition): AgentRailIconName => {
  const requested = panel.icon || fallbackIconByPanel[panel.id.toLowerCase()] || 'menu'
  return iconAliases[requested.toLowerCase()] || requested
}

const isKnownIcon = (icon: AgentRailIconName): boolean =>
  ['project', 'content', 'characters', 'world', 'materials', 'tools', 'log', 'run', 'progress', 'artifact', 'quality', 'menu'].includes(icon)

const buttonLabel = (panel: AgentRailPanelDefinition): string =>
  panel.description ? `${panel.label}：${panel.description}` : panel.label

const activate = (panel: AgentRailPanelDefinition): void => {
  if (panel.disabled) return
  const nextPanel = props.activePanel === panel.id ? null : panel.id
  emit('toggle', panel.id)
  emit('select', panel.id)
  emit('update:activePanel', nextPanel)
  if (nextPanel) emit('open', nextPanel)
  else emit('close')
}
</script>

<template>
  <nav
    class="agent-rail"
    :class="[`agent-rail--${side}`, { 'agent-rail--empty': resolvedPanels.length === 0 }]"
    data-testid="agent-rail"
    :data-side="side"
    :aria-label="railLabel"
    role="toolbar"
  >
    <button
      v-for="panel in resolvedPanels"
      :key="panel.id"
      class="agent-rail__button"
      :class="{ 'is-active': activePanel === panel.id }"
      :data-testid="`agent-rail-panel-${side}-${panel.id}`"
      :aria-label="buttonLabel(panel)"
      :aria-pressed="activePanel === panel.id"
      :disabled="panel.disabled"
      :title="panel.label"
      type="button"
      @click="activate(panel)"
    >
      <span class="agent-rail__icon" aria-hidden="true">
        <svg v-if="isKnownIcon(iconKind(panel))" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path v-if="iconKind(panel) === 'project'" d="M4 6.5A2.5 2.5 0 0 1 6.5 4h4l2 2h5A2.5 2.5 0 0 1 20 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z" />
          <path v-else-if="iconKind(panel) === 'content'" d="M6 4.5h9.5L19 8v11.5H6zM15 4.5V8h4M9 12h7M9 15.5h7" />
          <path v-else-if="iconKind(panel) === 'characters'" d="M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM5 20a7 7 0 0 1 14 0M18 9a2.5 2.5 0 0 1 1.5 4.5M19 16a4.5 4.5 0 0 1 2 4" />
          <path v-else-if="iconKind(panel) === 'world'" d="M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM3.8 10h16.4M3.8 14h16.4M12 3.5c2 2.2 3 5 3 8.5s-1 6.3-3 8.5c-2-2.2-3-5-3-8.5s1-6.3 3-8.5Z" />
          <path v-else-if="iconKind(panel) === 'materials'" d="m12 3 8 4.5-8 4.5-8-4.5zM4 12l8 4.5 8-4.5M4 16.5l8 4.5 8-4.5" />
          <path v-else-if="iconKind(panel) === 'tools'" d="m14.5 6.5 3-3 3 3-3 3M4 20l8.5-8.5M7 4.5 19.5 17 17 19.5 4.5 7z" />
          <path v-else-if="iconKind(panel) === 'log'" d="M5 5h14v14H5zM8 9h8M8 12h8M8 15h5" />
          <path v-else-if="iconKind(panel) === 'run'" d="m9 5 10 7-10 7z" />
          <path v-else-if="iconKind(panel) === 'progress'" d="M5 19V9M12 19V5M19 19v-7" />
          <path v-else-if="iconKind(panel) === 'artifact'" d="M6 3.5h9l3 3V20.5H6zM15 3.5v3h3M9 11h6M9 14.5h6" />
          <path v-else-if="iconKind(panel) === 'quality'" d="m12 3 2.4 5 5.6.8-4 3.9.9 5.6-4.9-2.6-4.9 2.6.9-5.6-4-3.9L9.6 8z" />
          <path v-else d="M5 12h14M12 5v14" />
        </svg>
        <span v-else>{{ panel.icon || panel.shortLabel || panel.label.slice(0, 1) }}</span>
      </span>
      <span class="agent-rail__label">{{ panel.shortLabel || panel.label }}</span>
      <span v-if="panel.badge !== undefined" class="agent-rail__badge" aria-hidden="true">{{ panel.badge }}</span>
    </button>
  </nav>
</template>

<style scoped>
.agent-rail {
  --agent-rail-size: 3.25rem;
  display: flex;
  flex: 0 0 var(--agent-rail-size);
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  width: var(--agent-rail-size);
  min-width: var(--agent-rail-size);
  padding: 0.45rem 0.25rem;
  box-sizing: border-box;
  border: 1px solid var(--xq-border, rgba(148, 163, 184, 0.35));
  border-radius: 0.9rem;
  background: var(--xq-paper, rgba(255, 255, 255, 0.82));
  box-shadow: 0 0.6rem 1.5rem rgba(15, 23, 42, 0.06);
}
.agent-rail--right { order: 2; }
.agent-rail__button {
  position: relative;
  display: grid;
  place-items: center;
  width: 2.7rem;
  min-height: 2.7rem;
  padding: 0.35rem;
  box-sizing: border-box;
  border: 1px solid transparent;
  border-radius: 0.7rem;
  color: var(--xq-ink-muted, #64748b);
  background: transparent;
  cursor: pointer;
  font: inherit;
  transition: color 160ms ease, background 160ms ease, border-color 160ms ease, transform 160ms ease;
}
.agent-rail__button:hover:not(:disabled) { color: var(--xq-ink, #0f172a); background: rgba(148, 163, 184, 0.14); }
.agent-rail__button:focus-visible { outline: 3px solid rgba(37, 99, 235, 0.3); outline-offset: 2px; }
.agent-rail__button.is-active { color: var(--xq-gold-deep, #a16207); border-color: rgba(180, 130, 30, 0.32); background: rgba(245, 158, 11, 0.13); }
.agent-rail__button:disabled { opacity: 0.42; cursor: not-allowed; }
.agent-rail__icon { display: grid; place-items: center; width: 1.25rem; height: 1.25rem; font-size: 1.05rem; font-weight: 800; line-height: 1; }
.agent-rail__icon svg { display: block; width: 100%; height: 100%; }
.agent-rail__label { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.agent-rail__badge { position: absolute; top: 0.05rem; right: 0.05rem; min-width: 1rem; padding: 0.05rem 0.2rem; box-sizing: border-box; border-radius: 999px; color: white; background: var(--xq-cinnabar, #dc2626); font-size: 0.62rem; font-weight: 800; line-height: 1.2; }
@media (max-width: 650px) {
  .agent-rail { --agent-rail-size: 100%; flex: 1 1 auto; flex-direction: row; justify-content: space-around; width: 100%; min-width: 0; padding: 0.3rem; border-radius: 0.75rem; }
  .agent-rail--right { order: initial; }
  .agent-rail__button { flex: 1 1 0; width: auto; min-height: 2.5rem; }
}
</style>
