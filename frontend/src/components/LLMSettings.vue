<template>
  <div class="llm-settings-root">
    <section class="llm-toolbar">
      <div>
        <h2>LLM 配置</h2>
        <p>统一管理接口地址、API Key、模型列表，并支持健康检查和自动切换。</p>
      </div>
      <div class="llm-toolbar__actions">
        <button class="primary-btn" :disabled="saving" @click="handleSave">{{ saving ? '保存中...' : '保存配置' }}</button>
        <button class="ghost-btn" @click="addProfile">新增配置组</button>
        <button class="ghost-btn" :disabled="loadingModels" @click="loadModelsForActiveProfile">{{ loadingModels ? '拉取中...' : '拉取模型' }}</button>
        <button class="ghost-btn" :disabled="checkingHealth" @click="runHealthCheck">{{ checkingHealth ? '检查中...' : '健康检查' }}</button>
        <button class="ghost-btn" :disabled="switching" @click="handleAutoSwitch">{{ switching ? '切换中...' : '自动切换' }}</button>
      </div>
    </section>

    <div v-if="notice" class="notice" :class="`notice--${notice.type}`">{{ notice.message }}</div>

    <section class="summary-grid">
      <article class="summary-card">
        <span>当前激活组</span>
        <strong>{{ activeProfile?.name || '未命名配置组' }}</strong>
      </article>
      <article class="summary-card">
        <span>当前地址</span>
        <strong>{{ activeProfile?.llm_provider_url || '未填写' }}</strong>
      </article>
      <article class="summary-card">
        <span>启用 Key</span>
        <strong>{{ countEnabled(activeProfile?.api_keys || []) }}</strong>
      </article>
      <article class="summary-card">
        <span>启用模型</span>
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
          <strong>{{ profile.name || '未命名配置组' }}</strong>
          <span>{{ profile.enabled ? '启用中' : '已停用' }}</span>
        </button>
      </aside>

      <div v-if="activeProfile" class="profile-editor">
        <div class="field-grid">
          <label class="field">
            <span>配置组名称</span>
            <input v-model="activeProfile.name" type="text" placeholder="例如：主力 / 备用 / 便宜模型" />
          </label>
          <label class="field">
            <span>API 地址</span>
            <input v-model="activeProfile.llm_provider_url" type="url" placeholder="https://api.example.com/v1" />
          </label>
        </div>

        <div class="inline-switches">
          <label><input v-model="activeProfile.enabled" type="checkbox" /> 启用该配置组</label>
          <label><input v-model="showApiKey" type="checkbox" /> 显示 API Key</label>
        </div>

        <section class="editor-section">
          <div class="section-head">
            <div>
              <h3>API Key</h3>
              <p>已保存的 Key 留空即可保留；输入新值才会覆盖。</p>
            </div>
            <div class="section-actions">
              <button class="ghost-btn" @click="addApiKey(activeProfile.id)">新增 Key</button>
            </div>
          </div>
          <div class="item-list">
            <div v-for="(item, index) in activeProfile.api_keys" :key="item.uid" class="item-card">
              <div class="item-card__top">
                <label><input v-model="item.enabled" type="checkbox" /> 启用</label>
                <div class="section-actions">
                  <button class="text-btn" @click="promoteApiKey(activeProfile.id, index)">设为首选</button>
                  <button class="text-btn text-btn--danger" @click="removeApiKey(activeProfile.id, index)">删除</button>
                </div>
              </div>
              <input
                v-model="item.value"
                :type="showApiKey ? 'text' : 'password'"
                placeholder="输入 API Key"
                @input="handleKeyInput(item)"
              />
              <small v-if="item.hasStoredValue && !item.value.trim()">已保存：{{ item.maskedValue || '已隐藏' }}，留空会继续保留。</small>
            </div>
          </div>
        </section>

        <section class="editor-section">
          <div class="section-head">
            <div>
              <h3>模型列表</h3>
              <p>支持手动维护，也可以直接从当前配置组拉取模型列表。</p>
            </div>
            <div class="section-actions">
              <button class="ghost-btn" @click="addModel(activeProfile.id)">新增模型</button>
            </div>
          </div>
          <div class="item-list">
            <div v-for="(item, index) in activeProfile.models" :key="item.uid" class="item-card">
              <div class="item-card__top">
                <label><input v-model="item.enabled" type="checkbox" /> 启用</label>
                <div class="section-actions">
                  <button class="text-btn" @click="promoteModel(activeProfile.id, index)">设为首选</button>
                  <button class="text-btn text-btn--danger" @click="removeModel(activeProfile.id, index)">删除</button>
                </div>
              </div>
              <input v-model="item.value" type="text" placeholder="输入模型名称" />
            </div>
          </div>
        </section>

        <div v-if="healthCheck" class="health-panel">
          <div class="section-head">
            <div>
              <h3>健康检查</h3>
              <p>总体状态：{{ healthCheck.overall_status }}；推荐动作：{{ healthCheck.recommended_action || '无' }}</p>
            </div>
          </div>
          <div class="health-grid">
            <article v-for="profile in healthCheck.profiles" :key="profile.profile_id" class="health-card">
              <strong>{{ profile.profile_name }}</strong>
              <span>{{ profile.summary }}</span>
              <small>状态：{{ profile.status }} · 可用模型 {{ profile.model_count }} 个</small>
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
  createOrUpdateLLMConfig,
  getAvailableModels,
  getLLMConfig,
  getProviderHealthCheck,
  type LLMConfig,
  type LLMHealthCheckResponse,
  type LLMProfileItem,
  type LLMProfileItemRead,
  type LLMProviderProfile,
  type LLMProviderProfileRead,
} from '@/api/llm'

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
    setNotice('error', error instanceof Error ? error.message : '读取 LLM 配置失败')
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
    const saved = await createOrUpdateLLMConfig(buildSavePayload())
    hydrateFromConfig(saved)
    setNotice('success', 'LLM 配置已保存')
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : '保存 LLM 配置失败')
  } finally {
    saving.value = false
  }
}

const loadModelsForProfile = async (profile: EditableProfile) => {
  const key = profile.api_keys.find(item => item.enabled && item.value.trim())?.value.trim()
  if (!key) {
    setNotice('error', '请先填写并启用一个 API Key，再拉取模型')
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
    setNotice('success', `已拉取 ${unique.length} 个模型`)
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : '获取模型列表失败')
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
    setNotice('success', '健康检查已完成')
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : '执行健康检查失败')
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
    setNotice('success', result.reason || '自动切换完成')
  } catch (error) {
    setNotice('error', error instanceof Error ? error.message : '自动切换失败')
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
.health-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.health-card { padding: 12px; display: grid; gap: 6px; }
.health-card span,
.health-card small { color: #475569; font-size: 0.8rem; }
@media (max-width: 960px) {
  .summary-grid,
  .field-grid,
  .health-grid { grid-template-columns: 1fr; }
  .profiles-layout { flex-direction: column; }
  .profile-list { width: 100%; }
}
</style>
