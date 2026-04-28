<template>
  <div class="analysis-workbench space-y-5 overflow-y-auto">
    <section class="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">{{ title }}</h3>
          <p class="mt-1 text-sm leading-6 text-slate-600">{{ subtitle }}</p>
        </div>
        <div class="rounded-2xl bg-white px-4 py-3 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200/70">
          <div class="font-medium text-slate-800">对生成的作用</div>
          <div class="mt-1 leading-6">{{ generationUsage }}</div>
        </div>
      </div>
    </section>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article
        v-for="item in metricCards"
        :key="item.label"
        class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
      >
        <div class="text-xs font-medium tracking-wide text-slate-500">{{ item.label }}</div>
        <div class="mt-2 text-2xl font-semibold text-slate-900">{{ item.value }}</div>
        <div v-if="item.hint" class="mt-2 text-xs leading-5 text-slate-500">{{ item.hint }}</div>
      </article>
    </section>

    <section class="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h4 class="text-base font-semibold text-slate-900">当前最该处理的问题</h4>
            <p class="mt-1 text-sm text-slate-500">这里列的是最值得回灌到下一章生成与当前精修链路的问题。</p>
          </div>
          <span class="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">优先级排序</span>
        </div>
        <div v-if="priorityIssues.length" class="mt-4 space-y-3">
          <div
            v-for="(issue, index) in priorityIssues"
            :key="`${sectionType}-issue-${index}`"
            class="rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-3"
          >
            <div class="flex items-start justify-between gap-3">
              <p class="text-sm font-medium leading-6 text-slate-900">{{ issue.title }}</p>
              <span class="rounded-full bg-white px-2.5 py-1 text-xs text-amber-700">P{{ index + 1 }}</span>
            </div>
            <p v-if="issue.detail" class="mt-2 text-sm leading-6 text-slate-600">{{ issue.detail }}</p>
            <p v-if="issue.hint" class="mt-2 text-xs leading-5 text-slate-500">{{ issue.hint }}</p>
          </div>
        </div>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          当前没有高优先级风险，下一章可继续按既定主线推进。
        </div>
      </article>

      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h4 class="text-base font-semibold text-slate-900">下一章执行建议</h4>
        <p class="mt-1 text-sm text-slate-500">按“立刻可用”的粒度整理，方便直接喂给正文生成。</p>
        <ul v-if="nextActions.length" class="mt-4 space-y-3">
          <li
            v-for="(action, index) in nextActions"
            :key="`${sectionType}-next-${index}`"
            class="rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-sm leading-6 text-slate-700"
          >
            <div class="font-medium text-slate-900">建议 {{ index + 1 }}</div>
            <div class="mt-1">{{ action }}</div>
          </li>
        </ul>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          暂无新的下一章建议，说明当前数据不足或主线稳定。
        </div>
      </article>
    </section>

    <section class="grid gap-4 xl:grid-cols-2">
      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h4 class="text-base font-semibold text-slate-900">关键章节 / 关键节点</h4>
        <div v-if="milestones.length" class="mt-4 flex flex-wrap gap-2">
          <span
            v-for="(item, index) in milestones"
            :key="`${sectionType}-milestone-${index}`"
            class="rounded-full bg-sky-50 px-3 py-2 text-sm text-sky-700 ring-1 ring-sky-100"
          >
            {{ item }}
          </span>
        </div>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          暂无明确里程碑数据。
        </div>
      </article>

      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h4 class="text-base font-semibold text-slate-900">长线规划 / 补充说明</h4>
        <ul v-if="longTermItems.length" class="mt-4 space-y-3">
          <li
            v-for="(item, index) in longTermItems"
            :key="`${sectionType}-long-${index}`"
            class="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700"
          >
            {{ item }}
          </li>
        </ul>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
          暂无更多长线规划说明。
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ComprehensiveAnalysis, CreativeGuidanceAnalysis, StoryTrajectoryAnalysis } from '@/api/novel'

const props = defineProps<{
  sectionType: 'story_trajectory' | 'creative_guidance' | 'comprehensive_analysis'
  data?: StoryTrajectoryAnalysis | CreativeGuidanceAnalysis | ComprehensiveAnalysis | Record<string, any> | null
}>()

type MetricCard = { label: string; value: string; hint?: string }
type IssueCard = { title: string; detail?: string; hint?: string }

