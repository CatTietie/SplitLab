"""User targeting and stratification

Revision ID: 003
Revises: 002
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_attributes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(256), nullable=False),
        sa.Column("attribute_key", sa.String(64), nullable=False),
        sa.Column("attribute_value", sa.String(256), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "attribute_key", name="uq_user_attr"),
    )
    op.create_index("idx_user_attr_user_id", "user_attributes", ["user_id"])
    op.create_index("idx_user_attr_key_value", "user_attributes", ["attribute_key", "attribute_value"])

    op.add_column("experiments", sa.Column("targeting_rules", postgresql.JSONB, nullable=True))
    op.add_column("experiments", sa.Column("stratification_dimensions", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "stratification_dimensions")
    op.drop_column("experiments", "targeting_rules")
    op.drop_index("idx_user_attr_key_value", table_name="user_attributes")
    op.drop_index("idx_user_attr_user_id", table_name="user_attributes")
    op.drop_table("user_attributes")
