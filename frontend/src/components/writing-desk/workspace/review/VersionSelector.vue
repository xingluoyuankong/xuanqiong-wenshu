<template>
  <div class="version-selector-shell">
    <section class="version-selector-head">
      <div>
        <div class="version-selector-head__chips">
          <span class="vs-chip vs-chip--primary">候选版本评审区</span>
          <span class="vs-chip">共 {{ availableVersions.length }} 个版本</span>
          <span v-if="selectedChapter?.content" class="vs-chip">当前正文已存在</span>
        </div>
        <h4>先横向浏览候选版本，再决定对比、评审还是确认采用</h4>
        <p>每个卡片都会明确标出版本编号、当前正文、当前查看和对比对象，不再让你猜 AI 在说哪一版。</p>
      </div>

      <div class="version-selector-head__actions">
        <button type="button" class="md-btn md-btn-text md-ripple" @click="emit('hideVersionSelector')">返回正文</button>
        <button
          v-if="selectedChapter?.evaluation"
          type="button"
          class="md-btn md-btn-filled md-ripple version-selector-head__action version-selector-head__action--primary"
          @click="emit('showEvaluationDetail')"
        >
          查看综合评审
        </button>
      </div>
    </section>

    <section class="version-decision-panel" aria-label="候选版本决策面板">
      <div class="version-decision-panel__lead">
        <p class="version-selector-list__kicker">决策辅助</p>
        <h5>{{ decisionTitle }}</h5>
        <p>{{ decisionHint }}</p>
      </div>
      <div class="version-decision-metrics">
        <div v-for="item in decisionMetrics" :key="item.label" :class="['version-decision-metric', `version-decision-metric--${item.tone}`]">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </div>
      </div>
    </section>

    <section v-if="evaluatingChapter === selectedChapter?.chapter_number" class="version-selector-progress">
      <div class="progress-row">
        <span>AI 评审处理中</span>
        <strong>正在等待评审结果返回</strong>
      </div>
      <div class="progress-track" aria-label="ai-review-progress">
        <div class="progress-bar progress-bar--phase progress-bar--indeterminate"></div>
      </div>
    </section>

    <section
      v-if="isEvaluationFailed || selectedChapter?.evaluation"
      :class="['version-selector-banner', isEvaluationFailed ? 'version-selector-banner--error' : 'version-selector-banner--success']"
    >
      <div>
        <h4>{{ isEvaluationFailed ? 'AI 评审未完整返回' : 'AI 评审已生成' }}</h4>
        <p>
          {{
            isEvaluationFailed
              ? '候选版本仍然可以继续查看和确认，你也可以重新发起 AI 评审。'
              : '综合评审入口已经收口到上方“查看综合评审”，避免这里再放一颗重复按钮。'
          }}
        </p>
      </div>
      <button
        v-if="isEvaluationFailed"
        type="button"
        class="md-btn md-btn-filled md-ripple"
        :disabled="evaluatingChapter === selectedChapter?.chapter_number"
        @click="emit('evaluateAllVersions')"
      >
        重新发起评审
      </button>
      <span v-else class="version-selector-banner__note">先看综合结论，再决定确认哪一版。</span>
    </section>

    <section v-if="renderedGenerationMessage" class="version-selector-note">
      <div class="version-selector-note__badge">本轮生成说明</div>
      <div class="version-selector-note__content" v-html="renderedGenerationMessage"></div>
    </section>

    <section class="version-selector-list">
      <div class="version-selector-list__head">
        <div>
          <p class="version-selector-list__kicker">候选版本横向总览</p>
          <h5>左右滑动并点击选择候选版本</h5>
        </div>
        <div class="version-selector-nav">
          <button type="button" class="version-selector-nav__btn" :disabled="!hasPrevVersion" @click="selectPrevVersion">上一个版本</button>
          <button type="button" class="version-selector-nav__btn" :disabled="!hasNextVersion" @click="selectNextVersion">下一个版本</button>
        </div>
      </div>

      <div ref="cardRowRef" class="version-selector-row">
        <article
          v-for="card in versionCardModels"
          :key="card.version.id ?? card.index"
          :class="['version-card', selectedVersionIndex === card.index ? 'version-card--selected' : '', card.isCurrent ? 'version-card--current' : '']"
        >
          <button
            type="button"
            class="version-card__main"
            :aria-pressed="selectedVersionIndex === card.index"
            @click="selectVersionIndex(card.index)"
          >
            <div class="version-card__head">
              <div>
                <p class="version-card__code">候选版本 {{ card.index + 1 }}</p>
                <strong>{{ card.version.style || '标准版本' }}</strong>
              </div>
              <div class="version-card__tags">
                <span class="vs-chip">约 {{ card.approxWordCount }} 字</span>
                <span v-if="card.isAiRecommended" class="vs-chip vs-chip--recommend">AI 推荐</span>
                <span v-if="card.isCurrent" class="vs-chip vs-chip--success">当前正文</span>
                <span v-else-if="selectedVersionIndex === card.index" class="vs-chip vs-chip--accent">当前查看</span>
                <span v-if="compareVersionIndex === card.index" class="vs-chip vs-chip--warn">对比对象</span>
              </div>
            </div>
            <p class="version-card__excerpt">{{ card.preview }}</p>
            <div v-if="card.qualitySummary" class="version-card__quality">
              <span :class="['version-card__quality-pill', `version-card__quality-pill--${card.qualitySummary.tone}`]">
                {{ card.qualitySummary.label }}
              </span>
              <span v-if="card.qualitySummary.issues.length" class="version-card__quality-issues">
                {{ card.qualitySummary.issues.slice(0, 2).join(' / ') }}
              </span>
            </div>
          </button>

          <div class="version-card__actions">
            <button
              type="button"
              class="md-btn md-btn-text md-ripple"
              :disabled="evaluatingVersionIndex === card.index"
              @click.stop="card.version.evaluation ? emit('showEvaluationDetail', card.index) : emit('evaluateVersion', card.index)"
            >
              {{ evaluatingVersionIndex === card.index ? '评审中…' : card.version.evaluation ? '查看评审' : 'AI 评审' }}
            </button>
            <button type="button" class="md-btn md-btn-text md-ripple" @click.stop="setCompareVersion(card.index)">
              {{ compareVersionIndex === card.index ? '取消对比' : '加入对比' }}
            </button>
            <button
              v-if="!card.isCurrent && availableVersions.length > 1"
              type="button"
              class="md-btn md-btn-text md-ripple version-card__delete"
              :disabled="deletingVersionIndex === card.index"
              @click.stop="handleDeleteVersion(card.index)"
            >
              {{ deletingVersionIndex === card.index ? '删除中…' : '删除' }}
            </button>
          </div>
        </article>
      </div>
    </section>

    <section class="version-preview">
      <div class="version-preview__top">
        <div>
          <p class="version-preview__kicker">当前预览</p>
          <h5>候选版本 {{ selectedVersionIndex + 1 }}</h5>
          <p class="version-preview__meta">
            {{ activeVersion?.style || '标准版本' }} · {{ Math.max(1, Math.round(selectedVersionContent.length / 100)) * 100 }} 字
          </p>
        </div>
        <div class="version-preview__tags">
          <span v-if="activeVersionCard?.isAiRecommended" class="vs-chip vs-chip--recommend">AI 推荐采用</span>
          <span v-if="isCurrentVersion(selectedVersionIndex)" class="vs-chip vs-chip--success">这就是当前正文</span>
          <span v-else class="vs-chip vs-chip--accent">待确认候选版本</span>
          <span v-if="compareVersionIndex !== null && compareVersionIndex !== undefined" class="vs-chip">
            当前对比对象：候选版本 {{ compareVersionIndex + 1 }}
          </span>
        </div>
      </div>

      <div class="version-preview__body">
        <div
          v-if="activeQualitySummary"
          :class="['version-preview__quality', `version-preview__quality--${activeQualitySummary.tone}`]"
        >
          <div>
            <strong>{{ activeQualitySummary.label }}</strong>
            <p>{{ activeQualityHint }}</p>
          </div>
          <ul v-if="activeQualitySummary.issues.length">
            <li v-for="issue in activeQualitySummary.issues" :key="issue">{{ issue }}</li>
          </ul>
        </div>
        <div class="version-preview__excerpt">{{ selectedVersionPreview }}</div>
        <p v-if="previewHintVisible" class="version-preview__hint">这里只保留预览摘要，点击“查看全文”会跳到完整阅读页。</p>
      </div>

      <div class="version-preview__actions">
        <div class="version-preview__tools">
          <span class="version-preview__tools-label">辅助工具</span>
          <button type="button" class="md-btn md-btn-text md-ripple" :disabled="!activeVersion?.content" @click="openVersionReader(selectedVersionIndex)">查看全文</button>
          <button type="button" class="md-btn md-btn-text md-ripple" :disabled="!activeVersion?.content" @click="emit('optimizeVersion', selectedVersionIndex)">优化这一版</button>
        </div>
        <div class="version-preview__decision">
          <button
            type="button"
            class="md-btn md-btn-outlined md-ripple"
            :disabled="compareVersionIndex === null || compareVersionIndex === undefined || !activeVersion?.content"
            @click="openVersionDiff"
          >
            对比候选版本
          </button>
          <button
            type="button"
            class="md-btn md-btn-filled md-ripple version-preview__confirm"
            :disabled="!activeVersion?.content || isCurrentVersion(selectedVersionIndex) || isSelectingVersion"
            @click="emit('confirmVersionSelection')"
          >
            {{ isSelectingVersion ? '确认中…' : isCurrentVersion(selectedVersionIndex) ? '当前正文已选中' : `确认候选版本 ${selectedVersionIndex + 1}` }}
          </button>
          <p v-if="activeQualitySummary?.tone === 'danger'" class="version-preview__confirm-warning">
            确认前注意：当前候选仍有明显质量风险，建议先优化或改选质量更稳的版本。
          </p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { Chapter, ChapterGenerationResponse, ChapterVersion } from '@/api/novel'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import { buildChapterPreview, normalizeChapterContent } from '@/utils/chapterContent'
