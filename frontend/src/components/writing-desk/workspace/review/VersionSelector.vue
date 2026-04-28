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
          type="button"
          class="md-btn md-btn-tonal md-ripple"
          :disabled="evaluatingChapter === selectedChapter?.chapter_number"
          @click="emit('evaluateAllVersions')"
        >
          {{ evaluatingChapter === selectedChapter?.chapter_number ? 'AI 评审中…' : 'AI 评审全部版本' }}
        </button>
        <button
          v-if="selectedChapter?.evaluation"
          type="button"
          class="md-btn md-btn-text md-ripple"
          @click="emit('showEvaluationDetail')"
        >
          查看综合评审
        </button>
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
              : '建议先看综合评审，再决定最终确认哪一个候选版本。'
          }}
        </p>
      </div>
      <button
        type="button"
        class="md-btn md-btn-filled md-ripple"
        :disabled="isEvaluationFailed && evaluatingChapter === selectedChapter?.chapter_number"
        @click="isEvaluationFailed ? emit('evaluateAllVersions') : emit('showEvaluationDetail')"
      >
        {{ isEvaluationFailed ? '重新发起评审' : '查看综合评审' }}
      </button>
    </section>

    <section v-if="chapterGenerationResult?.ai_message" class="version-selector-note">
      <div class="version-selector-note__badge">本轮生成说明</div>
      <div class="version-selector-note__content" v-html="parseMarkdown(chapterGenerationResult.ai_message)"></div>
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
          v-for="(version, index) in availableVersions"
          :key="index"
          :class="['version-card', selectedVersionIndex === index ? 'version-card--selected' : '', isCurrentVersion(index) ? 'version-card--current' : '']"
        >
          <button
            type="button"
            class="version-card__main"
            :aria-pressed="selectedVersionIndex === index"
            @click="selectVersionIndex(index)"
          >
            <div class="version-card__head">
              <div>
                <p class="version-card__code">候选版本 {{ index + 1 }}</p>
                <strong>{{ version.style || '标准版本' }}</strong>
              </div>
              <div class="version-card__tags">
                <span class="vs-chip">约 {{ Math.max(1, Math.round(cleanVersionContent(version.content).length / 100)) * 100 }} 字</span>
                <span v-if="isCurrentVersion(index)" class="vs-chip vs-chip--success">当前正文</span>
                <span v-else-if="selectedVersionIndex === index" class="vs-chip vs-chip--accent">当前查看</span>
                <span v-if="compareVersionIndex === index" class="vs-chip vs-chip--warn">对比对象</span>
              </div>
            </div>
            <p class="version-card__excerpt">{{ getVersionPreview(version.content) }}</p>
          </button>

          <div class="version-card__actions">
            <button
              type="button"
              class="md-btn md-btn-text md-ripple"
              :disabled="evaluatingVersionIndex === index"
              @click.stop="version.evaluation ? emit('showEvaluationDetail', index) : emit('evaluateVersion', index)"
            >
              {{ evaluatingVersionIndex === index ? '评审中…' : version.evaluation ? `查看版本 ${index + 1} 评审` : `AI 评审版本 ${index + 1}` }}
            </button>
            <button type="button" class="md-btn md-btn-text md-ripple" @click.stop="setCompareVersion(index)">
              {{ compareVersionIndex === index ? '取消对比' : `设为对比版本 ${index + 1}` }}
            </button>
            <button type="button" class="md-btn md-btn-text md-ripple" :disabled="!version.content" @click.stop="openVersionReader(index)">查看全文</button>
            <button
              v-if="!isCurrentVersion(index) && availableVersions.length > 1"
              type="button"
              class="md-btn md-btn-text md-ripple version-card__delete"
              :disabled="deletingVersionIndex === index"
              @click.stop="handleDeleteVersion(index)"
            >
              {{ deletingVersionIndex === index ? '删除中…' : '删除' }}
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
        <div class="version-preview__excerpt">{{ selectedVersionPreview }}</div>
        <p v-if="previewHintVisible" class="version-preview__hint">这里只保留预览摘要，点击“查看全文”会跳到完整阅读页。</p>
      </div>

      <div class="version-preview__actions">
        <button type="button" class="md-btn md-btn-text md-ripple" :disabled="!activeVersion?.content" @click="openVersionReader(selectedVersionIndex)">查看全文</button>
        <button
          type="button"
          class="md-btn md-btn-outlined md-ripple"
          :disabled="compareVersionIndex === null || compareVersionIndex === undefined || !activeVersion?.content"
          @click="openVersionDiff"
        >
          对比候选版本
        </button>
        <button type="button" class="md-btn md-btn-outlined md-ripple" :disabled="!activeVersion?.content" @click="emit('optimizeVersion', selectedVersionIndex)">优化当前预览</button>
        <button
          type="button"
          class="md-btn md-btn-filled md-ripple"
          :disabled="!activeVersion?.content || isCurrentVersion(selectedVersionIndex) || isSelectingVersion"
          @click="emit('confirmVersionSelection')"
        >
          {{ isSelectingVersion ? '确认中…' : isCurrentVersion(selectedVersionIndex) ? '当前正文已选中' : `确认候选版本 ${selectedVersionIndex + 1}` }}
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { Chapter, ChapterGenerationResponse, ChapterVersion } from '@/api/novel'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import { buildChapterPreview, normalizeChapterContent } from '@/utils/chapterContent'

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
const activeVersion = computed(() => props.availableVersions?.[props.selectedVersionIndex] || null)
const selectedVersionContent = computed(() => normalizeChapterContent(activeVersion.value?.content || ''))
const selectedVersionPreview = computed(() => buildChapterPreview(activeVersion.value?.content || '', 1400))
const previewHintVisible = computed(() => selectedVersionContent.value.length > selectedVersionPreview.value.length + 40)
const hasConfirmedSelection = computed(() => props.selectedChapter?.generation_status === 'successful')
const hasPrevVersion = computed(() => props.selectedVersionIndex > 0)
const hasNextVersion = computed(() => props.selectedVersionIndex < props.availableVersions.length - 1)

