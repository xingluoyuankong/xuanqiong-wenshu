<template>
  <section class="space-y-6 overflow-y-auto">
    <header class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-xl font-semibold text-slate-900">联网研究中心</h2>
        <p class="mt-1 text-sm text-slate-600">全局研究、章节大纲强化研究、每章写前研究。资料按项目与类别归档，不启用本地模型。</p>
      </div>
      <button class="md-btn md-btn-filled" :disabled="saving" @click="saveConfig">{{ saving ? '保存中…' : '保存配置' }}</button>
    </header>

    <div class="grid gap-4 lg:grid-cols-3">
      <label class="space-y-2"><span class="text-sm font-medium">运行模式</span><select v-model="config.mode" class="w-full rounded-xl border p-3"><option value="auto">自动（默认）</option><option value="ask">每次询问</option><option value="off">关闭</option></select></label>
      <label class="space-y-2"><span class="text-sm font-medium">搜索服务</span><select v-model="config.search_provider" class="w-full rounded-xl border p-3"><option value="tavily">Tavily</option><option value="serper">Serper</option><option value="bing">Bing</option><option value="none">不联网</option></select></label>
      <label class="space-y-2"><span class="text-sm font-medium">最大并行查询</span><input v-model.number="config.max_parallel_queries" type="number" min="1" max="8" class="w-full rounded-xl border p-3" /></label>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <label class="space-y-2"><span class="text-sm font-medium">联网搜索 API Key（最高优先级）</span><input v-model="searchApiKey" type="password" class="w-full rounded-xl border p-3" :placeholder="config.search_api_key_masked || '输入新的搜索 API Key'" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">搜索 Base URL（可选）</span><input v-model="config.search_base_url" class="w-full rounded-xl border p-3" placeholder="留空使用服务默认地址" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">研究 LLM API Key（第二优先级）</span><input v-model="researchApiKey" type="password" class="w-full rounded-xl border p-3" :placeholder="config.research_llm_api_key_masked || '可留空并复用正文 LLM'" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">研究模型</span><input v-model="config.research_llm_model" class="w-full rounded-xl border p-3" placeholder="例如 gpt-4.1-mini" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">研究 LLM Base URL</span><input v-model="config.research_llm_base_url" class="w-full rounded-xl border p-3" /></label>
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.reuse_writing_llm" type="checkbox" /><span>独立研究 LLM 不可用时复用正文 LLM API</span></label>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <label class="space-y-2"><span class="text-sm font-medium">优先研究类别（逗号分隔）</span><input v-model="categoryPreferencesText" class="w-full rounded-xl border p-3" placeholder="history,culture,philosophy,naming" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">优先来源域名（逗号分隔，可选）</span><input v-model="preferredDomainsText" class="w-full rounded-xl border p-3" placeholder="gov.cn,edu.cn,museum.org" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">屏蔽来源域名（逗号分隔）</span><input v-model="blockedDomainsText" class="w-full rounded-xl border p-3" placeholder="低质量或不可信域名" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">每个查询最大结果数</span><input v-model.number="config.max_results_per_query" type="number" min="1" max="10" class="w-full rounded-xl border p-3" /></label>
    </div>

    <div class="grid gap-3 md:grid-cols-3">
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.global_research_enabled" type="checkbox" /><span>粗纲后全局研究</span></label>
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.enhanced_research_enabled" type="checkbox" /><span>章节大纲后强化研究</span></label>
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.chapter_research_enabled" type="checkbox" /><span>每章正文前标准研究</span></label>
    </div>

    <div class="rounded-2xl bg-amber-50 p-4 text-sm text-amber-900">提供方优先级：联网搜索 API Key → 独立研究 LLM API Key → 正文 LLM API Key。浏览器不会显示完整密钥；本地模型默认且强制禁用。</div>

    <div class="flex flex-wrap gap-3">
      <button v-for="scope in scopes" :key="scope.value" class="md-btn md-btn-outlined" :disabled="Boolean(running)" @click="run(scope.value)">{{ running === scope.value ? '运行中…' : scope.label }}</button>
      <button v-if="activeRunId" class="md-btn md-btn-outlined" @click="cancelRun">取消当前研究</button>
      <button class="md-btn md-btn-outlined" :disabled="loading" @click="load">刷新资料</button>
    </div>

    <p v-if="message" class="rounded-xl bg-slate-100 p-3 text-sm">{{ message }}</p>
    <div class="space-y-3">
      <article v-for="artifact in artifacts" :key="artifact.run_id" class="rounded-2xl border p-4">
        <div class="flex flex-wrap items-center justify-between gap-2"><strong>{{ scopeLabel(artifact.scope) }}{{ artifact.chapter_number ? ` · 第${artifact.chapter_number}章` : '' }}</strong><span class="rounded-full bg-slate-100 px-3 py-1 text-xs">{{ artifact.status }}</span></div>
        <p class="mt-2 text-sm text-slate-700">{{ artifact.summary || '暂无摘要' }}</p>
        <div class="mt-3 text-xs text-slate-500">来源 {{ artifact.sources?.length || 0 }} 条 · 归档 {{ artifact.file_manifest?.run_directory || '未生成' }}</div>
        <details v-if="artifact.sources?.length" class="mt-3"><summary class="cursor-pointer text-sm font-medium">查看来源</summary><ul class="mt-2 space-y-2"><li v-for="source in artifact.sources.slice(0, 12)" :key="source.url"><a class="text-blue-700 underline" :href="source.url" target="_blank" rel="noreferrer">{{ source.title || source.url }}</a><p class="text-xs text-slate-600">{{ source.snippet }}</p><p class="text-xs text-slate-500">可信度 {{ source.credibility_score ?? 50 }} · {{ trustLabel(source.trust_tier) }} · 交叉来源 {{ source.cross_source_count ?? 1 }}</p></li></ul></details>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { NovelAPI, type ResearchArtifact, type ResearchConfig } from '@/api/novel'
