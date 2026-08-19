<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="handleClose">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-150"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-slate-950/45 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-3 sm:p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-200"
            enter-from="opacity-0 translate-y-4 sm:scale-95"
            enter-to="opacity-100 translate-y-0 sm:scale-100"
            leave="ease-in duration-150"
            leave-from="opacity-100 translate-y-0 sm:scale-100"
            leave-to="opacity-0 translate-y-4 sm:scale-95"
          >
            <DialogPanel class="xq-dialog-shell xq-dialog-shell--xl skill-dialog-shell">
              <div class="xq-dialog-header skill-dialog-header">
                <div>
                  <DialogTitle as="h3">{{ pick('写作技能中心', 'Writing skill hub') }}</DialogTitle>
                  <p>{{ pick(
                    '安装只是把技能加入你的可用工具箱；执行时才会把当前项目、当前章节和你的输入一起送进去分析，不会自动改系统配置，也不会直接覆盖正文。',
                    'Installing only adds a skill to your toolbox. Running it sends this project, this chapter and your input in for analysis — it never changes system settings and never overwrites the draft.',
                  ) }}</p>
                </div>
                <button type="button" class="xq-dialog-close" :aria-label="t('common.close')" @click="handleClose">×</button>
              </div>

              <div class="xq-dialog-body skill-dialog-body">
                <section class="skill-guide-panel">
                  <article>
                    <h4>{{ pick('技能的安装与使用逻辑', 'How installing and running works') }}</h4>
                    <ul>
                      <li><strong>{{ pick('安装：', 'Install: ') }}</strong>{{ pick(
                        '只是启用这项技能，不会修改系统配置，也不会覆盖全局 LLM 配置。',
                        'this only enables the skill; system settings and the global LLM configuration stay untouched.',
                      ) }}</li>
                      <li><strong>{{ pick('执行：', 'Run: ') }}</strong>{{ pick(
                        '会把你填写的要求，连同当前项目 / 当前章节上下文一起送入技能。',
                        'your instructions go in together with the current project and chapter context.',
                      ) }}</li>
                      <li><strong>{{ pick('产出：', 'Output: ') }}</strong>{{ pick(
                        '默认返回建议、诊断或改写方向，不会直接覆盖正文。',
                        'by default you get suggestions, diagnostics or rewrite directions — the draft is never overwritten.',
                      ) }}</li>
                      <li><strong>{{ pick('冲突：', 'Conflicts: ') }}</strong>{{ pick(
                        '技能之间不会互相覆盖配置，可以按需组合使用。',
                        'skills never override each other, so you can combine them freely.',
                      ) }}</li>
                    </ul>
                  </article>
                  <article>
                    <h4>{{ pick('推荐用法', 'Suggested workflow') }}</h4>
                    <ul>
                      <li>{{ pick(
                        '先用诊断类技能找问题，再用节奏类、对白类、润色类技能定向补强。',
                        'Start with a diagnostic skill to find the problem, then reach for pacing, dialogue or polish skills.',
                      ) }}</li>
                      <li>{{ pick(
                        '如果你只想改局部，输入里直接点明：哪一段、哪个人物、想强化什么效果。',
                        'For a local fix, say exactly which passage, which character and which effect you want.',
                      ) }}</li>
                      <li>{{ pick(
                        '技能结果会保留在右侧，方便你复制回重写或局部优化。',
                        'Results stay on the right so you can copy them into a rewrite or a local pass.',
                      ) }}</li>
                    </ul>
                  </article>
                </section>

                <div v-if="operationVisible" class="skill-progress-card">
                  <div class="progress-row">
                    <span>{{ operationTitle }}</span>
                    <strong>{{ operationStep }}</strong>
                  </div>
                  <div class="progress-track">
                    <div class="progress-bar progress-bar--indeterminate"></div>
                  </div>
                  <p>{{ operationHint }}</p>
                </div>

                <div class="skill-main-grid">
                  <section>
                    <div class="skill-section-head">
                      <h4>{{ pick('技能目录', 'Skill catalogue') }}</h4>
                      <button type="button" class="text-sm text-indigo-600 hover:text-indigo-700" @click="loadData">{{ t('common.refresh') }}</button>
                    </div>

                    <div v-if="loading" class="skill-empty">{{ pick('正在加载技能目录…', 'Loading the skill catalogue…') }}</div>
                    <div v-else class="skill-card-grid">
                      <button
                        v-for="skill in catalog"
                        :key="skill.id"
                        type="button"
                        class="skill-catalog-card"
                        :class="selectedSkill?.id === skill.id ? 'skill-catalog-card--active' : ''"
                        @click="selectedSkill = skill"
                      >
                        <div class="skill-catalog-card__head">
                          <div>
                            <p class="skill-catalog-card__title">{{ catalogName(skill) }}</p>
                            <p class="skill-catalog-card__meta">{{ catalogCategory(skill) || pick('未分类', 'Uncategorised') }} · {{ skill.version }}</p>
                          </div>
                          <span :class="['skill-status-badge', skill.installed ? 'skill-status-badge--installed' : '']">
                            {{ skill.installed ? pick('已安装', 'Installed') : pick('未安装', 'Not installed') }}
                          </span>
                        </div>
                        <p class="skill-catalog-card__desc">{{ catalogDescription(skill) || pick('暂无说明', 'No description') }}</p>
                      </button>
                    </div>
                  </section>

                  <section class="skill-detail-panel">
                    <template v-if="selectedSkill">
                      <div class="skill-detail-panel__head">
                        <div>
                          <h4>{{ skillDisplay.name }}</h4>
                          <p>{{ skillDisplay.category || pick('未分类', 'Uncategorised') }} · {{ selectedSkill.version }} · {{ selectedSkill.author || pick('玄穹文枢', 'Xuanqiong Wenshu') }}</p>
                        </div>
                        <button
                          type="button"
                          class="skill-install-btn"
                          :class="selectedSkill.installed ? 'skill-install-btn--danger' : 'skill-install-btn--primary'"
                          :disabled="installing || executing"
                          @click="selectedSkill.installed ? uninstallSkill(selectedSkill.id) : installSkill(selectedSkill)"
                        >
                          {{ selectedSkill.installed ? pick('卸载技能', 'Remove skill') : pick('安装技能', 'Install skill') }}
                        </button>
                      </div>

                      <p class="skill-detail-panel__summary">{{ skillDisplay.description || pick('暂无技能说明。', 'No description for this skill yet.') }}</p>

                      <div class="skill-detail-sections">
                        <article v-if="skillDisplay.overview">
                          <h5>{{ pick('技能简介', 'What it does') }}</h5>
                          <p>{{ skillDisplay.overview }}</p>
                        </article>
                        <article v-if="skillDisplay.inputGuide">
                          <h5>{{ pick('建议输入方式', 'How to phrase your input') }}</h5>
                          <p>{{ skillDisplay.inputGuide }}</p>
                        </article>
                        <article v-if="skillDisplay.examplePrompt">
                          <h5>{{ pick('示例要求', 'Example request') }}</h5>
                          <p>{{ skillDisplay.examplePrompt }}</p>
                        </article>
                      </div>

                      <div v-if="skillDisplay.useCases.length" class="skill-info-block">
                        <h5>{{ pick('适用场景', 'Good for') }}</h5>
                        <ul>
                          <li v-for="item in skillDisplay.useCases" :key="item">{{ item }}</li>
                        </ul>
                      </div>

                      <div v-if="skillDisplay.outputFormats.length" class="skill-info-block">
                        <h5>{{ pick('预期输出', 'What you get') }}</h5>
                        <div class="skill-tag-list">
                          <span v-for="item in skillDisplay.outputFormats" :key="item" class="skill-tag">{{ item }}</span>
                        </div>
                      </div>

                      <div v-if="skillDisplay.tips.length" class="skill-info-block skill-info-block--warn">
                        <h5>{{ pick('使用提示', 'Tips') }}</h5>
                        <ul>
                          <li v-for="item in skillDisplay.tips" :key="item">{{ item }}</li>
                        </ul>
                      </div>

                      <div v-if="skillDisplay.tags.length" class="skill-tag-list">
                        <span v-for="tag in skillDisplay.tags" :key="tag" class="skill-tag skill-tag--accent">{{ tag }}</span>
                      </div>

                      <div class="mt-5">
                        <label class="mb-2 block text-sm font-medium text-slate-700">{{ pick('执行输入', 'Your input') }}</label>
                        <textarea v-model="executionPrompt" class="skill-textarea" :placeholder="executionPlaceholder" />
                      </div>

                      <div class="skill-detail-actions">
                        <button
                          type="button"
                          class="skill-run-btn"
                          :disabled="executing || !selectedSkill.installed || !executionPrompt.trim()"
                          @click="executeSkill"
                        >
                          {{ executing ? pick('执行中…', 'Running…') : pick('执行技能', 'Run skill') }}
                        </button>
                      </div>

                      <div v-if="executionResult" class="skill-result-panel">
                        <h5>{{ pick('执行结果', 'Result') }}</h5>
                        <p class="skill-result-panel__summary">{{ executionResult.result.summary }}</p>
                        <pre>{{ executionResult.result.suggestion }}</pre>
                      </div>
                    </template>

                    <div v-else class="skill-empty skill-empty--detail">{{ pick('从左侧选择一个技能。', 'Pick a skill on the left.') }}</div>
                  </section>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { WritingSkillsAPI, type WritingSkillExecutionResult, type WritingSkillItem } from '@/api/novel'
import { globalAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'

const { pick, t } = useLocale()

type SkillItem = WritingSkillItem

type ExecutionResult = WritingSkillExecutionResult & {
  result: {
    summary: string
    suggestion: string
  }
}

const asRecord = (value: unknown): Record<string, unknown> | null => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
)

const asText = (value: unknown): string => typeof value === 'string' ? value : ''

/** 统一错误文案，避免各处重复拼接 */
const errorText = (error: unknown): string => (
  error instanceof Error ? error.message : pick('未知错误', 'Unknown error')
)

const normalizeExecutionResult = (response: WritingSkillExecutionResult): ExecutionResult => {
  const responseData = asRecord(response)
  const result = asRecord(responseData?.result)
  const message = asText(responseData?.message)
  const summary = asText(result?.summary) || message || pick('技能已执行', 'Skill executed')

  return {
    ...response,
    result: {
      summary,
      suggestion: asText(result?.suggestion) || asText(responseData?.data),
    },
  }
}

type SkillTextEntry = Partial<{
  name: string
  description: string
  overview: string
  category: string
  inputGuide: string
  examplePrompt: string
}>

// 技能展示文案必须放在 computed 内按语言重算，否则切到英文后仍显示中文
const skillTextMap = computed<Record<string, SkillTextEntry>>(() => ({
  'scene-conflict-booster': {
    name: pick('场景冲突强化', 'Scene conflict booster'),
    description: pick(
      '聚焦当前场景的阻力、选择与代价，给出能直接落到正文改写里的强化建议。',
      'Focuses on resistance, choice and cost in the current scene, and returns notes you can apply straight to the draft.',
    ),
    overview: pick(
      '适合处理“冲突存在但不够抓人”的章节，重点加强目标、阻碍、博弈和压迫感。',
      'Best for chapters where conflict exists but does not grip: it strengthens goals, obstacles, maneuvering and pressure.',
    ),
    category: pick('情节', 'Plot'),
  },
  'character-voice-polisher': {
    name: pick('角色声音校准', 'Character voice calibration'),
    description: pick(
      '检查角色对白是否贴合身份、关系和情绪状态，避免所有人说话像同一个人。',
      'Checks whether dialogue matches each character’s role, relationships and emotional state, so nobody sounds interchangeable.',
    ),
    overview: pick(
      '适合处理人物辨识度不足、对白语气趋同的问题。',
      'Use it when characters blur together and their dialogue starts to sound the same.',
    ),
    category: pick('角色', 'Characters'),
  },
  'clue-layout-checker': {
    name: pick('线索布局检查', 'Clue layout check'),
    description: pick(
      '检查伏笔、误导和回收点是否足够清晰，尤其适合推理、悬疑章节。',
      'Checks whether foreshadowing, misdirection and payoffs read clearly — especially in mystery and suspense chapters.',
    ),
    overview: pick(
      '用于判断线索埋设是否过浅、过深或回收不稳。',
      'Tells you whether clues are too obvious, too buried, or paid off unevenly.',
    ),
    category: pick('推理', 'Mystery'),
  },
  'pacing-rhythm-tuner': {
    name: pick('章节节奏调校', 'Chapter pacing tuner'),
    description: pick(
      '检查章节的推进速度、信息密度和情绪起伏，找出拖沓或过快的段落。',
      'Checks momentum, information density and emotional swings to find passages that drag or rush.',
    ),
    overview: pick(
      '适合整章体检节奏，用来决定哪里该删、哪里该补。',
      'A whole-chapter pacing check-up: it tells you what to cut and what to expand.',
    ),
    category: pick('节奏', 'Pacing'),
  },
  'show-dont-tell-rewriter': {
    name: pick('展示感改写器', 'Show-don’t-tell rewriter'),
    description: pick(
      '把解释式叙述改成可被读者看见、听见、感受到的场景表达。',
      'Turns explanatory narration into scenes the reader can see, hear and feel.',
    ),
    overview: pick(
      '适合处理“作者在解释，而不是角色在经历”的段落。',
      'For passages where the author is explaining instead of letting characters live it.',
    ),
    category: pick('叙述', 'Narration'),
  },
  'dialogue-subtext-enhancer': {
    name: pick('对白潜台词增强', 'Dialogue subtext enhancer'),
    description: pick(
      '强化对白中的试探、遮掩、压迫和关系张力，让“话里有话”。',
      'Sharpens probing, evasion, pressure and relational tension so lines carry a second meaning.',
    ),
    overview: pick(
      '适合审讯、谈判、摊牌、对峙等需要暗流的对话场景。',
      'Built for interrogations, negotiations, confrontations and any scene that needs an undercurrent.',
    ),
    category: pick('对白', 'Dialogue'),
  },
  'chapter-hook-designer': {
    name: pick('章首抓钩设计', 'Chapter opening hook'),
    description: pick(
      '检查开场是否够抓人，并给出更强的切入方式。',
      'Checks whether the opening grabs the reader and proposes stronger ways in.',
    ),
    overview: pick(
      '适合新章节开头、转场后首段和连载更新开篇。',
      'For chapter openings, the first paragraph after a transition, and serialised updates.',
    ),
    category: pick('结构', 'Structure'),
  },
  'chapter-ending-cliffhanger': {
    name: pick('章末悬念强化', 'Chapter-ending cliffhanger'),
    description: pick(
      '检查章节结尾的悬念、余波和续读牵引力。',
      'Checks the suspense, aftershock and pull-through at the end of a chapter.',
    ),
    overview: pick(
      '适合连载或章节化长篇，用来加强“点下一章”的冲动。',
      'For serialised or chaptered novels, to strengthen the urge to open the next chapter.',
    ),
    category: pick('结构', 'Structure'),
  },
  'motivation-consistency-checker': {
    name: pick('动机一致性检查', 'Motivation consistency check'),
    description: pick(
      '检查人物行为和选择是否符合既有目标、立场和心理轨迹。',
      'Checks whether behaviour and choices line up with established goals, stances and inner trajectory.',
    ),
    overview: pick(
      '适合处理“为了剧情需要硬拐弯”的违和感。',
      'For moments where a character turns on a dime just because the plot needs it.',
    ),
    category: pick('角色', 'Characters'),
  },
  'emotion-arc-calibrator': {
    name: pick('情绪曲线校准', 'Emotional arc calibration'),
    description: pick(
      '检查章节内情绪推进是否顺滑，避免情绪爆点失衡或断裂。',
      'Checks whether emotion builds smoothly, so peaks neither overshoot nor break.',
    ),
    overview: pick(
      '适合处理关系戏、高压戏和情绪层递进不足的问题。',
      'For relationship scenes, high-pressure scenes and emotion that fails to escalate.',
    ),
    category: pick('情绪', 'Emotion'),
  },
  'prose-clarity-polisher': {
    name: pick('语言清晰度润色', 'Prose clarity polish'),
    description: pick(
      '找出拗口、重复、信息拥堵的句段，提高清晰度而不抹掉风格。',
      'Finds clumsy, repetitive or overloaded sentences and clarifies them without flattening your voice.',
    ),
    overview: pick(
      '适合定稿前最后一轮清句和减负。',
      'A final pass before you lock the draft: trim and clarify.',
    ),
    category: pick('文风', 'Style'),
  },
}))

