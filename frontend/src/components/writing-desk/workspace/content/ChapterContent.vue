<template>
  <div class="wc-shell">
    <section class="wc-topbar">
      <div class="wc-topbar__lead">
        <div class="wc-topbar__chips">
          <span class="wc-chip wc-chip--success">已确认正文</span>
          <span class="wc-chip">正文 {{ normalizedChapterContent.length }} 字</span>
          <span class="wc-chip">候选 {{ selectedChapter.versions?.length || 1 }} 版</span>
        </div>
        <h4>{{ selectedChapter.title || `第${selectedChapter.chapter_number}章正文` }}</h4>
      </div>

      <div class="wc-topbar__actions">
        <button
          type="button"
          class="md-btn md-btn-outlined md-ripple md-btn--sm"
          :disabled="!selectedChapter.content"
          @click="exportChapterAsTxt(selectedChapter)"
        >
          导出 TXT
        </button>
        <button type="button" class="md-btn md-btn-filled md-ripple md-btn--sm" @click="showOptimizer = true">
          精修
        </button>
      </div>
    </section>

    <section class="wc-reader">
      <div class="wc-reader__head">
        <p class="wc-reader__kicker">正文预览</p>
        <div class="wc-reader__meta">
          <span>{{ Math.round(normalizedChapterContent.length / 100) * 100 }} 字</span>
        </div>
      </div>
      <article class="wc-reader__body">{{ chapterPreviewContent }}</article>
    </section>

    <Teleport to="body">
      <div v-if="showOptimizer" class="md-dialog-overlay" @click.self="showOptimizer = false">
        <div class="md-dialog wc-dialog">
          <div class="wc-dialog__head">
            <h3 class="md-title-medium font-semibold">精修这一章</h3>
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
              rows="3"
              class="md-textarea w-full resize-none mt-4"
              placeholder="补充你想强化的方向..."
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

      <div v-if="optimizeResult" class="md-dialog-overlay" @click.self="optimizeResult = null">
        <div class="md-dialog wc-result">
          <div class="wc-result__head">
            <h3 class="md-title-medium font-semibold">精修结果：{{ selectedDimensionLabel }}</h3>
            <button type="button" class="md-icon-btn md-ripple" @click="optimizeResult = null">×</button>
          </div>
          <div class="wc-result__body">{{ optimizeResult }}</div>
          <div class="wc-result__foot">
            <button type="button" class="md-btn md-btn-outlined md-ripple" @click="optimizeResult = null">关闭</button>
            <button type="button" class="md-btn md-btn-filled md-ripple" @click="applyOptimizeResult">应用此版本</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Chapter } from '@/api/novel'

interface Props {
  selectedChapter: Chapter
  selectedVersionIndex?: number
  compareVersionIndex?: number
}

const props = withDefaults(defineProps<Props>(), {
  selectedVersionIndex: 0,
  compareVersionIndex: -1,
})

const emit = defineEmits<{
  (e: 'openReader'): void
  (e: 'openPatchDiff'): void
  (e: 'chapterUpdated', payload: { chapterNumber: number; content: string }): void
}>()

const showOptimizer = ref(false)
const selectedDimension = ref<string | null>(null)
const additionalNotes = ref('')
const isOptimizing = ref(false)
const optimizeResult = ref<string | null>(null)

const optimizeDimensions = [
  { key: 'dialogue', label: '对话优化', description: '让对话更自然、有个性' },
  { key: 'pacing', label: '节奏优化', description: '调整叙事节奏和张力' },
  { key: 'description', label: '描写优化', description: '丰富场景和感官描写' },
  { key: 'emotion', label: '情感深化', description: '增强情感冲击力' },
]

const selectedDimensionLabel = computed(() => {
  return optimizeDimensions.find(d => d.key === selectedDimension.value)?.label || ''
})

const normalizedChapterContent = computed(() => {
  const chapter = props.selectedChapter
  if (!chapter.content) return ''
  if (props.selectedVersionIndex >= 0 && chapter.versions?.length) {
    const version = chapter.versions[props.selectedVersionIndex]
    if (version?.content) return version.content
  }
  return chapter.content
})

const chapterPreviewContent = computed(() => {
  const content = normalizedChapterContent.value
  if (content.length > 1500) {
    return content.slice(0, 1500) + '\n\n... （更多内容请用上方"全文阅读"查看）'
  }
  return content
})

