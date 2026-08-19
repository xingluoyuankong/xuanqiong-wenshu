<!-- AIMETA P=蓝图展示_蓝图详细信息|R=蓝图详情展示|NR=不含编辑功能|E=component:BlueprintDisplay|X=internal|A=展示组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <section class="flex min-h-0 flex-col overflow-hidden rounded-[32px] border border-slate-200/80 bg-white/95 shadow-[0_24px_90px_-40px_rgba(15,23,42,0.34)] backdrop-blur-xl">
    <header class="sticky top-0 z-20 shrink-0 border-b border-white/10 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.24),transparent_35%),linear-gradient(135deg,#0f172a_0%,#1e1b4b_55%,#155e75_100%)] px-5 py-5 text-white sm:px-6 lg:px-8">
      <div class="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div class="min-w-0 space-y-3">
          <div class="flex flex-wrap items-center gap-2 text-xs font-medium">
            <span class="rounded-full border border-white/10 bg-white/12 px-3 py-1 text-white">{{ pick('蓝图总览', 'Blueprint overview') }}</span>
            <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">{{ pick('只读预览', 'Read-only preview') }}</span>
            <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">{{ hasChapterOutline ? `${chapterOutline.length} ${pick('章', 'chapters')}` : `${novelOutline.length} ${pick('段总纲', 'outline stages')}` }}</span>
            <span v-if="hasAiMessage" class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">{{ pick('含系统说明', 'Includes system notes') }}</span>
          </div>

          <div class="space-y-3">
            <h2 class="text-xl font-semibold tracking-tight sm:text-3xl">{{ blueprintTitle }}</h2>
            <p class="max-w-3xl text-sm leading-6 text-slate-200 sm:text-base">
              {{ synopsis }}
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <span
              v-for="tag in heroTags"
              :key="tag"
              class="inline-flex items-center rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-medium text-slate-100"
            >
              {{ tag }}
            </span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3 xl:justify-end">
          <div class="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm leading-6 text-slate-100">
            <p class="font-semibold text-white">{{ pick('此处决定下一步推进层级', 'This screen decides what happens next') }}</p>
            <p class="mt-1 text-slate-200">{{ pick('若还只有小说总大纲，会先继续生成章节大纲；只有章节大纲完成后才进入写作台。', 'With only the master outline ready, the next step generates the chapter outline; the writing desk opens after the chapter outline is complete.') }}</p>
          </div>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 hover:bg-white/15"
            @click="confirmRegenerate"
          >
            {{ regenerateActionLabel }}
          </button>
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/20 transition-all hover:-translate-y-0.5 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
            :disabled="props.isSaving || !blueprint"
            @click="confirmBlueprint"
          >
            {{ props.isSaving ? savingActionLabel : (blueprint ? primaryActionLabel : pick('缺少蓝图', 'Blueprint missing')) }}
          </button>
        </div>
      </div>

      <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="item in overviewStats"
          :key="item.label"
          class="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 backdrop-blur"
        >
          <p class="text-xs uppercase tracking-[0.24em] text-slate-300">{{ item.label }}</p>
          <p class="mt-1 text-lg font-semibold text-white">{{ item.value }}</p>
          <p class="mt-1 text-xs leading-5 text-slate-300">{{ item.hint }}</p>
        </div>
      </div>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 lg:px-8">
      <div
        v-if="hasAiMessage"
        class="mb-4 rounded-[24px] border border-indigo-200/80 bg-indigo-50/80 p-5 shadow-[0_12px_40px_-30px_rgba(79,70,229,0.32)]"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">{{ pick('系统说明', 'System notes') }}</p>
            <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ pick('这份说明会一起带到写作台', 'These notes travel with you to the writing desk') }}</h3>
          </div>
          <span class="inline-flex rounded-full border border-indigo-200 bg-white px-3 py-1 text-xs font-medium text-indigo-700">
            {{ pick('可直接阅读', 'Ready to read') }}
          </span>
        </div>
        <div class="blueprint-markdown mt-3 rounded-2xl border border-indigo-100 bg-white px-4 py-4 text-slate-700" v-html="renderedAiMessage"></div>
      </div>

      <div v-if="!blueprint" class="rounded-[28px] border border-rose-200 bg-rose-50 p-8 text-center text-rose-700 shadow-[0_12px_40px_-28px_rgba(244,63,94,0.18)]">
        <p class="text-lg font-semibold">{{ pick('暂时没有可展示的蓝图', 'No blueprint to display yet') }}</p>
        <p class="mt-2 text-sm leading-6">{{ emptyBlueprintHint }}</p>
        <button
          type="button"
          class="mt-5 inline-flex items-center justify-center rounded-2xl bg-rose-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-rose-900/10 transition-all hover:-translate-y-0.5 hover:bg-rose-500"
          @click="confirmRegenerate"
        >
          {{ regenerateActionLabel }}
        </button>
      </div>

      <div v-else class="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,360px)]">
        <main class="space-y-3">
          <section class="rounded-[28px] border border-slate-200/80 bg-slate-50/90 p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">{{ pick('故事摘要', 'Story summary') }}</p>
                <h3 class="mt-2 text-xl font-semibold text-slate-950">{{ pick('开写前先确认这四个维度', 'Confirm these four dimensions before writing') }}</h3>
                <p class="mt-2 text-sm leading-6 text-slate-600">
                  {{ pick('这是后续写作时最先参考的骨架。确认无误后，内容会直接进入写作台。', 'This is the first skeleton later writing refers to. Once confirmed, the content goes straight to the writing desk.') }}
                </p>
              </div>
              <span class="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
                {{ pick('只读预览', 'Read-only preview') }}
              </span>
            </div>

            <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <article
                v-for="field in overviewFields"
                :key="field.label"
                class="rounded-2xl border border-white/80 bg-white px-4 py-4 shadow-sm"
              >
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{{ field.label }}</p>
                <p class="mt-2 text-sm font-semibold text-slate-950">{{ field.value }}</p>
              </article>
            </div>

            <div class="mt-3 rounded-2xl border border-white/80 bg-white p-4">
              <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{{ pick('完整梗概', 'Full synopsis') }}</p>
              <p class="mt-3 whitespace-pre-line text-sm leading-7 text-slate-700">
                {{ fullSynopsis }}
              </p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">{{ pick('世界观', 'World setting') }}</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ pick('规则、地标和势力', 'Rules, landmarks, and factions') }}</h3>
              </div>
              <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
                {{ worldLocations.length }} {{ pick('个地点', 'locations') }} / {{ worldFactions.length }} {{ pick('个势力', 'factions') }}
              </span>
            </div>

            <div class="mt-3 rounded-2xl border border-sky-200/70 bg-sky-50 p-4">
              <p class="text-xs font-medium uppercase tracking-[0.24em] text-sky-600">{{ pick('核心规则', 'Core rules') }}</p>
              <p class="mt-2 whitespace-pre-line text-sm leading-7 text-sky-900">
                {{ worldCoreRules }}
              </p>
            </div>

            <div v-if="worldSystemCards.length" class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <article
                v-for="card in worldSystemCards"
                :key="card.label"
                class="rounded-2xl border border-emerald-200/70 bg-emerald-50/70 px-4 py-4"
              >
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-emerald-700">{{ card.label }}</p>
                <p class="mt-2 whitespace-pre-line text-sm leading-6 text-emerald-950">{{ card.value }}</p>
              </article>
            </div>

            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{{ pick('关键地点', 'Key locations') }}</p>
                  <span class="text-xs font-medium text-slate-500">{{ worldLocations.length }}</span>
                </div>
                <div class="mt-3 space-y-3">
                  <article
                    v-for="location in worldLocations"
                    :key="location.name"
                    class="rounded-xl border border-slate-200 bg-white px-3 py-3"
                  >
                    <p class="text-sm font-semibold text-slate-900">{{ location.name }}</p>
                    <p class="mt-1 text-sm leading-6 text-slate-600">{{ location.description }}</p>
                  </article>
                  <p v-if="!worldLocations.length" class="text-sm text-slate-500">{{ pick('暂无地点信息。', 'No location details yet.') }}</p>
                </div>
              </div>

              <div class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{{ pick('主要势力', 'Major factions') }}</p>
                  <span class="text-xs font-medium text-slate-500">{{ worldFactions.length }}</span>
                </div>
                <div class="mt-3 space-y-3">
                  <article
                    v-for="faction in worldFactions"
                    :key="faction.name"
                    class="rounded-xl border border-slate-200 bg-white px-3 py-3"
                  >
                    <p class="text-sm font-semibold text-slate-900">{{ faction.name }}</p>
                    <p class="mt-1 text-sm leading-6 text-slate-600">{{ faction.description }}</p>
                  </article>
                  <p v-if="!worldFactions.length" class="text-sm text-slate-500">{{ pick('暂无势力信息。', 'No faction details yet.') }}</p>
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">{{ pick('小说总大纲', 'Master outline') }}</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ pick('按阶段展开的全书推进路线', 'The whole-book route laid out stage by stage') }}</h3>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
                  {{ novelOutline.length }} {{ pick('段', 'stages') }}
                </span>
                <button
                  v-if="hasNovelOutline"
                  type="button"
                  class="inline-flex items-center justify-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 transition hover:border-indigo-300 hover:bg-indigo-100"
                  @click="confirmRegenerate"
                >
                  {{ pick('重新生成小说总大纲', 'Regenerate master outline') }}
                </button>
              </div>
            </div>

            <div class="mt-3 space-y-3">
              <article
                v-for="stage in novelOutline"
                :key="stage.stage"
                class="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4"
              >
                <div class="flex items-start gap-3">
                  <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-900 text-sm font-semibold text-white">
                    {{ stage.stage }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <h4 class="text-base font-semibold text-slate-950">{{ stage.title }}</h4>
                      <span class="rounded-full bg-white px-2 py-1 text-xs font-medium text-slate-500">
                        {{ pick(`第 ${stage.stage} 阶段`, `Stage ${stage.stage}`) }}
                      </span>
                      <span class="rounded-full bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">
                        {{ stage.expectedChapterRange }}
                      </span>
                    </div>
                    <p class="mt-2 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">{{ pick('阶段主题：', 'Stage theme: ') }}</span>{{ stage.coreTheme }}</p>
                    <p class="mt-2 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">{{ pick('阶段目标：', 'Stage goal: ') }}</span>{{ stage.goal }}</p>
                    <p class="mt-2 text-sm leading-6 text-slate-600"><span class="font-semibold text-slate-900">{{ pick('核心冲突：', 'Core conflict: ') }}</span>{{ stage.mainConflict }}</p>
                    <div class="mt-3 grid gap-3 md:grid-cols-2">
                      <p class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">{{ pick('阶段背景：', 'Stage background: ') }}</span>{{ stage.background }}</p>
                      <p class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">{{ pick('人物推进：', 'Character progression: ') }}</span>{{ stage.characterProgression }}</p>
                      <p class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">{{ pick('世界推进：', 'World progression: ') }}</span>{{ stage.worldProgression }}</p>
                      <p class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700"><span class="font-semibold text-slate-900">{{ pick('势力变化：', 'Faction shifts: ') }}</span>{{ stage.factionProgression }}</p>
                      <p class="rounded-xl bg-white px-3 py-3 text-sm leading-6 text-slate-700 md:col-span-2"><span class="font-semibold text-slate-900">{{ pick('体系推进：', 'System progression: ') }}</span>{{ stage.powerProgression }}</p>
                    </div>
                    <div class="mt-3 grid gap-3 md:grid-cols-2" v-if="stage.survivalAndLifeProgression || stage.culturalAndCivilizationalProgression || stage.resourceAndOperationLine || stage.emotionalCore || stage.majorSetpiece || stage.storyFunction">
                      <p v-if="stage.survivalAndLifeProgression" class="rounded-xl bg-cyan-50 px-3 py-3 text-sm leading-6 text-cyan-900"><span class="font-semibold">{{ pick('生存/生活推进：', 'Survival/life progression: ') }}</span>{{ stage.survivalAndLifeProgression }}</p>
                      <p v-if="stage.culturalAndCivilizationalProgression" class="rounded-xl bg-violet-50 px-3 py-3 text-sm leading-6 text-violet-900"><span class="font-semibold">{{ pick('文化/文明推进：', 'Culture/civilization progression: ') }}</span>{{ stage.culturalAndCivilizationalProgression }}</p>
                      <p v-if="stage.resourceAndOperationLine" class="rounded-xl bg-emerald-50 px-3 py-3 text-sm leading-6 text-emerald-900"><span class="font-semibold">{{ pick('资源/运营线：', 'Resource/operations line: ') }}</span>{{ stage.resourceAndOperationLine }}</p>
                      <p v-if="stage.emotionalCore" class="rounded-xl bg-rose-50 px-3 py-3 text-sm leading-6 text-rose-900"><span class="font-semibold">{{ pick('情绪核心：', 'Emotional core: ') }}</span>{{ stage.emotionalCore }}</p>
                      <p v-if="stage.majorSetpiece" class="rounded-xl bg-amber-50 px-3 py-3 text-sm leading-6 text-amber-950"><span class="font-semibold">{{ pick('场面支点：', 'Setpiece anchor: ') }}</span>{{ stage.majorSetpiece }}</p>
                      <p v-if="stage.storyFunction" class="rounded-xl bg-slate-100 px-3 py-3 text-sm leading-6 text-slate-800 md:col-span-2"><span class="font-semibold">{{ pick('阶段职责：', 'Stage function: ') }}</span>{{ stage.storyFunction }}</p>
                    </div>
                    <div class="mt-3 rounded-xl bg-slate-50 px-3 py-3">
                      <p class="text-sm font-semibold text-slate-900">{{ pick('关键事件', 'Key events') }}</p>
                      <ul v-if="stage.keyEvents.length" class="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-600">
                        <li v-for="event in stage.keyEvents" :key="`${stage.stage}-${event}`">{{ event }}</li>
                      </ul>
                    </div>
                    <div v-if="stage.turningPoints.length || stage.stageTasks.length" class="mt-3 grid gap-3 md:grid-cols-2">
                      <div v-if="stage.turningPoints.length" class="rounded-xl bg-indigo-50 px-3 py-3">
                        <p class="text-sm font-semibold text-indigo-900">{{ pick('转折节点', 'Turning points') }}</p>
                        <ul class="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-indigo-800">
                          <li v-for="point in stage.turningPoints" :key="`${stage.stage}-${point}`">{{ point }}</li>
                        </ul>
                      </div>
                      <div v-if="stage.stageTasks.length" class="rounded-xl bg-teal-50 px-3 py-3">
                        <p class="text-sm font-semibold text-teal-900">{{ pick('阶段任务', 'Stage tasks') }}</p>
                        <ul class="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-teal-800">
                          <li v-for="task in stage.stageTasks" :key="`${stage.stage}-${task}`">{{ task }}</li>
                        </ul>
                      </div>
                    </div>
                    <p class="mt-3 rounded-xl bg-amber-50 px-3 py-3 text-sm leading-6 text-amber-900"><span class="font-semibold">{{ pick('阶段高潮：', 'Stage climax: ') }}</span>{{ stage.stageClimax }}</p>
                    <p class="mt-3 rounded-xl bg-emerald-50 px-3 py-3 text-sm leading-6 text-emerald-800"><span class="font-semibold">{{ pick('伏笔与回收：', 'Foreshadowing and payoff: ') }}</span>{{ stage.foreshadowingAndPayoff }}</p>
                    <p v-if="stage.endingHook" class="mt-3 rounded-xl bg-white px-3 py-2 text-sm leading-6 text-indigo-700">
                      <span class="font-semibold">{{ pick('阶段钩子：', 'Stage hook: ') }}</span>{{ stage.endingHook }}
                    </p>
                  </div>
                </div>
              </article>
              <p v-if="!novelOutline.length" class="text-sm text-slate-500">{{ pick('暂无小说总大纲。', 'No master outline yet.') }}</p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">{{ pick('章节总览', 'Chapter overview') }}</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ pick('按章节展开的写作路线', 'The writing route laid out chapter by chapter') }}</h3>
              </div>
              <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-500">
                {{ chapterOutline.length }} {{ pick('章', 'chapters') }}
              </span>
            </div>

            <div class="mt-3 space-y-3">
              <article
                v-for="chapter in chapterOutline"
                :key="chapter.number"
                class="group rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4 transition-all hover:-translate-y-0.5 hover:border-indigo-200 hover:bg-indigo-50/60"
              >
                <div class="flex items-start gap-3">
                  <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-900 text-sm font-semibold text-white">
                    {{ chapter.number }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap items-center gap-2">
                      <h4 class="text-base font-semibold text-slate-950">{{ chapter.title }}</h4>
                      <span class="rounded-full bg-white px-2 py-1 text-xs font-medium text-slate-500">
                        {{ pick(`第 ${chapter.number} 章`, `Chapter ${chapter.number}`) }}
                      </span>
                    </div>
                    <p class="mt-2 text-sm leading-6 text-slate-600">{{ chapter.summary }}</p>
                  </div>
                </div>
              </article>
              <p v-if="!chapterOutline.length" class="text-sm text-slate-500">{{ pick('当前还没有章节大纲，先确认上面的小说总大纲，再继续细化。', 'No chapter outline yet. Confirm the master outline above, then keep refining.') }}</p>
            </div>
          </section>
        </main>

        <aside class="space-y-3 xl:sticky xl:top-6 self-start">
          <section class="rounded-[28px] border border-slate-200/80 bg-slate-950 p-5 text-white shadow-[0_16px_48px_-30px_rgba(15,23,42,0.55)]">
            <p class="text-xs uppercase tracking-[0.28em] text-slate-400">{{ pick('角色速览', 'Character quick view') }}</p>
            <h3 class="mt-2 text-lg font-semibold">{{ pick('一眼扫完人物表', 'Scan the character list at a glance') }}</h3>
            <div class="mt-3 max-h-[34rem] space-y-3 overflow-y-auto pr-1">
              <article
                v-for="character in characterCards"
                :key="character.name"
                class="rounded-2xl border border-white/10 bg-white/5 px-4 py-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-sm font-semibold text-white">{{ character.name }}</p>
                  <span v-if="character.role" class="rounded-full bg-white/10 px-2 py-1 text-[11px] font-medium text-slate-200">
                    {{ character.role }}
                  </span>
                  <span class="rounded-full bg-cyan-400/10 px-2 py-1 text-[11px] font-medium text-cyan-100">
                    {{ character.importance }}
                  </span>
                </div>
                <p v-if="character.summary" class="mt-2 text-sm leading-6 text-slate-300">
                  {{ character.summary }}
                </p>
                <p v-if="character.spotlight" class="mt-2 rounded-xl bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-100">
                  {{ character.spotlight }}
                </p>
                <div v-if="character.details.length" class="mt-3 space-y-2">
                  <div
                    v-for="detail in character.details"
                    :key="`${character.name}-${detail.label}`"
                    class="rounded-xl bg-white/5 px-3 py-2 text-sm leading-6 text-slate-300"
                  >
                    <span class="font-medium text-white">{{ detail.label }}{{ punct.colon }}</span>{{ detail.value }}
                  </div>
                </div>
              </article>
              <p v-if="!characterCards.length" class="text-sm text-slate-300">{{ pick('暂无角色信息。', 'No character details yet.') }}</p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{{ pick('关系网', 'Relationship map') }}</p>
            <div class="mt-3 space-y-3">
              <article
                v-for="relationship in relationshipCards"
                :key="`${relationship.from}-${relationship.to}`"
                class="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded-full bg-white px-3 py-1 text-sm font-semibold text-rose-700">{{ relationship.from }}</span>
                  <span class="text-rose-400">→</span>
                  <span class="rounded-full bg-white px-3 py-1 text-sm font-semibold text-rose-700">{{ relationship.to }}</span>
                  <span class="rounded-full border border-rose-200 bg-white px-3 py-1 text-xs font-semibold text-rose-600">
                    {{ relationship.relationType }}
                  </span>
                </div>
                <p class="mt-3 text-sm leading-6 text-rose-700">{{ relationship.description }}</p>
                <div class="mt-3 grid gap-2">
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">{{ pick('当前状态：', 'Current state: ') }}</span>{{ relationship.currentState }}
                  </div>
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">{{ pick('核心张力：', 'Core tension: ') }}</span>{{ relationship.tension }}
                  </div>
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">{{ pick('预期变化：', 'Expected change: ') }}</span>{{ relationship.expectedChange }}
                  </div>
                  <div class="rounded-xl bg-white px-3 py-2 text-sm leading-6 text-rose-700">
                    <span class="font-semibold">{{ pick('关键触发：', 'Key trigger: ') }}</span>{{ relationship.keyTrigger }}
                  </div>
                </div>
              </article>
              <p v-if="!relationshipCards.length" class="text-sm text-slate-500">{{ pick('暂无关键信息。', 'No key details yet.') }}</p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-gradient-to-br from-indigo-50 via-white to-emerald-50 p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">{{ pick('进入写作前', 'Before you start writing') }}</p>
            <p class="mt-2 text-sm leading-6 text-slate-700">
              {{ pick('右上角主按钮已经是唯一确认入口，这里只保留说明，避免同一屏出现重复主 CTA。', 'The top-right button is the only confirmation entry; this block keeps the explanation so one screen never shows duplicate primary CTAs.') }}
            </p>
            <div class="mt-3 space-y-3 text-sm leading-6 text-slate-600">
              <div class="rounded-2xl border border-white/80 bg-white/80 px-4 py-3">
                <p class="font-semibold text-slate-900">{{ hasCompleteChapterOutline ? pick('确认蓝图并进入开写', 'Confirm blueprint and start writing') : pick('基于小说总大纲生成章节大纲', 'Generate chapter outline from master outline') }}</p>
                <p class="mt-1">{{ hasCompleteChapterOutline ? pick('会把当前蓝图保留在项目中，并直接切到小说详情工作台。', 'Keeps the current blueprint in the project and switches straight to the novel detail workspace.') : pick('会继续调用软件的正式生成链，把全书总纲细化成可执行章节大纲。', 'Keeps using the official generation chain to refine the whole-book master outline into an executable chapter outline.') }}</p>
              </div>
              <div class="rounded-2xl border border-white/80 bg-white/80 px-4 py-3">
                <p class="font-semibold text-slate-900">{{ regenerateActionLabel }}</p>
                <p class="mt-1">{{ pick('用于方向不满意时重新生成；如果当前已经有小说总大纲，这里会直接走总纲重生成流程。', 'Use it when the direction is off; if a master outline already exists, this runs the master outline regeneration flow.') }}</p>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { globalAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'
import type { Blueprint } from '@/api/novel'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'

interface Props {
  blueprint: Blueprint | null
  aiMessage?: string
  isSaving?: boolean
}

interface DetailItem {
  label: string
  value: string
}

interface CharacterCard {
  name: string
  role: string
  importance: string
  summary: string
  spotlight: string
  details: DetailItem[]
}

interface RelationshipCard {
  from: string
  to: string
  description: string
  relationType: string
  currentState: string
  tension: string
  expectedChange: string
  keyTrigger: string
}

interface WorldItem {
  name: string
  description: string
}

interface SystemCard {
  label: string
  value: string
}

interface ChapterItem {
  number: number
  title: string
  summary: string
}

interface NovelOutlineStage {
  stage: number
  title: string
  coreTheme: string
  goal: string
  mainConflict: string
  background: string
  characterProgression: string
  worldProgression: string
  factionProgression: string
  powerProgression: string
  survivalAndLifeProgression: string
  culturalAndCivilizationalProgression: string
  resourceAndOperationLine: string
  emotionalCore: string
  majorSetpiece: string
  storyFunction: string
  turningPoints: string[]
  stageTasks: string[]
  keyEvents: string[]
  stageClimax: string
  foreshadowingAndPayoff: string
  endingHook: string
  expectedChapterRange: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  confirm: []
  regenerate: []
}>()

const { pick, punct } = useLocale()

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const readPositiveInt = (value: unknown): number | null => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null
}

const optionalText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  return ''
}

// 默认兜底文案在每次调用时求值，因此始终跟随当前语言。
const displayText = (value: unknown, fallback = pick('待补充', 'To be added')): string => {
  return optionalText(value) || fallback
}

const maybeText = (value: unknown): string => optionalText(value)

const formatStructuredValue = (value: unknown): string => {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value
      .map((item) => formatStructuredValue(item))
      .filter(Boolean)
      .join('；')
  }
  if (isRecord(value)) {
    return Object.entries(value)
      .map(([key, nested]) => {
        const nestedText = formatStructuredValue(nested)
        return nestedText ? `${key}：${nestedText}` : ''
      })
      .filter(Boolean)
      .join('\n')
  }
  return ''
}

