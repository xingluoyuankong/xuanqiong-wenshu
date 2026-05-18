<template>
  <div class="space-y-6">
    <section class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-indigo-600">长篇骨架</p>
          <h3 class="mt-2 text-xl font-semibold text-slate-950">小说总大纲与世界骨架</h3>
          <p class="mt-2 text-sm leading-6 text-slate-500">
            这里汇总阶段级总纲、故事弧线、卷规划与伏笔系统，正式详情页可以直接审阅长篇骨架，而不是只看摘要。
          </p>
        </div>
        <div class="grid grid-cols-2 gap-3 md:w-[20rem]">
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">阶段数</p>
            <p class="mt-2 text-2xl font-bold text-slate-900">{{ novelOutline.length }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">故事弧线</p>
            <p class="mt-2 text-2xl font-bold text-slate-900">{{ storyArcs.length }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">卷规划</p>
            <p class="mt-2 text-2xl font-bold text-slate-900">{{ volumePlan.length }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">伏笔项</p>
            <p class="mt-2 text-2xl font-bold text-slate-900">{{ foreshadowingSystem.length }}</p>
          </div>
        </div>
      </div>

      <div v-if="worldSystemCards.length" class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="card in worldSystemCards"
          :key="card.label"
          class="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4"
        >
          <p class="text-xs font-semibold uppercase tracking-wide text-emerald-700">{{ card.label }}</p>
          <p class="mt-2 whitespace-pre-line text-sm leading-6 text-emerald-950">{{ card.value }}</p>
        </article>
      </div>
    </section>

    <section class="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-slate-950">阶段级小说总大纲</h3>
          <p class="mt-1 text-sm text-slate-500">按阶段查看目标、冲突、推进轴与章节区间。</p>
        </div>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
          {{ novelOutline.length }} 段
        </span>
      </div>

      <div class="mt-4 space-y-4">
        <article
          v-for="stage in novelOutline"
          :key="`${stage.stage}-${stage.title}`"
          class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4"
        >
          <div class="flex items-start gap-4">
            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-900 text-sm font-semibold text-white">
              {{ stage.stage }}
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <h4 class="text-base font-semibold text-slate-950">{{ stage.title }}</h4>
                <span class="rounded-full bg-white px-2 py-1 text-xs font-medium text-slate-500">第 {{ stage.stage }} 阶段</span>
                <span v-if="stage.expectedChapterRange" class="rounded-full bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">{{ stage.expectedChapterRange }}</span>
              </div>
              <div class="mt-3 grid gap-3 md:grid-cols-2">
                <p v-if="stage.coreTheme" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">阶段主题：</span>{{ stage.coreTheme }}</p>
                <p v-if="stage.goal" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">阶段目标：</span>{{ stage.goal }}</p>
                <p v-if="stage.mainConflict" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">核心冲突：</span>{{ stage.mainConflict }}</p>
                <p v-if="stage.background" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">阶段背景：</span>{{ stage.background }}</p>
                <p v-if="stage.characterProgression" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">人物推进：</span>{{ stage.characterProgression }}</p>
                <p v-if="stage.worldProgression" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">世界推进：</span>{{ stage.worldProgression }}</p>
                <p v-if="stage.factionProgression" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">势力变化：</span>{{ stage.factionProgression }}</p>
                <p v-if="stage.powerProgression" class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700 md:col-span-2"><span class="font-semibold text-slate-900">体系推进：</span>{{ stage.powerProgression }}</p>
              </div>

              <div v-if="stage.survivalAndLifeProgression || stage.culturalAndCivilizationalProgression || stage.resourceAndOperationLine || stage.emotionalCore || stage.majorSetpiece || stage.storyFunction" class="mt-3 grid gap-3 md:grid-cols-2">
                <p v-if="stage.survivalAndLifeProgression" class="rounded-xl bg-cyan-50 px-3 py-3 text-sm leading-6 text-cyan-900"><span class="font-semibold">生存/生活推进：</span>{{ stage.survivalAndLifeProgression }}</p>
                <p v-if="stage.culturalAndCivilizationalProgression" class="rounded-xl bg-violet-50 px-3 py-3 text-sm leading-6 text-violet-900"><span class="font-semibold">文化/文明推进：</span>{{ stage.culturalAndCivilizationalProgression }}</p>
                <p v-if="stage.resourceAndOperationLine" class="rounded-xl bg-emerald-50 px-3 py-3 text-sm leading-6 text-emerald-900"><span class="font-semibold">资源/运营线：</span>{{ stage.resourceAndOperationLine }}</p>
                <p v-if="stage.emotionalCore" class="rounded-xl bg-rose-50 px-3 py-3 text-sm leading-6 text-rose-900"><span class="font-semibold">情绪核心：</span>{{ stage.emotionalCore }}</p>
                <p v-if="stage.majorSetpiece" class="rounded-xl bg-amber-50 px-3 py-3 text-sm leading-6 text-amber-950"><span class="font-semibold">场面支点：</span>{{ stage.majorSetpiece }}</p>
                <p v-if="stage.storyFunction" class="rounded-xl bg-slate-100 px-3 py-3 text-sm leading-6 text-slate-800 md:col-span-2"><span class="font-semibold">阶段职责：</span>{{ stage.storyFunction }}</p>
              </div>

              <div v-if="stage.keyEvents.length" class="mt-3 rounded-xl bg-slate-100 px-3 py-3">
                <p class="text-sm font-semibold text-slate-900">关键事件</p>
                <ul class="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600">
                  <li v-for="event in stage.keyEvents" :key="`${stage.stage}-${event}`">{{ event }}</li>
                </ul>
              </div>

              <div v-if="stage.turningPoints.length || stage.stageTasks.length" class="mt-3 grid gap-3 md:grid-cols-2">
                <div v-if="stage.turningPoints.length" class="rounded-xl bg-indigo-50 px-3 py-3">
                  <p class="text-sm font-semibold text-indigo-900">转折节点</p>
                  <ul class="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-indigo-800">
                    <li v-for="point in stage.turningPoints" :key="`${stage.stage}-${point}`">{{ point }}</li>
                  </ul>
                </div>
                <div v-if="stage.stageTasks.length" class="rounded-xl bg-teal-50 px-3 py-3">
                  <p class="text-sm font-semibold text-teal-900">阶段任务</p>
                  <ul class="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-teal-800">
                    <li v-for="task in stage.stageTasks" :key="`${stage.stage}-${task}`">{{ task }}</li>
                  </ul>
                </div>
              </div>

              <p v-if="stage.stageClimax" class="mt-3 rounded-xl bg-amber-50 px-3 py-3 text-sm leading-6 text-amber-900"><span class="font-semibold">阶段高潮：</span>{{ stage.stageClimax }}</p>
              <p v-if="stage.foreshadowingAndPayoff" class="mt-3 rounded-xl bg-emerald-50 px-3 py-3 text-sm leading-6 text-emerald-800"><span class="font-semibold">伏笔与回收：</span>{{ stage.foreshadowingAndPayoff }}</p>
              <p v-if="stage.endingHook" class="mt-3 rounded-xl bg-white px-3 py-3 text-sm leading-6 text-indigo-700"><span class="font-semibold">阶段钩子：</span>{{ stage.endingHook }}</p>
            </div>
          </div>
        </article>
        <p v-if="!novelOutline.length" class="text-sm text-slate-500">暂无小说总大纲数据。</p>
      </div>
    </section>

    <section class="grid gap-6 xl:grid-cols-3">
      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-slate-950">故事弧线</h3>
            <p class="mt-1 text-sm text-slate-500">主副线目标、冲突与阶段性回收。</p>
          </div>
          <span class="rounded-full bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">{{ storyArcs.length }} 条</span>
        </div>
        <div class="mt-4 space-y-3">
          <div v-for="(arc, index) in storyArcs" :key="`arc-${index}`" class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
            <p class="text-sm font-semibold text-slate-900">{{ arc.title || `故事弧线 ${index + 1}` }}</p>
            <p v-if="arc.summary || arc.goal || arc.conflict" class="mt-2 text-sm leading-6 text-slate-600">{{ arc.summary || arc.goal || arc.conflict }}</p>
          </div>
          <p v-if="!storyArcs.length" class="text-sm text-slate-500">暂无故事弧线数据。</p>
        </div>
      </article>

      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-slate-950">卷规划</h3>
            <p class="mt-1 text-sm text-slate-500">分卷焦点、目标与卷级承接。</p>
          </div>
          <span class="rounded-full bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">{{ volumePlan.length }} 卷</span>
        </div>
        <div class="mt-4 space-y-3">
          <div v-for="(volume, index) in volumePlan" :key="`volume-${index}`" class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
            <p class="text-sm font-semibold text-slate-900">{{ volume.title || volume.volume || `第 ${index + 1} 卷` }}</p>
            <p v-if="volume.focus || volume.goal || volume.summary" class="mt-2 text-sm leading-6 text-slate-600">{{ volume.summary || volume.focus || volume.goal }}</p>
          </div>
          <p v-if="!volumePlan.length" class="text-sm text-slate-500">暂无卷规划数据。</p>
        </div>
      </article>

      <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-slate-950">伏笔系统</h3>
            <p class="mt-1 text-sm text-slate-500">查看埋设、触发与回收职责。</p>
          </div>
          <span class="rounded-full bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">{{ foreshadowingSystem.length }} 项</span>
        </div>
        <div class="mt-4 space-y-3">
          <div v-for="(item, index) in foreshadowingSystem" :key="`foreshadow-${index}`" class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
            <p class="text-sm font-semibold text-slate-900">{{ item.plant || item.summary || `伏笔 ${index + 1}` }}</p>
            <p v-if="item.payoff || item.trigger || item.owner" class="mt-2 text-sm leading-6 text-slate-600">
              {{ [item.payoff, item.trigger, item.owner].filter(Boolean).join('｜') }}
            </p>
          </div>
          <p v-if="!foreshadowingSystem.length" class="text-sm text-slate-500">暂无伏笔系统数据。</p>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BlueprintForeshadowingItem, NovelOutlineStage, StoryArc, VolumePlanItem, WorldSetting } from '@/api/novel'

interface SystemCard {
  label: string
  value: string
}

interface StageItem {
  stage: number
  title: string
  coreTheme: string
  goal: string
  mainConflict: string
  background: string
  characterProgression: string
  worldProgression: string
  factionProgression: string
  powerProgression: string
  survivalAndLifeProgression: string
  culturalAndCivilizationalProgression: string
  resourceAndOperationLine: string
  emotionalCore: string
  majorSetpiece: string
  storyFunction: string
  keyEvents: string[]
  turningPoints: string[]
  stageTasks: string[]
  stageClimax: string
  foreshadowingAndPayoff: string
  endingHook: string
  expectedChapterRange: string
}

interface NovelOutlineSectionData {
  novel_outline?: NovelOutlineStage[]
  story_arcs?: StoryArc[]
  volume_plan?: VolumePlanItem[]
  foreshadowing_system?: BlueprintForeshadowingItem[]
  world_setting?: WorldSetting
}

const props = defineProps<{
  data: NovelOutlineSectionData | null
}>()

const maybeText = (value: unknown): string => typeof value === 'string' ? value.trim() : ''
const normalizeList = (value: unknown): string[] => Array.isArray(value) ? value.map(item => maybeText(item)).filter(Boolean) : []

const formatStructuredValue = (value: any): string => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value
      .map(item => formatStructuredValue(item))
      .filter(Boolean)
      .join('；')
  }
  if (value && typeof value === 'object') {
    return Object.entries(value)
      .map(([key, nested]) => {
        const nestedText = formatStructuredValue(nested)
        return nestedText ? `${key}：${nestedText}` : ''
      })
      .filter(Boolean)
      .join('\n')
  }
  return ''
}

