<template>
  <section class="quality-trend-panel" aria-live="polite">
    <button
      type="button"
      class="quality-trend-panel__toggle"
      data-testid="quality-trend-toggle"
      :aria-expanded="expanded"
      aria-controls="quality-trend-details"
      @click="expanded = !expanded"
    >
      <span>{{ pick('质量趋势', 'Quality trend') }}</span>
      <span class="quality-trend-panel__summary">{{ summaryText }}</span>
      <span aria-hidden="true">{{ expanded ? '▾' : '▸' }}</span>
    </button>
    <div
      v-if="expanded"
      id="quality-trend-details"
      class="quality-trend-panel__details"
      data-testid="quality-trend-details"
    >
      <p v-if="loading" class="quality-trend-panel__message">
        {{ pick('正在加载质量趋势…', 'Loading quality trend…') }}
      </p>
      <p v-else-if="error" class="quality-trend-panel__message quality-trend-panel__message--error">
        {{ error }}
      </p>
      <p
        v-else-if="!trendChapters.length"
        class="quality-trend-panel__message"
        data-testid="quality-trend-empty"
      >
        {{ pick('暂无质量快照', 'No quality snapshots yet') }}
      </p>
      <template v-else>
        <div
          class="quality-trend-panel__chapters"
          :aria-label="pick('逐章质量状态', 'Per-chapter quality status')"
        >
          <article
            v-for="chapter in trendChapters"
            :key="chapter.chapter_number"
            class="quality-trend-panel__chapter"
            :class="chapterToneClass(chapter)"
            :data-testid="`quality-trend-chapter-${chapter.chapter_number}`"
          >
            <strong>{{
              pick(`第 ${chapter.chapter_number} 章`, `Chapter ${chapter.chapter_number}`)
            }}</strong>
            <span>{{ chapterStatusText(chapter) }}</span>
            <span v-if="chapter.score != null">{{
              pick(`分数 ${chapter.score}`, `Score ${chapter.score}`)
            }}</span>
            <span v-if="chapter.word_count != null">{{
              pick(`字数 ${chapter.word_count}`, `Words ${chapter.word_count}`)
            }}</span>
            <span class="quality-trend-panel__metrics">{{ chapterMetricsText(chapter) }}</span>
          </article>
        </div>
        <div class="quality-trend-panel__counts">
          <div>
            <h4>Blocker</h4>
            <ul v-if="blockerEntries.length" data-testid="quality-trend-blocker-counts">
              <li v-for="[code, count] in blockerEntries" :key="code">
                <span>{{ code }}</span
                ><strong> {{ count }}</strong
                ><i
                  class="quality-trend-panel__bar"
                  :style="{ width: barWidth(count) }"
                  aria-hidden="true"
                ></i>
              </li>
            </ul>
            <p v-else>{{ pick('无', 'None') }}</p>
          </div>
          <div>
            <h4>Warning</h4>
            <ul v-if="warningEntries.length" data-testid="quality-trend-warning-counts">
              <li v-for="[code, count] in warningEntries" :key="code">
                <span>{{ code }}</span><strong> {{ count }}</strong>
                <i class="quality-trend-panel__bar" :style="{ width: barWidth(count) }" aria-hidden="true"></i>
              </li>
            </ul>
            <p v-else>{{ pick('无', 'None') }}</p>
          </div>
          <div>
            <h4>{{ pick('豁免', 'Exemptions') }}</h4>
            <ul v-if="exemptionEntries.length" data-testid="quality-trend-exemption-counts">
              <li v-for="[code, count] in exemptionEntries" :key="code">
                <span>{{ code }}</span
                ><strong> {{ count }}</strong
                ><i
                  class="quality-trend-panel__bar"
                  :style="{ width: barWidth(count) }"
                  aria-hidden="true"
                ></i>
              </li>
            </ul>
            <p v-else>{{ pick('无', 'None') }}</p>
          </div>
        </div>
        <div
          v-if="patchEntries.length"
          class="quality-trend-panel__patches"
          data-testid="quality-trend-patch-suggestions"
        >
          <h4>{{ pick('定向修复建议', 'Patch suggestions') }}</h4>
          <ul>
            <li v-for="entry in patchEntries" :key="entry.key">
              <strong>{{ entry.chapterLabel }}</strong>
              <span v-if="entry.code">{{ entry.code }}</span>
              <span v-if="entry.suggestion">{{ entry.suggestion }}</span>
            </li>
          </ul>
        </div>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NovelAPI } from '@/api/novel-client'
