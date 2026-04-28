import { computed, reactive, ref } from 'vue'

import {
  AdminAPI,
  type SystemConfig,
  type SystemConfigUpdatePayload,
} from '@/api/admin'
import { useAlert } from '@/composables/useAlert'
import { getSystemConfigMeta, SYSTEM_CONFIG_META, type SystemConfigMeta } from '@/components/admin/settings/systemConfigMeta'

export interface SystemConfigViewModel extends SystemConfig {
  meta?: SystemConfigMeta
  displayKey: string
  displayCategory: string
  displayDescription: string
  valueType: SystemConfigMeta['type'] | 'text'
  options?: SystemConfigMeta['options']
  order: number
}

export const useAdminSettings = () => {
  const { showAlert } = useAlert()

  const dailyLimit = ref<number | null>(null)
  const dailyLimitLoading = ref(false)
  const dailyLimitSaving = ref(false)
  const dailyLimitError = ref<string | null>(null)

  const configs = ref<SystemConfigViewModel[]>([])
  const configLoading = ref(false)
  const configSaving = ref(false)
  const configError = ref<string | null>(null)

  const configModalVisible = ref(false)
  const configForm = reactive<SystemConfigViewModel>({
    key: '',
    value: '',
    description: '',
    displayKey: '',
    displayCategory: '',
    displayDescription: '',
    valueType: 'text',
    order: 9999,
  })

  const modalTitle = computed(() => `编辑参数：${configForm.displayKey || configForm.key}`)

  const resetConfigForm = () => {
    configForm.key = ''
    configForm.value = ''
    configForm.description = ''
    configForm.displayKey = ''
    configForm.displayCategory = ''
    configForm.displayDescription = ''
    configForm.valueType = 'text'
    configForm.options = undefined
    configForm.order = 9999
    configForm.meta = undefined
  }

  const normalizeConfig = (config: SystemConfig): SystemConfigViewModel => {
    const meta = getSystemConfigMeta(config.key)
    return {
      ...config,
      meta,
      displayKey: meta?.labelZh || config.key,
      displayCategory: meta?.categoryZh || '其他参数',
      displayDescription: meta?.descriptionZh || config.description || '暂无详细说明',
      valueType: meta?.type || inferValueType(config.value),
      options: meta?.options,
      order: meta?.order ?? 9999,
    }
  }

  const buildConfigList = (serverConfigs: SystemConfig[]) => {
    const byKey = new Map(serverConfigs.map(item => [item.key, item]))
    const normalized: SystemConfigViewModel[] = []

    for (const meta of SYSTEM_CONFIG_META) {
      const found = byKey.get(meta.key)
      normalized.push(normalizeConfig({
        key: meta.key,
        value: found?.value ?? '',
        description: found?.description || meta.descriptionZh,
      }))
      byKey.delete(meta.key)
    }

    for (const unknown of byKey.values()) {
      normalized.push(normalizeConfig(unknown))
    }

    return normalized.sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
  }

  const fetchDailyLimit = async () => {
    dailyLimitLoading.value = true
    dailyLimitError.value = null
    try {
      const result = await AdminAPI.getDailyRequestLimit()
      dailyLimit.value = result.limit
    } catch (err) {
      dailyLimitError.value = err instanceof Error ? err.message : '加载每日限制失败'
    } finally {
      dailyLimitLoading.value = false
    }
  }

  const saveDailyLimit = async () => {
    if (dailyLimit.value === null || dailyLimit.value < 0) {
      showAlert('请设置有效的每日额度', 'error')
      return
    }
    dailyLimitSaving.value = true
    try {
      await AdminAPI.setDailyRequestLimit(dailyLimit.value)
      showAlert('每日额度已更新', 'success')
    } catch (err) {
      showAlert(err instanceof Error ? err.message : '保存失败', 'error')
    } finally {
      dailyLimitSaving.value = false
    }
  }

  const fetchConfigs = async () => {
    configLoading.value = true
    configError.value = null
    try {
      const result = await AdminAPI.listSystemConfigs()
      configs.value = buildConfigList(result)
    } catch (err) {
      configError.value = err instanceof Error ? err.message : '加载配置失败'
    } finally {
      configLoading.value = false
    }
  }

  const openEditModal = (config: SystemConfigViewModel) => {
    resetConfigForm()
    Object.assign(configForm, JSON.parse(JSON.stringify(config)))
    configModalVisible.value = true
  }

  const closeConfigModal = () => {
    configModalVisible.value = false
  }

  const submitConfig = async () => {
    if (!configForm.key.trim()) {
      showAlert('参数 Key 不能为空', 'error')
      return
    }

    configSaving.value = true
    try {
      const updated = await AdminAPI.upsertSystemConfig(configForm.key.trim(), {
        value: normalizeConfigValue(configForm.value, configForm.valueType),
        description: configForm.description || configForm.displayDescription || undefined,
      })
      const normalized = normalizeConfig(updated)
      const index = configs.value.findIndex((item) => item.key === updated.key)
      if (index !== -1) configs.value.splice(index, 1, normalized)
      else configs.value.push(normalized)
      configs.value = [...configs.value].sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
      showAlert('参数已保存', 'success')
      closeConfigModal()
    } catch (err) {
      showAlert(err instanceof Error ? err.message : '保存失败', 'error')
    } finally {
      configSaving.value = false
    }
  }

  const saveConfigValue = async (config: SystemConfigViewModel, value: string) => {
    const updated = await AdminAPI.upsertSystemConfig(config.key.trim(), {
      value: normalizeConfigValue(value, config.valueType),
      description: config.description || config.displayDescription || undefined,
    })
    const normalized = normalizeConfig(updated)
    const index = configs.value.findIndex((item) => item.key === updated.key)
    if (index !== -1) configs.value.splice(index, 1, normalized)
    else configs.value.push(normalized)
    configs.value = [...configs.value].sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
    return normalized
  }

  const initialize = async () => {
    await Promise.all([fetchDailyLimit(), fetchConfigs()])
  }

  return {
    dailyLimit,
    dailyLimitLoading,
    dailyLimitSaving,
    dailyLimitError,
    configs,
    configLoading,
    configSaving,
    configError,
    configModalVisible,
    configForm,
    modalTitle,
    fetchDailyLimit,
    saveDailyLimit,
    openEditModal,
    closeConfigModal,
    submitConfig,
    saveConfigValue,
    initialize,
  }
}

function inferValueType(value: string): SystemConfigMeta['type'] | 'text' {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'true' || normalized === 'false') return 'boolean'
  if (/^-?\d+(\.\d+)?$/.test(normalized)) return 'number'
  return 'text'
}

function normalizeConfigValue(value: string, type: SystemConfigMeta['type'] | 'text') {
  if (type === 'boolean') return String(value).trim().toLowerCase() === 'true' ? 'true' : 'false'
  return String(value ?? '')
}
