<template>
  <div class="analysis-workbench space-y-3 overflow-y-auto">
    <section class="rounded-xl border border-slate-200/80 bg-slate-50/80 p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">{{ title }}</h3>
          <p class="mt-1 text-sm leading-6 text-slate-600">{{ subtitle }}</p>
        </div>
        <div class="rounded-lg bg-white px-4 py-3 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200/70">
          <div class="font-medium text-slate-800">{{ pick('对生成的作用', 'How this feeds generation') }}</div>
          <div class="mt-1 leading-6">{{ generationUsage }}</div>
        </div>
      </div>
    </section>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article
        v-for="item in metricCards"
        :key="item.label"
        class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      >
        <div class="text-xs font-medium tracking-wide text-slate-500">{{ item.label }}</div>
        <div class="mt-2 text-xl font-semibold text-slate-900">{{ item.value }}</div>
        <div v-if="item.hint" class="mt-2 text-xs leading-5 text-slate-500">{{ item.hint }}</div>
      </article>
    </section>

    <section class="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <article class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h4 class="text-base font-semibold text-slate-900">{{ pick('当前最该处理的问题', 'What to fix first') }}</h4>
            <p class="mt-1 text-sm text-slate-500">{{ pick(
              '这里列的是最值得回灌到下一章生成与当前精修链路的问题。',
              'These are the issues most worth feeding back into the next chapter and the current polishing pass.'
            ) }}</p>
          </div>
          <span class="rounded-full bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">{{ pick('优先级排序', 'Sorted by priority') }}</span>
        </div>
        <div v-if="priorityIssues.length" class="mt-4 space-y-3">
          <div
            v-for="(issue, index) in priorityIssues"
            :key="`${sectionType}-issue-${index}`"
            class="rounded-lg border border-sky-100 bg-sky-50/70 px-4 py-3"
          >
            <div class="flex items-start justify-between gap-3">
              <p class="text-sm font-medium leading-6 text-slate-900">{{ issue.title }}</p>
              <span class="rounded-full bg-white px-2.5 py-1 text-xs text-sky-700">P{{ index + 1 }}</span>
            </div>
            <p v-if="issue.detail" class="mt-2 text-sm leading-6 text-slate-600">{{ issue.detail }}</p>
            <p v-if="issue.hint" class="mt-2 text-xs leading-5 text-slate-500">{{ issue.hint }}</p>
          </div>
        </div>
        <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          {{ pick(
            '当前没有高优先级风险，下一章可继续按既定主线推进。',
            'No high-priority risks right now — the next chapter can keep following the established main thread.'
          ) }}
        </div>
      </article>

      <article class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <h4 class="text-base font-semibold text-slate-900">{{ pick('下一章执行建议', 'Next-chapter actions') }}</h4>
        <p class="mt-1 text-sm text-slate-500">{{ pick(
          '按“立刻可用”的粒度整理，方便直接喂给正文生成。',
          'Written at a ready-to-use granularity so it can go straight into prose generation.'
        ) }}</p>
        <ul v-if="nextActions.length" class="mt-4 space-y-3">
          <li
            v-for="(action, index) in nextActions"
            :key="`${sectionType}-next-${index}`"
            class="rounded-lg border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-sm leading-6 text-slate-700"
          >
            <div class="font-medium text-slate-900">{{ pick(`建议 ${index + 1}`, `Action ${index + 1}`) }}</div>
            <div class="mt-1">{{ action }}</div>
          </li>
        </ul>
        <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          {{ pick(
            '暂无新的下一章建议，说明当前数据不足或主线稳定。',
            'No new next-chapter actions yet — either the data is thin or the main thread is stable.'
          ) }}
        </div>
      </article>
    </section>

    <section class="grid gap-4 xl:grid-cols-2">
      <article class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <h4 class="text-base font-semibold text-slate-900">{{ pick('关键章节 / 关键节点', 'Key chapters and beats') }}</h4>
        <div v-if="milestones.length" class="mt-4 flex flex-wrap gap-2">
          <span
            v-for="(item, index) in milestones"
            :key="`${sectionType}-milestone-${index}`"
            class="rounded-full bg-sky-50 px-3 py-2 text-sm text-sky-700 ring-1 ring-sky-100"
          >
            {{ item }}
          </span>
        </div>
        <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          {{ pick('暂无明确里程碑数据。', 'No milestone data yet.') }}
        </div>
      </article>

      <article class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <h4 class="text-base font-semibold text-slate-900">{{ pick('长线规划 / 补充说明', 'Long-range planning and notes') }}</h4>
        <ul v-if="longTermItems.length" class="mt-4 space-y-3">
          <li
            v-for="(item, index) in longTermItems"
            :key="`${sectionType}-long-${index}`"
            class="rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700"
          >
            {{ item }}
          </li>
        </ul>
        <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          {{ pick('暂无更多长线规划说明。', 'No further long-range planning notes.') }}
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ComprehensiveAnalysis, CreativeGuidanceAnalysis, StoryTrajectoryAnalysis } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

