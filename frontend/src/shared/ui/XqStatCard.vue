<template>
  <article class="xq-stat-card">
    <span v-if="kicker" class="xq-stat-card__kicker">{{ kicker }}</span>
    <strong class="xq-stat-card__value">{{ value }}</strong>
    <span class="xq-stat-card__label">{{ label }}</span>
    <p v-if="hint" class="xq-stat-card__hint">{{ hint }}</p>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  kicker?: string
  value: string | number
  label: string
  hint?: string
}>()
</script>

<style scoped>
.xq-stat-card {
  display: grid;
  gap: 0.3rem;
  min-width: 0;
  padding: 1rem;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
}

.xq-stat-card__kicker {
  color: var(--xq-gold-deep);
  font-size: 0.68rem;
  font-weight: 900;
  letter-spacing: 0.16em;
}

.xq-stat-card__value {
  overflow: hidden;
  color: var(--xq-ink);
  font-family: var(--xq-font-serif);
  font-size: clamp(1.45rem, 3vw, 2.1rem);
  line-height: 1.12;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xq-stat-card__label {
  color: var(--xq-ink-muted);
  font-size: 0.88rem;
  font-weight: 800;
}

.xq-stat-card__hint {
  margin: 0.1rem 0 0;
  color: var(--xq-ink-faint);
  font-size: 0.78rem;
  line-height: 1.55;
}
</style>
