<template>
  <div class="style-center-page">
    <section class="style-center-hero">
      <div>
        <p class="style-center-hero__eyebrow">{{ '\u72ec\u7acb\u6587\u98ce\u4e2d\u5fc3 \u00b7 \u5916\u90e8\u4f5c\u54c1\u5b66\u4e60\u53f0' }}</p>
        <h1>{{ '\u5916\u90e8\u53c2\u8003\u6587\u98ce\u5e93' }}</h1>
        <p class="style-center-hero__desc">{{ '\u4e0d\u518d\u8981\u6c42\u624b\u52a8\u7c98\u8d34\u6574\u672c\u5c0f\u8bf4\u3002\u8fd9\u91cc\u6539\u6210\u5bfc\u5165\u5916\u90e8\u4f5c\u54c1\u3001\u5206\u6279\u5b66\u4e60\u3001\u6301\u7eed\u63d0\u70bc\u3001\u518d\u8f93\u51fa\u53ef\u4fee\u6539\u53ef\u8865\u5145\u7684\u6587\u98ce\u753b\u50cf\u3002' }}</p>
      </div>
      <div class="style-center-hero__actions">
        <label class="style-center-hero__select">
          <span>{{ '\u5f53\u524d\u9879\u76ee' }}</span>
          <select v-model="selectedProjectId" @change="loadLibrary">
            <option value="">{{ '\u8bf7\u9009\u62e9\u9879\u76ee' }}</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.title }}</option>
          </select>
        </label>
      </div>
    </section>

    <section v-if="styleProgressVisible" class="style-progress-panel">
      <div class="style-progress-panel__head">
        <strong>{{ styleProgressTitle }}</strong>
        <span>{{ styleProgressPercent }}%</span>
      </div>
      <p class="style-progress-panel__desc">{{ styleProgressDescription }}</p>
      <div class="style-progress-panel__track" aria-label="style-progress">
        <div class="style-progress-panel__bar" :style="{ width: `${styleProgressPercent}%` }"></div>
      </div>
    </section>

    <section class="style-center-summary-grid">
      <article class="style-summary-card style-summary-card--accent">
        <span class="style-summary-card__label">当前项目</span>
        <strong class="style-summary-card__value">{{ currentProjectTitle }}</strong>
        <p class="style-summary-card__meta">先选项目，再决定把风格画像应用到项目级还是全局级。</p>
      </article>
      <article class="style-summary-card">
        <span class="style-summary-card__label">全局生效</span>
        <strong class="style-summary-card__value">{{ globalActiveProfile?.name || '未启用' }}</strong>
        <p class="style-summary-card__meta">适合统一所有项目的默认文风方向。</p>
      </article>
      <article class="style-summary-card">
        <span class="style-summary-card__label">项目生效</span>
        <strong class="style-summary-card__value">{{ projectActiveProfile?.name || '未启用' }}</strong>
        <p class="style-summary-card__meta">只覆盖当前项目，不影响其他小说。</p>
      </article>
    </section>

    <section v-if="selectedProjectId" class="style-center-stack">
      <article class="style-card style-card--pipeline">
        <div class="style-card__header style-card__header--split">
          <div>
            <h2>文风学习流程重构</h2>
            <p>改成导入 → 拆批 → 提炼 → 累积画像 → 应用的工作流，专门对应长篇、超长篇参考作品。</p>
          </div>
          <span class="workflow-badge">增量式学习</span>
        </div>

        <div class="pipeline-grid">
          <div class="pipeline-step">
            <span class="pipeline-step__index">01</span>
            <strong>导入外部作品</strong>
            <p>支持 txt、docx、epub、复制片段、整理稿等任意可转文本来源。先导入文件或分卷，再建立素材记录。</p>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step__index">02</span>
            <strong>按批次学习</strong>
            <p>把超长文本拆成多批学习记录，每次只处理一部分，避免一次性塞入几十万到几百万字。</p>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step__index">03</span>
            <strong>累计风格画像</strong>
            <p>每次学习都补充节奏、句式、叙述距离、描写倾向等维度，允许你后续再修改、再追加。</p>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step__index">04</span>
            <strong>排除具体元素</strong>
            <p>明确只提炼写法，不吸收角色名、势力名、地名、剧情结构、设定专名，避免照搬内容。</p>
          </div>
        </div>
      </article>

      <section class="style-center-grid style-center-grid--top">
        <article class="style-card style-card--importer">
          <div class="style-card__header">
            <div>
              <h2>1. 建立外部作品素材</h2>
              <p>先登记一部参考作品，再决定通过文件导入、手动补充还是分批录入。</p>
            </div>
          </div>

          <div class="import-mode-grid">
            <button :class="['mode-chip', { 'mode-chip--active': importMode === 'file_stub' }]" @click="importMode = 'file_stub'">
              文件导入
            </button>
            <button :class="['mode-chip', { 'mode-chip--active': importMode === 'chunk_manual' }]" @click="importMode = 'chunk_manual'">
              分批录入
            </button>
            <button :class="['mode-chip', { 'mode-chip--active': importMode === 'hybrid' }]" @click="importMode = 'hybrid'">
              混合模式
            </button>
          </div>

          <div class="form-grid">
            <label class="field-block">
              <span>作品名称</span>
              <input v-model.trim="draftTitle" type="text" class="form-input" placeholder="例如：某部参考长篇" />
            </label>
            <label class="field-block">
              <span>来源格式</span>
              <input v-model.trim="draftFormat" type="text" class="form-input" placeholder="txt / docx / epub / 网页整理稿 / 片段合集" />
            </label>
            <label class="field-block field-block--full">
              <span>导入说明</span>
              <textarea
                v-model="draftContent"
                class="form-textarea form-textarea--medium"
                :placeholder="sourcePlaceholder"
              ></textarea>
            </label>
          </div>

          <div class="import-dropzone">
            <div>
              <strong>文件导入入口</strong>
              <p>当前已支持 txt / md / json / csv / log / docx / epub；纯文本会在前端预览片段，docx/epub 交给服务端抽取正文后进入学习批次。</p>
            </div>
            <div class="import-dropzone__actions">
              <input ref="fileInputRef" class="import-dropzone__input" type="file" accept=".txt,.md,.markdown,.json,.csv,.log,.text,.docx,.epub" @change="handleFilePicked" />
              <button class="secondary-btn" type="button" @click="triggerFilePick">选择文件</button>
            </div>
          </div>
          <p v-if="selectedFileName" class="selected-file-copy">已载入文件：{{ selectedFileName }} <span v-if="selectedFileChars">· {{ selectedFileChars }} 字</span></p>

          <div class="style-card__footer">
            <span class="style-hint">当前实现先兼容现有接口：把“导入说明 / 当前批次摘要”保存为素材记录，UI 已明确转成大文本分批学习语义。</span>
            <button class="primary-btn" :disabled="savingSource || !canCreateSource" @click="createSource">保存素材记录</button>
          </div>
        </article>

        <article class="style-card style-card--batch">
          <div class="style-card__header style-card__header--split">
            <div>
              <h2>2. 学习批次策略</h2>
              <p>为长篇/超长篇建立拆批规则，后续每一批都可以单独学习并继续补充画像。</p>
            </div>
            <span class="panel-tip">{{ activeProfileId ? '补充到现有画像' : '新建画像批次' }}</span>
          </div>

          <div class="batch-plan-grid">
            <label class="field-block">
              <span>当前批次名称</span>
              <input v-model.trim="batchLabel" type="text" class="form-input" placeholder="例如：第一卷前 12 章 / 中段对白批次" />
            </label>
            <label class="field-block">
              <span>建议批量</span>
              <select v-model="batchSize" class="form-input">
                <option value="8k-15k">8k - 15k 字 / 批</option>
                <option value="15k-30k">15k - 30k 字 / 批</option>
                <option value="30k+">30k+ 字 / 批</option>
              </select>
            </label>
            <label class="field-block field-block--full">
              <span>拆批说明</span>
              <textarea
                v-model="batchStrategy"
                class="form-textarea form-textarea--small"
                placeholder="例如：先拆开世界观铺垫段、核心对白段、战斗段、抒情段，逐批建立风格特征。"
              ></textarea>
            </label>
          </div>

          <div class="batch-notes">
            <div class="batch-note">
              <strong>适合超长文本</strong>
              <p>一次只分析一个批次，不要求把全书一次塞进去。</p>
            </div>
            <div class="batch-note">
              <strong>适合持续补录</strong>
              <p>今天录一卷，后面继续补另一卷，画像会逐步完善。</p>
            </div>
          </div>
        </article>
      </section>

      <section class="style-center-grid style-center-grid--bottom">
        <article class="style-card style-card--sources">
          <div class="style-card__header style-card__header--split">
            <div>
              <h2>3. 素材库 / 学习来源</h2>
              <p>这些是你已经建立的外部作品或学习批次。选择多个来源后，可以继续生成或补全文风画像。</p>
            </div>
            <span class="panel-tip">可多选合并</span>
          </div>

          <div v-if="sources.length" class="list-stack">
            <label v-for="source in sources" :key="source.id" class="list-item list-item--selectable list-item--source">
              <div class="list-item__main list-item__main--top">
                <input v-model="selectedSourceIds" :value="source.id" type="checkbox" />
                <div>
                  <div class="source-row__title">
                    <h3>{{ source.title }}</h3>
                    <span class="tag tag--source">{{ source.source_type === 'external_novel' ? '长篇来源' : '学习批次' }}</span>
                  </div>
                  <p>{{ source.char_count || 0 }} 字 · {{ source.extra?.format || draftFormat || '未标注格式' }}</p>
                  <p class="source-row__note">{{ source.extra?.note || '当前版本接口未拆出文件元数据，先保留为素材描述。' }}</p>
                </div>
              </div>
              <button class="text-btn text-btn--danger" @click="deleteSource(source.id)">删除</button>
            </label>
          </div>
          <p v-else class="empty-copy">还没有素材，先建立一部参考作品或一个学习批次。</p>

          <div class="style-card__footer">
            <select v-model="activeProfileId" class="form-input">
              <option value="">新建画像</option>
              <option v-for="profile in profiles" :key="profile.id" :value="profile.id">补充到：{{ profile.name }}</option>
            </select>
            <input v-model.trim="profileName" type="text" class="form-input" :placeholder="activeProfileId ? '可选：为补全后的画像改名' : '画像名称（例如：冷峻叙事+高密度对白）'" />
            <button class="primary-btn" :disabled="creatingProfile || selectedSourceIds.length === 0" @click="createProfile">生成 / 补全文风画像</button>
          </div>
        </article>

        <article class="style-card style-card--history">
          <div class="style-card__header style-card__header--split">
            <div>
              <h2>4. 学习批次历史</h2>
              <p>把文件来源、批次标签、格式、字符数和导入模式展开成真正的批次视图，方便追踪每轮学习来源。</p>
            </div>
            <span class="panel-tip">{{ sourceStats.total }} 个批次</span>
          </div>

          <div class="history-toolbar">
            <label class="field-block">
              <span>关键词</span>
              <input v-model.trim="historyKeyword" type="text" class="form-input" placeholder="筛选批次名、文件名、格式" />
            </label>
            <label class="field-block">
              <span>模式</span>
              <select v-model="historyModeFilter" class="form-input">
                <option value="all">全部模式</option>
                <option value="file_stub">文件导入</option>
                <option value="chunk_manual">分批录入</option>
                <option value="hybrid">混合模式</option>
              </select>
            </label>
            <label class="field-block">
              <span>来源类型</span>
              <select v-model="historyTypeFilter" class="form-input">
                <option value="all">全部类型</option>
                <option value="external_novel">长篇来源</option>
                <option value="external_text">学习批次</option>
              </select>
            </label>
            <label class="field-block">
              <span>排序</span>
              <select v-model="historySort" class="form-input">
                <option value="latest">最新导入优先</option>
                <option value="chars_desc">字数从高到低</option>
                <option value="chars_asc">字数从低到高</option>
                <option value="name_asc">名称 A-Z</option>
              </select>
            </label>
          </div>

          <div v-if="groupedFilteredSources.length" class="history-group-stack">
            <section v-for="group in groupedFilteredSources" :key="group.key" class="history-source-group">
              <button class="history-source-group__header" type="button" @click="toggleHistoryGroup(group.key)">
                <div>
                  <strong>{{ group.label }}</strong>
                  <small>{{ group.fileName }}</small>
                </div>
                <div class="history-source-group__meta">
                  <span>{{ group.count }} 条</span>
                  <span>{{ group.totalChars }} 字</span>
                  <span>{{ isHistoryGroupExpanded(group.key) ? '收起' : '展开' }}</span>
                </div>
              </button>

              <div v-if="isHistoryGroupExpanded(group.key)" class="batch-history-table">
                <div class="batch-history-table__head">
                  <span>批次 / 来源</span>
                  <span>模式</span>
                  <span>格式</span>
                  <span>体量</span>
                  <span>轮次线索</span>
                </div>
                <article v-for="source in group.items" :key="`${source.id}-history`" class="batch-history-row">
                  <div class="batch-history-row__main">
                    <strong>{{ source.extra?.batch_label || source.title }}</strong>
                    <small>{{ source.extra?.file_name || source.title }}</small>
                  </div>
                  <span>{{ source.extra?.import_mode_label || importModeText(source.extra?.import_mode) }}</span>
                  <span>{{ source.extra?.format || '未标注' }}</span>
                  <span>{{ source.char_count || source.extra?.file_chars || 0 }} 字</span>
                  <span>{{ source.extra?.batch_size || '待补充' }}</span>
                </article>
              </div>
            </section>
          </div>
          <p v-else class="empty-copy">当前筛选条件下没有批次，先放宽筛选或继续导入素材。</p>

          <div class="source-stats-grid">
            <div class="source-stat-card">
              <span>长篇来源</span>
              <strong>{{ sourceStats.novel }}</strong>
              <small>{{ sourceTypeStats.novelChars }} 字</small>
            </div>
            <div class="source-stat-card">
              <span>学习批次</span>
              <strong>{{ sourceStats.batch }}</strong>
              <small>{{ sourceTypeStats.batchChars }} 字</small>
            </div>
            <div class="source-stat-card">
              <span>总字数</span>
              <strong>{{ sourceStats.chars }}</strong>
              <small>{{ filteredSources.length }} 条可见记录</small>
            </div>
          </div>

          <div class="history-group-grid">
            <article class="history-group-card">
              <span>文件导入</span>
              <strong>{{ sourceModeStats.file_stub.count }}</strong>
              <small>{{ sourceModeStats.file_stub.chars }} 字</small>
            </article>
            <article class="history-group-card">
              <span>分批录入</span>
              <strong>{{ sourceModeStats.chunk_manual.count }}</strong>
              <small>{{ sourceModeStats.chunk_manual.chars }} 字</small>
            </article>
            <article class="history-group-card">
              <span>混合模式</span>
              <strong>{{ sourceModeStats.hybrid.count }}</strong>
              <small>{{ sourceModeStats.hybrid.chars }} 字</small>
            </article>
          </div>

          <div class="timeline-card">
            <div class="timeline-card__head">
              <strong>学习轮次时间线</strong>
              <span>{{ filteredSources.length }} 条轨迹</span>
            </div>
            <div v-if="timelineEntries.length" class="timeline-list">
              <article v-for="entry in timelineEntries" :key="entry.id" class="timeline-item">
                <div class="timeline-item__dot"></div>
                <div class="timeline-item__content">
                  <div class="timeline-item__title-row">
                    <strong>{{ entry.title }}</strong>
                    <span>{{ entry.mode }}</span>
                  </div>
                  <p>{{ entry.source }} · {{ entry.format }} · {{ entry.chars }} 字</p>
                  <small>{{ entry.batch }}</small>
                </div>
              </article>
            </div>
            <p v-else class="empty-copy">还没有可展示的学习轨迹。</p>
          </div>
        </article>

        <article class="style-card style-card--profiles">
          <div class="style-card__header">
            <div>
              <h2>4. 文风画像与应用</h2>
              <p>画像保留为可持续编辑的风格摘要。应用时只传递写法倾向，不应复制角色名、地名、组织名和剧情结构。</p>
            </div>
          </div>

          <div class="guardrail-box">
            <strong>提炼边界</strong>
            <ul>
              <li>保留：叙述视角、句长分布、节奏切换、对白密度、描写偏好、措辞倾向。</li>
              <li>排除：角色姓名、关系网、专有设定、门派/组织、地名、世界观专词、剧情桥段。</li>
            </ul>
          </div>

          <div class="status-banner" v-if="globalActiveProfile || projectActiveProfile">
            <div v-if="globalActiveProfile">
              <strong>全局应用：</strong>{{ globalActiveProfile.name }}
            </div>
            <div v-if="projectActiveProfile">
              <strong>项目应用：</strong>{{ projectActiveProfile.name }}
            </div>
          </div>

          <div v-if="profiles.length" class="list-stack">
            <article v-for="profile in profiles" :key="profile.id" class="list-item list-item--profile">
              <div>
                <div class="profile-title-row">
                  <h3>{{ profile.name }}</h3>
                  <span v-if="projectActiveProfile?.id === profile.id" class="tag tag--project">当前项目</span>
                  <span v-else-if="globalActiveProfile?.id === profile.id" class="tag tag--global">全局</span>
                  <span class="tag tag--source">累计 {{ profile.quality_metrics?.merge_rounds || 1 }} 轮</span>
                </div>
                <p class="profile-meta">来源：{{ (profile.extra?.source_titles || []).join(' / ') || '未命名来源' }}</p>
                <ul class="summary-list">
                  <li v-for="(value, key) in profile.summary || {}" :key="key"><span>{{ summaryLabels[key] || key }}</span><strong>{{ value }}</strong></li>
                </ul>

                <div class="profile-editor-grid">
                  <label v-for="field in profileSummaryFields" :key="`${profile.id}-${field.key}`" class="field-block">
                    <span>{{ field.label }}</span>
                    <textarea
                      v-model="profileSummaryDrafts[profile.id][field.key]"
                      class="form-textarea form-textarea--micro"
                      :placeholder="field.placeholder"
                    ></textarea>
                  </label>
                </div>

                <label class="field-block profile-name-editor">
                  <span>画像名称</span>
                  <input
                    v-model.trim="profileNameDrafts[profile.id]"
                    type="text"
                    class="form-input"
                    placeholder="可直接调整画像标题"
                  />
                </label>

                <textarea
                  v-model="profileDrafts[profile.id]"
                  class="form-textarea form-textarea--small profile-edit-box"
                  placeholder="补充说明：例如保留冷峻旁白、降低比喻密度、对白更克制。"
                ></textarea>
              </div>
              <div class="profile-actions">
                <button class="secondary-btn" @click="saveProfileEdits(profile)">保存画像字段</button>
                <button class="secondary-btn" @click="applyProfile(profile.id, 'global')">设为全局</button>
                <button class="primary-btn" @click="applyProfile(profile.id, 'project')">应用到当前项目</button>
              </div>
            </article>
          </div>
          <p v-else class="empty-copy">还没有画像，先从左侧素材中选择一批或多批来源。</p>

          <div class="style-card__footer style-card__footer--split">
            <button class="secondary-btn" :disabled="!globalActiveProfile" @click="clearApplication('global')">清理全局应用</button>
            <button class="secondary-btn" :disabled="!projectActiveProfile" @click="clearApplication('project')">清理当前项目应用</button>
          </div>
        </article>
      </section>
    </section>

    <section v-else class="style-card">
      <p class="empty-copy">当前还没有项目。请先创建小说项目，再进入独立文风中心。</p>
    </section>

    <p v-if="error" class="error-copy">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NovelAPI, OptimizerAPI, type NovelProjectSummary } from '@/api/novel'

