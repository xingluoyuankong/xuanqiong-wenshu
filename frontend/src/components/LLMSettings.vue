<template>
  <div class="llm-settings-root">
    <section class="llm-toolbar xq-page-topbar xq-page-topbar--llm">
      <div>
        <h2>{{ pick('LLM 配置', 'LLM config') }}</h2>
        <p>{{ pick('统一管理接口地址、API Key、模型列表，并支持健康检查和自动切换。', 'Manage endpoints, API keys, and model lists in one place, with health checks and automatic switching.') }}</p>
      </div>
      <div class="llm-toolbar__actions">
        <button class="primary-btn" :disabled="saving" @click="handleSave">{{ saving ? pick('保存中...', 'Saving...') : pick('保存配置', 'Save config') }}</button>
        <button class="ghost-btn" @click="addProfile">{{ pick('新增配置组', 'Add profile') }}</button>
        <button class="ghost-btn" :disabled="loadingModels" @click="loadModelsForActiveProfile">{{ loadingModels ? pick('拉取中...', 'Fetching...') : pick('拉取模型', 'Fetch models') }}</button>
        <button class="ghost-btn" :disabled="checkingHealth" @click="runHealthCheck">{{ checkingHealth ? pick('检查中...', 'Checking...') : pick('健康检查', 'Health check') }}</button>
        <button class="ghost-btn" :disabled="switching" @click="handleAutoSwitch">{{ switching ? pick('切换中...', 'Switching...') : pick('自动切换', 'Auto switch') }}</button>
      </div>
    </section>

    <div v-if="notice" class="notice" :class="`notice--${notice.type}`">{{ notice.message }}</div>

    <section class="summary-grid">
      <article class="summary-card">
        <span>{{ pick('当前激活组', 'Active profile') }}</span>
        <strong>{{ activeProfile?.name || pick('未命名配置组', 'Unnamed profile') }}</strong>
      </article>
      <article class="summary-card">
        <span>{{ pick('当前地址', 'Current endpoint') }}</span>
        <strong>{{ activeProfile?.llm_provider_url || pick('未填写', 'Not set') }}</strong>
      </article>
      <article class="summary-card">
        <span>{{ pick('启用 Key', 'Enabled keys') }}</span>
        <strong>{{ countEnabled(activeProfile?.api_keys || []) }}</strong>
      </article>
      <article class="summary-card">
        <span>{{ pick('启用模型', 'Enabled models') }}</span>
        <strong>{{ countEnabled(activeProfile?.models || []) }}</strong>
      </article>
    </section>

    <section class="profiles-layout">
      <aside class="profile-list">
        <button
          v-for="profile in profiles"
          :key="profile.id"
          class="profile-list__item"
          :class="{ 'profile-list__item--active': profile.id === activeProfileId }"
          @click="activeProfileId = profile.id"
        >
          <strong>{{ profile.name || pick('未命名配置组', 'Unnamed profile') }}</strong>
          <span>{{ profile.enabled ? pick('启用中', 'Enabled') : pick('已停用', 'Disabled') }}</span>
        </button>
      </aside>

      <div v-if="activeProfile" class="profile-editor">
        <div class="field-grid">
          <label class="field">
            <span>{{ pick('配置组名称', 'Profile name') }}</span>
            <input v-model="activeProfile.name" type="text" :placeholder="pick('例如：主力 / 备用 / 便宜模型', 'e.g. primary / backup / low-cost')" />
          </label>
          <label class="field">
            <span>{{ pick('API 地址', 'API endpoint') }}</span>
            <input v-model="activeProfile.llm_provider_url" type="url" placeholder="https://api.example.com/v1" />
          </label>
        </div>

        <div class="inline-switches">
          <label><input v-model="activeProfile.enabled" type="checkbox" /> {{ pick('启用该配置组', 'Enable this profile') }}</label>
          <label><input v-model="showApiKey" type="checkbox" /> {{ pick('显示 API Key', 'Show API Key') }}</label>
        </div>

        <section class="editor-section">
          <div class="section-head">
            <div>
              <h3>API Key</h3>
              <p>{{ pick('已保存的 Key 留空即可保留；输入新值才会覆盖。', 'Leave a stored key blank to keep it; only a new value overwrites it.') }}</p>
            </div>
            <div class="section-actions">
              <button class="ghost-btn" @click="addApiKey(activeProfile.id)">{{ pick('新增 Key', 'Add key') }}</button>
            </div>
          </div>
          <div class="item-list">
            <div v-for="(item, index) in activeProfile.api_keys" :key="item.uid" class="item-card">
              <div class="item-card__top">
                <label><input v-model="item.enabled" type="checkbox" /> {{ pick('启用', 'Enable') }}</label>
                <div class="section-actions">
                  <button class="text-btn" @click="promoteApiKey(activeProfile.id, index)">{{ pick('设为首选', 'Set as primary') }}</button>
                  <button class="text-btn text-btn--danger" @click="removeApiKey(activeProfile.id, index)">{{ pick('删除', 'Delete') }}</button>
                </div>
              </div>
              <input
                v-model="item.value"
                :type="showApiKey ? 'text' : 'password'"
                :placeholder="pick('输入 API Key', 'Enter an API Key')"
                @input="handleKeyInput(item)"
              />
              <small v-if="item.hasStoredValue && !item.value.trim()">{{ pick('已保存：', 'Stored: ') }}{{ item.maskedValue || pick('已隐藏', 'hidden') }}{{ pick('，留空会继续保留。', ' — leaving it blank keeps it.') }}</small>
            </div>
          </div>
        </section>

        <section class="editor-section">
          <div class="section-head">
            <div>
              <h3>{{ pick('模型列表', 'Model list') }}</h3>
              <p>{{ pick('支持手动维护，也可以直接从当前配置组拉取模型列表。', 'Maintain it by hand, or fetch the model list from the current profile.') }}</p>
            </div>
            <div class="section-actions">
              <button class="ghost-btn" @click="addModel(activeProfile.id)">{{ pick('新增模型', 'Add model') }}</button>
            </div>
          </div>
          <div class="item-list">
            <div v-for="(item, index) in activeProfile.models" :key="item.uid" class="item-card">
              <div class="item-card__top">
                <label><input v-model="item.enabled" type="checkbox" /> {{ pick('启用', 'Enable') }}</label>
                <div class="section-actions">
                  <button class="text-btn" @click="promoteModel(activeProfile.id, index)">{{ pick('设为首选', 'Set as primary') }}</button>
                  <button class="text-btn text-btn--danger" @click="removeModel(activeProfile.id, index)">{{ pick('删除', 'Delete') }}</button>
                </div>
              </div>
              <input v-model="item.value" type="text" :placeholder="pick('输入模型名称', 'Enter a model name')" />
            </div>
          </div>
        </section>

        <div v-if="healthCheck" class="health-panel">
          <div class="section-head">
            <div>
              <h3>{{ pick('健康检查', 'Health check') }}</h3>
              <p>{{ pick('总体状态：', 'Overall status: ') }}{{ healthStatusLabel(healthCheck.overall_status) }}{{ pick('；推荐动作：', ' — recommended action: ') }}{{ healthCheck.recommended_action || pick('无', 'none') }}</p>
            </div>
          </div>
          <div class="health-overview">
            <article>
              <span>{{ pick('当前配置', 'Current profile') }}</span>
              <strong>{{ healthCheck.current_profile_name || pick('未识别', 'Unknown') }}</strong>
              <small>{{ healthCheck.current_profile_usable ? pick('当前可用', 'Currently usable') : pick('当前不可用或未检查', 'Unusable or unchecked') }}</small>
            </article>
            <article>
              <span>{{ pick('推荐配置', 'Recommended profile') }}</span>
              <strong>{{ healthCheck.recommended_profile_name || pick('暂无', 'None') }}</strong>
              <small>{{ healthCheck.has_usable_profile ? pick('可执行自动切换', 'Auto switch available') : pick('需要先修复 Provider', 'Fix the provider first') }}</small>
            </article>
            <article>
              <span>{{ pick('检查时间', 'Checked at') }}</span>
              <strong>{{ formatCheckedAt(healthCheck.checked_at) }}</strong>
              <small>{{ pick('用于判断最近一次 Provider 抖动', 'Helps spot the most recent provider instability') }}</small>
            </article>
          </div>
          <div class="health-grid">
            <article v-for="profile in healthCheck.profiles" :key="profile.profile_id" class="health-card" :class="`health-card--${profile.status}`">
              <div class="health-card__top">
                <strong>{{ profile.profile_name }}</strong>
                <span class="health-badge" :class="`health-badge--${profile.status}`">{{ healthStatusLabel(profile.status) }}</span>
              </div>
              <span>{{ profile.summary }}</span>
              <small>{{ pick('地址：', 'Endpoint: ') }}{{ profile.llm_provider_url || pick('默认 OpenAI 地址', 'Default OpenAI endpoint') }}</small>
              <small>{{ pick(`模型 ${profile.model_count} 个 · 已检查 Key ${profile.checked_key_count} 个`, `Models: ${profile.model_count} · Keys checked: ${profile.checked_key_count}`) }}</small>
              <div v-if="profile.keys?.length" class="health-key-list">
                <div v-for="key in profile.keys" :key="`${profile.profile_id}-${key.key_index}`" class="health-key" :class="{ 'health-key--ok': key.usable }">
                  <div class="health-key__top">
                    <strong>Key {{ key.key_index }} · {{ key.key_mask }}</strong>
                    <span>{{ keyStateText(key) }}</span>
                  </div>
                  <p>{{ key.detail || keyDiagnosticHint(key) }}</p>
                  <small>{{ keyMetaText(key) }}</small>
                  <small class="health-key__hint">{{ keyRetrySuggestion(key, profile) }}</small>
                </div>
              </div>
              <p v-else class="health-empty">{{ pick('没有可检查的 Key，请补充并保存后再检查。', 'No keys to check — add and save one first.') }}</p>
            </article>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  autoSwitchProvider,
  bumpLLMConfigVersion,
  createOrUpdateLLMConfig,
  getAvailableModels,
  getLLMConfig,
  getProviderHealthCheck,
  type LLMConfig,
  type LLMHealthCheckResponse,
  type LLMProfileItem,
  type LLMProfileItemRead,
  type LLMProviderHealth,
  type LLMProviderKeyHealth,
  type LLMProviderProfile,
  type LLMProviderProfileRead,
} from '@/api/llm'
import { useLocale } from '@/composables/useLocale'

