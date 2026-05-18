<template>
  <span class="xq-badge" :class="[`xq-badge--${tone}`]">
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'gold' | 'jade' | 'ink' | 'danger' | 'muted'
  }>(),
  {
    tone: 'gold',
  },
)
</script>

<style scoped>
.xq-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 1.75rem;
  padding: 0 0.75rem;
  border: 1px solid transparent;
  border-radius: var(--xq-radius-pill);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.xq-badge--gold {
  color: var(--xq-gold-deep);
  background: rgba(214, 169, 79, 0.14);
  border-color: rgba(214, 169, 79, 0.26);
}

.xq-badge--jade {
  color: #1f6f5e;
  background: rgba(61, 143, 125, 0.12);
  border-color: rgba(61, 143, 125, 0.22);
}

.xq-badge--ink {
  color: #fffaf0;
  background: rgba(13, 16, 33, 0.86);
  border-color: rgba(214, 169, 79, 0.22);
}

.xq-badge--danger {
  color: #9b2e25;
  background: rgba(185, 74, 61, 0.12);
  border-color: rgba(185, 74, 61, 0.22);
}

.xq-badge--muted {
  color: var(--xq-ink-muted);
  background: rgba(255, 250, 240, 0.62);
  border-color: var(--xq-border);
}
</style>
