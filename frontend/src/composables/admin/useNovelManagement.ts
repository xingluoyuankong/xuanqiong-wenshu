import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { AdminAPI, type AdminNovelSummary } from '@/api/admin'
import { useResponsiveFlag } from './useResponsiveFlag'

export const formatAdminNovelDate = (value: string | null | undefined) => {
  if (!value) return '未记录'

  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '未记录'

    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')

    return `${year}年${month}月${day}日 ${hours}:${minutes}`
  } catch {
    return '未记录'
  }
}

export const formatAdminNovelProgress = (
  novel: Pick<AdminNovelSummary, 'completed_chapters' | 'total_chapters'>,
) => {
  const total = novel.total_chapters || 0
  const completed = novel.completed_chapters || 0
  return `${completed} / ${total}`
}

export const useNovelManagement = () => {
  const novels = ref<AdminNovelSummary[]>([])
  const loading = ref(true)
  const error = ref<string | null>(null)
  const router = useRouter()
  const { matched: isMobile } = useResponsiveFlag(768)

  const pagination = computed(() => ({
    pageSize: 8,
    showSizePicker: false,
  }))

  const viewDetails = (novelId: string) => {
    router.push(`/admin/novel/${novelId}`)
  }

  const fetchNovels = async () => {
    loading.value = true
    error.value = null
    try {
      novels.value = await AdminAPI.listNovels()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '获取小说数据失败'
    } finally {
      loading.value = false
    }
  }

  return {
    novels,
    loading,
    error,
    isMobile,
    pagination,
    fetchNovels,
    viewDetails,
  }
}
