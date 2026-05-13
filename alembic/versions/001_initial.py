"""Initial schema: users, couples, buttons

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("auth_token", sa.Text(), nullable=False),
        sa.Column("fcm_token", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "couples",
        sa.Column("couple_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pairing_code", sa.String(6), nullable=False, unique=True),
        sa.Column(
            "user_a_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_b_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_couples_pairing_code", "couples", ["pairing_code"])

    op.create_table(
        "buttons",
        sa.Column("button_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "couple_id",
            UUID(as_uuid=True),
            sa.ForeignKey("couples.couple_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("video_path", sa.Text(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_buttons_couple_id", "buttons", ["couple_id"])


def downgrade() -> None:
    op.drop_table("buttons")
    op.drop_index("ix_couples_pairing_code", table_name="couples")
    op.drop_table("couples")
    op.drop_table("users")
