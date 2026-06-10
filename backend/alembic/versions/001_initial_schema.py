"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_layers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("salt", sa.String(64), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("layer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiment_layers.id"), nullable=False),
        sa.Column("key", sa.String(128), unique=True, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("bucket_start", sa.Integer, nullable=False),
        sa.Column("bucket_end", sa.Integer, nullable=False),
        sa.Column("winner_group_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft','running','paused','full_rollout','archived')", name="chk_exp_status"),
    )

    op.create_table(
        "experiment_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("traffic_percentage", sa.Integer, nullable=False),
        sa.Column("config_json", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("traffic_percentage >= 0 AND traffic_percentage <= 100", name="chk_group_pct"),
    )

    op.create_table(
        "whitelists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiment_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("experiment_id", "user_id", name="uq_whitelist_exp_user"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiment_groups.id"), nullable=False),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("event_name", sa.String(128), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_events_experiment_group", "events", ["experiment_id", "group_id"])
    op.create_index("idx_events_experiment_event", "events", ["experiment_id", "event_name"])

    op.create_table(
        "experiment_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB, nullable=False),
        sa.Column("reason", sa.String(256)),
        sa.Column("created_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("old_value", postgresql.JSONB),
        sa.Column("new_value", postgresql.JSONB),
        sa.Column("performed_by", sa.String(128)),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("experiment_snapshots")
    op.drop_index("idx_events_experiment_event", "events")
    op.drop_index("idx_events_experiment_group", "events")
    op.drop_table("events")
    op.drop_table("whitelists")
    op.drop_table("experiment_groups")
    op.drop_table("experiments")
    op.drop_table("experiment_layers")
