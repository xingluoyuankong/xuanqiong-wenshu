from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class ProjectMemberRole(str, Enum):
    """Roles used by the project access layer."""

    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class ProjectMember(Base):
    """Membership grant for a novel project.

    ``NovelProject.user_id`` remains the legacy owner source of truth during the
    migration period.  Rows in this table are additive grants and are filtered by
    ``deleted_at`` rather than physically removed.
    """

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member_project_user"),
        Index("ix_project_members_project_id", "project_id"),
        Index("ix_project_members_user_id", "user_id"),
        Index("ix_project_members_deleted_at", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novel_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ProjectMemberRole.viewer.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=False,
    )

    project: Mapped["NovelProject"] = relationship(
        "NovelProject", back_populates="members"
    )
    user: Mapped["User"] = relationship(
        "User", back_populates="project_members"
    )
