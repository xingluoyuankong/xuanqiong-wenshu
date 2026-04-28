<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="$emit('close')">
      <TransitionChild
        as="template"
        enter="ease-out duration-300"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-200"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0" style="background-color: rgba(0, 0, 0, 0.32);" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <TransitionChild
            as="template"
            enter="ease-out duration-300"
            enter-from="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            enter-to="opacity-100 translate-y-0 sm:scale-100"
            leave="ease-in duration-200"
            leave-from="opacity-100 translate-y-0 sm:scale-100"
            leave-to="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
          >
            <DialogPanel class="md-dialog m3-generate-dialog flex flex-col text-left transition-all sm:my-6 sm:w-full sm:max-w-4xl">
              <div class="flex-1 min-h-0 overflow-y-auto px-5 pt-6 pb-5 sm:px-6 sm:pt-6 sm:pb-5">
                <div class="flex items-center gap-3 mb-5">
                  <div class="flex h-11 w-11 items-center justify-center rounded-full" style="background-color: var(--md-primary-container);">
                    <svg class="h-6 w-6" style="color: var(--md-on-primary-container);" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m6-6H6" />
                    </svg>
                  </div>
                  <div>
                    <DialogTitle as="h3" class="md-headline-small font-semibold leading-7">
                      生成第 {{ chapterNumber ?? '-' }} 章
                    </DialogTitle>
                    <p class="md-body-small md-on-surface-variant mt-1">
                      可指定章节方向、质量偏好与字数约束（最低 1200 字）。
                    </p>
                  </div>
                </div>

                <div class="grid grid-cols-1 gap-4">
                  <div>
                    <div class="flex items-center justify-between mb-2">
                      <label class="md-text-field-label">章节方向 / 写作指令（可选）</label>
                      <button type="button" class="text-xs text-gray-500 hover:text-gray-700" @click="writingNotes = ''">清空</button>
                    </div>
                    <textarea
                      v-model="writingNotes"
                      class="md-textarea w-full mt-2 min-h-[96px]"
                      placeholder="例如：本章推进主线冲突，角色必须做高风险选择，章尾埋钩子。"
                    />
                    <div class="mt-3 flex flex-wrap gap-2 max-h-32 overflow-y-auto pr-1">
                      <button
                        v-for="preset in writingDirectionPresets"
                        :key="preset"
                        type="button"
                        class="md-btn md-btn-outlined md-ripple text-xs"
                        @click="appendWritingPreset(preset)"
                      >
                        {{ preset }}
                      </button>
                    </div>
                  </div>

                  <div>
                    <div class="flex items-center justify-between mb-2">
                      <label class="md-text-field-label">质量偏好（可选）</label>
                      <button type="button" class="text-xs text-gray-500 hover:text-gray-700" @click="qualityRequirements = ''">清空</button>
                    </div>
                    <textarea
                      v-model="qualityRequirements"
                      class="md-textarea w-full mt-2 min-h-[96px]"
                      placeholder="例如：冲突更强、反转更自然、对白更有张力、环境描写更有画面感。"
                    />
                    <div class="mt-3 flex flex-wrap gap-2 max-h-32 overflow-y-auto pr-1">
                      <button
                        v-for="preset in qualityPresets"
                        :key="preset"
                        type="button"
                        class="md-btn md-btn-outlined md-ripple text-xs"
                        @click="appendQualityPreset(preset)"
                      >
                        {{ preset }}
                      </button>
                    </div>
                  </div>
                </div>

                <div class="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label class="md-text-field-label">最低字数（强约束目标）</label>
                    <input
                      v-model.number="minWordCount"
                      type="number"
                      min="1200"
                      step="100"
                      class="md-text-field-input w-full mt-2"
                      @blur="normalizeWordCounts('min')"
                    >
                  </div>
                  <div>
                    <label class="md-text-field-label">目标字数（建议）</label>
                    <input
                      v-model.number="targetWordCount"
                      type="number"
                      :min="targetWordCountMin"
                      step="100"
                      class="md-text-field-input w-full mt-2"
                      @blur="normalizeWordCounts('target')"
                    >
                  </div>
                </div>

                <!-- 字数配置保存 -->
                <div class="mt-4 flex flex-wrap items-center gap-3">
                   <button
                     type="button"
                     class="md-btn md-btn-outlined md-ripple text-sm"
                     @click="handleSaveChapterConfig"
                   >
                     保存为本章配置
                   </button>
                   <button
                     type="button"
                     class="md-btn md-btn-outlined md-ripple text-sm"
                     @click="handleSaveGlobalConfig"
                   >
                     保存为全局默认
                   </button>
                   <span v-if="saveConfigMessage" class="text-sm" :class="saveConfigSuccess ? 'text-green-600' : 'text-red-500'">
                     {{ saveConfigMessage }}
                   </span>
                   <span v-else-if="loadedConfigSourceLabel" class="text-sm text-gray-500">
                     已加载{{ loadedConfigSourceLabel }}
                   </span>
                 </div>
                <p class="mt-2 text-xs text-gray-500">
                  本章配置仅作用于当前项目当前章节；全局默认仅保存在当前浏览器。
                </p>
              </div>

              <div class="shrink-0 border-t px-6 py-4 sm:flex sm:flex-row-reverse sm:px-8" style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);">
                <button
                  type="button"
                  class="md-btn md-btn-filled md-ripple sm:ml-3 sm:w-auto w-full justify-center"
                  @click="handleGenerate"
                >
                  生成章节
                </button>
                <button
                  type="button"
                  class="md-btn md-btn-outlined md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3"
                  @click="$emit('close')"
                >
                  取消
                </button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'

