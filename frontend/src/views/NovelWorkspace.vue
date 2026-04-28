<!-- AIMETA P=小说工作台_项目列表管理|R=小说列表_创建|NR=不含章节编辑|E=route:/workspace#component:NovelWorkspace|X=ui|A=工作台|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <div class="min-h-screen overflow-x-hidden bg-[radial-gradient(circle_at_top_left,_rgba(37,99,235,0.15),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(16,185,129,0.14),_transparent_24%),linear-gradient(180deg,_#f8fafc_0%,_#eef2ff_100%)] text-slate-900">
    <transition
      enter-active-class="transition-all duration-300"
      leave-active-class="transition-all duration-300"
      enter-from-class="opacity-0 translate-y-4"
      leave-to-class="opacity-0 translate-y-4"
    >
      <div v-if="deleteMessage" class="fixed right-4 top-4 z-50 rounded-full border border-white/70 bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-2xl shadow-slate-950/20">
        {{ deleteMessage.text }}
      </div>
    </transition>

    <header class="sticky top-0 z-30 border-b border-white/70 bg-white/80 backdrop-blur-xl">
      <div class="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-[0.3em] text-sky-700">小说工作台</p>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">我的小说项目</h1>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button class="rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-sky-200 hover:text-sky-700" @click="goBack">
            返回首页
          </button>
          <button class="rounded-full border border-sky-200 bg-sky-50 px-4 py-2.5 text-sm font-semibold text-sky-700 shadow-sm transition hover:-translate-y-0.5 hover:bg-sky-100" @click="goToInspiration">
            新建项目
          </button>
          <button class="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-semibold text-emerald-700 shadow-sm transition hover:-translate-y-0.5 hover:bg-emerald-100" @click="triggerImport">
            导入小说
          </button>
          <router-link v-if="authStore.user?.is_admin" to="/admin" class="rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300">
            管理后台
          </router-link>
        </div>
      </div>
    </header>

    <main class="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div v-if="novelStore.isLoading && !novelStore.projects.length" class="rounded-[30px] border border-white/70 bg-white/85 p-10 shadow-[0_20px_90px_-40px_rgba(15,23,42,0.45)] backdrop-blur-xl">
        <div class="mx-auto flex max-w-sm flex-col items-center justify-center py-12 text-center">
          <div class="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-slate-950"></div>
          <p class="mt-4 text-base font-medium text-slate-700">正在加载项目列表...</p>
        </div>
      </div>

      <div v-else-if="novelStore.error" class="rounded-[30px] border border-white/70 bg-white/88 p-8 shadow-[0_20px_90px_-40px_rgba(15,23,42,0.45)] backdrop-blur-xl">
        <div class="mx-auto max-w-md text-center">
          <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
            <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 class="mt-4 text-2xl font-semibold text-slate-950">项目加载失败</h2>
          <p class="mt-3 text-sm leading-6 text-rose-600">{{ novelStore.error }}</p>
          <button class="mt-6 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="loadProjects">
            重试
          </button>
        </div>
      </div>

      <div v-else class="space-y-6">
        <section class="grid gap-4 rounded-[24px] border border-white/70 bg-white/88 p-4 shadow-[0_16px_48px_-34px_rgba(15,23,42,0.32)] backdrop-blur-xl lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)] lg:p-5">
          <div class="min-w-0 space-y-4">
            <div class="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              <span class="rounded-full bg-slate-950 px-3 py-1 text-white">管理</span>
              <span class="rounded-full bg-sky-50 px-3 py-1 text-sky-700">高密度列表</span>
              <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">搜索 / 筛选 / 导入</span>
            </div>

            <div>
              <h2 class="text-3xl font-semibold tracking-tight text-slate-950">把每个项目都放进可管理的列表里。</h2>
              <p class="mt-3 max-w-3xl text-base leading-7 text-slate-600">
                这里专门用于找项目、筛项目、进项目。搜索、筛选、新建、导入都放在同一条工具带上，不再把入口藏在大卡片里。
              </p>
            </div>

            <div class="grid gap-3 sm:grid-cols-4">
              <div class="rounded-[22px] border border-slate-200 bg-slate-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">总项目</p>
                <p class="mt-2 text-2xl font-semibold text-slate-950">{{ summary.total }}</p>
              </div>
              <div class="rounded-[22px] border border-sky-100 bg-sky-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">连载中</p>
                <p class="mt-2 text-2xl font-semibold text-slate-950">{{ summary.active }}</p>
              </div>
              <div class="rounded-[22px] border border-emerald-100 bg-emerald-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">已完结</p>
                <p class="mt-2 text-2xl font-semibold text-slate-950">{{ summary.finished }}</p>
              </div>
              <div class="rounded-[22px] border border-rose-100 bg-rose-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-rose-700">待起稿</p>
                <p class="mt-2 text-2xl font-semibold text-slate-950">{{ summary.draft }}</p>
              </div>
            </div>
          </div>

          <div class="grid gap-3 self-start rounded-[20px] border border-slate-200 bg-slate-50 p-3.5">
            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px]">
              <label class="flex items-center gap-3 rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 shadow-sm">
                <svg class="h-5 w-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z" />
                </svg>
                <input v-model.trim="searchQuery" type="text" class="w-full bg-transparent text-sm outline-none placeholder:text-slate-400" placeholder="搜索标题或题材" />
              </label>
              <select v-model="sortMode" class="rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm outline-none">
                <option value="recent">最近编辑</option>
                <option value="progress">进度优先</option>
                <option value="title">按标题</option>
              </select>
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                v-for="filter in filters"
                :key="filter.id"
                :class="[
                  'rounded-full px-4 py-1.5 text-sm font-semibold transition',
                  activeFilter === filter.id
                    ? 'bg-slate-950 text-white shadow-lg shadow-slate-950/10'
                    : 'border border-slate-200 bg-white text-slate-700 hover:border-sky-200 hover:text-sky-700',
                ]"
                @click="activeFilter = filter.id"
              >
                {{ filter.label }}
              </button>
            </div>

            <div class="flex flex-wrap gap-2">
              <button class="rounded-[18px] bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800" @click="goToInspiration">
                新建项目
              </button>
              <button class="rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-emerald-200 hover:text-emerald-700" @click="triggerImport">
                导入小说
              </button>
              <button class="rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300" @click="loadProjects">
                刷新列表
              </button>
            </div>
          </div>
        </section>

        <section class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div class="space-y-4">
            <!-- 项目列表为空时：搜索无结果 vs 还没有任何项目 -->
          <div v-if="projects.length === 0" class="empty-state rounded-[24px] border border-white/70 bg-white/90 p-9 text-center shadow-[0_16px_56px_-36px_rgba(15,23,42,0.34)] backdrop-blur-xl">
            <div class="empty-illustration mx-auto mb-8 flex justify-center opacity-40">
              <svg viewBox="0 0 200 160" class="h-40 w-48 text-slate-400">
                <rect x="20" y="20" width="160" height="120" rx="8" fill="currentColor" opacity="0.3"/>
                <rect x="35" y="35" width="130" height="8" rx="4" fill="currentColor" opacity="0.5"/>
                <rect x="35" y="50" width="100" height="8" rx="4" fill="currentColor" opacity="0.5"/>
                <rect x="35" y="65" width="115" height="8" rx="4" fill="currentColor" opacity="0.5"/>
                <rect x="35" y="85" width="70" height="8" rx="4" fill="currentColor" opacity="0.4"/>
                <rect x="35" y="100" width="55" height="8" rx="4" fill="currentColor" opacity="0.4"/>
                <rect x="35" y="115" width="85" height="8" rx="4" fill="currentColor" opacity="0.3"/>
                <rect x="35" y="90" width="60" height="30" rx="4" fill="currentColor" opacity="0.2"/>
              </svg>
            </div>
            <h3 class="text-2xl font-semibold text-slate-950">还没有小说项目</h3>
            <p class="mt-3 text-base leading-7 text-slate-500">开始你的第一个故事，让 AI 帮你创作</p>
            <div class="mt-8 flex flex-wrap justify-center gap-3">
              <button class="rounded-2xl bg-slate-950 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/10 transition hover:-translate-y-0.5 hover:bg-slate-800" @click="goToInspiration">
                创建新小说
              </button>
              <button class="rounded-2xl border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:text-emerald-700" @click="triggerImport">
                导入小说
              </button>
            </div>
          </div>

          <div v-else-if="filteredProjects.length === 0" class="rounded-[24px] border border-dashed border-slate-300 bg-white/80 p-8 text-center shadow-[0_14px_42px_-32px_rgba(15,23,42,0.28)] backdrop-blur-xl">
            <p class="text-xl font-semibold text-slate-950">没有符合条件的项目</p>
            <p class="mt-2 text-sm leading-6 text-slate-600">调整搜索、筛选条件，或者直接新建一个项目。</p>
            <div class="mt-5 flex flex-wrap justify-center gap-3">
              <button class="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="goToInspiration">
                新建项目
              </button>
              <button class="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:text-sky-700" @click="triggerImport">
                导入小说
              </button>
            </div>
          </div>

            <div v-else class="space-y-4">
              <article
                v-for="project in filteredProjects"
                :key="project.id"
                class="group rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_16px_50px_-38px_rgba(15,23,42,0.35)] transition hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-xl"
              >
                <div class="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <h3 class="truncate text-xl font-semibold text-slate-950">{{ project.title }}</h3>
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">{{ statusLabel(project) }}</span>
                      <span v-if="project.genre" class="rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">{{ project.genre }}</span>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-500">
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">{{ project.total_chapters || 0 }} 章</span>
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">已完成 {{ project.completed_chapters }} 章</span>
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">最后编辑 {{ formatDate(project.last_edited) }}</span>
                    </div>

                    <div class="mt-4">
                      <div class="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                        <span>完成进度</span>
                        <span>{{ progressOf(project) }}%</span>
                      </div>
                      <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
                        <div class="h-full rounded-full bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-500" :style="{ width: `${progressOf(project)}%` }"></div>
                      </div>
                    </div>
                  </div>

                  <div class="grid gap-2 sm:grid-cols-3 xl:w-[260px] xl:flex-none">
                    <button class="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="enterProject(project)">
                      继续
                    </button>
                    <button class="rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:text-sky-700" @click="viewProjectDetail(project.id)">
                      详情
                    </button>
                    <button class="rounded-2xl border border-rose-200 bg-white px-4 py-3 text-sm font-semibold text-rose-700 transition hover:bg-rose-50" @click="handleDeleteProject(project.id)">
                      删除
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <aside class="space-y-4">
            <section class="rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_16px_50px_-38px_rgba(15,23,42,0.35)]">
              <p class="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">工作提示</p>
              <div class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
                <p>先搜索标题，再缩小到“连载中”或“待起稿”，定位速度会快很多。</p>
                <p>如果是新灵感，直接从灵感页进入，不要先在这里空建一个项目。</p>
                <p>导入旧稿会自动分析，之后可以直接进入工作台继续写作。</p>
              </div>
            </section>

            <section class="rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_16px_50px_-38px_rgba(15,23,42,0.35)]">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-700">最近项目</p>
                  <h2 class="mt-1 text-lg font-semibold text-slate-950">快速进入</h2>
                </div>
                <button class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-emerald-200 hover:text-emerald-700" @click="goBack">
                  首页
                </button>
              </div>

              <div v-if="topProjects.length" class="mt-4 space-y-3">
                <button
                  v-for="project in topProjects"
                  :key="`quick-${project.id}`"
                  class="w-full rounded-[22px] border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:border-sky-200 hover:bg-sky-50"
                  @click="enterProject(project)"
                >
                  <div class="flex items-center justify-between gap-3">
                    <span class="truncate text-sm font-semibold text-slate-950">{{ project.title }}</span>
                    <span class="text-xs font-semibold text-slate-500">{{ progressOf(project) }}%</span>
                  </div>
                  <p class="mt-2 text-xs text-slate-500">{{ formatDate(project.last_edited) }}</p>
                </button>
              </div>
            </section>

            <section class="rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_16px_50px_-38px_rgba(15,23,42,0.35)]">
              <p class="text-xs font-semibold uppercase tracking-[0.28em] text-sky-700">快捷入口</p>
              <div class="mt-4 grid gap-3">
                <button class="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="goToInspiration">新建灵感</button>
                <button class="rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:text-sky-700" @click="triggerImport">导入小说</button>
                <button class="rounded-[18px] border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300" @click="goBack">返回首页</button>
              </div>
            </section>
          </aside>
        </section>
      </div>
    </main>

    <input ref="fileInput" type="file" accept=".txt" class="hidden" @change="handleFileImport" />

    <transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div v-if="showDeleteDialog" class="md-dialog-overlay">
        <div class="md-dialog mx-4 w-full max-w-xl rounded-[28px] bg-white shadow-2xl">
          <div class="flex items-center gap-4 border-b border-slate-200 px-6 py-5">
            <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
              <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-slate-950">确认删除</h3>
              <p class="text-sm text-slate-500">此操作不可撤销。</p>
            </div>
          </div>

          <div class="px-6 py-5">
            <p class="text-base leading-7 text-slate-700">确定要删除项目“<strong>{{ projectToDelete?.title }}</strong>”吗？相关数据将被永久删除。</p>
          </div>

          <div class="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
            <button class="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300" @click="cancelDelete">
              取消
            </button>
            <button class="rounded-2xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-700" :disabled="isDeleting" @click="confirmDelete">
              {{ isDeleting ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useAuthStore } from '@/stores/auth'
import type { NovelProjectSummary } from '@/api/novel'
import { NovelAPI } from '@/api/novel'

const router = useRouter()
const novelStore = useNovelStore()
const authStore = useAuthStore()

const fileInput = ref<HTMLInputElement | null>(null)
const isImporting = ref(false)
const showDeleteDialog = ref(false)
const projectToDelete = ref<NovelProjectSummary | null>(null)
const isDeleting = ref(false)
const deleteMessage = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const searchQuery = ref('')
const activeFilter = ref<'all' | 'draft' | 'active' | 'finished'>('all')
const sortMode = ref<'recent' | 'progress' | 'title'>('recent')
const bootstrapLoading = ref(true)

const filters = [
  { id: 'all', label: '全部' },
  { id: 'draft', label: '待起稿' },
  { id: 'active', label: '连载中' },
  { id: 'finished', label: '已完结' },
] as const

const projects = computed(() =>
  [...novelStore.projects].sort((a, b) => parseTime(b.last_edited) - parseTime(a.last_edited))
)

const filteredProjects = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  const list = [...projects.value].filter((project) => {
    const text = `${project.title} ${project.genre || ''}`.toLowerCase()
    if (query && !text.includes(query)) return false
    const state = projectState(project)
    if (activeFilter.value !== 'all' && state !== activeFilter.value) return false
    return true
  })

  const sorted = list.sort((a, b) => {
    if (sortMode.value === 'title') return a.title.localeCompare(b.title, 'zh-Hans-CN')
    if (sortMode.value === 'progress') {
      const progressDiff = progressOf(b) - progressOf(a)
      return progressDiff !== 0 ? progressDiff : parseTime(b.last_edited) - parseTime(a.last_edited)
    }
    return parseTime(b.last_edited) - parseTime(a.last_edited)
  })

  return sorted
})

