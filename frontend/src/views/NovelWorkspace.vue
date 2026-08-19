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

    <transition
      enter-active-class="transition-all duration-300"
      leave-active-class="transition-all duration-300"
      enter-from-class="opacity-0 translate-y-4"
      leave-to-class="opacity-0 translate-y-4"
    >
      <div v-if="isImporting" class="fixed bottom-5 left-1/2 z-50 flex w-[min(92vw,560px)] -translate-x-1/2 flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-100 bg-white px-4 py-3 text-sm shadow-2xl shadow-slate-950/15">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">{{ pick('旧稿导入', 'Draft import') }}</p>
          <p class="mt-1 truncate font-medium text-slate-800">{{ importStatusMessage || pick('正在提交旧稿导入任务...', 'Submitting the draft import task...') }}</p>
        </div>
        <button
          class="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-rose-200 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!importRunId || importCancelRequested"
          @click="cancelImport"
        >
          {{ importCancelRequested ? pick('取消中...', 'Cancelling...') : pick('取消', 'Cancel') }}
        </button>
      </div>
    </transition>

    <header class="xq-topbar xq-topbar--workspace sticky top-0 z-30 border-b border-white/70 bg-white/80 backdrop-blur-xl">
      <div class="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6 lg:px-8">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-[0.3em] text-sky-700">{{ pick('小说工作台', 'Novel workspace') }}</p>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">{{ pick('我的小说项目', 'My novel projects') }}</h1>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button class="rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-sky-200 hover:text-sky-700" @click="goBack">
            {{ pick('返回首页', 'Back to home') }}
          </button>
          <button class="rounded-full border border-sky-200 bg-sky-50 px-4 py-2.5 text-sm font-semibold text-sky-700 shadow-sm transition hover:-translate-y-0.5 hover:bg-sky-100" @click="goToInspiration">
            {{ pick('新建项目', 'New project') }}
          </button>
          <button class="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-semibold text-emerald-700 shadow-sm transition hover:-translate-y-0.5 hover:bg-emerald-100" @click="triggerImport">
            {{ pick('导入小说', 'Import novel') }}
          </button>
          <router-link v-if="authStore.user?.is_admin" to="/admin" class="rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300">
            {{ pick('管理后台', 'Admin panel') }}
          </router-link>
        </div>
      </div>
    </header>

    <main class="mx-auto w-full max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
      <div v-if="novelStore.isLoading && !novelStore.projects.length" class="rounded-lg border border-white/70 bg-white/85 p-10 shadow-[0_8px_24px_-12px_rgba(15,23,42,0.45)] backdrop-blur-xl">
        <div class="mx-auto flex max-w-sm flex-col items-center justify-center py-12 text-center">
          <div class="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-slate-950"></div>
          <p class="mt-4 text-base font-medium text-slate-700">{{ pick('正在加载项目列表...', 'Loading the project list...') }}</p>
        </div>
      </div>

      <div v-else-if="novelStore.error" class="rounded-lg border border-white/70 bg-white/88 p-8 shadow-[0_8px_24px_-12px_rgba(15,23,42,0.45)] backdrop-blur-xl">
        <div class="mx-auto max-w-md text-center">
          <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
            <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 class="mt-4 text-xl font-semibold text-slate-950">{{ pick('项目加载失败', 'Failed to load projects') }}</h2>
          <p class="mt-3 text-sm leading-6 text-rose-600">{{ novelStore.error }}</p>
          <button class="mt-6 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="loadProjects">
            {{ pick('重试', 'Retry') }}
          </button>
        </div>
      </div>

      <div v-else class="space-y-6">
        <section class="grid gap-3 rounded-lg border border-white/70 bg-white/88 p-4 shadow-[0_4px_12px_-6px_rgba(15,23,42,0.32)] backdrop-blur-xl lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)] lg:p-5">
          <div class="min-w-0 space-y-4">
            <div class="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
              <span class="rounded-full bg-slate-950 px-3 py-1 text-white">{{ pick('管理', 'Manage') }}</span>
              <span class="rounded-full bg-sky-50 px-3 py-1 text-sky-700">{{ pick('高密度列表', 'Dense list') }}</span>
              <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">{{ pick('搜索 / 筛选 / 导入', 'Search / Filter / Import') }}</span>
            </div>

            <div>
              <h2 class="text-2xl font-semibold tracking-tight text-slate-950">{{ pick('把每个项目都放进可管理的列表里。', 'Keep every project in one manageable list.') }}</h2>
              <p class="mt-3 max-w-3xl text-base leading-7 text-slate-600">
                {{ pick(
                  '这里专门用于找项目、筛项目、进项目。搜索、筛选、新建、导入都放在同一条工具带上，不再把入口藏在大卡片里。',
                  'This page is only for finding, filtering, and opening projects. Search, filter, create, and import all sit on the same toolbar instead of hiding inside large cards.',
                ) }}
              </p>
            </div>

            <div class="grid gap-3 sm:grid-cols-4">
              <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{{ pick('总项目', 'Total projects') }}</p>
                <p class="mt-2 text-xl font-semibold text-slate-950">{{ summary.total }}</p>
              </div>
              <div class="rounded-xl border border-sky-100 bg-sky-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">{{ pick('连载中', 'In progress') }}</p>
                <p class="mt-2 text-xl font-semibold text-slate-950">{{ summary.active }}</p>
              </div>
              <div class="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700">{{ pick('已完结', 'Completed') }}</p>
                <p class="mt-2 text-xl font-semibold text-slate-950">{{ summary.finished }}</p>
              </div>
              <div class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
                <p class="text-xs font-semibold uppercase tracking-[0.22em] text-rose-700">{{ pick('待起稿', 'Not started') }}</p>
                <p class="mt-2 text-xl font-semibold text-slate-950">{{ summary.draft }}</p>
              </div>
            </div>
          </div>

          <div class="grid gap-3 self-start rounded-lg border border-slate-200 bg-slate-50 p-3.5">
            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px]">
              <label class="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2.5 shadow-sm">
                <svg class="h-5 w-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z" />
                </svg>
                <input v-model.trim="searchQuery" type="text" class="w-full bg-transparent text-sm outline-none placeholder:text-slate-400" :placeholder="pick('搜索标题或题材', 'Search by title or genre')" />
              </label>
              <select v-model="sortMode" class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm outline-none">
                <option value="recent">{{ pick('最近编辑', 'Recently edited') }}</option>
                <option value="progress">{{ pick('进度优先', 'Progress first') }}</option>
                <option value="title">{{ pick('按标题', 'By title') }}</option>
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
              <button class="rounded-lg bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800" @click="goToInspiration">
                {{ pick('新建项目', 'New project') }}
              </button>
              <button class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-emerald-200 hover:text-emerald-700" @click="triggerImport">
                {{ pick('导入小说', 'Import novel') }}
              </button>
              <button class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300" @click="loadProjects">
                {{ pick('刷新列表', 'Refresh list') }}
              </button>
            </div>
          </div>
        </section>

        <section class="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div class="space-y-4">
            <!-- 项目列表为空时：搜索无结果 vs 还没有任何项目 -->
          <div v-if="projects.length === 0" class="empty-state rounded-lg border border-white/70 bg-white/90 p-6 text-center shadow-[0_6px_18px_-10px_rgba(15,23,42,0.34)] backdrop-blur-xl">
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
            <h3 class="text-xl font-semibold text-slate-950">{{ pick('还没有小说项目', 'No novel projects yet') }}</h3>
            <p class="mt-3 text-base leading-7 text-slate-500">{{ pick('开始你的第一个故事，让 AI 帮你创作', 'Start your first story and let AI write with you') }}</p>
            <div class="mt-8 flex flex-wrap justify-center gap-3">
              <button class="rounded-2xl bg-slate-950 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/10 transition hover:-translate-y-0.5 hover:bg-slate-800" @click="goToInspiration">
                {{ pick('创建新小说', 'Create a novel') }}
              </button>
              <button class="rounded-2xl border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:text-emerald-700" @click="triggerImport">
                {{ pick('导入小说', 'Import novel') }}
              </button>
            </div>
          </div>

          <div v-else-if="filteredProjects.length === 0" class="rounded-lg border border-dashed border-slate-300 bg-white/80 p-8 text-center shadow-[0_14px_42px_-32px_rgba(15,23,42,0.28)] backdrop-blur-xl">
            <p class="text-xl font-semibold text-slate-950">{{ pick('没有符合条件的项目', 'No projects match the filters') }}</p>
            <p class="mt-2 text-sm leading-6 text-slate-600">{{ pick('调整搜索、筛选条件，或者直接新建一个项目。', 'Adjust the search or filters, or just create a new project.') }}</p>
            <div class="mt-5 flex flex-wrap justify-center gap-3">
              <button class="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="goToInspiration">
                {{ pick('新建项目', 'New project') }}
              </button>
              <button class="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:text-sky-700" @click="triggerImport">
                {{ pick('导入小说', 'Import novel') }}
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
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">{{ project.total_chapters || 0 }} {{ pick('章', 'chapters') }}</span>
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">{{ pick('已完成', 'Completed') }} {{ project.completed_chapters }} {{ pick('章', 'chapters') }}</span>
                      <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">{{ pick('最后编辑', 'Last edited') }} {{ formatDate(project.last_edited) }}</span>
                    </div>

                    <div class="mt-4">
                      <div class="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                        <span>{{ pick('完成进度', 'Completion') }}</span>
                        <span>{{ progressOf(project) }}%</span>
                      </div>
                      <div class="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
                        <div class="h-full rounded-full bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-500" :style="{ width: `${progressOf(project)}%` }"></div>
                      </div>
                    </div>
                  </div>

                  <div class="grid gap-2 sm:grid-cols-3 xl:w-[260px] xl:flex-none">
                    <button class="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="enterProject(project)">
                      {{ pick('继续', 'Continue') }}
                    </button>
                    <button class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:text-sky-700" @click="viewProjectDetail(project.id)">
                      {{ pick('详情', 'Details') }}
                    </button>
                    <button class="rounded-2xl border border-rose-200 bg-white px-4 py-3 text-sm font-semibold text-rose-700 transition hover:bg-rose-50" @click="handleDeleteProject(project.id)">
                      {{ pick('删除', 'Delete') }}
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <aside class="space-y-4">
            <section class="rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_16px_50px_-38px_rgba(15,23,42,0.35)]">
              <p class="text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">{{ pick('工作提示', 'Working tips') }}</p>
              <div class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
                <p>{{ pick(
                  '先搜索标题，再缩小到“连载中”或“待起稿”，定位速度会快很多。',
                  'Search the title first, then narrow it down to "In progress" or "Not started" — you will find things much faster.',
                ) }}</p>
                <p>{{ pick(
                  '如果是新灵感，直接从灵感页进入，不要先在这里空建一个项目。',
                  'For a brand-new idea, start from the inspiration page instead of creating an empty project here.',
                ) }}</p>
                <p>{{ pick(
                  '导入旧稿会自动分析，之后可以直接进入工作台继续写作。',
                  'An imported draft is analyzed automatically, and then you can head into the workspace and keep writing.',
                ) }}</p>
              </div>
            </section>

            <section class="rounded-[28px] border border-white/80 bg-white/90 p-5 shadow-[0_16px_50px_-38px_rgba(15,23,42,0.35)]">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-700">{{ pick('最近项目', 'Recent projects') }}</p>
                  <h2 class="mt-1 text-lg font-semibold text-slate-950">{{ pick('快速进入', 'Jump back in') }}</h2>
                </div>
                <button class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-emerald-200 hover:text-emerald-700" @click="goBack">
                  {{ pick('首页', 'Home') }}
                </button>
              </div>

              <div v-if="topProjects.length" class="mt-4 space-y-3">
                <button
                  v-for="project in topProjects"
                  :key="`quick-${project.id}`"
                  class="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:border-sky-200 hover:bg-sky-50"
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
              <p class="text-xs font-semibold uppercase tracking-[0.28em] text-sky-700">{{ pick('快捷入口', 'Quick actions') }}</p>
              <div class="mt-4 grid gap-3">
                <button class="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800" @click="goToInspiration">{{ pick('新建灵感', 'New inspiration') }}</button>
                <button class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:text-sky-700" @click="triggerImport">{{ pick('导入小说', 'Import novel') }}</button>
                <button class="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300" @click="goBack">{{ pick('返回首页', 'Back to home') }}</button>
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
          <div class="flex items-center gap-3 border-b border-slate-200 px-6 py-5">
            <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
              <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </div>
            <div>
              <h3 class="text-lg font-semibold text-slate-950">{{ pick('确认删除', 'Confirm deletion') }}</h3>
              <p class="text-sm text-slate-500">{{ pick('此操作不可撤销。', 'This cannot be undone.') }}</p>
            </div>
          </div>

          <div class="px-6 py-5">
            <p class="text-base leading-7 text-slate-700">{{ pick('确定要删除项目“', 'Delete the project "') }}<strong>{{ projectToDelete?.title }}</strong>{{ pick('”吗？相关数据将被永久删除。', '"? All related data will be permanently removed.') }}</p>
          </div>

          <div class="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
            <button class="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-300" @click="cancelDelete">
              {{ pick('取消', 'Cancel') }}
            </button>
            <button class="rounded-2xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-700" :disabled="isDeleting" @click="confirmDelete">
              {{ isDeleting ? pick('删除中...', 'Deleting...') : pick('确认删除', 'Confirm deletion') }}
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
import { useLocale } from '@/composables/useLocale'
import { resolveProjectWritingEntryFromSummary } from '@/utils/projectRouting'

