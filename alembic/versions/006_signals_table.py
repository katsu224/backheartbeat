"""Add signals table for history

Revision ID: 006
Revises: 005
Create Date: 2026-05-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sender_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("receiver_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("button_label", sa.Text, nullable=True),
        sa.Column("button_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("bg_color", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_signals_sender_id", "signals", ["sender_id"])
    op.create_index("ix_signals_receiver_id", "signals", ["receiver_id"])
    op.create_index("ix_signals_created_at", "signals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_signals_created_at", "signals")
    op.drop_index("ix_signals_receiver_id", "signals")
    op.drop_index("ix_signals_sender_id", "signals")
    op.drop_table("signals")
