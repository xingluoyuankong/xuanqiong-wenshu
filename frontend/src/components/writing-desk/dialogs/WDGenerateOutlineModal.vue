<!-- AIMETA P=生成大纲弹窗_大纲生成界面|R=大纲生成表单|NR=不含生成逻辑|E=component:WDGenerateOutlineModal|X=ui|A=生成弹窗|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="$emit('close')">
      <TransitionChild as="template" enter="ease-out duration-300" enter-from="opacity-0" enter-to="opacity-100" leave="ease-in duration-200" leave-from="opacity-100" leave-to="opacity-0">
        <div class="fixed inset-0" style="background-color: rgba(0, 0, 0, 0.32);" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <TransitionChild as="template" enter="ease-out duration-300" enter-from="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" enter-to="opacity-100 translate-y-0 sm:scale-100" leave="ease-in duration-200" leave-from="opacity-100 translate-y-0 sm:scale-100" leave-to="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95">
            <DialogPanel class="xq-dialog-shell m3-outline-dialog text-left transition-all">
              <div class="xq-dialog-header">
                <div>
                  <p class="xq-dialog-kicker">Outline Expansion</p>
                  <DialogTitle as="h3" class="xq-dialog-title">{{ pick('生成后续大纲', 'Generate follow-up outline') }}</DialogTitle>
                  <p class="xq-dialog-subtitle">{{ pick('请输入或选择要生成的后续章节数量；长篇项目建议分批扩展，便于稳定控制节奏。', 'Enter or pick how many follow-up chapters to generate. For long projects, expand in batches to keep the pacing under control.') }}</p>
                </div>
                <button type="button" class="xq-dialog-close" @click="$emit('close')" :aria-label="t('common.close')">×</button>
              </div>
              <div class="xq-dialog-body">
                <div class="xq-field-panel">
                  <label for="numChapters" class="md-text-field-label">{{ pick('生成数量', 'Chapters to generate') }}</label>
                  <input type="number" name="numChapters" id="numChapters" v-model.number="numChapters" class="md-text-field-input w-full mt-2" min="1" max="1000">
                  <div class="mt-5 flex flex-wrap justify-center gap-3">
                    <button type="button" v-for="count in [1, 2, 5, 10, 20, 50]" :key="count" @click="setNumChapters(count)"
                      :class="['md-btn md-btn-outlined md-ripple', numChapters === count ? 'm3-count-selected' : '']">
                      {{ count }} {{ pick('章', count === 1 ? 'chapter' : 'chapters') }}
                    </button>
                  </div>
                  <p class="mt-3 md-body-small md-on-surface-variant">
                    {{ pick('建议每次生成 10-50 章，长篇项目可分多次扩展，稳定性更高。', 'Generating 10-50 chapters at a time works best; long projects can be expanded over several passes for better stability.') }}
                  </p>
                </div>

                <div class="mt-6 grid grid-cols-1 gap-4">
                  <div>
                    <label for="targetTotalChapters" class="md-text-field-label">{{ pick('全书目标总章节（可选）', 'Target total chapters (optional)') }}</label>
                    <input
                      id="targetTotalChapters"
                      type="number"
                      v-model.number="targetTotalChapters"
                      class="md-text-field-input w-full mt-2"
                      min="1"
                      :placeholder="pick('例如：200', 'e.g. 200')"
                    >
                  </div>
                  <div>
                    <label for="targetTotalWords" class="md-text-field-label">{{ pick('全书目标总字数（可选）', 'Target total word count (optional)') }}</label>
                    <input
                      id="targetTotalWords"
                      type="number"
                      v-model.number="targetTotalWords"
                      class="md-text-field-input w-full mt-2"
                      min="10000"
                      step="10000"
                      :placeholder="pick('例如：200000', 'e.g. 200000')"
                    >
                  </div>
                  <div>
                    <label for="chapterWordTarget" class="md-text-field-label">{{ pick('单章目标字数（可选）', 'Target word count per chapter (optional)') }}</label>
                    <input
                      id="chapterWordTarget"
                      type="number"
                      v-model.number="chapterWordTarget"
                      class="md-text-field-input w-full mt-2"
                      min="500"
                      step="100"
                      :placeholder="pick('例如：2500', 'e.g. 2500')"
                    >
                  </div>
                  <p class="md-body-small md-on-surface-variant">
                    {{ pick('说明：设置“全书目标总章节/总字数”后，系统会在生成大纲时避免过早完结。', 'Note: once a target total chapter or word count is set, outline generation avoids ending the story too early.') }}
                  </p>
                </div>

                <!-- 长篇小说模式 -->
                <div class="form-section mt-6">
                  <label class="toggle-row">
                    <input type="checkbox" v-model="longFormMode" />
                    <span>{{ pick('长篇小说模式', 'Long-form novel mode') }}</span>
                    <span class="hint">{{ pick('适用于50章以上长篇', 'For books longer than 50 chapters') }}</span>
                  </label>
                  <div v-if="longFormMode" class="longform-controls mt-3">
                    <label>{{ pick('卷数', 'Volumes') }} <input type="number" v-model.number="volumeCount" min="1" max="20" class="md-text-field-input" /></label>
                    <label>{{ pick('每卷章节', 'Chapters per volume') }} <input type="number" v-model.number="chaptersPerVolume" min="5" max="50" class="md-text-field-input" /></label>
                    <span class="computed">{{ pick('预计总章节', 'Estimated total chapters') }}: {{ volumeCount * chaptersPerVolume }}{{ pick('章', ' chapters') }}</span>
                  </div>
                </div>
              </div>
              <div class="xq-dialog-footer">
                <button type="button" class="md-btn md-btn-filled md-ripple sm:ml-3 sm:w-auto w-full justify-center" @click="handleGenerate">{{ t('common.generate') }}</button>
                <button type="button" class="md-btn md-btn-outlined md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3" @click="$emit('close')">{{ t('common.cancel') }}</button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { useLocale } from '@/composables/useLocale'