const router = useRouter()
const novelStore = useNovelStore()
const authStore = useAuthStore()
const { pick } = useLocale()

const fileInput = ref<HTMLInputElement | null>(null)
const isImporting = ref(false)
const importStatusMessage = ref('')
const importRunId = ref('')
const importCancelRequested = ref(false)
const showDeleteDialog = ref(false)
const projectToDelete = ref<NovelProjectSummary | null>(null)
const isDeleting = ref(false)
const deleteMessage = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const searchQuery = ref('')
const activeFilter = ref<'all' | 'draft' | 'active' | 'finished'>('all')
const sortMode = ref<'recent' | 'progress' | 'title'>('recent')
const bootstrapLoading = ref(true)

// 筛选标签放在 computed 里，切换语言时才会重新求值。
const filters = computed<ReadonlyArray<{ id: 'all' | 'draft' | 'active' | 'finished'; label: string }>>(() => [
  { id: 'all', label: pick('全部', 'All') },
  { id: 'draft', label: pick('待起稿', 'Not started') },
  { id: 'active', label: pick('连载中', 'In progress') },
  { id: 'finished', label: pick('已完结', 'Completed') },
])

const IMPORT_POLL_INTERVAL_MS = 2000
const IMPORT_MAX_POLL_ATTEMPTS = 900
const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

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
  if (state === 'finished') return pick('已完结', 'Completed')
  if (state === 'active') return pick('连载中', 'In progress')
  return pick('待起稿', 'Not started')
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
  router.push(resolveProjectWritingEntryFromSummary(project))
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
    window.alert(pick('请上传 .txt 格式的文本文件', 'Please upload a .txt text file'))
    target.value = ''
    return
  }

  isImporting.value = true
  importStatusMessage.value = pick('正在提交旧稿导入任务...', 'Submitting the draft import task...')
  importRunId.value = ''
  importCancelRequested.value = false
  try {
    let status = await NovelAPI.startNovelImport(file)
    importRunId.value = status.run_id

    for (let attempt = 0; attempt < IMPORT_MAX_POLL_ATTEMPTS; attempt += 1) {
      importStatusMessage.value = status.progress_message || pick('旧稿导入进行中...', 'Draft import in progress...')
      if (status.status === 'successful' && status.project_id) {
        await loadProjects()
        router.push(`/novel/${status.project_id}`)
        return
      }
      if (status.status === 'failed') {
        const rawError = status.error
        const message = typeof rawError === 'string'
          ? rawError
          : rawError?.detail || rawError?.message || status.progress_message
        throw new Error(message || pick('导入失败，请重试', 'Import failed. Please try again.'))
      }
      if (status.status === 'cancelled' || importCancelRequested.value) {
        throw new Error(status.progress_message || pick('旧稿导入已取消', 'Draft import cancelled'))
      }

      await wait(IMPORT_POLL_INTERVAL_MS)
      status = await NovelAPI.getNovelImportStatus(importRunId.value)
    }

    throw new Error(pick(
      '旧稿导入后台任务等待超时，请稍后刷新项目列表查看结果。',
      'Timed out waiting for the draft import task. Refresh the project list later to check the result.',
    ))
  } catch (error: any) {
    console.error('导入失败:', error)
    window.alert(error?.message || pick('导入失败，请重试', 'Import failed. Please try again.'))
  } finally {
    isImporting.value = false
    importStatusMessage.value = ''
    importRunId.value = ''
    importCancelRequested.value = false
    target.value = ''
  }
}

async function cancelImport() {
  if (!importRunId.value || importCancelRequested.value) return
  importCancelRequested.value = true
  try {
    const status = await NovelAPI.cancelNovelImport(importRunId.value)
    importStatusMessage.value = status.progress_message || pick('正在取消旧稿导入...', 'Cancelling the draft import...')
    if (status.status !== 'cancelled') {
      importCancelRequested.value = false
    }
  } catch (error) {
    console.error('取消导入失败:', error)
    importCancelRequested.value = false
    importStatusMessage.value = pick('取消失败，导入任务仍在继续', 'Cancellation failed; the import is still running')
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
    deleteMessage.value = {
      type: 'success',
      text: pick(`项目“${deletedTitle}”已删除`, `Project "${deletedTitle}" deleted`),
    }
    showDeleteDialog.value = false
    projectToDelete.value = null

    window.setTimeout(() => {
      deleteMessage.value = null
    }, 2200)
  } catch (error) {
    console.error('删除失败:', error)
    deleteMessage.value = {
      type: 'error',
      text: pick('删除失败，请稍后重试', 'Delete failed. Please try again later.'),
    }
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
