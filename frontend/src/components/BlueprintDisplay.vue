<!-- AIMETA P=蓝图展示_蓝图详细信息|R=蓝图详情展示|NR=不含编辑功能|E=component:BlueprintDisplay|X=internal|A=展示组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <section class="flex min-h-0 flex-col overflow-hidden rounded-[32px] border border-slate-200/80 bg-white/95 shadow-[0_24px_90px_-40px_rgba(15,23,42,0.34)] backdrop-blur-xl">
    <header class="sticky top-0 z-20 shrink-0 border-b border-white/10 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.24),transparent_35%),linear-gradient(135deg,#0f172a_0%,#1e1b4b_55%,#155e75_100%)] px-5 py-5 text-white sm:px-6 lg:px-8">
      <div class="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div class="min-w-0 space-y-4">
          <div class="flex flex-wrap items-center gap-2 text-xs font-medium">
            <span class="rounded-full border border-white/10 bg-white/12 px-3 py-1 text-white">蓝图总览</span>
            <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">只读预览</span>
            <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">{{ chapterOutline.length }} 章</span>
            <span v-if="hasAiMessage" class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">含系统说明</span>
          </div>

          <div class="space-y-3">
            <h2 class="text-2xl font-semibold tracking-tight sm:text-3xl">{{ blueprintTitle }}</h2>
            <p class="max-w-3xl text-sm leading-6 text-slate-200 sm:text-base">
              {{ synopsis }}
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <span
              v-for="tag in heroTags"
              :key="tag"
              class="inline-flex items-center rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-medium text-slate-100"
            >
              {{ tag }}
            </span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3 xl:justify-end">
          <div class="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm leading-6 text-slate-100">
            <p class="font-semibold text-white">此处只做最终决定</p>
            <p class="mt-1 text-slate-200">确认后直接进入写作台；如需改方向，请先重做蓝图。</p>
          </div>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 hover:bg-white/15"
            @click="confirmRegenerate"
          >
            重做蓝图
          </button>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/20 transition-all hover:-translate-y-0.5 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
            :disabled="props.isSaving || !blueprint"
            @click="confirmBlueprint"
          >
            {{ props.isSaving ? '正在进入写作台...' : blueprint ? '确认蓝图并进入开写' : '缺少蓝图' }}
          </button>
        </div>
      </div>

      <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="item in overviewStats"
          :key="item.label"
          class="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 backdrop-blur"
        >
          <p class="text-xs uppercase tracking-[0.24em] text-slate-300">{{ item.label }}</p>
          <p class="mt-1 text-lg font-semibold text-white">{{ item.value }}</p>
          <p class="mt-1 text-xs leading-5 text-slate-300">{{ item.hint }}</p>
        </div>
      </div>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 lg:px-8">
      <div
        v-if="hasAiMessage"
        class="mb-4 rounded-[24px] border border-indigo-200/80 bg-indigo-50/80 p-5 shadow-[0_12px_40px_-30px_rgba(79,70,229,0.32)]"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">系统说明</p>
            <h3 class="mt-2 text-lg font-semibold text-slate-950">这份说明会一起带到写作台</h3>
          </div>
          <span class="inline-flex rounded-full border border-indigo-200 bg-white px-3 py-1 text-xs font-medium text-indigo-700">
            可直接阅读
          </span>
        </div>
        <div class="blueprint-markdown mt-4 rounded-2xl border border-indigo-100 bg-white px-4 py-4 text-slate-700" v-html="renderedAiMessage"></div>
      </div>

      <div v-if="!blueprint" class="rounded-[28px] border border-rose-200 bg-rose-50 p-8 text-center text-rose-700 shadow-[0_12px_40px_-28px_rgba(244,63,94,0.18)]">
        <p class="text-lg font-semibold">暂时没有可展示的蓝图</p>
        <p class="mt-2 text-sm leading-6">先返回上一页重新生成，或者直接点“重做蓝图”再来一版。</p>
        <button
          type="button"
          class="mt-5 inline-flex items-center justify-center rounded-2xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-rose-900/10 transition-all hover:-translate-y-0.5 hover:bg-rose-500"
          @click="confirmRegenerate"
        >
          重做蓝图
        </button>
      </div>

      <div v-else class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,360px)]">
        <main class="space-y-4">
          <section class="rounded-[28px] border border-slate-200/80 bg-slate-50/90 p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">故事摘要</p>
                <h3 class="mt-2 text-xl font-semibold text-slate-950">开写前先确认这四个维度</h3>
                <p class="mt-2 text-sm leading-6 text-slate-600">
                  这是后续写作时最先参考的骨架。确认无误后，内容会直接进入写作台。
                </p>
              </div>
              <span class="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
                只读预览
              </span>
            </div>

            <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <article
                v-for="field in overviewFields"
                :key="field.label"
                class="rounded-2xl border border-white/80 bg-white px-4 py-4 shadow-sm"
              >
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{{ field.label }}</p>
                <p class="mt-2 text-sm font-semibold text-slate-950">{{ field.value }}</p>
              </article>
            </div>

            <div class="mt-4 rounded-2xl border border-white/80 bg-white p-4">
              <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">完整梗概</p>
              <p class="mt-3 whitespace-pre-line text-sm leading-7 text-slate-700">
                {{ fullSynopsis }}
              </p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">世界观</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">规则、地标和势力</h3>
              </div>
              <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
                {{ worldLocations.length }} 个地点 / {{ worldFactions.length }} 个势力
              </span>
            </div>

            <div class="mt-4 rounded-2xl border border-amber-200/70 bg-amber-50 p-4">
              <p class="text-xs font-medium uppercase tracking-[0.24em] text-amber-600">核心规则</p>
              <p class="mt-2 whitespace-pre-line text-sm leading-7 text-amber-900">
                {{ worldCoreRules }}
              </p>
            </div>

            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">关键地点</p>
                  <span class="text-xs font-medium text-slate-500">{{ worldLocations.length }}</span>
                </div>
                <div class="mt-3 space-y-3">
                  <article
                    v-for="location in worldLocations"
                    :key="location.name"
                    class="rounded-xl border border-slate-200 bg-white px-3 py-3"
                  >
                    <p class="text-sm font-semibold text-slate-900">{{ location.name }}</p>
                    <p class="mt-1 text-sm leading-6 text-slate-600">{{ location.description }}</p>
                  </article>
                  <p v-if="!worldLocations.length" class="text-sm text-slate-500">暂无地点信息。</p>
                </div>
              </div>

              <div class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">主要势力</p>
                  <span class="text-xs font-medium text-slate-500">{{ worldFactions.length }}</span>
                </div>
                <div class="mt-3 space-y-3">
                  <article
                    v-for="faction in worldFactions"
                    :key="faction.name"
                    class="rounded-xl border border-slate-200 bg-white px-3 py-3"
                  >
                    <p class="text-sm font-semibold text-slate-900">{{ faction.name }}</p>
                    <p class="mt-1 text-sm leading-6 text-slate-600">{{ faction.description }}</p>
                  </article>
                  <p v-if="!worldFactions.length" class="text-sm text-slate-500">暂无势力信息。</p>
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">章节总览</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">按章节展开的写作路线</h3>
              </div>
              <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
                {{ chapterOutline.length }} 章
              </span>
            </div>

            <div class="mt-4 space-y-3">
              <article
                v-for="chapter in chapterOutline"
                :key="chapter.number"
                class="group rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4 transition-all hover:-translate-y-0.5 hover:border-indigo-200 hover:bg-indigo-50/60"
              >
                <div class="flex items-start gap-4">
                  <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-900 text-sm font-semibold text-white">
                    {{ chapter.number }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <h4 class="text-base font-semibold text-slate-950">{{ chapter.title }}</h4>
                      <span class="rounded-full bg-white px-2 py-1 text-xs font-medium text-slate-500">
                        第 {{ chapter.number }} 章
                      </span>
                    </div>
                    <p class="mt-2 text-sm leading-6 text-slate-600">{{ chapter.summary }}</p>
                  </div>
                </div>
              </article>
              <p v-if="!chapterOutline.length" class="text-sm text-slate-500">暂无章节大纲。</p>
            </div>
          </section>
        </main>

        <aside class="space-y-4 xl:sticky xl:top-6 self-start">
          <section class="rounded-[28px] border border-slate-200/80 bg-slate-950 p-5 text-white shadow-[0_16px_48px_-30px_rgba(15,23,42,0.55)]">
            <p class="text-xs uppercase tracking-[0.28em] text-slate-400">角色速览</p>
            <h3 class="mt-2 text-lg font-semibold">一眼扫完人物表</h3>
            <div class="mt-4 max-h-[34rem] space-y-3 overflow-y-auto pr-1">
              <article
                v-for="character in characterCards"
                :key="character.name"
                class="rounded-2xl border border-white/10 bg-white/5 px-4 py-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-sm font-semibold text-white">{{ character.name }}</p>
                  <span v-if="character.role" class="rounded-full bg-white/10 px-2 py-1 text-[11px] font-medium text-slate-200">
                    {{ character.role }}
                  </span>
                  <span class="rounded-full bg-cyan-400/10 px-2 py-1 text-[11px] font-medium text-cyan-100">
                    {{ character.importance }}
                  </span>
                </div>
                <p v-if="character.summary" class="mt-2 text-sm leading-6 text-slate-300">
                  {{ character.summary }}
                </p>
                <p v-if="character.spotlight" class="mt-2 rounded-xl bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-100">
                  {{ character.spotlight }}
                </p>
                <div v-if="character.details.length" class="mt-3 space-y-2">
                  <div
                    v-for="detail in character.details"
                    :key="`${character.name}-${detail.label}`"
                    class="rounded-xl bg-white/5 px-3 py-2 text-sm leading-6 text-slate-300"
                  >
                    <span class="font-medium text-white">{{ detail.label }}：</span>{{ detail.value }}
                  </div>
                </div>
              </article>
              <p v-if="!characterCards.length" class="text-sm text-slate-300">暂无角色信息。</p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">关系网</p>
            <div class="mt-4 space-y-3">
              <article
                v-for="relationship in relationshipCards"
                :key="`${relationship.from}-${relationship.to}`"
                class="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded-full bg-white px-3 py-1 text-sm font-semibold text-rose-700">{{ relationship.from }}</span>
                  <span class="text-rose-400">→</span>
                  <span class="rounded-full bg-white px-3 py-1 text-sm font-semibold text-rose-700">{{ relationship.to }}</span>
                  <span class="rounded-full border border-rose-200 bg-white px-3 py-1 text-xs font-semibold text-rose-600">
                    {{ relationship.relationType }}
                  </span>
                </div>
                <p class="mt-3 text-sm leading-6 text-rose-700">{{ relationship.description }}</p>
                <div class="mt-3 grid gap-2">
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">当前状态：</span>{{ relationship.currentState }}
                  </div>
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">核心张力：</span>{{ relationship.tension }}
                  </div>
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">预期变化：</span>{{ relationship.expectedChange }}
                  </div>
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">关键触发：</span>{{ relationship.keyTrigger }}
                  </div>
                </div>
              </article>
              <p v-if="!relationshipCards.length" class="text-sm text-slate-500">暂无关键信息。</p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-gradient-to-br from-indigo-50 via-white to-emerald-50 p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">进入写作前</p>
            <p class="mt-2 text-sm leading-6 text-slate-700">
              右上角主按钮已经是唯一确认入口，这里只保留说明，避免同一屏出现重复主 CTA。
            </p>
            <div class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <div class="rounded-2xl border border-white/80 bg-white/80 px-4 py-3">
                <p class="font-semibold text-slate-900">确认蓝图并进入开写</p>
                <p class="mt-1">会把当前蓝图保存到项目中，并直接切到小说详情工作台。</p>
              </div>
              <div class="rounded-2xl border border-white/80 bg-white/80 px-4 py-3">
                <p class="font-semibold text-slate-900">重做蓝图</p>
                <p class="mt-1">用于方向不满意时重新生成，避免带着错误骨架进入后续写作。</p>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { globalAlert } from '@/composables/useAlert'
import type { Blueprint } from '@/api/novel'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'

interface Props {
  blueprint: Blueprint | null
  aiMessage?: string
  isSaving?: boolean
}

interface DetailItem {
  label: string
  value: string
}

interface CharacterCard {
  name: string
  role: string
  importance: string
  summary: string
  spotlight: string
  details: DetailItem[]
}

interface RelationshipCard {
  from: string
  to: string
  description: string
  relationType: string
  currentState: string
  tension: string
  expectedChange: string
  keyTrigger: string
}

interface WorldItem {
  name: string
  description: string
}

interface ChapterItem {
  number: number
  title: string
  summary: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: []
  regenerate: []
}>()

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const optionalText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  return ''
}

