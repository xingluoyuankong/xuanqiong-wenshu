<template>
  <div class="style-center-page">
    <section class="style-center-hero xq-page-topbar xq-page-topbar--style">
      <div>
        <p class="style-center-hero__eyebrow">{{ pick('独立文风中心 · 外部作品学习台', 'Standalone style center · External work learning desk') }}</p>
        <h1>{{ pick('外部参考文风库', 'External reference style library') }}</h1>
        <p class="style-center-hero__desc">{{ pick('不再要求手动粘贴整本小说。这里改成导入外部作品、分批学习、持续提炼、再输出可修改可补充的文风画像。', 'No more pasting a whole novel by hand. Import external works, learn in batches, keep distilling, then output a style profile you can edit and extend.') }}</p>
      </div>
      <div class="style-center-hero__actions">
        <label class="style-center-hero__select">
          <span>{{ pick('当前项目', 'Current project') }}</span>
          <select v-model="selectedProjectId" @change="loadLibrary">
            <option value="">{{ pick('请选择项目', 'Select a project') }}</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.title }}</option>
          </select>
        </label>
      </div>
    </section>

    <section v-if="styleProgressVisible" class="style-progress-panel">
      <div class="style-progress-panel__head">
        <strong>{{ styleProgressTitle }}</strong>
        <div class="style-progress-panel__actions">
          <span>{{ styleProgressPercent }}%</span>
          <button
            v-if="savingSource && sourceUploadRunId"
            type="button"
            class="style-progress-panel__cancel"
            :disabled="sourceUploadCancelRequested"
            @click="cancelSourceUpload"
          >
            {{ sourceUploadCancelRequested ? pick('取消中...', 'Cancelling...') : pick('取消', 'Cancel') }}
          </button>
        </div>
      </div>
      <p class="style-progress-panel__desc">{{ styleProgressDescription }}</p>
      <div class="style-progress-panel__track" aria-label="style-progress">
        <div class="style-progress-panel__bar" :style="{ width: `${styleProgressPercent}%` }"></div>
      </div>
    </section>

    <section class="style-center-summary-grid\ style-center-summary-grid--compact">
      <article class="style-summary-card--accent">
        <span class="style-summary-card__label">{{ pick('当前项目', 'Current project') }}</span>
        <strong class="style-summary-card__value">{{ currentProjectTitle }}</strong>
        <p class="style-summary-card__meta">{{ pick('先选项目，再决定把风格画像应用到项目级还是全局级。', 'Pick a project first, then decide whether to apply the style profile at project or global scope.') }}</p>
      </article>
      <article class="style-summary-card style-summary-card--compact">
        <span class="style-summary-card__label">{{ pick('全局生效', 'Global active') }}</span>
        <strong class="style-summary-card__value">{{ globalActiveProfile?.name || pick('未启用', 'Not enabled') }}</strong>
        <p class="style-summary-card__meta">{{ pick('适合统一所有项目的默认文风方向。', 'Best for one default style direction shared by every project.') }}</p>
      </article>
      <article class="style-summary-card style-summary-card--compact">
        <span class="style-summary-card__label">{{ pick('项目生效', 'Project active') }}</span>
        <strong class="style-summary-card__value">{{ projectActiveProfile?.name || pick('未启用', 'Not enabled') }}</strong>
        <p class="style-summary-card__meta">{{ pick('只覆盖当前项目，不影响其他小说。', 'Overrides the current project only, leaving other novels untouched.') }}</p>
      </article>
    </section>

    <section v-if="selectedProjectId" class="style-center-stack style-center-stack--compact">
      <article class="style-card style-card--pipeline style-card--compact">
        <div class="style-card__header style-card__header--split">
          <div>
            <h2>{{ pick('文风学习流程重构', 'Style learning workflow, rebuilt') }}</h2>
            <p>{{ pick('改成导入 → 拆批 → 提炼 → 累积画像 → 应用的工作流，专门对应长篇、超长篇参考作品。', 'The workflow is now import → split into batches → distill → accumulate the profile → apply, built for long and extra-long reference works.') }}</p>
          </div>
          <span class="workflow-badge">{{ pick('增量式学习', 'Incremental learning') }}</span>
        </div>

        <div class="pipeline-grid pipeline-grid--compact">
          <div class="pipeline-step">
            <span class="pipeline-step__index">01</span>
            <strong>{{ pick('导入外部作品', 'Import external works') }}</strong>
            <p>{{ pick('支持 txt、docx、epub、复制片段、整理稿等任意可转文本来源。先导入文件或分卷，再建立素材记录。', 'Supports txt, docx, epub, pasted excerpts, cleaned-up transcripts, and any other source that converts to text. Import a file or a volume first, then create the source record.') }}</p>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step__index">02</span>
            <strong>{{ pick('按批次学习', 'Learn batch by batch') }}</strong>
            <p>{{ pick('把超长文本拆成多批学习记录，每次只处理一部分，避免一次性塞入几十万到几百万字。', 'Split extra-long text into several learning records and handle one part per round, instead of pushing hundreds of thousands to millions of characters in at once.') }}</p>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step__index">03</span>
            <strong>{{ pick('累计风格画像', 'Accumulate the style profile') }}</strong>
            <p>{{ pick('每次学习都补充节奏、句式、叙述距离、描写倾向等维度，允许你后续再修改、再追加。', 'Every round adds dimensions such as pacing, sentence patterns, narrative distance, and descriptive tendencies, and you can revise or append later.') }}</p>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step__index">04</span>
            <strong>{{ pick('排除具体元素', 'Exclude concrete elements') }}</strong>
            <p>{{ pick('明确只提炼写法，不吸收角色名、势力名、地名、剧情结构、设定专名，避免照搬内容。', 'Only writing technique is distilled: no character names, faction names, place names, plot structure, or setting-specific terms, so nothing is copied verbatim.') }}</p>
          </div>
        </div>
      </article>

      <section class="style-center-grid style-center-grid--compact style-center-grid style-center-grid--compact--top">
        <article class="style-card style-card--importer style-card--compact">
          <div class="style-card__header">
            <div>
              <h2>{{ pick('1. 建立外部作品素材', '1. Create an external work source') }}</h2>
              <p>{{ pick('先登记一部参考作品，再决定通过文件导入、手动补充还是分批录入。', 'Register a reference work first, then choose file import, manual notes, or batch entry.') }}</p>
            </div>
          </div>

          <div class="import-mode-grid">
            <button :class="['mode-chip', { 'mode-chip--active': importMode === 'file_stub' }]" @click="importMode = 'file_stub'">
              {{ pick('文件导入', 'File import') }}
            </button>
            <button :class="['mode-chip', { 'mode-chip--active': importMode === 'chunk_manual' }]" @click="importMode = 'chunk_manual'">
              {{ pick('分批录入', 'Batch entry') }}
            </button>
            <button :class="['mode-chip', { 'mode-chip--active': importMode === 'hybrid' }]" @click="importMode = 'hybrid'">
              {{ pick('混合模式', 'Hybrid mode') }}
            </button>
          </div>

          <div class="form-grid">
            <label class="field-block">
              <span>{{ pick('作品名称', 'Work title') }}</span>
              <input v-model.trim="draftTitle" type="text" class="form-input" :placeholder="pick('例如：某部参考长篇', 'e.g. a long reference novel')" />
            </label>
            <label class="field-block">
              <span>{{ pick('来源格式', 'Source format') }}</span>
              <input v-model.trim="draftFormat" type="text" class="form-input" :placeholder="pick('txt / docx / epub / 网页整理稿 / 片段合集', 'txt / docx / epub / cleaned-up web text / excerpt collection')" />
            </label>
            <label class="field-block field-block--full">
              <span>{{ pick('导入说明', 'Import notes') }}</span>
              <textarea
                v-model="draftContent"
                class="form-textarea form-textarea--medium"
                :placeholder="sourcePlaceholder"
              ></textarea>
            </label>
          </div>

          <div class="import-dropzone">
            <div>
              <strong>{{ pick('文件导入入口', 'File import entry') }}</strong>
              <p>{{ pick('当前已支持 txt / md / json / csv / log / docx / epub；纯文本会在前端预览片段，docx/epub 交给服务端抽取正文后进入学习批次。', 'txt / md / json / csv / log / docx / epub are supported. Plain text is previewed in the browser; docx/epub go to the server, which extracts the body before it enters a learning batch.') }}</p>
            </div>
            <div class="import-dropzone__actions">
              <input ref="fileInputRef" class="import-dropzone__input" type="file" accept=".txt,.md,.markdown,.json,.csv,.log,.text,.docx,.epub" @change="handleFilePicked" />
              <button class="secondary-btn" type="button" @click="triggerFilePick">{{ pick('选择文件', 'Choose file') }}</button>
            </div>
          </div>
          <p v-if="selectedFileName" class="selected-file-copy">{{ pick('已载入文件：', 'Loaded file: ') }}{{ selectedFileName }} <span v-if="selectedFileChars">· {{ selectedFileChars }} {{ pick('字', 'chars') }}</span></p>

          <div class="style-card__footer">
            <span class="style-hint">{{ pick('已支持大文本分批学习：超长文本会自动拆分为多个批次逐批提取风格特征，再合并为统一画像。', 'Large-text batch learning is supported: extra-long text is split into batches, style features are extracted batch by batch, then merged into one profile.') }}</span>
            <button class="primary-btn" :disabled="savingSource || !canCreateSource" @click="createSource">{{ pick('保存素材记录', 'Save source record') }}</button>
          </div>
        </article>

        <article class="style-card style-card--batch">
          <div class="style-card__header style-card__header--split">
            <div>
              <h2>{{ pick('2. 学习批次策略', '2. Learning batch strategy') }}</h2>
              <p>{{ pick('为长篇/超长篇建立拆批规则，后续每一批都可以单独学习并继续补充画像。', 'Set batching rules for long and extra-long works; each batch can then be learned on its own and keep extending the profile.') }}</p>
            </div>
            <span class="panel-tip">{{ activeProfileId ? pick('补充到现有画像', 'Append to existing profile') : pick('新建画像批次', 'New profile batch') }}</span>
          </div>

          <div class="batch-plan-grid">
            <label class="field-block">
              <span>{{ pick('当前批次名称', 'Current batch name') }}</span>
              <input v-model.trim="batchLabel" type="text" class="form-input" :placeholder="pick('例如：第一卷首批章节 / 中段对白批次', 'e.g. first chapters of volume one / mid-section dialogue batch')" />
            </label>
            <label class="field-block">
              <span>{{ pick('建议批量', 'Suggested batch size') }}</span>
              <select v-model="batchSize" class="form-input">
                <option value="8k-15k">{{ pick('8k - 15k 字 / 批', '8k - 15k chars / batch') }}</option>
                <option value="15k-30k">{{ pick('15k - 30k 字 / 批', '15k - 30k chars / batch') }}</option>
                <option value="30k+">{{ pick('30k+ 字 / 批', '30k+ chars / batch') }}</option>
              </select>
            </label>
            <label class="field-block field-block--full">
              <span>{{ pick('拆批说明', 'Batching notes') }}</span>
              <textarea
                v-model="batchStrategy"
                class="form-textarea form-textarea--small"
                :placeholder="pick('例如：先拆开世界观铺垫段、核心对白段、战斗段、抒情段，逐批建立风格特征。', 'e.g. separate the world setting setup, the core dialogue, the combat, and the lyrical passages, then build style features batch by batch.')"
              ></textarea>
            </label>
          </div>

          <div class="batch-notes">
            <div class="batch-note">
              <strong>{{ pick('适合超长文本', 'Good for extra-long text') }}</strong>
              <p>{{ pick('一次只分析一个批次，不要求把全书一次塞进去。', 'Only one batch is analyzed per round, so the whole book never has to go in at once.') }}</p>
            </div>
            <div class="batch-note">
              <strong>{{ pick('适合持续补录', 'Good for ongoing additions') }}</strong>
              <p>{{ pick('今天录一卷，后面继续补另一卷，画像会逐步完善。', 'Add one volume today and another later; the profile keeps getting richer.') }}</p>
            </div>
          </div>
        </article>
      </section>

      <section class="style-center-grid style-center-grid--compact style-center-grid style-center-grid--compact--bottom">
        <article class="style-card style-card--sources">
          <div class="style-card__header style-card__header--split">
            <div>
              <h2>{{ pick('3. 素材库 / 学习来源', '3. Source library / learning sources') }}</h2>
              <p>{{ pick('这些是你已经建立的外部作品或学习批次。选择多个来源后，可以继续生成或补全文风画像。', 'These are the external works and learning batches you have created. Select several sources to generate or complete a style profile.') }}</p>
            </div>
            <span class="panel-tip">{{ pick('可多选合并', 'Multi-select and merge') }}</span>
          </div>

          <div v-if="sources.length" class="list-stack">
            <label v-for="source in sources" :key="source.id" class="list-item list-item--selectable list-item--source">
              <div class="list-item__main list-item__main--top">
                <input v-model="selectedSourceIds" :value="source.id" type="checkbox" />
                <div>
                  <div class="source-row__title">
                    <h3>{{ source.title }}</h3>
                    <span class="tag tag--source">{{ source.source_type === 'external_novel' ? pick('长篇来源', 'Long-form source') : pick('学习批次', 'Learning batch') }}</span>
                  </div>
                  <p>{{ source.char_count || 0 }} {{ pick('字', 'chars') }} · {{ source.extra?.format || draftFormat || pick('未标注格式', 'Format not set') }}</p>
                  <p class="source-row__note">{{ source.extra?.note || pick('当前版本接口未拆出文件元数据，先保留为素材描述。', 'This build does not split out file metadata yet, so it stays as the source description.') }}</p>
                </div>
              </div>
              <button class="text-btn text-btn--danger" @click="deleteSource(source.id)">{{ pick('删除', 'Delete') }}</button>
            </label>
          </div>
          <p v-else class="empty-copy">{{ pick('还没有素材，先建立一部参考作品或一个学习批次。', 'No sources yet. Create a reference work or a learning batch first.') }}</p>

          <div class="style-card__footer">
            <select v-model="activeProfileId" class="form-input">
              <option value="">{{ pick('新建画像', 'New profile') }}</option>
              <option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ pick('补充到：', 'Append to: ') }}{{ profile.name }}</option>
            </select>
            <input v-model.trim="profileName" type="text" class="form-input" :placeholder="activeProfileId ? pick('可选：为补全后的画像改名', 'Optional: rename the completed profile') : pick('画像名称（例如：冷峻叙事+高密度对白）', 'Profile name (e.g. cool narration + dense dialogue)')" />
            <button class="primary-btn" :disabled="creatingProfile || selectedSourceIds.length === 0" @click="createProfile">{{ pick('生成 / 补全文风画像', 'Generate / complete style profile') }}</button>
          </div>
        </article>

        <article class="style-card style-card--history">
          <div class="style-card__header style-card__header--split">
            <div>
              <h2>{{ pick('4. 学习批次历史', '4. Learning batch history') }}</h2>
              <p>{{ pick('把文件来源、批次标签、格式、字符数和导入模式展开成真正的批次视图，方便追踪每轮学习来源。', 'File source, batch label, format, character count, and import mode are laid out as a real batch view, so every learning round stays traceable.') }}</p>
            </div>
            <span class="panel-tip">{{ sourceStats.total }} {{ pick('个批次', 'batches') }}</span>
          </div>

          <div class="history-toolbar">
            <label class="field-block">
              <span>{{ pick('关键词', 'Keyword') }}</span>
              <input v-model.trim="historyKeyword" type="text" class="form-input" :placeholder="pick('筛选批次名、文件名、格式', 'Filter by batch name, file name, or format')" />
            </label>
            <label class="field-block">
              <span>{{ pick('模式', 'Mode') }}</span>
              <select v-model="historyModeFilter" class="form-input">
                <option value="all">{{ pick('全部模式', 'All modes') }}</option>
                <option value="file_stub">{{ pick('文件导入', 'File import') }}</option>
                <option value="chunk_manual">{{ pick('分批录入', 'Batch entry') }}</option>
                <option value="hybrid">{{ pick('混合模式', 'Hybrid mode') }}</option>
              </select>
            </label>
            <label class="field-block">
              <span>{{ pick('来源类型', 'Source type') }}</span>
              <select v-model="historyTypeFilter" class="form-input">
                <option value="all">{{ pick('全部类型', 'All types') }}</option>
                <option value="external_novel">{{ pick('长篇来源', 'Long-form source') }}</option>
                <option value="external_text">{{ pick('学习批次', 'Learning batch') }}</option>
              </select>
            </label>
            <label class="field-block">
              <span>{{ pick('排序', 'Sort') }}</span>
              <select v-model="historySort" class="form-input">
                <option value="latest">{{ pick('最新导入优先', 'Newest import first') }}</option>
                <option value="chars_desc">{{ pick('字数从高到低', 'Word count high to low') }}</option>
                <option value="chars_asc">{{ pick('字数从低到高', 'Word count low to high') }}</option>
                <option value="name_asc">{{ pick('名称 A-Z', 'Name A-Z') }}</option>
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
                  <span>{{ group.count }} {{ pick('条', 'items') }}</span>
                  <span>{{ group.totalChars }} {{ pick('字', 'chars') }}</span>
                  <span>{{ isHistoryGroupExpanded(group.key) ? pick('收起', 'Collapse') : pick('展开', 'Expand') }}</span>
                </div>
              </button>

              <div v-if="isHistoryGroupExpanded(group.key)" class="batch-history-table">
                <div class="batch-history-table__head">
                  <span>{{ pick('批次 / 来源', 'Batch / source') }}</span>
                  <span>{{ pick('模式', 'Mode') }}</span>
                  <span>{{ pick('格式', 'Format') }}</span>
                  <span>{{ pick('体量', 'Size') }}</span>
                  <span>{{ pick('轮次线索', 'Round hint') }}</span>
                </div>
                <article v-for="source in group.items" :key="`${source.id}-history`" class="batch-history-row">
                  <div class="batch-history-row__main">
                    <strong>{{ source.extra?.batch_label || source.title }}</strong>
                    <small>{{ source.extra?.file_name || source.title }}</small>
                  </div>
                  <span>{{ source.extra?.import_mode_label || importModeText(source.extra?.import_mode) }}</span>
                  <span>{{ source.extra?.format || pick('未标注', 'Not set') }}</span>
                  <span>{{ source.char_count || source.extra?.file_chars || 0 }} {{ pick('字', 'chars') }}</span>
                  <span>{{ source.extra?.batch_size || pick('待补充', 'To be filled') }}</span>
                </article>
              </div>
            </section>
          </div>
          <p v-else class="empty-copy">{{ pick('当前筛选条件下没有批次，先放宽筛选或继续导入素材。', 'No batches match the current filters. Loosen the filters or import more sources.') }}</p>

          <div class="source-stats-grid">
            <div class="source-stat-card">
              <span>{{ pick('长篇来源', 'Long-form source') }}</span>
              <strong>{{ sourceStats.novel }}</strong>
              <small>{{ sourceTypeStats.novelChars }} {{ pick('字', 'chars') }}</small>
            </div>
            <div class="source-stat-card">
              <span>{{ pick('学习批次', 'Learning batch') }}</span>
              <strong>{{ sourceStats.batch }}</strong>
              <small>{{ sourceTypeStats.batchChars }} {{ pick('字', 'chars') }}</small>
            </div>
            <div class="source-stat-card">
              <span>{{ pick('总字数', 'Total word count') }}</span>
              <strong>{{ sourceStats.chars }}</strong>
              <small>{{ filteredSources.length }} {{ pick('条可见记录', 'visible records') }}</small>
            </div>
          </div>

          <div class="history-group-grid">
            <article class="history-group-card">
              <span>{{ pick('文件导入', 'File import') }}</span>
              <strong>{{ sourceModeStats.file_stub.count }}</strong>
              <small>{{ sourceModeStats.file_stub.chars }} {{ pick('字', 'chars') }}</small>
            </article>
            <article class="history-group-card">
              <span>{{ pick('分批录入', 'Batch entry') }}</span>
              <strong>{{ sourceModeStats.chunk_manual.count }}</strong>
              <small>{{ sourceModeStats.chunk_manual.chars }} {{ pick('字', 'chars') }}</small>
            </article>
            <article class="history-group-card">
              <span>{{ pick('混合模式', 'Hybrid mode') }}</span>
              <strong>{{ sourceModeStats.hybrid.count }}</strong>
              <small>{{ sourceModeStats.hybrid.chars }} {{ pick('字', 'chars') }}</small>
            </article>
          </div>

          <div class="timeline-card">
            <div class="timeline-card__head">
              <strong>{{ pick('学习轮次时间线', 'Learning round timeline') }}</strong>
              <span>{{ filteredSources.length }} {{ pick('条轨迹', 'traces') }}</span>
            </div>
            <div v-if="timelineEntries.length" class="timeline-list">
              <article v-for="entry in timelineEntries" :key="entry.id" class="timeline-item">
                <div class="timeline-item__dot"></div>
                <div class="timeline-item__content">
                  <div class="timeline-item__title-row">
                    <strong>{{ entry.title }}</strong>
                    <span>{{ entry.mode }}</span>
                  </div>
                  <p>{{ entry.source }} · {{ entry.format }} · {{ entry.chars }} {{ pick('字', 'chars') }}</p>
                  <small>{{ entry.batch }}</small>
                </div>
              </article>
            </div>
            <p v-else class="empty-copy">{{ pick('还没有可展示的学习轨迹。', 'No learning traces to show yet.') }}</p>
          </div>
        </article>

        <article class="style-card style-card--profiles">
          <div class="style-card__header">
            <div>
              <h2>{{ pick('4. 文风画像与应用', '4. Style profiles and application') }}</h2>
              <p>{{ pick('画像保留为可持续编辑的风格摘要。应用时只传递写法倾向，不应复制角色名、地名、组织名和剧情结构。', 'A profile stays an editable style summary. Applying it passes on writing tendencies only, never character names, place names, organization names, or plot structure.') }}</p>
            </div>
          </div>

          <div class="guardrail-box">
            <strong>{{ pick('提炼边界', 'Distillation boundary') }}</strong>
            <ul>
              <li>{{ pick('保留：叙述视角、句长分布、节奏切换、对白密度、描写偏好、措辞倾向。', 'Kept: narrative viewpoint, sentence length distribution, pacing shifts, dialogue density, descriptive preferences, word choice tendencies.') }}</li>
              <li>{{ pick('排除：角色姓名、关系网、专有设定、门派/组织、地名、世界观专词、剧情桥段。', 'Excluded: character names, relationship webs, proprietary settings, sects and organizations, place names, world setting jargon, plot set pieces.') }}</li>
            </ul>
          </div>

          <div class="status-banner" v-if="globalActiveProfile || projectActiveProfile">
            <div v-if="globalActiveProfile">
              <strong>{{ pick('全局应用：', 'Applied globally: ') }}</strong>{{ globalActiveProfile.name }}
            </div>
            <div v-if="projectActiveProfile">
              <strong>{{ pick('项目应用：', 'Applied to project: ') }}</strong>{{ projectActiveProfile.name }}
            </div>
          </div>

          <div v-if="profiles.length" class="list-stack">
            <article v-for="profile in profiles" :key="profile.id" class="list-item list-item--profile">
              <div>
                <div class="profile-title-row">
                  <h3>{{ profile.name }}</h3>
                  <span v-if="projectActiveProfile?.id === profile.id" class="tag tag--project">{{ pick('当前项目', 'Current project') }}</span>
                  <span v-else-if="globalActiveProfile?.id === profile.id" class="tag tag--global">{{ pick('全局', 'Global') }}</span>
                  <span class="tag tag--source">{{ pick('累计', 'Merged') }} {{ profile.quality_metrics?.merge_rounds || 1 }} {{ pick('轮', 'rounds') }}</span>
                </div>
                <p class="profile-meta">{{ pick('来源：', 'Sources: ') }}{{ (profile.extra?.source_titles || []).join(' / ') || pick('未命名来源', 'Untitled source') }}</p>
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
                  <span>{{ pick('画像名称', 'Profile name') }}</span>
                  <input
                    v-model.trim="profileNameDrafts[profile.id]"
                    type="text"
                    class="form-input"
                    :placeholder="pick('可直接调整画像标题', 'Rename the profile directly')"
                  />
                </label>

                <textarea
                  v-model="profileDrafts[profile.id]"
                  class="form-textarea form-textarea--small profile-edit-box"
                  :placeholder="pick('补充说明：例如保留冷峻旁白、降低比喻密度、对白更克制。', 'Extra notes, e.g. keep the cool narration, lower metaphor density, make dialogue more restrained.')"
                ></textarea>
              </div>
              <div class="profile-actions">
                <button class="secondary-btn" @click="saveProfileEdits(profile)">{{ pick('保存画像字段', 'Save profile fields') }}</button>
                <button class="secondary-btn" @click="applyProfile(profile.id, 'global')">{{ pick('设为全局', 'Set as global') }}</button>
                <button class="primary-btn" @click="applyProfile(profile.id, 'project')">{{ pick('应用到当前项目', 'Apply to current project') }}</button>
              </div>
            </article>
          </div>
          <p v-else class="empty-copy">{{ pick('还没有画像，先从左侧素材中选择一批或多批来源。', 'No profiles yet. Select one or more sources from the library on the left.') }}</p>

          <div class="style-card__footer style-card__footer--split">
            <button class="secondary-btn" :disabled="!globalActiveProfile" @click="clearApplication('global')">{{ pick('清理全局应用', 'Clear global application') }}</button>
            <button class="secondary-btn" :disabled="!projectActiveProfile" @click="clearApplication('project')">{{ pick('清理当前项目应用', 'Clear current project application') }}</button>
          </div>
        </article>
      </section>
    </section>

    <section v-else class="style-card">
      <p class="empty-copy">{{ pick('当前还没有项目。请先创建小说项目，再进入独立文风中心。', 'No projects yet. Create a novel project first, then come back to the standalone style center.') }}</p>
    </section>

    <p v-if="error" class="error-copy">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NovelAPI, OptimizerAPI, type NovelProjectSummary, type StyleSourceUploadJobResponse } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

