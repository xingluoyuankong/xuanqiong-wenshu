<template>
  <section class="xq-panel xq-paper-grain" :class="[`xq-panel--${tone}`]">
    <header v-if="$slots.kicker || title || subtitle || $slots.actions" class="xq-panel__header">
      <div>
        <p v-if="$slots.kicker" class="xq-panel__kicker"><slot name="kicker" /></p>
        <h2 v-if="title" class="xq-panel__title">{{ title }}</h2>
        <p v-if="subtitle" class="xq-panel__subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="xq-panel__actions"><slot name="actions" /></div>
    </header>
    <div class="xq-panel__body"><slot /></div>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    tone?: 'paper' | 'ink' | 'glass'
  }>(),
  {
    tone: 'paper',
  },
)
</script>

<style scoped>
.xq-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  box-shadow: var(--xq-shadow-paper);
}

.xq-panel--paper {
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.94), rgba(239, 246, 255, 0.90));
}

.xq-panel--glass {
  background: var(--xq-bg-glass);
  backdrop-filter: blur(18px);
}

.xq-panel--ink {
  color: #ffffff;
  background:
    radial-gradient(circle at 20% 0%, rgba(14, 165, 233, 0.20), transparent 18rem),
    linear-gradient(135deg, var(--xq-bg-ink), var(--xq-bg-midnight));
  border-color: rgba(14, 165, 233, 0.24);
  box-shadow: var(--xq-shadow-floating);
}

.xq-panel__header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 1.5rem 1.5rem 0;
}

.xq-panel__kicker {
  margin: 0 0 0.4rem;
  color: var(--xq-gold-deep);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.xq-panel__title {
  margin: 0;
  font-family: var(--xq-font-serif);
  font-size: clamp(1.25rem, 2vw, 1.75rem);
  line-height: 1.25;
}

.xq-panel__subtitle {
  margin: 0.5rem 0 0;
  color: var(--xq-ink-muted);
  line-height: 1.75;
}

.xq-panel--ink .xq-panel__subtitle {
  color: rgba(255, 255, 255, 0.72);
}

.xq-panel__body {
  position: relative;
  z-index: 1;
  padding: 1.5rem;
}
</style>
