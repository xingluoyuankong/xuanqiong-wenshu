<template>
  <div class="emotion-curve-section">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full flex items-center justify-center" style="background-color: var(--md-primary-container);">
          <svg class="w-5 h-5" style="color: var(--md-on-primary-container);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
        </div>
        <div>
          <h3 class="md-title-medium" style="color: var(--md-on-surface);">{{ pick('情感曲线', 'Emotion curve') }}</h3>
          <p class="md-body-small" style="color: var(--md-on-surface-variant);">{{ pick('追踪章节情感变化', 'Tracks emotional shifts across chapters') }}</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button 
          @click="useAIAnalysis" 
          class="md-btn md-btn-tonal md-ripple"
          :disabled="isLoading"
        >
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          {{ pick('AI深度分析', 'Deep AI analysis') }}
        </button>
        <button
          @click="refreshData"
          class="md-icon-btn md-ripple"
          :disabled="isLoading"
        >
          <svg
            class="w-5 h-5 transition-transform"
            :class="{ 'animate-spin': isLoading }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ pick('刷新', 'Refresh') }}
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="emotion-state-card flex flex-col items-center justify-center py-12">
      <div class="md-spinner"></div>
      <p class="mt-4 md-body-medium" style="color: var(--md-on-surface-variant);">{{ loadingLabel }}</p>
      <p class="mt-2 md-body-small text-center" style="color: var(--md-on-surface-variant);">{{ loadingHint }}</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="emotion-state-card flex flex-col items-center justify-center py-12">
      <div class="w-12 h-12 rounded-full flex items-center justify-center mb-4" style="background-color: var(--md-error-container);">
        <svg class="w-6 h-6" style="color: var(--md-error);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p class="md-body-medium" style="color: var(--md-error);">{{ error }}</p>
      <p class="mt-2 md-body-small text-center" style="color: var(--md-on-surface-variant);">{{ pick(
        '可先刷新已有结果；若章节已更新但仍无数据，再尝试 AI 深度分析。',
        'Try refreshing the saved results first. If chapters have been updated but there is still no data, run the deep AI analysis.'
      ) }}</p>
      <div class="mt-4 flex flex-wrap justify-center gap-3">
        <button @click="refreshData" class="md-btn md-btn-text md-ripple">{{ pick('刷新结果', 'Refresh results') }}</button>
        <button @click="useAIAnalysis" class="md-btn md-btn-tonal md-ripple">{{ pick('重新 AI 分析', 'Re-run AI analysis') }}</button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="!emotionPoints || emotionPoints.length === 0" class="emotion-state-card flex flex-col items-center justify-center py-12">
      <div class="w-16 h-16 rounded-full flex items-center justify-center mb-4" style="background-color: var(--md-surface-container);">
        <svg class="w-8 h-8" style="color: var(--md-on-surface-variant);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      </div>
      <p class="md-body-large" style="color: var(--md-on-surface);">{{ pick('暂无情感数据', 'No emotion data yet') }}</p>
      <p class="md-body-medium text-center" style="color: var(--md-on-surface-variant);">{{ pick(
        '先生成章节内容，再点击“AI深度分析”补齐情绪趋势；如果只是想看已有结果，也可以先点刷新。',
        'Generate chapter content first, then hit “Deep AI analysis” to fill in the emotional trend. To view what is already saved, just refresh.'
      ) }}</p>
      <div class="mt-4 flex flex-wrap justify-center gap-3">
        <button @click="refreshData" class="md-btn md-btn-text md-ripple">{{ pick('刷新结果', 'Refresh results') }}</button>
        <button @click="useAIAnalysis" class="md-btn md-btn-tonal md-ripple">{{ pick('AI深度分析', 'Deep AI analysis') }}</button>
      </div>
    </div>

    <!-- Chart Container -->
    <div v-else>
      <!-- Statistics Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
        <div class="md-card md-card-outlined p-4 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-label-medium" style="color: var(--md-on-surface-variant);">{{ pick('总章节', 'Chapters') }}</p>
          <p class="md-headline-small" style="color: var(--md-primary);">{{ totalChapters }}</p>
        </div>
        <div class="md-card md-card-outlined p-4 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-label-medium" style="color: var(--md-on-surface-variant);">{{ pick('平均强度', 'Average intensity') }}</p>
          <p class="md-headline-small" style="color: var(--md-primary);">{{ averageIntensity }}</p>
        </div>
        <div class="md-card md-card-outlined p-4 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-label-medium" style="color: var(--md-on-surface-variant);">{{ pick('主导情感', 'Dominant emotion') }}</p>
          <p class="md-headline-small" style="color: var(--md-primary);">{{ dominantEmotion }}</p>
        </div>
        <div class="md-card md-card-outlined p-4 text-center" style="border-radius: var(--md-radius-md);">
          <p class="md-label-medium" style="color: var(--md-on-surface-variant);">{{ pick('情感类型', 'Emotion types') }}</p>
          <p class="md-headline-small" style="color: var(--md-primary);">{{ emotionTypeCount }}</p>
        </div>
      </div>

      <!-- Emotion Type Filter Chips -->
      <div class="flex flex-wrap gap-2 mb-3">
        <button
          v-for="emotion in emotionTypes"
          :key="emotion.key"
          @click="toggleEmotion(emotion.key)"
          class="md-chip md-chip-filter md-ripple"
          :class="{ 'selected': selectedEmotions.includes(emotion.key) }"
          :style="selectedEmotions.includes(emotion.key) ? { backgroundColor: emotion.color + '20', color: emotion.color, borderColor: emotion.color } : {}"
        >
          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: emotion.color }"></span>
          {{ emotionDisplayLabel(emotion.label) }}
          <span v-if="emotionDistribution[emotion.label]" class="ml-1 opacity-70">({{ emotionDistribution[emotion.label] }})</span>
        </button>
      </div>

      <!-- Chart -->
      <div class="md-card md-card-outlined p-4" style="border-radius: var(--md-radius-md);">
        <canvas ref="chartCanvas" height="300"></canvas>
      </div>

      <!-- Chapter Details List -->
      <div class="mt-3 space-y-3">
        <h4 class="md-title-small" style="color: var(--md-on-surface);">{{ pick('章节情感详情', 'Chapter emotion details') }}</h4>
        <div 
          v-for="point in emotionPoints" 
          :key="point.chapter_number"
          class="md-card md-card-outlined p-4 flex items-center gap-4"
          style="border-radius: var(--md-radius-md);"
        >
          <div 
            class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
            :style="{ backgroundColor: getEmotionColor(point.emotion_type) + '20' }"
          >
            <span class="md-label-large" :style="{ color: getEmotionColor(point.emotion_type) }">{{ point.chapter_number }}</span>
          </div>
          <div class="flex-1 min-w-0">
            <p class="md-body-medium truncate" style="color: var(--md-on-surface);">{{ point.title }}</p>
            <p class="md-body-small" style="color: var(--md-on-surface-variant);">{{ formatPointDescription(point) }}</p>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <span
              class="md-chip md-chip-filter selected px-2 py-1"
              :style="{ backgroundColor: getEmotionColor(point.emotion_type) + '20', color: getEmotionColor(point.emotion_type) }"
            >
              {{ emotionDisplayLabel(point.emotion_type) }}
            </span>
            <span class="md-label-medium" style="color: var(--md-on-surface-variant);">
              {{ pick(`强度: ${point.intensity}/10`, `Intensity: ${point.intensity}/10`) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import type { Chart as ChartType } from 'chart.js'
import { AnalyticsAPI } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

const { pick, locale } = useLocale()

// Chart 实例类型
let Chart: typeof ChartType | null = null

interface EmotionPoint {
  chapter_number: number
  title: string
  emotion_type: string
  intensity: number
  narrative_phase?: string
  is_turning_point?: boolean
  description: string
}

interface EnhancedEmotionPoint {
  chapter_number: number
  title: string
  primary_emotion: string
  primary_intensity: number
  narrative_phase?: string
  is_turning_point?: boolean
  description: string
}

interface EmotionCurveResponse {
  project_id: string
  project_title: string
  total_chapters: number
  emotion_points: EmotionPoint[]
  average_intensity: number
  emotion_distribution: Record<string, number>
}

const props = defineProps<{
  projectId?: string
}>()

const projectId = computed(() => props.projectId || '')

const chartCanvas = ref<HTMLCanvasElement | null>(null)
const isLoading = ref(false)
const isAiAnalyzing = ref(false)
const error = ref<string | null>(null)
const emotionPoints = ref<EmotionPoint[]>([])
const totalChapters = ref(0)
const averageIntensity = ref(0)
const emotionDistribution = ref<Record<string, number>>({})
let chartInstance: ChartType | null = null

// 键是后端下发的 primary_emotion 英文枚举，值是组件内部统一使用的中文真源标签，两侧都不翻译
const EMOTION_KEY_MAP: { [key: string]: string } = {
  'joy': '喜悦',
  'sadness': '悲伤',
  'anger': '愤怒',
  'fear': '恐惧',
  'surprise': '惊讶',
  'calm': '平静'
};

// label 是内部真源（与 EMOTION_KEY_MAP 的值、emotionDistribution 的键保持一致），只参与匹配不参与翻译；
// labelEn 仅用于界面展示，切换语言时由 emotionDisplayLabel 选取
const emotionTypes = [
  { key: 'joy', label: '喜悦', labelEn: 'Joy', color: '#34A853' },
  { key: 'sadness', label: '悲伤', labelEn: 'Sadness', color: '#4285F4' },
  { key: 'anger', label: '愤怒', labelEn: 'Anger', color: '#EA4335' },
  { key: 'fear', label: '恐惧', labelEn: 'Fear', color: '#9334E6' },
  { key: 'surprise', label: '惊讶', labelEn: 'Surprise', color: '#FBBC04' },
  { key: 'calm', label: '平静', labelEn: 'Calm', color: '#5F6368' }
]

const selectedEmotions = ref(emotionTypes.map(emotion => emotion.key))

// 把中文真源标签转成当前界面语言的展示文案；未登记的标签（后端直接下发的未知情绪）原样返回
const emotionDisplayLabel = (label: string) => {
  if (!label) return label
  const matched = emotionTypes.find(item => item.label === label)
  return pick(label, matched?.labelEn || label)
}

// 转折标记在展示时拼接，而不是在取数时写进 description，这样切换语言可以立即生效
const formatPointDescription = (point: EmotionPoint) => {
  const base = point.description || ''
  if (!point.is_turning_point) return base
  return `${base}${pick('（本章检测到转折）', ' (turning point detected in this chapter)')}`
}

const dominantEmotion = computed(() => {
  if (Object.keys(emotionDistribution.value).length === 0) return '-'
  const sorted = Object.entries(emotionDistribution.value).sort((a, b) => b[1] - a[1])
  const top = sorted[0]?.[0]
  return top ? emotionDisplayLabel(top) : '-'
})

const loadingLabel = computed(() => isAiAnalyzing.value
  ? pick('正在重新分析章节情绪…', 'Re-analysing chapter emotions…')
  : pick('正在加载情感分析结果…', 'Loading the emotion analysis results…'))
const loadingHint = computed(() => isAiAnalyzing.value
  ? pick('AI 深度分析通常需要几十秒，请保持页面打开。', 'Deep AI analysis usually takes tens of seconds — keep this page open.')
  : pick('正在读取当前项目已保存的情感曲线结果。', 'Reading the saved emotion curve for this project.'))

const emotionTypeCount = computed(() => {
  return Object.keys(emotionDistribution.value).length
})

const getEmotionColor = (emotionType: string) => {
  // 入参是中文真源标签，与 EMOTION_KEY_MAP 的值一致；直接复用 emotionTypes 的配色，避免两份颜色表漂移
  return emotionTypes.find(item => item.label === emotionType)?.color || '#5F6368'
}

const toggleEmotion = (key: string) => {
  const index = selectedEmotions.value.indexOf(key)
  if (index > -1) {
    if (selectedEmotions.value.length > 1) {
      selectedEmotions.value.splice(index, 1)
    }
  } else {
    selectedEmotions.value.push(key)
  }
  updateChart()
}

const fetchEmotionData = async (useAI = false) => {
  if (!projectId.value) return

  isLoading.value = true
  isAiAnalyzing.value = useAI
  error.value = null

  try {
    if (useAI) {
      const data: EmotionCurveResponse = await AnalyticsAPI.analyzeEmotionWithAI(projectId.value)
      emotionPoints.value = data.emotion_points
      totalChapters.value = data.total_chapters
      averageIntensity.value = parseFloat(data.average_intensity.toFixed(2))
      emotionDistribution.value = data.emotion_distribution
    } else {
      const data: EnhancedEmotionPoint[] = await AnalyticsAPI.getEnhancedEmotionCurve(projectId.value)
      emotionPoints.value = data.map(point => ({
        chapter_number: point.chapter_number,
        title: point.title,
        emotion_type: EMOTION_KEY_MAP[point.primary_emotion] || point.primary_emotion || '平静',
        intensity: Number(point.primary_intensity || 0),
        narrative_phase: point.narrative_phase,
        is_turning_point: point.is_turning_point,
        description: point.description
      }))
      totalChapters.value = emotionPoints.value.length
      averageIntensity.value = emotionPoints.value.length
        ? parseFloat((emotionPoints.value.reduce((sum, item) => sum + item.intensity, 0) / emotionPoints.value.length).toFixed(2))
        : 0
      emotionDistribution.value = emotionPoints.value.reduce<Record<string, number>>((acc, item) => {
        acc[item.emotion_type] = (acc[item.emotion_type] || 0) + 1
        return acc
      }, {})
    }

    nextTick(() => {
      if (chartInstance) {
        updateChart()
      } else {
        initChart()
      }
    })
  } catch (err: any) {
    error.value = err.message || pick('加载情感数据时发生错误', 'Something went wrong while loading the emotion data')
    console.error('Failed to fetch emotion data:', err)
  } finally {
    isLoading.value = false
    isAiAnalyzing.value = false
  }
}

// updateChart 与 initChart 共用同一份数据构造，避免两处 labels/datasets 逻辑漂移
const buildChartLabels = () => emotionPoints.value.map(p => pick(`第${p.chapter_number}章`, `Ch. ${p.chapter_number}`))

const buildChartDatasets = () => emotionTypes
  .filter(et => selectedEmotions.value.includes(et.key))
  .map(emotionType => {
    const data = emotionPoints.value.map(p => {
      const key = Object.keys(EMOTION_KEY_MAP).find(k => EMOTION_KEY_MAP[k] === p.emotion_type);
      return key === emotionType.key ? p.intensity : null;
    });
    return {
      label: emotionDisplayLabel(emotionType.label),
      data: data,
      borderColor: emotionType.color,
      backgroundColor: emotionType.color + '33',
      tension: 0.4,
      fill: false,
      spanGaps: true,
    };
  });

const updateChart = () => {
  if (!chartInstance) {
    initChart();
    return;
  }

  chartInstance.data.labels = buildChartLabels();
  chartInstance.data.datasets = buildChartDatasets();
  chartInstance.update();
}

const initChart = async () => {
  if (!chartCanvas.value) {
    console.warn('Chart canvas not found.');
    return;
  }

  if (chartInstance) {
    chartInstance.destroy();
  }

  // 动态导入图表所需最小模块，减少详情页图表分包体积
  if (!Chart) {
    const chartModule = await import('chart.js')
    const {
      Chart: ChartJS,
      CategoryScale,
      Filler,
      Legend,
      LineController,
      LineElement,
      LinearScale,
      PointElement,
      Title,
      Tooltip,
    } = chartModule

    ChartJS.register(
      LineController,
      LineElement,
      PointElement,
      CategoryScale,
      LinearScale,
      Tooltip,
      Legend,
      Title,
      Filler,
    )

    Chart = ChartJS
  }

  const ctx = chartCanvas.value.getContext('2d');
  if (!ctx) {
    console.error('Failed to get 2D context for canvas.');
    return;
  }

  const labels = buildChartLabels();
  const datasets = buildChartDatasets();

  chartInstance = new Chart!(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 10,
          title: {
            display: true,
            text: pick('情感强度', 'Emotion intensity')
          }
        },
        x: {
          title: {
            display: true,
            text: pick('章节', 'Chapter')
          }
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: function(context: any) {
              return context[0].label;
            },
            label: function(context: any) {
              // dataset.label 已经是展示语言的标签，这里必须用同一个转换函数比对
              const emotionType = emotionTypes.find(et => emotionDisplayLabel(et.label) === context.dataset.label);
              const point = emotionPoints.value[context.dataIndex];
              if (point && emotionType && Object.keys(EMOTION_KEY_MAP).find(k => EMOTION_KEY_MAP[k] === point.emotion_type) === emotionType.key) {
                return `${emotionDisplayLabel(point.emotion_type)}: ${point.intensity}/10`;
              }
              return '';
            }
          }
        },
        legend: {
          display: true,
          position: 'top',
        }
      }
    },
  });
};