// 这里比对的是后端下发的 importance 原始取值（数据，不是界面文案），因此不走 pick。
const importanceWeight = (value: string): number => {
  const normalized = value.trim().toLowerCase()
  if (['主角', 'protagonist', 'main'].includes(normalized)) return 0
  if (['核心', 'core', 'major'].includes(normalized)) return 1
  if (['配角', 'supporting', 'support'].includes(normalized)) return 2
  if (['次要', 'minor'].includes(normalized)) return 3
  return 4
}

const toRecordArray = (value: unknown): Record<string, unknown>[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter(isRecord)
}

const blueprintTitle = computed(() => displayText(props.blueprint?.title, pick('未命名蓝图', 'Untitled blueprint')))
const synopsis = computed(() => displayText(props.blueprint?.one_sentence_summary, pick('暂无一句话梗概', 'No one-sentence summary yet')))
const fullSynopsis = computed(() => displayText(props.blueprint?.full_synopsis, pick('暂无完整梗概', 'No full synopsis yet')))

const heroTags = computed(() => {
  const tags = [
    displayText(props.blueprint?.genre, ''),
    displayText(props.blueprint?.style, ''),
    displayText(props.blueprint?.tone, ''),
    displayText(props.blueprint?.target_audience, ''),
  ].filter(Boolean)

  return tags.length ? tags : [pick('暂无标签', 'No tags yet')]
})