interface Props {
  show: boolean
}

const props = defineProps<Props>()

interface OutlineGeneratePayload {
  numChapters: number
  targetTotalChapters?: number
  targetTotalWords?: number
  chapterWordTarget?: number
  longFormMode?: boolean
  volumeCount?: number
  chaptersPerVolume?: number
}

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'generate', payload: OutlineGeneratePayload): void
}>()

const { pick, t } = useLocale()

const numChapters = ref(5)
const targetTotalChapters = ref<number | null>(null)
const targetTotalWords = ref<number | null>(null)
const chapterWordTarget = ref<number | null>(null)
const longFormMode = ref(false)
const volumeCount = ref(8)
const chaptersPerVolume = ref(25)

const setNumChapters = (count: number) => {
  numChapters.value = count
}

const handleGenerate = () => {
  if (numChapters.value <= 0 || numChapters.value > 1000) {
    return
  }
  if (targetTotalChapters.value !== null && targetTotalChapters.value <= 0) {
    return
  }
  if (targetTotalWords.value !== null && targetTotalWords.value < 10000) {
    return
  }
  if (chapterWordTarget.value !== null && chapterWordTarget.value < 500) {
    return
  }

  const payload: OutlineGeneratePayload = {
    numChapters: numChapters.value,
  }
  if (targetTotalChapters.value) {
    payload.targetTotalChapters = targetTotalChapters.value
  }
  if (targetTotalWords.value) {
    payload.targetTotalWords = targetTotalWords.value
  }
  if (chapterWordTarget.value) {
    payload.chapterWordTarget = chapterWordTarget.value
  }
  if (longFormMode.value) {
    payload.longFormMode = true
    payload.volumeCount = volumeCount.value
    payload.chaptersPerVolume = chaptersPerVolume.value
  }

  emit('generate', payload)
  emit('close')
}
</script>

<style scoped>
.m3-outline-dialog {
  border-radius: var(--md-radius-xl);
  max-height: calc(100vh - 32px);
}

.m3-count-selected {
  background-color: var(--md-primary);
  color: var(--md-on-primary);
  border-color: transparent;
}

.form-section {
  border-top: 1px solid var(--md-outline-variant, #ccc);
  padding-top: 1rem;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 500;
}

.toggle-row input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
}

.hint {
  font-size: 0.78rem;
  color: var(--md-on-surface-variant, #666);
  font-weight: 400;
}

.longform-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--md-surface-variant, #f5f5f5);
  border-radius: 6px;
}

.longform-controls label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
}

.longform-controls input[type="number"] {
  width: 5rem;
}

.computed {
  font-size: 0.85rem;
  color: var(--md-primary, #1976d2);
  font-weight: 600;
}
</style>
