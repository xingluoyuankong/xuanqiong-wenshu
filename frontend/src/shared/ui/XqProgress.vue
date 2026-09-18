<template>
  <div class="xq-progress" :aria-label="label" role="progressbar" :aria-valuenow="safeValue" aria-valuemin="0" aria-valuemax="100">
    <div class="xq-progress__meta">
      <span>{{ label }}</span>
      <strong>{{ safeValue }}%</strong>
    </div>
    <div class="xq-progress__track">
      <div class="xq-progress__bar" :style="{ width: `${safeValue}%` }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    value?: number
    label?: string
  }>(),
  {
    value: 0,
    label: '进度',
  },
)

const safeValue = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.value) || 0))))
</script>

<style scoped>
.xq-progress {
  display: grid;
  gap: 0.55rem;
}

.xq-progress__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--xq-ink-muted);
  font-size: 0.82rem;
  font-weight: 700;
}

.xq-progress__meta strong {
  color: var(--xq-gold-deep);
}

.xq-progress__track {
  overflow: hidden;
  height: 0.6rem;
  border-radius: var(--xq-radius-pill);
  background: rgba(93, 70, 43, 0.1);
}

.xq-progress__bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--xq-gold-deep), var(--xq-gold), #67e8f9);
  transition: width var(--xq-normal);
}
</style>
