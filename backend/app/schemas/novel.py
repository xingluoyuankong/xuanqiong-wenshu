# AIMETA P=小说模式_小说和章节请求响应|R=小说结构_章节结构|NR=不含业务逻辑|E=NovelSchema_ChapterSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChoiceOption(BaseModel):
    """前端选择项描述，用于动态 UI 控件。"""

    id: str
    label: str


class UIControl(BaseModel):
    """描述前端应渲染的组件类型与配置。"""

    type: str = Field(..., description="控件类型，如 single_choice/text_input")
    options: Optional[List[ChoiceOption]] = Field(default=None, description="可选项列表")
    placeholder: Optional[str] = Field(default=None, description="输入提示文案")


class ConverseResponse(BaseModel):
    """概念对话接口的统一返回体。"""

    ai_message: str
    ui_control: UIControl
    conversation_state: Dict[str, Any]
    is_complete: bool = False
    ready_for_blueprint: Optional[bool] = None


class ConverseRequest(BaseModel):
    """概念对话接口的请求体。"""

    user_input: Dict[str, Any]
    conversation_state: Dict[str, Any]


class ChapterGenerationStatus(str, Enum):
    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    SELECTING = "selecting"
    FAILED = "failed"
    EVALUATION_FAILED = "evaluation_failed"
    WAITING_FOR_CONFIRM = "waiting_for_confirm"
    SUCCESSFUL = "successful"


class ChapterOutline(BaseModel):
    chapter_number: int
    title: str
    summary: str
    narrative_phase: Optional[str] = None
    chapter_role: Optional[str] = None
    suspense_hook: Optional[str] = None
    emotional_progression: Optional[str] = None
    character_focus: List[str] = Field(default_factory=list)
    conflict_escalation: List[str] = Field(default_factory=list)
    continuity_notes: List[str] = Field(default_factory=list)
    foreshadowing: Dict[str, List[str]] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChapterVersionSchema(BaseModel):
    id: Optional[int] = None
    content: str
    style: Optional[str] = "标准"
    evaluation: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

class Chapter(ChapterOutline):
    real_summary: Optional[str] = None
    content: Optional[str] = None
    versions: Optional[List[ChapterVersionSchema]] = None
    evaluation: Optional[str] = None
    generation_status: ChapterGenerationStatus = ChapterGenerationStatus.NOT_GENERATED
    word_count: int = 0
    progress_stage: str = "not_generated"
    progress_message: str = ""
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    allowed_actions: List[str] = Field(default_factory=list)
    last_error_summary: Optional[str] = None
    generation_runtime: Optional[Dict[str, Any]] = None


class WorkspaceSummary(BaseModel):
    total_chapters: int = 0
    completed_chapters: int = 0
    failed_chapters: int = 0
    in_progress_chapters: int = 0
    total_word_count: int = 0
    active_chapter: Optional[int] = None
    first_incomplete_chapter: Optional[int] = None
    next_chapter_to_generate: Optional[int] = None
    can_generate_next: bool = False
    available_actions: List[str] = Field(default_factory=list)


class Relationship(BaseModel):
    character_from: str
    character_to: str
    description: str
    core_conflict: Optional[str] = None
    relationship_type: Optional[str] = None
    status: Optional[str] = None
    tension: Optional[str] = None
    direction: Optional[str] = None
    trigger_event: Optional[str] = None
    importance: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class Blueprint(BaseModel):
    title: str
    target_audience: str = ""
    genre: str = ""
    style: str = ""
    tone: str = ""
    one_sentence_summary: str = ""
    full_synopsis: str = ""
    world_setting: Dict[str, Any] = Field(default_factory=dict)
    characters: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    story_arcs: List[Dict[str, Any]] = Field(default_factory=list)
    volume_plan: List[Dict[str, Any]] = Field(default_factory=list)
    foreshadowing_system: List[Dict[str, Any]] = Field(default_factory=list)
    chapter_outline: List[ChapterOutline] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NovelProject(BaseModel):
    id: str
    user_id: int
    title: str
    initial_prompt: str
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    blueprint: Optional[Blueprint] = None
    chapters: List[Chapter] = Field(default_factory=list)
    generation_runtime: Optional[Dict[str, Any]] = None
    workspace_summary: Optional[WorkspaceSummary] = None

    model_config = ConfigDict(from_attributes=True)


class NovelProjectSummary(BaseModel):
    id: str
    title: str
    genre: str
    last_edited: str
    completed_chapters: int
    total_chapters: int


class BlueprintGenerationResponse(BaseModel):
    blueprint: Blueprint
    ai_message: str


class ChapterGenerationResponse(BaseModel):
    ai_message: str
    chapter_versions: List[Dict[str, Any]]


class NovelSectionType(str, Enum):
    OVERVIEW = "overview"
    WORLD_SETTING = "world_setting"
    CHARACTERS = "characters"
    RELATIONSHIPS = "relationships"
    CHAPTER_OUTLINE = "chapter_outline"
    CHAPTERS = "chapters"


class NovelSectionResponse(BaseModel):
    section: NovelSectionType
    data: Dict[str, Any]


