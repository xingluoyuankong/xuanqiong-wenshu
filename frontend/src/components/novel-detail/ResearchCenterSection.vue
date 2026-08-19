<template>
  <section class="space-y-6 overflow-y-auto">
    <header class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-xl font-semibold text-slate-900">{{ pick('联网研究中心', 'Online research center') }}</h2>
        <p class="mt-1 text-sm text-slate-600">{{ pick('全局研究、章节大纲强化研究、每章写前研究。资料按项目与类别归档，不启用本地模型。', 'Global research, outline-enhancement research, and pre-chapter research. Material is archived per project and category; local models stay disabled.') }}</p>
      </div>
      <button class="md-btn md-btn-filled" :disabled="saving" @click="saveConfig">{{ saving ? pick('保存中…', 'Saving…') : pick('保存配置', 'Save config') }}</button>
    </header>

    <div class="grid gap-4 lg:grid-cols-3">
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('运行模式', 'Run mode') }}</span><select v-model="config.mode" class="w-full rounded-xl border p-3"><option value="auto">{{ pick('自动（默认）', 'Automatic (default)') }}</option><option value="ask">{{ pick('每次询问', 'Ask every time') }}</option><option value="off">{{ pick('关闭', 'Off') }}</option></select></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('搜索服务', 'Search provider') }}</span><select v-model="config.search_provider" class="w-full rounded-xl border p-3"><option value="tavily">Tavily</option><option value="serper">Serper</option><option value="bing">Bing</option><option value="none">{{ pick('不联网', 'Offline') }}</option></select></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('最大并行查询', 'Max parallel queries') }}</span><input v-model.number="config.max_parallel_queries" type="number" min="1" max="8" class="w-full rounded-xl border p-3" /></label>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('联网搜索 API Key（最高优先级）', 'Search API Key (highest priority)') }}</span><input v-model="searchApiKey" type="password" class="w-full rounded-xl border p-3" :placeholder="config.search_api_key_masked || pick('输入新的搜索 API Key', 'Enter a new search API Key')" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('搜索 Base URL（可选）', 'Search base URL (optional)') }}</span><input v-model="config.search_base_url" class="w-full rounded-xl border p-3" :placeholder="pick('留空使用服务默认地址', 'Leave empty to use the provider default')" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('研究 LLM API Key（第二优先级）', 'Research LLM API Key (second priority)') }}</span><input v-model="researchApiKey" type="password" class="w-full rounded-xl border p-3" :placeholder="config.research_llm_api_key_masked || pick('可留空并复用正文 LLM', 'Leave empty to reuse the draft LLM')" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('研究模型', 'Research model') }}</span><input v-model="config.research_llm_model" class="w-full rounded-xl border p-3" :placeholder="pick('例如 gpt-4.1-mini', 'e.g. gpt-4.1-mini')" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('研究 LLM Base URL', 'Research LLM base URL') }}</span><input v-model="config.research_llm_base_url" class="w-full rounded-xl border p-3" /></label>
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.reuse_writing_llm" type="checkbox" /><span>{{ pick('独立研究 LLM 不可用时复用正文 LLM API', 'Reuse the draft LLM API when the dedicated research LLM is unavailable') }}</span></label>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('优先研究类别（逗号分隔）', 'Preferred research categories (comma separated)') }}</span><input v-model="categoryPreferencesText" class="w-full rounded-xl border p-3" placeholder="history,culture,philosophy,naming" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('优先来源域名（逗号分隔，可选）', 'Preferred source domains (comma separated, optional)') }}</span><input v-model="preferredDomainsText" class="w-full rounded-xl border p-3" placeholder="gov.cn,edu.cn,museum.org" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('屏蔽来源域名（逗号分隔）', 'Blocked source domains (comma separated)') }}</span><input v-model="blockedDomainsText" class="w-full rounded-xl border p-3" :placeholder="pick('低质量或不可信域名', 'Low-quality or untrusted domains')" /></label>
      <label class="space-y-2"><span class="text-sm font-medium">{{ pick('每个查询最大结果数', 'Max results per query') }}</span><input v-model.number="config.max_results_per_query" type="number" min="1" max="10" class="w-full rounded-xl border p-3" /></label>
    </div>

    <div class="grid gap-3 md:grid-cols-3">
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.global_research_enabled" type="checkbox" /><span>{{ pick('粗纲后全局研究', 'Global research after the rough outline') }}</span></label>
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.enhanced_research_enabled" type="checkbox" /><span>{{ pick('章节大纲后强化研究', 'Enhanced research after the chapter outline') }}</span></label>
      <label class="flex items-center gap-3 rounded-xl border p-3"><input v-model="config.chapter_research_enabled" type="checkbox" /><span>{{ pick('每章正文前标准研究', 'Standard research before each chapter draft') }}</span></label>
    </div>

    <div class="rounded-2xl bg-amber-50 p-4 text-sm text-amber-900">{{ pick('提供方优先级：联网搜索 API Key → 独立研究 LLM API Key → 正文 LLM API Key。浏览器不会显示完整密钥；本地模型默认且强制禁用。', 'Provider priority: search API Key → dedicated research LLM API Key → draft LLM API Key. Full keys are never shown in the browser, and local models stay disabled.') }}</div>

    <div class="flex flex-wrap gap-3">
      <button v-for="scope in scopes" :key="scope.value" class="md-btn md-btn-outlined" :disabled="Boolean(running)" @click="run(scope.value)">{{ running === scope.value ? pick('运行中…', 'Running…') : scope.label }}</button>
      <button v-if="activeRunId" class="md-btn md-btn-outlined" @click="cancelRun">{{ pick('取消当前研究', 'Cancel current research') }}</button>
      <button class="md-btn md-btn-outlined" :disabled="loading" @click="load">{{ pick('刷新资料', 'Refresh material') }}</button>
    </div>

    <p v-if="message" class="rounded-xl bg-slate-100 p-3 text-sm">{{ message }}</p>
    <div class="space-y-3">
      <article v-for="artifact in artifacts" :key="artifact.run_id" class="rounded-2xl border p-4">
        <div class="flex flex-wrap items-center justify-between gap-2"><strong>{{ scopeLabel(artifact.scope) }}{{ artifact.chapter_number ? pick(` · 第${artifact.chapter_number}章`, ` · Chapter ${artifact.chapter_number}`) : '' }}</strong><span class="rounded-full bg-slate-100 px-3 py-1 text-xs">{{ artifact.status }}</span></div>
        <p class="mt-2 text-sm text-slate-700">{{ artifact.summary || pick('暂无摘要', 'No summary') }}</p>
        <div class="mt-3 text-xs text-slate-500">{{ pick(`来源 ${artifact.sources?.length || 0} 条 · 归档 `, `Sources: ${artifact.sources?.length || 0} · Archive: `) }}{{ artifact.file_manifest?.run_directory || pick('未生成', 'Not generated') }}</div>
        <details v-if="artifact.sources?.length" class="mt-3"><summary class="cursor-pointer text-sm font-medium">{{ pick('查看来源', 'View sources') }}</summary><ul class="mt-2 space-y-2"><li v-for="source in artifact.sources.slice(0, 12)" :key="source.url"><a class="text-blue-700 underline" :href="source.url" target="_blank" rel="noreferrer">{{ source.title || source.url }}</a><p class="text-xs text-slate-600">{{ source.snippet }}</p><p class="text-xs text-slate-500">{{ pick(`可信度 ${source.credibility_score ?? 50} · `, `Credibility ${source.credibility_score ?? 50} · `) }}{{ trustLabel(source.trust_tier) }}{{ pick(` · 交叉来源 ${source.cross_source_count ?? 1}`, ` · Cross sources ${source.cross_source_count ?? 1}`) }}</p></li></ul></details>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { NovelAPI, type ResearchArtifact, type ResearchConfig, type ResearchConfigUpdate, type ResearchScope } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'