const { pick } = useLocale()

const props = defineProps<{
  sectionType: 'story_trajectory' | 'creative_guidance' | 'comprehensive_analysis'
  data?: StoryTrajectoryAnalysis | CreativeGuidanceAnalysis | ComprehensiveAnalysis | Record<string, any> | null
}>()

type MetricCard = { label: string; value: string; hint?: string }
type IssueCard = { title: string; detail?: string; hint?: string }

// 键是后端下发的英文枚举（内部真源），值是展示文案，用函数惰性求值以便切换语言后重新取值
const emotionLabelMap: Record<string, () => string> = {
  joy: () => pick('喜悦', 'Joy'),
  sadness: () => pick('悲伤', 'Sadness'),
  anger: () => pick('愤怒', 'Anger'),
  fear: () => pick('恐惧', 'Fear'),
  surprise: () => pick('惊讶', 'Surprise'),
  anticipation: () => pick('期待', 'Anticipation'),
  calm: () => pick('平静', 'Calm'),
  love: () => pick('爱意', 'Love'),
  determination: () => pick('坚定', 'Determination'),
}
const trajectoryLabelMap: Record<string, () => string> = {
  rising: () => pick('持续上扬', 'Steadily rising'),
  falling: () => pick('持续走低', 'Steadily falling'),
  wave: () => pick('波浪推进', 'Wave-like'),
  spiral: () => pick('螺旋升级', 'Spiralling up'),
  zigzag: () => pick('锯齿推进', 'Zigzag'),
  flat: () => pick('平稳推进', 'Flat'),
}
const guidancePriorityMap: Record<string, () => string> = {
  critical: () => pick('立即处理', 'Fix now'),
  high: () => pick('高优先级', 'High priority'),
  medium: () => pick('中优先级', 'Medium priority'),
  low: () => pick('低优先级', 'Low priority'),
}

const source = computed(() => props.data || {})
const trajectory = computed<StoryTrajectoryAnalysis | Record<string, any>>(() => props.sectionType === 'comprehensive_analysis' ? (source.value as ComprehensiveAnalysis)?.trajectory || {} : source.value as StoryTrajectoryAnalysis)
const guidance = computed<CreativeGuidanceAnalysis | Record<string, any>>(() => props.sectionType === 'comprehensive_analysis' ? (source.value as ComprehensiveAnalysis)?.guidance || {} : source.value as CreativeGuidanceAnalysis)
const emotionPoints = computed<any[]>(() => props.sectionType === 'comprehensive_analysis' && Array.isArray((source.value as ComprehensiveAnalysis)?.emotion_points) ? (source.value as ComprehensiveAnalysis).emotion_points : [])

const title = computed(() => props.sectionType === 'story_trajectory'
  ? pick('故事轨迹工作台', 'Story trajectory workbench')
  : props.sectionType === 'creative_guidance'
    ? pick('创意指导工作台', 'Creative guidance workbench')
    : pick('综合分析工作台', 'Comprehensive analysis workbench'))
const subtitle = computed(() => props.sectionType === 'story_trajectory'
  ? pick(
      '把情节走势、关键转折和低谷章节整理成可执行的推进判断，避免剧情空转。',
      'Turns plot momentum, key turns, and low-energy chapters into actionable calls so the story never idles.'
    )
  : props.sectionType === 'creative_guidance'
    ? pick(
        '把当前章节的优点、弱点和后续写法建议整理成一套能直接用于生成的创作提示。',
        'Turns this chapter’s strengths, weaknesses, and craft notes into prompts you can generate from directly.'
      )
    : pick(
        '把情感曲线、故事轨迹和创意指导汇总成一张总控面板，用于决定下一章到底该怎么写。',
        'Rolls the emotion curve, story trajectory, and creative guidance into one control panel for deciding what the next chapter does.'
      ))
const generationUsage = computed(() => props.sectionType === 'story_trajectory'
  ? pick(
      '用于提醒模型当前主线是该拉高冲突、补低谷，还是准备关键转折。',
      'Tells the model whether the main thread needs escalated conflict, a lifted trough, or a setup for a key turn.'
    )
  : props.sectionType === 'creative_guidance'
    ? pick(
        '用于把弱点、章节建议和长期规划回灌到下一章生成与评审阶段。',
        'Feeds weaknesses, chapter notes, and long-range plans back into next-chapter generation and review.'
      )
    : pick(
        '用于综合判断“现在最该修什么”和“下一章最该推进什么”，减少空分析。',
        'Combines “what to fix now” with “what the next chapter should advance”, cutting down on empty analysis.'
      ))