interface EditableProfileItem {
  uid: string
  value: string
  enabled: boolean
  maskedValue?: string
  hasStoredValue: boolean
  retain_existing?: boolean
}

interface EditableProfile {
  id: string
  name: string
  enabled: boolean
  llm_provider_url: string
  api_keys: EditableProfileItem[]
  models: EditableProfileItem[]
}

const profiles = ref<EditableProfile[]>([])
const activeProfileId = ref('')
const saving = ref(false)
const loadingModels = ref(false)
const checkingHealth = ref(false)
const switching = ref(false)
const showApiKey = ref(false)
const healthCheck = ref<LLMHealthCheckResponse | null>(null)
const notice = ref<{ type: 'success' | 'error' | 'info'; message: string } | null>(null)

const { pick } = useLocale()

const activeProfile = computed(() => profiles.value.find(item => item.id === activeProfileId.value) || null)

const makeUid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

const createEditableItem = (seed?: Partial<EditableProfileItem>): EditableProfileItem => ({
  uid: seed?.uid || makeUid(),
  value: seed?.value || '',
  enabled: seed?.enabled ?? true,
  maskedValue: seed?.maskedValue,
  hasStoredValue: seed?.hasStoredValue ?? false,
  retain_existing: seed?.retain_existing,
})

const createEmptyProfile = (): EditableProfile => ({
  id: makeUid(),
  name: '',
  enabled: true,
  llm_provider_url: '',
  api_keys: [createEditableItem()],
  models: [createEditableItem()],
})

