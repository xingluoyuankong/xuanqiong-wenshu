<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch, type ComponentPublicInstance } from 'vue'
import type { AgentReasoningChunk } from './reducers/agentEventReducer'

type Measurement = { content: string; height: number }
type Anchor = { key: string; offset: number }
const props = withDefaults(defineProps<{
  chunks?: AgentReasoningChunk[]
  text?: string
  contextKey?: string
  status?: 'idle' | 'streaming' | 'completed' | 'failed'
  hasPrevious?: boolean
  loadingPrevious?: boolean
  previousError?: string
}>(), {
  chunks: () => [], text: '', contextKey: '', status: 'idle',
  hasPrevious: false, loadingPrevious: false, previousError: '',
})
const emit = defineEmits<{ (event: 'load-previous'): void }>()
const manuallyExpanded = ref(false)
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
const bodyRef = ref<HTMLElement | null>(null)
const listRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const viewportHeight = ref(416)
const listOffset = ref(0)
const contentWidth = ref(576)
const measuredHeights = ref<Record<string, Measurement>>({})
const elements = new Map<string, Element>()
const itemRefs = new Map<string, (element: Element | ComponentPublicInstance | null) => void>()
let anchor: Anchor | null = null
let followTail = true
let tailPinned = false
let queued = false
let disposed = false
let copyGeneration = 0
let copyTimer: ReturnType<typeof setTimeout> | undefined
const GAP = 9
const OVERSCAN_PX = 240
const isStreaming = computed(() => props.status === 'streaming')
const isExpanded = computed(() => isStreaming.value || manuallyExpanded.value)
const statusLabel = computed(() => ({ idle: '待开始', streaming: '流式中', completed: '已完成', failed: '失败' })[props.status])
const displayText = computed(() => props.text || props.chunks.map((chunk) => chunk.content).join(''))
const items = computed(() => {
  const chunks = props.chunks.length ? props.chunks : props.text ? [{ sequence: 0, chunkIndex: 0, content: props.text }] : []
  return chunks.map(chunk => ({
    chunk,
    // Sequence alone is not an identity: chunks and runs may reuse it.
    key: JSON.stringify([props.contextKey, chunk.runId, chunk.id ?? [chunk.sequence, chunk.chunkIndex]]),
  }))
})
const layout = computed(() => {
  let top = 0
  return items.value.map((item, index) => {
    const measurement = measuredHeights.value[item.key]
    const columns = Math.max(1, Math.floor(contentWidth.value / 8))
    const lines = item.chunk.content.split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / columns)), 0)
    const height = measurement?.content === item.chunk.content ? measurement.height : Math.max(24, lines * 22)
    const result = { ...item, index, top, height }
    top += height + GAP
    return result
  })
})
const totalHeight = computed(() => {
  const last = layout.value.at(-1)
  return last ? last.top + last.height : 0
})
// Lower bound on row bottoms. Out-of-range offsets select the last row, never all rows.
const indexAt = (offset: number) => {
  let low = 0
  let high = layout.value.length
  while (low < high) {
    const mid = (low + high) >>> 1
    const item = layout.value[mid]!
    if (item.top + item.height < offset) low = mid + 1
    else high = mid
  }
  return Math.min(low, Math.max(0, layout.value.length - 1))
}
const visibleItems = computed(() => {
  if (!isExpanded.value || !layout.value.length) return []
  const top = Math.min(Math.max(0, scrollTop.value - listOffset.value), Math.max(0, totalHeight.value - viewportHeight.value))
  const start = indexAt(Math.max(0, top - OVERSCAN_PX))
  const end = indexAt(top + viewportHeight.value + OVERSCAN_PX)
  return layout.value.slice(start, end + 1)
})
const captureAnchor = () => {
  const item = layout.value[indexAt(Math.max(0, scrollTop.value - listOffset.value))]
  anchor = item ? { key: item.key, offset: scrollTop.value - listOffset.value - item.top } : null
}
const readMetrics = () => {
  const body = bodyRef.value
  const list = listRef.value
  if (!body || !list) return
  viewportHeight.value = body.clientHeight || 416
  // Geometry includes the history button, error text, and body padding.
  if (body.getBoundingClientRect().height > 0) {
    listOffset.value = list.getBoundingClientRect().top - body.getBoundingClientRect().top - body.clientTop + body.scrollTop
  }
  const width = list.getBoundingClientRect().width
  if (width > 0 && Math.abs(width - contentWidth.value) > 0.5) {
    contentWidth.value = width
    measuredHeights.value = {}
  }
}
const measureRows = () => {
  const updates: Record<string, Measurement> = {}
  for (const item of visibleItems.value) {
    const height = elements.get(item.key)?.getBoundingClientRect().height || 0
    const previous = measuredHeights.value[item.key]
    if (height > 0 && (!previous || previous.content !== item.chunk.content || Math.abs(previous.height - height) > 0.5)) {
      updates[item.key] = { content: item.chunk.content, height }
    }
  }
  if (Object.keys(updates).length) measuredHeights.value = { ...measuredHeights.value, ...updates }
}
const restorePosition = () => {
  const body = bodyRef.value
  if (!body) return
  const maximum = Math.max(0, body.scrollHeight > 0 ? body.scrollHeight - body.clientHeight : totalHeight.value + listOffset.value - viewportHeight.value)
  const anchored = anchor && layout.value.find(item => item.key === anchor!.key)
  const target = followTail && (isStreaming.value || tailPinned) ? maximum
    : anchored && anchor ? listOffset.value + anchored.top + anchor.offset : scrollTop.value
  body.scrollTop = Math.min(maximum, Math.max(0, target))
  // Programmatic scrolling need not emit an event before the next render.
  scrollTop.value = body.scrollTop
}
const scheduleLayout = () => {
  if (queued || disposed) return
  queued = true
  void nextTick(async () => {
    if (!disposed && isExpanded.value) {
      readMetrics()
      measureRows()
      await nextTick()
      if (!disposed && isExpanded.value) restorePosition()
    }
    queued = false
  })
}
const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(scheduleLayout) : null
const itemRef = (key: string) => {
  if (!itemRefs.has(key)) itemRefs.set(key, (value: Element | ComponentPublicInstance | null) => {
    const element = value instanceof Element ? value : null
    const previous = elements.get(key)
    if (previous === element) return
    if (previous) observer?.unobserve(previous)
    elements.delete(key)
    if (element) {
      elements.set(key, element)
      observer?.observe(element)
      scheduleLayout()
    }
  })
  return itemRefs.get(key)!
}
const onScroll = () => {
  const body = bodyRef.value
  if (!body) return
  scrollTop.value = body.scrollTop
  viewportHeight.value = body.clientHeight || 416
  const height = body.scrollHeight || totalHeight.value + listOffset.value
  followTail = height - viewportHeight.value - body.scrollTop < 72
  tailPinned = followTail
  captureAnchor()
}
const onKeydown = (event: KeyboardEvent) => {
  if (!(event.ctrlKey || event.metaKey) || !['Home', 'End'].includes(event.key)) return
  event.preventDefault()
  anchor = null
  followTail = event.key === 'End'
  tailPinned = followTail
  scrollTop.value = 0
  scheduleLayout()
}
const toggle = () => { manuallyExpanded.value = !manuallyExpanded.value }
const copyText = async () => {
  const generation = ++copyGeneration
  if (copyTimer) clearTimeout(copyTimer)
  try {
    if (!navigator.clipboard) throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(displayText.value)
    if (disposed || generation !== copyGeneration) return
    copyState.value = 'copied'
    copyTimer = setTimeout(() => { copyState.value = 'idle' }, 1200)
  } catch {
    if (!disposed && generation === copyGeneration) copyState.value = 'failed'
  }
}
watch(bodyRef, (body, oldBody) => {
  if (oldBody) observer?.unobserve(oldBody)
  if (body) observer?.observe(body)
  scheduleLayout()
}, { flush: 'post' })
watch(() => props.contextKey, () => {
  anchor = null
  followTail = true
  tailPinned = false
  scrollTop.value = 0
  measuredHeights.value = {}
  manuallyExpanded.value = false
  copyGeneration++
  copyState.value = 'idle'
  if (copyTimer) clearTimeout(copyTimer)
})
watch(items, () => {
  const keys = new Set(items.value.map(item => item.key))
  measuredHeights.value = Object.fromEntries(Object.entries(measuredHeights.value).filter(([key]) => keys.has(key)))
  for (const key of itemRefs.keys()) if (!keys.has(key)) itemRefs.delete(key)
}, { flush: 'pre' })
watch([layout, isExpanded, () => props.status, () => props.hasPrevious, () => props.previousError], scheduleLayout, { flush: 'post', immediate: true })
onBeforeUnmount(() => {
  disposed = true
  observer?.disconnect()
  elements.clear()
  itemRefs.clear()
  if (copyTimer) clearTimeout(copyTimer)
})
</script>