const contentHealthStatus = computed(() => {
  const wordCount = normalizedChapterContent.value.length
  if (wordCount >= 2000) return '健康'
  if (wordCount >= 500) return '较短'
  return '待补充'
})

const paragraphCount = computed(() => {
  return normalizedChapterContent.value.split(/\n\s*\n/).filter(p => p.trim()).length
})

const previewRatioLabel = computed(() => {
  const total = normalizedChapterContent.value.length
  const preview = chapterPreviewContent.value.length
  if (total === 0) return '0%'
  return Math.round((preview / total) * 100) + '%'
})

function exportChapterAsTxt(chapter: Chapter) {
  const content = normalizedChapterContent.value
  if (!content) return
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `第${chapter.chapter_number}章_${chapter.title || '未命名'}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

async function startOptimize() {
  if (!selectedDimension.value) return
  isOptimizing.value = true
  try {
    await new Promise(resolve => setTimeout(resolve, 1500))
    optimizeResult.value = `这是针对"${selectedDimensionLabel.value}"的精修结果预览。\n\n优化建议：\n1. 增强场景描写的感官细节\n2. 让人物对话更贴合性格\n3. 调整段落节奏，提高可读性\n\n（实际功能需对接后端 API）`
  } finally {
    isOptimizing.value = false
  }
}

function applyOptimizeResult() {
  if (!optimizeResult.value) return
  emit('chapterUpdated', {
    chapterNumber: props.selectedChapter.chapter_number,
    content: optimizeResult.value,
  })
  optimizeResult.value = null
  showOptimizer.value = false
}
</script>

<style scoped>
.wc-shell {
  display: grid;
  gap: 8px;
  min-height: 0;
}

.wc-topbar,
.wc-reader,
.wc-dialog,
.wc-result {
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
}

.wc-topbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.8);
}

.wc-topbar__lead {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wc-topbar__lead h4 {
  margin: 0;
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
}

.wc-topbar__chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}

.wc-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: #475569;
  font-size: 10px;
  font-weight: 600;
}

.wc-chip--success {
  background: rgba(22, 163, 74, 0.1);
  color: #166534;
}

.wc-topbar__actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.wc-reader {
  display: grid;
  min-height: 0;
  background: rgba(255, 255, 255, 0.9);
}

.wc-reader__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
}

.wc-reader__kicker {
  font-size: 11px;
  font-weight: 700;
  color: #2563eb;
  margin: 0;
}

.wc-reader__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.04);
  color: #64748b;
  font-size: 10px;
  font-weight: 600;
}

.wc-reader__body {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #0f172a;
  padding: 14px 16px;
  font-size: 13px;
  max-width: 70ch;
  margin: 0 auto;
}

.wc-dialog,
.wc-result {
  width: min(600px, calc(100vw - 32px));
  max-height: calc(100vh - 64px);
  padding: 18px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.12);
}

.wc-dialog__head,
.wc-dialog__foot,
.wc-result__head,
.wc-result__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.wc-dialog__body {
  margin-top: 12px;
}

.wc-result__body {
  margin-top: 12px;
  max-height: 50vh;
  overflow: auto;
  white-space: pre-wrap;
  line-height: 1.7;
  color: #0f172a;
  padding: 12px;
  border-radius: 6px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.1);
  font-size: 13px;
}

.wc-result__foot {
  margin-top: 12px;
}

.wc-dimension-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.wc-dimension {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  text-align: left;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(248, 250, 252, 0.8);
  cursor: pointer;
  transition: all 0.15s ease;
}

.wc-dimension:hover {
  border-color: rgba(37, 99, 235, 0.3);
}

.wc-dimension--active {
  border-color: rgba(37, 99, 235, 0.4);
  background: rgba(219, 234, 254, 0.7);
}

.wc-dimension strong {
  font-size: 12px;
  color: #0f172a;
}

.wc-dimension span {
  color: #64748b;
  font-size: 11px;
  line-height: 1.4;
}

.md-btn--sm {
  min-height: 28px;
  padding: 0 10px;
  font-size: 11px;
}

@media (max-width: 768px) {
  .wc-topbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .wc-dimension-grid {
    grid-template-columns: 1fr;
  }
}
</style>