const fileInputRef = ref<HTMLInputElement | null>(null)

const projects = ref<NovelProjectSummary[]>([])
const selectedProjectId = ref('')
const sources = ref<any[]>([])
const profiles = ref<any[]>([])
const globalActiveProfile = ref<any | null>(null)
const projectActiveProfile = ref<any | null>(null)
const selectedSourceIds = ref<string[]>([])
const draftTitle = ref('')
const draftContent = ref('')
const draftFormat = ref('')
const profileName = ref('')
const activeProfileId = ref('')
const sourceType = ref<'external_text' | 'external_novel'>('external_novel')
const importMode = ref<'file_stub' | 'chunk_manual' | 'hybrid'>('file_stub')
const batchLabel = ref('')
const batchSize = ref<'8k-15k' | '15k-30k' | '30k+'>('15k-30k')
const batchStrategy = ref('按卷或情节段拆分：先录入最能代表文风的部分，再逐批追加。')
const selectedFileName = ref('')
const selectedFileChars = ref(0)
const selectedUploadFile = ref<File | null>(null)
const historyKeyword = ref('')
const historyModeFilter = ref<'all' | 'file_stub' | 'chunk_manual' | 'hybrid'>('all')
const historyTypeFilter = ref<'all' | 'external_novel' | 'external_text'>('all')
const historySort = ref<'latest' | 'chars_desc' | 'chars_asc' | 'name_asc'>('latest')
const expandedHistoryGroups = ref<string[]>([])
const profileDrafts = ref<Record<string, string>>({})
const profileNameDrafts = ref<Record<string, string>>({})
const profileSummaryDrafts = ref<Record<string, Record<string, string>>>({})
const savingSource = ref(false)
const creatingProfile = ref(false)
const error = ref('')
const styleProgressVisible = computed(() => savingSource.value || creatingProfile.value)
const styleProgressPercent = computed(() => {
  if (creatingProfile.value) return 78
  if (savingSource.value) return 46
  return 0
})
const styleProgressTitle = computed(() => {
  if (creatingProfile.value) return '\u6b63\u5728\u751f\u6210\u6587\u98ce\u753b\u50cf'
  if (savingSource.value) return '\u6b63\u5728\u5199\u5165\u5b66\u4e60\u7d20\u6750'
  return ''
})
const styleProgressDescription = computed(() => {
  if (creatingProfile.value) return '\u7cfb\u7edf\u6b63\u5728\u6c47\u603b\u5df2\u9009\u6765\u6e90\uff0c\u63d0\u70bc\u53d9\u4e8b\u3001\u8282\u594f\u3001\u53e5\u5f0f\u548c\u63cf\u5199\u503e\u5411\u3002'
  if (savingSource.value) return '\u5f53\u524d\u7d20\u6750\u6b63\u5728\u843d\u5e93\uff0c\u7a0d\u540e\u5c31\u53ef\u4ee5\u52a0\u5165\u5b66\u4e60\u6279\u6b21\u6216\u7ee7\u7eed\u8865\u5f55\u3002'
  return ''
})

