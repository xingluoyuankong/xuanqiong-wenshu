<!-- 风格学习弹窗 - 支持我的章节与外部参考文本 -->
<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/50" @click="$emit('close')"></div>

    <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[88vh] overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-200">
        <h3 class="text-xl font-bold text-slate-900">文风学习</h3>
        <p class="text-sm text-slate-500 mt-1">既可以学习你自己的章节风格，也可以学习外部参考文本的文风</p>
      </div>

      <div class="px-6 pt-4 border-b border-slate-100 flex gap-2">
        <button
          type="button"
          class="px-4 py-2 rounded-t-xl text-sm font-medium"
          :class="mode === 'self' ? 'bg-indigo-50 text-indigo-700 border border-b-0 border-indigo-200' : 'text-slate-500'"
          @click="mode = 'self'"
        >
          我的章节
        </button>
        <button
          type="button"
          class="px-4 py-2 rounded-t-xl text-sm font-medium"
          :class="mode === 'external' ? 'bg-indigo-50 text-indigo-700 border border-b-0 border-indigo-200' : 'text-slate-500'"
          @click="mode = 'external'"
        >
          外部参考
        </button>
      </div>

      <div class="px-6 py-4 overflow-y-auto max-h-[62vh] space-y-4">
        <div v-if="loading" class="flex flex-col items-center justify-center py-12">
          <div class="animate-spin rounded-full h-12 w-12 border-4 border-indigo-500 border-t-transparent"></div>
          <p class="mt-4 text-slate-500">AI 正在分析文风...</p>
        </div>

        <template v-else>
          <div v-if="mode === 'self'" class="space-y-4">
            <div class="rounded-2xl border border-slate-200 p-4 bg-slate-50">
              <p class="text-sm text-slate-600 mb-3">请选择 2-5 个代表性章节，系统会学习你自己的写作风格。</p>

              <div v-if="availableChapters.length" class="space-y-2 max-h-[320px] overflow-y-auto">
                <div
                  v-for="ch in availableChapters"
                  :key="ch.number"
                  class="flex items-center gap-3 p-3 border-2 rounded-xl cursor-pointer transition-all"
                  :class="selectedChapters.includes(ch.number)
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-slate-200 hover:border-indigo-300'"
                  @click="toggleChapter(ch.number)"
                >
                  <div
                    class="w-6 h-6 rounded-md flex items-center justify-center border-2 transition-all"
                    :class="selectedChapters.includes(ch.number)
                      ? 'bg-indigo-500 border-indigo-500'
                      : 'border-slate-300'"
                  >
                    <svg v-if="selectedChapters.includes(ch.number)" class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                    </svg>
                  </div>
                  <div class="flex-1">
                    <p class="font-medium text-slate-900">第 {{ ch.number }} 章</p>
                    <p class="text-sm text-slate-500 truncate">{{ ch.title }}</p>
                  </div>
                  <span v-if="ch.content_length" class="text-xs text-slate-400">
                    {{ Math.round(ch.content_length / 1000) }}k 字
                  </span>
                </div>
              </div>

              <div v-else class="text-center py-8 text-slate-500">
                <p>暂无已完成的章节可供选择</p>
                <p class="text-sm mt-1">请先完成至少 2 个章节</p>
              </div>
            </div>

            <div v-if="selfStyleSummary" class="rounded-2xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-slate-700 space-y-2">
              <p class="font-medium text-indigo-700">当前项目章节文风摘要</p>
              <p v-if="selfStyleSummary.narrative">🎭 叙事：{{ selfStyleSummary.narrative }}</p>
              <p v-if="selfStyleSummary.rhythm">⚡ 节奏：{{ selfStyleSummary.rhythm }}</p>
              <p v-if="selfStyleSummary.vocabulary">📚 词汇：{{ selfStyleSummary.vocabulary }}</p>
              <p v-if="selfStyleSummary.dialogue">💬 对话：{{ selfStyleSummary.dialogue }}</p>
            </div>

            <div
              v-else-if="activeProfile"
              class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 space-y-1"
            >
              <p class="font-medium">当前启用的是外部参考文风</p>
              <p>正在使用「{{ activeProfile.name }}」，如需学习自己的章节文风，请先点击下方“学习我的文风”。</p>
            </div>
          </div>

          <div v-else class="space-y-4">
            <div class="rounded-2xl border border-slate-200 p-4 bg-slate-50 space-y-3">
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-2">参考文本名称</label>
                <input
                  v-model.trim="externalTitle"
                  type="text"
                  class="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  placeholder="例如：雪中悍刀行风格参考"
                />
              </div>
              <div class="space-y-2">
                <label class="block text-sm font-medium text-slate-700">导入类型</label>
                <div class="flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="px-3 py-2 rounded-lg text-sm border"
                    :class="externalSourceType === 'external_text' ? 'bg-indigo-50 text-indigo-700 border-indigo-300' : 'bg-white text-slate-600 border-slate-300'"
                    @click="externalSourceType = 'external_text'"
                  >
                    小说片段 / 章节
                  </button>
                  <button
                    type="button"
                    class="px-3 py-2 rounded-lg text-sm border"
                    :class="externalSourceType === 'external_novel' ? 'bg-indigo-50 text-indigo-700 border-indigo-300' : 'bg-white text-slate-600 border-slate-300'"
                    @click="externalSourceType = 'external_novel'"
                  >
                    整本小说
                  </button>
                </div>
                <p class="text-xs text-slate-500">
                  {{ externalSourceType === 'external_novel' ? '适合导入整本小说全文，建议至少 5000 字，系统会截取上限范围做整书级风格归纳。' : '适合导入单个片段、章节或若干连续章节，建议至少 500 字。' }}
                </p>
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-2">粘贴外部参考文本</label>
                <textarea
                  v-model="externalContent"
                  class="w-full min-h-[180px] rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                  :placeholder="externalPlaceholder"
                ></textarea>
              </div>
              <div class="flex flex-wrap gap-3">
                <button
                  type="button"
                  class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  :disabled="!canCreateSource"
                  @click="handleCreateSource"
                >
                  保存为参考文本
                </button>
                <button
                  type="button"
                  class="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:border-indigo-300"
                  :disabled="selectedSourceIds.length === 0"
                  @click="handleCreateProfile"
                >
                  生成文风画像
                </button>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div class="rounded-2xl border border-slate-200 p-4 space-y-3">
                <div class="flex items-center justify-between gap-2">
                  <h4 class="font-semibold text-slate-900">参考文本</h4>
                  <span class="text-xs text-slate-400">{{ sources.length }} 条</span>
                </div>
                <div v-if="sources.length" class="space-y-2 max-h-[260px] overflow-y-auto">
                  <div
                    v-for="source in sources"
                    :key="source.id"
                    class="rounded-xl border p-3"
                    :class="selectedSourceIds.includes(source.id) ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200'"
                  >
                    <label class="flex items-start gap-3 cursor-pointer">
                      <input type="checkbox" class="mt-1 accent-indigo-600" :value="source.id" v-model="selectedSourceIds" />
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center justify-between gap-2">
                          <p class="font-medium text-slate-900 truncate">{{ source.title }}</p>
                          <button type="button" class="text-xs text-rose-600 hover:text-rose-700" @click.stop="handleDeleteSource(source.id)">删除</button>
                        </div>
                        <p class="text-xs text-slate-500 mt-1">{{ source.char_count || 0 }} 字 · {{ source.source_type === 'external_novel' ? '整本小说' : '外部文本' }}</p>
                      </div>
                    </label>
                  </div>
                </div>
                <div v-else class="text-sm text-slate-500 py-8 text-center">还没有外部参考文本</div>
              </div>

              <div class="rounded-2xl border border-slate-200 p-4 space-y-3">
                <div class="flex items-center justify-between gap-2">
                  <h4 class="font-semibold text-slate-900">文风画像</h4>
                  <span v-if="activeProfile" class="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700">已激活</span>
                </div>
                <div v-if="profiles.length" class="space-y-2 max-h-[260px] overflow-y-auto">
                  <div v-for="profile in profiles" :key="profile.id" class="rounded-xl border border-slate-200 p-3 space-y-2">
                    <div class="flex items-center justify-between gap-2">
                      <div>
                        <p class="font-medium text-slate-900">{{ profile.name }}</p>
                        <p class="text-xs text-slate-500">来源 {{ profile.source_ids?.length || 0 }} 条</p>
                      </div>
                      <button
                        type="button"
                        class="px-3 py-1.5 text-xs font-medium rounded-lg"
                        :class="activeProfile?.id === profile.id ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-600 text-white hover:bg-indigo-700'"
                        @click="handleActivateProfile(profile.id)"
                      >
                        {{ activeProfile?.id === profile.id ? '当前使用中' : '设为当前文风' }}
                      </button>
                    </div>
                    <div class="text-xs text-slate-600 space-y-1">
                      <p v-if="profile.summary?.narrative">🎭 叙事：{{ profile.summary.narrative }}</p>
                      <p v-if="profile.summary?.rhythm">⚡ 节奏：{{ profile.summary.rhythm }}</p>
                      <p v-if="profile.summary?.vocabulary">📚 词汇：{{ profile.summary.vocabulary }}</p>
                      <p v-if="profile.summary?.dialogue">💬 对话：{{ profile.summary.dialogue }}</p>
                    </div>
                  </div>
                </div>
                <div v-else class="text-sm text-slate-500 py-8 text-center">还没有文风画像</div>
                <button
                  v-if="activeProfile"
                  type="button"
                  class="w-full px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:border-slate-400"
                  @click="handleClearActiveProfile"
                >
                  停用当前外部文风
                </button>
              </div>
            </div>
          </div>

          <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
            {{ error }}
          </div>
        </template>
      </div>

      <div class="px-6 py-4 border-t border-slate-200 flex justify-between items-center">
        <div class="text-xs text-slate-500">
          <span v-if="mode === 'external' && activeProfile">当前已启用外部文风：{{ activeProfile.name }}</span>
          <span v-else-if="mode === 'self'">当前模式：学习自己的章节文风</span>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800"
            @click="$emit('close')"
          >
            关闭
          </button>
          <button
            v-if="mode === 'self' && !loading"
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="selectedChapters.length < 2 || selectedChapters.length > 5"
            @click="startExtract"
          >
            学习我的文风
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NovelAPI, OptimizerAPI } from '@/api/novel'