const props = defineProps<{ projectId: string }>()
const config = reactive<ResearchConfig>({ mode: 'auto', enabled: true, search_provider: 'tavily', reuse_writing_llm: true, local_model_enabled: false, global_research_enabled: true, enhanced_research_enabled: true, chapter_research_enabled: true, max_parallel_queries: 4, max_results_per_query: 5 })
const searchApiKey = ref('')
const researchApiKey = ref('')
const categoryPreferencesText = ref('')
const preferredDomainsText = ref('')
const blockedDomainsText = ref('')
const artifacts = ref<ResearchArtifact[]>([])
const loading = ref(false)
const saving = ref(false)
const running = ref<string | false>(false)
const activeRunId = ref('')
let pollTimer: ReturnType<typeof setTimeout> | null = null
const message = ref('')
const scopes = [{ value: 'global', label: '运行全局研究' }, { value: 'enhanced', label: '运行强化研究' }, { value: 'chapter', label: '运行章节研究' }]
const load = async () => { loading.value = true; try { Object.assign(config, await NovelAPI.getResearchConfig(props.projectId)); categoryPreferencesText.value = (config.category_preferences || []).join(','); preferredDomainsText.value = (config.preferred_domains || []).join(','); blockedDomainsText.value = (config.blocked_domains || []).join(','); artifacts.value = await NovelAPI.listResearchArtifacts(props.projectId) } finally { loading.value = false } }
const parseList = (value: string) => value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean)
const saveConfig = async () => { saving.value = true; try { const payload: Record<string, unknown> = { ...config, category_preferences: parseList(categoryPreferencesText.value), preferred_domains: parseList(preferredDomainsText.value), blocked_domains: parseList(blockedDomainsText.value), local_model_enabled: false }; if (searchApiKey.value) payload.search_api_key = searchApiKey.value; if (researchApiKey.value) payload.research_llm_api_key = researchApiKey.value; Object.assign(config, await NovelAPI.updateResearchConfig(props.projectId, payload)); searchApiKey.value = ''; researchApiKey.value = ''; message.value = '研究配置已保存' } catch (error) { message.value = error instanceof Error ? error.message : '保存失败' } finally { saving.value = false } }
const pollRun = async (runId: string) => {
  const job = await NovelAPI.getResearchJobStatus(props.projectId, runId)
  if (['queued', 'running'].includes(job.status)) {
    pollTimer = setTimeout(() => { void pollRun(runId).catch((error) => { message.value = error instanceof Error ? error.message : '研究状态查询失败'; running.value = false; activeRunId.value = '' }) }, 1000)
    return
  }
  activeRunId.value = ''
  running.value = false
  await load()
  message.value = job.status === 'cancelled' ? '研究任务已取消' : job.status === 'failed' ? '研究任务失败' : '研究运行完成'
}
const run = async (scope: string) => { let chapterNumber: number | undefined; if (scope === 'chapter') { const raw = window.prompt('请输入要研究的章节号', '1'); if (!raw) return; chapterNumber = Number(raw); if (!Number.isInteger(chapterNumber) || chapterNumber < 1) { message.value = '章节号无效'; return } } running.value = scope; try { const job = await NovelAPI.startResearchJob(props.projectId, { scope, chapter_number: chapterNumber, consent: true, force: true, trigger: 'manual_ui' }); activeRunId.value = job.run_id; await pollRun(job.run_id) } catch (error) { message.value = error instanceof Error ? error.message : '研究失败'; running.value = false; activeRunId.value = '' } }
const cancelRun = async () => { if (!activeRunId.value) return; const runId = activeRunId.value; if (pollTimer) clearTimeout(pollTimer); await NovelAPI.cancelResearchJob(props.projectId, runId); activeRunId.value = ''; running.value = false; message.value = '研究任务已取消' }
const scopeLabel = (scope: string) => ({ global: '全局研究', enhanced: '强化研究', chapter: '章节研究' }[scope] || scope)
const trustLabel = (tier?: string) => ({ official_or_education: '官方/教育', academic_index: '学术索引', institutional: '机构来源', search_summary_unverified: '搜索摘要待核验' }[tier || ''] || '待核验')
onMounted(load)
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>