import type { QualityTrendChapter, QualityTrendResponse } from '@/api/types/novel'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ projectId: string }>()
const { pick } = useLocale()
const expanded = ref(false)
const loading = ref(false)
const error = ref('')
const trend = ref<QualityTrendResponse | null>(null)
const trendChapters = computed(() => trend.value?.chapters ?? [])
const trendChapterCount = computed(() => trend.value?.chapter_count ?? trendChapters.value.length)

const countEntries = (counts: Record<string, number> = {}) =>
  Object.entries(counts)
    .filter(([, count]) => Number.isFinite(count) && count > 0)
    .sort(([a], [b]) => a.localeCompare(b))
const blockerEntries = computed(() => countEntries(trend.value?.blocker_counts))
const warningEntries = computed(() => countEntries(trend.value?.warning_counts))
const exemptionEntries = computed(() => countEntries(trend.value?.exemption_counts))
const patchEntries = computed(() =>
  (trend.value?.chapters ?? []).flatMap((chapter) =>
    (chapter.patch_suggestions ?? []).map((patch, index) => ({
      key: `${chapter.chapter_number}-${patch.code ?? 'patch'}-${index}`,
      chapterLabel: pick(`第 ${chapter.chapter_number} 章`, `Chapter ${chapter.chapter_number}`),
      code: patch.code ?? '',
      suggestion: patch.suggestion ?? '',
    })),
  ),
)
const largestCount = computed(() =>
  Math.max(
    1,
    ...blockerEntries.value.map(([, count]) => count),
    ...warningEntries.value.map(([, count]) => count),
    ...exemptionEntries.value.map(([, count]) => count),
  ),
)
const summaryText = computed(() => {
  if (loading.value) return pick('加载中', 'Loading')
  if (error.value) return pick('加载失败', 'Unavailable')
  if (!trend.value) return pick('暂无数据', 'No data')
  return pick(
    `${trendChapterCount.value} 章 · ${blockerEntries.value.length} 类 blocker · ${warningEntries.value.length} 类 warning · ${exemptionEntries.value.length} 类豁免`,
    `${trendChapterCount.value} chapters · ${blockerEntries.value.length} blocker types · ${warningEntries.value.length} warning types · ${exemptionEntries.value.length} exemption types`,
  )
})
const hasFailure = (chapter: QualityTrendChapter) =>
  (chapter.blocker_codes?.length ?? 0) > 0 ||
  (chapter.warning_codes?.length ?? 0) > 0 ||
  chapter.repetition_risk === true ||
  chapter.continuity_inherit_missing === true ||
  chapter.continuity_inherit_late === true ||
  chapter.scene_transition_warning === true ||
  chapter.reversal_in_late_section === false ||
  (chapter.missing_focus_characters?.length ?? 0) > 0 ||
  (chapter.mission_quality_codes?.length ?? 0) > 0 ||
  chapter.word_requirement_met === false ||
  chapter.word_count_below_min === true ||
  chapter.word_count_far_below_target === true ||
  chapter.word_count_far_above_target === true ||
  (chapter.event_density_evaluated !== false && chapter.event_density_passed === false) ||
  (chapter.event_density_evaluated !== false && chapter.long_chapter_density_passed === false) ||
  (chapter.event_density_evaluated !== false && chapter.state_change_interval_passed === false) ||
  chapter.ending_pressure_passed === false ||
  chapter.dialogue_changes_state === false ||
  chapter.static_description_risk === true ||
  chapter.quality_gate_passed === false
const hasSnapshot = (chapter: QualityTrendChapter) =>
  // word_count alone is not a quality evaluation; legacy rows with only
  // length metadata must remain N/A instead of being shown as passed.
  chapter.quality_gate_passed != null ||
  chapter.score != null ||
  chapter.repetition_risk != null ||
  chapter.reversal_in_late_section != null ||
  chapter.scene_transition_warning != null ||
  chapter.continuity_inherit_missing != null ||
  chapter.continuity_inherit_late != null ||
  chapter.word_requirement_met != null ||
  chapter.event_density_passed != null ||
  chapter.long_chapter_density_passed != null ||
  chapter.state_change_interval_passed != null ||
  chapter.ending_pressure_passed != null ||
  chapter.dialogue_changes_state != null ||
  chapter.static_description_risk != null
const chapterToneClass = (chapter: QualityTrendChapter) =>
  hasFailure(chapter)
    ? 'quality-trend-panel__chapter--bad'
    : hasSnapshot(chapter)
      ? 'quality-trend-panel__chapter--good'
      : 'quality-trend-panel__chapter--unknown'