const summaryLabels: Record<string, string> = {
  narrative: '叙事',
  rhythm: '节奏',
  vocabulary: '词汇',
  dialogue: '对白',
  sentence: '句式',
  description: '描写'
}

const profileSummaryFields = [
  { key: 'narrative', label: '叙事', placeholder: '例如：第三人称冷观察、克制介入、旁白压低情绪。' },
  { key: 'rhythm', label: '节奏', placeholder: '例如：慢铺垫后快推进，关键冲突段骤然提速。' },
  { key: 'vocabulary', label: '词汇', placeholder: '例如：偏冷硬、少形容词、动词更锋利。' },
  { key: 'dialogue', label: '对白', placeholder: '例如：对白短促、有潜台词、避免过度解释。' },
  { key: 'sentence', label: '句式', placeholder: '例如：短句与中句混排，段尾常做收束。' },
  { key: 'description', label: '描写', placeholder: '例如：重动作和氛围，不堆设定名词，不复制专有元素。' }
] as const

const currentProjectTitle = computed(() => {
  if (!selectedProjectId.value) return '未选择项目'
  return projects.value.find(project => project.id === selectedProjectId.value)?.title || '未找到项目'
})

const sourcePlaceholder = computed(() => {
  if (importMode.value === 'file_stub') {
    return '填写这次导入的文件说明，例如：已导入 epub 全本、当前先学习第一卷前 10 章；后续可继续追加其他批次。'
  }

  if (importMode.value === 'hybrid') {
    return '填写“文件来源 + 当前补录批次”的组合说明，例如：原书为 txt，这里补录高密度对白段作为第二批学习样本。'
  }

  return '填写本次学习批次的摘要，而不是整本硬贴进去。例如：第 21-35 章，重点观察叙事节奏、对白推进和场景描写。'
})

