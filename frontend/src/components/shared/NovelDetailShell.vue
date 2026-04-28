<!-- AIMETA P=灏忚璇︽儏澹砡璇︽儏椤靛竷灞€瀹瑰櫒|R=璇︽儏椤靛竷灞€_瀵艰埅|NR=涓嶅惈鍏蜂綋鍐呭|E=component:NovelDetailShell|X=internal|A=甯冨眬缁勪欢|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="h-screen flex flex-col overflow-hidden md-surface">
    <!-- Material 3 Top App Bar -->
    <header class="md-top-app-bar sticky top-0 z-40">
      <div class="max-w-[1800px] mx-auto w-full flex items-center px-4 h-16">
        <!-- Leading: Menu Button (Mobile) -->
        <button
          class="md-icon-btn lg:hidden mr-2"
          @click="toggleSidebar"
          aria-label="Toggle sidebar"
        >
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <!-- Title -->
        <div class="flex-1 min-w-0">
          <h1 class="md-title-large truncate" style="color: var(--md-on-surface);">
            {{ formattedTitle }}
          </h1>
          <p v-if="overviewMeta.updated_at" class="md-body-small" style="color: var(--md-on-surface-variant);">
            最近更新：{{ formatDateTime(overviewMeta.updated_at) }}
          </p>
        </div>

        <!-- Trailing: Actions -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <button
            class="md-btn md-btn-outlined md-ripple"
            @click="goBack"
          >
            <svg class="w-5 h-5 hidden sm:block" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span class="hidden sm:inline">返回列表</span>
            <span class="sm:hidden">返回</span>
          </button>
          <button
            v-if="!isAdmin"
            class="md-btn md-btn-filled md-ripple"
            @click="goToWritingDesk"
          >
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
            <span class="hidden sm:inline">开始创作</span>
            <span class="sm:hidden">创作</span>
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <div class="flex max-w-[1800px] mx-auto w-full flex-1 min-h-0 overflow-hidden">
      <!-- Material 3 Navigation Drawer -->
      <aside
        class="fixed left-0 top-16 bottom-0 z-30 w-80 md-surface transform transition-transform duration-300 lg:translate-x-0"
        :class="isSidebarOpen ? 'translate-x-0' : '-translate-x-full'"
        style="border-right: 1px solid var(--md-outline-variant);"
      >
        <!-- Drawer Header -->
        <div class="flex items-center gap-3 px-6 py-4" style="border-bottom: 1px solid var(--md-outline-variant);">
          <div class="w-10 h-10 rounded-full flex items-center justify-center" style="background-color: var(--md-primary-container);">
            <svg class="w-5 h-5" style="color: var(--md-on-primary-container);" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          </div>
          <span class="md-title-medium" style="color: var(--md-on-surface);">
            {{ isAdmin ? '内容视图' : '蓝图导航' }}
          </span>
        </div>

        <!-- Navigation Items -->
        <nav class="px-3 py-4 space-y-1 overflow-y-auto h-[calc(100%-5rem)]">
          <button
            v-for="section in sections"
            :key="section.key"
            type="button"
            @click="switchSection(section.key)"
            class="md-nav-drawer-item w-full md-ripple"
            :class="{ 'active': activeSection === section.key }"
          >
            <span
              class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full transition-all duration-200"
              :style="activeSection === section.key
                ? 'background-color: var(--md-primary); color: var(--md-on-primary);'
                : 'background-color: var(--md-surface-container); color: var(--md-on-surface-variant);'"
            >
              <component :is="getSectionIcon(section.key)" class="w-5 h-5" />
            </span>
            <span class="text-left flex-1">
              <span class="block md-label-large">{{ section.label }}</span>
              <span class="md-body-small" style="color: var(--md-on-surface-variant);">{{ section.description }}</span>
            </span>
          </button>
        </nav>
      </aside>

      <!-- Sidebar Overlay (Mobile) -->
      <transition
        enter-active-class="transition-opacity duration-300"
        leave-active-class="transition-opacity duration-300"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <div
          v-if="isSidebarOpen"
          class="fixed inset-0 z-20 lg:hidden"
          style="background-color: rgba(0, 0, 0, 0.32);"
          @click="toggleSidebar"
        ></div>
      </transition>

      <!-- Main Content Area -->
      <div class="flex-1 lg:ml-80 min-h-0 flex flex-col h-full">
        <div class="flex-1 min-h-0 h-full p-4 sm:p-6 lg:p-8 flex flex-col overflow-hidden box-border">
          <div class="flex-1 flex flex-col min-h-0 h-full">
            <!-- Material 3 Card -->
            <div 
              class="md-card md-card-elevated flex-1 h-full p-6 sm:p-8 min-h-[20rem] flex flex-col box-border" 
              :class="contentCardClass"
              style="border-radius: var(--md-radius-lg);"
            >
              <!-- Loading State -->
              <div v-if="isSectionLoading" class="flex flex-col items-center justify-center py-20 sm:py-28">
                <div class="md-spinner"></div>
                <p class="mt-4 md-body-medium" style="color: var(--md-on-surface-variant);">正在加载 {{ activeSectionMeta.label }}</p>
                <p class="mt-2 md-body-small text-center" style="color: var(--md-on-surface-variant);">{{ activeSectionMeta.description }}</p>
              </div>

              <!-- Error State -->
              <div v-else-if="currentError" class="flex flex-col items-center justify-center py-20 sm:py-28 space-y-4">
                <div class="w-16 h-16 rounded-full flex items-center justify-center" style="background-color: var(--md-error-container);">
                  <svg class="w-8 h-8" style="color: var(--md-error);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p class="md-body-large text-center" style="color: var(--md-on-surface);">{{ currentError }}</p>
                <p class="md-body-small text-center max-w-md" style="color: var(--md-on-surface-variant);">可以先重试当前分析区；如果仍然失败，也可以先切换到其他模块继续查看，不会影响整个项目详情页。</p>
                <button
                  class="md-btn md-btn-filled md-ripple"
                  @click="reloadSection(activeSection, true)"
                >
                  重试
                </button>
              </div>

              <!-- Content -->
              <component
                v-else
                :is="currentComponent"
                v-bind="componentProps"
                :class="componentContainerClass"
                @edit="handleSectionEdit"
                @add="startAddChapter"
                @evolve="openEvolveModal"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Blueprint Edit Modal -->
    <BlueprintEditModal
      v-if="!isAdmin"
      :show="isModalOpen"
      :title="modalTitle"
      :content="modalContent"
      :field="modalField"
      @close="isModalOpen = false"
      @save="handleSave"
    />

    <!-- Material 3 Add Chapter Modal -->
    <transition
      enter-active-class="md-scale-enter-active"
      leave-active-class="md-scale-leave-active"
      enter-from-class="md-scale-enter-from"
      leave-to-class="md-scale-leave-to"
    >
      <div v-if="isAddChapterModalOpen && !isAdmin" class="md-dialog-overlay">
        <div class="absolute inset-0" @click="cancelNewChapter"></div>
        <div class="md-dialog relative w-full max-w-lg mx-4" @click.stop>
          <div class="md-dialog-header">
            <h3 class="md-dialog-title">鏂板绔犺妭澶х翰</h3>
          </div>
          <div class="md-dialog-content space-y-6">
            <div class="md-text-field">
              <label for="new-chapter-title" class="md-text-field-label">
                绔犺妭鏍囬
              </label>
              <input
                id="new-chapter-title"
                v-model="newChapterTitle"
                type="text"
                class="md-text-field-input"
                placeholder="渚嬪锛氭剰澶栫殑鐩搁亣"
              >
            </div>
            <div class="md-text-field">
              <label for="new-chapter-summary" class="md-text-field-label">
                绔犺妭鎽樿
              </label>
              <textarea
                id="new-chapter-summary"
                v-model="newChapterSummary"
                rows="4"
                class="md-textarea w-full"
                placeholder="绠€瑕佹弿杩版湰绔犲彂鐢熺殑涓昏浜嬩欢"
              ></textarea>
            </div>
          </div>
          <div class="md-dialog-actions">
            <button
              type="button"
              class="md-btn md-btn-text md-ripple"
              @click="cancelNewChapter"
            >
              鍙栨秷
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple"
              @click="saveNewChapter"
            >
              淇濆瓨
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 鍓ф儏婕旇繘寮圭獥 -->
    <WDEvolveOutlineModal
      :show="showEvolveModal"
      :project-id="novel?.id || projectId"
      :chapter-number="evolveChapterNumber"
      @close="showEvolveModal = false"
      @select="handleSelectEvolveOption"
    />

    <!-- 璁板繂绠＄悊寮圭獥 -->
    <WDMemoryManageModal
      :show="showMemoryModal"
      :project-id="novel?.id || projectId"
      @close="showMemoryModal = false"
      @updated="handleMemoryUpdated"
    />

    <!-- Token棰勭畻绠＄悊寮圭獥 -->
    <WDTokenBudgetModal
      :show="showTokenBudgetModal"
      :project-id="novel?.id || projectId"
      @close="showTokenBudgetModal = false"
      @updated="reloadSection('overview', true)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { NovelAPI, OptimizerAPI, AnalyticsAPI } from '@/api/novel'
