<template>
  <div class="admin-layout" :class="{ 'admin-layout--collapsed': collapsed }">
    <aside class="admin-sider" :class="{ 'admin-sider--collapsed': collapsed }">
      <button v-if="!collapsed" type="button" class="admin-sider__backdrop" aria-label="关闭侧栏" @click="collapsed = true"></button>
      <div class="admin-sider__panel">
        <button type="button" class="admin-sider__toggle" :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed">{{ collapsed ? '›' : '‹' }}</button>
        <div class="sider-header"><span v-if="!collapsed" class="logo">玄穹文枢管理台</span><span v-else class="logo-small">管理</span></div>
        <n-menu :value="activeKey" :options="menuOptions" :collapsed="collapsed" :collapsed-width="64" :accordion="true" @update:value="handleMenuSelect" />
      </div>
    </aside>

    <div class="admin-main">
      <header class="admin-header">
        <div class="header-content">
          <div class="header-main">
            <button type="button" class="mobile-trigger" aria-label="切换侧栏" @click="collapsed = !collapsed">☰</button>
            <div>
              <p class="header-kicker">{{ pick('玄穹文枢管理台', 'Xuanqiong Console') }}</p>
              <span class="header-title">{{ currentMenuLabel }}</span>
            </div>
          </div>
          <div class="header-actions">
            <span class="header-subtitle">{{ currentMenuDescription }}</span>
            <button type="button" class="locale-btn" :title="switchLabel" @click="toggleLocale">{{ languageLabel }}</button>
            <button type="button" class="back-button" @click="router.push('/')">{{ pick('返回主页', 'Home') }}</button>
          </div>
        </div>
      </header>
      <main class="admin-content"><div class="content-scroll"><component :is="activeComponent" /></div></main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NMenu, type MenuOption } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { useLocale } from '@/composables/useLocale'

const collapsed = ref(false)
const activeKey = ref<MenuKey>('statistics')
const router = useRouter()
const route = useRoute()
const { languageLabel, switchLabel, toggleLocale, pick } = useLocale()

type MenuKey = 'statistics' | 'diagnostics' | 'prompts' | 'novels' | 'runtime-logs' | 'logs' | 'settings' | 'llm-settings'

const components: Partial<Record<MenuKey, ReturnType<typeof defineAsyncComponent>>> = {
  statistics: defineAsyncComponent(() => import('../components/admin/Statistics.vue')),
  diagnostics: defineAsyncComponent(() => import('../components/admin/RootCauseDiagnostics.vue')),
  prompts: defineAsyncComponent(() => import('../components/admin/PromptManagement.vue')),
  novels: defineAsyncComponent(() => import('../components/admin/NovelManagement.vue')),
  'runtime-logs': defineAsyncComponent(() => import('../components/admin/RuntimeLogManagement.vue')),
  logs: defineAsyncComponent(() => import('../components/admin/UpdateLogManagement.vue')),
  settings: defineAsyncComponent(() => import('../components/admin/SystemSettingsPanel.vue')),
  'llm-settings': defineAsyncComponent(() => import('../components/admin/LLMSettingsPanel.vue')),
}

const labels = computed<Record<MenuKey, string>>(() => ({
  statistics: pick('数据总览', 'Overview'),
  diagnostics: pick('故障诊断', 'Diagnostics'),
  prompts: pick('提示词管理', 'Prompt Management'),
  novels: pick('小说管理', 'Novel Management'),
  'runtime-logs': pick('运行日志', 'Runtime Logs'),
  logs: pick('更新日志', 'Update Logs'),
  settings: pick('系统配置', 'System Settings'),
  'llm-settings': pick('LLM 配置', 'LLM Settings'),
}))
const descriptions = computed<Record<MenuKey, string>>(() => ({
  statistics: pick('管理台总览。系统配置和 LLM 配置在上方是并列入口，不互相归属。', 'Overview of the console. System Settings and LLM Settings are parallel entries.'),
  diagnostics: pick('排查后端、接口和生成链路问题。', 'Investigate backend, API, and generation pipeline issues.'),
  prompts: pick('管理会影响生成链路的提示词。', 'Manage prompts that affect generation pipelines.'),
  novels: pick('后台查看和管理小说项目。', 'Inspect and manage novel projects.'),
  'runtime-logs': pick('简略日志只看关键阶段；详细区直接看后台运行流水。', 'Brief logs show milestones; detailed area shows backend runtime stream.'),
  logs: pick('面向用户展示的更新说明。', 'User-facing update notes.'),
  settings: pick('和数据总览、故障诊断一样，属于管理后台并列入口。', 'Parallel admin entry for system configuration.'),
  'llm-settings': pick('和提示词管理、小说管理一样，属于管理后台并列入口。', 'Parallel admin entry for LLM configuration.'),
}))
const icons: Record<MenuKey, string> = { statistics: '📊', diagnostics: '🧪', prompts: '📝', novels: '📚', 'runtime-logs': '📡', logs: '📌', settings: '⚙️', 'llm-settings': '🤖' }
const iconRenderers = Object.fromEntries(Object.entries(icons).map(([key, icon]) => [key, () => h('span', { class: 'menu-icon' }, icon)])) as Record<MenuKey, () => any>
const menuOptions = computed<MenuOption[]>(() => (Object.keys(labels.value) as MenuKey[]).map(key => ({ key, label: labels.value[key], icon: iconRenderers[key] })))
const isMenuKey = (key: string): key is MenuKey => ['statistics', 'diagnostics', 'prompts', 'novels', 'runtime-logs', 'logs', 'settings', 'llm-settings'].includes(key)

