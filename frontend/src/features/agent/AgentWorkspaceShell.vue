<template>
  <main class="agent-page xq-page-canvas" data-testid="agent-workspace">
    <section class="agent-hero xq-page-topbar xq-paper-grain">
      <div>
        <p class="agent-kicker">玄穹文枢 · PROJECT AGENT</p>
        <h1>小说创作 Agent 工作台</h1>
        <p>用自然语言统一规划、查看和调用当前小说项目的能力；读取与分析自动执行，写入与高风险操作先展示计划。</p>
      </div>
      <div class="agent-status" data-testid="agent-status">
        <span class="status-dot" :class="{ busy }" />
        <strong>{{ projectTitle || '尚未选择小说项目' }}</strong>
        <small>{{ statusText }}</small>
      </div>
    </section>

    <section class="agent-layout" :class="{ 'has-left-panel': activeLeftPanel, 'has-right-panel': activeRightPanel }">
      <aside class="agent-sidebar-rail" data-testid="agent-left-rail">
        <AgentRail
          side="left"
          :active-panel="activeLeftPanel"
          :panels="leftPanels"
          aria-label="项目资源面板"
          @toggle="togglePanel('left', $event)"
        />
      </aside>
      <aside
        class="agent-side-panel agent-sidebar agent-side-panel--left"
        :class="{ 'agent-panel-open': activeLeftPanel }"
        data-testid="agent-left-panel"
        :data-panel-open="Boolean(activeLeftPanel)"
        :aria-hidden="!activeLeftPanel"
      >
        <header class="agent-side-panel__header">
          <div>
            <strong>{{ leftPanelTitle }}</strong>
            <small>项目资源与上下文</small>
          </div>
          <button type="button" class="agent-side-panel__close" data-testid="agent-side-panel-close-left" aria-label="关闭项目资源面板" @click="closePanel('left')">×</button>
        </header>
        <div class="agent-side-panel__body"><slot name="sidebar" /></div>
      </aside>

      <section class="agent-main"><slot name="main" /></section>

      <aside
        class="agent-side-panel agent-activity agent-side-panel--right"
        :class="{ 'agent-panel-open': activeRightPanel }"
        data-testid="agent-right-panel"
        :data-panel-open="Boolean(activeRightPanel)"
        :aria-hidden="!activeRightPanel"
      >
        <header class="agent-side-panel__header">
          <div>
            <strong>{{ rightPanelTitle }}</strong>
            <small>运行轨迹与诊断信息</small>
          </div>
          <button type="button" class="agent-side-panel__close" data-testid="agent-side-panel-close-right" aria-label="关闭运行信息面板" @click="closePanel('right')">×</button>
        </header>
        <div class="agent-side-panel__body"><slot name="activity" /></div>
      </aside>
      <aside class="agent-activity-rail" data-testid="agent-right-rail">
        <AgentRail
          side="right"
          :active-panel="activeRightPanel"
          :panels="rightPanels"
          aria-label="运行信息面板"
          @toggle="togglePanel('right', $event)"
        />
      </aside>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AgentRail, { type AgentRailPanelDefinition } from './layout/AgentRail.vue'
import { useAgentPanelState, type AgentPanelId, type AgentPanelSide } from './composables/useAgentPanelState'

const props = withDefaults(
  defineProps<{
    busy?: boolean
    projectTitle?: string | null
    sessionStatus?: string | null
    hasSelectedProject?: boolean
  }>(),
  { busy: false, projectTitle: null, sessionStatus: null, hasSelectedProject: false },
)

const panelState = useAgentPanelState({
  storageKey: 'xuanqiong-wenshu:agent-workspace-panels',
})
const activeLeftPanel = panelState.activeLeftPanel
const activeRightPanel = panelState.activeRightPanel

const leftPanels: AgentRailPanelDefinition[] = [
  { id: 'project', label: '项目', shortLabel: '项目', icon: 'project' },
  { id: 'content', label: '内容', shortLabel: '内容', icon: 'content' },
  { id: 'characters', label: '人物', shortLabel: '人物', icon: 'characters' },
  { id: 'world', label: '世界观', shortLabel: '世界', icon: 'world' },
  { id: 'materials', label: '资料', shortLabel: '资料', icon: 'materials' },
  { id: 'tools', label: '工具', shortLabel: '工具', icon: 'tools' },
]
const rightPanels: AgentRailPanelDefinition[] = [
  { id: 'log', label: '运行日志', shortLabel: '日志', icon: 'log' },
  { id: 'run', label: '运行详情', shortLabel: '运行', icon: 'run' },
  { id: 'progress', label: '进度', shortLabel: '进度', icon: 'progress' },
  { id: 'artifact', label: '结果产物', shortLabel: '产物', icon: 'artifact' },
  { id: 'quality', label: '质量', shortLabel: '质量', icon: 'quality' },
]

