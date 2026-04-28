import { reactive, ref } from 'vue'
import { AdminAPI, type PromptCreatePayload, type PromptItem } from '@/api/admin'
import { useAlert } from '@/composables/useAlert'

const createEmptyPromptForm = (): PromptCreatePayload => ({
  name: '',
  title: '',
  content: '',
  tags: [],
})

export const usePromptManagement = () => {
  const { showAlert } = useAlert()

  const prompts = ref<PromptItem[]>([])
  const selectedPrompt = ref<PromptItem | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const deleting = ref(false)
  const creating = ref(false)
  const error = ref<string | null>(null)

  const editForm = reactive({
    name: '',
    title: '',
    content: '',
    tags: [] as string[],
  })

  const createModalVisible = ref(false)
  const createForm = reactive<PromptCreatePayload>(createEmptyPromptForm())

  const resetSelection = () => {
    selectedPrompt.value = null
    editForm.name = ''
    editForm.title = ''
    editForm.content = ''
    editForm.tags = []
  }

  const resetCreateForm = () => {
    Object.assign(createForm, createEmptyPromptForm())
  }

  const selectPrompt = (prompt: PromptItem) => {
    selectedPrompt.value = prompt
    editForm.name = prompt.name
    editForm.title = prompt.title || ''
    editForm.content = prompt.content
    editForm.tags = prompt.tags ? [...prompt.tags] : []
  }

  const fetchPrompts = async () => {
    loading.value = true
    error.value = null
    try {
      prompts.value = await AdminAPI.listPrompts()
      if (selectedPrompt.value) {
        const refreshed = prompts.value.find(item => item.id === selectedPrompt.value?.id)
        if (refreshed) selectPrompt(refreshed)
        else resetSelection()
      } else if (prompts.value.length) {
        selectPrompt(prompts.value[0])
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '获取提示词列表失败'
    } finally {
      loading.value = false
    }
  }

  const savePrompt = async () => {
    if (!selectedPrompt.value) return
    if (!editForm.content.trim()) {
      showAlert('提示词内容不能为空', 'error')
      return
    }
    saving.value = true
    try {
      const updated = await AdminAPI.updatePrompt(selectedPrompt.value.id, {
        title: editForm.title || undefined,
        content: editForm.content,
        tags: editForm.tags,
      })
      selectPrompt(updated)
      const index = prompts.value.findIndex(item => item.id === updated.id)
      if (index !== -1) prompts.value.splice(index, 1, updated)
      showAlert('保存成功', 'success')
    } catch (err) {
      showAlert(err instanceof Error ? err.message : '保存失败', 'error')
    } finally {
      saving.value = false
    }
  }

  const deletePrompt = async () => {
    if (!selectedPrompt.value) return
    deleting.value = true
    try {
      await AdminAPI.deletePrompt(selectedPrompt.value.id)
      prompts.value = prompts.value.filter(item => item.id !== selectedPrompt.value?.id)
      resetSelection()
      showAlert('删除成功', 'success')
    } catch (err) {
      showAlert(err instanceof Error ? err.message : '删除失败', 'error')
    } finally {
      deleting.value = false
    }
  }

  const openCreateModal = () => {
    createModalVisible.value = true
  }

  const closeCreateModal = () => {
    createModalVisible.value = false
    resetCreateForm()
  }

  const createPrompt = async () => {
    if (!createForm.name.trim() || !createForm.content.trim()) {
      showAlert('提示词名称和内容都是必填项', 'error')
      return
    }
    creating.value = true
    try {
      const created = await AdminAPI.createPrompt({
        name: createForm.name.trim(),
        title: createForm.title?.trim() || undefined,
        content: createForm.content,
        tags: createForm.tags?.length ? [...createForm.tags] : undefined,
      })
      prompts.value.unshift(created)
      selectPrompt(created)
      closeCreateModal()
      showAlert('创建成功', 'success')
    } catch (err) {
      showAlert(err instanceof Error ? err.message : '创建失败', 'error')
    } finally {
      creating.value = false
    }
  }

  return {
    prompts,
    selectedPrompt,
    loading,
    saving,
    deleting,
    creating,
    error,
    editForm,
    createModalVisible,
    createForm,
    fetchPrompts,
    resetSelection,
    selectPrompt,
    savePrompt,
    deletePrompt,
    openCreateModal,
    closeCreateModal,
    createPrompt,
  }
}
