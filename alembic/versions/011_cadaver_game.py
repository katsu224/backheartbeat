"""011 add cadaver_games table

Revision ID: 011
Revises: 010
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cadaver_games",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("couple_id", UUID(as_uuid=True),
                  sa.ForeignKey("couples.couple_id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_a_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("head_path", sa.Text, nullable=True),
        sa.Column("body_path", sa.Text, nullable=True),
        sa.Column("is_complete", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("cadaver_games")
