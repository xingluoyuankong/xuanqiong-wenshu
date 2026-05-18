<template>
  <main class="entry-page xq-page-canvas">
    <section class="entry-hero xq-page-topbar xq-page-topbar--entry xq-paper-grain">
      <div class="entry-hero__copy">
        <p class="entry-kicker">玄穹文书 · AI 长篇创作驾驶舱</p>
        <h1>从一个灵感，推进到可连载的完整小说工程。</h1>
        <p class="entry-hero__desc">
          这里把灵感访谈、蓝图规划、章节生成、版本评审和 LLM 配置整合在同一个创作工作流中，帮助你稳定地产出可读、可追踪、可迭代的长篇内容。
        </p>
        <div class="entry-actions">
          <XqButton size="lg" @click="startPrimaryAction">{{ primaryActionLabel }}</XqButton>
          <XqButton variant="secondary" size="lg" @click="go('/inspiration')">开启灵感模式</XqButton>
          <XqButton variant="ghost" size="lg" @click="go('/workspace')">进入项目工作台</XqButton>
        </div>
      </div>
      <aside class="entry-hero__status">
        <span class="status-dot"></span>
        <p>当前流程</p>
        <strong>灵感 → 蓝图 → 大纲 → 正文 → 优化</strong>
        <small>先确认故事方向，再进入章节生成；后台任务状态会在写作台持续同步。</small>
      </aside>
    </section>

    <section class="entry-grid" aria-label="核心功能入口">
      <button v-for="item in mainFunctions" :key="item.title" type="button" class="entry-card" @click="go(item.to)">
        <span class="entry-card__icon">{{ item.icon }}</span>
        <span class="entry-card__label">{{ item.label }}</span>
        <strong>{{ item.title }}</strong>
        <small>{{ item.desc }}</small>
      </button>
    </section>

    <XqPanel class="recent-panel" title="最近项目" subtitle="显示最近 5 个项目，便于直接续写或检查生成状态。">
      <template #kicker>继续创作</template>
      <template #actions>
        <XqButton variant="secondary" size="sm" @click="reloadProjects">刷新列表</XqButton>
      </template>

      <div v-if="bootstrapLoading" class="entry-empty">正在加载项目列表……</div>
      <div v-else-if="bootstrapError" class="entry-empty entry-empty--error">{{ bootstrapError }}</div>
      <div v-else-if="!recentProjects.length" class="entry-empty">还没有项目。先进入灵感模式，创建你的第一部小说。</div>
      <div v-else class="project-list">
        <article v-for="project in recentProjects" :key="project.id" class="project-row">
          <button type="button" class="project-main" @click="enterProject(project)">
            <strong>{{ project.title || '未命名项目' }}</strong>
            <span>{{ projectProgress(project) }} · {{ formatDate(project.last_edited) }}</span>
          </button>
          <div class="project-actions">
            <XqButton variant="secondary" size="sm" @click="enterProject(project)">打开</XqButton>
            <XqButton variant="ghost" size="sm" @click="openRuntimeLogs(project.id)">运行日志</XqButton>
          </div>
        </article>
      </div>
    </XqPanel>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '../stores/novel'
import type { NovelProjectSummary } from '@/api/novel'
import { XqButton, XqPanel } from '@/shared/ui'

const router = useRouter()
const novelStore = useNovelStore()
const bootstrapLoading = ref(true)
const bootstrapError = ref('')

const projects = computed(() =>
  [...novelStore.projects].sort((a, b) => parseTime(b.last_edited) - parseTime(a.last_edited)),
)
const recentProjects = computed(() => projects.value.slice(0, 5))
const leadProject = computed(() => recentProjects.value[0] ?? null)
const primaryActionLabel = computed(() => (leadProject.value ? '继续最近项目' : '创建第一部小说'))

const mainFunctions = [
  { icon: '✦', label: '从 0 到 1', title: '灵感模式', desc: '通过访谈把模糊想法变成可执行小说蓝图。', to: '/inspiration' },
  { icon: '▦', label: '项目管理', title: '项目工作台', desc: '查看项目、章节、生成进度与最近改动。', to: '/workspace' },
  { icon: '◇', label: '审美统一', title: '风格中心', desc: '维护文风、叙事口吻和生成要求。', to: '/style-center' },
  { icon: '◎', label: '运行监控', title: '管理后台', desc: '检查任务日志、状态恢复与异常记录。', to: '/admin' },
  { icon: '⚙', label: '系统配置', title: '应用设置', desc: '调整偏好、快捷键与创作环境。', to: '/settings' },
  { icon: 'AI', label: '模型连接', title: 'LLM 设置', desc: '配置模型、Key、供应商与连通性测试。', to: '/llm-settings' },
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
  if (!value) return '未编辑'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(date)
}
function projectProgress(project: NovelProjectSummary) {
  return project.total_chapters ? `${project.completed_chapters}/${project.total_chapters} 章` : '蓝图待确认'
}
function startPrimaryAction() {
  const project = leadProject.value
  if (project) enterProject(project)
  else go('/inspiration')
}
function enterProject(project: NovelProjectSummary) {
  if (!project.total_chapters || project.total_chapters <= 0) {
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
    bootstrapError.value = error instanceof Error ? error.message : '加载项目失败'
  } finally {
    bootstrapLoading.value = false
  }
}
onMounted(reloadProjects)
</script>
<style scoped>
.entry-page {
  min-height: calc(100vh - 64px);
  padding: 1.75rem;
}