<template>
  <section v-if="displayText || chunks.length || status !== 'idle'" class="reasoning-card" data-testid="agent-reasoning-card" aria-live="polite">
    <header class="reasoning-card__header">
      <button type="button" class="reasoning-card__toggle" data-testid="agent-reasoning-toggle" :aria-expanded="isExpanded" @click="toggle">
        <span class="reasoning-card__title"><span aria-hidden="true">◌</span> Provider 原始 reasoning</span>
        <span class="reasoning-card__status" :class="`is-${status}`">{{ statusLabel }}<template v-if="chunks.length"> · {{ chunks.length }} 段</template></span>
      </button>
      <button v-if="displayText" type="button" class="reasoning-card__copy" data-testid="agent-reasoning-copy" @click="copyText">{{ copyState === 'copied' ? '已复制' : copyState === 'failed' ? '复制失败，请重试' : '复制' }}</button>
    </header>
    <div v-show="isExpanded" ref="bodyRef" tabindex="0" aria-label="推理历史" class="reasoning-card__body" data-testid="agent-reasoning-body" @scroll="onScroll" @keydown="onKeydown">
      <button v-if="hasPrevious" type="button" class="reasoning-card__load" data-testid="agent-reasoning-load-previous" :disabled="loadingPrevious" @click="emit('load-previous')">
        {{ loadingPrevious ? '正在加载更早 reasoning…' : '加载更早 reasoning' }}
      </button>
      <p v-if="previousError" class="reasoning-card__error">{{ previousError }}</p>
      <div v-if="isExpanded" ref="listRef" class="reasoning-card__virtual-list" data-testid="agent-reasoning-virtual-list" :style="{ minHeight: `${totalHeight}px` }">
        <pre v-for="item in visibleItems" :key="item.key" :ref="itemRef(item.key)" :data-reasoning-index="item.index" :style="{ top: `${item.top}px` }">{{ item.chunk.content }}</pre>
      </div>
    </div>
  </section>