import { AdminAPI } from '@/api/admin'
import type { NovelProject, NovelSectionResponse, NovelSectionType, AllSectionType } from '@/api/novel'
import { formatDateTime } from '@/utils/date'
import OverviewSection from '@/components/novel-detail/OverviewSection.vue'
import WorldSettingSection from '@/components/novel-detail/WorldSettingSection.vue'
import CharactersSection from '@/components/novel-detail/CharactersSection.vue'
import RelationshipsSection from '@/components/novel-detail/RelationshipsSection.vue'
import ChapterOutlineSection from '@/components/novel-detail/ChapterOutlineSection.vue'
import AnalysisWorkbench from '@/components/novel-detail/AnalysisWorkbench.vue'

const BlueprintEditModal = defineAsyncComponent(() => import('@/components/BlueprintEditModal.vue'))
const ChaptersSection = defineAsyncComponent(() => import('@/components/novel-detail/ChaptersSection.vue'))
const EmotionCurveSection = defineAsyncComponent(() => import('@/components/novel-detail/EmotionCurveSection.vue'))
const ForeshadowingSection = defineAsyncComponent(() => import('@/components/novel-detail/ForeshadowingSection.vue'))
const KnowledgeGraphView = defineAsyncComponent(() => import('@/components/knowledge-graph/KnowledgeGraphView.vue'))
const ClueTrackerView = defineAsyncComponent(() => import('@/components/clue-tracker/ClueTrackerView.vue'))
const WDEvolveOutlineModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDEvolveOutlineModal.vue'))
const WDMemoryManageModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDMemoryManageModal.vue'))
const WDTokenBudgetModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDTokenBudgetModal.vue'))