const { pick } = useLocale()

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
// 表单初值：用户可以随手改写，所以只在挂载时按当前语言取一次，避免切换语言把已编辑内容冲掉。
const batchStrategy = ref(pick(
  '按卷或情节段拆分：先录入最能代表文风的部分，再逐批追加。',
  'Split by volume or plot segment: enter the most representative parts first, then append batch by batch.',
))
const selectedFileName = ref('')
const selectedFileChars = ref(0)
const selectedUploadFile = ref<File | null>(null)
const sourceUploadRunId = ref('')
const sourceUploadStage = ref('')
const sourceUploadMessage = ref('')
const sourceUploadCancelRequested = ref(false)
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
  if (savingSource.value) {
    const stageProgress: Record<string, number> = {
      queued: 8,
      upload_reading: 24,
      upload_extracting: 58,
      upload_saving: 84,
      successful: 100,
      failed: 100,
      cancelled: 100
    }
    return stageProgress[sourceUploadStage.value] ?? 46
  }
  return 0
})
const styleProgressTitle = computed(() => {
  if (creatingProfile.value) return pick('正在生成文风画像', 'Generating the style profile')
  if (savingSource.value) return pick('正在写入学习素材', 'Writing the learning source')
  return ''
})
const styleProgressDescription = computed(() => {
  if (creatingProfile.value) return pick('系统正在汇总已选来源，提炼叙事、节奏、句式和描写倾向。', 'The selected sources are being merged to distill narrative, pacing, sentence patterns, and descriptive tendencies.')
  if (savingSource.value && sourceUploadMessage.value) return sourceUploadMessage.value
  if (savingSource.value) return pick('当前素材正在落库，稍后就可以加入学习批次或继续补录。', 'The source is being stored; soon you can add it to a learning batch or keep appending.')
  return ''
})

