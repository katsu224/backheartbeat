"""012 add player_b_id to cadaver_games

Revision ID: 012
Revises: 011
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cadaver_games",
        sa.Column(
            "player_b_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("cadaver_games", "player_b_id")