interface Props {
  isAdmin?: boolean
}

type SectionKey = AllSectionType

const props = withDefaults(defineProps<Props>(), {
  isAdmin: false
})

const route = useRoute()
const router = useRouter()
const novelStore = useNovelStore()

const projectId = route.params.id as string
const isSidebarOpen = ref(typeof window !== 'undefined' ? window.innerWidth >= 1024 : true)

const sections: Array<{ key: SectionKey; label: string; description: string }> = [
  { key: 'overview', label: '项目概览', description: '定位与整体梗概' },
  { key: 'world_setting', label: '世界设定', description: '规则、地点与阵营' },
  { key: 'characters', label: '主要角色', description: '人物性格与目标' },
  { key: 'relationships', label: '人物关系', description: '角色之间的联系' },
  { key: 'chapter_outline', label: '章节大纲', description: props.isAdmin ? '故事章节规划' : '故事结构规划' },
  { key: 'chapters', label: '章节内容', description: props.isAdmin ? '生成章节与正文' : '生成状态与摘要' },
  { key: 'emotion_curve', label: '情感曲线', description: '追踪章节情感变化' },
  { key: 'story_trajectory', label: '故事轨迹', description: '识别情节走势与关键转折' },
  { key: 'creative_guidance', label: '创意指导', description: '给出当前章节与后续建议' },
  { key: 'comprehensive_analysis', label: '综合分析', description: '汇总情感、轨迹与指导结果' },
  { key: 'foreshadowing', label: '伏笔管理', description: '埋下、推进与回收看板' },
  { key: 'knowledge_graph', label: '知识图谱', description: '角色关系与情节追踪' },
  { key: 'style_learning', label: '风格学习', description: '直达文风中心，支持外部片段与整本小说导入' },
  { key: 'memory_management', label: '记忆管理', description: '动态记忆层与版本控制' },
  { key: 'token_budget', label: 'Token预算', description: '控制AI生成成本与模块分配' },
  { key: 'clue_tracker', label: '线索追踪', description: '伏笔、红鲱鱼与推理线索管理' }
]
const sectionComponents: Record<SectionKey, any> = {
  overview: OverviewSection,
  world_setting: WorldSettingSection,
  characters: CharactersSection,
  relationships: RelationshipsSection,
  chapter_outline: ChapterOutlineSection,
  chapters: ChaptersSection,
  emotion_curve: EmotionCurveSection,
  story_trajectory: AnalysisWorkbench,
  creative_guidance: AnalysisWorkbench,
  comprehensive_analysis: AnalysisWorkbench,
  foreshadowing: ForeshadowingSection,
  knowledge_graph: KnowledgeGraphView,
  clue_tracker: ClueTrackerView,
  style_learning: null,
  memory_management: null,
  token_budget: null
}