const novelOutline = computed<StageItem[]>(() => {
  const source = Array.isArray(props.data?.novel_outline) ? props.data!.novel_outline : []
  return source.map((record: NovelOutlineStage, index) => ({
    stage: typeof record.stage === 'number' ? record.stage : index + 1,
    title: maybeText(record.title) || `阶段 ${index + 1}`,
    coreTheme: maybeText(record.core_theme),
    goal: maybeText(record.goal),
    mainConflict: maybeText(record.main_conflict),
    background: maybeText(record.background),
    characterProgression: maybeText(record.character_progression),
    worldProgression: maybeText(record.world_progression),
    factionProgression: maybeText(record.faction_progression),
    powerProgression: maybeText(record.power_progression),
    survivalAndLifeProgression: maybeText(record.survival_and_life_progression),
    culturalAndCivilizationalProgression: maybeText(record.cultural_and_civilizational_progression),
    resourceAndOperationLine: maybeText(record.resource_and_operation_line),
    emotionalCore: maybeText(record.emotional_core),
    majorSetpiece: maybeText(record.major_setpiece),
    storyFunction: maybeText(record.story_function),
    keyEvents: normalizeList(record.key_events),
    turningPoints: normalizeList(record.turning_points),
    stageTasks: normalizeList(record.stage_tasks),
    stageClimax: maybeText(record.stage_climax),
    foreshadowingAndPayoff: maybeText(record.foreshadowing_and_payoff),
    endingHook: maybeText(record.ending_hook),
    expectedChapterRange: maybeText(record.expected_chapter_range),
  }))
})

