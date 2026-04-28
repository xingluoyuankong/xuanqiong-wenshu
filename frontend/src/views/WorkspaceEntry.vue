<template>
  <main class="entry-page">
    <section class="entry-hero">
      <div class="entry-hero__copy">
        <p class="entry-kicker">玄穹文枢 · AI 长篇小说工作台</p>
        <h1>从灵感、大纲到章节成稿，一条线完成。</h1>
        <p class="entry-hero__desc">
          首页只保留清晰入口：灵感模式负责把想法收束成蓝图；小说项目负责继续写作；管理台负责数据、日志和诊断；系统配置与 LLM 配置独立维护。
        </p>
        <div class="entry-actions">
          <button type="button" class="entry-btn entry-btn--primary" @click="startPrimaryAction">{{ primaryActionLabel }}</button>
          <button type="button" class="entry-btn entry-btn--ghost" @click="go('/inspiration')">新建灵感项目</button>
          <button type="button" class="entry-btn entry-btn--ghost" @click="go('/workspace')">查看全部小说</button>
        </div>
      </div>
      <aside class="entry-hero__status">
        <span class="status-dot"></span>
        <p>创作流水线</p>
        <strong>灵感 → 蓝图 → 章节 → 评审 → 定稿</strong>
        <small>全局导航已按真实路由对齐，不再把系统配置/LLM 配置误导到管理台 Tab。</small>
      </aside>
    </section>

    <section class="entry-grid" aria-label="主功能入口">
      <button v-for="item in mainFunctions" :key="item.title" type="button" class="entry-card" @click="go(item.to)">
        <span class="entry-card__icon">{{ item.icon }}</span>
        <span class="entry-card__label">{{ item.label }}</span>
        <strong>{{ item.title }}</strong>
        <small>{{ item.desc }}</small>
      </button>
    </section>

    <section class="recent-panel">
      <div class="panel-head">
        <div>
          <p class="entry-kicker">最近项目</p>
          <h2>继续创作</h2>
          <span>展示最近 5 本小说；未完成蓝图的灵感项目会回到灵感模式。</span>
        </div>
        <button type="button" class="entry-btn entry-btn--soft" @click="reloadProjects">刷新列表</button>
      </div>

      <div v-if="bootstrapLoading" class="entry-empty">正在加载小说列表……</div>
      <div v-else-if="bootstrapError" class="entry-empty entry-empty--error">{{ bootstrapError }}</div>
      <div v-else-if="!recentProjects.length" class="entry-empty">暂无小说。建议先进入灵感模式，把一个核心点子收束成蓝图。</div>
      <div v-else class="project-list">
        <article v-for="project in recentProjects" :key="project.id" class="project-row">
          <div class="project-main" @click="enterProject(project)">
            <strong>{{ project.title }}</strong>
            <span>{{ projectProgress(project) }} · {{ formatDate(project.last_edited) }}</span>
          </div>
          <div class="project-actions">
            <button type="button" @click="enterProject(project)">进入创作</button>
            <button type="button" @click="openRuntimeLogs(project.id)">运行日志</button>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '../stores/novel'
import type { NovelProjectSummary } from '@/api/novel'

const router = useRouter()
const novelStore = useNovelStore()
const bootstrapLoading = ref(true)
const bootstrapError = ref('')

const projects = computed(() =>
  [...novelStore.projects].sort((a, b) => parseTime(b.last_edited) - parseTime(a.last_edited)),
)
const recentProjects = computed(() => projects.value.slice(0, 5))
const leadProject = computed(() => recentProjects.value[0] ?? null)
const primaryActionLabel = computed(() => (leadProject.value ? '继续最近小说' : '开始灵感创作'))

const mainFunctions = [
  { icon: '✦', label: '从 0 到 1', title: '灵感模式', desc: '对话式梳理题材、人物、冲突，并生成小说蓝图。', to: '/inspiration' },
  { icon: '📚', label: '项目总览', title: '小说项目', desc: '查看全部小说，继续章节生成、评审和定稿。', to: '/workspace' },
  { icon: '✍', label: '风格资产', title: '文风中心', desc: '导入外部作品，学习并沉淀可复用文风画像。', to: '/style-center' },
  { icon: '🧭', label: '运营后台', title: '管理台', desc: '小说管理、提示词、运行日志、统计与根因诊断。', to: '/admin' },
  { icon: '⚙', label: '系统参数', title: '系统配置', desc: '维护全站限制、默认参数和非模型类配置。', to: '/settings' },
  { icon: '🤖', label: '模型接入', title: 'LLM 配置', desc: '配置模型地址、Key、模型组，并做连通性检查。', to: '/llm-settings' },
]

function go(to: string) {
  router.push(to)
}
function parseTime(value: string | null | undefined) {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? 0 : time
}
function formatDate(value: string | null | undefined) {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(date)
}
function projectProgress(project: NovelProjectSummary) {
  return project.total_chapters ? `${project.completed_chapters}/${project.total_chapters} 章` : '蓝图未完成'
}
function startPrimaryAction() {
  const project = leadProject.value
  if (project) enterProject(project)
  else go('/inspiration')
}
function enterProject(project: NovelProjectSummary) {
  if (project.title === '未命名灵感' || project.total_chapters === 0) {
    router.push(`/inspiration?project_id=${project.id}`)
    return
  }
  router.push(`/novel/${project.id}`)
}
function openRuntimeLogs(projectId: string) {
  router.push({ path: '/admin', query: { tab: 'runtime-logs', project_id: projectId } })
}
async function reloadProjects() {
  bootstrapLoading.value = true
  bootstrapError.value = ''
  try {
    await novelStore.loadProjects()
  } catch (error) {
    bootstrapError.value = error instanceof Error ? error.message : '加载小说列表失败'
  } finally {
    bootstrapLoading.value = false
  }
}
onMounted(reloadProjects)
</script>