// Section icons as functional components
const getSectionIcon = (key: SectionKey) => {
  const icons: Record<SectionKey, any> = {
    overview: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('rect', { x: 3, y: 3, width: 18, height: 18, rx: 2 }),
      h('line', { x1: 3, y1: 9, x2: 21, y2: 9 }),
      h('line', { x1: 9, y1: 21, x2: 9, y2: 9 })
    ]),
    world_setting: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 12, cy: 12, r: 10 }),
      h('path', { d: 'M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z' })
    ]),
    characters: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2' }),
      h('circle', { cx: 9, cy: 7, r: 4 }),
      h('path', { d: 'M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75' })
    ]),
    relationships: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2' }),
      h('circle', { cx: 9, cy: 7, r: 4 }),
      h('path', { d: 'M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75' })
    ]),
    chapter_outline: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('line', { x1: 8, y1: 6, x2: 21, y2: 6 }),
      h('line', { x1: 8, y1: 12, x2: 21, y2: 12 }),
      h('line', { x1: 8, y1: 18, x2: 21, y2: 18 }),
      h('line', { x1: 3, y1: 6, x2: 3.01, y2: 6 }),
      h('line', { x1: 3, y1: 12, x2: 3.01, y2: 12 }),
      h('line', { x1: 3, y1: 18, x2: 3.01, y2: 18 })
    ]),
    chapters: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 19.5A2.5 2.5 0 016.5 17H20' }),
      h('path', { d: 'M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z' })
    ]),
    emotion_curve: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' })
    ]),
    story_trajectory: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M3 17l6-6 4 4 8-8' }),
      h('path', { d: 'M14 7h7v7' })
    ]),
    creative_guidance: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M12 2l2.4 4.86L20 9l-4 3.89L16.8 19 12 16.27 7.2 19l.8-6.11L4 9l5.6-2.14L12 2z' })
    ]),
    comprehensive_analysis: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M9 11l3 3L22 4' }),
      h('path', { d: 'M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11' })
    ]),
    foreshadowing: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M13 10V3L4 14h7v7l9-11h-7z' })
    ]),
    knowledge_graph: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 12, cy: 12, r: 3 }),
      h('circle', { cx: 4, cy: 6, r: 2 }),
      h('circle', { cx: 20, cy: 6, r: 2 }),
      h('circle', { cx: 4, cy: 18, r: 2 }),
      h('circle', { cx: 20, cy: 18, r: 2 }),
      h('line', { x1: 9.5, y1: 10, x2: 5.5, y2: 7.5 }),
      h('line', { x1: 14.5, y1: 10, x2: 18.5, y2: 7.5 }),
      h('line', { x1: 9.5, y1: 14, x2: 5.5, y2: 16.5 }),
      h('line', { x1: 14.5, y1: 14, x2: 18.5, y2: 16.5 })
    ]),
    clue_tracker: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 11, cy: 11, r: 7 }),
      h('line', { x1: 21, y1: 21, x2: 16.65, y2: 16.65 }),
      h('path', { d: 'M11 8v3l2 2' })
    ]),
    style_learning: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5' })
    ]),
    memory_management: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('path', { d: 'M4 19.5A2.5 2.5 0 016.5 17H20' }),
      h('path', { d: 'M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z' })
    ]),
    token_budget: () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 }, [
      h('circle', { cx: 12, cy: 12, r: 9 }),
      h('path', { d: 'M8 10h8M8 14h5' }),
      h('path', { d: 'M12 7v10' })
    ])
  }
  return icons[key]
}