class GenerateChapterRequest(BaseModel):
    chapter_number: int
    writing_notes: Optional[str] = Field(default=None, description="章节额外写作指令")
    quality_requirements: Optional[str] = Field(default=None, description="章节质量偏好与方向")
    target_word_count: Optional[int] = Field(default=None, description="章节目标字数")
    min_word_count: Optional[int] = Field(default=None, description="章节最低字数")


class FlowConfig(BaseModel):
    preset: str = Field(default="basic", description="basic|enhanced|ultimate|longform|custom")
    versions: Optional[int] = Field(default=None, description="生成版本数量")
    enable_preview: Optional[bool] = Field(default=None, description="是否启用预演生成")
    enable_optimizer: Optional[bool] = Field(default=None, description="是否启用优化器")
    enable_consistency: Optional[bool] = Field(default=None, description="是否启用一致性检查")
    enable_enrichment: Optional[bool] = Field(default=None, description="是否启用字数扩写")
    enable_constitution: Optional[bool] = Field(default=None, description="是否启用宪法式写作约束")
    enable_persona: Optional[bool] = Field(default=None, description="是否启用写作人格/风格约束")
    enable_six_dimension: Optional[bool] = Field(default=None, description="是否启用六维评审")
    enable_reader_sim: Optional[bool] = Field(default=None, description="是否启用读者模拟反馈")
    enable_self_critique: Optional[bool] = Field(default=None, description="是否启用自我批判修订")
    enable_memory: Optional[bool] = Field(default=None, description="是否启用记忆层上下文")
    async_finalize: Optional[bool] = Field(default=None, description="是否异步定稿")
    enable_rag: Optional[bool] = Field(default=None, description="是否启用 RAG")
    rag_mode: Optional[str] = Field(default=None, description="simple|two_stage")
    enable_foreshadowing: Optional[bool] = Field(default=None, description="是否启用伏笔约束")
    enable_faction: Optional[bool] = Field(default=None, description="是否启用势力约束")
    target_word_count: Optional[int] = Field(default=None, description="章节目标字数")
    min_word_count: Optional[int] = Field(default=None, description="章节最低字数，低于该值自动扩写")
    max_enrich_iterations: Optional[int] = Field(default=None, description="自动扩写最大迭代次数")
    allow_truncated_response: Optional[bool] = Field(default=None, description="允许模型触发长度截断时返回部分内容")


class AdvancedGenerateRequest(BaseModel):
    project_id: str
    chapter_number: int
    writing_notes: Optional[str] = Field(default=None, description="章节额外写作指令")
    flow_config: FlowConfig = Field(default_factory=FlowConfig)


class AdvancedGenerateVariant(BaseModel):
    index: int
    version_id: int
    content: str
    metadata: Optional[Dict[str, Any]] = None


class AdvancedGenerateResponse(BaseModel):
    project_id: str
    chapter_number: int
    preset: str
    best_version_index: int
    variants: List[AdvancedGenerateVariant]
    review_summaries: Dict[str, Any] = Field(default_factory=dict)
    debug_metadata: Optional[Dict[str, Any]] = None


class FinalizeChapterRequest(BaseModel):
    project_id: str
    selected_version_id: int
    skip_vector_update: Optional[bool] = Field(default=False, description="是否跳过向量库更新")


class FinalizeChapterResponse(BaseModel):
    project_id: str
    chapter_number: int
    selected_version_id: int
    result: Dict[str, Any]


class SelectVersionRequest(BaseModel):
    chapter_number: int
    version_index: int


class EvaluateChapterRequest(BaseModel):
    chapter_number: int
    version_index: Optional[int] = Field(default=None, description="要评审的版本索引（0-based），不传则使用已选版本或最新版本")
    evaluate_all: bool = Field(default=False, description="是否评审所有版本进行对比（多版本评审模式）")


class CancelChapterRequest(BaseModel):
    chapter_number: int
    reason: Optional[str] = Field(default=None, description="手动终止原因")


class UpdateChapterOutlineRequest(BaseModel):
    chapter_number: int
    title: str
    summary: str


class RewriteChapterOutlineRequest(BaseModel):
    chapter_number: int
    title: str
    summary: str
    direction: Optional[str] = Field(default=None, description="重写方向要求")


class DeleteChapterRequest(BaseModel):
    chapter_numbers: List[int]


class GenerateOutlineRequest(BaseModel):
    start_chapter: int
    num_chapters: int
    target_total_chapters: Optional[int] = Field(default=None, description="全书目标总章节数")
    target_total_words: Optional[int] = Field(default=None, description="全书目标总字数")
    chapter_word_target: Optional[int] = Field(default=None, description="单章目标字数")


class BlueprintPatch(BaseModel):
    one_sentence_summary: Optional[str] = None
    full_synopsis: Optional[str] = None
    world_setting: Optional[Dict[str, Any]] = None
    characters: Optional[List[Dict[str, Any]]] = None
    relationships: Optional[List[Relationship]] = None
    story_arcs: Optional[List[Dict[str, Any]]] = None
    volume_plan: Optional[List[Dict[str, Any]]] = None
    foreshadowing_system: Optional[List[Dict[str, Any]]] = None
    chapter_outline: Optional[List[ChapterOutline]] = None


class EditChapterRequest(BaseModel):
    chapter_number: int
    content: str
