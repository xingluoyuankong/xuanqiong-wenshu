// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
// Phase 5.2 重构：此文件现为 re-export 桥接文件
// 类型定义已提取到 @/api/types/novel
// API 客户端代码已提取到 @/api/novel-client
// 所有从 @/api/novel 导入的代码无需修改，此文件 re-export 全部内容

// re-export 所有类型定义
import { buildAuthHeaders } from '@/stores/auth'
const authFetch = (input: RequestInfo | URL, init: RequestInit = {}) => fetch(input, { ...init, headers: buildAuthHeaders(init.headers) })
export * from '@/api/types/novel'

import { API_BASE_URL } from '@/api/config'
import type { ForeshadowingItem, ForeshadowingListResponse, ForeshadowingReminderItem } from '@/api/types/novel'

// re-export API 客户端类和错误处理
export { ApiError, NovelAPI, OptimizerAPI, AnalyticsAPI, TokenBudgetAPI } from '@/api/novel-client'
export type { ResearchConfig, ResearchArtifact, ResearchRunStatus } from '@/api/types/novel'


// ====== Writing Skills API ======
export interface WritingSkillItem {
  id: number
  name: string
  description?: string | null
  overview?: string | null
  category?: string | null
  version?: string
  author?: string | null
  source_url?: string | null
  use_cases?: string[]
  input_guide?: string | null
  output_format?: string[]
  tips?: string[]
  example_prompt?: string | null
  tags?: string[]
  enabled?: boolean
  installed?: boolean
  installed_at?: string | null
  config?: Record<string, unknown>
}

export interface WritingSkillInstallRequest {
  name: string
  description?: string | null
  category?: string | null
  version?: string
  author?: string | null
  source_url?: string | null
}

export interface WritingSkillExecutionRequest {
  prompt: string
  project_id?: string
  chapter_number?: number
}

export interface WritingSkillExecutionResult {
  skill_id: string
  skill_name: string
  project_id?: string | null
  chapter_number?: number | null
  result: unknown
  executed_at: string
}

export const WritingSkillsAPI = {
  async getSkillCatalog(): Promise<WritingSkillItem[]> {
    const response = await authFetch(`${API_BASE_URL}/api/writing-skills/skills/catalog`)
    if (!response.ok) throw new Error('获取技能目录失败')
    return response.json() as Promise<WritingSkillItem[]>
  },
  async installSkill(skillId: number, options: WritingSkillInstallRequest): Promise<WritingSkillItem> {
    const response = await authFetch(`${API_BASE_URL}/api/writing-skills/skills/${skillId}/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    })
    if (!response.ok) throw new Error('安装技能失败')
    return response.json() as Promise<WritingSkillItem>
  },
  async uninstallSkill(skillId: number): Promise<{ status: string; message: string }> {
    const response = await authFetch(`${API_BASE_URL}/api/writing-skills/skills/${skillId}/uninstall`, {
      method: 'DELETE',
    })
    if (!response.ok) throw new Error('卸载技能失败')
    return response.json() as Promise<{ status: string; message: string }>
  },
  async executeSkill(skillId: number, options: WritingSkillExecutionRequest): Promise<WritingSkillExecutionResult> {
    const response = await authFetch(`${API_BASE_URL}/api/writing-skills/skills/${skillId}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    })
    if (!response.ok) throw new Error('执行技能失败')
    return response.json() as Promise<WritingSkillExecutionResult>
  },
}

// ====== Foreshadowing API ======
export interface ForeshadowingReminderListResponse {
  total: number
  data: ForeshadowingReminderItem[]
}

export interface ForeshadowingAnalysisResponse {
  total_foreshadowings: number
  resolved_count: number
  unresolved_count: number
  abandoned_count: number
  avg_resolution_distance: number | null
  unresolved_ratio: number | null
  overall_quality_score: number | null
  recommendations: string[]
}