const sectionData = reactive<Partial<Record<SectionKey, any>>>({})
const sectionLoading = reactive<Record<SectionKey, boolean>>({
  overview: false,
  world_setting: false,
  characters: false,
  relationships: false,
  chapter_outline: false,
  chapters: false,
  emotion_curve: false,
  story_trajectory: false,
  creative_guidance: false,
  comprehensive_analysis: false,
  foreshadowing: false,
  knowledge_graph: false,
  clue_tracker: false,
  style_learning: false,
  memory_management: false,
  token_budget: false
})
const sectionError = reactive<Record<SectionKey, string | null>>({
  overview: null,
  world_setting: null,
  characters: null,
  relationships: null,
  chapter_outline: null,
  chapters: null,
  emotion_curve: null,
  story_trajectory: null,
  creative_guidance: null,
  comprehensive_analysis: null,
  foreshadowing: null,
  knowledge_graph: null,
  clue_tracker: null,
  style_learning: null,
  memory_management: null,
  token_budget: null
})

const overviewMeta = reactive<{ title: string; updated_at: string | null }>({
  title: '鍔犺浇涓?..',
  updated_at: null
})

const activeSection = ref<SectionKey>('overview')
const activeSectionMeta = computed(() => sections.find(section => section.key === activeSection.value) || sections[0])

// Modal state (user mode only)
const isModalOpen = ref(false)
const modalTitle = ref('')
const modalContent = ref<any>('')
const modalField = ref('')

// Add chapter modal state (user mode only)
const isAddChapterModalOpen = ref(false)
const newChapterTitle = ref('')
const newChapterSummary = ref('')

// 鍓ф儏鎺ㄦ紨鐩稿叧鐘舵€?
const showEvolveModal = ref(false)

// 璁板繂绠＄悊涓?Token 棰勭畻寮圭獥鐘舵€?
const showMemoryModal = ref(false)
const showTokenBudgetModal = ref(false)
const evolveLoading = ref(false)
const evolveAlternatives = ref<any[]>([])
const evolveChapterNumber = ref(1)
const originalBodyOverflow = ref('')

const novel = computed(() => !props.isAdmin ? novelStore.currentProject as NovelProject | null : null)

const formattedTitle = computed(() => {
  const title = overviewMeta.title || '加载中…'
  return title.startsWith('《') && title.endsWith('》') ? title : `《${title}》`
})

const componentContainerClass = computed(() => {
  const fillSections: SectionKey[] = ['chapters']
  return fillSections.includes(activeSection.value)
    ? 'flex-1 min-h-0 h-full flex flex-col overflow-hidden'
    : 'overflow-y-auto'
})

