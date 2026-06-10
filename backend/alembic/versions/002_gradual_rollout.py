"""Gradual rollout engine

Revision ID: 002
Revises: 001
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("rollout_steps", postgresql.JSONB, nullable=True))
    op.add_column("experiments", sa.Column("current_step_index", sa.Integer, nullable=True))
    op.add_column("experiments", sa.Column("guardrail_metrics", postgresql.JSONB, nullable=True))

    op.create_table(
        "rollout_step_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("traffic_percentage", sa.Integer, nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("triggered_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_rollout_step_logs_experiment_id", "rollout_step_logs", ["experiment_id"])


def downgrade() -> None:
    op.drop_table("rollout_step_logs")
    op.drop_column("experiments", "guardrail_metrics")
    op.drop_column("experiments", "current_step_index")
    op.drop_column("experiments", "rollout_steps")
