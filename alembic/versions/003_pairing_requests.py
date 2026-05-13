"""Add pairing_requests table

Revision ID: 003
Revises: 002
Create Date: 2024-01-03 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pairing_requests",
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "from_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pairing_code", sa.String(6), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_pr_to_user_status", "pairing_requests", ["to_user_id", "status"])
    op.create_index("ix_pr_from_user_status", "pairing_requests", ["from_user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_pr_from_user_status", table_name="pairing_requests")
    op.drop_index("ix_pr_to_user_status", table_name="pairing_requests")
    op.drop_table("pairing_requests")
