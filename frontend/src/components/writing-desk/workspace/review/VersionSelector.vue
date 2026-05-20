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
  display: grid;
  gap: 12px;
}

.version-selector-head,
.version-selector-head__actions,
.version-selector-head__chips,
.version-selector-nav,
.version-card__actions,
.version-card__tags,
.version-selector-list__head,
.version-preview__top,
.version-preview__tags,
.version-preview__actions,
.progress-row {
  display: flex;
  gap: 8px;
}

.version-selector-head,
.version-selector-list__head,
.version-preview__top,
.progress-row {
  align-items: center;
  justify-content: space-between;
}

.version-selector-head,
.version-selector-progress,
.version-selector-banner,
.version-selector-note,
.version-selector-list,
.version-preview {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  padding: 12px 14px;
}

.version-selector-head h4,
.version-selector-list h5,
.version-preview h5,
.version-selector-banner h4 {
  margin: 6px 0 0;
  font-size: 0.98rem;
  font-weight: 700;
  color: #0f172a;
}

.version-selector-head p,
.version-selector-banner p,
.version-selector-note__content,
.version-preview__meta,
.version-preview__hint,
.version-card__excerpt {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.5;
  color: #475569;
}

.version-selector-head__actions,
.version-selector-head__chips,
.version-card__tags,
.version-card__actions,
.version-preview__tags,
.version-preview__actions {
  flex-wrap: wrap;
  align-items: center;
}

.version-selector-head__action {
  min-height: 40px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 0.84rem;
  font-weight: 850;
}

.version-selector-head__action--primary {
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.16);
}

.vs-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: #f8fafc;
  color: #334155;
  font-size: 0.76rem;
  font-weight: 700;
}

.vs-chip--primary {
  background: #111827;
  border-color: #111827;
  color: #fff;
}

.vs-chip--success {
  background: #ecfdf5;
  border-color: rgba(16, 185, 129, 0.26);
  color: #047857;
}

.vs-chip--accent {
  background: #eef2ff;
  border-color: rgba(99, 102, 241, 0.24);
  color: #4338ca;
}

.vs-chip--warn {
  background: #eff6ff;
  border-color: rgba(249, 115, 22, 0.24);
  color: #c2410c;
}

.version-selector-progress {
  display: grid;
  gap: 8px;
}

.version-decision-panel {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(0, 1.6fr);
  gap: 12px;
  padding: 14px;
  border-radius: 8px;
  border: 1px solid rgba(99, 102, 241, 0.16);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(245, 247, 255, 0.94));
  box-shadow: 0 18px 44px rgba(79, 70, 229, 0.08);
}

.version-decision-panel__lead {
  display: grid;
  align-content: center;
  gap: 4px;
}

.version-decision-panel__lead h5 {
  margin: 0;
  color: #0f172a;
  font-size: 1rem;
  font-weight: 900;
}

.version-decision-panel__lead p {
  margin: 0;
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.55;
}

.version-decision-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.version-decision-metric {
  display: grid;
  gap: 2px;
  min-height: 72px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.78);
}

.version-decision-metric span {
  color: #64748b;
  font-size: 0.7rem;
  font-weight: 850;
}

.version-decision-metric strong {
  color: #111827;
  font-size: 1.16rem;
  line-height: 1.1;
  font-weight: 950;
}

.version-decision-metric em {
  color: #64748b;
  font-size: 0.68rem;
  font-style: normal;
}

.version-decision-metric--success {
  border-color: rgba(34, 197, 94, 0.22);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.95), rgba(255, 255, 255, 0.82));
}

.version-decision-metric--warn {
  border-color: rgba(14, 165, 233, 0.25);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.95), rgba(255, 255, 255, 0.82));
}

.version-decision-metric--info {
  border-color: rgba(99, 102, 241, 0.2);
  background: linear-gradient(180deg, rgba(238, 242, 255, 0.96), rgba(255, 255, 255, 0.82));
}

.progress-track {
  position: relative;
  width: 100%;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.progress-bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2563eb, #38bdf8);
}

.progress-bar--phase {
  background: linear-gradient(90deg, #7c3aed, #a855f7);
}

.progress-bar--indeterminate {
  width: 40%;
  animation: loading-slide 1.2s ease-in-out infinite;
}

.version-selector-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.version-selector-banner__note {
  color: #475569;
  font-size: 0.8rem;
  font-weight: 700;
}

.version-selector-banner--error {
  background: #eff6ff;
}

.version-selector-banner--success {
  background: #eff6ff;
}

.version-selector-note__badge,
.version-selector-list__kicker,
.version-preview__kicker {
  margin-bottom: 6px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6366f1;
}

.version-selector-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 2px;
  scroll-snap-type: x proximity;
}

