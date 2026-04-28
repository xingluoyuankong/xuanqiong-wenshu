<template>
  <div v-if="show" class="md-dialog-overlay" @click.self="$emit('close')">
    <div class="md-dialog w-full max-w-3xl m3-edit-dialog flex flex-col" :class="show ? 'scale-100 opacity-100' : 'scale-95 opacity-0'">
      <div class="shrink-0 flex justify-between items-center p-6 border-b" style="border-bottom-color: var(--md-outline-variant);">
        <h2 class="md-headline-small font-semibold">编辑章节大纲</h2>
        <button type="button" @click="$emit('close')" class="md-icon-btn md-ripple">
          <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </button>
      </div>

      <div v-if="editableChapter" class="flex-1 min-h-0 overflow-y-auto p-6 space-y-6">
        <div>
          <label for="chapter-title" class="md-text-field-label mb-2">章节标题</label>
          <input
            id="chapter-title"
            v-model="editableChapter.title"
            type="text"
            class="md-text-field-input w-full"
            placeholder="请输入章节标题"
          >
        </div>

        <div>
          <label for="chapter-summary" class="md-text-field-label mb-2">章节摘要</label>
          <textarea
            id="chapter-summary"
            v-model="editableChapter.summary"
            rows="5"
            class="md-textarea w-full"
            placeholder="请输入章节摘要"
          ></textarea>
        </div>

        <div>
          <label for="rewrite-direction" class="md-text-field-label mb-2">AI 重写方向（可选）</label>
          <textarea
            id="rewrite-direction"
            v-model="rewriteDirection"
            rows="3"
            class="md-textarea w-full"
            placeholder="例如：冲突更强、结尾更狠、情绪更细腻"
          ></textarea>
          <div class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="preset in rewriteDirectionPresets"
              :key="preset"
              type="button"
              class="md-btn md-btn-outlined md-ripple text-xs"
              @click="appendRewriteDirection(preset)"
            >
              {{ preset }}
            </button>
            <button
              type="button"
              class="md-btn md-btn-text md-ripple text-xs"
              @click="rewriteDirection = ''"
            >
              清空方向
            </button>
          </div>
          <div class="mt-3 flex justify-end">
            <button
              type="button"
              class="md-btn md-btn-tonal md-ripple disabled:opacity-50"
              :disabled="!editableChapter || isRewriting"
              @click="rewriteWithAI"
            >
              {{ isRewriting ? 'AI 重写中...' : 'AI 重写摘要' }}
            </button>
          </div>
        </div>
      </div>

      <div class="shrink-0 flex justify-end gap-4 p-6 border-t" style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);">
        <button type="button" @click="$emit('close')" class="md-btn md-btn-outlined md-ripple">
          取消
        </button>
        <button type="button" @click="saveChanges" class="md-btn md-btn-filled md-ripple disabled:opacity-50" :disabled="!isChanged">
          保存更改
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ChapterOutline } from '@/api/novel'

interface Props {
  show: boolean
  chapter: ChapterOutline | null
  isRewriting?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', chapter: ChapterOutline): void
  (e: 'rewrite', payload: { chapter: ChapterOutline; direction?: string }): void
}>()

const editableChapter = ref<ChapterOutline | null>(null)
const rewriteDirection = ref('')
const rewriteDirectionPresets = [
  '强化本章主冲突',
  '提升情绪浓度',
  '增加伏笔与回收',
  '让人物动机更清晰',
  '结尾悬念更强',
  '对话更有潜台词',
  '反转更自然',
  '节奏更紧凑',
]

watch(
  () => props.chapter,
  (newChapter) => {
    editableChapter.value = newChapter ? { ...newChapter } : null
  },
  { deep: true, immediate: true }
)

watch(
  () => props.show,
  (visible) => {
    if (!visible) {
      rewriteDirection.value = ''
    }
  }
)

const isChanged = computed(() => {
  if (!props.chapter || !editableChapter.value) {
    return false
  }
  return (
    props.chapter.title !== editableChapter.value.title ||
    props.chapter.summary !== editableChapter.value.summary
  )
})

const saveChanges = () => {
  if (!editableChapter.value || !isChanged.value) {
    return
  }
  emit('save', editableChapter.value)
}

const rewriteWithAI = () => {
  if (!editableChapter.value) {
    return
  }
  emit('rewrite', {
    chapter: editableChapter.value,
    direction: rewriteDirection.value.trim() || undefined,
  })
}

const appendRewriteDirection = (preset: string) => {
  const current = rewriteDirection.value.trim()
  if (!current) {
    rewriteDirection.value = preset
    return
  }
  if (!current.includes(preset)) {
    rewriteDirection.value = `${current}；${preset}`
  }
}
</script>

<style scoped>
.m3-edit-dialog {
  border-radius: var(--md-radius-xl);
  max-width: min(800px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
}
</style>