const overviewFields = computed(() => [
  { label: pick('题材', 'Genre'), value: displayText(props.blueprint?.genre, pick('未填写', 'Not filled in')) },
  { label: pick('风格', 'Style'), value: displayText(props.blueprint?.style, pick('未填写', 'Not filled in')) },
  { label: pick('语气', 'Tone'), value: displayText(props.blueprint?.tone, pick('未填写', 'Not filled in')) },
  { label: pick('受众', 'Audience'), value: displayText(props.blueprint?.target_audience, pick('未填写', 'Not filled in')) },
])

const worldSetting = computed<Record<string, unknown> | null>(() => {
  return isRecord(props.blueprint?.world_setting) ? props.blueprint!.world_setting : null
})

const worldCoreRules = computed(() => {
  return displayText(worldSetting.value?.core_rules, pick('暂无世界观核心规则', 'No core world setting rules yet'))
})

const worldLocations = computed<WorldItem[]>(() => {
  return toRecordArray(worldSetting.value?.key_locations).map((item, index) => ({
    name: displayText(item.name, pick(`地点 ${index + 1}`, `Location ${index + 1}`)),
    description: displayText(item.description, pick('暂无说明', 'No description yet')),
  }))
})

const worldFactions = computed<WorldItem[]>(() => {
  return toRecordArray(worldSetting.value?.factions).map((item, index) => ({
    name: displayText(item.name, pick(`势力 ${index + 1}`, `Faction ${index + 1}`)),
    description: displayText(item.description, pick('暂无说明', 'No description yet')),
  }))
})

