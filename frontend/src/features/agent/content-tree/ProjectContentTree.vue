<template>
  <XqPanel title="项目内容树" subtitle="仅加载章节元数据；点击章节后再按需读取版本预览。" data-testid="agent-project-content-tree">
    <p v-if="loading" class="muted" data-testid="agent-content-tree-loading">正在加载项目章节目录…</p>
    <p v-else-if="error" class="error" data-testid="agent-content-tree-error">{{ error }}</p>
    <p v-else-if="!volumes.length" class="muted" data-testid="agent-content-tree-empty">当前项目还没有可展示的章节目录。</p>

    <ol v-else class="content-volume-list" data-testid="agent-content-volume-list">
      <li v-for="volume in volumes" :key="volume.id" class="content-volume">
        <strong>{{ volume.label }}</strong>
        <ol class="content-chapter-list">
          <li v-for="chapter in volume.chapters" :key="chapter.chapterNumber">
            <button
              type="button"
              class="content-chapter-button"
              :class="{ selected: chapter.chapterNumber === selectedChapterNumber }"
              :data-testid="`agent-content-chapter-${chapter.chapterNumber}`"
              @click="$emit('select-chapter', chapter.chapterNumber)"
            >
              <b>第 {{ chapter.chapterNumber }} 章 · {{ chapter.title }}</b>
              <span>{{ chapter.generationStatus }}<template v-if="chapter.wordCount !== undefined"> · {{ chapter.wordCount }} 字</template></span>
              <small>{{ chapter.summary || '暂无章节摘要' }}</small>
            </button>
          </li>
        </ol>
      </li>
    </ol>

    <section v-if="selectedChapterNumber" class="content-preview" data-testid="agent-content-preview">
      <header>
        <div><strong>{{ selectedChapter?.title || `第 ${selectedChapterNumber} 章` }}</strong><small>{{ loadingChapter ? '正在加载章节详情…' : selectedChapter?.summary || '仅在点击章节后读取详情。' }}</small></div>
        <XqButton size="sm" variant="secondary" :disabled="!selectedChapter" data-testid="agent-content-open-writing-desk" @click="$emit('open-writing-desk')">在写作台完整查看</XqButton>
      </header>
      <p v-if="loadingChapter" class="muted">正在加载版本列表与正文预览…</p>
      <template v-else-if="selectedChapter">
        <div v-if="versions.length" class="content-version-list" data-testid="agent-content-version-list">
          <button
            v-for="(version, index) in versions"
            :key="versionKey(version, index)"
            type="button"
            :class="{ selected: versionId(version) === selectedVersionId }"
            :data-testid="`agent-content-version-${versionId(version) || index}`"
            @click="selectVersion(version)"
          >
            {{ versionLabel(version, index) }}
          </button>
        </div>
        <pre v-if="previewText" class="content-preview-text" data-testid="agent-content-preview-text">{{ previewText }}</pre>
        <p v-else class="muted">当前版本没有可展示的正文预览。</p>
      </template>
    </section>
  </XqPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { Chapter, ChapterVersion } from '@/api/novel'
import { XqButton, XqPanel } from '@/shared/ui'
import type { AgentContentVolume } from './types'

const props = withDefaults(defineProps<{
  volumes: AgentContentVolume[]
  selectedChapterNumber?: number
  selectedVersionId?: number
  selectedChapter?: Chapter | null
  selectedVersion?: ChapterVersion | null
  loading?: boolean
  loadingChapter?: boolean
  error?: string
  previewLimit?: number
}>(), {
  selectedChapter: null,
  selectedVersion: null,
  loading: false,
  loadingChapter: false,
  error: '',
  previewLimit: 1600,
})

const emit = defineEmits<{
  (event: 'select-chapter', chapterNumber: number): void
  (event: 'select-version', versionId: number): void
  (event: 'open-writing-desk'): void
}>()

const versions = computed(() => Array.isArray(props.selectedChapter?.versions) ? props.selectedChapter!.versions : [])
const versionId = (version: ChapterVersion): number | undefined => typeof version.id === 'number' && Number.isInteger(version.id) && version.id >= 1 ? version.id : undefined
const versionKey = (version: ChapterVersion, index: number): string => String(versionId(version) || `index-${index}`)
const versionLabel = (version: ChapterVersion, index: number): string => {
  const id = versionId(version)
  return id ? `版本 ${id}${id === props.selectedChapter?.selected_version_id ? ' · 已选中' : ''}` : `版本 ${index + 1}`
}
const selectVersion = (version: ChapterVersion) => {
  const id = versionId(version)
  if (id) emit('select-version', id)
}
const previewText = computed(() => {
  const raw = props.selectedVersion?.content ?? props.selectedChapter?.content
  if (typeof raw !== 'string' || !raw.trim()) return ''
  const limit = Math.max(200, props.previewLimit)
  const normalized = raw.replace(/\u0000/g, '')
  return normalized.length > limit ? `${normalized.slice(0, limit)}\n\n[预览已截断，完整内容请在写作台查看]` : normalized
})
</script>

<style scoped>
.content-volume-list,.content-chapter-list,.content-version-list{display:grid;gap:.5rem;margin:0;padding:0;list-style:none}.content-volume{display:grid;gap:.45rem;padding:.55rem;border:1px solid var(--xq-border);border-radius:.6rem;background:rgba(255,255,255,.48)}.content-chapter-button{display:grid;gap:.18rem;width:100%;text-align:left;border:1px solid transparent;border-radius:.5rem;padding:.55rem;background:rgba(255,255,255,.68);font:inherit;cursor:pointer}.content-chapter-button:hover,.content-chapter-button.selected{border-color:var(--xq-jade);background:rgba(61,143,125,.08)}.content-chapter-button span,.content-chapter-button small,.content-preview small{color:var(--xq-ink-muted);line-height:1.45}.content-preview{display:grid;gap:.65rem;margin-top:.8rem;padding-top:.8rem;border-top:1px dashed var(--xq-border)}.content-preview header{display:flex;align-items:start;justify-content:space-between;gap:.7rem}.content-preview header>div{display:grid;gap:.2rem}.content-version-list{display:flex;flex-wrap:wrap}.content-version-list button{border:1px solid var(--xq-border);border-radius:999px;padding:.28rem .55rem;background:rgba(255,255,255,.7);font:inherit;cursor:pointer}.content-version-list button.selected{border-color:var(--xq-jade);color:var(--xq-jade)}.content-preview-text{max-height:18rem;overflow:auto;margin:0;padding:.7rem;border-radius:.55rem;background:rgba(15,23,42,.05);white-space:pre-wrap;line-height:1.65;font:inherit}.muted{color:var(--xq-ink-muted)}.error{color:var(--xq-cinnabar)}@media(max-width:560px){.content-preview header{align-items:stretch;flex-direction:column}}
</style>
