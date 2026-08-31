from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkTraceDelta(BaseModel):
    """Public, bounded work trace; never carries hidden reasoning or raw output."""

    trace_id: str = Field(min_length=1, max_length=120)
    run_id: str = Field(min_length=1, max_length=120)
    phase: Literal["observe", "decide", "act", "persist", "replan", "finish", "unknown"] = "unknown"
    action_id: str | None = Field(default=None, max_length=160)
    kind: Literal["status", "progress", "tool", "result", "approval", "error"] = "status"
    message: str = Field(min_length=1, max_length=1000)
    progress: float | None = Field(default=None, ge=0, le=100)
    capability_id: str | None = Field(default=None, max_length=160)
    result_ref: str | None = Field(default=None, max_length=160)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("message")
    @classmethod
    def reject_private_fields(cls, value: str) -> str:
        lowered = value.lower()
        forbidden = ("chain_of_thought", "private_reasoning", "system_prompt", "api_key", "authorization")
        if any(token in lowered for token in forbidden):
            raise ValueError("public work trace message contains a private field")
        return value.strip()


@dataclass(frozen=True)
class WorkTraceProjection:
    trace_id: str
    run_id: str
    sequence: int
    phase: str
    action_id: str | None
    kind: str
    message: str
    progress: float | None
    capability_id: str | None
    result_ref: str | None

    def as_event_data(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "phase": self.phase,
            "action_id": self.action_id,
            "kind": self.kind,
            "message": self.message,
            "progress": self.progress,
            "capability_id": self.capability_id,
            "result_ref": self.result_ref,
        }
