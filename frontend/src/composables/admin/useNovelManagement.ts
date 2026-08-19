import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { AdminAPI, type AdminNovelSummary } from '@/api/admin'
import { formatDateTime, pick } from '@/composables/useLocale'
import { useResponsiveFlag } from './useResponsiveFlag'

export const formatAdminNovelDate = (value: string | null | undefined) => {
  const fallback = pick('未记录', 'Not recorded')
  if (!value) return fallback
  return formatDateTime(value) || fallback
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
      error.value = e instanceof Error ? e.message : pick('获取小说数据失败', 'Failed to load the novel data')
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
