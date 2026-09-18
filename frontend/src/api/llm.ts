import { API_BASE_URL, API_PREFIX } from '@/api/config'

const LLM_BASE = `${API_BASE_URL}${API_PREFIX}/llm-config`

export interface LLMConfig {
  user_id: number
  llm_provider_url: string | null
  llm_provider_model: string | null
  llm_provider_api_key_masked: string | null
  llm_provider_api_key_configured: boolean
  llm_provider_profiles?: LLMProviderProfileRead[] | null
}

interface LLMApiErrorDetail {
  status: number
  message: string
  code?: string
  hint?: string
  rootCause?: string
}

export class LLMApiError extends Error {
  status: number
  detail: LLMApiErrorDetail

  constructor(detail: LLMApiErrorDetail) {
    super(detail.message)
    this.name = 'LLMApiError'
    this.status = detail.status
    this.detail = detail
  }
}

export interface LLMProfileItem {
  value: string
  enabled: boolean
  retain_existing?: boolean
}

export interface LLMProfileItemRead {
  value: string
  enabled: boolean
  masked_value?: string | null
  has_value: boolean
  is_masked: boolean
}

export interface LLMProviderProfile {
  id?: string
  name?: string
  enabled: boolean
  llm_provider_url?: string
  api_keys: LLMProfileItem[]
  models: LLMProfileItem[]
}

export interface LLMProviderProfileRead {
  id?: string
  name?: string
  enabled: boolean
  llm_provider_url?: string
  api_keys: LLMProfileItemRead[]
  models: LLMProfileItem[]
}

export interface LLMConfigCreate {
  llm_provider_url?: string
  llm_provider_api_key?: string
  llm_provider_model?: string
  llm_provider_profiles?: LLMProviderProfile[]
}

export interface LLMProviderKeyHealth {
  key_index: number
  key_mask: string
  enabled: boolean
  reachable: boolean
  usable: boolean
  model_count: number
  status_code?: number | null
  latency_ms?: number | null
  detail?: string | null
}

export interface LLMProviderHealth {
  profile_id: string
  profile_name: string
  enabled: boolean
  llm_provider_url?: string | null
  status: 'healthy' | 'degraded' | 'down' | 'no_key'
  summary: string
  reachable: boolean
  usable: boolean
  model_count: number
  checked_key_count: number
  keys: LLMProviderKeyHealth[]
}

export interface LLMHealthCheckResponse {
  checked_at: string
  overall_status: 'ok' | 'degraded' | 'down'
  has_usable_profile: boolean
  recommended_profile_id?: string | null
  recommended_profile_name?: string | null
  current_profile_id?: string | null
  current_profile_name?: string | null
  current_profile_usable?: boolean | null
  recommended_action?: string | null
  profiles: LLMProviderHealth[]
}

export interface LLMAutoSwitchResponse {
  switched: boolean
  reason: string
  switch_basis?: string | null
  previous_profile_id?: string | null
  previous_profile_name?: string | null
  active_profile_id?: string | null
  active_profile_name?: string | null
  health: LLMHealthCheckResponse
  config?: LLMConfig | null
}

const getHeaders = () => ({
  'Content-Type': 'application/json',
})

const parseLLMApiError = async (response: Response, fallbackMessage: string): Promise<LLMApiError> => {
  let payload: any = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  const rawDetail = payload?.detail
  const detail = rawDetail && typeof rawDetail === 'object' ? rawDetail : null
  const message =
    (typeof rawDetail === 'string' && rawDetail.trim()) ||
    detail?.message ||
    (typeof payload?.message === 'string' && payload.message.trim()) ||
    fallbackMessage

  return new LLMApiError({
    status: response.status,
    message,
    code: detail?.code,
    hint: detail?.hint,
    rootCause: detail?.rootCause || detail?.root_cause,
  })
}

export const getLLMConfig = async (): Promise<LLMConfig> => {
  const response = await fetch(LLM_BASE, {
    method: 'GET',
    headers: getHeaders(),
  })
  if (!response.ok) {
    throw await parseLLMApiError(response, '读取 LLM 配置失败')
  }
  return response.json()
}

export const createOrUpdateLLMConfig = async (config: LLMConfigCreate): Promise<LLMConfig> => {
  const response = await fetch(LLM_BASE, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(config),
  })
  if (!response.ok) {
    throw await parseLLMApiError(response, '保存 LLM 配置失败')
  }
  return response.json()
}

export const deleteLLMConfig = async (): Promise<void> => {
  const response = await fetch(LLM_BASE, {
    method: 'DELETE',
    headers: getHeaders(),
  })
  if (!response.ok) {
    throw await parseLLMApiError(response, '删除 LLM 配置失败')
  }
}

export interface ModelListRequest {
  llm_provider_url?: string
  llm_provider_api_key: string
}

export const getAvailableModels = async (request: ModelListRequest): Promise<string[]> => {
  const response = await fetch(`${LLM_BASE}/models`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw await parseLLMApiError(response, '获取模型列表失败')
  }
  return response.json()
}

export const getProviderHealthCheck = async (includeDisabled = true): Promise<LLMHealthCheckResponse> => {
  const query = includeDisabled ? '?include_disabled=true' : '?include_disabled=false'
  const response = await fetch(`${LLM_BASE}/health-check${query}`, {
    method: 'GET',
    headers: getHeaders(),
  })
  if (!response.ok) {
    throw await parseLLMApiError(response, '执行健康检查失败')
  }
  return response.json()
}

export const autoSwitchProvider = async (): Promise<LLMAutoSwitchResponse> => {
  const response = await fetch(`${LLM_BASE}/auto-switch`, {
    method: 'POST',
    headers: getHeaders(),
  })
  if (!response.ok) {
    throw await parseLLMApiError(response, '自动切换配置失败')
  }
  return response.json()
}
