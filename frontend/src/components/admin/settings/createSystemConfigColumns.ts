import { h } from 'vue'
import {
  NButton,
  NPopconfirm,
  NSpace,
  type DataTableColumns,
} from 'naive-ui'

import type { SystemConfig } from '@/api/admin'

interface CreateColumnsOptions {
  onEdit: (config: SystemConfig) => void
  onDelete: (key: string) => void
}

export const createSystemConfigColumns = ({
  onEdit,
  onDelete,
}: CreateColumnsOptions): DataTableColumns<SystemConfig> => [
  {
    title: 'Key',
    key: 'key',
    width: 220,
    ellipsis: { tooltip: true },
  },
  {
    title: '值',
    key: 'value',
    ellipsis: { tooltip: true },
  },
  {
    title: '描述',
    key: 'description',
    ellipsis: { tooltip: true },
    render(row) {
      return row.description || '—'
    },
  },
  {
    title: '操作',
    key: 'actions',
    align: 'center',
    width: 160,
    render(row) {
      return h(
        NSpace,
        { justify: 'center', size: 'small' },
        {
          default: () => [
            h(
              NButton,
              {
                size: 'small',
                type: 'primary',
                tertiary: true,
                onClick: () => onEdit(row),
              },
              { default: () => '编辑' },
            ),
            h(
              NPopconfirm,
              {
                'positive-text': '删除',
                'negative-text': '取消',
                type: 'error',
                placement: 'left',
                onPositiveClick: () => onDelete(row.key),
              },
              {
                default: () => '确认删除该配置项？',
                trigger: () =>
                  h(
                    NButton,
                    { size: 'small', type: 'error', quaternary: true },
                    { default: () => '删除' },
                  ),
              },
            ),
          ],
        },
      )
    },
  },
]
