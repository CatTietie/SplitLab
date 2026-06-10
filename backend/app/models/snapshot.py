import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ExperimentSnapshot(Base):
    __tablename__ = "experiment_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=False)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256))
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
