<template>
  <div class="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-7xl">
      <header class="mb-6 rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
        <p class="text-xs font-bold uppercase tracking-[0.3em] text-slate-500">系统配置</p>
        <h1 class="mt-2 text-3xl font-bold tracking-tight">全站系统参数</h1>
        <p class="mt-3 max-w-3xl leading-7 text-slate-600">这里放系统级参数。LLM 配置只是系统配置中的一个独立小项，已单独放到“LLM 配置”页面，避免和管理台混在一起。</p>
        <div class="mt-5 flex flex-wrap gap-3">
          <router-link class="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-bold text-white" :to="{ name: 'llm-settings' }">打开 LLM 配置</router-link>
          <router-link class="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-700" :to="{ name: 'workspace-entry' }">返回主页</router-link>
        </div>
      </header>
      <SettingsManagement />
    </div>
  </div>
</template>

<script setup lang="ts">
import SettingsManagement from '@/components/admin/SettingsManagement.vue'
</script>
