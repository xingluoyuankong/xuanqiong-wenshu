<!-- AIMETA P=角色区_角色信息展示|R=角色卡片|NR=不含编辑功能|E=component:CharactersSection|X=ui|A=角色组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-slate-900">{{ pick('主要角色', 'Main characters') }}</h2>
        <p class="text-sm text-slate-500">{{ pick('不再只看蓝图初始角色，同时显示定稿后自动追踪到的动态角色与最近变化', 'Beyond the blueprint cast, this also shows characters tracked automatically after finalizing, plus their recent changes') }}</p>
      </div>
      <button
        v-if="editable"
        type="button"
        class="text-gray-400 hover:text-indigo-600 transition-colors"
        @click="emitEdit('characters', pick('主要角色', 'Main characters'), data?.characters)">
        <svg class="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
          <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
          <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
        </svg>
      </button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="bg-slate-50 rounded-2xl border border-slate-200 p-4">
        <p class="text-xs text-slate-500">{{ pick('当前可见角色', 'Visible characters') }}</p>
        <p class="text-2xl font-bold text-slate-900">{{ data?.character_count || 0 }}</p>
      </div>
      <div class="bg-slate-50 rounded-2xl border border-slate-200 p-4">
        <p class="text-xs text-slate-500">{{ pick('动态新增角色', 'Newly tracked') }}</p>
        <p class="text-2xl font-bold text-slate-900">{{ data?.dynamic_character_count || 0 }}</p>
      </div>
      <div class="bg-slate-50 rounded-2xl border border-slate-200 p-4">
        <p class="text-xs text-slate-500">{{ pick('对生成的实际作用', 'Effect on generation') }}</p>
        <p class="text-sm leading-6 text-slate-700">{{ data?.generation_usage || pick('后续写作会回读角色状态。', 'Later writing reads character state back.') }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <article
        v-for="(character, index) in characters"
        :key="index"
        class="bg-white/95 rounded-2xl border border-slate-200 shadow-sm hover:shadow-lg transition-all duration-300">
        <div class="p-6">
          <div class="flex flex-col sm:flex-row sm:items-center gap-4 mb-4">
            <div class="w-16 h-16 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 text-lg font-semibold">
              {{ character.name?.slice(0, 1) || pick('角', 'C') }}
            </div>
            <div>
              <h3 class="text-xl font-bold text-slate-900">{{ character.name || pick('未命名角色', 'Unnamed character') }}</h3>
              <p v-if="character.identity" class="text-sm text-indigo-500 font-medium">{{ character.identity }}</p>
            </div>
          </div>
          <dl class="space-y-3 text-sm text-slate-600">
            <div v-if="character.personality">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('性格', 'Personality') }}</dt>
              <dd class="leading-6">{{ character.personality }}</dd>
            </div>
            <div v-if="character.goals">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('目标', 'Goals') }}</dt>
              <dd class="leading-6">{{ character.goals }}</dd>
            </div>
            <div v-if="character.abilities">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('能力', 'Abilities') }}</dt>
              <dd class="leading-6">{{ character.abilities }}</dd>
            </div>
            <div v-if="character.relationship_to_protagonist">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('与主角的关系', 'Relation to protagonist') }}</dt>
              <dd class="leading-6">{{ character.relationship_to_protagonist }}</dd>
            </div>
            <div v-if="character.current_emotion || character.current_location || character.health_status">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('当前状态', 'Current state') }}</dt>
              <dd class="leading-6">
                <span v-if="character.current_emotion">{{ pick('情绪：', 'Emotion: ') }}{{ character.current_emotion }}</span>
                <span v-if="character.current_location">{{ pick('｜位置：', ' | Location: ') }}{{ character.current_location }}</span>
                <span v-if="character.health_status">{{ pick('｜状态：', ' | Status: ') }}{{ character.health_status }}</span>
              </dd>
            </div>
            <div v-if="character.last_active_chapter">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('最近活跃', 'Last active') }}</dt>
              <dd class="leading-6">{{ pick(`第 ${character.last_active_chapter} 章`, `Chapter ${character.last_active_chapter}`) }}</dd>
            </div>
            <div v-if="character.recent_changes?.length">
              <dt class="font-semibold text-slate-800 mb-1">{{ pick('最近变化', 'Recent changes') }}</dt>
              <dd class="leading-6">
                <ul class="list-disc pl-5 space-y-1">
                  <li v-for="(change, changeIndex) in character.recent_changes" :key="changeIndex">{{ change }}</li>
                </ul>
              </dd>
            </div>
          </dl>
        </div>
      </article>
      <div v-if="!characters.length" class="bg-white/95 rounded-2xl border border-dashed border-slate-300 p-10 text-center text-slate-400">
        {{ pick('暂无角色信息', 'No character data yet') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { useLocale } from '@/composables/useLocale'

interface CharacterItem {
  name?: string
  identity?: string
  personality?: string
  goals?: string
  abilities?: string
  relationship_to_protagonist?: string
  current_location?: string
  current_emotion?: string
  health_status?: string
  last_active_chapter?: number
  recent_changes?: string[]
}

const props = defineProps<{
  data: {
    characters?: CharacterItem[]
    character_count?: number
    dynamic_character_count?: number
    generation_usage?: string
  } | null
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', payload: { field: string; title: string; value: any }): void
}>()

const characters = computed(() => props.data?.characters || [])

const { pick } = useLocale()

const emitEdit = (field: string, title: string, value: any) => {
  if (!props.editable) return
  emit('edit', { field, title, value })
}
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'CharactersSection'
})
</script>