const STYLE_SOURCE_UPLOAD_POLL_INTERVAL_MS = 2000
const STYLE_SOURCE_UPLOAD_MAX_POLL_ATTEMPTS = 900
const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

// 后端 summary 的 key 固定不变，这里只翻译展示用的维度名，放在 computed 里保证切语言重新求值。
const summaryLabels = computed<Record<string, string>>(() => ({
  narrative: pick('叙事', 'Narrative'),
  rhythm: pick('节奏', 'Pacing'),
  vocabulary: pick('词汇', 'Vocabulary'),
  dialogue: pick('对白', 'Dialogue'),
  sentence: pick('句式', 'Sentence patterns'),
  description: pick('描写', 'Description')
}))

const profileSummaryFields = computed(() => [
  { key: 'narrative', label: pick('叙事', 'Narrative'), placeholder: pick('例如：第三人称冷观察、克制介入、旁白压低情绪。', 'e.g. cool third-person observation, restrained intervention, narration that keeps emotion low.') },
  { key: 'rhythm', label: pick('节奏', 'Pacing'), placeholder: pick('例如：慢铺垫后快推进，关键冲突段骤然提速。', 'e.g. slow setup then fast progression, with a sudden speed-up at key conflicts.') },
  { key: 'vocabulary', label: pick('词汇', 'Vocabulary'), placeholder: pick('例如：偏冷硬、少形容词、动词更锋利。', 'e.g. cold and hard, few adjectives, sharper verbs.') },
  { key: 'dialogue', label: pick('对白', 'Dialogue'), placeholder: pick('例如：对白短促、有潜台词、避免过度解释。', 'e.g. clipped dialogue with subtext, no over-explaining.') },
  { key: 'sentence', label: pick('句式', 'Sentence patterns'), placeholder: pick('例如：短句与中句混排，段尾常做收束。', 'e.g. short and medium sentences mixed, with paragraphs often closing on a beat.') },
  { key: 'description', label: pick('描写', 'Description'), placeholder: pick('例如：重动作和氛围，不堆设定名词，不复制专有元素。', 'e.g. lean on action and atmosphere, no piling up setting nouns, no copying proprietary elements.') }
])

