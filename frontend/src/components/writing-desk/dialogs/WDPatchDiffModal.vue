<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="handleClose">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-160"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-slate-950/45 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-2 sm:p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-220"
            enter-from="opacity-0 translate-y-6 sm:scale-95"
            enter-to="opacity-100 translate-y-0 sm:scale-100"
            leave="ease-in duration-160"
            leave-from="opacity-100 translate-y-0 sm:scale-100"
            leave-to="opacity-0 translate-y-4 sm:scale-95"
          >
            <DialogPanel class="xq-dialog-shell xq-dialog-shell--xl xq-diff-dialog m3-patchdiff-dialog flex h-[calc(100vh-1rem)] flex-col overflow-hidden text-left">
              <!-- Header -->
              <div class="xq-dialog-header m3-patchdiff-dialog__head">
                <div class="min-w-0 flex-1">
                  <div class="m3-patchdiff-dialog__chips">
                    <span class="m3-reader-chip">{{ pick('精细编辑', 'Fine editing') }}</span>
                    <span class="m3-reader-chip">{{ pick(`第 ${activeChapterNumber} 章`, `Chapter ${activeChapterNumber}`) }}</span>
                  </div>
                  <DialogTitle as="h3" class="m3-patchdiff-title">
                    {{ pick('Patch+Diff 精细编辑', 'Patch + Diff fine editing') }}
                  </DialogTitle>
                  <p class="m3-patchdiff-subtitle">
                    {{ pick('对比原始文本与修改后文本，行级别高亮显示差异', 'Compare the original and revised text with line-level diff highlighting') }}
                  </p>
                </div>

                <div class="m3-patchdiff-dialog__actions">
                  <button type="button" class="xq-dialog-close md-ripple" @click="handleClose" :aria-label="t('common.close')">
                    ×
                  </button>
                </div>
              </div>

              <!-- Body -->
              <div class="xq-dialog-body m3-patchdiff-dialog__body">
                <!-- 输入编辑区 -->
                <div class="patchdiff-edit-area mb-4">
                  <div class="grid grid-cols-2 gap-4">
                    <!-- 原始文本 -->
                    <div class="flex flex-col">
                      <label class="md-text-field-label mb-2 flex items-center gap-2">
                        <span class="text-red-500">●</span> {{ pick('原始文本', 'Original text') }}
                      </label>
                      <textarea
                        v-model="originalText"
                        class="md-textarea flex-1 w-full resize-none bg-slate-50"
                        :placeholder="pick('请输入原始文本...', 'Enter the original text...')"
                        :disabled="true"
                        rows="6"
                      />
                      <div class="md-body-small md-on-surface-variant mt-1 text-right">
                        {{ formatWords(originalText.length) }}
                      </div>
                    </div>
                    <!-- 修改后文本 -->
                    <div class="flex flex-col">
                      <label class="md-text-field-label mb-2 flex items-center gap-2">
                        <span class="text-green-500">●</span> {{ pick('修改后文本', 'Revised text') }}
                      </label>
                      <textarea
                        v-model="patchedText"
                        class="md-textarea flex-1 w-full resize-none"
                        :placeholder="pick('请输入修改后的文本...', 'Enter the revised text...')"
                        :disabled="isApplying"
                        rows="6"
                      />
                      <div class="md-body-small md-on-surface-variant mt-1 text-right">
                        {{ formatWords(patchedText.length) }}
                      </div>
                    </div>
                  </div>
                  <div class="mt-3 flex justify-center gap-3">
                    <button
                      type="button"
                      class="md-btn md-btn-outlined md-ripple disabled:opacity-50"
                      :disabled="isApplying"
                      @click="resetPatchedText"
                    >
                      {{ pick('重置修改稿', 'Reset revision') }}
                    </button>
                    <button
                      type="button"
                      class="md-btn md-btn-tonal md-ripple disabled:opacity-50"
                      :disabled="isApplying || isGeneratingDiff || !originalText.trim() || !patchedText.trim()"
                      @click="generateDiffPreview"
                    >
                      <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      {{ pick('生成差异预览', 'Generate diff preview') }}
                    </button>
                  </div>
                </div>

                <!-- 差异预览区 -->
                <div v-if="diffLines.length > 0" class="patchdiff-preview flex-1 overflow-hidden">
                  <div class="flex items-center justify-between mb-2">
                    <label class="md-text-field-label">{{ pick('差异预览', 'Diff preview') }}</label>
                    <div class="flex items-center gap-2 text-xs">
                      <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-green-500"></span> {{ pick(`新增 ${diffSummary.added}`, `${diffSummary.added} added`) }}</span>
                      <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-red-500"></span> {{ pick(`删除 ${diffSummary.deleted}`, `${diffSummary.deleted} deleted`) }}</span>
                      <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-sky-500"></span> {{ pick(`修改 ${diffSummary.modified}`, `${diffSummary.modified} modified`) }}</span>
                    </div>
                  </div>
                  <div class="patchdiff-diff-container overflow-y-auto border rounded-lg">
                    <table class="w-full text-sm">
                      <thead class="sticky top-0 bg-slate-100 dark:bg-slate-800">
                        <tr>
                          <th class="w-12 px-2 py-1 text-center">{{ pick('行号', 'Line') }}</th>
                          <th class="px-2 py-1 text-left">{{ pick('原始内容', 'Original') }}</th>
                          <th class="px-2 py-1 text-left">{{ pick('修改后内容', 'Revised') }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(line, index) in diffLines"
                          :key="`${line.line_number}-${line.change_type}-${index}`"
                          :class="{
                            'bg-green-50 dark:bg-green-900/20': line.change_type === 'added',
                            'bg-red-50 dark:bg-red-900/20': line.change_type === 'deleted',
                            'bg-sky-50 dark:bg-sky-900/20': line.change_type === 'modified',
                          }"
                        >
                          <td class="px-2 py-1 text-center text-slate-400">{{ line.line_number }}</td>
                          <td class="px-2 py-1 font-mono text-xs" :class="line.original_line ? 'text-slate-700 dark:text-slate-300' : 'text-slate-300 dark:text-slate-600'">
                            {{ line.original_line || '⏎' }}
                          </td>
                          <td class="px-2 py-1 font-mono text-xs" :class="line.patched_line ? 'text-slate-700 dark:text-slate-300' : 'text-slate-300 dark:text-slate-600'">
                            {{ line.patched_line || '⏎' }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- 空状态 -->
                <div v-else-if="hasGeneratedDiff" class="patchdiff-empty flex-1 flex items-center justify-center">
                  <div class="text-center text-slate-400">
                    <svg class="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p>{{ pick('点击"生成差异预览"查看文本差异', 'Click "Generate diff preview" to see the text differences') }}</p>
                  </div>
                </div>
              </div>

              <!-- Footer -->
              <div class="xq-dialog-footer m3-patchdiff-dialog__foot">
                <div class="m3-patchdiff-dialog__foot-note">
                  <span v-if="isApplying">{{ pick('正在应用 Patch...', 'Applying patch...') }}</span>
                  <span v-else-if="diffLines.length > 0">
                    {{ pick(
                      `共 ${diffSummary.total_lines} 行，${diffSummary.added + diffSummary.modified} 处变更`,
                      `${diffSummary.total_lines} lines, ${diffSummary.added + diffSummary.modified} changes`
                    ) }}
                  </span>
                  <span v-else>{{ pick('输入原始文本和修改后文本，然后生成差异预览', 'Enter the original and revised text, then generate the diff preview') }}</span>
                </div>

                <div class="m3-patchdiff-dialog__foot-actions">
                  <button type="button" class="md-btn md-btn-outlined md-ripple" @click="handleClose">
                    {{ t('common.cancel') }}
                  </button>
                  <button
                    type="button"
                    class="md-btn md-btn-filled md-ripple disabled:opacity-50 disabled:cursor-not-allowed"
                    :disabled="isApplying || diffLines.length === 0"
                    @click="applyPatch"
                  >
                    {{ isApplying ? pick('应用中...', 'Applying...') : pick('应用 Patch', 'Apply patch') }}
                  </button>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { ApiError } from '@/api/novel'
import { applyChapterPatch, getChapterDiff } from '@/api/modules/chapterDiff'
import { globalAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'

const { pick, t, punct, formatWords } = useLocale()

interface DiffLine {
  line_number: number
  original_line: string | null
  patched_line: string | null
  change_type: 'added' | 'modified' | 'deleted' | 'unchanged'
}

interface Props {
  show: boolean
  projectId: string
  chapterNumber: number
  initialOriginal?: string
  initialPatched?: string
}

const props = withDefaults(defineProps<Props>(), {
  initialOriginal: '',
  initialPatched: ''
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'applied', data: { original: string; patched: string }): void
}>()

// 状态
const originalText = ref('')
const patchedText = ref('')
const diffLines = ref<DiffLine[]>([])
const isApplying = ref(false)
const isGeneratingDiff = ref(false)
const hasGeneratedDiff = ref(false)
const activeChapterNumber = ref(props.chapterNumber)

// 初始化
watch(
  () => props.show,
  (visible) => {
    if (visible) {
      activeChapterNumber.value = props.chapterNumber
      originalText.value = props.initialOriginal
      patchedText.value = props.initialPatched
      diffLines.value = []
      hasGeneratedDiff.value = false
    }
  },
  { immediate: true }
)

// 计算差异统计
const diffSummary = computed(() => {
  const lines = diffLines.value
  return {
    total_lines: lines.length,
    added: lines.filter(l => l.change_type === 'added').length,
    deleted: lines.filter(l => l.change_type === 'deleted').length,
    modified: lines.filter(l => l.change_type === 'modified').length,
    unchanged: lines.filter(l => l.change_type === 'unchanged').length,
  }
})

// 生成差异预览
const generateDiffPreview = async () => {
  if (!originalText.value.trim() || !patchedText.value.trim()) {
    globalAlert.showError(
      pick('请输入原始文本和修改后文本', 'Enter both the original and the revised text'),
      pick('输入不完整', 'Incomplete input')
    )
    return
  }

  isGeneratingDiff.value = true
  try {
    const result = await getChapterDiff(
      props.projectId,
      activeChapterNumber.value,
      originalText.value,
      patchedText.value
    )
    diffLines.value = result.diff_lines
    hasGeneratedDiff.value = true
  } catch (error) {
    console.error(pick('生成差异失败:', 'Failed to generate diff:'), error)
    if (error instanceof ApiError) {
      globalAlert.showError([
        error.detail.message || pick('生成差异失败', 'Failed to generate diff'),
        error.detail.rootCause ? `${pick('根因', 'Root cause')}${punct.colon}${error.detail.rootCause}` : '',
        error.detail.requestId ? `${pick('请求ID', 'Request ID')}${punct.colon}${error.detail.requestId}` : '',
      ].filter(Boolean).join('\n'), pick('错误', 'Error'))
    } else {
      globalAlert.showError(
        pick(
          `生成差异失败: ${error instanceof Error ? error.message : '未知错误'}`,
          `Failed to generate diff: ${error instanceof Error ? error.message : 'Unknown error'}`
        ),
        pick('错误', 'Error')
      )
    }
  } finally {
    isGeneratingDiff.value = false
  }
}

const resetPatchedText = () => {
  if (isApplying.value || isGeneratingDiff.value) return
  patchedText.value = originalText.value
  diffLines.value = []
  hasGeneratedDiff.value = false
}

// 应用 Patch
const applyPatch = async () => {
  if (!originalText.value.trim() || !patchedText.value.trim()) {
    globalAlert.showError(
      pick('请输入原始文本和修改后文本', 'Enter both the original and the revised text'),
      pick('输入不完整', 'Incomplete input')
    )
    return
  }

  isApplying.value = true
  try {
    const result = await applyChapterPatch(
      props.projectId,
      activeChapterNumber.value,
      originalText.value,
      patchedText.value
    )

    if (result.status === 'success') {
      globalAlert.showSuccess(
        pick('Patch 应用成功，已创建新版本', 'Patch applied. A new version has been created'),
        pick('应用成功', 'Applied')
      )
      emit('applied', {
        original: originalText.value,
        patched: patchedText.value,
      })
      handleClose()
    } else {
      globalAlert.showError(result.message || pick('应用失败', 'Apply failed'), pick('错误', 'Error'))
    }
  } catch (error) {
    console.error(pick('应用 Patch 失败:', 'Failed to apply patch:'), error)
    if (error instanceof ApiError) {
      globalAlert.showError([
        error.detail.message || pick('应用 Patch 失败', 'Failed to apply patch'),
        error.detail.rootCause ? `${pick('根因', 'Root cause')}${punct.colon}${error.detail.rootCause}` : '',
        error.detail.requestId ? `${pick('请求ID', 'Request ID')}${punct.colon}${error.detail.requestId}` : '',
      ].filter(Boolean).join('\n'), pick('错误', 'Error'))
    } else {
      globalAlert.showError(
        pick(
          `应用 Patch 失败: ${error instanceof Error ? error.message : '未知错误'}`,
          `Failed to apply patch: ${error instanceof Error ? error.message : 'Unknown error'}`
        ),
        pick('错误', 'Error')
      )
    }
  } finally {
    isApplying.value = false
  }
}

// 关闭处理
const handleClose = () => {
  if (isApplying.value) return
  emit('close')
}
</script>

<style scoped>
.m3-patchdiff-dialog {
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 30px 80px rgba(15, 23, 42, 0.22);
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.08), transparent 28%),
    radial-gradient(circle at bottom left, rgba(20, 184, 166, 0.08), transparent 24%),
    rgba(255, 255, 255, 0.98);
}