const normalizeReadItem = (item: LLMProfileItemRead | LLMProfileItem): EditableProfileItem => {
  const readItem = item as LLMProfileItemRead
  return createEditableItem({
    value: readItem.is_masked ? '' : (item.value || ''),
    enabled: item.enabled,
    maskedValue: readItem.masked_value || undefined,
    hasStoredValue: Boolean(readItem.has_value),
    retain_existing: Boolean(readItem.has_value),
  })
}

const normalizeProfile = (profile: LLMProviderProfileRead): EditableProfile => ({
  id: profile.id || makeUid(),
  name: profile.name || '',
  enabled: profile.enabled,
  llm_provider_url: profile.llm_provider_url || '',
  api_keys: profile.api_keys?.length ? profile.api_keys.map(normalizeReadItem) : [createEditableItem()],
  models: profile.models?.length ? profile.models.map(normalizeReadItem) : [createEditableItem()],
})

const loadConfig = async () => {
  try {
    const config = await getLLMConfig()
    hydrateFromConfig(config)
  } catch (error) {
    profiles.value = [createEmptyProfile()]
    activeProfileId.value = profiles.value[0].id
    setNotice('error', error instanceof Error ? error.message : pick('读取 LLM 配置失败', 'Failed to read the LLM config'))
  }
}