import { buildChapterQualitySummary, type ChapterQualitySummary } from '@/utils/chapterQuality'

interface Props {
  selectedChapter: Chapter | null
  chapterGenerationResult: ChapterGenerationResponse | null
  availableVersions: ChapterVersion[]
  selectedVersionIndex: number
  compareVersionIndex?: number | null
  evaluatingChapter: number | null
  evaluatingVersionIndex?: number | null
  isSelectingVersion?: boolean
  isEvaluationFailed?: boolean
  deletingVersionIndex?: number | null
}

interface ReaderPayload {
  title: string
  content: string
  subtitle?: string
  source?: string
  chapterNumber?: number
  versionIndex?: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'hideVersionSelector'): void
  (e: 'update:selectedVersionIndex', index: number): void
  (e: 'update:compareVersionIndex', index: number | null): void
  (e: 'openVersionDiff', payload: { baseVersionIndex: number; compareVersionIndex: number }): void
  (e: 'openReader', payload: ReaderPayload): void
  (e: 'confirmVersionSelection'): void
  (e: 'evaluateChapter'): void
  (e: 'evaluateAllVersions'): void
  (e: 'evaluateVersion', versionIndex: number): void
  (e: 'showEvaluationDetail', versionIndex?: number): void
  (e: 'showVersionDetail', versionIndex: number): void
  (e: 'deleteVersion', versionIndex: number): void
  (e: 'optimizeVersion', versionIndex: number): void
}>()