const refreshData = () => {
  fetchEmotionData(false);
};

const useAIAnalysis = () => {
  fetchEmotionData(true);
};

onMounted(() => {
  fetchEmotionData()
})

watch(projectId, (value) => {
  if (value) fetchEmotionData()
}, { immediate: false })

watch(emotionPoints, (newPoints) => {
  if (newPoints && newPoints.length > 0) {
    nextTick(() => {
      if (chartInstance) {
        updateChart();
      } else {
        initChart();
      }
    });
  } else if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
}, { deep: true });

watch(selectedEmotions, () => {
  updateChart();
}, { deep: true });

// canvas 里的轴标题、图例、tooltip 都是绘制时写死的，切换语言必须整块重建
watch(locale, () => {
  if (chartInstance) void initChart();
});
</script>

<style scoped>
.emotion-curve-section {
  padding: 20px;
  background-color: var(--md-surface);
  border-radius: var(--md-radius-lg);
  color: var(--md-on-surface);
}

.emotion-state-card {
  border: 1px solid var(--md-outline-variant);
  border-radius: var(--md-radius-md);
  background: var(--md-surface-container-low);
}

.md-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 0 16px;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}

.md-btn-tonal {
  background-color: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}

.md-btn-tonal:hover {
  background-color: var(--md-secondary-container-hover);
}

