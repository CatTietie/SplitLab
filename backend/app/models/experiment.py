import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    layer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiment_layers.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    bucket_start: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket_end: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rollout_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    current_step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guardrail_metrics: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    targeting_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stratification_dimensions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('draft','running','paused','full_rollout','archived')", name="chk_exp_status"),
    )

    layer: Mapped["ExperimentLayer"] = relationship(back_populates="experiments")
    groups: Mapped[list["ExperimentGroup"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")
    whitelists: Mapped[list["Whitelist"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")


class ExperimentGroup(Base):
    __tablename__ = "experiment_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    __table_args__ = (
        CheckConstraint("traffic_percentage >= 0 AND traffic_percentage <= 100", name="chk_group_pct"),
    )

    experiment: Mapped["Experiment"] = relationship(back_populates="groups")


class Whitelist(Base):
    __tablename__ = "whitelists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("experiment_groups.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    __table_args__ = (
        UniqueConstraint("experiment_id", "user_id", name="uq_whitelist_exp_user"),
    )

    experiment: Mapped["Experiment"] = relationship(back_populates="whitelists")


from app.models.layer import ExperimentLayer  # noqa: E402 - resolve forward ref
