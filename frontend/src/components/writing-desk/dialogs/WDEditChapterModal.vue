<template>
  <Teleport to="body">
    <div v-if="show" class="xq-dialog-overlay" @click.self="$emit('close')">
      <div class="xq-dialog-shell m3-edit-dialog" :class="show ? 'scale-100 opacity-100' : 'scale-95 opacity-0'">
        <div class="xq-dialog-header">
          <div>
            <p class="xq-dialog-kicker">Chapter Outline</p>
            <h2 class="xq-dialog-title">编辑章节大纲</h2>
            <p class="xq-dialog-subtitle">微调标题、摘要与 AI 重写方向，确保后续章节生成承接准确。</p>
          </div>
          <button type="button" @click="$emit('close')" class="xq-dialog-close" aria-label="关闭">
            ×
          </button>
        </div>

        <div v-if="editableChapter" class="xq-dialog-body xq-soft-grid">
          <div class="xq-field-panel">
            <label for="chapter-title" class="md-text-field-label mb-2">章节标题</label>
            <input
              id="chapter-title"
              v-model="editableChapter.title"
              type="text"
              class="md-text-field-input w-full"
              placeholder="请输入章节标题"
            >
          </div>

          <div class="xq-field-panel">
            <label for="chapter-summary" class="md-text-field-label mb-2">章节摘要</label>
            <textarea
              id="chapter-summary"
              v-model="editableChapter.summary"
              rows="5"
              class="md-textarea w-full"
              placeholder="请输入章节摘要"
            ></textarea>
          </div>

          <div class="xq-field-panel">
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
                :disabled="!editableChapter || isRewriting || isSaving"
                @click="rewriteWithAI"
              >
                {{ isRewriting ? 'AI 重写中...' : 'AI 重写摘要' }}
              </button>
            </div>
          </div>
        </div>

        <div class="xq-dialog-footer">
          <button type="button" @click="$emit('close')" class="md-btn md-btn-outlined md-ripple" :disabled="isSaving">
            取消
          </button>
          <button
            type="button"
            @click="saveChanges"
            class="md-btn md-btn-filled md-ripple disabled:opacity-50"
            :disabled="!isChanged || isSaving"
          >
            {{ isSaving ? '保存中...' : '保存更改' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ChapterOutline } from '@/api/novel'

interface Props {
  show: boolean
  chapter: ChapterOutline | null
  isRewriting?: boolean
  isSaving?: boolean
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
