<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="emit('close')">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-slate-950/45 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-2 sm:p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 translate-y-6 sm:scale-95"
            enter-to="opacity-100 translate-y-0 sm:scale-100"
            leave="ease-in duration-150"
            leave-from="opacity-100 translate-y-0 sm:scale-100"
            leave-to="opacity-0 translate-y-4 sm:scale-95"
          >
            <DialogPanel class="wd-version-diff-dialog md-dialog flex h-[calc(100vh-1rem)] w-[min(1400px,calc(100vw-1rem))] flex-col overflow-hidden text-left">
              <div class="wd-version-diff-dialog__head">
                <div class="min-w-0 flex-1">
                  <div class="wd-version-diff-dialog__chips">
                    <span class="wd-chip wd-chip--primary">候选版本对比</span>
                    <span class="wd-chip">第 {{ chapterNumber }} 章</span>
                    <span class="wd-chip">{{ baseLabel }}</span>
                    <span class="wd-chip">{{ compareLabel }}</span>
                  </div>
                  <DialogTitle as="h3" class="wd-version-diff-dialog__title">
                    候选版本差异对比
                  </DialogTitle>
                  <p class="wd-version-diff-dialog__subtitle">
                    只读对比两个候选版本的文本差异，不会修改正文，也不会创建新版本。
                  </p>
                </div>
                <button type="button" class="md-icon-btn md-ripple" @click="emit('close')" aria-label="关闭">
                  ×
                </button>
              </div>

              <div class="wd-version-diff-dialog__body">
                <div class="wd-version-diff-dialog__summary">
                  <span>总行数 {{ diffSummary.total_lines }}</span>
                  <span>新增 {{ diffSummary.added }}</span>
                  <span>删除 {{ diffSummary.deleted }}</span>
                  <span>修改 {{ diffSummary.modified }}</span>
                  <span>未变 {{ diffSummary.unchanged }}</span>
                </div>

                <div v-if="isLoading" class="wd-version-diff-dialog__empty">
                  <p>正在加载版本差异...</p>
                </div>

                <div v-else-if="errorMessage" class="wd-version-diff-dialog__empty wd-version-diff-dialog__empty--error">
                  <p>{{ errorMessage }}</p>
                </div>

                <div v-else-if="diffLines.length === 0" class="wd-version-diff-dialog__empty">
                  <p>两个版本目前没有可展示的差异。</p>
                </div>

                <div v-else class="wd-version-diff-dialog__table-wrap">
                  <table class="wd-version-diff-table">
                    <thead>
                      <tr>
                        <th class="wd-version-diff-table__line">行号</th>
                        <th>{{ baseLabel }}</th>
                        <th>{{ compareLabel }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(line, index) in diffLines"
                        :key="`${line.line_number}-${line.change_type}-${index}`"
                        :class="[
                          'wd-version-diff-table__row',
                          `wd-version-diff-table__row--${line.change_type}`
                        ]"
                      >
                        <td class="wd-version-diff-table__line">{{ line.line_number }}</td>
                        <td class="wd-version-diff-table__cell">{{ line.original_line || '⏎' }}</td>
                        <td class="wd-version-diff-table__cell">{{ line.patched_line || '⏎' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="wd-version-diff-dialog__foot">
                <span>当前仅做只读候选版本对比；需要修改正文请使用“精细编辑”。</span>
                <button type="button" class="md-btn md-btn-outlined md-ripple" @click="emit('close')">
                  关闭
                </button>
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
import { getChapterVersionDiff } from '@/api/modules/chapterDiff'
import { globalAlert } from '@/composables/useAlert'

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
  baseVersionId: number | null
  compareVersionId: number | null
  baseLabel?: string
  compareLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  baseLabel: '基准版本',
  compareLabel: '对比版本'
})

const emit = defineEmits<{
  (e: 'close'): void
}>()

const diffLines = ref<DiffLine[]>([])
const isLoading = ref(false)
const errorMessage = ref('')

const diffSummary = computed(() => {
  const lines = diffLines.value
  return {
    total_lines: lines.length,
    added: lines.filter((line) => line.change_type === 'added').length,
    deleted: lines.filter((line) => line.change_type === 'deleted').length,
    modified: lines.filter((line) => line.change_type === 'modified').length,
    unchanged: lines.filter((line) => line.change_type === 'unchanged').length
  }
})

const loadVersionDiff = async () => {
  if (!props.show) return
  if (!props.projectId || !props.baseVersionId || !props.compareVersionId) {
    diffLines.value = []
    errorMessage.value = '缺少可对比的版本信息。'
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  try {
    const result = await getChapterVersionDiff(
      props.projectId,
      props.chapterNumber,
      props.baseVersionId,
      props.compareVersionId
    )
    diffLines.value = result.diff_lines
  } catch (error) {
    console.error('加载版本差异失败:', error)
    diffLines.value = []
    if (error instanceof ApiError) {
      errorMessage.value = [
        error.detail.message || '加载版本差异失败',
        error.detail.rootCause ? `根因：${error.detail.rootCause}` : '',
        error.detail.requestId ? `请求ID：${error.detail.requestId}` : '',
      ].filter(Boolean).join('\n')
    } else {
      errorMessage.value = error instanceof Error ? error.message : '加载版本差异失败'
    }
    globalAlert.showError(errorMessage.value, '版本对比失败')
  } finally {
    isLoading.value = false
  }
}

watch(
  () => [props.show, props.projectId, props.chapterNumber, props.baseVersionId, props.compareVersionId],
  () => {
    if (!props.show) {
      diffLines.value = []
      errorMessage.value = ''
      return
    }
    void loadVersionDiff()
  },
  { immediate: true }
)
</script>

<style scoped>
.wd-version-diff-dialog {
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 30px 80px rgba(15, 23, 42, 0.22);
  background: rgba(255, 255, 255, 0.98);
}

.wd-version-diff-dialog__head,
.wd-version-diff-dialog__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.wd-version-diff-dialog__foot {
  border-bottom: none;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  font-size: 0.85rem;
  color: rgba(15, 23, 42, 0.62);
}

.wd-version-diff-dialog__body {
  flex: 1;
  min-height: 0;
  padding: 1rem 1.5rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.wd-version-diff-dialog__chips,
.wd-version-diff-dialog__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.wd-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 0.78rem;
  font-weight: 700;
}

.wd-chip--primary {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.wd-version-diff-dialog__title {
  margin-top: 0.5rem;
  font-size: 1.35rem;
  font-weight: 700;
  color: rgba(15, 23, 42, 0.92);
}

.wd-version-diff-dialog__subtitle {
  margin-top: 0.3rem;
  font-size: 0.9rem;
  color: rgba(15, 23, 42, 0.58);
}

.wd-version-diff-dialog__table-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
}

.wd-version-diff-dialog__empty {
  flex: 1;
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(15, 23, 42, 0.55);
}

.wd-version-diff-dialog__empty--error {
  color: #b91c1c;
}

.wd-version-diff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}

.wd-version-diff-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.wd-version-diff-table__line {
  width: 72px;
  text-align: center;
  color: #64748b;
}

.wd-version-diff-table__cell {
  padding: 10px 12px;
  vertical-align: top;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, Courier New, monospace;
}

.wd-version-diff-table__row--added {
  background: rgba(220, 252, 231, 0.7);
}

.wd-version-diff-table__row--deleted {
  background: rgba(254, 226, 226, 0.7);
}

.wd-version-diff-table__row--modified {
  background: rgba(254, 249, 195, 0.75);
}
</style>