const emotionLabelMap: Record<string, string> = {
  joy: '喜悦', sadness: '悲伤', anger: '愤怒', fear: '恐惧', surprise: '惊讶', anticipation: '期待', calm: '平静', love: '爱意', determination: '坚定'
}
const trajectoryLabelMap: Record<string, string> = {
  rising: '持续上扬', falling: '持续走低', wave: '波浪推进', spiral: '螺旋升级', zigzag: '锯齿推进', flat: '平稳推进'
}
const guidancePriorityMap: Record<string, string> = {
  critical: '立即处理', high: '高优先级', medium: '中优先级', low: '低优先级'
}

const source = computed(() => props.data || {})
const trajectory = computed<StoryTrajectoryAnalysis | Record<string, any>>(() => props.sectionType === 'comprehensive_analysis' ? (source.value as ComprehensiveAnalysis)?.trajectory || {} : source.value as StoryTrajectoryAnalysis)
const guidance = computed<CreativeGuidanceAnalysis | Record<string, any>>(() => props.sectionType === 'comprehensive_analysis' ? (source.value as ComprehensiveAnalysis)?.guidance || {} : source.value as CreativeGuidanceAnalysis)
const emotionPoints = computed<any[]>(() => props.sectionType === 'comprehensive_analysis' && Array.isArray((source.value as ComprehensiveAnalysis)?.emotion_points) ? (source.value as ComprehensiveAnalysis).emotion_points : [])

const title = computed(() => props.sectionType === 'story_trajectory' ? '故事轨迹工作台' : props.sectionType === 'creative_guidance' ? '创意指导工作台' : '综合分析工作台')
const subtitle = computed(() => props.sectionType === 'story_trajectory'
  ? '把情节走势、关键转折和低谷章节整理成可执行的推进判断，避免剧情空转。'
  : props.sectionType === 'creative_guidance'
    ? '把当前章节的优点、弱点和后续写法建议整理成一套能直接用于生成的创作提示。'
    : '把情感曲线、故事轨迹和创意指导汇总成一张总控面板，用于决定下一章到底该怎么写。')
const generationUsage = computed(() => props.sectionType === 'story_trajectory'
  ? '用于提醒模型当前主线是该拉高冲突、补低谷，还是准备关键转折。'
  : props.sectionType === 'creative_guidance'
    ? '用于把弱点、章节建议和长期规划回灌到下一章生成与评审阶段。'
    : '用于综合判断“现在最该修什么”和“下一章最该推进什么”，减少空分析。')

const metricCards = computed<MetricCard[]>(() => {
  if (props.sectionType === 'story_trajectory') {
    const data = trajectory.value
    return [
      { label: '走势形状', value: trajectoryLabelMap[String(data.shape || '')] || String(data.shape || '未识别') },
      { label: '走势置信度', value: typeof data.shape_confidence === 'number' ? `${Math.round(data.shape_confidence * 100)}%` : '—' },
      { label: '已分析章节', value: data.total_chapters != null ? String(data.total_chapters) : '—' },
      { label: '波动强度', value: data.volatility != null ? String(data.volatility) : '—', hint: typeof data.avg_intensity === 'number' ? `平均张力 ${data.avg_intensity.toFixed(1)}` : undefined }
    ]
  }
  if (props.sectionType === 'creative_guidance') {
    const data = guidance.value
    return [
      { label: '当前章节', value: data.current_chapter ? `第 ${data.current_chapter} 章` : '—' },
      { label: '优势条数', value: Array.isArray(data.strengths) ? String(data.strengths.length) : '0' },
      { label: '弱点条数', value: Array.isArray(data.weaknesses) ? String(data.weaknesses.length) : '0' },
      { label: '指导条数', value: Array.isArray(data.guidance_items) ? String(data.guidance_items.length) : '0' }
    ]
  }
  const data = source.value as ComprehensiveAnalysis
  const firstPoint = emotionPoints.value[emotionPoints.value.length - 1]
  return [
    { label: '情感节点', value: String(emotionPoints.value.length) },
    { label: '当前章节', value: data.guidance?.current_chapter ? `第 ${data.guidance.current_chapter} 章` : '—' },
    { label: '故事走势', value: trajectoryLabelMap[String(data.trajectory?.shape || '')] || String(data.trajectory?.shape || '未识别') },
    { label: '最新情绪', value: firstPoint?.primary_emotion ? (emotionLabelMap[firstPoint.primary_emotion] || firstPoint.primary_emotion) : '—' }
  ]
})

