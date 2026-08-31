import { readFileSync } from 'node:fs'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import QualityTrendPanel from './QualityTrendPanel.vue'

describe('QualityTrendPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('requests the project quality trend and keeps the compact panel collapsed until opened', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toMatch(/\/api\/novels\/project-9\/quality-trend$/)
      return new Response(
        JSON.stringify({
          project_id: 'project-9',
          chapter_count: 2,
          chapters: [
            {
              chapter_number: 1,
              status: 'successful',
              score: 860,
              word_count: 3000,
              repetition_risk: false,
              repeated_paragraph_count: 0,
              max_repeated_paragraph_count: 0,
              repeated_paragraph_ratio: 0,
              longest_repeated_paragraph_chars: 0,
              focus_character_names: ['沈砚'],
              focus_character_hit_count: 1,
              missing_focus_characters: [],
              target_word_count: 3000,
              min_word_count: 2700,
              preferred_word_floor: 2800,
              upper_word_ceiling: 3600,
              word_count_below_min: false,
              word_count_far_above_target: false,
              word_count_far_below_target: false,
              word_requirement_met: true,
              event_density_evaluated: true,
              event_density_skip_reason: null,
              event_density_passed: true,
              long_chapter_density_passed: null,
              state_change_interval_passed: true,
              ending_pressure_passed: true,
              dialogue_changes_state: true,
              static_description_risk: false,
              reversal_signal_count: 2,
              reversal_in_late_section: true,
              speaker_count: 2,
              dominant_speaker_ratio: 0.65,
              hard_scene_cut_count: 0,
              summary_scene_cut_count: 0,
              mission_quality_codes: [],
              warning_codes: [],
              patch_suggestions: [],
              blocker_codes: [],
              exemptions: [],
              critique_exemption_applied: [],
              self_critique_final_score: 82,
              self_critique_critical_count: 0,
              self_critique_major_count: 1,
              selected_critique_source: 'self_critique_after_consistency',
            },
            {
              chapter_number: 2,
              status: 'successful',
              score: 620,
              word_count: 900,
              repetition_risk: true,
              repeated_paragraph_count: 3,
              max_repeated_paragraph_count: 4,
              repeated_paragraph_ratio: 0.18,
              longest_repeated_paragraph_chars: 180,
              focus_character_names: ['沈砚', '顾昭'],
              focus_character_hit_count: 1,
              missing_focus_characters: ['顾昭'],
              target_word_count: 3000,
              min_word_count: 2250,
              preferred_word_floor: 2700,
              upper_word_ceiling: 3600,
              word_count_below_min: true,
              word_count_far_above_target: false,
              word_count_far_below_target: true,
              word_requirement_met: false,
              event_density_evaluated: false,
              event_density_skip_reason: '样本过短',
              event_density_passed: false,
              long_chapter_density_passed: null,
              state_change_interval_passed: null,
              ending_pressure_passed: false,
              dialogue_changes_state: false,
              static_description_risk: true,
              dialogue_ratio: 0.75,
              action_ratio: 0.25,
              description_ratio: 0,
              speaker_count: 3,
              dominant_speaker_ratio: 0.9,
              hard_scene_cut_count: 2,
              summary_scene_cut_count: 1,
              scene_transition_warning: true,
              mission_quality_codes: ['mission_dialogue_strategy_empty'],
              warning_codes: ['continuity_inherit_missing'],
              patch_suggestions: [
                {
                  code: 'continuity_inherit_missing',
                  suggestion: '在开篇补入上一章未决目标和即时后果。',
                },
              ],
              blocker_codes: ['event_density_weak', 'ending_pressure_missing'],
              exemptions: ['ending_pressure_missing'],
              critique_exemption_applied: [],
            },
          ],
          blocker_counts: { ending_pressure_missing: 1, event_density_weak: 1 },
          warning_counts: { continuity_inherit_missing: 1 },
          exemption_counts: { ending_pressure_missing: 1 },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-9' } })
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="quality-trend-toggle"]').text()).toContain('质量趋势')
    expect(wrapper.find('[data-testid="quality-trend-details"]').exists()).toBe(false)

    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    expect(wrapper.get('[data-testid="quality-trend-details"]').text()).toContain('第 1 章')
    expect(wrapper.get('[data-testid="quality-trend-details"]').text()).toContain('第 2 章')
    expect(
      wrapper
        .get('[data-testid="quality-trend-blocker-counts"]')
        .findAll('li')
        .map((item) => [item.get('span').text(), item.get('strong').text().trim()]),
    ).toEqual([
      ['ending_pressure_missing', '1'],
      ['event_density_weak', '1'],
    ])
    expect(
      wrapper
        .get('[data-testid="quality-trend-exemption-counts"]')
        .findAll('li')
        .map((item) => [item.get('span').text(), item.get('strong').text().trim()]),
    ).toEqual([['ending_pressure_missing', '1']])
    expect(
      wrapper
        .get('[data-testid="quality-trend-warning-counts"]')
        .findAll('li')
        .map((item) => [item.get('span').text(), item.get('strong').text().trim()]),
    ).toEqual([['continuity_inherit_missing', '1']])
    expect(wrapper.get('[data-testid="quality-trend-patch-suggestions"]').text()).toContain(
      '在开篇补入上一章未决目标和即时后果。',
    )
    const chapterOneText = wrapper.get('[data-testid="quality-trend-chapter-1"]').text()
    expect(chapterOneText).toContain('重复段落 0/0 · 0%')
    expect(chapterOneText).toContain('焦点人物 沈砚 · 命中 1 · 缺席 无')
    expect(chapterOneText).toContain('目标 3000 · 下限 2700 · 优先线 2800 · 上限 3600')
    expect(chapterOneText).toContain('后段反转 2')
    expect(chapterOneText).toContain('长章密度未评估 · 状态变化间隔通过')
    expect(chapterOneText).toContain('自评 82 · critical 0 · major 1 · source self_critique_after_consistency')

    const chapterTwoText = wrapper.get('[data-testid="quality-trend-chapter-2"]').text()
    expect(chapterTwoText).toContain('事件密度未评估：样本过短')
    expect(chapterTwoText).toContain('长章密度未评估 · 状态变化间隔未评估')
    expect(chapterTwoText).toContain('重复段落 3/4 · 18% · 最长 180 字 · 重复风险')
    expect(chapterTwoText).toContain('焦点人物 沈砚、顾昭 · 命中 1 · 缺席 顾昭')
    expect(chapterTwoText).toContain('目标 3000 · 下限 2250 · 优先线 2700 · 上限 3600 · 低于下限 · 显著低于目标 · 未满足字数要求')
    expect(chapterTwoText).toContain('配比 对白75% / 动作25% / 描写0%')
    expect(chapterTwoText).toContain('说话人 3 · 主导 90%')
    expect(chapterTwoText).toContain('场景切换 硬切2 / 总结1 · 场景切换告警')
    expect(chapterTwoText).toContain('任务书提示 mission_dialogue_strategy_empty')
    expect(wrapper.get('[data-testid="quality-trend-chapter-1"]').classes()).toContain(
      'quality-trend-panel__chapter--good',
    )
    expect(wrapper.get('[data-testid="quality-trend-chapter-2"]').classes()).toContain(
      'quality-trend-panel__chapter--bad',
    )
  })

  it('keeps a short sample with skipped density assessment out of the density-failure state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              project_id: 'project-short',
              chapter_count: 1,
              chapters: [
                {
                  chapter_number: 1,
                  status: 'successful',
                  score: 860,
                  word_count: 420,
                  event_density_evaluated: false,
                  event_density_skip_reason: '样本过短',
                  event_density_passed: false,
                  long_chapter_density_passed: false,
                  state_change_interval_passed: false,
                  ending_pressure_passed: true,
                  dialogue_changes_state: true,
                  static_description_risk: false,
                  warning_codes: [],
                  patch_suggestions: [],
                },
              ],
              blocker_counts: {},
              warning_counts: {},
              exemption_counts: {},
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-short' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('事件密度未评估：样本过短')
    expect(chapter.text()).toContain('长章密度未评估 · 状态变化间隔未评估')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--good')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--bad')
  })

  it('does not treat legacy reversal warning as quality passed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-reversal-warning',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          word_count: 3000,
          reversal_in_late_section: false,
          warning_codes: [],
          blocker_codes: [],
          exemptions: [],
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-reversal-warning' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('需关注')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--bad')
  })

  it('quality status consumes quality_gate_passed for gate-only rows', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-gate-only',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'evaluation_failed',
          quality_gate_passed: false,
          blocker_codes: [],
          warning_codes: [],
          exemptions: [],
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-gate-only' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('需关注')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--bad')
  })

  it('keeps a null quality gate state as not assessed in the trend panel', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-gate-unknown',
        chapter_count: 1,
        chapters: [{ chapter_number: 1, status: 'successful', quality_gate_passed: null }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-gate-unknown' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('未评估')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--unknown')
  })

  it('quality status uses the explicit gate result as a tri-state field', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('chapter.quality_gate_passed === false')
    expect(source).toContain('chapter.quality_gate_passed != null')
  })

  it('quality status consumes the legacy reversal warning field', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('chapter.reversal_in_late_section === false')
  })

  it('does not treat legacy explicit warning flags as quality passed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-legacy-warning-flags',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          word_count: 3000,
          repetition_risk: true,
          continuity_inherit_missing: true,
          scene_transition_warning: true,
          missing_focus_characters: ['顾昭'],
          mission_quality_codes: ['mission_focus_placeholder'],
          warning_codes: [],
          blocker_codes: [],
          exemptions: [],
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-legacy-warning-flags' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('需关注')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--bad')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--good')
  })

  it('quality status consumes legacy explicit warning fields', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('chapter.repetition_risk === true')
    expect(source).toContain('chapter.continuity_inherit_missing === true')
    expect(source).toContain('chapter.scene_transition_warning === true')
  })

  it('does not treat warning-only chapters as quality passed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-warning-only',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          word_count: 3000,
          warning_codes: ['continuity_inherit_missing'],
          blocker_codes: [],
          exemptions: ['some_exemption'],
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-warning-only' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('需关注')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--bad')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--good')
  })

  it('quality status includes warning codes but not exemptions', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('(chapter.warning_codes?.length ?? 0) > 0')
    expect(source).not.toContain('(chapter.exemptions?.length ?? 0) > 0')
  })

  it('does not treat an explicit word requirement failure as quality passed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-word-requirement-failed',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          word_count: 1200,
          target_word_count: 3000,
          min_word_count: 2700,
          word_requirement_met: false,
          word_count_below_min: true,
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-word-requirement-failed' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('未满足字数要求')
    expect(chapter.text()).toContain('需关注')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--bad')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--good')
  })

  it('quality status includes explicit word requirement failures', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('chapter.word_requirement_met === false')
    expect(source).toContain('chapter.word_count_below_min === true')
    expect(source).toContain('chapter.word_count_far_below_target === true')
    expect(source).toContain('chapter.word_count_far_above_target === true')
  })

  it('does not treat far-above-target word counts as a healthy quality snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-word-distance-failed',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          word_count: 9000,
          target_word_count: 3000,
          word_count_far_above_target: true,
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-word-distance-failed' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('远超目标')
    expect(chapter.text()).toContain('需关注')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--bad')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--good')
  })

  it('trend density guards require evaluation state for all three metrics', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    const longGuard = 'chapter.event_density_evaluated !== false && chapter.long_chapter_density_passed === false'
    const intervalGuard = 'chapter.event_density_evaluated !== false && chapter.state_change_interval_passed === false'
    expect(source).toContain(longGuard)
    expect(source).toContain(intervalGuard)
    expect(source.replace(longGuard, 'true')).not.toContain(longGuard)
    expect(source.replace(intervalGuard, 'true')).not.toContain(intervalGuard)
  })

  it('treats omitted legacy tri-state fields as not assessed rather than passed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              project_id: 'project-legacy',
              chapter_count: 1,
              chapters: [
                {
                  chapter_number: 1,
                  status: 'successful',
                  score: null,
                  word_count: null,
                  blocker_codes: [],
                  warning_codes: [],
                  patch_suggestions: [],
                  exemptions: [],
                },
              ],
              blocker_counts: {},
              warning_counts: {},
              exemption_counts: {},
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-legacy' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('未评估')
    expect(chapter.text()).toContain('静态描写未评估')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--unknown')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--good')
  })

  it('snapshot presence and static risk use nullish guards', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('chapter.ending_pressure_passed != null')
    expect(source).toContain('chapter.static_description_risk == null')
    expect(source).not.toContain('chapter.ending_pressure_passed !== null')
    expect(source).not.toContain('chapter.static_description_risk !== null')
  })

  it('accepts legacy trend chapters without blocker or exemption arrays', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              project_id: 'project-legacy-arrays',
              chapter_count: 1,
              chapters: [
                {
                  chapter_number: 1,
                  status: 'successful',
                  score: null,
                  word_count: null,
                  event_density_evaluated: false,
                  event_density_passed: null,
                  long_chapter_density_passed: null,
                  state_change_interval_passed: null,
                },
              ],
              blocker_counts: {},
              warning_counts: {},
              exemption_counts: {},
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-legacy-arrays' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('事件密度未评估')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--unknown')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--bad')
  })

  it('uses an optional blocker array guard', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('(chapter.blocker_codes?.length ?? 0) > 0')
    expect(source).not.toContain('chapter.blocker_codes.length > 0')
  })

  it('treats explicit legacy pass flags as an evaluated snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-legacy-pass-flags',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          word_count: 3000,
          repetition_risk: false,
          reversal_in_late_section: true,
          scene_transition_warning: false,
          continuity_inherit_missing: false,
          continuity_inherit_late: false,
          word_requirement_met: true,
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-legacy-pass-flags' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('通过')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--good')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--unknown')
  })

  it('quality snapshot accepts explicit legacy pass flags', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).toContain('chapter.repetition_risk != null')
    expect(source).toContain('chapter.reversal_in_late_section != null')
    expect(source).toContain('chapter.word_requirement_met != null')
  })

  it('does not treat a legacy word-count-only row as quality passed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-word-count-only',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          word_count: 3200,
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-word-count-only' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('字数 3200')
    expect(chapter.text()).toContain('未评估')
    expect(chapter.classes()).toContain('quality-trend-panel__chapter--unknown')
    expect(chapter.classes()).not.toContain('quality-trend-panel__chapter--good')
  })

  it('does not call continuity normal when both continuity flags are unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-continuity-unknown',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          continuity_inherit_missing: null,
          continuity_inherit_late: null,
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-continuity-unknown' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('承接未评估')
    expect(chapter.text()).not.toContain('承接正常')
  })

  it('does not call a missing mission-quality field healthy', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-mission-unknown',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          score: 900,
          mission_quality_codes: null,
        }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-mission-unknown' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).toContain('任务书未评估')
    expect(chapter.text()).not.toContain('任务书体检正常')
  })

  it('quality status cannot use word_count as a quality snapshot', () => {
    const source = readFileSync('src/components/writing-desk/widgets/QualityTrendPanel.vue', 'utf8')
    expect(source).not.toContain('chapter.word_count != null ||\n  chapter.event_density_passed')
  })

  it('does not render omitted score or word count fields as undefined', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-legacy-scalars',
        chapter_count: 1,
        chapters: [{
          chapter_number: 1,
          status: 'successful',
          event_density_evaluated: false,
          event_density_passed: null,
        }],
        blocker_counts: {},
        warning_counts: {},
        exemption_counts: {},
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-legacy-scalars' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    const chapter = wrapper.get('[data-testid="quality-trend-chapter-1"]')
    expect(chapter.text()).not.toContain('分数 undefined')
    expect(chapter.text()).not.toContain('字数 undefined')
    expect(chapter.text()).toContain('自评未记录')
  })

  it('accepts a legacy trend response without a chapters array', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({
        project_id: 'project-no-chapters',
        chapter_count: 0,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-no-chapters' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    expect(wrapper.get('[data-testid="quality-trend-empty"]').text()).toContain('暂无质量快照')
    expect(wrapper.get('[data-testid="quality-trend-toggle"]').text()).toContain('0 章')
    expect(wrapper.get('[data-testid="quality-trend-toggle"]').text()).not.toContain('undefined')
  })

  it('renders an empty state when a project has no quality snapshots', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              project_id: 'project-empty',
              chapter_count: 0,
              chapters: [],
              blocker_counts: {},
              exemption_counts: {},
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    )

    const wrapper = mount(QualityTrendPanel, { props: { projectId: 'project-empty' } })
    await flushPromises()
    await wrapper.get('[data-testid="quality-trend-toggle"]').trigger('click')

    expect(wrapper.get('[data-testid="quality-trend-empty"]').text()).toContain('暂无质量快照')
  })
})
