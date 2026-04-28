<template>
  <div v-if="show" class="eval-overlay" @click.self="emit('close')">
    <div class="eval-dialog">
      <header class="eval-header">
        <div>
          <p class="eval-kicker">AI 综合评审</p>
          <h3>候选版本评审详情</h3>
          <p class="eval-subtitle">会明确写清楚推荐的是哪个候选版本、每个版本各自的优缺点，以及可直接回填的优化建议。</p>
        </div>
        <button type="button" class="md-icon-btn md-ripple" aria-label="关闭评审详情" @click="emit('close')">×</button>
      </header>

      <div class="eval-body">
        <section v-if="parsedEvaluation" class="eval-overview">
          <div class="eval-overview__summary">
            <div>
              <p class="eval-kicker">推荐结论</p>
              <h4>推荐优先查看：候选版本 {{ recommendedVersionLabel }}</h4>
              <p>{{ recommendationText }}</p>
            </div>
            <div class="eval-overview__stats">
              <div class="eval-stat">
                <span>推荐版本</span>
                <strong>候选版本 {{ recommendedVersionLabel }}</strong>
              </div>
              <div class="eval-stat">
                <span>评审结果数</span>
                <strong>{{ versionEvaluations.length }}</strong>
              </div>
              <div v-if="parsedEvaluation?.content_to_evaluate?.total_versions" class="eval-stat">
                <span>候选版本总数</span>
                <strong>{{ parsedEvaluation.content_to_evaluate.total_versions }}</strong>
              </div>
            </div>
          </div>

          <div v-if="versionEvaluations.length" class="eval-grid">
            <article
              v-for="item in versionEvaluations"
              :key="item.key"
              :class="['eval-card', item.isRecommended ? 'eval-card--recommended' : '']"
            >
              <div class="eval-card__head">
                <div>
                  <p class="eval-card__code">候选版本 {{ item.label }}</p>
                  <h5>{{ item.title }}</h5>
                </div>
                <span v-if="item.isRecommended" class="eval-badge">推荐采用</span>
              </div>

              <p class="eval-card__review">{{ item.overallReview || '该版本暂无完整总评。' }}</p>

              <div class="eval-card__lists">
                <div>
                  <p class="eval-list-title">优点</p>
                  <ul>
                    <li v-for="pro in item.pros" :key="`${item.key}-pro-${pro}`">{{ pro }}</li>
                    <li v-if="!item.pros.length" class="eval-empty">当前没有提炼出明确优点。</li>
                  </ul>
                </div>
                <div>
                  <p class="eval-list-title">问题 / 待补强</p>
                  <ul>
                    <li v-for="con in item.cons" :key="`${item.key}-con-${con}`">{{ con }}</li>
                    <li v-if="!item.cons.length" class="eval-empty">当前没有列出明显短板，可重点查看总评。</li>
                  </ul>
                </div>
              </div>
            </article>
          </div>

          <div v-if="additionalInsights.length" class="eval-insights">
            <p class="eval-kicker">补充提示</p>
            <ul>
              <li v-for="note in additionalInsights" :key="note">{{ note }}</li>
            </ul>
          </div>
        </section>

        <section v-else class="eval-fallback">
          <p class="eval-kicker">原始评审文本</p>
          <pre>{{ normalizedEvaluationText }}</pre>
        </section>

        <section class="eval-suggestion-panel">
          <div class="eval-suggestion-panel__head">
            <div>
              <p class="eval-kicker">直接可用的建议</p>
              <h4>选中后可以直接带回重写或局部优化</h4>
            </div>
            <div class="eval-target-tabs">
              <button type="button" :class="['eval-target-tab', activeTarget === 'writing' ? 'eval-target-tab--active' : '']" @click="activeTarget = 'writing'">重写方向</button>
              <button type="button" :class="['eval-target-tab', activeTarget === 'quality' ? 'eval-target-tab--active' : '']" @click="activeTarget = 'quality'">质量要求</button>
              <button type="button" :class="['eval-target-tab', activeTarget === 'optimize' ? 'eval-target-tab--active' : '']" @click="activeTarget = 'optimize'">局部优化</button>
            </div>
          </div>

          <div class="eval-tag-list">
            <button v-for="tag in suggestionTags" :key="tag" type="button" class="eval-tag" @click="appendSuggestion(tag)">{{ tag }}</button>
          </div>

          <div class="eval-draft-grid">
            <div>
              <label class="md-text-field-label mb-2">重写方向</label>
              <textarea v-model="writingNotesDraft" rows="4" class="md-textarea w-full" placeholder="例如：加强前半章压迫感，让尾声钩子更狠。" />
            </div>
            <div>
              <label class="md-text-field-label mb-2">质量要求</label>
              <textarea v-model="qualityNotesDraft" rows="4" class="md-textarea w-full" placeholder="例如：让主角心理变化更自然，对话带更多潜台词。" />
            </div>
            <div class="eval-draft-grid__wide">
              <label class="md-text-field-label mb-2">局部优化说明</label>
              <textarea v-model="optimizeNotesDraft" rows="3" class="md-textarea w-full" placeholder="例如：只优化节奏和心理层，不动核心剧情。" />
            </div>
          </div>
        </section>
      </div>

      <footer class="eval-footer">
        <button type="button" class="md-btn md-btn-outlined md-ripple" @click="emit('close')">关闭</button>
        <button type="button" class="md-btn md-btn-tonal md-ripple" :disabled="!canUseOptimizeSuggestion" @click="emitOptimizeSuggestion">用于局部优化</button>
        <button type="button" class="md-btn md-btn-filled md-ripple" :disabled="!canRegenerate" @click="emitRegenerate">带着这些建议重写</button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Props {
  show: boolean
  evaluation: string | null
}

