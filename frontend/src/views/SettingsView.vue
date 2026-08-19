<template>
  <div class="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-6xl space-y-5">
      <header class="xq-page-topbar xq-page-topbar--settings rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="max-w-3xl">
            <p class="text-xs font-bold uppercase tracking-[0.3em] text-indigo-600">{{ pick('LLM 配置', 'LLM configuration') }}</p>
            <h1 class="mt-2 text-3xl font-bold tracking-tight">{{ pick('模型地址、Key 和模型组', 'Endpoints, keys, and model groups') }}</h1>
            <p class="mt-3 text-sm leading-7 text-slate-600">{{ pick(
              '这里只处理 LLM 相关配置，不再塞多余导航。系统配置和 LLM 配置是并列关系；在管理台里也作为两个并列入口。',
              'This page only handles LLM configuration — no extra navigation. System configuration and LLM configuration sit side by side, and appear as two peer entries in the admin console.'
            ) }}</p>
          </div>
          <div class="flex flex-wrap gap-3">
            <router-link class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-700" :to="{ name: 'admin' }">{{ pick('回管理台', 'Back to admin') }}</router-link>
            <router-link class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-700" :to="{ name: 'settings' }">{{ pick('系统配置', 'System configuration') }}</router-link>
            <router-link class="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white" :to="{ name: 'workspace-entry' }">{{ pick('返回主页', 'Back to home') }}</router-link>
          </div>
        </div>
      </header>

      <LLMSettings />
    </div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useLocale } from '@/composables/useLocale'

const { pick } = useLocale()

const LLMSettings = defineAsyncComponent(() => import('@/components/LLMSettings.vue'))
</script>
