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
            <DialogPanel class="md-dialog m3-outline-dialog flex flex-col text-left transition-all sm:my-6 sm:w-full sm:max-w-2xl">
              <div class="flex-1 min-h-0 overflow-y-auto px-5 pt-6 pb-5 sm:px-6 sm:pt-6 sm:pb-5">
                <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
                  <div class="mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full sm:mx-0 sm:h-12 sm:w-12" style="background-color: var(--md-primary-container);">
                    <svg class="h-6 w-6" style="color: var(--md-on-primary-container);" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m6-6H6" />
                    </svg>
                  </div>
                  <div class="text-center sm:flex-1 sm:text-left">
                    <DialogTitle as="h3" class="md-headline-small font-semibold leading-7">生成后续大纲</DialogTitle>
                    <div class="mt-2">
                      <p class="md-body-medium md-on-surface-variant">请输入或选择要生成的后续章节数量。</p>
                    </div>
                  </div>
                </div>
                <div class="mt-6">
                  <label for="numChapters" class="md-text-field-label">生成数量</label>
                  <input type="number" name="numChapters" id="numChapters" v-model.number="numChapters" class="md-text-field-input w-full mt-2" min="1" max="1000">
                  <div class="mt-5 flex flex-wrap justify-center gap-3">
                    <button type="button" v-for="count in [1, 2, 5, 10, 20, 50]" :key="count" @click="setNumChapters(count)"
                      :class="['md-btn md-btn-outlined md-ripple', numChapters === count ? 'm3-count-selected' : '']">
                      {{ count }} 章
                    </button>
                  </div>
                  <p class="mt-3 md-body-small md-on-surface-variant">
                    建议每次生成 10-50 章，长篇项目可分多次扩展，稳定性更高。
                  </p>
                </div>

                <div class="mt-6 grid grid-cols-1 gap-4">
                  <div>
                    <label for="targetTotalChapters" class="md-text-field-label">全书目标总章节（可选）</label>
                    <input
                      id="targetTotalChapters"
                      type="number"
                      v-model.number="targetTotalChapters"
                      class="md-text-field-input w-full mt-2"
                      min="1"
                      placeholder="例如：200"
                    >
                  </div>
                  <div>
                    <label for="targetTotalWords" class="md-text-field-label">全书目标总字数（可选）</label>
                    <input
                      id="targetTotalWords"
                      type="number"
                      v-model.number="targetTotalWords"
                      class="md-text-field-input w-full mt-2"
                      min="10000"
                      step="10000"
                      placeholder="例如：200000"
                    >
                  </div>
                  <div>
                    <label for="chapterWordTarget" class="md-text-field-label">单章目标字数（可选）</label>
                    <input
                      id="chapterWordTarget"
                      type="number"
                      v-model.number="chapterWordTarget"
                      class="md-text-field-input w-full mt-2"
                      min="500"
                      step="100"
                      placeholder="例如：2500"
                    >
                  </div>
                  <p class="md-body-small md-on-surface-variant">
                    说明：设置“全书目标总章节/总字数”后，系统会在生成大纲时避免过早完结。
                  </p>
                </div>
              </div>
              <div class="shrink-0 border-t px-6 py-4 sm:flex sm:flex-row-reverse sm:px-8" style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);">
                <button type="button" class="md-btn md-btn-filled md-ripple sm:ml-3 sm:w-auto w-full justify-center" @click="handleGenerate">生成</button>
                <button type="button" class="md-btn md-btn-outlined md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3" @click="$emit('close')">取消</button>
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

interface Props {
  show: boolean
}

const props = defineProps<Props>()

interface OutlineGeneratePayload {
  numChapters: number
  targetTotalChapters?: number
  targetTotalWords?: number
  chapterWordTarget?: number
}

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'generate', payload: OutlineGeneratePayload): void
}>()

const numChapters = ref(5)
const targetTotalChapters = ref<number | null>(null)
const targetTotalWords = ref<number | null>(null)
const chapterWordTarget = ref<number | null>(null)

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
</style>