const canCreateSource = computed(() => {
  return draftTitle.value.trim().length > 0 && draftContent.value.trim().length >= 20
})

const sourceStats = computed(() => {
  const total = sources.value.length
  const novel = sources.value.filter(source => source.source_type === 'external_novel').length
  const batch = total - novel
  const chars = sources.value.reduce((sum, source) => sum + Number(source.char_count || source.extra?.file_chars || 0), 0)
  return { total, novel, batch, chars }
})

const filteredSources = computed(() => {
  const keyword = historyKeyword.value.trim().toLowerCase()
  const sorted = [...sources.value].filter((source) => {
    const mode = source.extra?.import_mode
    const sourceType = source.source_type
    const searchable = [
      source.title,
      source.extra?.batch_label,
      source.extra?.file_name,
      source.extra?.format,
      source.extra?.note,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()

    if (historyModeFilter.value !== 'all' && mode !== historyModeFilter.value) return false
    if (historyTypeFilter.value !== 'all' && sourceType !== historyTypeFilter.value) return false
    if (keyword && !searchable.includes(keyword)) return false
    return true
  })

  sorted.sort((a, b) => {
    const aChars = Number(a.char_count || a.extra?.file_chars || 0)
    const bChars = Number(b.char_count || b.extra?.file_chars || 0)
    const aName = String(a.extra?.batch_label || a.title || '')
    const bName = String(b.extra?.batch_label || b.title || '')

    if (historySort.value === 'chars_desc') return bChars - aChars
    if (historySort.value === 'chars_asc') return aChars - bChars
    if (historySort.value === 'name_asc') return aName.localeCompare(bName, 'zh-Hans-CN')
    return 0
  })

  return sorted
})

const sourceTypeStats = computed(() => {
  const novelChars = sources.value
    .filter(source => source.source_type === 'external_novel')
    .reduce((sum, source) => sum + Number(source.char_count || source.extra?.file_chars || 0), 0)
  const batchChars = sources.value
    .filter(source => source.source_type === 'external_text')
    .reduce((sum, source) => sum + Number(source.char_count || source.extra?.file_chars || 0), 0)
  return { novelChars, batchChars }
})

const groupedFilteredSources = computed(() => {
  const groups = new Map<string, { key: string; label: string; fileName: string; count: number; totalChars: number; items: any[] }>()

  for (const source of filteredSources.value) {
    const label = source.title || source.extra?.file_name || '未命名来源'
    const fileName = source.extra?.file_name || source.title || '未命名文件'
    const key = `${label}::${fileName}`
    const chars = Number(source.char_count || source.extra?.file_chars || 0)
    const existing = groups.get(key)

    if (existing) {
      existing.count += 1
      existing.totalChars += chars
      existing.items.push(source)
    } else {
      groups.set(key, {
        key,
        label,
        fileName,
        count: 1,
        totalChars: chars,
        items: [source]
      })
    }
  }

  return Array.from(groups.values())
})

const timelineEntries = computed(() => {
  return filteredSources.value.slice(0, 12).map((source, index) => ({
    id: `${source.id}-${index}`,
    title: source.extra?.batch_label || source.title || '未命名批次',
    source: source.extra?.file_name || source.title || '未命名来源',
    mode: source.extra?.import_mode_label || importModeText(source.extra?.import_mode),
    format: source.extra?.format || '未标注',
    chars: Number(source.char_count || source.extra?.file_chars || 0),
    batch: source.extra?.batch_size || '未标注轮次体量'
  }))
})

const sourceModeStats = computed(() => {
  const base = {
    file_stub: { count: 0, chars: 0 },
    chunk_manual: { count: 0, chars: 0 },
    hybrid: { count: 0, chars: 0 }
  }

  for (const source of sources.value) {
    const mode = source.extra?.import_mode
    if (mode && mode in base) {
      base[mode as keyof typeof base].count += 1
      base[mode as keyof typeof base].chars += Number(source.char_count || source.extra?.file_chars || 0)
    }
  }

  return base
})

async function loadProjects() {
  const res = await NovelAPI.getAllNovels()
  projects.value = res || []
  if (!selectedProjectId.value && projects.value.length) {
    selectedProjectId.value = projects.value[0].id
  }
}

async function loadLibrary() {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    const res = await OptimizerAPI.getStyleLibrary(selectedProjectId.value)
    sources.value = res.sources || []
    profiles.value = res.profiles || []
    globalActiveProfile.value = res.global_active_profile || null
    projectActiveProfile.value = res.project_active_profile || null
    profileDrafts.value = Object.fromEntries(
      profiles.value.map(profile => [profile.id, profile.extra?.editor_note || ''])
    )
    profileNameDrafts.value = Object.fromEntries(
      profiles.value.map(profile => [profile.id, profile.name || ''])
    )
    profileSummaryDrafts.value = Object.fromEntries(
      profiles.value.map(profile => [
        profile.id,
        Object.fromEntries(
          profileSummaryFields.map(field => [field.key, profile.summary?.[field.key] || ''])
        )
      ])
    )
    if (activeProfileId.value && !profiles.value.some(profile => profile.id === activeProfileId.value)) {
      activeProfileId.value = ''
    }
    expandedHistoryGroups.value = groupedFilteredSources.value.map(group => group.key)
  } catch (e: any) {
    error.value = e.message || '加载文风库失败'
  }
}

