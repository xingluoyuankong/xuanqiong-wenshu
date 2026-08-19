<!-- AIMETA P=世界观区_世界设定展示|R=世界观信息|NR=不含编辑功能|E=component:WorldSettingSection|X=ui|A=世界观组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-6">
    <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
      <div class="flex items-start justify-between gap-4 mb-4">
        <h3 class="text-lg font-semibold text-slate-900">{{ pick('核心规则', 'Core rules') }}</h3>
        <button
          v-if="editable"
          type="button"
          class="text-gray-400 hover:text-indigo-600 transition-colors"
          @click="emitEdit('world_setting.core_rules', pick('核心规则', 'Core rules'), worldSetting.core_rules)">
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
            <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      <p class="text-slate-600 leading-7 whitespace-pre-line">{{ worldSetting.core_rules || pick('暂无', 'None') }}</p>
    </div>

    <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
      <div class="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">{{ pick('世界观总览', 'World setting overview') }}</h3>
          <p class="text-sm text-slate-500 mt-1">{{ pick('用地点、阵营与规则快速检查世界设定是否完整', 'Check completeness at a glance through locations, factions, and rules') }}</p>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{{ pick('规则密度', 'Rule density') }}</p>
          <p class="text-2xl font-bold text-slate-900">{{ rulesCount }}</p>
          <p class="text-sm text-slate-500 mt-1">{{ pick('核心规则/设定点', 'Core rules / setting points') }}</p>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{{ pick('关键地点', 'Key locations') }}</p>
          <p class="text-2xl font-bold text-slate-900">{{ locations.length }}</p>
          <p class="text-sm text-slate-500 mt-1">{{ pick('可直接进入编辑器维护', 'Editable directly in the editor') }}</p>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{{ pick('主要阵营', 'Main factions') }}</p>
          <p class="text-2xl font-bold text-slate-900">{{ factions.length }}</p>
          <p class="text-sm text-slate-500 mt-1">{{ pick('观察冲突结构是否充分', 'Check whether the conflict structure is rich enough') }}</p>
        </div>
      </div>

      <div v-if="systemCards.length" class="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div
          v-for="card in systemCards"
          :key="card.label"
          class="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-4"
        >
          <p class="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-2">{{ card.label }}</p>
          <p class="text-sm leading-6 text-emerald-950 whitespace-pre-line">{{ card.value }}</p>
        </div>
      </div>

      <div class="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4">
          <div class="flex items-center justify-between mb-3">
            <h4 class="text-sm font-semibold text-slate-900">{{ pick('地点分布', 'Location spread') }}</h4>
            <button
              v-if="editable"
              type="button"
              class="text-xs font-medium text-indigo-600 hover:text-indigo-700"
              @click="emitEdit('world_setting.key_locations', pick('关键地点', 'Key locations'), worldSetting.key_locations)"
            >
              {{ pick('编辑地点', 'Edit locations') }}
            </button>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="(item, index) in locations.slice(0, 8)"
              :key="index"
              class="inline-flex items-center rounded-full bg-white px-3 py-1 text-xs text-slate-700 border border-indigo-100"
            >
              {{ item.title }}
            </span>
            <span v-if="!locations.length" class="text-sm text-slate-400">{{ pick('暂无地点数据', 'No location data yet') }}</span>
          </div>
        </div>

        <div class="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-4">
          <div class="flex items-center justify-between mb-3">
            <h4 class="text-sm font-semibold text-slate-900">{{ pick('阵营关系面', 'Faction relations') }}</h4>
            <button
              v-if="editable"
              type="button"
              class="text-xs font-medium text-emerald-600 hover:text-emerald-700"
              @click="emitEdit('world_setting.factions', pick('主要阵营', 'Main factions'), worldSetting.factions)"
            >
              {{ pick('编辑阵营', 'Edit factions') }}
            </button>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="(item, index) in factions.slice(0, 8)"
              :key="index"
              class="inline-flex items-center rounded-full bg-white px-3 py-1 text-xs text-slate-700 border border-emerald-100"
            >
              {{ item.title }}
            </span>
            <span v-if="!factions.length" class="text-sm text-slate-400">{{ pick('暂无阵营数据', 'No faction data yet') }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center text-slate-900 font-semibold">
            <svg class="mr-2 text-indigo-500" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18"/><path d="M6 18H4a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h2v7Z"/><path d="M18 18h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2h-2v7Z"/></svg>
            <span>{{ pick('关键地点', 'Key locations') }}</span>
          </div>
          <button
            v-if="editable"
            type="button"
            class="text-gray-400 hover:text-indigo-600 transition-colors"
            @click="emitEdit('world_setting.key_locations', pick('关键地点', 'Key locations'), worldSetting.key_locations)">
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
              <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
        <ul class="space-y-4 text-sm text-slate-600">
          <li v-for="(item, index) in locations" :key="index" class="bg-slate-50 border border-slate-100 rounded-xl p-4">
            <strong class="block text-slate-800 mb-1">{{ item.title }}</strong>
            <span class="text-xs text-slate-500 leading-5">{{ item.description }}</span>
          </li>
          <li v-if="!locations.length" class="text-slate-400 text-sm">{{ pick('暂无数据', 'No data yet') }}</li>
        </ul>
      </div>

      <div class="bg-white/95 rounded-2xl shadow-sm border border-slate-200 p-6">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center text-slate-900 font-semibold">
            <svg class="mr-2 text-indigo-500" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>{{ pick('主要阵营', 'Main factions') }}</span>
          </div>
          <button
            v-if="editable"
            type="button"
            class="text-gray-400 hover:text-indigo-600 transition-colors"
            @click="emitEdit('world_setting.factions', pick('主要阵营', 'Main factions'), worldSetting.factions)">
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
              <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
        <ul class="space-y-4 text-sm text-slate-600">
          <li v-for="(item, index) in factions" :key="index" class="bg-slate-50 border border-slate-100 rounded-xl p-4">
            <strong class="block text-slate-800 mb-1">{{ item.title }}</strong>
            <span class="text-xs text-slate-500 leading-5">{{ item.description }}</span>
          </li>
          <li v-if="!factions.length" class="text-slate-400 text-sm">{{ pick('暂无数据', 'No data yet') }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { useLocale } from '@/composables/useLocale'

interface ListItem {
  title: string
  description: string
}

interface SystemCard {
  label: string
  value: string
}

const props = defineProps<{
  data: Record<string, any> | null
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', payload: { field: string; title: string; value: any }): void
}>()

const worldSetting = computed(() => props.data?.world_setting || {})

const { pick } = useLocale()

const formatStructuredValue = (value: any): string => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value
      .map(item => formatStructuredValue(item))
      .filter(Boolean)
      .join(pick('；', '; '))
  }
  if (value && typeof value === 'object') {
    return Object.entries(value)
      .map(([key, nested]) => {
        const nestedText = formatStructuredValue(nested)
        return nestedText ? `${key}${pick('：', ': ')}${nestedText}` : ''
      })
      .filter(Boolean)
      .join('\n')
  }
  return ''
}

