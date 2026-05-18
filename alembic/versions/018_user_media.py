"""018 add user_media table

Revision ID: 018
Revises: 017
Create Date: 2026-05-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_media",
        sa.Column("media_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_user_media_user_id", "user_media", ["user_id"])
    op.create_index("ix_user_media_media_type", "user_media", ["media_type"])
    op.create_index("ix_user_media_created_at", "user_media", ["created_at"])
    op.create_index(
        "ix_user_media_user_type_created",
        "user_media",
        ["user_id", "media_type", "created_at"],
    )


def downgrade():
    op.drop_index("ix_user_media_user_type_created", table_name="user_media")
    op.drop_index("ix_user_media_created_at", table_name="user_media")
    op.drop_index("ix_user_media_media_type", table_name="user_media")
    op.drop_index("ix_user_media_user_id", table_name="user_media")
    op.drop_table("user_media")