const cardRowRef = ref<HTMLElement | null>(null)
const hasConfirmedSelection = computed(() => props.selectedChapter?.generation_status === 'successful')
const normalizedSelectedChapterContent = computed(() => normalizeChapterContent(props.selectedChapter?.content || ''))
const selectedVersionId = computed(() => props.selectedChapter?.selected_version_id ?? null)
const renderedGenerationMessage = computed(() => {
  const message = props.chapterGenerationResult?.ai_message
  return message ? renderSafeMarkdown(message) : ''
})

interface VersionCardModel {
  index: number
  version: ChapterVersion
  normalizedContent: string
  preview: string
  approxWordCount: number
  isCurrent: boolean
  isAiRecommended: boolean
  qualitySummary: ChapterQualitySummary | null
}

const versionCardModels = computed<VersionCardModel[]>(() => props.availableVersions.map((version, index) => {
  const normalizedContent = normalizeChapterContent(version.content || '')
  const isCurrent = hasConfirmedSelection.value
    ? selectedVersionId.value && version.id
      ? selectedVersionId.value === version.id
      : Boolean(normalizedSelectedChapterContent.value && normalizedContent && normalizedSelectedChapterContent.value === normalizedContent)
    : false

  return {
    index,
    version,
    normalizedContent,
    preview: buildChapterPreview(version.content || '', 280),
    approxWordCount: Math.max(1, Math.round(normalizedContent.length / 100)) * 100,
    isCurrent,
    isAiRecommended: Boolean(version.metadata?.ai_review?.is_best),
    qualitySummary: buildChapterQualitySummary({
      ...(props.selectedChapter || {
        chapter_number: 0,
        title: '',
        summary: '',
        content: null,
        versions: null,
        evaluation: null,
        generation_status: 'not_generated',
      }),
      selected_version_id: version.id ?? null,
      versions: [version],
    }),
  }
}))