const worldSystemCards = computed<SystemCard[]>(() => {
  // 元组左侧是后端字段名（不可译），右侧才是界面标签。
  const fields = [
    ['era_background', pick('时代背景', 'Era background')],
    ['world_structure', pick('世界结构', 'World structure')],
    ['power_system', pick('力量体系', 'Power system')],
    ['survival_system', pick('生存体系', 'Survival system')],
    ['life_system', pick('生活体系', 'Life system')],
    ['culture_system', pick('文化体系', 'Culture system')],
    ['civilization_system', pick('文明体系', 'Civilization system')],
    ['economy_system', pick('经济体系', 'Economy system')],
    ['social_structure', pick('社会结构', 'Social structure')],
    ['resource_system', pick('资源体系', 'Resource system')],
    ['belief_system', pick('信仰体系', 'Belief system')],
    ['geography_system', pick('地理体系', 'Geography system')],
    ['faction_order', pick('势力秩序', 'Faction order')],
  ] as const

  return fields
    .map(([key, label]) => ({
      label,
      value: formatStructuredValue(worldSetting.value?.[key]),
    }))
    .filter((item) => item.value)
})

const novelOutline = computed<NovelOutlineStage[]>(() => {
  const outline = Array.isArray(props.blueprint?.novel_outline) ? props.blueprint!.novel_outline : []

  return outline
    .map((item, index) => {
      const record = isRecord(item) ? item : {}
      const keyEvents = Array.isArray(record.key_events)
        ? record.key_events.map((event) => displayText(event, '')).filter(Boolean)
        : []
      const turningPoints = Array.isArray(record.turning_points)
        ? record.turning_points.map((item) => displayText(item, '')).filter(Boolean)
        : []
      const stageTasks = Array.isArray(record.stage_tasks)
        ? record.stage_tasks.map((item) => displayText(item, '')).filter(Boolean)
        : []
      return {
        stage: Number(record.stage) || index + 1,
        title: displayText(record.title, pick(`阶段 ${index + 1}`, `Stage ${index + 1}`)),
        coreTheme: displayText(record.core_theme, pick('暂无阶段主题', 'No stage theme yet')),
        goal: displayText(record.goal, pick('暂无阶段目标', 'No stage goal yet')),
        mainConflict: displayText(record.main_conflict, pick('暂无核心冲突', 'No core conflict yet')),
        background: displayText(record.background, pick('暂无阶段背景', 'No stage background yet')),
        characterProgression: displayText(record.character_progression, pick('暂无人物推进', 'No character progression yet')),
        worldProgression: displayText(record.world_progression, pick('暂无世界推进', 'No world progression yet')),
        factionProgression: displayText(record.faction_progression, pick('暂无势力变化', 'No faction shifts yet')),
        powerProgression: displayText(record.power_progression, pick('暂无体系推进', 'No system progression yet')),
        survivalAndLifeProgression: maybeText(record.survival_and_life_progression),
        culturalAndCivilizationalProgression: maybeText(record.cultural_and_civilizational_progression),
        resourceAndOperationLine: maybeText(record.resource_and_operation_line),
        emotionalCore: maybeText(record.emotional_core),
        majorSetpiece: maybeText(record.major_setpiece),
        storyFunction: maybeText(record.story_function),
        turningPoints,
        stageTasks,
        keyEvents,
        stageClimax: displayText(record.stage_climax, pick('暂无阶段高潮', 'No stage climax yet')),
        foreshadowingAndPayoff: displayText(record.foreshadowing_and_payoff, pick('暂无伏笔信息', 'No foreshadowing details yet')),
        endingHook: displayText(record.ending_hook, ''),
        expectedChapterRange: displayText(record.expected_chapter_range, pick('章节范围待定', 'Chapter range to be decided')),
      }
    })
    .sort((left, right) => left.stage - right.stage)
})

