// AIMETA P=小说类型定义|R=类型导出|NR=不含API逻辑|E=types:novel|X=internal|D=none|S=none|RD=./README.ai
// Phase 5.2 重构：从 novel.ts 提取的所有 TypeScript 类型定义
// 此文件只包含 interface/type/class ApiError，不包含任何 API 调用逻辑

// ============================================================================
// 错误处理类型（ApiError class 定义在 novel-client.ts 中，因为其 constructor 依赖 formatApiErrorMessage）
// ============================================================================

export interface ApiErrorDetail {
  status: number
  message: string
  code?: string
  hint?: string
  rootCause?: string
  requestId?: string
  retryable?: boolean
  responseSnippet?: string
  rejectionSummary?: Record<string, any>
  missingChapters?: number[]
}

// ============================================================================
// 核心小说类型
// ============================================================================

export interface NovelProject {
  id: string
  title: string
  initial_prompt: string
  blueprint?: Blueprint
  chapters: Chapter[]
  conversation_history: ConversationMessage[]
  generation_runtime?: GenerationRuntime
  workspace_summary?: WorkspaceSummary
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface WorldSetting {
  core_rules?: string
  era?: string
  time_period?: string
  atmosphere?: string
  tone?: string
  era_background?: unknown
  world_structure?: unknown
  power_system?: unknown
  survival_system?: unknown
  life_system?: unknown
  culture_system?: unknown
  civilization_system?: unknown
  economy_system?: unknown
  social_structure?: unknown
  technology_system?: unknown
  resource_system?: unknown
  belief_system?: unknown
  geography_system?: unknown
  faction_order?: unknown
  system_blueprint?: Record<string, unknown>
  key_locations?: Array<Record<string, unknown>>
  factions?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface StoryArc {
  title?: string
  theme?: string
  goal?: string
  conflict?: string
  summary?: string
  [key: string]: unknown
}

export interface VolumePlanItem {
  volume?: number | string
  title?: string
  focus?: string
  goal?: string
  summary?: string
  [key: string]: unknown
}

export interface NovelOutlineStage {
  stage?: number
  title?: string
  core_theme?: string
  goal?: string
  main_conflict?: string
  background?: string
  character_progression?: string
  world_progression?: string
  faction_progression?: string
  power_progression?: string
  survival_and_life_progression?: string
  cultural_and_civilizational_progression?: string
  resource_and_operation_line?: string
  emotional_core?: string
  major_setpiece?: string
  story_function?: string
  key_events?: string[]
  turning_points?: string[]
  stage_tasks?: string[]
  stage_climax?: string
  foreshadowing_and_payoff?: string
  ending_hook?: string
  expected_chapter_range?: string
  [key: string]: unknown
}

export interface BlueprintForeshadowingItem {
  plant?: unknown
  payoff?: unknown
  owner?: string
  trigger?: string
  summary?: string
  [key: string]: unknown
}

export interface Blueprint {
  title?: string
  target_audience?: string
  genre?: string
  style?: string
  tone?: string
  one_sentence_summary?: string
  full_synopsis?: string
  world_setting?: WorldSetting
  characters?: Character[]
  relationships?: Relationship[]
  story_arcs?: StoryArc[]
  volume_plan?: VolumePlanItem[]
  novel_outline?: NovelOutlineStage[]
  foreshadowing_system?: BlueprintForeshadowingItem[]
  chapter_outline?: ChapterOutline[]
}

export interface Character {
  name: string
  description?: string
  summary?: string
  role?: string
  identity?: string
  archetype?: string
  personality?: string
  goals?: string
  core_motivation?: string
  fear_or_wound?: string
  external_goal?: string
  hidden_secret?: string
  growth_arc?: string
  first_highlight_chapter?: number | string
  relationship_hook?: string
  importance?: 'protagonist' | 'core' | 'supporting' | 'minor' | string
  tags?: string[]
  abilities?: string
  relationship_to_protagonist?: string
  extra?: Record<string, any>
}

export interface Relationship {
  character_from: string
  character_to: string
  description: string
  relation_type?: string
  relationship_type?: string
  status?: string
  current_state?: string
  core_conflict?: string
  tension?: string
  direction?: string
  expected_change?: string
  trigger_event?: string
  key_trigger?: string
  importance?: number
  extra?: Record<string, any>
}

export interface ChapterOutline {
  chapter_number: number
  title: string
  summary: string
  narrative_phase?: string
  chapter_role?: string
  suspense_hook?: string
  emotional_progression?: string
  character_focus?: string[]
  conflict_escalation?: string[]
  continuity_notes?: string[]
  foreshadowing?: {
    plant?: string[]
    payoff?: string[]
  }
  metadata?: Record<string, any>
}

export interface ChapterVersion {
  id?: number
  content: string
  style?: string
  evaluation?: string
  metadata?: Record<string, any>
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content: string | null
  selected_version_id?: number | null
  versions: ChapterVersion[] | null
  evaluation: string | null
  generation_status: 'not_generated' | 'generating' | 'evaluating' | 'selecting' | 'failed' | 'evaluation_failed' | 'waiting_for_confirm' | 'successful'
  word_count?: number
  progress_stage?: 'queued' | 'generating' | 'evaluating' | 'selecting' | 'ready' | 'failed' | string
  progress_message?: string | null
  started_at?: string | null
  updated_at?: string | null
  allowed_actions?: string[]
  last_error_summary?: string | null
  generation_runtime?: GenerationRuntime
}

export interface GenerationRuntimeEvent {
  at?: string
  stage?: string
  level?: 'info' | 'warning' | 'error' | string
  kind?: 'status' | 'content' | 'review' | 'continuity' | 'save' | 'error' | string
  title?: string
  summary?: string
  content_preview?: string
  progress_percent?: number
  metrics?: Record<string, any>
  artifact_refs?: Record<string, any> | Array<Record<string, any>>
  developer_detail?: Record<string, any>
  message?: string
  metadata?: Record<string, any>
}

export interface GenerationRuntime {
  queued?: boolean
  generation_mode?: string
  preset?: string
  version_count?: number
  target_word_count?: number
  min_word_count?: number
  progress_stage?: string
  progress_message?: string
  progress_percent?: number
  estimated_remaining_seconds?: number
  started_at?: string | null
  updated_at?: string | null
  chapter_number?: number
  allowed_actions?: string[]
  last_error_summary?: string | null
  events?: GenerationRuntimeEvent[]
  [key: string]: any
}

export interface WorkspaceSummary {
  total_chapters: number
  completed_chapters: number
  failed_chapters: number
  in_progress_chapters: number
  total_word_count: number
  active_chapter?: number | null
  first_incomplete_chapter?: number | null
  next_chapter_to_generate?: number | null
  can_generate_next: boolean
  available_actions: string[]
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ConverseResponse {
  ai_message: string
  ui_control: UIControl
  conversation_state: any
  is_complete: boolean
  ready_for_blueprint?: boolean
}

export interface BlueprintGenerationResponse {
  blueprint: Blueprint
  ai_message: string
}

export interface BlueprintGenerationError {
  code: string
  message: string
  detail?: string | null
  retryable?: boolean
}

export interface BlueprintGenerationJobResponse {
  run_id: string
  project_id: string
  status: 'idle' | 'queued' | 'generating' | 'polishing' | 'successful' | 'failed' | 'cancelled'
  progress_stage: string
  progress_message: string
  started_at?: string | null
  updated_at?: string | null
  blueprint?: Blueprint | null
  ai_message?: string | null
  error?: BlueprintGenerationError | string | null
}

export interface OutlineGenerationJobResponse {
  run_id: string
  project_id: string
  status:
    | 'idle'
    | 'queued'
    | 'generating'
    | 'outline_context'
    | 'outline_chapter_skeleton'
    | 'outline_rewrite'
    | 'saving'
    | 'successful'
    | 'failed'
    | 'cancelled'
  progress_stage: string
  progress_message: string
  started_at?: string | null
  updated_at?: string | null
  project?: NovelProject | null
  events?: GenerationRuntimeEvent[]
  error?: BlueprintGenerationError | string | null
}

export interface StyleProfileJobResponse {
  run_id: string
  project_id: string
  status: 'idle' | 'queued' | 'extracting' | 'profiling' | 'saving' | 'successful' | 'failed' | 'cancelled'
  progress_stage: string
  progress_message: string
  started_at?: string | null
  updated_at?: string | null
  profile?: any | null
  error?: BlueprintGenerationError | string | null
}

export interface StyleSourceUploadJobResponse {
  run_id: string
  project_id: string
  status:
    | 'idle'
    | 'queued'
    | 'upload_reading'
    | 'upload_extracting'
    | 'upload_saving'
    | 'successful'
    | 'failed'
    | 'cancelled'
  progress_stage: string
  progress_message: string
  started_at?: string | null
  updated_at?: string | null
  filename?: string | null
  source?: any | null
  metrics?: Record<string, any>
  error?: BlueprintGenerationError | string | null
}

export interface NovelImportJobResponse {
  run_id: string
  status:
    | 'idle'
    | 'queued'
    | 'import_reading'
    | 'import_splitting'
    | 'import_sampling'
    | 'import_character_verify'
    | 'import_blueprint_extract'
    | 'import_saving'
    | 'import_ledger_rebuild'
    | 'successful'
    | 'failed'
    | 'cancelled'
  progress_stage: string
  progress_message: string
  started_at?: string | null
  updated_at?: string | null
  filename?: string | null
  project_id?: string | null
  metrics?: Record<string, any>
  error?: BlueprintGenerationError | string | null
}

export interface UIControl {
  type: 'single_choice' | 'multi_choice' | 'text_input'
  options?: Array<{ id: string; label: string }>
  placeholder?: string
}

export interface ChapterGenerationResponse {
  versions: ChapterVersion[]
  evaluation: string | null
  ai_message: string
  chapter_number: number
  generation_runtime?: GenerationRuntime
}

export interface GenerateOutlineOptions {
  targetTotalChapters?: number
  targetTotalWords?: number
  chapterWordTarget?: number
}

export interface GenerateChapterOptions {
  writingNotes?: string
  qualityRequirements?: string
  minWordCount?: number
  targetWordCount?: number
  preset?: 'basic' | 'enhanced' | 'longform' | 'ultimate'
  enableConsistency?: boolean
  enableEnrichment?: boolean
  enableSelfCritique?: boolean
  enableReaderSim?: boolean
  enableMemory?: boolean
  enableForeshadowing?: boolean
  versionCount?: number
  force?: boolean
}

export interface CancelChapterOptions {
  reason?: string
}

export interface RewriteChapterOutlineOptions {
  direction?: string
}

export interface DeleteNovelsResponse {
  status: string
  message: string
}

// ============================================================================
// Section 类型
// ============================================================================

export type NovelSectionType = 'overview' | 'world_setting' | 'novel_outline' | 'characters' | 'relationships' | 'chapter_outline' | 'chapters'

export type AnalysisSectionType =
  | 'emotion_curve'
  | 'foreshadowing'
  | 'knowledge_graph'
  | 'story_trajectory'
  | 'creative_guidance'
  | 'comprehensive_analysis'
  | 'clue_tracker'

export type FeatureEntryType = 'style_learning' | 'memory_management' | 'token_budget' | 'research' | 'clue_tracker' | 'knowledge_graph' | 'foreshadowing'

export type AllSectionType = NovelSectionType | AnalysisSectionType | FeatureEntryType

export interface NovelSectionResponse {
  section: NovelSectionType
  data: Record<string, any>
}

// ============================================================================
// 优化相关类型
// ============================================================================

export interface EmotionBeat {
  primary_emotion: string
  intensity: number
  curve: {
    start: number
    peak: number
    end: number
  }
  turning_point: string
}

export interface OptimizeRequest {
  project_id: string
  chapter_number: number
  dimension:
    | 'dialogue'
    | 'environment'
    | 'psychology'
    | 'rhythm'
  additional_notes?: string
  version_index?: number
  version_id?: number
}

export interface OptimizeResponse {
  optimized_content: string
  optimization_notes: string | string[]
  dimension: string
}

export interface ApplyOptimizationResponse {
  status: string
  message: string
  chapter: Chapter
}

// ============================================================================
// 分析相关类型
// ============================================================================

export interface EnhancedEmotionPoint {
  chapter_number: number
  chapter_id: string
  title: string
  primary_emotion: string
  primary_intensity: number
  secondary_emotions: Array<[string, number]>
  narrative_phase: string
  pace: string
  is_turning_point: boolean
  turning_point_type?: string | null
  description: string
}

export interface StoryTrajectoryAnalysis {
  project_id: string
  project_title: string
  shape: string
  shape_confidence: number
  total_chapters: number
  avg_intensity: number
  intensity_range: [number, number]
  volatility: number
  peak_chapters: number[]
  valley_chapters: number[]
  turning_points: number[]
  description: string
  recommendations: string[]
}

export interface GuidanceItemAnalysis {
  type: string
  priority: string
  title: string
  description: string
  specific_suggestions: string[]
  affected_chapters: number[]
  examples: string[]
}

export interface CreativeGuidanceAnalysis {
  project_id: string
  project_title: string
  current_chapter: number
  overall_assessment: string
  strengths: string[]
  weaknesses: string[]
  guidance_items: GuidanceItemAnalysis[]
  next_chapter_suggestions: string[]
  long_term_planning: string[]
}

export interface ComprehensiveAnalysis {
  project_id: string
  project_title: string
  emotion_points: EnhancedEmotionPoint[]
  trajectory: StoryTrajectoryAnalysis
  guidance: CreativeGuidanceAnalysis
}

// ============================================================================
// 线索追踪类型
// ============================================================================

export interface ForeshadowingItem {
  id: number
  name?: string | null
  chapter_number: number
  content: string
  type: string
  status: string
  target_reveal_chapter?: number | null
  reveal_method?: string | null
  reveal_impact?: string | null
  related_characters?: string[] | null
  related_plots?: string[] | null
  importance?: string | null
  urgency?: number | null
  keywords?: string[] | null
  resolved_chapter_number: number | null
  is_manual: boolean
  ai_confidence: number | null
  author_note: string | null
  created_at: string
}

export interface ForeshadowingListResponse {
  total: number
  limit: number
  offset: number
  data: ForeshadowingItem[]
}

export interface ForeshadowingCreateRequest {
  chapter_id: number
  chapter_number: number
  content: string
  type: string
  keywords?: string[]
  author_note?: string
}

export interface ForeshadowingCreateResponse extends ForeshadowingItem {
  project_id: string
}

export interface ForeshadowingResolveRequest {
  resolved_chapter_id: number
  resolved_chapter_number: number
  resolution_text: string
  resolution_type?: string
  quality_score?: number
}

export interface ForeshadowingResolveResponse {
  status: string
  message: string
  resolution_id: number
}

export interface ForeshadowingReminderItem {
  id: number
  foreshadowing_id: number
  reminder_type: string
  message: string
  status: string
  suggested_chapter_range?: { start?: number; end?: number } | null
  created_at: string
}


// ===== Research Types =====
export interface ResearchConfig {
  mode: "auto" | "manual"
  enabled: boolean
  search_provider: string
  reuse_writing_llm: boolean
  local_model_enabled: boolean
  local_model_name?: string
  local_model_base_url?: string
  local_model_api_key?: string
  max_sources: number
  category_preferences: string[]
}

export interface ResearchArtifact {
  id: string
  project_id: string
  run_id?: string
  title: string
  url?: string
  notes?: string
  source_type: string
  status: "pending" | "completed" | "cancelled" | "interrupted"
  content_preview?: string
  created_at: string
  updated_at: string
}

export interface ResearchRunStatus {
  run_id: string
  status: "running" | "completed" | "failed" | "cancelled"
  progress_percent: number
  message?: string
  artifacts_count: number
  started_at?: string
  completed_at?: string
}