<style scoped>
.entry-page { min-height: calc(100vh - 64px); padding: 28px; background: radial-gradient(circle at 8% 0%, rgba(99,102,241,.16), transparent 30%), radial-gradient(circle at 94% 8%, rgba(20,184,166,.14), transparent 30%), #f8fafc; color: #0f172a; }
.entry-hero, .recent-panel { max-width: 1180px; margin: 0 auto 22px; border: 1px solid rgba(148,163,184,.22); border-radius: 32px; background: rgba(255,255,255,.88); box-shadow: 0 22px 70px rgba(15,23,42,.08); backdrop-filter: blur(16px); }
.entry-hero { display: grid; grid-template-columns: minmax(0,1fr) 330px; gap: 22px; padding: 34px; }
.entry-kicker { margin: 0; color: #4f46e5; font-size: 12px; font-weight: 900; letter-spacing: .22em; text-transform: uppercase; }
h1 { max-width: 820px; margin: 12px 0 0; font-size: clamp(34px, 5vw, 64px); line-height: 1.02; letter-spacing: -.05em; }
.entry-hero__desc { max-width: 760px; margin: 18px 0 0; color: #475569; line-height: 1.9; }
.entry-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 28px; }
.entry-btn { border: 0; border-radius: 16px; padding: 12px 18px; font-weight: 800; cursor: pointer; transition: .18s ease; }
.entry-btn:hover { transform: translateY(-1px); }
.entry-btn--primary { background: #0f172a; color: #fff; box-shadow: 0 14px 32px rgba(15,23,42,.22); }
.entry-btn--ghost { background: #eef2ff; color: #3730a3; }
.entry-btn--soft { border: 1px solid #cbd5e1; background: #fff; color: #334155; }
.entry-hero__status { align-self: stretch; display: grid; align-content: end; gap: 10px; border-radius: 26px; padding: 24px; color: #fff; background: linear-gradient(145deg, #111827, #1e293b 55%, #0f766e); box-shadow: inset 0 1px rgba(255,255,255,.16); }
.entry-hero__status p, .entry-hero__status small { margin: 0; color: rgba(255,255,255,.72); line-height: 1.7; }.entry-hero__status strong { font-size: 22px; line-height: 1.35; }.status-dot { width: 12px; height: 12px; border-radius: 999px; background: #34d399; box-shadow: 0 0 0 8px rgba(52,211,153,.16); }
.entry-grid { max-width: 1180px; margin: 0 auto 22px; display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; }
.entry-card { min-height: 178px; text-align: left; border: 1px solid rgba(148,163,184,.22); border-radius: 26px; background: rgba(255,255,255,.92); padding: 22px; cursor: pointer; box-shadow: 0 14px 38px rgba(15,23,42,.06); transition: .18s ease; }
.entry-card:hover { transform: translateY(-2px); border-color: rgba(79,70,229,.35); box-shadow: 0 20px 52px rgba(79,70,229,.14); }.entry-card__icon { display: inline-flex; width: 42px; height: 42px; align-items: center; justify-content: center; border-radius: 16px; background: #eef2ff; color: #3730a3; font-size: 22px; }.entry-card__label { display: block; margin-top: 16px; color: #64748b; font-size: 12px; font-weight: 900; letter-spacing: .16em; }.entry-card strong { display: block; margin-top: 6px; font-size: 22px; }.entry-card small { display: block; margin-top: 10px; color: #64748b; line-height: 1.7; font-size: 14px; }
.recent-panel { padding: 24px; }.panel-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }.panel-head h2 { margin: 8px 0 6px; font-size: 28px; }.panel-head span { color: #64748b; }
.project-list { display: grid; gap: 10px; margin-top: 18px; }.project-row { display: flex; justify-content: space-between; gap: 14px; align-items: center; border: 1px solid #e2e8f0; border-radius: 20px; padding: 15px; background: #fbfdff; }.project-main { cursor: pointer; display: grid; gap: 6px; }.project-main strong { font-size: 17px; }.project-main span { color: #64748b; font-size: 14px; }.project-actions { display: flex; gap: 8px; flex-wrap: wrap; }.project-actions button { border: 1px solid #cbd5e1; border-radius: 12px; background: #fff; color: #334155; padding: 9px 12px; font-weight: 800; cursor: pointer; }
.entry-empty { margin-top: 18px; border: 1px dashed #cbd5e1; border-radius: 20px; padding: 24px; color: #64748b; background: #f8fafc; }.entry-empty--error { color: #b91c1c; background: #fff1f2; border-color: #fecdd3; }
@media (max-width: 980px) { .entry-hero { grid-template-columns: 1fr; } .entry-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } .project-row { align-items: stretch; flex-direction: column; } }
@media (max-width: 560px) { .entry-page { padding: 14px; } .entry-hero { padding: 24px; border-radius: 26px; } .entry-grid { grid-template-columns: 1fr; } .panel-head { flex-direction: column; } }
</style>
