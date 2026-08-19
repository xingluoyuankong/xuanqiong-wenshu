<template>
  <main class="entry-page xq-page-canvas">
    <section
      class="entry-hero xq-page-topbar xq-page-topbar--entry xq-paper-grain"
      aria-labelledby="entry-title"
    >
      <div class="entry-hero__copy">
        <p class="entry-kicker">{{ pick('玄穹文书 · AI 长篇创作驾驶舱', 'Xuanqiong Wenshu · AI long-form writing cockpit') }}</p>
        <h1 id="entry-title">{{ pick(
          '从一个灵感，推进到可连载的完整小说工程。',
          'Take a single idea all the way to a complete, serialisable novel project.'
        ) }}</h1>
        <p class="entry-hero__desc">
          {{ pick(
            '这里把灵感访谈、蓝图规划、章节生成、版本评审和 LLM 配置整合在同一个创作工作流中，帮助你稳定地产出可读、可追踪、可迭代的长篇内容。',
            'Inspiration interviews, blueprint planning, chapter generation, version review, and LLM configuration all live in one writing workflow, so you can keep producing readable, traceable, iterable long-form work.'
          ) }}
        </p>
        <div class="entry-actions">
          <XqButton data-testid="entry-primary-action" size="lg" @click="startPrimaryAction">{{
            primaryActionLabel
          }}</XqButton>
          <XqButton variant="secondary" size="lg" @click="go('/inspiration')">{{
            pick('开启灵感模式', 'Start inspiration mode')
          }}</XqButton>
          <XqButton variant="ghost" size="lg" @click="go('/workspace')">{{
            pick('进入项目工作台', 'Open the project workspace')
          }}</XqButton>
        </div>
      </div>
      <aside
        class="entry-hero__status"
        data-testid="hero-next-step"
        :aria-label="pick('下一步创作', 'Next writing step')"
      >
        <div class="status-heading">
          <span class="status-dot" aria-hidden="true"></span>
          <p>{{ pick('下一步创作', 'Next writing step') }}</p>
        </div>
        <template v-if="leadProject">
          <span class="status-label">{{ pick('最近编辑', 'Recently edited') }}</span>
          <strong class="status-project-title">{{ leadProject.title || pick('未命名项目', 'Untitled project') }}</strong>
          <span class="status-progress"
            >{{ projectProgress(leadProject) }} · {{ formatLastEdited(leadProject.last_edited) }}</span
          >
          <small>{{ pick(
            '接着上次的进度继续，正文、蓝图和生成状态会在项目内保持同步。',
            'Pick up where you left off — draft text, blueprint, and generation state stay in sync inside the project.'
          ) }}</small>
          <XqButton
            data-testid="hero-continue"
            class="status-action"
            variant="secondary"
            size="sm"
            @click="enterProject(leadProject)"
          >
            <template #icon>↗</template>
            {{ pick('继续写作', 'Continue writing') }}
          </XqButton>
        </template>
        <template v-else>
          <strong>{{ pick('从灵感开始', 'Start from an idea') }}</strong>
          <small>{{ pick(
            '先用一次简短访谈确定故事方向，再生成可执行的长篇蓝图。',
            'Settle the story direction with one short interview, then generate an actionable long-form blueprint.'
          ) }}</small>
          <XqButton
            data-testid="hero-create"
            class="status-action"
            variant="secondary"
            size="sm"
            @click="go('/inspiration')"
          >
            <template #icon>✦</template>
            {{ pick('创建第一部小说', 'Create your first novel') }}
          </XqButton>
        </template>
      </aside>
    </section>

    <section class="entry-grid" :aria-label="pick('核心功能入口', 'Core feature entries')">
      <div class="entry-grid__heading">
        <div>
          <p class="entry-grid__kicker">{{ pick('快速入口', 'Quick entries') }}</p>
          <h2>{{ pick('把创作推进到下一步', 'Move the work one step forward') }}</h2>
        </div>
        <span>{{ pick('按需进入，不打断当前写作流程', 'Jump in as needed without breaking your writing flow') }}</span>
      </div>
      <button
        v-for="item in mainFunctions"
        :key="item.id"
        :data-testid="`entry-function-${item.id}`"
        type="button"
        class="entry-card"
        @click="go(item.to)"
      >
        <span class="entry-card__icon">{{ item.icon }}</span>
        <span class="entry-card__label">{{ item.label }}</span>
        <strong>{{ item.title }}</strong>
        <small>{{ item.desc }}</small>
      </button>
    </section>

    <XqPanel
      class="recent-panel"
      :title="pick('最近项目', 'Recent projects')"
      :subtitle="pick(
        '显示最近 5 个项目，便于直接续写或检查生成状态。',
        'Shows the 5 most recent projects so you can keep writing or check generation status right away.'
      )"
    >
      <template #kicker>{{ pick('继续创作', 'Keep writing') }}</template>
      <template #actions>
        <XqButton variant="secondary" size="sm" @click="reloadProjects">{{ pick('刷新列表', 'Refresh list') }}</XqButton>
      </template>

      <div v-if="bootstrapLoading" class="entry-empty">{{ pick('正在加载项目列表……', 'Loading the project list…') }}</div>
      <div v-else-if="bootstrapError" class="entry-empty entry-empty--error">
        {{ bootstrapError }}
      </div>
      <div v-else-if="!recentProjects.length" class="entry-empty">
        {{ pick(
          '还没有项目。先进入灵感模式，创建你的第一部小说。',
          'No projects yet. Head into inspiration mode and create your first novel.'
        ) }}
      </div>
      <div v-else class="project-list grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <article v-for="project in recentProjects" :key="project.id" class="project-row">
          <button type="button" class="project-main" @click="enterProject(project)">
            <strong>{{ project.title || pick('未命名项目', 'Untitled project') }}</strong>
            <span>{{ projectProgress(project) }} · {{ formatLastEdited(project.last_edited) }}</span>
          </button>
          <div class="project-actions">
            <XqButton variant="secondary" size="sm" @click="enterProject(project)">{{ pick('打开', 'Open') }}</XqButton>
            <XqButton variant="ghost" size="sm" @click="openRuntimeLogs(project.id)">{{
              pick('运行日志', 'Runtime logs')
            }}</XqButton>
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
import { useLocale } from '@/composables/useLocale'