.entry-hero,
.recent-panel {
  max-width: 1180px;
  margin: 0 auto 1.35rem;
}

.entry-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 1.5rem;
  overflow: hidden;
  padding: clamp(1.5rem, 4vw, 2.6rem);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  background: rgba(255, 250, 240, 0.84);
  box-shadow: var(--xq-shadow-paper);
  backdrop-filter: blur(18px);
}

.entry-kicker {
  margin: 0;
  color: var(--xq-gold-deep);
  font-size: 0.78rem;
  font-weight: 900;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

h1 {
  max-width: 820px;
  margin: 0.85rem 0 0;
  font-family: var(--xq-font-serif);
  font-size: clamp(2.45rem, 6vw, 5rem);
  line-height: 1;
  letter-spacing: -0.05em;
}

.entry-hero__desc {
  max-width: 760px;
  margin: 1.15rem 0 0;
  color: var(--xq-ink-muted);
  line-height: 1.95;
}

.entry-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.75rem;
}

.entry-hero__status {
  align-self: stretch;
  display: grid;
  align-content: end;
  gap: 0.7rem;
  min-height: 250px;
  border-radius: var(--xq-radius-md);
  padding: 1.55rem;
  color: #fffaf0;
  background:
    radial-gradient(circle at 18% 8%, rgba(214, 169, 79, 0.28), transparent 12rem),
    linear-gradient(145deg, var(--xq-bg-ink), var(--xq-bg-midnight) 58%, #2b594f);
  box-shadow: var(--xq-shadow-floating), inset 0 1px rgba(255, 255, 255, 0.16);
}

.entry-hero__status p,
.entry-hero__status small {
  margin: 0;
  color: rgba(255, 250, 240, 0.72);
  line-height: 1.75;
}

.entry-hero__status strong {
  font-family: var(--xq-font-serif);
  font-size: 1.55rem;
  line-height: 1.35;
}

.status-dot {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 999px;
  background: var(--xq-jade);
  box-shadow: 0 0 0 0.5rem rgba(61, 143, 125, 0.18);
}

.entry-grid {
  max-width: 1180px;
  margin: 0 auto 1.35rem;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
}

.entry-card {
  min-height: 180px;
  text-align: left;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  background: rgba(255, 250, 240, 0.78);
  padding: 1.35rem;
  color: var(--xq-ink);
  cursor: pointer;
  box-shadow: 0 14px 38px rgba(80, 54, 24, 0.07);
  transition: transform var(--xq-fast), border-color var(--xq-fast), box-shadow var(--xq-fast), background var(--xq-fast);
}

.entry-card:hover {
  transform: translateY(-3px);
  border-color: rgba(214, 169, 79, 0.45);
  background: rgba(255, 250, 240, 0.94);
  box-shadow: 0 22px 54px rgba(154, 106, 34, 0.14);
}

.entry-card__icon {
  display: inline-flex;
  width: 2.8rem;
  height: 2.8rem;
  align-items: center;
  justify-content: center;
  border-radius: 1rem;
  background: rgba(214, 169, 79, 0.16);
  color: var(--xq-gold-deep);
  font-size: 1.35rem;
}

.entry-card__label {
  display: block;
  margin-top: 1rem;
  color: var(--xq-ink-faint);
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.16em;
}

.entry-card strong {
  display: block;
  margin-top: 0.35rem;
  font-family: var(--xq-font-serif);
  font-size: 1.4rem;
}

.entry-card small {
  display: block;
  margin-top: 0.65rem;
  color: var(--xq-ink-muted);
  line-height: 1.7;
  font-size: 0.9rem;
}

.project-list {
  display: grid;
  gap: 0.75rem;
}

.project-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  padding: 0.95rem;
  background: rgba(255, 250, 240, 0.64);
}

.project-main {
  display: grid;
  gap: 0.4rem;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.project-main strong {
  font-size: 1.05rem;
}

.project-main span {
  color: var(--xq-ink-muted);
  font-size: 0.88rem;
}

.project-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.entry-empty {
  border: 1px dashed rgba(154, 106, 34, 0.28);
  border-radius: var(--xq-radius-md);
  padding: 1.5rem;
  color: var(--xq-ink-muted);
  background: rgba(255, 250, 240, 0.52);
}

.entry-empty--error {
  color: var(--xq-cinnabar);
  background: rgba(185, 74, 61, 0.08);
  border-color: rgba(185, 74, 61, 0.24);
}

@media (max-width: 980px) {
  .entry-hero { grid-template-columns: 1fr; }
  .entry-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .project-row { align-items: stretch; flex-direction: column; }
}

@media (max-width: 560px) {
  .entry-page { padding: 0.9rem; }
  .entry-hero { border-radius: var(--xq-radius-md); }
  .entry-grid { grid-template-columns: 1fr; }
}
</style>