async function createSource() {
  if (!selectedProjectId.value) return
  savingSource.value = true
  error.value = ''
  try {
    const noteText = draftContent.value.trim()
    const noteLabel = batchLabel.value.trim() || noteText.slice(0, 80) || '未命名批次'

    let res: { success: boolean; source: any }
    if (selectedUploadFile.value) {
      res = await OptimizerAPI.uploadStyleSource(selectedProjectId.value, {
        file: selectedUploadFile.value,
        title: draftTitle.value,
        source_type: importMode.value === 'chunk_manual' ? 'external_text' : 'external_novel',
        extra: {
          format: draftFormat.value.trim(),
          note: noteLabel,
          batch_label: batchLabel.value.trim(),
          batch_size: batchSize.value,
          batch_strategy: batchStrategy.value.trim(),
          import_mode: importMode.value,
          import_mode_label: importModeLabel(importMode.value),
          file_name: selectedFileName.value,
          file_chars: selectedFileChars.value,
          is_batch_note: false,
        }
      })
    } else {
      res = await OptimizerAPI.createStyleSource(selectedProjectId.value, {
        title: draftTitle.value,
        content_text: [
          `导入模式：${importModeLabel(importMode.value)}`,
          `来源格式：${draftFormat.value.trim() || '未标注'}`,
          `批次名称：${batchLabel.value.trim() || '未命名批次'}`,
          `建议批量：${batchSize.value}`,
          `拆批策略：${batchStrategy.value.trim() || '未填写'}`,
          '',
          noteText
        ].join('\n'),
        source_type: importMode.value === 'chunk_manual' ? 'external_text' : 'external_novel',
        extra: {
          format: draftFormat.value.trim(),
          note: noteLabel,
          batch_label: batchLabel.value.trim(),
          batch_size: batchSize.value,
          batch_strategy: batchStrategy.value.trim(),
          import_mode: importMode.value,
          import_mode_label: importModeLabel(importMode.value),
          file_name: selectedFileName.value,
          file_chars: selectedFileChars.value,
          is_batch_note: true,
        }
      })
    }

    sources.value = [res.source, ...sources.value]
    selectedSourceIds.value = [res.source.id]
    draftContent.value = ''
    batchLabel.value = ''
    selectedFileName.value = ''
    selectedFileChars.value = 0
    selectedUploadFile.value = null
    if (!draftTitle.value.trim()) draftTitle.value = res.source.title || ''
  } catch (e: any) {
    error.value = e.message || '保存素材失败'
  } finally {
    savingSource.value = false
  }
}