const currentProjectTitle = computed(() => {
  if (!selectedProjectId.value) return pick('未选择项目', 'No project selected')
  return projects.value.find(project => project.id === selectedProjectId.value)?.title || pick('未找到项目', 'Project not found')
})

const sourcePlaceholder = computed(() => {
  if (importMode.value === 'file_stub') {
    return pick(
      '填写这次导入的文件说明，例如：已导入 epub 全本、当前先学习第一卷前 10 章；后续可继续追加其他批次。',
      'Describe the file you imported, e.g. the full epub is in and you are starting with the first 10 chapters of volume one; more batches can be appended later.',
    )
  }

  if (importMode.value === 'hybrid') {
    return pick(
      '填写"文件来源 + 当前补录批次"的组合说明，例如：原书为 txt，这里补录高密度对白段作为第二批学习样本。',
      'Describe the combination of file source plus the batch you are adding now, e.g. the original is txt and you are adding dense dialogue passages as the second learning sample.',
    )
  }

  return pick(
    '填写本次学习批次的摘要，而不是整本硬贴进去。例如：第 21-35 章，重点观察叙事节奏、对白推进和场景描写。',
    'Summarize this learning batch instead of pasting the whole book. E.g. chapters 21-35, focusing on narrative pacing, dialogue progression, and scene description.',
  )
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
    const label = source.title || source.extra?.file_name || pick('未命名来源', 'Untitled source')
    const fileName = source.extra?.file_name || source.title || pick('未命名文件', 'Untitled file')
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
    title: source.extra?.batch_label || source.title || pick('未命名批次', 'Untitled batch'),
    source: source.extra?.file_name || source.title || pick('未命名来源', 'Untitled source'),
    mode: source.extra?.import_mode_label || importModeText(source.extra?.import_mode),
    format: source.extra?.format || pick('未标注', 'Not set'),
    chars: Number(source.char_count || source.extra?.file_chars || 0),
    batch: source.extra?.batch_size || pick('未标注轮次体量', 'Round size not set')
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
          profileSummaryFields.value.map(field => [field.key, profile.summary?.[field.key] || ''])
        )
      ])
    )
    if (activeProfileId.value && !profiles.value.some(profile => profile.id === activeProfileId.value)) {
      activeProfileId.value = ''
    }
    expandedHistoryGroups.value = groupedFilteredSources.value.map(group => group.key)
  } catch (e: any) {
    error.value = e.message || pick('加载文风库失败', 'Failed to load the style library')
  }
}