const contentCardClass = computed(() => {
  const fillSections: SectionKey[] = ['chapters']
  return fillSections.includes(activeSection.value)
    ? 'overflow-hidden'
    : 'overflow-visible'
})

// 鎳掑姞杞藉畬鏁撮」鐩紙浠呭湪闇€瑕佺紪杈戞椂锛?
const ensureProjectLoaded = async () => {
  if (props.isAdmin || !projectId) return
  if (novel.value) return // 宸插姞杞?
  await novelStore.loadProject(projectId)
}

const toggleSidebar = () => {
  isSidebarOpen.value = !isSidebarOpen.value
}

const handleResize = () => {
  if (typeof window === 'undefined') return
  isSidebarOpen.value = window.innerWidth >= 1024
}

const loadSection = async (section: SectionKey, force = false) => {
  if (!projectId) return

  // 鍒嗘瀽鍨婼ection浣跨敤鐙珛鐨凙PI锛屼笉闇€瑕佸湪杩欓噷鍔犺浇
  const analysisSections: SectionKey[] = [
    'emotion_curve',
    'story_trajectory',
    'creative_guidance',
    'comprehensive_analysis',
    'foreshadowing',
    'knowledge_graph',
    'clue_tracker'
  ]
  if (analysisSections.includes(section)) {
    return
  }
  
  if (!force && sectionData[section]) {
    return
  }

  sectionLoading[section] = true
  sectionError[section] = null
  try {
    const response: NovelSectionResponse = props.isAdmin
      ? await AdminAPI.getNovelSection(projectId, section as NovelSectionType)
      : await NovelAPI.getSection(projectId, section as NovelSectionType)
    sectionData[section] = response.data
    if (section === 'overview') {
      overviewMeta.title = response.data?.title || overviewMeta.title
      overviewMeta.updated_at = response.data?.updated_at || null
    }
  } catch (error) {
    console.error('鍔犺浇妯″潡澶辫触:', error)
    sectionError[section] = error instanceof Error ? error.message : '鍔犺浇澶辫触'
  } finally {
    sectionLoading[section] = false
  }
}

const reloadSection = (section: SectionKey, force = false) => {
  if (section === 'story_trajectory' || section === 'creative_guidance' || section === 'comprehensive_analysis') {
    fetchAnalysisSection(section)
    return
  }
  loadSection(section, force)
}

const fetchAnalysisSection = async (section: Extract<SectionKey, 'story_trajectory' | 'creative_guidance' | 'comprehensive_analysis'>) => {
  if (!projectId) return

  sectionLoading[section] = true
  sectionError[section] = null

  try {
    const targetProjectId = novel.value?.id || projectId
    if (section === 'story_trajectory') {
      sectionData[section] = await AnalyticsAPI.getStoryTrajectory(targetProjectId)
    } else if (section === 'creative_guidance') {
      sectionData[section] = await AnalyticsAPI.getCreativeGuidance(targetProjectId)
    } else {
      sectionData[section] = await AnalyticsAPI.getComprehensiveAnalysis(targetProjectId)
    }
  } catch (error) {
    console.error('鍔犺浇澧炲己鍒嗘瀽澶辫触:', error)
    sectionError[section] = error instanceof Error ? error.message : '鍔犺浇澶辫触'
  } finally {
    sectionLoading[section] = false
  }
}

const switchSection = (section: SectionKey) => {
  // 椋庢牸瀛︿範鐩磋揪鏂囬涓績锛涜蹇嗙鐞嗐€乀oken棰勭畻浠嶇洿鎺ユ墦寮€寮圭獥
  if (section === 'style_learning') {
    router.push('/style-center')
    return
  }
  if (section === 'memory_management') {
    showMemoryModal.value = true
    return
  }
  if (section === 'token_budget') {
    showTokenBudgetModal.value = true
    return
  }

  activeSection.value = section
  if (typeof window !== 'undefined' && window.innerWidth < 1024) {
    isSidebarOpen.value = false
  }

  if (section === 'story_trajectory' || section === 'creative_guidance' || section === 'comprehensive_analysis') {
    fetchAnalysisSection(section)
    return
  }

  loadSection(section)
}