</template>

<style scoped>
.reasoning-card { margin: .75rem 0; border: 1px solid color-mix(in srgb, #7c3aed 34%, var(--xq-border)); border-radius: var(--xq-radius-md); background: color-mix(in srgb, #f5f3ff 88%, transparent); overflow: hidden; }
.reasoning-card__header { display: flex; align-items: stretch; justify-content: space-between; gap: .5rem; }
.reasoning-card__toggle { display: flex; align-items: center; justify-content: space-between; flex: 1; min-width: 0; gap: .6rem; padding: .65rem .8rem; border: 0; color: #5b21b6; background: transparent; text-align: left; cursor: pointer; }
.reasoning-card__title { font-weight: 800; }
.reasoning-card__status { color: #6b7280; font-size: .76rem; font-weight: 700; white-space: nowrap; }
.reasoning-card__status.is-streaming { color: #7c3aed; }
.reasoning-card__status.is-failed { color: var(--xq-cinnabar); }
.reasoning-card__copy { align-self: center; margin-right: .55rem; padding: .25rem .45rem; border: 1px solid color-mix(in srgb, #7c3aed 24%, var(--xq-border)); border-radius: .4rem; color: #6d28d9; background: white; cursor: pointer; }
.reasoning-card__body { border-top: 1px solid color-mix(in srgb, #7c3aed 18%, var(--xq-border)); padding: .7rem .8rem; max-height: 26rem; overflow: auto; overflow-anchor: none; }
.reasoning-card__load { margin-bottom: .55rem; padding: .3rem .55rem; border: 1px solid color-mix(in srgb, #7c3aed 24%, var(--xq-border)); border-radius: .4rem; color: #6d28d9; background: white; cursor: pointer; }
.reasoning-card__load:disabled { cursor: wait; opacity: .65; }
.reasoning-card__error { margin: 0 0 .45rem; color: var(--xq-cinnabar); font-size: .78rem; }
.reasoning-card__virtual-list { position: relative; }
.reasoning-card__virtual-list pre { position: absolute; left: 0; right: 0; min-height: 24px; margin: 0; color: #312e81; white-space: pre-wrap; overflow-wrap: anywhere; font: .82rem/1.65 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
</style>
