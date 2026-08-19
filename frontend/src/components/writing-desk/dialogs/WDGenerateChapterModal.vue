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
                      {{ pick(`生成第 ${chapterNumber ?? '-'} 章`, `Generate chapter ${chapterNumber ?? '-'}`) }}
                    </DialogTitle>
                    <p class="md-body-small md-on-surface-variant mt-1">
                      {{ pick(
                        '可指定章节方向、质量偏好与字数约束（默认约 5000 字，可自行调整，最低 1200 字）。',
                        'Set the direction, quality preferences and word-count limits (about 5,000 words by default, 1,200 minimum).',
                      ) }}
                    </p>
                  </div>
                </div>

                <div class="grid grid-cols-1 gap-4">
                  <div>
                    <div class="flex items-center justify-between mb-2">
                      <label class="md-text-field-label">{{ pick('章节方向 / 写作指令（可选）', 'Chapter direction / writing notes (optional)') }}</label>
                      <button type="button" class="text-xs text-gray-500 hover:text-gray-700" @click="writingNotes = ''">{{ t('common.clear') }}</button>
                    </div>
                    <textarea
                      v-model="writingNotes"
                      class="md-textarea w-full mt-2 min-h-[96px]"
                      :placeholder="pick(
                        '例如：本章推进主线冲突，角色必须做高风险选择，章尾埋钩子。',
                        'For example: push the main conflict forward, force a high-stakes choice, end on a hook.',
                      )"
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
                      <label class="md-text-field-label">{{ pick('质量偏好（可选）', 'Quality preferences (optional)') }}</label>
                      <button type="button" class="text-xs text-gray-500 hover:text-gray-700" @click="qualityRequirements = ''">{{ t('common.clear') }}</button>
                    </div>
                    <textarea
                      v-model="qualityRequirements"
                      class="md-textarea w-full mt-2 min-h-[96px]"
                      :placeholder="pick(
                        '例如：冲突更强、反转更自然、对白更有张力、环境描写更有画面感。',
                        'For example: stronger conflict, more natural twists, sharper dialogue, more vivid settings.',
                      )"
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

                <!-- 质量档位选择 -->
                <div class="mt-5">
                  <label class="md-text-field-label mb-2 block">{{ pick('质量档位（可选）', 'Quality tier (optional)') }}</label>
                  <div class="flex flex-wrap gap-2">
                    <button
                      v-for="opt in presetOptions"
                      :key="opt.value"
                      type="button"
                      :class="['md-btn md-ripple text-xs', selectedPreset === opt.value ? 'md-btn-filled' : 'md-btn-outlined']"
                      @click="selectedPreset = opt.value"
                    >
                      {{ opt.label }}
                    </button>
                    <button
                      type="button"
                      :class="['md-btn md-ripple text-xs', selectedPreset === '' ? 'md-btn-filled' : 'md-btn-outlined']"
                      @click="selectedPreset = ''"
                    >
                      {{ pick('自动（按字数推断）', 'Auto (infer from word count)') }}
                    </button>
                  </div>
                  <p class="mt-1 text-xs text-gray-500">
                    {{ pick(
                      'basic=快速生成 / enhanced=增强质量 / longform=长篇深度 / ultimate=最高质量。留空则由目标字数自动推断。',
                      'basic = fast draft / enhanced = higher quality / longform = long-form depth / ultimate = best quality. Leave empty to infer from the target word count.',
                    ) }}
                  </p>
                </div>

                <div class="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label class="md-text-field-label">{{ pick('最低字数（强约束目标）', 'Minimum word count (hard target)') }}</label>
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
                    <label class="md-text-field-label">{{ pick('目标字数（建议）', 'Target word count (guideline)') }}</label>
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

                <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label class="md-text-field-label">{{ pick('长篇分段字数（可选）', 'Long-form segment size (optional)') }}</label>
                    <input v-model.number="segmentWordLimit" type="number" min="500" step="100" class="md-text-field-input w-full mt-2">
                    <p class="mt-1 text-xs text-gray-500">{{ pick(
                      '目标字数达到 2 万字时按此预算分段，并在段后保存断点。',
                      'Once the target reaches 20,000 words, the draft is split by this budget and a checkpoint is saved after each segment.',
                    ) }}</p>
                  </div>
                  <div>
                    <label class="md-text-field-label">{{ pick('任务超时（秒，0 为后端自动计算）', 'Task timeout (seconds, 0 = decided by the server)') }}</label>
                    <input v-model.number="generationTimeoutSeconds" type="number" min="0" step="60" class="md-text-field-input w-full mt-2">
                    <p class="mt-1 text-xs text-gray-500">{{ pick(
                      '仅作为任务预算传递，后端仍会执行安全上下限。',
                      'Passed through as a budget hint; the server still enforces safe bounds.',
                    ) }}</p>
                  </div>
                </div>

                <!-- 字数配置保存 -->
                <div class="mt-4 flex flex-wrap items-center gap-3">
                   <button
                     type="button"
                     class="md-btn md-btn-outlined md-ripple text-sm"
                     @click="handleSaveChapterConfig"
                   >
                     {{ pick('保存为本章配置', 'Save for this chapter') }}
                   </button>
                   <button
                     type="button"
                     class="md-btn md-btn-outlined md-ripple text-sm"
                     @click="handleSaveGlobalConfig"
                   >
                     {{ pick('保存为全局默认', 'Save as global default') }}
                   </button>
                   <span v-if="saveConfigMessage" class="text-sm" :class="saveConfigSuccess ? 'text-green-600' : 'text-red-500'">
                     {{ saveConfigMessage }}
                   </span>
                   <span v-else-if="loadedConfigHint" class="text-sm text-gray-500">
                     {{ loadedConfigHint }}
                   </span>
                 </div>
                <p class="mt-2 text-xs text-gray-500">
                  {{ pick(
                    '本章配置仅作用于当前项目当前章节；全局默认仅保存在当前浏览器。',
                    'Chapter settings apply only to this chapter of this project; the global default is stored in this browser only.',
                  ) }}
                </p>
              </div>

                              <!-- 高级质量配置开关 -->
                <div class="mt-5 pt-4 border-t border-gray-100">
                  <button type="button" class="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900" @click="showAdvanced = !showAdvanced">
                    <span class="text-lg">{{ showAdvanced ? '▼' : '▶' }}</span>
                    {{ pick('高级质量配置', 'Advanced quality settings') }}
                    <span class="text-xs text-slate-400 ml-1">{{ pick('(连续性、充实度、自我审查)', '(continuity, enrichment, self-critique)') }}</span>
                  </button>
                  <div v-if="showAdvanced" class="mt-3 p-4 bg-slate-50 rounded-2xl border border-slate-100 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    <label class="flex items-center gap-2 p-2 rounded-xl hover:bg-white cursor-pointer"><input type="checkbox" v-model="enableConsistency" class="sr-only peer"><span class="text-sm font-medium text-slate-700">{{ pick('一致性检查', 'Continuity check') }}</span></label>
                    <label class="flex items-center gap-2 p-2 rounded-xl hover:bg-white cursor-pointer"><input type="checkbox" v-model="enableEnrichment" class="sr-only peer"><span class="text-sm font-medium text-slate-700">{{ pick('内容充实', 'Content enrichment') }}</span></label>
                    <label class="flex items-center gap-2 p-2 rounded-xl hover:bg-white cursor-pointer"><input type="checkbox" v-model="enableSelfCritique" class="sr-only peer"><span class="text-sm font-medium text-slate-700">{{ pick('自我审查', 'Self-critique') }}</span></label>
                    <label class="flex items-center gap-2 p-2 rounded-xl hover:bg-white cursor-pointer"><input type="checkbox" v-model="enableReaderSim" class="sr-only peer"><span class="text-sm font-medium text-slate-700">{{ pick('读者模拟', 'Reader simulation') }}</span></label>
                    <label class="flex items-center gap-2 p-2 rounded-xl hover:bg-white cursor-pointer"><input type="checkbox" v-model="enableMemory" class="sr-only peer"><span class="text-sm font-medium text-slate-700">{{ pick('记忆层', 'Memory layer') }}</span></label>
                    <label class="flex items-center gap-2 p-2 rounded-xl hover:bg-white cursor-pointer"><input type="checkbox" v-model="enableForeshadowing" class="sr-only peer"><span class="text-sm font-medium text-slate-700">{{ pick('伏笔计划', 'Foreshadowing plan') }}</span></label>
                  </div>
                </div>


              <div class="xq-dialog-footer">
                <button
                  type="button"
                  class="md-btn md-btn-filled md-ripple sm:ml-3 sm:w-auto w-full justify-center"
                  @click="handleGenerate"
                >
                  {{ pick('生成章节', 'Generate chapter') }}
                </button>
                <button
                  type="button"
                  class="md-btn md-btn-outlined md-ripple sm:mt-0 sm:ml-3 sm:w-auto w-full justify-center mt-3"
                  @click="$emit('close')"
                >
                  {{ t('common.cancel') }}
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
import { useLocale } from '@/composables/useLocale'

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
  segmentWordLimit?: number
  generationTimeoutSeconds?: number
  preset?: 'basic' | 'enhanced' | 'longform' | 'ultimate'
  enableConsistency?: boolean
  enableEnrichment?: boolean
  enableSelfCritique?: boolean
  enableReaderSim?: boolean
  enableMemory?: boolean
  enableForeshadowing?: boolean
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