const priorityIssues = computed<IssueCard[]>(() => {
  if (props.sectionType === 'story_trajectory') {
    const data = trajectory.value
    const items: IssueCard[] = []
    if (typeof data.shape_confidence === 'number' && data.shape_confidence < 0.55) items.push({ title: '整体走势辨识度偏低', detail: '当前章节的推进方向还不够清晰，容易让后续章节失去主线焦点。', hint: '建议在下一章明确一次冲突升级或目标转向。' })
    if (Array.isArray(data.valley_chapters) && data.valley_chapters.length) items.push({ title: `低谷章节集中在 ${data.valley_chapters.slice(0, 4).map((value: number) => `第${value}章`).join('、')}`, detail: '这些章节可能节奏偏缓、冲突不足，容易拖慢阅读黏性。', hint: '可回看这些章节的目标推进与悬念释放。' })
    if (typeof data.volatility === 'number' && data.volatility > 7) items.push({ title: '情节波动偏大', detail: '张力上下起伏过猛，可能导致章节之间承接不稳。', hint: '补一层过渡动机或因果桥接，会比单纯加戏更有效。' })
    return items.concat((Array.isArray(data.recommendations) ? data.recommendations : []).slice(0, 3).map((text: string) => ({ title: text }))).slice(0, 5)
  }
  const weaknessCards = (Array.isArray(guidance.value.weaknesses) ? guidance.value.weaknesses : []).map((text: string) => ({ title: text }))
  const guidanceCards = (Array.isArray(guidance.value.guidance_items) ? guidance.value.guidance_items : []).map((item: any) => ({ title: item.title || '未命名指导项', detail: item.description || '', hint: guidancePriorityMap[item.priority] || item.priority || undefined }))
  if (props.sectionType === 'creative_guidance') return [...weaknessCards, ...guidanceCards].slice(0, 6)
  const combo = [...weaknessCards, ...guidanceCards]
  if (trajectory.value?.recommendations) combo.push(...trajectory.value.recommendations.map((text: string) => ({ title: text })))
  if (!combo.length && emotionPoints.value.length) {
    const lastPoint = emotionPoints.value[emotionPoints.value.length - 1]
    combo.push({ title: `最新章节情绪以“${emotionLabelMap[lastPoint.primary_emotion] || lastPoint.primary_emotion || '未知'}”为主`, detail: lastPoint.description || '建议核查这一情绪是否与剧情推进一致。' })
  }
  return combo.slice(0, 6)
})

const nextActions = computed<string[]>(() => props.sectionType === 'story_trajectory'
  ? (Array.isArray(trajectory.value.recommendations) ? trajectory.value.recommendations : [])
  : (Array.isArray(guidance.value.next_chapter_suggestions) ? guidance.value.next_chapter_suggestions : []))

const milestones = computed<string[]>(() => {
  if (props.sectionType === 'story_trajectory') {
    return [
      ...(Array.isArray(trajectory.value.turning_points) ? trajectory.value.turning_points.map((value: number) => `关键转折：第 ${value} 章`) : []),
      ...(Array.isArray(trajectory.value.peak_chapters) ? trajectory.value.peak_chapters.map((value: number) => `高峰章节：第 ${value} 章`) : []),
      ...(Array.isArray(trajectory.value.valley_chapters) ? trajectory.value.valley_chapters.map((value: number) => `低谷章节：第 ${value} 章`) : [])
    ].slice(0, 12)
  }
  if (props.sectionType === 'creative_guidance') {
    return (Array.isArray(guidance.value.guidance_items) ? guidance.value.guidance_items : []).flatMap((item: any) => Array.isArray(item.affected_chapters) && item.affected_chapters.length ? [`${item.title || '未命名指导'}：${item.affected_chapters.map((value: number) => `第 ${value} 章`).join('、')}`] : []).slice(0, 12)
  }
  return emotionPoints.value.slice(-8).map((point: any) => `第 ${point.chapter_number} 章：${emotionLabelMap[point.primary_emotion] || point.primary_emotion || '未知情绪'}${point.is_turning_point ? ' · 转折点' : ''}`)
})

const longTermItems = computed<string[]>(() => {
  if (props.sectionType === 'story_trajectory') return [trajectory.value.description].filter(Boolean) as string[]
  if (props.sectionType === 'creative_guidance') return Array.isArray(guidance.value.long_term_planning) ? guidance.value.long_term_planning : []
  return [ ...(Array.isArray(guidance.value.long_term_planning) ? guidance.value.long_term_planning : []), ...(trajectory.value?.description ? [trajectory.value.description] : []) ].slice(0, 8)
})
</script>