const topProjects = computed(() => projects.value.slice(0, 3))

const summary = computed(() => {
  const total = projects.value.length
  const finished = projects.value.filter((project) => projectState(project) === 'finished').length
  const active = projects.value.filter((project) => projectState(project) === 'active').length
  const draft = total - finished - active
  return { total, finished, active, draft }
})

function parseTime(value: string | null | undefined) {
  if (!value) return 0
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? 0 : time
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function progressOf(project: NovelProjectSummary) {
  if (!project.total_chapters) return 0
  return Math.round((project.completed_chapters / project.total_chapters) * 100)
}

function projectState(project: NovelProjectSummary) {
  if (!project.total_chapters) return 'draft'
  if (project.completed_chapters >= project.total_chapters) return 'finished'
  if (project.completed_chapters > 0) return 'active'
  return 'draft'
}

function statusLabel(project: NovelProjectSummary) {
  const state = projectState(project)
  if (state === 'finished') return '已完结'
  if (state === 'active') return '连载中'
  return '待起稿'
}

function goBack() {
  router.push('/')
}

function goToInspiration() {
  router.push('/inspiration')
}

function viewProjectDetail(projectId: string) {
  router.push(`/detail/${projectId}`)
}

function enterProject(project: NovelProjectSummary) {
  if (project.title === '未命名灵感' || project.total_chapters === 0) {
    router.push(`/inspiration?project_id=${project.id}`)
    return
  }
  router.push(`/novel/${project.id}`)
}

async function loadProjects() {
  await novelStore.loadProjects()
}

function triggerImport() {
  if (isImporting.value) return
  fileInput.value?.click()
}

async function handleFileImport(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return

  const file = target.files[0]
  if (!file.name.toLowerCase().endsWith('.txt')) {
    window.alert('请上传 .txt 格式的文本文件')
    target.value = ''
    return
  }

  isImporting.value = true
  try {
    const response = await NovelAPI.importNovel(file)
    await loadProjects()
    router.push(`/novel/${response.id}`)
  } catch (error: any) {
    console.error('导入失败:', error)
    window.alert(error?.message || '导入失败，请重试')
  } finally {
    isImporting.value = false
    target.value = ''
  }
}

function handleDeleteProject(projectId: string) {
  const project = novelStore.projects.find((item) => item.id === projectId)
  if (project) {
    projectToDelete.value = project
    showDeleteDialog.value = true
  }
}

function cancelDelete() {
  showDeleteDialog.value = false
  projectToDelete.value = null
}

async function confirmDelete() {
  if (!projectToDelete.value) return

  isDeleting.value = true
  try {
    const deletedTitle = projectToDelete.value.title
    await novelStore.deleteProjects([projectToDelete.value.id])
    deleteMessage.value = { type: 'success', text: `项目“${deletedTitle}”已删除` }
    showDeleteDialog.value = false
    projectToDelete.value = null

    window.setTimeout(() => {
      deleteMessage.value = null
    }, 2200)
  } catch (error) {
    console.error('删除失败:', error)
    deleteMessage.value = { type: 'error', text: '删除失败，请稍后重试' }
  } finally {
    isDeleting.value = false
  }
}

async function bootstrap() {
  if (!novelStore.projects.length) {
    await loadProjects()
  }
  bootstrapLoading.value = false
}

onMounted(() => {
  void bootstrap()
})
</script>