const activeVersionCard = computed(() => versionCardModels.value[props.selectedVersionIndex] || null)
const activeVersion = computed(() => activeVersionCard.value?.version || null)
const activeQualitySummary = computed(() => activeVersionCard.value?.qualitySummary || null)
const activeQualityHint = computed(() => {
  if (!activeQualitySummary.value) return ''
  if (activeQualitySummary.value.tone === 'success') return '这一版在场景兑现、对白推进、章末递压和静态描写风险上暂未触发硬风险。'
  return '这些问题会直接影响章节推进感和连续性，确认前建议优先处理。'
})
const selectedVersionContent = computed(() => activeVersionCard.value?.normalizedContent || '')
const selectedVersionPreview = computed(() => buildChapterPreview(activeVersion.value?.content || '', 1400))
const previewHintVisible = computed(() => selectedVersionContent.value.length > selectedVersionPreview.value.length + 40)
const hasPrevVersion = computed(() => props.selectedVersionIndex > 0)
const hasNextVersion = computed(() => props.selectedVersionIndex < props.availableVersions.length - 1)
const evaluatedVersionCount = computed(() => props.availableVersions.filter((version) => Boolean(version.evaluation)).length)
const currentVersionCount = computed(() => versionCardModels.value.filter((card) => card.isCurrent).length)
const averageVersionLength = computed(() => {
  if (!versionCardModels.value.length) return 0
  const total = versionCardModels.value.reduce((sum, card) => sum + card.normalizedContent.length, 0)
  return Math.round(total / versionCardModels.value.length)
})
const decisionTitle = computed(() => {
  if (props.isEvaluationFailed) return 'AI 评审异常，但候选稿仍可人工确认'
  if (props.selectedChapter?.evaluation) return '综合评审已就绪，建议先看结论再确认'
  if (props.availableVersions.length > 1) return '多版本对照中，先选基准再设对比对象'
  return '单版本确认中，重点检查正文完整度'
})
const decisionHint = computed(() => {
  if (props.compareVersionIndex !== null && props.compareVersionIndex !== undefined) {
    return `正在用候选版本 ${props.selectedVersionIndex + 1} 对比候选版本 ${props.compareVersionIndex + 1}。`
  }
  if (props.availableVersions.length > 1) return '建议选中最顺的一版，再设置另一个候选为对比对象，最后确认采用。'
  return '当前只有一个候选版本，如质量不足可先优化或重新生成。'
})
const decisionMetrics = computed(() => [
  { label: '候选版本', value: props.availableVersions.length, hint: '可选择稿件', tone: props.availableVersions.length > 1 ? 'info' : 'warn' },
  { label: '已评审', value: evaluatedVersionCount.value, hint: '单版评审', tone: evaluatedVersionCount.value ? 'success' : 'warn' },
  { label: '当前正文', value: currentVersionCount.value, hint: '已采用标记', tone: currentVersionCount.value ? 'success' : 'info' },
  { label: '均字数', value: averageVersionLength.value, hint: '候选平均', tone: averageVersionLength.value >= 600 ? 'success' : 'warn' }
])

const cleanVersionContent = (content: string) => normalizeChapterContent(content)

const isCurrentVersion = (versionIndex: number) => versionCardModels.value[versionIndex]?.isCurrent ?? false

const scrollCardIntoView = async (index: number) => {
  await nextTick()
  const container = cardRowRef.value
  const card = container?.children?.[index] as HTMLElement | undefined
  if (typeof card?.scrollIntoView === 'function') {
    card.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }
}

const selectVersionIndex = (index: number) => {
  emit('update:selectedVersionIndex', index)
  void scrollCardIntoView(index)
}

const selectPrevVersion = () => {
  if (hasPrevVersion.value) selectVersionIndex(props.selectedVersionIndex - 1)
}

const selectNextVersion = () => {
  if (hasNextVersion.value) selectVersionIndex(props.selectedVersionIndex + 1)
}

