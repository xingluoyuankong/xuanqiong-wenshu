# AIMETA P=模型包初始化_导出所有模型类|R=包标识_模型导出|NR=不含模型实现|E=-|X=internal|A=-|D=none|S=none|RD=./README.ai
"""集中导出 ORM 模型，确保 SQLAlchemy 元数据在初始化时被正确加载。"""

from .admin_setting import AdminSetting
from .llm_config import LLMConfig
from .user_style_library import UserStyleLibrary
from .novel import (
    BlueprintCharacter,
    BlueprintRelationship,
    BlueprintGenerationJob,
    Chapter,
    ChapterEvaluation,
    ChapterOutline,
    ChapterVersion,
    NovelBlueprint,
    NovelConversation,
    NovelProject,
    ProjectLedgerSyncLease,
)
from .prompt import Prompt
from .update_log import UpdateLog
from .usage_metric import UsageMetric
from .user import User
from .user_daily_request import UserDailyRequest
from .system_config import SystemConfig
from .constitution import NovelConstitution
from .outline_alternative import OutlineAlternative, OutlineEvolutionHistory
from .writer_persona import WriterPersona

# 新增：项目记忆模型
from .project_memory import ProjectMemory, ChapterSnapshot

# 新增：章节蓝图模型
from .chapter_blueprint import (
    ChapterBlueprint,
    BlueprintTemplate,
    SuspenseDensity,
    ForeshadowingOp,
    ChapterFunction,
)

# 新增：记忆层模型
from .memory_layer import (
    CharacterState,
    CharacterStateType,
    TimelineEvent,
    CausalChain,
    StoryTimeTracker,
)

# 新增：伏笔模型
from .foreshadowing import (
    Foreshadowing,
    ForeshadowingResolution,
    ForeshadowingReminder,
    ForeshadowingStatusHistory,
    ForeshadowingAnalysis,
)

# 新增：知识图谱模型
from .knowledge_graph import (
    CharacterNode,
    EventEdge,
    KnowledgeGraphMetadata,
)

# 新增：Patch+Diff 精细编辑模型
from .patch_diff import (
    PatchEdit,
    DiffLine,
    ChapterVersionPatch,
    DiffChangeType,
)

# 新增：写作技能模型
from .writing_skill import WritingSkill, SkillExecution

# 新增：Token 预算模型
from .token_budget import TokenBudget, TokenUsage, TokenBudgetAlert

# 新增：线索追踪模型
from .clue_tracker import StoryClue, ClueChapterLink, ClueThread

# 新增：阵营模型
from .faction import Faction, FactionRelationship, FactionMember, FactionRelationshipHistory

# 可恢复任务运行时模型（必须在 Base.metadata.create_all 前导入）
from .task_runtime import TaskRuntime, TaskRuntimeEvent

__all__ = [
    # 基础模型
    "AdminSetting",
    "LLMConfig",
    "UserStyleLibrary",
    "NovelConversation",
    "NovelBlueprint",
    "BlueprintGenerationJob",
    "BlueprintCharacter",
    "BlueprintRelationship",
    "ChapterOutline",
    "Chapter",
    "ChapterVersion",
    "ChapterEvaluation",
    "NovelProject",
    "ProjectLedgerSyncLease",
    "Prompt",
    "UpdateLog",
    "UsageMetric",
    "User",
    "UserDailyRequest",
    "SystemConfig",
    "NovelConstitution",
    "OutlineAlternative",
    "OutlineEvolutionHistory",
    "WriterPersona",
    # 项目记忆模型
    "ProjectMemory",
    "ChapterSnapshot",
    # 章节蓝图模型
    "ChapterBlueprint",
    "BlueprintTemplate",
    "SuspenseDensity",
    "ForeshadowingOp",
    "ChapterFunction",
    # 记忆层模型
    "CharacterState",
    "CharacterStateType",
    "TimelineEvent",
    "CausalChain",
    "StoryTimeTracker",
    # 伏笔模型
    "Foreshadowing",
    "ForeshadowingResolution",
    "ForeshadowingReminder",
    "ForeshadowingStatusHistory",
    "ForeshadowingAnalysis",
    # 知识图谱模型
    "CharacterNode",
    "EventEdge",
    "KnowledgeGraphMetadata",
    # Patch+Diff 模型
    "PatchEdit",
    "DiffLine",
    "ChapterVersionPatch",
    "DiffChangeType",
    # 写作技能模型
    "WritingSkill",
    "SkillExecution",
    # Token 预算模型
    "TokenBudget",
    "TokenUsage",
    "TokenBudgetAlert",
    # 线索追踪模型
    "StoryClue",
    "ClueChapterLink",
    "ClueThread",
    # 阵营模型
    "Faction",
    "FactionRelationship",
    "FactionMember",
    "FactionRelationshipHistory",
    "TaskRuntime",
    "TaskRuntimeEvent",
    "AgentSession",
    "AgentMessage",
    "AgentRun",
    "AgentRunStep",
    "AgentEventRecord",
    "AgentApproval",
    "AgentArtifactRef",
    "AgentRunCommand",
    "AgentJob",
    "AgentCapabilityExecution",
    "AgentRunCapabilitySnapshot",
    "AgentCapabilityDefinition",
    "AgentProviderRelease",
    "AgentCatalogRelease",
    "QualityResult",
    "QualityFinding",
    "QualityGate",
    "ArtifactLineage",
    "ContextSnapshot",
    "ContextSnapshotRef",
    "PlanRevision",
    "ConversationSummary",
]

# Agent 创作工作台持久化模型
from .agent import AgentSession, AgentMessage, AgentRun, AgentRunStep, AgentEventRecord, AgentApproval, AgentArtifactRef, AgentRunCommand, AgentJob

# Agent Catalog/Resolver 关系化模型
from .agent_catalog import (
    AgentCatalogRelease,
    AgentProviderRelease,
    AgentCapabilityDefinition,
    AgentRunCapabilitySnapshot,
    AgentCapabilityExecution,
)

# Agent Quality/Artifact/Lineage 关系化模型
from .agent_quality import QualityResult, QualityFinding, QualityGate
from .agent_lineage import ArtifactLineage

# Agent P1-A context / plan / conversation immutable facts
from .agent_context import ContextSnapshot, ContextSnapshotRef
from .agent_plan import PlanRevision
from .agent_conversation import ConversationSummary