const chapterStatusText = (chapter: QualityTrendChapter) =>
  hasFailure(chapter)
    ? pick('需关注', 'Needs attention')
    : hasSnapshot(chapter)
      ? pick('通过', 'Passed')
      : pick('未评估', 'Not assessed')
const metricLabel = (passed: boolean | null | undefined, pass: string, fail: string) =>
  passed == null ? pick('未评估', 'N/A') : passed ? pass : fail
const formatPercent = (value: number | null | undefined) =>
  value == null ? null : `${Math.round(value * 100)}%`
const densityMetricText = (chapter: QualityTrendChapter) => {
  if (chapter.event_density_evaluated === false) {
    const reason = chapter.event_density_skip_reason?.trim()
    return pick(
      `事件密度未评估${reason ? `：${reason}` : '：样本过短'}`,
      `Density not assessed${reason ? `: ${reason}` : ': sample too short'}`,
    )
  }
  return metricLabel(
    chapter.event_density_passed,
    pick('事件密度通过', 'Density passed'),
    pick('事件密度不足', 'Density weak'),
  )
}
const repetitionMetricText = (chapter: QualityTrendChapter) => {
  const hasDiagnostic = [
    chapter.repeated_paragraph_count,
    chapter.max_repeated_paragraph_count,
    chapter.repeated_paragraph_ratio,
    chapter.longest_repeated_paragraph_chars,
    chapter.repetition_risk,
  ].some((value) => value != null)
  if (!hasDiagnostic) return pick('重复诊断未评估', 'Repetition N/A')
  const details = [
    pick(
      `重复段落 ${chapter.repeated_paragraph_count ?? 0}/${chapter.max_repeated_paragraph_count ?? 0}`,
      `Repeated paragraphs ${chapter.repeated_paragraph_count ?? 0}/${chapter.max_repeated_paragraph_count ?? 0}`,
    ),
    formatPercent(chapter.repeated_paragraph_ratio),
    chapter.longest_repeated_paragraph_chars != null
      ? pick(`最长 ${chapter.longest_repeated_paragraph_chars} 字`, `Longest ${chapter.longest_repeated_paragraph_chars} chars`)
      : null,
    chapter.repetition_risk === true ? pick('重复风险', 'Repetition risk') : null,
  ].filter(Boolean)
  return details.join(' · ')
}
const focusCharacterMetricText = (chapter: QualityTrendChapter) => {
  if (!chapter.focus_character_names?.length) return pick('焦点人物未设', 'Focus not set')
  const hitCount =
    chapter.focus_character_hit_count != null
      ? pick(`命中 ${chapter.focus_character_hit_count}`, `Hit ${chapter.focus_character_hit_count}`)
      : null
  const missing = chapter.missing_focus_characters?.length
    ? pick(
        `缺席 ${chapter.missing_focus_characters.join('、')}`,
        `Missing ${chapter.missing_focus_characters.join(', ')}`,
      )
    : pick('缺席 无', 'Missing none')
  return [
    pick(
      `焦点人物 ${chapter.focus_character_names.join('、')}`,
      `Focus ${chapter.focus_character_names.join(', ')}`,
    ),
    hitCount,
    missing,
  ]
    .filter(Boolean)
    .join(' · ')
}
const wordCountMetricText = (chapter: QualityTrendChapter) => {
  const hasContract = [
    chapter.target_word_count,
    chapter.min_word_count,
    chapter.preferred_word_floor,
    chapter.upper_word_ceiling,
    chapter.word_count_below_min,
    chapter.word_count_far_above_target,
    chapter.word_count_far_below_target,
    chapter.word_requirement_met,
  ].some((value) => value != null)
  if (!hasContract) return pick('字数目标未记录', 'Word target N/A')
  const penalties = [
    chapter.word_count_below_min === true ? pick('低于下限', 'Below minimum') : null,
    chapter.word_count_far_below_target === true ? pick('显著低于目标', 'Far below target') : null,
    chapter.word_count_far_above_target === true ? pick('远超目标', 'Far above target') : null,
    chapter.word_requirement_met === false ? pick('未满足字数要求', 'Word requirement unmet') : null,
  ].filter(Boolean)
  const contract = [
    chapter.target_word_count != null ? pick(`目标 ${chapter.target_word_count}`, `Target ${chapter.target_word_count}`) : null,
    chapter.min_word_count != null ? pick(`下限 ${chapter.min_word_count}`, `Min ${chapter.min_word_count}`) : null,
    chapter.preferred_word_floor != null ? pick(`优先线 ${chapter.preferred_word_floor}`, `Preferred ${chapter.preferred_word_floor}`) : null,
    chapter.upper_word_ceiling != null ? pick(`上限 ${chapter.upper_word_ceiling}`, `Ceiling ${chapter.upper_word_ceiling}`) : null,
  ].filter(Boolean)
  return [...contract, ...penalties].join(' · ')
}
const selfCritiqueMetricText = (chapter: QualityTrendChapter) => {
  const hasMetric =
    chapter.self_critique_final_score != null ||
    chapter.self_critique_critical_count != null ||
    chapter.self_critique_major_count != null ||
    Boolean(chapter.selected_critique_source?.trim()) ||
    (chapter.critique_exemption_applied?.length ?? 0) > 0
  if (!hasMetric) return pick('自评未记录', 'Self-critique N/A')
  const details = [
    chapter.self_critique_final_score != null
      ? pick(`自评 ${chapter.self_critique_final_score}`, `Self ${chapter.self_critique_final_score}`)
      : null,
    chapter.self_critique_critical_count != null ? `critical ${chapter.self_critique_critical_count}` : null,
    chapter.self_critique_major_count != null ? `major ${chapter.self_critique_major_count}` : null,
    chapter.selected_critique_source?.trim() ? `source ${chapter.selected_critique_source.trim()}` : null,
    (chapter.critique_exemption_applied?.length ?? 0) > 0
      ? pick(`豁免 ${chapter.critique_exemption_applied!.join('、')}`, `Exemptions ${chapter.critique_exemption_applied!.join(', ')}`)
      : null,
  ].filter(Boolean)
  return details.join(' · ')
}
const chapterMetricsText = (chapter: QualityTrendChapter) =>
  [
    densityMetricText(chapter),
    chapter.event_density_evaluated === false || chapter.long_chapter_density_passed == null
      ? pick('长章密度未评估', 'Long-chapter density N/A')
      : chapter.long_chapter_density_passed
        ? pick('长章密度通过', 'Long-chapter density passed')
        : pick('长章推进不足', 'Long-chapter progression weak'),
    chapter.event_density_evaluated === false || chapter.state_change_interval_passed == null
      ? pick('状态变化间隔未评估', 'State-change interval N/A')
      : chapter.state_change_interval_passed
        ? pick('状态变化间隔通过', 'State-change interval passed')
        : pick('状态变化间隔过长', 'State-change interval weak'),
    repetitionMetricText(chapter),
    focusCharacterMetricText(chapter),
    wordCountMetricText(chapter),
    selfCritiqueMetricText(chapter),
    metricLabel(
      chapter.ending_pressure_passed,
      pick('章末递压通过', 'Ending passed'),
      pick('章末递压不足', 'Ending weak'),
    ),
    metricLabel(
      chapter.dialogue_changes_state,
      pick('对白改局势', 'Dialogue shifts state'),
      pick('对白未改局势', 'Dialogue static'),
    ),
    chapter.static_description_risk == null
      ? pick('静态描写未评估', 'Description N/A')
      : chapter.static_description_risk
        ? pick('静态描写偏高', 'Description risk')
        : pick('静态描写可控', 'Description clear'),
    chapter.reversal_in_late_section === true
      ? pick(`后段反转 ${chapter.reversal_signal_count ?? 0}`, `Late reversal ${chapter.reversal_signal_count ?? 0}`)
      : pick('后段反转未观测', 'No late reversal observed'),
    chapter.continuity_inherit_missing === true
      ? pick('承接缺失', 'Continuity missing')
      : chapter.continuity_inherit_late === true
        ? pick('承接偏晚', 'Continuity late')
        : chapter.continuity_inherit_missing === false
          ? pick('承接正常', 'Continuity present')
          : pick('承接未评估', 'Continuity N/A'),
    chapter.dialogue_ratio != null
      ? pick(`配比 对白${Math.round(chapter.dialogue_ratio * 100)}% / 动作${Math.round((chapter.action_ratio ?? 0) * 100)}% / 描写${Math.round((chapter.description_ratio ?? 0) * 100)}%`, `Mix D${Math.round(chapter.dialogue_ratio * 100)}% / A${Math.round((chapter.action_ratio ?? 0) * 100)}% / Desc${Math.round((chapter.description_ratio ?? 0) * 100)}%`)
      : pick('配比未评估', 'Mix N/A'),
    chapter.speaker_count != null
      ? pick(`说话人 ${chapter.speaker_count} · 主导 ${Math.round((chapter.dominant_speaker_ratio ?? 0) * 100)}%`, `Speakers ${chapter.speaker_count} · Lead ${Math.round((chapter.dominant_speaker_ratio ?? 0) * 100)}%`)
      : pick('说话人未观测', 'Speaker N/A'),
    chapter.hard_scene_cut_count != null || chapter.summary_scene_cut_count != null
      ? `${pick(`场景切换 硬切${chapter.hard_scene_cut_count ?? 0} / 总结${chapter.summary_scene_cut_count ?? 0}`, `Scene cuts hard ${chapter.hard_scene_cut_count ?? 0} / closure ${chapter.summary_scene_cut_count ?? 0}`)}${chapter.scene_transition_warning === true ? ` · ${pick('场景切换告警', 'Scene transition warning')}` : ''}`
      : chapter.scene_transition_warning === true
        ? pick('场景切换告警', 'Scene transition warning')
        : pick('场景转换未观测', 'Scene transition N/A'),
    chapter.mission_quality_codes == null
      ? pick('任务书未评估', 'Mission check N/A')
      : chapter.mission_quality_codes.length
        ? pick(`任务书提示 ${chapter.mission_quality_codes.join('、')}`, `Mission notes ${chapter.mission_quality_codes.join(', ')}`)
        : pick('任务书体检正常', 'Mission check clear'),
  ].join(' · ')