async function deleteSource(sourceId: string) {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    await OptimizerAPI.deleteStyleSource(selectedProjectId.value, sourceId)
    await loadLibrary()
    selectedSourceIds.value = selectedSourceIds.value.filter((id) => id !== sourceId)
  } catch (e: any) {
    error.value = e.message || '删除素材失败'
  }
}

async function createProfile() {
  if (!selectedProjectId.value) return
  creatingProfile.value = true
  error.value = ''
  try {
    await OptimizerAPI.createStyleProfile(selectedProjectId.value, {
      source_ids: selectedSourceIds.value,
      name: profileName.value.trim() || undefined,
      append_to_profile_id: activeProfileId.value || undefined
    })
    profileName.value = ''
    activeProfileId.value = ''
    await loadLibrary()
  } catch (e: any) {
    error.value = e.message || '生成画像失败'
  } finally {
    creatingProfile.value = false
  }
}

async function saveProfileEdits(profile: any) {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    const summaryDraft = profileSummaryDrafts.value[profile.id] || {}
    const normalizedSummary = Object.fromEntries(
      profileSummaryFields
        .map(field => [field.key, (summaryDraft[field.key] || '').trim()])
        .filter(([, value]) => Boolean(value))
    )

    await OptimizerAPI.updateStyleProfile(selectedProjectId.value, profile.id, {
      name: profileNameDrafts.value[profile.id]?.trim() || undefined,
      summary: normalizedSummary,
      extra: {
        editor_note: profileDrafts.value[profile.id] || ''
      }
    })
    await loadLibrary()
  } catch (e: any) {
    error.value = e.message || '保存画像字段失败'
  }
}

async function applyProfile(profileId: string, scope: 'global' | 'project') {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    await OptimizerAPI.activateStyleProfile(selectedProjectId.value, profileId, scope)
    await loadLibrary()
  } catch (e: any) {
    error.value = e.message || '应用文风失败'
  }
}

async function clearApplication(scope: 'global' | 'project') {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    await OptimizerAPI.clearActiveStyleProfile(selectedProjectId.value, scope)
    await loadLibrary()
  } catch (e: any) {
    error.value = e.message || '清理应用失败'
  }
}

function importModeLabel(mode: 'file_stub' | 'chunk_manual' | 'hybrid') {
  if (mode === 'file_stub') return '文件导入'
  if (mode === 'hybrid') return '混合模式'
  return '分批录入'
}

function importModeText(mode?: string) {
  if (mode === 'file_stub') return '文件导入'
  if (mode === 'hybrid') return '混合模式'
  if (mode === 'chunk_manual') return '分批录入'
  return '未标注'
}

function isHistoryGroupExpanded(groupKey: string) {
  return expandedHistoryGroups.value.includes(groupKey)
}

function toggleHistoryGroup(groupKey: string) {
  if (isHistoryGroupExpanded(groupKey)) {
    expandedHistoryGroups.value = expandedHistoryGroups.value.filter(key => key !== groupKey)
    return
  }
  expandedHistoryGroups.value = [...expandedHistoryGroups.value, groupKey]
}

function triggerFilePick() {
  fileInputRef.value?.click()
}

async function handleFilePicked(event: Event) {
  const input = event.target as HTMLInputElement | null
  const file = input?.files?.[0]
  if (!file) return

  try {
    selectedUploadFile.value = file
    selectedFileName.value = file.name
    draftFormat.value = file.name.split('.').pop()?.toLowerCase() || draftFormat.value
    if (!draftTitle.value.trim()) {
      draftTitle.value = file.name.replace(/\.[^.]+$/, '')
    }
    if (!batchLabel.value.trim()) {
      batchLabel.value = `文件批次 · ${file.name}`
    }

    const lightweightPreviewTypes = new Set(['txt', 'md', 'markdown', 'json', 'csv', 'log', 'text'])
    if (lightweightPreviewTypes.has(draftFormat.value)) {
      const text = await file.text()
      const normalized = text.replace(/\r\n/g, '\n').trim()
      selectedFileChars.value = normalized.length
      draftContent.value = normalized.slice(0, 4000)
    } else {
      selectedFileChars.value = file.size
      draftContent.value = `已选择文件 ${file.name}，将由服务端解析正文并建立素材。`
    }
  } catch (e: any) {
    error.value = e?.message || '读取文件失败'
  } finally {
    if (input) input.value = ''
  }
}

