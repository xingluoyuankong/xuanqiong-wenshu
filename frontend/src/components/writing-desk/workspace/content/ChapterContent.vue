<template>
  <div class="wc-shell">
    <section class="wc-topbar">
      <div class="wc-topbar__lead">
        <div class="wc-topbar__chips">
          <span class="wc-chip wc-chip--success">已确认正文</span>
          <span class="wc-chip">正文 {{ normalizedChapterContent.length }} 字</span>
          <span class="wc-chip">候选 {{ selectedChapter.versions?.length || 1 }} 版</span>
          <span class="wc-chip">{{ showOptimizeResult ? '有待确认的优化稿' : '当前版本稳定' }}</span>
        </div>

        <div>
          <h4>{{ selectedChapter.title || `第${selectedChapter.chapter_number}章正文` }}</h4>
          <p>正文先在这里快速看；全文阅读已经收口到上方工具区，候选版本切换也统一放到顶部主操作区。</p>
        </div>
      </div>

      <div class="wc-topbar__actions">
        <button
          type="button"
          class="md-btn md-btn-outlined md-ripple"
          :disabled="!selectedChapter.content"
          @click="exportChapterAsTxt(selectedChapter)"
        >
          导出 TXT
        </button>
        <button type="button" class="md-btn md-btn-filled md-ripple" @click="showOptimizer = true">
          精修这一章
        </button>
      </div>
    </section>

    <section class="wc-health-strip" aria-label="正文健康检查">
      <div class="wc-health-card wc-health-card--primary">
        <span>正文状态</span>
        <strong>{{ contentHealthStatus }}</strong>
        <em>{{ contentHealthHint }}</em>
      </div>
      <div class="wc-health-card">
        <span>段落</span>
        <strong>{{ paragraphCount }}</strong>
        <em>阅读节奏</em>
      </div>
      <div class="wc-health-card">
        <span>预览比例</span>
        <strong>{{ previewRatioLabel }}</strong>
        <em>当前页展示</em>
      </div>
      <div class="wc-health-card" :class="showOptimizeResult ? 'wc-health-card--warn' : 'wc-health-card--success'">
        <span>精修队列</span>
        <strong>{{ showOptimizeResult ? '待应用' : '空闲' }}</strong>
        <em>{{ showOptimizeResult ? '已有优化稿' : '可继续创作' }}</em>
      </div>
    </section>

    <section class="wc-reader">
      <div class="wc-reader__head">
        <div>
          <p class="wc-reader__kicker">正文预览区</p>
          <h5 class="md-title-medium font-semibold">当前生效版本</h5>
          <p class="md-body-small md-on-surface-variant">
            预览保留一屏内的核心内容；真正全文请用上方工具区的“全文阅读”，这样更适合浏览，也不会把按钮和正文挤到两层滚动里。
          </p>
        </div>
        <div class="wc-reader__meta">
          <span>章节 {{ selectedChapter.chapter_number }}</span>
          <span>{{ Math.round(normalizedChapterContent.length / 100) * 100 }} 字</span>
          <span>{{ showOptimizeResult ? '优化稿待确认' : '可继续写下章节' }}</span>
        </div>
      </div>

      <article class="wc-reader__body">{{ chapterPreviewContent }}</article>
    </section>

    <Teleport to="body">
      <div v-if="showOptimizer" class="md-dialog-overlay" @click.self="showOptimizer = false">
        <div class="md-dialog wc-dialog">
          <div class="wc-dialog__head">
            <div>
              <h3 class="md-title-large font-semibold">精修这一章</h3>
              <p class="md-body-small md-on-surface-variant mt-1">只针对一个维度微调，不做整章重写。</p>
            </div>
            <button type="button" class="md-icon-btn md-ripple" @click="showOptimizer = false">×</button>
          </div>

          <div class="wc-dialog__body">
            <div class="wc-dimension-grid">
              <button
                v-for="dim in optimizeDimensions"
                :key="dim.key"
                type="button"
                :class="['wc-dimension', selectedDimension === dim.key ? 'wc-dimension--active' : '']"
                @click="selectedDimension = dim.key"
              >
                <strong>{{ dim.label }}</strong>
                <span>{{ dim.description }}</span>
              </button>
            </div>

            <textarea
              v-model="additionalNotes"
              rows="4"
              class="md-textarea w-full resize-none mt-5"
              placeholder="补充你想强化的方向，例如：加重压迫感、增强潜台词、提高场景层次。"
            ></textarea>
          </div>

          <div class="wc-dialog__foot">
            <button type="button" class="md-btn md-btn-outlined md-ripple" @click="showOptimizer = false">取消</button>
            <button type="button" class="md-btn md-btn-filled md-ripple" :disabled="!selectedDimension || isOptimizing" @click="startOptimize">
              {{ isOptimizing ? '精修中...' : '开始精修' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showOptimizeResult" class="md-dialog-overlay" @click.self="showOptimizeResult = false">
        <div class="md-dialog wc-result">
          <div class="wc-dialog__head">
            <div>
              <h3 class="md-title-large font-semibold">优化结果预览</h3>
              <p class="md-body-small md-on-surface-variant mt-1">{{ optimizeResultNotes }}</p>
            </div>
            <button type="button" class="md-icon-btn md-ripple" @click="showOptimizeResult = false">×</button>
          </div>
          <div class="wc-result__body">{{ optimizedContent }}</div>
          <div class="wc-dialog__foot">
            <button type="button" class="md-btn md-btn-outlined md-ripple" @click="showOptimizeResult = false">取消</button>
            <button type="button" class="md-btn md-btn-filled md-ripple" :disabled="isApplying" @click="applyOptimization">
              {{ isApplying ? '应用中...' : '应用优化结果' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { globalAlert } from '@/composables/useAlert'
import { ApiError, type Chapter } from '@/api/novel'
import { OptimizerAPI } from '@/api/novel'
import { buildChapterPreview, normalizeChapterContent } from '@/utils/chapterContent'

interface Props {
  selectedChapter: Chapter
  projectId?: string
}

interface ReaderPayload {
  title: string
  content: string
  subtitle?: string
  source?: string
  chapterNumber?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'chapterUpdated', payload: Chapter): void
  (e: 'openReader', payload: ReaderPayload): void
}>()

const showOptimizer = ref(false)
const showOptimizeResult = ref(false)
const selectedDimension = ref('')
const additionalNotes = ref('')
const isOptimizing = ref(false)
const isApplying = ref(false)
const optimizedContent = ref('')
const optimizeResultNotes = ref('')

const normalizedChapterContent = computed(() => normalizeChapterContent(props.selectedChapter.content || ''))
const chapterPreviewContent = computed(() => buildChapterPreview(props.selectedChapter.content || '', 980))
const paragraphCount = computed(() => normalizedChapterContent.value.split(/\n{2,}/).filter((item) => item.trim()).length)
const previewRatioLabel = computed(() => {
  const total = normalizedChapterContent.value.length
  if (!total) return '0%'
  return `${Math.min(100, Math.round((chapterPreviewContent.value.length / total) * 100))}%`
})
const contentHealthStatus = computed(() => {
  const len = normalizedChapterContent.value.length
  if (!len) return '无正文'
  if (len < 600) return '偏短'
  if (len > 12000) return '偏长'
  return '可交付'
})
const contentHealthHint = computed(() => {
  const len = normalizedChapterContent.value.length
  if (!len) return '需要重新生成或粘贴正文'
  if (len < 600) return '建议补足场景和转折'
  if (len > 12000) return '建议拆分或压缩节奏'
  return '适合继续评审、精修或导出'
})

const optimizeDimensions = [
  { key: 'dialogue', label: '对话', description: '让人物声音更有区分度，并强化潜台词。' },
  { key: 'environment', label: '环境', description: '增强场景氛围，让空间参与叙事。' },
  { key: 'psychology', label: '心理', description: '深入角色内心，增加真实波动。' },
  { key: 'rhythm', label: '节奏', description: '优化句式长短和段落推进感。' }
]

const sanitizeFileName = (name: string) => name.replace(/[\\/:*?"<>|]/g, '_')

const openReader = () => {
  if (!normalizedChapterContent.value) return

  emit('openReader', {
    title: props.selectedChapter.title?.trim() || `第${props.selectedChapter.chapter_number}章正文`,
    subtitle: props.selectedChapter.summary?.trim() || '当前章节正文',
    content: normalizedChapterContent.value,
    source: 'chapter-content',
    chapterNumber: props.selectedChapter.chapter_number
  })
}

const exportChapterAsTxt = (chapter?: Chapter | null) => {
  if (!chapter) return
  const title = chapter.title?.trim() || `第${chapter.chapter_number}章正文`
  const content = normalizeChapterContent(chapter.content || '')
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${sanitizeFileName(title)}.txt`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const formatOptimizeError = (error: unknown, fallback: string) => {
  if (error instanceof ApiError) {
    const lines = [error.detail.message || fallback]
    if (error.detail.rootCause) lines.push(`根因：${error.detail.rootCause}`)
    if (error.detail.requestId) lines.push(`请求ID：${error.detail.requestId}`)
    if (error.detail.hint) lines.push(`建议：${error.detail.hint}`)
    return lines.join('\n')
  }
  if (error instanceof Error) return error.message || fallback
  return fallback
}

const startOptimize = async () => {
  if (!selectedDimension.value || !props.projectId) {
    globalAlert.showError('请先选择一个优化维度', '无法开始')
    return
  }

  isOptimizing.value = true
  showOptimizer.value = false
  try {
    const result = await OptimizerAPI.optimizeChapter({
      project_id: props.projectId,
      chapter_number: props.selectedChapter.chapter_number,
      dimension: selectedDimension.value as 'dialogue' | 'environment' | 'psychology' | 'rhythm',
      additional_notes: additionalNotes.value || undefined
    })

    optimizedContent.value = result.optimized_content
    optimizeResultNotes.value = Array.isArray(result.optimization_notes)
      ? result.optimization_notes.join('\n')
      : result.optimization_notes
    showOptimizeResult.value = true
  } catch (error: unknown) {
    console.error('优化失败:', error)
    globalAlert.showError(formatOptimizeError(error, '优化失败，请稍后重试'), '优化失败')
  } finally {
    isOptimizing.value = false
  }
}

const applyOptimization = async () => {
  if (!optimizedContent.value || !props.projectId) return
  isApplying.value = true
  try {
    const result = await OptimizerAPI.applyOptimization(
      props.projectId,
      props.selectedChapter.chapter_number,
      optimizedContent.value
    )
    emit('chapterUpdated', result.chapter)
    globalAlert.showSuccess('优化结果已应用', '操作成功')
    showOptimizeResult.value = false
    selectedDimension.value = ''
    additionalNotes.value = ''
    optimizedContent.value = ''
    optimizeResultNotes.value = ''
  } catch (error: unknown) {
    console.error('应用优化失败:', error)
    globalAlert.showError(formatOptimizeError(error, '应用优化失败，请稍后重试'), '应用失败')
  } finally {
    isApplying.value = false
  }
}
</script>

<style scoped>
.wc-shell {
  display: grid;
  gap: 14px;
  min-height: 0;
}

.wc-topbar,
.wc-reader,
.wc-dialog,
.wc-result {
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.wc-topbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 18px;
  background:
    linear-gradient(135deg, rgba(219, 234, 254, 0.78), rgba(255, 255, 255, 0.94)),
    rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 44px rgba(37, 99, 235, 0.08);
}

.wc-topbar__lead,
.wc-topbar__actions,
.wc-dialog__head,
.wc-dialog__foot {
  display: flex;
  gap: 12px;
}

.wc-topbar__lead {
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.wc-topbar__lead h4 {
  color: #0f172a;
  font-size: 1.12rem;
  font-weight: 800;
}

.wc-topbar__lead p {
  margin-top: 6px;
  color: #475569;
  font-size: 0.92rem;
  line-height: 1.72;
}

.wc-topbar__chips,
.wc-topbar__actions,
.wc-reader__meta {
  flex-wrap: wrap;
  align-items: center;
}

.wc-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 0.78rem;
  font-weight: 700;
}

.wc-chip--success {
  background: rgba(22, 163, 74, 0.12);
  color: #166534;
}

.wc-health-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.wc-health-card {
  display: grid;
  gap: 3px;
  min-height: 78px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92));
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
}

.wc-health-card span {
  color: #64748b;
  font-size: 0.72rem;
  font-weight: 850;
}

.wc-health-card strong {
  color: #0f172a;
  font-size: 1.16rem;
  line-height: 1.1;
  font-weight: 950;
}

.wc-health-card em {
  color: #64748b;
  font-size: 0.72rem;
  font-style: normal;
}

.wc-health-card--primary {
  border-color: rgba(37, 99, 235, 0.24);
  background:
    linear-gradient(180deg, rgba(239, 246, 255, 0.98), rgba(255, 255, 255, 0.9));
}

.wc-health-card--success {
  border-color: rgba(34, 197, 94, 0.22);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.98), rgba(255, 255, 255, 0.9));
}

.wc-health-card--warn {
  border-color: rgba(14, 165, 233, 0.28);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.98), rgba(255, 255, 255, 0.9));
}

.wc-reader {
  display: grid;
  min-height: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 252, 255, 0.96));
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.05);
}

.wc-reader__head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 18px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.wc-reader__kicker {
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #2563eb;
}

.wc-reader__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
  font-size: 0.78rem;
  font-weight: 700;
}

.wc-reader__body,
.wc-result__body {
  white-space: pre-wrap;
  line-height: 1.58;
  color: #0f172a;
  padding: 20px 18px 24px;
}

.wc-reader__body {
  max-width: 76ch;
  margin: 0 auto;
  font-size: 1.02rem;
  letter-spacing: 0.01em;
  background:
    linear-gradient(90deg, rgba(37, 99, 235, 0.08), transparent 1px) 0 0 / 1px 100% no-repeat;
}

.wc-dialog,
.wc-result {
  width: min(920px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  padding: 24px;
}

.wc-dialog__head,
.wc-dialog__foot {
  align-items: center;
  justify-content: space-between;
}

.wc-dialog__body {
  margin-top: 20px;
}

.wc-dimension-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.wc-dimension {
  display: grid;
  gap: 6px;
  padding: 16px;
  text-align: left;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.92);
}

.wc-dimension--active {
  border-color: rgba(37, 99, 235, 0.34);
  background: rgba(219, 234, 254, 0.84);
}

.wc-dimension span {
  color: #64748b;
  font-size: 0.84rem;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .wc-topbar,
  .wc-reader__head,
  .wc-dialog__head,
  .wc-dialog__foot {
    flex-direction: column;
    align-items: stretch;
  }

  .wc-dimension-grid {
    grid-template-columns: 1fr;
  }

  .wc-health-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .wc-health-strip {
    grid-template-columns: 1fr;
  }
}
</style>