const router = useRouter()
const novelStore = useNovelStore()
const { pick, formatDate } = useLocale()
const bootstrapLoading = ref(true)
const bootstrapError = ref('')

const projects = computed(() =>
  [...novelStore.projects].sort((a, b) => parseTime(b.last_edited) - parseTime(a.last_edited)),
)
const recentProjects = computed(() => projects.value.slice(0, 5))
const leadProject = computed(() => recentProjects.value[0] ?? null)
const primaryActionLabel = computed(() => (leadProject.value
  ? pick('继续最近项目', 'Continue the latest project')
  : pick('创建第一部小说', 'Create your first novel')))

const mainFunctions = computed(() => [
  {
    id: 'inspiration',
    icon: '✦',
    label: pick('从 0 到 1', 'Zero to one'),
    title: pick('灵感模式', 'Inspiration mode'),
    desc: pick('通过访谈把模糊想法变成可执行小说蓝图。', 'Turn a vague idea into an actionable novel blueprint through an interview.'),
    to: '/inspiration',
  },
  {
    id: 'workspace',
    icon: '▦',
    label: pick('项目管理', 'Project management'),
    title: pick('项目工作台', 'Project workspace'),
    desc: pick('查看项目、章节、生成进度与最近改动。', 'Review projects, chapters, generation progress, and recent changes.'),
    to: '/workspace',
  },
  {
    id: 'style',
    icon: '◇',
    label: pick('审美统一', 'Consistent voice'),
    title: pick('风格中心', 'Style centre'),
    desc: pick('维护文风、叙事口吻和生成要求。', 'Maintain prose style, narrative voice, and generation requirements.'),
    to: '/style-center',
  },
  {
    id: 'admin',
    icon: '◎',
    label: pick('运行监控', 'Runtime monitoring'),
    title: pick('管理后台', 'Admin console'),
    desc: pick('检查任务日志、状态恢复与异常记录。', 'Inspect job logs, state recovery, and error records.'),
    to: '/admin',
  },
  {
    id: 'settings',
    icon: '⚙',
    label: pick('系统配置', 'System configuration'),
    title: pick('应用设置', 'App settings'),
    desc: pick('调整偏好、快捷键与创作环境。', 'Adjust preferences, shortcuts, and the writing environment.'),
    to: '/settings',
  },
  {
    id: 'llm',
    icon: 'AI',
    label: pick('模型连接', 'Model connection'),
    title: pick('LLM 设置', 'LLM settings'),
    desc: pick('配置模型、Key、供应商与连通性测试。', 'Configure models, keys, providers, and connectivity tests.'),
    to: '/llm-settings',
  },
])

function go(to: string) {
  router.push(to)
}
function parseTime(value: string | null | undefined) {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? 0 : time
}
function formatLastEdited(value: string | null | undefined) {
  if (!value) return pick('未编辑', 'Not edited yet')
  return formatDate(value) || value
}
function projectProgress(project: NovelProjectSummary) {
  return project.total_chapters
    ? pick(
        `${project.completed_chapters}/${project.total_chapters} 章`,
        `${project.completed_chapters}/${project.total_chapters} ch.`,
      )
    : pick('蓝图待确认', 'Blueprint pending confirmation')
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
    bootstrapError.value = error instanceof Error ? error.message : pick('加载项目失败', 'Failed to load projects')
  } finally {
    bootstrapLoading.value = false
  }
}
onMounted(reloadProjects)
</script>
<style scoped>
.entry-page {
  min-height: calc(100vh - 64px);
  padding: clamp(1rem, 3vw, 1.75rem);
}

