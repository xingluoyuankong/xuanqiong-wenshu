import { computed, reactive, ref } from 'vue'
import type { SelectOption } from 'naive-ui'

import {
  AdminAPI,
  type SystemConfig,
  type SystemConfigUpdatePayload,
} from '@/api/admin'
import { useAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'
import { getSystemConfigMeta, SYSTEM_CONFIG_META, type SystemConfigMeta } from '@/components/admin/settings/systemConfigMeta'

export interface SystemConfigViewModel extends SystemConfig {
  meta?: SystemConfigMeta
  displayKey: string
  displayCategory: string
  displayDescription: string
  valueType: SystemConfigMeta['type'] | 'text'
  options?: SelectOption[]
  order: number
}

export const useAdminSettings = () => {
  const { showAlert } = useAlert()
  const { pick } = useLocale()

  const dailyLimit = ref<number | null>(null)
  const dailyLimitLoading = ref(false)
  const dailyLimitSaving = ref(false)
  const dailyLimitError = ref<string | null>(null)

  // 服务端原始数据。展示字段由 configs 这个 computed 派生，切换语言后自动跟着变
  const rawConfigs = ref<SystemConfig[]>([])
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

  const modalTitle = computed(() => {
    const meta = getSystemConfigMeta(configForm.key)
    const name = meta?.label() || configForm.displayKey || configForm.key
    return pick(`编辑参数：${name}`, `Edit parameter: ${name}`)
  })

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
      displayKey: meta?.label() || config.key,
      displayCategory: meta?.category() || pick('其他参数', 'Other parameters'),
      displayDescription: meta?.description() || config.description || pick('暂无详细说明', 'No description yet'),
      valueType: meta?.type || inferValueType(config.value),
      options: meta?.options?.(),
      order: meta?.order ?? 9999,
    }
  }

  const configs = computed<SystemConfigViewModel[]>(() =>
    rawConfigs.value
      .map(normalizeConfig)
      .sort((a, b) => a.order - b.order || a.key.localeCompare(b.key))
  )

  /** 用 SYSTEM_CONFIG_META 的顺序补齐后端缺失的参数，未知参数追加在后面。 */
  const buildRawList = (serverConfigs: SystemConfig[]): SystemConfig[] => {
    const byKey = new Map(serverConfigs.map(item => [item.key, item]))
    const list: SystemConfig[] = []

    for (const meta of SYSTEM_CONFIG_META) {
      const found = byKey.get(meta.key)
      list.push({
        key: meta.key,
        value: found?.value ?? '',
        description: found?.description || '',
      })
      byKey.delete(meta.key)
    }

    for (const unknown of byKey.values()) {
      list.push(unknown)
    }

    return list
  }

  const upsertRawConfig = (updated: SystemConfig) => {
    const index = rawConfigs.value.findIndex((item) => item.key === updated.key)
    if (index !== -1) rawConfigs.value.splice(index, 1, updated)
    else rawConfigs.value.push(updated)
  }

  const fetchDailyLimit = async () => {
    dailyLimitLoading.value = true
    dailyLimitError.value = null
    try {
      const result = await AdminAPI.getDailyRequestLimit()
      dailyLimit.value = result.limit
    } catch (err) {
      dailyLimitError.value = err instanceof Error ? err.message : pick('加载每日限制失败', 'Failed to load the daily limit')
    } finally {
      dailyLimitLoading.value = false
    }
  }

  const saveDailyLimit = async () => {
    if (dailyLimit.value === null || dailyLimit.value < 0) {
      showAlert(pick('请设置有效的每日额度', 'Enter a valid daily quota'), 'error')
      return
    }
    dailyLimitSaving.value = true
    try {
      await AdminAPI.setDailyRequestLimit(dailyLimit.value)
      showAlert(pick('每日额度已更新', 'Daily quota updated'), 'success')
    } catch (err) {
      showAlert(err instanceof Error ? err.message : pick('保存失败', 'Save failed'), 'error')
    } finally {
      dailyLimitSaving.value = false
    }
  }

  const fetchConfigs = async () => {
    configLoading.value = true
    configError.value = null
    try {
      const result = await AdminAPI.listSystemConfigs()
      rawConfigs.value = buildRawList(result)
    } catch (err) {
      configError.value = err instanceof Error ? err.message : pick('加载配置失败', 'Failed to load the configuration')
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
      showAlert(pick('参数 Key 不能为空', 'The parameter key cannot be empty'), 'error')
      return
    }

    configSaving.value = true
    try {
      const updated = await AdminAPI.upsertSystemConfig(configForm.key.trim(), {
        value: normalizeConfigValue(configForm.value, configForm.valueType),
        description: configForm.description || configForm.displayDescription || undefined,
      })
      upsertRawConfig(updated)
      showAlert(pick('参数已保存', 'Parameter saved'), 'success')
      closeConfigModal()
    } catch (err) {
      showAlert(err instanceof Error ? err.message : pick('保存失败', 'Save failed'), 'error')
    } finally {
      configSaving.value = false
    }
  }

  const saveConfigValue = async (config: SystemConfigViewModel, value: string) => {
    const updated = await AdminAPI.upsertSystemConfig(config.key.trim(), {
      value: normalizeConfigValue(value, config.valueType),
      description: config.description || config.displayDescription || undefined,
    })
    upsertRawConfig(updated)
    return normalizeConfig(updated)
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