const barWidth = (count: number) => `${Math.round((count / largestCount.value) * 100)}%`
const loadTrend = async () => {
  const projectId = props.projectId.trim()
  trend.value = null
  error.value = ''
  if (!projectId) return
  loading.value = true
  try {
    trend.value = await NovelAPI.getQualityTrend(projectId)
  } catch {
    error.value = pick('质量趋势暂不可用', 'Quality trend is unavailable')
  } finally {
    loading.value = false
  }
}
watch(() => props.projectId, loadTrend, { immediate: true })
</script>

<style scoped>
.quality-trend-panel {
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  background: var(--xq-surface);
  color: var(--xq-text-body);
}
.quality-trend-panel__toggle {
  display: flex;
  width: 100%;
  align-items: center;
  gap: var(--xq-space-2);
  border: 0;
  border-radius: inherit;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: var(--xq-space-3);
  text-align: left;
}
.quality-trend-panel__toggle:focus-visible {
  outline: none;
  box-shadow: var(--xq-ring);
}
.quality-trend-panel__summary {
  flex: 1;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
}
.quality-trend-panel__details {
  border-top: 1px solid var(--xq-border);
  padding: var(--xq-space-3);
}
.quality-trend-panel__message {
  margin: 0;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
}
.quality-trend-panel__message--error {
  color: var(--xq-danger);
}
.quality-trend-panel__chapters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: var(--xq-space-2);
}
.quality-trend-panel__chapter {
  display: grid;
  gap: var(--xq-space-1);
  border-left: 3px solid var(--xq-border-strong);
  border-radius: var(--xq-radius-sm);
  background: var(--xq-surface-2);
  padding: var(--xq-space-2);
  font-size: var(--xq-text-xs);
}
.quality-trend-panel__chapter--good {
  border-left-color: var(--xq-success);
}
.quality-trend-panel__chapter--bad {
  border-left-color: var(--xq-danger);
}
.quality-trend-panel__chapter--unknown {
  border-left-color: var(--xq-warning);
}
.quality-trend-panel__metrics {
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
}
.quality-trend-panel__counts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--xq-space-3);
  margin-top: var(--xq-space-3);
}
.quality-trend-panel__counts h4,
.quality-trend-panel__counts p {
  margin: 0 0 var(--xq-space-1);
  font-size: var(--xq-text-xs);
}
.quality-trend-panel__counts ul {
  display: grid;
  gap: var(--xq-space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}
.quality-trend-panel__counts li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--xq-space-1);
  align-items: center;
  font-size: var(--xq-text-2xs);
}
.quality-trend-panel__counts li span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quality-trend-panel__patches {
  margin-top: var(--xq-space-3);
}
.quality-trend-panel__patches h4 {
  margin: 0 0 var(--xq-space-1);
  font-size: var(--xq-text-xs);
}
.quality-trend-panel__patches ul {
  display: grid;
  gap: var(--xq-space-1);
  margin: 0;
  padding-left: var(--xq-space-4);
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
}
.quality-trend-panel__patches li {
  display: flex;
  flex-wrap: wrap;
  gap: var(--xq-space-1);
}
.quality-trend-panel__patches strong {
  color: var(--xq-text-body);
}
.quality-trend-panel__bar {
  grid-column: 1 / -1;
  display: block;
  min-width: 2px;
  height: 3px;
  border-radius: var(--xq-radius-pill);
  background: var(--xq-accent);
}
@media (max-width: 520px) {
  .quality-trend-panel__counts {
    grid-template-columns: 1fr;
  }
}
</style>
