import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import VersionSelector from './VersionSelector.vue'

describe('VersionSelector', () => {
  it('shows quality risk summaries on candidate cards and active preview', () => {
    const wrapper = mount(VersionSelector, {
      props: {
        selectedChapter: {
          chapter_number: 1,
          title: 'Chapter 1',
          summary: 'Summary',
          content: null,
          versions: null,
          evaluation: null,
          generation_status: 'waiting_for_confirm',
        },
        chapterGenerationResult: null,
        availableVersions: [
          {
            id: 1,
            content: 'Candidate content A',
            metadata: {
              quality_metrics: {
                scene_fulfillment_rate: 0.25,
                dialogue_changes_state: false,
                ending_pressure_passed: false,
                static_description_risk: true,
              },
            },
          },
          {
            id: 2,
            content: 'Candidate content B',
            metadata: {
              quality_metrics: {
                scene_fulfillment_rate: 0.9,
                dialogue_changes_state: true,
                ending_pressure_passed: true,
                static_description_risk: false,
              },
            },
          },
        ],
        selectedVersionIndex: 0,
        compareVersionIndex: null,
        evaluatingChapter: null,
      },
    })

    expect(wrapper.findAll('.version-card__quality-pill--danger')).toHaveLength(1)
    expect(wrapper.findAll('.version-card__quality-pill--success')).toHaveLength(1)
    expect(wrapper.find('.version-preview__quality--danger').exists()).toBe(true)
    expect(wrapper.find('.version-preview__confirm-warning').exists()).toBe(true)
  })
})
