"""008 scheduled signals table

Revision ID: 008
Revises: 007
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scheduled_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("button_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("buttons.button_id", ondelete="SET NULL"), nullable=True),
        sa.Column("button_label", sa.String(200), nullable=True),
        sa.Column("button_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_sent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_scheduled_signals_user_id", "scheduled_signals", ["user_id"])
    op.create_index("ix_scheduled_signals_scheduled_at", "scheduled_signals", ["scheduled_at"])


def downgrade():
    op.drop_table("scheduled_signals")