const cleanVersionContent = (content: string) => normalizeChapterContent(content)
const getVersionPreview = (content: unknown) => buildChapterPreview(content, 280)
const parseMarkdown = (text: string): string => renderSafeMarkdown(text)

const isCurrentVersion = (versionIndex: number) => {
  if (!hasConfirmedSelection.value) return false
  if (!props.selectedChapter?.content || !props.availableVersions?.[versionIndex]?.content) return false
  return normalizeChapterContent(props.selectedChapter.content) === normalizeChapterContent(props.availableVersions[versionIndex].content)
}

const scrollCardIntoView = async (index: number) => {
  await nextTick()
  const container = cardRowRef.value
  const card = container?.children?.[index] as HTMLElement | undefined
  card?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
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
  border-radius: 18px;
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
  background: #fff7ed;
  border-color: rgba(249, 115, 22, 0.24);
  color: #c2410c;
}

.version-selector-progress {
  display: grid;
  gap: 8px;
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

.version-selector-banner--error {
  background: #fff7ed;
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
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #f8fafc;
  scroll-snap-align: start;
}

.version-card--selected {
  background: #eef2ff;
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
  border-radius: 16px;
  background: #f8fafc;
  padding: 18px 20px;
}

.version-preview__excerpt {
  white-space: pre-wrap;
  line-height: 1.38;
  font-size: 0.96rem;
  color: #0f172a;
}

.version-preview__actions {
  justify-content: flex-end;
}

@keyframes loading-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(280%); }
}

@media (max-width: 900px) {
  .version-card {
    flex-basis: 250px;
    min-width: 250px;
    max-width: 250px;
    grid-template-columns: minmax(0, 1fr) 88px;
  }

  .version-preview__body {
    min-height: 460px;
    max-height: 660px;
  }
}
</style>