const storyArcs = computed<StoryArc[]>(() => Array.isArray(props.data?.story_arcs) ? props.data!.story_arcs : [])
const volumePlan = computed<VolumePlanItem[]>(() => Array.isArray(props.data?.volume_plan) ? props.data!.volume_plan : [])
const foreshadowingSystem = computed<BlueprintForeshadowingItem[]>(() => Array.isArray(props.data?.foreshadowing_system) ? props.data!.foreshadowing_system : [])
const worldSetting = computed<WorldSetting>(() => props.data?.world_setting && typeof props.data.world_setting === 'object' ? props.data.world_setting : {})

const worldSystemCards = computed<SystemCard[]>(() => {
  const fields: Array<[string, string]> = [
    ['era_background', '时代背景'],
    ['world_structure', '世界结构'],
    ['power_system', '力量体系'],
    ['survival_system', '生存体系'],
    ['life_system', '生活体系'],
    ['culture_system', '文化体系'],
    ['civilization_system', '文明体系'],
    ['economy_system', '经济体系'],
    ['social_structure', '社会结构'],
    ['resource_system', '资源体系'],
    ['belief_system', '信仰体系'],
    ['geography_system', '地理体系'],
    ['faction_order', '势力秩序'],
  ]

  return fields
    .map(([key, label]) => ({ label, value: formatStructuredValue(worldSetting.value?.[key]) }))
    .filter(item => item.value)
})
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'NovelOutlineSection'
})
</script>
