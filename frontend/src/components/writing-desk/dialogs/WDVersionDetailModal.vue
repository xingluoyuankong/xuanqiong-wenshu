<!-- AIMETA P=版本详情弹窗_版本信息展示|R=版本对比_历史|NR=不含版本管理|E=component:WDVersionDetailModal|X=ui|A=版本弹窗|D=vue|S=dom|RD=./README.ai -->
<template>
  <div v-if="show" class="xq-dialog-overlay" @click.self="$emit('close')">
    <div class="xq-dialog-shell xq-dialog-shell--wide m3-detail-dialog flex flex-col">
      <div class="xq-dialog-header" style="border-bottom-color: var(--md-outline-variant);">
        <div>
          <h3 class="xq-dialog-title">{{ pick('版本详情', 'Version details') }}</h3>
          <p class="xq-dialog-subtitle">
            {{ pick('版本', 'Version') }} {{ detailVersionIndex + 1 }}
            <span class="md-on-surface-variant">•</span>
            {{ version?.style || pick('标准', 'Standard') }}{{ pick('风格', ' style') }}
            <span class="md-on-surface-variant">•</span>
            {{ pick('约', 'About') }} {{ Math.round(normalizedVersionContent.length / 100) * 100 }} {{ pick('字', 'words') }}
          </p>
        </div>
        <button
          type="button"
          @click="$emit('close')"
          class="xq-dialog-close md-ripple"
        >
          <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
          </svg>
        </button>
      </div>

      <div class="xq-dialog-body space-y-3">
        <section v-if="hasReviewInsights" class="m3-review-summary">
          <div class="m3-review-summary__head">
            <div>
              <p class="m3-kicker">{{ pick('生成链路摘要', 'Generation pipeline summary') }}</p>
              <h4 class="md-title-medium font-semibold">{{ pick('这一版经过了哪些修订与把关', 'Revisions and checks applied to this version') }}</h4>
            </div>
            <div class="m3-review-badges">
              <span v-if="selfCritiqueSummary" class="m3-mini-badge">{{ pick('自我批评', 'Self-critique') }} {{ selfCritiqueSummary.final_score ?? '—' }} {{ pick('分', 'pts') }}</span>
              <span v-if="consistencySummary" class="m3-mini-badge">{{ pick('一致性', 'Continuity') }} {{ consistencyIssueCount }} {{ pick('项', 'issue(s)') }}</span>
              <span v-if="optimizerSummary" class="m3-mini-badge">{{ pick('专项优化', 'Targeted optimization') }} {{ optimizerStepCount }} {{ pick('步', 'step(s)') }}</span>
            </div>
          </div>

          <div class="m3-review-grid">
            <article v-if="selfCritiqueSummary" class="m3-review-card">
              <p class="m3-kicker">{{ pick('自我批评', 'Self-critique') }}</p>
              <ul>
                <li>{{ pick('最终分', 'Final score') }}{{ punct.colon }}{{ selfCritiqueSummary.final_score ?? '—' }}</li>
                <li>{{ pick('迭代次数', 'Iterations') }}{{ punct.colon }}{{ selfCritiqueSummary.iterations ?? 0 }}</li>
                <li>{{ pick('提升分', 'Score gain') }}{{ punct.colon }}{{ selfCritiqueSummary.improvement ?? 0 }}</li>
                <li>{{ pick('关键问题', 'Key issues') }}{{ punct.colon }}{{ selfCritiqueSummary.critical_count ?? 0 }} {{ pick('严重', 'critical') }} / {{ selfCritiqueSummary.major_count ?? 0 }} {{ pick('主要', 'major') }}</li>
              </ul>
              <div v-if="selfCritiquePriorityFixes.length" class="m3-review-card__notes">
                <p class="m3-list-title">{{ pick('优先修复项', 'Priority fixes') }}</p>
                <ul>
                  <li v-for="item in selfCritiquePriorityFixes" :key="item">{{ item }}</li>
                </ul>
              </div>
            </article>

            <article v-if="consistencySummary" class="m3-review-card">
              <p class="m3-kicker">{{ pick('一致性检查', 'Continuity check') }}</p>
              <ul>
                <li>{{ pick('状态', 'Status') }}{{ punct.colon }}{{ consistencySummary.is_consistent ? pick('通过', 'Passed') : pick('发现问题', 'Issues found') }}</li>
                <li>{{ pick('问题数', 'Issue count') }}{{ punct.colon }}{{ consistencyIssueCount }}</li>
                <li>{{ pick('自动修复', 'Auto fix') }}{{ punct.colon }}{{ consistencySummary.auto_fix_applied ? pick('已执行', 'Applied') : pick('未执行', 'Not applied') }}</li>
              </ul>
              <p v-if="consistencySummary.summary" class="m3-review-card__desc">{{ consistencySummary.summary }}</p>
            </article>

            <article v-if="optimizerSummary" class="m3-review-card">
              <p class="m3-kicker">{{ pick('专项优化', 'Targeted optimization') }}</p>
              <ul>
                <li>{{ pick('优化步数', 'Optimization steps') }}{{ punct.colon }}{{ optimizerStepCount }}</li>
                <li v-if="targetedDimensionsText">{{ pick('定向维度', 'Targeted dimensions') }}{{ punct.colon }}{{ targetedDimensionsText }}</li>
                <li v-for="step in optimizerSteps" :key="step">{{ step }}</li>
              </ul>
            </article>

            <article v-if="qualityMetrics" class="m3-review-card">
              <p class="m3-kicker">{{ pick('质量快照', 'Quality snapshot') }}</p>
              <ul>
                <li>{{ pick('字数', 'Word count') }}{{ punct.colon }}{{ qualityMetricValue('word_count') }}</li>
                <li>{{ pick('场景兑现', 'Scene fulfillment') }}{{ punct.colon }}{{ formatPercent(qualityMetrics.scene_fulfillment_rate) }}{{ punct.paren(`${qualityMetricValue('fulfilled_scene_count')}/${qualityMetricValue('scene_count')}`) }}</li>
                <li>{{ pick('对白改局势', 'Dialogue changes state') }}{{ punct.colon }}{{ formatTriState(qualityMetrics.dialogue_changes_state, pick('通过', 'Passed'), pick('未通过', 'Not passed')) }}</li>
                <li>{{ pick('章末递压', 'Ending pressure') }}{{ punct.colon }}{{ qualityMetrics.ending_pressure_passed ? pick('通过', 'Passed') : pick('未通过', 'Not passed') }}</li>
                <li>{{ pick('静态描写风险', 'Static description risk') }}{{ punct.colon }}{{ qualityMetrics.static_description_risk ? pick('偏高', 'High') : pick('可控', 'Under control') }}</li>
                <!-- D-22 相关：事件密度此前完全没进这份快照，用户在版本详情里看不到它。 -->
                <li>{{ pick('事件密度', 'Event density') }}{{ punct.colon }}{{ formatTriState(qualityMetrics.event_density_passed, pick('达标', 'Passed'), pick('不足', 'Too low')) }}</li>
                <li>{{ pick('局势变化间隔', 'State change interval') }}{{ punct.colon }}{{ formatTriState(qualityMetrics.state_change_interval_passed, pick('达标', 'Passed'), pick('过长', 'Too long')) }}</li>
              </ul>
            </article>

            <article v-if="runtimeWordSummary" class="m3-review-card">
              <p class="m3-kicker">{{ pick('字数达标', 'Word count target') }}</p>
              <ul>
                <li>{{ runtimeWordSummary }}</li>
                <li v-if="runtimeWordReason">{{ runtimeWordReason }}</li>
              </ul>
            </article>

            <article v-if="generationCallMetrics.length" class="m3-review-card">
              <p class="m3-kicker">{{ pick('生成调用', 'Generation calls') }}</p>
              <ul>
                <li v-for="item in generationCallMetrics" :key="item.label">
                  {{ item.label }}{{ punct.colon }}{{ item.summary }}
                </li>
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
            {{ pick('当前选中版本', 'Currently selected version') }}
          </span>
          <span v-else class="md-on-surface-variant">{{ pick('未选中版本', 'Not the selected version') }}</span>
        </div>

        <div class="flex gap-3">
          <button
            type="button"
            @click="$emit('close')"
            class="md-btn md-btn-outlined md-ripple"
          >
            {{ t('common.close') }}
          </button>
          <button
            v-if="!isCurrent"
            type="button"
            @click="$emit('selectVersion')"
            class="md-btn md-btn-filled md-ripple"
          >
            {{ pick('选择此版本', 'Use this version') }}
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
import { useLocale } from '@/composables/useLocale'