const chapterOutline = computed<ChapterItem[]>(() => {
  const outline = Array.isArray(props.blueprint?.chapter_outline) ? props.blueprint!.chapter_outline : []

  return outline.map((chapter, index) => ({
    number: Number((chapter as { chapter_number?: unknown }).chapter_number) || index + 1,
    title: displayText((chapter as { title?: unknown }).title, pick(`第 ${index + 1} 章`, `Chapter ${index + 1}`)),
    summary: displayText((chapter as { summary?: unknown }).summary, pick('暂无章节摘要', 'No chapter summary yet')),
  }))
})

const chapterOutlineExpectedCount = computed(() => {
  if (!props.blueprint) return 0
  const root = props.blueprint as Record<string, unknown>
  const world = isRecord(props.blueprint.world_setting) ? props.blueprint.world_setting : {}
  const systemBlueprint = isRecord(world.system_blueprint) ? world.system_blueprint : {}
  const candidates = [
    isRecord(root.length_contract) ? root.length_contract : null,
    isRecord(world.length_contract) ? world.length_contract : null,
    isRecord(systemBlueprint.length_contract) ? systemBlueprint.length_contract : null,
  ].filter(isRecord)

  for (const candidate of candidates) {
    const seedCount = readPositiveInt(candidate.chapter_outline_seed_count)
    const targetCount = readPositiveInt(candidate.target_chapter_count)
    if (seedCount && targetCount) return Math.min(seedCount, targetCount)
    if (seedCount) return seedCount
    if (targetCount && targetCount <= 60) return targetCount
  }

  const inferredTotal = novelOutline.value.reduce((maxChapter, stage) => {
    const numbers = Array.from(stage.expectedChapterRange.matchAll(/\d+/g)).map((match) => Number(match[0]))
    const stageMax = numbers.length ? Math.max(...numbers.filter((item) => Number.isFinite(item))) : 0
    return Math.max(maxChapter, stageMax)
  }, 0)
  if (inferredTotal > 0) {
    if (inferredTotal <= 60) return inferredTotal
    if (inferredTotal <= 120) return 60
    if (inferredTotal <= 300) return 80
    if (inferredTotal <= 600) return 100
    return 120
  }

  return chapterOutline.value.length
})