interface EvaluationVersionView {
  key: string
  label: string
  title: string
  isRecommended: boolean
  overallReview: string
  pros: string[]
  cons: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'regenerate', payload: { writingNotes?: string; qualityRequirements?: string }): void
  (e: 'optimize', payload: { notes: string }): void
}>()

const writingNotesDraft = ref('')
const qualityNotesDraft = ref('')
const optimizeNotesDraft = ref('')
const activeTarget = ref<'writing' | 'quality' | 'optimize'>('writing')

const normalizeText = (value: unknown): string => {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (Array.isArray(value)) return value.map(item => normalizeText(item)).filter(Boolean).join('；')
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

const stripCodeFence = (text: string) => text.trim().replace(/^```(?:json|JSON)?\s*/u, '').replace(/```$/u, '').trim()

const extractJsonCandidate = (text: string) => {
  const cleaned = stripCodeFence(text).replace(/^`+|`+$/g, '').trim()
  if (!cleaned) return ''
  if ((cleaned.startsWith('{') && cleaned.endsWith('}')) || (cleaned.startsWith('[') && cleaned.endsWith(']'))) return cleaned
  const objectMatch = cleaned.match(/\{[\s\S]*\}/u)
  if (objectMatch) return objectMatch[0]
  const arrayMatch = cleaned.match(/\[[\s\S]*\]/u)
  return arrayMatch?.[0] || cleaned
}

const tryParseEvaluation = (raw: string | null): Record<string, any> | null => {
  if (!raw) return null
  const candidates = [raw, stripCodeFence(raw), extractJsonCandidate(raw)].filter(Boolean)
  for (const candidate of candidates) {
    try {
      let parsed: unknown = JSON.parse(candidate)
      while (typeof parsed === 'string') {
        const next = extractJsonCandidate(parsed)
        if (!next || next === parsed) break
        parsed = JSON.parse(next)
      }
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, any>
    } catch {
      continue
    }
  }
  return null
}

const parsedEvaluation = computed(() => tryParseEvaluation(props.evaluation))
const normalizedEvaluationText = computed(() =>
  props.evaluation ? stripCodeFence(props.evaluation).replace(/\\n/g, '\n').trim() : '暂无评审结果。'
)

const recommendedVersionIndex = computed(() => {
  const parsed = parsedEvaluation.value
  if (!parsed) return null
  const raw = parsed.best_choice ?? parsed.best_version_index ?? parsed.bestVersion ?? parsed.recommended_version ?? null
  const numeric = Number(raw)
  if (Number.isFinite(numeric) && numeric > 0) return numeric
  if (Number.isFinite(numeric) && numeric >= 0) return numeric + 1
  return null
})

const recommendedVersionLabel = computed(() => recommendedVersionIndex.value ?? '未指定')
const recommendationText = computed(() => {
  const parsed = parsedEvaluation.value
  return normalizeText(parsed?.reason_for_choice) || normalizeText(parsed?.final_recommendation) || normalizeText(parsed?.summary) || '当前评审已返回，但没有给出一句明确结论。建议先看各版本优缺点再决定。'
})

const versionEvaluations = computed<EvaluationVersionView[]>(() => {
  const parsed = parsedEvaluation.value
  const source = parsed?.evaluation
  if (!source || typeof source !== 'object') {
    if (parsed && (parsed.overall_evaluation || parsed.critical_flaws || parsed.pros || parsed.cons)) {
      return [{
        key: 'version1',
        label: '1',
        title: '单版本评审结果',
        isRecommended: true,
        overallReview: normalizeText(parsed.overall_evaluation) || '该版本已完成评审。',
        pros: Array.isArray(parsed.pros) ? parsed.pros.map((item: string) => normalizeText(item)).filter(Boolean) : [],
        cons: Array.isArray(parsed.cons) ? parsed.cons.map((item: string) => normalizeText(item)).filter(Boolean) : [],
      }]
    }
    return []
  }

  return Object.entries(source).map(([key, value], index) => {
    const data = (value && typeof value === 'object' ? value : {}) as Record<string, any>
    const label = key.replace(/^version/iu, '') || String(index + 1)
    return {
      key,
      label,
      title: recommendedVersionIndex.value === Number(label) ? '综合表现最佳' : '可参考候选版本',
      isRecommended: recommendedVersionIndex.value === Number(label),
      overallReview: normalizeText(data.overall_review) || normalizeText(data.summary) || normalizeText(data.reason) || '该版本暂无完整总评。',
      pros: Array.isArray(data.pros) ? data.pros.map(item => normalizeText(item)).filter(Boolean) : [],
      cons: Array.isArray(data.cons) ? data.cons.map(item => normalizeText(item)).filter(Boolean) : [],
    }
  })
})

const additionalInsights = computed(() => {
  const parsed = parsedEvaluation.value
  const notes = [normalizeText(parsed?.critical_flaws), normalizeText(parsed?.refinement_suggestions), normalizeText(parsed?.final_recommendation)]
    .filter(Boolean)
    .flatMap(item => item.split(/[；。！\n]/u).map(part => part.trim()).filter(part => part.length >= 6 && part.length <= 120))
  return Array.from(new Set(notes)).slice(0, 6)
})

const fallbackTags = ['加强章节开场冲突', '让角色心理变化更自然', '尾声钩子更狠', '对话增加潜台词', '压缩解释性叙述', '强化前后文承接']
const suggestionTags = computed(() => {
  const dynamicTags = versionEvaluations.value.flatMap(item => [...item.pros, ...item.cons]).map(text => text.trim()).filter(Boolean).slice(0, 8)
  return Array.from(new Set([...dynamicTags, ...fallbackTags])).slice(0, 12)
})

const appendSuggestion = (tag: string) => {
  if (activeTarget.value === 'quality') {
    qualityNotesDraft.value = [qualityNotesDraft.value.trim(), tag].filter(Boolean).join('?')
  } else if (activeTarget.value === 'optimize') {
    optimizeNotesDraft.value = [optimizeNotesDraft.value.trim(), tag].filter(Boolean).join('?')
  } else {
    writingNotesDraft.value = [writingNotesDraft.value.trim(), tag].filter(Boolean).join('?')
  }
}

const canRegenerate = computed(() => Boolean(writingNotesDraft.value.trim() || qualityNotesDraft.value.trim()))
const canUseOptimizeSuggestion = computed(() => Boolean(optimizeNotesDraft.value.trim() || writingNotesDraft.value.trim() || qualityNotesDraft.value.trim()))

const emitRegenerate = () => emit('regenerate', {
  writingNotes: writingNotesDraft.value.trim() || undefined,
  qualityRequirements: qualityNotesDraft.value.trim() || undefined,
})

const emitOptimizeSuggestion = () => emit('optimize', {
  notes: [optimizeNotesDraft.value.trim(), writingNotesDraft.value.trim(), qualityNotesDraft.value.trim()].filter(Boolean).join('?')
})

watch(() => props.show, (visible) => {
  if (!visible) return
  writingNotesDraft.value = ''
  qualityNotesDraft.value = ''
  optimizeNotesDraft.value = ''
  activeTarget.value = 'writing'
}, { immediate: true })
</script>

<style scoped>
.eval-overlay { position: fixed; inset: 0; z-index: 80; background: rgba(15, 23, 42, 0.45); backdrop-filter: blur(6px); display: flex; justify-content: center; align-items: center; padding: 16px; }
.eval-dialog { width: min(1440px, 100%); max-height: calc(100vh - 32px); overflow: hidden; display: flex; flex-direction: column; border-radius: 28px; background: #fff; box-shadow: 0 32px 80px rgba(15, 23, 42, 0.24); }
.eval-header, .eval-overview__summary, .eval-overview__stats, .eval-card__head, .eval-suggestion-panel__head, .eval-target-tabs, .eval-tag-list, .eval-footer { display: flex; gap: 10px; }
.eval-header, .eval-overview__summary, .eval-suggestion-panel__head, .eval-footer { justify-content: space-between; align-items: center; }
.eval-header { padding: 18px 22px; border-bottom: 1px solid rgba(148,163,184,.18); }
.eval-body { padding: 18px 22px; overflow: auto; display: grid; gap: 18px; }
.eval-kicker { margin: 0 0 4px; color: #6366f1; font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.eval-header h3, .eval-overview h4, .eval-suggestion-panel h4 { margin: 0; color: #0f172a; }
.eval-subtitle, .eval-overview p, .eval-card__review, .eval-empty, .eval-fallback pre { color: #475569; }
.eval-overview, .eval-suggestion-panel, .eval-fallback, .eval-insights { border: 1px solid rgba(148,163,184,.18); border-radius: 22px; background: #f8fafc; padding: 16px; }
.eval-overview__stats, .eval-target-tabs, .eval-tag-list { flex-wrap: wrap; align-items: center; }
.eval-stat { min-width: 140px; border-radius: 16px; background: #fff; padding: 12px 14px; border: 1px solid rgba(148,163,184,.18); display: grid; gap: 4px; }
.eval-stat span { color: #64748b; font-size: .82rem; }
.eval-stat strong { color: #0f172a; font-size: 1rem; }
.eval-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }
.eval-card { border-radius: 20px; border: 1px solid rgba(148,163,184,.2); background: #fff; padding: 16px; display: grid; gap: 14px; }
.eval-card--recommended { border-color: rgba(79,70,229,.35); box-shadow: inset 0 0 0 1px rgba(79,70,229,.18); }
.eval-card__code { margin: 0 0 4px; font-size: .8rem; color: #6366f1; font-weight: 700; }
.eval-card h5 { margin: 0; font-size: 1rem; color: #0f172a; }
.eval-badge { display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px; background: #eef2ff; color: #4338ca; font-size: .78rem; font-weight: 700; }
.eval-card__review { margin: 0; line-height: 1.6; }
.eval-card__lists { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.eval-list-title { margin: 0 0 8px; font-size: .85rem; font-weight: 700; color: #0f172a; }
.eval-card ul, .eval-insights ul { margin: 0; padding-left: 18px; display: grid; gap: 8px; }
.eval-empty { list-style: none; padding-left: 0; }
.eval-target-tab, .eval-tag { border: 1px solid rgba(148,163,184,.2); background: #fff; color: #334155; border-radius: 999px; padding: 8px 12px; cursor: pointer; }
.eval-target-tab--active { background: #eef2ff; color: #4338ca; border-color: rgba(99,102,241,.24); }
.eval-tag-list { margin-top: 12px; }
.eval-draft-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }
.eval-draft-grid__wide { grid-column: 1 / -1; }
.eval-footer { padding: 16px 22px; border-top: 1px solid rgba(148,163,184,.18); }
@media (max-width: 980px) { .eval-grid, .eval-card__lists, .eval-draft-grid { grid-template-columns: 1fr; } }
</style>