const openVersionReader = (versionIndex: number) => {
  const version = props.availableVersions?.[versionIndex]
  if (!version?.content) return

  emit('update:selectedVersionIndex', versionIndex)
  emit('openReader', {
    title: props.selectedChapter?.title?.trim() || `第 ${props.selectedChapter?.chapter_number || ''} 章`,
    subtitle: version.style ? `候选版本 ${versionIndex + 1} · ${version.style}` : `候选版本 ${versionIndex + 1}`,
    content: cleanVersionContent(version.content),
    source: 'candidate-version',
    chapterNumber: props.selectedChapter?.chapter_number || undefined,
    versionIndex: isCurrentVersion(versionIndex) ? undefined : versionIndex,
  })
}

const setCompareVersion = (versionIndex: number) => {
  if (versionIndex === props.selectedVersionIndex) {
    emit('update:compareVersionIndex', null)
    return
  }
  emit('update:compareVersionIndex', props.compareVersionIndex === versionIndex ? null : versionIndex)
}

const openVersionDiff = () => {
  if (props.compareVersionIndex === null || props.compareVersionIndex === undefined) return
  emit('openVersionDiff', {
    baseVersionIndex: props.selectedVersionIndex,
    compareVersionIndex: props.compareVersionIndex,
  })
}

const handleDeleteVersion = (versionIndex: number) => {
  if (isCurrentVersion(versionIndex) || props.availableVersions.length <= 1) return
  emit('deleteVersion', versionIndex)
}

watch(() => props.selectedVersionIndex, index => { void scrollCardIntoView(index) }, { immediate: true })
</script>

<style scoped>
.version-selector-shell {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}

.version-selector-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.85);
}

.version-selector-head h4 {
  margin: 4px 0 0;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.version-selector-head p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.version-selector-head__chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.vs-chip {
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

.vs-chip--primary {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
}

.version-selector-head__actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.version-selector-head__action--primary {
  min-height: 28px;
  padding: 0 10px;
  font-size: 11px;
}

.version-decision-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(248, 250, 252, 0.8);
}

.version-decision-panel__lead {
  display: grid;
  gap: 2px;
}

.version-selector-list__kicker {
  margin: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #6366f1;
}

.version-decision-panel__lead h5 {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.version-decision-panel__lead p {
  margin: 0;
  font-size: 10px;
  color: #64748b;
}

.version-decision-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 6px;
}

.version-decision-metric {
  display: grid;
  gap: 1px;
  padding: 6px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.1);
  text-align: center;
}

.version-decision-metric span {
  color: #94a3b8;
  font-size: 9px;
  font-weight: 600;
}

.version-decision-metric strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.version-decision-metric em {
  color: #94a3b8;
  font-size: 9px;
  font-style: normal;
}

.version-decision-metric--success { border-color: rgba(34, 197, 94, 0.2); }
.version-decision-metric--warn { border-color: rgba(14, 165, 233, 0.25); }
.version-decision-metric--danger { border-color: rgba(239, 68, 68, 0.2); }

.version-selector-progress {
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(248, 250, 252, 0.8);
}

.version-selector-progress .progress-row {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #64748b;
}

.version-selector-progress .progress-track {
  width: 100%;
  height: 4px;
  background: rgba(148, 163, 184, 0.15);
  border-radius: 999px;
  overflow: hidden;
  margin-top: 4px;
}

.version-selector-progress .progress-bar {
  height: 100%;
  border-radius: 999px;
}

.version-selector-progress .progress-bar--phase {
  background: linear-gradient(90deg, #8b5cf6, #3b82f6);
}

.version-selector-progress .progress-bar--indeterminate {
  width: 40%;
  animation: loading-slide 1.5s ease-in-out infinite;
}

@keyframes loading-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

.version-selector-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 11px;
}

.version-selector-banner--success {
  border: 1px solid rgba(34, 197, 94, 0.2);
  background: rgba(240, 253, 244, 0.8);
}

.version-selector-banner--error {
  border: 1px solid rgba(239, 68, 68, 0.2);
  background: rgba(254, 242, 242, 0.8);
}

.version-selector-banner h4 {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
}

.version-selector-banner p {
  margin: 2px 0 0;
  color: #64748b;
  font-size: 10px;
}

.version-selector-banner__note {
  color: #059669;
  font-weight: 600;
  font-size: 10px;
}

.version-selector-note {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.8);
  font-size: 11px;
}

.version-selector-note__badge {
  font-weight: 700;
  color: #6366f1;
  font-size: 10px;
  margin-bottom: 4px;
}