onMounted(async () => {
  await loadProjects()
  await loadLibrary()
})
</script>

<style scoped>
.style-center-page {
  max-width: 1360px;
  margin: 0 auto;
  padding: 28px 20px 48px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.style-center-hero,
.style-card {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(200, 210, 220, 0.24);
  border-radius: 24px;
  padding: 22px;
  box-shadow: 0 12px 32px rgba(88, 110, 140, 0.08);
}

.style-center-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 255, 0.94)),
    linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(139, 92, 246, 0.06));
}

.style-center-hero__eyebrow {
  margin-bottom: 8px;
  color: #64748b;
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.style-center-hero h1 {
  font-size: 1.65rem;
  font-weight: 800;
  color: #0f172a;
}

.style-center-hero__desc {
  color: #64748b;
  margin-top: 10px;
  line-height: 1.65;
  max-width: 780px;
}

.style-center-hero__select {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 240px;
  color: #475569;
  font-size: 0.86rem;
  font-weight: 600;
}

.style-center-hero__select select,
.form-input,
.form-textarea {
  width: 100%;
  border: 1px solid #d8e0ea;
  border-radius: 16px;
  padding: 12px 14px;
  background: #fcfdff;
  font-family: inherit;
}

.form-textarea {
  min-height: 180px;
  resize: vertical;
  line-height: 1.65;
}

.form-textarea--medium {
  min-height: 160px;
}

.form-textarea--small {
  min-height: 110px;
}

.form-textarea--micro {
  min-height: 88px;
}

.style-progress-panel {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  background: rgba(239, 246, 255, 0.9);
}

.style-progress-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.88rem;
  font-weight: 700;
  color: #0f172a;
}

.style-progress-panel__desc {
  margin: 0;
  color: #475569;
  font-size: 0.8rem;
  line-height: 1.45;
}

.style-progress-panel__track {
  width: 100%;
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
}

.style-progress-panel__bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2563eb, #14b8a6);
  transition: width 0.25s ease;
}

.style-center-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.style-summary-card {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(200, 210, 220, 0.24);
  border-radius: 22px;
  padding: 18px;
  box-shadow: 0 10px 24px rgba(88, 110, 140, 0.06);
}

.style-summary-card--accent {
  background: linear-gradient(135deg, #eff6ff, #f8fbff);
  border-color: #bfdbfe;
}

.style-summary-card__label {
  display: block;
  color: #64748b;
  font-size: 0.82rem;
}

.style-summary-card__value {
  display: block;
  margin-top: 10px;
  font-size: 1.08rem;
  color: #0f172a;
}

.style-summary-card__meta {
  margin-top: 8px;
  color: #64748b;
  font-size: 0.88rem;
  line-height: 1.6;
}

.style-center-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.style-card__header {
  margin-bottom: 16px;
}

.style-card__header--split {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.style-card__header h2 {
  font-size: 1.12rem;
  font-weight: 800;
  color: #0f172a;
}

.style-card__header p {
  margin-top: 8px;
  color: #64748b;
  font-size: 0.92rem;
  line-height: 1.65;
}

.workflow-badge,
.panel-tip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 700;
  color: #4338ca;
  background: rgba(139, 92, 246, 0.12);
}

.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.pipeline-step {
  border: 1px solid rgba(200, 210, 220, 0.18);
  border-radius: 18px;
  padding: 16px;
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.94), rgba(255, 255, 255, 0.94));
}

.pipeline-step__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  height: 24px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
  font-size: 0.74rem;
  font-weight: 800;
}

.pipeline-step strong {
  display: block;
  margin-top: 10px;
  font-size: 0.92rem;
  color: #0f172a;
}

.pipeline-step p {
  margin-top: 8px;
  font-size: 0.84rem;
  line-height: 1.58;
  color: #64748b;
}

.style-center-grid {
  display: grid;
  gap: 18px;
  align-items: start;
}

.style-center-grid--top {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.9fr);
}

.style-center-grid--bottom {
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.9fr) minmax(0, 1.15fr);
}

.import-mode-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.mode-chip,
.primary-btn,
.secondary-btn,
.text-btn {
  border: none;
  border-radius: 14px;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 700;
  transition: all 0.2s ease;
  font-family: inherit;
}

.mode-chip {
  background: #f1f5f9;
  color: #475569;
}

.mode-chip--active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.16), rgba(139, 92, 246, 0.16));
  color: #4338ca;
}

.primary-btn {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.secondary-btn {
  background: #eef2ff;
  color: #4338ca;
}

.text-btn {
  background: transparent;
  color: #475569;
}

.text-btn--danger {
  color: #dc2626;
}

.form-grid,
.batch-plan-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-block span {
  font-size: 0.82rem;
  font-weight: 700;
  color: #475569;
}

.field-block--full {
  grid-column: 1 / -1;
}

.import-dropzone {
  margin-top: 14px;
  border: 1px dashed rgba(148, 163, 184, 0.4);
  border-radius: 18px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.9), rgba(255, 255, 255, 0.9));
}

.import-dropzone__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-dropzone__input {
  display: none;
}

.selected-file-copy {
  margin-top: 10px;
  color: #475569;
  font-size: 0.84rem;
}

.profile-edit-box {
  margin-top: 14px;
}

.style-card--history {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.history-toolbar {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.history-group-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-source-group {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: #fcfdff;
  overflow: hidden;
}

.history-source-group__header {
  width: 100%;
  border: none;
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.96));
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  text-align: left;
  cursor: pointer;
}

.history-source-group__header strong {
  display: block;
  color: #0f172a;
  font-size: 0.9rem;
}

.history-source-group__header small {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 0.76rem;
}

.history-source-group__meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: #475569;
  font-size: 0.78rem;
  font-weight: 700;
}

.batch-history-table {
  display: flex;
  flex-direction: column;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  overflow: hidden;
  background: #fbfdff;
}

.batch-history-table__head,
.batch-history-row {
  display: grid;
  grid-template-columns: minmax(160px, 1.5fr) minmax(88px, 0.8fr) minmax(72px, 0.7fr) minmax(88px, 0.8fr) minmax(96px, 0.9fr);
  gap: 12px;
  padding: 12px 14px;
  align-items: center;
}