interface Props {
  show: boolean
  detailVersionIndex: number
  version: ChapterVersion | null
  isCurrent: boolean
}

const props = defineProps<Props>()

defineEmits(['close', 'selectVersion'])

const { pick, t, punct } = useLocale()

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
const qualityMetrics = computed<Record<string, any> | null>(() => {
  const direct = runtimeMeta.value.quality_metrics
  if (direct && typeof direct === 'object') return direct as Record<string, any>
  const finalMetrics = reviewSummaries.value.final_quality_metrics
  if (finalMetrics && typeof finalMetrics === 'object') return finalMetrics as Record<string, any>
  const guardSnapshot = runtimeMeta.value.story_progression_guard?.quality_metric_snapshot
  if (guardSnapshot && typeof guardSnapshot === 'object') return guardSnapshot as Record<string, any>
  return null
})
const qualityMetricValue = (key: string) => {
  const value = qualityMetrics.value?.[key]
  return value === null || value === undefined || value === '' ? '—' : value
}
const formatPercent = (value: unknown) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${Math.round(numeric * 100)}%`
}
// T-13 / T-14：质量快照里的判定字段是三态（true / false / null）。
// null 表示「该维度不适用或样本太短未评估」，必须显示成「不适用」而不是「未通过」——
// 用真假判断（`x ? 通过 : 未通过`）会把「没测」说成「测过且不合格」。
const formatTriState = (value: unknown, passed: string, failed: string) => {
  if (value === true) return passed
  if (value === false) return failed
  return pick('不适用', 'Not applicable')
}
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
      return [dimension ? pick(`【${dimension}】`, `[${dimension}]`) : '', notes].filter(Boolean).join(' ')
    })
    .filter(Boolean)
})
const optimizerStepCount = computed(() => optimizerSteps.value.length)
const targetedDimensionsText = computed(() => {
  const dimensions = optimizerSummary.value?.targeted_dimensions
  if (!Array.isArray(dimensions) || !dimensions.length) return ''
  const labelMap: Record<string, string> = {
    dialogue: pick('对话', 'Dialogue'),
    psychology: pick('心理', 'Psychology'),
    rhythm: pick('节奏', 'Pacing'),
  }
  return dimensions.map((item) => labelMap[String(item)] || String(item)).join(' / ')
})
const runtimeWordSummary = computed(() => {
  const actual = runtimeMeta.value.actual_word_count
  const min = runtimeMeta.value.min_word_count
  const target = runtimeMeta.value.target_word_count
  if (!actual && !min && !target) return ''
  const parts = []
  if (actual) parts.push(pick(`实际 ${actual} 字`, `Actual ${actual} words`))
  if (min) parts.push(pick(`最低 ${min} 字`, `Minimum ${min} words`))
  if (target) parts.push(pick(`目标 ${target} 字`, `Target ${target} words`))
  return parts.join(' / ')
})
const runtimeWordReason = computed(() => {
  const reason = runtimeMeta.value.word_requirement_reason
  if (!reason) return ''
  const map: Record<string, string> = {
    target_met: pick('已达到目标字数', 'Target word count reached'),
    close_to_target: pick('已接近目标字数', 'Close to the target word count'),
    minimum_met: pick('已达到最低字数', 'Minimum word count reached'),
    minimum_met_but_below_target: pick('已达到最低字数，但仍低于目标', 'Minimum reached but still below target'),
    below_minimum_after_enrichment: pick('补字后仍低于最低要求', 'Still below the minimum after enrichment'),
    below_minimum: pick('低于最低要求', 'Below the minimum'),
  }
  return map[String(reason)] || String(reason)
})
const generationCallMetrics = computed(() => {
  const items = runtimeMeta.value.generation_call_metrics
  if (!Array.isArray(items)) return []
  return items
    .map((item, index) => {
      if (!item || typeof item !== 'object') return null
      const record = item as Record<string, any>
      const label = String(record.label || pick(`调用 ${index + 1}`, `Call ${index + 1}`))
      const parts = [
        record.attempts ? pick(`尝试 ${record.attempts} 次`, `${record.attempts} attempt(s)`) : '',
        record.estimated_total_tokens ? pick(`约 ${record.estimated_total_tokens} tokens`, `about ${record.estimated_total_tokens} tokens`) : '',
        record.effective_max_tokens ? pick(`上限 ${record.effective_max_tokens}`, `limit ${record.effective_max_tokens}`) : '',
        record.provider_error_type ? pick(`曾遇到 ${record.provider_error_type}`, `hit ${record.provider_error_type}`) : '',
      ].filter(Boolean)
      return { label, summary: parts.join(' / ') || pick('已记录调用指标', 'Call metrics recorded') }
    })
    .filter((item): item is { label: string; summary: string } => Boolean(item))
    .slice(0, 4)
})
const hasReviewInsights = computed(() => Boolean(
  qualityMetrics.value || selfCritiqueSummary.value || consistencySummary.value || optimizerSummary.value || runtimeWordSummary.value || generationCallMetrics.value.length
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