const props = defineProps<{
  show: boolean
  projectId: string
  chapterNumber?: number | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const loading = ref(false)
const installing = ref(false)
const executing = ref(false)
const catalog = ref<SkillItem[]>([])
const selectedSkill = ref<SkillItem | null>(null)
const executionPrompt = ref('')
const executionResult = ref<ExecutionResult | null>(null)

const operationVisible = computed(() => loading.value || installing.value || executing.value)
const operationTitle = computed(() => loading.value
  ? pick('正在加载技能目录', 'Loading the skill catalogue')
  : installing.value
    ? pick('正在处理技能安装状态', 'Updating installation state')
    : pick('正在执行写作技能', 'Running the writing skill'))
const operationStep = computed(() => loading.value
  ? pick('同步目录', 'Syncing catalogue')
  : installing.value
    ? pick('安装 / 卸载中', 'Installing / removing')
    : pick('分析当前输入', 'Analysing your input'))
const operationHint = computed(() => (
  loading.value
    ? pick('正在同步可用技能列表和安装状态。', 'Syncing the list of available skills and their installation state.')
    : installing.value
      ? pick(
          '只会更新技能可用状态，不会修改系统配置，也不会改正文内容。',
          'Only the skill’s availability changes — no system settings and no draft content are touched.',
        )
      : pick(
          '正在把当前项目、当前章节和你的输入要求一起送入技能处理。',
          'Sending this project, this chapter and your instructions into the skill.',
        )
))

const skillDisplay = computed(() => {
  const skill = selectedSkill.value
  if (!skill) {
    return {
      name: '',
      description: '',
      overview: '',
      category: '',
      inputGuide: '',
      examplePrompt: '',
      useCases: [] as string[],
      outputFormats: [] as string[],
      tips: [] as string[],
      tags: [] as string[],
    }
  }
  const mapped = skillTextMap.value[skill.id] || {}
  return {
    name: mapped.name || skill.name,
    description: mapped.description || skill.description || '',
    overview: mapped.overview || skill.overview || '',
    category: mapped.category || skill.category || '',
    inputGuide: mapped.inputGuide || skill.input_guide || '',
    examplePrompt: mapped.examplePrompt || skill.example_prompt || '',
    useCases: skill.use_cases || [],
    outputFormats: skill.output_format || [],
    tips: skill.tips || [],
    tags: skill.tags || [],
  }
})

/** 目录卡片文案：优先用本地映射，缺失时回落后端返回值 */
const catalogName = (skill: SkillItem) => skillTextMap.value[skill.id]?.name || skill.name
const catalogCategory = (skill: SkillItem) => skillTextMap.value[skill.id]?.category || skill.category
const catalogDescription = (skill: SkillItem) => skillTextMap.value[skill.id]?.description || skill.description

const executionPlaceholder = computed(() => {
  if (!selectedSkill.value) {
    return pick(
      '例如：检查这一章的冲突是否够强，并给出 3 条可以直接改写的建议。',
      'For example: check whether the conflict in this chapter is strong enough and give me 3 concrete rewrites.',
    )
  }
  return skillDisplay.value.inputGuide
    || skillDisplay.value.examplePrompt
    || pick('请输入你希望技能处理的问题。', 'Describe what you want this skill to work on.')
})

const loadData = async () => {
  loading.value = true
  try {
    catalog.value = await WritingSkillsAPI.getSkillCatalog()
    if (!selectedSkill.value && catalog.value.length) {
      selectedSkill.value = catalog.value[0]
    } else if (selectedSkill.value) {
      selectedSkill.value = catalog.value.find(item => item.id === selectedSkill.value?.id) || catalog.value[0] || null
    }
  } catch (error) {
    globalAlert.showError(
      pick(`加载技能目录失败：${errorText(error)}`, `Could not load the skill catalogue: ${errorText(error)}`),
      t('common.error'),
    )
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (visible) => {
  if (!visible) return
  executionResult.value = null
  if (!catalog.value.length) void loadData()
}, { immediate: true })

const installSkill = async (skill: SkillItem) => {
  installing.value = true
  const mapped = skillTextMap.value[skill.id]
  try {
    await WritingSkillsAPI.installSkill(skill.id, {
      name: mapped?.name || skill.name,
      description: mapped?.description || skill.description,
      category: mapped?.category || skill.category,
      version: skill.version,
      author: skill.author,
      source_url: skill.source_url,
    })
    globalAlert.showSuccess(
      pick(`已安装技能：${mapped?.name || skill.name}`, `Skill installed: ${mapped?.name || skill.name}`),
      pick('安装成功', 'Installed'),
    )
    await loadData()
  } catch (error) {
    globalAlert.showError(
      pick(`安装技能失败：${errorText(error)}`, `Could not install the skill: ${errorText(error)}`),
      t('common.error'),
    )
  } finally {
    installing.value = false
  }
}

const uninstallSkill = async (skillId: number) => {
  installing.value = true
  try {
    await WritingSkillsAPI.uninstallSkill(skillId)
    globalAlert.showSuccess(pick('技能已卸载', 'Skill removed'), pick('操作成功', 'Done'))
    await loadData()
  } catch (error) {
    globalAlert.showError(
      pick(`卸载技能失败：${errorText(error)}`, `Could not remove the skill: ${errorText(error)}`),
      t('common.error'),
    )
  } finally {
    installing.value = false
  }
}

const executeSkill = async () => {
  if (!selectedSkill.value || !executionPrompt.value.trim()) return
  executing.value = true
  try {
    const response = await WritingSkillsAPI.executeSkill(selectedSkill.value.id, {
      prompt: executionPrompt.value.trim(),
      project_id: props.projectId || undefined,
      chapter_number: props.chapterNumber || undefined,
    })
    executionResult.value = normalizeExecutionResult(response)
    globalAlert.showSuccess(
      pick(`已执行技能：${skillDisplay.value.name}`, `Skill finished: ${skillDisplay.value.name}`),
      pick('执行成功', 'Completed'),
    )
  } catch (error) {
    globalAlert.showError(
      pick(`执行技能失败：${errorText(error)}`, `Could not run the skill: ${errorText(error)}`),
      t('common.error'),
    )
  } finally {
    executing.value = false
  }
}

const handleClose = () => emit('close')
</script>

<style scoped>
.skill-dialog-shell {
  width: min(1440px, 100%);
  overflow: hidden;
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #fff;
  box-shadow: 0 30px 80px rgba(15, 23, 42, 0.28);
}

.skill-dialog-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.skill-dialog-header h3 {
  margin: 0;
  color: #0f172a;
  font-size: 1.18rem;
  font-weight: 700;
}

.skill-dialog-header p {
  margin: 6px 0 0;
  color: #475569;
  font-size: 0.9rem;
  line-height: 1.6;
}

.skill-dialog-body {
  display: grid;
  gap: 14px;
  padding: 18px 22px 22px;
}

.skill-guide-panel,
.skill-main-grid,
.skill-section-head,
.skill-catalog-card__head,
.skill-detail-panel__head,
.skill-tag-list,
.skill-detail-actions,
.progress-row {
  display: flex;
  gap: 10px;
}

.skill-guide-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.skill-guide-panel article,
.skill-progress-card,
.skill-detail-panel,
.skill-catalog-card,
.skill-info-block,
.skill-result-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: #f8fafc;
}

.skill-guide-panel article,
.skill-progress-card,
.skill-detail-panel,
.skill-info-block,
.skill-result-panel {
  padding: 14px 16px;
}

.skill-guide-panel h4,
.skill-detail-panel h4 {
  margin: 0 0 8px;
  color: #0f172a;
  font-size: 1rem;
}

.skill-guide-panel ul,
.skill-info-block ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
  color: #475569;
}