/** 配置来源：本章 / 全局默认 / 历史遗留 */
type ConfigScope = 'chapter' | 'global' | 'legacy'

const DEFAULT_MIN_WORD_COUNT = 4500
const DEFAULT_TARGET_WORD_COUNT = 5000

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

const { pick, t, formatNumber } = useLocale()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'generate', payload: GenerateChapterPayload): void
}>()

const writingNotes = ref('')
const qualityRequirements = ref('')
const minWordCount = ref<number | null>(DEFAULT_MIN_WORD_COUNT)
const targetWordCount = ref<number | null>(DEFAULT_TARGET_WORD_COUNT)
const segmentWordLimit = ref<number | null>(4500)
const generationTimeoutSeconds = ref<number | null>(0)
const selectedPreset = ref<'' | 'basic' | 'enhanced' | 'longform' | 'ultimate'>('')
const showAdvanced = ref(false)
const enableConsistency = ref(true)
const enableEnrichment = ref(false)
const enableSelfCritique = ref(true)
const enableReaderSim = ref(false)
const enableMemory = ref(false)
const enableForeshadowing = ref(true)

// 档位标签含中文说明，必须走 computed，否则切换语言后不会刷新
const presetOptions = computed(() => [
  { value: 'basic' as const, label: pick('basic · 快速', 'basic · fast') },
  { value: 'enhanced' as const, label: pick('enhanced · 增强', 'enhanced · improved') },
  { value: 'longform' as const, label: pick('longform · 长篇', 'longform · extended') },
  { value: 'ultimate' as const, label: pick('ultimate · 最高', 'ultimate · best') },
])
const targetWordCountMin = computed(() => minWordCount.value ?? DEFAULT_MIN_WORD_COUNT)