const hasNovelOutline = computed(() => novelOutline.value.length > 0)
const hasCompleteChapterOutline = computed(() => {
  const expectedCount = chapterOutlineExpectedCount.value
  if (expectedCount <= 0 || chapterOutline.value.length < expectedCount) return false
  const sortedNumbers = chapterOutline.value.map((chapter) => chapter.number).sort((left, right) => left - right)
  return sortedNumbers.slice(0, expectedCount).every((chapterNumber, index) => chapterNumber === index + 1)
})
const hasChapterOutline = computed(() => chapterOutline.value.length > 0)
const primaryActionLabel = computed(() => {
  if (!props.blueprint) return pick('缺少蓝图', 'Blueprint missing')
  if (!hasCompleteChapterOutline.value && hasNovelOutline.value) return pick('基于小说总大纲生成章节大纲', 'Generate chapter outline from master outline')
  return pick('确认蓝图并进入开写', 'Confirm blueprint and start writing')
})
const savingActionLabel = computed(() => {
  if (!hasCompleteChapterOutline.value && hasNovelOutline.value) return pick('正在生成章节大纲...', 'Generating chapter outline...')
  return pick('正在进入写作台...', 'Opening the writing desk...')
})
const regenerateActionLabel = computed(() => {
  if (hasNovelOutline.value) return pick('重新生成小说总大纲', 'Regenerate master outline')
  return pick('重新生成蓝图', 'Regenerate blueprint')
})
// 空态提示需要把按钮名嵌在句子中间，整句一起 pick 才能保证两种语言的语序都自然。
const emptyBlueprintHint = computed(() =>
  pick(
    `先返回上一页重新生成，或者直接点“${regenerateActionLabel.value}”再来一版。`,
    `Go back to the previous page and regenerate, or click “${regenerateActionLabel.value}” for another version.`,
  ),
)

