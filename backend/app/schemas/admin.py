# AIMETA P=管理员模式_管理API请求响应结构|R=用户管理_统计响应|NR=不含业务逻辑|E=AdminSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Statistics(BaseModel):
    novel_count: int
    api_request_count: int


class DailyRequestLimit(BaseModel):
    limit: int = Field(..., ge=0, description="匿名用户每日可用次数")


class UpdateLogRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    created_by: Optional[str] = None
    is_pinned: bool

    model_config = ConfigDict(from_attributes=True)


class UpdateLogBase(BaseModel):
    content: Optional[str] = None
    is_pinned: Optional[bool] = None


class UpdateLogCreate(UpdateLogBase):
    content: str


class UpdateLogUpdate(UpdateLogBase):
    pass


class AdminNovelSummary(BaseModel):
    id: str
    title: str
    owner_id: int
    owner_username: str
    genre: str
    last_edited: str
    completed_chapters: int
    total_chapters: int


class RootCauseIncident(BaseModel):
    occurred_at: datetime
    source_log: str
    error_type: str
    error_message: str
    root_cause: Optional[str] = None
    request_id: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    stack_excerpt: Optional[str] = None
    hint: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class RootCauseDiagnosticsResponse(BaseModel):
    generated_at: datetime
    scanned_logs: list[str]
    primary_error_type: str
    primary_error_message: str
    root_cause: Optional[str] = None
    request_id: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    occurred_at: Optional[datetime] = None
    source_log: Optional[str] = None
    stack_excerpt: Optional[str] = None
    hint: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    incidents: list[RootCauseIncident] = Field(default_factory=list)


class ChapterRuntimeLogItem(BaseModel):
    chapter_number: int
    chapter_title: Optional[str] = None
    generation_status: str
    word_count: int = 0
    run_id: Optional[str] = None
    progress_stage: str = "not_generated"
    progress_message: str = ""
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    summary_snapshot: Dict[str, Any] = Field(default_factory=dict)
    runtime_snapshot: Dict[str, Any] = Field(default_factory=dict)
    runtime_events: List[Dict[str, Any]] = Field(default_factory=list)


class NovelRuntimeLogItem(BaseModel):
    project_id: str
    project_title: str
    user_id: int
    chapter_count: int = 0
    active_chapter: Optional[int] = None
    updated_at: Optional[datetime] = None
    chapters: List[ChapterRuntimeLogItem] = Field(default_factory=list)
