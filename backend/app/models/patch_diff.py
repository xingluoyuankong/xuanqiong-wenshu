# AIMETA P=PatchDiff模型_Patch和Diff数据模型|R=精细编辑_版本对比|NR=存储编辑记录|E=PatchEdit_DiffLine_ChapterVersionPatch|X=internal|A=ORM模型|D=sqlalchemy|S=none
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

# 自定义列类型：兼容跨数据库环境
BIGINT_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")
LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class DiffChangeType(str, Enum):
    """差异行变更类型"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class PatchEdit(Base):
    """精细编辑记录，存储每次 Patch 的元信息"""

    __tablename__ = "patch_edits"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    original_text: Mapped[str] = mapped_column(LONG_TEXT_TYPE, nullable=False)
    patched_text: Mapped[str] = mapped_column(LONG_TEXT_TYPE, nullable=False)
    patch_operations: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    from_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chapter_versions.id", ondelete="SET NULL"))
    to_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chapter_versions.id", ondelete="SET NULL"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiffLine(Base):
    """差异行，用于返回行级别的差异信息"""

    __tablename__ = "diff_lines"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)
    patch_edit_id: Mapped[int] = mapped_column(ForeignKey("patch_edits.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_line: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)
    patched_line: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False, default=DiffChangeType.UNCHANGED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChapterVersionPatch(Base):
    """章节版本的 Patch 信息"""

    __tablename__ = "chapter_version_patches"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("chapter_versions.id", ondelete="CASCADE"), nullable=False)
    cumulative_patch: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