.batch-history-table__head {
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.95), rgba(248, 250, 252, 0.96));
  color: #475569;
  font-size: 0.78rem;
  font-weight: 800;
}

.batch-history-row {
  border-top: 1px solid #edf2f7;
  color: #334155;
  font-size: 0.84rem;
}

.batch-history-row:nth-child(even) {
  background: rgba(248, 250, 252, 0.72);
}

.batch-history-row__main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.batch-history-row__main strong {
  color: #0f172a;
  font-size: 0.88rem;
}

.batch-history-row__main small {
  color: #64748b;
  font-size: 0.76rem;
}

.source-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.source-stat-card {
  border-radius: 18px;
  padding: 14px;
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.96));
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.source-stat-card span {
  display: block;
  color: #64748b;
  font-size: 0.8rem;
}

.source-stat-card strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 1.08rem;
}

.source-stat-card small,
.history-group-card small {
  display: block;
  margin-top: 6px;
  color: #64748b;
  font-size: 0.78rem;
}

.history-group-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.history-group-card {
  border-radius: 18px;
  padding: 14px;
  background: linear-gradient(135deg, rgba(238, 242, 255, 0.92), rgba(248, 250, 252, 0.96));
  border: 1px solid rgba(199, 210, 254, 0.9);
}

.history-group-card span {
  display: block;
  color: #64748b;
  font-size: 0.8rem;
}

.history-group-card strong {
  display: block;
  margin-top: 8px;
  color: #312e81;
  font-size: 1.08rem;
}

.timeline-card {
  border-radius: 20px;
  border: 1px solid rgba(199, 210, 254, 0.9);
  background: linear-gradient(135deg, rgba(238, 242, 255, 0.7), rgba(255, 255, 255, 0.96));
  padding: 16px;
}

.timeline-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.timeline-card__head strong {
  color: #312e81;
}

.timeline-card__head span {
  color: #64748b;
  font-size: 0.8rem;
  font-weight: 700;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.timeline-item__dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.12);
}

.timeline-item__content {
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(224, 231, 255, 0.9);
}

.timeline-item__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.timeline-item__title-row strong {
  color: #0f172a;
  font-size: 0.88rem;
}

.timeline-item__title-row span,
.timeline-item__content p,
.timeline-item__content small {
  color: #64748b;
  font-size: 0.8rem;
  line-height: 1.6;
}

.timeline-item__content p {
  margin-top: 6px;
}

.timeline-item__content small {
  display: block;
  margin-top: 4px;
}

.profile-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.profile-name-editor {
  margin-top: 14px;
}

.import-dropzone strong,
.batch-note strong,
.guardrail-box strong {
  color: #0f172a;
}

.import-dropzone p,
.batch-note p {
  margin-top: 6px;
  font-size: 0.84rem;
  line-height: 1.56;
  color: #64748b;
}

.batch-notes {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.batch-note {
  border-radius: 18px;
  padding: 14px;
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.95), rgba(248, 250, 252, 0.92));
  border: 1px solid rgba(191, 219, 254, 0.8);
}

.style-card__footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.style-card__footer--split {
  flex-direction: row;
  justify-content: flex-end;
}

.style-hint,
.empty-copy,
.profile-meta,
.source-row__note {
  color: #64748b;
  font-size: 0.88rem;
  line-height: 1.6;
}

.list-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 18px;
}

.list-item {
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  padding: 14px;
  background: #fafcff;
}

.list-item--selectable {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.list-item__main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.list-item__main--top {
  align-items: flex-start;
}

.list-item--source {
  background: linear-gradient(135deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.96));
}

.source-row__title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.source-row__title h3 {
  font-size: 0.92rem;
  font-weight: 800;
  color: #0f172a;
}

.tag {
  font-size: 0.76rem;
  border-radius: 999px;
  padding: 4px 10px;
  font-weight: 700;
}

.tag--global {
  background: #ede9fe;
  color: #6d28d9;
}

.tag--project {
  background: #dbeafe;
  color: #1d4ed8;
}

.tag--source {
  background: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.list-item--profile {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.profile-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.summary-list {
  margin-top: 14px;
  display: grid;
  gap: 8px;
}

.summary-list li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #334155;
  font-size: 0.86rem;
}

.profile-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.guardrail-box {
  border: 1px solid rgba(191, 219, 254, 0.8);
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.95), rgba(248, 250, 252, 0.92));
  color: #334155;
  border-radius: 18px;
  padding: 14px 16px;
}

.guardrail-box ul {
  margin-top: 10px;
  padding-left: 18px;
  display: grid;
  gap: 8px;
  color: #475569;
  font-size: 0.86rem;
  line-height: 1.56;
}

.status-banner {
  border: 1px solid #dbeafe;
  background: #f8fbff;
  color: #334155;
  border-radius: 18px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
}

.error-copy {
  color: #dc2626;
}

@media (max-width: 1180px) {
  .pipeline-grid,
  .style-center-grid--top,
  .style-center-grid--bottom,
  .style-progress-panel {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  background: rgba(239, 246, 255, 0.9);
}

.style-progress-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.88rem;
  font-weight: 700;
  color: #0f172a;
}

.style-progress-panel__desc {
  margin: 0;
  color: #475569;
  font-size: 0.8rem;
  line-height: 1.45;
}

.style-progress-panel__track {
  width: 100%;
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
}

.style-progress-panel__bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2563eb, #14b8a6);
  transition: width 0.25s ease;
}

.style-center-summary-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .style-center-page {
    padding: 18px 14px 40px;
  }

  .style-center-hero,
  .style-card,
  .import-dropzone,
  .list-item--selectable,
  .style-card__header--split,
  .style-card__footer--split {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .form-grid,
  .batch-plan-grid,
  .profile-editor-grid,
  .source-stats-grid,
  .history-group-grid,
  .history-toolbar,
  .batch-history-table__head,
  .batch-history-row {
    grid-template-columns: 1fr;
  }

  .primary-btn,
  .secondary-btn,
  .mode-chip,
  .text-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