const displayText = (value: unknown, fallback = '待补充'): string => {
  return optionalText(value) || fallback
}

const maybeText = (value: unknown): string => optionalText(value)

const importanceWeight = (value: string): number => {
  const normalized = value.trim().toLowerCase()
  if (['主角', 'protagonist', 'main'].includes(normalized)) return 0
  if (['核心', 'core', 'major'].includes(normalized)) return 1
  if (['配角', 'supporting', 'support'].includes(normalized)) return 2
  if (['次要', 'minor'].includes(normalized)) return 3
  return 4
}

const toRecordArray = (value: unknown): Record<string, unknown>[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter(isRecord)
}

const blueprintTitle = computed(() => displayText(props.blueprint?.title, '未命名蓝图'))
const synopsis = computed(() => displayText(props.blueprint?.one_sentence_summary, '暂无一句话梗概'))
const fullSynopsis = computed(() => displayText(props.blueprint?.full_synopsis, '暂无完整梗概'))

const heroTags = computed(() => {
  const tags = [
    displayText(props.blueprint?.genre, ''),
    displayText(props.blueprint?.style, ''),
    displayText(props.blueprint?.tone, ''),
    displayText(props.blueprint?.target_audience, ''),
  ].filter(Boolean)

  return tags.length ? tags : ['暂无标签']
})