interface ChapterInfo {
  number: number
  title: string
  content_length: number
}

function getChapterNumber(ch: any): number | null {
  if (typeof ch?.number === 'number') return ch.number
  if (typeof ch?.chapter_number === 'number') return ch.chapter_number
  return null
}

const props = defineProps<{
  show: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'extracted', summary: any): void
}>()

const mode = ref<'self' | 'external'>('self')
const loading = ref(false)
const error = ref('')
const availableChapters = ref<ChapterInfo[]>([])
const selectedChapters = ref<number[]>([])
const selfStyleSummary = ref<any>(null)
const selfStyleSourceMode = ref<string | null>(null)

const externalTitle = ref('')
const externalContent = ref('')
const externalSourceType = ref<'external_text' | 'external_novel'>('external_text')
const sources = ref<any[]>([])
const profiles = ref<any[]>([])
const selectedSourceIds = ref<string[]>([])
const activeProfile = ref<any | null>(null)

const minExternalChars = computed(() => externalSourceType.value === 'external_novel' ? 5000 : 500)
const externalPlaceholder = computed(() => externalSourceType.value === 'external_novel'
  ? '粘贴整本小说全文，建议 5000 字以上'
  : '粘贴你想学习文风的外部小说片段或章节，建议 3000 字以上')
