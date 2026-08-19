"""任务运行时 API 的稳定请求/响应契约。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskRuntimeStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STALE = "stale"


class TaskRuntimeEventType(str, Enum):
    TASK_CREATED = "task_created"
    STAGE_CHANGED = "stage_changed"
    PROGRESS = "progress"
    HEARTBEAT = "heartbeat"
    LOG = "log"
    CONTENT_DELTA = "content_delta"
    DIAGNOSTIC = "diagnostic"
    QUALITY_UPDATE = "quality_update"
    CANCEL_REQUESTED = "cancel_requested"
    RETRY_REQUESTED = "retry_requested"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    TASK_STALE = "task_stale"


class TaskRuntimeEventChannel(str, Enum):
    """事件在客户端工作区中的稳定频道。"""

    CONTENT = "content"
    LOG = "log"
    PROGRESS = "progress"
    DIAGNOSTIC = "diagnostic"
    TERMINAL = "terminal"
    TASK_RUNTIME = "task_runtime"


class TaskRuntimeCreate(BaseModel):
    task_type: str = Field(min_length=1, max_length=96)
    idempotency_key: Optional[str] = Field(default=None, max_length=255)
    input_hash: Optional[str] = Field(default=None, max_length=128)
    config_snapshot_id: Optional[str] = Field(default=None, max_length=128)
    artifact_ref: Optional[str] = Field(default=None, max_length=255)
    artifact_revision: Optional[str] = Field(default=None, max_length=128)
    project_id: Optional[str] = Field(default=None, max_length=64)
    chapter_id: Optional[str] = Field(default=None, max_length=64)
    payload: Optional[dict[str, Any]] = None
    max_retries: int = Field(default=3, ge=0, le=100)


class TaskRuntimeProgressUpdate(BaseModel):
    progress: float = Field(ge=0, le=100)
    stage: Optional[str] = Field(default=None, max_length=128)
    message: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    attempt: Optional[int] = Field(default=None, ge=1)
    lease_owner: Optional[str] = Field(default=None, max_length=128)
    lease_generation: Optional[int] = Field(default=None, ge=0)


class TaskRuntimeHeartbeat(BaseModel):
    lease_owner: Optional[str] = Field(default=None, max_length=128)
    lease_generation: Optional[int] = Field(default=None, ge=0)
    attempt: Optional[int] = Field(default=None, ge=1)
    message: Optional[str] = None


class TaskRuntimeClaim(BaseModel):
    lease_owner: str = Field(min_length=1, max_length=128)
    stale_after_seconds: int = Field(default=120, ge=1, le=86400)


class TaskRuntimeMetrics(BaseModel):
    elapsed_ms: Optional[int] = Field(default=None, ge=0)
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)


class TaskRuntimeRetryRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=255)
    message: Optional[str] = None


class TaskRuntimeEventCreate(BaseModel):
    event_type: TaskRuntimeEventType
    status: Optional[TaskRuntimeStatus] = None
    stage: Optional[str] = Field(default=None, max_length=128)
    progress: Optional[float] = Field(default=None, ge=0, le=100)
    message: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=255)
    attempt: Optional[int] = Field(default=None, ge=1)
    lease_owner: Optional[str] = Field(default=None, max_length=128)
    lease_generation: Optional[int] = Field(default=None, ge=0)
    payload: Optional[dict[str, Any]] = None


class TaskRuntimeEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    task_id: str
    event_type: str
    status: Optional[str] = None
    stage: Optional[str] = None
    progress: Optional[float] = None
    message: Optional[str] = None
    idempotency_key: Optional[str] = None
    attempt: int = 1
    lease_generation: int = 0
    channel: Optional[str] = None
    sequence: Optional[int] = None
    payload: Optional[dict[str, Any]] = None
    event_sequence: Optional[int] = None
    created_at: datetime

    @model_validator(mode="after")
    def project_event_envelope(self) -> "TaskRuntimeEventRead":
        """从持久化 payload 投影稳定 envelope，兼容旧事件记录。"""
        payload = self.payload or {}
        if self.channel is None:
            self.channel = payload.get("channel")
        if self.event_sequence is None:
            sequence = payload.get("event_sequence")
            self.event_sequence = sequence if sequence is not None else self.event_id
        return self


class TaskRuntimeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    owner_user_id: Optional[int] = None
    project_id: Optional[str] = None
    chapter_id: Optional[str] = None
    task_type: str
    idempotency_key: Optional[str] = None
    input_hash: Optional[str] = None
    config_snapshot_id: Optional[str] = None
    artifact_ref: Optional[str] = None
    artifact_revision: Optional[str] = None
    status: str
    stage: Optional[str] = None
    progress: float
    message: Optional[str] = None
    event_cursor: int
    retry_count: int
    max_retries: int
    attempt: int = 1
    lease_generation: int = 0
    lease_owner: Optional[str] = None
    heartbeat_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    result_ref: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
