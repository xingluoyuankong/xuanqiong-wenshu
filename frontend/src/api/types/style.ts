/**
 * Style-related type definitions for novel-client.ts
 * Extracted to replace 'any' types with proper interfaces
 */

/** Style summary content */
export interface StyleSummaryContent {
  narrative?: string
  rhythm?: string
  vocabulary?: string
  dialogue?: string
  description?: string
  tone?: string
  pacing?: string
  vocabulary_level?: string
  sentence_structure?: string
  themes?: string[]
  techniques?: string[]
}

/** Style summary from extraction */
export interface StyleSummary {
  summary?: StyleSummaryContent
  tone?: string
  pacing?: string
  vocabulary_level?: string
  sentence_structure?: string
  themes?: string[]
  techniques?: string[]
  description?: string
}

/** Style source */
export interface StyleSourceExtra {
  batch_label?: string
  file_name?: string
  import_mode?: string
  import_mode_label?: string
  [key: string]: unknown
}

export interface StyleSource {
  id: string
  name?: string
  title?: string
  type?: string
  source_type?: string
  mode?: string
  content?: string
  char_count?: number
  extra?: StyleSourceExtra
  created_at?: string
  updated_at?: string
}

/** Style profile */
export interface StyleProfile {
  id: string
  name: string
  description?: string
  summary?: StyleSummaryContent
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

/** Outline alternative */
export interface OutlineAlternative {
  id: number
  title: string
  description: string
  content?: string
  evolution_type: string
  score: number
  new_outline: Record<string, unknown>
  changes: string
}

/** Outline evolution result */
export interface OutlineEvolutionResult {
  alternatives: OutlineAlternative[]
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
  alternatives: OutlineAlternative[]
  chapter_number: number
  total: number
}

/** Outline history entry */
export interface OutlineHistoryEntry {
  id: string
  version: number
  created_at: string
  content?: string
}

/** Outline history */
export interface OutlineHistory {
  history: OutlineHistoryEntry[]
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