const metricCards = computed<MetricCard[]>(() => {
  const unknown = pick('未识别', 'Unclassified')
  if (props.sectionType === 'story_trajectory') {
    const data = trajectory.value
    return [
      { label: pick('走势形状', 'Curve shape'), value: trajectoryLabelMap[String(data.shape || '')]?.() || String(data.shape || unknown) },
      { label: pick('走势置信度', 'Shape confidence'), value: typeof data.shape_confidence === 'number' ? `${Math.round(data.shape_confidence * 100)}%` : '—' },
      { label: pick('已分析章节', 'Chapters analysed'), value: data.total_chapters != null ? String(data.total_chapters) : '—' },
      { label: pick('波动强度', 'Volatility'), value: data.volatility != null ? String(data.volatility) : '—', hint: typeof data.avg_intensity === 'number' ? pick(`平均张力 ${data.avg_intensity.toFixed(1)}`, `Average tension ${data.avg_intensity.toFixed(1)}`) : undefined }
    ]
  }
  if (props.sectionType === 'creative_guidance') {
    const data = guidance.value
    return [
      { label: pick('当前章节', 'Current chapter'), value: data.current_chapter ? pick(`第 ${data.current_chapter} 章`, `Chapter ${data.current_chapter}`) : '—' },
      { label: pick('优势条数', 'Strengths'), value: Array.isArray(data.strengths) ? String(data.strengths.length) : '0' },
      { label: pick('弱点条数', 'Weaknesses'), value: Array.isArray(data.weaknesses) ? String(data.weaknesses.length) : '0' },
      { label: pick('指导条数', 'Guidance items'), value: Array.isArray(data.guidance_items) ? String(data.guidance_items.length) : '0' }
    ]
  }
  const data = source.value as ComprehensiveAnalysis
  const firstPoint = emotionPoints.value[emotionPoints.value.length - 1]
  return [
    { label: pick('情感节点', 'Emotion points'), value: String(emotionPoints.value.length) },
    { label: pick('当前章节', 'Current chapter'), value: data.guidance?.current_chapter ? pick(`第 ${data.guidance.current_chapter} 章`, `Chapter ${data.guidance.current_chapter}`) : '—' },
    { label: pick('故事走势', 'Story curve'), value: trajectoryLabelMap[String(data.trajectory?.shape || '')]?.() || String(data.trajectory?.shape || unknown) },
    { label: pick('最新情绪', 'Latest emotion'), value: firstPoint?.primary_emotion ? (emotionLabelMap[firstPoint.primary_emotion]?.() || firstPoint.primary_emotion) : '—' }
  ]
})