function readStyleSourceUploadError(status: StyleSourceUploadJobResponse): string {
  const rawError = status.error
  const fallback = pick('文风素材导入失败，请稍后重试', 'Style source import failed. Please try again later.')
  if (!rawError) return status.progress_message || fallback
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || fallback
}

async function uploadSourceWithProgress(payload: {
  file: File
  title?: string
  source_type?: string
  extra?: Record<string, any>
}): Promise<{ success: boolean; source: any }> {
  if (!selectedProjectId.value) throw new Error(pick('请先选择项目', 'Select a project first'))
  const projectId = selectedProjectId.value

  let status = await OptimizerAPI.startStyleSourceUpload(projectId, payload)
  sourceUploadRunId.value = status.run_id

  for (let attempt = 0; attempt < STYLE_SOURCE_UPLOAD_MAX_POLL_ATTEMPTS; attempt += 1) {
    sourceUploadStage.value = status.progress_stage || status.status
    sourceUploadMessage.value = status.progress_message || pick('文风素材导入进行中...', 'Style source import in progress...')

    if (status.status === 'successful' && status.source) {
      return { success: true, source: status.source }
    }
    if (status.status === 'failed') {
      throw new Error(readStyleSourceUploadError(status))
    }
    if (status.status === 'cancelled') {
      throw new Error(status.progress_message || pick('文风素材导入已取消', 'Style source import cancelled'))
    }

    await wait(STYLE_SOURCE_UPLOAD_POLL_INTERVAL_MS)
    status = await OptimizerAPI.getStyleSourceUploadStatus(projectId, sourceUploadRunId.value)
  }

  throw new Error(pick(
    '文风素材导入后台任务等待超时，请稍后刷新文风中心查看结果。',
    'The style source import job timed out. Refresh the style center later to check the result.',
  ))
}