// UI state for save config
const hasSavedConfig = ref(false)
const loadedConfigSourceKey = ref<ConfigScope | ''>('')
const saveConfigMessage = ref('')
const saveConfigSuccess = ref(true)

/** 配置来源作用域名称 */
const configScopeLabel = (scope: ConfigScope) => {
  if (scope === 'chapter') return pick('本章配置', 'chapter settings')
  if (scope === 'global') return pick('全局默认配置', 'global default settings')
  return pick('历史全局配置', 'legacy global settings')
}

const loadedConfigHint = computed(() => {
  const scope = loadedConfigSourceKey.value
  if (!scope) return ''
  const label = configScopeLabel(scope)
  return pick(`已加载${label}（浏览器本地）`, `Loaded ${label} (stored in this browser)`)
})

// 预设短语既是按钮文案，也会写进写作指令，因此必须随语言切换整体重算
const writingDirectionPresets = computed(() => [
  pick('开篇即冲突', 'Open with conflict'),
  pick('主角必须做艰难选择', 'Force a hard choice on the protagonist'),
  pick('推进主线谜团', 'Advance the central mystery'),
  pick('制造强烈反差', 'Create a sharp contrast'),
  pick('埋下新伏笔', 'Plant new foreshadowing'),
  pick('回收旧伏笔', 'Pay off earlier foreshadowing'),
  pick('强化角色关系拉扯', 'Tighten the pull between characters'),
  pick('升级外部危机', 'Escalate the external crisis'),
  pick('突出世界规则代价', 'Highlight the cost of the world rules'),
  pick('让反派更立体', 'Give the antagonist more depth'),
  pick('增加战术博弈感', 'Add tactical maneuvering'),
  pick('以情绪爆点收束', 'Close on an emotional peak'),
  pick('章尾留下强钩子', 'Leave a strong hook at the chapter end'),
  pick('通过对话推进剧情', 'Move the plot through dialogue'),
  pick('细节暗示后续反转', 'Seed details that hint at a later twist'),
  pick('增加误导线索', 'Add a misleading clue'),
  pick('增加信息差推进', 'Drive tension with unequal information'),
  pick('小胜后立刻反噬', 'Let a small win backfire at once'),
  pick('阶段目标先达成再崩塌', 'Reach the milestone, then let it collapse'),
  pick('主角秘密被逼近', 'Close in on the protagonist secret'),
  pick('配角主动推动剧情', 'Let a supporting character drive the plot'),
  pick('阵营冲突升级', 'Escalate the faction conflict'),
  pick('情感线与主线交叉爆发', 'Collide the emotional arc with the main plot'),
  pick('制造身份错位危机', 'Trigger a mistaken-identity crisis'),
  pick('本章结尾必须留悬念', 'End this chapter on a cliffhanger'),
  pick('主角在本章犯下代价', 'Make the protagonist pay a real price here'),
  pick('让关键配角逆袭抢戏', 'Let a key supporting character steal the scene'),
  pick('制造价值观冲突对撞', 'Stage a clash of values'),
  pick('压缩铺垫，直接见刀锋', 'Cut the setup and get to the blade'),
  pick('在结尾抛出新问题而非新答案', 'End with a new question, not a new answer'),
  pick('强化主角短板暴露', 'Expose the protagonist weakness'),
  pick('加入一次失败的尝试', 'Include one failed attempt'),
  pick('增加压迫性的时间限制', 'Add a pressing deadline'),
  pick('信息揭露分三段递进', 'Reveal information in three escalating beats'),
])