.version-card {
  flex: 0 0 292px;
  min-width: 292px;
  max-width: 292px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  padding: 8px 9px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94));
  scroll-snap-align: start;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.05);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.version-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 40px rgba(79, 70, 229, 0.1);
}

.version-card--selected {
  background:
    linear-gradient(180deg, #eef2ff, #ffffff);
  border-color: rgba(79, 70, 229, 0.34);
}

.version-card--current {
  box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.35);
}

.version-card__main {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.version-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.version-card__code {
  margin: 0 0 1px;
  font-size: 0.76rem;
  font-weight: 700;
  color: #4f46e5;
}

.version-card__excerpt {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  line-height: 1.38;
  font-size: 0.83rem;
}

.version-card__quality {
  display: grid;
  gap: 4px;
}

.version-card__quality-pill {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 850;
}

.version-card__quality-pill--success {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}

.version-card__quality-pill--warning {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.version-card__quality-pill--danger {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
}

.version-card__quality-issues {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #64748b;
  font-size: 0.72rem;
}

.version-card__actions {
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 4px;
  width: 96px;
}

.version-card__actions :deep(.md-btn) {
  min-height: 24px;
  padding: 0 6px;
  border-radius: 10px;
  font-size: 0.72rem;
  line-height: 1.15;
  white-space: normal;
}

.version-card__delete {
  color: #b91c1c;
}

.version-selector-nav__btn {
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #fff;
  color: #334155;
  border-radius: 999px;
  padding: 8px 12px;
  cursor: pointer;
}

.version-selector-nav__btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.version-preview {
  display: grid;
  gap: 10px;
}

.version-preview__body {
  min-height: 560px;
  max-height: 820px;
  overflow: auto;
  border-radius: 8px;
  background: #f8fafc;
  padding: 18px 20px;
}

.version-preview__excerpt {
  white-space: pre-wrap;
  line-height: 1.38;
  font-size: 0.96rem;
  color: #0f172a;
}

.version-preview__quality {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: #fff;
}

.version-preview__quality--success {
  border-color: rgba(34, 197, 94, 0.26);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.96), rgba(255, 255, 255, 0.94));
}

.version-preview__quality--warning {
  border-color: rgba(245, 158, 11, 0.28);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.96), rgba(255, 255, 255, 0.94));
}

.version-preview__quality--danger {
  border-color: rgba(239, 68, 68, 0.3);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.96), rgba(255, 255, 255, 0.94));
}

.version-preview__quality strong {
  color: #0f172a;
  font-size: 0.86rem;
  font-weight: 900;
}

.version-preview__quality p {
  margin: 4px 0 0;
  color: #475569;
  font-size: 0.78rem;
  line-height: 1.45;
}

.version-preview__quality ul {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  max-width: 420px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.version-preview__quality li {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 0.72rem;
  font-weight: 800;
}

.version-preview__actions {
  justify-content: space-between;
  align-items: stretch;
  gap: 12px;
}

.version-preview__tools,
.version-preview__decision {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.version-preview__tools {
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
}

.version-preview__tools-label {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.1);
  color: #4338ca;
  font-size: 0.74rem;
  font-weight: 800;
}

.version-preview__decision {
  justify-content: flex-end;
}

.version-preview__confirm {
  min-height: 42px;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 0.86rem;
  font-weight: 850;
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.18);
}

.version-preview__confirm-warning {
  flex-basis: 100%;
  max-width: 420px;
  margin: 0;
  color: #b91c1c;
  font-size: 0.75rem;
  font-weight: 800;
  line-height: 1.45;
  text-align: right;
}

@keyframes loading-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(280%); }
}

@media (max-width: 900px) {
  .version-decision-panel {
    grid-template-columns: 1fr;
  }

  .version-decision-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .version-card {
    flex-basis: 250px;
    min-width: 250px;
    max-width: 250px;
    grid-template-columns: minmax(0, 1fr) 88px;
  }

  .version-preview__actions {
    flex-direction: column;
  }

  .version-preview__decision {
    justify-content: flex-start;
  }

  .version-preview__body {
    min-height: 460px;
    max-height: 660px;
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