const characterCards = computed<CharacterCard[]>(() => {
  const characters: unknown[] = Array.isArray(props.blueprint?.characters)
    ? (props.blueprint!.characters as unknown[])
    : []

  return characters.map((item, index) => {
    if (typeof item === 'string') {
      return {
        name: item.trim() || pick(`角色 ${index + 1}`, `Character ${index + 1}`),
        role: pick('角色', 'Character'),
        importance: pick('待补充', 'To be added'),
        summary: '',
        spotlight: '',
        details: [],
      }
    }

    if (!isRecord(item)) {
      return {
        name: pick(`角色 ${index + 1}`, `Character ${index + 1}`),
        role: pick('角色', 'Character'),
        importance: pick('待补充', 'To be added'),
        summary: '',
        spotlight: '',
        details: [],
      }
    }

    const nestedDescription = isRecord(item.description) ? item.description : null
    const summary =
      optionalText(item.summary) ||
      optionalText(item.description) ||
      optionalText(nestedDescription?.summary) ||
      optionalText(nestedDescription?.description) ||
      ''

    const details: DetailItem[] = [
      { label: pick('身份', 'Identity'), value: optionalText(item.identity) || optionalText(nestedDescription?.identity) },
      { label: pick('定位', 'Positioning'), value: optionalText(item.archetype) || optionalText(item.position) || optionalText(item.kind) },
      { label: pick('性格', 'Personality'), value: optionalText(item.personality) || optionalText(nestedDescription?.personality) },
      { label: pick('目标', 'Goal'), value: optionalText(item.goals) || optionalText(item.goal) || optionalText(nestedDescription?.goal) },
      { label: pick('动机', 'Motivation'), value: optionalText(item.core_motivation) || optionalText(item.motivation) },
      { label: pick('恐惧/缺口', 'Fear/gap'), value: optionalText(item.fear_or_wound) || optionalText(item.flaw) || optionalText(item.weakness) },
      { label: pick('外在目标', 'External goal'), value: optionalText(item.external_goal) },
      { label: pick('隐藏信息', 'Hidden information'), value: optionalText(item.hidden_secret) || optionalText(item.secret) },
      { label: pick('成长弧', 'Growth arc'), value: optionalText(item.growth_arc) || optionalText(item.arc) },
      { label: pick('关系钩子', 'Relationship hook'), value: optionalText(item.relationship_hook) },
      { label: pick('能力', 'Abilities'), value: optionalText(item.abilities) || optionalText(item.skills) || optionalText(nestedDescription?.abilities) },
      {
        label: pick('关系', 'Relationship'),
        value:
          optionalText(item.relationship_to_protagonist) ||
          optionalText(item.relationship) ||
          optionalText(nestedDescription?.relationship_to_protagonist),
      },
    ].filter((detail) => detail.value)

    return {
      name: displayText(item.name, pick(`角色 ${index + 1}`, `Character ${index + 1}`)),
      role: optionalText(item.role) || optionalText(item.character_role) || pick('角色', 'Character'),
      importance: optionalText(item.importance) || optionalText(item.priority) || pick('待补充', 'To be added'),
      summary,
      spotlight: maybeText(item.first_highlight_chapter)
        ? pick(
            `首次高光：第 ${maybeText(item.first_highlight_chapter)} 章`,
            `First spotlight: Chapter ${maybeText(item.first_highlight_chapter)}`,
          )
        : '',
      details,
    }
  }).sort((left, right) => {
    const weightDiff = importanceWeight(left.importance) - importanceWeight(right.importance)
    if (weightDiff !== 0) return weightDiff
    return left.name.localeCompare(right.name, 'zh-Hans-CN')
  })
})