interface Props {
  show: boolean
  projectId?: string
  chapterNumber: number | null
  initialWritingNotes?: string
  initialQualityRequirements?: string
  initialMinWordCount?: number
  initialTargetWordCount?: number
}

interface GenerateChapterPayload {
  chapterNumber: number
  writingNotes?: string
  qualityRequirements?: string
  minWordCount: number
  targetWordCount: number
}

const GLOBAL_GENERATION_STORAGE_KEY = 'xuanqiong_wenshu:chapter_generation:global'
const LEGACY_WORD_COUNT_STORAGE_KEY = 'xuanqiong_wenshu_word_count_config'
const LEGACY_WRITING_PREFERENCES_STORAGE_KEY = 'xuanqiong_wenshu_writing_preferences'

interface ChapterGenerationConfig {
  writingNotes: string
  qualityRequirements: string
  minWordCount: number
  targetWordCount: number
}

const DEFAULT_MIN_WORD_COUNT = 2400
const DEFAULT_TARGET_WORD_COUNT = 3200

const getChapterGenerationStorageKey = (projectId?: string, chapterNumber?: number | null) => {
  if (!projectId || !chapterNumber) return null
  return `xuanqiong_wenshu:chapter_generation:${projectId}:${chapterNumber}`
}

const normalizePersistedConfig = (value: unknown): ChapterGenerationConfig | null => {
  if (!value || typeof value !== 'object') return null
  const parsed = value as Partial<ChapterGenerationConfig>
  const minWordCount = Math.max(1200, Number(parsed.minWordCount) || DEFAULT_MIN_WORD_COUNT)
  const targetWordCount = Math.max(minWordCount, Number(parsed.targetWordCount) || DEFAULT_TARGET_WORD_COUNT)
  return {
    writingNotes: String(parsed.writingNotes || ''),
    qualityRequirements: String(parsed.qualityRequirements || ''),
    minWordCount,
    targetWordCount
  }
}

const loadConfigFromStorage = (key: string | null): ChapterGenerationConfig | null => {
  if (!key) return null
  try {
    const saved = localStorage.getItem(key)
    if (!saved) return null
    return normalizePersistedConfig(JSON.parse(saved))
  } catch {
    return null
  }
}

const saveConfigToStorage = (key: string | null, config: ChapterGenerationConfig) => {
  if (!key) return false
  try {
    localStorage.setItem(key, JSON.stringify(config))
    return true
  } catch {
    return false
  }
}

const loadLegacyConfig = (): ChapterGenerationConfig | null => {
  try {
    const savedPreferences = localStorage.getItem(LEGACY_WRITING_PREFERENCES_STORAGE_KEY)
    if (savedPreferences) {
      return normalizePersistedConfig(JSON.parse(savedPreferences))
    }
    const savedWordCount = localStorage.getItem(LEGACY_WORD_COUNT_STORAGE_KEY)
    if (savedWordCount) {
      return normalizePersistedConfig(JSON.parse(savedWordCount))
    }
  } catch {
    return null
  }
  return null
}

const clearLegacyConfig = () => {
  try {
    localStorage.removeItem(LEGACY_WORD_COUNT_STORAGE_KEY)
    localStorage.removeItem(LEGACY_WRITING_PREFERENCES_STORAGE_KEY)
  } catch {
    // Ignore storage errors
  }
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'generate', payload: GenerateChapterPayload): void
}>()

