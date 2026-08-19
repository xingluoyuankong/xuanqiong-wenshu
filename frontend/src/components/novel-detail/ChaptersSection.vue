<!-- AIMETA P=章节区_章节列表展示|R=章节列表_状态|NR=不含编辑功能|E=component:ChaptersSection|X=ui|A=章节组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="flex flex-col h-full min-h-0 overflow-hidden relative">
    <div class="flex flex-row flex-1 h-full lg:min-h-0 overflow-hidden">
      <!-- 移动端遮罩层 -->
      <div
        v-if="showChapterList"
        class="fixed inset-0 bg-black/50 z-40 lg:hidden"
        @click="showChapterList = false"
      ></div>

      <!-- 章节列表侧边栏 -->
      <aside
        class="fixed lg:static inset-y-0 left-0 z-50 w-64 lg:w-64 bg-white lg:bg-slate-50/70 border-r border-slate-200 flex flex-col h-full min-h-0 max-h-full overflow-hidden transition-transform duration-300 lg:translate-x-0 shadow-2xl lg:shadow-none"
        :class="showChapterList ? 'translate-x-0' : '-translate-x-full'"
      >
        <div class="px-3 py-2.5 border-b border-slate-200 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-slate-900">{{ pick('章节', 'Chapters') }}</h3>
          <div class="flex items-center gap-2">
            <button
              @click="exportAllChapters('txt')"
              class="text-xs px-2 py-1 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded"
              :title="pick('导出全部章节为TXT', 'Export all chapters as TXT')"
            >
              {{ pick('导出TXT', 'Export TXT') }}
            </button>
            <button
              @click="exportAllChapters('docx')"
              class="text-xs px-2 py-1 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded"
              :title="pick('导出全部章节为DOCX', 'Export all chapters as DOCX')"
            >
              {{ pick('导出DOCX', 'Export DOCX') }}
            </button>
            <span class="text-xs text-slate-500">{{ pick(`${chapters.length} 篇`, `${chapters.length} chapters`) }}</span>
          </div>
        </div>
        <ul class="flex-1 h-full overflow-y-auto divide-y divide-slate-200 overscroll-contain">
          <li v-for="(chapter, index) in chapters" :key="chapter.chapter_number">
            <button
              class="w-full text-left px-3 py-2 transition-all duration-200 hover:translate-x-1-colors duration-200"
              :class="selectedChapter?.chapter_number === chapter.chapter_number ? 'bg-indigo-50 text-indigo-600 font-semibold border-l-3 border-indigo-500' : 'hover:bg-slate-50 lg:hover:bg-white text-slate-700'"
              @click="selectChapter(chapter.chapter_number)"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-3 min-w-0">
                  <span class="inline-flex items-center justify-center w-5 h-5 text-[11px] font-semibold text-slate-500 bg-slate-100 rounded-full">
                    {{ index + 1 }}
                  </span>
                  <span class="truncate">{{ chapter.title || chapterFallbackTitle(chapter.chapter_number) }}</span>
                </div>
                <span v-if="chapterCache.has(chapter.chapter_number)" class="text-xs text-slate-400">
                  {{ formatWordCountLabel(calculateWordCount(chapterCache.get(chapter.chapter_number)?.content)) }}
                </span>
                <span v-else class="text-xs text-slate-400">{{ pick('未加载', 'Not loaded') }}</span>
              </div>
              <p v-if="chapter.summary" class="mt-0.5 text-[11px] text-slate-400 truncate">
                {{ chapter.summary }}
              </p>
            </button>
          </li>
        </ul>
      </aside>

      <section class="flex-1 flex flex-col bg-white h-full min-h-0 max-h-full overflow-hidden relative">
        <!-- 移动端浮动按钮 -->
        <button
          v-if="!showChapterList"
          @click="showChapterList = true"
          class="lg:hidden fixed bottom-6 left-6 z-30 w-14 h-14 bg-indigo-600 text-white rounded-full shadow-lg flex items-center justify-center hover:bg-indigo-700 transition-colors"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <!-- Loading State -->
        <div v-if="isLoading" class="h-full flex items-center justify-center">
          <div class="text-center">
            <div class="w-7 h-7 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mx-auto mb-2"></div>
            <p class="text-sm text-slate-500">{{ pick('加载中...', 'Loading…') }}</p>
          </div>
        </div>

        <!-- Error State -->
        <div v-else-if="error" class="h-full flex items-center justify-center">
          <div class="text-center max-w-md px-6">
            <div class="w-8 h-8 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-2">
              <svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p class="text-sm text-slate-600">{{ error }}</p>
            <p class="mt-2 text-xs leading-6 text-slate-500">{{ pick('可以重试当前章节加载；如果只是正文未生成，也可以先回到写作台继续推进生成流程。', 'You can retry loading this chapter; if only the draft is missing, head back to the writing desk and continue the generation flow.') }}</p>
            <button
              @click="retryFailedChapter"
              :disabled="!failedChapterNumber"
              class="mt-4 inline-flex items-center rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {{ pick('重试加载本章', 'Retry loading this chapter') }}
            </button>
          </div>
        </div>

        <!-- Content -->
        <template v-else-if="selectedChapter">
          <!-- Header with Status and Tabs -->
          <header class="px-4 py-2.5 border-b border-slate-200 bg-slate-50/40">
            <div class="flex items-start justify-between gap-4 mb-2">
              <div class="flex-1">
                <h4 class="text-base font-bold text-slate-900">{{ selectedChapter.title || chapterFallbackTitle(selectedChapter.chapter_number) }}</h4>
                <div class="flex items-center gap-3 mt-1.5">
                  <span class="text-sm text-slate-500">{{ pick(`第 ${selectedChapter.chapter_number} 章`, `Chapter ${selectedChapter.chapter_number}`) }}</span>
                  <span class="text-sm text-slate-400">·</span>
                  <span class="text-sm text-slate-500">{{ formatWordCountLabel(calculateWordCount(selectedChapter.content)) }}</span>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <button
                  class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md border transition-colors duration-200"
                  :class="selectedChapter?.content ? 'border-indigo-200 text-indigo-600 hover:bg-indigo-50' : 'border-slate-200 text-slate-400 cursor-not-allowed'"
                  :disabled="!selectedChapter?.content"
                  @click="exportChapterAsTxt"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v16h16V4m-4 4l-4-4-4 4m4-4v12" />
                  </svg>
                  {{ pick('导出TXT', 'Export TXT') }}
                </button>
                <button
                  class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md border transition-colors duration-200"
                  :class="selectedChapter?.content ? 'border-indigo-200 text-indigo-600 hover:bg-indigo-50' : 'border-slate-200 text-slate-400 cursor-not-allowed'"
                  :disabled="!selectedChapter?.content"
                  @click="exportChapterAsDocx"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {{ pick('导出DOCX', 'Export DOCX') }}
                </button>
                <span v-if="selectedChapter.generation_status"
                  class="px-3 py-1 text-xs font-medium rounded-full"
                  :class="getStatusColor(selectedChapter.generation_status)">
                  {{ getStatusLabel(selectedChapter.generation_status) }}
                </span>
              </div>
            </div>

            <!-- Tab Navigation -->
            <div class="flex gap-1">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                @click="activeTab = tab.key"
                class="px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
                :class="activeTab === tab.key
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'"
              >
                {{ tab.label }}
                <span v-if="tab.badge && getTabBadgeCount(tab.key)"
                  class="ml-1.5 px-1.5 py-0.5 text-xs rounded-full"
                  :class="activeTab === tab.key ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-200 text-slate-600'">
                  {{ getTabBadgeCount(tab.key) }}
                </span>
              </button>
            </div>
          </header>

          <!-- Tab Content -->
          <article class="flex-1 h-full overflow-y-auto min-h-0 overscroll-contain">
            <!-- 正文 Tab -->
            <div v-show="activeTab === 'content'" class="px-2 py-2">
              <div class="max-w-full space-y-4">
                <!-- Summary Cards -->
                <div v-if="selectedChapter.summary || selectedChapter.real_summary" class="grid gap-4">
                  <div v-if="selectedChapter.summary" class="bg-blue-50 border border-blue-100 rounded-lg p-3">
                    <h5 class="text-xs font-semibold text-blue-900 mb-2 flex items-center gap-1.5">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      {{ pick('计划大纲', 'Planned outline') }}
                    </h5>
                    <p class="text-sm text-blue-800 leading-relaxed">{{ selectedChapter.summary }}</p>
                  </div>
                  <div v-if="selectedChapter.real_summary" class="bg-green-50 border border-green-100 rounded-lg p-3">
                    <h5 class="text-xs font-semibold text-green-900 mb-2 flex items-center gap-1.5">
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                      </svg>
                      {{ pick('实际内容概要', 'Actual content summary') }}
                    </h5>
                    <div class="prose prose-sm prose-green max-w-none text-green-800" v-html="renderedRealSummary"></div>
                  </div>
                </div>

                <!-- Main Content -->
                <div class="prose prose-slate max-w-none p-4 sm:p-6 rounded-xl bg-[var(--paper-card)]">
                  <div class="text-base text-slate-900 leading-8 whitespace-pre-wrap font-serif">
                    {{ selectedChapter.content || pick('暂无内容', 'No content yet') }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 版本 Tab -->
            <div v-show="activeTab === 'versions'" class="px-2 py-2">
              <div class="max-w-full">
                <div v-if="selectedChapter.versions && selectedChapter.versions.length > 0" class="space-y-4">
                  <div v-for="(version, index) in selectedChapter.versions" :key="index"
                    class="border border-slate-200 rounded-xl p-5 hover:border-indigo-300 hover:shadow-md transition-all duration-200 group cursor-pointer"
                    @click="openVersionModal(version.content, index)">
                    <div class="flex items-center justify-between mb-2">
                      <h5 class="text-sm font-semibold text-slate-900 flex items-center gap-2">
                        <span class="w-6 h-6 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center text-xs font-bold">
                          {{ index + 1 }}
                        </span>
                        {{ pick(`版本 ${index + 1}`, `Version ${index + 1}`) }}
                      </h5>
                      <div class="flex items-center gap-3">
                        <span class="text-xs text-slate-500">{{ formatWordCountLabel(calculateWordCount(version.content)) }}</span>
                        <span class="text-xs font-medium text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity">
                          {{ pick('点击查看全文 →', 'Click to read the full text →') }}
                        </span>
                      </div>
                    </div>
                    <div class="text-sm text-slate-700 leading-7 whitespace-pre-wrap line-clamp-4">
                      {{ version.content }}
                    </div>
                  </div>
                </div>
                <div v-else class="text-center py-12 text-slate-400">
                  <p>{{ pick('暂无版本记录', 'No version history yet') }}</p>
                  <p class="mt-2 text-sm text-slate-500">{{ pick('当前章节还没有可切换版本。回到写作台生成、评审或优化后，这里会出现版本列表。', 'This chapter has no alternate versions yet. Generate, review, or optimize it on the writing desk and the version list will appear here.') }}</p>
                </div>
              </div>
            </div>

            <!-- 评审 Tab -->
            <div v-show="activeTab === 'evaluation'" class="px-2 py-2">
              <div class="max-w-full">
                <div v-if="evaluationData" class="space-y-4">
                  <!-- 最佳选择 -->
                  <div v-if="evaluationData.best_choice" class="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-lg p-3">
                    <div class="flex items-start gap-4">
                      <div class="w-8 h-8 bg-indigo-500 rounded-xl flex items-center justify-center flex-shrink-0">
                        <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                        </svg>
                      </div>
                      <div class="flex-1">
                        <h5 class="text-base font-bold text-indigo-900 mb-2">{{ pick('最佳版本选择', 'Best version choice') }}</h5>
                        <div class="flex items-center gap-2 mb-2">
                          <span class="px-2 py-0.5 bg-indigo-500 text-white text-xs font-bold rounded-full">
                            {{ pick(`版本 ${evaluationData.best_choice}`, `Version ${evaluationData.best_choice}`) }}
                          </span>
                        </div>
                        <p v-if="evaluationData.reason_for_choice" class="text-sm text-indigo-900 leading-relaxed">
                          {{ evaluationData.reason_for_choice }}
                        </p>
                      </div>
                    </div>
                  </div>

                  <!-- 各版本详细评审 -->
                  <div v-if="evaluationData.evaluation" class="space-y-4">
                    <div v-for="(versionEval, versionKey) in evaluationData.evaluation" :key="versionKey"
                      class="border border-slate-200 rounded-xl overflow-hidden"
                      :class="isSelectedVersion(versionKey, evaluationData.best_choice) ? 'ring-2 ring-indigo-400' : ''">
                      <!-- 版本标题 -->
                      <div class="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                        <h6 class="font-bold text-slate-900 flex items-center gap-2">
                          <span class="w-6 h-6 bg-slate-700 text-white rounded-full flex items-center justify-center text-xs">
                            {{ getVersionNumber(versionKey) }}
                          </span>
                          {{ getVersionLabel(versionKey) }}
                        </h6>
                        <span v-if="isSelectedVersion(versionKey, evaluationData.best_choice)"
                          class="px-2.5 py-1 bg-indigo-100 text-indigo-700 text-xs font-semibold rounded-full">
                          {{ pick('最佳', 'Best') }}
                        </span>
                      </div>

                      <div class="p-3 space-y-2">
                        <!-- 优点 -->
                        <div v-if="versionEval.pros && versionEval.pros.length > 0"
                          class="bg-green-50 border border-green-100 rounded-lg p-3">
                          <h6 class="text-xs font-bold text-green-900 mb-2 flex items-center gap-1.5">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                            </svg>
                            {{ pick('优点', 'Strengths') }}
                          </h6>
                          <ul class="space-y-1.5">
                            <li v-for="(item, idx) in versionEval.pros" :key="idx"
                              class="flex items-start gap-2 text-xs text-green-800 leading-relaxed">
                              <span class="w-1 h-1 bg-green-500 rounded-full mt-1.5 flex-shrink-0"></span>
                              <span>{{ item }}</span>
                            </li>
                          </ul>
                        </div>

                        <!-- 缺点 -->
                        <div v-if="versionEval.cons && versionEval.cons.length > 0"
                          class="bg-red-50 border border-red-100 rounded-lg p-3">
                          <h6 class="text-xs font-bold text-red-900 mb-2 flex items-center gap-1.5">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                            {{ pick('缺点', 'Weaknesses') }}
                          </h6>
                          <ul class="space-y-1.5">
                            <li v-for="(item, idx) in versionEval.cons" :key="idx"
                              class="flex items-start gap-2 text-xs text-red-800 leading-relaxed">
                              <span class="w-1 h-1 bg-red-500 rounded-full mt-1.5 flex-shrink-0"></span>
                              <span>{{ item }}</span>
                            </li>
                          </ul>
                        </div>

                        <!-- 总体评价 -->
                        <div v-if="versionEval.overall_review"
                          class="bg-blue-50 border border-blue-100 rounded-lg p-3">
                          <h6 class="text-xs font-bold text-blue-900 mb-2">{{ pick('总体评价', 'Overall review') }}</h6>
                          <p class="text-xs text-blue-800 leading-relaxed">{{ versionEval.overall_review }}</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 简单格式兼容 -->
                  <div v-else-if="evaluationData.decision || evaluationData.feedback" class="space-y-4">
                    <!-- 评审决策 -->
                    <div v-if="evaluationData.decision" class="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-200 rounded-lg p-3">
                      <div class="flex items-center gap-3 mb-3">
                        <div class="w-7 h-7 bg-indigo-500 rounded-lg flex items-center justify-center">
                          <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                        </div>
                        <div>
                          <h5 class="text-sm font-bold text-indigo-900">{{ pick('评审决策', 'Review decision') }}</h5>
                          <p class="text-xs text-indigo-700">{{ evaluationData.decision }}</p>
                        </div>
                      </div>
                    </div>

                    <!-- 评分卡片 -->
                    <div v-if="evaluationData.scores" class="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <div v-for="(score, key) in evaluationData.scores" :key="key"
                        class="bg-white border border-slate-200 rounded-lg p-3 hover:shadow-md transition-shadow">
                        <div class="flex items-center justify-between mb-2">
                          <span class="text-xs font-medium text-slate-600">{{ getScoreLabel(key) }}</span>
                          <span class="text-base font-bold" :class="getScoreColor(score)">{{ score }}</span>
                        </div>
                        <div class="w-full bg-slate-100 rounded-full h-2">
                          <div class="h-2 rounded-full transition-all duration-300"
                            :class="getScoreBarColor(score)"
                            :style="{ width: `${(score / 10) * 100}%` }"></div>
                        </div>
                      </div>
                    </div>

                    <!-- 详细反馈 -->
                    <div v-if="evaluationData.feedback"
                      class="bg-slate-50 border border-slate-200 rounded-lg p-3">
                      <h5 class="text-sm font-bold text-slate-900 mb-2">{{ pick('详细反馈', 'Detailed feedback') }}</h5>
                      <p class="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{{ evaluationData.feedback }}</p>
                    </div>
                  </div>
                </div>

                <div v-else class="text-center py-12">
                  <div class="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-2">
                    <svg class="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <p class="text-slate-400">{{ pick('暂无评审意见', 'No review notes yet') }}</p>
                </div>
              </div>
            </div>
          </article>
        </template>

        <!-- Empty State -->
        <div v-else class="h-full flex items-center justify-center text-slate-400">
          <div class="text-center">
            <svg class="w-16 h-16 mx-auto mb-2 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            <p class="text-sm">{{ pick('请选择章节查看详细内容', 'Select a chapter to see its details') }}</p>
          </div>
        </div>
      </section>
    </div>

    <!-- 版本全文弹窗 -->
    <transition
      enter-active-class="transition-all duration-300"
      leave-active-class="transition-all duration-300"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div v-if="versionModal.show" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
        @click="closeVersionModal">
        <div class="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[85vh] overflow-hidden"
          @click.stop>
          <!-- Modal Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
            <div class="flex items-center gap-3">
              <span class="w-8 h-8 bg-indigo-500 text-white rounded-full flex items-center justify-center text-sm font-bold">
                {{ versionModal.index + 1 }}
              </span>
              <div>
                <h3 class="text-base font-bold text-slate-900">{{ pick(`版本 ${versionModal.index + 1}`, `Version ${versionModal.index + 1}`) }}</h3>
                <p class="text-xs text-slate-500">{{ formatWordCountLabel(calculateWordCount(versionModal.content)) }}</p>
              </div>
            </div>
            <button @click="closeVersionModal"
              class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-200 transition-colors">
              <svg class="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Modal Content -->
          <div class="overflow-y-auto p-6 max-h-[calc(85vh-5rem)]">
            <div class="prose prose-slate max-w-none">
              <div class="text-base text-slate-900 leading-8 whitespace-pre-wrap font-serif">
                {{ versionModal.content }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NovelAPI } from '@/api/novel'
import type { ChapterVersion } from '@/api/novel'
import { AdminAPI } from '@/api/admin'
import { useRoute } from 'vue-router'
import { API_BASE_URL, API_PREFIX } from '@/api/config'
import { buildAuthHeaders } from '@/stores/auth'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import { useLocale } from '@/composables/useLocale'

interface ChapterItem {
  chapter_number: number
  title?: string | null
  summary?: string | null
  content?: string | null
  word_count?: number
}

interface ChapterDetail extends ChapterItem {
  real_summary?: string | null
  versions?: ChapterVersion[] | null
  evaluation?: string | null
  generation_status?: string
}

interface ExportPreflight {
  ready: boolean
  total_chapters: number
  outline_chapters: number
  exportable_chapters: number
  total_word_count: number
  missing_chapter_numbers?: number[]
  issues?: string[]
}

const props = defineProps<{
  chapters: ChapterItem[]
  isAdmin?: boolean
}>()

const route = useRoute()
const projectId = route.params.id as string

const { pick } = useLocale()

const selectedChapter = ref<ChapterDetail | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)
const failedChapterNumber = ref<number | null>(null)
const activeTab = ref<'content' | 'versions' | 'evaluation'>('content')