const goBack = () => router.push(props.isAdmin ? '/admin' : '/workspace')

const goToWritingDesk = async () => {
  await ensureProjectLoaded()
  const project = novel.value
  if (!project) return
  const path = project.title === '未命名灵感项目' ? `/inspiration?project_id=${project.id}` : `/novel/${project.id}`
  router.push(path)
}

const currentComponent = computed(() => sectionComponents[activeSection.value])
const isSectionLoading = computed(() => sectionLoading[activeSection.value])
const currentError = computed(() => sectionError[activeSection.value])

const componentProps = computed(() => {
  const data = sectionData[activeSection.value]
  const editable = !props.isAdmin

  switch (activeSection.value) {
    case 'overview':
      return { data: data || null, editable }
    case 'world_setting':
      return { data: data || null, editable }
    case 'characters':
      return { data: data || null, editable }
    case 'relationships':
      return { data: data || null, editable }
    case 'chapter_outline':
      return {
        outline: data?.chapter_outline || [],
        editable,
        projectId: novel.value?.id || projectId,
        chapterNumber: data?.chapters?.[0]?.chapter_number || 1
      }
    case 'chapters':
      return { chapters: data?.chapters || [], isAdmin: props.isAdmin }
    case 'emotion_curve':
    case 'foreshadowing':
    case 'knowledge_graph':
      return { projectId: novel.value?.id || projectId }
    case 'story_trajectory':
    case 'creative_guidance':
    case 'comprehensive_analysis':
      return {
        sectionType: activeSection.value,
        data
      }
    case 'clue_tracker':
      return { projectId: novel.value?.id || projectId || '' }
    default:
      return {}
  }
})

const handleSectionEdit = (payload: { field: string; title: string; value: any }) => {
  if (props.isAdmin) return
  modalField.value = payload.field
  modalTitle.value = payload.title
  modalContent.value = payload.value
  isModalOpen.value = true
}

const resolveSectionKey = (field: string): SectionKey => {
  if (field.startsWith('world_setting')) return 'world_setting'
  if (field.startsWith('characters')) return 'characters'
  if (field.startsWith('relationships')) return 'relationships'
  if (field.startsWith('chapter_outline')) return 'chapter_outline'
  return 'overview'
}

const handleSave = async (data: { field: string; content: any }) => {
  if (props.isAdmin) return
  await ensureProjectLoaded()
  const project = novel.value
  if (!project) return

  const { field, content } = data
  const payload: Record<string, any> = {}

  if (field.includes('.')) {
    const [parentField, childField] = field.split('.')
    payload[parentField] = {
      ...(project.blueprint?.[parentField as keyof typeof project.blueprint] as Record<string, any> | undefined),
      [childField]: content
    }
  } else {
    payload[field] = content
  }

  try {
    if (field === 'world_setting.factions') {
      await NovelAPI.updateFactions(project.id, Array.isArray(content) ? content : [])
      const updatedProject = await NovelAPI.getNovel(project.id)
      novelStore.setCurrentProject(updatedProject)
    } else {
      const updatedProject = await NovelAPI.updateBlueprint(project.id, payload)
      novelStore.setCurrentProject(updatedProject)
    }
    const sectionToReload = resolveSectionKey(field)
    await loadSection(sectionToReload, true)
    if (sectionToReload !== 'overview') {
      await loadSection('overview', true)
    }
    isModalOpen.value = false
  } catch (error) {
    console.error('淇濆瓨鍙樻洿澶辫触:', error)
  }
}

const startAddChapter = async () => {
  if (props.isAdmin) return
  await ensureProjectLoaded()
  const outline = sectionData.chapter_outline?.chapter_outline || novel.value?.blueprint?.chapter_outline || []
  const nextNumber = outline.length > 0 ? Math.max(...outline.map((item: any) => item.chapter_number)) + 1 : 1
  newChapterTitle.value = `新章节 ${nextNumber}`
  newChapterSummary.value = ''
  isAddChapterModalOpen.value = true
}