const writingNotes = ref('')
const qualityRequirements = ref('')
const minWordCount = ref<number | null>(DEFAULT_MIN_WORD_COUNT)
const targetWordCount = ref<number | null>(DEFAULT_TARGET_WORD_COUNT)
const targetWordCountMin = computed(() => minWordCount.value ?? DEFAULT_MIN_WORD_COUNT)

// UI state for save config
const hasSavedConfig = ref(false)
const loadedConfigSourceLabel = ref('')
const saveConfigMessage = ref('')
const saveConfigSuccess = ref(true)

const writingDirectionPresets = [
  '开篇即冲突',
  '主角必须做艰难选择',
  '推进主线谜团',
  '制造强烈反差',
  '埋下新伏笔',
  '回收旧伏笔',
  '强化角色关系拉扯',
  '升级外部危机',
  '突出世界规则代价',
  '让反派更立体',
  '增加战术博弈感',
  '以情绪爆点收束',
  '章尾留下强钩子',
  '通过对话推进剧情',
  '细节暗示后续反转',
  '增加误导线索',
  '增加信息差推进',
  '小胜后立刻反噬',
  '阶段目标先达成再崩塌',
  '主角秘密被逼近',
  '配角主动推动剧情',
  '阵营冲突升级',
  '情感线与主线交叉爆发',
  '制造身份错位危机',
  '本章结尾必须留悬念',
  '主角在本章犯下代价',
  '让关键配角逆袭抢戏',
  '制造价值观冲突对撞',
  '压缩铺垫，直接见刀锋',
  '在结尾抛出新问题而非新答案',
  '强化主角短板暴露',
  '加入一次失败的尝试',
  '增加压迫性的时间限制',
  '信息揭露分三段递进',
]

const qualityPresets = [
  '冲突更强',
  '钩子更狠',
  '情绪更细腻',
  '反转更自然',
  '对白更有张力',
  '节奏更紧凑',
  '画面感更强',
  '细节更真实',
  '人物动机更清晰',
  '角色弧光更明显',
  '悬念密度更高',
  '叙事更连贯',
  '张弛更有层次',
  '信息密度更高',
  '文风更有辨识度',
  '情节推进更果断',
  '伏笔与回收更闭环',
  '心理描写更深入',
  '场景调度更清楚',
  '行动逻辑更清晰',
  '章节开头吸引力更高',
  '章节结尾留白更强',
  '视角控制更稳定',
  '避免口水化叙述',
  '避免机械重复表达',
  '句式更有变化',
  '比喻更克制更准确',
  '细节服务情节推进',
  '减少解释性旁白',
  '人物说话更贴合身份',
  '场景切换更自然',
  '高潮段落更有爆发力',
  '低潮段落更有余韵',
  '叙述更具电影感',
  '关键词回环更明显',
]

const normalizeWordCounts = (source: 'min' | 'target' = 'target') => {
  const normalizedMin = Math.max(1200, Number(minWordCount.value) || DEFAULT_MIN_WORD_COUNT)
  let normalizedTarget = Number(targetWordCount.value) || Math.max(normalizedMin, DEFAULT_TARGET_WORD_COUNT)

  if (normalizedTarget < normalizedMin) {
    normalizedTarget = normalizedMin
  }

  minWordCount.value = normalizedMin
  targetWordCount.value = source === 'min'
    ? Math.max(normalizedTarget, normalizedMin)
    : normalizedTarget
}

const buildCurrentConfig = (): ChapterGenerationConfig => {
  const minValue = Math.max(1200, Number(minWordCount.value) || DEFAULT_MIN_WORD_COUNT)
  const targetValue = Math.max(minValue, Number(targetWordCount.value) || DEFAULT_TARGET_WORD_COUNT)
  return {
    writingNotes: writingNotes.value.trim(),
    qualityRequirements: qualityRequirements.value.trim(),
    minWordCount: minValue,
    targetWordCount: targetValue
  }
}

const resolveInitialConfig = (): { config: ChapterGenerationConfig; source: string } => {
  const chapterConfig = loadConfigFromStorage(getChapterGenerationStorageKey(props.projectId, props.chapterNumber))
  if (chapterConfig) {
    return { config: chapterConfig, source: '本章配置' }
  }

  const globalConfig = loadConfigFromStorage(GLOBAL_GENERATION_STORAGE_KEY)
  if (globalConfig) {
    return { config: globalConfig, source: '全局默认配置' }
  }

  const legacyConfig = loadLegacyConfig()
  if (legacyConfig) {
    saveConfigToStorage(GLOBAL_GENERATION_STORAGE_KEY, legacyConfig)
    clearLegacyConfig()
    return { config: legacyConfig, source: '历史全局配置' }
  }

  return {
    config: {
      writingNotes: '',
      qualityRequirements: '',
      minWordCount: Math.max(1200, Number(props.initialMinWordCount) || DEFAULT_MIN_WORD_COUNT),
      targetWordCount: Math.max(
        Math.max(1200, Number(props.initialMinWordCount) || DEFAULT_MIN_WORD_COUNT),
        Number(props.initialTargetWordCount) || DEFAULT_TARGET_WORD_COUNT
      )
    },
    source: ''
  }
}