.md-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  font-size: 1.25rem;
  cursor: pointer;
  transition: background-color 0.2s;
  color: var(--md-on-surface-variant);
}

.md-icon-btn:hover {
  background-color: var(--md-on-surface-variant-hover);
}

.md-spinner {
  width: 32px;
  height: 32px;
  border: 4px solid var(--md-primary);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.md-card {
  background-color: var(--md-surface-container-low);
  border-radius: var(--md-radius-md);
  padding: 16px;
}

.md-card-outlined {
  border: 1px solid var(--md-outline);
  background-color: var(--md-surface);
}

.md-chip {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 0.875rem;
  background-color: var(--md-surface-container-low);
  color: var(--md-on-surface);
  border: 1px solid var(--md-outline);
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s;
}

.md-chip.selected {
  background-color: var(--md-primary-container);
  color: var(--md-on-primary-container);
  border-color: var(--md-primary);
}

.md-chip-filter .w-2.h-2 {
  margin-right: 8px;
}

.md-title-medium {
  font-size: 1rem;
  font-weight: 500;
}

.md-body-small {
  font-size: 0.75rem;
}

.md-body-medium {
  font-size: 0.875rem;
}

.md-body-large {
  font-size: 1rem;
}

.md-label-medium {
  font-size: 0.75rem;
  font-weight: 500;
}

.md-headline-small {
  font-size: 1.5rem;
  font-weight: 400;
}

.md-title-small {
  font-size: 0.875rem;
  font-weight: 500;
}

.md-label-large {
  font-size: 1rem;
  font-weight: 500;
}
</style>
