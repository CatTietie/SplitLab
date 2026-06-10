import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiment_groups.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    event_time: Mapped[datetime] = mapped_column(nullable=False)
    received_at: Mapped[datetime] = mapped_column(default=utcnow)

    __table_args__ = (
        Index("idx_events_experiment_group", "experiment_id", "group_id"),
        Index("idx_events_experiment_event", "experiment_id", "event_name"),
    )