const props = defineProps<{ projectId: string }>()
const { pick } = useLocale()
const config = reactive<ResearchConfig>({ project_id: '', mode: 'auto', enabled: true, search_provider: 'tavily', search_base_url: null, search_api_key_masked: null, search_api_key_configured: false, research_llm_base_url: null, research_llm_model: null, research_llm_api_key_masked: null, research_llm_api_key_configured: false, reuse_writing_llm: true, local_model_enabled: false, global_research_enabled: true, enhanced_research_enabled: true, chapter_research_enabled: true, max_parallel_queries: 4, max_results_per_query: 5, preferred_domains: [], blocked_domains: [], category_preferences: [], provider_priority: [] })
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
// 按钮文案必须放在 computed 里求值，否则顶层 const 会把语言锁死在首次渲染时
const scopes = computed<Array<{ value: ResearchScope; label: string }>>(() => [
  { value: 'global', label: pick('运行全局研究', 'Run global research') },
  { value: 'enhanced', label: pick('运行强化研究', 'Run enhanced research') },
  { value: 'chapter', label: pick('运行章节研究', 'Run chapter research') },
])
const load = async () => { loading.value = true; try { Object.assign(config, await NovelAPI.getResearchConfig(props.projectId)); categoryPreferencesText.value = (config.category_preferences || []).join(','); preferredDomainsText.value = (config.preferred_domains || []).join(','); blockedDomainsText.value = (config.blocked_domains || []).join(','); artifacts.value = await NovelAPI.listResearchArtifacts(props.projectId) } finally { loading.value = false } }
const parseList = (value: string) => value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean)
const saveConfig = async () => { saving.value = true; try { const payload: ResearchConfigUpdate = { mode: config.mode, enabled: config.enabled, search_provider: config.search_provider, search_base_url: config.search_base_url, research_llm_base_url: config.research_llm_base_url, research_llm_model: config.research_llm_model, reuse_writing_llm: config.reuse_writing_llm, local_model_enabled: false, global_research_enabled: config.global_research_enabled, enhanced_research_enabled: config.enhanced_research_enabled, chapter_research_enabled: config.chapter_research_enabled, max_parallel_queries: config.max_parallel_queries, max_results_per_query: config.max_results_per_query, category_preferences: parseList(categoryPreferencesText.value), preferred_domains: parseList(preferredDomainsText.value), blocked_domains: parseList(blockedDomainsText.value) }; if (searchApiKey.value) payload.search_api_key = searchApiKey.value; if (researchApiKey.value) payload.research_llm_api_key = researchApiKey.value; Object.assign(config, await NovelAPI.updateResearchConfig(props.projectId, payload)); searchApiKey.value = ''; researchApiKey.value = ''; message.value = pick('研究配置已保存', 'Research config saved') } catch (error) { message.value = error instanceof Error ? error.message : pick('保存失败', 'Save failed') } finally { saving.value = false } }
const pollRun = async (runId: string) => {
  const job = await NovelAPI.getResearchJobStatus(props.projectId, runId)
  if (['queued', 'running'].includes(job.status)) {
    pollTimer = setTimeout(() => { void pollRun(runId).catch((error) => { message.value = error instanceof Error ? error.message : pick('研究状态查询失败', 'Failed to read the research status'); running.value = false; activeRunId.value = '' }) }, 1000)
    return
  }
  activeRunId.value = ''
  running.value = false
  await load()
  message.value = job.status === 'cancelled' ? pick('研究任务已取消', 'Research job cancelled') : job.status === 'failed' ? pick('研究任务失败', 'Research job failed') : pick('研究运行完成', 'Research run finished')
}
const run = async (scope: ResearchScope) => { let chapterNumber: number | undefined; if (scope === 'chapter') { const raw = window.prompt(pick('请输入要研究的章节号', 'Enter the chapter number to research'), '1'); if (!raw) return; chapterNumber = Number(raw); if (!Number.isInteger(chapterNumber) || chapterNumber < 1) { message.value = pick('章节号无效', 'Invalid chapter number'); return } } running.value = scope; try { const job = await NovelAPI.startResearchJob(props.projectId, { scope, chapter_number: chapterNumber, consent: true, force: true, trigger: 'manual_ui' }); activeRunId.value = job.run_id; await pollRun(job.run_id) } catch (error) { message.value = error instanceof Error ? error.message : pick('研究失败', 'Research failed'); running.value = false; activeRunId.value = '' } }
const cancelRun = async () => { if (!activeRunId.value) return; const runId = activeRunId.value; if (pollTimer) clearTimeout(pollTimer); await NovelAPI.cancelResearchJob(props.projectId, runId); activeRunId.value = ''; running.value = false; message.value = pick('研究任务已取消', 'Research job cancelled') }
// 键是后端 scope / trust_tier 枚举，保持原文；值在函数体内经 pick 求值
const scopeLabel = (scope: string) => ({ global: pick('全局研究', 'Global research'), enhanced: pick('强化研究', 'Enhanced research'), chapter: pick('章节研究', 'Chapter research') }[scope] || scope)
const trustLabel = (tier?: string | null) => ({ official_or_education: pick('官方/教育', 'Official / education'), academic_index: pick('学术索引', 'Academic index'), institutional: pick('机构来源', 'Institutional source'), search_summary_unverified: pick('搜索摘要待核验', 'Search summary, unverified') }[tier || ''] || pick('待核验', 'Unverified'))
onMounted(load)
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>
