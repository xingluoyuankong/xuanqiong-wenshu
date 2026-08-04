// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
// Phase 5.2 重构：此文件现为 re-export 桥接文件
// 类型定义已提取到 @/api/types/novel
// API 客户端代码已提取到 @/api/novel-client
// 所有从 @/api/novel 导入的代码无需修改，此文件 re-export 全部内容

// re-export 所有类型定义
export * from '@/api/types/novel'

// re-export API 客户端类和错误处理
export { ApiError, NovelAPI, OptimizerAPI, AnalyticsAPI, TokenBudgetAPI } from '@/api/novel-client'
export type { ResearchConfig, ResearchArtifact, ResearchRunStatus } from '@/api/types/novel'


// ====== Writing Skills API ======
export interface WritingSkillItem {
  id: number
  name: string
  description: string
  category: string
  installed: boolean
  config?: Record<string, unknown>
}

export interface WritingSkillExecutionResult {
  success: boolean
  message: string
  data?: unknown
}

export const WritingSkillsAPI = {
  async getSkillCatalog(): Promise<WritingSkillItem[]> {
    const response = await fetch(`${API_BASE_URL}/api/writing-skills/skills/catalog`)
    if (!response.ok) throw new Error("获取技能目录失败")
    return response.json()
  },
  async installSkill(skillId: number, options?: Record<string, unknown>): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/writing-skills/skills/${skillId}/install`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options || {}),
    })
    if (!response.ok) throw new Error("安装技能失败")
  },
  async uninstallSkill(skillId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/writing-skills/skills/${skillId}/uninstall`, {
      method: "POST",
    })
    if (!response.ok) throw new Error("卸载技能失败")
  },
  async executeSkill(skillId: number, options?: Record<string, unknown>): Promise<WritingSkillExecutionResult> {
    const response = await fetch(`${API_BASE_URL}/api/writing-skills/skills/${skillId}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options || {}),
    })
    if (!response.ok) throw new Error("执行技能失败")
    return response.json()
  },
}


// ====== Foreshadowing API ======
export interface ForeshadowingItem {
  id: number
  name: string
  description: string
  status: string
  planted_chapter?: number
  expected_reveal_chapter?: number
}

export interface ForeshadowingReminderItem {
  id: number
  foreshadowing_id: number
  chapter_number: number
  summary: string
}

export interface ForeshadowingAnalysisResponse {
  items: ForeshadowingItem[]
  summary: string
}

export const ForeshadowingAPI = {
  async getForeshadowing(projectId: string): Promise<ForeshadowingAnalysisResponse> {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/foreshadowings`)
    if (!response.ok) throw new Error("获取伏笔数据失败")
    return response.json()
  },
  async getReminders(projectId: string, chapterNumber: number): Promise<ForeshadowingReminderItem[]> {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/foreshadowings/reminders?chapter_number=${chapterNumber}`)
    if (!response.ok) throw new Error("获取伏笔提醒失败")
    return response.json()
  },
}

// ====== Clue Tracker API ======
export interface ClueItem {
  id: number
  name: string
  description: string
  status: string
  category: string
}

export const ClueTrackerAPI = {
  async getClues(projectId: string): Promise<ClueItem[]> {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/clues`)
    if (!response.ok) throw new Error("获取线索数据失败")
    return response.json()
  },
}

// ====== Knowledge Graph API ======
export const KnowledgeGraphAPI = {
  async getGraph(projectId: string): Promise<unknown> {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/knowledge-graph`)
    if (!response.ok) throw new Error("获取知识图谱失败")
    return response.json()
  },
}


// ====== Constitution API ======
export const ConstitutionAPI = {
  async getConstitution(projectId: string): Promise<Record<string, unknown>> {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/constitution`)
    if (!response.ok) throw new Error("获取小说宪法失败")
    return response.json()
  },
  async updateConstitution(projectId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
    const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/constitution`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!response.ok) throw new Error("更新小说宪法失败")
    return response.json()
  },
}