const canCreateSource = computed(() => externalTitle.value.trim().length > 0 && externalContent.value.trim().length >= minExternalChars.value)

async function loadChapters() {
  try {
    const res = await NovelAPI.getChapters(props.projectId)
    availableChapters.value = (res.chapters || [])
      .filter((ch: any) => ch.content && ch.content.length > 500)
      .map((ch: any) => {
        const number = getChapterNumber(ch)
        return number === null ? null : {
          number,
          title: ch.title || `第 ${number} 章`,
          content_length: ch.content?.length || 0
        }
      })
      .filter((ch: ChapterInfo | null): ch is ChapterInfo => ch !== null)
      .slice(0, 10)
  } catch (e) {
    console.error('加载章节失败:', e)
    availableChapters.value = []
  }
}

function toggleChapter(num: number) {
  const idx = selectedChapters.value.indexOf(num)
  if (idx > -1) {
    selectedChapters.value.splice(idx, 1)
  } else if (selectedChapters.value.length < 5) {
    selectedChapters.value.push(num)
  }
}

async function loadStyleSummary() {
  try {
    const res = await OptimizerAPI.getProjectStyle(props.projectId)
    selfStyleSourceMode.value = res.source?.mode || null
    selfStyleSummary.value = res.source?.mode === 'project_chapters' ? (res.summary || null) : null
  } catch (e) {
    console.error('加载项目文风失败:', e)
    selfStyleSummary.value = null
    selfStyleSourceMode.value = null
  }
}