.skill-progress-card p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 0.86rem;
}

.skill-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(440px, 0.9fr);
  gap: 16px;
}

.skill-section-head,
.skill-catalog-card__head,
.skill-detail-panel__head,
.progress-row {
  justify-content: space-between;
  align-items: center;
}

.skill-section-head h4 {
  margin: 0;
  color: #0f172a;
}

.skill-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.skill-catalog-card {
  padding: 14px 16px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: 0.18s ease;
}

.skill-catalog-card--active {
  background: #eef2ff;
  border-color: rgba(79, 70, 229, 0.3);
}

.skill-catalog-card__title {
  margin: 0;
  color: #0f172a;
  font-weight: 700;
}

.skill-catalog-card__meta,
.skill-catalog-card__desc,
.skill-detail-panel__summary,
.skill-detail-panel__head p,
.skill-detail-sections p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 0.88rem;
  line-height: 1.55;
}

.skill-status-badge,
.skill-tag {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #475569;
  font-size: 0.76rem;
  font-weight: 700;
}

.skill-status-badge--installed {
  background: #dcfce7;
  color: #047857;
}

.skill-detail-panel {
  background: #fff;
}

.skill-install-btn,
.skill-run-btn {
  border: 0;
  border-radius: 12px;
  padding: 10px 14px;
  font-weight: 700;
  cursor: pointer;
}

