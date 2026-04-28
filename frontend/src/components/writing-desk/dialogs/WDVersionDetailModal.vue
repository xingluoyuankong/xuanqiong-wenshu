<!-- AIMETA P=版本详情弹窗_版本信息展示|R=版本对比_历史|NR=不含版本管理|E=component:WDVersionDetailModal|X=ui|A=版本弹窗|D=vue|S=dom|RD=./README.ai -->
<template>
  <div v-if="show" class="md-dialog-overlay" @click.self="$emit('close')">
    <div class="md-dialog w-full max-w-5xl m3-detail-dialog flex flex-col">
      <div class="flex items-center justify-between p-6 border-b" style="border-bottom-color: var(--md-outline-variant);">
        <div>
          <h3 class="md-headline-small font-semibold">版本详情</h3>
          <p class="md-body-small md-on-surface-variant mt-1">
            版本 {{ detailVersionIndex + 1 }}
            <span class="md-on-surface-variant">•</span>
            {{ version?.style || '标准' }}风格
            <span class="md-on-surface-variant">•</span>
            约 {{ Math.round(normalizedVersionContent.length / 100) * 100 }} 字
          </p>
        </div>
        <button
          type="button"
          @click="$emit('close')"
          class="md-icon-btn md-ripple"
        >
          <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </button>
      </div>

      <div class="flex-1 min-h-0 p-6 overflow-y-auto space-y-5">
        <section v-if="hasReviewInsights" class="m3-review-summary">
          <div class="m3-review-summary__head">
            <div>
              <p class="m3-kicker">生成链路摘要</p>
              <h4 class="md-title-medium font-semibold">这一版经过了哪些修订与把关</h4>
            </div>
            <div class="m3-review-badges">
              <span v-if="selfCritiqueSummary" class="m3-mini-badge">自我批评 {{ selfCritiqueSummary.final_score ?? '—' }} 分</span>
              <span v-if="consistencySummary" class="m3-mini-badge">一致性 {{ consistencyIssueCount }} 项</span>
              <span v-if="optimizerSummary" class="m3-mini-badge">专项优化 {{ optimizerStepCount }} 步</span>
            </div>
          </div>

          <div class="m3-review-grid">
            <article v-if="selfCritiqueSummary" class="m3-review-card">
              <p class="m3-kicker">自我批评</p>
              <ul>
                <li>最终分：{{ selfCritiqueSummary.final_score ?? '—' }}</li>
                <li>迭代次数：{{ selfCritiqueSummary.iterations ?? 0 }}</li>
                <li>提升分：{{ selfCritiqueSummary.improvement ?? 0 }}</li>
                <li>关键问题：{{ selfCritiqueSummary.critical_count ?? 0 }} 严重 / {{ selfCritiqueSummary.major_count ?? 0 }} 主要</li>
              </ul>
              <div v-if="selfCritiquePriorityFixes.length" class="m3-review-card__notes">
                <p class="m3-list-title">优先修复项</p>
                <ul>
                  <li v-for="item in selfCritiquePriorityFixes" :key="item">{{ item }}</li>
                </ul>
              </div>
            </article>

            <article v-if="consistencySummary" class="m3-review-card">
              <p class="m3-kicker">一致性检查</p>
              <ul>
                <li>状态：{{ consistencySummary.is_consistent ? '通过' : '发现问题' }}</li>
                <li>问题数：{{ consistencyIssueCount }}</li>
                <li>自动修复：{{ consistencySummary.auto_fix_applied ? '已执行' : '未执行' }}</li>
              </ul>
              <p v-if="consistencySummary.summary" class="m3-review-card__desc">{{ consistencySummary.summary }}</p>
            </article>

            <article v-if="optimizerSummary" class="m3-review-card">
              <p class="m3-kicker">专项优化</p>
              <ul>
                <li>优化步数：{{ optimizerStepCount }}</li>
                <li v-if="targetedDimensionsText">定向维度：{{ targetedDimensionsText }}</li>
                <li v-for="step in optimizerSteps" :key="step">{{ step }}</li>
              </ul>
            </article>

            <article v-if="runtimeWordSummary" class="m3-review-card">
              <p class="m3-kicker">字数达标</p>
              <ul>
                <li>{{ runtimeWordSummary }}</li>
                <li v-if="runtimeWordReason">{{ runtimeWordReason }}</li>
              </ul>
            </article>
          </div>
        </section>

        <div class="prose max-w-none">
          <div class="whitespace-pre-wrap leading-relaxed" style="color: var(--md-on-surface);">
            {{ normalizedVersionContent }}
          </div>
        </div>
      </div>

      <div class="shrink-0 flex items-center justify-between p-6 border-t" style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);">
        <div class="md-body-small md-on-surface-variant">
          <span v-if="isCurrent" class="md-chip" style="background-color: var(--md-success-container); color: var(--md-on-success-container);">
            <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
            </svg>
            当前选中版本
          </span>
          <span v-else class="md-on-surface-variant">未选中版本</span>
        </div>

        <div class="flex gap-3">
          <button
            type="button"
            @click="$emit('close')"
            class="md-btn md-btn-outlined md-ripple"
          >
            关闭
          </button>
          <button
            v-if="!isCurrent"
            type="button"
            @click="$emit('selectVersion')"
            class="md-btn md-btn-filled md-ripple"
          >
            选择此版本
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChapterVersion } from '@/api/novel'
import { computed } from 'vue'
import { normalizeChapterContent } from '@/utils/chapterContent'

