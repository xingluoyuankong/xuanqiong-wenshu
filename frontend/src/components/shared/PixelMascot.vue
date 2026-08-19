<template>
  <span
    class="pixel-mascot"
    :class="[`pixel-mascot--${activeGait}`, { 'is-static': !moving }]"
    :style="{ '--pixel-color': color, '--pixel-size': `${size}px` }"
    aria-hidden="true"
  >
    <span v-for="(row, rowIndex) in currentFrame" :key="rowIndex" class="pixel-mascot__row">
      <i
        v-for="(cell, cellIndex) in row"
        :key="cellIndex"
        class="pixel-mascot__cell"
        :data-ink="cell"
      />
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  buildMascotFrames,
  MASCOT_GAITS,
  usePixelMascot,
  type MascotGaitId,
  type PixelMascotId,
} from '@/composables/usePixelMascot'

const props = withDefaults(
  defineProps<{
    mascotId?: PixelMascotId
    color?: string
    size?: number
    moving?: boolean
    /** 显式指定姿态；不传则跟随全局设置（auto 时为随机姿态） */
    gait?: MascotGaitId
  }>(),
  { mascotId: 'cat', color: 'var(--xq-accent)', size: 30, moving: true },
)

const { gaitId: globalGaitId } = usePixelMascot()
const activeGait = computed<MascotGaitId>(() => props.gait || globalGaitId.value)
const frames = computed(() => buildMascotFrames(props.mascotId, activeGait.value))
const frameIndex = ref(0)
const currentFrame = computed(() => frames.value[frameIndex.value % frames.value.length])

/** 系统开启"减少动效"时不做逐帧播放，静止在第一帧 */
const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

let timer: ReturnType<typeof setInterval> | null = null

const stop = () => {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

const start = () => {
  stop()
  if (!props.moving || prefersReducedMotion()) {
    frameIndex.value = 0
    return
  }
  const duration =
    MASCOT_GAITS.find((item) => item.id === activeGait.value)?.frameDuration ?? 190
  timer = setInterval(() => {
    frameIndex.value = (frameIndex.value + 1) % frames.value.length
  }, duration)
}

watch(() => [props.moving, activeGait.value], start, { immediate: true })
onBeforeUnmount(stop)
</script>

<style scoped>
.pixel-mascot {
  /* 暗部由主色推导：不支持 color-mix 的环境回落到中性灰 */
  --pixel-shade: var(--xq-text-muted);
  --pixel-shade: color-mix(in srgb, var(--pixel-color) 58%, var(--xq-text));
  display: inline-flex;
  flex: 0 0 auto;
  flex-direction: column;
  width: var(--pixel-size);
  height: var(--pixel-size);
  image-rendering: pixelated;
  transform-origin: 50% 100%;
  will-change: transform;
}

.pixel-mascot__row {
  display: flex;
  flex: 1;
}

.pixel-mascot__cell {
  flex: 1;
  background: transparent;
}

.pixel-mascot__cell[data-ink='1'] {
  background: var(--pixel-color);
}

.pixel-mascot__cell[data-ink='2'] {
  background: var(--pixel-shade);
}

.pixel-mascot__cell[data-ink='4'] {
  background: var(--xq-warning);
}

.pixel-mascot__cell[data-ink='5'] {
  background: var(--xq-text);
}

.pixel-mascot__cell[data-ink='6'] {
  background: var(--xq-surface);
}

/* 姿态位移：逐帧像素负责肢体，容器动画负责整体体态 */
.pixel-mascot.is-static {
  animation: none;
}

.pixel-mascot--walk {
  animation: mascot-walk 760ms steps(2, end) infinite;
}

.pixel-mascot--run {
  animation: mascot-run 440ms steps(2, end) infinite;
}

.pixel-mascot--hop {
  animation: mascot-hop 680ms var(--xq-ease-out) infinite;
}

.pixel-mascot--swim {
  animation: mascot-swim 840ms ease-in-out infinite;
}

.pixel-mascot--waddle {
  animation: mascot-waddle 920ms ease-in-out infinite;
}

.pixel-mascot--wriggle {
  animation: mascot-wriggle 1040ms ease-in-out infinite;
}

@keyframes mascot-walk {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1px);
  }
}

@keyframes mascot-run {
  0%,
  100% {
    transform: translateY(0) rotate(-3deg);
  }
  50% {
    transform: translateY(-2px) rotate(-1deg);
  }
}

@keyframes mascot-hop {
  0%,
  100% {
    transform: translateY(0) scaleY(1);
  }
  30% {
    transform: translateY(-4px) scaleY(1.06);
  }
  60% {
    transform: translateY(0) scaleY(0.94);
  }
}

@keyframes mascot-swim {
  0%,
  100% {
    transform: translateY(0) rotate(-4deg);
  }
  50% {
    transform: translateY(-1px) rotate(4deg);
  }
}

@keyframes mascot-waddle {
  0%,
  100% {
    transform: rotate(-6deg);
  }
  50% {
    transform: rotate(6deg);
  }
}

@keyframes mascot-wriggle {
  0%,
  100% {
    transform: skewX(-6deg) translateY(0);
  }
  50% {
    transform: skewX(6deg) translateY(-1px);
  }
}
</style>