const relationshipCards = computed<RelationshipCard[]>(() => {
  const relationships: unknown[] = Array.isArray(props.blueprint?.relationships)
    ? (props.blueprint!.relationships as unknown[])
    : []

  return relationships.map((item, index) => {
    if (!isRecord(item)) {
      return {
        from: pick(`关系 ${index + 1}`, `Relationship ${index + 1}`),
        to: pick('待补充', 'To be added'),
        description: pick('暂无关键信息', 'No key details yet'),
        relationType: pick('关系未定', 'Relationship undecided'),
        currentState: pick('现状待补充', 'Current state to be added'),
        tension: pick('张力待补充', 'Tension to be added'),
        expectedChange: pick('变化待补充', 'Change to be added'),
        keyTrigger: pick('触发事件待补充', 'Trigger event to be added'),
      }
    }

    return {
      from: displayText(item.character_from || item.source || item.from, pick(`角色 ${index + 1}`, `Character ${index + 1}`)),
      to: displayText(item.character_to || item.target || item.to, pick('待补充', 'To be added')),
      description: displayText(item.description || item.summary, pick('暂无关键信息', 'No key details yet')),
      relationType: displayText(item.relation_type || item.relationship_type || item.type, pick('关系未定', 'Relationship undecided')),
      currentState: displayText(item.current_state || item.status, pick('现状待补充', 'Current state to be added')),
      tension: displayText(item.tension || item.core_conflict, pick('张力待补充', 'Tension to be added')),
      expectedChange: displayText(item.expected_change || item.direction, pick('变化待补充', 'Change to be added')),
      keyTrigger: displayText(item.key_trigger || item.trigger, pick('触发事件待补充', 'Trigger event to be added')),
    }
  })
})

const overviewStats = computed(() => [
  {
    label: hasChapterOutline.value ? pick('章节数', 'Chapter count') : pick('总纲段数', 'Master outline stages'),
    value: String(hasChapterOutline.value ? chapterOutline.value.length : novelOutline.value.length),
    hint: hasChapterOutline.value && chapterOutlineExpectedCount.value
      ? pick(
          `首批目标 ${chapterOutlineExpectedCount.value} 章，后续可继续批量扩展`,
          `First batch targets ${chapterOutlineExpectedCount.value} chapters, and you can keep expanding in batches`,
        )
      : pick('下一步将基于这些阶段拆成章节', 'The next step splits these stages into chapters'),
  },
  {
    label: pick('角色数', 'Character count'),
    value: String(characterCards.value.length),
    hint: pick('核心角色卡会直接进入写作参考区', 'Core character cards go straight to the writing reference area'),
  },
  {
    label: pick('当前阶段', 'Current stage'),
    value: hasCompleteChapterOutline.value
      ? (props.isSaving ? pick('进入写作台', 'Opening writing desk') : pick('蓝图定稿', 'Blueprint finalized'))
      : (props.isSaving ? pick('生成章节大纲', 'Generating chapter outline') : pick('总纲确认', 'Master outline confirmation')),
    hint: hasCompleteChapterOutline.value
      ? pick('这一屏只负责最后确认或重做', 'This screen only handles the final confirmation or a redo')
      : pick('先确认全书推进，再继续细化到章节', 'Confirm the whole-book progression first, then refine down to chapters'),
  },
  {
    label: pick('世界块', 'World blocks'),
    value: String((worldLocations.value.length > 0 ? 1 : 0) + (worldFactions.value.length > 0 ? 1 : 0) + (worldCoreRules.value ? 1 : 0)),
    hint: pick('可用世界设定块数量', 'Number of available world setting blocks'),
  },
])

const hasAiMessage = computed(() => {
  return optionalText(props.aiMessage).length > 0
})

const renderedAiMessage = ref('')

const renderAiMessage = (raw: string) => {
  if (!raw) {
    renderedAiMessage.value = ''
    return
  }

  renderedAiMessage.value = renderSafeMarkdown(raw)
}

watch(
  () => optionalText(props.aiMessage),
  (value) => {
    renderAiMessage(value)
  },
  { immediate: true }
)

const confirmRegenerate = async () => {
  const confirmed = await globalAlert.showConfirm(
    hasNovelOutline.value
      ? pick(
          '重新生成小说总大纲会覆盖当前总纲及其下游章节大纲，确定继续吗？',
          'Regenerating the master outline overwrites the current master outline and its downstream chapter outline. Continue?',
        )
      : pick('重新生成蓝图会覆盖当前内容，确定继续吗？', 'Regenerating the blueprint overwrites the current content. Continue?'),
    hasNovelOutline.value
      ? pick('重新生成小说总大纲确认', 'Confirm master outline regeneration')
      : pick('重新生成蓝图确认', 'Confirm blueprint regeneration')
  )
  if (confirmed) {
    emit('regenerate')
  }
}

const confirmBlueprint = () => {
  if (props.isSaving || !props.blueprint) return
  emit('confirm')
}
</script>

<style scoped>
.blueprint-markdown :deep(p) {
  margin: 0 0 0.85rem;
  line-height: 1.85;
}

.blueprint-markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.blueprint-markdown :deep(h3),
.blueprint-markdown :deep(h4) {
  margin: 1rem 0 0.5rem;
  color: rgb(15 23 42);
  font-weight: 700;
}

.blueprint-markdown :deep(ul),
.blueprint-markdown :deep(ol) {
  margin: 0.85rem 0 0.85rem 1.25rem;
  padding: 0;
}

.blueprint-markdown :deep(li) {
  margin: 0.35rem 0;
  line-height: 1.75;
}

.blueprint-markdown :deep(blockquote) {
  margin: 1rem 0;
  border-left: 3px solid rgb(165 180 252);
  padding-left: 1rem;
  color: rgb(51 65 85);
}

.blueprint-markdown :deep(strong) {
  color: rgb(15 23 42);
  font-weight: 700;
}

.blueprint-markdown :deep(a) {
  color: rgb(79 70 229);
  text-decoration: none;
}

.blueprint-markdown :deep(a:hover) {
  text-decoration: underline;
}
</style>