const applyInitialValues = () => {
  const { config, source } = resolveInitialConfig()
  const hasPersistedConfig = Boolean(source)

  const initialWritingNotes = props.initialWritingNotes?.trim()
  const initialQualityRequirements = props.initialQualityRequirements?.trim()
  const initialMinWordCount = Math.max(1200, Number(props.initialMinWordCount) || 0)
  const initialTargetWordCount = Math.max(initialMinWordCount || 1200, Number(props.initialTargetWordCount) || 0)

  writingNotes.value = initialWritingNotes || config.writingNotes || ''
  qualityRequirements.value = initialQualityRequirements || config.qualityRequirements || ''

  if (hasPersistedConfig) {
    minWordCount.value = config.minWordCount
    targetWordCount.value = config.targetWordCount
  } else {
    minWordCount.value = initialMinWordCount || config.minWordCount
    targetWordCount.value = initialTargetWordCount || config.targetWordCount
  }

  hasSavedConfig.value = hasPersistedConfig
  loadedConfigSourceLabel.value = source ? `${source}（浏览器本地）` : ''
  saveConfigMessage.value = ''
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      applyInitialValues()
    }
  }
)

const appendPreset = (target: typeof writingNotes, preset: string) => {
  const current = target.value.trim()
  if (!current) {
    target.value = preset
    return
  }
  if (!current.includes(preset)) {
    target.value = `${current}；${preset}`
  }
}

const appendWritingPreset = (preset: string) => appendPreset(writingNotes, preset)
const appendQualityPreset = (preset: string) => appendPreset(qualityRequirements, preset)

const finishSaveMessage = (scopeLabel: string, config: ChapterGenerationConfig) => {
  hasSavedConfig.value = true
  loadedConfigSourceLabel.value = `${scopeLabel}（浏览器本地）`
  saveConfigSuccess.value = true
  const savedNotes = config.writingNotes ? '已保存写作指令' : '未填写写作指令'
  const savedQuality = config.qualityRequirements ? '已保存质量偏好' : '未填写质量偏好'
  saveConfigMessage.value = `${scopeLabel}已保存：${savedNotes}，${savedQuality}，最低${config.minWordCount}字，目标${config.targetWordCount}字`
  setTimeout(() => {
    saveConfigMessage.value = ''
  }, 3000)
}

const handleSaveChapterConfig = () => {
  normalizeWordCounts('target')
  const chapterStorageKey = getChapterGenerationStorageKey(props.projectId, props.chapterNumber)
  const config = buildCurrentConfig()
  minWordCount.value = config.minWordCount
  targetWordCount.value = config.targetWordCount

  if (!chapterStorageKey || !saveConfigToStorage(chapterStorageKey, config)) {
    saveConfigSuccess.value = false
    saveConfigMessage.value = '保存本章配置失败，请稍后重试。'
    return
  }

  finishSaveMessage('本章配置', config)
}

const handleSaveGlobalConfig = () => {
  normalizeWordCounts('target')
  const config = buildCurrentConfig()
  minWordCount.value = config.minWordCount
  targetWordCount.value = config.targetWordCount

  if (!saveConfigToStorage(GLOBAL_GENERATION_STORAGE_KEY, config)) {
    saveConfigSuccess.value = false
    saveConfigMessage.value = '保存全局默认失败，请稍后重试。'
    return
  }

  finishSaveMessage('全局默认配置', config)
}

const handleGenerate = () => {
  if (!props.chapterNumber) {
    return
  }

  normalizeWordCounts('target')

  const minValue = Math.max(1200, Number(minWordCount.value) || DEFAULT_MIN_WORD_COUNT)
  const targetValue = Math.max(minValue, Number(targetWordCount.value) || minValue)

  emit('generate', {
    chapterNumber: props.chapterNumber,
    writingNotes: writingNotes.value.trim() || undefined,
    qualityRequirements: qualityRequirements.value.trim() || undefined,
    minWordCount: minValue,
    targetWordCount: targetValue
  })
  emit('close')
}
</script>

<style scoped>
.m3-generate-dialog {
  border-radius: var(--md-radius-xl);
  max-height: calc(100vh - 32px);
}
</style>
