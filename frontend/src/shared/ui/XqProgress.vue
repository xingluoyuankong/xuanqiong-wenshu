<template>
  <div class="xq-progress">
    <div class="xq-progress__meta">
      <span class="xq-progress__label">{{ labelText }}</span>
      <strong class="xq-progress__value">{{ safeValue }}%</strong>
    </div>
    <div
      class="xq-progress__track"
      role="progressbar"
      :aria-label="labelText"
      :aria-valuenow="safeValue"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="xq-progress__bar" :style="{ width: barWidth }" />
      <span v-if="mascot" class="xq-progress__mascot" :style="{ left: `${safeValue}%` }">
        <PixelMascot :mascot-id="mascotId" :color="mascotColor" :size="22" :moving="safeValue < 100" />
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

import PixelMascot from '@/components/shared/PixelMascot.vue'
import { useLocale } from '@/composables/useLocale'
import { usePixelMascot } from '@/composables/usePixelMascot'

const props = withDefaults(
  defineProps<{
    value?: number
    label?: string
    /** 是否在进度点上挂一只像素吉祥物。 */
    mascot?: boolean
  }>(),
  {
    value: 0,
    label: '',
    mascot: false,
  },
)

const { pick } = useLocale()
const { mascotId, color: mascotColor, beginRun, endRun } = usePixelMascot()

const safeValue = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.value) || 0))))
const labelText = computed(() => props.label || pick('进度', 'Progress'))
const barWidth = computed(() => `${Math.max(safeValue.value, 1)}%`)

/** 推进中 = 已启动且未完成；进入该状态时随机换一种可爱姿态 */
const isAdvancing = computed(() => props.mascot && safeValue.value > 0 && safeValue.value < 100)
let counted = false

watch(
  isAdvancing,
  (advancing) => {
    if (advancing && !counted) {
      counted = true
      beginRun()
    } else if (!advancing && counted) {
      counted = false
      endRun()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (counted) {
    counted = false
    endRun()
  }
})
</script>

<style scoped>
.xq-progress {
  display: grid;
  gap: var(--xq-space-2);
}

.xq-progress__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--xq-space-2);
}

.xq-progress__label {
  overflow: hidden;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
  font-weight: var(--xq-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xq-progress__value {
  color: var(--xq-text);
  font-size: var(--xq-text-sm);
  font-weight: var(--xq-weight-bold);
  font-variant-numeric: tabular-nums;
}

.xq-progress__track {
  position: relative;
  height: 8px;
  border-radius: var(--xq-radius-pill);
  background: var(--xq-surface-3);
}

.xq-progress__bar {
  height: 100%;
  border-radius: inherit;
  background: var(--xq-accent);
  /* 均匀推进只能用 linear。 */
  transition: width 300ms linear;
}

.xq-progress__mascot {
  position: absolute;
  top: 50%;
  display: grid;
  place-items: center;
  transform: translate(-50%, -50%);
  transition: left 300ms linear;
  pointer-events: none;
}
</style>