const qualityPresets = computed(() => [
  pick('情节推进更果断', 'Push the plot forward more decisively'),
  pick('对白更有张力', 'Sharper tension in dialogue'),
  pick('行动逻辑更清晰', 'Clearer logic behind actions'),
  pick('细节服务情节推进', 'Keep details in service of the plot'),
  pick('减少解释性旁白', 'Cut explanatory narration'),
  pick('冲突更强', 'Stronger conflict'),
  pick('钩子更狠', 'Harder hooks'),
  pick('反转更自然', 'More natural twists'),
  pick('节奏更紧凑', 'Tighter pacing'),
  pick('人物动机更清晰', 'Clearer character motivation'),
  pick('角色弧光更明显', 'More visible character arcs'),
  pick('悬念密度更高', 'Higher suspense density'),
  pick('叙事更连贯', 'More coherent narration'),
  pick('伏笔与回收更闭环', 'Close the loop on foreshadowing and payoff'),
  pick('场景调度更清楚', 'Clearer scene staging'),
  pick('人物说话更贴合身份', 'Voices that match who the characters are'),
  pick('章节开头吸引力更高', 'A more gripping chapter opening'),
  pick('章节结尾留白更强', 'A more resonant chapter ending'),
  pick('视角控制更稳定', 'Steadier point of view'),
  pick('避免口水化叙述', 'Avoid rambling narration'),
  pick('避免机械重复表达', 'Avoid repetitive phrasing'),
  pick('信息密度更高', 'Higher information density'),
  pick('张弛更有层次', 'Better rhythm of tension and release'),
  pick('句式更有变化', 'More varied sentence structure'),
  pick('比喻更克制更准确', 'Restrained, precise metaphors'),
  pick('场景切换更自然', 'Smoother scene transitions'),
  pick('高潮段落更有爆发力', 'More explosive climaxes'),
  pick('低潮段落更有余韵', 'Quiet passages that linger'),
  pick('文风更有辨识度', 'A more distinctive voice'),
  pick('情绪更细腻', 'Subtler emotion'),
  pick('画面感更强', 'Stronger visual imagery'),
  pick('细节更真实', 'More convincing detail'),
  pick('心理描写更深入', 'Deeper interiority'),
  pick('叙述更具电影感', 'More cinematic narration'),
  pick('关键词回环更明显', 'Clearer motif echoes'),
])

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