const panelLabel = (panels: AgentRailPanelDefinition[], active: AgentPanelId | null, fallback: string) =>
  panels.find((panel) => panel.id === active)?.label || fallback
const leftPanelTitle = computed(() => panelLabel(leftPanels, activeLeftPanel.value, '项目资源'))
const rightPanelTitle = computed(() => panelLabel(rightPanels, activeRightPanel.value, '运行信息'))

const togglePanel = (side: AgentPanelSide, panelId: AgentPanelId) => panelState.toggle(side, panelId)
const closePanel = (side: AgentPanelSide) => panelState.close(side)

const statusText = computed(() => {
  if (props.sessionStatus) return `会话已恢复 · ${props.sessionStatus}`
  if (props.hasSelectedProject) return '正在准备项目会话'
  return '选择项目后，Agent 会限制在该项目范围内工作'
})
</script>

<style scoped>
.agent-page { display: grid; gap: 0.75rem; min-width: 0; padding: clamp(0.6rem, 1.5vw, 1rem); }
.agent-hero { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: clamp(0.9rem, 2vw, 1.4rem); border-radius: var(--xq-radius-lg); }
.agent-kicker { margin: 0 0 0.35rem; color: var(--xq-gold-deep); font-size: 0.72rem; font-weight: 900; letter-spacing: 0.16em; }
.agent-hero h1 { margin: 0; font-family: var(--xq-font-serif); font-size: clamp(1.45rem, 2.5vw, 2.25rem); }
.agent-hero p { max-width: 52rem; margin: 0.45rem 0 0; color: var(--xq-ink-muted); line-height: 1.55; }
.agent-status { display: grid; align-content: center; min-width: min(15rem, 28vw); gap: 0.3rem; padding: 0.75rem; border: 1px solid var(--xq-border); border-radius: var(--xq-radius-md); background: rgba(255, 255, 255, 0.7); }
.agent-status small { color: var(--xq-ink-muted); line-height: 1.45; }
.status-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: var(--xq-jade); }
.status-dot.busy { background: #d97706; }
.agent-layout { display: grid; grid-template-columns: 3.5rem 0 minmax(0, 1fr) 0 3.5rem; grid-template-areas: 'left-rail left-panel main right-panel right-rail'; gap: 0.65rem; align-items: stretch; min-width: 0; min-height: min(72vh, 56rem); }
.agent-layout.has-left-panel { grid-template-columns: 3.5rem minmax(15rem, 20rem) minmax(0, 1fr) 0 3.5rem; }
.agent-layout.has-right-panel { grid-template-columns: 3.5rem 0 minmax(0, 1fr) minmax(16rem, 22rem) 3.5rem; }
.agent-layout.has-left-panel.has-right-panel { grid-template-columns: 3.5rem minmax(15rem, 20rem) minmax(0, 1fr) minmax(16rem, 22rem) 3.5rem; }
.agent-sidebar-rail { grid-area: left-rail; }
.agent-activity-rail { grid-area: right-rail; }
.agent-side-panel--left { grid-area: left-panel; }
.agent-side-panel--right { grid-area: right-panel; }
.agent-sidebar-rail, .agent-activity-rail { min-width: 0; position: sticky; top: 0.75rem; height: fit-content; z-index: 3; }
.agent-side-panel { display: none; min-width: 0; min-height: 0; max-height: calc(100vh - 1.5rem); overflow: hidden; border: 1px solid color-mix(in srgb, var(--xq-border) 82%, transparent); border-radius: var(--xq-radius-md); background: rgba(255, 255, 255, 0.46); box-shadow: var(--xq-shadow-sm, 0 8px 24px rgba(16, 24, 40, 0.08)); }
.agent-side-panel.agent-panel-open { display: flex; flex-direction: column; }
.agent-side-panel__header { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.7rem 0.8rem; border-bottom: 1px solid var(--xq-border); background: rgba(255, 255, 255, 0.72); }
.agent-side-panel__header div { display: grid; gap: 0.15rem; min-width: 0; }
.agent-side-panel__header small { color: var(--xq-ink-muted); font-size: 0.72rem; }
.agent-side-panel__close { width: 1.8rem; height: 1.8rem; border: 0; border-radius: 0.5rem; color: var(--xq-ink-muted); background: transparent; font-size: 1.35rem; cursor: pointer; }
.agent-side-panel__close:hover { background: rgba(15, 23, 42, 0.08); color: var(--xq-ink); }
.agent-side-panel__body { min-width: 0; min-height: 0; overflow: auto; padding: 0.45rem; scrollbar-gutter: stable; }
.agent-main { grid-area: main; display: grid; min-width: 0; min-height: min(72vh, 56rem); }
.agent-main > * { min-width: 0; }
@media (max-width: 1120px) {
  .agent-layout { gap: 0.5rem; grid-template-columns: 3.25rem 0 minmax(0, 1fr) 0 3.25rem; }
  .agent-layout.has-left-panel { grid-template-columns: 3.25rem minmax(13rem, 17rem) minmax(0, 1fr) 0 3.25rem; }
  .agent-layout.has-right-panel { grid-template-columns: 3.25rem 0 minmax(0, 1fr) minmax(14rem, 18rem) 3.25rem; }
  .agent-layout.has-left-panel.has-right-panel { grid-template-columns: 3.25rem minmax(13rem, 17rem) minmax(0, 1fr) minmax(14rem, 18rem) 3.25rem; }
  .agent-page { padding-inline: 0.65rem; }
}
@media (max-width: 960px) {
  .agent-layout, .agent-layout.has-left-panel, .agent-layout.has-right-panel, .agent-layout.has-left-panel.has-right-panel { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-areas: 'main'; position: relative; }
  .agent-main { grid-row: 1; min-height: min(78vh, 60rem); }
  .agent-sidebar-rail { position: fixed; left: 0.65rem; top: 5.5rem; }
  .agent-activity-rail { position: fixed; right: 0.65rem; top: 5.5rem; }
  .agent-side-panel { position: fixed; top: 5.5rem; bottom: 0.75rem; width: min(22rem, calc(100vw - 5rem)); z-index: 4; }
  .agent-side-panel--left { left: 0.65rem; }
  .agent-side-panel--right { right: 0.65rem; }
}
@media (max-width: 650px) {
  .agent-hero { align-items: stretch; flex-direction: column; }
  .agent-status { min-width: 0; }
  .agent-layout, .agent-layout.has-left-panel, .agent-layout.has-right-panel, .agent-layout.has-left-panel.has-right-panel { display: flex; flex-direction: column; min-height: calc(100vh - 9rem); padding-bottom: calc(4.25rem + env(safe-area-inset-bottom)); }
  .agent-main { order: 1; min-height: calc(100vh - 11rem); }
  .agent-sidebar-rail, .agent-activity-rail { position: fixed; top: auto; bottom: calc(0.55rem + env(safe-area-inset-bottom)); z-index: 5; }
  .agent-sidebar-rail { left: 0.55rem; width: calc(50% - 0.8rem); }
  .agent-activity-rail { right: 0.55rem; width: calc(50% - 0.8rem); }
  .agent-side-panel { top: 4.8rem; bottom: calc(4.1rem + env(safe-area-inset-bottom)); width: calc(100vw - 1.1rem); }
  .agent-side-panel--left, .agent-side-panel--right { left: 0.55rem; right: 0.55rem; }
}


/* 主页面继续持有业务模板；壳层用 :deep 保持命名插槽内既有 Agent 样式。 */
:deep(.muted) { color: var(--xq-ink-muted); line-height: 1.6; }
:deep(.error) { color: var(--xq-cinnabar); }
:deep(.agent-sidebar label) { display: block; margin-bottom: 0.4rem; font-weight: 800; }
:deep(.agent-sidebar select) { width: 100%; min-height: 2.5rem; box-sizing: border-box; border: 1px solid var(--xq-border); border-radius: 0.7rem; padding: 0.7rem; background: rgba(255, 255, 255, 0.85); font: inherit; }
:deep(.session-actions), :deep(.approval-actions) { display: flex; gap: 0.5rem; margin-top: 0.55rem; }
:deep(.timeline-filters) { display: grid; gap: 0.4rem; margin-bottom: 0.6rem; }
:deep(.timeline-filters select) { width: 100%; border: 1px solid var(--xq-border); border-radius: 0.5rem; padding: 0.45rem; background: rgba(255, 255, 255, 0.85); font: inherit; }
:deep(.timeline-list), :deep(.tool-list), :deep(.step-list), :deep(.plan-list), :deep(.blocker-list), :deep(.artifact-diff-list) { display: grid; margin: 0; padding: 0; list-style: none; }
:deep(.timeline-list) { gap: 0.65rem; max-height: 24rem; overflow: auto; }
:deep(.timeline-list li), :deep(.tool-list li), :deep(.step-list li) { display: grid; gap: 0.2rem; padding-bottom: 0.55rem; border-bottom: 1px dashed var(--xq-border); }
:deep(.timeline-list span), :deep(.timeline-list small), :deep(.tool-list small), :deep(.step-list small), :deep(.step-list span) { color: var(--xq-ink-muted); line-height: 1.5; }
:deep(.tool-list), :deep(.step-list) { gap: 0.65rem; }
:deep(.tool-list span) { width: max-content; padding: 0.12rem 0.45rem; border-radius: 999px; background: rgba(37, 99, 235, 0.1); color: #2563eb; font-size: 0.72rem; font-weight: 800; }
:deep(.plan-list) { gap: 0.7rem; }
:deep(.plan-list li) { display: grid; gap: 0.2rem; }
:deep(.plan-list span) { color: var(--xq-ink-muted); }
:deep(.plan-list em) { color: #b45309; font-style: normal; font-size: 0.78rem; }
:deep(.approval-card) { display: grid; gap: 0.35rem; padding: 0.65rem; border: 1px solid var(--xq-border); border-radius: 0.6rem; margin-bottom: 0.55rem; }
:deep(.approval-card span) { font-size: 0.78rem; color: var(--xq-gold-deep); }
:deep(.approval-approved) { color: var(--xq-jade) !important; }
:deep(.approval-rejected) { color: var(--xq-cinnabar) !important; }
:deep(.blocker-list) { gap: 0.55rem; margin-top: 0.6rem; }
:deep(.blocker-list li) { display: grid; gap: 0.2rem; padding: 0.45rem; border-left: 3px solid var(--xq-cinnabar); background: rgba(239, 68, 68, 0.06); }
:deep(.blocker-list span), :deep(.blocker-list small) { color: var(--xq-ink-muted); line-height: 1.45; }
:deep(.artifact-diff-list) { gap: 0.25rem; max-height: 20rem; overflow: auto; margin-top: 0.6rem; font-family: monospace; }
:deep(.artifact-diff-list li) { display: grid; grid-template-columns: 2.5rem 1fr; gap: 0.5rem; padding: 0.2rem 0.35rem; border-radius: 0.25rem; }
:deep(.diff-added) { background: rgba(16, 185, 129, 0.15); }
:deep(.diff-modified) { background: rgba(245, 158, 11, 0.18); }
:deep(.diff-deleted) { text-decoration: line-through; background: rgba(239, 68, 68, 0.12); }
:deep(.run-summary) { display: grid; grid-template-columns: auto 1fr; gap: 0.45rem 0.75rem; margin: 0; }
:deep(.run-summary dt) { color: var(--xq-ink-muted); }
:deep(.run-summary dd) { margin: 0; font-weight: 700; }
:deep(.agent-activity ul) { margin: 0; padding-left: 1.2rem; line-height: 1.9; }
:deep(.rewrite-instruction-list) { display: grid; gap: 0.45rem; margin: 0.5rem 0; padding: 0.55rem; border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 0.55rem; background: rgba(245, 158, 11, 0.06); }
:deep(.rewrite-instruction) { display: grid; gap: 0.2rem; padding: 0.35rem 0; border-bottom: 1px dashed var(--xq-border); }
:deep(.rewrite-instruction:last-child) { border-bottom: 0; }
:deep(.rewrite-instruction span), :deep(.rewrite-instruction small) { color: var(--xq-ink-muted); line-height: 1.45; }
</style>
