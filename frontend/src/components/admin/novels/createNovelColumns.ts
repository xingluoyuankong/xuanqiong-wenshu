import { h } from 'vue'
import { NButton, NTag, type DataTableColumns } from 'naive-ui'

import type { AdminNovelSummary } from '@/api/admin'
import { formatAdminNovelDate, formatAdminNovelProgress } from '@/composables/admin/useNovelManagement'

export const createNovelColumns = (
  onView: (novelId: string) => void,
): DataTableColumns<AdminNovelSummary> => [
  {
    title: '项目',
    key: 'title',
    ellipsis: { tooltip: true },
    render(row) {
      return h('div', { class: 'table-title-cell' }, [
        h('div', { class: 'table-title' }, row.title),
        h('div', { class: 'table-subtitle' }, row.id),
      ])
    },
  },
  {
    title: '类型',
    key: 'genre',
    render(row) {
      return h(
        NTag,
        { type: 'info', size: 'small', round: true, bordered: false },
        { default: () => row.genre || '未分类' },
      )
    },
  },
  {
    title: '创作者',
    key: 'owner_username',
    render(row) {
      return h('span', { class: 'table-owner' }, row.owner_username)
    },
  },
  {
    title: '进度',
    key: 'progress',
    render(row) {
      return h('span', { class: 'table-progress' }, formatAdminNovelProgress(row))
    },
  },
  {
    title: '最近更新',
    key: 'last_edited',
    render(row) {
      return h('span', { class: 'table-date' }, formatAdminNovelDate(row.last_edited))
    },
  },
  {
    title: '操作',
    key: 'actions',
    align: 'center',
    render(row) {
      return h(
        NButton,
        {
          size: 'small',
          type: 'primary',
          tertiary: true,
          onClick: () => onView(row.id),
        },
        { default: () => '详情' },
      )
    },
  },
]
