"""010 add end_seconds to watch_clips

Revision ID: 010
Revises: 009
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("watch_clips", sa.Column("end_seconds", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("watch_clips", "end_seconds")