const priorityIssues = computed<IssueCard[]>(() => {
  if (props.sectionType === 'story_trajectory') {
    const data = trajectory.value
    const items: IssueCard[] = []
    if (typeof data.shape_confidence === 'number' && data.shape_confidence < 0.55) items.push({
      title: pick('整体走势辨识度偏低', 'The overall curve is hard to read'),
      detail: pick(
        '当前章节的推进方向还不够清晰，容易让后续章节失去主线焦点。',
        'The direction of recent chapters is still vague, which risks losing the main thread later on.'
      ),
      hint: pick(
        '建议在下一章明确一次冲突升级或目标转向。',
        'Land one clear escalation or goal shift in the next chapter.'
      )
    })
    if (Array.isArray(data.valley_chapters) && data.valley_chapters.length) items.push({
      title: pick(
        `低谷章节集中在 ${data.valley_chapters.slice(0, 4).map((value: number) => `第${value}章`).join('、')}`,
        `Troughs cluster around ${data.valley_chapters.slice(0, 4).map((value: number) => `chapter ${value}`).join(', ')}`
      ),
      detail: pick(
        '这些章节可能节奏偏缓、冲突不足，容易拖慢阅读黏性。',
        'These chapters may be slow and short on conflict, which weakens reader pull.'
      ),
      hint: pick(
        '可回看这些章节的目标推进与悬念释放。',
        'Revisit how those chapters advance goals and release suspense.'
      )
    })
    if (typeof data.volatility === 'number' && data.volatility > 7) items.push({
      title: pick('情节波动偏大', 'Plot swings are too wide'),
      detail: pick(
        '张力上下起伏过猛，可能导致章节之间承接不稳。',
        'Tension jumps too sharply, which can make chapter-to-chapter handoffs unstable.'
      ),
      hint: pick(
        '补一层过渡动机或因果桥接，会比单纯加戏更有效。',
        'Adding a layer of transitional motive or causal bridging beats simply adding more scenes.'
      )
    })
    return items.concat((Array.isArray(data.recommendations) ? data.recommendations : []).slice(0, 3).map((text: string) => ({ title: text }))).slice(0, 5)
  }
  const weaknessCards = (Array.isArray(guidance.value.weaknesses) ? guidance.value.weaknesses : []).map((text: string) => ({ title: text }))
  const guidanceCards = (Array.isArray(guidance.value.guidance_items) ? guidance.value.guidance_items : []).map((item: any) => ({ title: item.title || pick('未命名指导项', 'Untitled guidance item'), detail: item.description || '', hint: guidancePriorityMap[item.priority]?.() || item.priority || undefined }))
  if (props.sectionType === 'creative_guidance') return [...weaknessCards, ...guidanceCards].slice(0, 6)
  const combo = [...weaknessCards, ...guidanceCards]
  if (trajectory.value?.recommendations) combo.push(...trajectory.value.recommendations.map((text: string) => ({ title: text })))
  if (!combo.length && emotionPoints.value.length) {
    const lastPoint = emotionPoints.value[emotionPoints.value.length - 1]
    const emotion = emotionLabelMap[lastPoint.primary_emotion]?.() || lastPoint.primary_emotion || pick('未知', 'unknown')
    combo.push({
      title: pick(`最新章节情绪以“${emotion}”为主`, `The latest chapter reads mainly as “${emotion}”`),
      detail: lastPoint.description || pick(
        '建议核查这一情绪是否与剧情推进一致。',
        'Check whether that emotion matches how the plot is progressing.'
      )
    })
  }
  return combo.slice(0, 6)
})

const nextActions = computed<string[]>(() => props.sectionType === 'story_trajectory'
  ? (Array.isArray(trajectory.value.recommendations) ? trajectory.value.recommendations : [])
  : (Array.isArray(guidance.value.next_chapter_suggestions) ? guidance.value.next_chapter_suggestions : []))

const milestones = computed<string[]>(() => {
  if (props.sectionType === 'story_trajectory') {
    return [
      ...(Array.isArray(trajectory.value.turning_points) ? trajectory.value.turning_points.map((value: number) => pick(`关键转折：第 ${value} 章`, `Key turn: chapter ${value}`)) : []),
      ...(Array.isArray(trajectory.value.peak_chapters) ? trajectory.value.peak_chapters.map((value: number) => pick(`高峰章节：第 ${value} 章`, `Peak: chapter ${value}`)) : []),
      ...(Array.isArray(trajectory.value.valley_chapters) ? trajectory.value.valley_chapters.map((value: number) => pick(`低谷章节：第 ${value} 章`, `Trough: chapter ${value}`)) : [])
    ].slice(0, 12)
  }
  if (props.sectionType === 'creative_guidance') {
    return (Array.isArray(guidance.value.guidance_items) ? guidance.value.guidance_items : []).flatMap((item: any) => Array.isArray(item.affected_chapters) && item.affected_chapters.length
      ? [pick(
          `${item.title || '未命名指导'}：${item.affected_chapters.map((value: number) => `第 ${value} 章`).join('、')}`,
          `${item.title || 'Untitled guidance'}: ${item.affected_chapters.map((value: number) => `chapter ${value}`).join(', ')}`
        )]
      : []).slice(0, 12)
  }
  return emotionPoints.value.slice(-8).map((point: any) => {
    const emotion = emotionLabelMap[point.primary_emotion]?.() || point.primary_emotion || pick('未知情绪', 'Unknown emotion')
    return pick(
      `第 ${point.chapter_number} 章：${emotion}${point.is_turning_point ? ' · 转折点' : ''}`,
      `Chapter ${point.chapter_number}: ${emotion}${point.is_turning_point ? ' · turning point' : ''}`
    )
  })
})

const longTermItems = computed<string[]>(() => {
  if (props.sectionType === 'story_trajectory') return [trajectory.value.description].filter(Boolean) as string[]
  if (props.sectionType === 'creative_guidance') return Array.isArray(guidance.value.long_term_planning) ? guidance.value.long_term_planning : []
  return [ ...(Array.isArray(guidance.value.long_term_planning) ? guidance.value.long_term_planning : []), ...(trajectory.value?.description ? [trajectory.value.description] : []) ].slice(0, 8)
})
</script>