const resolveInitialConfig = (): { config: ChapterGenerationConfig; source: ConfigScope | '' } => {
  const chapterConfig = loadConfigFromStorage(getChapterGenerationStorageKey(props.projectId, props.chapterNumber))
  if (chapterConfig) {
    return { config: chapterConfig, source: 'chapter' }
  }

  const globalConfig = loadConfigFromStorage(GLOBAL_GENERATION_STORAGE_KEY)
  if (globalConfig) {
    return { config: globalConfig, source: 'global' }
  }

  const legacyConfig = loadLegacyConfig()
  if (legacyConfig) {
    saveConfigToStorage(GLOBAL_GENERATION_STORAGE_KEY, legacyConfig)
    clearLegacyConfig()
    return { config: legacyConfig, source: 'legacy' }
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
  loadedConfigSourceKey.value = source
  saveConfigMessage.value = ''
}

watch(
  () => [props.show, props.projectId, props.chapterNumber],
  ([visible]) => {
    if (visible) {
      applyInitialValues()
    }
  },
  { immediate: true }
)

const appendPreset = (target: typeof writingNotes, preset: string) => {
  const current = target.value.trim()
  if (!current) {
    target.value = preset
    return
  }
  if (!current.includes(preset)) {
    target.value = `${current}${pick('；', '; ')}${preset}`
  }
}

const appendWritingPreset = (preset: string) => appendPreset(writingNotes, preset)
const qualityBaseline = () => pick(
  '优先保证章级推进、对话攻防、逻辑递进，描写只服务冲突',
  'Prioritise chapter-level progression, dialogue as attack and defence, and escalating logic; description only serves the conflict',
)
const appendQualityPreset = (preset: string) => {
  appendPreset(qualityRequirements, qualityBaseline())
  appendPreset(qualityRequirements, preset)
}

const finishSaveMessage = (scope: ConfigScope, config: ChapterGenerationConfig) => {
  hasSavedConfig.value = true
  loadedConfigSourceKey.value = scope
  saveConfigSuccess.value = true
  const scopeLabel = configScopeLabel(scope)
  const savedNotes = config.writingNotes
    ? pick('已保存写作指令', 'writing notes saved')
    : pick('未填写写作指令', 'no writing notes')
  const savedQuality = config.qualityRequirements
    ? pick('已保存质量偏好', 'quality preferences saved')
    : pick('未填写质量偏好', 'no quality preferences')
  saveConfigMessage.value = pick(
    `${scopeLabel}已保存：${savedNotes}，${savedQuality}，最低${config.minWordCount}字，目标${config.targetWordCount}字`,
    `${scopeLabel.charAt(0).toUpperCase()}${scopeLabel.slice(1)} saved: ${savedNotes}, ${savedQuality}, minimum ${formatNumber(config.minWordCount)} words, target ${formatNumber(config.targetWordCount)} words`,
  )
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
    saveConfigMessage.value = pick('保存本章配置失败，请稍后重试。', 'Could not save the chapter settings. Please try again.')
    return
  }

  finishSaveMessage('chapter', config)
}

const handleSaveGlobalConfig = () => {
  normalizeWordCounts('target')
  const config = buildCurrentConfig()
  minWordCount.value = config.minWordCount
  targetWordCount.value = config.targetWordCount

  if (!saveConfigToStorage(GLOBAL_GENERATION_STORAGE_KEY, config)) {
    saveConfigSuccess.value = false
    saveConfigMessage.value = pick('保存全局默认失败，请稍后重试。', 'Could not save the global default. Please try again.')
    return
  }

  finishSaveMessage('global', config)
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
    targetWordCount: targetValue,
    segmentWordLimit: Math.max(500, Number(segmentWordLimit.value) || 4500),
    generationTimeoutSeconds: Math.max(0, Number(generationTimeoutSeconds.value) || 0),
    preset: (selectedPreset.value || undefined) as GenerateChapterPayload['preset'],
    enableConsistency: enableConsistency.value,
    enableEnrichment: enableEnrichment.value,
    enableSelfCritique: enableSelfCritique.value,
    enableReaderSim: enableReaderSim.value,
    enableMemory: enableMemory.value,
    enableForeshadowing: enableForeshadowing.value
  })
  emit('close')
}
</script>

<style scoped>
.m3-generate-dialog {
  border-radius: var(--md-radius-xl);
  max-height: calc(100vh - 32px);
}
.peer ~ .toggle-indicator { transition: all 0.2s; }
.peer:checked ~ .toggle-indicator { background: var(--xq-accent); }
.peer:checked ~ .toggle-indicator::after { transform: translateX(18px); }
</style>
