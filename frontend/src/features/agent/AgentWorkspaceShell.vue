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
    <section class="agent-layout">
      <aside class="agent-sidebar"><slot name="sidebar" /></aside>
      <section class="agent-main"><slot name="main" /></section>
      <aside class="agent-activity"><slot name="activity" /></aside>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    busy?: boolean
    projectTitle?: string | null
    sessionStatus?: string | null
    hasSelectedProject?: boolean
  }>(),
  { busy: false, projectTitle: null, sessionStatus: null, hasSelectedProject: false },
)

const statusText = computed(() => {
  if (props.sessionStatus) return `会话已恢复 · ${props.sessionStatus}`
  if (props.hasSelectedProject) return '正在准备项目会话'
  return '选择项目后，Agent 会限制在该项目范围内工作'
})
</script>

<style scoped>
.agent-page {
  display: grid;
  gap: 0.75rem;
  min-width: 0;
  padding: clamp(0.6rem, 1.5vw, 1rem);
}
.agent-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: clamp(0.9rem, 2vw, 1.4rem);
  border-radius: var(--xq-radius-lg);
}
.agent-kicker { margin: 0 0 0.35rem; color: var(--xq-gold-deep); font-size: 0.72rem; font-weight: 900; letter-spacing: 0.16em; }
.agent-hero h1 { margin: 0; font-family: var(--xq-font-serif); font-size: clamp(1.45rem, 2.5vw, 2.25rem); }
.agent-hero p { max-width: 52rem; margin: 0.45rem 0 0; color: var(--xq-ink-muted); line-height: 1.55; }
.agent-status { display: grid; align-content: center; min-width: min(15rem, 28vw); gap: 0.3rem; padding: 0.75rem; border: 1px solid var(--xq-border); border-radius: var(--xq-radius-md); background: rgba(255, 255, 255, 0.7); }
.agent-status small { color: var(--xq-ink-muted); line-height: 1.45; }
.status-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: var(--xq-jade); }
.status-dot.busy { background: #d97706; }
.agent-layout {
  display: grid;
  grid-template-columns: minmax(176px, 13.5rem) minmax(0, 1fr) minmax(238px, 18rem);
  gap: 0.75rem;
  align-items: start;
  min-width: 0;
}
.agent-sidebar,
.agent-main,
.agent-activity {
  display: grid;
  min-width: 0;
  gap: 0.75rem;
}
.agent-sidebar {
  position: sticky;
  top: 0.75rem;
  max-height: calc(100vh - 1.5rem);
  overflow: auto;
  scrollbar-gutter: stable;
}
.agent-main {
  min-height: min(72vh, 56rem);
}
.agent-activity {
  position: sticky;
  top: 0.75rem;
  max-height: calc(100vh - 1.5rem);
  overflow: auto;
  scrollbar-gutter: stable;
}
.agent-main > *,
.agent-sidebar > *,
.agent-activity > * { min-width: 0; }
@media (max-width: 1120px) {
  .agent-layout { grid-template-columns: minmax(168px, 12rem) minmax(0, 1fr) minmax(220px, 15rem); gap: 0.6rem; }
  .agent-page { padding-inline: 0.65rem; }
}
@media (max-width: 880px) {
  .agent-layout { grid-template-columns: minmax(160px, 11rem) minmax(0, 1fr); }
  .agent-activity { position: static; grid-column: 1 / -1; max-height: none; overflow: visible; }
}
@media (max-width: 650px) {
  .agent-layout { grid-template-columns: 1fr; }
  .agent-sidebar, .agent-main, .agent-activity { grid-column: auto; position: static; max-height: none; overflow: visible; }
  .agent-hero { align-items: stretch; flex-direction: column; }
  .agent-status { min-width: 0; }
}

/* 主页面继续持有业务模板；壳层用 :deep 保持三个命名 Slot 内既有 Agent 样式。 */
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
