import uuid
from datetime import datetime, timezone

from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class RolloutStepLog(Base):
    __tablename__ = "rollout_step_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
