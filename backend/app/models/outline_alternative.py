# AIMETA P=剧情演进选项模型_大纲分支存储|R=演进选项CRUD|NR=不含业务逻辑|E=OutlineAlternative|X=internal|A=ORM模型|D=sqlalchemy|S=none|RD=./README.ai
"""
剧情演进选项数据模型

存储每章的多个可能剧情走向，供用户选择后更新大纲。
实现"抽卡式"的大纲演进机制。
"""
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

BIGINT_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")
LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class EvolutionStatus(str, enum.Enum):
    """演进状态"""
    PENDING = "pending"        # 待选择
    SELECTED = "selected"      # 已被选中
    REJECTED = "rejected"      # 被拒绝
    EXPIRED = "expired"        # 已过期


class OutlineAlternative(Base):
    """
    剧情演进选项表

    存储每次调用 evolve API 时生成的所有分支选项。
    用户选择某个选项后，该选项标记为 selected，其他选项标记为 rejected。
    """
    __tablename__ = "outline_alternatives"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)

    # 所属项目
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 关联的章节号（如果是整章演进）
    chapter_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 演进批次ID（同一批生成的所有选项共享一个 batch_id）
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 选项序号（0, 1, 2...）
    option_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # 演进方向标题（如"主角选择冒险"、"主角选择退让"）
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # 演进描述（详细说明这个分支的剧情走向）
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 更新的章节大纲（JSON格式，包含 title, summary 等）
    new_outline: Mapped[Optional[dict]] = mapped_column(JSON)

    # 变更说明（描述这个分支相比原大纲有什么变化）
    changes: Mapped[Optional[str]] = mapped_column(Text)

    # 演进类型：branch（分支剧情）、extend（延伸剧情）、twist（反转剧情）
    evolution_type: Mapped[str] = mapped_column(String(32), default="branch")

    # 置信度/吸引力评分（0-100）
    score: Mapped[Optional[float]] = mapped_column(Integer, nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(
        String(32),
        default=EvolutionStatus.PENDING.value
    )

    # 元数据（存储额外信息，如生成的模型、token消耗等）
    extra: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OutlineEvolutionHistory(Base):
    """
    演进历史记录表

    记录用户每次选择演进的过程，用于回溯和审计。
    """
    __tablename__ = "outline_evolution_history"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)

    # 所属项目
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 演进批次ID
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 被选择的选项ID
    selected_option_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("outline_alternatives.id", ondelete="SET NULL"),
        nullable=True
    )

    # 演进前的章节号
    chapter_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 演进前的章节标题
    previous_title: Mapped[Optional[str]] = mapped_column(String(255))

    # 演进后的章节标题
    new_title: Mapped[Optional[str]] = mapped_column(String(255))

    # 用户ID（记录是谁做的选择）
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())