export const ForeshadowingAPI = {
  async getForeshadowings(projectId: string): Promise<ForeshadowingListResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/foreshadowings`)
    if (!response.ok) throw new Error('获取伏笔数据失败')
    return response.json() as Promise<ForeshadowingListResponse>
  },
  async getReminders(projectId: string): Promise<ForeshadowingReminderListResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/foreshadowings/reminders`)
    if (!response.ok) throw new Error('获取伏笔提醒失败')
    return response.json() as Promise<ForeshadowingReminderListResponse>
  },
  async getAnalysis(projectId: string): Promise<ForeshadowingAnalysisResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/foreshadowings/analysis`)
    if (!response.ok) throw new Error('获取伏笔分析失败')
    return response.json() as Promise<ForeshadowingAnalysisResponse>
  },
}

// ====== Clue Tracker API ======
export interface ClueItem {
  id: number
  project_id: string
  name: string
  clue_type: string
  description: string | null
  importance: number
  planted_chapter: number | null
  resolution_chapter: number | null
  status: string
  is_red_herring: boolean
  red_herring_explanation: string | null
  clue_content: string | null
  hint_level: number
  design_intent: string | null
  created_at: string
  updated_at: string
}

export interface ClueThread {
  thread_type: string
  clue_count: number
  clue_ids: number[]
}

export interface ClueThreadAnalysisResponse {
  project_id: string
  total_clues: number
  type_counts: Record<string, number>
  status_counts: Record<string, number>
  red_herring_count: number
  unresolved_count: number
  threads: ClueThread[]
}

export interface ClueOverviewResponse {
  project_id: string
  clues: ClueItem[]
  analysis: ClueThreadAnalysisResponse
  sync: Record<string, unknown>
}

export const ClueTrackerAPI = {
  async getOverview(projectId: string): Promise<ClueOverviewResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/clues/overview`)
    if (!response.ok) throw new Error('获取线索一致性快照失败')
    return response.json() as Promise<ClueOverviewResponse>
  },
  async getProjectClues(projectId: string): Promise<ClueItem[]> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/clues`)
    if (!response.ok) throw new Error('获取线索数据失败')
    return response.json() as Promise<ClueItem[]>
  },
  async analyzeClueThreads(projectId: string): Promise<ClueThreadAnalysisResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/clues/threads`)
    if (!response.ok) throw new Error('分析线索线程失败')
    return response.json() as Promise<ClueThreadAnalysisResponse>
  },
}

// ====== Knowledge Graph API ======
export interface KnowledgeGraphNode {
  id: number
  project_id: string
  name: string
  role_type: string | null
  description: string | null
  traits: string[]
  goals: string[]
  fears: string[]
  background: string | null
  status: string | null
  location: string | null
  emotional_state: string | null
  blueprint_character_id: number | null
  extra: Record<string, unknown> | null
  fact_source: string | null
  fact_source_label: string | null
  first_chapter: number | null
  latest_chapter: number | null
  confidence: number | null
  lifecycle: string | null
  relationship_count: number | null
  created_at: string
  updated_at: string
}

export interface KnowledgeGraphEdge {
  id: number
  project_id: string
  source_id: number
  target_id: number
  source_name: string | null
  target_name: string | null
  event_type: string
  description: string | null
  chapter_number: number | null
  scene_number: number | null
  timestamp: string | null
  order_index: number | null
  causality: string | null
  importance: number | null
  emotional_impact: string | null
  plot_advancement: string | null
  extra: Record<string, unknown> | null
  fact_source: string | null
  fact_source_label: string | null
  source_chapter: number | null
  latest_chapter: number | null
  confidence: number | null
  created_at: string
  updated_at: string
}

export interface KnowledgeGraphResponse {
  project_id: string
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
  node_count: number
  edge_count: number
}

export interface PlotThreadEvent {
  description?: string
  [key: string]: unknown
}

export interface PlotThread {
  thread_id: string
  title: string
  characters: string[]
  events: PlotThreadEvent[]
  chapter_range: [number, number]
}

export interface PlotThreadAnalysisResponse {
  project_id: string
  threads: PlotThread[]
  thread_count: number
}

export interface KnowledgeGraphOverviewResponse {
  project_id: string
  graph: KnowledgeGraphResponse
  threads: PlotThread[]
  thread_count: number
  sync: Record<string, unknown>
}

export const KnowledgeGraphAPI = {
  async getOverview(projectId: string): Promise<KnowledgeGraphOverviewResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/knowledge-graph/overview`)
    if (!response.ok) throw new Error('获取知识图谱一致性快照失败')
    return response.json() as Promise<KnowledgeGraphOverviewResponse>
  },
  async getFullGraph(projectId: string): Promise<KnowledgeGraphResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/knowledge-graph`)
    if (!response.ok) throw new Error('获取知识图谱失败')
    return response.json() as Promise<KnowledgeGraphResponse>
  },
  async analyzePlotThreads(projectId: string): Promise<PlotThreadAnalysisResponse> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/knowledge-graph/threads`)
    if (!response.ok) throw new Error('分析剧情线失败')
    const payload: unknown = await response.json()
    if (Array.isArray(payload)) {
      return { project_id: projectId, threads: payload as PlotThread[], thread_count: payload.length }
    }
    return payload as PlotThreadAnalysisResponse
  },
}

// ====== Constitution API ======
export const ConstitutionAPI = {
  async getConstitution(projectId: string): Promise<Record<string, unknown>> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/constitution`)
    if (!response.ok) throw new Error("获取小说宪法失败")
    return response.json()
  },
  async updateConstitution(projectId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
    const response = await authFetch(`${API_BASE_URL}/api/projects/${projectId}/constitution`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!response.ok) throw new Error("更新小说宪法失败")
    return response.json()
  },
}
