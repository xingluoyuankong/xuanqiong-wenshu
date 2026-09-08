/**
 * Style-related type definitions for novel-client.ts
 * Extracted to replace 'any' types with proper interfaces
 */

/** Style summary from extraction */
export interface StyleSummary {
  tone?: string
  pacing?: string
  vocabulary_level?: string
  sentence_structure?: string
  themes?: string[]
  techniques?: string[]
  description?: string
}

/** Style source */
export interface StyleSource {
  id: string
  name: string
  type: string
  content?: string
  created_at?: string
  updated_at?: string
}

/** Style profile */
export interface StyleProfile {
  id: string
  name: string
  description?: string
  settings: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

/** Style library response */
export interface StyleLibrary {
  sources: StyleSource[]
  profiles: StyleProfile[]
  project_active_profile: StyleProfile | null
  global_active_profile: StyleProfile | null
}

/** Memory operation result */
export interface MemoryOperationResult {
  project_id: string
  result: {
    status: string
    message?: string
    affected_items?: number
  }
}

/** Outline evolution result */
export interface OutlineEvolutionResult {
  alternatives: Array<{
    id: string
    title?: string
    content?: string
    score?: number
  }>
  batch_id: string
  chapter_number: number
}

/** Outline update result */
export interface OutlineUpdateResult {
  success: boolean
  message: string
  updated_outline: {
    id?: string
    content?: string
    version?: number
  }
}

/** Outline alternatives */
export interface OutlineAlternatives {
  alternatives: Array<{
    id: string
    title?: string
    content?: string
  }>
  chapter_number: number
  total: number
}

/** Outline history */
export interface OutlineHistory {
  history: Array<{
    id: string
    version: number
    created_at: string
    content?: string
  }>
  total: number
}

/** Patch operations */
export interface PatchOperations {
  operations: Array<{
    op: string
    path: string
    value?: unknown
  }>
}