.skill-install-btn--primary,
.skill-run-btn {
  background: #111827;
  color: #fff;
}

.skill-install-btn--danger {
  background: #fee2e2;
  color: #b91c1c;
}

.skill-detail-sections {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.skill-detail-sections article {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  background: #f8fafc;
}

.skill-detail-sections h5,
.skill-info-block h5,
.skill-result-panel h5 {
  margin: 0 0 8px;
  color: #0f172a;
  font-size: 0.92rem;
}

.skill-info-block {
  margin-top: 14px;
}

.skill-info-block--warn {
  background: rgba(239, 246, 255, 0.95);
}

.skill-tag-list {
  flex-wrap: wrap;
}

.skill-tag--accent {
  background: #eef2ff;
  color: #4338ca;
}

.skill-textarea {
  width: 100%;
  min-height: 150px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 16px;
  background: #fff;
  outline: none;
  resize: vertical;
}

.skill-detail-actions {
  justify-content: flex-end;
  margin-top: 12px;
}

.skill-result-panel {
  margin-top: 14px;
}

.skill-result-panel__summary {
  margin: 0 0 8px;
  color: #475569;
}

.skill-result-panel pre {
  margin: 0;
  white-space: pre-wrap;
  color: #0f172a;
  line-height: 1.6;
}

.skill-empty {
  padding: 34px 18px;
  border: 1px dashed rgba(148, 163, 184, 0.3);
  border-radius: 18px;
  text-align: center;
  color: #94a3b8;
}

.skill-empty--detail {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 360px;
}

.progress-track {
  position: relative;
  width: 100%;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.progress-bar--indeterminate {
  width: 40%;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #7c3aed, #a855f7);
  animation: skill-loading 1.2s ease-in-out infinite;
}

@keyframes skill-loading {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(280%); }
}

@media (max-width: 1180px) {
  .skill-main-grid,
  .skill-guide-panel,
  .skill-card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