const overviewFields = computed(() => [
  { label: '题材', value: displayText(props.blueprint?.genre, '未填写') },
  { label: '风格', value: displayText(props.blueprint?.style, '未填写') },
  { label: '语气', value: displayText(props.blueprint?.tone, '未填写') },
  { label: '受众', value: displayText(props.blueprint?.target_audience, '未填写') },
])

const worldSetting = computed<Record<string, unknown> | null>(() => {
  return isRecord(props.blueprint?.world_setting) ? props.blueprint!.world_setting : null
})

const worldCoreRules = computed(() => {
  return displayText(worldSetting.value?.core_rules, '暂无世界观核心规则')
})

const worldLocations = computed<WorldItem[]>(() => {
  return toRecordArray(worldSetting.value?.key_locations).map((item, index) => ({
    name: displayText(item.name, `地点 ${index + 1}`),
    description: displayText(item.description, '暂无说明'),
  }))
})

const worldFactions = computed<WorldItem[]>(() => {
  return toRecordArray(worldSetting.value?.factions).map((item, index) => ({
    name: displayText(item.name, `势力 ${index + 1}`),
    description: displayText(item.description, '暂无说明'),
  }))
})

const chapterOutline = computed<ChapterItem[]>(() => {
  const outline = Array.isArray(props.blueprint?.chapter_outline) ? props.blueprint!.chapter_outline : []

  return outline.map((chapter, index) => ({
    number: Number((chapter as { chapter_number?: unknown }).chapter_number) || index + 1,
    title: displayText((chapter as { title?: unknown }).title, `第 ${index + 1} 章`),
    summary: displayText((chapter as { summary?: unknown }).summary, '暂无章节摘要'),
  }))
})