const cancelNewChapter = () => {
  isAddChapterModalOpen.value = false
}

// 鍓ф儏鎺ㄦ紨鐩稿叧鍑芥暟
const openEvolveModal = async (payload: { projectId: string; chapterNumber: number }) => {
  if (props.isAdmin) return
  evolveChapterNumber.value = payload.chapterNumber
  showEvolveModal.value = true
  evolveLoading.value = true
  evolveAlternatives.value = []

  try {
    const res = await OptimizerAPI.evolveOutline(payload.projectId, payload.chapterNumber, 3)
    evolveAlternatives.value = res.alternatives
  } catch (e) {
    console.error('鐢熸垚鍓ф儏婕旇繘閫夐」澶辫触:', e)
  } finally {
    evolveLoading.value = false
  }
}

const handleSelectEvolveOption = async (option: any) => {
  const project = novel.value
  if (!project || props.isAdmin) return

  try {
    await OptimizerAPI.selectAlternative(project.id, option.id, evolveChapterNumber.value)
    showEvolveModal.value = false
    // 鍒锋柊澶х翰鏁版嵁
    await novelStore.loadProject(project.id)
    // 鍒囨崲鍒扮珷鑺傚ぇ绾叉爣绛?
    activeSection.value = 'chapter_outline'
  } catch (e) {
    console.error('閫夋嫨鍓ф儏閫夐」澶辫触:', e)
  }
}

// 椋庢牸瀛︿範鐩稿叧澶勭悊鍑芥暟
async function handleStyleExtracted(summary: any) {
  console.log('风格已提取:', summary)
  await loadSection('overview', true)
  if (activeSection.value === 'creative_guidance' || activeSection.value === 'comprehensive_analysis') {
    await fetchAnalysisSection(activeSection.value)
  }
}

// 璁板繂绠＄悊鐩稿叧澶勭悊鍑芥暟
async function handleMemoryUpdated() {
  console.log('记忆已更新')
  await loadSection('overview', true)
  if (activeSection.value === 'creative_guidance' || activeSection.value === 'comprehensive_analysis') {
    await fetchAnalysisSection(activeSection.value)
  }
}

const saveNewChapter = async () => {
  if (props.isAdmin) return
  await ensureProjectLoaded()
  const project = novel.value
  if (!project) return
  if (!newChapterTitle.value.trim()) {
    alert('章节标题不能为空')
    return
  }

  const existingOutline = project.blueprint?.chapter_outline || []
  const nextNumber = existingOutline.length > 0 ? Math.max(...existingOutline.map(ch => ch.chapter_number)) + 1 : 1
  const newOutline = [...existingOutline, {
    chapter_number: nextNumber,
    title: newChapterTitle.value,
    summary: newChapterSummary.value
  }]

  try {
    const updatedProject = await NovelAPI.updateBlueprint(project.id, { chapter_outline: newOutline })
    novelStore.setCurrentProject(updatedProject)
    await loadSection('chapter_outline', true)
    isAddChapterModalOpen.value = false
  } catch (error) {
    console.error('鏂板绔犺妭澶辫触:', error)
  }
}

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', handleResize)
  }
  if (typeof document !== 'undefined') {
    originalBodyOverflow.value = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }

  // 鍙姞杞藉繀瑕佺殑 section 鏁版嵁锛屼笉棰勫姞杞藉畬鏁撮」鐩?
  await loadSection('overview', true)
  loadSection('world_setting')
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', handleResize)
  }
  if (typeof document !== 'undefined') {
    document.body.style.overflow = originalBodyOverflow.value || ''
  }
})
</script>

<style scoped>
/* Material 3 Transition Classes */
.md-scale-enter-active,
.md-scale-leave-active {
  transition: all 250ms cubic-bezier(0.2, 0, 0, 1);
}

.md-scale-enter-from,
.md-scale-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/* Smooth scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--md-outline);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--md-on-surface-variant);
}
</style>

