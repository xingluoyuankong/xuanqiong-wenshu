<template>
  <Teleport to="body">
    <div v-if="show" class="xq-dialog-overlay" @click.self="$emit('close')">
      <div class="xq-dialog-shell m3-edit-dialog" :class="show ? 'scale-100 opacity-100' : 'scale-95 opacity-0'">
        <div class="xq-dialog-header">
          <div>
            <p class="xq-dialog-kicker">Chapter Outline</p>
            <h2 class="xq-dialog-title">{{ pick('编辑章节大纲', 'Edit chapter outline') }}</h2>
            <p class="xq-dialog-subtitle">{{ pick('微调标题、摘要与 AI 重写方向，确保后续章节生成承接准确。', 'Fine-tune the title, summary, and AI rewrite direction so later chapters follow on accurately.') }}</p>
          </div>
          <button type="button" @click="$emit('close')" class="xq-dialog-close" :aria-label="t('common.close')">
            ×
          </button>
        </div>

        <div v-if="editableChapter" class="xq-dialog-body xq-soft-grid">
          <div class="xq-field-panel">
            <label for="chapter-title" class="md-text-field-label mb-2">{{ pick('章节标题', 'Chapter title') }}</label>
            <input
              id="chapter-title"
              v-model="editableChapter.title"
              type="text"
              class="md-text-field-input w-full"
              :placeholder="pick('请输入章节标题', 'Enter the chapter title')"
            >
          </div>

          <div class="xq-field-panel">
            <label for="chapter-summary" class="md-text-field-label mb-2">{{ pick('章节摘要', 'Chapter summary') }}</label>
            <textarea
              id="chapter-summary"
              v-model="editableChapter.summary"
              rows="5"
              class="md-textarea w-full"
              :placeholder="pick('请输入章节摘要', 'Enter the chapter summary')"
            ></textarea>
          </div>

          <div class="xq-field-panel">
            <label for="rewrite-direction" class="md-text-field-label mb-2">{{ pick('AI 重写方向（可选）', 'AI rewrite direction (optional)') }}</label>
            <textarea
              id="rewrite-direction"
              v-model="rewriteDirection"
              rows="3"
              class="md-textarea w-full"
              :placeholder="pick('例如：冲突更强、结尾更狠、情绪更细腻', 'For example: sharper conflict, harsher ending, subtler emotion')"
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
                {{ pick('清空方向', 'Clear direction') }}
              </button>
            </div>
            <div class="mt-3 flex justify-end">
              <button
                type="button"
                class="md-btn md-btn-tonal md-ripple disabled:opacity-50"
                :disabled="!editableChapter || isRewriting || isSaving"
                @click="rewriteWithAI"
              >
                {{ isRewriting ? pick('AI 重写中...', 'AI is rewriting...') : pick('AI 重写摘要', 'Rewrite summary with AI') }}
              </button>
            </div>
          </div>
        </div>

        <div class="xq-dialog-footer">
          <button type="button" @click="$emit('close')" class="md-btn md-btn-outlined md-ripple" :disabled="isSaving">
            {{ t('common.cancel') }}
          </button>
          <button
            type="button"
            @click="saveChanges"
            class="md-btn md-btn-filled md-ripple disabled:opacity-50"
            :disabled="!isChanged || isSaving"
          >
            {{ isSaving ? pick('保存中...', 'Saving...') : pick('保存更改', 'Save changes') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ChapterOutline } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

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
const { pick, t } = useLocale()
// 预设文案随语言切换刷新，因此用 computed 而非顶层常量
const rewriteDirectionPresets = computed(() => [
  pick('强化本章主冲突', 'Strengthen the main conflict'),
  pick('提升情绪浓度', 'Raise emotional intensity'),
  pick('增加伏笔与回收', 'Add foreshadowing and payoff'),
  pick('让人物动机更清晰', 'Clarify character motivation'),
  pick('结尾悬念更强', 'Sharpen the closing hook'),
  pick('对话更有潜台词', 'Add subtext to the dialogue'),
  pick('反转更自然', 'Make the reversal feel natural'),
  pick('节奏更紧凑', 'Tighten the pacing'),
])

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
    rewriteDirection.value = `${current}${pick('；', '; ')}${preset}`
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