.entry-hero,
.recent-panel {
  max-width: 1180px;
  margin: 0 auto 1.35rem;
}

.entry-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 312px;
  gap: 1.25rem;
  overflow: hidden;
  padding: clamp(1.35rem, 3.2vw, 2.15rem);
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
  max-width: 700px;
  margin: 0.72rem 0 0;
  font-family: var(--xq-font-serif);
  font-size: clamp(2.25rem, 5vw, 4.25rem);
  line-height: 1.06;
  letter-spacing: 0;
}

.entry-hero__desc {
  max-width: 680px;
  margin: 1rem 0 0;
  color: var(--xq-ink-muted);
  line-height: 1.95;
}

.entry-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.45rem;
}

.entry-hero__status {
  align-self: stretch;
  display: grid;
  align-content: start;
  gap: 0.65rem;
  min-height: 220px;
  border-radius: var(--xq-radius-md);
  padding: 1.15rem;
  color: #fffaf0;
  background:
    radial-gradient(circle at 18% 8%, rgba(214, 169, 79, 0.28), transparent 12rem),
    linear-gradient(145deg, var(--xq-bg-ink), var(--xq-bg-midnight) 58%, #2b594f);
  box-shadow:
    var(--xq-shadow-floating),
    inset 0 1px rgba(255, 255, 255, 0.16);
}

.status-heading {
  display: flex;
  align-items: center;
  gap: 0.7rem;
}

.entry-hero__status p,
.entry-hero__status small,
.status-progress,
.status-label {
  margin: 0;
  color: rgba(255, 250, 240, 0.72);
  line-height: 1.75;
}

.status-label {
  margin-top: 0.8rem;
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.entry-hero__status strong {
  font-family: var(--xq-font-serif);
  font-size: 1.65rem;
  line-height: 1.35;
}

.status-project-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-progress {
  font-size: 0.88rem;
}

.status-action {
  justify-self: start;
  margin-top: 0.35rem;
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

.entry-grid__heading {
  grid-column: 1 / -1;
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.25rem 0.15rem 0.1rem;
}

.entry-grid__heading h2 {
  margin: 0.25rem 0 0;
  font-family: var(--xq-font-serif);
  font-size: 1.55rem;
  line-height: 1.2;
}

.entry-grid__heading > span {
  color: var(--xq-ink-faint);
  font-size: 0.86rem;
}

.entry-grid__kicker {
  margin: 0;
  color: var(--xq-gold-deep);
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.entry-card {
  min-height: 148px;
  text-align: left;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  background: rgba(255, 250, 240, 0.78);
  padding: 1.1rem;
  color: var(--xq-ink);
  cursor: pointer;
  box-shadow: 0 14px 38px rgba(80, 54, 24, 0.07);
  transition:
    transform var(--xq-fast),
    border-color var(--xq-fast),
    box-shadow var(--xq-fast),
    background var(--xq-fast);
}

.entry-card:hover {
  transform: translateY(-3px);
  border-color: rgba(214, 169, 79, 0.45);
  background: rgba(255, 250, 240, 0.94);
  box-shadow: 0 22px 54px rgba(154, 106, 34, 0.14);
}

.entry-card__icon {
  display: inline-flex;
  width: 2.35rem;
  height: 2.35rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.8rem;
  background: rgba(214, 169, 79, 0.16);
  color: var(--xq-gold-deep);
  font-size: 1.35rem;
}

.entry-card__label {
  display: block;
  margin-top: 0.8rem;
  color: var(--xq-ink-faint);
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.16em;
}

.entry-card strong {
  display: block;
  margin-top: 0.35rem;
  font-family: var(--xq-font-serif);
  font-size: 1.25rem;
}

.entry-card small {
  display: block;
  margin-top: 0.45rem;
  color: var(--xq-ink-muted);
  line-height: 1.7;
  font-size: 0.9rem;
}

.project-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr));
  gap: 0.75rem;
}

.project-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  padding: 0.9rem;
  background: rgba(255, 250, 240, 0.64);
}

.project-main {
  min-width: 0;
  flex: 1;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  .entry-hero {
    grid-template-columns: 1fr;
  }
  .entry-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .project-row {
    align-items: stretch;
  }
  .entry-hero__status {
    min-height: 0;
  }
}

@media (max-width: 560px) {
  .entry-page {
    padding: 0.9rem;
  }
  .entry-hero {
    border-radius: var(--xq-radius-md);
  }
  .entry-grid {
    grid-template-columns: 1fr;
  }
  .entry-grid__heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.35rem;
  }
  .entry-card {
    min-height: 0;
  }
  .project-row {
    flex-direction: column;
  }
  .project-actions {
    width: 100%;
  }
}
</style>