const hydrateFromConfig = (config: LLMConfig) => {
  const normalized = config.llm_provider_profiles?.length
    ? config.llm_provider_profiles.map(normalizeProfile)
    : [createEmptyProfile()]
  profiles.value = normalized
  activeProfileId.value = normalized.find(item => item.enabled)?.id || normalized[0].id
}

const setNotice = (type: 'success' | 'error' | 'info', message: string) => {
  notice.value = { type, message }
}

const countEnabled = (items: EditableProfileItem[]) => items.filter(item => item.enabled && (item.value || item.hasStoredValue)).length

const healthStatusLabel = (status?: string | null) => {
  // 键是后端状态枚举保持原文；值在函数体内经 pick 求值，切换语言即刷新
  const map: Record<string, string> = {
    ok: pick('整体可用', 'All usable'),
    healthy: pick('可用', 'Usable'),
    degraded: pick('部分异常', 'Partially degraded'),
    down: pick('不可用', 'Unusable'),
    no_key: pick('缺少 Key', 'No key'),
  }
  return map[String(status || '')] || String(status || pick('未检查', 'Unchecked'))
}

const formatCheckedAt = (value?: string | null) => {
  if (!value) return pick('未记录', 'Not recorded')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const keyStateText = (key: LLMProviderKeyHealth) => {
  if (!key.enabled) return pick('已停用', 'Disabled')
  if (key.usable) return pick('可用', 'Usable')
  if (key.reachable) return pick('可达但不可用', 'Reachable but unusable')
  return pick('不可达', 'Unreachable')
}

const keyDiagnosticHint = (key: LLMProviderKeyHealth) => {
  if (!key.enabled) return pick('该 Key 已停用，健康检查只作为参考。', 'This key is disabled; the health check is informational only.')
  if (key.usable) return pick('该 Key 可以拉取模型，生成链路可优先使用。', 'This key can fetch models and should be preferred for generation.')
  if (key.status_code === 401 || key.status_code === 403) return pick('鉴权失败，通常是 API Key 填错、过期或权限不足。', 'Authentication failed — the API Key is usually wrong, expired, or lacks permission.')
  if (key.status_code === 429) return pick('Provider 返回限流或额度不足，短时间内可能继续失败。', 'The provider reported rate limiting or insufficient quota; it may keep failing for a while.')
  if (key.status_code && key.status_code >= 500) return pick('Provider 服务端异常，建议切换备用配置组或稍后重试。', 'The provider had a server-side error; switch to a backup profile or retry later.')
  if (!key.reachable) return pick('无法连接 Provider，请检查 base_url、代理、网络或本地 CPA 是否启动。', 'Cannot reach the provider — check base_url, proxy, network, or whether the local CPA is running.')
  return pick('Provider 可达但没有返回可用模型，请检查模型列表和服务兼容性。', 'The provider is reachable but returned no usable models — check the model list and API compatibility.')
}

const keyMetaText = (key: LLMProviderKeyHealth) => [
  key.status_code ? `HTTP ${key.status_code}` : pick('无 HTTP 状态', 'No HTTP status'),
  key.latency_ms !== null && key.latency_ms !== undefined ? `${key.latency_ms} ms` : pick('未记录耗时', 'No latency recorded'),
  pick(`模型 ${key.model_count || 0} 个`, `Models: ${key.model_count || 0}`),
].join(' · ')

const keyRetrySuggestion = (key: LLMProviderKeyHealth, profile: LLMProviderHealth) => {
  if (key.usable) return pick('建议：保留为当前可用 Key。', 'Suggestion: keep this as the active usable key.')
  if (key.status_code === 429) return pick('建议：等待限流恢复，或使用自动切换换到其它可用配置组。', 'Suggestion: wait for the rate limit to reset, or use auto switch to move to another usable profile.')
  if (key.status_code === 401 || key.status_code === 403) return pick('建议：重新粘贴 Key，确认账号额度和模型权限。', 'Suggestion: paste the key again and confirm account quota and model permissions.')
  if (key.status_code && key.status_code >= 500) return pick('建议：先切换备用 Provider，稍后再回测该配置。', 'Suggestion: switch to a backup provider first and retest this profile later.')
  if (!profile.llm_provider_url) return pick('建议：确认默认 OpenAI 地址是否适用于当前 Key。', 'Suggestion: confirm the default OpenAI endpoint works for this key.')
  return pick('建议：检查 base_url 是否以 /v1 结尾，并确认该 Provider 支持 OpenAI 兼容 models 接口。', 'Suggestion: check that base_url ends with /v1 and that the provider exposes an OpenAI-compatible models endpoint.')
}

const addProfile = () => {
  const profile = createEmptyProfile()
  profiles.value.push(profile)
  activeProfileId.value = profile.id
}

const addApiKey = (profileId: string) => {
  const profile = profiles.value.find(item => item.id === profileId)
  if (!profile) return
  profile.api_keys.push(createEditableItem())
}
const removeApiKey = (profileId: string, index: number) => {
  const profile = profiles.value.find(item => item.id === profileId)
  if (!profile) return
  profile.api_keys.splice(index, 1)
  if (!profile.api_keys.length) profile.api_keys.push(createEditableItem())
}
const promoteApiKey = (profileId: string, index: number) => {
  const profile = profiles.value.find(item => item.id === profileId)
  if (!profile) return
  const [item] = profile.api_keys.splice(index, 1)
  profile.api_keys.unshift(item)
}

const addModel = (profileId: string) => {
  const profile = profiles.value.find(item => item.id === profileId)
  if (!profile) return
  profile.models.push(createEditableItem())
}
const removeModel = (profileId: string, index: number) => {
  const profile = profiles.value.find(item => item.id === profileId)
  if (!profile) return
  profile.models.splice(index, 1)
  if (!profile.models.length) profile.models.push(createEditableItem())
}
const promoteModel = (profileId: string, index: number) => {
  const profile = profiles.value.find(item => item.id === profileId)
  if (!profile) return
  const [item] = profile.models.splice(index, 1)
  profile.models.unshift(item)
}

const handleKeyInput = (item: EditableProfileItem) => {
  if (item.value.trim()) {
    item.hasStoredValue = false
    item.retain_existing = false
  } else if (item.maskedValue) {
    item.hasStoredValue = true
    item.retain_existing = true
  }
}

const buildSavePayload = () => {
  const normalizedProfiles: LLMProviderProfile[] = profiles.value.map(profile => ({
    id: profile.id,
    name: profile.name.trim() || undefined,
    enabled: profile.enabled,
    llm_provider_url: profile.llm_provider_url.trim() || undefined,
    api_keys: profile.api_keys.map(item => ({
      value: item.value.trim(),
      enabled: item.enabled,
      retain_existing: !item.value.trim() && item.hasStoredValue,
    })),
    models: profile.models
      .map(item => ({ value: item.value.trim(), enabled: item.enabled }))
      .filter(item => item.value),
  }))

  const active = normalizedProfiles.find(item => item.id === activeProfileId.value) || normalizedProfiles[0]
  const primaryKey = active?.api_keys.find(item => item.enabled && item.value)?.value
  const primaryModel = active?.models.find(item => item.enabled && item.value)?.value

  return {
    llm_provider_profiles: normalizedProfiles,
    llm_provider_url: active?.llm_provider_url,
    llm_provider_api_key: primaryKey,
    llm_provider_model: primaryModel,
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    await createOrUpdateLLMConfig(buildSavePayload())
    const sync = await bumpLLMConfigVersion()
    // The PUT response is not the final authority for masked/defaulted values:
    // read the persisted config back after the backend cache-version bump.
    const verified = await getLLMConfig()
    hydrateFromConfig(verified)
    setNotice('success', pick(`LLM 配置已保存，后端已回读配置 v${sync.version}`, `LLM config saved; the backend re-read config v${sync.version}`))

  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : pick('保存 LLM 配置失败', 'Failed to save the LLM config'))
  } finally {
    saving.value = false
  }
}