const characterCards = computed<CharacterCard[]>(() => {
  const characters: unknown[] = Array.isArray(props.blueprint?.characters)
    ? (props.blueprint!.characters as unknown[])
    : []

  return characters.map((item, index) => {
    if (typeof item === 'string') {
      return {
        name: item.trim() || `角色 ${index + 1}`,
        role: '角色',
        importance: '待补充',
        summary: '',
        spotlight: '',
        details: [],
      }
    }

    if (!isRecord(item)) {
      return {
        name: `角色 ${index + 1}`,
        role: '角色',
        importance: '待补充',
        summary: '',
        spotlight: '',
        details: [],
      }
    }

    const nestedDescription = isRecord(item.description) ? item.description : null
    const summary =
      optionalText(item.summary) ||
      optionalText(item.description) ||
      optionalText(nestedDescription?.summary) ||
      optionalText(nestedDescription?.description) ||
      ''

    const details: DetailItem[] = [
      { label: '身份', value: optionalText(item.identity) || optionalText(nestedDescription?.identity) },
      { label: '定位', value: optionalText(item.archetype) || optionalText(item.position) || optionalText(item.kind) },
      { label: '性格', value: optionalText(item.personality) || optionalText(nestedDescription?.personality) },
      { label: '目标', value: optionalText(item.goals) || optionalText(item.goal) || optionalText(nestedDescription?.goal) },
      { label: '动机', value: optionalText(item.core_motivation) || optionalText(item.motivation) },
      { label: '恐惧/缺口', value: optionalText(item.fear_or_wound) || optionalText(item.flaw) || optionalText(item.weakness) },
      { label: '外在目标', value: optionalText(item.external_goal) },
      { label: '隐藏信息', value: optionalText(item.hidden_secret) || optionalText(item.secret) },
      { label: '成长弧', value: optionalText(item.growth_arc) || optionalText(item.arc) },
      { label: '关系钩子', value: optionalText(item.relationship_hook) },
      { label: '能力', value: optionalText(item.abilities) || optionalText(item.skills) || optionalText(nestedDescription?.abilities) },
      {
        label: '关系',
        value:
          optionalText(item.relationship_to_protagonist) ||
          optionalText(item.relationship) ||
          optionalText(nestedDescription?.relationship_to_protagonist),
      },
    ].filter((detail) => detail.value)

    return {
      name: displayText(item.name, `角色 ${index + 1}`),
      role: optionalText(item.role) || optionalText(item.character_role) || '角色',
      importance: optionalText(item.importance) || optionalText(item.priority) || '待补充',
      summary,
      spotlight: maybeText(item.first_highlight_chapter)
        ? `首次高光：第 ${maybeText(item.first_highlight_chapter)} 章`
        : '',
      details,
    }
  }).sort((left, right) => {
    const weightDiff = importanceWeight(left.importance) - importanceWeight(right.importance)
    if (weightDiff !== 0) return weightDiff
    return left.name.localeCompare(right.name, 'zh-Hans-CN')
  })
})

