# AIMETA P=运行schema状态模型_指纹KV|R=启动schema基线|NR=不执行迁移|E=SchemaState|X=internal|A=ORM模型|D=sqlalchemy|S=db|RD=./README.ai
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class SchemaState(Base):
    """运行时 schema 指纹状态；不替代正式 migration history。"""

    __tablename__ = "app_schema_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())