const normalizeList = (source: any): ListItem[] => {
  if (!source) return []
  if (Array.isArray(source)) {
    return source.map((item: any) => {
      if (typeof item === 'string') {
        // '：' 是后端数据里的分隔符，属于解析规则而非展示文案，不随语言变化
        const [title, ...rest] = item.split('：')
        return {
          title: title || item,
          description: rest.join('：') || pick('暂无描述', 'No description')
        }
      }
      return {
        title: item?.name || pick('未命名', 'Unnamed'),
        description: item?.description || item?.details || pick('暂无描述', 'No description')
      }
    })
  }
  return []
}

const locations = computed(() => normalizeList(worldSetting.value?.key_locations))
const factions = computed(() => normalizeList(worldSetting.value?.factions))
const systemCards = computed<SystemCard[]>(() => {
  // 键是后端字段名保持原文；标签在 computed 内经 pick 求值，切换语言即刷新
  const fields: Array<[string, string]> = [
    ['era_background', pick('时代背景', 'Era background')],
    ['world_structure', pick('世界结构', 'World structure')],
    ['power_system', pick('力量体系', 'Power system')],
    ['survival_system', pick('生存体系', 'Survival system')],
    ['life_system', pick('生活体系', 'Life system')],
    ['culture_system', pick('文化体系', 'Culture system')],
    ['civilization_system', pick('文明体系', 'Civilization system')],
    ['economy_system', pick('经济体系', 'Economy system')],
    ['social_structure', pick('社会结构', 'Social structure')],
    ['resource_system', pick('资源体系', 'Resource system')],
    ['belief_system', pick('信仰体系', 'Belief system')],
    ['geography_system', pick('地理体系', 'Geography system')],
    ['faction_order', pick('势力秩序', 'Faction order')],
  ]

  return fields
    .map(([key, label]) => ({ label, value: formatStructuredValue(worldSetting.value?.[key]) }))
    .filter(item => item.value)
})
const rulesCount = computed(() => {
  const raw = String(worldSetting.value?.core_rules || '').trim()
  if (!raw) return 0
  return raw
    .split(/\n+/)
    .map(item => item.trim())
    .filter(Boolean).length
})

const emitEdit = (field: string, title: string, value: any) => {
  if (!props.editable) return
  emit('edit', { field, title, value })
}
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'WorldSettingSection'
})
</script>