const loadModelsForProfile = async (profile: EditableProfile) => {
  const key = profile.api_keys.find(item => item.enabled && item.value.trim())?.value.trim()
  if (!key) {
    setNotice('error', pick('请先填写并启用一个 API Key，再拉取模型', 'Enter and enable an API Key before fetching models'))
    return
  }
  loadingModels.value = true
  try {
    const models = await getAvailableModels({
      llm_provider_url: profile.llm_provider_url.trim() || undefined,
      llm_provider_api_key: key,
    })
    const unique = [...new Set(models.filter(Boolean))]
    profile.models = unique.length
      ? unique.map((model, index) => createEditableItem({ value: model, enabled: index === 0 }))
      : [createEditableItem()]
    setNotice('success', pick(`已拉取 ${unique.length} 个模型`, `Fetched ${unique.length} models`))
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : pick('获取模型列表失败', 'Failed to fetch the model list'))
  } finally {
    loadingModels.value = false
  }
}

const loadModelsForActiveProfile = async () => {
  if (!activeProfile.value) return
  await loadModelsForProfile(activeProfile.value)
}

const runHealthCheck = async () => {
  checkingHealth.value = true
  try {
    healthCheck.value = await getProviderHealthCheck(true)
    setNotice('success', pick('健康检查已完成', 'Health check finished'))
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : pick('执行健康检查失败', 'Failed to run the health check'))
  } finally {
    checkingHealth.value = false
  }
}