async function loadExternalData() {
  try {
    const [sourcesRes, profilesRes, activeRes] = await Promise.all([
      OptimizerAPI.listStyleSources(props.projectId),
      OptimizerAPI.listStyleProfiles(props.projectId),
      OptimizerAPI.getActiveStyleProfile(props.projectId),
    ])
    sources.value = sourcesRes.sources || []
    profiles.value = profilesRes.profiles || []
    activeProfile.value = activeRes.profile || null
  } catch (e) {
    console.error('加载外部文风数据失败:', e)
  }
}

async function startExtract() {
  if (selectedChapters.value.length < 2) {
    error.value = '请至少选择 2 个章节'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const res = await OptimizerAPI.extractStyle(props.projectId, selectedChapters.value)
    selfStyleSourceMode.value = 'project_chapters'
    selfStyleSummary.value = res.style_summary?.summary || res.style_summary
    emit('extracted', selfStyleSummary.value)
  } catch (e: any) {
    error.value = e.message || '提取失败，请重试'
    console.error('风格提取失败:', e)
  } finally {
    loading.value = false
  }
}

async function handleCreateSource() {
  loading.value = true
  error.value = ''
  try {
    const res = await OptimizerAPI.createStyleSource(props.projectId, {
      title: externalTitle.value,
      content_text: externalContent.value,
      source_type: externalSourceType.value
    })
    sources.value.unshift(res.source)
    selectedSourceIds.value = [res.source.id]
    externalContent.value = ''
    if (!externalTitle.value.trim()) {
      externalTitle.value = res.source.title || ''
    }
  } catch (e: any) {
    error.value = e.message || '保存参考文本失败'
  } finally {
    loading.value = false
  }
}

async function handleDeleteSource(sourceId: string) {
  loading.value = true
  error.value = ''
  try {
    await OptimizerAPI.deleteStyleSource(props.projectId, sourceId)
    sources.value = sources.value.filter((item) => item.id !== sourceId)
    selectedSourceIds.value = selectedSourceIds.value.filter((id) => id !== sourceId)
  } catch (e: any) {
    error.value = e.message || '删除参考文本失败'
  } finally {
    loading.value = false
  }
}

async function handleCreateProfile() {
  loading.value = true
  error.value = ''
  try {
    const res = await OptimizerAPI.createStyleProfile(props.projectId, {
      source_ids: selectedSourceIds.value,
      name: externalTitle.value.trim() || undefined,
    })
    profiles.value.unshift(res.profile)
    await handleActivateProfile(res.profile.id)
    emit('extracted', res.profile.summary || null)
  } catch (e: any) {
    error.value = e.message || '生成文风画像失败'
  } finally {
    loading.value = false
  }
}

async function handleActivateProfile(profileId: string) {
  loading.value = true
  error.value = ''
  try {
    const res = await OptimizerAPI.activateStyleProfile(props.projectId, profileId, 'project')
    activeProfile.value = res.profile
    profiles.value = profiles.value.map((item) => ({ ...item, active: item.id === profileId }))
    emit('extracted', res.profile.summary || null)
  } catch (e: any) {
    error.value = e.message || '激活文风画像失败'
  } finally {
    loading.value = false
  }
}

async function handleClearActiveProfile() {
  loading.value = true
  error.value = ''
  try {
    await OptimizerAPI.clearActiveStyleProfile(props.projectId)
    const [styleRes, activeRes, profilesRes] = await Promise.all([
      OptimizerAPI.getProjectStyle(props.projectId),
      OptimizerAPI.getActiveStyleProfile(props.projectId),
      OptimizerAPI.listStyleProfiles(props.projectId),
    ])

    activeProfile.value = activeRes.profile || null
    profiles.value = profilesRes.profiles || []
    selfStyleSourceMode.value = styleRes.source?.mode || null
    selfStyleSummary.value = styleRes.source?.mode === 'project_chapters' ? (styleRes.summary || null) : null
    emit('extracted', selfStyleSummary.value)
  } catch (e: any) {
    error.value = e.message || '停用失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.show, async (newVal) => {
  if (!newVal) return
  error.value = ''
  selectedChapters.value = []
  selectedSourceIds.value = []
  await Promise.all([
    loadChapters(),
    loadStyleSummary(),
    loadExternalData(),
  ])
})
</script>
