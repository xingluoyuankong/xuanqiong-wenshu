from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base
from .novel import PROJECT_ID_TYPE


class ProjectResearchConfig(Base):
    __tablename__ = "project_research_configs"

    project_id: Mapped[str] = mapped_column(
        PROJECT_ID_TYPE,
        ForeignKey("novel_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    search_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="tavily")
    search_base_url: Mapped[Optional[str]] = mapped_column(Text)
    search_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    research_llm_base_url: Mapped[Optional[str]] = mapped_column(Text)
    research_llm_model: Mapped[Optional[str]] = mapped_column(String(255))
    research_llm_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    reuse_writing_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    local_model_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    global_research_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enhanced_research_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    chapter_research_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_parallel_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    max_results_per_query: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    preferred_domains: Mapped[Optional[list]] = mapped_column(JSON)
    blocked_domains: Mapped[Optional[list]] = mapped_column(JSON)
    category_preferences: Mapped[Optional[list]] = mapped_column(JSON)
    extra: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResearchArtifact(Base):
    __tablename__ = "research_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "run_id", name="uq_research_artifacts_project_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        PROJECT_ID_TYPE,
        ForeignKey("novel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    chapter_number: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    query_plan: Mapped[Optional[list]] = mapped_column(JSON)
    sources: Mapped[Optional[list]] = mapped_column(JSON)
    category_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    file_manifest: Mapped[Optional[dict]] = mapped_column(JSON)
    provider_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[dict]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