// 移动端章节列表显示状态
const showChapterList = ref(false)

// 版本弹窗状态
const versionModal = ref({
  show: false,
  content: '',
  index: 0
})

// 缓存已加载的章节详情
const chapterCache = new Map<number, ChapterDetail>()

const chapters = computed(() => props.chapters || [])

// Tab 配置：包成 computed，标签才会随语言切换刷新
const tabs = computed(() => [
  { key: 'content' as const, label: pick('正文', 'Draft'), badge: false },
  { key: 'versions' as const, label: pick('版本', 'Versions'), badge: true },
  { key: 'evaluation' as const, label: pick('评审', 'Review'), badge: false }
])

// 章节标题缺失时的回退文案
const chapterFallbackTitle = (chapterNumber: number): string => pick(`第${chapterNumber}章`, `Chapter ${chapterNumber}`)

const formatWordCountLabel = (count: number): string => pick(`${count} 字`, `${count} words`)

// 计算字数的辅助函数
const calculateWordCount = (content: string | null | undefined): number => {
  if (!content) return 0
  // 移除所有空白字符后计算字数
  return content.replace(/\s/g, '').length
}

// 获取状态标签
const getStatusLabel = (status: string): string => {
  // 键是后端 generation_status 枚举保持原文
  const statusMap: Record<string, string> = {
    'not_generated': pick('未生成', 'Not generated'),
    'generating': pick('生成中', 'Generating'),
    'evaluating': pick('评审中', 'Reviewing'),
    'selecting': pick('选择中', 'Selecting'),
    'failed': pick('生成失败', 'Generation failed'),
    'evaluation_failed': pick('评审失败', 'Review failed'),
    'waiting_for_confirm': pick('待确认', 'Awaiting confirmation'),
    'successful': pick('已完成', 'Completed')
  }
  return statusMap[status] || status
}

