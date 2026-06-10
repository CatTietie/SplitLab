import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ExperimentLayer(Base):
    __tablename__ = "experiment_layers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    experiments: Mapped[list["Experiment"]] = relationship(back_populates="layer", cascade="all, delete-orphan")