.m3-patchdiff-dialog__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 1.5rem 1.5rem 1rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.m3-patchdiff-dialog__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 0.375rem;
}

.m3-reader-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.625rem;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.25rem;
  border-radius: 9999px;
  background-color: rgba(15, 23, 42, 0.06);
  color: rgba(15, 23, 42, 0.64);
}

.m3-patchdiff-title {
  font-size: 1.375rem;
  font-weight: 600;
  line-height: 1.75rem;
  color: rgba(15, 23, 42, 0.88);
}

.m3-patchdiff-subtitle {
  font-size: 0.875rem;
  line-height: 1.25rem;
  color: rgba(15, 23, 42, 0.56);
  margin-top: 0.25rem;
}

.m3-patchdiff-dialog__actions {
  display: flex;
  gap: 0.5rem;
}

.m3-patchdiff-dialog__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  min-height: 0;
  overflow: hidden;
}

.patchdiff-edit-area {
  flex-shrink: 0;
}

.patchdiff-preview {
  flex: 1;
  min-height: 200px;
  display: flex;
  flex-direction: column;
}

.patchdiff-diff-container {
  flex: 1;
  max-height: 300px;
}

.patchdiff-empty {
  flex: 1;
  min-height: 200px;
}

.m3-patchdiff-dialog__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem 1.5rem;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.5);
}

.m3-patchdiff-dialog__foot-note {
  font-size: 0.875rem;
  color: rgba(15, 23, 42, 0.56);
}

.m3-patchdiff-dialog__foot-actions {
  display: flex;
  gap: 0.75rem;
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .m3-patchdiff-dialog {
    background:
      radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 28%),
      radial-gradient(circle at bottom left, rgba(20, 184, 166, 0.12), transparent 24%),
      rgba(30, 41, 59, 0.98);
  }

  .m3-patchdiff-title {
    color: rgba(248, 250, 252, 0.92);
  }

  .m3-patchdiff-subtitle {
    color: rgba(248, 250, 252, 0.56);
  }

  .m3-reader-chip {
    background-color: rgba(248, 250, 252, 0.1);
    color: rgba(248, 250, 252, 0.72);
  }
}
</style>