const relationshipCards = computed<RelationshipCard[]>(() => {
  const relationships: unknown[] = Array.isArray(props.blueprint?.relationships)
    ? (props.blueprint!.relationships as unknown[])
    : []

  return relationships.map((item, index) => {
    if (!isRecord(item)) {
      return {
        from: `关系 ${index + 1}`,
        to: '待补充',
        description: '暂无关键信息',
        relationType: '关系未定',
        currentState: '现状待补充',
        tension: '张力待补充',
        expectedChange: '变化待补充',
        keyTrigger: '触发事件待补充',
      }
    }

    return {
      from: displayText(item.character_from || item.source || item.from, `角色 ${index + 1}`),
      to: displayText(item.character_to || item.target || item.to, '待补充'),
      description: displayText(item.description || item.summary, '暂无关键信息'),
      relationType: displayText(item.relation_type || item.relationship_type || item.type, '关系未定'),
      currentState: displayText(item.current_state || item.status, '现状待补充'),
      tension: displayText(item.tension || item.core_conflict, '张力待补充'),
      expectedChange: displayText(item.expected_change || item.direction, '变化待补充'),
      keyTrigger: displayText(item.key_trigger || item.trigger, '触发事件待补充'),
    }
  })
})

const overviewStats = computed(() => [
  {
    label: '章节数',
    value: String(chapterOutline.value.length),
    hint: '后续会按这个结构开写',
  },
  {
    label: '角色数',
    value: String(characterCards.value.length),
    hint: '核心角色卡会直接进入写作参考区',
  },
  {
    label: '当前阶段',
    value: props.isSaving ? '进入写作台' : '蓝图定稿',
    hint: '这一屏只负责最后确认或重做',
  },
  {
    label: '世界块',
    value: String((worldLocations.value.length > 0 ? 1 : 0) + (worldFactions.value.length > 0 ? 1 : 0) + (worldCoreRules.value ? 1 : 0)),
    hint: '可用世界设定块数量',
  },
])

const hasAiMessage = computed(() => {
  return optionalText(props.aiMessage).length > 0
})

const renderedAiMessage = ref('')

const renderAiMessage = (raw: string) => {
  if (!raw) {
    renderedAiMessage.value = ''
    return
  }

  renderedAiMessage.value = renderSafeMarkdown(raw)
}

watch(
  () => optionalText(props.aiMessage),
  (value) => {
    renderAiMessage(value)
  },
  { immediate: true }
)

const confirmRegenerate = async () => {
  const confirmed = await globalAlert.showConfirm('重做蓝图会覆盖当前内容，确定继续吗？', '重做蓝图确认')
  if (confirmed) {
    emit('regenerate')
  }
}

const confirmBlueprint = () => {
  if (props.isSaving || !props.blueprint) return
  emit('confirm')
}
</script>

<style scoped>
.blueprint-markdown :deep(p) {
  margin: 0 0 0.85rem;
  line-height: 1.85;
}

.blueprint-markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.blueprint-markdown :deep(h3),
.blueprint-markdown :deep(h4) {
  margin: 1rem 0 0.5rem;
  color: rgb(15 23 42);
  font-weight: 700;
}

.blueprint-markdown :deep(ul),
.blueprint-markdown :deep(ol) {
  margin: 0.85rem 0 0.85rem 1.25rem;
  padding: 0;
}

.blueprint-markdown :deep(li) {
  margin: 0.35rem 0;
  line-height: 1.75;
}

.blueprint-markdown :deep(blockquote) {
  margin: 1rem 0;
  border-left: 3px solid rgb(165 180 252);
  padding-left: 1rem;
  color: rgb(51 65 85);
}

.blueprint-markdown :deep(strong) {
  color: rgb(15 23 42);
  font-weight: 700;
}

.blueprint-markdown :deep(a) {
  color: rgb(79 70 229);
  text-decoration: none;
}

.blueprint-markdown :deep(a:hover) {
  text-decoration: underline;
}
</style>
