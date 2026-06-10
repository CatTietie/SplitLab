import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class UserAttribute(Base):
    __tablename__ = "user_attributes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    attribute_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute_value: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "attribute_key", name="uq_user_attr"),
        Index("idx_user_attr_user_id", "user_id"),
        Index("idx_user_attr_key_value", "attribute_key", "attribute_value"),
    )