function syncActiveKeyWithRoute() { const tab = route.query.tab; if (typeof tab === 'string' && isMenuKey(tab)) activeKey.value = tab }
function handleMenuSelect(key: string) {
  if (!isMenuKey(key)) return
  activeKey.value = key
  const query: Record<string, string> = { tab: key }
  if (key === 'runtime-logs' && typeof route.query.project_id === 'string') query.project_id = route.query.project_id
  if (key === 'runtime-logs' && typeof route.query.chapter === 'string') query.chapter = route.query.chapter
  router.replace({ name: 'admin', query })
}
const activeComponent = computed(() => components[activeKey.value] || components.statistics)
const currentMenuLabel = computed(() => labels.value[activeKey.value])
const currentMenuDescription = computed(() => descriptions.value[activeKey.value])
const updateCollapsedByWidth = () => { collapsed.value = window.innerWidth < 992 }
onMounted(() => { updateCollapsedByWidth(); window.addEventListener('resize', updateCollapsedByWidth); syncActiveKeyWithRoute() })
onBeforeUnmount(() => window.removeEventListener('resize', updateCollapsedByWidth))
watch(() => route.query.tab, syncActiveKeyWithRoute)
</script>

<style scoped>
.admin-layout { display:flex; min-height:100vh; background:#f5f5f7; }
.admin-main { min-width:0; flex:1; display:flex; flex-direction:column; min-height:100vh; }
.admin-sider { position:relative; width:240px; flex-shrink:0; }
.admin-sider__panel { position:relative; z-index:2; display:flex; height:100vh; flex-direction:column; border-right:1px solid #e5e7eb; background:#fff; transition:width .2s ease, transform .2s ease; }
.admin-layout:not(.admin-layout--collapsed) .admin-sider__panel { width:240px; }
.admin-sider--collapsed .admin-sider__panel { width:64px; }
.admin-sider__toggle { position:absolute; top:14px; right:12px; z-index:3; display:inline-flex; height:32px; width:32px; align-items:center; justify-content:center; border:1px solid #e5e7eb; border-radius:9999px; background:#fff; color:#475569; cursor:pointer; box-shadow:0 4px 14px rgba(15,23,42,.08); }
.admin-sider__backdrop { display:none; }
.sider-header { height:64px; display:flex; align-items:center; justify-content:center; padding:0 12px; font-weight:800; letter-spacing:.08em; color:#111827; }
.logo { font-size:1.05rem; }
.logo-small { font-size:.9rem; }
.admin-header { background:rgba(255,255,255,.92); backdrop-filter:blur(8px); border-bottom:1px solid #e5e7eb; padding:0 20px 14px; }
.header-content { display:flex; min-height:72px; width:100%; align-items:center; justify-content:space-between; gap:16px; }
.header-main, .header-actions { display:flex; align-items:center; gap:12px; }
.header-kicker { margin:0 0 2px; font-size:12px; color:#64748b; font-weight:800; letter-spacing:.16em; }
.header-title { font-size:1.2rem; font-weight:800; color:#111827; }
.header-subtitle { font-size:.92rem; color:#6b7280; }
.config-link, .back-button, .mobile-trigger, .locale-btn { display:inline-flex; align-items:center; justify-content:center; border:1px solid #cbd5e1; border-radius:9999px; background:#fff; color:#334155; cursor:pointer; }
.locale-btn, .config-link { min-height:36px; padding:0 16px; font-size:.875rem; font-weight:700; }
.config-link:hover, .locale-btn:hover { background:#eef2ff; border-color:#c7d2fe; color:#3730a3; }
.back-button { min-height:34px; padding:0 14px; font-size:.875rem; font-weight:700; }
.admin-content { flex:1; min-height:0; background:#f5f5f7; }
.content-scroll { height:100%; overflow:auto; padding:24px; box-sizing:border-box; }
.menu-icon { font-size:1.1rem; }
.mobile-trigger { display:none; height:34px; width:34px; padding:0; }
@media (max-width:991px) { .admin-layout { position:relative; } .admin-sider { position:absolute; inset:0 auto 0 0; width:0; z-index:30; } .admin-sider__panel { box-shadow:0 24px 60px -24px rgba(15,23,42,.4); transform:translateX(-100%); width:240px !important; } .admin-layout:not(.admin-layout--collapsed) .admin-sider__panel { transform:translateX(0); } .admin-sider__backdrop { position:fixed; inset:0; display:block; border:0; background:rgba(15,23,42,.38); } .admin-sider--collapsed .admin-sider__backdrop, .admin-sider__toggle { display:none; } .content-scroll { padding:16px; } .mobile-trigger { display:inline-flex; } .header-content { min-height:auto; flex-direction:column; align-items:stretch; padding:12px 0; } .header-main, .header-actions { justify-content:space-between; } }
</style>


