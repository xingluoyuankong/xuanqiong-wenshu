from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class UserStyleLibrary(Base):
    """用户级外部文风素材库与全局应用状态。"""

    __tablename__ = "user_style_libraries"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    style_sources_json: Mapped[Optional[str]] = mapped_column(Text())
    style_profiles_json: Mapped[Optional[str]] = mapped_column(Text())
    global_active_profile_id: Mapped[Optional[str]] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship("User", back_populates="style_library")