.version-selector-note__content {
  color: #475569;
  font-size: 11px;
  line-height: 1.5;
}

.version-selector-list {
  display: grid;
  gap: 8px;
}

.version-selector-list__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0;
}

.version-selector-list__head h5 {
  margin: 4px 0 0;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.version-selector-nav {
  display: flex;
  gap: 4px;
}

.version-selector-nav__btn {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #fff;
  color: #334155;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 10px;
  cursor: pointer;
}

.version-selector-nav__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.version-selector-row {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(180px, 220px);
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.version-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 70px;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: #fff;
  transition: all 0.15s ease;
}

.version-card:hover {
  border-color: rgba(79, 70, 229, 0.3);
}

.version-card--selected {
  border-color: rgba(79, 70, 229, 0.4);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.1);
}

.version-card--current {
  background: rgba(238, 242, 255, 0.6);
}

.version-card__main {
  display: grid;
  gap: 4px;
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
}

.version-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.version-card__code {
  margin: 0;
  font-size: 10px;
  font-weight: 700;
  color: #4f46e5;
}

.version-card__badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.1);
  color: #64748b;
}

.version-card__excerpt {
  font-size: 10px;
  color: #64748b;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.version-card__quality-pill {
  display: inline-flex;
  align-items: center;
  min-height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  width: fit-content;
}

.version-card__quality-pill--success {
  background: rgba(22, 163, 74, 0.1);
  color: #15803d;
}

.version-card__quality-pill--warning {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.version-card__quality-pill--danger {
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
}

.version-card__quality-issues {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #94a3b8;
  font-size: 9px;
}

.version-card__actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: stretch;
}

.version-card__actions :deep(.md-btn) {
  min-height: 22px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 1.2;
}

.version-preview {
  display: grid;
  gap: 8px;
}

.version-preview__body {
  min-height: 300px;
  max-height: 500px;
  overflow: auto;
  border-radius: 6px;
  background: #f8fafc;
  padding: 12px 14px;
}

.version-preview__excerpt {
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 12px;
  color: #0f172a;
}

.version-preview__quality {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 6px;
  background: #fff;
}

.version-preview__quality--success {
  border-color: rgba(34, 197, 94, 0.2);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.9), rgba(255, 255, 255, 0.85));
}

.version-preview__quality--warning {
  border-color: rgba(245, 158, 11, 0.25);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.9), rgba(255, 255, 255, 0.85));
}

.version-preview__quality--danger {
  border-color: rgba(239, 68, 68, 0.25);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.9), rgba(255, 255, 255, 0.85));
}

.version-preview__quality strong {
  color: #0f172a;
  font-size: 11px;
  font-weight: 700;
}

.version-preview__quality p {
  margin: 2px 0 0;
  color: #64748b;
  font-size: 10px;
  line-height: 1.4;
}

.version-preview__quality ul {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  max-width: 300px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.version-preview__quality li {
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: #334155;
  font-size: 9px;
  font-weight: 600;
}

.version-preview__actions {
  display: flex;
  justify-content: space-between;
  align-items: stretch;
  gap: 8px;
}

.version-preview__tools,
.version-preview__decision {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.version-preview__tools {
  flex: 1;
  min-width: 0;
  padding: 6px 8px;
  border-radius: 6px;
  background: #f8fafc;
}

.version-preview__tools-label {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.08);
  color: #4338ca;
  font-size: 10px;
  font-weight: 700;
}

.version-preview__decision {
  justify-content: flex-end;
}

.version-preview__confirm {
  min-height: 32px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.12);
}

.version-preview__confirm-warning {
  flex-basis: 100%;
  max-width: 300px;
  margin: 0;
  color: #b91c1c;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.4;
  text-align: right;
}

@media (max-width: 900px) {
  .version-decision-panel {
    grid-template-columns: 1fr;
  }

  .version-decision-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .version-card {
    flex-basis: 200px;
    min-width: 200px;
    max-width: 200px;
  }

  .version-preview__actions {
    flex-direction: column;
  }

  .version-preview__decision {
    justify-content: flex-start;
  }

  .version-preview__body {
    min-height: 250px;
    max-height: 400px;
  }
}

@media (max-width: 560px) {
  .version-decision-metrics {
    grid-template-columns: 1fr;
  }

  .version-preview__tools,
  .version-preview__decision {
    flex-direction: column;
    align-items: stretch;
  }

  .version-preview__tools-label {
    justify-content: center;
  }
}
</style>