interface Props {
  show: boolean
  detailVersionIndex: number
  version: ChapterVersion | null
  isCurrent: boolean
}

const props = defineProps<Props>()

defineEmits(['close', 'selectVersion'])

const normalizedVersionContent = computed(() => normalizeChapterContent(props.version?.content || ''))
const reviewSummaries = computed<Record<string, any>>(() => {
  const metadata = props.version?.metadata
  if (!metadata || typeof metadata !== 'object') return {}
  const raw = metadata.review_summaries
  return raw && typeof raw === 'object' ? raw as Record<string, any> : {}
})
const selfCritiqueSummary = computed<Record<string, any> | null>(() => {
  const value = reviewSummaries.value.self_critique
  return value && typeof value === 'object' ? value as Record<string, any> : null
})
const consistencySummary = computed<Record<string, any> | null>(() => {
  const value = reviewSummaries.value.consistency
  return value && typeof value === 'object' ? value as Record<string, any> : null
})
const optimizerSummary = computed<Record<string, any> | null>(() => {
  const value = reviewSummaries.value.optimizer
  return value && typeof value === 'object' ? value as Record<string, any> : null
})
const runtimeMeta = computed<Record<string, any>>(() => {
  const metadata = props.version?.metadata
  if (!metadata || typeof metadata !== 'object') return {}
  return metadata as Record<string, any>
})
const selfCritiquePriorityFixes = computed(() => {
  const items = selfCritiqueSummary.value?.priority_fixes
  if (!Array.isArray(items)) return []
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return ''
      const record = item as Record<string, any>
      return String(record.problem || record.suggestion || '').trim()
    })
    .filter(Boolean)
    .slice(0, 4)
})
const consistencyIssueCount = computed(() => Array.isArray(consistencySummary.value?.violations) ? consistencySummary.value!.violations.length : 0)
const optimizerSteps = computed(() => {
  const steps = optimizerSummary.value?.steps
  if (!Array.isArray(steps)) return []
  return steps
    .map((item) => {
      if (!item || typeof item !== 'object') return ''
      const record = item as Record<string, any>
      const dimension = String(record.dimension || '').trim()
      const notes = String(record.notes || '').trim()
      return [dimension ? `【${dimension}】` : '', notes].filter(Boolean).join(' ')
    })
    .filter(Boolean)
})
const optimizerStepCount = computed(() => optimizerSteps.value.length)
const targetedDimensionsText = computed(() => {
  const dimensions = optimizerSummary.value?.targeted_dimensions
  if (!Array.isArray(dimensions) || !dimensions.length) return ''
  const labelMap: Record<string, string> = {
    dialogue: '对话',
    psychology: '心理',
    rhythm: '节奏',
  }
  return dimensions.map((item) => labelMap[String(item)] || String(item)).join(' / ')
})
const runtimeWordSummary = computed(() => {
  const actual = runtimeMeta.value.actual_word_count
  const min = runtimeMeta.value.min_word_count
  const target = runtimeMeta.value.target_word_count
  if (!actual && !min && !target) return ''
  const parts = []
  if (actual) parts.push(`实际 ${actual} 字`)
  if (min) parts.push(`最低 ${min} 字`)
  if (target) parts.push(`目标 ${target} 字`)
  return parts.join(' / ')
})
const runtimeWordReason = computed(() => {
  const reason = runtimeMeta.value.word_requirement_reason
  if (!reason) return ''
  const map: Record<string, string> = {
    target_met: '已达到目标字数',
    close_to_target: '已接近目标字数',
    minimum_met: '已达到最低字数',
    minimum_met_but_below_target: '已达到最低字数，但仍低于目标',
    below_minimum_after_enrichment: '补字后仍低于最低要求',
    below_minimum: '低于最低要求',
  }
  return map[String(reason)] || String(reason)
})
const hasReviewInsights = computed(() => Boolean(
  selfCritiqueSummary.value || consistencySummary.value || optimizerSummary.value || runtimeWordSummary.value
))
</script>

<style scoped>
.m3-detail-dialog {
  max-width: min(1320px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  border-radius: var(--md-radius-xl);
}

.m3-review-summary {
  padding: 16px;
  border-radius: 20px;
  background: var(--md-surface-container-low);
  border: 1px solid var(--md-outline-variant);
}

.m3-review-summary__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.m3-review-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.m3-mini-badge {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--md-primary-container);
  color: var(--md-on-primary-container);
  font-size: 12px;
  line-height: 1;
}

.m3-review-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.m3-review-card {
  padding: 14px;
  border-radius: 16px;
  background: var(--md-surface);
  border: 1px solid var(--md-outline-variant);
}

.m3-review-card ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--md-on-surface-variant);
  font-size: 13px;
  line-height: 1.7;
}

.m3-review-card__desc {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--md-on-surface-variant);
}

.m3-review-card__notes {
  margin-top: 10px;
}

.m3-kicker {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--md-primary);
}

.m3-list-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--md-on-surface);
}
</style>