const handleAutoSwitch = async () => {
  switching.value = true
  try {
    const result = await autoSwitchProvider()
    healthCheck.value = result.health
    if (result.config) hydrateFromConfig(result.config)
    setNotice('success', result.reason || pick('自动切换完成', 'Auto switch finished'))
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : pick('自动切换失败', 'Auto switch failed'))
  } finally {
    switching.value = false
  }
}

onMounted(() => {
  void loadConfig()
})
</script>

<style scoped>
.llm-settings-root {
  display: grid;
  gap: 16px;
}
.llm-toolbar,
.summary-grid,
.profiles-layout,
.field-grid,
.inline-switches,
.section-head,
.section-actions,
.item-card__top,
.health-card__top,
.health-key__top,
.health-grid {
  display: flex;
  gap: 12px;
}
.llm-toolbar,
.editor-section,
.summary-card,
.profile-list,
.profile-editor,
.health-card,
.notice {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: #fff;
}
.llm-toolbar {
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 18px;
  flex-wrap: wrap;
}
.llm-toolbar h2 { margin: 0; font-size: 1.05rem; color: #0f172a; }
.llm-toolbar p { margin: 6px 0 0; font-size: 0.84rem; color: #64748b; }
.llm-toolbar__actions { display: flex; gap: 8px; flex-wrap: wrap; }
.primary-btn,
.ghost-btn,
.text-btn,
.profile-list__item {
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  font-weight: 700;
}
.primary-btn { background: #0f172a; color: #fff; border-color: #0f172a; padding: 10px 14px; }
.ghost-btn { padding: 10px 14px; }
.text-btn { padding: 6px 10px; font-size: 0.78rem; }
.text-btn--danger { color: #b91c1c; }
.notice { padding: 12px 14px; font-size: 0.84rem; }
.notice--success { border-color: #86efac; background: #f0fdf4; color: #166534; }
.notice--error { border-color: #fecaca; background: #fef2f2; color: #991b1b; }
.notice--info { border-color: #bfdbfe; background: #eff6ff; color: #1d4ed8; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.summary-card { padding: 14px 16px; display: grid; gap: 6px; }
.summary-card span { font-size: 0.78rem; color: #64748b; }
.summary-card strong { font-size: 0.88rem; color: #0f172a; word-break: break-word; }
.profiles-layout { align-items: flex-start; }
.profile-list { width: 220px; padding: 10px; display: grid; gap: 8px; }
.profile-list__item { padding: 12px; text-align: left; display: grid; gap: 4px; }
.profile-list__item--active { background: #eef2ff; border-color: #a5b4fc; }
.profile-list__item span { font-size: 0.78rem; color: #64748b; }
.profile-editor { flex: 1; min-width: 0; padding: 16px; display: grid; gap: 16px; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.field { display: grid; gap: 8px; font-size: 0.84rem; color: #475569; }
.field input,
.item-card input {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 0.9rem;
}
.inline-switches { flex-wrap: wrap; font-size: 0.84rem; color: #475569; }
.inline-switches label,
.item-card__top label { display: inline-flex; align-items: center; gap: 8px; }
.editor-section { padding: 14px; display: grid; gap: 12px; }
.section-head { justify-content: space-between; align-items: center; flex-wrap: wrap; }
.section-head h3 { margin: 0; font-size: 0.95rem; color: #0f172a; }
.section-head p { margin: 4px 0 0; font-size: 0.8rem; color: #64748b; }
.section-actions { flex-wrap: wrap; }
.item-list { display: grid; gap: 10px; }
.item-card { border: 1px solid #e2e8f0; border-radius: 14px; padding: 12px; display: grid; gap: 8px; }
.item-card small { color: #64748b; font-size: 0.76rem; }
.health-panel { display: grid; gap: 12px; }
.health-overview { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.health-overview article { border: 1px solid #e2e8f0; border-radius: 14px; padding: 12px; background: #f8fafc; display: grid; gap: 5px; }
.health-overview span { color: #64748b; font-size: 0.76rem; }
.health-overview strong { color: #0f172a; font-size: 0.9rem; word-break: break-word; }
.health-overview small { color: #64748b; line-height: 1.5; }
.health-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.health-card { padding: 12px; display: grid; gap: 6px; }
.health-card--healthy { border-color: #86efac; background: #f0fdf4; }
.health-card--degraded { border-color: #fde68a; background: #fffbeb; }
.health-card--down,
.health-card--no_key { border-color: #fecaca; background: #fef2f2; }
.health-card__top,
.health-key__top { justify-content: space-between; align-items: center; }
.health-badge { display: inline-flex; align-items: center; min-height: 22px; padding: 0 8px; border-radius: 999px; background: #e2e8f0; color: #334155; font-size: 0.72rem; font-weight: 800; }
.health-badge--healthy { background: #dcfce7; color: #166534; }
.health-badge--degraded { background: #fef3c7; color: #92400e; }
.health-badge--down,
.health-badge--no_key { background: #fee2e2; color: #991b1b; }
.health-card span,
.health-card small { color: #475569; font-size: 0.8rem; }
.health-key-list { display: grid; gap: 8px; margin-top: 6px; }
.health-key { border: 1px solid #e2e8f0; border-radius: 12px; padding: 10px; background: rgba(255, 255, 255, 0.82); display: grid; gap: 5px; }
.health-key--ok { border-color: #bbf7d0; background: #f7fee7; }
.health-key__top strong { font-size: 0.82rem; color: #0f172a; }
.health-key__top span { color: #475569; font-weight: 800; font-size: 0.76rem; }
.health-key p,
.health-empty { margin: 0; color: #334155; line-height: 1.55; font-size: 0.8rem; }
.health-key__hint { color: #0f172a !important; font-weight: 700; }
@media (max-width: 960px) {
  .summary-grid,
  .field-grid,
  .health-overview,
  .health-grid { grid-template-columns: 1fr; }
  .profiles-layout { flex-direction: column; }
  .profile-list { width: 100%; }
}
</style>