// 获取状态颜色
const getStatusColor = (status: string): string => {
  const colorMap: Record<string, string> = {
    'not_generated': 'bg-slate-100 text-slate-600',
    'generating': 'bg-blue-100 text-blue-700',
    'evaluating': 'bg-purple-100 text-purple-700',
    'selecting': 'bg-sky-100 text-sky-700',
    'failed': 'bg-red-100 text-red-700',
    'evaluation_failed': 'bg-sky-100 text-sky-700',
    'waiting_for_confirm': 'bg-sky-100 text-sky-700',
    'successful': 'bg-green-100 text-green-700'
  }
  return colorMap[status] || 'bg-slate-100 text-slate-600'
}

// 获取 Tab Badge 数量
const getTabBadgeCount = (tabKey: string): number => {
  if (!selectedChapter.value) return 0
  if (tabKey === 'versions') {
    return selectedChapter.value.versions?.length || 0
  }
  return 0
}

const sanitizeFileName = (name: string): string => {
  return name.replace(/[\\/:*?"<>|]/g, '_')
}

const triggerBrowserDownload = (blob: Blob, fileName: string) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const exportChapterAsTxt = () => {
  const chapter = selectedChapter.value
  if (!chapter) return

  const title = chapter.title?.trim() || chapterFallbackTitle(chapter.chapter_number)
  const safeTitle = sanitizeFileName(title) || `chapter-${chapter.chapter_number}`
  const content = chapter.content ?? ''
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  triggerBrowserDownload(blob, `${safeTitle}.txt`)
}

const exportChapterAsDocx = async () => {
  const chapter = selectedChapter.value
  if (!chapter) return

  const { Document, Packer, Paragraph, TextRun, HeadingLevel, PageBreakBefore } = await import('docx')

  const title = chapter.title?.trim() || chapterFallbackTitle(chapter.chapter_number)
  const safeTitle = sanitizeFileName(title) || `chapter-${chapter.chapter_number}`
  const content = chapter.content ?? ''

  // 解析内容为段落
  const paragraphs = content.split('\n\n').filter(p => p.trim())

  const doc = new Document({
    sections: [{
      properties: {},
      children: [
        // 章节标题
        new Paragraph({
          text: title,
          heading: HeadingLevel.HEADING_1,
          spacing: { after: 200 }
        }),
        // 内容段落
        ...paragraphs.map(para =>
          new Paragraph({
            children: [new TextRun({ text: para.trim(), size: 24 })],
            spacing: { after: 200 }
          })
        )
      ]
    }]
  })

  const blob = await Packer.toBlob(doc)
  triggerBrowserDownload(blob, `${safeTitle}.docx`)
}

const readExportFailure = async (response: Response): Promise<string> => {
  const rawText = await response.text().catch(() => '')
  try {
    const data = rawText ? JSON.parse(rawText) : {}
    const detail = data?.detail
    if (detail && typeof detail === 'object') {
      const message = typeof detail.message === 'string' ? detail.message : pick('导出失败', 'Export failed')
      const issues = Array.isArray(detail.issues) ? detail.issues.slice(0, 8).join('\n') : ''
      return issues ? `${message}\n${issues}` : message
    }
    if (typeof detail === 'string') return detail
    if (typeof data?.message === 'string') return data.message
  } catch {
    // fallback below
  }
  return rawText.trim() || pick('导出失败，请检查章节是否已生成并确认版本。', 'Export failed — check that the chapters are generated and a version is confirmed.')
}

const checkExportPreflight = async (): Promise<boolean> => {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/novels/${projectId}/export/preflight`, { headers: buildAuthHeaders() })
  if (!response.ok) {
    throw new Error(await readExportFailure(response))
  }
  const data = await response.json() as ExportPreflight
  if (data.ready) return true

  const issues = Array.isArray(data.issues) ? data.issues.slice(0, 10) : []
  const header = [
    pick(
      `当前可导出章节：${data.exportable_chapters}/${Math.max(data.total_chapters, data.outline_chapters)}`,
      `Exportable chapters: ${data.exportable_chapters}/${Math.max(data.total_chapters, data.outline_chapters)}`
    ),
    data.total_word_count ? pick(`可导出字数约 ${data.total_word_count} 字`, `Exportable word count: about ${data.total_word_count}`) : '',
  ].filter(Boolean).join('\n')
  throw new Error([header, ...issues].filter(Boolean).join('\n') || pick('小说仍有章节未生成、未定稿或正文为空。', 'Some chapters are still ungenerated, unfinalized, or have an empty draft.'))
}

// 导出全部章节
const exportAllChapters = async (format: 'txt' | 'docx') => {
  try {
    await checkExportPreflight()
    const url = `${API_BASE_URL}${API_PREFIX}/novels/${projectId}/export/${format}`
    const response = await fetch(url, { headers: buildAuthHeaders() })

    if (!response.ok) {
      throw new Error(await readExportFailure(response))
    }

    const blob = await response.blob()
    triggerBrowserDownload(blob, `${pick('小说', 'novel')}_${projectId}_${new Date().toISOString().split('T')[0]}.${format}`)
  } catch (err) {
    console.error(pick('导出失败:', 'Export failed:'), err)
    alert(err instanceof Error ? err.message : pick('导出失败，请重试', 'Export failed — please retry'))
  }
}

// 打开版本弹窗
const openVersionModal = (content: string, index: number) => {
  versionModal.value = {
    show: true,
    content,
    index
  }
}

// 关闭版本弹窗
const closeVersionModal = () => {
  versionModal.value.show = false
}

// 解析评审数据
const evaluationData = computed(() => {
  if (!selectedChapter.value?.evaluation) return null

  try {
    // 尝试解析 JSON
    const parsed = JSON.parse(selectedChapter.value.evaluation)
    return parsed
  } catch {
    // 如果不是 JSON，返回简单的文本格式
    return {
      feedback: selectedChapter.value.evaluation
    }
  }
})

// 获取评分标签
const getScoreLabel = (key: string | number): string => {
  const normalizedKey = typeof key === 'number' ? key.toString() : key
  // 键是后端评分维度枚举保持原文
  const labelMap: Record<string, string> = {
    'plot': pick('情节', 'Plot'),
    'character': pick('人物', 'Characters'),
    'writing': pick('文笔', 'Prose'),
    'logic': pick('逻辑', 'Logic'),
    'emotion': pick('情感', 'Emotion'),
    'creativity': pick('创意', 'Creativity'),
    'coherence': pick('连贯性', 'Continuity'),
    'engagement': pick('吸引力', 'Engagement')
  }
  return labelMap[normalizedKey] || normalizedKey
}

// 获取评分颜色
const getScoreColor = (score: number): string => {
  if (score >= 8) return 'text-green-600'
  if (score >= 6) return 'text-blue-600'
  if (score >= 4) return 'text-sky-600'
  return 'text-red-600'
}

// 获取评分条颜色
const getScoreBarColor = (score: number): string => {
  if (score >= 8) return 'bg-green-500'
  if (score >= 6) return 'bg-blue-500'
  if (score >= 4) return 'bg-sky-500'
  return 'bg-red-500'
}

// 从版本 key 中提取版本号 (version1 -> 1)
const getVersionNumber = (versionKey: string | number): number => {
  const normalizedKey = typeof versionKey === 'number' ? versionKey.toString() : versionKey
  const match = normalizedKey.match(/\d+/)
  return match ? parseInt(match[0]) : 0
}

// 获取版本标签
const getVersionLabel = (versionKey: string | number): string => {
  const num = getVersionNumber(versionKey)
  return pick(`版本 ${num}`, `Version ${num}`)
}

// 判断是否为选中的版本
const isSelectedVersion = (versionKey: string | number, bestChoice?: number): boolean => {
  if (!bestChoice) return false
  return getVersionNumber(versionKey) === bestChoice
}

const renderedRealSummary = ref('')

const renderMarkdown = (text: string | null | undefined): string => {
  if (!text) return ''

  return renderSafeMarkdown(text)
}

const normalizeVersion = (value: unknown): ChapterVersion => {
  if (typeof value === 'string') {
    return {
      content: value,
      style: '标准'
    }
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    const content = typeof record.content === 'string'
      ? record.content
      : (() => {
          try {
            return JSON.stringify(value, null, 2)
          } catch {
            return String(value)
          }
        })()
    return {
      id: typeof record.id === 'number' ? record.id : undefined,
      content,
      style: typeof record.style === 'string' ? record.style : '标准',
      evaluation: typeof record.evaluation === 'string' ? record.evaluation : undefined,
    }
  }
  return {
    content: String(value ?? ''),
    style: '标准'
  }
}

// 加载章节详情
const loadChapterDetail = async (chapterNumber: number) => {
  // 检查缓存
  failedChapterNumber.value = chapterNumber

  if (chapterCache.has(chapterNumber)) {
    selectedChapter.value = chapterCache.get(chapterNumber)!
    error.value = null
    return
  }

  isLoading.value = true
  error.value = null

  try {
    const detail = props.isAdmin
      ? await AdminAPI.getNovelChapter(projectId, chapterNumber)
      : await NovelAPI.getChapter(projectId, chapterNumber)

    const normalizedDetail: ChapterDetail = {
      ...detail,
      versions: Array.isArray(detail.versions)
        ? detail.versions.map(version => normalizeVersion(version))
        : detail.versions ?? null,
    }

    // 存入缓存
    chapterCache.set(chapterNumber, normalizedDetail)
    selectedChapter.value = normalizedDetail
    failedChapterNumber.value = chapterNumber
  } catch (err) {
    error.value = err instanceof Error ? err.message : pick('加载失败', 'Load failed')
    console.error(pick('加载章节详情失败:', 'Failed to load chapter detail:'), err)
  } finally {
    isLoading.value = false
  }
}

watch(
  () => selectedChapter.value?.real_summary,
  (summary) => {
    if (!summary) {
      renderedRealSummary.value = ''
      return
    }

    const html = renderMarkdown(summary)
    if (selectedChapter.value?.real_summary === summary) {
      renderedRealSummary.value = html
    }
  },
  { immediate: true }
)

watch(
  chapters,
  async (list) => {
    if (list.length === 0) {
      selectedChapter.value = null
      return
    }
    // 自动选中第一个章节（但不加载详情，等用户点击）
    if (!selectedChapter.value && list.length > 0) {
      await loadChapterDetail(list[0].chapter_number)
    }
  },
  { immediate: true }
)

const selectChapter = async (chapterNumber: number) => {
  activeTab.value = 'content' // 切换章节时重置到正文标签
  await loadChapterDetail(chapterNumber)
  // 移动端选择章节后关闭章节列表
  showChapterList.value = false
}

const retryFailedChapter = async () => {
  if (failedChapterNumber.value == null) return
  await selectChapter(failedChapterNumber.value)
}

const isAdmin = computed(() => props.isAdmin ?? false)

defineExpose({
  focusChapter: async (chapterNumber: number) => {
    const target = chapters.value.find(ch => ch.chapter_number === chapterNumber)
    if (target) {
      await loadChapterDetail(chapterNumber)
    }
  }
})
</script>

<style scoped>
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-4 {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-6 {
  display: -webkit-box;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'ChaptersSection'
})
</script>