async function createSource() {
  if (!selectedProjectId.value) return
  savingSource.value = true
  error.value = ''
  sourceUploadRunId.value = ''
  sourceUploadStage.value = selectedUploadFile.value ? 'queued' : 'upload_saving'
  sourceUploadMessage.value = selectedUploadFile.value
    ? pick('正在提交文风素材导入任务...', 'Submitting the style source import job...')
    : pick('正在保存手动学习素材...', 'Saving the manual learning source...')
  sourceUploadCancelRequested.value = false
  try {
    const noteText = draftContent.value.trim()
    const noteLabel = batchLabel.value.trim() || noteText.slice(0, 80) || pick('未命名批次', 'Untitled batch')

    let res: { success: boolean; source: any }
    if (selectedUploadFile.value) {
      res = await uploadSourceWithProgress({
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
        // 下面这段是写给后端/模型的素材正文，属于 payload 数据而不是界面文案，固定用中文以保证后端解析稳定。
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
    error.value = e.message || pick('保存素材失败', 'Failed to save the source')
  } finally {
    savingSource.value = false
    sourceUploadRunId.value = ''
    sourceUploadStage.value = ''
    sourceUploadMessage.value = ''
    sourceUploadCancelRequested.value = false
  }
}

async function cancelSourceUpload() {
  if (!selectedProjectId.value || !sourceUploadRunId.value || sourceUploadCancelRequested.value) return
  sourceUploadCancelRequested.value = true
  try {
    const status = await OptimizerAPI.cancelStyleSourceUpload(selectedProjectId.value, sourceUploadRunId.value)
    sourceUploadStage.value = status.progress_stage || status.status
    sourceUploadMessage.value = status.progress_message || pick('正在取消文风素材导入...', 'Cancelling the style source import...')
    if (status.status !== 'cancelled') {
      sourceUploadCancelRequested.value = false
    }
  } catch (e: any) {
    sourceUploadCancelRequested.value = false
    sourceUploadMessage.value = e?.message || pick('取消失败，文风素材导入仍在继续', 'Cancel failed; the style source import is still running')
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
    error.value = e.message || pick('删除素材失败', 'Failed to delete the source')
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
    error.value = e.message || pick('生成画像失败', 'Failed to generate the profile')
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
      profileSummaryFields.value
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
    error.value = e.message || pick('保存画像字段失败', 'Failed to save the profile fields')
  }
}

async function applyProfile(profileId: string, scope: 'global' | 'project') {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    await OptimizerAPI.activateStyleProfile(selectedProjectId.value, profileId, scope)
    await loadLibrary()
  } catch (e: any) {
    error.value = e.message || pick('应用文风失败', 'Failed to apply the style')
  }
}

async function clearApplication(scope: 'global' | 'project') {
  if (!selectedProjectId.value) return
  error.value = ''
  try {
    await OptimizerAPI.clearActiveStyleProfile(selectedProjectId.value, scope)
    await loadLibrary()
  } catch (e: any) {
    error.value = e.message || pick('清理应用失败', 'Failed to clear the application')
  }
}

// 只在写入后端 payload（extra.import_mode_label 与素材正文）时使用，属于持久化数据，保持中文不随界面语言变化。
function importModeLabel(mode: 'file_stub' | 'chunk_manual' | 'hybrid') {
  if (mode === 'file_stub') return '文件导入'
  if (mode === 'hybrid') return '混合模式'
  return '分批录入'
}

function importModeText(mode?: string) {
  if (mode === 'file_stub') return pick('文件导入', 'File import')
  if (mode === 'hybrid') return pick('混合模式', 'Hybrid mode')
  if (mode === 'chunk_manual') return pick('分批录入', 'Batch entry')
  return pick('未标注', 'Not set')
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
      batchLabel.value = `${pick('文件批次', 'File batch')} · ${file.name}`
    }

    const lightweightPreviewTypes = new Set(['txt', 'md', 'markdown', 'json', 'csv', 'log', 'text'])
    if (lightweightPreviewTypes.has(draftFormat.value)) {
      const text = await file.text()
      const normalized = text.replace(/\r\n/g, '\n').trim()
      selectedFileChars.value = normalized.length
      draftContent.value = normalized.slice(0, 4000)
    } else {
      selectedFileChars.value = file.size
      draftContent.value = pick(
        `已选择文件 ${file.name}，将由服务端解析正文并建立素材。`,
        `Selected file ${file.name}. The server will parse the body and create the source.`,
      )
    }
  } catch (e: any) {
    error.value = e?.message || pick('读取文件失败', 'Failed to read the file')
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
  padding: 16px 16px 32px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.style-center-hero,
.style-card {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(200, 210, 220, 0.24);
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 4px 16px rgba(88,110,140,0.06);
}

.style-center-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
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

.style-progress-panel__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.style-progress-panel__cancel {
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: #475569;
  font-size: 0.74rem;
  font-weight: 700;
  padding: 4px 9px;
  transition: all 0.18s ease;
}

.style-progress-panel__cancel:not(:disabled):hover {
  border-color: rgba(225, 29, 72, 0.28);
  color: #be123c;
}

.style-progress-panel__cancel:disabled {
  cursor: not-allowed;
  opacity: 0.55;
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

.style-center-summary-grid\ style-center-summary-grid--compact {
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

.style-center-stack style-center-stack--compact {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
  color: var(--xq-ui-primary, #2563eb);
  background: rgba(239, 246, 255, 0.82);
  border: 1px solid rgba(14, 165, 233, 0.24);
}

.pipeline-grid pipeline-grid--compact {
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

.style-center-grid--compact {
  display: grid;
  gap: 18px;
  align-items: start;
}

.style-center-grid--compact--top {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.9fr);
}

.style-center-grid--compact--bottom {
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
  background: rgba(255,255,255,0.70);
  color: var(--xq-ui-muted, #64748b);
  border: 1px solid var(--xq-ui-border, rgba(148, 163, 184, 0.24));
}

.mode-chip--active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.14), rgba(14, 165, 233, 0.12));
  color: var(--xq-ui-primary, #2563eb);
  border-color: rgba(14, 165, 233, 0.34);
}

.primary-btn {
  background: linear-gradient(135deg, var(--xq-ui-primary, #2563eb), var(--xq-ui-primary-2, #0891b2));
  color: white;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.20);
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.secondary-btn {
  background: rgba(255, 255, 255, 0.76);
  color: var(--xq-ui-primary, #2563eb);
  border: 1px solid var(--xq-ui-border, rgba(148, 163, 184, 0.24));
}

.text-btn {
  background: rgba(255, 255, 255, 0.46);
  color: var(--xq-ui-muted, #64748b);
  border: 1px solid transparent;
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
  .pipeline-grid pipeline-grid--compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .style-center-grid--compact--top,
  .style-center-grid--compact--bottom,
  .style-center-summary-grid\ style-center-summary-grid--compact {
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

/* --- Compact style cards --- */
.style-card {
  padding: 10px 14px !important;
  margin-bottom: 6px !important;
  border-radius: 8px !important;
}
.style-card__header {
  font-size: 12px !important;
  gap: 4px !important;
}
.style-card__body {
  font-size: 11px !important;
}
.style-group-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  padding: 8px 0 4px 0;
  border-bottom: 1px solid rgba(148,163,184,0.12);
  margin-bottom: 6px;
}
.style-center-grid--compact {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}
</style>
